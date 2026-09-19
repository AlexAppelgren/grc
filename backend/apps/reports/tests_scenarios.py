"""Scenario stubs for the reports app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: REP.
"""

from unittest import skip

from django.test import TestCase


class ReportsScenarioTests(TestCase):
    """Scenario tests for apps.reports, one method per @integration scenario."""

    @skip("pending: REP-S1")
    def test_rep_s1(self) -> None:
        """REP-S1

        The dashboard shows the officer's figures from keys and categories (REP-01).
        """

    @skip("pending: REP-S2")
    def test_rep_s2(self) -> None:
        """REP-S2

        The committee pack and the exports are produced by jobs (REP-02).
        """

    @skip("pending: REP-S3")
    def test_rep_s3(self) -> None:
        """REP-S3

        An export needs step-up and never runs inside the request (REP-02).
        """

    @skip("pending: REP-S4")
    def test_rep_s4(self) -> None:
        """REP-S4

        A spreadsheet register imports with a dry run and a mapping asked once per value (REP-03).
        """

    @skip("pending: REP-S5")
    def test_rep_s5(self) -> None:
        """REP-S5

        A tenant can leave with everything and have deletion verified (REP-04).
        """

    @skip("pending: REP-S6 (REP-02, REG-08, chunk 12)")
    def test_rep_s6(self) -> None:
        """REP-S6

        The Statement of Applicability exports as a dated inventory export (REP-02, REG-08).
        """
