"""The out-of-scope count a run files as it closes (AGT-08).

A document outside the sector scope leaves one trace: the count. So the count is refused
when it cannot be a count, and a run closed before the count existed reads 0 rather than
failing to read. What the count means end to end — two source checks, no change, no
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
