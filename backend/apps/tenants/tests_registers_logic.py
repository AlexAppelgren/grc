"""From a supervisor's register to scope terms (TEN-07, FP-05; PUBLIC_REGISTERS.md 4.1).

The facts are the mock register's Example Group, the E2E seed's companies; the terms are the
seeded taxonomy, so a key in `register_terms.json` that the taxonomy does not hold fails here
rather than being dropped in silence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase

from apps.library import testing as library_build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared.adapters.registers import MockRegisters
from apps.taxonomy.models import TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants import registers_logic
from apps.tenants.schemas import RegisterFacts

FI = "fi"
LICENCE_BOUND = ("regime", "service_type", "licensed_activity")


def mapped_terms() -> set[tuple[str, str]]:
    raw = json.loads(registers_logic.MAPPING_FILE.read_text(encoding="utf-8"))
    terms = {term for spec in raw.values() if isinstance(spec, dict) for terms in spec["categories"].values() for term in terms}
    terms |= {term for spec in raw.values() if isinstance(spec, dict) for rule in spec["licences"] for term in rule["terms"]}
    return {(term.split(":")[0], term.split(":")[1]) for term in terms}


class RegisterWorld(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        library_build.authority(key="fi", short_name="FI")
        library_build.authority(key="finanstilsynet-dk", short_name="Finanstilsynet", jurisdiction="dk")

    def facts(self, number: str) -> RegisterFacts:
        read = MockRegisters().licence_facts(FI, number)
        assert read is not None
        return registers_logic.register_facts(FI, read)


class DerivedTerms(RegisterWorld):
    def test_the_bank_derives_what_its_licences_allow(self) -> None:
        self.assertEqual(
            registers_logic.derived_terms(FI, self.facts("556000-0001")),
            {
                "legal_entity": {"bank", "investment_firm"},
                "regime": {"banking", "payments", "securities", "insurance"},
                "service_type": {"custody", "advice", "portfolio_management", "insurance_distribution"},
                "licensed_activity": {"card_issuing", "card_acquiring"},
            },
        )

    def test_the_fund_company_and_the_life_insurer(self) -> None:
        self.assertEqual(
            registers_logic.derived_terms(FI, self.facts("556000-0003")),
            {"legal_entity": {"fund_company"}, "regime": {"securities"}, "service_type": {"portfolio_management"}},
        )
        self.assertEqual(
            registers_logic.derived_terms(FI, self.facts("516000-0002")),
            {"legal_entity": {"insurer"}, "regime": {"insurance"}, "service_type": {"insurance_distribution"}},
        )

    def test_a_company_gone_from_the_register_derives_nothing_and_knows_no_main_business(self) -> None:
        gone = self.facts("556000-0003").model_copy(update={"licences": [], "branches": [], "listed": False})
        self.assertEqual(registers_logic.derived_terms(FI, gone), {})
        self.assertFalse(registers_logic.knows_main_business(FI, gone))
        self.assertTrue(registers_logic.knows_main_business(FI, self.facts("556000-0003")))

    def test_an_authority_without_a_mapping_derives_nothing(self) -> None:
        self.assertEqual(registers_logic.derived_terms("eba", self.facts("556000-0001")), {})
        self.assertEqual(registers_logic.derivable_terms("eba"), {})

    def test_the_type_is_the_first_legal_entity_of_the_main_business(self) -> None:
        self.assertEqual(registers_logic.entity_type(FI, self.facts("556000-0001")), "bank")
        self.assertEqual(registers_logic.entity_type(FI, self.facts("516000-0002")), "insurer")
        unknown = self.facts("556000-0001").model_copy(update={"main_business": "Annan verksamhet"})
        self.assertIsNone(registers_logic.entity_type(FI, unknown))
        self.assertTrue(registers_logic.knows_main_business(FI, unknown))
        self.assertFalse(registers_logic.knows_main_business(FI, unknown.model_copy(update={"main_business": "Okänt bolag"})))

    def test_what_maps_to_nothing_is_listed_in_the_registers_order(self) -> None:
        self.assertEqual(registers_logic.unmapped(FI, self.facts("556000-0001")), ["IM_MR_SA"])
        self.assertEqual(registers_logic.unmapped(FI, self.facts("556000-0003")), [])
        odd = self.facts("556000-0001").model_copy(update={"main_business": "Okänt bolag", "other_businesses": ["Värdepappersbolag", "Nytt slag"]})
        self.assertEqual(registers_logic.unmapped(FI, odd), ["Okänt bolag", "Nytt slag", "IM_MR_SA"])

    def test_the_derivable_terms_are_the_briefs(self) -> None:
        derivable = registers_logic.derivable_terms(FI)
        self.assertEqual(derivable["regime"], {"banking", "securities", "insurance", "payments"})
        self.assertEqual(derivable["service_type"], {"portfolio_management", "advice", "custody", "insurance_distribution"})
        self.assertEqual(derivable["licensed_activity"], {"card_issuing", "card_acquiring"})
        self.assertEqual(
            derivable["legal_entity"],
            {"bank", "credit_market_company", "investment_firm", "fund_company", "insurer", "payment_institution", "emoney_institution"},
        )
        self.assertEqual(set(derivable), {"legal_entity", *LICENCE_BOUND})

    def test_every_term_the_mapping_names_is_an_active_term_of_the_seeded_taxonomy(self) -> None:
        missing = sorted(
            f"{dimension}:{key}"
            for dimension, key in mapped_terms()
            if not TaxonomyTerm.objects.filter(dimension__key=dimension, key=key, active=True).exists()
        )
        self.assertEqual(missing, [], "register_terms.json names terms the taxonomy does not hold")

    def test_entity_terms_label_the_live_ones_and_drop_the_rest(self) -> None:
        refs = registers_logic.entity_terms({"bank", "fund_company", "no_such_type"}, ["en"])
        self.assertEqual(set(refs), {"bank", "fund_company"})
        self.assertEqual(refs["bank"].key, "bank")
        self.assertEqual(registers_logic.entity_terms(set(), ["en"]), {})


class BusinessNames(SimpleTestCase):
    def test_a_name_holding_a_comma_is_one_name(self) -> None:
        self.assertEqual(
            registers_logic.split_businesses(FI, "Värdepappersbolag, Riksbolag, livförsäkringar, Stort Institut"),
            (["Värdepappersbolag", "Riksbolag, livförsäkringar", "Stort Institut"], []),
        )

    def test_unknown_names_are_the_comma_separated_rest_in_order(self) -> None:
        self.assertEqual(
            registers_logic.split_businesses(FI, "Nytt slag, Riksbolag, livförsäkringar, Annat, Försäkringsdistribution"),
            (["Riksbolag, livförsäkringar", "Försäkringsdistribution"], ["Nytt slag", "Annat"]),
        )
        self.assertEqual(registers_logic.split_businesses(FI, ""), ([], []))

    def test_a_known_name_counts_only_as_a_whole_item(self) -> None:
        # `Fondbolag` inside `Fondbolagsgruppen` is not the business `Fondbolag`.
        self.assertEqual(registers_logic.split_businesses(FI, "Fondbolagsgruppen, Fondbolag"), (["Fondbolag"], ["Fondbolagsgruppen"]))


class MappingFileShape(SimpleTestCase):
    def load(self, content: object) -> object:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "register_terms.json"
            path.write_text(json.dumps(content), encoding="utf-8")
            with mock.patch.object(registers_logic, "MAPPING_FILE", path):
                return registers_logic._mappings.__wrapped__()

    def test_a_mapping_of_another_shape_refuses_to_load(self) -> None:
        for case, content in {
            "no licences": {"fi": {"categories": {}}},
            "a term without a dimension": {"fi": {"categories": {"Fondbolag": ["fund_company"]}, "licences": []}},
            "a phrase missing": {"fi": {"categories": {}, "licences": [{"terms": ["regime:banking"]}]}},
            "terms not a list": {"fi": {"categories": {}, "licences": [{"contains": "bank", "terms": "regime:banking"}]}},
        }.items():
            with self.subTest(case), self.assertRaises(ImproperlyConfigured):
                self.load(content)

    def test_the_shipped_mapping_loads(self) -> None:
        self.assertIn("Bankaktiebolag", registers_logic._mappings()[FI].categories)


class CountriesAndAuthorities(RegisterWorld):
    def test_branch_countries_are_matched_on_the_jurisdiction_labels(self) -> None:
        facts = self.facts("556000-0001")
        self.assertEqual(registers_logic.branch_jurisdictions(facts), {"dk", "no"})
        self.assertEqual([branch.jurisdiction for branch in facts.branches], ["dk", "no"])
        abroad = facts.model_copy(
            update={"branches": [*facts.branches, facts.branches[0].model_copy(update={"country_name": "Hongkong"})]}
        )
        self.assertEqual(registers_logic.branch_jurisdictions(abroad), {"dk", "no"})
        self.assertEqual(registers_logic.branch_jurisdictions(facts.model_copy(update={"branches": []})), set())

    def test_the_authority_is_the_one_whose_register_is_read_for_the_country(self) -> None:
        sweden = registers_logic.authority_for_country("SE")
        assert sweden is not None
        self.assertEqual(sweden.key, "fi")
        # Denmark has an authority in the library, but no register of it is read.
        self.assertIsNone(registers_logic.authority_for_country("DK"))
        self.assertIsNone(registers_logic.authority_for_country("EE"))
        self.assertIsNone(registers_logic.authority_for_country(""))
        self.assertEqual(set(registers_logic.authorities({"fi", "nope"})), {"fi"})

    def test_the_facts_keep_the_registers_order_and_wording(self) -> None:
        facts = self.facts("556000-0001")
        self.assertEqual(facts.other_businesses, ["Värdepappersbolag", "Försäkringsdistribution", "Medelstort institut"])
        self.assertTrue(facts.listed)
        self.assertEqual(facts.licences[0].text, "Tillstånd att driva bankrörelse, enligt lag 2004:297 om bank- och finansieringsrörelse")
