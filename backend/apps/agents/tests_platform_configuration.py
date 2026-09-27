"""Nobody but a platform administrator writes bleqq's agent configuration (D-102, ADR 0059,
AGT-03).

An agent definition, its versions and its platform settings are platform configuration,
written by three console routes alone. The library fence proves the routes' shape
(`apps/shared/tests_library_fence.py`, `PlatformConfigurationGuard`); this proves the
runtime half against real credentials: a platform agent's key and a bank's key holding
every scope, and a bank administrator's session holding every tenant permission with a
fresh passkey, are each refused on all three, and nothing changes and nothing is recorded.

Proven to fail 2026-09-25, then reverted: `@requires_permission` on publishAgentVersion
swapped for `perms.AGENTS_MANAGE`, a tenant permission: the bank's session passed the
gate and was stopped only by the folder check (422 where 403 was due).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.agents.models import Agent, AgentVersion
from apps.agents.tests_definitions import platform_agent
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, stub_session, user_principal

DEFINITIONS = "/api/v1/agent-definitions"
JSON = "application/json"


class NoAgentKeyOrBankWritesPlatformConfiguration(TestCase):
    def setUp(self) -> None:
        self.agent = platform_agent(f"nordic-watch-{uuid.uuid4().hex[:6]}", versions=2)
        self.bank = factories.tenant(slug=f"bank-{uuid.uuid4().hex[:6]}")
        tenancy.clear_tenant()  # a platform key is written with no bank activated
        self.writes: dict[str, tuple[str, str, dict[str, Any] | None]] = {
            "publishAgentVersion": (
                "post",
                f"{DEFINITIONS}/{self.agent.key}/versions",
                {"versionNo": 3, "changeNote": "Reads the new FFFS index page."},
            ),
            "retireAgentVersion": ("post", f"{DEFINITIONS}/{self.agent.key}/versions/1/retire", None),
            "updatePlatformAgentSettings": (
                "put",
                f"{DEFINITIONS}/{self.agent.key}/settings",
                {"cadence": "daily", "jurisdictions": ["se"], "monthlyBudget": "1.00"},
            ),
        }

    def snapshot(self) -> tuple[Any, ...]:
        agent = Agent.objects.get(pk=self.agent.pk)
        versions = list(AgentVersion.objects.filter(agent=agent).order_by("version_no").values_list("version_no", "retired_at"))
        audit = AuditEvent.objects.filter(subject_title__startswith=self.agent.key).count()
        return agent.current_version, agent.default_cadence, agent.platform_scope, agent.platform_monthly_budget, versions, audit

    def assert_refused_everywhere(self, send: Any, statuses: set[int]) -> None:
        before = self.snapshot()
        for operation_id, (method, url, body) in self.writes.items():
            with self.subTest(route=operation_id):
                response = send(method, url, body)
                self.assertIn(response.status_code, statuses, response.content)
        self.assertEqual(self.snapshot(), before, "a refused write changed platform configuration or recorded it")

    def test_a_platform_agents_key_holding_every_scope_is_refused(self) -> None:
        key = agent_build.agent_key(agent_row=self.agent, scopes=perms.ALL_SCOPES)

        def send(method: str, url: str, body: Any) -> Any:
            return getattr(self.client, method)(url, data=body, content_type=JSON, HTTP_X_API_KEY=key.plain_key)

        self.assert_refused_everywhere(send, {401})

    def test_a_banks_key_holding_every_scope_is_refused(self) -> None:
        key = factories.api_key(self.bank, scopes=perms.ALL_SCOPES - perms.PLATFORM_ONLY_SCOPES)

        def send(method: str, url: str, body: Any) -> Any:
            return getattr(self.client, method)(url, data=body, content_type=JSON, HTTP_X_API_KEY=key.plain_key)

        self.assert_refused_everywhere(send, {401})

    def test_a_bank_administrator_with_every_tenant_permission_and_a_fresh_passkey_is_refused(self) -> None:
        administrator = user_principal(
            permissions=perms.TENANT_PERMISSIONS,
            tenant_id=self.bank.id,
            subject_id=factories.member_user(self.bank, roles=("admin",)).id,
            step_up_at=timezone.now(),
        )
        self.assertNotIn(perms.AGENT_DEFINITIONS_MANAGE, perms.TENANT_PERMISSIONS)

        def send(method: str, url: str, body: Any) -> Any:
            with stub_session(administrator):
                return getattr(self.client, method)(
                    url, data=body, content_type=JSON, HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}"
                )

        self.assert_refused_everywhere(send, {403})
