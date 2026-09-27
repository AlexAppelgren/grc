"""The runner seam (AGT-06, c11-runner-and-definitions): a runner is an executor that
reports only `RunnerEvent`s, and one function applies each to its run through `record()`.

What is proved here: the mock is deterministic by run id and emits the events a test needs;
the Managed Agents runner still raises for the reason D-54 and ADR 0047 give; an event is
validated at the boundary, refused for a finished run, an unknown run or a run of another
zone than the one applying it, and leaves the row alone when refused; an applied event
writes its audit and outbox rows in the same transaction; the error text is stored and
never logged; and the boot refuses `AGENT_RUNNER=mock` on a deployed environment other than
test.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from decimal import Decimal
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.agents import runner_events
from apps.agents.models import (
    Agent,
    AgentKind,
    AgentRun,
    AgentScopeKind,
    AgentWritesTo,
    RunStatus,
    RunTrigger,
    TenantAgent,
)
from apps.shared import factories, tenancy
from apps.shared import tests_production_guard as boot_guard
from apps.shared.adapters import agent_runner
from apps.shared.adapters.agent_runner import MockAgentRunner, RunHandle, RunnerEvent
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.tenancy import library_write

# Text a runner might carry back from a page it fetched: stored on the run for the people
# who operate the agents, and never written to a log line or an audit row.
ERROR_TEXT = "fetch refused: Kundens interna riktlinje 7.2 citerad på sidan"


class TheSeam(SimpleTestCase):
    """What a runner may tell the app, and what the mock tells it."""

    def test_the_mock_starts_a_run_that_is_running_and_is_the_same_for_the_same_run(self) -> None:
        run_id = uuid.uuid4()
        handle = agent_runner.get_agent_runner().start(run_id=run_id, definition_key="watch-sweeper", definition_version=1)
        self.assertIsInstance(handle, RunHandle)
        self.assertIs(handle.status, RunStatus.RUNNING, "the app records the run; the runner only answers")
        self.assertEqual(handle.run_id, run_id)
        self.assertTrue(handle.external_id)
        self.assertEqual(handle, MockAgentRunner().start(run_id=run_id, definition_key="watch-sweeper", definition_version=1))

    def test_the_mock_reports_progress_then_success_with_no_findings_seeded_from_the_run_id(self) -> None:
        runner = MockAgentRunner()
        handle = runner.start(run_id=uuid.uuid4(), definition_key="watch-sweeper", definition_version=1)
        events = runner.poll(handle)
        self.assertEqual([event.status for event in events], [RunStatus.RUNNING, RunStatus.SUCCEEDED])
        self.assertTrue(all(event.run_id == handle.run_id for event in events))
        self.assertEqual(events[-1].stats, {}, "a mock run finds nothing")
        self.assertEqual(events[-1].error, "")
        self.assertGreater(events[-1].cost or 0, events[0].cost or 0)
        self.assertEqual(events, runner.poll(handle), "the same run id, the same events: no clock, no chance")
        other = runner.start(run_id=uuid.uuid4(), definition_key="watch-sweeper", definition_version=1)
        spent = [(event.cost, event.tokens_in, event.tokens_out) for event in (runner.poll(other)[-1], events[-1])]
        self.assertNotEqual(spent[0], spent[1], "another run id, other numbers")

    def test_an_interrupted_mock_run_reports_that_it_was_interrupted(self) -> None:
        runner = MockAgentRunner()
        handle = runner.interrupt(runner.start(run_id=uuid.uuid4(), definition_key="watch-sweeper", definition_version=1))
        self.assertIs(handle.status, RunStatus.INTERRUPTED)
        self.assertEqual([event.status for event in runner.poll(handle)], [RunStatus.INTERRUPTED])

    @override_settings(AGENT_RUNNER="managed_agents")
    def test_managed_agents_still_raises_because_the_boot_refuses_it_deployed(self) -> None:
        """Ruling 4: D-54 and ADR 0047 refuse `managed_agents` on every deployed environment
        but test, so it cannot be the first real runner. Reversing that is a decision, and
        this pin makes it a visible one."""
        runner = agent_runner.get_agent_runner()
        handle = RunHandle(run_id=uuid.uuid4(), external_id="x", status=RunStatus.RUNNING, started_at=None)
        for call in (
            lambda: runner.start(run_id=uuid.uuid4(), definition_key="watch-sweeper", definition_version=1),
            lambda: runner.poll(handle),
            lambda: runner.interrupt(handle),
        ):
            with self.assertRaises(NotImplementedError) as refused:
                call()
            self.assertIn("D-54", str(refused.exception))
            self.assertIn("ADR 0047", str(refused.exception))
        self.assertIn("D-54", agent_runner.ManagedAgentsRunner.__doc__ or "")


class RunnerEventCase(TestCase):
    """A platform run the worker opened and a bank's own run, both still running."""

    def setUp(self) -> None:
        with library_write("test"):
            platform = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)
            bank_kind = Agent.objects.create(
                key="tenant-source-watch",
                kind=AgentKind.WATCH.value,
                current_version=1,
                scope=AgentScopeKind.TENANT.value,
                tenant_configurable=True,
                writes_to=AgentWritesTo.TENANT.value,
            )
        self.platform_run = AgentRun.objects.create(
            agent=platform, model="m", pipeline_version="0.4", trigger=RunTrigger.SCHEDULE.value
        )
        self.tenant = factories.tenant(slug="runner-events-a")
        self.other_tenant = factories.tenant(slug="runner-events-b")
        tenancy.activate(self.tenant.id)
        tenant_agent = TenantAgent.objects.create(tenant=self.tenant, agent=bank_kind, enabled=True)
        self.tenant_run = AgentRun.objects.create(
            agent=bank_kind, tenant_agent=tenant_agent, model="m", pipeline_version="0.4", trigger=RunTrigger.SCHEDULE.value
        )
        tenancy.clear_tenant()

    def event(self, run: AgentRun, **fields: Any) -> RunnerEvent:  # compliance: allow-kwargs test helper overriding event fields
        base = RunnerEvent(
            run_id=run.id,
            status=RunStatus.RUNNING,
            stats={"modelCalls": 3, "fetches": 5},
            cost=Decimal("0.1250"),
            tokens_in=1200,
            tokens_out=300,
            error="",
        )
        return replace(base, **fields)

    def in_zone(self, tenant_id: uuid.UUID | None) -> None:
        if tenant_id is None:
            tenancy.clear_tenant()
        else:
            tenancy.activate(tenant_id)

    def refused(self, run: AgentRun, event: RunnerEvent, code: str, zone: uuid.UUID | None = None) -> None:
        """The event, applied from `zone`, is refused with `code`, and the run and its audit
        trail stay as they were, read from the run's own zone."""
        self.in_zone(run.tenant_id)
        before = AgentRun.objects.filter(pk=run.pk).values().get()
        audits = AuditEvent.objects.filter(subject_id=run.pk).count()
        self.in_zone(zone)
        with self.assertRaises(ValidationError) as refusal:
            runner_events.apply_event(event)
        self.assertEqual(refusal.exception.code, code, refusal.exception)
        self.in_zone(run.tenant_id)
        self.assertEqual(AgentRun.objects.filter(pk=run.pk).values().get(), before, "a refused event leaves the row alone")
        self.assertEqual(AuditEvent.objects.filter(subject_id=run.pk).count(), audits)


class ApplyingAnEvent(RunnerEventCase):
    def test_a_progress_event_updates_the_counters_and_cost_and_the_run_stays_open(self) -> None:
        applied = runner_events.apply_event(self.event(self.platform_run))
        run = AgentRun.objects.get(pk=self.platform_run.pk)
        self.assertEqual(applied.pk, run.pk)
        self.assertEqual(run.status, RunStatus.RUNNING.value)
        self.assertIsNone(run.finished_at)
        self.assertEqual((run.cost, run.tokens_in, run.tokens_out), (Decimal("0.1250"), 1200, 300))
        self.assertEqual((run.stats["modelCalls"], run.stats["fetches"]), (3, 5))

    def test_every_applied_event_leaves_an_audit_and_an_outbox_row_in_the_runs_zone(self) -> None:
        runner_events.apply_event(self.event(self.platform_run))
        self.in_zone(self.tenant.id)
        runner_events.apply_event(self.event(self.tenant_run, status=RunStatus.SUCCEEDED))
        for run, zone in ((self.platform_run, None), (self.tenant_run, self.tenant.id)):
            event = AuditEvent.objects.get(action="agent_run.runner_event", subject_id=run.id)
            self.assertEqual(event.tenant_id, zone)
            self.assertEqual(event.subject_type, "agent_run")
            self.assertEqual(event.after["status"], AgentRun.objects.get(pk=run.pk).status)
            self.assertTrue(OutboxEvent.objects.filter(topic="agent_run.runner_event", payload__subjectId=str(run.id)).exists())

    def test_the_run_and_its_audit_row_are_one_transaction(self) -> None:
        with mock.patch.object(runner_events, "record", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                runner_events.apply_event(self.event(self.platform_run, status=RunStatus.SUCCEEDED))
        run = AgentRun.objects.get(pk=self.platform_run.pk)
        self.assertEqual((run.status, run.cost), (RunStatus.RUNNING.value, None), "no audit row, no change")

    def test_a_terminal_event_closes_the_run_and_stores_its_error_without_logging_it(self) -> None:
        with self.assertNoLogs(level=logging.DEBUG):
            runner_events.apply_event(self.event(self.platform_run, status=RunStatus.FAILED, error=ERROR_TEXT))
        run = AgentRun.objects.get(pk=self.platform_run.pk)
        self.assertEqual(run.status, RunStatus.FAILED.value)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.error, ERROR_TEXT, "stored for the operators")
        audit = AuditEvent.objects.get(action="agent_run.runner_event", subject_id=run.id)
        outbox = OutboxEvent.objects.get(topic="agent_run.runner_event", payload__subjectId=str(run.id))
        for written in (audit.before, audit.after, audit.summary, outbox.payload):
            self.assertNotIn("riktlinje", str(written), "an error is text off a network: never in an audit or outbox row")

    def test_an_interrupted_event_says_so_and_when(self) -> None:
        runner_events.apply_event(self.event(self.platform_run, status=RunStatus.INTERRUPTED))
        run = AgentRun.objects.get(pk=self.platform_run.pk)
        self.assertEqual(run.status, RunStatus.INTERRUPTED.value)
        self.assertIsNotNone(run.interrupted_at)
        self.assertEqual(run.finished_at, run.interrupted_at)

    def test_the_mocks_events_run_a_run_to_success(self) -> None:
        runner = MockAgentRunner()
        handle = runner.start(run_id=self.platform_run.id, definition_key="watch-sweeper", definition_version=1)
        for event in runner.poll(handle):
            runner_events.apply_event(event)
        run = AgentRun.objects.get(pk=self.platform_run.pk)
        self.assertEqual((run.status, run.cost), (RunStatus.SUCCEEDED.value, runner.poll(handle)[-1].cost))
        self.assertEqual(AuditEvent.objects.filter(action="agent_run.runner_event", subject_id=run.id).count(), 2)


class RefusingAnEvent(RunnerEventCase):
    def test_an_event_for_a_finished_run_is_refused(self) -> None:
        runner_events.apply_event(self.event(self.platform_run, status=RunStatus.SUCCEEDED))
        for status in RunStatus:
            self.refused(self.platform_run, self.event(self.platform_run, status=status), "run_finished")

    def test_an_event_is_applied_only_in_its_runs_own_zone(self) -> None:
        """The zone is the run's, never the event's: the worker applying it must stand in the
        run's zone. A bank's run is invisible from any other zone under row-level security,
        so it answers as a run that does not exist; a platform run every bank can read is
        found from a bank's zone and refused, so a bank's worker cannot move it."""
        self.refused(self.tenant_run, self.event(self.tenant_run), "not_found", zone=None)
        self.refused(self.tenant_run, self.event(self.tenant_run), "not_found", zone=self.other_tenant.id)
        self.refused(self.platform_run, self.event(self.platform_run), "wrong_zone", zone=self.tenant.id)

    def test_an_event_for_a_run_that_does_not_exist_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as refusal:
            runner_events.apply_event(replace(self.event(self.platform_run), run_id=uuid.uuid4()))
        self.assertEqual(refusal.exception.code, "not_found")

    def test_an_event_that_is_not_what_a_runner_may_say_is_refused(self) -> None:
        """A runner is our executor, and still validated at the boundary: what it reports came
        from a model and a network."""
        runner_events.apply_event(self.event(self.platform_run))
        run = self.platform_run
        for event, why in (
            (self.event(run, status="completed"), "a status that is not a RunStatus"),
            (self.event(run, cost=Decimal("-0.01")), "a negative cost"),
            (self.event(run, cost=Decimal("0.00001")), "a cost finer than the column keeps"),
            (self.event(run, cost=Decimal("1000000")), "a cost the column cannot hold"),
            (self.event(run, cost=Decimal("NaN")), "a cost that is not a number"),
            (self.event(run, cost=Decimal("0.1000")), "a cost that went backwards"),
            (self.event(run, tokens_in=-1), "negative tokens"),
            (self.event(run, tokens_out=299), "tokens that went backwards"),
            (self.event(run, tokens_in=2**63), "tokens the column cannot hold"),
            (self.event(run, stats={"outOfScope": -1}), "a counter that cannot be a count"),
            (self.event(run, stats={"secret": 1}), "a counter the run does not keep"),
            (self.event(run, error="x" * 2001), "an error longer than a run's error may be"),
        ):
            with self.subTest(why):
                self.refused(run, event, "invalid_runner_event")


class TheBootRefusesTheMockRunnerDeployed(boot_guard.ProductionGuard):
    """AGT-S8's last line, for this setting on its own: the adapter adds no guard, and
    `MOCK_ADAPTER_SETTINGS` already refuses `AGENT_RUNNER=mock` outside the named test
    environment. Runs the production guard's own boot harness on these cases alone."""

    def cases(self) -> list[boot_guard.Case]:
        return [
            boot_guard.Case(
                "prod refuses the mock runner",
                self._good_deployed("prod", AGENT_RUNNER="mock"),
                False,
                "AGENT_RUNNER",
                "rule 5",
            ),
            boot_guard.Case(
                "staging refuses the mock runner",
                self._good_deployed("staging", AGENT_RUNNER="mock"),
                False,
                "AGENT_RUNNER",
                "rule 5",
            ),
            boot_guard.Case("deployed test runs the mock runner", self._good_deployed("test", AGENT_RUNNER="mock"), True),
        ]
