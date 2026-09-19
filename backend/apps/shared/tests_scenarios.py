"""Scenario stubs for the shared app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Several of these are already proven by the structural guards in this app
(tests_rls.py, tests_production_guard.py, tests_route_permissions.py,
tests_health.py, ...). The stubs stay until each scenario is un-skipped
against the guard that proves it, so the coverage gate reads one source.

Prefixes hosted: NFR (S1..S16), I18N (S3, S4 are @e2e only, no stub).
"""

from unittest import skip

from django.test import TestCase


class SharedScenarioTests(TestCase):
    """Scenario tests for apps.shared, one method per @integration scenario."""

    @skip("pending: NFR-S1")
    def test_nfr_s1(self) -> None:
        """NFR-S1

        A record of tenant A requested by tenant B answers 404 on every tenant route.
        """

    @skip("pending: NFR-S2")
    def test_nfr_s2(self) -> None:
        """NFR-S2

        The app refuses to boot on a role that can bypass row-level security.
        """

    @skip("pending: NFR-S3")
    def test_nfr_s3(self) -> None:
        """NFR-S3

        Every tenant table has row-level security enabled, forced and with a policy.
        """

    @skip("pending: NFR-S4")
    def test_nfr_s4(self) -> None:
        """NFR-S4

        An unset tenant matches no rows.
        """

    @skip("pending: NFR-S5")
    def test_nfr_s5(self) -> None:
        """NFR-S5

        Every tenant task is wrapped in @tenant_task and every beat entry exists.
        """

    @skip("pending: NFR-S6")
    def test_nfr_s6(self) -> None:
        """NFR-S6

        Every API response carries Server-Timing and the budget is enforced.
        """

    @skip("pending: NFR-S10")
    def test_nfr_s10(self) -> None:
        """NFR-S10

        Tone is never chosen by a person and the API never sends a phrase.
        """

    @skip("pending: NFR-S11")
    def test_nfr_s11(self) -> None:
        """NFR-S11

        An unrecognised environment name is treated as production.
        """

    @skip("pending: NFR-S12")
    def test_nfr_s12(self) -> None:
        """NFR-S12

        The boot guards refuse an unsafe deployed configuration.
        """

    @skip("pending: NFR-S13")
    def test_nfr_s13(self) -> None:
        """NFR-S13

        Every route is permission-gated or ungated by design with a reason.
        """

    @skip("pending: NFR-S14")
    def test_nfr_s14(self) -> None:
        """NFR-S14

        /health/ names the failing component.
        """

    @skip("pending: NFR-S15")
    def test_nfr_s15(self) -> None:
        """NFR-S15

        Tenant content and personal data beyond name and id never reach logs or Sentry.
        """

    @skip("pending: NFR-S16")
    def test_nfr_s16(self) -> None:
        """NFR-S16

        Every error uses one shape and an empty answer is 200.
        """
