"""bleqq's own agents in the console (AGT-03, ADM-02, ADR 0053): their settings and their
runs, and the bank that no longer receives a platform run.

A platform agent's cadence, the jurisdictions it sweeps and its budget are one setting for
every bank, read without touching any bank's row. Changing them answers 501 until the fence
decision in docs/TODO_FOR_alex.md (c11-definitions-platform). The console's run list carries bleqq's runs alone, newest first, with what each
filed counted from the rows themselves in one query per page, and no bank's name or figure.

Proven to fail 2026-09-25 against the declared contract: every route test below answered
501 `not_built` before `platform.py` was written, and the bank's run log still listed the
library's runs.
"""

from __future__ import annotations

import datetime
import re
import time
import uuid
from decimal import Decimal
from typing import Any

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.agents.models import Agent, AgentRun, RunTrigger
from apps.agents.tests_definitions import platform_agent
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.tenancy import TenantModel, library_write
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, production_models, stub_session, user_principal
from apps.taxonomy.seeds import seed_library_vocabularies
from apps.watch import testing as watch_build

DEFINITIONS = "/api/v1/agent-definitions"
CONSOLE_RUNS = "/api/v1/console/agent-runs"
RUNS = "/api/v1/agent-runs"
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}
JSON = "application/json"
BANK_NAMES = ("Nordbanken Settings AB", "Fjordbank Settings ASA")
# The tables that hold a bank's rows: every tenant model, and the bank itself.
TENANT_TABLES = frozenset({"tenant"} | {model._meta.db_table for model in production_models() if issubclass(model, TenantModel)})


def two_banks() -> list[Any]:
    """Two banks, each with an agent of its own and a run of it, so a read of either shows."""
    definition = _tenant_definition()
    banks = []
    for name in BANK_NAMES:
        bank = factories.tenant(slug=f"bank-{uuid.uuid4().hex[:6]}", name=name)
        admin = factories.member_user(bank, roles=("admin",))
        tenancy.activate(bank.id)
        from apps.agents.models import TenantAgent

        own = TenantAgent.objects.create(tenant=bank, agent=definition)
        AgentRun.objects.create(
            agent=definition,
            tenant_agent=own,
            trigger=RunTrigger.MANUAL.value,
            requested_by=admin,
            model="bank-model",
            pipeline_version="1",
            cost=Decimal("12.5000"),
        )
        tenancy.clear_tenant()
        banks.append(bank)
    return banks


def _tenant_definition() -> Agent:
    from apps.agents.models import AgentKind, AgentScopeKind, AgentWritesTo

    with library_write("test"):
        return Agent.objects.create(
            key=f"bank-watch-{uuid.uuid4().hex[:6]}",
            kind=AgentKind.RESEARCH.value,
            current_version=1,
            scope=AgentScopeKind.TENANT.value,
            tenant_configurable=True,
            writes_to=AgentWritesTo.TENANT.value,
        )


class ConsoleCase(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        self.admin = factories.platform_user()
        self.assertion = uuid.uuid4()

    def principal(self, *, step_up: bool = True) -> Any:
        return user_principal(
            permissions={perms.AGENT_DEFINITIONS_MANAGE},
            subject_id=self.admin.id,
            step_up_at=timezone.now() if step_up else None,
            step_up_assertion_id=self.assertion if step_up else None,
        )

    def call(self, method: str, url: str, body: Any = None, principal: Any = None) -> Any:
        with stub_session(principal or self.principal()):
            return getattr(self.client, method)(url, data=body, content_type=JSON, **AS_SESSION)


class PlatformAgentSettings(ConsoleCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent = platform_agent(f"nordic-watch-{uuid.uuid4().hex[:6]}", versions=1)
        self.url = f"{DEFINITIONS}/{self.agent.key}/settings"

    def test_reading_them(self) -> None:
        response = self.call("get", self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"agentKey": self.agent.key, "cadence": "weekly", "jurisdictions": [], "monthlyBudget": None})

    def test_a_definition_a_bank_adds_for_itself_has_no_platform_settings(self) -> None:
        own = _tenant_definition()
        self.assertEqual(self.call("get", f"{DEFINITIONS}/{own.key}/settings").status_code, 404)
        self.assertEqual(self.call("get", f"{DEFINITIONS}/no-such-agent/settings").status_code, 404)

    def test_no_bank_row_is_read(self) -> None:
        """Two banks with agents and runs of their own are there to be read; the settings
        read touches none of their tables."""
        two_banks()
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.call("get", self.url).status_code, 200)
        reads = [query["sql"] for query in queries.captured_queries if query["sql"].lstrip().upper().startswith("SELECT")]
        self.assertTrue(reads)
        touched = {table for sql in reads for table in re.findall(r'(?:FROM|JOIN) "([a-z_]+)"', sql)}
        self.assertEqual(touched & TENANT_TABLES, set(), touched)


class PlatformRuns(ConsoleCase):
    def setUp(self) -> None:
        super().setUp()
        self.banks = two_banks()
        self.key = agent_build.agent_key(agent_row=platform_agent(f"sweeper-{uuid.uuid4().hex[:6]}", versions=1))

    def platform_runs(self, count: int) -> list[AgentRun]:
        """`count` platform runs a night apart, the newest last."""
        anchor = timezone.now().replace(hour=2, minute=0, second=0, microsecond=0)
        made = [agent_build.platform_run(key=self.key) for _ in range(count)]
        for age, run in enumerate(reversed(made)):
            AgentRun.objects.filter(pk=run.pk).update(started_at=anchor - datetime.timedelta(days=age))
        return made

    def test_bleqqs_runs_newest_first_and_no_banks(self) -> None:
        older, newer = self.platform_runs(2)
        response = self.call("get", f"{CONSOLE_RUNS}?limit=100")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([row["id"] for row in body["items"]], [str(newer.id), str(older.id)])
        self.assertEqual(body["total"], 2)

    def test_no_row_carries_a_bank(self) -> None:
        self.platform_runs(1)
        response = self.call("get", f"{CONSOLE_RUNS}?limit=100")
        for name in BANK_NAMES:
            self.assertNotIn(name, response.content.decode())
        for row in response.json()["items"]:
            self.assertIsNone(row["tenantAgentId"])
            self.assertEqual([field for field in row if "tenant" in field.lower() and field != "tenantAgentId"], [])

    def test_each_run_carries_what_it_filed_counted_from_the_rows(self) -> None:
        [run] = self.platform_runs(1)
        seed_library_vocabularies()
        first, second = watch_build.source(authority=None), watch_build.source(authority=None)
        for source in (first, first, second):
            watch_build.source_check(source, run=run)
        stats = self.call("get", CONSOLE_RUNS).json()["items"][0]["stats"]
        self.assertEqual((stats["sourcesChecked"], stats["changesRegistered"], stats["proposalsSubmitted"]), (2, 0, 0))

    def test_one_query_per_page_however_many_runs(self) -> None:
        self.platform_runs(3)
        with CaptureQueriesContext(connection) as few:
            self.call("get", f"{CONSOLE_RUNS}?limit=100")
        self.platform_runs(10)
        with CaptureQueriesContext(connection) as many:
            self.call("get", f"{CONSOLE_RUNS}?limit=100")
        self.assertEqual(len(many.captured_queries), len(few.captured_queries))

    def test_pages_of_20_by_default_and_100_at_most(self) -> None:
        self.platform_runs(25)
        first = self.call("get", CONSOLE_RUNS).json()
        self.assertEqual((len(first["items"]), first["total"]), (20, 25))
        rest = self.call("get", f"{CONSOLE_RUNS}?offset=20").json()["items"]
        self.assertEqual(len({row["id"] for row in first["items"]} | {row["id"] for row in rest}), 25)
        self.assertEqual(self.call("get", f"{CONSOLE_RUNS}?limit=101").status_code, 422)

    def test_an_empty_list_is_200(self) -> None:
        response = self.call("get", CONSOLE_RUNS)
        self.assertEqual((response.status_code, response.json()), (200, {"items": [], "total": 0}))

    def test_inside_the_budget_at_200_runs(self) -> None:
        self.platform_runs(200)
        started = time.perf_counter()
        response = self.call("get", f"{CONSOLE_RUNS}?limit=100")
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertEqual(response.status_code, 200)
        server_ms = float(re.fullmatch(r"app;dur=([\d.]+)", response["Server-Timing"]).group(1))  # type: ignore[union-attr]
        self.assertLess(server_ms, 250, "API budget: under 250 ms server time")
        self.assertLess(server_ms, elapsed_ms + 1)


class ABankReadsNoPlatformRun(ConsoleCase):
    """ADR 0053 and the default on what a bank sees of bleqq's watch: its own runs, and no
    run row of bleqq's agents, which the console reads instead."""

    def test_a_bank_session_reads_its_own_runs_and_no_library_run(self) -> None:
        bank, other = two_banks()
        library = agent_build.platform_run()
        principal = user_principal(permissions={perms.AGENTS_MANAGE}, tenant_id=bank.id)
        with stub_session(principal):
            response = self.client.get(f"{RUNS}?limit=100", **AS_SESSION)
        self.assertEqual(response.status_code, 200, response.content)
        ids = [row["id"] for row in response.json()["items"]]
        tenancy.activate(bank.id)
        own = list(AgentRun.objects.filter(tenant_id=bank.id).values_list("id", flat=True))
        tenancy.clear_tenant()
        self.assertEqual(ids, [str(run_id) for run_id in own])
        self.assertNotIn(str(library.id), ids)
        self.assertEqual(response.json()["total"], len(own))
