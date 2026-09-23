"""Routes of the watch app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Two gates here serve more than one principal, so they are logic gates listed in
`UNGATED_BY_DESIGN` and still answer the structured 403 with `requiredPermission`
(apps/shared/permissions.py, apps/taxonomy/http.py):

- **The registry reads** serve a person with `watch.read` and an agent's key with
  `library:read`: an agent must know which sources to check before it checks them
  (AGT-02). They also serve a console session with `sources.manage`, which has no tenant
  and therefore no `watch.read`, so the read-only console Sources page calls a real route
  (`c5-contract-api-screens`, ruling 3).
- **The change facts** are written by an agent's key with `changes:write` and corrected by
  a library editor's session with `proposals.review` (PRO-01: a change's type, flags and
  scope are library facts, and no tenant role holds that permission).

Registering a source is a library editor's alone, and attaching a fetched page is a key's
alone: a page arrives from the agent that screened it (AGT-07), never from a screen.

The reads split by zone, which is why there are two lists of changes. `GET /changes` is a
bank's feed: it joins that bank's own case and answers under `watch.read`.
`GET /console/changes` is the library editor's queue: it joins no case, because a platform
console session has no tenant and would otherwise read an empty feed, and it answers under
`proposals.review`, which no tenant role holds.

No route here writes an inventory row. Everything the agent may change about the library
itself goes through a proposal (AC-PRO1).
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Body, Header, Path, Query, Router

from apps.agents import runs
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, PrincipalKind, SessionAuth
from apps.shared.permissions import requires_permission, requires_scope
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, deny, principal, require_any
from apps.taxonomy.reading import language_order
from apps.watch import curation, reading, registration, sources
from apps.watch.schemas import (
    COVERAGE_EXAMPLE,
    LINKS_MAX,
    OBLIGATION_LINK_EXAMPLE,
    SOURCE_EXAMPLE,
    WatchChange,
    WatchChangeDetail,
    WatchChangeDocument,
    WatchChangeDocumentInput,
    WatchChangeEvent,
    WatchChangeEventInput,
    WatchChangeInput,
    WatchChangePage,
    WatchChangePatch,
    WatchChangeQuery,
    WatchConsoleChangePage,
    WatchConsoleChangeQuery,
    WatchObligationChangePage,
    WatchObligationLink,
    WatchObligationLinkInput,
    WatchSourceCheckInput,
    WatchSourceCoverage,
    WatchSourceInput,
    WatchSourceOut,
    WatchSourcePatch,
)

router = Router(tags=["Watch"])

KEY = ApiKeyAuth()
SESSION = SessionAuth()
SESSION_OR_KEY = [SessionAuth(), ApiKeyAuth()]
IdempotencyKey = Header(
    None,
    alias="Idempotency-Key",
    description=(
        "A value of your own that names this attempt, so a call that timed out can be "
        "repeated safely: a retry answers what the first attempt wrote instead of writing it "
        "a second time. Send one on every agent write, because a run retries. Each operation "
        "says below what its own retry answers, and repeating a value against a different "
        "body is a conflict rather than a silent overwrite."
    ),
)

# What each path parameter means to a caller, hoisted out of the signatures so a route
# body stays one line of gate, schema and call (playbook 4.1).
_CHANGE_ID = (
    "The library change to read, as a UUID. The same id for every bank; the bank's own case "
    "is resolved from the caller's session, never from the path. A change the caller cannot "
    "see answers 404, never 403, so no id can be probed for."
)
_OBLIGATION_ID = (
    "The library obligation whose related changes to list, as a UUID. A record the caller "
    "cannot see answers 404, never 403, so no id can be probed for what another bank holds "
    "privately."
)
_CHANGE_ID_WRITE = (
    "The library change being corrected, as a UUID, the `id` the registration answered. It "
    "is the same change for every bank: what is written here every bank reads. A change no "
    "longer in the library answers 404, never 403, so no id can be probed for."
)
_EVENT_ID = (
    "The timeline entry being corrected, as a UUID, the `id` the entry was added under. An "
    "entry belonging to another change answers 404 exactly as one that never existed does."
)
_SOURCE_ID = (
    "The registered source being changed, as a UUID, the `id` `GET /sources` answers. The "
    "registry is shared, so this is the same id for every bank. A source no longer "
    "registered answers 404, never 403."
)
_RUN_ID = (
    "The agent run this check is filed against, as a UUID, the `id` `POST /agent-runs` "
    "answered. It must be a run this key opened and has not closed; another key's run "
    "answers 404 exactly as one that never existed does."
)
# Three of these answer a bare array, and an array carries no schema of its own to hang an
# example on, so each names one beside its media type (apps/home/api.py does the same for
# its feeds). The obligation links travel as an array in both directions.
_SOURCES_EXAMPLE = {"responses": {200: {"content": {"application/json": {"example": [SOURCE_EXAMPLE]}}}}}
_COVERAGE_EXAMPLE = {"responses": {200: {"content": {"application/json": {"example": [COVERAGE_EXAMPLE]}}}}}
_LINKS_EXAMPLE = {
    "requestBody": {
        "content": {
            "application/json": {
                "example": [{"obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17", "confidence": 0.82}]
            }
        }
    },
    "responses": {200: {"content": {"application/json": {"example": [OBLIGATION_LINK_EXAMPLE]}}}},
}


def require_watch_reader(request: HttpRequest) -> None:
    """The registry and its coverage log: a person with `watch.read`, an agent's key with
    `library:read` so a run knows what to check (WAT-01, AGT-02), or a library editor with
    `sources.manage` reading the console's own Sources page. The editor is named here
    because a console session has no tenant and so holds no tenant permission; without it
    the read-only console page would call a route it could never pass (ruling 3)."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if not who.has_scope(perms.SCOPE_LIBRARY_READ):
            raise deny(perms.SCOPE_LIBRARY_READ)
        return
    require_any(request, perms.WATCH_READ, perms.SOURCES_MANAGE)


def require_change_writer(request: HttpRequest) -> None:
    """A change's library facts: an agent's key with `changes:write`, or a library editor
    with `proposals.review` (WAT-02, WAT-03, PRO-01). A bank's key is refused even with the
    scope (`tenant_agents_not_available`): in R1 every run and what it files is the
    platform's (item 14)."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        # The reason first: a bank's key has its watch scopes withheld when it is resolved
        # (D-78), so the scope test alone would never name it.
        runs.refuse_tenant_key(who)
        if not who.has_scope(perms.SCOPE_CHANGES_WRITE):
            raise deny(perms.SCOPE_CHANGES_WRITE)
        return
    require_any(request, perms.PROPOSALS_REVIEW)


# ---------------------------------------------------------------------------------------
# The source registry and the coverage log (WAT-01)
# ---------------------------------------------------------------------------------------
@router.get(
    "/sources",
    response=list[WatchSourceOut],
    auth=SESSION_OR_KEY,
    operation_id="listSources",
    by_alias=True,
    summary="See every place bleqq watches for new regulation",
    openapi_extra=_SOURCES_EXAMPLE,
)
@answers_problems
def list_sources(request: HttpRequest) -> Any:
    """The registry of sources: what each one is, who publishes it, how often it is meant to
    be checked and whether automated checks are on. Call it from the console's Sources page,
    and from an agent at the start of a run, which is how a run knows what to check and
    reports its checks against the right name.

    A read: it changes nothing and writes no audit row. A person's session holding
    `watch.read` in their own bank, a library editor's console session holding
    `sources.manage`, or an agent's key holding `library:read`. The registry is a library
    fact: the same list for every bank, and no bank's own source is in it (a bank's private
    sources are WAT-06 and arrive later).

    The whole registry comes back in one answer, ordered by name; it is tens of rows, not
    thousands, so it does not page. An empty registry is a 200 with an empty list, never a
    404. Errors: `permission_denied` without one of those three, `unauthenticated` without a
    credential.
    """
    # Ungated by design: logic-gate (watch.read in a tenant, or a key with library:read).
    require_watch_reader(request)
    return sources.list_sources(language_order(request))


@router.get(
    "/sources/coverage",
    response=list[WatchSourceCoverage],
    auth=SESSION_OR_KEY,
    operation_id="getSourceCoverage",
    by_alias=True,
    summary="Check that nothing we watch has gone unchecked",
    openapi_extra=_COVERAGE_EXAMPLE,
)
@answers_problems
def get_source_coverage(request: HttpRequest) -> Any:
    """The coverage log's bottom line, one row per source: when it was last swept, how that
    sweep ended, what went wrong if it failed, and whether the source has now gone stale.
    Call it for the console's Source coverage page and whenever somebody asks how we know a
    reform was not missed.

    A read: it changes nothing and writes no audit row. The same three callers as
    `GET /sources`, and the same library fact for every bank.

    `overdue` is computed by the server, never stored: true when the last
    `SOURCE_STALE_AFTER_CHECKS` sweeps of the source all failed, or when longer than the
    source's own cadence plus `SOURCE_STALE_GRACE_HOURS` has passed since the last sweep
    that succeeded. Both are settings. Two rows are never overdue and a reader should not
    treat them alike: a source whose automated checks are switched off, which is meant not
    to be checked, and a source with `lastStatus` `never`, which has no log to measure.
    Re-checks are left out of all of this on purpose — a re-check looks again at a record
    the source already gave us, so a run full of them never makes a source look fresh.

    One row per registered source, ordered by name, and no paging. A registry with nothing
    in it is a 200 with an empty list. Errors: `permission_denied` without `watch.read`,
    `sources.manage` or the `library:read` scope; `unauthenticated` without a credential.
    """
    # Ungated by design: logic-gate (watch.read in a tenant, or a key with library:read).
    require_watch_reader(request)
    return sources.source_coverage(language_order(request))


@router.post(
    "/sources",
    response={201: WatchSourceOut},
    auth=SESSION,
    operation_id="createSource",
    by_alias=True,
    summary="Add a place for the agents to watch",
)
@requires_permission(perms.SOURCES_MANAGE)
@answers_problems
def create_source(request: HttpRequest, body: WatchSourceInput) -> Any:
    """Register a public page, a legal database or an open-web sweep for bleqq's agents to
    check, with the cadence we promise for it. Call it when a supervisor opens a new
    newsroom, when a register moves, or when a market we have started watching brings a
    publisher we do not yet follow. The answer is the registry row as it now stands.

    A library editor's session holding `sources.manage`, which is a platform permission and
    which no bank's role holds: the registry is shared by every bank, so one bank never adds
    to it. No API key scope reaches this route either — an agent reports on the registry and
    never edits it. There is no passkey step-up and no `If-Match`: a registry row carries no
    version, and adding a place to look at is not a decision about the law.

    The source is registered with automated checks on. Nothing is checked in this call: the
    first sweep is the next run's, and until one happens the coverage log says `never`. The
    row and its audit row, which names who registered it, are written in one transaction,
    and the keys are resolved first, so a refusal stores nothing.

    Errors to branch on: `unknown_key` (422) when `kind` names no active row of the
    source-kind vocabulary, with the valid keys listed, or when `authorityId` names no
    authority the library holds; `duplicate_key` (409) when a source of that name is already
    registered — names are unique across the library, so change the row that exists;
    `validation_error` (422) for a body the schema refuses, including a `url` that is not
    http or https; `permission_denied` (403) without `sources.manage`; `unauthenticated`
    (401) without a session.
    """
    return 201, sources.create_source(
        actor=actor_for(request), order=language_order(request), body=body
    )


@router.patch(
    "/sources/{source_id}",
    response=WatchSourceOut,
    auth=SESSION,
    operation_id="updateSource",
    by_alias=True,
    summary="Move a watched source, or stop checking it",
)
@requires_permission(perms.SOURCES_MANAGE)
@answers_problems
def update_source(
    request: HttpRequest,
    body: WatchSourcePatch,
    source_id: uuid.UUID = Path(..., description=_SOURCE_ID),
) -> Any:
    """Point a registered source at the page the publisher has moved it to, change how often
    we promise to check it, or switch its automated checks off. Call it when a fetch starts
    failing because an address changed, and when a publisher's terms mean we must stop
    checking automatically (WAT-07, D-45). The answer is the row as it now stands.

    A library editor's session holding `sources.manage`, the same platform permission that
    registers one, and no key. A field left out, and a field sent as null, both mean "leave
    it alone"; the name and the kind are not on this shape and never move, because a
    different place to watch is a different source and the name is what a run reports
    against. No step-up and no `If-Match`: a registry row carries no version.

    Switching `active` off stops the automated checks and keeps every check already logged:
    the coverage log is never rewritten, and the source stops being reported stale, because
    it is now meant not to be checked. The row and its audit row, which holds the row as it
    was and as it now is, are written in one transaction.

    Errors to branch on: `not_found` (404) when no source has that id, answered the same way
    for a source that never existed so no id can be probed for; `validation_error` (422) for
    a body the schema refuses, including a `url` that is not http or https and a
    `checkFrequency` outside `daily`, `weekly` and `monthly`; `permission_denied` (403)
    without `sources.manage`; `unauthenticated` (401) without a session.
    """
    return sources.update_source(
        actor=actor_for(request), order=language_order(request), source_id=source_id, body=body
    )


@router.post(
    "/agent-runs/{run_id}/source-checks",
    response={204: None},
    auth=KEY,
    operation_id="recordSourceCheck",
    by_alias=True,
    summary="Log that a run checked a source, and how it went",
)
@runs.refuses_tenant_keys
@requires_scope(perms.SCOPE_SOURCES_WRITE)
@answers_problems
def record_source_check(
    request: HttpRequest,
    body: WatchSourceCheckInput,
    run_id: uuid.UUID = Path(..., description=_RUN_ID),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    """Write one line of the coverage log: this run looked at this source at this time, and
    this is how it went. Call it once per source a sweep visits, whether or not anything new
    was found, and once per library record a re-check looks at (`kind` `recheck`). Finding
    nothing is a result and must still be logged — an unlogged check is indistinguishable
    from one that never happened, and the coverage log is the whole evidence that a reform
    was not missed.

    An agent's key holding the scope `sources:write`, on a run that key has open; no
    person's session reaches it, and no scope here registers a source or touches the
    obligations inventory. A key that belongs to a bank is refused with
    `tenant_agents_not_available` (403), because in this release every run is the platform's. The line and its audit row, with the agent behind the key as the
    actor, are written in one transaction, and every refusal comes before the write, so a
    rejected call logs nothing.

    Answers 204 with no body: a line of a log has nothing to read back. Repeating it is
    safe in the sense that matters — a second identical line changes no conclusion the
    coverage page draws, because it reads the most recent sweep — so send an
    `Idempotency-Key` and retry a call that timed out rather than leaving a gap.

    Errors to branch on: `run_not_open` (422) when the run named is closed, so nothing can
    be filed against it any more; `unknown_source` (422) when `sourceName` names no
    registered source — read `GET /sources` at run start and report against those names;
    `validation_error` (422) when a failed check carries no `error`, when a successful one
    carries an error, when a `recheck` names no `subjectType` and `subjectId`, or when a
    `sweep` names one; `not_found` (404) when the run belongs to another key or to nobody,
    answered alike so no run id can be probed for; `tenant_agents_not_available` (403) from
    a key that belongs to a bank; `permission_denied` (403) without `sources:write`;
    `unauthenticated` (401) without a key.
    """
    sources.record_check(
        who=principal(request), actor=actor_for(request), run_id=run_id, body=body
    )
    return 204, None


# ---------------------------------------------------------------------------------------
# Reading changes: the bank's feed and the library editor's queue (WAT-02, FP-03, FP-04)
# ---------------------------------------------------------------------------------------
@router.get(
    "/changes",
    response=WatchChangePage,
    auth=SESSION,
    operation_id="listChanges",
    by_alias=True,
    summary="See the regulatory changes that reach your bank",
)
@requires_permission(perms.WATCH_READ)
@answers_problems
def list_changes(request: HttpRequest, query: Query[WatchChangeQuery]) -> Any:
    """The watch feed: every reform bleqq has registered that touches this bank, newest key
    date first, with the bank's own case beside each one. Call it for the feed screen, for a
    weekly briefing (`week`), and to find the changes nobody has triaged yet (`tab=new`) or
    whose "So what?" is still an AI draft (`unconfirmedSoWhat=true`).

    A read: it changes nothing and writes no audit row. A person's session holding
    `watch.read` in their own bank; no API key reaches it, because every row joins that
    bank's own case. What the reader sees is filtered by the bank's footprint by default,
    which `footprint=all` lifts and `footprint=watched` widens to the markets the bank
    watches; the library half of every row is the same for every bank and the `case` half
    never leaves this one.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. An empty feed is a
    200 with an empty `items` and a `total` of 0, never a 404. Errors: `permission_denied`
    when the session lacks `watch.read`, `unauthenticated` when there is no session,
    `not_found` when the session belongs to no bank, and `validation_error` for a filter
    value the schema refuses — including the designed `inFootprint`, which this build
    replaced with the single `footprint` value.

    `footprint=watched` is answered and empty for now: a change's jurisdiction is derived
    from its authority, which the market view is still waiting for, and an empty answer is
    the honest one until it lands.
    """
    tenant = caller_tenant(request)
    return reading.list_changes(tenant, language_order(request, tenant=tenant), query)


@router.get(
    "/console/changes",
    response=WatchConsoleChangePage,
    auth=SESSION,
    operation_id="listConsoleChanges",
    by_alias=True,
    summary="Work the queue of change facts nobody has confirmed",
)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def list_console_changes(request: HttpRequest, query: Query[WatchConsoleChangeQuery]) -> Any:
    """The platform console's queue: the changes carrying a type, a flag, a scope term or an
    obligation link that an agent proposed and no library editor has confirmed. Call it to
    find what needs a library editor's eye, narrow it by authority, or switch to
    `confirmed=all` to look a change up.

    A read: it changes nothing and writes no audit row. A library editor's session holding
    `proposals.review`, which no tenant role holds, so a bank's member is refused here and
    reads `GET /changes` instead. It joins no case and answers no bank's judgement: a console
    session belongs to no tenant, and a change's classification is a library fact that only
    `proposals.review` may correct (PRO-01).

    Pages with `limit` and `offset`, 20 rows by default and 100 at most, newest first by when
    the reform was first seen. An empty queue is a 200 with an empty `items` and a `total` of
    0. Errors: `permission_denied` without `proposals.review`, `unauthenticated` without a
    session, `validation_error` for a filter value the schema refuses.
    """
    return reading.list_console_changes(language_order(request), query)


@router.get(
    "/changes/{change_id}",
    response=WatchChangeDetail,
    auth=SESSION,
    operation_id="getChange",
    by_alias=True,
    summary="Read one regulatory change and what it means for your bank",
)
@requires_permission(perms.WATCH_READ)
@answers_problems
def get_change(request: HttpRequest, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    """The whole change page: the reform's sourced facts — its type, its flags, its scope,
    its timeline from consultation to in force, the pages it was found on and the obligations
    it affects — and beside them the reader's own bank's case, with its urgency, its
    footprint verdict and its "So what?". Call it when a person opens a change from the feed,
    a briefing or an obligation.

    A read: it changes nothing and writes no audit row. A person's session holding
    `watch.read` in their own bank. Everything outside `case` is a library fact shared by
    every bank and changed only by a library editor or through a proposal; everything inside
    `case` is this bank's own and is invisible to bleqq, to every other bank and to every
    model endpoint. An obligation link says on itself whether a library editor confirmed it;
    `confirmed: false` is a suggestion an agent made and must not be read as checked, nor as
    a statement that the change does not touch that duty. Each flag and each scope term says
    the same on itself, as `{ref, confidence, suggested}` exactly as a feed row answers it:
    `suggested: true` is the agent's reading and not a checked fact, `confidence` is the
    agent's own number and orders nothing here. A library editor confirms them in the console
    queue rather than here, and a bank never confirms one at all.

    Errors: `not_found` when no change has that id, when the caller may not see it, or when
    the session belongs to no bank — all answered the same way on purpose, so no id can be
    probed; `permission_denied` without `watch.read`; `unauthenticated` without a session.
    """
    tenant = caller_tenant(request)
    return reading.get_change(tenant, language_order(request, tenant=tenant), change_id)


@router.get(
    "/obligations/{obligation_id}/changes",
    response=WatchObligationChangePage,
    auth=SESSION,
    operation_id="listObligationChanges",
    by_alias=True,
    summary="See the changes that affect one obligation, and how many are still open for you",
)
@requires_permission(perms.WATCH_READ)
@answers_problems
def list_obligation_changes(
    request: HttpRequest,
    page: Query[PageQuery],
    obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID),
) -> Any:
    """The related-changes panel of an obligation, and the `openCount` the inventory shows
    beside it: how many of those changes still have work open for this bank — a case that is
    neither closed nor dismissed. Call it from the obligation page, and for the "n open
    changes" count on an inventory row.

    A read: it changes nothing and writes no audit row. A person's session holding
    `watch.read` in their own bank. The links themselves are library facts with the agent's
    confidence on them, the same for every bank; `openCount` is computed from the reader's
    own cases, so two banks reading one obligation see different numbers. It counts cases and
    says nothing about whether the bank complies, which is a separate fact in the register
    (REG-02).

    The links a library editor has confirmed come first; the rest follow the feed's own
    order, newest key date first. Pages with `limit` and `offset`, 20 rows by default and
    100 at most, and `openCount` is counted over every linked change rather than over the
    page, so paging never changes it. An obligation no change touches is a 200 with an empty
    `items`, a `total` of 0 and an `openCount` of 0. Errors: `not_found` when no obligation
    has that id, when the caller may not see it, or when the session belongs to no bank;
    `permission_denied` without `watch.read`; `unauthenticated` without a session.
    """
    tenant = caller_tenant(request)
    return reading.list_obligation_changes(tenant, language_order(request, tenant=tenant), obligation_id, page)


# ---------------------------------------------------------------------------------------
# Registering a change and its pages (WAT-02, AGT-07)
# ---------------------------------------------------------------------------------------
@router.post(
    "/changes",
    response={200: WatchChange, 201: WatchChange},
    auth=SESSION_OR_KEY,
    operation_id="createChange",
    by_alias=True,
    summary="File a reform the run has just sighted",
)
@answers_problems
def create_change(request: HttpRequest, body: WatchChangeInput, idempotency_key: str | None = IdempotencyKey) -> Any:
    """Put one reform into the shared library, with the timeline the source states, the
    pages it was found on, what the run thinks it is about and the obligations it may touch.
    Call it once per reform a sweep finds, and from the console when a library editor files
    one by hand. This is the call that starts the work: every active bank gets a case for
    the change, with its own footprint verdict, a moment later.

    An agent's key needs the scope `changes:write` and a library editor's session the
    permission `proposals.review`, which no bank's role holds. `agentRunId` must name a run
    the calling key has open, so every library row an agent wrote can be traced to the night
    that wrote it: a key that names none answers `run_not_open` (422), exactly as a closed
    run does. A library editor filing one by hand names no run. A key that belongs to a bank
    is refused with `tenant_agents_not_available` (403) whatever scopes it holds, because in
    this release every run, and everything a run files, is the platform's.

    One reform is one record, and `stableKey` is what makes that true. Sending a key the
    library already holds answers **200** with the change that exists: the pages the call
    carries are attached to it as duplicates, a milestone it did not have is added, and not
    one field of the stored change is changed. A new key answers **201**. That is what makes
    the call safe to retry — send an `Idempotency-Key` as well, but the stable key is the
    guarantee. Correcting a fact already stored is `PATCH /changes/{changeId}`, never a
    second registration.

    Everything the call files about what the reform is — its type, its flags, its scope
    terms and its obligation links — is stored as a suggestion, with nobody named as having
    confirmed it, whoever sent it. A reader must not treat any of it as checked.

    **The drafted “So what?” comes from the run that read the source** (D-66). Send
    it in `soWhat` with the model and the model version that wrote it and the public pages
    it rests on; the words are stored on the shared change, copied unconfirmed into every
    bank's case and recorded in the AI output log, where each bank's own person confirms or
    rewrites its own copy. **The model and the version are the caller's own report about
    itself, not something bleqq measured**, and the log row says so
    (`modelMetadataReportedByAgent`). In R1 every agent is bleqq's own, so that is a
    reporting boundary; it becomes a trust boundary the day a bank runs its own agent
    against this route. Send no `soWhat` and the change simply carries no draft: nothing
    else about the call changes, and a later `PATCH /changes/{changeId}` may still file one.
    On a merge — a `stableKey` the library already holds — a `soWhat` is filed only when the
    change has no draft yet, like a page and a milestone: the merge adds what is missing and
    rewrites nothing.

    Every page's text is screened for embedded instructions before it is stored (AGT-07) and
    what the screen finds is recorded in that page's `riskFlags`. The text itself is kept
    exactly as it arrived, because it is evidence: it is never executed, never rendered as
    HTML and never followed. A flag is a warning about the page, not about the reform.

    The change, its timeline, its pages, its classification, its audit row and the outbox
    row that opens the cases all go in one transaction, and every key is resolved first, so
    a refusal stores nothing at all.

    Errors to branch on: `run_not_open` (422) when a key names no run in `agentRunId`, or
    one that is closed;
    `unknown_key` (422) when `changeType`, `suggestedUrgency`, a flag key, a `termId`, an
    `obligationId` or `authorityCode` names a row the library does not hold or has retired,
    with the valid keys listed for a vocabulary; `jurisdiction_term_mirrored` (422) when a
    `termId` is a term that mirrors the jurisdiction list, since a change's market comes
    from its authority and never from a tag; `validation_error` (422) for a body the
    schema refuses, for the same obligation named twice, for two pages both marked primary,
    and for a `soWhat` whose words carry no model, no model version or no citation; `not_found` (404) when `agentRunId` names a run belonging to another key;
    `tenant_agents_not_available` (403) from a key that belongs to a bank;
    `permission_denied` (403) without the scope or the permission; `unauthenticated` (401)
    without a credential.
    """
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return registration.register_change(
        who=principal(request), actor=actor_for(request), order=language_order(request), body=body
    )


@router.post(
    "/changes/{change_id}/documents",
    response={201: WatchChangeDocument},
    auth=KEY,
    operation_id="addChangeDocument",
    by_alias=True,
    summary="Attach a page a reform was found on",
)
@runs.refuses_tenant_keys
@requires_scope(perms.SCOPE_CHANGES_WRITE)
@answers_problems
def add_change_document(
    request: HttpRequest,
    body: WatchChangeDocumentInput,
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID_WRITE),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    """Record one more public page behind a reform already registered: its address, its
    headline, who published it, when it was fetched and a hash of what was fetched. Call it
    when a later run finds the same reform somewhere else, and when the first call carried
    only the page it started from. The answer is the page as it was stored.

    An agent's key holding the scope `changes:write`, and no person's session: a page
    arrives from the run that fetched and screened it (AGT-07), never from a screen. No
    scope here reaches the obligations inventory. A key that belongs to a bank is refused
    with `tenant_agents_not_available` (403), because in this release every run is the
    platform's.

    The text of the page is never stored. What is kept is the address, the headline, the
    publisher, the time and a hash — for a standards publisher that is all we may keep
    (WAT-07, D-45) — plus what the injection screen found, in `riskFlags`. A page whose
    address this change already carries answers the page that is already there instead of
    doubling it, which is what makes this safe for a run to retry; send an
    `Idempotency-Key` as well.

    The page and its audit row are written in one transaction.

    Errors to branch on: `validation_error` (422) when the change already has a primary page
    and this one is marked primary too, and for a body the schema refuses, including a `url`
    that is not http or https; `not_found` (404) when no change has that id;
    `tenant_agents_not_available` (403) from a key that belongs to a bank;
    `permission_denied` (403) without `changes:write`; `unauthenticated` (401) without a key.
    """
    return registration.add_document(
        who=principal(request), actor=actor_for(request), order=language_order(request), change_id=change_id, body=body
    )


# ---------------------------------------------------------------------------------------
# A change's facts, timeline and obligation links (WAT-03, WAT-04)
# ---------------------------------------------------------------------------------------
@router.patch(
    "/changes/{change_id}",
    response=WatchChange,
    auth=SESSION_OR_KEY,
    operation_id="updateChange",
    by_alias=True,
    summary="Correct what a registered change is and what it is about",
)
@answers_problems
def update_change(
    request: HttpRequest,
    body: WatchChangePatch,
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID_WRITE),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    """Move the library facts of a reform already registered: its title, its type, its
    summary, the date that drives "coming up", the flags that say what it is about and the
    taxonomy terms that say who it reaches. Call it when a run reads the source again and
    has something better than it filed the first time, and when a library editor corrects
    what a run got wrong. The answer is the change as it now stands.

    `flags` and `termIds` each replace the whole set they name, so send the full set and
    never a delta; every other field is left exactly as it was when it is left out or sent
    as null. Nothing here is versioned, so no `If-Match` is taken and no ETag is checked;
    the record that carries a version is the bank's own case, which this call never touches.

    An agent's key needs the scope `changes:write` and a library editor's session the
    permission `proposals.review`, which no bank's role holds: a change's classification is
    a library fact and a bank neither writes nor confirms one, so a key that belongs to a
    bank is refused with `tenant_agents_not_available` (403). Two things only the editor
    may set: `status` and `supersededBy`, because deciding that a reform has been replaced
    or withdrawn is a reading of the law and not a sighting of it.

    Everything written here is a suggestion. A flag or a term arrives with `suggested` true
    and nobody named as having confirmed it, whoever sent it, and a reader must not treat it
    as checked. Confirming one is a library editor's act on a library row and is not built
    yet, so a call that would drop or overwrite something already confirmed answers
    `not_built` to that editor and is refused outright to a key. The whole call is one
    transaction that writes an audit row naming who changed which facts, and the keys are
    resolved before anything is stored, so a refusal stores nothing.

    **A drafted “So what?” may be filed here too** (D-66, WAT-05): send `soWhat`
    with the words, the model and the model version that wrote them and the public pages
    they rest on. The words replace the change's draft and reach every bank whose copy is
    still that draft; a bank that has confirmed or rewritten its own keeps its wording,
    because a bank's words are its own. One row is written in the AI output log per send, so
    the earlier draft stays on the record. **The model and the version are the caller's own
    report about itself, not something bleqq measured**, and the log row says so
    (`modelMetadataReportedByAgent`): in R1 every agent is bleqq's own, so that is a
    reporting boundary, and it becomes a trust boundary the day a bank runs its own agent
    against this route.

    Sending it again with the same body simply writes the same facts, so `Idempotency-Key`
    costs nothing here and no retry can duplicate anything — except that each `soWhat` sent
    is one more row in the AI output log, which is a ledger of calls and never deduplicated.

    Errors to branch on: `unknown_key` (422) when `changeType`, a flag key, a term id or
    `supersededBy` names a row the library does not hold or has retired, with the valid keys
    listed for a vocabulary; `jurisdiction_term_mirrored` (422) when a term id is a term
    that mirrors the jurisdiction list, since a change's market comes from its authority and
    never from a tag; `editor_only_field` (422) when a key sends `status` or
    `supersededBy`; `confirmed_fact` (422) when a key's new set would drop a flag or a term
    a library editor confirmed; `not_built` (501) when an editor's call would do the same,
    which is the confirmation half of this feature; `validation_error` (422) for a field the
    schema refuses, for a change asked to supersede itself, and for a `soWhat` whose words
    carry no model, no model version or no citation; `not_found` (404) when no
    change has that id; `tenant_agents_not_available` (403) from a key that belongs to a
    bank; `permission_denied` (403) without the scope or the permission;
    `unauthenticated` (401) without a credential.
    """
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.update_change_facts(
        who=principal(request),
        actor=actor_for(request),
        order=language_order(request),
        change_id=change_id,
        body=body,
    )


@router.post(
    "/changes/{change_id}/events",
    response={201: WatchChangeEvent},
    auth=SESSION_OR_KEY,
    operation_id="addChangeEvent",
    by_alias=True,
    summary="Add a milestone to a reform's timeline",
)
@answers_problems
def add_change_event(
    request: HttpRequest,
    body: WatchChangeEventInput,
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID_WRITE),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    """Put one step of a reform's path on its timeline — the consultation opening, the
    consultation closing, the board adopting it, the rules coming into force, a transition
    ending. Call it as a run learns each step from the source; the change screen renders
    them in `sortOrder`, and the answer is the entry as it was stored.

    A milestone's date is a plain calendar date with a precision beside it and never a
    timestamp, so a screen prints "June 2026" where the source said only the month and never
    invents a day. `occurred` is what the source says has happened, not what the clock says.

    An agent's key needs the scope `changes:write` and a library editor's session the
    permission `proposals.review`. The timeline is a library fact shared by every bank; no
    bank's date is ever here, and a key that belongs to a bank is refused with
    `tenant_agents_not_available` (403). The entry and its audit row are written in one
    transaction.

    A retry is safe: the entry's label is its name on that change, so posting "Consultation
    closed" twice with the same dates answers the entry that is already there instead of
    doubling the timeline. The same label carrying different dates is `duplicate_key`,
    because storing either version would lose the other; correct the entry you already have
    instead.

    Errors to branch on: `duplicate_key` (409) when this change already has a milestone with
    that label and other dates; `validation_error` (422) for a body the schema refuses,
    including a timestamp where a plain date belongs and a precision outside `day`, `month`,
    `quarter` and `year`; `not_found` (404) when no change has that id;
    `tenant_agents_not_available` (403) from a key that belongs to a bank; `permission_denied`
    (403) without the scope or the permission; `unauthenticated` (401) without a credential.
    """
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.add_event(actor=actor_for(request), change_id=change_id, body=body)


@router.patch(
    "/changes/{change_id}/events/{event_id}",
    response=WatchChangeEvent,
    auth=SESSION_OR_KEY,
    operation_id="updateChangeEvent",
    by_alias=True,
    summary="Correct a milestone on a reform's timeline",
)
@answers_problems
def update_change_event(
    request: HttpRequest,
    body: WatchChangeEventInput,
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID_WRITE),
    event_id: uuid.UUID = Path(..., description=_EVENT_ID),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    """Restate one entry of a reform's timeline: reword it, give it the date the source has
    now stated, sharpen its precision, move it in the order or mark that it has happened.
    Call it when a later run reads a firmer date than the one filed, and when a library
    editor corrects a run. The answer is the entry as it now stands.

    The body is the entry as it should now read and not a delta: it is the same shape that
    adds one, so a field you leave out takes that shape's default — `occurred` false,
    `sortOrder` 0, no date and no source page. Send the whole entry.

    An agent's key needs the scope `changes:write` and a library editor's session the
    permission `proposals.review`; a key that belongs to a bank is refused with
    `tenant_agents_not_available` (403). A timeline is a library fact shared by every bank,
    and nothing here is versioned, so no `If-Match` is taken. The entry and its audit row, which
    holds the entry as it was and as it now is, are written in one transaction.

    Errors to branch on: `validation_error` (422) for a body the schema refuses, including a
    timestamp where a plain date belongs and a precision outside `day`, `month`, `quarter`
    and `year`; `not_found` (404) when no change has that id, or the entry belongs to
    another change — the two are answered alike so no id can be probed;
    `tenant_agents_not_available` (403) from a key that belongs to a bank;
    `permission_denied` (403) without the scope or the permission; `unauthenticated` (401)
    without a credential.
    """
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.update_event(actor=actor_for(request), change_id=change_id, event_id=event_id, body=body)


@router.put(
    "/changes/{change_id}/obligations",
    response=list[WatchObligationLink],
    auth=SESSION_OR_KEY,
    operation_id="replaceChangeObligations",
    by_alias=True,
    summary="Say which obligations a change affects",
    openapi_extra=_LINKS_EXAMPLE,
)
@answers_problems
def replace_change_obligations(
    request: HttpRequest,
    # Capped like the same list inside `WatchChangeInput`: a key sends this one, and an
    # uncapped array is an unbounded body to parse and hold (playbook 11.2).
    body: list[WatchObligationLinkInput] = Body(..., max_length=LINKS_MAX),
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID_WRITE),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    """Set the obligations in the shared inventory that this reform touches. Call it when a
    run has matched a change against the library, and when a library editor adds one the run
    missed. The answer is the whole set as it now stands, most confident first.

    The body is the whole set and not a delta: an obligation left out is unlinked, and at
    most 200 links may travel in one call. A link never creates an obligation and no key
    scope reaches the inventory, so an id the library does not hold, or one it has retired,
    is refused rather than invented. Naming the same obligation twice in one body is refused
    too, because the two entries carry two confidences and keeping either would lose the
    other.

    An agent's key needs the scope `changes:write` and a library editor's session the
    permission `proposals.review`; a key that belongs to a bank is refused with
    `tenant_agents_not_available` (403). `origin` records which of the two drew the link and never
    changes afterwards; `confidence` is the model's own number, is null when a person set
    the link, and orders the list and nothing else.

    Two decisions that look alike and are not. `confirmed` here is a library editor's, and a
    confirmed link reads the same for every bank; confirming one is not built yet, so a call
    that would drop a link somebody has confirmed answers `not_built` to an editor and is
    refused outright to a key. A bank accepting or removing a suggested link is a different
    act entirely, lives on that bank's own case, is invisible to everyone else and changes
    no row here — so `false` never means "not related", only "nobody has confirmed it".

    The set and its audit row are written in one transaction, and sending the same set again
    leaves it exactly as it was, so a retry costs nothing.

    Errors to branch on: `unknown_key` (422) when an `obligationId` names no active
    obligation of the library; `validation_error` (422) when the same obligation is named
    twice, or for a body the schema refuses, including more than 200 links;
    `confirmed_fact` (422) when a key's new set would drop a link a library editor
    confirmed; `not_built` (501) when an editor's call would do the same, which is the
    confirmation half of this feature; `not_found` (404) when no change has that id;
    `tenant_agents_not_available` (403) from a key that belongs to a bank;
    `permission_denied` (403) without the scope or the permission; `unauthenticated` (401)
    without a credential.
    """
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.set_obligation_links(
        who=principal(request),
        actor=actor_for(request),
        order=language_order(request),
        change_id=change_id,
        body=body,
    )
