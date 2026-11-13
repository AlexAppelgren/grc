"""Applying an approved proposal (PRO-02, VOC-07): the only module outside the reference
seeds and the watch pipeline allowed to write a library row (the library fence,
apps/shared/tests_library_fence.py). Every write happens inside `library_write()` naming
the proposal, in the approval's transaction, with its own audit row through `record()`, so
the library change, its audit row and the decision commit together or not at all. Records
get a version row rather than an overwrite (playbook 4.3).

`apply_reverification()` is the single exception to "a proposal is the only door"
(INV-06): checking a record against its source changes no fact, so it needs only a
reviewer's fresh passkey. It writes an append-only Verification row and, on `no_change`,
moves `last_verified_at` and `verified_by` and nothing else.

A payload is re-checked here against the library as it is now: a key taken meanwhile is 409
`duplicate_key`, a retired row cannot be relabelled into life, and a system row is never
retired.
"""

from __future__ import annotations

import contextlib
import functools
import operator
import uuid
from collections.abc import Iterator, Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from pydantic.alias_generators import to_camel

from apps.library.models import (
    Instrument,
    InstrumentSummary,
    InstrumentTitle,
    Jurisdiction,
    Obligation,
    ObligationProvision,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
    RecurringDuty,
    SubjectType,
    Verification,
    VerificationOutcome,
)
from apps.library.reading import active_obligation, active_shared_obligations, live_duty_type, obligation_scope_terms, terms_of
from apps.proposals import private_controls, standards
from apps.proposals.logic import (
    Reviewer,
    as_reviewer,
    merge_pair,
    parsed_payload,
    refuse_vocabulary_change,
    validated_instrument,
    PRIVATE_RECORD_KINDS,
    validated_obligation,
    validated_instrument_summary,
    validated_provision,
    validated_provision_version,
    validated_recurring_duty,
    validated_translations,
)
from apps.proposals.models import OriginType, Proposal, ProposalBatchRow, ProposalKind
from apps.proposals.schemas import (
    ObligationScopePayload,
    ProposalControlPayload,
    ProposalInstrumentPayload,
    ProposalInstrumentSummaryPayload,
    ProposalObligationPayload,
    ProposalObligationVersionPayload,
    ProposalProvisionPayload,
    ProposalProvisionVersionPayload,
    ProposalRecurringDutyPayload,
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
    ProposalTranslationsPayload,
    ProposalVocabularyCreatePayload,
    ProposalVocabularyMergePayload,
    ProposalVocabularyRelabelPayload,
    ProposalVocabularyRetirePayload,
)
from apps.search.logic import reindex, reindex_obligations, reindex_provision
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write
from apps.shared.vocabulary import write_labels
from apps.taxonomy import repoint
from apps.taxonomy.models import TaxonomyTerm, TaxonomyTermLabel, TermDimension
from apps.taxonomy.registry import REGISTRY, VocabularyList
from apps.taxonomy.tenant_lists_logic import extra_columns
from apps.taxonomy.terms_logic import refuse_mirrored


def apply(
    proposal: Proposal,
    *,
    actor: Actor,
    reviewer: "Reviewer | Any",
    step_up: uuid.UUID | None,
    rows: Sequence[ProposalBatchRow] = (),
) -> None:
    """Write what the approved `proposal` asks for, as the reviewer corrected it.

    A batch (PRO-04) is applied by its approved `rows`, every one checked before any is
    written; a single proposal takes none. `corrected_payload` is what the library gets;
    the proposal's own `payload` stays as it arrived. `step_up` goes on every audit row, so
    the log says which passkey opened the door (ID-06, AC-ID3); it is null for an agent's
    decision (PRO-S13, D-62, ADR 0054). `reviewer` is a `Reviewer` or a bare `User`;
    `as_reviewer` normalizes either.
    """
    reviewer = as_reviewer(reviewer, actor)
    stored = proposal.corrected_payload or proposal.payload
    # A batch's payload is filed by apps/proposals/batch.py, never through the single
    # proposal's kinds, so its schema is named here rather than in `PAYLOAD_SCHEMAS`.
    batched = proposal.kind == ProposalKind.OBLIGATION_SCOPE.value
    payload = ObligationScopePayload.model_validate(stored) if batched else parsed_payload(proposal.kind, stored)
    if proposal.owner_tenant_id is not None and proposal.kind not in PRIVATE_RECORD_KINDS:
        # Creation files nothing else as a bank's own (`logic.owner_of`); a row that says
        # otherwise is refused rather than written into either zone.
        raise ValidationError(f"{proposal.kind!r} is never a record of an organisation's own.", code="validation_error")
    if proposal.kind == ProposalKind.NEW_CONTROL.value:
        # A control writes no library row (OWN-05, D-99): it is the bank's own internal item,
        # written in the bank's zone outside the library's door, and decided by a person.
        assert isinstance(payload, ProposalControlPayload)
        if reviewer.user is None:
            raise ValidationError("A control is approved by a person, never by an agent.", code="person_review_required")
        private_controls.apply_control(proposal, payload, actor=actor, reviewer_id=reviewer.user.id, step_up=step_up)
        return
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
        elif proposal.kind == ProposalKind.NEW_INSTRUMENT_SUMMARY.value:
            assert isinstance(payload, ProposalInstrumentSummaryPayload)
            _new_instrument_summary(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.NEW_TRANSLATIONS.value:
            assert isinstance(payload, ProposalTranslationsPayload)
            _new_translations(payload, proposal, actor, step_up)
        elif proposal.kind == ProposalKind.NEW_RECURRING_DUTY.value:
            assert isinstance(payload, ProposalRecurringDutyPayload)
            _new_recurring_duty(payload, proposal, actor, reviewer, step_up)
        elif proposal.kind == ProposalKind.OBLIGATION_SCOPE.value:
            assert isinstance(payload, ObligationScopePayload)
            _obligation_scope(payload, rows, proposal, actor, step_up)
        else:
            # A kind that enters the queue before its apply exists is refused where the
            # reviewer sees it, never applied in part or silently ignored.
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


# --- New instruments and obligations (INV-01, INV-03, INV-05, PRO-02) ---
@contextlib.contextmanager
def _key_free_in_every_zone(subject: str) -> Iterator[None]:
    """A stable key is unique across the library, both zones (the database's unique index),
    while `stable_key_taken` reads under row-level security and sees the caller's zone
    alone. A key another zone holds is the same 409 `duplicate_key` a visible one answers,
    never an unhandled error, and the savepoint leaves nothing written. The answer names
    no zone and no owner (INV-07, D-57)."""
    try:
        with transaction.atomic():
            yield
    except IntegrityError as error:
        constraint = getattr(getattr(error.__cause__, "diag", None), "constraint_name", "") or ""
        if "stable_key" not in constraint:
            raise
        raise ValidationError(f"That key is already {subject} key.", code="duplicate_key") from None


def _verified_origin(reviewer: Reviewer) -> str:
    """Who confirmed the change (INV-05, D-62): an independent agent, or a person. An
    agent's confirmation is machine-confirmed and never reads as a person's."""
    return OriginType.AGENT.value if reviewer.agent_id is not None else OriginType.USER.value


def _new_instrument(
    payload: ProposalInstrumentPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the instrument the proposal asks for, with its official name per language.

    Checked again by `logic.validated_instrument` against the library as it is now: a key
    taken meanwhile is 409 `duplicate_key`, a regime outside the regime dimension 422
    `not_a_regime` (D-39, INV-S12). Provenance names who proposed it and who confirmed it.
    An instrument is not indexed on its own; its obligations and provisions are.

    A bank's own instrument (INV-07, OWN-03) takes its owner from the proposal, never from
    the payload, and its audit row is written in that bank's zone.
    """
    refs, regime = validated_instrument(payload)
    with _key_free_in_every_zone("an instrument's"):
        instrument = Instrument.objects.create(
            owner_tenant_id=proposal.owner_tenant_id,
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
        tenant_id=proposal.owner_tenant_id,
        after={
            "stableKey": instrument.stable_key,
            "regime": payload.regime,
            "level": payload.level,
            "verifiedOrigin": instrument.verified_origin,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _new_instrument_summary(
    payload: ProposalInstrumentSummaryPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the instrument's summary the proposal asks for (INV-09, D-124), one row per
    language. Checked again by the function creation ran: the instrument may have been
    retired, or have been given a summary, while the proposal waited. The instrument's row
    is locked first, so two approvals cannot both find it without one."""
    instrument = validated_instrument_summary(payload)
    instrument = Instrument.objects.select_for_update().get(pk=instrument.pk)
    if InstrumentSummary.objects.filter(instrument=instrument).exists():
        raise ValidationError(f"{payload.instrument!r} already has a summary.", code="duplicate_key")
    for language, text, is_original, is_machine in _texts(payload.summaries, payload.original_language, payload.is_machine, reviewer):
        InstrumentSummary.objects.create(instrument=instrument, language_id=language, text=text, is_original=is_original, is_machine=is_machine)
    record(
        action="instrument.summary_added",
        actor=actor,
        subject_type=SubjectType.INSTRUMENT.value,
        subject_id=instrument.id,
        subject_title=instrument.stable_key,
        summary=f"Added the summary of the instrument {instrument.stable_key} (proposal {proposal.id}).",
        tenant_id=None,
        after={"stableKey": instrument.stable_key, "languages": sorted(payload.summaries), "proposal": str(proposal.id)},
        step_up_assertion_id=step_up,
    )


def _new_translations(payload: ProposalTranslationsPayload, proposal: Proposal, actor: Actor, step_up: uuid.UUID | None) -> None:
    """Add the record's translations the proposal asks for (INV-05, I18N-01, D-129): rows are
    only added, each labelled machine-made and never the original, whoever approved them.

    The record's row is locked, then the payload is checked again, so a language added
    meanwhile is 409 `duplicate_key`, and an obligation's summaries still translate its
    version in force. An obligation is re-indexed inside this transaction."""
    shared = Instrument if payload.target == SubjectType.INSTRUMENT.value else Obligation
    shared.objects.select_for_update().filter(stable_key=payload.key).exists()
    texts = validated_translations(payload)
    if texts.target == SubjectType.INSTRUMENT.value:
        for language, text in payload.titles.items():
            InstrumentTitle.objects.create(instrument_id=texts.id, language_id=language, text=text, is_original=False, is_machine=True)
        for language, text in payload.summaries.items():
            InstrumentSummary.objects.create(instrument_id=texts.id, language_id=language, text=text, is_original=False, is_machine=True)
    else:
        for language, text in payload.titles.items():
            ObligationTitle.objects.create(obligation_id=texts.id, language_id=language, text=text, is_original=False, is_machine=True)
        if payload.summaries and payload.version is not None:
            version = ObligationVersion.objects.get(obligation_id=texts.id, version_number=payload.version)
            for language, text in payload.summaries.items():
                ObligationSummary.objects.create(version=version, language_id=language, text=text, is_original=False, is_machine=True)
        reindex(texts.id)
    record(
        action=f"{texts.target}.translations_added",
        actor=actor,
        subject_type=texts.target,
        subject_id=texts.id,
        subject_title=texts.key,
        summary=f"Added machine translations of the {texts.target} {texts.key} (proposal {proposal.id}).",
        tenant_id=None,
        after={
            "stableKey": texts.key,
            "titles": sorted(payload.titles),
            "summaries": sorted(payload.summaries),
            "version": payload.version,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _new_obligation(
    payload: ProposalObligationPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the obligation the proposal asks for, with its title, its scope and its first
    version, which names the proposal that filed it (`applied_by_proposal`).

    Checked again by `logic.validated_obligation`: the instrument may have been retired, or
    the key taken, while the proposal waited. The index moves in this transaction, so a
    failed re-index leaves the proposal open.

    The standards check runs here too (INV-08, D-35): a standard holds one conformance
    obligation with one standard term, and a law's obligation none. The instrument's row is
    locked first, so two approvals under one standard cannot both find it empty.

    A bank's own obligation (INV-07, OWN-03, OWN-04) takes its owner from the proposal, sits
    under the same bank's own instrument, is never indexed, and is audited in that bank.
    """
    owner = proposal.owner_tenant_id
    instrument, terms = validated_obligation(payload, owner)
    instrument = Instrument.objects.select_for_update().get(pk=instrument.pk)
    standards.check(
        proposal.kind, instrument, [term.id for term in terms], proposal.field_sources, payload.ref_label, proposal.source_label
    )
    verified_origin = _verified_origin(reviewer)
    with _key_free_in_every_zone("an obligation's"):
        obligation = Obligation.objects.create(
            owner_tenant_id=owner,
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
    if owner is None:
        reindex(obligation.id)
    record(
        action="obligation.created",
        actor=actor,
        subject_type=SubjectType.OBLIGATION.value,
        subject_id=obligation.id,
        subject_title=obligation.stable_key,
        summary=f"Added the obligation {obligation.stable_key} under {instrument.stable_key} (proposal {proposal.id}).",
        tenant_id=owner,
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


def _new_recurring_duty(
    payload: ProposalRecurringDutyPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the recurring duty the proposal asks for to its obligation (REG-07), its only
    door into the library.

    Checked again by `logic.validated_recurring_duty` against today's calendar and library.
    Provenance names both sides, so a duty an agent confirmed never reads as a person's check
    (INV-05, D-79). The obligation is re-indexed in this transaction.
    """
    assert proposal.target_id is not None
    obligation = active_obligation(proposal.target_id)
    authority = validated_recurring_duty(payload)
    verified_origin = _verified_origin(reviewer)
    duty = RecurringDuty.objects.create(
        obligation=obligation,
        title=payload.title,
        recurrence_rule=payload.recurrence_rule,
        due_rule_note=payload.due_rule_note,
        recipient_authority=authority,
        lead_days=payload.lead_days,
        applied_by_proposal=proposal,
        created_origin=proposal.origin,
        created_by_agent_id=proposal.proposed_by_agent_id,
        verified_origin=verified_origin,
        verified_by_agent_id=reviewer.agent_id,
        approved_by=reviewer.user,
        approved_at=timezone.now(),
    )
    reindex(obligation.id)
    record(
        action="recurring_duty.created",
        actor=actor,
        subject_type="recurring_duty",
        subject_id=duty.id,
        subject_title=duty.title,
        summary=f"Added a recurring duty to {obligation.stable_key} (proposal {proposal.id}).",
        tenant_id=None,
        after={
            "obligation": obligation.stable_key,
            "recurrenceRule": duty.recurrence_rule,
            "recipientAuthority": payload.recipient_authority,
            "leadDays": duty.lead_days,
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


# --- Obligation versions (INV-04, INV-05, PRO-02) ---
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

    Nothing is overwritten: a new summary is a new numbered row, and every earlier version
    stays as written. The obligation is checked again, since it may have been retired.

    The scope is the one thing a version replaces: a term list belongs to the obligation, so
    a payload carrying one rewrites the links and the audit row holds before and after. A
    payload without `terms` leaves the scope alone; an empty list clears it.

    The search index moves inside this transaction (`reindex`).
    """
    # Read again against the library as it is now: the obligation may have been retired.
    assert proposal.target_id is not None
    # Locked before its highest version is read, so two approvals number their versions in
    # turn rather than colliding on the unique key (PRO-02; tests_decide.ObligationVersionRaces).
    Obligation.objects.select_for_update().filter(pk=proposal.target_id).exists()
    obligation = active_obligation(proposal.target_id)
    # Resolved before anything is written; a mirrored jurisdiction term is refused here too
    # (FP-S12). `terms_of` is never handed an empty list, which matches every term.
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
        # names itself and never reads as a person's verification; the proposing agent is
        # read through `applied_by_proposal.proposed_by_agent`.
        verified_origin=(OriginType.AGENT.value if reviewer.agent_id is not None else OriginType.USER.value),
        verified_by_agent_id=reviewer.agent_id,
    )
    for language, text in payload.summaries.items():
        # Translations stay machine-made until a person confirms them (INV-05, AUD-02); an
        # agent's approval confirms nothing a person would.
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


def _obligation_scope(
    payload: ObligationScopePayload, rows: Sequence[ProposalBatchRow], proposal: Proposal, actor: Actor, step_up: uuid.UUID | None
) -> None:
    """Re-tag each obligation of the approved `rows` (PRO-04, AGT-05): its scope terms become
    the row's `after`, and nothing else changes; no version is filed. The audit row holds the
    terms before and after, and the index moves in the same transaction.

    Checked again under the obligations' locks: a record retired, or whose scope moved since
    the preview, is 409 `stale_write` and the whole decision fails. Added terms are live and
    mirror no jurisdiction; a standard's obligation keeps exactly one standard term (D-35).
    Set-based: every check before any write, one DELETE and one INSERT for the links that
    change, one index rebuild, one audit row per obligation."""
    ids = [row.subject_id for row in rows]
    list(Obligation.objects.select_for_update().filter(pk__in=ids).order_by("id").values_list("id", flat=True))
    in_force = active_shared_obligations(ids)
    live = obligation_scope_terms(ids)
    wanted = sorted({ref for row in rows for ref in row.after["terms"] if ref not in live.get(row.subject_id, {})})
    added = {f"{term.dimension.key}:{term.key}": term for term in (terms_of(wanted) if wanted else [])}
    refuse_mirrored(term.dimension_id for term in added.values())
    sources = {change.obligation_id: change.source for change in payload.changes}
    scopes: dict[uuid.UUID, list[uuid.UUID]] = {}
    for row in rows:
        obligation = in_force.get(row.subject_id)
        if obligation is None:
            raise ValidationError("A record in this batch was retired after it was filed: reject its row.", code="stale_write")
        before = live.get(obligation.id, {})
        if sorted(before) != row.before["terms"]:
            raise ValidationError(
                f"The scope of {obligation.stable_key} changed after the batch was filed: reject its row and file it again.",
                code="stale_write",
            )
        scopes[obligation.id] = [before[ref] if ref in before else added[ref].id for ref in row.after["terms"]]
    opt_in = standards.opt_in_terms({term_id for scope in scopes.values() for term_id in scope})
    # One DELETE of every link the approved rows drop, one INSERT of every link they add.
    dropped: list[Q] = []
    links: list[ObligationTerm] = []
    for row in rows:
        obligation = in_force[row.subject_id]
        standards.check(
            proposal.kind, obligation.instrument, scopes[obligation.id], {"terms": sources[obligation.id]}, source_label=proposal.source_label, opt_in=opt_in
        )
        before = live.get(obligation.id, {})
        after: list[str] = row.after["terms"]
        gone = [term_id for ref, term_id in before.items() if ref not in after]
        if gone:
            dropped.append(Q(obligation=obligation, term_id__in=gone))
        links += [ObligationTerm(obligation=obligation, term=added[ref]) for ref in after if ref not in before]
        record(
            action="obligation.scope_changed",
            actor=actor,
            subject_type=SubjectType.OBLIGATION.value,
            subject_id=obligation.id,
            subject_title=obligation.stable_key,
            summary=f"Re-tagged {obligation.stable_key} (proposal {proposal.id}).",
            tenant_id=None,
            before={"terms": sorted(before)},
            after={"terms": after, "proposal": str(proposal.id), "batchRow": str(row.id), "decision": "approved"},
            step_up_assertion_id=step_up,
        )
    if dropped:
        ObligationTerm.objects.filter(functools.reduce(operator.or_, dropped)).delete()
    if links:
        ObligationTerm.objects.bulk_create(links)
    reindex_obligations(ids)


# --- Provisions (INV-02, INV-08, PRO-02) ---
def _provision_texts(version: ProvisionVersion, payload: ProposalProvisionPayload | ProposalProvisionVersionPayload) -> None:
    """One row per language (INV-05, D-142): the original, the other languages the authority
    itself published, which are neither the original nor machine-made, and every remaining
    text a machine translation, whatever the payload says and whoever approves it. A
    translation of law is never stored unmarked, or it would read as the authority's own."""
    official = set(payload.official_languages or [])
    for language, text in payload.texts.items():
        is_original = language == payload.original_language
        ProvisionText.objects.create(
            version=version, language_id=language, text=text, is_original=is_original, is_machine=not is_original and language not in official
        )


def _cite(provision: Provision, obligations: list[Obligation]) -> list[str]:
    """Tie each obligation to the provision it cites (INV-02), one row per pair; a pair the
    library already holds is left as it is. Returns the keys newly tied, for the audit row."""
    if not obligations:
        return []
    held = set(ObligationProvision.objects.filter(provision=provision, obligation__in=obligations).values_list("obligation_id", flat=True))
    tied = [obligation for obligation in obligations if obligation.id not in held]
    ObligationProvision.objects.bulk_create([ObligationProvision(obligation=obligation, provision=provision) for obligation in tied])
    return [obligation.stable_key for obligation in tied]


def _new_provision(
    payload: ProposalProvisionPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the provision the proposal asks for, with its first verbatim text, which names
    the proposal that filed it, and tie it to the obligations that cite it.

    Checked again by `logic.validated_provision` and the standards check: a standard's text
    is licensed (422 `licensed_text`), and the trigger `provision_not_under_standard` refuses
    the row on its own. The instrument is locked first, so a concurrent level merge is seen
    (H25). The index moves in this transaction.
    """
    instrument, parent, kind, obligations = validated_provision(payload)
    # Locked and read again so a level merge onto a standard is seen before the check (H25).
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
    _provision_texts(version, payload)
    cited = _cite(provision, obligations)
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
            "obligations": cited,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


def _provision_version(
    payload: ProposalProvisionVersionPayload, proposal: Proposal, actor: Actor, reviewer: Reviewer, step_up: uuid.UUID | None
) -> None:
    """Add the text of a provision in force from a date (INV-02): every earlier version stays
    as it was written, and the obligations the text names are tied to the provision, an
    existing tie left alone. The provision is locked and checked again by
    `logic.validated_provision_version`, so a retired one is refused, the original is still
    its jurisdiction's language, and two approvals number their versions one after the other."""
    assert proposal.target_id is not None
    Provision.objects.select_for_update().filter(pk=proposal.target_id).exists()
    provision, obligations = validated_provision_version(payload, proposal.target_id)
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
    _provision_texts(version, payload)
    cited = _cite(provision, obligations)
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
            "obligations": cited,
            "proposal": str(proposal.id),
        },
        step_up_assertion_id=step_up,
    )


# --- Vocabulary rows ---
def _entry(name: str, kind: str, keys: list[str]) -> VocabularyList:
    """The library list a vocabulary proposal names, with the rules its change obeys checked
    again for the list as it is now (`logic.refuse_vocabulary_change`)."""
    entry = REGISTRY[name]
    if not entry.is_library:  # pragma: no cover - logic.validated_payload refused it
        raise ValidationError(f"{name!r} is a tenant list; its admin writes it.", code="unknown_key")
    refuse_vocabulary_change(entry, kind, keys)
    return entry


def _row(entry: VocabularyList, key: str) -> Any:
    """The row `key` names, locked, so a second approval on the same row reads what the
    first wrote rather than writing over its stamp and version bump (H34)."""
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
    wording (INV-05, D-62). Only a write of labels, a usage note or a row column calls this;
    a sort order, retire, restore or merge keeps the stamp the row had.

    A person's approval stamps `user` only once nothing the agents confirmed is left: while
    a label is still machine-made, or a usage note this approval did not rewrite remains, an
    agent-stamped row keeps naming the agents, so their wording never reads as a person's
    check. `labels` is read after this approval wrote its labels."""
    if (
        reviewer.agent_id is None
        and row.verified_origin == OriginType.AGENT.value
        and (labels.filter(is_machine=True).exists() or (row.usage_note and not usage_note_written))
    ):
        return
    for name, value in _confirmation(proposal, reviewer).items():
        setattr(row, name, value)


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
    write_labels(entry.label_model, {"vocabulary": row}, payload.labels, is_machine=reviewer.agent_id is not None)
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
        write_labels(entry.label_model, {"vocabulary": row}, payload.labels, is_machine=reviewer.agent_id is not None)
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
    # Every current row holding the source moves to the target; the source stays, retired,
    # so old references resolve. A move the database refuses undoes every move before it.
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
    the same transaction (FP-04, D-28, D-94): labels, sort order and `active`. No proposal
    may change a mirrored term itself (FP-S12), so this is the one way its wording moves. A
    jurisdiction with no mirrored term (D-38) changes alone. `reviewer` is needed only when
    there are labels to write."""
    terms = TaxonomyTerm.objects.select_for_update(of=("self",)).select_related("dimension").filter(jurisdiction=row).order_by("id")
    for term in terms:
        if not labels and sort_order is None and term.active == row.active:
            continue
        before = {label.language: label.text for label in TaxonomyTermLabel.objects.filter(term=term)}
        was_active = term.active
        if labels and reviewer is not None:
            write_labels(TaxonomyTermLabel, {"term": term}, labels, is_machine=reviewer.agent_id is not None)
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


# --- Taxonomy terms ---
def _dimension(key: str) -> TermDimension:
    dimension = TermDimension.objects.filter(key=key, active=True).order_by("sort_order", "key").first()
    if dimension is None:
        raise ValidationError(f"{key!r} is not a taxonomy dimension.", code="unknown_key")
    return dimension


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
    write_labels(TaxonomyTermLabel, {"term": term}, payload.labels, is_machine=reviewer.agent_id is not None)
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
        write_labels(TaxonomyTermLabel, {"term": term}, payload.labels, is_machine=reviewer.agent_id is not None)
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
