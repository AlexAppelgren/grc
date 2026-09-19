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
        """
