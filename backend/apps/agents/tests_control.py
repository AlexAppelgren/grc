"""Run now, pause, resume and interrupt a bank's own agent, and the cap stopping a run mid-way
(AGT-04, AGT-06, ADR 0053).

Each control loads its record under row-level security, passes the platform fence, writes
through `record()` in the same transaction, and never reaches the runner before the run row
exists. The cap has a second point beside the scheduler's: a runner event whose cumulative
cost passes the bank's monthly cap interrupts the run through the runner and pauses the
agent, as the scheduler pauses it.

Written before the logic: against the contract's stubs every control below answered 501
`not_built`, and a runner event passing the cap left its run running.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest import mock

from django.utils import timezone

from apps.agents import control, opener, runner_events
from apps.agents import testing as agent_build
from apps.agents.models import AgentCadence, AgentRun, RunStatus, TenantAgent, TenantAgentBudget
from apps.agents.tests_tasks import Recorded, published, with_runner
from apps.agents.tests_tenant_agents import AGENTS, TenantAgentCase
from apps.collab.models import Notification
from apps.shared import tenancy
from apps.shared.adapters.agent_runner import MockAgentRunner, RunHandle, RunnerEvent
from apps.shared.models import Tenant

RUNS = "/api/v1/agent-runs"


class Interrupting(MockAgentRunner):
    """The mock runner, noting each run it was asked to stop."""

    def __init__(self) -> None:
        self.stopped: list[RunHandle] = []

    def interrupt(self, handle: RunHandle) -> RunHandle:
        self.stopped.append(handle)
        return super().interrupt(handle)


def with_interrupts(runner: Interrupting) -> Any:
    return mock.patch.object(control, "get_agent_runner", return_value=runner)


class ControlCase(TenantAgentCase):
    """The bank's own agent, switched on, weekly, with a published version and a cap."""

    def setUp(self) -> None:
        super().setUp()
        published(self.definition)
        self.set_cap()
        self.activate(self.bank)
        self.own = TenantAgent.objects.create(
            tenant=self.bank,
            agent=self.definition,
            enabled=True,
            cadence=AgentCadence.WEEKLY.value,
            run_weekday=1,
            run_hour=6,
            scope={"jurisdictions": ["se", "fi"], "terms": []},
        )
        tenancy.clear_tenant()

    def reload(self) -> TenantAgent:
        self.activate(self.bank)
        agent = TenantAgent.objects.get(pk=self.own.pk)
        tenancy.clear_tenant()
        return agent

    def stored(self, run_id: Any) -> AgentRun:
        self.activate(self.bank)
        run = AgentRun.objects.get(pk=run_id)
        tenancy.clear_tenant()
        return run

    def runs(self) -> list[AgentRun]:
        self.activate(self.bank)
        rows = list(AgentRun.objects.order_by("started_at", "id"))
        tenancy.clear_tenant()
        return rows

    def run_now(self) -> Any:
        return self.call("post", f"{AGENTS}/{self.own.id}/runs", {})


class RunningNow(ControlCase):
    def test_a_run_is_queued_with_the_agents_settings_and_the_caller(self) -> None:
        answer = self.run_now()
        self.assertEqual(answer.status_code, 202, answer.content)
        body = answer.json()
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["trigger"], "manual")
        self.assertEqual(body["tenantAgentId"], str(self.own.id))
        self.assertEqual(body["requestedBy"]["id"], str(self.admin.id))
        run = self.stored(body["id"])
        self.assertEqual(run.tenant_id, self.bank.id)
        self.assertEqual([row["key"] for row in run.scope["jurisdictions"]], ["se", "fi"])
        self.assertIsNotNone(run.budget_limit)
        opened = self.audit("agent_run.opened")
        self.assertEqual([row.subject_id for row in opened], [run.id])
        self.assertEqual(opened[0].actor_id, self.admin.id)

    def test_the_run_keeps_the_scope_it_started_with(self) -> None:
        run_id = self.run_now().json()["id"]
        changed = self.call(
            "patch", f"{AGENTS}/{self.own.id}", {"scope": {"jurisdictions": ["dk"], "terms": []}}
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual([row["key"] for row in self.stored(run_id).scope["jurisdictions"]], ["se", "fi"])

    def test_the_row_exists_before_the_runner_is_asked(self) -> None:
        """A runner that fails leaves the recorded run closed as failed, never missing."""
        runner = Recorded(fail=True)
        with with_runner(runner):
            answer = self.run_now()
        self.assertEqual(answer.status_code, 202, answer.content)
        self.assertEqual(runner.seen, [(True, self.bank.id)])
        self.assertEqual(self.stored(answer.json()["id"]).status, RunStatus.FAILED.value)

    def test_each_refusal_has_its_own_code_and_opens_no_run(self) -> None:
        cases: list[tuple[str, dict[str, Any], int, str]] = [
            ("paused", {"paused_at": timezone.now(), "paused_by": self.admin}, 409, "agent_paused"),
            ("switched off", {"enabled": False}, 409, "agent_disabled"),
        ]
        for label, fields, status, code in cases:
            with self.subTest(label):
                self.activate(self.bank)
                TenantAgent.objects.filter(pk=self.own.pk).update(**fields)
                tenancy.clear_tenant()
                answer = self.run_now()
                self.assertEqual(answer.status_code, status, answer.content)
                self.assertEqual(answer.json()["code"], code)
                self.activate(self.bank)
                TenantAgent.objects.filter(pk=self.own.pk).update(
                    enabled=True, paused_at=None, paused_by=None
                )
                tenancy.clear_tenant()
        self.assertEqual(self.runs(), [])

    def test_ai_off_and_the_cap_refuse_through_the_scheduler_of_record(self) -> None:
        Tenant.objects.filter(pk=self.bank.pk).update(ai_enabled=False)
        answer = self.run_now()
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "feature_off")
        Tenant.objects.filter(pk=self.bank.pk).update(ai_enabled=True)
        self.activate(self.bank)
        TenantAgentBudget.objects.filter(tenant=self.bank).update(monthly_cap=Decimal("1.00"))
        tenancy.clear_tenant()
        answer = self.run_now()
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "budget_cap_reached")
        self.assertEqual(self.runs(), [])
        self.assertIsNone(self.reload().paused_at, "a person asking is answered; nothing is paused")

    def test_another_banks_agent_is_not_found(self) -> None:
        answer = self.call(
            "post", f"{AGENTS}/{self.own.id}/runs", {}, bank=self.other, admin=self.other_admin
        )
        self.assertEqual(answer.status_code, 404, answer.content)
        self.assertEqual(self.runs(), [])


class PausingAndResuming(ControlCase):
    def test_pause_stops_the_schedule_and_names_the_person(self) -> None:
        answer = self.call("post", f"{AGENTS}/{self.own.id}/pause", {})
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertIsNotNone(answer.json()["pausedAt"])
        self.assertEqual(answer.json()["pausedBy"]["id"], str(self.admin.id))
        self.assertIsNone(answer.json()["nextRunAt"])
        again = self.call("post", f"{AGENTS}/{self.own.id}/pause", {})
        self.assertEqual(again.status_code, 200, again.content)
        paused = self.audit("agents.tenant_agent_paused")
        self.assertEqual(len(paused), 1, "pausing a paused agent records nothing")
        self.assertEqual(paused[0].actor_id, self.admin.id)
        self.assertEqual(paused[0].after["pauseReason"], control.PAUSED_BY_PERSON)

    def test_pause_leaves_an_open_run_running(self) -> None:
        run_id = self.run_now().json()["id"]
        self.call("post", f"{AGENTS}/{self.own.id}/pause", {})
        self.assertEqual(self.stored(run_id).status, RunStatus.RUNNING.value)

    def test_resume_clears_the_pause_and_schedules_the_next_run(self) -> None:
        self.call("post", f"{AGENTS}/{self.own.id}/pause", {})
        answer = self.call("delete", f"{AGENTS}/{self.own.id}/pause")
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertIsNone(answer.json()["pausedAt"])
        self.assertIsNone(answer.json()["pausedBy"])
        self.assertIsNotNone(answer.json()["nextRunAt"])
        agent = self.reload()
        self.assertEqual(agent.pause_reason, "")
        self.assertIsNotNone(agent.next_run_at)
        assert agent.next_run_at is not None
        self.assertGreater(agent.next_run_at, timezone.now())
        resumed = self.audit("agents.tenant_agent_resumed")
        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed[0].actor_id, self.admin.id)
        self.assertEqual(resumed[0].tenant_id, self.bank.id)

    def test_resuming_an_agent_that_is_not_paused_records_nothing(self) -> None:
        answer = self.call("delete", f"{AGENTS}/{self.own.id}/pause")
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(self.audit("agents.tenant_agent_resumed"), [])

    def test_another_bank_reaches_neither(self) -> None:
        for method, body in (("post", {}), ("delete", None)):
            with self.subTest(method):
                answer = self.call(
                    method,
                    f"{AGENTS}/{self.own.id}/pause",
                    body,
                    bank=self.other,
                    admin=self.other_admin,
                )
                self.assertEqual(answer.status_code, 404, answer.content)
        self.assertIsNone(self.reload().paused_at)


class StoppingARun(ControlCase):
    def interrupt(self, run_id: Any, *, bank: Any = None, admin: Any = None) -> Any:
        return self.call("post", f"{RUNS}/{run_id}/interrupt", {}, bank=bank, admin=admin)

    def test_an_open_run_is_stopped_through_the_runner_with_when_and_by_whom(self) -> None:
        run_id = self.run_now().json()["id"]
        runner = Interrupting()
        with with_interrupts(runner):
            answer = self.interrupt(run_id)
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(answer.json()["status"], "interrupted")
        self.assertIsNotNone(answer.json()["interruptedAt"])
        self.assertEqual([handle.run_id for handle in runner.stopped], [uuid.UUID(run_id)])
        self.assertEqual(runner.stopped[0].external_id, f"mock-{run_id}")
        run = self.stored(run_id)
        self.assertEqual(run.interrupted_by_id, self.admin.id)
        self.assertEqual(run.finished_at, run.interrupted_at)
        stopped = self.audit("agent_run.interrupted")
        self.assertEqual([row.subject_id for row in stopped], [run.id])
        self.assertEqual(stopped[0].actor_id, self.admin.id)

    def test_a_finished_run_is_409_and_unchanged(self) -> None:
        run_id = self.run_now().json()["id"]
        self.activate(self.bank)
        AgentRun.objects.filter(pk=run_id).update(
            status=RunStatus.SUCCEEDED.value, finished_at=timezone.now()
        )
        tenancy.clear_tenant()
        runner = Interrupting()
        with with_interrupts(runner):
            answer = self.interrupt(run_id)
        self.assertEqual(answer.status_code, 409, answer.content)
        self.assertEqual(answer.json()["code"], "run_finished")
        self.assertEqual(runner.stopped, [])
        self.assertEqual(self.stored(run_id).status, RunStatus.SUCCEEDED.value)
        self.assertEqual(self.audit("agent_run.interrupted"), [])

    def test_another_banks_run_is_404_and_a_platform_run_403(self) -> None:
        run_id = self.run_now().json()["id"]
        answer = self.interrupt(run_id, bank=self.other, admin=self.other_admin)
        self.assertEqual(answer.status_code, 404, answer.content)
        self.assertEqual(self.stored(run_id).status, RunStatus.RUNNING.value)
        platform = agent_build.platform_run()
        answer = self.interrupt(platform.id)
        self.assertEqual(answer.status_code, 403, answer.content)
        tenancy.clear_tenant()
        self.assertEqual(AgentRun.objects.get(pk=platform.id).status, RunStatus.RUNNING.value)


class TheCapMidRun(ControlCase):
    """The cap's second point: a runner event whose cumulative cost passes the month's cap."""

    def setUp(self) -> None:
        super().setUp()
        self.activate(self.bank)
        TenantAgentBudget.objects.filter(tenant=self.bank).update(monthly_cap=Decimal("10.00"))
        tenancy.clear_tenant()
        self.run_id = uuid.UUID(self.run_now().json()["id"])

    def report(self, cost: str, status: RunStatus = RunStatus.RUNNING) -> AgentRun:
        self.activate(self.bank)
        try:
            return runner_events.apply_event(
                RunnerEvent(run_id=self.run_id, status=status, cost=Decimal(cost))
            )
        finally:
            tenancy.clear_tenant()

    def test_under_the_cap_the_run_goes_on(self) -> None:
        self.assertEqual(self.report("9.9900").status, RunStatus.RUNNING.value)
        self.assertEqual(
            self.report("10.0000").status,
            RunStatus.RUNNING.value,
            "reaching the cap is not passing it",
        )
        self.assertIsNone(self.reload().paused_at)

    def test_passing_the_cap_interrupts_the_run_and_pauses_the_agent(self) -> None:
        runner = Interrupting()
        with with_interrupts(runner):
            self.report("4.0000")
            run = self.report("10.0100")
        self.assertEqual(run.status, RunStatus.INTERRUPTED.value)
        self.assertEqual([handle.run_id for handle in runner.stopped], [self.run_id])
        stored = self.stored(self.run_id)
        self.assertEqual(stored.status, RunStatus.INTERRUPTED.value)
        self.assertEqual(stored.cost, Decimal("10.0100"), "what it spent is kept")
        self.assertIsNotNone(stored.interrupted_at)
        self.assertIsNone(stored.interrupted_by_id, "the cap stopped it, not a person")
        agent = self.reload()
        self.assertIsNotNone(agent.paused_at)
        self.assertIsNone(agent.paused_by_id)
        self.assertEqual(agent.pause_reason, "budget_cap")
        stopped = self.audit("agent_run.interrupted")
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0].after["reason"], "budget_cap")
        self.assertEqual(len(self.audit("agents.tenant_agent_paused")), 1)
        self.activate(self.bank)
        self.assertTrue(
            Notification.objects.filter(user=self.admin, subject_id=self.own.id).exists()
        )
        tenancy.clear_tenant()

    def test_earlier_runs_this_month_count_toward_the_cap(self) -> None:
        self.activate(self.bank)
        AgentRun.objects.create(
            agent=self.definition,
            tenant_agent=self.own,
            trigger="manual",
            requested_by=self.admin,
            model="claude-opus-5",
            pipeline_version="1",
            status=RunStatus.SUCCEEDED.value,
            finished_at=timezone.now(),
            cost=Decimal("6.0000"),
        )
        tenancy.clear_tenant()
        with with_interrupts(Interrupting()):
            self.assertEqual(self.report("4.0000").status, RunStatus.RUNNING.value)
            self.assertEqual(self.report("4.0100").status, RunStatus.INTERRUPTED.value)

    def test_a_finished_run_that_passes_the_cap_is_not_reopened(self) -> None:
        with with_interrupts(Interrupting()):
            run = self.report("12.0000", RunStatus.SUCCEEDED)
        self.assertEqual(run.status, RunStatus.SUCCEEDED.value)
        self.assertEqual(self.audit("agent_run.interrupted"), [])

    def test_a_platform_run_never_meets_a_banks_cap(self) -> None:
        platform = agent_build.platform_run()
        tenancy.clear_tenant()
        runner = Interrupting()
        with with_interrupts(runner):
            run = runner_events.apply_event(
                RunnerEvent(run_id=platform.id, status=RunStatus.RUNNING, cost=Decimal("999.0000"))
            )
        self.assertEqual(run.status, RunStatus.RUNNING.value)
        self.assertEqual(runner.stopped, [])
        self.assertIsNone(self.reload().paused_at)


class OpenerIsTheOnlyDoor(ControlCase):
    def test_run_now_opens_through_the_scheduler_of_record(self) -> None:
        with mock.patch.object(opener, "open_run", wraps=opener.open_run) as opened:
            self.run_now()
        self.assertEqual(opened.call_count, 1)
