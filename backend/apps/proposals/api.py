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

from apps.proposals import logic, reading
from apps.proposals.schemas import (
    ProposalApproveBody,
    ProposalCreateBody,
    ProposalDetail,
    ProposalPage,
    ProposalQuery,
    ProposalRejectBody,
    ProposalRow,
    TenantProposalPage,
    TenantProposalQuery,
)
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.reading import language_order
from apps.taxonomy.http import (
    actor_for,
    answers_problems,
    caller_user,
    idempotency_key,
    principal,
    proposer_for,
    require_proposer,
    uuid_or_404,
)

router = Router(tags=["Proposals"])

SESSION = SessionAuth()


@router.get(
    "/proposals",
    response=ProposalPage,
    auth=SESSION,
    operation_id="listProposals",
    by_alias=True,
    summary="Read the queue of changes waiting to enter the shared library",
)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def list_proposals(request: HttpRequest, query: Query[ProposalQuery]) -> ProposalPage:
    """Every change an agent or a person has asked for, with the library record each one
    would change named by its own title and reference, so a reviewer can work the queue
    without opening each proposal. Call it for the console's Waiting, Approved and Rejected
    tabs, each of which is this call with its own `status`.

    The answer is every proposal matching the filters in one page, oldest first. Nothing is
    hidden by them: `total` counts the same rows the list carries. A proposal filed inside a
    bank arrives without its proposer and says `fromOrganisation` instead, and `isMine` says
    whether the reader filed it, which four eyes will not let them decide.

    Needs the platform permission `proposals.review`. No bank role reaches it, whatever the
    member holds inside their own organisation, and no API key scope reaches it either.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without `proposals.review`; `unknown_key` (422) when `origin` is a value that is
    neither `agent` nor `user`.
    """
    me_id = principal(request).subject_id
    queryset = logic.queue(
        status=query.status,
        kind=query.kind,
        target_list=query.target_list,
        origin=query.origin,
        not_mine=query.not_mine,
        reviewer_id=me_id,
    )
    rows = reading.queue_rows(list(queryset), language_order(request), me_id=me_id)
    return ProposalPage(items=rows, total=len(rows))


@router.get(
    "/tenant/proposals",
    response=TenantProposalPage,
    auth=SESSION,
    operation_id="listTenantProposals",
    by_alias=True,
    summary="Read what your organisation has asked to change in the shared library",
)
@requires_permission(perms.VOCAB_MANAGE)
@answers_problems
def list_tenant_proposals(request: HttpRequest, query: Query[TenantProposalQuery], page: Query[PageQuery]) -> TenantProposalPage:
    """The proposals this organisation filed against the shared library lists, and how far
    each has got. Call it for the pending list beside a shared vocabulary, so somebody who
    suggested a value can see it is still waiting rather than suggesting it again.

    It answers this organisation's own proposals and no others: the link between a proposal
    and the organisation that filed it is a row in this organisation's zone, and row-level
    security is what limits the read. Another bank's proposals are not filtered out of the
    answer; they are never in it. What comes back is the request and its status, never the
    platform reviewer who decided it and never another organisation's wording.

    Paginated: 20 rows by default and 100 at most, with a larger limit refused rather than
    quietly trimmed, oldest first so paging is repeatable. Nothing matching the filters is a
    200 with an empty items list and a total of 0, never a 404.

    Needs `vocab.manage`, the permission that manages this organisation's vocabularies.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without `vocab.manage`; `not_found` (404) for a principal in no organisation;
    `validation_error` (422) when the page size or offset is out of range.
    """
    queryset = reading.tenant_queue(status=query.status, kind=query.kind, target_list=query.target_list)
    total = queryset.count()
    rows = reading.tenant_rows(list(queryset[page.offset : page.offset + page.limit]))
    return TenantProposalPage(items=rows, total=total)


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


@router.get(
    "/proposals/{proposal_id}",
    response=ProposalDetail,
    auth=SESSION,
    operation_id="getProposal",
    by_alias=True,
    summary="Open one proposal and read it against what the library says today",
)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def get_proposal(request: HttpRequest, proposal_id: str) -> ProposalDetail:
    """One proposal as a reviewer decides it: the record it would change, what that record
    says today against what this would make it say, the two compared sentence by sentence,
    the source behind every changed value, and the scope before and after. Read it, open the
    sources, and only then approve.

    What comes back is a request and not the library: until the proposal is approved the
    library still says what `currentSummary` says. A proposal filed inside a bank arrives
    without its proposer, as in the list.

    Needs the platform permission `proposals.review`; no bank role and no API key scope
    reaches it.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without `proposals.review`; `not_found` (404) for a proposal that does not exist
    and for anything that is not a UUID.
    """
    return reading.detail(logic.by_id(uuid_or_404(proposal_id)), language_order(request), me_id=principal(request).subject_id)


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
