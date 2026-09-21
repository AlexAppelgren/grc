"""The fused hybrid query (SRC-01, SRC-02): what it finds, what it refuses to find, and
what it costs.

What these tests hold in place, in the order a reviewer would ask about it:

1. **One statement, whatever the page size.** The two legs, every filter and everything a
   hit shows are one query. The count is pinned at two page sizes, so a hydrating query per
   hit cannot creep in and put the 800 ms budget in the hands of the answer's length.
2. **Each leg says honestly whether it found the row.** An identifier is won by the words,
   a concept by the vector, and a chunk whose embedding has not arrived yet is still found
   by its words — the answer is narrower and never wrong.
3. **Filters run before ranking, and compare keys.** Validity against `asOf`, the language's
   own configuration, the kinds, the instrument, the terms, binding, jurisdiction and duty
   type. Renaming a vocabulary row changes nothing a caller sent.
4. **Narrower, never wider.** Only shared chunks are read, the bank's regulatory scope is
   chunk 3's one rule, and `inFootprint: false` is the reader asking to see what the scope
   held back.
"""

from __future__ import annotations

import datetime
import sys
import time
import uuid
from typing import Any, ClassVar
from unittest import mock

from django.conf import settings
from django.contrib.postgres.search import SearchQuery
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from apps.library.models import (
    Instrument,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
)
from apps.identity.models import User
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.models import OriginType
from apps.search import hybrid, indexing
from apps.search.models import SearchChunk, SearchSource
from apps.search.schemas import SearchFilters, SearchHitType, SearchMatchKind, SearchRequest
from apps.shared import factories
from apps.shared.adapters import embedder, reranker
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared import tenancy
from apps.shared.tenancy import library_write
from apps.shared.testing import sign_in
from apps.taxonomy.models import DutyType, FootprintTerm, InstrumentLevel, ProvisionKind, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

# The corpus is the prototype's own data (design/prototype), so the identifiers, the stems
# and the concepts are the ones a reader will actually type.
FFFS = "FFFS 2017:2"
COSTS_TITLE_SV = "Lamna information om kostnader och avgifter"
COSTS_TITLE_FI = "Ilmoita kulut ja maksut"
COSTS_SUMMARY_SV = "Institutet ska i god tid lamna information om samtliga kostnader och avgifter till kunden."
# The Finnish summary of the same duty, quoting the Swedish term. It is the whole point of
# SRC-S2: the same word, indexed twice, each time in its own language's configuration.
COSTS_SUMMARY_FI = "Laitoksen on hyvissa ajoin ilmoitettava asiakkaalle kaikki kulut ja maksut (kostnader och avgifter)."
WARNINGS_TITLE = "Make appropriateness warnings prominent and do not encourage clients to ignore them"
WARNINGS_SUMMARY = (
    "Warnings given after an appropriateness assessment are clear, prominent and not misleading. "
    "The firm does not downplay a warning or encourage the client to proceed despite it."
)
REPORTING_TITLE = "Report capital adequacy to the supervisor"
REPORTING_SUMMARY_V1 = "The institution reports its capital adequacy figures to the supervisor every quarter."
REPORTING_SUMMARY_V2 = "The institution reports its capital adequacy figures to the supervisor every month."
EU_REPORTING_TITLE = "Report transaction data to the competent authority"
EU_REPORTING_SUMMARY = "Firms report complete and accurate transaction data to the national competent authority."
PROVISION_HEADING = "Information om kostnader"
PROVISION_TEXT = "Institutet ska lamna information om kostnader innan tjansten utfors."

SEARCH = "/api/v1/search"

FIRST_DAY = datetime.date(2026, 1, 1)
SECOND_VERSION_DAY = datetime.date(2026, 9, 1)
MIDSUMMER = datetime.date(2026, 6, 30)


def seed_reference() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_term_dimensions()
    seed_taxonomy_terms()


def _instrument(*, key: str, official_ref: str, jurisdiction: str, binding: bool, level: str) -> Instrument:
    return Instrument.objects.create(
        stable_key=key,
        short_name=official_ref,
        official_ref=official_ref,
        source_url="https://www.example.test/source",
        level=InstrumentLevel.objects.get(key=level),
        binding=binding,
        jurisdiction=Jurisdiction.objects.get(key=jurisdiction),
        regime=TaxonomyTerm.objects.get(dimension__key="regime", key="securities"),
        created_origin=OriginType.USER.value,
    )


def _obligation(
    instrument: Instrument,
    *,
    key: str,
    ref_label: str,
    duty_type: str,
    titles: dict[str, str],
    versions: tuple[tuple[datetime.date, dict[str, str]], ...],
) -> Obligation:
    obligation = Obligation.objects.create(
        stable_key=key,
        instrument=instrument,
        ref_label=ref_label,
        duty_type=DutyType.objects.get(key=duty_type),
        created_origin=OriginType.USER.value,
        source_url="https://www.example.test/source",
        source_label=f"{instrument.official_ref}, {ref_label}",
    )
    for index, (language, text) in enumerate(titles.items()):
        ObligationTitle.objects.create(obligation=obligation, language_id=language, text=text, is_original=index == 0)
    for number, (effective_from, summaries) in enumerate(versions, start=1):
        version = ObligationVersion.objects.create(
            obligation=obligation, version_number=number, effective_from=effective_from
        )
        for index, (language, text) in enumerate(summaries.items()):
            ObligationSummary.objects.create(
                version=version, language_id=language, text=text, is_original=index == 0
            )
    return obligation


class CorpusMixin:
    """Two instruments, four obligations and one provision, indexed and embedded the way an
    approval and the sweep behind it leave them."""

    fffs: ClassVar[Instrument]
    esma: ClassVar[Instrument]
    costs: ClassVar[Obligation]
    warnings: ClassVar[Obligation]
    reporting: ClassVar[Obligation]
    eu_reporting: ClassVar[Obligation]
    provision: ClassVar[Provision]
    tenant: ClassVar[Tenant]

    @classmethod
    def build_corpus(cls) -> None:
        seed_reference()
        with library_write("search test corpus"):
            cls.fffs = _instrument(
                key="fffs-2017-2", official_ref=FFFS, jurisdiction="se", binding=True, level="act"
            )
            cls.esma = _instrument(
                key="esma-35-43-3172",
                official_ref="ESMA35-43-3172",
                jurisdiction="eu",
                binding=False,
                level="eu_guidance",
            )
            cls.costs = _obligation(
                cls.fffs,
                key="obl-costs-and-charges",
                ref_label="9 kap. 6 §",
                duty_type="disclosure",
                titles={"sv": COSTS_TITLE_SV, "fi": COSTS_TITLE_FI},
                versions=((FIRST_DAY, {"sv": COSTS_SUMMARY_SV, "fi": COSTS_SUMMARY_FI}),),
            )
            cls.warnings = _obligation(
                cls.esma,
                key="obl-appropriateness-warnings",
                ref_label="Guideline 5",
                duty_type="conduct",
                titles={"en": WARNINGS_TITLE},
                versions=((FIRST_DAY, {"en": WARNINGS_SUMMARY}),),
            )
            cls.reporting = _obligation(
                cls.fffs,
                key="obl-capital-adequacy-reporting",
                ref_label="12 kap. 2 §",
                duty_type="reporting",
                titles={"en": REPORTING_TITLE},
                versions=(
                    (FIRST_DAY, {"en": REPORTING_SUMMARY_V1}),
                    (SECOND_VERSION_DAY, {"en": REPORTING_SUMMARY_V2}),
                ),
            )
            cls.eu_reporting = _obligation(
                cls.esma,
                key="obl-transaction-reporting",
                ref_label="Guideline 9",
                duty_type="reporting",
                titles={"en": EU_REPORTING_TITLE},
                versions=((FIRST_DAY, {"en": EU_REPORTING_SUMMARY}),),
            )
            cls.provision = Provision.objects.create(
                stable_key="fffs-2017-2-9-kap",
                instrument=cls.fffs,
                kind=ProvisionKind.objects.get(key="chapter"),
                ref_label="9 kap.",
                heading=PROVISION_HEADING,
                path=f"{FFFS} > 9 kap.",
            )
            provision_version = ProvisionVersion.objects.create(
                provision=cls.provision, version_number=1, effective_from=FIRST_DAY
            )
            ProvisionText.objects.create(
                version=provision_version, language_id="sv", text=PROVISION_TEXT, is_original=True
            )
        indexing.reindex_all()
        indexing.embed_backlog()
        cls.tenant = factories.tenant(slug="search-corpus")


def search(
    query: str,
    *,
    tenant: Tenant,
    lang: str | None = "en",
    as_of: datetime.date | None = None,
    types: list[SearchHitType] | None = None,
    filters: SearchFilters | None = None,
    limit: int = settings.API_PAGE_SIZE_DEFAULT,
) -> Any:
    body = SearchRequest(
        q=query, lang=lang, as_of=as_of, types=types or [], filters=filters, limit=limit
    )
    return hybrid.run_search(body, tenant_id=tenant.id)


def titles_of(response: Any) -> list[str]:
    return [hit.title for hit in response.items]


def kind_by_title(response: Any) -> dict[str, SearchMatchKind]:
    return {hit.title: hit.match_kind for hit in response.items}


class HybridLegsTests(CorpusMixin, TestCase):
    """AC-SRC1: the identifier by the words, the concept by the meaning, in one query."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()

    def test_an_identifier_is_won_by_the_keyword_leg(self) -> None:
        response = search(FFFS, tenant=self.tenant, lang="sv")

        self.assertTrue(response.items, "the identifier is in every chunk of that instrument")
        first = response.items[0]
        self.assertEqual(first.match_kind, SearchMatchKind.KEYWORD)
        self.assertEqual(first.instrument_short_name, FFFS)
        self.assertNotIn(
            EU_REPORTING_TITLE, titles_of(response), "another instrument's text does not carry the reference"
        )

    def test_a_concept_is_won_by_the_vector_leg(self) -> None:
        response = search("nudging in onboarding", tenant=self.tenant)

        self.assertEqual(response.items[0].title, WARNINGS_TITLE)
        self.assertEqual(
            response.items[0].match_kind,
            SearchMatchKind.CONCEPT,
            "the words are nowhere in the text; only the meaning is",
        )

    def test_a_chunk_matched_by_both_legs_says_so(self) -> None:
        response = search("kostnader och avgifter", tenant=self.tenant, lang="sv")

        self.assertEqual(kind_by_title(response)[COSTS_TITLE_SV], SearchMatchKind.BOTH)

    def test_a_chunk_with_no_vector_yet_is_still_found_by_its_words(self) -> None:
        """The narrower answer, never the wrong one: an approval is searchable the moment it
        commits, and the vector follows behind it."""
        with indexing.index_write("test: the sweep has not reached these chunks yet"):
            SearchChunk.objects.filter(embedding__isnull=False).update(embedding=None)

        response = search("capital adequacy", tenant=self.tenant)

        self.assertIn(REPORTING_TITLE, titles_of(response))
        self.assertEqual(
            {hit.match_kind for hit in response.items},
            {SearchMatchKind.KEYWORD},
            "nothing can be a concept hit while the corpus has no vectors",
        )

    def test_the_reranker_judges_the_fused_window_and_nothing_below_it(self) -> None:
        adapter = reranker.get_reranker()
        with mock.patch.object(
            reranker.MockReranker, "rerank", autospec=True, side_effect=reranker.MockReranker.rerank
        ) as judged:
            response = search("kostnader och avgifter", tenant=self.tenant, lang="sv")

        self.assertTrue(response.items)
        judged.assert_called_once()
        documents = judged.call_args.kwargs["documents"]
        self.assertLessEqual(len(documents), adapter.top_k, "the reranker sees the fused window, not the corpus")
        self.assertIn(COSTS_SUMMARY_SV, documents[0], "the window is the fused order, best first")

    def test_no_reranker_leaves_the_fused_order_standing(self) -> None:
        with override_settings(RERANKER_PROVIDER="none"):
            unjudged = titles_of(search("kostnader och avgifter", tenant=self.tenant, lang="sv"))

        self.assertTrue(unjudged)
        self.assertEqual(unjudged[0], COSTS_TITLE_SV)

    def test_keyword_only_when_no_embedding_model_is_contracted(self) -> None:
        """`EMBEDDER_PROVIDER=none` is a contracted state (D-09), not a failure: the vector
        leg is simply not there, and nothing asks the adapter for a vector."""
        with override_settings(EMBEDDER_PROVIDER="none"):
            with mock.patch.object(embedder.NoEmbedder, "embed") as embed:
                response = search("nudging in onboarding", tenant=self.tenant)

        embed.assert_not_called()
        self.assertEqual([hit.match_kind for hit in response.items], [], "no words of that query are in the library")


class SearchHybridQueryCountTests(CorpusMixin, TestCase):
    """One statement per query, however long the answer (NFR-02)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()

    def test_the_count_does_not_grow_with_the_page_size(self) -> None:
        # Two: the bank, whose time zone and scope the search is read in, and the fused
        # query itself. Everything a hit shows comes back with it.
        for limit in (5, 50):
            with self.subTest(limit=limit):
                with self.assertNumQueries(2):
                    response = search("kostnader och avgifter", tenant=self.tenant, lang="sv", limit=limit)
                self.assertTrue(response.items)

    def test_the_page_is_no_longer_than_the_limit(self) -> None:
        response = search("information", tenant=self.tenant, lang="sv", limit=1)

        self.assertEqual(len(response.items), 1)


class SearchFilterTests(CorpusMixin, TestCase):
    """SRC-02: every filter runs before ranking, and every one of them compares a key."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()

    def test_as_of_picks_the_version_in_force(self) -> None:
        earlier = search("capital adequacy", tenant=self.tenant, as_of=MIDSUMMER)
        today = search("capital adequacy", tenant=self.tenant, as_of=SECOND_VERSION_DAY)

        self.assertIn("quarter", earlier.items[0].snippet)
        self.assertEqual(earlier.as_of, MIDSUMMER)
        self.assertIn("month", today.items[0].snippet)
        self.assertEqual(today.items[0].version_no, 2)

    def test_as_of_defaults_to_today_where_the_bank_is(self) -> None:
        response = search("capital adequacy", tenant=self.tenant)

        self.assertEqual(response.as_of, datetime.date.today())

    def test_jurisdiction_and_duty_type_are_compared_as_keys(self) -> None:
        response = search(
            "report",
            tenant=self.tenant,
            as_of=MIDSUMMER,
            filters=SearchFilters(jurisdiction="se", duty_type="reporting"),
        )

        self.assertEqual(titles_of(response), [REPORTING_TITLE])

    def test_a_renamed_vocabulary_label_changes_nothing(self) -> None:
        before = titles_of(search("report", tenant=self.tenant, filters=SearchFilters(duty_type="reporting")))
        duty = DutyType.objects.get(key="reporting")
        with library_write("test: an administrator relabels a vocabulary row"):
            duty.labels.filter(language="en").update(text="Supervisory returns")

        after = titles_of(search("report", tenant=self.tenant, filters=SearchFilters(duty_type="reporting")))

        self.assertEqual(before, after)
        self.assertTrue(before, "the filter matched something before the rename too")

    def test_binding_and_the_instrument_narrow_the_search(self) -> None:
        guidance = search("report", tenant=self.tenant, filters=SearchFilters(binding=False))
        one_instrument = search("report", tenant=self.tenant, filters=SearchFilters(instrument_id=self.fffs.id))

        self.assertEqual(titles_of(guidance), [EU_REPORTING_TITLE])
        self.assertNotIn(EU_REPORTING_TITLE, titles_of(one_instrument))

    def test_terms_narrow_the_search_to_records_carrying_them(self) -> None:
        advice = TaxonomyTerm.objects.get(dimension__key="service_type", key="advice")
        with library_write("search test corpus"):
            ObligationTerm.objects.create(obligation=self.warnings, term=advice)
        indexing.reindex(self.warnings.id)

        response = search("assessment", tenant=self.tenant, filters=SearchFilters(term_ids=[advice.id]))

        self.assertEqual(titles_of(response), [WARNINGS_TITLE])

    def test_types_narrow_the_search_to_one_kind_of_record(self) -> None:
        response = search("information om kostnader", tenant=self.tenant, lang="sv", types=[SearchHitType.PROVISION])

        self.assertEqual(titles_of(response), [PROVISION_HEADING])
        self.assertEqual(response.items[0].type, SearchHitType.PROVISION)
        self.assertEqual(response.items[0].id, self.provision.id)
        self.assertIsNone(response.items[0].version_no, "a provision has no obligation version")

    def test_an_unknown_language_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(ValidationError) as refusal:
            search("kostnader", tenant=self.tenant, lang="xx")

        self.assertEqual(refusal.exception.code, "unknown_key")

    def test_the_language_chooses_the_configuration_the_query_is_read_in(self) -> None:
        """SRC-S2's mechanics: the same word indexed twice, each time in its own language's
        configuration, so a Swedish query stems onto the Swedish chunk and a Finnish one
        onto the Finnish chunk of the very same duty."""
        swedish = SearchChunk.objects.filter(tsv=SearchQuery("kostnader", config="swedish"))
        self.assertEqual(
            {chunk.language_id for chunk in swedish.filter(source_type="obligation_version")},
            {"sv"},
            "the Finnish chunk holds the same word and no Swedish query reaches it",
        )

        as_swedish = titles_of(search("kostnader", tenant=self.tenant, lang="sv"))
        as_finnish = titles_of(search("kostnader", tenant=self.tenant, lang="fi"))

        self.assertIn(COSTS_TITLE_SV, as_swedish)
        self.assertNotIn(COSTS_TITLE_FI, as_swedish, "one hit per duty: the language that read the query best")
        self.assertIn(COSTS_TITLE_FI, as_finnish)
        self.assertNotIn(COSTS_TITLE_SV, as_finnish)

    def test_one_hit_per_record_however_many_languages_it_is_summarised_in(self) -> None:
        response = search("kostnader", tenant=self.tenant, lang="sv")
        ids = [hit.id for hit in response.items]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(self.costs.id, ids)


class SearchScopeTests(CorpusMixin, TestCase):
    """FP-03 and H7: narrower, never wider."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        insurance = TaxonomyTerm.objects.get(dimension__key="regime", key="insurance")
        with library_write("search test corpus"):
            cls.esma.regime = insurance
            cls.esma.save()
        indexing.reindex_all()

    def setUp(self) -> None:
        securities = TaxonomyTerm.objects.get(dimension__key="regime", key="securities")
        FootprintTerm.objects.create(tenant=self.tenant, term=securities)

    def test_the_standing_scope_holds_back_what_the_bank_does_not_do(self) -> None:
        response = search("report", tenant=self.tenant)

        self.assertIn(REPORTING_TITLE, titles_of(response))
        self.assertNotIn(EU_REPORTING_TITLE, titles_of(response), "the bank does not do insurance")

    def test_looking_outside_the_scope_shows_what_was_held_back(self) -> None:
        response = search("report", tenant=self.tenant, filters=SearchFilters(in_footprint=False))

        self.assertEqual(titles_of(response), [EU_REPORTING_TITLE])

    def test_the_scope_rule_is_the_one_the_inventory_applies(self) -> None:
        """Not a second copy of FP-03: the dimension a bank has no terms in does not narrow
        anything, exactly as `taxonomy_in_footprint` has it for the obligations list."""
        FootprintTerm.objects.all().delete()

        response = search("report", tenant=self.tenant)

        self.assertIn(EU_REPORTING_TITLE, titles_of(response))

    def test_a_chunk_a_bank_owns_is_never_read(self) -> None:
        """`owner_tenant_id IS NULL` is in the query as well as in the policy, so a row a
        bank could own after R1 cannot be reached by a query written before it existed.

        The row is this bank's own, which is the only case the policy would let through:
        row-level security shows a bank its own zone, so what keeps this chunk out of the
        answer is the query saying `owner_tenant_id IS NULL` and nothing else.
        """
        owned_title = "Our own note on capital adequacy"
        tenancy.activate(self.tenant.id)
        with indexing.index_write("test: a row this bank owns"):
            SearchChunk(
                source_type=SearchSource.OBLIGATION_VERSION.value,
                source_id=uuid.uuid4(),
                language_id="en",
                title=owned_title,
                body="The bank writes its own capital adequacy commentary here.",
                owner_tenant=self.tenant,
            ).save()
        self.assertTrue(
            SearchChunk.objects.filter(owner_tenant=self.tenant).exists(),
            "the policy shows the bank its own row, so the query is what has to refuse it",
        )

        response = search("capital adequacy", tenant=self.tenant)

        self.assertNotIn(owned_title, titles_of(response))
        self.assertIn(REPORTING_TITLE, titles_of(response), "the shared library still answers")


class SearchCallerTests(CorpusMixin, TestCase):
    """The caller, and what a hit shows them."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()

    def test_a_session_in_no_company_is_a_404(self) -> None:
        with self.assertRaises(ProblemError) as refusal:
            hybrid.run_search(SearchRequest(q=FFFS), tenant_id=None)

        self.assertEqual((refusal.exception.status, refusal.exception.code), (404, "not_found"))

    def test_a_hit_carries_what_the_screen_draws_beside_it(self) -> None:
        response = search("capital adequacy", tenant=self.tenant, as_of=MIDSUMMER)
        hit = response.items[0]

        self.assertEqual(hit.type, SearchHitType.OBLIGATION)
        self.assertEqual(hit.id, self.reporting.id, "the hit opens the obligation, not the chunk")
        self.assertEqual(hit.title, REPORTING_TITLE)
        self.assertEqual(hit.instrument_short_name, FFFS)
        self.assertEqual(hit.version_no, 1)
        self.assertTrue(hit.binding)
        self.assertEqual(hit.valid_from, FIRST_DAY)
        self.assertEqual(hit.valid_to, SECOND_VERSION_DAY - datetime.timedelta(days=1))
        self.assertIsNone(hit.urgency, "the library's urgency lives on a registered change")
        self.assertGreater(hit.score, 0.0)

    def test_a_snippet_is_capped_and_cut_around_the_match(self) -> None:
        long_text = f"{'Inledande text om annat. ' * 20}kapitaltackning ska rapporteras. {'Slutord. ' * 20}"
        with library_write("search test corpus"):
            ObligationSummary.objects.create(
                version=ObligationVersion.objects.get(obligation=self.warnings, version_number=1),
                language_id="sv",
                text=long_text,
            )
        indexing.reindex(self.warnings.id)

        response = search("kapitaltackning", tenant=self.tenant, lang="sv")
        snippet = response.items[0].snippet

        self.assertLessEqual(len(snippet), settings.SEARCH_SNIPPET_CHARS + 2, "two ellipses at most")
        self.assertIn("kapitaltackning", snippet)
        self.assertTrue(snippet.startswith(hybrid.ELLIPSIS))

    def test_an_answer_with_nothing_in_it_is_an_empty_list(self) -> None:
        response = search("kvartalsrapporten fastnade i Ekeroth-flodet", tenant=self.tenant, lang="sv")

        self.assertEqual(response.items, [])


class SearchBudgetTests(CorpusMixin, TestCase):
    """NFR-02: hybrid search answers inside 800 ms, and 1.5 s with the reranker, reported
    in `Server-Timing`. Measured the way the watch feed's read is, on thread time and on
    the fastest of five runs, so a loaded machine cannot fail a gate about the query."""

    reader: ClassVar[User]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def test_the_answer_arrives_inside_the_budget_and_reports_its_time(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        client = Client()
        body = {"q": "kostnader och avgifter", "lang": "sv"}

        response = client.post(SEARCH, data=body, content_type="application/json", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                client.post(SEARCH, data=body, content_type="application/json", **headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.SEARCH_BUDGET_MS)
        self.assertLess(min(spent), settings.SEARCH_RERANKED_BUDGET_MS, "the reranker is on in this run")


class SearchWritesNothingTests(CorpusMixin, TestCase):
    """A read is a read: `POST /search` changes no record and leaves no audit row."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()

    def test_searching_writes_no_chunk_and_asks_for_no_embedding(self) -> None:
        before = list(SearchChunk.objects.values_list("id", "embedded_at"))

        with mock.patch.object(indexing, "_write") as written:
            search(FFFS, tenant=self.tenant, lang="sv")

        written.assert_not_called()
        self.assertEqual(list(SearchChunk.objects.values_list("id", "embedded_at")), before)

    def test_the_query_text_is_never_logged(self) -> None:
        """The bank's own text reaches the text search and the embedder, and nothing else
        (playbook 4.7)."""
        typed = "hemligt sokord om kostnader"
        with self.assertNoLogs(level="DEBUG"):
            search(typed, tenant=self.tenant, lang="sv")


class SearchStubsTests(TestCase):
    """What this task did not build yet."""

    def test_find_similar_is_still_the_contract_stub(self) -> None:
        from apps.search.schemas import SimilarRequest

        with self.assertRaises(ProblemError) as refusal:
            hybrid.find_similar(SimilarRequest(text="anything at all"))

        self.assertEqual((refusal.exception.status, refusal.exception.code), (501, "not_built"))

    def test_every_hit_kind_maps_to_a_source_and_back(self) -> None:
        """A `types` filter and a hit read the one mapping, so they cannot disagree about
        what a chunk is."""
        self.assertEqual(set(hybrid.SOURCE_OF_HIT), set(SearchHitType))
        self.assertEqual(len(hybrid.HIT_OF_SOURCE), len(hybrid.SOURCE_OF_HIT))
        self.assertNotIn(uuid.uuid4().hex, hybrid.HIT_OF_SOURCE)
