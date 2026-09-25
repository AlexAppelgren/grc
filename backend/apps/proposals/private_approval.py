"""The bank's own queue (INV-07, OWN-03, PRO-03; D-57, D-89, ADR 0050, ADR 0059).

A proposal of a bank's own record carries `owner_tenant_id` (apps/proposals/logic.py sets
it), and row-level security on `proposal` keeps it inside that bank: the console reads no
owned row and another bank reads none of this one's. A person holding
`private_records.approve` decides it here, never the proposer, through the same apply code
and the same `proposal_four_eyes` constraint as the shared queue.

The routes are declared ahead of the logic that fills them (d89-private-records): each loads
its proposal under row-level security first, so another bank's proposal answers 404 before
anything else, and then answers 501 `not_built`.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError

from apps.proposals.models import Proposal
from apps.proposals.schemas import PrivateProposalPage, PrivateProposalRow
from apps.shared.errors import ProblemError

NOT_BUILT = "The organisation's own queue is not built yet."


def by_id(proposal_id: uuid.UUID) -> Proposal:
    """The bank's own proposal `proposal_id`, or 404. Row-level security is what hides
    another bank's: this filter only leaves out the shared proposals every bank reads."""
    proposal = Proposal.objects.filter(pk=proposal_id, owner_tenant__isnull=False).first()  # ordering: pk lookup, at most one row
    if proposal is None:
        raise ValidationError("That proposal is not here.", code="not_found")
    return proposal


def queue(*, limit: int, offset: int) -> PrivateProposalPage:
    """The bank's own proposals, oldest first (OWN-03). Not built yet."""
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def approve(*, proposal: Proposal, note: str, step_up_assertion_id: uuid.UUID) -> PrivateProposalRow:
    """Approve the bank's own proposal and apply it (OWN-03). Not built yet."""
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def reject(*, proposal: Proposal, rejection_code: str, note: str) -> PrivateProposalRow:
    """Reject the bank's own proposal with a reason (OWN-03). Not built yet."""
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
