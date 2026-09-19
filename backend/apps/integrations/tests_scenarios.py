"""Scenario stubs for the integrations app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: INT.
"""

from unittest import skip

from django.test import TestCase


class IntegrationsScenarioTests(TestCase):
    """Scenario tests for apps.integrations, one method per @integration scenario."""

    @skip("pending: INT-S1")
    def test_int_s1(self) -> None:
        """INT-S1

        A signed webhook is delivered from the outbox with a delivery log (INT-01).
        """

    @skip("pending: INT-S2")
    def test_int_s2(self) -> None:
        """INT-S2

        Webhook delivery and inbound handlers are idempotent (INT-01).
        """

    @skip("pending: INT-S3")
    def test_int_s3(self) -> None:
        """INT-S3

        Actions export as tickets (INT-02).
        """

    @skip("pending: INT-S4")
    def test_int_s4(self) -> None:
        """INT-S4

        Audit events stream to the customer's SIEM (INT-03).
        """

    @skip("pending: INT-S5")
    def test_int_s5(self) -> None:
        """INT-S5

        Subscriptions store keys so a rename changes nothing (INT-01).
        """
