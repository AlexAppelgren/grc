"""Scenario stubs for the home app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: HOM.
"""

from unittest import skip

from django.test import TestCase


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

    @skip("pending: HOM-S4")
    def test_hom_s4(self) -> None:
        """HOM-S4

        The roadmap shows quarters with regulatory dates and our own deadlines (HOM-03).
        """

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
