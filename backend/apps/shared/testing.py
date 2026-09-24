"""Test support (playbook 8.1). `ScenarioTestCase` is the base class for every
`tests_scenarios.py`: its client fails a mutating request that wrote no audit row
(AC-AUD1), and its helpers stub a principal without touching a token.

Excluded from coverage (pyproject) because it is test scaffolding."""

from __future__ import annotations

import importlib
import os
import uuid
from datetime import datetime
from time import monotonic, sleep
from typing import Any
from unittest import mock

from django.db import connection
from django.db.models import Model
from django.test import Client, TestCase
from sentry_sdk.integrations import logging as sentry_logging

from apps.shared import authentication, tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import AuditEvent

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def production_models() -> list[type[Model]]:
    """Every registered model that is not a throwaway defined inside a tests_ module. The
    structural guards enumerate these; probe models a test creates for its own proof are
    scaffolding, not product."""
    from django.apps import apps

    return [
        model
        for model in apps.get_models()
        if model.__module__.startswith("apps.") and ".tests_" not in model.__module__
    ]


def sentry_init_kwargs() -> dict[str, Any]:
    """Boots the settings with a DSN and returns what they pass to `sentry_sdk.init`, so a
    test that starts the SDK starts it as a deployed process does, never from a copy of
    settings.py that could drift from it."""
    # The ignored set is process-global; start without the entry so the reload has to add it.
    sentry_logging.unignore_logger("gunicorn.access")
    env = {"SENTRY_DSN": "https://public@sentry.example.invalid/1", "ENVIRONMENT": "test", "DEBUG": "true"}
    import config.settings as base

    try:
        with mock.patch.dict(os.environ, env), mock.patch("sentry_sdk.init") as init:
            importlib.reload(base)
    finally:
        # Reload once more without the DSN so later tests see the runner's settings module.
        with mock.patch.dict(os.environ, {"SENTRY_DSN": "", "ENVIRONMENT": "test", "DEBUG": "false"}):
            importlib.reload(base)
    return dict(init.call_args.kwargs)


SESSION_TOKEN_FOR_TESTS = "test-session-token"  # noqa: S105 a stub, never a real credential
API_KEY_FOR_TESTS = "test-api-key"  # noqa: S105 a stub, never a real credential


def user_principal(
    *,
    permissions: set[str] | frozenset[str] = frozenset(),
    tenant_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    step_up_at: datetime | None = None,
    step_up_assertion_id: uuid.UUID | None = None,
) -> Principal:
    """A stubbed person. A step-up time implies an assertion id (the real resolver always
    sets both, and `enforce_step_up` demands both)."""
    return Principal(
        kind=PrincipalKind.USER,
        subject_id=subject_id or uuid.uuid4(),
        tenant_id=tenant_id,
        permissions=frozenset(permissions),
        step_up_at=step_up_at,
        step_up_assertion_id=step_up_assertion_id or (uuid.uuid4() if step_up_at is not None else None),
    )


def agent_principal(*, scopes: set[str] | frozenset[str] = frozenset(), tenant_id: uuid.UUID | None = None) -> Principal:
    return Principal(kind=PrincipalKind.AGENT, subject_id=uuid.uuid4(), tenant_id=tenant_id, scopes=frozenset(scopes))


def enrolment_principal(*, subject_id: uuid.UUID | None = None) -> Principal:
    return Principal(kind=PrincipalKind.ENROLMENT, subject_id=subject_id or uuid.uuid4())


def _resolving(principal: Principal, expected: str) -> Any:
    """What a stubbed resolver does: hand back the principal and, like the real one, put the
    connection in the principal's zone so row-level security scopes the request (playbook
    14). A platform principal has no tenant, and clearing one a factory activated earlier in
    the test is what makes the request look like the production one, which never had it."""

    def resolve(token: str) -> Principal | None:
        if token != expected:
            return None
        if principal.tenant_id is not None:
            tenancy.activate(principal.tenant_id)
        else:
            tenancy.clear_tenant()
        return principal

    return resolve


def stub_session(principal: Principal) -> Any:
    """Patch the session resolver so SESSION_TOKEN_FOR_TESTS resolves to `principal`."""
    return mock.patch.object(authentication, "resolve_session_token", _resolving(principal, SESSION_TOKEN_FOR_TESTS))


def stub_api_key(principal: Principal) -> Any:
    return mock.patch.object(authentication, "resolve_api_key", _resolving(principal, API_KEY_FOR_TESTS))


def stub_enrolment(principal: Principal) -> Any:
    return mock.patch.object(authentication, "resolve_enrolment_token", _resolving(principal, SESSION_TOKEN_FOR_TESTS))


# ---------------------------------------------------------------------------------------
# Real sessions for scenario tests: the ceremonies are proven in their own scenarios;
# every other scenario signs in through the session logic and carries a real access token.
# ---------------------------------------------------------------------------------------
def sign_in(user: Any, *, tenant: Any = None, step_up: bool = False, kind: str = "full") -> dict[str, Any]:
    """Headers for a real session of `user` in `tenant` (activated). `step_up=True` adds a
    fresh assertion on the session, backed by the user's first live passkey (created if
    none exists)."""
    from apps.identity import session_logic
    from apps.identity.models import AuthChallenge, ChallengeKind, SessionKind, StepUpAssertion, WebAuthnCredential
    from apps.shared import factories
    from django.utils import timezone

    tenant_id = tenant.id if tenant is not None else None
    if tenant_id is not None:
        tenancy.activate(tenant_id)
    else:
        tenancy.clear_tenant()  # a platform session, as production has it: no tenant activated
    bundle = session_logic.create_session(
        user=user, kind=SessionKind(kind), tenant_id=tenant_id, request=None
    )
    if step_up:
        credential = WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).order_by("created_at").first()
        if credential is None:
            credential = factories.passkey(user)
        challenge = AuthChallenge.objects.create(
            kind=ChallengeKind.STEP_UP.value,
            challenge=f"stub-{bundle.session.id.hex}",
            user=user,
            session=bundle.session,
            expires_at=timezone.now(),
            consumed_at=timezone.now(),
        )
        StepUpAssertion.objects.create(session=bundle.session, credential=credential, challenge=challenge)
    return {"HTTP_AUTHORIZATION": f"Bearer {bundle.access_token}", "HTTP_COOKIE": f"cw_refresh={bundle.refresh_value}"}


class AuditAssertingClient(Client):
    """A test client whose mutating requests must leave an audit row (playbook 5, 8.1).
    A 4xx response is exempt: a refused request writes nothing by design."""

    def generic(  # compliance: allow-kwargs Django Client signature
        self, method: str, path: Any, *args: Any, **extra: Any
    ) -> Any:
        before = AuditEvent.objects.count()
        response = super().generic(method, path, *args, **extra)
        if method.upper() in MUTATING_METHODS and 200 <= response.status_code < 300:
            after = AuditEvent.objects.count()
            if after <= before:
                raise AssertionError(
                    f"{method.upper()} {path} answered {response.status_code} but wrote no "
                    "audit_event row. Every write goes through record() (AC-AUD1)."
                )
        return response


class ScenarioTestCase(TestCase):
    client_class = AuditAssertingClient

    def activate(self, tenant: Any) -> None:
        """Scope the test's own queries to `tenant` (a request may have activated another)."""
        tenancy.activate(tenant.id)

    def as_user(self, principal: Principal) -> dict[str, Any]:
        """Headers for a stubbed person. Use with `with stub_session(principal):`."""
        return {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

    def as_agent(self, principal: Principal) -> dict[str, Any]:
        return {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}


# --- Races between two real sessions ----------------------------------------------------
# Each racing session runs on its own cw_app connection in its own thread and transaction,
# the way two requests reach production. The first acts and holds its transaction open
# until PostgreSQL reports the second one waiting on it, then commits: the interleaving in
# which a check on an unlocked row lets both through (apps/taxonomy/tests_footprint.py,
# apps/proposals/tests_decide.py).
RACE_WAIT_SECONDS = 10
LANDED = "landed"


def backend_pid() -> int:
    """The PostgreSQL backend of this thread's connection, which the first session watches."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return int(cursor.fetchone()[0])


def hold_until_waiting_on_me(other_pid: list[int]) -> None:
    """Return once the session `other_pid[0]` waits on a lock this one holds, or fail after
    RACE_WAIT_SECONDS: a second session that never waited was never serialized."""
    deadline = monotonic() + RACE_WAIT_SECONDS
    while monotonic() < deadline:
        if other_pid:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))", [other_pid[0]])
                if cursor.fetchone()[0]:
                    return
        sleep(0.01)
    raise AssertionError("the second session never waited on the first")
