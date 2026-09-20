"""Scenario stubs for the library app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: INV.
"""

from unittest import skip

from django.test import TestCase


class LibraryScenarioTests(TestCase):
    """Scenario tests for apps.library, one method per @integration scenario."""

    @skip("pending: INV-S1")
    def test_inv_s1(self) -> None:
        """INV-S1

        An instrument carries its identity, dates and lineage (INV-01).
        """

    @skip("pending: INV-S2")
    def test_inv_s2(self) -> None:
        """INV-S2

        The provision tree holds verbatim text versions (INV-02).
        """

    @skip("pending: INV-S3")
    def test_inv_s3(self) -> None:
        """INV-S3

        An obligation states the duty and its facets (INV-03).
        """

    @skip("pending: INV-S4")
    def test_inv_s4(self) -> None:
        """INV-S4

        "As of" returns the version in force on a date (INV-04, AC-INV1).
        """

    @skip("pending: INV-S5")
    def test_inv_s5(self) -> None:
        """INV-S5

        The diff between two versions is at sentence level (INV-04, AC-INV1).
        """

    @skip("pending: INV-S6")
    def test_inv_s6(self) -> None:
        """INV-S6

        Text exists in the original language with labelled translations (INV-05).
        """

    @skip("pending: INV-S7")
    def test_inv_s7(self) -> None:
        """INV-S7

        Every record has a source link, a last-verified date and a way to report it (INV-06).
        """

    @skip("pending: INV-S8")
    def test_inv_s8(self) -> None:
        """INV-S8

        The re-verification stamp is the only write outside a proposal (INV-06).
        """

    @skip("pending: INV-S9")
    def test_inv_s9(self) -> None:
        """INV-S9

        Tenant-private records are visible to their owner only (INV-07).
        """

    @skip("pending: INV-S10")
    def test_inv_s10(self) -> None:
        """INV-S10

        Legal dates are plain dates with a precision (INV-01, INV-02).
        """

    @skip("pending: INV-S11 (INV-08, chunk 3)")
    def test_inv_s11(self) -> None:
        """INV-S11

        An edition of a standard is an instrument with public facts and no text (INV-01, INV-02, INV-08).
        """

    @skip("pending: INV-S12 (INV-08, chunk 3)")
    def test_inv_s12(self) -> None:
        """INV-S12

        Every instrument carries a regime from the regime dimension (INV-01, INV-08).
        """

    @skip("pending: INV-S13 (INV-07, chunk 13)")
    def test_inv_s13(self) -> None:
        """INV-S13

        A private record's text never reaches a model, the index or another bank (INV-07).
        """
