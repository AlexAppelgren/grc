"""Routes of the proposals app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

The queue is the platform console's (PRO-03): reading and deciding need `proposals.review`
from a person, or the scope `proposals:review` from a platform key bound to an agent
(PRO-S13, D-62, ADR 0054); approving needs a fresh passkey assertion from a person and
never from a key, which holds no assertion to give. `require_reviewer` below is that gate,
in the route body rather than a decorator: `Principal.has_permission` and `has_scope` are
kind-exclusive, so no single decorator can express "a session or a key" the way
`@requires_permission`/`@requires_scope` express one kind alone (apps/shared/tests_library_fence.py
reads this function back as the door's gate). Creating is open to a tenant member with
`proposals.create`, a platform editor with `library_vocab.manage` and an agent's key with
`proposals:write` (a logic gate, listed in `UNGATED_BY_DESIGN`). No route writes a library
row: approval does, through apps/proposals/apply.py.
"""

from dataclasses import replace
from typing import Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.proposals import logic, reading, updates
from apps.proposals.logic import Reviewer
from apps.proposals.schemas import (
    LibraryUpdatesPage,
    LibraryUpdatesQuery,
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
from apps.shared.audit import Actor, ActorType
from apps.shared.authentication import ApiKeyAuth, PrincipalKind, SessionAuth
from apps.shared.errors import ProblemError
from apps.shared.permissions import enforce_step_up, requires_permission
from apps.shared.schemas import PageQuery
from apps.taxonomy.reading import language_order
from apps.taxonomy.http import (
    actor_for,
    answers_problems,
    caller_tenant,
    caller_user,
    idempotency_key,
    principal,
    proposer_for,
    require_proposer,
    uuid_or_404,
)

router = Router(tags=["Proposals"])

SESSION = SessionAuth()
REVIEWER_AUTH = [SessionAuth(), ApiKeyAuth()]


def require_reviewer(request: HttpRequest) -> Reviewer:
    """Who may work the review queue (PRO-S13, PRO-S14, ID-S31, D-62, ADR 0054): a person
    holding `proposals.review`, or a platform key bound to an agent and holding the scope
    `proposals:review`. `proposals:review` is platform-only (`PLATFORM_ONLY_SCOPES`): a key
    carrying a tenant is refused here with 403 even if its scopes list somehow names it,
    which is the gate's own word beside the 422 a tenant key is refused it with at creation
    (apps/identity/api_keys_logic.py). A reviewing key that names no agent is refused too,
    the same way the widened `proposal_four_eyes` constraint refuses it on its own: an
    unbound platform key can never stand in for the independent second agent the scope is
    for. Never applies a step-up: a key holds no passkey assertion, so that stays the
    caller's own job for the one route that needs one (`approve_proposal`)."""
    from apps.identity.models import ApiKey

    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if who.tenant_id is not None or not who.has_scope(perms.SCOPE_PROPOSALS_REVIEW):
            raise ProblemError(
                status=403,
                code="permission_denied",
                detail="This key does not have the scope for that.",
                required_permission=perms.SCOPE_PROPOSALS_REVIEW,
            )
        key = ApiKey.objects.select_related("agent").filter(pk=who.subject_id).first()  # ordering: pk lookup, at most one row
        version = key.agent.current_version if key is not None and key.agent is not None else None
        label = who.agent_label if version is None else f"{who.agent_label} v{version}"
        return Reviewer(
            actor=Actor(kind=ActorType.AGENT, id=who.agent_id, label=label),
            api_key_id=who.subject_id,
            agent_id=who.agent_id,
            api_key_prefix=key.key_prefix if key is not None else "",
        )
    if not who.has_permission(perms.PROPOSALS_REVIEW):
        raise ProblemError(
            status=403, code="permission_denied", detail="You do not have access to this.", required_permission=perms.PROPOSALS_REVIEW
        )
    user = caller_user(request)
    return Reviewer(actor=actor_for(request, user), user=user)


@router.get(
    "/proposals",
    response=ProposalPage,
    auth=REVIEWER_AUTH,
    operation_id="listProposals",
    by_alias=True,
    summary="Read the queue of changes waiting to enter the shared library",
)
@answers_problems
def list_proposals(request: HttpRequest, query: Query[ProposalQuery], page: Query[PageQuery]) -> ProposalPage:
    """Every change an agent or a person has asked for, with the library record each one
    would change named by its own title and reference, so a reviewer can work the queue
    without opening each proposal. Call it for the console's Waiting, Approved and Rejected
    tabs, each of which is this call with its own `status`, and call it from a confirming
    agent's key to read the same queue a person reads.

    Each row names who filed it and who decided it: a platform person in `proposedBy` and
    `reviewedBy`, or an agent by its definition key in `proposedByAgent` and
    `reviewedByAgent`, and whoever corrected the payload on the way to approving it. A
    proposal filed inside a bank arrives without its proposer and says `fromOrganisation`
    instead. `isMine` says whether the reader filed it, which four eyes will not let them
    decide: for a person their own, for an agent's key the key's own and those of every
    other key of the same agent definition. `notMine` drops exactly those rows.

    Nothing here changes a record and nothing is written to the audit trail: it is a read.

    Paginated: 20 rows by default and 100 at most, with a larger limit refused rather than
    quietly trimmed, oldest first so paging is repeatable, and `total` counting every
    proposal matching the filters across every page. Nothing matching is a 200 with an empty
    items list and a total of 0, never a 404.

    Needs the platform permission `proposals.review` from a person, or the platform-only
    scope `proposals:review` from a key bound to an agent definition (D-62, ADR 0054). No
    bank role and no tenant key reaches it either way.

    Errors to branch on: `unauthenticated` (401) without a session or a key;
    `permission_denied` (403) without `proposals.review` or `proposals:review`;
    `unknown_key` (422) when `origin` is a value that is neither `agent` nor `user`;
    `validation_error` (422) when the page size or offset is out of range.
    """
    reviewer = require_reviewer(request)
    queryset = logic.queue(
        reviewer=reviewer,
        status=query.status,
        kind=query.kind,
        target_list=query.target_list,
        origin=query.origin,
        not_mine=query.not_mine,
    )
    total = queryset.count()
    rows = reading.queue_rows(list(queryset[page.offset : page.offset + page.limit]), language_order(request), reviewer=reviewer)
    return ProposalPage(items=rows, total=total)


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


@router.get(
    "/library-updates",
    response=LibraryUpdatesPage,
    auth=SESSION,
    operation_id="listLibraryUpdates",
    by_alias=True,
    summary="See what changed in the shared library since you last looked",
)
@requires_permission(perms.LIBRARY_READ)
@answers_problems
def list_library_updates(request: HttpRequest, query: Query[LibraryUpdatesQuery], page: Query[PageQuery]) -> LibraryUpdatesPage:
    """Every change that reached the shared library since this reader last marked it as seen
    with `POST /me/visit`, grouped by the day it arrived in the organisation's own time zone,
    the most recent day first. Call it for the "what changed" screen a reader opens when they
    come back from leave; `since` in the answer says what the list is measured from, and for
    a reader who has never marked the library as seen it is the start of the default window
    instead of an empty list.

    Each change is titled by the library record it touched, never by the request that carried
    it, and nobody's name appears: a change another organisation asked for reads exactly like
    any other. Duties outside this organisation's footprint are left out unless
    `outsideFootprint` asks for them, by the same rule the inventory applies, and each of
    those says in `outsideReason` which facets would have hidden it. A change to a shared
    list is never cut, because a list belongs to every organisation.

    What comes back are facts about the shared library. Whether a duty applies here, and
    whether this organisation complies with it, are its own judgements and are recorded
    elsewhere; a change appearing here decides neither and is not a task.

    Paginated: 20 changes by default and 100 at most, with a larger limit refused rather than
    quietly trimmed, and `total` counting every change since that moment. Nothing since then
    is a 200 with an empty days list and a total of 0, never a 404.

    Needs `library.read`, which every member holds, and a session in an organisation: an API
    key has no bookmark of its own, so this list is a person's.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403)
    without `library.read`; `not_found` (404) for a principal in no organisation;
    `validation_error` (422) when the page size or offset is out of range.
    """
    tenant = caller_tenant(request)
    membership = reading.membership_of(tenant, principal(request).subject_id)
    return updates.page(
        tenant,
        language_order(request, tenant=tenant),
        membership,
        kind=query.kind,
        outside_footprint=query.outside_footprint,
        limit=page.limit,
        offset=page.offset,
    )



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
    who = require_proposer(request)
    proposer = proposer_for(request)
    if who.kind is PrincipalKind.AGENT and who.agent_id is not None:
        # Copied from the key onto the proposal at this one write path, because the widened
        # `proposal_four_eyes` constraint compares agent ids and a check constraint cannot
        # dereference a key to find one (PRO-S13, PRO-S14, D-62, ADR 0054).
        proposer = replace(proposer, agent_id=who.agent_id)
    proposal, created = logic.create(
        kind=body.kind,
        title=body.title,
        payload=body.payload,
        proposer=proposer,
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
    return (201 if created else 200), logic.proposer_row(proposal)


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
    return reading.detail(logic.by_id(uuid_or_404(proposal_id)), language_order(request), reviewer=require_reviewer(request))


@router.post(
    "/proposals/{proposal_id}/approve",
    response=ProposalRow,
    auth=REVIEWER_AUTH,
    operation_id="approveProposal",
    by_alias=True,
    summary="Approve a proposal and let the change into the shared library",
)
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

    Needs the platform permission `proposals.review` from a person, stepped up fresh: the
    assertion id is written on the audit rows the approval leaves. Or the platform-only
    scope `proposals:review` from a key bound to an agent definition (D-62, ADR 0054): a
    key holds no passkey assertion, so it is never asked for one, and the audit rows the
    approval leaves carry no assertion id for its decision. Either way the reviewer is
    never the proposer, the same key, or a key of the same agent definition: the widened
    proposal_four_eyes constraint refuses that row on its own, whichever principal wrote
    it.

    Errors to branch on: `permission_denied` without `proposals.review` or
    `proposals:review`; `step_up_required` when a person calls without a fresh passkey
    assertion; `four_eyes_violation` when the reviewer is the person, key or agent who made
    the proposal, or a reviewing key names no agent definition; `invalid_transition` when
    the proposal was already approved or rejected, which is also what a repeated call
    answers, since nothing is ever applied twice; `source_missing` when a correction
    introduces a field the proposal never sourced; `validation_error` when a correction is
    offered on a kind that cannot be corrected or does not fit its payload; `unknown_key`
    when the payload names a row the library does not hold; `not_found` when there is no
    such proposal.
    """
    reviewer = require_reviewer(request)
    step_up_assertion_id = enforce_step_up(request) if reviewer.user is not None else None
    proposal = logic.approve(
        proposal=logic.by_id(uuid_or_404(proposal_id)),
        reviewer=reviewer,
        actor=reviewer.actor,
        note=body.note,
        payload_overrides=body.payload_overrides,
        step_up_assertion_id=step_up_assertion_id,
    )
    return logic.row(proposal)


@router.post("/proposals/{proposal_id}/reject", response=ProposalRow, auth=REVIEWER_AUTH, operation_id="rejectProposal", by_alias=True)
@answers_problems
def reject_proposal(request: HttpRequest, proposal_id: str, body: ProposalRejectBody) -> ProposalRow:
    reviewer = require_reviewer(request)
    proposal = logic.reject(
        proposal=logic.by_id(uuid_or_404(proposal_id)),
        reviewer=reviewer,
        actor=reviewer.actor,
        rejection_code=body.rejection_code,
        note=body.note,
    )
    return logic.row(proposal)
