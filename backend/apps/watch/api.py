"""Routes of the watch app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Two gates here serve more than one principal, so they are logic gates listed in
`UNGATED_BY_DESIGN` and still answer the structured 403 with `requiredPermission`
(apps/shared/permissions.py, apps/taxonomy/http.py):

- **The registry reads** serve a person with `watch.read` and an agent's key with
  `library:read`: an agent must know which sources to check before it checks them
  (AGT-02). `c5-contract-api-screens` widens them to a console session with
  `sources.manage`, for the read-only Sources page.
- **The change facts** are written by an agent's key with `changes:write` and corrected by
  a library editor's session with `proposals.review` (PRO-01: a change's type, flags and
  scope are library facts, and no tenant role holds that permission).

Registering a source is a library editor's alone, and attaching a fetched page is a key's
alone: a page arrives from the agent that screened it (AGT-07), never from a screen.

No route here writes an inventory row. Everything the agent may change about the library
itself goes through a proposal (AC-PRO1).
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Body, Header, Router

from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, PrincipalKind, SessionAuth
from apps.shared.permissions import requires_permission, requires_scope
from apps.taxonomy.http import answers_problems, deny, principal, require_any
from apps.watch import curation, registration, sources
from apps.watch.schemas import (
    LINKS_MAX,
    WatchChange,
    WatchChangeDocument,
    WatchChangeDocumentInput,
    WatchChangeEvent,
    WatchChangeEventInput,
    WatchChangeInput,
    WatchChangePatch,
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


def require_watch_reader(request: HttpRequest) -> None:
    """The registry and its coverage log: a person with `watch.read`, or an agent's key
    with `library:read` so a run knows what to check (WAT-01, AGT-02)."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if not who.has_scope(perms.SCOPE_LIBRARY_READ):
            raise deny(perms.SCOPE_LIBRARY_READ)
        return
    require_any(request, perms.WATCH_READ)


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
