"""Scenario stubs for the library app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: INV.

The scenarios that read an obligation (INV-S3 to INV-S6) run against the sample library
the prototype's data seeds, so what a reader sees is what the product ships with. INV-S4
and INV-S5 add versions of their own, dated, so no test depends on the day it runs.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest import skip

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from apps.identity.models import User
from apps.library import testing as build
from apps.library.models import Obligation, ObligationVersion
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import load_library, seed_authorities
from apps.shared import factories
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

URL = "/api/v1/obligations"
D = datetime.date
# The two dates INV-S4 and INV-S5 compare, fixed: research payments version 2 takes effect
# on 2026-10-01, and nothing here reads the clock.
FIRST_VERSION = D(2025, 1, 1)
SECOND_VERSION = D(2026, 10, 1)
FIRST_SUMMARY = "Research is paid from own resources. The institution keeps the records."
SECOND_SUMMARY = "Research may be paid jointly with execution. The institution keeps the records."


class LibraryScenarioTests(TestCase):
    """Scenario tests for apps.library, one method per @integration scenario."""

    tenant: Tenant
    reader: User
    versioned: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        seed_authorities()
        load_library()
        cls.tenant = factories.tenant(slug="inventory-reader")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.versioned = build.obligation(
            build.instrument(key="fffs-2017-2-versions", short_name="FFFS 2017:2", regime="regime:securities"),
            key="obl-research-payments-versions",
            titles={"en": "Pay for research only under the permitted models"},
            ref_label="Third-party payments",
            versions=((FIRST_VERSION, {"en": FIRST_SUMMARY}), (SECOND_VERSION, {"en": SECOND_SUMMARY})),
        )

    def read(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.get(path, params or {}, **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def card(self, stable_key: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.read(f"{URL}/{Obligation.objects.get(stable_key=stable_key).id}", params)

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

    def test_inv_s3(self) -> None:
        """INV-S3

        An obligation states the duty and its facets (INV-03).
        """
        card = self.card("obl-appropriateness")
        self.assertEqual(card["title"]["text"], "Assess appropriateness before non-advised trades in complex instruments")
        self.assertTrue(card["summary"]["text"].startswith("Before providing a non-advised service"), card["summary"])
        self.assertEqual(card["dutyType"]["key"], "conduct", "a key and a label, never a phrase to match on")
        self.assertEqual(
            (card["productScope"], card["triggerFrequency"], card["retention"], card["sanctionExposure"]),
            ("Complex instruments", "Per order in a complex instrument", "5 years", "FI remark, warning or sanction fee"),
        )
        scope = {entry["dimension"]["key"]: [term["key"] for term in entry["terms"]] for entry in card["scope"]}
        self.assertEqual(scope["service_type"], ["non_advised", "execution_only"])
        self.assertEqual(scope["client_category"], ["retail"])
        self.assertEqual(scope["regime"], ["securities"], "the instrument's regime is part of the obligation's scope")
        self.assertEqual(scope["lifecycle_stage"], ["pre_trade"])
        self.assertEqual(
            [(provision["refLabel"], provision["path"]) for provision in card["provisions"]],
            [("9 kap.", "LVM > 9 kap.")],
            "the provision it comes from, by reference and path; the verbatim text is the tree's",
        )
        self.assertEqual(
            [(related["instrument"]["key"], related["binding"], related["relation"]["key"]) for related in card["related"]],
            [("esma-35-43-3006", False, "related")],
        )
        self.assertEqual((card["instrument"]["key"], card["regime"]["key"], card["bindingLevel"]["key"]), ("sfs-2007-528", "securities", "act"))
        self.assertEqual(card["binding"], True)

    def test_inv_s4(self) -> None:
        """INV-S4

        "As of" returns the version in force on a date (INV-04, AC-INV1).
        """
        path = f"{URL}/{self.versioned.id}"
        early = self.read(path, {"asOf": "2026-06-30"})
        self.assertEqual(early["version"]["versionNumber"], 1)
        self.assertEqual(early["summary"]["text"], FIRST_SUMMARY)
        on_the_day = self.read(path, {"asOf": SECOND_VERSION.isoformat()})
        self.assertEqual(on_the_day["version"]["versionNumber"], 2)
        self.assertEqual(on_the_day["summary"]["text"], SECOND_SUMMARY)
        self.assertEqual(
            [(row["versionNumber"], row["effectiveFrom"]["date"], row["effectiveTo"]) for row in early["versions"]],
            [(1, "2025-01-01", {"date": "2026-09-30", "precision": "day"}), (2, "2026-10-01", None)],
        )
        # Nothing has rewritten the first version, and nothing can: the table is append-only
        # whatever the write path, so "as of" reads a history no correction can change.
        first = ObligationVersion.objects.get(obligation=self.versioned, version_number=1)
        with self.assertRaisesMessage(DatabaseError, "obligation_version is append-only"), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE obligation_version SET effective_from = %s WHERE id = %s", ["2027-01-01", first.id])
        first.refresh_from_db()
        self.assertEqual(first.effective_from, FIRST_VERSION)

    def test_inv_s5(self) -> None:
        """INV-S5

        The diff between two versions is at sentence level (INV-04, AC-INV1).
        """
        diff = self.read(f"{URL}/{self.versioned.id}/diff")
        self.assertEqual((diff["fromVersion"], diff["toVersion"]), (1, 2), "the latest version against the one before it")
        self.assertEqual(
            [(segment["op"], segment["text"]) for segment in diff["segments"]],
            [
                ("delete", "Research is paid from own resources."),
                ("insert", "Research may be paid jointly with execution."),
                ("equal", "The institution keeps the records."),
            ],
            "the changed sentence is marked and the others are left alone",
        )
        self.assertEqual(
            (diff["fromEffective"]["date"], diff["toEffective"]["date"]),
            (FIRST_VERSION.isoformat(), SECOND_VERSION.isoformat()),
            "the screen names the two effective dates being compared",
        )

    def test_inv_s6(self) -> None:
        """INV-S6

        Text exists in the original language with labelled translations (INV-05).
        """
        # The reader's language order is en; the research payment summary was written in sv.
        card = self.card("obl-research-payments")
        self.assertEqual(card["summary"]["language"], "en")
        self.assertTrue(card["summary"]["isMachine"], "a machine translation stays labelled until a person confirms it")
        self.assertFalse(card["summary"]["isOriginal"])
        original = next(text for text in card["translations"] if text["isOriginal"])
        self.assertEqual(original["language"], "sv", "the original is there for 'Show original'")
        self.assertFalse(original["isMachine"])
        self.assertEqual({text["language"] for text in card["translations"]}, {"en", "sv"})
        swedish = self.read(f"{URL}/{self.versioned.id}/diff", {"lang": "sv"})
        self.assertEqual(swedish["language"], "en", "a language neither version has falls back to one both have")

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

    @skip("pending: INV-S14 (D-62, chunk 4 c4-agent-approver)")
    def test_inv_s14(self) -> None:
        """INV-S14

        A record an agent confirmed reads as machine-confirmed (INV-05, INV-06, PRO-02).
        """
