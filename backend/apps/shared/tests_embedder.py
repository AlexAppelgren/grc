"""Embedder and reranker adapters (playbook 16, DECISIONS D-09, SRC-01, AC-SRC1).

The mock embedder has to behave the way a real one does, not the way a hash does. Chunk 7
builds hybrid search and the evaluation gate against it, so a question asked in any of the
five content languages must reach the obligation whose summary says the same thing in
English or Swedish. These tests run the concept questions of `eval/retrieval.jsonl` over
the prototype corpus by the vector leg alone, with no keyword leg to lean on.

Identifiers are deliberately not the embedder's job (AC-SRC1): "FFFS 2017:2" carries no
concept, keeps a plain hash vector, and is won by keyword in chunk 7.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.shared.adapters import embedder, reranker

BACKEND = Path(settings.BASE_DIR)
PROTOTYPE_DATA = BACKEND / "apps" / "library" / "fixtures" / "prototype_data.json"
RETRIEVAL_SET = BACKEND / "eval" / "retrieval.jsonl"
TOP_N = 3  # every expected key ranks 1 or 2 today; a third place leaves one rank of margin.


def _corpus() -> list[tuple[str, str]]:
    """(stable key, text) for the library rows the evaluation set names. Obligations are
    one document per content language, as chunks will be; changes are English only, as the
    prototype has them. Every row is a distractor for every other row's question."""
    data = json.loads(PROTOTYPE_DATA.read_text(encoding="utf-8"))
    titles = {row["stable_key"]: row["title"] for row in data["obligations"]}
    documents = []
    for version in data["obligation_versions"]:
        key = version["obligation"]
        documents.append((key, f"{titles[key]} {version['summary_en']}"))
        documents.append((key, version["summary_sv"]))
    for change in data["regulatory_changes"]:
        documents.append((change["stable_key"], f"{change['title']} {change['summary']}"))
    return documents


def _questions(match_kind: str) -> list[dict]:
    rows = [
        json.loads(line)
        for line in RETRIEVAL_SET.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return [row for row in rows if row["match_kind"] == match_kind]


def _ranked(query: str, corpus: list[tuple[str, str]], adapter: embedder.EmbedderAdapter) -> list[str]:
    """The stable keys of the corpus by cosine similarity to the query, best first. One key
    is scored by its best document, so a question answered in Swedish counts once."""
    vectors = adapter.embed([text for _, text in corpus])
    question = adapter.embed([query])[0]
    best: dict[str, float] = {}
    for (key, _), vector in zip(corpus, vectors, strict=True):
        score = sum(a * b for a, b in zip(question, vector, strict=True))
        best[key] = max(best.get(key, -1.0), score)
    return sorted(best, key=lambda key: -best[key])


class MockEmbedderVectors(SimpleTestCase):
    def test_the_same_text_always_gives_the_same_vector(self) -> None:
        first = embedder.MockEmbedder(64).embed(["passandebedömning", "costs and charges"])
        second = embedder.MockEmbedder(64).embed(["passandebedömning", "costs and charges"])
        self.assertEqual(first, second)
        self.assertNotEqual(first[0], first[1])

    def test_vectors_are_unit_length_of_the_configured_size(self) -> None:
        for text in ("", "FFFS 2017:2", "nudging in onboarding"):
            with self.subTest(text=text):
                vector = embedder.MockEmbedder(128).embed([text])[0]
                self.assertEqual(len(vector), 128)
                self.assertAlmostEqual(math.sqrt(sum(v * v for v in vector)), 1.0, places=6)

    def test_text_the_concept_table_does_not_know_keeps_a_hash_vector(self) -> None:
        adapter = embedder.MockEmbedder(1024)
        self.assertEqual(embedder.concepts("Vattenfall AB, protokoll från styrelsemötet"), [])
        a, b = adapter.embed(["Vattenfall AB, protokoll från styrelsemötet", "Ovanåkers kommun, bilaga 12"])
        self.assertLess(abs(sum(x * y for x, y in zip(a, b, strict=True))), 0.2)


class MockEmbedderConcepts(SimpleTestCase):
    """AC-SRC1 and D-09: the concept leg, over the prototype corpus, in all five languages."""

    corpus: list[tuple[str, str]]
    adapter: embedder.EmbedderAdapter

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.corpus = _corpus()
        cls.adapter = embedder.MockEmbedder(settings.EMBEDDING_DIMENSIONS)

    def test_every_concept_question_reaches_its_obligation_by_the_vector_leg_alone(self) -> None:
        misses = []
        for row in _questions("concept"):
            ranked = _ranked(row["query"], self.corpus, self.adapter)[:TOP_N]
            for key in row["expected"]:
                if key not in ranked:
                    misses.append(f"{row['id']} ({row['language']}) {row['query']!r}: {key} not in {ranked}")
        self.assertEqual(misses, [], "\n".join(misses))

    def test_the_concept_questions_cover_all_five_content_languages(self) -> None:
        languages = {row["language"] for row in _questions("concept")}
        self.assertEqual(languages, {"en", "sv", "da", "nb", "fi"})

    def test_nudging_in_onboarding_is_answered_first_by_the_esma_warnings_obligation(self) -> None:
        ranked = _ranked("nudging in onboarding", self.corpus, self.adapter)
        self.assertEqual(ranked[0], "obl-esma-warnings")

    def test_an_identifier_question_carries_no_concept_and_is_left_to_the_keyword_leg(self) -> None:
        for query in ("FFFS 2017:2", "SFS 2007:528", "ESMA35-43-3006"):
            with self.subTest(query=query):
                self.assertEqual(embedder.concepts(query), [])

    def test_a_concept_is_found_once_however_many_of_its_terms_the_text_uses(self) -> None:
        one = embedder.concepts("The warning is prominent")
        many = embedder.concepts("The warning is prominent, not misleading, and never downplayed")
        self.assertEqual(one, many)


class RerankerAdapter(SimpleTestCase):
    documents = [
        "Clients receive aggregated information on all costs and charges of the service",
        "A policyholder may transfer the value of a pension insurance to another insurer",
        "Warnings given after an appropriateness assessment are clear and prominent",
    ]
    question = "costs and charges of the service"

    def test_the_mock_puts_the_document_that_shares_the_most_of_the_question_first(self) -> None:
        ranked = reranker.get_reranker().rerank(query=self.question, documents=self.documents)
        self.assertEqual(ranked[0].index, 0)
        self.assertGreater(ranked[0].score, ranked[-1].score)
        again = reranker.MockReranker(settings.RERANKER_TOP_K).rerank(query=self.question, documents=self.documents)
        self.assertEqual(ranked, again)

    def test_documents_that_share_nothing_keep_their_fused_order(self) -> None:
        ranked = reranker.get_reranker().rerank(query="schablonintäkt", documents=self.documents)
        self.assertEqual([hit.index for hit in ranked], [0, 1, 2])
        self.assertEqual({hit.score for hit in ranked}, {0.0})

    @override_settings(RERANKER_TOP_K=2)
    def test_the_window_comes_from_settings(self) -> None:
        ranked = reranker.get_reranker().rerank(query="costs and charges", documents=self.documents)
        self.assertEqual(len(ranked), 2)

    @override_settings(RERANKER_PROVIDER="none")
    def test_none_hands_back_the_fused_order_unscored(self) -> None:
        adapter = reranker.get_reranker()
        self.assertEqual(adapter.name, "none")
        ranked = adapter.rerank(query=self.question, documents=self.documents)
        self.assertEqual([hit.index for hit in ranked], [0, 1, 2])
        self.assertEqual({hit.score for hit in ranked}, {0.0})

    @override_settings(RERANKER_PROVIDER="cohere")
    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            reranker.get_reranker()

    def test_an_empty_candidate_list_stays_empty(self) -> None:
        self.assertEqual(reranker.get_reranker().rerank(query="costs", documents=[]), [])
