"""A bank's AI off switch stops its own agents before a run opens, and nothing of bleqq's
(AGT-04, D-07, D-61, owner item 14).

The switch has one reader, `apps.shared.ai.ensure_enabled`; the opener in `tasks.py` asks
it and adds no reader of its own. Written before the opener's check existed.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError

from apps.agents import tasks
from apps.agents.models import AgentRun, RunTrigger, TenantAgent
from apps.agents.tests_tasks import WEDNESDAY, BankBeatCase, Recorded, frozen, platform_runs, published, with_runner
from apps.governance.models import AiGeneration
from apps.shared import tenancy
from apps.shared.models import AuditEvent, Tenant


class AiOffStopsTheBanksOwnAgents(BankBeatCase):
    def setUp(self) -> None:
        super().setUp()
        Tenant.objects.filter(pk=self.bank.id).update(ai_enabled=False)
        self.theirs = self.own(self.other)

    def skipped(self) -> list[AuditEvent]:
        self.activate(self.bank)
        rows = list(AuditEvent.objects.filter(action="agent_run.skipped"))
        tenancy.clear_tenant()
        return rows

    def test_a_scheduled_run_is_skipped_with_one_audit_row_and_no_run_row(self) -> None:
        runner = self.beat()
        self.assertEqual(runner.seen, [])
        self.assertEqual(self.runs(), [])
        [skipped] = self.skipped()
        self.assertEqual(skipped.tenant_id, self.bank.id)
        self.assertEqual((skipped.after["reason"], skipped.after["agent"]), ("feature_off", self.definition.key))
        moved = self.fresh(self.agent).next_run_at
        assert moved is not None
        self.assertGreater(moved, WEDNESDAY, "the slot is taken, so the next beat does not skip it again")
        self.beat(at=WEDNESDAY + datetime.timedelta(minutes=15))
        self.assertEqual(len(self.skipped()), 1)
        self.assertIsNone(self.fresh(self.agent).paused_at, "AI off pauses nothing; switching it on resumes the schedule")

    def test_run_now_answers_feature_off_and_opens_no_run(self) -> None:
        self.activate(self.bank)
        with with_runner(Recorded()) as _, self.assertRaises(ValidationError) as refused:
            tasks.open_tenant_run(TenantAgent.objects.get(pk=self.agent.pk), trigger=RunTrigger.MANUAL, requested_by=self.admin)
        self.assertEqual(refused.exception.code, "feature_off")
        self.assertFalse(AgentRun.objects.exists())
        self.assertFalse(AiGeneration.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action__startswith="agent_run.").exists())

    def test_another_bank_and_bleqqs_agents_run_in_the_same_beat(self) -> None:
        published(self.bleqq)
        self.beat()
        self.beat(self.other)
        with frozen(WEDNESDAY), with_runner(Recorded()):
            tasks.run_platform_agents()
        self.assertEqual(self.runs(), [])
        self.assertEqual([run.tenant_agent_id for run in self.runs(self.other)], [self.theirs.id])
        self.assertEqual([run.agent_id for run in platform_runs()], [self.bleqq.id])

    def test_switching_it_back_on_lets_the_next_due_run_start(self) -> None:
        self.beat()
        Tenant.objects.filter(pk=self.bank.id).update(ai_enabled=True)
        self.beat(at=WEDNESDAY + datetime.timedelta(days=7))
        self.assertEqual(len(self.runs()), 1)
