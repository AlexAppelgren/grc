"""The three principals (playbook 4.2) as Django Ninja auth classes.

- `SessionAuth`: people, tenant members and platform staff, with our own short-lived
  access token as a bearer (INPUT_DELTAS §2: `bearerAuth` means our session token).
- `ApiKeyAuth`: agents and integrations, `X-API-Key`, narrow scopes. No scope allows a
  library edit (AC-PRO1).
- `EnrolmentAuth`: the one session a verified emailed code yields. It reaches the passkey
  registration ceremony and `GET /me`, nothing else (ID-02, AC-ID2).

Each class turns a credential into a `Principal`, which is what `request.auth` holds
for the permission decorators. The lookup functions (`resolve_session_token`,
`resolve_api_key`, `resolve_enrolment_token`) are the seam chunk 1 fills with the
`user_session`, `api_key` and enrolment tables; in Phase 0 they find nothing, so every
credential is refused and the contract is pinned by tests that stub them.

Tokens are compared by hash lookup in chunk 1 (stored hashed, playbook 4.2); nothing here
logs a token, and nothing here uses `random` (playbook 9: security modules use `secrets`).
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
    """

    kind: PrincipalKind
    subject_id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    is_platform_staff: bool = False
    step_up_at: datetime | None = None
    session_id: uuid.UUID | None = None

    def has_permission(self, permission: str) -> bool:
        return self.kind is PrincipalKind.USER and permission in self.permissions

    def has_scope(self, scope: str) -> bool:
        return self.kind is PrincipalKind.AGENT and scope in self.scopes


Resolver = Callable[[str], Principal | None]


def _no_lookup_yet(token: str) -> Principal | None:
    """Phase 0: no session, key or enrolment table exists, so nothing authenticates.
    Chunk 1 replaces the three resolvers below with hashed lookups (ID-02, ID-03, ID-10)."""
    return None


# Module-level so chunk 1 replaces them and tests stub them (tests_authentication.py).
resolve_session_token: Resolver = _no_lookup_yet
resolve_api_key: Resolver = _no_lookup_yet
resolve_enrolment_token: Resolver = _no_lookup_yet


class SessionAuth(HttpBearer):
    """People. Accepts only a user principal, so a stubbed resolver that returns the wrong
    kind is refused rather than let through."""

    def authenticate(self, request: HttpRequest, token: str) -> Principal | None:
        principal = resolve_session_token(token)
        if principal is None or principal.kind is not PrincipalKind.USER:
            return None
        return principal


class ApiKeyAuth(APIKeyHeader):
    """Agents and integrations. `X-API-Key`, scopes checked by `@requires_scope`."""

    param_name = "X-API-Key"

    def authenticate(self, request: HttpRequest, key: str | None) -> Principal | None:
        if not key:
            return None
        principal = resolve_api_key(key)
        if principal is None or principal.kind is not PrincipalKind.AGENT:
            return None
        return principal


class EnrolmentAuth(HttpBearer):
    """The enrolment session (ID-02). Only routes that explicitly take this class accept it:
    passkey registration and `GET /me`. SessionAuth refuses an enrolment principal."""

    def authenticate(self, request: HttpRequest, token: str) -> Principal | None:
        principal = resolve_enrolment_token(token)
        if principal is None or principal.kind is not PrincipalKind.ENROLMENT:
            return None
        return principal
