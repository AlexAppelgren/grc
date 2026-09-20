"""Routes of the proposals app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

The queue is the platform console's (PRO-03): reading and deciding need
`proposals.review`, and approving needs a fresh passkey assertion (AC-PRO2). Creating is
open to a tenant member with `proposals.create`, a platform editor with
`library_vocab.manage` and an agent's key with `proposals:write` (a logic gate, listed in
`UNGATED_BY_DESIGN`). No route writes a library row: approval does, through
apps/proposals/apply.py.
"""

from typing import Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.proposals import logic
from apps.proposals.schemas import (
    ProposalApproveBody,
    ProposalCreateBody,
    ProposalPage,
    ProposalQuery,
    ProposalRejectBody,
    ProposalRow,
)
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.taxonomy.http import (
    actor_for,
    answers_problems,
    caller_user,
    idempotency_key,
    proposer_for,
    require_proposer,
    uuid_or_404,
)

router = Router(tags=["Proposals"])

SESSION = SessionAuth()


@router.get("/proposals", response=ProposalPage, auth=SESSION, operation_id="listProposals", by_alias=True)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def list_proposals(request: HttpRequest, query: Query[ProposalQuery]) -> ProposalPage:
    queryset = logic.queue(status=query.status, kind=query.kind, target_list=query.target_list)
    rows = [logic.row(proposal) for proposal in queryset]
    return ProposalPage(items=rows, total=len(rows))


@router.post(
    "/proposals",
    response={200: ProposalRow, 201: ProposalRow},
    auth=[SessionAuth(), ApiKeyAuth()],
    operation_id="createProposal",
    by_alias=True,
)
@answers_problems
def create_proposal(request: HttpRequest, body: ProposalCreateBody) -> Any:
    # Ungated by design: logic-gate (proposals.create, library_vocab.manage or the proposals:write scope; PRO-01).
    require_proposer(request)
    proposal, created = logic.create(
        kind=body.kind,
        title=body.title,
        payload=body.payload,
        proposer=proposer_for(request),
        idempotency_key=idempotency_key(request),
        target_type=body.target_type,
        target_id=body.target_id,
        change_id=body.change_id,
        agent_run_id=body.agent_run_id,
        model=body.model,
        field_sources=body.field_sources,
        source_label=body.source_label,
        source_url=body.source_url,
        effective_from=body.effective_from,
    )
    return (201 if created else 200), logic.row(proposal)


@router.get("/proposals/{proposal_id}", response=ProposalRow, auth=SESSION, operation_id="getProposal", by_alias=True)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def get_proposal(request: HttpRequest, proposal_id: str) -> ProposalRow:
    return logic.row(logic.by_id(uuid_or_404(proposal_id)))


@router.post(
    "/proposals/{proposal_id}/approve",
    response=ProposalRow,
    auth=SESSION,
    operation_id="approveProposal",
    by_alias=True,
    summary="Approve a proposal and let the change into the shared library",
)
@requires_permission(perms.PROPOSALS_REVIEW)
@requires_step_up
@answers_problems
def approve_proposal(
    request: HttpRequest,
    body: ProposalApproveBody,
    proposal_id: str = Path(
        ...,
        description=(
            "The proposal being decided, the UUID the queue returns as `id`. A proposal "
            "that does not exist, and anything that is not a UUID, answers `not_found`."
        ),
    ),
) -> ProposalRow:
    """The only door into the shared library. Call it once a reviewer has read the
    proposal, opened its sources and satisfied themselves that the facts are right; what
    it applies is what every bank on the platform will read as the library's own text.

    In one transaction it applies the payload, writes the new library version, writes the
    audit rows for the library record and for the proposal, and re-indexes the record for
    search: all of it commits or none of it does. The reviewer may correct the payload on
    the way through with `payloadOverrides`, and what they approved is stored beside what
    was proposed, so the queue and the audit trail keep both. The answer is the proposal
    row as it now stands, with `status` `approved` and `appliedAt` set.

    Needs the platform permission `proposals.review` and a fresh passkey step-up, whose
    assertion id is written on the audit rows the approval leaves. The reviewer is never
    the proposer. No API key scope reaches this call: a key holds no passkey assertion, so
    an agent working the same queue is a separate, independent principal by construction.

    Errors to branch on: `permission_denied` without `proposals.review`;
    `step_up_required` when no fresh passkey assertion accompanies the call;
    `four_eyes_violation` when the reviewer is the person who made the proposal;
    `invalid_transition` when the proposal was already approved or rejected, which is also
    what a repeated call answers, since nothing is ever applied twice; `source_missing`
    when a correction introduces a field the proposal never sourced; `validation_error`
    when a correction is offered on a kind that cannot be corrected or does not fit its
    payload; `unknown_key` when the payload names a row the library does not hold;
    `not_found` when there is no such proposal.
    """
    reviewer = caller_user(request)
    proposal = logic.approve(
        proposal=logic.by_id(uuid_or_404(proposal_id)),
        reviewer=reviewer,
        actor=actor_for(request, reviewer),
        note=body.note,
        payload_overrides=body.payload_overrides,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return logic.row(proposal)


@router.post("/proposals/{proposal_id}/reject", response=ProposalRow, auth=SESSION, operation_id="rejectProposal", by_alias=True)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def reject_proposal(request: HttpRequest, proposal_id: str, body: ProposalRejectBody) -> ProposalRow:
    reviewer = caller_user(request)
    proposal = logic.reject(
        proposal=logic.by_id(uuid_or_404(proposal_id)),
        reviewer=reviewer,
        actor=actor_for(request, reviewer),
        rejection_code=body.rejection_code,
        note=body.note,
    )
    return logic.row(proposal)
