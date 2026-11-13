"""Reading the review queue (PRO-01, PRO-03): the rows a reviewer scans, the page they
decide on, and the list a bank sees of its own proposals. Nothing here writes; library
records are read through apps/library/reading.py and compared with apps/library/logic.py's
sentence diff.

- A proposal made inside a bank reaches the console without its proposer (PRO-03), only
  `fromOrganisation`; `logic.row()` withholds it for every answer.
- `isMine` is computed from the caller, never sent by the client; it marks exactly the rows
  `notMine` drops (`logic.filed_by`), and the server refuses that approval anyway (AC-PRO2).

An approved proposal is read against what it replaced (the version before the one it wrote,
and the scope its audit row found), not against today. Any other is read against today.
A bank's own list is scoped by row-level security on `proposal_tenant`, never by a filter
in Python.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.library.logic import in_force, sentence_diff
from apps.library.models import ObligationVersion
from apps.library.reading import (
    cited_provision_keys,
    localized,
    obligation_headings,
    obligation_scope_refs,
    provision_labels,
    shared_instrument_short_name,
    translatable_records,
)
from apps.library.schemas import DiffSegment, LibraryRef, LocalizedText
from apps.proposals import logic
from apps.proposals.logic import Reviewer
from apps.proposals.models import Proposal, ProposalStatus, ProposalTenant
from apps.proposals.schemas import (
    ProposalAppliedVersion,
    ProposalCitedProvision,
    ProposalDetail,
    ProposalInstrumentSummaryPayload,
    ProposalObligationPayload,
    ProposalObligationVersionPayload,
    ProposalProvisionPayload,
    ProposalQueueRow,
    ProposalSource,
    ProposalTarget,
    ProposalTranslationsPayload,
    TenantProposalRow,
)
from apps.shared.models import AuditEvent
from apps.taxonomy.reading import Labels
from apps.shared.vocabulary import label_of
from apps.taxonomy.registry import REGISTRY

# The audit action the approval of an obligation version writes, whose `before` holds the
# scope, titles, citation and cited provisions that approval found (apps/proposals/apply.py
# `_obligation_version`).
VERSION_APPLIED = "obligation.version_applied"
# The new records that sit under a shared instrument, which the detail names by its short name.
NAMES_ITS_INSTRUMENT = (ProposalObligationPayload, ProposalInstrumentSummaryPayload, ProposalProvisionPayload)


def _is_mine(proposal: Proposal, reviewer: Reviewer) -> bool:
    """Did the reader file this one? For a person, their own; for an agent's key, the key's
    own or any key's of the same agent definition, which four eyes refuses alike (D-62). A
    proposal made inside a bank is never theirs: the console reader is platform staff, and
    the bank's proposer is withheld anyway. The same rule as `logic.filed_by`, for one row."""
    if proposal.proposed_in_tenant:
        return False
    if reviewer.user is not None:
        return proposal.proposed_by_user_id == reviewer.user.id
    return proposal.proposed_by_api_key_id == reviewer.api_key_id or (
        reviewer.agent_id is not None and proposal.proposed_by_agent_id == reviewer.agent_id
    )


def _targets(proposals: Sequence[Proposal], order: list[str]) -> dict[uuid.UUID, ProposalTarget]:
    """The library record each proposal points at, by its own title and reference, in two
    queries however many rows there are (playbook 10)."""
    wanted = {
        proposal.target_id
        for proposal in proposals
        if proposal.target_id is not None and proposal.target_type == logic.OBLIGATION_TARGET
    }
    headings = obligation_headings(wanted, order)
    return {
        record_id: ProposalTarget(
            id=record_id,
            title=heading.title,
            reference_label=heading.reference_label,
            instrument_short_name=heading.instrument_short_name,
        )
        for record_id, heading in headings.items()
    }


def queue_rows(proposals: Sequence[Proposal], order: list[str], *, reviewer: Reviewer) -> list[ProposalQueueRow]:
    """The console queue's rows, each naming the record it would change and whether the
    reader filed it."""
    targets = _targets(proposals, order)
    return [
        ProposalQueueRow(
            **dict(logic.row(proposal)),
            target=targets.get(proposal.target_id) if proposal.target_id is not None else None,
            is_mine=_is_mine(proposal, reviewer),
        )
        for proposal in proposals
    ]


def _sources(proposal: Proposal) -> list[ProposalSource]:
    """One source per changed field, as a reviewer opens them: the proposal's own sentence
    about the source for a link, and the provision's stable key when the source is a record
    the library already holds."""
    return [
        ProposalSource(
            field=field,
            label=proposal.source_label if value.startswith("https://") else value,
            url=value if value.startswith("https://") else "",
        )
        for field, value in sorted(proposal.field_sources.items())
    ]


def _current_version(obligation_id: uuid.UUID) -> ObligationVersion | None:
    """The version of the record in force today, which is the wording a proposal still to be
    decided would replace. A record whose every version starts in the future is compared
    with its latest version, and a record with no version at all with nothing."""
    versions = list(ObligationVersion.objects.filter(obligation_id=obligation_id).prefetch_related("summaries"))
    return in_force(versions, timezone.now().date()) or (versions[-1] if versions else None)


def _applied(proposal: Proposal) -> ObligationVersion | None:
    """The version the approval wrote, found through `ObligationVersion.applied_by_proposal`
    rather than stored twice on the proposal. None unless the proposal was approved."""
    if proposal.status != ProposalStatus.APPROVED.value:
        return None
    return ObligationVersion.objects.filter(applied_by_proposal=proposal).first()  # ordering: one approval writes one version


def _replaced(target_id: uuid.UUID, applied: ObligationVersion | None) -> ObligationVersion | None:
    """The version whose wording the proposal replaces. For an approved proposal it is the
    one numbered just before the version the approval wrote, which neither the calendar nor
    a later version can move; for any other it is the version in force today."""
    if applied is None:
        return _current_version(target_id)
    return (
        ObligationVersion.objects.filter(obligation_id=applied.obligation_id, version_number=applied.version_number - 1)
        .prefetch_related("summaries")
        .first()  # ordering: a version number is unique per obligation
    )


def _found(proposal: Proposal, target_id: uuid.UUID, applied: ObligationVersion | None) -> dict[str, Any]:
    """What an approved proposal's approval found on the obligation, from the audit row it
    wrote (no column on the proposal holds it): the scope, titles, citation and cited
    provisions it replaced, each null where it left that part alone. Empty for a proposal
    not approved, which is compared with the record as it is now."""
    if applied is None:
        return {}
    event = AuditEvent.objects.filter(
        action=VERSION_APPLIED, subject_type=logic.OBLIGATION_TARGET, subject_id=target_id, after__proposal=str(proposal.id)
    ).first()  # ordering: one approval writes one version_applied row
    return {} if event is None else dict(event.before)


def _cited_changes(payload: ProposalObligationVersionPayload, before: list[str]) -> tuple[list[ProposalCitedProvision], list[ProposalCitedProvision]]:
    """The provisions a version would add to its obligation's citations and those it would
    drop, each named as the law numbers it; neither when it leaves the citations alone."""
    if payload.provisions is None:
        return [], []
    added = [key for key in payload.provisions if key not in before]
    removed = [key for key in before if key not in payload.provisions]
    labels = provision_labels(added + removed)

    def cited(keys: list[str]) -> list[ProposalCitedProvision]:
        return [ProposalCitedProvision(key=key, reference_label=labels.get(key, "")) for key in keys]

    return cited(added), cited(removed)


def _rejection_reason(proposal: Proposal, order: list[str]) -> LibraryRef | None:
    """The reason it was refused, as key and label. A code whose row has since been retired
    or renamed still resolves; a code the list no longer holds at all answers null rather
    than inventing a label."""
    if not proposal.rejection_code:
        return None
    entry = REGISTRY[logic.REJECTION_REASON_LIST]
    row = entry.model.objects.filter(key=proposal.rejection_code).first()  # ordering: a list holds one row per key
    if row is None:
        return None
    labels = Labels.for_rows(entry.label_model, [row])
    return LibraryRef(key=row.key, kind=None, label=label_of(labels.texts(row.id), order, original=labels.original(row.id), key=row.key))


def detail(proposal: Proposal, order: list[str], *, reviewer: Reviewer) -> ProposalDetail:
    """One proposal as a reviewer decides it: the row, the record it changes, the wording it
    replaces against what this would make it say, the source behind every changed field, and
    the scope, title, citation and cited provisions before and after (D-144)."""
    row = queue_rows([proposal], order, reviewer=reviewer)[0]
    if proposal.is_batch:
        # A batch's preview is its rows, read through `GET /proposal-batches/{batchId}`
        # (apps/proposals/batch.py); its payload has no single record to compare with.
        return ProposalDetail(**dict(row), sources=_sources(proposal), rejection_reason=_rejection_reason(proposal, order))
    payload = logic.parsed_payload(proposal.kind, proposal.corrected_payload or proposal.payload)
    if isinstance(payload, ProposalTranslationsPayload):
        return _translations_detail(proposal, payload, row, order)
    if not isinstance(payload, ProposalObligationVersionPayload) or proposal.target_id is None:
        # No wording to compare: a list row is a person's wording and a new record replaces
        # nothing. Its sources are still checked, and a new duty, summary or provision names
        # the instrument it would sit under.
        return ProposalDetail(
            **dict(row),
            sources=_sources(proposal),
            rejection_reason=_rejection_reason(proposal, order),
            instrument_short_name=shared_instrument_short_name(payload.instrument) if isinstance(payload, NAMES_ITS_INSTRUMENT) else "",
        )
    language = payload.original_language
    applied = _applied(proposal)
    replaced = _replaced(proposal.target_id, applied)
    summary = None if replaced is None else localized([text for text in replaced.summaries.all() if text.language_id == language], [language])
    proposed_text = payload.summaries.get(language, "")
    found = _found(proposal, proposal.target_id, applied)
    heading = obligation_headings([proposal.target_id], [language]).get(proposal.target_id)
    titles_found: dict[str, str] | None = found.get("titles")
    title_before = (titles_found.get(language) or next(iter(titles_found.values()), "")) if titles_found else (heading.title if heading else "")
    ref_label_found: str | None = found.get("refLabel")
    cited_found: list[str] | None = found.get("provisions")
    added, removed = _cited_changes(payload, cited_provision_keys(proposal.target_id) if cited_found is None else cited_found)
    return ProposalDetail(
        **dict(row),
        language=language,
        current_summary=summary,
        proposed_text=proposed_text,
        diff=[DiffSegment(op=op, text=text) for op, text in sentence_diff("" if summary is None else summary.text, proposed_text)],
        sources=_sources(proposal),
        scope_before=obligation_scope_refs(proposal.target_id) if found.get("terms") is None else list(found["terms"]),
        scope_after=payload.terms,
        title_before=title_before,
        title_after=None if payload.titles is None else payload.titles.get(language, ""),
        ref_label_before=ref_label_found if ref_label_found is not None else (heading.reference_label if heading else ""),
        ref_label_after=payload.ref_label,
        provisions_added=added,
        provisions_removed=removed,
        rejection_reason=_rejection_reason(proposal, order),
        applied_version=(
            None
            if applied is None
            else ProposalAppliedVersion(id=applied.id, version_number=applied.version_number, effective_from=applied.effective_from)
        ),
    )


def _translations_detail(proposal: Proposal, payload: ProposalTranslationsPayload, row: ProposalQueueRow, order: list[str]) -> ProposalDetail:
    """A record's translations beside the originals they were made from (D-129), as the
    library holds them now, so a reviewer judges each against its source text."""
    found = translatable_records(timezone.localdate(), target=payload.target, key=payload.key)
    record = found[0] if found else None

    def original(texts: dict[str, str], language: str, asked: bool) -> LocalizedText | None:
        if record is None or not asked or language not in texts:
            return None
        return LocalizedText(text=texts[language], language=language, is_original=True, is_machine=False)

    return ProposalDetail(
        **dict(row),
        sources=_sources(proposal),
        rejection_reason=_rejection_reason(proposal, order),
        instrument_short_name="" if record is None else record.short_name,
        original_title=None if record is None else original(record.titles, record.title_original, bool(payload.titles)),
        original_summary=None if record is None else original(record.summaries, record.summary_original, bool(payload.summaries)),
    )


def membership_of(tenant: Any, user_id: uuid.UUID) -> Any:
    """The reader's membership of this bank, which carries their own bookmark of when they
    last marked the library as seen. Read under row-level security, so it is theirs and
    their bank's; a session always has one, and None means a member who has since left."""
    from apps.identity.models import Membership

    return Membership.objects.filter(tenant=tenant, user_id=user_id).first()  # ordering: one membership per person per bank


def tenant_queue(*, status: str | None, kind: str | None, target_list: str | None) -> QuerySet[Proposal]:
    """The proposals this bank filed, oldest first. The cut is row-level security on
    `proposal_tenant`: the session's own tenant is the only one whose link rows the database
    returns, so another bank's proposals are not filtered out here — they are not here."""
    mine = Proposal.objects.filter(id__in=ProposalTenant.objects.values("proposal_id"))
    return logic.filtered(mine, status=status, kind=kind, target_list=target_list)


def tenant_rows(proposals: Sequence[Proposal]) -> list[TenantProposalRow]:
    """A bank's own proposals as its vocabulary screen lists them: what was asked, how far
    it has got and when it was filed. No reviewer, no note and no payload: what a bank needs
    is whether its request is still waiting."""
    return [
        TenantProposalRow(id=proposal.id, kind=proposal.kind, status=proposal.status, title=proposal.title, created_at=proposal.created_at)
        for proposal in proposals
    ]
