"""Scenario stubs for the search app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: SRC.
"""

from unittest import skip

from django.test import TestCase


class SearchScenarioTests(TestCase):
    """Scenario tests for apps.search, one method per @integration scenario."""

    @skip("pending: SRC-S1")
    def test_src_s1(self) -> None:
        """SRC-S1

        An identifier is won by keyword and a concept by vector in one query (SRC-01, AC-SRC1).

        Operations: `search`, and `findSimilar`, which ranks the same chunks for an
        agent's key. Both answer 501 not_built until the hybrid query lands.
        """

    @skip("pending: SRC-S2")
    def test_src_s2(self) -> None:
        """SRC-S2

        Chunks are indexed per language with the matching text search configuration (SRC-01).
        """

    @skip("pending: SRC-S3")
    def test_src_s3(self) -> None:
        """SRC-S3

        Filters come from vocabularies, "as of" picks the version, and each hit states its match kind (SRC-02).
        """

    @skip("pending: SRC-S4")
    def test_src_s4(self) -> None:
        """SRC-S4

        An answer cites every statement and flags pending changes (SRC-03, AC-SRC2).

        Operations: `ask`. Answers 501 not_built until the Ask backend lands.
        """

    @skip("pending: SRC-S5")
    def test_src_s5(self) -> None:
        """SRC-S5

        A question without support returns "no answer" (SRC-03, AC-SRC2).
        """

    @skip("pending: SRC-S6")
    def test_src_s6(self) -> None:
        """SRC-S6

        The Ask question is the only tenant text sent to a model, and a tenant can switch it off (SRC-03).
        """

    @skip("pending: SRC-S7")
    def test_src_s7(self) -> None:
        """SRC-S7

        Saved searches notify and show what changed since the last visit (SRC-04).
        """

    @skip("pending: SRC-S8")
    def test_src_s8(self) -> None:
        """SRC-S8

        The evaluation set gates releases (SRC-05).

        Operations: `rateAnswer`, the reader's verdict the evaluation set reads back.
        It answers 501 not_built until the Ask backend lands.
        """

    @skip("pending: SRC-S9")
    def test_src_s9(self) -> None:
        """SRC-S9

        Search and Ask stay within their budgets and are rate limited (SRC-01, NFR-02).
        """

    @skip("pending: SRC-S11")
    def test_src_s11(self) -> None:
        """SRC-S11

        Only the library is indexed in R1 (SRC-01).
        """

    @skip("pending: SRC-S12 (INV-08, chunk 7)")
    def test_src_s12(self) -> None:
        """SRC-S12

        A question about a standard's control gets "no answer" (SRC-03, SRC-05, INV-08).
        """

    @skip("pending: SRC-S13 (REG-08, chunk 8)")
    def test_src_s13(self) -> None:
        """SRC-S13

        Nothing a tenant writes under a standard reaches the index or a model (REG-08, SRC-01).
        """
