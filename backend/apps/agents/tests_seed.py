"""The chunk 11 E2E seed (c11-e2e-seed; AGT-03, AGT-04, AGT-05, PRO-04).

Proven here, over one real `seed_e2e()`: the sweeper is published at two versions and a
scheduled platform run names each; tenant A's own source watch is on, weekly, with a scope,
and its runs over the recent weeks put the month's spend just under its one cap, so one more
run of the same cost would pass it; tenant B has no agent, no cap and no run; the open
re-tag of twelve obligations was filed by `batch.create_batch()`, once, and a reseed files
nothing and changes nothing. With the clock moved either side of a month boundary, the
spend figure stays the same.

Spend is ruling 3's (INPUT_DELTAS §18): the `cost` of the bank's own runs started in its
current month, in its own zone. The spend panel's own query arrives with the scheduler.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentRun, AgentVersion, RunStatus, RunTrigger, TenantAgent, TenantAgentBudget
from apps.identity.models import User
from apps.library.models import Obligation
from apps.proposals import batch as proposal_batch
from apps.proposals.models import Proposal, ProposalBatchRow, ProposalStatus
from apps.shared import tenancy
from apps.shared.e2e_seed import EXPECTED_CHUNK11, TENANT_A, TENANT_B, c11_run_starts, seed_chunk11_agents, seed_e2e
from apps.shared.models import AuditEvent, Tenant

ZONE = ZoneInfo(TENANT_A.timezone)
MONTH_SPEND = sum(EXPECTED_CHUNK11.month_costs, Decimal(0))


def _spend(tenant: Tenant, now: datetime.datetime) -> Decimal:
    tenancy.activate(tenant.id)
    local = now.astimezone(ZoneInfo(tenant.timezone))
    first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    runs = AgentRun.objects.filter(tenant=tenant, started_at__gte=first, started_at__lte=now)
    return runs.aggregate(total=Sum("cost"))["total"] or Decimal(0)


def _snapshot() -> dict[str, Any]:
    """Every row the chunk 11 seed writes, and the audit trail, in each zone."""
    tenancy.clear_tenant()
    shot: dict[str, Any] = {
        "agents": list(Agent.objects.order_by("key").values_list("key", "current_version")),
        "versions": list(AgentVersion.objects.order_by("agent__key", "version_no").values()),
        "platform_runs": list(AgentRun.objects.filter(tenant__isnull=True).order_by("id").values()),
        "batches": list(Proposal.objects.filter(is_batch=True).order_by("id").values()),
        "rows": list(ProposalBatchRow.objects.order_by("id").values()),
        # Every seed rebuilds the search index and says so; nothing else in the library's zone may add a row.
        "library_audit": AuditEvent.objects.filter(tenant__isnull=True).exclude(action="search.index_rebuilt").count(),
    }
    for tenant in Tenant.objects.order_by("slug"):
        tenancy.activate(tenant.id)
        shot[tenant.slug] = (
            list(TenantAgent.objects.order_by("id").values()),
            list(TenantAgentBudget.objects.order_by("id").values()),
            list(AgentRun.objects.filter(tenant=tenant).order_by("id").values()),
            AuditEvent.objects.filter(tenant=tenant).count(),
        )
    return shot


@override_settings(E2E_MODE=True)
class ChunkElevenSeed(TestCase):
    batches_filed: int
    tenant_a: Tenant
    tenant_b: Tenant

    @classmethod
    def setUpTestData(cls) -> None:
        with mock.patch.object(proposal_batch, "create_batch", wraps=proposal_batch.create_batch) as filed:
            seed_e2e()
        cls.batches_filed = filed.call_count
        cls.tenant_a = Tenant.objects.get(pk=TENANT_A.id)
        cls.tenant_b = Tenant.objects.get(pk=TENANT_B.id)

    def test_the_sweeper_has_two_published_versions_and_a_platform_run_on_each(self) -> None:
        tenancy.clear_tenant()
        sweeper = Agent.objects.get(key=EXPECTED_CHUNK11.platform_agent)
        self.assertEqual(sorted(sweeper.versions.values_list("version_no", flat=True)), list(EXPECTED_CHUNK11.platform_versions))
        self.assertEqual(sweeper.current_version, EXPECTED_CHUNK11.platform_versions[-1])
        scheduled = AgentRun.objects.filter(tenant__isnull=True, api_key__isnull=True, trigger=RunTrigger.SCHEDULE.value)
        self.assertEqual(
            set(scheduled.filter(agent=sweeper).values_list("agent_version__version_no", flat=True)),
            set(EXPECTED_CHUNK11.platform_versions),
        )
        # The older version's run is the earlier one: publishing never re-points a run.
        older, newer = (scheduled.filter(agent=sweeper, agent_version__version_no=n).get() for n in EXPECTED_CHUNK11.platform_versions)
        self.assertLess(older.started_at, newer.started_at)
        self.assertTrue(scheduled.filter(agent__key=EXPECTED_CHUNK11.confirming_agent).exists())

    def test_tenant_a_runs_its_own_weekly_agent_with_a_scope_just_under_its_cap(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        tenancy.activate(self.tenant_a.id)
        agent = TenantAgent.objects.select_related("agent").get()
        self.assertEqual(agent.agent.key, EXPECTED_CHUNK11.tenant_agent)
        self.assertEqual((agent.enabled, agent.cadence, agent.scope), (True, "weekly", EXPECTED_CHUNK11.scope))
        assert agent.next_run_at is not None
        self.assertGreater(agent.next_run_at, now)
        budget = TenantAgentBudget.objects.get()
        self.assertEqual((budget.monthly_cap, budget.currency), (EXPECTED_CHUNK11.monthly_cap, EXPECTED_CHUNK11.currency))

        spend = _spend(self.tenant_a, now)
        self.assertEqual(spend, MONTH_SPEND)
        self.assertLess(spend, budget.monthly_cap)
        self.assertGreater(spend + min(EXPECTED_CHUNK11.month_costs), budget.monthly_cap, "one more run passes the cap")

        runs = AgentRun.objects.filter(tenant=self.tenant_a)
        self.assertEqual(set(runs.values_list("tenant_agent", flat=True)), {agent.id})
        for run in runs.select_related("agent_version"):
            with self.subTest(run=run.id):
                assert run.agent_version is not None and run.finished_at is not None and run.cost is not None
                self.assertEqual((run.agent_version.agent_id, run.status, run.trigger), (agent.agent_id, RunStatus.SUCCEEDED.value, "schedule"))
                self.assertEqual(run.scope, agent.scope)
                self.assertLessEqual(run.started_at, run.finished_at)
                self.assertLessEqual(run.finished_at, now)
        # Recent weeks: the oldest run is from the month before.
        first = now.astimezone(ZONE).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        self.assertLess(runs.order_by("started_at").first().started_at, first)  # type: ignore[union-attr]

    def test_tenant_b_has_no_agent_no_cap_and_no_run_of_its_own(self) -> None:
        tenancy.activate(self.tenant_b.id)
        self.assertFalse(TenantAgent.objects.exists())
        self.assertFalse(TenantAgentBudget.objects.exists())
        self.assertFalse(AgentRun.objects.filter(tenant__isnull=False).exists())
        self.assertEqual(_spend(self.tenant_b, datetime.datetime.now(datetime.UTC)), Decimal(0))

    def test_the_open_re_tag_of_twelve_rows_is_filed_by_create_batch(self) -> None:
        tenancy.clear_tenant()
        self.assertEqual(self.batches_filed, 1, "the seed files its batch through batch.create_batch() and nothing else")
        batch = Proposal.objects.get(is_batch=True, title=EXPECTED_CHUNK11.batch_title)
        self.assertEqual((batch.status, batch.row_count), (ProposalStatus.OPEN.value, len(EXPECTED_CHUNK11.batch_obligations)))
        self.assertEqual(batch.proposed_by_user_id, User.objects.get(email=EXPECTED_CHUNK11.batch_proposer_email).id)
        rows = ProposalBatchRow.objects.filter(proposal=batch)
        subjects = {row.subject_id: row for row in rows}
        obligations = dict(Obligation.objects.filter(stable_key__in=EXPECTED_CHUNK11.batch_obligations).values_list("id", "stable_key"))
        self.assertEqual(set(subjects), set(obligations))
        for row in rows:
            with self.subTest(obligation=obligations[row.subject_id]):
                self.assertEqual(row.decision, "pending")
                self.assertNotIn(EXPECTED_CHUNK11.batch_term, row.before["terms"])
                self.assertEqual(sorted(row.after["terms"]), sorted([*row.before["terms"], EXPECTED_CHUNK11.batch_term]))
        # The audit row create_batch writes, naming exactly the rows: a batch built by hand has none.
        audited = AuditEvent.objects.get(action="proposal.created", subject_id=batch.id)
        self.assertEqual((audited.after["isBatch"], audited.after["rowCount"]), (True, len(rows)))
        self.assertEqual(set(audited.after["subjectIds"]), {str(subject) for subject in subjects})

    def test_a_reseed_files_nothing_and_changes_nothing(self) -> None:
        before = _snapshot()
        with mock.patch.object(proposal_batch, "create_batch", wraps=proposal_batch.create_batch) as filed:
            seed_e2e()
        self.assertEqual(filed.call_count, 0)
        self.assertEqual(_snapshot(), before)

    def test_a_month_boundary_leaves_the_spend_figure_alone(self) -> None:
        tenants = list(Tenant.objects.order_by("slug"))
        for day, hour in (
            (datetime.date(2026, 10, 31), 23),  # the last hour of a month, in the bank's zone
            (datetime.date(2026, 11, 1), 0),  # the first, when UTC is still in October
            (datetime.date(2026, 11, 15), 12),
            (datetime.date(2027, 1, 1), 0),
            (datetime.date(2027, 3, 1), 0),
        ):
            now = datetime.datetime.combine(day, datetime.time(hour, 30), tzinfo=ZONE)
            with self.subTest(now=now):
                seed_chunk11_agents(tenants, now=now)
                self.assertEqual(_spend(self.tenant_a, now), MONTH_SPEND)
                tenancy.activate(self.tenant_a.id)
                self.assertFalse(AgentRun.objects.filter(tenant=self.tenant_a, started_at__gt=now).exists(), "no run starts after now")

    def test_this_months_runs_stay_in_the_month_and_the_earlier_ones_before_it(self) -> None:
        for day in (datetime.date(2026, 11, 1), datetime.date(2026, 11, 8), datetime.date(2026, 11, 30), datetime.date(2028, 2, 29)):
            now = datetime.datetime.combine(day, datetime.time(0, 1), tzinfo=ZONE)
            this_month, earlier = c11_run_starts(now)
            with self.subTest(day=day):
                self.assertEqual({start.date().replace(day=1) for start in this_month}, {day.replace(day=1)})
                self.assertTrue(all(start <= now for start in this_month))
                self.assertTrue(all(start.date() < day.replace(day=1) for start in earlier))
