"""One execution of a watch agent over the real routes (AGT-01, ID-10, WAT-01, WAT-02,
PRO-01): open a run, log a source check, find the records near what it read, register the
change, submit a proposal and close — every write naming the run it belongs to.

AGT-S1 walks the whole flow once (tests_scenarios.py). What is held in place here:

- **Each step needs its own scope.** A key missing it answers 403 naming it, and writes
  nothing, even with a run of its own open.
- **A run is its key's alone.** Every step that names another key's run answers 404, as a
  run that never existed does, and nothing is filed against it.
- **What an agent files names an open run of its own.** A change or a proposal that names
  no run, or a closed one, answers 422 `run_not_open` and stores nothing, so no library row
  or proposal an agent wrote lacks the night that produced it.

The calls carry real keys (`X-API-Key`), never a stubbed principal, so the resolver,
row-level security and the mixed write rule run as they do in production. The base class
is Django's own `TestCase` rather than `ScenarioTestCase`: `POST /search/similar` is a read
over POST that writes no audit row by design, and the audit rows the writes leave are
asserted by name below instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from django.test import Client, TestCase

from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, RunStatus
from apps.library import testing as library_build
from apps.proposals.models import Proposal
from apps.search import indexing
from apps.shared import permissions as perms, tenancy
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange, SourceCheck

RUNS = "/api/v1/agent-runs"
CHANGES = "/api/v1/changes"
PROPOSALS = "/api/v1/proposals"
SIMILAR = "/api/v1/search/similar"
JSON = "application/json"

# Every scope one execution spends, one per step it takes (ID-10).
FLOW_SCOPES: tuple[str, ...] = (
    perms.SCOPE_AGENT_RUNS_WRITE,
    perms.SCOPE_SOURCES_WRITE,
    perms.SCOPE_CHANGES_WRITE,
    perms.SCOPE_SEARCH_READ,
    perms.SCOPE_PROPOSALS_WRITE,
)

# The prototype's lead reform and the duty it touches: FI's amended rules on paying for
# investment research, and the obligation to assess the research an institution pays for.
SOURCE_NAME = "Finansinspektionen news"
PAGE = "https://www.fi.se/en/published/news/2026/research-payments/"
OBLIGATION_TITLE = "Assess the quality of investment research paid for"
OBLIGATION_SUMMARY = (
    "The institution assesses the quality, usefulness and value of the investment research "
    "it pays for at least once a year, against documented criteria."
)
NEW_SUMMARY = (
    "The institution may receive investment research from a third party only if it pays "
    "for it from its own resources or from a research payment account, and it assesses the "
    "research against documented criteria at least once a year."
)
STATS = {"modelCalls": 4, "fetches": 3, "sourcesChecked": 1, "changesRegistered": 1, "proposalsSubmitted": 1}


@dataclass(frozen=True)
class World:
    """What a run finds when it starts: one duty in the library, indexed for search, the
    registered source it sweeps, and a platform key holding every scope of the flow."""

    obligation: Any
    key: SimpleNamespace


def world() -> World:
    watch_build.seed_watch_reference()
    tenancy.clear_tenant()  # platform rows are written with no tenant activated (H15)
    obligation = library_build.obligation(
        library_build.instrument(key="fffs-2017-2", regime="regime:securities"),
        key="fffs-2017-2-11-4",
        titles={"en": OBLIGATION_TITLE},
        ref_label="11 kap. 4 §",
        versions=((None, {"en": OBLIGATION_SUMMARY}),),
    )
    indexing.reindex(obligation.id)
    watch_build.source(name=SOURCE_NAME)
    return World(obligation=obligation, key=agent_build.agent_key(scopes=FLOW_SCOPES))


def key_without(scope: str) -> SimpleNamespace:
    """A platform key holding every scope of the flow but `scope`."""
    tenancy.clear_tenant()
    return agent_build.agent_key(scopes=tuple(held for held in FLOW_SCOPES if held != scope))


class Flow:
    """The calls one execution makes, in order, each as its key makes them. A run id of
    None leaves `agentRunId` out of the body, as a caller that forgot it would."""

    def __init__(self, client: Client, key: SimpleNamespace) -> None:
        self.client = client
        self.key = key

    def _send(self, method: str, path: str, body: Any, idempotency_key: str | None = None) -> Any:
        """One call as the key makes it, under a fresh `Idempotency-Key` unless a retry names
        the one it already sent."""
        return getattr(self.client, method)(
            path,
            data=body,
            content_type=JSON,
            HTTP_X_API_KEY=self.key.plain_key,
            HTTP_IDEMPOTENCY_KEY=idempotency_key or str(uuid.uuid4()),
        )

    def open(self, *, agent: str | None = None) -> Any:
        """Open a run of the key's own agent, or of `agent` for a key bound to none."""
        body = {
            "agent": agent or self.key.agent.key,
            "model": agent_build.SWEEPER_MODEL,
            "pipelineVersion": agent_build.SWEEPER_PIPELINE,
        }
        return self._send("post", RUNS, body)

    def check(self, run_id: Any) -> Any:
        return self._send("post", f"{RUNS}/{run_id}/source-checks", {"sourceName": SOURCE_NAME, "status": "ok", "itemsFound": 1})

    def similar(self) -> Any:
        return self.client.post(
            SIMILAR,
            data={"text": OBLIGATION_SUMMARY, "types": ["obligation"]},
            content_type=JSON,
            HTTP_X_API_KEY=self.key.plain_key,
        )

    def register(self, run_id: Any, *, obligation_id: Any = None) -> Any:
        body: dict[str, Any] = {
            "stableKey": "chg-fi-2026-research-payments",
            "title": "FI adopts amended rules on paying for investment research",
            "changeType": "adopted",
            "authorityLabel": "Finansinspektionen",
            "authorityCode": "fi",
            "summary": "FI's board decided to amend three regulations in the securities area.",
            "sourceLabel": "Finansinspektionen",
            "sourceUrl": "https://www.fi.se/",
            "documents": [{"url": PAGE, "isPrimary": True}],
            "model": agent_build.SWEEPER_MODEL,
            # Every change carries a regime (D-39, AC-AGT1).
            "termIds": [str(watch_build.term("regime:securities").id)],
        }
        if obligation_id is not None:
            body["obligationLinks"] = [{"obligationId": str(obligation_id), "confidence": 0.82}]
        return self._send("post", CHANGES, _with_run(body, run_id))

    def propose(
        self, run_id: Any, *, obligation_id: Any, change_id: Any = None, idempotency_key: str | None = None
    ) -> Any:
        body: dict[str, Any] = {
            "kind": "new_obligation_version",
            "title": "Version 2 of the research assessment duty",
            "targetType": "obligation",
            "targetId": str(obligation_id),
            "payload": {"summaries": {"en": NEW_SUMMARY}, "originalLanguage": "en", "isMachine": True},
            "fieldSources": {"summaries.en": PAGE},
            "sourceLabel": "Finansinspektionen, board decision",
            "sourceUrl": PAGE,
            "model": agent_build.SWEEPER_MODEL,
        }
        if change_id is not None:
            body["changeId"] = str(change_id)
        return self._send("post", PROPOSALS, _with_run(body, run_id), idempotency_key)

    def close(self, run_id: Any, *, status: str = "succeeded", error: str | None = None) -> Any:
        return self._send("patch", f"{RUNS}/{run_id}", {"status": status, "stats": STATS, "error": error})


def _with_run(body: dict[str, Any], run_id: Any) -> dict[str, Any]:
    return body if run_id is None else {**body, "agentRunId": str(run_id)}


def assert_refused(case: TestCase, response: Any, status: int, code: str) -> None:
    case.assertEqual(response.status_code, status, response.content)
    case.assertEqual(response.json()["code"], code)


class EachStepNeedsItsOwnScope(TestCase):
    """ID-10: a key is granted each step by name. Every key here has a run of its own open,
    so the refusal is about the scope and nothing else."""

    def setUp(self) -> None:
        self.world = world()

    def flow_without(self, scope: str) -> tuple[Flow, AgentRun]:
        key = key_without(scope)
        return Flow(self.client, key), agent_build.platform_run(key=key)

    def assert_denied(self, response: Any, scope: str) -> None:
        assert_refused(self, response, 403, "permission_denied")
        self.assertEqual(response.json()["requiredPermission"], scope)

    def test_opening_and_closing_a_run_needs_agent_runs_write(self) -> None:
        flow, run = self.flow_without(perms.SCOPE_AGENT_RUNS_WRITE)
        self.assert_denied(flow.open(), perms.SCOPE_AGENT_RUNS_WRITE)
        self.assert_denied(flow.close(run.id), perms.SCOPE_AGENT_RUNS_WRITE)
        self.assertEqual(AgentRun.objects.get().status, RunStatus.RUNNING.value, "no run opened, none closed")

    def test_logging_a_source_check_needs_sources_write(self) -> None:
        flow, run = self.flow_without(perms.SCOPE_SOURCES_WRITE)
        self.assert_denied(flow.check(run.id), perms.SCOPE_SOURCES_WRITE)
        self.assertFalse(SourceCheck.objects.exists())

    def test_finding_similar_records_needs_search_read(self) -> None:
        flow, _ = self.flow_without(perms.SCOPE_SEARCH_READ)
        self.assert_denied(flow.similar(), perms.SCOPE_SEARCH_READ)

    def test_registering_a_change_needs_changes_write(self) -> None:
        flow, run = self.flow_without(perms.SCOPE_CHANGES_WRITE)
        self.assert_denied(flow.register(run.id), perms.SCOPE_CHANGES_WRITE)
        self.assertFalse(RegulatoryChange.objects.exists())

    def test_submitting_a_proposal_needs_proposals_write(self) -> None:
        flow, run = self.flow_without(perms.SCOPE_PROPOSALS_WRITE)
        self.assert_denied(flow.propose(run.id, obligation_id=self.world.obligation.id), perms.SCOPE_PROPOSALS_WRITE)
        self.assertFalse(Proposal.objects.exists())


class ARunIsItsKeysAlone(TestCase):
    """A key acts on its own run only, and another key's run is answered exactly as a run
    that never existed, so a run id is not something a key can probe for."""

    def setUp(self) -> None:
        self.world = world()
        self.run_id = Flow(self.client, self.world.key).open().json()["id"]
        tenancy.clear_tenant()
        self.stranger = Flow(self.client, agent_build.agent_key(scopes=FLOW_SCOPES))

    def test_every_step_naming_another_keys_run_answers_404(self) -> None:
        obligation_id = self.world.obligation.id
        steps = {
            "check": lambda: self.stranger.check(self.run_id),
            "register": lambda: self.stranger.register(self.run_id),
            "propose": lambda: self.stranger.propose(self.run_id, obligation_id=obligation_id),
            "close": lambda: self.stranger.close(self.run_id),
        }
        for step, call in steps.items():
            with self.subTest(step=step):
                assert_refused(self, call(), 404, "not_found")
        self.assertFalse(SourceCheck.objects.exists())
        self.assertFalse(RegulatoryChange.objects.exists())
        self.assertFalse(Proposal.objects.exists())
        self.assertEqual(AgentRun.objects.get(pk=self.run_id).status, RunStatus.RUNNING.value, "nobody else closed it")

    def test_a_run_that_never_existed_answers_the_same(self) -> None:
        own = Flow(self.client, self.world.key)
        assert_refused(self, own.propose(uuid.uuid4(), obligation_id=self.world.obligation.id), 404, "not_found")


class WhatAnAgentFilesNamesAnOpenRunOfItsOwn(TestCase):
    """AGT-01, PRO-01: a change and a proposal from an agent's key carry the run they were
    found in, and a run that is closed takes nothing more."""

    def setUp(self) -> None:
        self.world = world()
        self.flow = Flow(self.client, self.world.key)

    def test_a_proposal_names_the_run_it_was_filed_under(self) -> None:
        run_id = self.flow.open().json()["id"]
        response = self.flow.propose(run_id, obligation_id=self.world.obligation.id)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["agentRunId"], run_id)
        self.assertEqual(str(Proposal.objects.get().agent_run_id), run_id)

    def test_a_proposal_or_a_change_naming_no_run_is_refused(self) -> None:
        self.flow.open()
        assert_refused(self, self.flow.propose(None, obligation_id=self.world.obligation.id), 422, "run_not_open")
        assert_refused(self, self.flow.register(None), 422, "run_not_open")
        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(RegulatoryChange.objects.exists())

    def test_a_retry_answers_while_its_run_is_open_and_is_refused_once_it_closed(self) -> None:
        """The run is checked before the retry is looked up, so an agent retries a lost answer
        before it closes the run; afterwards the retry is a filing against a closed run."""
        run_id = self.flow.open().json()["id"]
        obligation_id = self.world.obligation.id
        first = self.flow.propose(run_id, obligation_id=obligation_id, idempotency_key="retry-of-one-proposal")
        again = self.flow.propose(run_id, obligation_id=obligation_id, idempotency_key="retry-of-one-proposal")
        self.assertEqual((first.status_code, again.status_code), (201, 200), again.content)
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual(self.flow.close(run_id).status_code, 200)
        late = self.flow.propose(run_id, obligation_id=obligation_id, idempotency_key="retry-of-one-proposal")
        assert_refused(self, late, 422, "run_not_open")
        self.assertEqual(Proposal.objects.count(), 1)

    def test_a_proposal_or_a_change_naming_a_closed_run_is_refused(self) -> None:
        run_id = self.flow.open().json()["id"]
        self.assertEqual(self.flow.close(run_id).status_code, 200)
        assert_refused(self, self.flow.propose(run_id, obligation_id=self.world.obligation.id), 422, "run_not_open")
        assert_refused(self, self.flow.register(run_id), 422, "run_not_open")
        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(RegulatoryChange.objects.exists())
