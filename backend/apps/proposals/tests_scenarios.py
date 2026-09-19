"""Scenario stubs for the proposals app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: PRO.
"""

from unittest import skip

from django.test import TestCase


class ProposalsScenarioTests(TestCase):
    """Scenario tests for apps.proposals, one method per @integration scenario."""

    @skip("pending: PRO-S1")
    def test_pro_s1(self) -> None:
        """PRO-S1

        A proposal carries a source per changed field (PRO-01).
        """

    @skip("pending: PRO-S2")
    def test_pro_s2(self) -> None:
        """PRO-S2

        No scope and no tenant role can change a library record directly (PRO-01, AC-PRO1).
        """

    @skip("pending: PRO-S3")
    def test_pro_s3(self) -> None:
        """PRO-S3

        Approval applies payload, version, audit row and re-index in one transaction (PRO-02).
        """

    @skip("pending: PRO-S4")
    def test_pro_s4(self) -> None:
        """PRO-S4

        The reviewer corrects scope and wording before approving (PRO-02).
        """

    @skip("pending: PRO-S5")
    def test_pro_s5(self) -> None:
        """PRO-S5

        Approving your own proposal answers four_eyes_violation (PRO-02, AC-PRO2).
        """

    @skip("pending: PRO-S6")
    def test_pro_s6(self) -> None:
        """PRO-S6

        A retried submission with the same Idempotency-Key creates one proposal (PRO-01).
        """

    @skip("pending: PRO-S7")
    def test_pro_s7(self) -> None:
        """PRO-S7

        The queue is in the console and tenants see updates and report problems (PRO-03).
        """

    @skip("pending: PRO-S8")
    def test_pro_s8(self) -> None:
        """PRO-S8

        A batch proposal previews and is approved whole or row by row (PRO-04).
        """

    @skip("pending: PRO-S9")
    def test_pro_s9(self) -> None:
        """PRO-S9

        A rejection needs a reason and is audited (PRO-01).
        """
