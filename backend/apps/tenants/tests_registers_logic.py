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
from apps.shared.tenancy import library_write
from apps.taxonomy.models import TaxonomyTerm, TermDimension
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants import registers_logic
from apps.tenants.schemas import RegisterFacts, RegisterFactsLicence
from apps.tenants.testing import branch_jurisdictions, split_businesses

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
        # Its business names are still read, and none gives a term.
        self.assertEqual(registers_logic.line_terms(FI, gone), [("Fondbolag", []), ("Auktoriserad AIF-förvaltare", [])])
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

    def test_each_line_names_the_terms_it_gives_in_the_registers_order(self) -> None:
        """TEN-S15's rule, `term_sources` read the other way round: every business name and
        licence line with the terms the mapping gives it, each term once. Wording the mapping
        does not know gives None; wording it knows that adds nothing gives no term."""
        facts = self.facts("556000-0001")
        lines = registers_logic.line_terms(FI, facts)
        self.assertEqual([line for line, _ in lines], [facts.main_business, *facts.other_businesses, *(licence.text for licence in facts.licences)])
        given = dict(lines)
        credit_institution = [("regime", "banking"), ("regime", "payments"), ("service_type", "custody"), ("licensed_activity", "card_issuing"), ("licensed_activity", "card_acquiring")]
        self.assertEqual(given["Bankaktiebolag"], [("legal_entity", "bank"), *credit_institution])
        self.assertEqual(given["Värdepappersbolag"], [("legal_entity", "investment_firm"), ("regime", "securities")])
        # The banking licence matches two phrases that give the same terms.
        self.assertEqual(given["Tillstånd att driva bankrörelse, enligt lag 2004:297 om bank- och finansieringsrörelse"], credit_institution)
        self.assertEqual(given["Medelstort institut"], [])
        self.assertIsNone(given["IM_MR_SA"])

    def test_a_code_gives_its_terms_only_as_the_whole_line(self) -> None:
        coded = self.facts("556000-0003").model_copy(
            update={"licences": [RegisterFactsLicence(text=text, granted_on=None) for text in ("FÖFÖ", "FÖFÖ och annat", "IRK")]}
        )
        self.assertEqual(
            registers_logic.line_terms(FI, coded)[2:],
            [("FÖFÖ", [("regime", "insurance"), ("service_type", "insurance_distribution")]), ("FÖFÖ och annat", None), ("IRK", [])],
        )

    def test_the_lines_give_what_the_company_derives_and_what_its_sources_name(self) -> None:
        for number in ("556000-0001", "556000-0003", "516000-0002"):
            with self.subTest(number=number):
                facts = self.facts(number)
                lines = registers_logic.line_terms(FI, facts)
                derived = registers_logic.derived_terms(FI, facts)
                self.assertEqual({pair for _, given in lines for pair in given or ()}, {(dimension, key) for dimension, keys in derived.items() for key in keys})
                sources = registers_logic.term_sources(FI, facts)
                self.assertEqual(
                    {(pair, line) for line, given in lines for pair in given or ()},
                    {(pair, line) for pair, named in sources.items() for line in named},
                )

    def test_live_terms_are_the_mappings_terms_the_taxonomy_holds_in_the_scope_pages_order(self) -> None:
        with self.assertNumQueries(1):
            live = registers_logic.live_terms({FI})
        self.assertEqual(set(live), mapped_terms())
        self.assertEqual(list(live), sorted(live, key=lambda pair: (live[pair].dimension.sort_order, live[pair].sort_order, live[pair].key)))
        self.assertEqual((live["regime", "banking"].key, live["regime", "banking"].dimension.key), ("banking", "regime"))
        with library_write("a term and a dimension retired by proposal"):
            TaxonomyTerm.objects.filter(dimension__key="service_type", key="custody").update(active=False)
            TermDimension.objects.filter(key="licensed_activity").update(active=False)
        left = set(registers_logic.live_terms({FI}))
        self.assertEqual(mapped_terms() - left, {("service_type", "custody"), ("licensed_activity", "card_issuing"), ("licensed_activity", "card_acquiring")})
        # An authority without a mapping, or no authority at all, is no read.
        with self.assertNumQueries(0):
            self.assertEqual(registers_logic.live_terms({"eba"}), {})
            self.assertEqual(registers_logic.live_terms(set()), {})

    def test_a_bare_code_matches_only_the_whole_line_and_the_registers_codes_are_read(self) -> None:
        """FI's full register is mapped from its own sources (D-126): a bare code such as IRK
        never matches IRKA, a capital-method approval is known and adds no term, insurance
        mediation (FÖFÖ) and a MiFIR publishing entity give their terms, and a code no FI
        source defines stays unmapped rather than guessed."""
        mapping = registers_logic._mapping(FI)
        self.assertEqual(registers_logic._licence_terms(mapping, "IRK"), [])
        self.assertEqual(registers_logic._licence_terms(mapping, " IRKA "), [])
        self.assertIsNone(registers_logic._licence_terms(mapping, "IRKX"))
        self.assertEqual(registers_logic._licence_terms(mapping, "MVAR"), [])
        self.assertEqual(set(registers_logic._licence_terms(mapping, "FÖFÖ") or []), {("regime", "insurance"), ("service_type", "insurance_distribution")})
        publishing = "Anmälan som utsedd publiceringsenhet för vissa klasser av finansiella instrument enligt artikel 21 a i förordning (EU) nr 600/2014 (Mifir)."
        self.assertEqual(registers_logic._licence_terms(mapping, publishing), [("regime", "securities")])
        self.assertIsNone(registers_logic._licence_terms(mapping, "SAKRVP"))

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
            split_businesses(FI, "Värdepappersbolag, Riksbolag, livförsäkringar, Stort Institut"),
            (["Värdepappersbolag", "Riksbolag, livförsäkringar", "Stort Institut"], []),
        )

    def test_unknown_names_are_the_comma_separated_rest_in_order(self) -> None:
        self.assertEqual(
            split_businesses(FI, "Nytt slag, Riksbolag, livförsäkringar, Annat, Försäkringsdistribution"),
            (["Riksbolag, livförsäkringar", "Försäkringsdistribution"], ["Nytt slag", "Annat"]),
        )
        self.assertEqual(split_businesses(FI, ""), ([], []))

    def test_a_known_name_counts_only_as_a_whole_item(self) -> None:
        # `Fondbolag` inside `Fondbolagsgruppen` is not the business `Fondbolag`.
        self.assertEqual(split_businesses(FI, "Fondbolagsgruppen, Fondbolag"), (["Fondbolag"], ["Fondbolagsgruppen"]))


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
        self.assertEqual(branch_jurisdictions(facts), {"dk", "no"})
        self.assertEqual([branch.jurisdiction for branch in facts.branches], ["dk", "no"])
        abroad = facts.model_copy(
            update={"branches": [*facts.branches, facts.branches[0].model_copy(update={"country_name": "Hongkong"})]}
        )
        self.assertEqual(branch_jurisdictions(abroad), {"dk", "no"})
        self.assertEqual(branch_jurisdictions(facts.model_copy(update={"branches": []})), set())

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
