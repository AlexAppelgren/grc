"""Scenario stubs for the register app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ACC, REG.
"""

from unittest import skip

from django.test import TestCase


class RegisterScenarioTests(TestCase):
    """Scenario tests for apps.register, one method per @integration scenario."""

    @skip("pending: REG-S1")
    def test_reg_s1(self) -> None:
        """REG-S1

        Applicability changes through a request a second person approves (REG-01).
        """

    @skip("pending: REG-S2")
    def test_reg_s2(self) -> None:
        """REG-S2

        The requester cannot approve their own applicability request (REG-01).
        """

    @skip("pending: REG-S3")
    def test_reg_s3(self) -> None:
        """REG-S3

        Compliance status and its details are kept per legal entity (REG-02).
        """

    @skip("pending: REG-S4")
    def test_reg_s4(self) -> None:
        """REG-S4

        "Applies" and "we comply" are separate facts (REG-01, REG-02).
        """

    @skip("pending: REG-S5")
    def test_reg_s5(self) -> None:
        """REG-S5

        A gap has an owner, severity, target date and remediation (REG-03).
        """

    @skip("pending: REG-S6")
    def test_reg_s6(self) -> None:
        """REG-S6

        Risk acceptance is behind four eyes with step-up (REG-03).
        """

    @skip("pending: REG-S7")
    def test_reg_s7(self) -> None:
        """REG-S7

        Assessment history and "How we read this rule" are kept per obligation (REG-04).
        """

    @skip("pending: REG-S8")
    def test_reg_s8(self) -> None:
        """REG-S8

        Linked internal items carry external references (REG-05).
        """

    @skip("pending: REG-S9")
    def test_reg_s9(self) -> None:
        """REG-S9

        Yearly attestation and waivers (REG-06).
        """

    @skip("pending: REG-S10")
    def test_reg_s10(self) -> None:
        """REG-S10

        Recurring duties appear on the roadmap from recurrence rules (REG-07).
        """

    @skip("pending: REG-S11")
    def test_reg_s11(self) -> None:
        """REG-S11

        A stale write on a register row is refused (REG-02).
        """

    @skip("pending: REG-S12 (REG-01, chunk 8)")
    def test_reg_s12(self) -> None:
        """REG-S12

        A legal entity follows a standard when its applicability is approved (REG-01, REG-02).
        """

    @skip("pending: REG-S13 (REG-08, chunk 8)")
    def test_reg_s13(self) -> None:
        """REG-S13

        A tenant lists its clauses and controls as units in its own words (REG-08).
        """

    @skip("pending: REG-S14 (REG-08, chunk 8)")
    def test_reg_s14(self) -> None:
        """REG-S14

        Unit decisions are filed from the paste and decided in one call, with four eyes on every row (REG-01, REG-08).
        """

    @skip("pending: REG-S15 (REG-08, chunk 8)")
    def test_reg_s15(self) -> None:
        """REG-S15

        The register filtered by standard and entity is the Statement of Applicability (REG-08).
        """


class RegisterAgentAccessScenarioTests(TestCase):
    """Agent access scenarios for apps.register (PRD 0.5 module ACC), one method per
    @integration heading in app.md. Skipped until chunk 11 builds them."""

    @skip("pending: ACC-S4")
    def test_acc_s4(self) -> None:
        """ACC-S4

        With tenant reach on, an entry reads the register decisions in its scope and nothing else (ACC-04).
        """
