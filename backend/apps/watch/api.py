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

from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, PrincipalKind, SessionAuth
from apps.shared.permissions import requires_permission, requires_scope
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import answers_problems, deny, principal, require_any
from apps.watch import curation, reading, registration, sources
from apps.watch.schemas import (
    LINKS_MAX,
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
IdempotencyKey = Header(None, alias="Idempotency-Key")

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
    with `proposals.review` (WAT-02, WAT-03, PRO-01)."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if not who.has_scope(perms.SCOPE_CHANGES_WRITE):
            raise deny(perms.SCOPE_CHANGES_WRITE)
        return
    require_any(request, perms.PROPOSALS_REVIEW)


# ---------------------------------------------------------------------------------------
# The source registry and the coverage log (WAT-01)
# ---------------------------------------------------------------------------------------
@router.get("/sources", response=list[WatchSourceOut], auth=SESSION_OR_KEY, operation_id="listSources", by_alias=True)
@answers_problems
def list_sources(request: HttpRequest) -> Any:
    # Ungated by design: logic-gate (watch.read in a tenant, or a key with library:read).
    require_watch_reader(request)
    return sources.list_sources()


@router.get(
    "/sources/coverage",
    response=list[WatchSourceCoverage],
    auth=SESSION_OR_KEY,
    operation_id="getSourceCoverage",
    by_alias=True,
)
@answers_problems
def get_source_coverage(request: HttpRequest) -> Any:
    # Ungated by design: logic-gate (watch.read in a tenant, or a key with library:read).
    require_watch_reader(request)
    return sources.source_coverage()


@router.post("/sources", response={201: WatchSourceOut}, auth=SESSION, operation_id="createSource", by_alias=True)
@requires_permission(perms.SOURCES_MANAGE)
@answers_problems
def create_source(request: HttpRequest, body: WatchSourceInput) -> Any:
    return sources.create_source()


@router.patch(
    "/sources/{source_id}", response=WatchSourceOut, auth=SESSION, operation_id="updateSource", by_alias=True
)
@requires_permission(perms.SOURCES_MANAGE)
@answers_problems
def update_source(request: HttpRequest, source_id: uuid.UUID, body: WatchSourcePatch) -> Any:
    return sources.update_source()


@router.post(
    "/agent-runs/{run_id}/source-checks",
    response={204: None},
    auth=KEY,
    operation_id="recordSourceCheck",
    by_alias=True,
)
@requires_scope(perms.SCOPE_SOURCES_WRITE)
@answers_problems
def record_source_check(
    request: HttpRequest, run_id: uuid.UUID, body: WatchSourceCheckInput, idempotency_key: str | None = IdempotencyKey
) -> Any:
    return sources.record_check()


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
    when the session lacks `watch.read`, `unauthenticated` when there is no session, and
    `validation_error` for a filter value the schema refuses — including the designed
    `inFootprint`, which this build replaced with the single `footprint` value.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    return reading.list_changes()


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

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    return reading.list_console_changes()


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
    model endpoint. A classification an agent proposed carries `suggested: true` until a
    library editor confirms it, and must not be read as checked.

    Errors: `not_found` when no change has that id, or when the caller may not see it — the
    two are answered the same way on purpose, so no id can be probed; `permission_denied`
    without `watch.read`; `unauthenticated` without a session.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    return reading.get_change()


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

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. An obligation no
    change touches is a 200 with an empty `items`, a `total` of 0 and an `openCount` of 0.
    Errors: `not_found` when no obligation has that id or the caller may not see it;
    `permission_denied` without `watch.read`; `unauthenticated` without a session.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    return reading.list_obligation_changes()


# ---------------------------------------------------------------------------------------
# Registering a change and its pages (WAT-02, AGT-07)
# ---------------------------------------------------------------------------------------
@router.post(
    "/changes",
    response={200: WatchChange, 201: WatchChange},
    auth=SESSION_OR_KEY,
    operation_id="createChange",
    by_alias=True,
)
@answers_problems
def create_change(request: HttpRequest, body: WatchChangeInput, idempotency_key: str | None = IdempotencyKey) -> Any:
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return registration.register_change()


@router.post(
    "/changes/{change_id}/documents",
    response={201: WatchChangeDocument},
    auth=KEY,
    operation_id="addChangeDocument",
    by_alias=True,
)
@requires_scope(perms.SCOPE_CHANGES_WRITE)
@answers_problems
def add_change_document(
    request: HttpRequest,
    change_id: uuid.UUID,
    body: WatchChangeDocumentInput,
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    return registration.add_document()


# ---------------------------------------------------------------------------------------
# A change's facts, timeline and obligation links (WAT-03, WAT-04)
# ---------------------------------------------------------------------------------------
@router.patch(
    "/changes/{change_id}", response=WatchChange, auth=SESSION_OR_KEY, operation_id="updateChange", by_alias=True
)
@answers_problems
def update_change(
    request: HttpRequest, change_id: uuid.UUID, body: WatchChangePatch, idempotency_key: str | None = IdempotencyKey
) -> Any:
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.update_change_facts()


@router.post(
    "/changes/{change_id}/events",
    response={201: WatchChangeEvent},
    auth=SESSION_OR_KEY,
    operation_id="addChangeEvent",
    by_alias=True,
)
@answers_problems
def add_change_event(
    request: HttpRequest, change_id: uuid.UUID, body: WatchChangeEventInput, idempotency_key: str | None = IdempotencyKey
) -> Any:
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.add_event()


@router.patch(
    "/changes/{change_id}/events/{event_id}",
    response=WatchChangeEvent,
    auth=SESSION_OR_KEY,
    operation_id="updateChangeEvent",
    by_alias=True,
)
@answers_problems
def update_change_event(
    request: HttpRequest,
    change_id: uuid.UUID,
    event_id: uuid.UUID,
    body: WatchChangeEventInput,
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.update_event()


@router.put(
    "/changes/{change_id}/obligations",
    response=list[WatchObligationLink],
    auth=SESSION_OR_KEY,
    operation_id="replaceChangeObligations",
    by_alias=True,
)
@answers_problems
def replace_change_obligations(
    request: HttpRequest,
    change_id: uuid.UUID,
    # Capped like the same list inside `WatchChangeInput`: a key sends this one, and an
    # uncapped array is an unbounded body to parse and hold (playbook 11.2).
    body: list[WatchObligationLinkInput] = Body(..., max_length=LINKS_MAX),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    # Ungated by design: logic-gate (a key with changes:write, or a library editor with proposals.review).
    require_change_writer(request)
    return curation.set_obligation_links()
