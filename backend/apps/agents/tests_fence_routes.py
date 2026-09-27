"""Every tenant route that steers an agent passes the platform fence (AGT-03, AGT-04, ADR 0053).

A bank's controls address its own agents, and the database refuses a `tenant_agent` row on
one of bleqq's definitions (agents 0005), so a request can seldom name bleqq's agent to be
refused. What keeps that true as routes are added is that each one calls
`refuse_platform_agent` or `refuse_platform_run` before it acts. This guard walks every
registered operation, picks each write gated by `agents.manage` that names an agent or a run
(a `{tenant_agent_id}` or `{run_id}` in its path, or an `agent` or `tenantAgentId` in its
body), sends it for the caller's own agent or run, and fails on any that never reached the
fence. A new such route with no request below fails too, naming itself.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from unittest import mock

from pydantic import BaseModel

from apps.agents import platform
from apps.agents.models import AgentCadence, AgentRun, RunTrigger, TenantAgent
from apps.agents.tests_tasks import published
from apps.agents.tests_tenant_agents import TenantAgentCase
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.permissions import gate_of
from apps.shared.routes import RegisteredOperation, iter_operations
from config.api import api

FENCES = ("refuse_platform_agent", "refuse_platform_run")
NAMING_FIELDS = {"agent", "tenant_agent_id"}
WRITES = {"POST", "PUT", "PATCH", "DELETE"}

# The request each fenced route is sent, `{agent}`, `{run}` and `{definition}` filled with the
# caller's own agent, an open run of it and its definition key.
REQUESTS: dict[str, dict[str, Any]] = {
    "createTenantAgent": {"body": {"agent": "{definition}", "cadence": "weekly", "scope": {"jurisdictions": [], "terms": []}}},
    "updateTenantAgent": {"body": {"cadence": "weekly"}},
    "runTenantAgentNow": {"body": {}},
    "pauseTenantAgent": {"body": {}},
    "resumeTenantAgent": {"body": None},
    "interruptAgentRun": {"body": {}},
    "createResearchRequest": {"body": {"kind": "research_topic", "tenantAgentId": "{agent}", "topic": "DORA subcontracting"}},
}


def _body_fields(view: Callable[..., Any]) -> set[str]:
    """The field names of every request model the view takes."""
    fields: set[str] = set()
    for parameter in inspect.signature(view).parameters.values():
        annotation = parameter.annotation
        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            fields |= set(annotation.model_fields)
    return fields


def steering_routes() -> list[RegisteredOperation]:
    """Each write gated by `agents.manage` that names an agent or a run."""
    found = []
    for operation in iter_operations(api):
        gate = gate_of(operation.view_func)
        if operation.method not in WRITES or gate is None or gate.value != perms.AGENTS_MANAGE:
            continue
        names_one = "{tenant_agent_id}" in operation.path or "{run_id}" in operation.path
        if names_one or _body_fields(operation.view_func) & NAMING_FIELDS:
            found.append(operation)
    return found


@contextmanager
def fence_calls() -> Iterator[list[str]]:
    """Count every call of the fence, wherever a module bound it by name."""
    calls: list[str] = []
    patches = []
    for name in FENCES:
        original = getattr(platform, name)

        def spy(*args: Any, _original: Callable[..., None] = original, _name: str = name) -> None:
            calls.append(_name)
            _original(*args)

        for module in list(sys.modules.values()):
            if getattr(module, "__name__", "").startswith("apps.") and getattr(module, name, None) is original:
                patches.append(mock.patch.object(module, name, spy))
    for patch in patches:
        patch.start()
    try:
        yield calls
    finally:
        for patch in patches:
            patch.stop()


class EveryAgentRouteCallsTheFence(TenantAgentCase):
    def setUp(self) -> None:
        super().setUp()
        published(self.definition)
        self.set_cap()
        self.activate(self.bank)
        self.own = TenantAgent.objects.create(
            tenant=self.bank, agent=self.definition, enabled=True, cadence=AgentCadence.WEEKLY.value, scope={}
        )
        self.run_row = AgentRun.objects.create(
            agent=self.definition,
            tenant_agent=self.own,
            trigger=RunTrigger.MANUAL.value,
            requested_by=self.admin,
            model="claude-opus-5",
            pipeline_version="1",
        )
        tenancy.clear_tenant()

    def _fill(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._fill(item) for key, item in value.items()}
        if isinstance(value, str):
            return value.format(agent=self.own.id, run=self.run_row.id, definition=self.definition.key)
        return value

    def test_the_walk_finds_the_known_controls(self) -> None:
        """The rule is not vacuous: every control this chunk built is one it picks."""
        found = {operation.operation_id for operation in steering_routes()}
        self.assertLessEqual(set(REQUESTS), found)

    def test_every_route_that_steers_an_agent_reaches_the_fence(self) -> None:
        routes = steering_routes()
        missing = sorted(op.operation_id for op in routes if op.operation_id not in REQUESTS)
        self.assertEqual(missing, [], "a route that steers an agent needs a request here, and must call the fence")
        for operation in routes:
            path = operation.path.replace("{tenant_agent_id}", str(self.own.id)).replace("{run_id}", str(self.run_row.id))
            body = self._fill(REQUESTS[operation.operation_id]["body"])
            with self.subTest(operation=operation.operation_id), fence_calls() as calls:
                answer = self.call(operation.method.lower(), f"/api/v1{path}", body)
                self.assertNotEqual(answer.status_code, 404, answer.content)
                self.assertTrue(calls, f"{operation.operation_id} answered {answer.status_code} without calling the fence")
            self.activate(self.bank)
            TenantAgent.objects.filter(pk=self.own.pk).update(enabled=True, paused_at=None, paused_by=None)
            AgentRun.objects.filter(pk=self.run_row.pk).update(status="running", finished_at=None, interrupted_at=None)
            tenancy.clear_tenant()

    def test_the_spy_sees_a_refusal_as_well(self) -> None:
        """The spy passes the fence through: one of bleqq's agents is still refused."""
        with fence_calls() as calls:
            answer = self.call("post", "/api/v1/agents", {"agent": self.bleqq.key, "cadence": "weekly"})
        self.assertEqual(answer.status_code, 403, answer.content)
        self.assertEqual(answer.json()["requiredPermission"], perms.AGENT_DEFINITIONS_MANAGE)
        self.assertEqual(calls, ["refuse_platform_agent"])
