"""Scenario stubs for the cases app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: CAS.
"""

from unittest import skip

from django.test import TestCase


class CasesScenarioTests(TestCase):
    """Scenario tests for apps.cases, one method per @integration scenario."""

    @skip("pending: CAS-S1")
    def test_cas_s1(self) -> None:
        """CAS-S1

        A change creates one case per tenant in "Needs triage" with its footprint match (CAS-01).
        """

    @skip("pending: CAS-S2")
    def test_cas_s2(self) -> None:
        """CAS-S2

        Triage needs an urgency and an owner (CAS-02).
        """

    @skip("pending: CAS-S3")
    def test_cas_s3(self) -> None:
        """CAS-S3

        Dismissal needs a reason and can be restored (CAS-02).
        """

    @skip("pending: CAS-S4")
    def test_cas_s4(self) -> None:
        """CAS-S4

        The impact assessment records what applies and what must change (CAS-03).
        """

    @skip("pending: CAS-S5")
    def test_cas_s5(self) -> None:
        """CAS-S5

        Two people saving the same assessment: the second receives stale_write (CAS-03, CAS-08, AC-CAS2).
        """

    @skip("pending: CAS-S6")
    def test_cas_s6(self) -> None:
        """CAS-S6

        Actions have an owner and due date, lock during sign-off and export as tickets (CAS-04).
        """

    @skip("pending: CAS-S7")
    def test_cas_s7(self) -> None:
        """CAS-S7

        Evidence is scanned, hashed and streamed through permission checks (CAS-05).
        """

    @skip("pending: CAS-S8")
    def test_cas_s8(self) -> None:
        """CAS-S8

        Sign-off is refused while actions are open or evidence is missing (CAS-06, AC-CAS1).
        """

    @skip("pending: CAS-S9")
    def test_cas_s9(self) -> None:
        """CAS-S9

        The requester cannot sign off their own case (CAS-06, AC-CAS1).
        """

    @skip("pending: CAS-S10")
    def test_cas_s10(self) -> None:
        """CAS-S10

        A second person signs off with step-up and the inventory is untouched (CAS-06).
        """

    @skip("pending: CAS-S11")
    def test_cas_s11(self) -> None:
        """CAS-S11

        The case file stands alone as text and as an export (CAS-07).
        """

    @skip("pending: CAS-S12")
    def test_cas_s12(self) -> None:
        """CAS-S12

        Every response lists allowed transitions and an invalid one is refused (CAS-08).
        """

    @skip("pending: CAS-S13")
    def test_cas_s13(self) -> None:
        """CAS-S13

        Sub-statuses inside a category leave the guards untouched (CAS-02, VOC-04).
        """

    @skip("pending: CAS-S16")
    def test_cas_s16(self) -> None:
        """CAS-S16

        Another tenant's case and evidence answer 404 (CAS-05, CAS-07, NFR-01).
        """

    @skip("pending: CAS-S17 (CAS-03, COL-04, chunk 9)")
    def test_cas_s17(self) -> None:
        """CAS-S17

        Contributor teams are the case's team participants (CAS-03, COL-04).
        """
