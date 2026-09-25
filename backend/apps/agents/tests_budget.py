"""The bank's one monthly cap on its own agents and what they spent (AGT-04, ruling 3, D-61).

Written before the logic: against the contract's stubs both routes answered 501 `not_built`
and `spend`, `at_cap` and `cap_of` did not exist.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.agents import budget
from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, RunTrigger, TenantAgent, TenantAgentBudget
from apps.agents.tests_tenant_agents import TenantAgentCase
from apps.shared import tenancy
from apps.shared.models import AuditEvent

BUDGET = "/api/v1/tenant/agent-budget"


class BudgetCase(TenantAgentCase):
    def run_of(self, agent: TenantAgent, *, cost: str, started_at: datetime.datetime) -> AgentRun:
        tenancy.activate(agent.tenant_id)
        run = AgentRun.objects.create(
            agent=agent.agent,
            tenant_agent=agent,
            tenant=agent.tenant,
            trigger=RunTrigger.SCHEDULE.value,
            model="mock-llm",
            pipeline_version="1",
            cost=Decimal(cost),
        )
        AgentRun.objects.filter(pk=run.pk).update(started_at=started_at)
        tenancy.clear_tenant()
        return run

    def own_agent(self, bank: Any = None) -> TenantAgent:
        bank = bank or self.bank
        tenancy.activate(bank.id)
        agent = TenantAgent.objects.create(tenant=bank, agent=self.definition, enabled=True)
        tenancy.clear_tenant()
        return agent

    def month_start(self, bank: Any = None) -> datetime.datetime:
        """The start of the bank's current month in its own zone, from the real clock."""
        zone = ZoneInfo((bank or self.bank).timezone)
        first = timezone.now().astimezone(zone).date().replace(day=1)
        return datetime.datetime.combine(first, datetime.time.min, tzinfo=zone)


class ReadingTheBudget(BudgetCase):
    def test_no_cap_reads_as_null_and_nothing_is_written(self) -> None:
        answer = self.call("get", BUDGET)
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(answer.json(), {"monthlyCap": None, "currency": "EUR", "spentThisMonth": "0.00"})
        self.activate(self.bank)
        self.assertFalse(TenantAgentBudget.objects.exists())
        self.assertIsNone(budget.cap_of(self.bank))
        self.assertTrue(budget.at_cap(self.bank), "no agent of a bank's own runs uncapped")


class SettingTheCap(BudgetCase):
    def test_the_first_write_creates_the_row_and_later_ones_change_it(self) -> None:
        answer = self.call("put", BUDGET, {"monthlyCap": "500.00"})
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(answer.json()["monthlyCap"], "500.00")
        answer = self.call("put", BUDGET, {"monthlyCap": "250.00"})
        self.assertEqual(answer.json()["monthlyCap"], "250.00")
        self.activate(self.bank)
        self.assertEqual([str(row.monthly_cap) for row in TenantAgentBudget.objects.all()], ["250.00"])
        first, second = AuditEvent.objects.filter(action="agents.budget_set").order_by("created", "id")
        self.assertEqual(first.tenant_id, self.bank.id)
        self.assertEqual(first.before, {})
        self.assertEqual(first.after, {"monthlyCap": "500.00", "currency": "EUR"})
        self.assertEqual(second.before["monthlyCap"], "500.00")
        self.assertEqual(second.after["monthlyCap"], "250.00")
        # Another bank's cap is its own.
        self.assertIsNone(self.call("get", BUDGET, bank=self.other, admin=self.other_admin).json()["monthlyCap"])

    def test_a_negative_cap_is_refused(self) -> None:
        answer = self.call("put", BUDGET, {"monthlyCap": "-1.00"})
        self.assertEqual(answer.status_code, 422, answer.content)

    def test_a_cap_at_or_below_the_spend_is_accepted_and_pauses_the_banks_agents(self) -> None:
        running = self.own_agent()
        self.run_of(running, cost="40.00", started_at=self.month_start() + datetime.timedelta(hours=1))
        others = self.own_agent(self.other)
        self.assertEqual(self.call("put", BUDGET, {"monthlyCap": "100.00"}).status_code, 200)
        self.activate(self.bank)
        self.assertIsNone(TenantAgent.objects.get(pk=running.pk).paused_at, "a cap above the spend pauses nothing")

        answer = self.call("put", BUDGET, {"monthlyCap": "30.00"})
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(answer.json(), {"monthlyCap": "30.00", "currency": "EUR", "spentThisMonth": "40.00"})
        self.activate(self.bank)
        paused = TenantAgent.objects.get(pk=running.pk)
        self.assertIsNotNone(paused.paused_at)
        self.assertEqual(paused.pause_reason, budget.CAP_REASON)
        [row] = AuditEvent.objects.filter(action="agents.tenant_agent_paused")
        self.assertEqual((row.subject_id, row.tenant_id), (running.pk, self.bank.id))
        self.activate(self.other)
        self.assertIsNone(TenantAgent.objects.get(pk=others.pk).paused_at, "another bank's agents are its own")


class TheMonthsSpend(BudgetCase):
    def test_spend_sums_the_banks_own_runs_in_its_own_month_and_never_a_platform_run(self) -> None:
        mine = self.own_agent()
        start = self.month_start()
        self.run_of(mine, cost="12.50", started_at=start + datetime.timedelta(minutes=1))
        self.run_of(mine, cost="0.25", started_at=timezone.now())
        self.run_of(mine, cost="99.00", started_at=start - datetime.timedelta(minutes=1))
        self.run_of(self.own_agent(self.other), cost="77.00", started_at=timezone.now())
        platform = agent_build.platform_run(key=agent_build.agent_key(agent_row=self.bleqq))
        AgentRun.objects.filter(pk=platform.pk).update(cost=Decimal("500.00"))
        tenancy.clear_tenant()

        self.activate(self.bank)
        self.assertEqual(budget.spend(self.bank), Decimal("12.75"))
        tenancy.clear_tenant()
        self.assertEqual(self.call("get", BUDGET).json()["spentThisMonth"], "12.75")

    def test_at_cap_is_the_spend_reaching_the_cap(self) -> None:
        mine = self.own_agent()
        self.run_of(mine, cost="10.00", started_at=timezone.now())
        self.activate(self.bank)
        TenantAgentBudget.objects.create(tenant=self.bank, monthly_cap=Decimal("10.01"))
        self.assertFalse(budget.at_cap(self.bank))
        TenantAgentBudget.objects.filter(tenant=self.bank).update(monthly_cap=Decimal("10.00"))
        self.assertTrue(budget.at_cap(self.bank))
