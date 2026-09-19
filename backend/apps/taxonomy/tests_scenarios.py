"""Scenario stubs for the taxonomy app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: FP, I18N, VOC.
"""

from unittest import skip

from django.test import TestCase


class TaxonomyScenarioTests(TestCase):
    """Scenario tests for apps.taxonomy, one method per @integration scenario."""

    @skip("pending: VOC-S1")
    def test_voc_s1(self) -> None:
        """VOC-S1

        Extendable lists are rows in three tiers and kinds stay in code (VOC-01).
        """

    @skip("pending: VOC-S2")
    def test_voc_s2(self) -> None:
        """VOC-S2

        An admin adds a change type, a tag and a sub-status without a deploy (VOC-01, AC-VOC1).
        """

    @skip("pending: VOC-S3")
    def test_voc_s3(self) -> None:
        """VOC-S3

        The vocabulary screen renders the real pill with usage count, rename and reorder (VOC-02).
        """

    @skip("pending: VOC-S4")
    def test_voc_s4(self) -> None:
        """VOC-S4

        Retiring a used value keeps history readable and leaves pickers (VOC-02, AC-VOC2).
        """

    @skip("pending: VOC-S5")
    def test_voc_s5(self) -> None:
        """VOC-S5

        Merging re-points duplicates in one audited transaction (VOC-02).
        """

    @skip("pending: VOC-S6")
    def test_voc_s6(self) -> None:
        """VOC-S6

        Create where you use it offers Create or Suggest by permission (VOC-03).
        """

    @skip("pending: VOC-S7")
    def test_voc_s7(self) -> None:
        """VOC-S7

        A near-duplicate is refused with the near match offered (VOC-03, AC-VOC3).
        """

    @skip("pending: VOC-S8")
    def test_voc_s8(self) -> None:
        """VOC-S8

        Statuses live inside fixed categories and a category never goes empty (VOC-04).
        """

    @skip("pending: VOC-S9")
    def test_voc_s9(self) -> None:
        """VOC-S9

        Tenant scales map to fixed ordinals and the tone follows the ordinal (VOC-05).
        """

    @skip("pending: VOC-S10")
    def test_voc_s10(self) -> None:
        """VOC-S10

        Reason lists drive dismissal, closure and risk acceptance (VOC-06).
        """

    @skip("pending: VOC-S11")
    def test_voc_s11(self) -> None:
        """VOC-S11

        A library vocabulary change goes through the proposal queue (VOC-07).
        """

    @skip("pending: VOC-S12")
    def test_voc_s12(self) -> None:
        """VOC-S12

        Bulk tagging from a list previews and writes one audit entry (VOC-08).
        """

    @skip("pending: VOC-S13")
    def test_voc_s13(self) -> None:
        """VOC-S13

        Tenant configuration is versioned, exportable and importable (VOC-09).
        """

    @skip("pending: VOC-S14")
    def test_voc_s14(self) -> None:
        """VOC-S14

        System rows can be relabelled but not removed, and the API returns key and kind (VOC-01).
        """

    @skip("pending: FP-S1")
    def test_fp_s1(self) -> None:
        """FP-S1

        A record matches when every dimension it carries has a term in the footprint (FP-01).
        """

    @skip("pending: FP-S2")
    def test_fp_s2(self) -> None:
        """FP-S2

        A footprint change previews, waits for a second person and audits per term (FP-02, AC-FP1).
        """

    @skip("pending: FP-S3")
    def test_fp_s3(self) -> None:
        """FP-S3

        The requester cannot approve their own footprint change (FP-02).
        """

    @skip("pending: FP-S4")
    def test_fp_s4(self) -> None:
        """FP-S4

        Every surface respects the footprint and offers a way to look outside it (FP-03).
        """

    @skip("pending: I18N-S1")
    def test_i18n_s1(self) -> None:
        """I18N-S1

        Languages and jurisdictions are rows, never columns or branches (I18N-01).
        """

    @skip("pending: I18N-S2")
    def test_i18n_s2(self) -> None:
        """I18N-S2

        Translations are rows with the original marked and machine output labelled (I18N-01).
        """
