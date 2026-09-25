"""The cases the E2E seed gives each case journey (c9-e2e-seed; CAS-02, CAS-03, CAS-04,
CAS-06, J-2, J-3).

Each journey that moves a case has one of its own, so parallel Playwright workers never
share one (apps/shared/tests_seed_integrity.py names each case and its journey). These tests
prove the rest of the brief: a second seed changes nothing, every date is the anchor plus a
fixed offset whatever day the seed runs on, each case's trail is the path it walked, written
through record() with no text a person typed, and none of it disturbs tenant A's home
screens while tenant B's lead leads tenant B's week.
"""

from __future__ import annotations

import datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from apps.cases.models import Action, CaseTransition, ChangeCase, ImpactAssessment
from apps.home import roadmap
from apps.home.logic import week_cases, week_start_of
from apps.library.reading import today_for
from apps.shared import tenancy
from apps.shared.e2e_logins import TENANT_A_SLUG
from apps.shared.e2e_seed import (
    EXPECTED_CASE_JOURNEYS,
    EXPECTED_HOME,
    SeedCaseJourney,
    case_anchor,
    case_first_seen,
    case_moment,
    seed_e2e,
)
from apps.shared.models import AuditEvent, Tenant
from apps.taxonomy.models import CaseStatusCategory
from apps.watch.models import RegulatoryChange

PATH = ["new", "assigned", "assessing", "implementing", "signoff", "closed"]


def _spec(journey: str) -> SeedCaseJourney:
    return next(spec for spec in EXPECTED_CASE_JOURNEYS if spec.journey == journey)


def _tenant(spec: SeedCaseJourney) -> Tenant:
    tenant = Tenant.objects.get(slug=spec.tenant_slug)
    tenancy.activate(tenant.id)
    return tenant


def _snapshot() -> dict[str, Any]:
    """Every row the case seed writes, by content, in both banks."""
    keys = [spec.stable_key for spec in EXPECTED_CASE_JOURNEYS]
    rows: dict[str, Any] = {"changes": list(RegulatoryChange.objects.filter(stable_key__in=keys).order_by("stable_key").values(
        "id", "stable_key", "title", "first_seen_at", "key_date", "published_on", "suggested_urgency_id", "so_what_draft"
    ))}
    for tenant in Tenant.objects.order_by("slug"):
        tenancy.activate(tenant.id)
        cases = ChangeCase.objects.filter(change__stable_key__in=keys)
        rows[tenant.slug] = {
            "cases": list(cases.order_by("id").values()),
            "transitions": list(CaseTransition.objects.filter(case__in=cases).order_by("id").values()),
            "assessments": list(ImpactAssessment.objects.filter(case__in=cases).order_by("id").values()),
            "actions": list(Action.objects.filter(case__in=cases).order_by("id").values()),
            "audit": list(AuditEvent.objects.filter(subject_id__in=cases.values("id")).order_by("id").values("id", "action", "after")),
        }
    return rows


@override_settings(E2E_MODE=True)
class SeededCaseJourneys(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_e2e()

    def test_a_second_seed_changes_nothing(self) -> None:
        before = _snapshot()
        self.assertTrue(before[TENANT_A_SLUG]["transitions"])
        seed_e2e()
        self.assertEqual(_snapshot(), before)

    def test_each_trail_is_the_path_the_case_walked_by_the_people_on_it(self) -> None:
        for spec in EXPECTED_CASE_JOURNEYS:
            with self.subTest(journey=spec.journey, change=spec.stable_key):
                _tenant(spec)
                case = ChangeCase.objects.get(change__stable_key=spec.stable_key)
                path = ["new", "dismissed"] if spec.status == CaseStatusCategory.DISMISSED else PATH[: PATH.index(spec.status.value) + 1]
                trail = list(CaseTransition.objects.filter(case=case))
                self.assertEqual([(row.from_status, row.to_status) for row in trail], list(zip(path, path[1:], strict=False)))
                self.assertTrue(all(row.by_user_id is not None for row in trail), "a person made every move")
                self.assertEqual([row.at for row in trail], sorted(row.at for row in trail))
                if spec.requested_by:
                    requested = next(row for row in trail if row.to_status == "signoff")
                    self.assertEqual(requested.by_user_id, case.signoff_requested_by_id)
                    self.assertEqual(requested.at, case.signoff_requested_at)
                audit = AuditEvent.objects.filter(subject_id=case.id)
                self.assertEqual(audit.filter(action="case.created").count(), 1)
                # One audit row per move, per saved assessment and per action added or done.
                expected = 1 + len(trail) + (1 if hasattr(case, "assessment") else 0) + sum(1 + plan.done for plan in spec.actions)
                self.assertEqual(audit.count(), expected)
                self.assertEqual(set(audit.values_list("actor_label", flat=True)), {"seed_e2e"})

    def test_no_audit_row_carries_what_a_person_typed(self) -> None:
        """R2_CROSS_CUTTING (m): ids, keys and dates only, never assessment text or a title."""
        for spec in EXPECTED_CASE_JOURNEYS:
            _tenant(spec)
            case = ChangeCase.objects.get(change__stable_key=spec.stable_key)
            typed = [plan.title for plan in spec.actions]
            if hasattr(case, "assessment"):
                typed += [case.assessment.why, case.assessment.what_must_change]
            for row in AuditEvent.objects.filter(subject_id=case.id):
                with self.subTest(journey=spec.journey, action=row.action):
                    carried = f"{row.before} {row.after}"
                    self.assertFalse([text for text in typed if text in carried])

    def test_every_date_is_the_anchor_plus_a_fixed_offset(self) -> None:
        """What the seed wrote is what the plan gives today's anchor: the steps a fixed number
        of days after the sighting, an open action's due date a fixed number of days from the
        anchor, so "due yesterday" is overdue in every month."""
        for spec in EXPECTED_CASE_JOURNEYS:
            with self.subTest(journey=spec.journey):
                tenant = _tenant(spec)
                anchor = case_anchor(tenant.timezone)
                case = ChangeCase.objects.select_related("change").get(change__stable_key=spec.stable_key)
                self.assertEqual(case.change.first_seen_at, case_first_seen(spec, anchor))
                self.assertEqual(case.change.key_date, case_first_seen(spec, anchor).date() + datetime.timedelta(days=20))
                if case.triaged_at is not None:
                    self.assertEqual(case.triaged_at, case_moment(spec, anchor, 1))
                if case.closed_at is not None:
                    self.assertEqual(case.closed_at, case_moment(spec, anchor, 14))
                for action in Action.objects.filter(case=case):
                    plan = next(plan for plan in spec.actions if plan.title == action.title)
                    if not plan.done:
                        self.assertEqual(action.due_date, anchor.date() + datetime.timedelta(days=plan.due_in_days))
                        self.assertIsNone(action.done_at)
                    else:
                        assert action.done_at is not None
                        self.assertLessEqual(action.done_at.date(), action.due_date)
        overdue = next(plan for plan in _spec("CAS-S8").actions if not plan.done)
        self.assertEqual(overdue.due_in_days, -1)

    def test_the_offsets_hold_across_a_quarter_and_a_year_boundary(self) -> None:
        """Frozen at the last and first day of a quarter and of a year, the plan is the same
        distance from the anchor: no date depends on which real day the seed runs."""
        zone = ZoneInfo("Europe/Stockholm")

        def offsets(anchor: datetime.datetime) -> list[datetime.timedelta]:
            return [case_first_seen(spec, anchor) - anchor for spec in EXPECTED_CASE_JOURNEYS if spec.tenant_slug == TENANT_A_SLUG]

        anchors = [datetime.datetime(year, month, day, 9, tzinfo=zone) for year, month, day in ((2026, 3, 31), (2026, 4, 1), (2026, 12, 31), (2027, 1, 1))]
        first = offsets(anchors[0])
        for anchor in anchors[1:]:
            with self.subTest(anchor=anchor):
                self.assertEqual(offsets(anchor), first)
                # Tenant B's lead is sighted in the anchor's own ISO week, whatever week that is.
                lead = case_first_seen(_spec("CAS-S14"), anchor)
                self.assertEqual(week_start_of(lead.date()), week_start_of(anchor.date()))
        self.assertTrue(all(offset <= -datetime.timedelta(days=42) for offset in first), "sighted before last week's briefing")

    def test_tenant_b_lead_leads_its_week_and_tenant_a_keeps_its_own(self) -> None:
        """J-2 on tenant B's lead, its So what still the draft, leaves HOM-S1's lead alone."""
        spec = _spec("CAS-S14")
        tenant_b = _tenant(spec)
        lead = week_cases(tenant_b, week_start_of(today_for(tenant_b)), limit=1)[0]
        self.assertEqual(lead.change.stable_key, spec.stable_key)
        self.assertEqual((lead.status, lead.so_what_confirmed), ("new", False))

        tenant_a = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant_a.id)
        self.assertEqual(week_cases(tenant_a, week_start_of(today_for(tenant_a)), limit=1)[0].change.stable_key, EXPECTED_HOME.lead_change)

    def test_tenant_a_cases_stay_off_its_roadmap_and_its_weeks(self) -> None:
        """Every key date is past and every sighting weeks old, so Today's "Coming up", the
        roadmap and this and last week's briefing read exactly what they read before."""
        tenant = Tenant.objects.get(slug=TENANT_A_SLUG)
        tenancy.activate(tenant.id)
        keys = {spec.stable_key for spec in EXPECTED_CASE_JOURNEYS if spec.tenant_slug == TENANT_A_SLUG}
        today = today_for(tenant)
        on_roadmap = {case.change.stable_key for case in roadmap._cases(tenant, roadmap.HomeRoadmapQuery())}
        this_week = {case.change.stable_key for case in week_cases(tenant, week_start_of(today), limit=100)}
        last_week = {case.change.stable_key for case in week_cases(tenant, week_start_of(today) - datetime.timedelta(days=7), limit=100)}
        self.assertFalse(keys & (on_roadmap | this_week | last_week))
        self.assertFalse(ChangeCase.objects.filter(change__stable_key=_spec("CAS-S14").stable_key).exists())


# --- c9-e2e-signoff-j3 (CAS-S10) ----------------------------------------------------------------
@override_settings(E2E_MODE=True)
class SeededSignoffSpotCheck(TestCase):
    """CAS-S10 proves a sign-off leaves the inventory alone by reading one obligation before and
    after: the obligation its change links to, confirmed, and named by no other journey."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_e2e()

    def test_cas_s10_change_links_the_obligation_its_journey_reads(self) -> None:
        from apps.shared.e2e_seed import SIGNOFF_SPOT_CHECK_OBLIGATION
        from apps.watch.models import ChangeObligation

        tenancy.clear_tenant()
        link = ChangeObligation.objects.get(change__stable_key=_spec("CAS-S10").stable_key)
        self.assertEqual(link.obligation.stable_key, SIGNOFF_SPOT_CHECK_OBLIGATION)
        self.assertIsNotNone(link.confirmed_at, "a confirmed link, so the change page shows it as settled")
        linked_from = ChangeObligation.objects.filter(obligation=link.obligation).values_list("change__stable_key", flat=True)
        self.assertEqual(list(linked_from), [_spec("CAS-S10").stable_key], "no other seeded change names it")
