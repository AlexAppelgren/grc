"""Chunk 11's security review (docs/reviews/CHUNK11_REVIEW.md), the findings in the agents
app, each written before its fix:

- F1: the cap before a run counts what the bank's open runs may still spend, so a run now
  after a run now cannot open more than the cap holds.
- F2: a research request is stopped where run now is: a paused or switched-off agent, and a
  run whose budget would not fit under the cap, under the same lock as run now.
- F3: a check_url request is refused before anything is fetched when the month's requests,
  the AI switch or the cap already stop it.
- F4: a fetch has one deadline across every read and redirect, so a page that answers a byte
  at a time cannot hold a request thread.
- F5: the cap's second point reads the month's spend under the same lock as the first.
- F6: a runner event for a bank that switched its AI off stops the run.
- F7: a change to a bank's agent locks the row, so it never writes back a pause it did not see.
- F8: the person who asked for a re-tag never approves the batch its run filed (four eyes).
- F9: a person never files a proposal under an agent's run.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.agents import requests, runner_events, tasks, tenant_agents
from apps.agents.models import AgentRun, RunStatus, RunTrigger, TenantAgent, TenantAgentBudget
from apps.agents.tests_control import ControlCase, Interrupting, with_interrupts
from apps.agents.tests_requests import JSON, PAGE, TOPIC, RequestCase, RetagCase
from apps.agents.tests_tasks import WEDNESDAY, BankBeatCase, Recorded, frozen, with_runner
from apps.shared import factories, tenancy
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.proposals import logic as proposals
from apps.proposals.logic import Proposer
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared.audit import Actor, ActorType
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.testing import sign_in


class TheCapCountsOpenRuns(BankBeatCase):
    """F1. The cap is 100 and a run may spend up to `AGENT_RUN_BUDGET_LIMIT` (5)."""

    def open_run(self, cost: str | None = None, status: RunStatus = RunStatus.RUNNING) -> None:
        tenancy.activate(self.bank.id)
        with frozen(WEDNESDAY - datetime.timedelta(hours=2)):
            AgentRun.objects.create(
                agent=self.definition,
                tenant_agent=self.agent,
                trigger=RunTrigger.MANUAL.value,
                model="m",
                pipeline_version="1",
                status=status.value,
                budget_limit=Decimal("5.00"),
                cost=None if cost is None else Decimal(cost),
            )
        tenancy.clear_tenant()

    def run_now(self) -> AgentRun | None:
        self.activate(self.bank)
        try:
            with frozen(WEDNESDAY), with_runner(Recorded()):
                return tasks.open_tenant_run(TenantAgent.objects.get(pk=self.agent.pk), trigger=RunTrigger.MANUAL, requested_by=self.admin)
        finally:
            tenancy.clear_tenant()

    def test_an_open_run_with_no_cost_yet_holds_its_whole_limit(self) -> None:
        self.open_run(cost="91.00", status=RunStatus.SUCCEEDED)
        self.open_run()  # 91 spent + 5 held + 5 asked > 100
        with self.assertRaises(ValidationError) as refused:
            self.run_now()
        self.assertEqual(refused.exception.code, "budget_cap_reached")

    def test_runs_opened_one_after_another_stop_at_the_cap(self) -> None:
        opened = 0
        for _ in range(25):
            try:
                self.run_now()
            except ValidationError:
                break
            opened += 1
        self.assertEqual(opened, 20, "100 of cap holds twenty runs of 5 and no more")

    def test_an_open_run_that_spent_more_than_its_limit_holds_what_it_spent(self) -> None:
        self.open_run(cost="96.00")  # 96 held, more than its limit, + 5 asked > 100
        with self.assertRaises(ValidationError):
            self.run_now()

    def test_a_finished_run_holds_only_what_it_cost(self) -> None:
        self.open_run(cost="1.00", status=RunStatus.SUCCEEDED)
        self.open_run(cost=None, status=RunStatus.FAILED)
        self.open_run(cost="89.00", status=RunStatus.INTERRUPTED)  # 90 spent + 5 asked = 100
        self.assertIsNotNone(self.run_now())


class ARequestStopsWhereRunNowStops(RequestCase):
    """F2 and F3."""

    def set_agent(self, **fields: Any) -> None:  # compliance: allow-kwargs test helper setting the agent's columns
        tenancy.activate(self.bank.id)
        TenantAgent.objects.filter(pk=self.agent.pk).update(**fields)
        tenancy.clear_tenant()

    def spent(self, amount: str) -> None:
        tenancy.activate(self.bank.id)
        AgentRun.objects.create(
            agent=self.definition,
            tenant_agent=self.agent,
            trigger=RunTrigger.SCHEDULE.value,
            model="m",
            pipeline_version="1",
            status=RunStatus.SUCCEEDED.value,
            cost=Decimal(amount),
        )
        tenancy.clear_tenant()

    def test_a_paused_or_switched_off_agent_takes_no_request(self) -> None:
        self.set_agent(paused_at=datetime.datetime.now(datetime.UTC), pause_reason="budget_cap")
        self.refused(self.ask({"kind": "research_topic", "topic": TOPIC}), 409, "agent_paused")
        self.set_agent(paused_at=None, pause_reason="", enabled=False)
        self.refused(self.ask({"kind": "run_now"}), 409, "agent_disabled")
        self.assertEqual((self.requests_of(self.bank), self.runs_of(self.bank)), ([], []))

    def test_a_run_whose_budget_would_not_fit_under_the_cap_is_refused(self) -> None:
        self.spent("96.00")  # 96 + 5 > 100, although 96 has not reached the cap
        self.refused(self.ask({"kind": "research_topic", "topic": TOPIC}), 422, "budget_cap_reached")
        self.assertEqual(self.requests_of(self.bank), [])

    def test_a_request_holds_the_same_spend_lock_as_run_now(self) -> None:
        with mock.patch.object(tasks, "lock_tenant", wraps=tasks.lock_tenant) as locked:
            self.assertEqual(self.ask({"kind": "run_now"}).status_code, 202)
        self.assertIn("agent_spend", [call.args[1] for call in locked.call_args_list])

    def test_check_url_fetches_nothing_when_the_request_would_be_refused(self) -> None:
        with override_settings(RESEARCH_REQUESTS_PER_MONTH=0):
            self.refused(self.ask({"kind": "check_url", "url": PAGE}), 429, "plan_limit_reached")
        Tenant.objects.filter(pk=self.bank.pk).update(ai_enabled=False)
        self.refused(self.ask({"kind": "check_url", "url": PAGE}), 422, "feature_off")
        Tenant.objects.filter(pk=self.bank.pk).update(ai_enabled=True)
        tenancy.activate(self.bank.id)
        TenantAgentBudget.objects.filter(tenant=self.bank).update(monthly_cap="1.00")
        tenancy.clear_tenant()
        self.refused(self.ask({"kind": "check_url", "url": PAGE}), 422, "budget_cap_reached")
        self.set_agent(enabled=False)
        self.refused(self.ask({"kind": "check_url", "url": PAGE}), 409, "agent_disabled")
        self.get.assert_not_called()
        self.resolve.assert_not_called()


class Dripping:
    """A response that answers one byte per read and one second of the clock per byte."""

    def __init__(self, clock: list[float]) -> None:
        self.clock = clock

    def read1(self, amount: int) -> bytes:
        self.clock[0] += 1.0
        return b"x"


class OneDeadlinePerFetch(RequestCase):
    """F4, and two small refusals at the same boundary."""

    @override_settings(RESEARCH_URL_TOTAL_SECONDS=10, RESEARCH_URL_MAX_BYTES=1000)
    def test_a_page_that_drips_is_cut_off_at_the_deadline(self) -> None:
        clock = [0.0]
        with mock.patch.object(requests.time, "monotonic", side_effect=lambda: clock[0]):
            deadline = requests.time.monotonic() + 10
            with self.assertRaises(requests.Unreachable):
                requests._read_body(Dripping(clock), deadline=deadline)
        self.assertLessEqual(clock[0], 11.0, "stopped at the deadline, not after a thousand seconds")

    @override_settings(RESEARCH_URL_MAX_BYTES=5)
    def test_a_body_is_read_up_to_the_cap_and_no_further(self) -> None:
        clock = [0.0]
        with mock.patch.object(requests.time, "monotonic", side_effect=lambda: clock[0]):
            self.assertEqual(requests._read_body(Dripping(clock), deadline=100.0), b"xxxxx")

    def test_every_hop_shares_the_one_deadline(self) -> None:
        self.get.side_effect = [
            requests.Fetched(status=302, location="/a", body=b"", charset="utf-8"),
            requests.Fetched(status=200, location="", body=b"ok", charset="utf-8"),
        ]
        self.assertEqual(self.ask({"kind": "check_url", "url": PAGE}).status_code, 202)
        deadlines = {call.kwargs["deadline"] for call in self.get.call_args_list}
        self.assertEqual(len(deadlines), 1)

    def test_a_malformed_address_is_refused_not_an_error(self) -> None:
        for url in ("https://[x]/", "https://[::1/"):
            with self.subTest(url=url):
                self.refused(self.ask({"kind": "check_url", "url": url}), 422, "url_not_allowed")
        self.get.side_effect = [requests.Fetched(status=302, location="https://[x]/", body=b"", charset="utf-8")]
        self.refused(self.ask({"kind": "check_url", "url": PAGE}), 422, "url_not_allowed")

    def test_an_ipv4_address_wrapped_in_ipv6_is_judged_as_the_ipv4_address(self) -> None:
        for address in ("64:ff9b::a9fe:a9fe", "64:ff9b::7f00:1", "::7f00:1", "::a00:1"):
            with self.subTest(address=address):
                self.assertFalse(requests._public(address))
        self.assertTrue(requests._public("64:ff9b::5db8:d822"), "NAT64 of a public address stays public")


class TheSecondPointOfTheCap(ControlCase):
    """F5 and F6."""

    def setUp(self) -> None:
        super().setUp()
        self.run_id = uuid.UUID(self.run_now().json()["id"])

    def report(self, cost: str) -> AgentRun:
        self.activate(self.bank)
        try:
            return runner_events.apply_event(RunnerEvent(run_id=self.run_id, status=RunStatus.RUNNING, cost=Decimal(cost)))
        finally:
            tenancy.clear_tenant()

    def test_the_spend_is_read_under_the_banks_spend_lock(self) -> None:
        order: list[str] = []
        real_lock, real_spend = runner_events.lock_tenant, runner_events.budget.spend

        def lock(tenant: Tenant, purpose: str) -> None:
            order.append(f"lock:{purpose}")
            real_lock(tenant, purpose)

        def spend(tenant: Tenant) -> Decimal:
            order.append("spend")
            return real_spend(tenant)

        with mock.patch.object(runner_events, "lock_tenant", side_effect=lock), mock.patch.object(runner_events.budget, "spend", side_effect=spend):
            self.report("1.0000")
        self.assertEqual(order[:2], ["lock:agent_spend", "spend"])

    def test_an_event_after_the_bank_switched_ai_off_stops_the_run(self) -> None:
        Tenant.objects.filter(pk=self.bank.pk).update(ai_enabled=False)
        runner = Interrupting()
        with with_interrupts(runner):
            run = self.report("1.0000")
        self.assertEqual(run.status, RunStatus.INTERRUPTED.value)
        self.assertEqual([handle.run_id for handle in runner.stopped], [self.run_id])
        [stopped] = self.audit("agent_run.interrupted")
        self.assertEqual(stopped.after["reason"], "feature_off")
        self.assertIsNone(self.reload().paused_at, "the switch stops the run; it pauses nothing")


class AChangeLocksTheAgent(ControlCase):
    """F7: the PATCH reads the agent with FOR UPDATE, so a pause committed meanwhile is
    waited for and kept rather than overwritten."""

    def test_the_patch_reads_the_row_for_update(self) -> None:
        with CaptureQueriesContext(connection) as queries:
            answer = self.call("patch", f"/api/v1/agents/{self.own.id}", {"cadence": "monthly"})
        self.assertEqual(answer.status_code, 200, answer.content)
        reads = [query["sql"] for query in queries.captured_queries if 'FROM "tenant_agent"' in query["sql"] and query["sql"].startswith("SELECT")]
        self.assertTrue(reads and "FOR UPDATE" in reads[0], reads[:1])

    def test_own_agent_locks_only_when_asked(self) -> None:
        self.activate(self.bank)
        with CaptureQueriesContext(connection) as queries:
            tenant_agents.own_agent(self.own.id)
            tenant_agents.own_agent(self.own.id, lock=True)
        tenancy.clear_tenant()
        sql = [query["sql"] for query in queries.captured_queries if 'FROM "tenant_agent"' in query["sql"]]
        self.assertEqual(["FOR UPDATE" in statement for statement in sql], [False, True])


class TheRequesterIsNotTheSecondPerson(RetagCase):
    """F8 and F9: the editor who asked for the re-tag, and the run it opened."""

    def setUp(self) -> None:
        super().setUp()
        self.retag_run = AgentRun.objects.get(research_request_id=self.retag()["id"])

    def decide(self, person: Any) -> Any:
        proposal = requests.file_retag(run_id=self.retag_run.id, payload=self.payload(), source_label="Finansinspektionen", source_url=PAGE)
        answer = self.client.post(
            f"/api/v1/proposal-batches/{proposal.id}/decide", data={"rest": "approved"}, content_type=JSON, **sign_in(person, step_up=True)
        )
        tenancy.clear_tenant()
        return answer

    def test_the_requester_cannot_approve_the_batch_their_request_produced(self) -> None:
        self.refused(self.decide(self.editor), 409, "four_eyes_violation")
        self.assertEqual(Proposal.objects.get(is_batch=True).status, ProposalStatus.OPEN.value)

    def test_another_editor_can(self) -> None:
        second = factories.platform_user(roles=("library_editor",), email="second-editor@bleqq.test")
        self.assertEqual(self.decide(second).status_code, 200)

    def test_a_person_naming_an_agents_run_files_nothing(self) -> None:
        answer = self.client.post(
            "/api/v1/proposal-batches",
            data={
                "kind": "obligation_scope",
                "title": "Re-tag custody",
                "agentRunId": str(self.retag_run.id),
                "payload": self.payload().model_dump(mode="json", by_alias=True),
                "sourceUrl": PAGE,
            },
            content_type=JSON,
            **sign_in(self.editor),
        )
        tenancy.clear_tenant()
        self.refused(answer, 404, "not_found")
        self.assertFalse(Proposal.objects.filter(agent_run_id=self.retag_run.id).exists())

    def test_the_single_proposal_door_refuses_it_too(self) -> None:
        person = Proposer(actor=Actor(kind=ActorType.USER, id=self.editor.id, label=self.editor.name), user=self.editor)
        with self.assertRaises(ProblemError) as refused:
            proposals.create(kind="new_obligation", title="x", payload={}, proposer=person, agent_run_id=self.retag_run.id)
        self.assertEqual((refused.exception.status, refused.exception.code), (404, "not_found"))

