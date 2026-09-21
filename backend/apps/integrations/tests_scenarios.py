"""Scenario stubs for the integrations app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ACC, INT.
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


class IntegrationsAgentAccessScenarioTests(TestCase):
    """Agent access scenarios for apps.integrations (PRD 0.5 module ACC), one method per
    @integration heading in app.md. Skipped until chunk 11 builds them."""

    @skip("pending: ACC-S7")
    def test_acc_s7(self) -> None:
        """ACC-S7

        The MCP server is one router over the same gates, and every credential is read-only (ACC-05, AC-ACC4).
        """

    @skip("pending: ACC-S8")
    def test_acc_s8(self) -> None:
        """ACC-S8

        Pagination, the rate limit, the budget cap and the AI off switch bound every call (ACC-09).
        """
