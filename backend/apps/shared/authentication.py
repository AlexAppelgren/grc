"""The three principals (playbook 4.2) as Django Ninja auth classes.

- `SessionAuth`: people, tenant members and platform staff, with our own short-lived
  access token as a bearer (INPUT_DELTAS §2: `bearerAuth` means our session token).
- `ApiKeyAuth`: agents and integrations, `X-API-Key`, narrow scopes. No scope allows a
  library edit (AC-PRO1).
- `EnrolmentAuth`: the one session a verified emailed code yields. It reaches the passkey
  registration ceremony and `GET /me`, nothing else (ID-02, AC-ID2).

Each class turns a credential into a `Principal`, which is what `request.auth` holds
for the permission decorators. The lookup functions (`resolve_session_token`,
`resolve_api_key`, `resolve_enrolment_token`) delegate to the identity app's hashed
lookups (chunk 1: `user_session`, `api_key`); tests stub them through
apps/shared/testing.py when a scenario needs a principal without a ceremony.

Tokens are compared by hash lookup in chunk 1 (stored hashed, playbook 4.2); nothing here
logs a token, and nothing here uses `random` (playbook 9: security modules use `secrets`).

An agent access credential (ACC-03, ADR 0056) is an `api_key` row, so it reaches a route
only through `ApiKeyAuth`. `SessionAuth` never accepts one, but it still hands a live one
to the agent access guard, so a session-only step-up or write route answers the same 403
to a token as a route that takes keys does (apps/shared/agent_access_guard.py).
"""

from __future__ import annotations

import enum
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from django.http import HttpRequest
from ninja.security import APIKeyHeader, HttpBearer

logger = logging.getLogger(__name__)


class PrincipalKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): the auth classes and decorators branch on it."""

    USER = "user"
    AGENT = "agent"
    ENROLMENT = "enrolment"


@dataclass(frozen=True)
class Principal:
    """What `request.auth` holds after authentication.

    `permissions` are the flattened grants of the user's roles in `tenant_id` (people).
    `scopes` are an API key's scopes (agents). An enrolment principal has neither.
    `step_up_at` is the time of the freshest passkey assertion on this session, which
    `@requires_step_up` compares against `STEP_UP_FRESHNESS_MINUTES` (ID-06).
    `session_created_at` is when the session was opened (a refresh does not move it);
    adding or removing a passkey accepts a session younger than the window (F9).
    `agent_id` and `agent_label` name the agent the key is bound to (ID-10, AGT-01), so
    `record()` writes the agent as the actor rather than the key's id.
    `agent_access_id` and `agent_access_label` name the agent access entry a service key is
    bound to; `acting_user_id` and `acting_user_label` name the person a personal access
    token acts as (ACC-03). Either makes the principal an agent access credential, which
    reads and nothing else and can never step up (`is_agent_access`).
    `support_access_id` names the grant a support session stands on (TEN-06, ADR 0042):
    platform support reading one bank, with the seven reads and nothing else.
    """

    kind: PrincipalKind
    subject_id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    is_platform_staff: bool = False
    step_up_at: datetime | None = None
    step_up_assertion_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    session_created_at: datetime | None = None
    agent_id: uuid.UUID | None = None
    agent_label: str = ""
    agent_access_id: uuid.UUID | None = None
    agent_access_label: str = ""
    acting_user_id: uuid.UUID | None = None
    acting_user_label: str = ""
    support_access_id: uuid.UUID | None = None

    @property
    def is_agent_access(self) -> bool:
        return self.kind is PrincipalKind.AGENT and (self.agent_access_id is not None or self.acting_user_id is not None)

    def has_permission(self, permission: str) -> bool:
        return self.kind is PrincipalKind.USER and permission in self.permissions

    def has_scope(self, scope: str) -> bool:
        return self.kind is PrincipalKind.AGENT and scope in self.scopes


Resolver = Callable[[str], Principal | None]


def _resolve_session_token(token: str) -> Principal | None:
    """Chunk 1: the HMAC-signed access token names a session row (apps/identity/session_logic.py)."""
    from apps.identity import session_logic

    return session_logic.resolve_access_token(token, want=PrincipalKind.USER)


def _resolve_enrolment_token(token: str) -> Principal | None:
    from apps.identity import session_logic

    return session_logic.resolve_access_token(token, want=PrincipalKind.ENROLMENT)


def _resolve_api_key(key: str) -> Principal | None:
    from apps.identity import api_keys_logic

    return api_keys_logic.resolve_api_key(key)


# Module-level so tests stub them (apps/shared/testing.py) and the lookups stay lazy: the
# identity app imports this module, so the real resolvers are imported inside the call.
resolve_session_token: Resolver = _resolve_session_token
resolve_api_key: Resolver = _resolve_api_key
resolve_enrolment_token: Resolver = _resolve_enrolment_token

API_KEY_PREFIX = "cw_"
API_KEY_HEADER = "X-API-Key"


def _bearer(request: HttpRequest) -> str | None:
    scheme, _, credential = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return credential.strip() or None


def presented_api_key(request: HttpRequest) -> str | None:
    """The API key or token the request carries: `X-API-Key`, or a bearer that starts with
    the key prefix (chunk 1 brief)."""
    header_key = request.headers.get(API_KEY_HEADER, "").strip()
    if header_key:
        return header_key
    bearer = _bearer(request)
    return bearer if bearer and bearer.startswith(API_KEY_PREFIX) else None


def credential_principal(request: HttpRequest, key: str) -> Principal | None:
    """Resolve the presented key, then let the agent access guard refuse a rate, a step-up
    or a write before any route sees it (ACC-03, ACC-09)."""
    from apps.shared import agent_access_guard

    principal = resolve_api_key(key)
    if principal is None or principal.kind is not PrincipalKind.AGENT:
        return None
    agent_access_guard.check(request, principal)
    return principal


class SessionAuth(HttpBearer):
    """People. Accepts only a user principal, so a stubbed resolver that returns the wrong
    kind is refused rather than let through. It never accepts an API key or a personal
    access token (ACC-03): a request that presents one and no session is handed to the
    agent access guard and then answered as unauthenticated. On a route that also takes
    `ApiKeyAuth`, that class resolves it instead, so a credential is resolved and counted
    once per request."""

    def __call__(self, request: HttpRequest) -> Principal | None:
        from apps.shared import agent_access_guard

        bearer = _bearer(request)
        if bearer is None or bearer.startswith(API_KEY_PREFIX):
            key = presented_api_key(request)
            if key is not None:
                if not agent_access_guard.route_takes_keys(request):
                    credential_principal(request, key)
                return None
        return super().__call__(request)

    def authenticate(self, request: HttpRequest, token: str) -> Principal | None:
        principal = resolve_session_token(token)
        if principal is None or principal.kind is not PrincipalKind.USER:
            return None
        if principal.support_access_id is not None:
            _log_support_read(request, principal)
        return principal


def _log_support_read(request: HttpRequest, principal: Principal) -> None:
    """One `support_access.read` audit row in the bank for each request a support session
    makes (TEN-06, ADR 0042), written here, once the grant is proven live, in the request's
    transaction: the route template and its path ids, never the query string or the body.
    The read-only guard (apps/shared/middleware.py) has already refused a route off the
    allow-list, so every row names a route on it."""
    from apps.shared.agent_access_guard import operation_of
    from apps.tenants import support_access

    operation = operation_of(request)
    match = getattr(request, "resolver_match", None)
    support_access.record_read(
        principal=principal,
        method=request.method or "",
        route=operation.path if operation is not None else "",
        path_ids={name: str(value) for name, value in (match.kwargs if match is not None else {}).items()},
    )


class ApiKeyAuth(APIKeyHeader):
    """Agents and integrations. `X-API-Key`, or `Authorization: Bearer cw_<prefix>_<secret>`
    (chunk 1 brief); scopes checked by `@requires_scope`."""

    param_name = API_KEY_HEADER
    # The security scheme's description in openapi.json: the one place the fence around an
    # agent access credential is documented for every operation that takes a key.
    openapi_description = (
        "An API key or a personal access token, `cw_<prefix>_<secret>`, sent as `X-API-Key` or as a "
        "bearer token. A key of an agent access entry and every personal access token read and "
        "nothing else: any write other than `POST /search`, `POST /agent-access/what-applies` and "
        "`POST /mcp` answers 403 `read_only_credential`, a route that needs a passkey step-up "
        "answers 403 `step_up_required`, and more requests in a minute than "
        "`AGENT_ACCESS_RATE_PER_MINUTE` allows (60 unless the operator sets it) answer 429 "
        "`rate_limited`. A token stops working the moment its person, their membership or a "
        "permission behind one of its scopes is gone, and an entry's key the moment the entry is "
        "revoked; either then answers 401 `unauthenticated`. `tenant:read` counts only on a "
        "credential bound to an entry."
    )

    def _get_key(self, request: HttpRequest) -> str | None:
        return presented_api_key(request)

    def authenticate(self, request: HttpRequest, key: str | None) -> Principal | None:
        if not key:
            return None
        return credential_principal(request, key)


class EnrolmentAuth(HttpBearer):
    """The enrolment session (ID-02). Only routes that explicitly take this class accept it:
    passkey registration and `GET /me`. SessionAuth refuses an enrolment principal."""

    def authenticate(self, request: HttpRequest, token: str) -> Principal | None:
        principal = resolve_enrolment_token(token)
        if principal is None or principal.kind is not PrincipalKind.ENROLMENT:
            return None
        return principal
