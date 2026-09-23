"""The out-of-scope count a run files as it closes (AGT-08).

A document outside the sector scope leaves one trace: the count. So the count is refused
when it cannot be a count, and a run closed before the count existed reads 0 rather than
failing to read, and replays its own close rather than refusing it. What the count means end to end — two source checks, no change, no
proposal — is AGT-S12 in `tests_scenarios.py`.
"""

from __future__ import annotations

from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, RunStatus
from apps.agents.tests_runs import AgentRunCase
from apps.shared import permissions as perms
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, stub_session, user_principal


class TheOutOfScopeCount(AgentRunCase):
    def test_a_count_that_cannot_be_a_count_is_refused_and_the_run_stays_open(self) -> None:
        run_id = self.opened()["id"]
        for value in (-1, 2.5, "two"):
            with self.subTest(value=value):
                response = self.patch(run_id, {"status": "succeeded", "stats": {"outOfScope": value}})
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(AgentRun.objects.get(pk=run_id).status, RunStatus.RUNNING.value)

    def test_a_run_closed_before_the_count_existed_reads_zero(self) -> None:
        run = agent_build.platform_run(key=self.key)
        AgentRun.objects.filter(pk=run.pk).update(status=RunStatus.SUCCEEDED.value, stats={"sourcesChecked": 3})
        with stub_session(user_principal(permissions={perms.SYSTEM_HEALTH})):
            response = self.client.get("/api/v1/agent-runs", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
        self.assertEqual(response.status_code, 200, response.content)
        stats = next(item["stats"] for item in response.json()["items"] if item["id"] == str(run.id))
        self.assertEqual((stats["sourcesChecked"], stats["outOfScope"]), (3, 0))

    def test_the_same_close_of_a_run_closed_before_the_count_existed_still_replays(self) -> None:
        """A close stored before the count existed holds five counters. The agent that lost
        the answer sends that same close again: it is the same close, read as a reader reads
        it, so it replays; a close that differs in the count is still refused."""
        run_id = self.opened()["id"]
        older = {"modelCalls": 42, "fetches": 118, "sourcesChecked": 31, "changesRegistered": 2, "proposalsSubmitted": 5}
        self.assertEqual(self.patch(run_id, {"status": "succeeded", "stats": older}).status_code, 200)
        AgentRun.objects.filter(pk=run_id).update(stats=older)
        again = self.patch(run_id, {"status": "succeeded", "stats": older})
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["stats"]["outOfScope"], 0)
        other = self.patch(run_id, {"status": "succeeded", "stats": older | {"outOfScope": 1}})
        self.assertEqual(other.status_code, 409, other.content)
        self.assertEqual(other.json()["code"], "invalid_transition")
        self.assertEqual(AgentRun.objects.get(pk=run_id).stats, older, "neither answer rewrites the stored close")
