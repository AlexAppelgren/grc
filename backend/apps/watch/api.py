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
from apps.taxonomy.http import actor_for, answers_problems, deny, principal, require_any
from apps.taxonomy.reading import language_order
from apps.watch import curation, reading, registration, sources
from apps.watch.schemas import (
    LINKS_MAX,
    OBLIGATION_LINK_EXAMPLE,
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
# The obligation links travel as a bare array in both directions, and an array carries no
# schema of its own to hang an example on (apps/home/api.py does the same for its feeds).
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
    a library fact and a bank neither writes nor confirms one. Two things only the editor
    may set: `status` and `supersededBy`, because deciding that a reform has been replaced
    or withdrawn is a reading of the law and not a sighting of it.

    Everything written here is a suggestion. A flag or a term arrives with `suggested` true
    and nobody named as having confirmed it, whoever sent it, and a reader must not treat it
    as checked. Confirming one is a library editor's act on a library row and is not built
    yet, so a call that would drop or overwrite something already confirmed answers
    `not_built` to that editor and is refused outright to a key. The whole call is one
    transaction that writes an audit row naming who changed which facts, and the keys are
    resolved before anything is stored, so a refusal stores nothing.

    Sending it again with the same body simply writes the same facts, so `Idempotency-Key`
    costs nothing here and no retry can duplicate anything.

    Errors to branch on: `unknown_key` (422) when `changeType`, a flag key, a term id or
    `supersededBy` names a row the library does not hold or has retired, with the valid keys
    listed for a vocabulary; `editor_only_field` (422) when a key sends `status` or
    `supersededBy`; `confirmed_fact` (422) when a key's new set would drop a flag or a term
    a library editor confirmed; `not_built` (501) when an editor's call would do the same,
    which is the confirmation half of this feature; `validation_error` (422) for a field the
    schema refuses, and for a change asked to supersede itself; `not_found` (404) when no
    change has that id; `permission_denied` (403) without the scope or the permission;
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
    bank's date is ever here. The entry and its audit row are written in one transaction.

    A retry is safe: the entry's label is its name on that change, so posting "Consultation
    closed" twice with the same dates answers the entry that is already there instead of
    doubling the timeline. The same label carrying different dates is `duplicate_key`,
    because storing either version would lose the other; correct the entry you already have
    instead.

    Errors to branch on: `duplicate_key` (409) when this change already has a milestone with
    that label and other dates; `validation_error` (422) for a body the schema refuses,
    including a timestamp where a plain date belongs and a precision outside `day`, `month`,
    `quarter` and `year`; `not_found` (404) when no change has that id; `permission_denied`
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
    permission `proposals.review`. A timeline is a library fact shared by every bank, and
    nothing here is versioned, so no `If-Match` is taken. The entry and its audit row, which
    holds the entry as it was and as it now is, are written in one transaction.

    Errors to branch on: `validation_error` (422) for a body the schema refuses, including a
    timestamp where a plain date belongs and a precision outside `day`, `month`, `quarter`
    and `year`; `not_found` (404) when no change has that id, or the entry belongs to
    another change — the two are answered alike so no id can be probed;
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
    permission `proposals.review`. `origin` records which of the two drew the link and never
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
