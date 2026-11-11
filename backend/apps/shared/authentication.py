"""The three principals (playbook 4.2) as Django Ninja auth classes.

- `SessionAuth`: people, with our own short-lived access token as a bearer (INPUT_DELTAS §2).
- `ApiKeyAuth`: agents and integrations, `X-API-Key`, narrow scopes; none allows a library
  edit (AC-PRO1).
- `EnrolmentAuth`: the session a verified emailed code yields; it reaches passkey
  registration and `GET /me`, nothing else (ID-02, AC-ID2).

Each turns a credential into the `Principal` in `request.auth`, through the identity app's
hashed lookups; tests stub them through apps/shared/testing.py. Nothing here logs a token or
uses `random` (playbook 9).

An agent access credential (ACC-03, ADR 0056) reaches a route only through `ApiKeyAuth`;
`SessionAuth` still hands one to the agent access guard, so a session-only route answers it
the same 403.
"""

from __future__ import annotations

import enum
import logging
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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

    `permissions` are the flattened grants of the user's roles in `tenant_id`; `scopes` an API
    key's scopes; an enrolment principal has neither. `step_up_at` is the freshest passkey
    assertion, compared with `STEP_UP_FRESHNESS_MINUTES` (ID-06). `session_created_at` lets a
    young session add or remove a passkey (F9). `agent_id`/`agent_label` name a key's agent
    (ID-10, AGT-01), the actor `record()` writes. `agent_access_id`/`agent_access_label` (a
    service key's entry) or `acting_user_id`/`acting_user_label` (a personal token's person)
    make it an agent access credential, read-only and never stepped up (ACC-03).
    `support_access_id` names a support session's grant (TEN-06, ADR 0042). `user` and
    `tenant` are the rows the lookup already joined, None where a test stubs the principal;
    they never take part in comparing two principals.
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
    user: Any = field(default=None, compare=False, repr=False)
    tenant: Any = field(default=None, compare=False, repr=False)

    @property
    def is_agent_access(self) -> bool:
        return self.kind is PrincipalKind.AGENT and (self.agent_access_id is not None or self.acting_user_id is not None)

    def has_permission(self, permission: str) -> bool:
        return self.kind is PrincipalKind.USER and permission in self.permissions

    def has_scope(self, scope: str) -> bool:
        return self.kind is PrincipalKind.AGENT and scope in self.scopes


Resolver = Callable[[str], Principal | None]


def _resolve_session_token(token: str) -> Principal | None:
    """The HMAC-signed access token names a session row (apps/identity/session_logic.py)."""
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
    the key prefix."""
    header_key = request.headers.get(API_KEY_HEADER, "").strip()
    if header_key:
        return header_key
    bearer = _bearer(request)
    return bearer if bearer and bearer.startswith(API_KEY_PREFIX) else None


# Where a request keeps the credential it resolved: an attribute, never a header, so no
# caller can set it. The MCP server copies it onto the route requests behind its tools, so one
# HTTP request resolves its key once.
RESOLVED_CREDENTIAL = "resolved_credential"


def credential_principal(request: HttpRequest, key: str) -> Principal | None:
    """Resolve the presented key, once per request, then let the agent access guard refuse a
    rate, a step-up or a write before any route sees it (ACC-03, ACC-09)."""
    from apps.shared import agent_access_guard

    resolved: tuple[str, Principal | None] | None = getattr(request, RESOLVED_CREDENTIAL, None)
    if resolved is not None and secrets.compare_digest(resolved[0].encode(), key.encode()):
        principal = resolved[1]
    else:
        principal = resolve_api_key(key)
        setattr(request, RESOLVED_CREDENTIAL, (key, principal))
    if principal is None or principal.kind is not PrincipalKind.AGENT:
        return None
    agent_access_guard.check(request, principal)
    return principal


class SessionAuth(HttpBearer):
    """People. Accepts only a user principal. It never accepts an API key or personal token
    (ACC-03): one presented without a session goes to the agent access guard and is answered
    as unauthenticated; on a route that also takes `ApiKeyAuth` that class resolves it, so a
    credential is resolved once per request."""

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
    """One `support_access.read` audit row in the bank per request of a support session
    (TEN-06, ADR 0042), once the grant is proven live, written again by
    `SupportReadOnlyMiddleware` if a refusal rolled it back: route template and path ids,
    never the query string or body."""
    from apps.shared.agent_access_guard import operation_of
    from apps.tenants import support_access

    operation = operation_of(request)
    match = getattr(request, "resolver_match", None)
    # Kept for the read-only guard, which writes it again if a refusal rolled it back (ADR
    # 0042; security-review-c8 M5).
    request.support_read = support_access.record_read(  # type: ignore[attr-defined]
        principal=principal,
        method=request.method or "",
        route=operation.path if operation is not None else "",
        path_ids={name: str(value) for name, value in (match.kwargs if match is not None else {}).items()},
    )


class ApiKeyAuth(APIKeyHeader):
    """Agents and integrations. `X-API-Key`, or `Authorization: Bearer cw_<prefix>_<secret>`;
    scopes checked by `@requires_scope`."""

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
