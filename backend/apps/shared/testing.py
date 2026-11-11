"""Test support (playbook 8.1). `ScenarioTestCase` is the base class for every
`tests_scenarios.py`: its client fails a mutating request that wrote no audit row
(AC-AUD1), and its helpers stub a principal without touching a token.

Excluded from coverage (pyproject) because it is test scaffolding."""

from __future__ import annotations

import base64
import importlib
import json
import os
import uuid
from datetime import datetime
from time import monotonic, sleep
from collections.abc import Callable, Iterable
from typing import Any
from unittest import mock

from django.db import DEFAULT_DB_ALIAS, connection, connections, transaction
from django.utils import timezone
from django.db.models import Model
from django.test import Client, TestCase
from sentry_sdk.integrations import logging as sentry_logging

from apps.shared import authentication, outbox, permissions, tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import AuditEvent, OutboxEvent
from apps.taxonomy import matching

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
    return {"HTTP_AUTHORIZATION": f"Bearer {bundle.access_token}", "HTTP_COOKIE": f"{session_logic.refresh_cookie_name()}={bundle.refresh_value}"}


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


# ---- Readers only tests need: they look inside the mechanics they prove. ---------------
def b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def handlers_for(kind: str) -> tuple[outbox.Handler, ...]:
    """Who acts on this kind, in registration order: a consumer's own test proves it is the
    only handler for its kind."""
    return tuple(outbox._HANDLERS.get(kind, ()))


def gate_of(view: Callable[..., Any]) -> permissions.Gate | None:
    return getattr(view, "__cw_gate__", None)


def is_tenant_task(fn: Callable[..., Any]) -> bool:
    return bool(getattr(fn, "__cw_tenant_task__", False))


def library_write_reason() -> str | None:
    return tenancy._library_write_reason.get()


def identity_lookup_active(*, using: str = DEFAULT_DB_ALIAS) -> bool:
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [tenancy.IDENTITY_LOOKUP_SETTING])
        row = cursor.fetchone()
    return bool(row and row[0] == "on")


def in_footprint_sql(tenant_id: uuid.UUID, term_ids: Iterable[uuid.UUID]) -> bool:
    """The database's answer, from the SQL function the migration created, to pin the Python
    mirror against."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {matching.SQL_FUNCTION}(%s, %s::uuid[])", [str(tenant_id), [str(term_id) for term_id in term_ids]])
        row = cursor.fetchone()
    return bool(row and row[0])


def opt_in_dimensions() -> frozenset[str]:
    """The active opt-in dimensions alone: the standards a bank follows."""
    return matching.restricting_dimensions().opt_in


def admits_sql(tenant_id: uuid.UUID, entry_id: uuid.UUID, term_ids: Iterable[uuid.UUID]) -> bool:
    """The database's verdict on one record, from `taxonomy_entry_admits` (taxonomy 0011)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT taxonomy_entry_admits(%s, %s, %s::uuid[])",
            [str(tenant_id), str(entry_id), [str(term_id) for term_id in term_ids]],
        )
        row = cursor.fetchone()
    return bool(row and row[0])


# ---- Helpers many test modules repeated word for word. ---------------------------------
def drain() -> None:
    """Deliver the outbox until its backlog is empty, from the library's zone: the reference
    seed writes more rows than one `OUTBOX_BATCH_SIZE` pass delivers."""
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


def flush_outbox() -> None:
    """Mark what the fixtures recorded as delivered, so each test delivers its own rows."""
    with transaction.atomic():
        OutboxEvent.objects.filter(published_at__isnull=True).update(published_at=timezone.now())


def seed_reference() -> None:
    """Languages, jurisdictions, library vocabularies, taxonomy terms and authorities."""
    from apps.library.seeds import seed_jurisdictions, seed_languages
    from apps.library.seeds.library import seed_authorities
    from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()
    seed_authorities()


def call_route(client: Client, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    """`method` on `url` with `body` as JSON, or with no body when it is None."""
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


def events_of(response: Any) -> list[dict[str, Any]]:
    """The events a `text/event-stream` response carried, in order: one `data:` frame each."""
    body = b"".join(response.streaming_content).decode()
    return [json.loads(line.removeprefix("data: ")) for line in body.splitlines() if line.startswith("data: ")]


def assert_refused(
    case: Any, routes: Iterable[tuple[Any, ...]], headers: dict[str, Any], status: int, code: str | None = None, naming: bool = False
) -> None:
    """Each route of a gate table, `(name, method, url, body, ...)`, answers `status` (and
    `code`, when given) to `headers`; with `naming`, the problem names the route's fifth
    field as its `requiredPermission`. One subtest per route."""
    for route in routes:
        name, method, url, body = route[:4]
        with case.subTest(operation=name):
            response = call_route(case.client, method, url, body, headers)
            case.assertEqual(response.status_code, status, response.content)
            if code is not None:
                case.assertEqual(response.json()["code"], code)
            if naming:
                case.assertEqual(response.json()["requiredPermission"], route[4])
