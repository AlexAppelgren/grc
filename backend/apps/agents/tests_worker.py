"""The in-worker agent runner (D-147, AGT-01, AGT-06, H80): a platform run driven turn by
turn by the app's own worker, its tools the agent API's operations called in-process on the
keyless run.

The model is scripted (`Scripted`): each test names the turns it answers with, so what is
proven is the runner, never a model. Proven: a run checks a source, registers a change and
files a proposal through the same doors the API uses, each naming the run and its agent;
every turn is logged with its cost and the run row carries the running totals; a refusal
goes back to the model and stores nothing; a run stopped from outside takes no further turn;
the turn limit, the monthly budget and a model that does not answer each close the run as
failed; only the tools the published version names are offered; the worker runner queues a
platform run on commit and refuses a bank's run, which the opener then closes.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest import mock

from django.db import transaction
from django.test import TestCase, override_settings

from apps.agents import opener, tasks, worker
from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, AgentVersion, RunStatus, RunTrigger
from apps.agents.tests_flow import OBLIGATION_SUMMARY, PAGE, SOURCE_NAME, world
from apps.governance.models import AiGeneration
from apps.proposals.models import Proposal
from apps.shared import tenancy
from apps.shared.adapters import agent_runner
from apps.shared.adapters.llm import LlmError, MockLlm, Turn
from apps.shared.tenancy import library_write
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange, SourceCheck

SWEEPER_TOOLS = ["fetch", "startAgentRun", "listSources", "recordSourceCheck", "findSimilar", "createChange", "createProposal", "finishAgentRun"]


def _uses(*calls: tuple[str, dict[str, Any]]) -> Turn:
    content = [{"type": "tool_use", "id": f"toolu_{uuid.uuid4().hex[:8]}", "name": name, "input": given} for name, given in calls]
    return Turn(content=content, model="claude-opus-5-5", model_version="2023-06-01", input_tokens=2000, output_tokens=500, stop_reason="tool_use")


def _done(stop_reason: str = "end_turn") -> Turn:
    return Turn(content=[{"type": "text", "text": "Done."}], model="claude-opus-5-5", model_version="2023-06-01", input_tokens=2000, output_tokens=100, stop_reason=stop_reason)


class Scripted(MockLlm):
    """A model that answers each turn with the next scripted Turn and keeps what it was sent."""

    def __init__(self, *turns: Turn | Exception) -> None:
        self.turns = list(turns)
        self.sent: list[dict[str, Any]] = []

    def converse(self, **sent: Any) -> Turn:  # compliance: allow-kwargs test double of the adapter's keyword-only signature
        self.sent.append({**sent, "messages": list(sent["messages"])})
        answer = self.turns.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _change_body(term_id: str) -> dict[str, Any]:
    return {
        "stableKey": "chg-fi-2026-research-payments",
        "title": "FI adopts amended rules on paying for investment research",
        "changeType": "adopted",
        "authorityLabel": "Finansinspektionen",
        "authorityCode": "fi",
        "summary": "FI's board decided to amend three regulations in the securities area.",
        "sourceLabel": "Finansinspektionen",
        "sourceUrl": "https://www.fi.se/",
        "documents": [{"url": PAGE, "isPrimary": True}],
        "model": "claude-opus-5-5",
        "termIds": [term_id],
    }


class WorkerCase(TestCase):
    def setUp(self) -> None:
        self.world = world()
        tenancy.clear_tenant()
        self.agent = agent_build.agent(key="watch-sweeper")
        with library_write("test"):
            self.version = AgentVersion.objects.create(
                agent=self.agent, version_number=1, model="claude-opus-5", prompt_path="prompt.md", tools=SWEEPER_TOOLS
            )
        self.agent_run = AgentRun.objects.create(
            agent=self.agent, agent_version=self.version, trigger=RunTrigger.SCHEDULE.value, model="claude-opus-5", pipeline_version="1"
        )

    def drive(self, *turns: Turn | Exception) -> Scripted:
        model = Scripted(*turns)
        with mock.patch("apps.shared.ai.get_llm", return_value=model):
            tasks.drive_platform_run(str(self.agent_run.id))
        self.agent_run.refresh_from_db()
        return model


class ARunDoesItsWork(WorkerCase):
    def test_a_run_checks_a_source_registers_a_change_and_files_a_proposal_through_the_apis_doors(self) -> None:
        regime = str(watch_build.term("regime:securities").id)
        proposal = {
            "kind": "new_obligation_version",
            "title": "Version 2 of the research assessment duty",
            "targetType": "obligation",
            "targetId": str(self.world.obligation.id),
            "payload": {"summaries": {"en": "Assess the research payment first."}, "originalLanguage": "en", "isMachine": True},
            "fieldSources": {"summaries.en": PAGE},
            "sourceLabel": "Finansinspektionen, board decision",
            "sourceUrl": PAGE,
            "model": "claude-opus-5-5",
        }
        model = self.drive(
            _uses(("listSources", {}), ("recordSourceCheck", {"sourceName": SOURCE_NAME, "status": "ok", "itemsFound": 1})),
            _uses(("findSimilar", {"text": OBLIGATION_SUMMARY, "types": ["obligation"]}), ("createChange", _change_body(regime))),
            _uses(("createProposal", proposal)),
            _uses(("finishAgentRun", {"status": "succeeded", "stats": {"sourcesChecked": 1}})),
            _done(),
        )
        self.assertEqual(self.agent_run.status, RunStatus.SUCCEEDED.value, self.agent_run.error)
        check = SourceCheck.objects.get()
        change = RegulatoryChange.objects.get()
        filed = Proposal.objects.get()
        self.assertEqual((check.agent_run_id, change.agent_run_id, filed.agent_run_id), (self.agent_run.id,) * 3)
        self.assertEqual((change.origin, change.change_type_suggested_by_agent_id), ("agent", self.agent.id))
        self.assertEqual((filed.proposed_by_agent_id, filed.status), (self.agent.id, "open"))
        turns = AiGeneration.objects.filter(agent_run_id=self.agent_run.id, purpose="agent_turn")
        self.assertEqual(turns.count(), 5)
        self.assertEqual(self.agent_run.stats["modelCalls"], 5)
        self.assertEqual(self.agent_run.tokens_in, 10_000)
        self.assertGreater(self.agent_run.cost or 0, 0)
        # Every tool result went back in one message, each answering its call.
        results = model.sent[1]["messages"][-1]["content"]
        self.assertEqual([block["type"] for block in results], ["tool_result", "tool_result"])
        self.assertFalse(any(block["is_error"] for block in results), results)
        self.assertIn(SOURCE_NAME, results[0]["content"])

    def test_the_prompt_is_the_pinned_versions_and_the_tools_are_the_ones_it_names(self) -> None:
        model = self.drive(_done())
        sent = model.sent[0]
        self.assertEqual(sent["system"], (worker.DEFINITIONS / "watch-sweeper" / "v1" / "prompt.md").read_text(encoding="utf-8"))
        offered = [tool["name"] for tool in sent["tools"]]
        self.assertEqual(offered, [name for name in SWEEPER_TOOLS if name != "startAgentRun"], "startAgentRun is the runner's own")
        self.assertNotIn("agentRunId", sent["tools"][offered.index("createChange")]["input_schema"].get("properties", {}))
        self.assertIn(str(self.agent_run.id), sent["messages"][0]["content"])
        self.assertEqual(self.agent_run.status, RunStatus.SUCCEEDED.value)

    def test_a_tool_the_version_does_not_name_is_refused(self) -> None:
        model = self.drive(_uses(("listAuthorities", {})), _done())
        [result] = model.sent[1]["messages"][-1]["content"]
        self.assertTrue(result["is_error"])


class Refusals(WorkerCase):
    def test_a_refused_write_goes_back_to_the_model_and_stores_nothing(self) -> None:
        body = {**_change_body(str(watch_build.term("regime:securities").id)), "changeType": "invented"}
        model = self.drive(_uses(("createChange", body)), _done())
        [result] = model.sent[1]["messages"][-1]["content"]
        self.assertTrue(result["is_error"])
        self.assertIn("unknown_key", result["content"])
        self.assertFalse(RegulatoryChange.objects.exists())
        self.assertEqual(self.agent_run.status, RunStatus.SUCCEEDED.value)

    def test_input_the_schema_refuses_is_an_error_result(self) -> None:
        model = self.drive(_uses(("recordSourceCheck", {"sourceName": SOURCE_NAME, "status": "maybe"})), _done())
        [result] = model.sent[1]["messages"][-1]["content"]
        self.assertTrue(result["is_error"])
        self.assertFalse(SourceCheck.objects.exists())

    def test_a_long_tool_result_is_cut_to_the_setting(self) -> None:
        with override_settings(AGENT_TOOL_RESULT_MAX_CHARS=1000), mock.patch("apps.agents.requests.fetch_page", return_value="x" * 5000):
            model = self.drive(_uses(("fetch", {"url": PAGE})), _done())
        [result] = model.sent[1]["messages"][-1]["content"]
        self.assertEqual(len(result["content"]), 1000)
        self.assertIn("untrusted", result["content"])
        self.assertEqual(self.agent_run.stats["fetches"], 1)


class Endings(WorkerCase):
    def test_a_run_stopped_from_outside_takes_no_further_turn(self) -> None:
        def stop(**_: Any) -> Turn:  # compliance: allow-kwargs test double
            AgentRun.objects.filter(pk=self.agent_run.pk).update(status=RunStatus.INTERRUPTED.value)
            return _uses(("listSources", {}))

        model = Scripted()
        with mock.patch("apps.shared.ai.get_llm", return_value=model), mock.patch.object(model, "converse", side_effect=stop) as asked:
            tasks.drive_platform_run(str(self.agent_run.id))
        self.assertEqual(asked.call_count, 1)

    @override_settings(AGENT_RUN_MAX_TURNS=2)
    def test_the_turn_limit_closes_the_run_as_failed(self) -> None:
        self.drive(_uses(("listSources", {})), _uses(("listSources", {})))
        self.assertEqual((self.agent_run.status, self.agent_run.error), (RunStatus.FAILED.value, worker.TURN_LIMIT))

    @override_settings(PLATFORM_AGENT_MONTHLY_BUDGET="0.00")
    def test_an_agent_over_its_budget_asks_no_model(self) -> None:
        model = self.drive()
        self.assertEqual((self.agent_run.status, self.agent_run.error, model.sent), (RunStatus.FAILED.value, worker.OVER_BUDGET, []))

    def test_a_model_that_does_not_answer_fails_the_run_and_the_call_is_logged(self) -> None:
        self.drive(LlmError("the model API returned 529 (overloaded_error)"))
        self.assertEqual((self.agent_run.status, self.agent_run.error), (RunStatus.FAILED.value, worker.NO_ANSWER))
        self.assertEqual(AiGeneration.objects.get(agent_run_id=self.agent_run.id).stop_reason, "failed")

    def test_a_turn_cut_off_at_max_tokens_fails_the_run(self) -> None:
        self.drive(_done("max_tokens"))
        self.assertEqual((self.agent_run.status, self.agent_run.error), (RunStatus.FAILED.value, worker.CUT_SHORT))

    def test_the_model_reports_a_failed_run_through_finish(self) -> None:
        self.drive(_uses(("finishAgentRun", {"status": "failed", "error": "The source refused every fetch."})), _done())
        self.assertEqual((self.agent_run.status, self.agent_run.error), (RunStatus.FAILED.value, "The source refused every fetch."))

    def test_a_run_that_is_not_running_or_holds_a_key_is_left_alone(self) -> None:
        AgentRun.objects.filter(pk=self.agent_run.pk).update(status=RunStatus.SUCCEEDED.value)
        self.assertEqual(self.drive().sent, [])


class TheWorkerRunner(WorkerCase):
    @override_settings(AGENT_RUNNER="worker")
    def test_a_platform_run_is_queued_once_its_transaction_commits(self) -> None:
        with mock.patch.object(agent_runner.current_app, "send_task") as send, self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                handle = agent_runner.get_agent_runner().start(run_id=self.agent_run.id, definition_key="watch-sweeper", definition_version=1)
                send.assert_not_called()
        send.assert_called_once_with(agent_runner.PLATFORM_TASK, args=[str(self.agent_run.id)])
        self.assertEqual(handle.external_id, f"worker-{self.agent_run.id}")

    @override_settings(AGENT_RUNNER="worker")
    def test_a_banks_run_is_refused_so_the_opener_closes_it_as_failed(self) -> None:
        pinned = opener.Pinned(agent_id=self.agent.id, key="tenant-source-watch", version_id=self.version.id, version_no=1, model="m")
        with mock.patch("apps.shared.adapters.agent_runner.AgentRun.objects") as rows, mock.patch.object(agent_runner.current_app, "send_task") as send:
            rows.filter.return_value.values_list.return_value.first.return_value = uuid.uuid4()  # the run is a bank's
            opener._hand_over(self.agent_run, pinned, tasks.SCHEDULER)
        self.agent_run.refresh_from_db()
        self.assertEqual((self.agent_run.status, self.agent_run.error), (RunStatus.FAILED.value, opener.START_FAILED))
        send.assert_not_called()


CONFIRMER_TOOLS = ["startAgentRun", "listProposals", "approveProposal", "rejectProposal", "finishAgentRun"]
CITED = [{"label": "Finansinspektionen, board decision", "url": PAGE}]


class TheConfirmerDecides(WorkerCase):
    """library-confirmer on the runner (D-62, D-80): it reads the queue a person works and
    decides what another definition filed, each decision carrying the turn's logged call."""

    def setUp(self) -> None:
        super().setUp()
        from apps.agents import runner_tools
        from apps.agents.models import AgentKind

        sweeping = runner_tools.Session(run=self.agent_run)
        with transaction.atomic():
            runner_tools.call(
                sweeping,
                runner_tools.TOOLS["createProposal"],
                {
                    "kind": "new_obligation_version",
                    "title": "Version 2 of the research assessment duty",
                    "targetType": "obligation",
                    "targetId": str(self.world.obligation.id),
                    "payload": {"summaries": {"en": "Assess the research payment first."}, "originalLanguage": "en", "isMachine": True},
                    "fieldSources": {"summaries.en": PAGE},
                    "sourceLabel": "Finansinspektionen, board decision",
                    "sourceUrl": PAGE,
                    "model": "claude-opus-5-5",
                },
            )
        self.proposal = Proposal.objects.get()
        self.confirmer = agent_build.agent(key="library-confirmer", kind=AgentKind.REVIEW)
        with library_write("test"):
            version = AgentVersion.objects.create(agent=self.confirmer, version_number=2, model="claude-opus-5", prompt_path="prompt.md", tools=CONFIRMER_TOOLS)
        self.agent_run = AgentRun.objects.create(
            agent=self.confirmer, agent_version=version, trigger=RunTrigger.SCHEDULE.value, model="claude-opus-5", pipeline_version="2"
        )

    def decide(self, name: str, **extra: Any) -> Scripted:  # compliance: allow-kwargs test helper adding fields to the decision
        given = {"proposalId": str(self.proposal.id), "note": "The board decision states the new summary.", "output": "Checked the cited page.", "citations": CITED, **extra}
        return self.drive(_uses(("listProposals", {})), _uses((name, given)), _done())

    def test_it_approves_as_filed_and_the_record_names_both_agents(self) -> None:
        model = self.decide("approveProposal")
        listed = model.sent[1]["messages"][-1]["content"][0]["content"]
        self.assertIn(str(self.proposal.id), listed)
        self.proposal.refresh_from_db()
        self.assertEqual((self.proposal.status, self.proposal.reviewed_by_agent_id, self.proposal.proposed_by_agent_id), ("approved", self.confirmer.id, self.agent.id))
        review = AiGeneration.objects.get(purpose="agent_review", agent_run_id=self.agent_run.id)
        turn = AiGeneration.objects.filter(purpose="agent_turn", agent_run_id=self.agent_run.id).order_by("created_at")[1]
        self.assertEqual((review.model, review.prompt_hash), (turn.model, turn.prompt_hash), "the decision names the turn it was made in")
        self.assertEqual(review.citations[0]["url"], PAGE)

    def test_it_rejects_with_a_reason(self) -> None:
        self.decide("rejectProposal", rejectionReason="bad_source")
        self.proposal.refresh_from_db()
        self.assertEqual((self.proposal.status, self.proposal.rejection_code), ("rejected", "bad_source"))

    def test_a_decision_with_no_citation_is_refused_and_decides_nothing(self) -> None:
        model = self.decide("approveProposal", citations=[])
        [result] = model.sent[2]["messages"][-1]["content"]
        self.assertTrue(result["is_error"])
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, "open")

    def test_four_eyes_refuses_a_proposal_of_its_own_definition(self) -> None:
        Proposal.objects.filter(pk=self.proposal.pk).update(proposed_by_agent_id=self.confirmer.id)
        model = self.decide("approveProposal")
        [result] = model.sent[2]["messages"][-1]["content"]
        self.assertTrue(result["is_error"])
        self.assertIn("four_eyes_violation", result["content"])
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, "open")
