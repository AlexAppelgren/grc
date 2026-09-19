"""Scenario stubs for the governance app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ADM, AUD.
"""

from unittest import skip

from django.test import TestCase


class GovernanceScenarioTests(TestCase):
    """Scenario tests for apps.governance, one method per @integration scenario."""

    @skip("pending: AUD-S1")
    def test_aud_s1(self) -> None:
        """AUD-S1

        Every write leaves an audit row and an outbox row in the same transaction (AUD-01, AC-AUD1).
        """

    @skip("pending: AUD-S2")
    def test_aud_s2(self) -> None:
        """AUD-S2

        The audit table rejects update and delete (AUD-01, AC-AUD1).
        """

    @skip("pending: AUD-S4")
    def test_aud_s4(self) -> None:
        """AUD-S4

        Every model output is logged with its review state (AUD-02).
        """

    @skip("pending: AUD-S5")
    def test_aud_s5(self) -> None:
        """AUD-S5

        A problem report is resolved by a proposal (AUD-03).
        """

    @skip("pending: AUD-S6")
    def test_aud_s6(self) -> None:
        """AUD-S6

        Retention per tenant purges what it may and keeps append-only rows (AUD-04).
        """

    @skip("pending: AUD-S7")
    def test_aud_s7(self) -> None:
        """AUD-S7

        Mixed tables show library rows to everyone and tenant rows to their tenant (AUD-01).
        """

    @skip("pending: ADM-S4")
    def test_adm_s4(self) -> None:
        """ADM-S4

        The platform console offers each surface to the platform role that owns it (ADM-02).
        """

    @skip("pending: ADM-S5")
    def test_adm_s5(self) -> None:
        """ADM-S5

        System health names what is wrong (ADM-02).
        """

    @skip("pending: ADM-S6")
    def test_adm_s6(self) -> None:
        """ADM-S6

        Tenants, plans and support access are managed from the console (ADM-02).
        """
