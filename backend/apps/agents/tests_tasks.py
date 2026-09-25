"""The scheduler of record (AGT-03, AGT-04, AGT-06, D-61, ADR 0053): one opener that records a
run before the runner is asked, bleqq's beat in no tenant's zone, and a bank's beat that
starts its own due agents inside `@tenant_task` and checks the cap first.

Written before `tasks.py` existed.
"""

from __future__ import annotations

import ast
import datetime
import inspect
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from apps.agents import scope as run_scope
from apps.agents import opener, tasks
from apps.agents import testing as agent_build
from apps.agents.models import (
    Agent,
    AgentCadence,
    AgentRun,
    AgentVersion,
    RunStatus,
    RunTrigger,
    TenantAgent,
    TenantAgentBudget,
)
from apps.agents.tests_tenant_agents import TenantAgentCase
from apps.collab.models import Notification, NotificationKind
from apps.library.models import Jurisdiction
from apps.shared import factories, tenancy
from apps.shared.adapters.agent_runner import MockAgentRunner, RunHandle
from apps.shared.models import AuditEvent, Tenant
from apps.shared.tenancy import is_tenant_task, library_write

TASKS = Path(tasks.__file__)
OPENER = Path(opener.__file__)
# A Wednesday noon, UTC, well inside a week, a month and a day, so the clock is the test's.
WEDNESDAY = datetime.datetime(2026, 10, 14, 12, 0, tzinfo=datetime.UTC)


def published(agent: Agent, version_no: int = 1, model: str = "claude-opus-5") -> AgentVersion:
    """A published version of `agent`, which a run pins."""
    with library_write("test"):
        return AgentVersion.objects.create(agent=agent, version_number=version_no, model=model, prompt_path="prompt.md")


def frozen(at: datetime.datetime) -> Any:
    return mock.patch("django.utils.timezone.now", return_value=at)


class Recorded(MockAgentRunner):
    """The mock runner, noting at each start whether the run row already existed and which
    zone the database was in, then answering as the mock does."""

    def __init__(self, fail: bool = False) -> None:
        self.seen: list[tuple[bool, uuid.UUID | None]] = []
        self.fail = fail

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        self.seen.append((AgentRun.objects.filter(pk=run_id).exists(), tenancy.database_tenant_id()))
        if self.fail:
            raise RuntimeError("runner unreachable")
        return super().start(run_id=run_id, definition_key=definition_key, definition_version=definition_version)


def with_runner(runner: Recorded) -> Any:
    return mock.patch.object(opener, "get_agent_runner", return_value=runner)


def platform_runs() -> list[AgentRun]:
    tenancy.clear_tenant()
    return list(AgentRun.objects.filter(tenant__isnull=True).order_by("started_at", "id"))


class PlatformBeatCase(TenantAgentCase):
    """bleqq's watch-sweeper with a published version, and a bank that switched everything
    off: its AI, a zero cap and its own agent paused."""

    def setUp(self) -> None:
        super().setUp()
        self.version = published(self.bleqq)
        tenancy.activate(self.bank.id)
        Tenant.objects.filter(pk=self.bank.id).update(ai_enabled=False)
        TenantAgentBudget.objects.create(tenant=self.bank, monthly_cap="0.00")
        TenantAgent.objects.create(tenant=self.bank, agent=self.definition, enabled=True, paused_at=timezone.now())
        tenancy.clear_tenant()

    def beat(self, at: datetime.datetime = WEDNESDAY, runner: Recorded | None = None) -> Recorded:
        runner = runner or Recorded()
        with frozen(at), with_runner(runner):
            tasks.run_platform_agents()
        return runner


class BleqqsBeat(PlatformBeatCase):
    def test_a_due_agent_gets_one_run_with_no_tenant_the_schedule_trigger_and_its_version(self) -> None:
        runner = self.beat()
        [run] = platform_runs()
        self.assertEqual((run.agent_id, run.tenant_id, run.api_key_id), (self.bleqq.id, None, None))
        self.assertEqual(run.trigger, RunTrigger.SCHEDULE.value)
        self.assertEqual(run.agent_version_id, self.version.id)
        self.assertEqual(run.model, self.version.model)
        self.assertEqual(run.status, RunStatus.RUNNING.value)
        self.assertIsNone(run.budget_limit, "bleqq's run spends bleqq's budget, never a bank's cap")
        self.assertTrue(run.external_session_id)
        self.assertEqual(runner.seen, [(True, None)], "recorded first, and in no tenant's zone")
        opened = AuditEvent.objects.get(action="agent_run.opened", subject_id=run.id)
        self.assertIsNone(opened.tenant_id)
        self.assertEqual(opened.after["trigger"], "schedule")

    def test_its_scope_is_every_covered_jurisdiction_and_no_bank_market(self) -> None:
        self.beat()
        [run] = platform_runs()
        covered = list(Jurisdiction.objects.filter(active=True).order_by("sort_order", "key").values_list("key", flat=True))
        self.assertEqual(run.scope, {"jurisdictions": covered})

    def test_its_scope_is_the_agents_own_when_it_names_one(self) -> None:
        with library_write("test"):
            Agent.objects.filter(pk=self.bleqq.pk).update(platform_scope={"jurisdictions": ["se", "fi"]})
        self.beat()
        self.assertEqual(platform_runs()[0].scope, {"jurisdictions": ["se", "fi"]})

    def test_a_second_beat_inside_the_cadence_starts_nothing_and_the_next_period_starts_one(self) -> None:
        self.beat(WEDNESDAY)
        self.beat(WEDNESDAY + datetime.timedelta(hours=1))
        self.beat(WEDNESDAY + datetime.timedelta(days=4, hours=11))  # Sunday, 23:00 UTC
        self.assertEqual(len(platform_runs()), 1)
        self.beat(WEDNESDAY + datetime.timedelta(days=5))  # Monday: a new week
        self.assertEqual(len(platform_runs()), 2)

    def test_a_manual_an_inactive_or_a_banks_kind_of_definition_is_never_scheduled(self) -> None:
        manual = agent_build.agent(key="manual-sweeper")
        idle = agent_build.agent(key="idle-sweeper")
        with library_write("test"):
            Agent.objects.filter(pk=manual.pk).update(default_cadence=AgentCadence.MANUAL.value)
            Agent.objects.filter(pk=idle.pk).update(active=False)
            Agent.objects.filter(pk=self.definition.pk).update(active=True, default_cadence=AgentCadence.DAILY.value)
        self.beat()
        self.assertEqual([run.agent_id for run in platform_runs()], [self.bleqq.id])
        self.activate(self.bank)
        self.assertFalse(AgentRun.objects.filter(agent=self.definition).exists())

    @override_settings(AGENT_RUNS_PER_BEAT=2)
    def test_one_beat_starts_at_most_agent_runs_per_beat_and_the_next_beat_the_rest(self) -> None:
        for key in ("sweeper-b", "sweeper-c"):
            published(agent_build.agent(key=key))
        self.beat()
        self.assertEqual(len(platform_runs()), 2)
        self.beat(WEDNESDAY + datetime.timedelta(minutes=15))
        self.assertEqual(len({run.agent_id for run in platform_runs()}), 3)

    def test_a_bank_with_ai_off_a_zero_cap_and_its_agent_paused_does_not_stop_it(self) -> None:
        self.beat()
        self.assertEqual(len(platform_runs()), 1)
        self.activate(self.bank)
        self.assertFalse(AuditEvent.objects.filter(action="agent_run.skipped").exists())

    def test_a_failing_runner_leaves_the_run_recorded_and_failed(self) -> None:
        runner = self.beat(runner=Recorded(fail=True))
        [run] = platform_runs()
        self.assertEqual(runner.seen, [(True, None)])
        self.assertEqual(run.status, RunStatus.FAILED.value)
        self.assertEqual(run.error, opener.START_FAILED)
        self.assertIsNotNone(run.finished_at)
        self.assertTrue(AuditEvent.objects.filter(action="agent_run.start_failed", subject_id=run.id).exists())
        self.beat(WEDNESDAY + datetime.timedelta(hours=1))
        self.assertEqual(len(platform_runs()), 1, "a failed start still took this period's slot")

    def test_an_agent_whose_every_version_is_retired_is_skipped_with_an_audit_row(self) -> None:
        with library_write("test"):
            AgentVersion.objects.filter(pk=self.version.pk).update(retired_at=timezone.now())
        self.beat()
        self.assertEqual(platform_runs(), [])
        skipped = AuditEvent.objects.get(action="agent_run.skipped")
        self.assertEqual((skipped.tenant_id, skipped.after["reason"]), (None, "no_published_version"))


class TheBeatOfBleqqsAgentsStaysOutOfEveryBank(PlatformBeatCase):
    """The structural form of "a platform run reads no tenant row" (D-32)."""

    def test_the_platform_task_is_not_a_tenant_task_and_takes_no_tenant(self) -> None:
        self.assertFalse(is_tenant_task(tasks.run_platform_agents.run))
        self.assertEqual(list(inspect.signature(tasks.run_platform_agents.run).parameters), [])

    def test_it_activates_no_tenant_and_never_reaches_scope_py(self) -> None:
        refuse = mock.Mock(side_effect=AssertionError("a platform run reached a bank's zone"))
        with (
            mock.patch.object(tenancy, "activate", refuse),
            mock.patch.object(run_scope, "snapshot", refuse),
            mock.patch.object(run_scope, "for_run", refuse),
        ):
            runner = self.beat()
        self.assertEqual(runner.seen, [(True, None)])
        refuse.assert_not_called()

    def test_no_function_on_the_platform_path_names_scope_py_or_a_tenant_setting(self) -> None:
        """A guard over the source: the functions bleqq's beat calls never name the bank's
        scope module, the AI switch, the cap or the pause."""
        tree = ast.parse(TASKS.read_text())
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        platform_path = ("run_platform_agents", "open_platform_run", "_pinned", "_covered", "_due_platform_agents", "_claim", "_period_start")
        banned = {"run_scope", "ai", "budget", "pause", "ensure_enabled", "open_tenant_run"}
        for name in platform_path:
            used = {node.id for node in ast.walk(functions[name]) if isinstance(node, ast.Name)}
            self.assertEqual(used & banned, set(), f"{name} names a bank's setting or scope")
        # The opener is shared, and reaches scope.py only for a run of a bank's own agent.
        opener_functions = {node.name: node for node in ast.walk(ast.parse(OPENER.read_text())) if isinstance(node, ast.FunctionDef)}
        for name in ("_hand_over", "schedule_of"):
            used = {node.id for node in ast.walk(opener_functions[name]) if isinstance(node, ast.Name)}
            self.assertEqual(used & banned, set(), f"{name} names a bank's setting or scope")
        [branch] = [
            node for node in ast.walk(opener_functions["open_run"]) if isinstance(node, ast.If) and "run_scope" in ast.unparse(node)
        ]
        self.assertEqual(ast.unparse(branch.test), "tenant_agent is not None")
        self.assertEqual(sum("run_scope" in ast.unparse(node) for node in opener_functions["open_run"].body), 1)


class BankBeatCase(TenantAgentCase):
    """A bank with its own agent on, weekly, due an hour ago, a cap of 100 and a published
    version; its admin holds agents.manage and a reader does not."""

    def setUp(self) -> None:
        super().setUp()
        self.version = published(self.definition, model="claude-sonnet-5")
        self.reader = factories.member_user(self.bank, roles=("reader",))
        self.set_cap()
        self.set_cap(self.other)
        self.agent = self.own(self.bank)

    def own(self, bank: Any, **fields: Any) -> TenantAgent:  # compliance: allow-kwargs test helper overriding the agent's columns
        tenancy.activate(bank.id)
        agent = TenantAgent.objects.create(
            tenant=bank,
            agent=self.definition,
            enabled=True,
            cadence=AgentCadence.WEEKLY.value,
            run_weekday=3,
            run_hour=6,
            next_run_at=WEDNESDAY - datetime.timedelta(hours=1),
            **fields,
        )
        tenancy.clear_tenant()
        return agent

    def beat(self, bank: Any = None, at: datetime.datetime = WEDNESDAY, runner: Recorded | None = None) -> Recorded:
        runner = runner or Recorded()
        with frozen(at), with_runner(runner):
            tasks.run_due_tenant_agents((bank or self.bank).id)
        tenancy.clear_tenant()
        return runner

    def runs(self, bank: Any = None) -> list[AgentRun]:
        self.activate(bank or self.bank)
        found = list(AgentRun.objects.filter(tenant_agent__isnull=False).order_by("started_at", "id"))
        tenancy.clear_tenant()
        return found

    def fresh(self, agent: TenantAgent) -> TenantAgent:
        self.activate(agent.tenant)
        row = TenantAgent.objects.get(pk=agent.pk)
        tenancy.clear_tenant()
        return row


class ABanksBeat(BankBeatCase):
    def test_the_bank_task_is_a_wrapped_tenant_task_taking_the_tenant_first(self) -> None:
        self.assertTrue(is_tenant_task(tasks.run_due_tenant_agents.run))
        self.assertEqual(list(inspect.signature(tasks.run_due_tenant_agents.run).parameters)[0], "tenant_id")

    def test_a_due_agent_gets_one_run_recorded_before_the_runner_in_the_banks_zone(self) -> None:
        runner = self.beat()
        [run] = self.runs()
        self.assertEqual(runner.seen, [(True, self.bank.id)])
        self.assertEqual((run.tenant_id, run.tenant_agent_id, run.api_key_id), (self.bank.id, self.agent.id, None))
        self.assertEqual(run.trigger, RunTrigger.SCHEDULE.value)
        self.assertEqual((run.agent_version_id, run.model), (self.version.id, "claude-sonnet-5"))
        self.assertEqual(run.budget_limit, Decimal("5.00"))
        self.assertEqual(run.scope["source"], "markets", "the scope is snapshot from scope.py at start")
        self.activate(self.bank)
        opened = AuditEvent.objects.get(action="agent_run.opened", subject_id=run.id)
        self.assertEqual(opened.tenant_id, self.bank.id)
        self.assertEqual(opened.after["budgetLimit"], "5.00")

    def test_it_moves_next_run_at_to_the_next_slot_so_a_second_beat_starts_nothing(self) -> None:
        self.beat()
        moved = self.fresh(self.agent).next_run_at
        self.assertIsNotNone(moved)
        assert moved is not None
        self.assertGreater(moved, WEDNESDAY)
        self.beat(at=WEDNESDAY + datetime.timedelta(minutes=15))
        self.assertEqual(len(self.runs()), 1)

    def test_an_agent_that_is_off_paused_or_not_yet_due_starts_nothing(self) -> None:
        tenancy.activate(self.bank.id)
        TenantAgent.objects.filter(pk=self.agent.pk).update(enabled=False)
        tenancy.clear_tenant()
        other_definitions = [self.own_definition(f"bank-kind-{n}") for n in range(2)]
        paused = self.own_with(other_definitions[0], paused_at=WEDNESDAY - datetime.timedelta(days=1))
        later = self.own_with(other_definitions[1], next_run_at=WEDNESDAY + datetime.timedelta(hours=1))
        self.beat()
        self.assertEqual(self.runs(), [])
        self.assertIsNotNone(self.fresh(paused).paused_at)
        self.assertEqual(self.fresh(later).next_run_at, WEDNESDAY + datetime.timedelta(hours=1))

    def own_definition(self, key: str) -> Agent:
        from apps.agents.tests_tenant_agents import tenant_definition

        definition = tenant_definition(key)
        published(definition)
        return definition

    def own_with(self, definition: Agent, **fields: Any) -> TenantAgent:  # compliance: allow-kwargs test helper overriding the agent's columns
        tenancy.activate(self.bank.id)
        values: dict[str, Any] = {"next_run_at": WEDNESDAY - datetime.timedelta(hours=1), **fields}
        agent = TenantAgent.objects.create(
            tenant=self.bank, agent=definition, enabled=True, cadence=AgentCadence.WEEKLY.value, run_weekday=3, run_hour=6, **values
        )
        tenancy.clear_tenant()
        return agent

    def test_one_banks_beat_never_starts_another_banks_agent(self) -> None:
        theirs = self.own(self.other)
        self.beat()
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(self.runs(self.other), [])
        self.assertEqual(self.fresh(theirs).next_run_at, WEDNESDAY - datetime.timedelta(hours=1))

    def test_a_failing_runner_leaves_the_run_recorded_and_failed(self) -> None:
        runner = self.beat(runner=Recorded(fail=True))
        [run] = self.runs()
        self.assertEqual(runner.seen, [(True, self.bank.id)])
        self.assertEqual((run.status, run.error), (RunStatus.FAILED.value, opener.START_FAILED))

    def test_the_dispatcher_hands_on_every_active_bank_and_activates_none(self) -> None:
        refuse = mock.Mock(side_effect=AssertionError("the dispatcher entered a bank's zone"))
        with mock.patch.object(tasks.run_due_tenant_agents, "delay") as delay, mock.patch.object(tenancy, "activate", refuse):
            tasks.schedule_tenant_agents()
        handed = {call.args[0] for call in delay.call_args_list}
        self.assertTrue({str(self.bank.id), str(self.other.id)} <= handed)
        refuse.assert_not_called()


class TheCapBeforeARun(BankBeatCase):
    """The month's spend plus the run's budget limit must fit under the cap (AGT-04)."""

    def spent(self, amount: str) -> None:
        tenancy.activate(self.bank.id)
        with frozen(WEDNESDAY - datetime.timedelta(days=1)):  # this month, on the beat's clock
            self.spent_run = AgentRun.objects.create(
                agent=self.definition,
                tenant_agent=self.agent,
                trigger=RunTrigger.MANUAL.value,
                model="m",
                pipeline_version="1",
                status=RunStatus.SUCCEEDED.value,
                cost=Decimal(amount),
            )
        tenancy.clear_tenant()

    def test_a_run_that_would_pass_the_cap_is_not_started_the_agent_is_paused_and_admins_notified(self) -> None:
        self.spent("96.00")  # 96 + 5 > 100
        runner = self.beat()
        self.assertEqual(runner.seen, [])
        self.assertEqual(len(self.runs()), 1, "only the run that spent")
        agent = self.fresh(self.agent)
        self.assertIsNotNone(agent.paused_at)
        self.assertEqual(agent.pause_reason, "budget_cap")
        self.assertIsNone(agent.next_run_at)
        self.activate(self.bank)
        [paused] = AuditEvent.objects.filter(action="agents.tenant_agent_paused")
        self.assertEqual((paused.tenant_id, paused.after["pauseReason"]), (self.bank.id, "budget_cap"))
        [told] = Notification.objects.all()
        self.assertEqual((told.user_id, told.kind), (self.admin.id, NotificationKind.ESCALATION.value))
        self.assertEqual((told.subject_type, told.subject_id), ("tenant_agent", self.agent.id))
        self.assertFalse(AuditEvent.objects.filter(action="agent_run.opened").exists())

    def test_a_run_that_fits_exactly_starts(self) -> None:
        self.spent("95.00")  # 95 + 5 = 100
        self.beat()
        self.assertEqual(len(self.runs()), 2)
        self.assertIsNone(self.fresh(self.agent).paused_at)

    def test_a_platform_run_never_counts_toward_the_banks_spend(self) -> None:
        with frozen(WEDNESDAY), with_runner(Recorded()):
            published(self.bleqq)
            tenancy.clear_tenant()
            platform = tasks.open_platform_run(self.bleqq)
        AgentRun.objects.filter(pk=platform.pk).update(cost=Decimal("1000.0000"))
        self.beat()
        self.assertEqual(len(self.runs()), 1)

    def test_run_now_over_the_cap_answers_budget_cap_reached_and_pauses_nothing(self) -> None:
        self.spent("99.00")
        self.activate(self.bank)
        with frozen(WEDNESDAY), with_runner(Recorded()), self.assertRaises(ValidationError) as refused:
            tasks.open_tenant_run(TenantAgent.objects.get(pk=self.agent.pk), trigger=RunTrigger.MANUAL, requested_by=self.admin)
        self.assertEqual(refused.exception.code, "budget_cap_reached")
        self.assertIsNone(TenantAgent.objects.get(pk=self.agent.pk).paused_at)
        self.assertEqual(Notification.objects.count(), 0)

    def test_run_now_under_the_cap_opens_a_manual_run_naming_the_person(self) -> None:
        self.activate(self.bank)
        with with_runner(Recorded()):
            run = tasks.open_tenant_run(TenantAgent.objects.get(pk=self.agent.pk), trigger=RunTrigger.MANUAL, requested_by=self.admin)
        assert run is not None
        self.assertEqual((run.trigger, run.requested_by_id), (RunTrigger.MANUAL.value, self.admin.id))
        opened = AuditEvent.objects.get(action="agent_run.opened", subject_id=run.id)
        self.assertEqual(opened.actor_id, self.admin.id)

