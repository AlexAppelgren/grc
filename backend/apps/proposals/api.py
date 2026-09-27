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

from apps.proposals import batch, logic, private_approval, reading, updates
from apps.proposals.logic import Proposer, Reviewer
from apps.proposals.schemas import (
    LibraryUpdatesPage,
    ProposalBatch,
    ProposalBatchDecision,
    ProposalBatchInput,
    LibraryUpdatesQuery,
    ProposalApproveBody,
    ProposalCreateBody,
    ProposalDetail,
    ProposalPage,
    ProposalQuery,
    ProposalRejectBody,
    ProposalRow,
    PrivateProposalApproveBody,
    PrivateProposalPage,
    PrivateProposalRejectBody,
    PrivateProposalRow,
    TenantProposalPage,
    TenantProposalQuery,
)
from apps.shared import permissions as perms
from apps.shared.audit import Actor, ActorType
from apps.shared.authentication import ApiKeyAuth, PrincipalKind, SessionAuth
from apps.shared.errors import ProblemError
from apps.shared.permissions import enforce_step_up, requires_permission, requires_step_up
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
    "new_provision_version" (a provision's text in force from a date); "new_recurring_duty"
    (a schedule an obligation in force falls due on, as an RFC 5545 rule); "vocabulary_create", "vocabulary_relabel", "vocabulary_retire", "vocabulary_restore" or
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
    like an obligation version. A recurring duty names its obligation as `targetType`
    `obligation` and `targetId`, is sourced like an obligation version, field by field, and
    carries one RRULE line at a day or coarser without DTSTART, which must fall due at least
    once and at most `RECURRENCE_MAX_OCCURRENCES` times (120 unless the platform sets another
    number) in the next ten years; a key bound to no agent cannot propose one. A standard's text is licensed, so nothing of it enters: no
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
    `invalid_recurrence` (422) when a recurring duty's rule does not parse, is finer than a
    day, never falls due, or falls due more often than the cap in ten years;
    `validation_error` (422) for a body the schema or the kind's payload refuses, a
    `sourceUrl` that is not an https link on any kind, or a summary or text longer than
    `PROPOSAL_TEXT_MAX_CHARS` (50000 unless the platform sets another number);
    `standard_term_only_on_standards` (422) when the scope puts a standard's term on an
    obligation whose instrument is not a standard; `licensed_text` (422) for a provision or
    provision version under a standard, a source on a standard's obligation that is not
    an https link, a standard's new obligation whose `refLabel` is not the standard's
    official reference, or a `sourceLabel` under a standard that is anything but that
    reference; `one_conformance_obligation` (422) for a new obligation under a standard
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
    answers, since nothing is ever applied twice, and for a batch, which is decided row by
    row through `POST /proposal-batches/{batchId}/decide`; `source_missing` when a correction
    introduces a field the proposal never sourced, or changes a value without its fresh
    source in `fieldSources`; `validation_error` when a key sends no
    `decision` or a person sends one or names a run, and when a correction is offered on a
    kind that cannot be corrected or does not fit its payload; `unknown_key` when the
    payload names a row the library does not hold; `not_a_regime` when a new instrument's
    regime is not a term of the regime dimension; `duplicate_key` when a new record's key
    was taken while the proposal waited; `jurisdiction_term_mirrored` (422) when the payload
    adds or renames a term of a dimension that mirrors the jurisdiction list, or scopes an
    obligation with one, which a proposal filed before that rule may still ask for;
    `standard_term_only_on_standards` (422) when the payload, as proposed or as corrected,
    puts a standard's term on an obligation whose instrument is not a standard;
    `invalid_recurrence` (422) when a recurring duty's rule, as proposed or as corrected, no
    longer falls due between once and the cap in the ten years from today.
    """
    reviewer = require_reviewer(request)
    step_up_assertion_id = enforce_step_up(request) if reviewer.user is not None else None
    proposal = logic.approve(
        proposal=logic.by_id(uuid_or_404(proposal_id)),
        reviewer=reviewer,
        actor=reviewer.actor,
        note=body.note,
        payload_overrides=body.payload_overrides,
        field_sources=body.field_sources,
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
    (409) when the proposal was already approved or rejected, or is a batch, which is
    decided row by row through `POST /proposal-batches/{batchId}/decide`.
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


# ---------------------------------------------------------------------------------------
# Batch proposals (PRO-04, AGT-05; c11-proposal-batches-create)
# ---------------------------------------------------------------------------------------
def require_batch_proposer(request: HttpRequest) -> Proposer:
    """Who may file a batch: a platform person holding `proposals.review`, the console's
    re-tag, or a platform key holding `proposals:write`, which must then name an open run
    of its own (checked in `batch.create_batch`). Re-tagging the library is the platform's
    (AGT-05): a bank's session holds no platform permission, and a bank's key is refused
    here even though a bank's key may hold `proposals:write` for a single proposal. Neither
    403 carries a step-up: filing lets nothing into the library."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if who.tenant_id is not None or not who.has_scope(perms.SCOPE_PROPOSALS_WRITE):
            raise ProblemError(
                status=403,
                code="permission_denied",
                detail="This key does not have the scope for that.",
                required_permission=perms.SCOPE_PROPOSALS_WRITE,
            )
        return replace(proposer_for(request), agent_id=who.agent_id)
    if who.tenant_id is not None or not who.has_permission(perms.PROPOSALS_REVIEW):
        raise ProblemError(
            status=403, code="permission_denied", detail="You do not have access to this.", required_permission=perms.PROPOSALS_REVIEW
        )
    return proposer_for(request)


_BATCH_PATH = Path(
    ...,
    description=(
        "The batch, the UUID `POST /proposal-batches` returned and the queue lists as the proposal's "
        "`id`. A batch that does not exist, a proposal that is not a batch, and anything that is not a "
        "UUID answer `not_found`."
    ),
)


@router.post(
    "/proposal-batches",
    response={200: ProposalBatch, 201: ProposalBatch},
    auth=[SessionAuth(), ApiKeyAuth()],
    operation_id="createProposalBatch",
    by_alias=True,
    summary="Ask for one change to many library records at once, as one batch with a preview",
)
@answers_problems
def create_proposal_batch(request: HttpRequest, body: ProposalBatchInput) -> Any:
    """File a batch: one request that changes many shared library records the same way,
    such as putting a scope term on every duty it belongs on. Call it from the console's
    re-tag form, or from a platform agent's run that found a re-tag the library needs. The
    batch is one proposal in the queue, listed once with `isBatch` and `rowCount`, with a
    row per record carrying its preview: the record's fields before, as the library holds
    them now, and after, as approving the row would leave them. Nothing in the library
    changes until a second, independent reviewer approves a row.

    `kind` is "obligation_scope", a re-tag, the only batch kind today: per obligation, the
    scope terms to add and to take off, and the source for the new scope. It is checked in
    full before anything is stored: every obligation a library one in force, every term a
    live term and none of a dimension mirroring the jurisdiction list, every source an
    https link or a provision's stable key, and the standards rule: a standard's term only
    on a standard's obligation, which keeps exactly one, sourced by links alone. A batch
    holds at most `PROPOSAL_BATCH_MAX_ROWS` rows (100 unless the platform sets another
    number). The batch, its rows and its audit row are written in one transaction.

    Needs the platform permission `proposals.review` from a person, with no step-up since
    filing lets nothing in, or the scope `proposals:write` from a platform key, which names
    in `agentRunId` an open run of its own. No bank role and no bank's key reaches it:
    re-tagging the shared library is the platform's. Whoever files a batch never decides
    it, which the database enforces.

    Send an `Idempotency-Key`, because an agent retries: the same key with the same body
    answers **200** with the batch it already made and records the retry. A new batch
    answers **201**. Every text it arrives with is read by the injection screen and stored
    as it arrived; what the screen finds is returned in `riskFlags`.

    Errors to branch on: `unauthenticated` (401) without a session or a key;
    `permission_denied` (403) without `proposals.review` or `proposals:write`, and for a
    bank's session or key; `batch_too_large` (422) above `PROPOSAL_BATCH_MAX_ROWS` rows;
    `unknown_key` (422) for a kind that is not a batch kind, an obligation the library does
    not hold in force, or a term that is not a live term; `jurisdiction_term_mirrored`
    (422) for a term of a dimension that mirrors the jurisdiction list; `source_missing`
    (422) for an entry without a source; `standard_term_only_on_standards` (422) when a
    standard's term would sit on a law's obligation; `standard_term_required` (422) when a
    standard's obligation would carry no standard term or more than one; `licensed_text`
    (422) for a source on a standard's obligation that is not an https link, or a
    `sourceLabel` under a standard that is not its official reference; `run_not_open`
    (422) when a key names no run or a closed one; `run_budget_exhausted` (422) when the
    run has filed as many proposals as one run may; `not_found` (404) when the run is not
    one this key opened; `idempotency_conflict` (409) when the same proposer's
    `Idempotency-Key` arrives with a different body; `validation_error` (422) for a body
    the schema refuses, an obligation named twice, a term both added and removed, an entry
    that changes nothing, a source that is neither a link nor a provision's key, a
    `sourceUrl` that is not an https link, or an `Idempotency-Key` longer than 200
    characters.
    """
    # Ungated by design: logic-gate (proposals.review from the console or the proposals:write scope from a platform key; PRO-04, AGT-05).
    proposer = require_batch_proposer(request)
    proposal, created = batch.create_batch(
        kind=body.kind,
        title=body.title,
        payload=body.payload,
        proposer=proposer,
        agent_run_id=body.agent_run_id,
        idempotency_key=idempotency_key(request),
        model=body.model,
        source_label=body.source_label,
        source_url=body.source_url,
    )
    return (201 if created else 200), batch.read(proposal, language_order(request))


@router.get(
    "/proposal-batches/{batch_id}",
    response=ProposalBatch,
    auth=SESSION,
    operation_id="getProposalBatch",
    by_alias=True,
    summary="Open a batch proposal and read every record it would change, before and after",
)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def get_proposal_batch(request: HttpRequest, batch_id: str = _BATCH_PATH) -> ProposalBatch:
    """A batch as a reviewer decides it: the proposal the queue lists, and every row beneath
    it with the record it would change, by its own title and reference, the record's fields
    before and after, the source behind the change and where the row stands. Call it before
    deciding a batch, whole or row by row.

    The preview is what was computed when the batch was filed, never recomputed, so the
    reviewer decides on what was proposed. A pending row whose record has changed since is
    marked `stale`: it was previewed against another scope and cannot be approved. Every
    row comes back in one answer, since a batch holds at most `PROPOSAL_BATCH_MAX_ROWS`.
    Reading it changes nothing and records nothing; until a row is approved the library
    still says what it said.

    Needs the platform permission `proposals.review`. No bank role reaches it.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied`
    (403) without `proposals.review`; `not_found` (404) for a batch that does not exist, a
    proposal that is not a batch, and anything that is not a UUID.
    """
    return batch.read(batch.by_id(uuid_or_404(batch_id)), language_order(request))


@router.post(
    "/proposal-batches/{batch_id}/decide",
    response=ProposalBatch,
    auth=SESSION,
    operation_id="decideProposalBatch",
    by_alias=True,
    summary="Approve or reject a batch's rows, one by one or all the rest at once",
)
@requires_permission(perms.PROPOSALS_REVIEW)
@requires_step_up
@answers_problems
def decide_proposal_batch(request: HttpRequest, body: ProposalBatchDecision, batch_id: str = _BATCH_PATH) -> ProposalBatch:
    """Decide a batch: approve or reject the rows named in `rows`, and give every row still
    pending one decision in `rest`, so a reviewer rejects the few that are wrong and
    approves the others in one call. An approved row writes its record's new fields into the
    library: for a re-tag, the obligation's scope terms become the row's `after`, and the
    search index follows. A rejected one needs a reason from the "rejection_reason" list and
    changes nothing. Every row decision, with the record's fields before and after, and one
    more entry naming every row's outcome are written to the audit trail in the same
    transaction as the library write, each carrying the passkey assertion; a failure part
    way writes nothing. A row is decided once. The batch closes when no row is left pending:
    `approved` if any row was approved, else `rejected`. The answer is the batch as it then
    stands.

    A pending row whose record was retired or changed since the batch was filed is `stale`
    and cannot be approved: named for approval it fails the whole call, while under an
    approved `rest` it is left pending and the others still apply, for the reviewer to reject.

    Needs the platform permission `proposals.review` from a person, stepped up fresh with a
    passkey. No API key reaches this route, and an agent never decides a batch. The reviewer
    is never the batch's proposer, the person who asked for the re-tag, which the database
    enforces on every row and on the batch.

    Errors to branch on: `unauthenticated` (401) without a session, a key included;
    `permission_denied` (403) without `proposals.review`, a bank's session included;
    `step_up_required` (403) without a fresh passkey assertion; `not_found` (404) for a batch
    that does not exist, a proposal that is not a batch, and anything that is not a UUID;
    `four_eyes_violation` (409) when the reviewer proposed the batch, which decides nothing;
    `invalid_transition` (409) when the batch or a named row is already decided;
    `stale_write` (409) when a row named for approval is stale, or every row left to approve
    is; `reason_required` (422) for a rejection without a live row of the rejection reason
    list; `unknown_key` (422) for a row id that is not a row of this batch;
    `validation_error` (422) for a decision that is not `approved` or `rejected`, a row
    named twice, a reason on an approval, and a body that decides nothing.
    """
    user = caller_user(request)
    proposal = batch.decide(
        proposal=batch.by_id(uuid_or_404(batch_id)),
        decision=body,
        reviewer=Reviewer(actor=actor_for(request, user), user=user),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return batch.read(proposal, language_order(request))


# ---------------------------------------------------------------------------------------
# The bank's own queue (INV-07, OWN-03, PRO-03; D-57, ADR 0050, ADR 0059; d89-proposal-owner)
# ---------------------------------------------------------------------------------------
_PRIVATE_PATH = Path(
    ...,
    description=(
        "The organisation's own proposal, the UUID its queue returns as `id`. Another organisation's "
        "proposal, a proposal to the shared library, one that does not exist, and anything that is not a "
        "UUID all answer `not_found`."
    ),
)


@router.get(
    "/private-proposals",
    response=PrivateProposalPage,
    auth=SESSION,
    operation_id="listPrivateProposals",
    by_alias=True,
    summary="Read your organisation's own queue of records waiting for a decision",
)
@requires_permission(perms.PRIVATE_RECORDS_APPROVE)
@answers_problems
def list_private_proposals(request: HttpRequest, page: Query[PageQuery]) -> PrivateProposalPage:
    """Every proposal of this organisation's own records: the instruments and obligations the
    shared library does not hold, filed by a person here or found by the organisation's own
    research agent for a regulation it added to its scope. Call it for the organisation's own
    queue, where a second person decides each one. Nothing here is the shared library's, and
    nothing here ever reaches the platform console or another organisation: row-level security
    keeps each organisation's rows its own.

    Reading it changes nothing and records nothing. Paginated: 20 rows by default and 100 at
    most, with a larger limit refused rather than quietly trimmed, oldest first so the queue is
    worked in the order it was filed. Nothing waiting is a 200 with an empty items list and a
    total of 0, never a 404.

    Needs `private_records.approve`, which the Compliance officer and Approver roles hold. It is
    never a platform permission and never an API key scope, so no key and no platform session
    reaches it.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403)
    without `private_records.approve`; `validation_error` (422) when the page size or offset is
    out of range; `not_built` (501) for every call. Published ahead of the logic that will fill
    it, and answering 501 until that ships.
    """
    return private_approval.queue(limit=page.limit, offset=page.offset)


@router.post(
    "/private-proposals/{proposal_id}/approve",
    response=PrivateProposalRow,
    auth=SESSION,
    operation_id="approvePrivateProposal",
    by_alias=True,
    summary="Approve a record of your organisation's own and add it to your own inventory",
)
@requires_permission(perms.PRIVATE_RECORDS_APPROVE)
@requires_step_up
@answers_problems
def approve_private_proposal(request: HttpRequest, body: PrivateProposalApproveBody, proposal_id: str = _PRIVATE_PATH) -> PrivateProposalRow:
    """The only door into this organisation's own inventory. Call it once a person here has
    read the proposal and its sources and is satisfied the record is right. In one transaction
    it applies the payload through the same apply code as the shared queue, writes the record
    and its first version as the organisation's own, and writes the audit and outbox rows in
    the organisation's own zone. The record then reads "Private to us", only to this
    organisation, and is never indexed, embedded or sent to a model. The answer is the
    proposal as it then stands, with `status` `approved`.

    Needs `private_records.approve`, stepped up fresh with a passkey; the assertion's id is
    written on the audit rows. The approver is never the proposer: the four-eyes constraint
    refuses that row on its own. An agent never approves here.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403)
    without `private_records.approve`; `step_up_required` (403) without a fresh passkey
    assertion; `not_found` (404) for another organisation's proposal, a proposal to the shared
    library, one that does not exist and anything that is not a UUID; `validation_error` (422)
    for a field the body does not name or a note longer than 2000 characters; `not_built`
    (501) for every proposal of this organisation's own. Published ahead of the logic that
    will fill it, and answering 501 until that ships.
    """
    return private_approval.approve(
        proposal=private_approval.by_id(uuid_or_404(proposal_id)),
        note=body.note,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )


@router.post(
    "/private-proposals/{proposal_id}/reject",
    response=PrivateProposalRow,
    auth=SESSION,
    operation_id="rejectPrivateProposal",
    by_alias=True,
    summary="Turn down a record of your organisation's own with a reason",
)
@requires_permission(perms.PRIVATE_RECORDS_APPROVE)
@answers_problems
def reject_private_proposal(request: HttpRequest, body: PrivateProposalRejectBody, proposal_id: str = _PRIVATE_PATH) -> PrivateProposalRow:
    """Close a proposal of this organisation's own as refused. Call it once a person here has
    found the record wrong, already held or outside what the organisation needs. Nothing in the
    organisation's inventory changes; the reason and the note are stored on the proposal, which
    is closed for good, and the decision's audit row is written in the organisation's own zone.
    A rejected proposal is never reopened: its proposer files a new one. The answer is the
    proposal as it then stands, with `status` `rejected`.

    Needs `private_records.approve`, with no step-up, since a rejection adds nothing. The
    person rejecting is never the proposer.

    Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403)
    without `private_records.approve`; `not_found` (404) for another organisation's proposal, a
    proposal to the shared library, one that does not exist and anything that is not a UUID;
    `validation_error` (422) for a field the body does not name or a note longer than 2000
    characters; `not_built` (501) for every proposal of this organisation's own. Published ahead
    of the logic that will fill it, and answering 501 until that ships.
    """
    return private_approval.reject(
        proposal=private_approval.by_id(uuid_or_404(proposal_id)),
        rejection_code=body.rejection_code,
        note=body.note,
    )
