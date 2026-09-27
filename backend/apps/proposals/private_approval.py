"""The bank's own queue (INV-07, OWN-03, PRO-03; D-57, D-89, ADR 0050, ADR 0059).

A proposal of a bank's own record carries `owner_tenant_id` (apps/proposals/logic.py sets
it), and row-level security on `proposal` keeps it inside that bank: the console reads no
owned row and another bank reads none of this one's. A person holding
`private_records.approve` decides it here, never the proposer and never an agent, through the
same `logic.approve` and `logic.reject`, the same apply code and the same
`proposal_four_eyes` constraint as the shared queue. Those write the decision's audit and
outbox rows in the bank's own zone, with the approver's passkey assertion and never the
note's words.

Every function loads its proposal under row-level security first (`by_id`), so another
bank's proposal, a shared one and one that does not exist are the same 404.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError

from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.proposals.schemas import PrivateProposalPage, PrivateProposalRow
from apps.shared.audit import Actor


def by_id(proposal_id: uuid.UUID) -> Proposal:
    """The bank's own proposal `proposal_id`, or 404. Row-level security is what hides
    another bank's: this filter only leaves out the shared proposals every bank reads."""
    proposal = Proposal.objects.filter(pk=proposal_id, owner_tenant__isnull=False).first()  # ordering: pk lookup, at most one row
    if proposal is None:
        raise ValidationError("That proposal is not here.", code="not_found")
    return proposal


def row(proposal: Proposal, reader: Any) -> PrivateProposalRow:
    """One proposal as the bank's own queue shows it to `reader`, a person of the bank."""
    return PrivateProposalRow(
        id=proposal.id,
        kind=proposal.kind,
        status=proposal.status,
        title=proposal.title,
        origin=proposal.origin,
        is_mine=proposal.proposed_by_user_id == reader.id,
        payload=proposal.payload,
        field_sources=proposal.field_sources,
        source_url=proposal.source_url,
        created_at=proposal.created_at,
    )


def queue(*, reader: Any, limit: int, offset: int) -> PrivateProposalPage:
    """The bank's own proposals waiting for a decision, oldest first (OWN-03)."""
    waiting = Proposal.objects.filter(owner_tenant__isnull=False, status=ProposalStatus.OPEN.value).order_by("created_at", "id")
    return PrivateProposalPage(items=[row(proposal, reader) for proposal in waiting[offset : offset + limit]], total=waiting.count())


def approve(*, proposal: Proposal, reviewer: Any, actor: Actor, note: str, step_up_assertion_id: uuid.UUID) -> PrivateProposalRow:
    """Approve the bank's own proposal and apply it into the bank's own zone (OWN-03)."""
    decided = logic.approve(
        proposal=proposal,
        reviewer=logic.Reviewer(actor=actor, user=reviewer),
        actor=actor,
        note=note,
        step_up_assertion_id=step_up_assertion_id,
    )
    return row(decided, reviewer)


def reject(*, proposal: Proposal, reviewer: Any, actor: Actor, rejection_code: str, note: str) -> PrivateProposalRow:
    """Reject the bank's own proposal with a reason, a live rejection reason and a note
    (OWN-03); nothing is applied."""
    decided = logic.reject(
        proposal=proposal,
        reviewer=logic.Reviewer(actor=actor, user=reviewer),
        actor=actor,
        rejection_code=rejection_code,
        note=note,
    )
    return row(decided, reviewer)
