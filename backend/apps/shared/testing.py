"""Test support (playbook 8.1). `ScenarioTestCase` is the base class for every
`tests_scenarios.py`: its client fails a mutating request that wrote no audit row
(AC-AUD1), and its helpers stub a principal without touching a token.

Excluded from coverage (pyproject) because it is test scaffolding."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from unittest import mock

from django.db.models import Model
from django.test import Client, TestCase

from apps.shared import authentication
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
SESSION_TOKEN_FOR_TESTS = "test-session-token"  # noqa: S105 a stub, never a real credential
API_KEY_FOR_TESTS = "test-api-key"  # noqa: S105 a stub, never a real credential


def user_principal(
    *,
    permissions: set[str] | frozenset[str] = frozenset(),
    tenant_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    step_up_at: datetime | None = None,
) -> Principal:
    return Principal(
        kind=PrincipalKind.USER,
        subject_id=subject_id or uuid.uuid4(),
        tenant_id=tenant_id,
        permissions=frozenset(permissions),
        step_up_at=step_up_at,
    )


def agent_principal(*, scopes: set[str] | frozenset[str] = frozenset(), tenant_id: uuid.UUID | None = None) -> Principal:
    return Principal(kind=PrincipalKind.AGENT, subject_id=uuid.uuid4(), tenant_id=tenant_id, scopes=frozenset(scopes))


def enrolment_principal(*, subject_id: uuid.UUID | None = None) -> Principal:
    return Principal(kind=PrincipalKind.ENROLMENT, subject_id=subject_id or uuid.uuid4())


def stub_session(principal: Principal) -> Any:
    """Patch the session resolver so SESSION_TOKEN_FOR_TESTS resolves to `principal`."""
    return mock.patch.object(
        authentication,
        "resolve_session_token",
        lambda token: principal if token == SESSION_TOKEN_FOR_TESTS else None,
    )


def stub_api_key(principal: Principal) -> Any:
    return mock.patch.object(
        authentication,
        "resolve_api_key",
        lambda key: principal if key == API_KEY_FOR_TESTS else None,
    )


def stub_enrolment(principal: Principal) -> Any:
    return mock.patch.object(
        authentication,
        "resolve_enrolment_token",
        lambda token: principal if token == SESSION_TOKEN_FOR_TESTS else None,
    )


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

    def as_user(self, principal: Principal) -> dict[str, str]:
        """Headers for a stubbed person. Use with `with stub_session(principal):`."""
        return {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

    def as_agent(self, principal: Principal) -> dict[str, str]:
        return {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
