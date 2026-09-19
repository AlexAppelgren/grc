"""Scenario stubs for the tenants app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ADM, TEN.
"""

from unittest import skip

from django.test import TestCase


class TenantsScenarioTests(TestCase):
    """Scenario tests for apps.tenants, one method per @integration scenario."""

    @skip("pending: TEN-S1")
    def test_ten_s1(self) -> None:
        """TEN-S1

        A tenant profile holds timezone, languages and the onboarding checklist (TEN-01).
        """

    @skip("pending: TEN-S2")
    def test_ten_s2(self) -> None:
        """TEN-S2

        Legal entities and products are scoped like obligations (TEN-02).
        """

    @skip("pending: TEN-S3")
    def test_ten_s3(self) -> None:
        """TEN-S3

        A team can own work and the ownership survives a member leaving (TEN-03).
        """

    @skip("pending: TEN-S4")
    def test_ten_s4(self) -> None:
        """TEN-S4

        An out-of-office delegate receives approvals and reminders (TEN-04).
        """

    @skip("pending: TEN-S5")
    def test_ten_s5(self) -> None:
        """TEN-S5

        Removing a member with open work offers bulk reassignment (TEN-05).
        """

    @skip("pending: TEN-S6")
    def test_ten_s6(self) -> None:
        """TEN-S6

        A support access grant is visible, time-boxed and logged (TEN-06).
        """

    @skip("pending: ADM-S1")
    def test_adm_s1(self) -> None:
        """ADM-S1

        Tenant admin surfaces are gated by their own permissions (ADM-01, ADM-03).
        """

    @skip("pending: ADM-S3")
    def test_adm_s3(self) -> None:
        """ADM-S3

        User administration and business configuration can sit with different people (ADM-03).
        """
