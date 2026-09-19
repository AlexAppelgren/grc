"""Scenario stubs for the agents app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: AGT.
"""

from unittest import skip

from django.test import TestCase


class AgentsScenarioTests(TestCase):
    """Scenario tests for apps.agents, one method per @integration scenario."""

    @skip("pending: AGT-S1")
    def test_agt_s1(self) -> None:
        """AGT-S1

        A run opens, logs checks, finds similar, registers, proposes and closes (AGT-01).
        """

    @skip("pending: AGT-S2")
    def test_agt_s2(self) -> None:
        """AGT-S2

        Registering a change is idempotent across retries (AGT-01).
        """

    @skip("pending: AGT-S3")
    def test_agt_s3(self) -> None:
        """AGT-S3

        Agents read the vocabularies at run start and may use existing keys only (AGT-02).
        """

    @skip("pending: AGT-S4")
    def test_agt_s4(self) -> None:
        """AGT-S4

        Agent definitions are versioned and owned by the platform (AGT-03).
        """

    @skip("pending: AGT-S5")
    def test_agt_s5(self) -> None:
        """AGT-S5

        A tenant controls its agents without touching their instructions (AGT-04).
        """

    @skip("pending: AGT-S6")
    def test_agt_s6(self) -> None:
        """AGT-S6

        The budget cap pauses runs and the AI off switch stops every model call (AGT-04).
        """

    @skip("pending: AGT-S7")
    def test_agt_s7(self) -> None:
        """AGT-S7

        Research requests ask an agent to check, research or re-tag (AGT-05).
        """

    @skip("pending: AGT-S8")
    def test_agt_s8(self) -> None:
        """AGT-S8

        The runner is an adapter with a mock and the app is the scheduler of record (AGT-06).
        """

    @skip("pending: AGT-S9")
    def test_agt_s9(self) -> None:
        """AGT-S9

        Fetched content is screened for embedded instructions (AGT-07).
        """
