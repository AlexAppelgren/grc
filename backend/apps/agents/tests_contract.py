"""Contract guard for the agent-facing run routes, the platform agent-key routes and the
agent-definitions read (AGT-01, AGT-02, ID-10, NFR-01, chunk 5 `c5-contract-api-agent`).

The routes were declared before the logic that served them, each answering 501
`not_built` behind its real gate, and every refusal in front of that stub was proved here,
per route. Written before the routes existed (2026-09-20): every case below failed with
404 until `agents/api.py` and the three `identity/api.py` routes landed.

No route is a stub any more. The three run routes left the stub list on 2026-09-21
(`c5-agent-runs`, proved in `tests_runs.py`), `recordSourceCheck` the same day
(`c5-watch-sources-coverage`, `apps/watch/tests_sources.py`), and the three agent-key
routes on 2026-09-23 with the definitions read beside them (`identity-agent-keys-backend`,
`apps/identity/tests_api_keys.py`). Every gate assertion each of them had is kept, and
`AgentRoutesAnswerFromTheirLogic` pins that each answers from its logic behind the gate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.shared import factories, permissions as perms, tenancy
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)

RUN = "11111111-1111-4111-8111-111111111111"
KEY = "22222222-2222-4222-8222-222222222222"
RUNS = "/api/v1/agent-runs"
KEYS = "/api/v1/agent-keys"
DEFINITIONS = "/api/v1/agent-definitions"

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

RUN_BODY = {"agent": "watch-sweeper", "model": "mock-llm", "pipelineVersion": "1"}
FINISH_BODY = {"status": "succeeded"}
CHECK_BODY = {"sourceName": "Finansinspektionen news", "status": "ok", "itemsFound": 3}
KEY_BODY = {"name": "watch sweeper", "agentId": str(uuid.uuid4()), "scopes": ["changes:write"]}

# (name, method, url, body, the scope the key must hold)
KEY_ROUTES = [
    ("startAgentRun", "post", RUNS, RUN_BODY, perms.SCOPE_AGENT_RUNS_WRITE),
    ("finishAgentRun", "patch", f"{RUNS}/{RUN}", FINISH_BODY, perms.SCOPE_AGENT_RUNS_WRITE),
    ("recordSourceCheck", "post", f"{RUNS}/{RUN}/source-checks", CHECK_BODY, perms.SCOPE_SOURCES_WRITE),
]
# (name, method, url, body, the permission the session must hold)
SESSION_ROUTES = [
    ("listAgentRuns", "get", RUNS, None, perms.AGENTS_MANAGE),
    ("listAgentDefinitions", "get", DEFINITIONS, None, perms.AGENT_DEFINITIONS_MANAGE),
    ("listAgentKeys", "get", KEYS, None, perms.AGENT_DEFINITIONS_MANAGE),
    ("createAgentKey", "post", KEYS, KEY_BODY, perms.AGENT_DEFINITIONS_MANAGE),
    ("revokeAgentKey", "post", f"{KEYS}/{KEY}/revoke", {}, perms.AGENT_DEFINITIONS_MANAGE),
]


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class AgentRouteGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        for name, method, url, body, _ in KEY_ROUTES + SESSION_ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_key_without_the_scope_is_403_naming_it(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_LIBRARY_READ})):
            for name, method, url, body, scope in KEY_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], scope)

    def test_a_session_without_the_permission_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.LIBRARY_READ}, tenant_id=uuid.uuid4())):
            for name, method, url, body, permission in SESSION_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], permission)

    def test_a_person_never_opens_or_closes_a_run(self) -> None:
        """Item 14: bleqq's agents are platform-owned and platform-run. Only a key reaches
        the two run writes, so no session — tenant or platform — opens or closes a run."""
        with stub_session(user_principal(permissions=perms.ALL_PERMISSIONS, tenant_id=uuid.uuid4())):
            for name, method, url, body, _ in KEY_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 401)

    def test_a_key_never_reads_the_run_list_or_touches_a_key(self) -> None:
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body, _ in SESSION_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 401)

    def test_creating_a_key_needs_a_fresh_assertion_before_the_logic(self) -> None:
        with stub_session(user_principal(permissions={perms.AGENT_DEFINITIONS_MANAGE})):
            response = _call(self.client, "post", KEYS, KEY_BODY, AS_SESSION)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")

    def test_bad_input_is_422_before_the_logic(self) -> None:
        cases = [
            ("startAgentRun", "post", RUNS, {"agent": "watch-sweeper"}),  # model and pipelineVersion missing
            ("finishAgentRun", "patch", f"{RUNS}/{RUN}", {"status": "running"}),  # not a closing status
            ("recordSourceCheck", "post", f"{RUNS}/{RUN}/source-checks", {"sourceName": "x", "status": "maybe"}),
            ("recordSourceCheck", "post", f"{RUNS}/{RUN}/source-checks", {"sourceName": "x", "status": "ok", "tone": "negative"}),
        ]
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body in cases:
                with self.subTest(operation=name, body=sorted(body)):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_a_run_id_that_is_not_a_uuid_is_404(self) -> None:
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            response = _call(self.client, "patch", f"{RUNS}/not-a-uuid", FINISH_BODY, AS_KEY)
        self.assertIn(response.status_code, (404, 422))


class AgentRoutesAnswerFromTheirLogic(TestCase):
    """Behind the gate, every route of this contract answers from its logic: none is a stub."""

    def test_the_built_source_check_route_answers_from_its_logic(self) -> None:
        """`recordSourceCheck` no longer answers `not_built`. The run these constants name
        does not exist, so the honest answer is 404 — which is also the proof that the gate
        ran first and the lookup second."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            response = _call(self.client, "post", f"{RUNS}/{RUN}/source-checks", CHECK_BODY, AS_KEY)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["code"], "not_found")

    def test_a_platform_admin_reaches_each_key_route_and_its_logic_answers(self) -> None:
        """The key routes reached with the permission and a fresh assertion: the list reads,
        a key bound to no definition is refused by the logic, and a key that does not exist
        is not found. What each does beyond that is `apps/identity/tests_api_keys.py`."""
        admin = factories.platform_user(roles=("platform_admin",))
        tenancy.clear_tenant()
        principal = user_principal(
            permissions={perms.AGENT_DEFINITIONS_MANAGE}, subject_id=admin.id, step_up_at=timezone.now()
        )
        expected = {
            "listAgentDefinitions": (200, None),
            "listAgentKeys": (200, None),
            "createAgentKey": (422, "unknown_key"),
            "revokeAgentKey": (404, "not_found"),
        }
        with stub_session(principal):
            for name, method, url, body, _ in SESSION_ROUTES:
                if name not in expected:
                    continue
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    status, code = expected[name]
                    self.assertEqual(response.status_code, status, response.content)
                    if code is not None:
                        self.assertEqual(response.json()["code"], code)

    def test_system_health_also_reads_the_run_list(self) -> None:
        """The run log is served now, so the proof is that `system.health` passes its gate;
        what it returns is `tests_runs.py`'s."""
        with stub_session(user_principal(permissions={perms.SYSTEM_HEALTH})):
            response = _call(self.client, "get", RUNS, None, AS_SESSION)
        self.assertEqual(response.status_code, 200, response.content)


# ---------------------------------------------------------------------------------------
# Chunk 11 (`c11-agents-contract`, AGT-03, AGT-04, AGT-05, ADM-02): every console and
# tenant agent operation declared behind the gate it keeps, answering 501 `not_built`
# until the package that builds it lands. Written before the routes: every case below
# failed with 404 or 405 until `agents/api.py` declared them.
# ---------------------------------------------------------------------------------------
AGENT_KEY = "watch-sweeper"
TENANT_AGENTS = "/api/v1/agents"
CONSOLE_RUNS = "/api/v1/console/agent-runs"
BUDGET = "/api/v1/tenant/agent-budget"
REQUESTS = "/api/v1/research-requests"
SETTINGS_BODY = {"cadence": "daily", "jurisdictions": ["se", "eu"], "monthlyBudget": "250.00"}
PUBLISH_BODY = {"versionNo": 2, "changeNote": "Reads the new FFFS index page."}
TENANT_AGENT_BODY = {"agent": "bank-watch", "cadence": "weekly", "scope": {"jurisdictions": ["se"], "terms": []}}
REQUEST_BODY = {"kind": "research_topic", "tenantAgentId": KEY, "topic": "DORA subcontracting"}

# (name, method, url, body, the permission the session must hold, step-up)
CONSOLE_ROUTES: list[tuple[str, str, str, Any, str, bool]] = [
    ("getAgentDefinition", "get", f"{DEFINITIONS}/{AGENT_KEY}", None, perms.AGENT_DEFINITIONS_MANAGE, False),
    ("publishAgentVersion", "post", f"{DEFINITIONS}/{AGENT_KEY}/versions", PUBLISH_BODY, perms.AGENT_DEFINITIONS_MANAGE, True),
    ("retireAgentVersion", "post", f"{DEFINITIONS}/{AGENT_KEY}/versions/1/retire", {}, perms.AGENT_DEFINITIONS_MANAGE, True),
    ("getPlatformAgentSettings", "get", f"{DEFINITIONS}/{AGENT_KEY}/settings", None, perms.AGENT_DEFINITIONS_MANAGE, False),
    ("updatePlatformAgentSettings", "put", f"{DEFINITIONS}/{AGENT_KEY}/settings", SETTINGS_BODY, perms.AGENT_DEFINITIONS_MANAGE, True),
    ("listPlatformRuns", "get", CONSOLE_RUNS, None, perms.AGENT_DEFINITIONS_MANAGE, False),
    ("createRetagRequest", "post", "/api/v1/console/research-requests", {"topic": "Re-tag custody records with Client money."}, perms.PROPOSALS_REVIEW, False),
]
# (name, method, url, body, permission). `{id}` is filled with a record of the caller's own
# bank, of another bank, or with nothing, by the test that needs one.
TENANT_ROUTES: list[tuple[str, str, str, Any, str]] = [
    ("listTenantAgents", "get", TENANT_AGENTS, None, perms.AGENTS_MANAGE),
    ("createTenantAgent", "post", TENANT_AGENTS, TENANT_AGENT_BODY, perms.AGENTS_MANAGE),
    ("updateTenantAgent", "patch", f"{TENANT_AGENTS}/{{id}}", {"enabled": True}, perms.AGENTS_MANAGE),
    ("runTenantAgentNow", "post", f"{TENANT_AGENTS}/{{id}}/runs", {}, perms.AGENTS_MANAGE),
    ("pauseTenantAgent", "post", f"{TENANT_AGENTS}/{{id}}/pause", {}, perms.AGENTS_MANAGE),
    ("resumeTenantAgent", "delete", f"{TENANT_AGENTS}/{{id}}/pause", None, perms.AGENTS_MANAGE),
    ("interruptAgentRun", "post", f"{RUNS}/{{id}}/interrupt", {}, perms.AGENTS_MANAGE),
    ("getAgentBudget", "get", BUDGET, None, perms.AGENTS_MANAGE),
    ("putAgentBudget", "put", BUDGET, {"monthlyCap": "500.00"}, perms.AGENTS_MANAGE),
    ("listResearchRequests", "get", REQUESTS, None, perms.AGENTS_MANAGE),
    ("createResearchRequest", "post", REQUESTS, REQUEST_BODY, perms.AGENTS_MANAGE),
    ("getResearchRequest", "get", f"{REQUESTS}/{{id}}", None, perms.AGENTS_MANAGE),
    ("listPlatformWatch", "get", f"{TENANT_AGENTS}/platform", None, perms.WATCH_READ),
]
# Which record each id route addresses: a bank's own agent, its run, or its request.
ID_KIND = {
    "updateTenantAgent": "agent",
    "runTenantAgentNow": "agent",
    "pauseTenantAgent": "agent",
    "resumeTenantAgent": "agent",
    "interruptAgentRun": "run",
    "getResearchRequest": "request",
}


def _filled(url: str, record_id: Any = KEY) -> str:
    return url.replace("{id}", str(record_id))


class _Bank:
    """One bank's own agent, a run of it and a research request to it (AGT-04, AGT-05)."""

    def __init__(self, slug: str, definition: Any) -> None:
        from apps.agents.models import AgentRun, ResearchRequest, RunTrigger, TenantAgent

        self.tenant = factories.tenant(slug=slug)
        self.admin = factories.member_user(self.tenant, roles=("admin",))
        tenancy.activate(self.tenant.id)
        self.agent = TenantAgent.objects.create(tenant=self.tenant, agent=definition)
        self.run = AgentRun.objects.create(
            agent=definition,
            tenant_agent=self.agent,
            trigger=RunTrigger.MANUAL.value,
            requested_by=self.admin,
            model="mock-llm",
            pipeline_version="1",
        )
        self.request = ResearchRequest.objects.create(
            tenant=self.tenant, tenant_agent=self.agent, requested_by=self.admin, kind="run_now"
        )
        tenancy.clear_tenant()

    def record(self, kind: str) -> Any:
        return {"agent": self.agent.id, "run": self.run.id, "request": self.request.id}[kind]

    def principal(self, permissions: frozenset[str] = perms.TENANT_PERMISSIONS) -> Any:
        return user_principal(
            permissions=permissions, tenant_id=self.tenant.id, subject_id=self.admin.id, step_up_at=timezone.now()
        )


def _tenant_definition(key: str = "bank-watch") -> Any:
    from apps.agents.models import Agent, AgentKind, AgentScopeKind, AgentWritesTo
    from apps.shared.tenancy import library_write

    with library_write("test"):
        return Agent.objects.create(
            key=key,
            kind=AgentKind.RESEARCH.value,
            current_version=1,
            scope=AgentScopeKind.TENANT.value,
            tenant_configurable=True,
            writes_to=AgentWritesTo.TENANT.value,
        )


class ConsoleAgentRouteGates(TestCase):
    """AGT-03, ADM-02: bleqq's agents are the platform's. No tenant principal and no key
    reaches a definition, a version, a platform setting or a platform run, in any release."""

    def test_no_credential_is_401(self) -> None:
        for name, method, url, body, _, _ in CONSOLE_ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_key_of_any_scope_never_authenticates(self) -> None:
        """A key is not a session: these routes take `SessionAuth` alone, so a key holding
        every scope is refused before any gate reads it."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body, _, _ in CONSOLE_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_platform_session_without_the_permission_is_403_naming_it(self) -> None:
        for name, method, url, body, permission, _ in CONSOLE_ROUTES:
            others = perms.PLATFORM_PERMISSIONS - {permission}
            with self.subTest(operation=name), stub_session(user_principal(permissions=others, step_up_at=timezone.now())):
                response = _call(self.client, method, url, body, AS_SESSION)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "permission_denied")
                self.assertEqual(response.json()["requiredPermission"], permission)

    def test_every_tenant_session_is_403(self) -> None:
        """A bank's session holding every tenant permission there is, with a fresh
        passkey, still reaches no console agent route (AGT-03)."""
        bank = factories.tenant(slug="console-refused")
        principal = user_principal(permissions=perms.TENANT_PERMISSIONS, tenant_id=bank.id, step_up_at=timezone.now())
        with stub_session(principal):
            for name, method, url, body, permission, _ in CONSOLE_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["requiredPermission"], permission)

    def test_the_writes_that_change_every_bank_need_a_fresh_assertion_first(self) -> None:
        stepped = [route for route in CONSOLE_ROUTES if route[5]]
        self.assertEqual(
            {route[0] for route in stepped},
            {"publishAgentVersion", "retireAgentVersion", "updatePlatformAgentSettings"},
        )
        for name, method, url, body, permission, _ in stepped:
            with self.subTest(operation=name), stub_session(user_principal(permissions={permission})):
                response = _call(self.client, method, url, body, AS_SESSION)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "step_up_required")

    def test_behind_the_gate_each_answers_not_built(self) -> None:
        for name, method, url, body, permission, _ in CONSOLE_ROUTES:
            with self.subTest(operation=name), stub_session(user_principal(permissions={permission}, step_up_at=timezone.now())):
                response = _call(self.client, method, url, body, AS_SESSION)
                self.assertEqual(response.status_code, 501, response.content)
                self.assertEqual(response.json()["code"], "not_built")

    def test_the_definitions_list_carries_scope_and_version(self) -> None:
        """`GET /agent-definitions` is served: it gains the definition's scope and when its
        current version was published, and stays the one list (no second one)."""
        from apps.agents.models import AgentVersion
        from apps.shared.tenancy import library_write

        definition = _tenant_definition()
        with library_write("test"):
            version = AgentVersion.objects.create(agent=definition, version_no=1, model="m", prompt_path="prompt.md")
        with stub_session(user_principal(permissions={perms.AGENT_DEFINITIONS_MANAGE})):
            response = _call(self.client, "get", f"{DEFINITIONS}?limit=100", None, AS_SESSION)
        self.assertEqual(response.status_code, 200, response.content)
        row = next(item for item in response.json()["items"] if item["id"] == str(definition.id))
        self.assertEqual(row["scope"], "tenant")
        self.assertTrue(row["tenantConfigurable"])
        self.assertEqual(row["currentVersion"], 1)
        # The JSON encoder writes milliseconds, so the stored microseconds are cut.
        self.assertAlmostEqual(datetime.fromisoformat(row["publishedAt"]), version.published_at, delta=timedelta(milliseconds=1))


class TenantAgentRouteGates(TestCase):
    """AGT-04, AGT-05: a bank steers only its own agents, from a person's session holding
    `agents.manage` (what bleqq watches: `watch.read`), and only inside its own zone."""

    bank_a: _Bank
    bank_b: _Bank

    @classmethod
    def setUpTestData(cls) -> None:
        definition = _tenant_definition()
        cls.bank_a = _Bank("agents-a", definition)
        cls.bank_b = _Bank("agents-b", definition)

    def _url(self, name: str, url: str, bank: _Bank | None = None) -> str:
        kind = ID_KIND.get(name)
        return _filled(url, (bank or self.bank_a).record(kind)) if kind else url

    def test_no_credential_is_401(self) -> None:
        for name, method, url, body, _ in TENANT_ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, self._url(name, url), body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_key_of_any_scope_never_authenticates(self) -> None:
        """No agent key opens, steers or reads a bank's agents here, a bank's own key
        included: the routes take `SessionAuth` alone."""
        for tenant_id in (None, self.bank_a.tenant.id):
            with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES, tenant_id=tenant_id)):
                for name, method, url, body, _ in TENANT_ROUTES:
                    with self.subTest(operation=name, tenant=tenant_id):
                        response = _call(self.client, method, self._url(name, url), body, AS_KEY)
                        self.assertEqual(response.status_code, 401)

    def test_a_session_without_the_permission_is_403_naming_it(self) -> None:
        for name, method, url, body, permission in TENANT_ROUTES:
            principal = self.bank_a.principal(perms.TENANT_PERMISSIONS - {permission})
            with self.subTest(operation=name), stub_session(principal):
                response = _call(self.client, method, self._url(name, url), body, AS_SESSION)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "permission_denied")
                self.assertEqual(response.json()["requiredPermission"], permission)

    def test_inside_its_own_bank_each_answers_not_built(self) -> None:
        with stub_session(self.bank_a.principal(frozenset({perms.AGENTS_MANAGE, perms.WATCH_READ}))):
            for name, method, url, body, _ in TENANT_ROUTES:
                if name == "createResearchRequest":
                    body = {**body, "tenantAgentId": str(self.bank_a.agent.id)}
                with self.subTest(operation=name):
                    response = _call(self.client, method, self._url(name, url), body, AS_SESSION)
                    self.assertEqual(response.status_code, 501, response.content)
                    self.assertEqual(response.json()["code"], "not_built")

    def test_a_plain_reader_reaches_what_bleqq_watches(self) -> None:
        """Ruling 6: what bleqq watches is a member's read, gated by `watch.read` alone."""
        with stub_session(self.bank_a.principal(frozenset({perms.WATCH_READ}))):
            response = _call(self.client, "get", f"{TENANT_AGENTS}/platform", None, AS_SESSION)
        self.assertEqual(response.status_code, 501, response.content)

    def test_another_banks_record_is_404_before_the_501(self) -> None:
        """AC-NFR1: the 501 is reached only inside the caller's own bank. Bank B asking for
        bank A's agent, run or request, or for one that does not exist, is not found."""
        with stub_session(self.bank_b.principal()):
            for name, method, url, body, _ in TENANT_ROUTES:
                if name not in ID_KIND:
                    continue
                for label, target in (("another bank's", self.bank_a.record(ID_KIND[name])), ("none", uuid.uuid4())):
                    with self.subTest(operation=name, record=label):
                        response = _call(self.client, method, _filled(url, target), body, AS_SESSION)
                        self.assertEqual(response.status_code, 404, response.content)
                        self.assertEqual(response.json()["code"], "not_found")

    def test_a_request_to_another_banks_agent_is_404(self) -> None:
        body = {**REQUEST_BODY, "tenantAgentId": str(self.bank_a.agent.id)}
        with stub_session(self.bank_b.principal()):
            response = _call(self.client, "post", REQUESTS, body, AS_SESSION)
        self.assertEqual(response.status_code, 404, response.content)

    def test_a_console_session_has_no_bank_to_steer(self) -> None:
        with stub_session(user_principal(permissions=perms.ALL_PERMISSIONS, step_up_at=timezone.now())):
            response = _call(self.client, "get", TENANT_AGENTS, None, AS_SESSION)
        self.assertEqual(response.status_code, 404)


class PlatformFence(TestCase):
    """ADR 0053: a bank never steers one of bleqq's agents. `refuse_platform_agent` is the
    one function every tenant control calls; the database refuses the row as well."""

    def test_a_platform_agent_is_refused_naming_the_console_permission(self) -> None:
        from apps.agents import platform
        from apps.agents.testing import agent
        from apps.shared.errors import ProblemError

        for definition in (agent(), _tenant_definition_not_configurable()):
            with self.subTest(definition=definition.key), self.assertRaises(ProblemError) as refused:
                platform.refuse_platform_agent(definition)
            self.assertEqual(refused.exception.status, 403)
            self.assertEqual(refused.exception.code, "permission_denied")
            self.assertEqual(refused.exception.required_permission, perms.AGENT_DEFINITIONS_MANAGE)
        platform.refuse_platform_agent(_tenant_definition())  # a bank's own kind passes

    def test_a_bank_adding_one_of_bleqqs_agents_is_403(self) -> None:
        from apps.agents.testing import agent

        bleqq = agent(key=AGENT_KEY)
        bank = factories.tenant(slug="fence-create")
        with stub_session(user_principal(permissions={perms.AGENTS_MANAGE}, tenant_id=bank.id)):
            response = _call(self.client, "post", TENANT_AGENTS, {**TENANT_AGENT_BODY, "agent": bleqq.key}, AS_SESSION)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["requiredPermission"], perms.AGENT_DEFINITIONS_MANAGE)

    def test_an_unknown_definition_is_422_unknown_key(self) -> None:
        bank = factories.tenant(slug="fence-unknown")
        with stub_session(user_principal(permissions={perms.AGENTS_MANAGE}, tenant_id=bank.id)):
            response = _call(self.client, "post", TENANT_AGENTS, {**TENANT_AGENT_BODY, "agent": "no-such-agent"}, AS_SESSION)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "unknown_key")

    def test_a_bank_interrupting_a_platform_run_is_403(self) -> None:
        """A bank reads bleqq's runs in its run list; stopping one is the platform's."""
        from apps.agents.testing import platform_run

        run = platform_run()
        bank = factories.tenant(slug="fence-interrupt")
        with stub_session(user_principal(permissions={perms.AGENTS_MANAGE}, tenant_id=bank.id)):
            response = _call(self.client, "post", f"{RUNS}/{run.id}/interrupt", {}, AS_SESSION)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["requiredPermission"], perms.AGENT_DEFINITIONS_MANAGE)


def _tenant_definition_not_configurable() -> Any:
    from apps.agents.models import Agent, AgentKind, AgentScopeKind, AgentWritesTo
    from apps.shared.tenancy import library_write

    with library_write("test"):
        return Agent.objects.create(
            key="bank-fixed",
            kind=AgentKind.RESEARCH.value,
            current_version=1,
            scope=AgentScopeKind.TENANT.value,
            tenant_configurable=False,
            writes_to=AgentWritesTo.TENANT.value,
        )


class PlatformWatchShape(TestCase):
    def test_what_a_bank_reads_about_bleqqs_agents_is_exactly_these_fields(self) -> None:
        """No prompt, tool, model, version internals, budget, cost, findings, proposal
        count or setting: a later addition fails here first."""
        from apps.agents.schemas import PlatformWatchItem, PlatformWatchLastRun

        self.assertEqual(
            set(PlatformWatchItem.model_json_schema(by_alias=True)["properties"]),
            {"key", "name", "purpose", "jurisdictions", "cadence", "nextRunAt", "lastRun"},
        )
        self.assertEqual(set(PlatformWatchLastRun.model_json_schema(by_alias=True)["properties"]), {"finishedAt", "status"})


class RunListGainsChunk11(TestCase):
    """Ruling 9: `GET /agent-runs` gains `tenantAgentId` and `mine`, and each run its cost,
    trigger, requester, interruption and version. Served now, from `runs_read.py`."""

    bank: _Bank
    other: _Bank
    colleague: Any
    theirs: Any
    library: Any

    @classmethod
    def setUpTestData(cls) -> None:
        from apps.agents.models import AgentRun, RunTrigger
        from apps.agents.testing import platform_run

        definition = _tenant_definition()
        cls.bank = _Bank("runs-a", definition)
        cls.other = _Bank("runs-b", definition)
        tenancy.activate(cls.bank.tenant.id)
        cls.colleague = factories.member_user(cls.bank.tenant, roles=("admin",))
        cls.theirs = AgentRun.objects.create(
            agent=definition,
            tenant_agent=cls.bank.agent,
            trigger=RunTrigger.SCHEDULE.value,
            requested_by=cls.colleague,
            model="mock-llm",
            pipeline_version="1",
        )
        tenancy.clear_tenant()
        cls.library = platform_run()

    def _ids(self, query: str) -> list[str]:
        with stub_session(self.bank.principal(frozenset({perms.AGENTS_MANAGE}))):
            response = _call(self.client, "get", f"{RUNS}?limit=100{query}", None, AS_SESSION)
        self.assertEqual(response.status_code, 200, response.content)
        return [row["id"] for row in response.json()["items"]]

    def test_without_a_filter_the_bank_reads_the_librarys_runs_and_its_own(self) -> None:
        ids = self._ids("")
        self.assertIn(str(self.library.id), ids)
        self.assertIn(str(self.bank.run.id), ids)
        self.assertNotIn(str(self.other.run.id), ids)

    def test_one_agents_runs(self) -> None:
        ids = self._ids(f"&tenantAgentId={self.bank.agent.id}")
        self.assertEqual(sorted(ids), sorted([str(self.bank.run.id), str(self.theirs.id)]))
        self.assertEqual(self._ids(f"&tenantAgentId={self.other.agent.id}"), [])

    def test_mine_is_what_the_caller_asked_for(self) -> None:
        self.assertEqual(self._ids("&mine=true"), [str(self.bank.run.id)])

    def test_each_run_carries_the_chunk_11_fields(self) -> None:
        with stub_session(self.bank.principal(frozenset({perms.AGENTS_MANAGE}))):
            response = _call(self.client, "get", f"{RUNS}?limit=100&mine=true", None, AS_SESSION)
        row = response.json()["items"][0]
        self.assertEqual(row["trigger"], "manual")
        self.assertEqual(row["requestedBy"], {"id": str(self.bank.admin.id), "name": self.bank.admin.name})
        self.assertEqual(row["tenantAgentId"], str(self.bank.agent.id))
        self.assertIsNone(row["cost"])
        self.assertIsNone(row["interruptedAt"])
        self.assertIsNone(row["agentVersion"])
