"""Scenario stubs for the collab app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: COL.
"""

from unittest import skip

from django.test import TestCase


class CollabScenarioTests(TestCase):
    """Scenario tests for apps.collab, one method per @integration scenario."""

    @skip("pending: COL-S1")
    def test_col_s1(self) -> None:
        """COL-S1

        A comment with a mention notifies the mentioned person (COL-01).
        """

    @skip("pending: COL-S2")
    def test_col_s2(self) -> None:
        """COL-S2

        Reminders, escalation and the digest reach people in their language (COL-02).
        """

    @skip("pending: COL-S3")
    def test_col_s3(self) -> None:
        """COL-S3

        Schedules run in the tenant's timezone (COL-02).
        """

    @skip("pending: COL-S4")
    def test_col_s4(self) -> None:
        """COL-S4

        A user follows a record and hears about changes (COL-03).
        """

    @skip("pending: COL-S5")
    def test_col_s5(self) -> None:
        """COL-S5

        Comment text never reaches a log (COL-01).
        """
