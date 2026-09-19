"""Scenario stubs for the watch app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: WAT.
"""

from unittest import skip

from django.test import TestCase


class WatchScenarioTests(TestCase):
    """Scenario tests for apps.watch, one method per @integration scenario."""

    @skip("pending: WAT-S1")
    def test_wat_s1(self) -> None:
        """WAT-S1

        The source registry and coverage log show what was checked and with what result (WAT-01).
        """

    @skip("pending: WAT-S2")
    def test_wat_s2(self) -> None:
        """WAT-S2

        One record per reform carries a timeline with partial dates (WAT-02).
        """

    @skip("pending: WAT-S3")
    def test_wat_s3(self) -> None:
        """WAT-S3

        A known stableKey merges duplicates and returns the existing change (WAT-02, AC-WAT1).
        """

    @skip("pending: WAT-S4")
    def test_wat_s4(self) -> None:
        """WAT-S4

        Types, flags and scope come from vocabularies and stay suggestions until confirmed (WAT-03).
        """

    @skip("pending: WAT-S5")
    def test_wat_s5(self) -> None:
        """WAT-S5

        An unknown key answers unknown_key with the valid keys (WAT-03, AC-WAT2).
        """

    @skip("pending: WAT-S6")
    def test_wat_s6(self) -> None:
        """WAT-S6

        Links to affected obligations carry a confidence and are confirmed by a person (WAT-04).
        """

    @skip("pending: WAT-S7")
    def test_wat_s7(self) -> None:
        """WAT-S7

        The "So what?" is AI-drafted until a person confirms or rewrites it per tenant (WAT-05).
        """

    @skip("pending: WAT-S8")
    def test_wat_s8(self) -> None:
        """WAT-S8

        A tenant requests a source and private sources stay private (WAT-06).
        """

    @skip("pending: WAT-S10 (WAT-07, chunk 5)")
    def test_wat_s10(self) -> None:
        """WAT-S10

        A new edition of a standard is one change, and only tenants that follow it see it (WAT-02, WAT-07, CAS-01).
        """

    @skip("pending: WAT-S11 (WAT-07, chunk 5)")
    def test_wat_s11(self) -> None:
        """WAT-S11

        Every change carries a regime, a standard term needs a standards body, and a publisher's page keeps no snapshot (WAT-01, WAT-03, WAT-07).
        """
