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
    """Who may work the review queue, on every one of its four routes (PRO-S13, PRO-S14,
    ID-S31, D-62, ADR 0054): a person holding `proposals.review`, or a platform key bound to
    an agent definition and holding the scope `proposals:review`.

    A key is refused with 403 `permission_denied`, naming the scope, when it lacks
    `proposals:review` or carries a tenant: the scope is platform-only
    (`PLATFORM_ONLY_SCOPES`), so a bank's key is refused here even if its scopes list somehow
    names it, beside the 422 a bank's key is refused it with at creation
    (apps/identity/api_keys_logic.py). A key holding the scope but bound to no agent
    definition is refused with 403 `agent_not_bound`: four eyes compares agent definitions,
    and a key with none would be compared on a null, so an unbound key can never stand in
    for the independent second agent the scope is for. The widened `proposal_four_eyes`
    constraint refuses that decision on its own too, if this gate is ever bypassed.

    Never applies a step-up: a key holds no passkey assertion, so a person's step-up stays
    the job of the one route that needs one (`approve_proposal`)."""
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
        if who.agent_id is None:
            raise ProblemError(
                status=403,
                code="agent_not_bound",
                detail="This key is bound to no agent definition, so nothing it confirmed could be told apart from what it proposed.",
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
    quietly trimmed, and `total` counting every proposal matching the filters across every
    page. Oldest filed first by default, the order the Waiting tab is worked in; `order=newest`
    turns it round for the Approved and Rejected tabs. Either way the id breaks a tie, so
    paging is repeatable. Nothing matching is a 200 with an empty
    items list and a total of 0, never a 404.

    Needs the platform permission `proposals.review` from a person, or the platform-only
    scope `proposals:review` from a key bound to an agent definition (D-62, ADR 0054). No
    bank role and no tenant key reaches it either way.

    Errors to branch on: `unauthenticated` (401) without a session or a key;
    `permission_denied` (403) without `proposals.review` or `proposals:review`;
    `agent_not_bound` (403) for a key holding the scope but bound to no agent definition;
    `unknown_key` (422) when `origin` is a value that is neither `agent` nor `user`, or
    `order` one that is neither `oldest` nor `newest`;
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
        order=query.order,
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



# What an agent files after a run read the authority's page: a new version of one duty,
# sourced field by field, under the run that found it (the prototype's research-payments
# reform, never a real bank's data).
_CREATE_EXAMPLE = {
    "requestBody": {
        "content": {
            "application/json": {
                "example": {
                    "kind": "new_obligation_version",
                    "title": "Version 2 of the research assessment duty, in force 1 October 2026",
                    "targetType": "obligation",
                    "targetId": "7b1f2c4e-8d3a-4c61-9f0b-2e5a7c9d1a44",
                    "changeId": "b7e1c0a4-9f3d-4f6a-9c21-5d8e2f0a1b33",
                    "agentRunId": "3c2a9f1e-6b7d-4e58-a1c4-0f9d8e7b6a52",
                    "model": "agent pipeline 0.4",
                    "payload": {
                        "summaries": {
                            "sv": "Investeringsanalys från tredje part får tas emot endast om den betalas med institutets egna medel eller från ett analyskonto.",
                            "en": "Research from third parties may be received only if it is paid from the institution's own resources or from a research payment account.",
                        },
                        "originalLanguage": "sv",
                        "isMachine": True,
                        "effectiveFrom": "2026-10-01",
                        "effectiveFromPrecision": "day",
                    },
                    "fieldSources": {
                        "summaries.sv": "https://www.fi.se/en/published/news/2026/research-payments/",
                        "summaries.en": "https://www.fi.se/en/published/news/2026/research-payments/",
                        "effectiveFrom": "https://www.fi.se/en/published/news/2026/research-payments/",
                    },
                    "sourceLabel": "Finansinspektionen, board decision 15 September 2026",
                    "sourceUrl": "https://www.fi.se/en/published/news/2026/research-payments/",
                }
            }
        }
    }
}


@router.post(
    "/proposals",
    response={200: ProposalRow, 201: ProposalRow},
    auth=[SessionAuth(), ApiKeyAuth()],
    operation_id="createProposal",
    by_alias=True,
    summary="Ask for a change to the shared library, with the source behind every changed value",
    openapi_extra=_CREATE_EXAMPLE,
)
@answers_problems
def create_proposal(request: HttpRequest, body: ProposalCreateBody) -> Any:
    """Put one change to the shared library into the review queue, where a second and
    independent reviewer approves, corrects or rejects it; nothing in the library changes
    until then. Call it when a run has read new wording for a duty at the authority's own
    page, and when a person asks for a value on a shared list. `kind` says what is asked
    for: "new_obligation_version" (a new summary of one duty in force from a date, with its
    scope terms); "new_instrument" (a law, regulation, guideline or standard edition the
    library does not hold yet, with its regime); "new_obligation" (a duty the library does
    not hold yet, under an instrument it does, with its first summary and scope);
    "new_provision" (a node of a law's text, with its first verbatim text);
    "new_provision_version" (a provision's text in force from a date); "vocabulary_create", "vocabulary_relabel", "vocabulary_retire", "vocabulary_restore" or
    "vocabulary_merge" (a row of a shared list); or "term_create" or "term_update" (a
    taxonomy term).

    Who may call it: a bank's member with `proposals.create`, a platform editor with
    `library_vocab.manage`, or an API key with the scope `proposals:write`. A key bound to
    an agent must name, in `agentRunId`, a run that same key has open, so every proposal an
    agent filed can be traced to the model and the night that produced it: naming none, or
    a run that is closed, answers `run_not_open` (422). A run named by anybody is checked
    the same way, so another key's run, and any run a person names, answers `not_found`
    (404) exactly as a run that never existed does. A bank's own key, bound to no agent,
    names no run.

    A new obligation version carries a source for every value it changes, in
    `fieldSources`: a link to the authority's page or a provision of the library, and none
    for a value it leaves alone. A new instrument or obligation names no `targetType` or
    `targetId`, carries a source for every fact it sets, each an https link since the record
    has no provision of its own yet, and gives `sourceUrl`, the link the new record keeps
    as its own source. An instrument's `regime` is a term of the regime dimension, written
    `regime:<key>`. A new provision is sourced like a new record, and a provision version
    like an obligation version. A standard's text is licensed, so nothing of it enters: no
    provision under a standard, and only https links as sources on a standard's one
    conformance obligation, which carries exactly one standard term. The proposal is
    linked to the bank it was filed in, and
    the platform's reviewers see only that it came from a bank, never who asked. The
    proposal and its audit row are written in one transaction.

    Send an `Idempotency-Key`, because an agent retries: the same key with the same body
    answers **200** with the proposal it already made, and records that the retry
    happened. An agent retries before it closes the run: once the run is closed, the retry
    answers `run_not_open` (422) like any other filing against that run. A new proposal
    answers **201**.

    Every text the proposal arrives with — its title, the texts of its payload, its field
    sources, its source and its model — is read by the injection screen and stored exactly as it
    arrived. What the screen finds is returned in `riskFlags` and shown in the queue, and
    while a flag stands no agent may approve the proposal: a person decides it. A run files
    at most `WATCH_RUN_MAX_PROPOSALS` proposals (50 unless the platform sets another
    number); a retry of one it filed is not a new proposal and still answers.

    Errors to branch on: `run_not_open` (422) when a key bound to an agent names no run or
    a closed one; `run_budget_exhausted` (422) when the run has already filed as many
    proposals as one run may, so close it and open another; `not_found` (404) when the run
    named is not one this key opened;
    `source_missing` (422) when a changed value carries no source, or a new record no
    `sourceUrl`; `unknown_key` (422) for a kind, a list, a language, a term, a target
    obligation or provision, an instrument, a parent provision, a provision kind, a level, a jurisdiction, an authority or a duty type the
    library does not hold; `not_a_regime` (422) when a new instrument's regime is not a
    term of the regime dimension; `jurisdiction_term_mirrored` (422) when the payload scopes
    an obligation with a term of a dimension that mirrors the jurisdiction list;
    `duplicate_key` (409) when a new record's key is already a record's;
    `validation_error` (422) for a body the schema or the kind's payload refuses;
    `standard_term_only_on_standards` (422) when the scope puts a standard's term on an
    obligation whose instrument is not a standard; `licensed_text` (422) for a provision or
    provision version under a standard, a source on a standard's obligation that is not
    an https link, or a standard's new obligation whose `refLabel` is not the standard's
    official reference; `one_conformance_obligation` (422) for a new obligation under a standard
    that already holds one; `standard_term_required` (422) when a standard's obligation
    would carry no standard term, or more than one; `idempotency_conflict` (409) when the
    same proposer's `Idempotency-Key` arrives with a different body or from another bank
    (a key is its sender's own: another caller's value files a proposal of its own);
    `validation_error` (422) also for an `Idempotency-Key` longer than 200 characters;
    `permission_denied` (403) without
    the permission or the scope; `unauthenticated` (401) without a credential.
    """
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
    auth=REVIEWER_AUTH,
    operation_id="getProposal",
    by_alias=True,
    summary="Open one proposal and read it against the library version it is compared with",
)
@answers_problems
def get_proposal(
    request: HttpRequest,
    proposal_id: str = Path(
        ...,
        description=(
            "The proposal to open, the UUID the queue returns as `id`. A proposal that does "
            "not exist, and anything that is not a UUID, answers `not_found`."
        ),
    ),
) -> ProposalDetail:
    """One proposal as a reviewer decides it: the record it would change, the wording it is
    compared with against what this would make it say, the two compared sentence by
    sentence, the source behind every changed value, and the scope before and after. Call it
    before approving, correcting or rejecting: read it, open the sources, and only then
    decide.

    What it is compared with depends on where it stands. A proposal that was not approved,
    open or rejected, is read against the version in force today and the scope the record
    carries now, so its comparison moves when a version comes into force or another is
    approved. An approved one is pinned: it is read against the version numbered just before
    the one it wrote, and the scope its approval found, so its comparison stays the same
    whatever the calendar or a later version says.

    What comes back is a request and not the library: until the proposal is approved the
    library still says what the version in force says. Reading it changes nothing and
    records nothing. A proposal filed inside a bank arrives without its proposer, as in the
    list.

    Needs the platform permission `proposals.review` from a person, or the platform-only
    scope `proposals:review` from a key bound to an agent definition (D-62, ADR 0054): an
    independent agent opens the same proposal a person opens before it decides. No bank role
    and no bank's key reaches it.

    Errors to branch on: `unauthenticated` (401) without a session or a key;
    `permission_denied` (403) without `proposals.review` or `proposals:review`, or for a
    bank's key; `agent_not_bound` (403) for a key holding the scope but bound to no agent
    definition; `not_found` (404) for a proposal that does not exist and for anything that
    is not a UUID.
    """
    reviewer = require_reviewer(request)
    return reading.detail(logic.by_id(uuid_or_404(proposal_id)), language_order(request), reviewer=reviewer)


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
    it. An agent approves every kind whose record can name the agent that confirmed it: an
    obligation version, a new instrument, a new obligation, a library list row and a
    taxonomy term (D-79). What it confirmed never reads as a person's check: the record
    names the confirming agent, a translation it approves stays labelled machine-made,
    every list or term label it writes is stored machine-made, and its correction may
    reword a summary but never move `originalLanguage`, which answers `validation_error`.

    An agent's approval is a model call, and every model call is logged: a key sends the
    call behind its approval in `decision` and the open run of its own key it was made in
    in `agentRunId`, and in the same transaction the approval writes one entry of the AI
    output log under the purpose "agent_review", as the agent's own report, while its audit
    row names the run (D-80). A person sends neither.

    Errors to branch on: `permission_denied` without `proposals.review` or
    `proposals:review`; `agent_not_bound` for a key holding the scope but bound to no agent
    definition; `step_up_required` when a person calls without a fresh passkey assertion;
    `run_not_open` (422) when a key names no run in `agentRunId`, or a run it has closed;
    `not_found` (404) when that run is one another key opened, or when there is no such
    proposal; `four_eyes_violation` when the reviewer is the person, key or agent who made
    the proposal; `person_review_required` when an agent approves a kind whose record
    cannot name its confirming agent, a new provision or a provision's new text, which
    waits for a person; `risk_flagged` (409) when an agent approves a proposal whose
    `riskFlags` is not empty, or corrects it with text the injection screen flags, which
    waits for a person who reads the flag; `invalid_transition` when the proposal was
    already approved or rejected, which is also what a repeated or simultaneous second call
    answers, since nothing is ever applied twice; `source_missing` when a correction
    introduces a field the proposal never sourced; `validation_error` when a key sends no
    `decision` or a person sends one or names a run, and when a correction is offered on a
    kind that cannot be corrected or does not fit its payload; `unknown_key` when the
    payload names a row the library does not hold; `not_a_regime` when a new instrument's
    regime is not a term of the regime dimension; `duplicate_key` when a new record's key
    was taken while the proposal waited; `jurisdiction_term_mirrored` (422) when the payload
    adds or renames a term of a dimension that mirrors the jurisdiction list, or scopes an
    obligation with one, which a proposal filed before that rule may still ask for;
    `standard_term_only_on_standards` (422) when the payload, as proposed or as corrected,
    puts a standard's term on an obligation whose instrument is not a standard.
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
        decision=body.decision,
        agent_run_id=body.agent_run_id,
    )
    return logic.row(proposal)


@router.post(
    "/proposals/{proposal_id}/reject",
    response=ProposalRow,
    auth=REVIEWER_AUTH,
    operation_id="rejectProposal",
    by_alias=True,
    summary="Turn a proposal down with a reason the proposer can act on",
)
@answers_problems
def reject_proposal(
    request: HttpRequest,
    body: ProposalRejectBody,
    proposal_id: str = Path(
        ...,
        description=(
            "The proposal being decided, the UUID the queue returns as `id`. A proposal "
            "that does not exist, and anything that is not a UUID, answers `not_found`."
        ),
    ),
) -> ProposalRow:
    """Close a proposal as refused. Call it once a reviewer has read the proposal and its
    sources and found the change wrong, already made, badly worded or outside what the
    library covers; nothing in the shared library changes, now or later.

    In one transaction it stores the reason and the note on the proposal, closes it as
    `rejected` for good and writes the decision's audit row, whose outbox event is what
    tells the proposer, with the reason. The answer is the proposal row as it now stands,
    with `status` `rejected`, `rejectionCode` and `reviewNote` set. A rejected proposal is
    never reopened: the proposer files a new one.

    Needs the platform permission `proposals.review` from a person, with no step-up, since
    a rejection lets nothing into the library. Or the platform-only scope
    `proposals:review` from a key bound to an agent definition (D-62, ADR 0054), which may
    reject any kind, a vocabulary or term proposal included, because a rejection writes no
    library row (D-79). Either way the reviewer is never the proposer, the same key, or a
    key of the same agent definition. An agent's rejection is a model call and is logged as
    one: a key sends the call behind it in `decision` and the open run of its own key in
    `agentRunId`, the rejection writes one entry of the AI output log under the purpose
    "agent_review" in the same transaction, and its audit row names the run (D-80). A
    person sends neither.

    Errors to branch on: `permission_denied` (403) without `proposals.review` or
    `proposals:review`, or for a bank's key; `agent_not_bound` (403) for a key holding the
    scope but bound to no agent definition; `reason_required` (422) when `rejectionCode`
    or `note` is empty, or the code is not a live row of the "rejection_reason" vocabulary;
    `run_not_open` (422) when a key names no run, or a run it has closed; `not_found` (404)
    when that run is one another key opened, and when there is no such proposal;
    `validation_error` (422) when a key sends no `decision`, when a person sends one or
    names a run, and for a field the body does not name; `four_eyes_violation` (409) when
    the reviewer is the person, key or agent who made the proposal; `invalid_transition`
    (409) when the proposal was already approved or rejected.
    """
    reviewer = require_reviewer(request)
    proposal = logic.reject(
        proposal=logic.by_id(uuid_or_404(proposal_id)),
        reviewer=reviewer,
        actor=reviewer.actor,
        rejection_code=body.rejection_code,
        note=body.note,
        decision=body.decision,
        agent_run_id=body.agent_run_id,
    )
    return logic.row(proposal)
