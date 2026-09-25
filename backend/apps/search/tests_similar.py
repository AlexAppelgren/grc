"""The agents' nearest-neighbour read and the buckets both search routes spend from
(SRC-01, AC-SRC1, NFR-02).

What these tests hold in place, in the order a reviewer would ask about it:

1. **An agent reaches the shared library and nothing else.** `POST /search/similar` is the
   agents' route: it reads rows whose `owner_tenant_id` is NULL in the query as well as by
   the policy, applies no bank's footprint because a key belongs to no bank, and would
   leave an owned row out if one existed.
2. **The vector leg leads, the words catch what it cannot reach.** A passage that shares
   no word with the record that means the same thing still finds it; a chunk whose
   embedding has not arrived, and a deployment with no embedding model contracted at all
   (`EMBEDDER_PROVIDER=none`, D-09), are still answered by the keyword leg, read in every
   one of the five content languages because an agent sends no language.
3. **One caller cannot spend everyone's budget.** Search and Ask each have a bucket per
   caller, both settings, and a hit answers 429 `rate_limited` in the problem shape with
   nothing of what the caller typed in it.
4. **The budgets hold.** The agents' read answers inside 800 ms without the reranker and
   1.5 s with it, reported in `Server-Timing` (NFR-02).
"""

from __future__ import annotations

import sys
import time
import uuid
from typing import Any, ClassVar
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.agents.testing import agent_key
from apps.identity.models import User
from apps.search import hybrid, indexing, limits
from apps.search.models import SearchChunk, SearchSource
from apps.search.schemas import SearchHitType, SearchMatchKind, SimilarRequest
from apps.search.tests_hybrid import (
    COSTS_TITLE_SV,
    EU_REPORTING_TITLE,
    FFFS,
    PROVISION_HEADING,
    PROVISION_TEXT,
    REPORTING_TITLE,
    WARNINGS_TITLE,
    CorpusMixin,
)
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.adapters import embedder, reranker
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in

SEARCH = "/api/v1/search"
SIMILAR = "/api/v1/search/similar"

# What a watch agent actually sends: a paragraph it fetched from a Swedish supervisor's
# page, asking whether the library already tracks the duty it describes. The obligation
# that answers it is written in English and shares not one word with it, which is the whole
# point of the vector leg.
FETCHED_PASSAGE = (
    "Varningar ska vara framtradande och institutet far inte uppmuntra kunden att ga "
    "vidare trots dem."
)
# The version of the reporting duty in force today says "every month"; the quarterly text
# was the first version and stopped being law on 31 August (tests_hybrid.CorpusMixin).
CAPITAL_PASSAGE = "The institution reports its capital adequacy figures every month."


def similar(
    text: str,
    *,
    types: list[SearchHitType] | None = None,
    limit: int = settings.API_PAGE_SIZE_DEFAULT,
    caller_id: uuid.UUID | None = None,
) -> Any:
    body = SimilarRequest(text=text, types=types or [], limit=limit)
    return hybrid.find_similar(body, caller_id=caller_id or uuid.uuid4(), tenant_id=None)


def titles_of(response: Any) -> list[str]:
    return [hit.title for hit in response.items]


def platform_key(*, scope: str = perms.SCOPE_SEARCH_READ) -> Any:
    """A platform agent's key. Written with no tenant activated, which is the only session
    a mixed table accepts a platform row from (hardening H15), because the corpus builder
    leaves this test's bank active."""
    with tenancy.platform_zone():
        return agent_key(scopes=(scope,))


def as_the_platform() -> None:
    """What a key's request arrives in: no bank activated. The corpus builder leaves one
    set on the connection for the whole class transaction, which a real request never
    inherits, and under it even stamping the key's own `last_used_at` is refused."""
    tenancy.clear_tenant()


class FindSimilarTests(CorpusMixin, TestCase):
    """AGT-02: the shared library records nearest a piece of text an agent fetched."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()

    def test_a_passage_finds_the_record_that_means_the_same_thing(self) -> None:
        response = similar(FETCHED_PASSAGE)

        self.assertEqual(response.items[0].title, WARNINGS_TITLE)
        self.assertEqual(
            response.items[0].match_kind,
            SearchMatchKind.CONCEPT,
            "the passage and the obligation share a meaning, not a wording",
        )

    def test_an_identifier_is_still_won_by_the_words(self) -> None:
        response = similar(FFFS)

        self.assertEqual(response.items[0].instrument_short_name, FFFS)
        self.assertEqual(response.items[0].match_kind, SearchMatchKind.KEYWORD)

    def test_the_words_are_read_in_every_content_language(self) -> None:
        """An agent sends what it fetched, in the language it was published in, and never a
        `lang`: `SimilarRequest` has no such field. The keyword leg therefore reads the
        passage in every content language's own configuration, so a Swedish sentence
        reaches the Swedish chunk of the duty rather than being stemmed as English."""
        response = similar("Institutet ska lamna information om kostnader och avgifter.")

        self.assertIn(COSTS_TITLE_SV, titles_of(response))

    def test_a_chunk_with_no_vector_yet_is_still_found_by_its_words(self) -> None:
        # With no tenant active, which is the only session that writes a shared chunk
        # since H15: the corpus builder leaves this test's bank activated, and under that
        # session the policy would refuse the update and leave every vector in place.
        with tenancy.platform_zone(), indexing.index_write("test: the sweep has not reached these chunks yet"):
            SearchChunk.objects.filter(embedding__isnull=False).update(embedding=None)

        response = similar(CAPITAL_PASSAGE)

        self.assertIn(REPORTING_TITLE, titles_of(response))
        self.assertEqual(
            {hit.match_kind for hit in response.items},
            {SearchMatchKind.KEYWORD},
            "nothing can be a concept hit while the corpus has no vectors",
        )

    def test_no_embedding_model_contracted_leaves_the_keyword_leg_answering(self) -> None:
        """`EMBEDDER_PROVIDER=none` is a contracted state (D-09), not a failure: the agents'
        route still answers, by the words alone, and nothing asks the adapter for a vector."""
        with override_settings(EMBEDDER_PROVIDER="none"):
            with mock.patch.object(embedder.NoEmbedder, "embed") as embed:
                response = similar(CAPITAL_PASSAGE)

        embed.assert_not_called()
        self.assertIn(REPORTING_TITLE, titles_of(response))

    def test_types_narrow_the_comparison_to_one_kind_of_record(self) -> None:
        response = similar(PROVISION_TEXT, types=[SearchHitType.PROVISION])

        self.assertEqual(titles_of(response), [PROVISION_HEADING])
        self.assertEqual({hit.type for hit in response.items}, {SearchHitType.PROVISION})

    def test_the_page_is_no_longer_than_the_limit(self) -> None:
        response = similar("information", limit=1)

        self.assertEqual(len(response.items), 1)

    def test_the_answer_is_one_statement_over_the_chunk_table(self) -> None:
        # One query, and only one: no bank is read at all, because a key belongs to none.
        with self.assertNumQueries(1):
            response = similar(FETCHED_PASSAGE)

        self.assertTrue(response.items)

    def test_the_date_the_ranking_was_taken_at_comes_back(self) -> None:
        response = similar(FETCHED_PASSAGE)

        self.assertEqual(response.as_of, timezone.localdate())

    def test_a_passage_the_library_says_nothing_about_is_an_empty_list(self) -> None:
        response = similar("kvartalsrapporten fastnade i Ekeroth-flodet")

        self.assertEqual(response.items, [])


class FindSimilarReachesSharedRowsOnlyTests(CorpusMixin, TestCase):
    """H7 and D-10: an agent reads the shared library, and there is no other way in."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()

    def test_a_chunk_a_bank_owns_is_never_returned(self) -> None:
        """`owner_tenant_id IS NULL` is in the query as well as in the policy, so a row a
        bank could own after R1 cannot be reached by a read written before it existed."""
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
        self.assertTrue(SearchChunk.objects.filter(owner_tenant=self.tenant).exists())

        response = similar(CAPITAL_PASSAGE)

        self.assertNotIn(owned_title, titles_of(response))
        self.assertIn(REPORTING_TITLE, titles_of(response), "the shared library still answers")

    def test_no_banks_footprint_narrows_what_an_agent_is_shown(self) -> None:
        """A person's search applies their bank's regulatory scope (FP-03). A key belongs to
        no bank, so there is no scope to apply and the whole shared library answers."""
        response = similar("Firms report transaction data to the competent authority.")

        self.assertIn(EU_REPORTING_TITLE, titles_of(response))


class SimilarRouteTests(CorpusMixin, TestCase):
    """The agents' route end to end: the scope gate, then the answer."""

    key: ClassVar[Any]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        cls.key = platform_key()

    def setUp(self) -> None:
        as_the_platform()

    def post(self, body: dict[str, Any], *, plain_key: str) -> Any:
        return self.client.post(SIMILAR, data=body, content_type="application/json", HTTP_X_API_KEY=plain_key)

    def test_a_key_with_the_scope_gets_the_nearest_shared_records(self) -> None:
        response = self.post({"text": FETCHED_PASSAGE}, plain_key=self.key.plain_key)

        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual(answer["items"][0]["title"], WARNINGS_TITLE)
        self.assertEqual(answer["items"][0]["matchKind"], "concept")
        self.assertEqual(answer["asOf"], timezone.localdate().isoformat())

    def test_a_key_without_the_scope_is_refused_before_it_reaches_the_answer(self) -> None:
        without = platform_key(scope=perms.SCOPE_LIBRARY_READ)

        response = self.post({"text": FETCHED_PASSAGE}, plain_key=without.plain_key)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], perms.SCOPE_SEARCH_READ)

    def test_a_banks_own_key_sends_no_text_to_a_model_once_the_bank_switched_its_ai_off(self) -> None:
        """A bank's key may hold `search:read`, and the text it sends is the bank's own. The
        bank's switch covers it as it covers a reader's search (D-07, owner item 14;
        security-review-c7, M1): off, the text is compared by its words alone."""
        bank_key = factories.api_key(self.tenant, scopes=(perms.SCOPE_SEARCH_READ,))
        Tenant.objects.filter(pk=self.tenant.pk).update(ai_enabled=False)
        with (
            mock.patch.object(embedder.MockEmbedder, "embed") as embed,
            mock.patch.object(reranker.MockReranker, "rerank") as judged,
        ):
            response = self.post({"text": FFFS}, plain_key=bank_key.plain_key)

        self.assertEqual(response.status_code, 200, response.content)
        embed.assert_not_called()
        judged.assert_not_called()
        kinds = {hit["matchKind"] for hit in response.json()["items"]}
        self.assertEqual(kinds, {"keyword"})

    def test_a_person_is_refused_however_much_they_may_do(self) -> None:
        """No permission in the PRD's matrix gives a person a similarity read, so this is
        the agents' route and a session is not a caller here at all."""
        reader = factories.member_user(self.tenant, roles=("admin",))

        response = self.client.post(
            SIMILAR,
            data={"text": FETCHED_PASSAGE},
            content_type="application/json",
            **sign_in(reader, tenant=self.tenant),
        )

        self.assertEqual(response.status_code, 401)

    def test_the_read_writes_nothing(self) -> None:
        before = AuditEvent.objects.count()

        self.post({"text": FETCHED_PASSAGE}, plain_key=self.key.plain_key)

        self.assertEqual(AuditEvent.objects.count(), before, "a read changes nothing, so it writes no audit row")


class SearchRateLimitTests(CorpusMixin, TestCase):
    """NFR-02 and playbook 11.2: one caller cannot spend the budget every other reader is
    measured against. Rate limiting is off in tests except the tests that prove it fires."""

    reader: ClassVar[User]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(RATE_LIMITING_ENABLED=True, SEARCH_RATE_PER_USER_PER_MINUTE=2)
    def test_a_caller_over_the_search_limit_is_refused(self) -> None:
        caller = uuid.uuid4()
        for _ in range(settings.SEARCH_RATE_PER_USER_PER_MINUTE):
            limits.search_bucket(caller)

        with self.assertRaises(ProblemError) as refusal:
            limits.search_bucket(caller)

        self.assertEqual((refusal.exception.status, refusal.exception.code), (429, "rate_limited"))

    @override_settings(RATE_LIMITING_ENABLED=True, SEARCH_RATE_PER_USER_PER_MINUTE=1)
    def test_one_callers_spending_leaves_the_next_caller_untouched(self) -> None:
        busy = uuid.uuid4()
        limits.search_bucket(busy)
        with self.assertRaises(ProblemError):
            limits.search_bucket(busy)

        limits.search_bucket(uuid.uuid4())  # another caller, its own window

    @override_settings(RATE_LIMITING_ENABLED=True, ASK_RATE_PER_USER_PER_MINUTE=1)
    def test_ask_has_a_bucket_of_its_own(self) -> None:
        """Ask is tighter than search, because every call that passes it is a model call.
        The two are separate buckets, so spending one never spends the other."""
        caller = uuid.uuid4()
        limits.ask_bucket(caller)

        with self.assertRaises(ProblemError) as refusal:
            limits.ask_bucket(caller)

        self.assertEqual((refusal.exception.status, refusal.exception.code), (429, "rate_limited"))
        limits.search_bucket(caller)  # the search bucket is untouched by Ask's

    @override_settings(RATE_LIMITING_ENABLED=True, SEARCH_RATE_PER_USER_PER_MINUTE=1)
    def test_the_search_route_answers_429_over_the_limit(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        client = Client()
        body = {"q": "kostnader och avgifter", "lang": "sv"}

        first = client.post(SEARCH, data=body, content_type="application/json", **headers)
        second = client.post(SEARCH, data=body, content_type="application/json", **headers)

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["code"], "rate_limited")

    @override_settings(RATE_LIMITING_ENABLED=True, SEARCH_RATE_PER_USER_PER_MINUTE=1)
    def test_the_agents_route_answers_429_over_the_limit(self) -> None:
        key = platform_key()
        as_the_platform()
        client = Client()
        body = {"text": FETCHED_PASSAGE}

        first = client.post(SIMILAR, data=body, content_type="application/json", HTTP_X_API_KEY=key.plain_key)
        second = client.post(SIMILAR, data=body, content_type="application/json", HTTP_X_API_KEY=key.plain_key)

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["code"], "rate_limited")

    @override_settings(RATE_LIMITING_ENABLED=True, SEARCH_RATE_PER_USER_PER_MINUTE=1)
    def test_the_query_a_refused_reader_typed_is_nowhere_in_the_refusal(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        client = Client()
        query = "vad galler for kunder med diskretionar forvaltning"
        body = {"q": query, "lang": "sv"}
        client.post(SEARCH, data=body, content_type="application/json", **headers)

        refused = client.post(SEARCH, data=body, content_type="application/json", **headers)

        self.assertEqual(refused.status_code, 429)
        self.assertNotIn(query, refused.content.decode())

    def test_both_search_operations_tell_a_caller_the_code_to_branch_on(self) -> None:
        """A limit a caller cannot see is a limit they will hit in production (Alex's API
        rule, 2026-09-20). Both search operations name `rate_limited` and the setting
        behind it, and so does `POST /ask`, which spends a bucket of its own in `ask.py`
        before anything else runs."""
        from config.api import api

        paths = api.get_openapi_schema()["paths"]
        search = ("SEARCH_RATE_PER_USER_PER_MINUTE", settings.SEARCH_RATE_PER_USER_PER_MINUTE)
        ask = ("ASK_RATE_PER_USER_PER_MINUTE", settings.ASK_RATE_PER_USER_PER_MINUTE)
        for path, (setting, limit) in (
            ("/api/v1/search", search),
            ("/api/v1/search/similar", search),
            ("/api/v1/ask", ask),
        ):
            with self.subTest(path=path):
                description = " ".join(paths[path]["post"]["description"].split())
                self.assertIn("`rate_limited`", description)
                self.assertIn(setting, description)
                self.assertIn(str(limit), description)

    def test_neither_limit_can_be_set_to_a_value_that_admits_everything(self) -> None:
        """Every limit is a setting with an env override (playbook 4.3), and neither of
        these may be turned off by setting it to zero: settings.py refuses to boot on one,
        the way it already refuses an out-of-range page offset and diff cap."""
        self.assertGreaterEqual(settings.SEARCH_RATE_PER_USER_PER_MINUTE, 1)
        self.assertGreaterEqual(settings.ASK_RATE_PER_USER_PER_MINUTE, 1)


class SimilarBudgetTests(CorpusMixin, TestCase):
    """NFR-02: the agents' read answers inside the same budgets as `POST /search` — 800 ms
    without the reranker, 1.5 s with it — reported in `Server-Timing`. Measured the way the
    search budget is, on thread time and on the fastest of five runs, so a loaded machine
    cannot fail a gate that is about the query."""

    key: ClassVar[Any]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        cls.key = platform_key()

    def setUp(self) -> None:
        as_the_platform()

    def test_the_answer_arrives_inside_the_budget_and_reports_its_time(self) -> None:
        client = Client()
        # The longest text the contract accepts, because that is what the budget must hold
        # for: an agent sends a fetched page, not a reader's phrase.
        body = {"text": (FETCHED_PASSAGE + " ") * 40}

        def send() -> Any:
            return client.post(
                SIMILAR, data=body, content_type="application/json", HTTP_X_API_KEY=self.key.plain_key
            )

        response = send()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                send()
                spent.append((time.thread_time() - started) * 1000)
            with override_settings(RERANKER_PROVIDER="none"):
                started = time.thread_time()
                send()
                unranked = (time.thread_time() - started) * 1000
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.SEARCH_RERANKED_BUDGET_MS, "the reranker is on in this run")
        self.assertLess(unranked, settings.SEARCH_BUDGET_MS, "and the query alone is inside the tighter budget")
