"""Scenario stubs for the billing app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: NFR.
"""

from unittest import skip

from django.test import TestCase


class BillingScenarioTests(TestCase):
    """Scenario tests for apps.billing, one method per @integration scenario."""

    @skip("pending: NFR-S17")
    def test_nfr_s17(self) -> None:
        """NFR-S17

        A plan holds limits and a price as an integer minor unit (NFR-05).
        """

    @skip("pending: NFR-S18")
    def test_nfr_s18(self) -> None:
        """NFR-S18

        Plan limits are enforced where the tenant acts (NFR-05).
        """

    @skip("pending: NFR-S19")
    def test_nfr_s19(self) -> None:
        """NFR-S19

        Usage is metered and visible to the tenant and the platform (NFR-05).
        """
