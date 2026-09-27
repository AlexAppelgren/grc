"""A bank's own run history (AGT-04, ruling 9): `GET /agent-runs` read by a person.

What is proved here is what a bank's session sees and what it never sees:

- its own runs, newest first, with what started each, who asked, how it ended and what it
  cost; filtered to one of its agents with `tenantAgentId` and to the caller's own
  requests with `mine`;
- never a run of bleqq's own agents: those reach a bank as watch items and proposals, so no
  platform cost, token count or model is ever in a bank's list, and no figure on the page
  includes one. The console still reads the library's runs, as chunk 5 built it;
- never another bank's run, and naming another bank's agent matches nothing;
- paging at 20 by default and 100 at most, in a stable order when two runs start in the
  same microsecond, inside the API budget with `Server-Timing` reported.

Proven to fail 2026-09-25 against the contract's reading: a bank saw the library's runs,
oldest first.
"""

from __future__ import annotations

import datetime
import sys
import time
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.test import TestCase

from apps.agents import testing as agent_build
from apps.agents.models import Agent, AgentKind, AgentRun, AgentScopeKind, AgentWritesTo, RunTrigger, TenantAgent
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import Tenant
from apps.shared.tenancy import library_write
from apps.shared.testing import stub_session, user_principal

RUNS = "/api/v1/agent-runs"
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": "Bearer test-session-token"}
# Anchored so the order is an assertion about the contract and never about the clock: two
# runs opened inside one test are microseconds apart, on some machines the same tick.
EARLIER = datetime.datetime(2026, 9, 20, 2, 0, tzinfo=datetime.UTC)
LATER = EARLIER + datetime.timedelta(days=1)


def _definition(key: str) -> Agent:
    with library_write("test"):
        return Agent.objects.create(
            key=key,
            kind=AgentKind.RESEARCH.value,
            active=True,
            current_version=1,
            scope=AgentScopeKind.TENANT.value,
            tenant_configurable=True,
            writes_to=AgentWritesTo.TENANT.value,
        )


def _run(tenant_agent: TenantAgent, *, trigger: RunTrigger, started_at: datetime.datetime, **fields: Any) -> AgentRun:
    """One run of a bank's own agent, started when the test says. Written inside the bank."""
    tenancy.activate(tenant_agent.tenant_id)
    try:
        run = AgentRun.objects.create(
            agent=tenant_agent.agent, tenant_agent=tenant_agent, trigger=trigger.value, model="mock-llm", pipeline_version="1", **fields
        )
        AgentRun.objects.filter(pk=run.pk).update(started_at=started_at)
        run.refresh_from_db()
        return run
    finally:
        tenancy.clear_tenant()


class ABanksOwnRunHistory(TestCase):
    bank: Tenant
    other: Tenant
    asker: Any
    watch: TenantAgent
    second: TenantAgent
    theirs: TenantAgent
    asked: AgentRun
    scheduled: AgentRun
    tied: AgentRun
    other_run: AgentRun
    library: AgentRun

    @classmethod
    def setUpTestData(cls) -> None:
        definition = _definition("bank-watch")
        cls.bank = factories.tenant(slug="history-a")
        cls.other = factories.tenant(slug="history-b")
        cls.asker = factories.member_user(cls.bank, roles=("admin",))
        tenancy.activate(cls.bank.id)
        cls.watch = TenantAgent.objects.create(tenant=cls.bank, agent=definition)
        cls.second = TenantAgent.objects.create(tenant=cls.bank, agent=_definition("bank-second"))
        tenancy.activate(cls.other.id)
        cls.theirs = TenantAgent.objects.create(tenant=cls.other, agent=definition)
        tenancy.clear_tenant()
        cls.asked = _run(
            cls.watch,
            trigger=RunTrigger.MANUAL,
            started_at=LATER,
            requested_by=cls.asker,
            status="succeeded",
            finished_at=LATER + datetime.timedelta(minutes=4),
            cost=Decimal("1.2500"),
            tokens_in=51_000,
            tokens_out=2_300,
        )
        cls.scheduled = _run(cls.watch, trigger=RunTrigger.SCHEDULE, started_at=EARLIER)
        cls.tied = _run(cls.second, trigger=RunTrigger.SCHEDULE, started_at=EARLIER)
        cls.other_run = _run(cls.theirs, trigger=RunTrigger.SCHEDULE, started_at=LATER, cost=Decimal("9.0000"))
        cls.library = agent_build.platform_run()
        AgentRun.objects.filter(pk=cls.library.pk).update(cost=Decimal("40.0000"), tokens_in=900_000)

    def read(self, query: str = "", *, permissions: frozenset[str] = frozenset({perms.AGENTS_MANAGE}), tenant: Tenant | None = None) -> Any:
        principal = user_principal(permissions=permissions, tenant_id=(tenant or self.bank).id, subject_id=self.asker.id)
        with stub_session(principal):
            response = self.client.get(f"{RUNS}{query}", **AS_SESSION)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def ids(self, query: str = "") -> list[str]:
        return [row["id"] for row in self.read(query)["items"]]

    def test_a_bank_reads_its_own_runs_and_never_a_platform_run(self) -> None:
        body = self.read()
        self.assertEqual(
            {row["id"] for row in body["items"]}, {str(self.asked.id), str(self.scheduled.id), str(self.tied.id)}
        )
        self.assertNotIn(str(self.library.id), self.ids(), "bleqq's runs reach a bank as watch items, not run rows")
        self.assertNotIn(str(self.other_run.id), self.ids(), "a bank never reads another bank's run")
        self.assertEqual(body["total"], len(body["items"]), "total counts only the bank's own runs")

    def test_no_figure_on_the_page_is_a_platform_runs(self) -> None:
        body = self.read()
        self.assertEqual({row["tenantAgentId"] for row in body["items"]}, {str(self.watch.id), str(self.second.id)})
        costs = {row["cost"] for row in body["items"]} - {None}
        self.assertEqual({Decimal(cost) for cost in costs}, {self.asked.cost})
        self.assertNotIn("tokensIn", body["items"][0], "no token count is published")

    def test_newest_first_with_a_stable_tiebreak(self) -> None:
        tied = sorted([self.scheduled, self.tied], key=lambda run: run.id, reverse=True)
        expected = [str(self.asked.id)] + [str(run.id) for run in tied]
        self.assertEqual(self.ids(), expected)
        self.assertEqual(self.ids("?limit=1&offset=1") + self.ids("?limit=1&offset=2"), expected[1:])

    def test_each_run_carries_what_started_it_who_asked_and_what_it_cost(self) -> None:
        row = next(row for row in self.read()["items"] if row["id"] == str(self.asked.id))
        self.assertEqual(row["trigger"], "manual")
        self.assertEqual(row["requestedBy"], {"id": str(self.asker.id), "name": self.asker.name})
        self.assertEqual(row["status"], "succeeded")
        self.assertEqual(Decimal(row["cost"]), Decimal("1.25"))
        self.assertEqual(row["tenantAgentId"], str(self.watch.id))
        self.assertIsNone(row["interruptedAt"])
        scheduled = next(row for row in self.read()["items"] if row["id"] == str(self.scheduled.id))
        self.assertIsNone(scheduled["requestedBy"], "a schedule is nobody's request")

    def test_one_of_the_banks_agents(self) -> None:
        self.assertEqual(self.ids(f"?tenantAgentId={self.watch.id}"), [str(self.asked.id), str(self.scheduled.id)])
        self.assertEqual(self.ids(f"?tenantAgentId={self.second.id}"), [str(self.tied.id)])

    def test_another_banks_agent_matches_no_run(self) -> None:
        self.assertEqual(self.read(f"?tenantAgentId={self.theirs.id}"), {"items": [], "total": 0})
        self.assertEqual(self.read(f"?tenantAgentId={uuid.uuid4()}"), {"items": [], "total": 0})

    def test_mine_is_what_the_caller_asked_for(self) -> None:
        self.assertEqual(self.ids("?mine=true"), [str(self.asked.id)])

    def test_the_other_bank_reads_only_its_own(self) -> None:
        body = self.read(tenant=self.other)
        self.assertEqual([row["id"] for row in body["items"]], [str(self.other_run.id)])

    def test_the_console_still_reads_the_librarys_runs_and_no_banks(self) -> None:
        principal = user_principal(permissions={perms.SYSTEM_HEALTH})
        with stub_session(principal):
            body = self.client.get(RUNS, **AS_SESSION).json()
        self.assertEqual([row["id"] for row in body["items"]], [str(self.library.id)])


class RunHistoryPaging(TestCase):
    """Playbook 10 and NFR-02: 20 by default, 100 at most, inside the API budget with 200 runs."""

    bank: Tenant
    agent: TenantAgent

    @classmethod
    def setUpTestData(cls) -> None:
        cls.bank = factories.tenant(slug="history-paging")
        tenancy.activate(cls.bank.id)
        cls.agent = TenantAgent.objects.create(tenant=cls.bank, agent=_definition("bank-busy"))
        AgentRun.objects.bulk_create(
            AgentRun(
                agent=cls.agent.agent,
                tenant_agent=cls.agent,
                tenant=cls.bank,
                trigger=RunTrigger.SCHEDULE.value,
                model="mock-llm",
                pipeline_version="1",
                cost=Decimal("0.1000"),
            )
            for _ in range(200)
        )
        tenancy.clear_tenant()

    def get(self, query: str = "") -> Any:
        with stub_session(user_principal(permissions={perms.AGENTS_MANAGE}, tenant_id=self.bank.id)):
            return self.client.get(f"{RUNS}{query}", **AS_SESSION)

    def test_a_page_is_20_by_default_and_100_at_most(self) -> None:
        self.assertEqual(len(self.get().json()["items"]), settings.API_PAGE_SIZE_DEFAULT)
        self.assertEqual(len(self.get(f"?limit={settings.API_PAGE_SIZE_MAX}").json()["items"]), settings.API_PAGE_SIZE_MAX)
        self.assertEqual(self.get(f"?limit={settings.API_PAGE_SIZE_MAX + 1}").status_code, 422)

    def test_a_full_page_stays_inside_the_budget(self) -> None:
        query = f"?limit={settings.API_PAGE_SIZE_MAX}"
        response = self.get(query)
        self.assertEqual(response.json()["total"], 200)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        # CPU time on the request thread, the best of five, with the coverage tracer paused
        # for the timed requests only (the pattern of watch/tests_reading.py).
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.get(query)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)
