"""Scenario stubs for the home app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: HOM.
"""

import datetime
from unittest import mock, skip

from django.test import TestCase

from apps.cases import testing as cases_build
from apps.shared import factories
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build

# A fixed instant and fixed dates, never "now": a quarter boundary must not decide what a
# scenario sees (playbook 8.3). At this instant the bank's own day is 1 October 2026.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
THIS_QUARTER = datetime.date(2026, 10, 15)
NEXT_QUARTER = datetime.date(2027, 1, 20)


class HomeScenarioTests(TestCase):
    """Scenario tests for apps.home, one method per @integration scenario."""

    @skip("pending: HOM-S1")
    def test_hom_s1(self) -> None:
        """HOM-S1

        Today shows the next dates, the lead item, decisions, standing and source health (HOM-01).
        """

    @skip("pending: HOM-S3")
    def test_hom_s3(self) -> None:
        """HOM-S3

        The weekly briefing is reachable from home and snapshotted when emailed (HOM-02).
        """

    def test_hom_s4(self) -> None:
        """HOM-S4

        The roadmap shows the quarters ahead with their regulatory dates (HOM-03, FP-03).

        The expanding card is the journey's half. What is proved here is what the screen
        draws it from: two quarters in one roster, the items inside each in date order with
        the bank's own urgency on every one, and a dated change outside the bank's
        regulatory scope absent from both.
        """
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="hom-s4", timezone="Europe/Stockholm")
        reader = factories.member_user(tenant, roles=("reader",))
        soon = watch_build.change(
            title="FI adopts amended rules on paying for investment research",
            key_date=THIS_QUARTER,
            key_date_label="In force",
        )
        later = watch_build.change(
            title="Amended reporting of securities financing transactions",
            key_date=NEXT_QUARTER,
            key_date_label="Applies",
            urgency="six_months_plus",
        )
        elsewhere = watch_build.change(title="Insurance distribution guidance", key_date=THIS_QUARTER)
        cases_build.case(tenant, soon)
        cases_build.case(tenant, later, urgency="six_months_plus")
        cases_build.case(tenant, elsewhere, footprint_match=False)

        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            response = self.client.get("/api/v1/roadmap", **sign_in(reader, tenant=tenant))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["quarters"], ["2026-Q4", "2027-Q1"])
        self.assertEqual([item["title"] for item in body["items"]], [soon.title, later.title])
        self.assertEqual([item["quarter"] for item in body["items"]], ["2026-Q4", "2027-Q1"])
        self.assertEqual([item["urgency"]["key"] for item in body["items"]], ["act_now", "six_months_plus"])
        self.assertEqual([item["label"] for item in body["items"]], ["In force", "Applies"])
        self.assertNotIn(elsewhere.title, [item["title"] for item in body["items"]])

    @skip("pending: HOM-S5")
    def test_hom_s5(self) -> None:
        """HOM-S5

        Upcoming changes are public facts and the calendar feed is revocable (HOM-04).
        Operations: `listUpcoming`, `listCalendarFeeds`, `createCalendarFeed`,
        `revokeCalendarFeed`, `getCalendarIcs`.
        """

    @skip("pending: HOM-S7 (HOM-05, chunk 8)")
    def test_hom_s7(self) -> None:
        """HOM-S7

        My work lists what I'm responsible for or take part in, most urgent first (HOM-05, AC-HOM1).
        """

    @skip("pending: HOM-S8 (HOM-05, chunk 8)")
    def test_hom_s8(self) -> None:
        """HOM-S8

        Compliant and per-entity reviews reach My work (HOM-05, AC-HOM1).
        """

    @skip("pending: HOM-S9 (HOM-05, chunk 8)")
    def test_hom_s9(self) -> None:
        """HOM-S9

        A department head sees the department's work, naming who is responsible (HOM-05, TEN-02, TEN-03).
        """

    @skip("pending: HOM-S10 (HOM-05, chunk 8)")
    def test_hom_s10(self) -> None:
        """HOM-S10

        My work applies each record's read permission to rows and counts, and ignores the footprint (HOM-05).
        """

    @skip("pending: HOM-S11 (HOM-05, chunk 8)")
    def test_hom_s11(self) -> None:
        """HOM-S11

        Changes on your items are confirmed links and new versions only (HOM-05).
        """

    @skip("pending: HOM-S12 (HOM-05, chunk 8)")
    def test_hom_s12(self) -> None:
        """HOM-S12

        My work answers within budget for a fifty-member department (HOM-05, NFR-02).
        """

    @skip("pending: HOM-S14 (HOM-05, chunk 9)")
    def test_hom_s14(self) -> None:
        """HOM-S14

        Case work reaches My work (HOM-05).
        """

    @skip("pending: HOM-S15 (HOM-03, TEN-02, chunk 8)")
    def test_hom_s15(self) -> None:
        """HOM-S15

        A certificate's expiry and next audit are our deadlines, never in the calendar feed (HOM-03, HOM-04, TEN-02, AC-TEN1).
        """
