"""Applying an approved proposal (PRO-02, VOC-07): the only module outside the reference
seeds and the watch pipeline allowed to write a library row (the library fence,
apps/shared/tests_library_fence.py). Every write happens inside `library_write()` naming
the proposal, in the approval's transaction, with its own audit row through `record()`, so
the library change, its audit row and the proposal's decision commit together or not at
all.

Chunk 2 applies the vocabulary and term kinds. Chunk 4 adds instruments, provisions and
obligations, each with a version row rather than an overwrite (playbook 4.3).

`apply_reverification()` is the single exception to "a proposal is the only door"
(INV-06): checking a record against its source changes no fact, so it needs no second
pair of eyes to propose it, only a reviewer's fresh passkey. It stays a stamp. It writes
a Verification row, which is append-only in the database (library 0004), and on
`no_change` it moves `last_verified_at` and `verified_by` on the obligation and nothing
else. The library fence names this function as the one writer the re-verification route
may reach (apps/shared/tests_library_fence.py).

A payload is re-checked here against the library as it is now, not as it was when the
proposal was made: a key someone else created in the meantime is 409 `duplicate_key`, a
retired row cannot be relabelled into life, and a system row is never retired.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from pydantic.alias_generators import to_camel

from apps.library.models import (
    Instrument,
    InstrumentTitle,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
    SubjectType,
    Verification,
    VerificationOutcome,
)
from apps.library.reading import active_obligation, active_provision, live_duty_type, terms_of
from apps.proposals import standards
from apps.proposals.logic import (
    Reviewer,
    as_reviewer,
    merge_pair,
    parsed_payload,
    refuse_vocabulary_change,
    validated_instrument,
    validated_obligation,
    validated_provision,
)
from apps.proposals.models import OriginType, Proposal, ProposalKind
from apps.proposals.schemas import (
    ProposalInstrumentPayload,
    ProposalObligationPayload,
    ProposalObligationVersionPayload,
    ProposalProvisionPayload,
    ProposalProvisionVersionPayload,
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
    ProposalVocabularyCreatePayload,
    ProposalVocabularyMergePayload,
    ProposalVocabularyRelabelPayload,
    ProposalVocabularyRetirePayload,
)
from apps.search.logic import reindex, reindex_provision
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write
from apps.taxonomy import repoint
from apps.taxonomy.models import TaxonomyTerm, TaxonomyTermLabel, TermDimension
from apps.taxonomy.registry import REGISTRY, VocabularyList
from apps.taxonomy.tenant_lists_logic import extra_columns
from apps.taxonomy.terms_logic import refuse_mirrored

ORIGINAL_LANGUAGE = "en"


def apply(proposal: Proposal, *, actor: Actor, reviewer: "Reviewer | Any", step_up: uuid.UUID | None) -> None:
    """Write what the approved `proposal` asks for, as the reviewer corrected it.

    `corrected_payload` is what the reviewer approved and what the library gets; the
    proposal's own `payload` stays as it arrived, so the queue keeps both. `step_up` is the
    assertion the reviewer just made: it goes on every audit row this writes, so the log of
    a library change says which passkey opened the door (ID-06, AC-ID3). It is null for an
    agent's decision, since a key holds no passkey assertion (PRO-S13, D-62, ADR 0054).

    `reviewer` is a `Reviewer` from the API's dual-principal gate, or a bare `User` from an
    older caller (including this app's own tests); `as_reviewer` normalizes either.
    """
    reviewer = as_reviewer(reviewer, actor)
    payload = parsed_payload(proposal.kind, proposal.corrected_payload or proposal.payload)
    with library_write(f"proposal:{proposal.id}", door="proposal"):
        if proposal.kind == ProposalKind.VOCABULARY_CREATE.value:
            assert isinstance(payload, ProposalVocabularyCreatePayload)
            _vocabulary_create(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.VOCABULARY_RELABEL.value:
            assert isinstance(payload, ProposalVocabularyRelabelPayload)
            _vocabulary_relabel(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.VOCABULARY_RETIRE.value:
            assert isinstance(payload, ProposalVocabularyRetirePayload)
            _vocabulary_active(payload, proposal, actor, step_up, active=False)
        elif proposal.kind == ProposalKind.VOCABULARY_RESTORE.value:
            assert isinstance(payload, ProposalVocabularyRetirePayload)
            _vocabulary_active(payload, proposal, actor, step_up, active=True)
        elif proposal.kind == ProposalKind.VOCABULARY_MERGE.value:
            assert isinstance(payload, ProposalVocabularyMergePayload)
            _vocabulary_merge(payload, proposal, actor, step_up)
        elif proposal.kind == ProposalKind.TERM_CREATE.value:
            assert isinstance(payload, ProposalTermCreatePayload)
            _term_create(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.TERM_UPDATE.value:
            assert isinstance(payload, ProposalTermUpdatePayload)
            _term_update(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.NEW_OBLIGATION_VERSION.value:
            assert isinstance(payload, ProposalObligationVersionPayload)
            _obligation_version(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.NEW_INSTRUMENT.value:
            assert isinstance(payload, ProposalInstrumentPayload)
            _new_instrument(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.NEW_OBLIGATION.value:
            assert isinstance(payload, ProposalObligationPayload)
            _new_obligation(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.NEW_PROVISION.value:
            assert isinstance(payload, ProposalProvisionPayload)
            _new_provision(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.NEW_PROVISION_VERSION.value:
            assert isinstance(payload, ProposalProvisionVersionPayload)
            _provision_version(payload, proposal, actor, reviewer, step_up)
        else:
            # Reached by a kind that enters the queue before the apply that writes it
            # exists: an approval of one is refused where the reviewer can see it, never
            # applied in part and never silently ignored.
            raise ValidationError(f"{proposal.kind!r} cannot be applied yet.", code="unknown_key")


def apply_reverification(
    obligation: Obligation,
    *,
    actor: Actor,
    verified_by: Any,
    outcome: str,
    note: str,
    step_up_assertion_id: uuid.UUID,
) -> Verification:
    """Record that a person checked `obligation` against its source (INV-06, INV-S8).

    Every outcome files a Verification row, so the history holds the checks that found a
    change and the ones that could not reach the source, not only the reassuring ones.
    `no_change` also stamps the obligation: the reader's "Verified <date>" means someone
    saw the source say this on that date. Any other outcome leaves the old stamp standing
    and the change itself arrives as a proposal.
    """
    if outcome not in {member.value for member in VerificationOutcome}:
        raise ValidationError(f"{outcome!r} is not a verification outcome.", code="unknown_key")
    stamped = obligation.last_verified_at
    with library_write(f"reverification:obligation:{obligation.id}", door="reverification"):
        verification = Verification.objects.create(
            subject_type=SubjectType.OBLIGATION.value,
            subject_id=obligation.id,
            verified_by=verified_by,
            outcome=outcome,
            note=note.strip(),
        )
        if outcome == VerificationOutcome.NO_CHANGE.value:
            obligation.last_verified_at = verification.verified_at
            obligation.verified_by = verified_by
            obligation.save(update_fields=["last_verified_at", "verified_by"])
        record(
            action="library.reverified",
            actor=actor,
            subject_type=SubjectType.OBLIGATION.value,
            subject_id=obligation.id,
            subject_title=obligation.stable_key,
            summary=f"Re-verified {obligation.stable_key} against its source ({outcome}).",
            tenant_id=None,
            before={"lastVerifiedAt": stamped.isoformat() if stamped else None},
            after={
                "outcome": outcome,
                "verificationId": str(verification.id),
                "lastVerifiedAt": obligation.last_verified_at.isoformat() if obligation.last_verified_at else None,
            },
            step_up_assertion_id=step_up_assertion_id,
        )
    return verification


# ---------------------------------------------------------------------------------------
# New instruments and obligations (INV-01, INV-03, INV-05, PRO-02)
# ---------------------------------------------------------------------------------------
def _verified_origin(reviewer: Reviewer) -> str:
    """Who confirmed the change (INV-05, D-62): an independent agent, or a person. An
    agent's confirmation is machine-confirmed and never reads as a person's."""
    return OriginType.AGENT.value if reviewer.agent_id is not None else OriginType.USER.value


def _new_instrument(
    payload: ProposalInstrumentPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the instrument the proposal asks for, with its official name per language.

    The payload is checked again against the library as it is now, by the same function
    creation ran (`logic.validated_instrument`): a key taken meanwhile is 409
    `duplicate_key`, and a regime that is not a term of the regime dimension is 422
    `not_a_regime` here too, for a proposal stored before the rule (D-39, INV-S12).

    Provenance names both sides: who proposed it (`created_origin`, and the run it was
    found in) and who confirmed it (`verified_origin`, and the confirming agent when an
    agent did). An instrument is not indexed on its own; its obligations and provisions
    are, when they arrive.
    """
    refs, regime = validated_instrument(payload)
    instrument = Instrument.objects.create(
        stable_key=payload.key,
        short_name=payload.short_name,
        official_ref=payload.official_ref,
        eli_uri=payload.eli_uri,
        source_url=proposal.source_url,
        level=refs.level,
        binding=refs.level.binding_default if payload.binding is None else payload.binding,
        jurisdiction=refs.jurisdiction,
        authority=refs.authority,
        regime=regime,
        in_force_from=payload.in_force_from,
        in_force_from_precision=payload.in_force_from_precision,
        in_force_to=payload.in_force_to,
        in_force_to_precision=payload.in_force_to_precision,
        implements_note=payload.implements_note,
        created_origin=proposal.origin,
        created_by_agent_run=proposal.agent_run_id,
        verified_origin=_verified_origin(reviewer),
        verified_by_agent_id=reviewer.agent_id,
    )
    for language, text, is_original, is_machine in _texts(payload.titles, payload.original_language, payload.is_machine, reviewer):
        InstrumentTitle.objects.create(
            instrument=instrument, language_id=language, text=text, is_original=is_original, is_machine=is_machine
        )
    record(
        action="instrument.created",
        actor=actor,
        subject_type=SubjectType.INSTRUMENT.value,
        subject_id=instrument.id,
        subject_title=instrument.stable_key,
        summary=f"Added the instrument {instrument.stable_key} (proposal {proposal.id}).",
        tenant_id=None,
        after={
            "stableKey": instrument.stable_key,
            "regime": payload.regime,
            "level": payload.level,
            "verifiedOrigin": instrument.verified_origin,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _new_obligation(
    payload: ProposalObligationPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the obligation the proposal asks for, with its title, its scope and its first
    version, which names the proposal that filed it (`applied_by_proposal`), so the
    proposing side is read from there as for any later version.

    Checked again by the function creation ran (`logic.validated_obligation`): the
    instrument may have been retired, or the key taken, while the proposal waited. The
    search index moves inside this transaction, so an index that cannot be written takes
    the obligation down with it and leaves the proposal open.

    The standards check runs here too (INV-08, D-35): a standard holds one conformance
    obligation with one standard term, and a law's obligation none. The instrument's row is
    locked first, so two approvals under one standard cannot both find it empty.
    """
    instrument, terms = validated_obligation(payload)
    instrument = Instrument.objects.select_for_update().get(pk=instrument.pk)
    standards.check(
        proposal.kind, instrument, [term.id for term in terms], proposal.field_sources, payload.ref_label, proposal.source_label
    )
    verified_origin = _verified_origin(reviewer)
    obligation = Obligation.objects.create(
        stable_key=payload.key,
        instrument=instrument,
        ref_label=payload.ref_label,
        duty_type=live_duty_type(payload.duty_type),
        created_origin=proposal.origin,
        created_by_agent_run=proposal.agent_run_id,
        created_model=proposal.model,
        source_url=proposal.source_url,
        source_label=proposal.source_label or f"{instrument.official_ref}, {payload.ref_label}",
        verified_origin=verified_origin,
        verified_by_agent_id=reviewer.agent_id,
    )
    for language, text, is_original, is_machine in _texts(payload.titles, payload.original_language, payload.is_machine, reviewer):
        ObligationTitle.objects.create(
            obligation=obligation, language_id=language, text=text, is_original=is_original, is_machine=is_machine
        )
    for term in terms:
        ObligationTerm.objects.create(obligation=obligation, term=term)
    version = ObligationVersion.objects.create(
        obligation=obligation,
        version_number=1,
        effective_from=payload.effective_from,
        effective_from_precision=payload.effective_from_precision,
        caused_by_change=proposal.change_id,
        applied_by_proposal=proposal,
        approved_by=reviewer.user,
        approved_at=timezone.now(),
        verified_origin=verified_origin,
        verified_by_agent_id=reviewer.agent_id,
    )
    for language, text, is_original, is_machine in _texts(payload.summaries, payload.original_language, payload.is_machine, reviewer):
        ObligationSummary.objects.create(version=version, language_id=language, text=text, is_original=is_original, is_machine=is_machine)
    reindex(obligation.id)
    record(
        action="obligation.created",
        actor=actor,
        subject_type=SubjectType.OBLIGATION.value,
        subject_id=obligation.id,
        subject_title=obligation.stable_key,
        summary=f"Added the obligation {obligation.stable_key} under {instrument.stable_key} (proposal {proposal.id}).",
        tenant_id=None,
        after={
            "stableKey": obligation.stable_key,
            "instrument": instrument.stable_key,
            "versionNumber": version.version_number,
            "versionId": str(version.id),
            "effectiveFrom": payload.effective_from.isoformat() if payload.effective_from else None,
            "effectiveFromPrecision": payload.effective_from_precision,
            "languages": sorted(payload.summaries),
            "terms": payload.terms or [],
            "verifiedOrigin": verified_origin,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _texts(texts: dict[str, str], original: str, is_machine: bool, reviewer: Reviewer) -> list[tuple[str, str, bool, bool]]:
    """`(language, text, is_original, is_machine)` per translation row (INV-05): the
    original unlabelled, the others machine-made when the payload says so, and always under
    an agent's approval, which confirms nothing a person would."""
    return [
        (language, text, language == original, language != original and (is_machine or reviewer.user is None))
        for language, text in texts.items()
    ]


# ---------------------------------------------------------------------------------------
# Obligation versions (INV-04, INV-05, PRO-02)
# ---------------------------------------------------------------------------------------
def _scope(obligation: Obligation) -> list[str]:
    """The obligation's scope facets as the payload writes them, in the order a reader
    sees them, so the audit row shows the same spelling the proposal used."""
    return [
        f"{link.term.dimension.key}:{link.term.key}"
        for link in ObligationTerm.objects.filter(obligation=obligation).select_related("term__dimension")
    ]


def _obligation_version(
    payload: ProposalObligationVersionPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the version the proposal asks for, and nothing else (INV-04, PRO-02).

    Nothing is overwritten: the summary in force from a date is a new numbered row with
    its own translations, and every earlier version stays exactly as it was written, which
    is what "as of" and the diff read. The obligation is checked again here, at approval
    time rather than at proposal time, because it may have been retired while the proposal
    waited.

    The scope is the one thing a version replaces rather than adds to: a term list belongs
    to the obligation, not to a version, so when the payload carries one the links are
    rewritten and the audit row holds the scope before and after. A payload without
    `terms` leaves the scope alone, which is not the same as a payload with an empty list.

    The search index moves inside this transaction (`reindex`), so an index that cannot be
    written takes the version down with it and leaves the proposal open.
    """
    # The target is on the proposal, and creation refused one without it (`logic.
    # _validate_obligation_target`); it is read again here against the library as it is
    # now, because the obligation may have been retired while the proposal waited.
    assert proposal.target_id is not None
    # The obligation's row is locked before its highest version is read: a second approval
    # on the same obligation waits here until the first commits, then numbers its version
    # after that one, rather than both claiming one number and the second dying on the
    # unique key (PRO-02; apps/proposals/tests_decide.py, ObligationVersionRaces).
    Obligation.objects.select_for_update().filter(pk=proposal.target_id).exists()
    obligation = active_obligation(proposal.target_id)
    # The scope is resolved and checked before anything is written: a mirrored jurisdiction
    # term is refused here too, for a proposal that entered the queue before the rule did
    # (FP-S12). An empty list clears the scope; `terms_of` is never handed one, because an
    # empty filter matches every term.
    terms = terms_of(payload.terms) if payload.terms else []
    refuse_mirrored(term.dimension_id for term in terms)
    # A payload without `terms` leaves the scope alone, so it asks nothing of the standard
    # term rule; an empty list clears the scope, and is checked as one.
    scope = None if payload.terms is None else [term.id for term in terms]
    standards.check(proposal.kind, obligation.instrument, scope, proposal.field_sources, source_label=proposal.source_label)
    highest = (
        ObligationVersion.objects.filter(obligation=obligation)
        .order_by("-version_number")
        .values_list("version_number", flat=True)
        .first()
    )
    version = ObligationVersion.objects.create(
        obligation=obligation,
        version_number=(highest or 0) + 1,
        effective_from=payload.effective_from,
        effective_from_precision=payload.effective_from_precision,
        caused_by_change=proposal.change_id,
        applied_by_proposal=proposal,
        approved_by=reviewer.user,
        approved_at=timezone.now(),
        # Machine-confirmed provenance (INV-05, INV-06, PRO-02, D-62): an agent's decision
        # names itself here, beside `approved_by` staying null, and never reads as a
        # person's verification. The proposing agent is not repeated on this row: it is
        # read through `applied_by_proposal.proposed_by_agent`, so both agents are named
        # without a second column (chunk4-T26).
        verified_origin=(OriginType.AGENT.value if reviewer.agent_id is not None else OriginType.USER.value),
        verified_by_agent_id=reviewer.agent_id,
    )
    for language, text in payload.summaries.items():
        # The language it was written in is the original; the others are translations, and
        # they stay labelled machine-made until a person confirms them (INV-05, AUD-02). An
        # agent's approval confirms nothing a person would, so under it a translation is
        # machine-made whatever the payload claims.
        is_original = language == payload.original_language
        ObligationSummary.objects.create(
            version=version,
            language_id=language,
            text=text,
            is_original=is_original,
            is_machine=not is_original and (payload.is_machine or reviewer.user is None),
        )
    scope_before = scope_after = None
    if payload.terms is not None:
        scope_before = _scope(obligation)
        ObligationTerm.objects.filter(obligation=obligation).delete()
        for term in terms:
            ObligationTerm.objects.create(obligation=obligation, term=term)
        scope_after = _scope(obligation)
    reindex(obligation.id)
    record(
        action="obligation.version_applied",
        actor=actor,
        subject_type="obligation",
        subject_id=obligation.id,
        subject_title=obligation.stable_key,
        summary=f"Filed version {version.version_number} of {obligation.stable_key} (proposal {proposal.id}).",
        tenant_id=None,
        before={"versionNumber": highest, "terms": scope_before},
        after={
            "versionNumber": version.version_number,
            "versionId": str(version.id),
            "effectiveFrom": payload.effective_from.isoformat() if payload.effective_from else None,
            "effectiveFromPrecision": payload.effective_from_precision,
            "languages": sorted(payload.summaries),
            "terms": scope_after,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


# ---------------------------------------------------------------------------------------
# Provisions (INV-02, INV-08, PRO-02)
# ---------------------------------------------------------------------------------------
def _provision_texts(
    version: ProvisionVersion, payload: ProposalProvisionPayload | ProposalProvisionVersionPayload, reviewer: Reviewer
) -> None:
    for language, text, is_original, is_machine in _texts(payload.texts, payload.original_language, payload.is_machine, reviewer):
        ProvisionText.objects.create(version=version, language_id=language, text=text, is_original=is_original, is_machine=is_machine)


def _new_provision(
    payload: ProposalProvisionPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the provision the proposal asks for, with its first verbatim text, which names
    the proposal that filed it.

    Checked again by the function creation ran (`logic.validated_provision`) and by the
    standards check: a standard's text is licensed (422 `licensed_text`), and the trigger
    `provision_not_under_standard` refuses the row on its own if this is ever bypassed. The
    instrument is locked first, so a level merge re-pointing it waits for this insert, or
    this insert reads the level the merge left (H25). The index moves in this transaction,
    so a failed re-index writes nothing.
    """
    instrument, parent, kind = validated_provision(payload)
    # Locked and read again before the check: a level merge moving this instrument onto a
    # standard holds the row, and `provision_not_under_standard` would otherwise read the
    # level as it was before that merge committed (H25).
    instrument = Instrument.objects.select_for_update().get(pk=instrument.pk)
    standards.check(proposal.kind, instrument, None, proposal.field_sources, source_label=proposal.source_label)
    provision = Provision.objects.create(
        stable_key=payload.key,
        instrument=instrument,
        parent=parent,
        kind=kind,
        ref_label=payload.ref_label,
        heading=payload.heading,
        path=f"{parent.path if parent else instrument.short_name} > {payload.ref_label}",
        sort_order=payload.sort_order,
    )
    version = ProvisionVersion.objects.create(
        provision=provision,
        version_number=1,
        effective_from=payload.effective_from,
        effective_from_precision=payload.effective_from_precision,
        applied_by_proposal=proposal,
    )
    _provision_texts(version, payload, reviewer)
    reindex_provision(provision.id)
    record(
        action="provision.created",
        actor=actor,
        subject_type=SubjectType.PROVISION.value,
        subject_id=provision.id,
        subject_title=provision.stable_key,
        summary=f"Added the provision {provision.stable_key} under {instrument.stable_key} (proposal {proposal.id}).",
        tenant_id=None,
        after={
            "stableKey": provision.stable_key,
            "instrument": instrument.stable_key,
            "versionNumber": version.version_number,
            "versionId": str(version.id),
            "languages": sorted(payload.texts),
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _provision_version(
    payload: ProposalProvisionVersionPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the text of a provision in force from a date, and nothing else (INV-02): every
    earlier version stays as it was written. The provision is read again, and locked, so a
    retired one is refused and two approvals number their versions one after the other."""
    assert proposal.target_id is not None
    Provision.objects.select_for_update().filter(pk=proposal.target_id).exists()
    provision = active_provision(proposal.target_id)
    standards.check(proposal.kind, provision.instrument, None, proposal.field_sources, source_label=proposal.source_label)
    highest = (
        ProvisionVersion.objects.filter(provision=provision)
        .order_by("-version_number")
        .values_list("version_number", flat=True)
        .first()
    )
    version = ProvisionVersion.objects.create(
        provision=provision,
        version_number=(highest or 0) + 1,
        effective_from=payload.effective_from,
        effective_from_precision=payload.effective_from_precision,
        applied_by_proposal=proposal,
    )
    _provision_texts(version, payload, reviewer)
    reindex_provision(provision.id)
    record(
        action="provision.version_applied",
        actor=actor,
        subject_type=SubjectType.PROVISION.value,
        subject_id=provision.id,
        subject_title=provision.stable_key,
        summary=f"Filed version {version.version_number} of {provision.stable_key} (proposal {proposal.id}).",
        tenant_id=None,
        before={"versionNumber": highest},
        after={
            "versionNumber": version.version_number,
            "versionId": str(version.id),
            "effectiveFrom": payload.effective_from.isoformat() if payload.effective_from else None,
            "effectiveFromPrecision": payload.effective_from_precision,
            "languages": sorted(payload.texts),
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


# ---------------------------------------------------------------------------------------
# Vocabulary rows
# ---------------------------------------------------------------------------------------
def _entry(name: str, kind: str, keys: list[str]) -> VocabularyList:
    """The library list a vocabulary proposal names, with the rules its change obeys checked
    again for the list as it is now (`logic.refuse_vocabulary_change`): a proposal filed
    before a rule existed may still wait in the queue."""
    entry = REGISTRY[name]
    if not entry.is_library:  # pragma: no cover - logic.validated_payload refused it
        raise ValidationError(f"{name!r} is a tenant list; its admin writes it.", code="unknown_key")
    refuse_vocabulary_change(entry, kind, keys)
    return entry


def _row(entry: VocabularyList, key: str) -> Any:
    """The row `key` names, locked: an approval reads it and saves it whole, so a second
    approval on the same row waits and then reads what the first wrote, rather than writing
    back over its stamp and its version bump (H34)."""
    row = entry.model._default_manager.select_for_update().filter(key=key).order_by("sort_order", "key").first()
    if row is None:
        raise ValidationError(f"{key!r} is not a row of {entry.name!r}.", code="not_found")
    return row


def _confirmation(proposal: Proposal, reviewer: Reviewer) -> dict[str, Any]:
    """Who confirmed the wording an approval writes on a list row or a term (INV-05, PRO-02,
    D-62, D-79), as the columns `LibraryVocabulary` and `TaxonomyTerm` hold it: `agent` and
    the confirming agent when an independent agent approved, `user` and no agent when a
    person did. The proposing agent is read through the proposal, as an obligation
    version's is."""
    return {
        "verified_origin": (OriginType.AGENT if reviewer.agent_id is not None else OriginType.USER).value,
        "verified_by_agent_id": reviewer.agent_id,
        "applied_by_proposal": proposal,
    }


def _restamp(
    row: Any, proposal: Proposal, reviewer: Reviewer, labels: QuerySet[Any], *, usage_note_written: bool
) -> None:
    """Stamp an existing list row or term with the approval that just wrote some of its
    wording (INV-05, D-62). Only a relabel or a term update that writes labels, a usage
    note or one of the row's own columns calls this: a sort order, a retire, a restore or a
    merge writes no wording, and the row keeps the stamp it had.

    A row is reworded in place, a piece at a time, so a person's approval stamps `user`
    only once nothing the agents confirmed is left on it. While a label is still
    machine-made, or the row keeps a usage note this approval did not rewrite (the row
    cannot tell who wrote it), an agent-stamped row keeps naming the agents and the
    proposal they confirmed, so their wording never reads as a person's check. `labels` is
    the row's label queryset, read after this approval wrote its labels."""
    if (
        reviewer.agent_id is None
        and row.verified_origin == OriginType.AGENT.value
        and (labels.filter(is_machine=True).exists() or (row.usage_note and not usage_note_written))
    ):
        return
    for name, value in _confirmation(proposal, reviewer).items():
        setattr(row, name, value)


def _write_labels(entry: VocabularyList, row: Any, labels: dict[str, str], reviewer: Reviewer) -> None:
    """Write `labels` onto a list row. Every label an agent's approval writes, the original
    included, is machine-made, and an agent never clears the mark; a person's approval
    confirms exactly the labels it writes (INV-05, D-12, D-62). A row is relabelled in
    place, so each label carries its own mark rather than leaning on the row's stamp."""
    machine = reviewer.agent_id is not None
    existing = {label.language: label for label in entry.label_model._default_manager.filter(vocabulary=row)}
    original = None
    if not any(label.is_original for label in existing.values()):
        original = ORIGINAL_LANGUAGE if ORIGINAL_LANGUAGE in labels else next(iter(labels), None)
    for language, text in labels.items():
        label = existing.get(language)
        if label is not None:
            label.text = text
            label.is_machine = machine
            label.save(update_fields=["text", "is_machine"])
        else:
            entry.label_model._default_manager.create(
                vocabulary=row, language=language, text=text, is_original=language == original, is_machine=machine
            )


def _vocabulary_create(
    payload: ProposalVocabularyCreatePayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    entry = _entry(payload.list, proposal.kind, [payload.key])
    if entry.model._default_manager.filter(key__iexact=payload.key).exists():
        raise ValidationError(f"{payload.key!r} already exists on {payload.list!r}.", code="duplicate_key")
    highest = entry.model._default_manager.order_by("-sort_order").values_list("sort_order", flat=True).first()
    fields: dict[str, Any] = {
        "key": payload.key,
        "kind": payload.kind if entry.kinds else None,
        "usage_note": payload.usage_note,
        "sort_order": payload.sort_order if payload.sort_order is not None else (0 if highest is None else highest + 1),
        "active": True,
        "is_system": False,
        "is_default": False,
        **_confirmation(proposal, reviewer),
    }
    fields.update(extra_columns(entry, payload.extra))
    row = entry.model._default_manager.create(**fields)
    _write_labels(entry, row, payload.labels, reviewer)
    record(
        action="vocabulary.created",
        actor=actor,
        subject_type="vocabulary",
        subject_id=row.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"Added {payload.key} to {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        after={"list": payload.list, "key": payload.key, "labels": payload.labels, "proposal": str(proposal.id)},
        step_up_assertion_id=step_up,
    )


def _vocabulary_relabel(
    payload: ProposalVocabularyRelabelPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    entry = _entry(payload.list, proposal.kind, [payload.key])
    row = _row(entry, payload.key)
    before = {label.language: label.text for label in entry.label_model._default_manager.filter(vocabulary=row)}
    if payload.labels:
        _write_labels(entry, row, payload.labels, reviewer)
    if payload.usage_note is not None:
        row.usage_note = payload.usage_note
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    # A row's own columns are facts the rules read (a level's binding default, a dimension's
    # footprint rule), so a change to one is stamped as wording is and audited both ways.
    columns = extra_columns(entry, payload.extra)
    was = {to_camel(name): getattr(getattr(row, name), "key", getattr(row, name)) for name in columns}
    for name, value in columns.items():
        setattr(row, name, value)
    if payload.labels or payload.usage_note is not None or columns:
        _restamp(
            row,
            proposal,
            reviewer,
            entry.label_model._default_manager.filter(vocabulary=row),
            usage_note_written=payload.usage_note is not None,
        )
    row.version += 1
    row.save()
    if isinstance(row, Jurisdiction):
        _mirrored_term_follows(row, payload.labels, payload.sort_order, proposal, actor, reviewer, step_up)
    record(
        action="vocabulary.updated",
        actor=actor,
        subject_type="vocabulary",
        subject_id=row.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"Changed {payload.key} on {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        before={"labels": before, **({"extra": was} if columns else {})},
        after={
            "labels": {**before, **payload.labels},
            **({"extra": {to_camel(name): getattr(value, "key", value) for name, value in columns.items()}} if columns else {}),
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _vocabulary_active(payload: ProposalVocabularyRetirePayload, proposal: Proposal, actor: Actor, step_up: uuid.UUID | None, *, active: bool) -> None:
    entry = _entry(payload.list, proposal.kind, [payload.key])
    row = _row(entry, payload.key)
    # On a list of fixed keys every row is the seed's, so being seeded cannot be what keeps a
    # row: retiring is how a market leaves (D-94).
    if not active and row.is_system and not entry.fixed_keys:
        raise ValidationError(f"{payload.key} is a system value: it can be relabelled but not retired.", code="system_row")
    if row.active == active:
        raise ValidationError(
            f"{payload.key} is already {'active' if active else 'retired'}.", code="invalid_transition"
        )
    row.active = active
    row.version += 1
    row.save(update_fields=["active", "version"])
    if isinstance(row, Jurisdiction):
        _mirrored_term_follows(row, {}, None, proposal, actor, None, step_up)
    record(
        action="vocabulary.restored" if active else "vocabulary.retired",
        actor=actor,
        subject_type="vocabulary",
        subject_id=row.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"{'Restored' if active else 'Retired'} {payload.key} on {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        before={"active": not active},
        after={"active": active, "proposal": str(proposal.id)},
        step_up_assertion_id=step_up,
    )


def _vocabulary_merge(payload: ProposalVocabularyMergePayload, proposal: Proposal, actor: Actor, step_up: uuid.UUID | None) -> None:
    entry = _entry(payload.list, proposal.kind, [payload.key, payload.into])
    source, target = merge_pair(entry, payload.key, payload.into, lock=True)
    if source.is_system:
        raise ValidationError(f"{payload.key} is a system value: it can be relabelled but not merged away.", code="system_row")
    # Every current row holding the source moves to the target in this transaction; the
    # source row itself stays, retired, so versions, audit rows and old labels resolve. A
    # record the database refuses to move (a standard's level on an instrument holding
    # provisions) undoes every move before it and leaves the proposal open.
    try:
        with transaction.atomic():
            moved = repoint.move(entry.links, source, target, library=_repoint_rows)
    except IntegrityError as refused:
        raise ValidationError(
            f"{payload.key} cannot be merged into {payload.into}: a record that carries it cannot take {payload.into}.",
            code="invalid_transition",
        ) from refused
    source.active = False
    source.version += 1
    source.save(update_fields=["active", "version"])
    record(
        action="vocabulary.merged",
        actor=actor,
        subject_type="vocabulary",
        subject_id=source.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"Merged {payload.key} into {payload.into} on {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        before={"from": payload.key, "active": True},
        after={
            "into": payload.into,
            "repointed": repoint.count(moved),
            "moved": {table: len(rows.moved) for table, rows in moved.items()},
            "rows": repoint.audit_rows(moved),
            "active": False,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _mirrored_term_follows(
    row: Jurisdiction,
    labels: dict[str, str],
    sort_order: int | None,
    proposal: Proposal,
    actor: Actor,
    reviewer: Reviewer | None,
    step_up: uuid.UUID | None,
) -> None:
    """The term that mirrors a jurisdiction takes what the approval just wrote on the row, in
    the same transaction (FP-04, D-28, D-94): the labels, marked and stamped as a term
    update's are, the sort order, and whether it is active. No proposal may change a mirrored
    term itself (FP-S12), so this is the one way its wording moves after the seed filed it;
    the seed puts back only its link, its parent and `active` (apps/taxonomy/seeds). A
    jurisdiction with no mirrored term (International, D-38) changes alone. `reviewer` is
    needed only when there are labels to write."""
    terms = TaxonomyTerm.objects.select_for_update(of=("self",)).select_related("dimension").filter(jurisdiction=row).order_by("id")
    for term in terms:
        if not labels and sort_order is None and term.active == row.active:
            continue
        before = {label.language: label.text for label in TaxonomyTermLabel.objects.filter(term=term)}
        was_active = term.active
        if labels and reviewer is not None:
            _term_labels(term, labels, reviewer)
            _restamp(term, proposal, reviewer, TaxonomyTermLabel.objects.filter(term=term), usage_note_written=False)
        if sort_order is not None:
            term.sort_order = sort_order
        term.active = row.active
        term.version += 1
        term.save()
        record(
            action="taxonomy.term_updated",
            actor=actor,
            subject_type="taxonomy_term",
            subject_id=term.id,
            subject_title=f"{term.dimension.key}:{term.key}",
            summary=f"The term {term.key} in {term.dimension.key} followed the jurisdiction {row.key} (proposal {proposal.id}).",
            tenant_id=None,
            before={"labels": before, "active": was_active},
            after={"labels": {**before, **labels}, "active": term.active, "proposal": str(proposal.id)},
            step_up_assertion_id=step_up,
        )


def _repoint_rows(moving: Any, twins: Any, field: str, target: Any) -> int:
    """The inventory half of a merge's re-point, inside the approval's `library_write()`: a
    row whose twin already holds the target is dropped (a unique constraint), every other
    row moves, and only the moved rows count. Watch tables go through their own door."""
    twins.delete()
    return int(moving.update(**{field: target}))


# ---------------------------------------------------------------------------------------
# Taxonomy terms
# ---------------------------------------------------------------------------------------
def _dimension(key: str) -> TermDimension:
    dimension = TermDimension.objects.filter(key=key, active=True).order_by("sort_order", "key").first()
    if dimension is None:
        raise ValidationError(f"{key!r} is not a taxonomy dimension.", code="unknown_key")
    return dimension


def _term_labels(term: TaxonomyTerm, labels: dict[str, str], reviewer: Reviewer) -> None:
    """A term's labels, marked exactly as a list row's are (`_write_labels`)."""
    machine = reviewer.agent_id is not None
    existing = {label.language: label for label in TaxonomyTermLabel.objects.filter(term=term)}
    original = None
    if not any(label.is_original for label in existing.values()):
        original = ORIGINAL_LANGUAGE if ORIGINAL_LANGUAGE in labels else next(iter(labels), None)
    for language, text in labels.items():
        label = existing.get(language)
        if label is not None:
            label.text = text
            label.is_machine = machine
            label.save(update_fields=["text", "is_machine"])
        else:
            TaxonomyTermLabel.objects.create(
                term=term, language=language, text=text, is_original=language == original, is_machine=machine
            )


def _term_create(
    payload: ProposalTermCreatePayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    dimension = _dimension(payload.dimension)
    refuse_mirrored([dimension.id])
    if TaxonomyTerm.objects.filter(dimension=dimension, key__iexact=payload.key).exists():
        raise ValidationError(f"{payload.key!r} already exists in {payload.dimension!r}.", code="duplicate_key")
    parent = None
    if payload.parent:
        parent = TaxonomyTerm.objects.filter(dimension=dimension, key=payload.parent).order_by("sort_order", "key").first()
        if parent is None:
            raise ValidationError(f"{payload.parent!r} is not a term of {payload.dimension!r}.", code="unknown_key")
    highest = (
        TaxonomyTerm.objects.filter(dimension=dimension).order_by("-sort_order").values_list("sort_order", flat=True).first()
    )
    term = TaxonomyTerm.objects.create(
        dimension=dimension,
        key=payload.key,
        parent=parent,
        usage_note=payload.usage_note,
        sort_order=0 if highest is None else highest + 1,
        active=True,
        is_system=False,
        **_confirmation(proposal, reviewer),
    )
    _term_labels(term, payload.labels, reviewer)
    record(
        action="taxonomy.term_created",
        actor=actor,
        subject_type="taxonomy_term",
        subject_id=term.id,
        subject_title=f"{payload.dimension}:{payload.key}",
        summary=f"Added the term {payload.key} to {payload.dimension} (proposal {proposal.id}).",
        tenant_id=None,
        after={"dimension": payload.dimension, "key": payload.key, "labels": payload.labels, "proposal": str(proposal.id)},
        step_up_assertion_id=step_up,
    )


def _term_update(
    payload: ProposalTermUpdatePayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    dimension = _dimension(payload.dimension)
    refuse_mirrored([dimension.id])
    # Locked, as a list row is in `_row` (H34).
    term = TaxonomyTerm.objects.select_for_update().filter(dimension=dimension, key=payload.key).order_by("sort_order", "key").first()
    if term is None:
        raise ValidationError(f"{payload.key!r} is not a term of {payload.dimension!r}.", code="not_found")
    before = {label.language: label.text for label in TaxonomyTermLabel.objects.filter(term=term)}
    if payload.labels:
        _term_labels(term, payload.labels, reviewer)
    if payload.usage_note is not None:
        term.usage_note = payload.usage_note
    if payload.sort_order is not None:
        term.sort_order = payload.sort_order
    if payload.labels or payload.usage_note is not None:
        _restamp(
            term, proposal, reviewer, TaxonomyTermLabel.objects.filter(term=term), usage_note_written=payload.usage_note is not None
        )
    term.version += 1
    term.save()
    record(
        action="taxonomy.term_updated",
        actor=actor,
        subject_type="taxonomy_term",
        subject_id=term.id,
        subject_title=f"{payload.dimension}:{payload.key}",
        summary=f"Changed the term {payload.key} in {payload.dimension} (proposal {proposal.id}).",
        tenant_id=None,
        before={"labels": before},
        after={"labels": {**before, **payload.labels}, "proposal": str(proposal.id)},
        step_up_assertion_id=step_up,
    )
