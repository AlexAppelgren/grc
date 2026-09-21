"""Contract guard for the agent-facing run routes and the platform agent-key routes
(AGT-01, AGT-02, ID-10, NFR-01, chunk 5 `c5-contract-api-agent`).

The routes are declared before the logic that serves them: each one answers 501
`not_built` from the named function in the module that will build it, and every refusal
in front of that stub is proved here, per route. Written before the routes existed
(2026-09-20): every case below failed with 404 until `agents/api.py` and the three
`identity/api.py` routes landed.

The three run routes are no longer stubs — `c5-agent-runs` built them, and what they do
behind these gates is proved in `tests_runs.py` — so they left the stub list below on
2026-09-21 while keeping every gate assertion they had. `recordSourceCheck` followed them
the same day (`c5-watch-sources-coverage`, proved in `apps/watch/tests_sources.py`). The
three agent-key routes are still declared ahead of their logic.

The agent-key routes live in `identity/api.py` but are proved here, beside the runs they
create keys for: `identity/tests_api_keys.py` belongs to the task that builds their logic.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.shared import permissions as perms
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
    ("listAgentKeys", "get", KEYS, None, perms.AGENT_DEFINITIONS_MANAGE),
    ("createAgentKey", "post", KEYS, KEY_BODY, perms.AGENT_DEFINITIONS_MANAGE),
    ("revokeAgentKey", "post", f"{KEYS}/{KEY}/revoke", {}, perms.AGENT_DEFINITIONS_MANAGE),
]
# What is still declared ahead of its logic. The three run routes left this list when
# `c5-agent-runs` built them and `recordSourceCheck` when `c5-watch-sources-coverage` did;
# the gates above still cover all of them, so nothing is left unproved by their leaving.
STUBBED_KEY_ROUTES: list[tuple[str, str, str, Any, str]] = []
STUBBED_SESSION_ROUTES = [route for route in SESSION_ROUTES if route[0] != "listAgentRuns"]


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

    def test_creating_a_key_needs_a_fresh_assertion_before_the_stub(self) -> None:
        with stub_session(user_principal(permissions={perms.AGENT_DEFINITIONS_MANAGE})):
            response = _call(self.client, "post", KEYS, KEY_BODY, AS_SESSION)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")

    def test_bad_input_is_422_before_the_stub(self) -> None:
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


class AgentRouteStubs(TestCase):
    """Behind the gate, every route answers the same 501 until its logic task lands."""

    def assert_not_built(self, response: Any) -> None:
        self.assertEqual(response.status_code, 501)
        problem = response.json()
        self.assertEqual(problem["code"], "not_built")
        self.assertEqual(response.headers["Content-Type"], "application/problem+json")
        self.assertNotIn("traceback", response.content.decode().lower())

    def test_a_key_with_the_scope_reaches_the_stub(self) -> None:
        self.assertEqual(STUBBED_KEY_ROUTES, [], "every key route of this chunk is built; nothing is left to stub")
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body, _ in STUBBED_KEY_ROUTES:
                with self.subTest(operation=name):
                    self.assert_not_built(_call(self.client, method, url, body, AS_KEY))

    def test_the_built_source_check_route_answers_from_its_logic(self) -> None:
        """`recordSourceCheck` no longer answers `not_built`. The run these constants name
        does not exist, so the honest answer is 404 — which is also the proof that the gate
        ran first and the lookup second."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            response = _call(self.client, "post", f"{RUNS}/{RUN}/source-checks", CHECK_BODY, AS_KEY)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["code"], "not_found")

    def test_a_session_with_the_permission_reaches_the_stub(self) -> None:
        principal = user_principal(
            permissions={perms.AGENTS_MANAGE, perms.AGENT_DEFINITIONS_MANAGE},
            tenant_id=uuid.uuid4(),
            step_up_at=timezone.now(),
        )
        with stub_session(principal):
            for name, method, url, body, _ in STUBBED_SESSION_ROUTES:
                with self.subTest(operation=name):
                    self.assert_not_built(_call(self.client, method, url, body, AS_SESSION))

    def test_system_health_also_reads_the_run_list(self) -> None:
        """The run log is served now, so the proof is that `system.health` passes its gate;
        what it returns is `tests_runs.py`'s."""
        with stub_session(user_principal(permissions={perms.SYSTEM_HEALTH})):
            response = _call(self.client, "get", RUNS, None, AS_SESSION)
        self.assertEqual(response.status_code, 200, response.content)
