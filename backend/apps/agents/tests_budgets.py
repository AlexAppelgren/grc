"""A run's write budgets, held by the server (security-review-c5 M3, HARDENING H24).

The definition names what one run may file (`budget_defaults` in
`agents/watch-sweeper/v1/definition.yaml`), and the server holds every run to the same
numbers from settings with an env override: `WATCH_RUN_MAX_PROPOSALS`,
`WATCH_RUN_MAX_CHANGES` and `WATCH_RUN_MAX_RECHECKS`. A write past its budget is refused
with 422 `run_budget_exhausted` before anything is stored, so a runaway or injected run
cannot flood the review queue, the watch feed or the coverage log under one open run. A
retry of what the run already filed is not a new write and still answers. What a run
counts as it closes is the server's own count of what it filed, not the run's account of
itself.

Written before the fix: every refusal below was a 201 or a 204, and every count was the
number the run sent.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import override_settings

from apps.agents import testing as agent_build
from apps.agents.models import AgentRun
from apps.library import testing as library_build
from apps.proposals.models import Proposal
from apps.shared import permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange, SourceCheck
from apps.watch.tests_registration import body as change_body

V1 = "/api/v1"
JSON = "application/json"
BUDGET = "run_budget_exhausted"


class RunBudgetCase(ScenarioTestCase):
    """A sweeper key holding every write scope a sweep uses, with one run open, an
    obligation to propose against and a registered source to check."""

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        tenancy.clear_tenant()
        self.key = agent_build.agent_key(scopes=(*agent_build.WATCH_SCOPES, perms.SCOPE_PROPOSALS_WRITE))
        self.open_run = agent_build.platform_run(key=self.key)
        self.obligation = library_build.obligation(
            library_build.instrument(key="budget-instrument", regime="regime:securities"), key="obl-budget"
        )
        self.source = watch_build.source(name="fi.se news")

    def post(self, path: str, data: dict[str, Any], **headers: Any) -> Any:  # compliance: allow-kwargs test helper forwarding headers
        answer = self.client.post(f"{V1}{path}", data=data, content_type=JSON, HTTP_X_API_KEY=self.key.plain_key, **headers)
        tenancy.clear_tenant()
        return answer

    def propose(self, n: int, *, run: AgentRun | None = None, retry_key: str | None = None) -> Any:
        extra = {} if retry_key is None else {"HTTP_IDEMPOTENCY_KEY": retry_key}
        return self.post(
            "/proposals",
            {
                "kind": "new_obligation_version",
                "title": f"Refresh the wording against the source, reading {n}",
                "targetType": "obligation",
                "targetId": str(self.obligation.id),
                "payload": {"summaries": {"en": f"The duty as the source now reads it, reading {n}."}, "originalLanguage": "en"},
                "fieldSources": {"summaries.en": "https://www.fi.se/"},
                "agentRunId": str((run or self.open_run).id),
            },
            **extra,
        )

    def register(self, stable_key: str, *, run: AgentRun | None = None) -> Any:
        return self.post("/changes", change_body(stableKey=stable_key, agentRunId=str((run or self.open_run).id)))

    def recheck(self, *, run: AgentRun | None = None, subject: uuid.UUID | None = None) -> Any:
        return self.post(
            f"/agent-runs/{(run or self.open_run).id}/source-checks",
            {
                "sourceName": self.source.name,
                "status": "ok",
                "kind": "recheck",
                "subjectType": "obligation",
                "subjectId": str(subject or self.obligation.id),
            },
        )

    def sweep(self, *, run: AgentRun | None = None) -> Any:
        return self.post(f"/agent-runs/{(run or self.open_run).id}/source-checks", {"sourceName": self.source.name, "status": "ok"})

    def assert_over_budget(self, response: Any, what: str) -> None:
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], BUDGET)
        self.assertIn(what, response.json()["detail"])


class TheServerHoldsARunToItsBudget(RunBudgetCase):
    @override_settings(WATCH_RUN_MAX_PROPOSALS=2)
    def test_a_proposal_past_the_runs_budget_is_refused_and_nothing_is_stored(self) -> None:
        for n in (1, 2):
            self.assertEqual(self.propose(n).status_code, 201)
        audited = AuditEvent.objects.filter(action="proposal.created").count()
        refused = self.propose(3)
        self.assert_over_budget(refused, "2 proposals")
        self.assertEqual(Proposal.objects.filter(agent_run_id=self.open_run.id).count(), 2)
        self.assertEqual(AuditEvent.objects.filter(action="proposal.created").count(), audited, "a refusal is not audited as a write")
        # The budget is the run's: the same key's next run files again.
        self.assertEqual(self.propose(4, run=agent_build.platform_run(key=self.key)).status_code, 201)

    @override_settings(WATCH_RUN_MAX_PROPOSALS=1)
    def test_a_retry_of_a_proposal_the_run_already_filed_still_answers_it(self) -> None:
        first = self.propose(1, retry_key="budget-retry-1")
        self.assertEqual(first.status_code, 201, first.content)
        again = self.propose(1, retry_key="budget-retry-1")
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assert_over_budget(self.propose(2, retry_key="budget-retry-2"), "1 proposal")

    @override_settings(WATCH_RUN_MAX_CHANGES=1)
    def test_a_new_change_past_the_runs_budget_is_refused_and_a_second_sighting_still_merges(self) -> None:
        self.assertEqual(self.register("chg-budget-first").status_code, 201)
        self.assert_over_budget(self.register("chg-budget-second"), "1 change")
        self.assertFalse(RegulatoryChange.objects.filter(stable_key="chg-budget-second").exists())
        # A second sighting files no new change, so it is no new spending.
        self.assertEqual(self.register("chg-budget-first").status_code, 200)

    @override_settings(WATCH_RUN_MAX_RECHECKS=2)
    def test_a_recheck_past_the_runs_budget_is_refused_and_a_sweep_is_not_counted(self) -> None:
        self.assertEqual(self.recheck().status_code, 204)
        self.assertEqual(self.recheck(subject=uuid.uuid4()).status_code, 204)
        self.assert_over_budget(self.recheck(subject=uuid.uuid4()), "2 re-checks")
        self.assertEqual(SourceCheck.objects.filter(agent_run=self.open_run, kind="recheck").count(), 2)
        self.assertEqual(self.sweep().status_code, 204, "a sweep of a source is not a re-check")

    def test_the_budgets_are_the_definitions_defaults_out_of_the_box(self) -> None:
        from django.conf import settings

        self.assertEqual(
            (settings.WATCH_RUN_MAX_PROPOSALS, settings.WATCH_RUN_MAX_CHANGES, settings.WATCH_RUN_MAX_RECHECKS), (50, 50, 100)
        )


class TheServerCountsWhatARunFiled(RunBudgetCase):
    def test_a_close_stores_the_servers_count_of_what_the_run_filed(self) -> None:
        self.assertEqual(self.propose(1).status_code, 201)
        self.assertEqual(self.register("chg-count-first").status_code, 201)
        self.assertEqual(self.recheck().status_code, 204)
        self.assertEqual(self.recheck().status_code, 204, "the same record twice is one record re-checked")
        self.assertEqual(self.sweep().status_code, 204)
        self.assertEqual(self.sweep().status_code, 204, "the same source twice is one source checked")
        claimed = {
            "modelCalls": 42,
            "fetches": 118,
            "sourcesChecked": 31,
            "changesRegistered": 9,
            "proposalsSubmitted": 99,
            "outOfScope": 3,
            "recordsRechecked": 12,
            "correctionsProposed": 1,
        }
        closed = self.client.patch(
            f"{V1}/agent-runs/{self.open_run.id}",
            data={"status": "succeeded", "stats": claimed},
            content_type=JSON,
            HTTP_X_API_KEY=self.key.plain_key,
        )
        self.assertEqual(closed.status_code, 200, closed.content)
        counted = {"sourcesChecked": 1, "changesRegistered": 1, "proposalsSubmitted": 1, "recordsRechecked": 1}
        reported = {"modelCalls": 42, "fetches": 118, "outOfScope": 3, "correctionsProposed": 1}
        self.assertEqual(closed.json()["stats"], {**reported, **counted})
        tenancy.clear_tenant()
        self.assertEqual(AgentRun.objects.get(pk=self.open_run.pk).stats, {**reported, **counted})
        # The same close sent again is the same close: what the server counts is not the
        # caller's to contest, so it replays rather than conflicting.
        again = self.client.patch(
            f"{V1}/agent-runs/{self.open_run.id}",
            data={"status": "succeeded", "stats": claimed},
            content_type=JSON,
            HTTP_X_API_KEY=self.key.plain_key,
        )
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["stats"], {**reported, **counted})
