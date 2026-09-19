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

    @skip("pending: COL-S6 (COL-04, chunk 8)")
    def test_col_s6(self) -> None:
        """COL-S6

        A person or a team is added to a register entry, audited, and gains no access (COL-04, AC-COL1).
        """

    @skip("pending: COL-S7 (COL-04, chunk 8)")
    def test_col_s7(self) -> None:
        """COL-S7

        A participant leaves a register entry on their own (COL-04).
        """

    @skip("pending: COL-S8 (COL-04, chunk 8)")
    def test_col_s8(self) -> None:
        """COL-S8

        Register-entry participant routes refuse other tenants, strangers and people who cannot read (COL-04, NFR-01).
        """

    @skip("pending: COL-S9 (COL-04, chunk 9)")
    def test_col_s9(self) -> None:
        """COL-S9

        Case participants are managed by those who contribute, and refused across tenants (COL-04, NFR-01).
        """

    @skip("pending: COL-S10 (COL-02, COL-04, chunk 10)")
    def test_col_s10(self) -> None:
        """COL-S10

        Participation, confirmed links and new versions notify the people involved, once, if they can read (COL-02, COL-04).
        """

    @skip("pending: COL-S11 (COL-02, chunk 10)")
    def test_col_s11(self) -> None:
        """COL-S11

        Review reminders reach the people responsible, once (COL-02).
        """

    @skip("pending: COL-S12 (COL-01, HOM-05, chunk 10)")
    def test_col_s12(self) -> None:
        """COL-S12

        My comments and mentions are found on My work, limited to what I can read, and never logged (COL-01, HOM-05).
        """
