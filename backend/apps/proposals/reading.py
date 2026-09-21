"""Reading the review queue (PRO-01, PRO-03): the rows a reviewer scans, the page they
decide on, and the list a bank sees of its own proposals.

Nothing here writes, and nothing here writes a library row: the records a proposal points
at are read through apps/library/reading.py, where every library read lives, and the
comparison between what the library says and what a proposal would make it say is chunk 3's
one sentence diff (apps/library/logic.py), never a second implementation.

Two rules decide what a reader is told about who proposed what:

- A proposal made inside a bank reaches the console without its proposer (PRO-03). The row
  says `fromOrganisation` instead, which is the whole truth the console gets: not the
  person, not their id and not which bank they work for. `logic.row()` withholds it, so
  every answer carrying a proposal withholds it, not only the queue.
- `isMine` is computed here from the signed-in reviewer, never sent by the client, because
  it is what a screen hides its own Approve control behind; the server refuses that
  approval either way (four eyes, AC-PRO2).

A bank's own list is scoped by row-level security on `proposal_tenant` and never by a
tenant filter in Python: the tenant the session activated is the only one whose link rows
the database will return, so a bug here cannot widen it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.library.logic import in_force, sentence_diff
from apps.library.models import ObligationVersion
from apps.library.reading import localized, obligation_headings, obligation_scope_refs
from apps.library.schemas import DiffSegment, LibraryRef
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalStatus, ProposalTenant
from apps.proposals.schemas import (
    ProposalAppliedVersion,
    ProposalDetail,
    ProposalObligationVersionPayload,
    ProposalQueueRow,
    ProposalSource,
    ProposalTarget,
    TenantProposalRow,
)
from apps.taxonomy.reading import Labels, label_of
from apps.taxonomy.registry import REGISTRY


def _is_mine(proposal: Proposal, me_id: uuid.UUID) -> bool:
    """Did the reader file this one? A proposal made inside a bank is never theirs: the
    console reader is platform staff, and the bank's proposer is withheld anyway."""
    return not proposal.proposed_in_tenant and proposal.proposed_by_user_id == me_id


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


def queue_rows(proposals: Sequence[Proposal], order: list[str], *, me_id: uuid.UUID) -> list[ProposalQueueRow]:
    """The console queue's rows, each naming the record it would change and whether the
    reader filed it."""
    targets = _targets(proposals, order)
    return [
        ProposalQueueRow(
            **dict(logic.row(proposal)),
            target=targets.get(proposal.target_id) if proposal.target_id is not None else None,
            is_mine=_is_mine(proposal, me_id),
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
    """The version of the record in force today, which is the wording the proposal would
    replace. A record whose every version starts in the future has none yet, and the
    reviewer then compares against nothing."""
    versions = list(ObligationVersion.objects.filter(obligation_id=obligation_id).prefetch_related("summaries"))
    return in_force(versions, timezone.now().date()) or (versions[-1] if versions else None)


def _applied_version(proposal: Proposal) -> ProposalAppliedVersion | None:
    """The version the approval wrote, found through `ObligationVersion.applied_by_proposal`
    rather than stored twice on the proposal."""
    if proposal.status != ProposalStatus.APPROVED.value:
        return None
    version = ObligationVersion.objects.filter(applied_by_proposal=proposal).first()  # ordering: one approval writes one version
    if version is None:
        return None
    return ProposalAppliedVersion(id=version.id, version_number=version.version_number, effective_from=version.effective_from)


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


def detail(proposal: Proposal, order: list[str], *, me_id: uuid.UUID) -> ProposalDetail:
    """One proposal as a reviewer decides it: the row, the record it changes, what the
    library says today against what this would make it say, the source behind every changed
    field, and the scope before and after."""
    row = queue_rows([proposal], order, me_id=me_id)[0]
    payload = logic.parsed_payload(proposal.kind, proposal.corrected_payload or proposal.payload)
    if not isinstance(payload, ProposalObligationVersionPayload) or proposal.target_id is None:
        return ProposalDetail(**dict(row), rejection_reason=_rejection_reason(proposal, order))
    language = payload.original_language
    current = _current_version(proposal.target_id)
    summary = None if current is None else localized([text for text in current.summaries.all() if text.language_id == language], [language])
    proposed_text = payload.summaries.get(language, "")
    return ProposalDetail(
        **dict(row),
        language=language,
        current_summary=summary,
        proposed_text=proposed_text,
        diff=[DiffSegment(op=op, text=text) for op, text in sentence_diff("" if summary is None else summary.text, proposed_text)],
        sources=_sources(proposal),
        scope_before=obligation_scope_refs(proposal.target_id),
        scope_after=payload.terms,
        rejection_reason=_rejection_reason(proposal, order),
        applied_version=_applied_version(proposal),
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
