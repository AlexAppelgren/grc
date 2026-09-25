"""What a narrowed entry could not see (ACC-07, AC-ACC1): the words a description is read
as, and which footprint terms outside an entry's scope it touches, by label or usage note,
with AI switched off, naming labels and never records."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase, override_settings

from apps.agents.out_of_scope import outside_terms, words
from apps.agents.tests_what_applies import CARD_FEATURE, ORDER_ROUTING, TradingBank, term
from apps.shared import tenancy
from apps.shared.models import Tenant
from apps.taxonomy import entry_scope
from apps.taxonomy.models import FootprintTerm, TaxonomyTermLabel


class Words(SimpleTestCase):
    def test_endings_short_words_and_common_words_are_dropped(self) -> None:
        self.assertEqual(words("A feature that issues virtual Cards"), {"featur", "issu", "virtual", "card"})
        self.assertEqual(words("Card issuing"), {"card", "issu"})
        self.assertEqual(words("the and for"), set())

    def test_any_language_splits_on_letters(self) -> None:
        self.assertEqual(words("Kortutgivning för företag"), {"kortutgivn", "företag"})


class OutsideTerms(TestCase):
    def setUp(self) -> None:
        self.bank = TradingBank(slug="out-of-scope")

    def outside(self, description: str, entry_id: object = None) -> list[str]:
        tenancy.activate(self.bank.tenant.id)
        scope = entry_scope.scope_of(self.bank.tenant.id, entry_id or self.bank.trading.id)  # type: ignore[arg-type]
        return [f"{row.dimension.label}: {row.term.label}" for row in outside_terms(self.bank.tenant.id, scope, description, ["en"])]

    def test_a_card_feature_names_card_issuing_and_cards_and_not_card_acquiring(self) -> None:
        self.assertEqual(self.outside(CARD_FEATURE), ["Licensed activity: Card issuing", "Product type: Cards"])

    def test_nothing_is_named_for_what_the_entry_can_see(self) -> None:
        self.assertEqual(self.outside(ORDER_ROUTING), [])
        self.assertEqual(self.outside("derivatives and securities under investment services"), [])

    def test_an_entry_that_narrows_nothing_names_nothing(self) -> None:
        self.assertEqual(self.outside(CARD_FEATURE, self.bank.general.id), [])

    def test_a_dimension_the_entry_names_nothing_in_does_not_restrict_it_so_is_never_named(self) -> None:
        tenancy.activate(self.bank.tenant.id)
        FootprintTerm.objects.create(tenant=self.bank.tenant, term=term("client_category:retail"))
        self.assertEqual(self.outside("a savings product for retail clients"), [])

    def test_a_usage_note_sharing_enough_words_names_its_term(self) -> None:
        tenancy.activate(self.bank.tenant.id)
        acquiring = self.bank.acquiring
        acquiring.usage_note = "Merchant settlement of payment transactions"
        with tenancy.library_write("test"):
            acquiring.save(update_fields=["usage_note"])
        self.assertEqual(self.outside("reconcile merchant settlement files"), ["Licensed activity: Card acquiring"])
        with override_settings(AGENT_ACCESS_NOTE_MATCH_WORDS=3):
            self.assertEqual(self.outside("reconcile merchant settlement files"), [])

    def test_a_label_in_another_language_matches_and_the_answer_is_in_the_reader_s_language(self) -> None:
        with tenancy.library_write("test"):
            TaxonomyTermLabel.objects.create(term=self.bank.cards, language="sv", text="Kort")
        self.assertEqual(self.outside("ett nytt kort för handelskonton"), ["Product type: Cards"])

    def test_it_needs_no_model_so_it_answers_with_ai_switched_off(self) -> None:
        Tenant.objects.filter(pk=self.bank.tenant.id).update(ai_enabled=False)
        self.assertEqual(self.outside(CARD_FEATURE), ["Licensed activity: Card issuing", "Product type: Cards"])
