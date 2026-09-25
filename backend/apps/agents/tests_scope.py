"""What a run of a bank's own agent looks at (AGT-04, FP-04, D-32, D-89): the bank's markets
by default, operating then watching then the jurisdictions that reach them, or the agent's
own jurisdictions; keys only; retired keys dropped and noted; a copy kept on the run; the
footprint read and never written; and never a platform run.

Written before `scope.py` existed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.agents import scope as run_scope
from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, RunTrigger, TenantAgent
from apps.agents.tests_tenant_agents import TenantAgentCase
from apps.library.models import Jurisdiction
from apps.shared import tenancy
from apps.shared.tenancy import library_write
from apps.taxonomy.models import FootprintTerm, TaxonomyTerm, WatchedMarket

AGENTS_APP = Path(run_scope.__file__).resolve().parent


class RunScopeCase(TenantAgentCase):
    """A bank operating in Sweden and watching Norway, with an agent of its own that names
    no scope."""

    def setUp(self) -> None:
        super().setUp()
        self.activate(self.bank)
        FootprintTerm.objects.create(tenant=self.bank, term=TaxonomyTerm.objects.get(jurisdiction__key="se"))
        WatchedMarket.objects.create(tenant=self.bank, jurisdiction=Jurisdiction.objects.get(key="no"))
        self.agent = TenantAgent.objects.create(tenant=self.bank, agent=self.definition, enabled=True)

    def open_run(self) -> AgentRun:
        self.activate(self.bank)
        run = AgentRun.objects.create(
            agent=self.definition,
            tenant_agent=self.agent,
            tenant=self.bank,
            trigger=RunTrigger.SCHEDULE.value,
            model="mock-llm",
            pipeline_version="1",
        )
        run_scope.snapshot(run)
        return run

    def stored(self, run: AgentRun) -> dict[str, Any]:
        self.activate(self.bank)
        return AgentRun.objects.get(pk=run.pk).scope

    def retire(self, model: type[Jurisdiction] | type[TaxonomyTerm], **match: object) -> None:  # compliance: allow-kwargs test helper naming the row to retire
        with library_write("test"):
            model.objects.filter(**match).update(active=False)
        self.activate(self.bank)


class TheDefaultScopeFollowsTheMarkets(RunScopeCase):
    def test_operating_then_watching_then_reaching_stored_on_the_run(self) -> None:
        run = self.open_run()
        self.assertEqual(
            self.stored(run),
            {
                "source": "markets",
                "jurisdictions": [
                    {"key": "se", "level": "operating"},
                    {"key": "no", "level": "watching"},
                    {"key": "eu", "level": "reaching"},
                ],
                "terms": [],
                "dropped": [],
            },
        )

    def test_a_later_market_change_leaves_a_started_run_alone(self) -> None:
        run = self.open_run()
        before = self.stored(run)
        WatchedMarket.objects.create(tenant=self.bank, jurisdiction=Jurisdiction.objects.get(key="dk"))
        FootprintTerm.objects.filter(tenant=self.bank).delete()
        self.assertEqual(self.stored(run), before)
        self.assertEqual(
            [row["key"] for row in self.stored(self.open_run())["jurisdictions"]],
            ["dk", "no", "eu"],
        )

    def test_the_agents_own_jurisdictions_replace_the_markets_for_the_next_run_only(self) -> None:
        first = self.open_run()
        self.agent.scope = {"jurisdictions": ["se", "fi"], "terms": ["securities"]}
        self.agent.save()
        second = self.stored(self.open_run())
        self.assertEqual(second["source"], "agent")
        self.assertEqual(second["jurisdictions"], [{"key": "se", "level": "chosen"}, {"key": "fi", "level": "chosen"}])
        self.assertEqual(second["terms"], ["securities"])
        self.assertEqual(self.stored(first)["source"], "markets")

    def test_the_stored_scope_carries_keys_and_nothing_a_bank_typed(self) -> None:
        stored = self.stored(self.open_run())
        self.assertEqual(set(stored), {"source", "jurisdictions", "terms", "dropped"})
        for row in stored["jurisdictions"]:
            self.assertEqual(set(row), {"key", "level"})
            self.assertRegex(row["key"], r"^[a-z0-9-]+$")
        text = json.dumps(stored)
        for leak in (self.bank.name, "Sweden", "Norway", "Sverige"):
            self.assertNotIn(leak, text)


class RetiredKeys(RunScopeCase):
    def test_a_retired_key_is_dropped_from_the_run_noted_on_it_and_kept_on_the_agent(self) -> None:
        self.agent.scope = {"jurisdictions": ["se", "fi"], "terms": ["securities"]}
        self.agent.save()
        self.retire(Jurisdiction, key="fi")
        self.retire(TaxonomyTerm, key="securities")
        stored = self.stored(self.open_run())
        self.assertEqual(stored["jurisdictions"], [{"key": "se", "level": "chosen"}])
        self.assertEqual(stored["terms"], [])
        self.assertEqual(
            stored["dropped"],
            [{"vocabulary": "jurisdiction", "key": "fi"}, {"vocabulary": "taxonomy_term", "key": "securities"}],
        )
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.scope, {"jurisdictions": ["se", "fi"], "terms": ["securities"]})

    def test_a_retired_market_leaves_the_default_scope(self) -> None:
        self.retire(Jurisdiction, key="no")
        self.assertEqual(
            [row["key"] for row in self.stored(self.open_run())["jurisdictions"]],
            ["se", "eu"],
        )


class TheFootprintIsReadNeverWritten(RunScopeCase):
    def test_building_a_scope_writes_only_the_runs_own_copy(self) -> None:
        self.activate(self.bank)
        run = AgentRun.objects.create(
            agent=self.definition, tenant_agent=self.agent, tenant=self.bank, trigger=RunTrigger.SCHEDULE.value, model="m", pipeline_version="1"
        )
        with CaptureQueriesContext(connection) as queries:
            run_scope.snapshot(run)
        writes = [q["sql"] for q in queries.captured_queries if re.match(r"\s*(INSERT|UPDATE|DELETE)", q["sql"], re.I)]
        self.assertEqual(len(writes), 1, writes)
        self.assertRegex(writes[0], r'^UPDATE "agent_run" SET "scope"')


class NeverAPlatformRun(RunScopeCase):
    def test_a_platform_run_is_refused(self) -> None:
        tenancy.clear_tenant()
        run = agent_build.platform_run(key=agent_build.agent_key(agent_row=self.bleqq))
        with self.assertRaises(ValueError):
            run_scope.snapshot(run)
        self.assertEqual(AgentRun.objects.get(pk=run.pk).scope, {})

    def test_no_platform_path_reaches_the_scope(self) -> None:
        """bleqq's agents read `platform_scope`; the modules that serve them never import
        this one, so no bank's market reaches a platform prompt (D-32)."""
        for name in ("platform.py", "platform_read.py", "runs.py", "definitions.py"):
            with self.subTest(module=name):
                source = (AGENTS_APP / name).read_text(encoding="utf-8")
                self.assertNotRegex(source, r"agents\.scope\b|from apps\.agents import .*\bscope\b|import scope")
