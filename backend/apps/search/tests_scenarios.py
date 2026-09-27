"""Scenario stubs for the search app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: SRC.
"""

import datetime
import json
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, ClassVar, cast
from unittest import mock, skip

from django.conf import settings
from django.contrib.postgres.search import SearchQuery
from django.core.cache import cache
from django.db import connection, transaction
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.governance.models import AiGeneration, AiPurpose
from apps.identity.models import User
from apps.library.models import ProblemReport, SubjectType
from apps.library.seeds import seed_languages
from apps.search import ask, hybrid, indexing
from apps.search.eval import SPEC, Retriever
from apps.search.indexing import index_write
from apps.search.models import SearchChunk, SearchSource
from apps.search.tests_eval import load_search_eval
from apps.search.tests_hybrid import (
    COSTS_SUMMARY_FI,
    COSTS_SUMMARY_SV,
    COSTS_TITLE_FI,
    COSTS_TITLE_SV,
    EU_REPORTING_SUMMARY,
    EU_REPORTING_TITLE,
    FFFS,
    FIRST_DAY,
    REPORTING_SUMMARY_V1,
    REPORTING_SUMMARY_V2,
    REPORTING_TITLE,
    WARNINGS_SUMMARY,
    WARNINGS_TITLE,
    CorpusMixin,
    _instrument,
    _obligation,
)
from apps.shared import ai, factories, tenancy
from apps.shared.adapters import llm, reranker
from apps.shared.models import AuditEvent, Tenant
from apps.shared.tenancy import library_write
from apps.shared.testing import sign_in
from apps.taxonomy.models import DutyType, InstrumentLevel, InstrumentLevelKind
from apps.watch import testing as watch
from apps.watch.models import ChangeObligation
from apps.watch.write import watch_write

SEARCH = "/api/v1/search"
# SRC-S8's stand-in for the agents' classifier, named to the gate the way a real one is.
CLASSIFIER = "apps.search.tests_scenarios:LabelledClassifier"
ASK = "/api/v1/ask"


class SearchScenarioTests(TestCase):
    """Scenario tests for apps.search, one method per @integration scenario."""

    @skip("pending: SRC-S7 (SRC-04, chunk 13)")
    def test_src_s7(self) -> None:
        """SRC-S7

        Saved searches notify and show what changed since the last visit (SRC-04).
        """

    def test_src_s8(self) -> None:
        """SRC-S8

        The evaluation set gates releases (SRC-05).

        `scripts/search_eval.py` runs the real retriever, `apps.search.eval:Retriever`: hybrid
        search over the fixture library, seeded and indexed in this test's database, asked
        the committed questions. It reports recall and accuracy per language. A mock anywhere
        in the chain scores but is never recorded, so a mock embedder behind a real reranker
        (`none`, the fused order) is refused by `--record` and the baseline is untouched. A
        chain with no mock in it — the keyword leg and the fused order, which is what D-09
        leaves a deployment with until a model is chosen — passes a recorded baseline it
        matches and fails one it falls short of by more than the tolerance, naming every
        metric of both tracks. That baseline is synthetic: the committed one stays
        unrecorded until a real embedder earns it (docs/TODO_FOR_alex.md, D-09). The
        classifier is the agents' and not this app's, so a stand-in answering the labels
        takes its place (`LabelledClassifier`). A question the library cannot answer gets
        no hit at all from the real retriever, which is the one answer the gate scores right.

        Operations: `rateAnswer`, the reader's verdict the evaluation set reads back
        (proved in tests_ask_limits.py).
        """
        gate = load_search_eval()
        questions = gate.load_jsonl(gate.EVAL / "retrieval.jsonl")
        # The mock classifier reads these predictions, so the first report shows the
        # classification track's languages beside the retrieval track's.
        texts = [dict(row, predictions=row["expected"]) for row in gate.load_jsonl(gate.EVAL / "classification.jsonl")]
        tolerance = gate.load_json(gate.EVAL / "tolerance.json")["metrics"]
        committed = gate.load_json(gate.EVAL / "baseline.json")
        counts = {"retrieval": len(questions), "classification": len(texts)}

        with tempfile.TemporaryDirectory() as folder:
            paths = gate.Paths(
                retrieval=gate.EVAL / "retrieval.jsonl",
                classification=Path(folder) / "classification.jsonl",
                baseline=Path(folder) / "baseline.json",
                tolerance=gate.EVAL / "tolerance.json",
            )
            paths.classification.write_text("\n".join(json.dumps(row) for row in texts), encoding="utf-8")

            def run(baseline: dict[str, Any], *argv: str) -> tuple[int, list[str]]:
                paths.baseline.write_text(json.dumps(baseline), encoding="utf-8")
                lines: list[str] = []
                return gate.run(["--retriever", SPEC, *argv], paths, out=lines.append), lines

            with override_settings(EMBEDDER_PROVIDER="mock", RERANKER_PROVIDER="none"):
                code, lines = run(committed, "--record")

            self.assertEqual(code, 1, lines)
            self.assertEqual(lines[-1], "search_eval: nothing to record: no real evaluator ran")
            self.assertEqual(json.loads(paths.baseline.read_text(encoding="utf-8")), committed)
            self.assertIn(f"  retrieval: {len(questions)} rows, evaluator {SPEC} (embedder mock, reranker none)", lines)
            for track, rows in (("retrieval", questions), ("classification", texts)):
                report = _track_report(lines, track)
                first = gate.TRACKS[track][0].split("_", 1)[1]  # the report drops the track's prefix
                for language in sorted({row["language"] for row in rows}):
                    with self.subTest(track=track, language=language):
                        self.assertTrue(any(line.startswith(f"    by language {language}: {first} ") for line in report), report)

            with override_settings(EMBEDDER_PROVIDER="none", RERANKER_PROVIDER="none"):
                retriever = Retriever()
                self.assertFalse(retriever.is_mock, retriever.name)
                measured = {
                    **gate.evaluate_retrieval(questions, retriever).metrics,
                    **gate.evaluate_classification(texts, LabelledClassifier()).metrics,
                }
                real = ("--classifier", CLASSIFIER)
                matched, _ = run(_recorded(committed, measured, rows=counts), *real)
                short = {metric: value + tolerance[metric] + 0.01 for metric, value in measured.items()}
                code, lines = run(_recorded(committed, short, rows=counts), *real)
                silent = retriever.search("quidditch", "en", None)
                with override_settings(RERANKER_PROVIDER="mock"):
                    self.assertTrue(retriever.is_mock, "a mock reranker alone makes the chain a mock")

        self.assertEqual(matched, 0, "a real chain within its tolerance passes")
        self.assertEqual(code, 1, lines)
        self.assertEqual(lines[-1], "search_eval: FAILED")
        self.assertEqual(sorted(measured), sorted(gate.METRICS), "both tracks were measured")
        for metric in gate.METRICS:
            with self.subTest(metric=metric):
                self.assertTrue(
                    any(line.startswith(f"  {metric}: {measured[metric]:.3f} is under the floor ") for line in lines), lines
                )
        self.assertEqual(silent, [], "a question the library cannot answer gets no hit")
        self.assertEqual((gate.recall_at_k([], silent), gate.reciprocal_rank([], silent)), (1.0, 1.0))

    def test_src_s11(self) -> None:
        """SRC-S11

        Only the library is indexed in R1 (SRC-01, D-10).

        Given a tenant writes a note carrying a distinctive phrase, when the index is
        built through the only door there is, then no chunk holds the phrase and no
        embedding was asked for it. The index is fed from three library sources and from
        nothing else, so a bank's own words have no way in: `SearchSource` names an
        obligation version, a provision version and a registered change, and a chunk is
        written only inside `index_write()` from apps/search/indexing.py.
        """
        seed_languages()
        phrase = "kvartalsrapporten fastnade i Ekeroth-flodet"  # nothing in the library says this
        tenant = factories.tenant(slug="src-s11")
        ProblemReport.objects.create(
            tenant=tenant,
            reporter=factories.member_user(tenant),
            subject_type=SubjectType.OBLIGATION.value,
            subject_id=uuid.uuid4(),
            text=phrase,
        )

        # The indexer runs with no tenant active, which is how a shared chunk is written
        # at all: since H15 a session inside a bank's zone cannot write the shared one.
        with mock.patch("apps.shared.adapters.embedder.MockEmbedder.embed") as embed:
            with tenancy.platform_zone(), index_write("SRC-S11: the library, and only the library"):
                SearchChunk(
                    source_type=SearchSource.OBLIGATION_VERSION.value,
                    source_id=uuid.uuid4(),
                    language_id="sv",
                    title="Lamna information om kostnader och avgifter",
                    body="Institutet ska lamna information om samtliga kostnader och avgifter.",
                ).save()

        self.assertEqual(SearchChunk.objects.count(), 1, "the index was built, so an empty index is not the reason")
        self.assertFalse(SearchChunk.objects.filter(title__icontains=phrase).exists())
        self.assertFalse(SearchChunk.objects.filter(body__icontains=phrase).exists())
        self.assertFalse(
            SearchChunk.objects.filter(tsv=SearchQuery("Ekeroth", config="swedish")).exists(),
            "the tenant's words are searchable in the index",
        )
        embed.assert_not_called()
        self.assertEqual(
            sorted(SearchSource.values),
            ["change", "obligation_version", "provision_version"],
            "a source type outside the library would be a way in for a tenant's own words",
        )

    @skip("pending: SRC-S13 (REG-08, chunk 8)")
    def test_src_s13(self) -> None:
        """SRC-S13

        Nothing a tenant writes under a standard reaches the index or a model (REG-08, SRC-01).
        """


class HybridSearchScenarioTests(CorpusMixin, TestCase):
    """SRC-S1, SRC-S2 and SRC-S3, through `POST /search` against the indexed corpus.

    `search` is a read that needs a body, so it answers 200 and writes nothing, not even an
    audit row (AUD-01 audits changes, and nothing changed). The scenario client fails any
    2xx POST without an audit row, so these calls go through a plain client and assert the
    audit count is unchanged, exactly as the chunk 2 dry-run previews do.
    """

    reader: ClassVar[User]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        # Signing in is itself an audited act, so the session is opened before the count
        # each search is measured against.
        self.headers = sign_in(self.reader, tenant=self.tenant)

    def search(self, body: dict[str, Any]) -> Any:
        """One search by the seeded reader, through the real route and its real gate."""
        before = AuditEvent.objects.count()
        response = Client().post(SEARCH, data=body, content_type="application/json", **self.headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(AuditEvent.objects.count(), before, "a search changes nothing, so it writes no audit row")
        return response.json()

    def test_src_s1(self) -> None:
        """SRC-S1

        An identifier is won by keyword and a concept by vector in one query (SRC-01, AC-SRC1).

        Given the corpus is indexed with the mock embedder, when a reader searches
        "FFFS 2017:2" the first hit is that instrument's, matched by its words; when they
        search "nudging in onboarding" the conduct obligation comes back matched by its
        meaning, because not one of those words is in its text. Both answers are one
        statement over the chunk table, with the reranker given the fused window.

        Operations: `search`. `findSimilar` ranks these same chunks for an agent's key,
        proved in tests_similar.py.
        """
        with mock.patch.object(
            reranker.MockReranker, "rerank", autospec=True, side_effect=reranker.MockReranker.rerank
        ) as judged:
            with CaptureQueriesContext(connection) as queries:
                identifier = self.search({"q": FFFS, "lang": "sv"})

        first = identifier["items"][0]
        self.assertEqual(first["matchKind"], "keyword")
        self.assertEqual(first["instrumentShortName"], FFFS)
        self.assertEqual(
            len([query for query in queries.captured_queries if 'FROM "search_chunk"' in query["sql"]]),
            1,
            "both legs, every filter and everything a hit shows are one statement",
        )
        judged.assert_called_once()
        self.assertLessEqual(
            len(judged.call_args.kwargs["documents"]),
            reranker.get_reranker().top_k,
            "the reranker judges the fused window, not the corpus",
        )

        concept = self.search({"q": "nudging in onboarding"})

        self.assertEqual(concept["items"][0]["title"], WARNINGS_TITLE)
        self.assertEqual(concept["items"][0]["matchKind"], "concept")

    def test_src_s2(self) -> None:
        """SRC-S2

        Chunks are indexed per language with the matching text search configuration (SRC-01).

        Given the same duty summarised in Swedish and in Finnish, each chunk's tsvector is
        built in its own language's configuration. The Finnish text quotes the Swedish term
        word for word, and a Swedish query still does not reach it: it was stemmed as
        Finnish. So the Swedish chunk is the one that wins a Swedish reader's search, and
        the Finnish chunk the one that wins the same search read as Finnish. The reader
        gets one hit for the duty either way, in the language that read them best.
        """
        self.assertEqual(
            {
                chunk.language_id
                for chunk in SearchChunk.objects.filter(tsv=SearchQuery("kostnader", config="swedish"))
                if chunk.source_type == SearchSource.OBLIGATION_VERSION.value
            },
            {"sv"},
            "the Finnish chunk holds the word and is not reachable by a Swedish query",
        )

        as_swedish = self.search({"q": "kostnader", "lang": "sv"})
        as_finnish = self.search({"q": "kostnader", "lang": "fi"})
        swedish_titles = [hit["title"] for hit in as_swedish["items"]]
        finnish_titles = [hit["title"] for hit in as_finnish["items"]]

        self.assertIn(COSTS_TITLE_SV, swedish_titles)
        self.assertNotIn(COSTS_TITLE_FI, swedish_titles)
        self.assertIn(COSTS_TITLE_FI, finnish_titles)
        self.assertNotIn(COSTS_TITLE_SV, finnish_titles)
        self.assertEqual(
            {hit["title"]: hit["matchKind"] for hit in as_swedish["items"]}[COSTS_TITLE_SV],
            "both",
            "the Swedish chunk is reached by the words and by the meaning",
        )

    def test_src_s3(self) -> None:
        """SRC-S3

        Filters come from vocabularies, "as of" picks the version, and each hit states its match kind (SRC-02).

        Filtering by jurisdiction "se" and duty type "reporting" as of 30 June 2026 returns
        only the chunks valid on that date carrying those keys: the second version had not
        taken effect, and the EU guidance is another jurisdiction. Every hit says how it
        matched, and renaming the duty type's label afterwards changes nothing, because what
        travelled was the key.
        """
        body = {
            "q": "report capital adequacy",
            "asOf": "2026-06-30",
            "filters": {"jurisdiction": "se", "dutyType": "reporting"},
        }

        answer = self.search(body)

        self.assertEqual([hit["title"] for hit in answer["items"]], [REPORTING_TITLE])
        self.assertEqual(answer["asOf"], "2026-06-30")
        self.assertEqual(answer["items"][0]["versionNo"], 1)
        self.assertEqual(answer["items"][0]["validTo"], "2026-08-31", "the version in force on that date")
        self.assertIn("quarter", answer["items"][0]["snippet"])
        self.assertTrue(all(hit["matchKind"] for hit in answer["items"]), "every hit states its match kind")
        self.assertNotIn(EU_REPORTING_TITLE, [hit["title"] for hit in answer["items"]])

        with library_write("SRC-S3: an administrator relabels a vocabulary row"):
            DutyType.objects.get(key="reporting").labels.filter(language="en").update(text="Supervisory returns")

        self.assertEqual(self.search(body), answer, "the filter carried a key, so a new label changes nothing")


# ---------------------------------------------------------------------------------------
# SRC-S8: the release gate's harness, run the way the gate runs it
# ---------------------------------------------------------------------------------------
class BudgetScenarioTests(CorpusMixin, TestCase):
    """SRC-S9, through the real routes against the indexed corpus."""

    reader: ClassVar[User]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)

    def test_src_s9(self) -> None:
        """SRC-S9

        Search and Ask stay within their budgets and are rate limited (SRC-01, NFR-02).

        Given the indexed corpus and a warm cache, hybrid search answers inside
        `SEARCH_BUDGET_MS` without the reranker and `SEARCH_RERANKED_BUDGET_MS` with it,
        reporting its time in `Server-Timing`; Ask's first event, the answer's id, leaves
        inside `ASK_FIRST_TOKEN_BUDGET_MS`. Measured on thread time and on the fastest of
        five runs with the coverage tracer off, as the other budgets are, so a loaded
        machine cannot fail a gate about the query. r1-perf records the medians against a
        production build.

        When a reader spends a bucket (`limits.py`, a setting each), the next search and
        the next question answer 429 `rate_limited`, before anything is read.
        """
        headers = sign_in(self.reader, tenant=self.tenant)
        client = Client()
        query = {"q": "kostnader och avgifter", "lang": "sv"}
        question = {"question": "What must we disclose about costs and charges?", "lang": "en"}

        def search() -> Any:
            return client.post(SEARCH, data=query, content_type="application/json", **headers)

        def first_event() -> bytes:
            response: Any = client.post(ASK, data=question, content_type="application/json", **headers)
            self.assertEqual(response.status_code, 200, getattr(response, "content", b""))
            stream = iter(response.streaming_content)
            first = next(stream)
            list(stream)  # the rest of the answer, which is outside the first-token budget
            return cast(bytes, first)

        warm = search()
        self.assertEqual(warm.status_code, 200, warm.content)
        self.assertRegex(warm["Server-Timing"], r"^app;dur=\d+\.\d$")
        self.assertIn(b'"event": "start"', first_event())

        def fastest(call: Any) -> float:
            spent = []
            for _ in range(5):
                started = time.thread_time()
                call()
                spent.append((time.thread_time() - started) * 1000)
            return min(spent)

        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            reranked = fastest(search)
            with override_settings(RERANKER_PROVIDER="none"):
                unranked = fastest(search)
            asked = fastest(first_event)
        finally:
            sys.settrace(tracer)
        self.assertLess(reranked, settings.SEARCH_RERANKED_BUDGET_MS, "the reranker is on in this run")
        self.assertLess(unranked, settings.SEARCH_BUDGET_MS)
        self.assertLess(asked, settings.ASK_FIRST_TOKEN_BUDGET_MS)

        cache.clear()  # the runs above spent from the reader's buckets
        with override_settings(
            RATE_LIMITING_ENABLED=True, SEARCH_RATE_PER_USER_PER_MINUTE=1, ASK_RATE_PER_USER_PER_MINUTE=1
        ):
            self.assertEqual(search().status_code, 200)
            refused_search = search()
            self.assertEqual(first_event()[:6], b"data: ")
            refused_ask = client.post(ASK, data=question, content_type="application/json", **headers)
        for refused in (refused_search, refused_ask):
            with self.subTest(route=refused.request["PATH_INFO"]):
                self.assertEqual(refused.status_code, 429, refused.content)
                self.assertEqual(refused.json()["code"], "rate_limited")


class LabelledClassifier:
    """SRC-S8's stand-in for the agents' classifier, which is not this app's: it answers every
    text of the committed set with its label. It is not a mock, so the gate holds it to a
    recorded classification baseline the way it will hold the real one, and the only
    baseline it ever meets is SRC-S8's synthetic one in a temporary folder."""

    name = CLASSIFIER
    is_mock = False

    def __init__(self) -> None:
        gate = load_search_eval()
        self._labels = {row["text"]: row["expected"] for row in gate.load_jsonl(gate.EVAL / "classification.jsonl")}

    def classify(self, text: str) -> dict[str, Any]:
        return dict(self._labels[text])


def _track_report(lines: list[str], track: str) -> list[str]:
    """One track's lines of the report: its heading and everything indented under it."""
    start = next(index for index, line in enumerate(lines) if line.startswith(f"  {track}: "))
    end = next((index for index in range(start + 1, len(lines)) if not lines[index].startswith("    ")), len(lines))
    return lines[start:end]


def _recorded(baseline: dict[str, Any], metrics: dict[str, float], *, rows: dict[str, int]) -> dict[str, Any]:
    """A synthetic baseline with every track in `rows` recorded at these values. It is never
    written to eval/baseline.json, which only a real run's `--record` may change."""
    synthetic = json.loads(json.dumps(baseline))
    synthetic["recorded"] = True
    for track, count in rows.items():
        synthetic["tracks"][track] = {"recorded": True, "recorded_at": "SRC-S8", "evaluator": "synthetic", "rows": count}
    synthetic["metrics"].update(metrics)
    return synthetic


# ---------------------------------------------------------------------------------------
# SRC-S4 to SRC-S6: Ask (SRC-03, AC-SRC2)
# ---------------------------------------------------------------------------------------
# The library's own words, which is all a passage may say: a line of the prompt that is not
# one of these is text that came from somewhere else.
LIBRARY_SUMMARIES = {
    COSTS_SUMMARY_SV,
    COSTS_SUMMARY_FI,
    WARNINGS_SUMMARY,
    REPORTING_SUMMARY_V1,
    REPORTING_SUMMARY_V2,
    EU_REPORTING_SUMMARY,
}
# SRC-S12's conformance duty: an invented standard, named by an invented title, with no
# clause text, which is all the library ever holds of a standard (INV-08, D-35).
STANDARD_CONFORMANCE_SUMMARY = (
    "The institution conforms to the Example Security Standard and meets what it requires of every control it applies."
)
PASSAGE_LINE = re.compile(r"^\[(\d+)\] (.+) \(([^()]+)\)$")


class AskScenarioTests(CorpusMixin, TestCase):
    """SRC-S4, SRC-S5, SRC-S6 and SRC-S12, through `POST /ask` against the indexed corpus, on the mock
    model that answers one cited sentence per passage it is given.

    An answer is a read that asks a model: it writes the one AI log row every model call
    writes (AUD-02) and no audit row, because no record changed. The scenario client fails
    any 2xx POST without an audit row, so these calls go through a plain client and assert
    the audit count is unchanged, exactly as the searches above do.
    """

    reader: ClassVar[User]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.build_corpus()
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        self.headers = sign_in(self.reader, tenant=self.tenant)

    def post(self, body: dict[str, Any]) -> Any:
        return Client().post(ASK, data=body, content_type="application/json", **self.headers)

    def events(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        """One question by the seeded reader, through the real route; the events it streamed."""
        before = AuditEvent.objects.count()
        response = self.post(body)
        self.assertEqual(response.status_code, 200, getattr(response, "content", b""))
        frames = b"".join(response.streaming_content).decode().splitlines()
        self.assertEqual(AuditEvent.objects.count(), before, "an answer changes no record, so it writes no audit row")
        return [json.loads(frame.removeprefix("data: ")) for frame in frames if frame.startswith("data: ")]

    def test_src_s4(self) -> None:
        """SRC-S4

        An answer cites every statement and flags pending changes (SRC-03, AC-SRC2).

        Given the library confirmed that an adopted change moves the capital adequacy
        reporting duty on 1 October, when a reader asks about that duty as of 15 September,
        every statement streamed carries a citation to a passage the answer lists, the
        statement resting on the reporting duty names the change and the day it takes
        effect, and the AI log row records the purpose, the model and its version, the
        input reference (the prompt's template and hash, never the prompt), the output and
        the citations.

        Operations: `ask`.
        """
        change = watch.change(authority=None, urgency=None, key_date=datetime.date(2026, 10, 1))
        watch.obligation_link(change, self.reporting)
        with tenancy.platform_zone(), watch_write("SRC-S4: the library confirms the link"):
            ChangeObligation.objects.filter(change=change).update(
                confirmed_by=factories.platform_user(), confirmed_at=watch.ANCHOR
            )

        with mock.patch.object(llm.MockLlm, "stream", autospec=True, side_effect=llm.MockLlm.stream) as model:
            events = self.events({"question": "capital adequacy reporting to the supervisor", "asOf": "2026-09-15", "lang": "en"})

        self.assertEqual((events[0]["event"], events[-1]["event"]), ("start", "answer"))
        answer = events[-1]["answer"]
        self.assertEqual(answer["id"], events[0]["id"])
        self.assertFalse(answer["noAnswer"])
        self.assertTrue(answer["aiGenerated"], "AI output stays labelled until a person confirms it")
        self.assertEqual(
            [event["statement"] for event in events if event["event"] == "statement"],
            answer["statements"],
            "each statement streamed as soon as it was grounded",
        )
        cited = {citation["index"]: citation for citation in answer["citations"]}
        self.assertTrue(answer["statements"])
        for statement in answer["statements"]:
            self.assertTrue(statement["citationIndexes"], statement)
            self.assertLessEqual(set(statement["citationIndexes"]), set(cited))
        reporting = [
            statement
            for statement in answer["statements"]
            if cited[statement["citationIndexes"][0]]["obligationId"] == str(self.reporting.id)
        ]
        self.assertEqual(
            [(s["pendingChangeId"], s["pendingChangeLabel"], s["pendingChangeInForceOn"]) for s in reporting],
            [(str(change.id), change.title, "2026-10-01")],
        )
        self.assertEqual(cited[reporting[0]["citationIndexes"][0]]["versionNo"], 2, "the version in force that day")

        row = AiGeneration.objects.get(pk=answer["id"])
        self.assertEqual(row.purpose, AiPurpose.ANSWER.value)
        self.assertEqual((row.model, row.model_version), (answer["model"], "0"))
        self.assertEqual(row.prompt_template, ask.PROMPT_TEMPLATE)
        call = model.call_args.kwargs
        self.assertEqual(row.prompt_hash, ai.prompt_hash(call["system"], call["prompt"]))
        self.assertTrue(row.output)
        self.assertEqual(
            row.citations,
            [
                {"label": f"{c['instrumentShortName']}, {c['refLabel']}", "url": "https://www.example.test/source"}
                for c in answer["citations"]
            ],
        )

    def test_src_s5(self) -> None:
        """SRC-S5

        A question without support returns "no answer" (SRC-03, AC-SRC2).

        Given nothing in the library, inside the bank's scope, is about crypto custody, when a
        reader asks about it, the answer is `noAnswer` with no statement and no citation, no
        model was asked to guess, and nothing is logged as if one had been.

        Operations: `ask`.
        """
        with mock.patch.object(llm.MockLlm, "stream", autospec=True) as model:
            events = self.events({"question": "Do we need a licence for crypto custody?", "lang": "en"})

        model.assert_not_called()
        self.assertEqual([event["event"] for event in events], ["start", "answer"])
        answer = events[-1]["answer"]
        self.assertTrue(answer["noAnswer"])
        self.assertEqual((answer["statements"], answer["citations"]), ([], []))
        self.assertFalse(AiGeneration.objects.exists())

    def test_src_s6(self) -> None:
        """SRC-S6

        The Ask question is the only tenant text sent to a model, and a tenant can switch it off (SRC-03).

        Given the bank has a note of its own on the obligation the question is about, when a
        reader asks, the prompt holds the passages, each the library's own words and where
        they sit, and the question on one line, and nothing else: not the note, not the
        bank's name. When the bank switches its AI features off, the same question answers
        403 `feature_off` before any stream opens, having retrieved nothing and asked no
        model.

        Operations: `ask`.
        """
        question = "What must we disclose about costs and charges?"
        ProblemReport.objects.create(
            tenant=self.tenant,
            reporter=self.reader,
            subject_type=SubjectType.OBLIGATION.value,
            subject_id=self.costs.id,
            text="Our Ekeroth desk discloses costs only on request.",
        )

        with mock.patch.object(llm.MockLlm, "stream", autospec=True, side_effect=llm.MockLlm.stream) as model:
            self.events({"question": question, "lang": "en"})

        passages, asked = model.call_args.kwargs["prompt"].split("\n\nQuestion: ")
        self.assertEqual(asked, question)
        lines = passages.splitlines()
        self.assertEqual(lines[0], "Passages:")
        self.assertTrue(lines[1:], "the question was answered from at least one passage")
        for number, line in enumerate(lines[1:], start=1):
            match = PASSAGE_LINE.match(line)
            self.assertIsNotNone(match, line)
            assert match is not None
            self.assertEqual(int(match.group(1)), number)
            self.assertIn(match.group(2), LIBRARY_SUMMARIES, "a passage is the library's own words")
        for own in ("Ekeroth", self.tenant.name, self.reader.name, self.reader.email):
            self.assertNotIn(own, model.call_args.kwargs["prompt"])
            self.assertNotIn(own, model.call_args.kwargs["system"])

        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            Tenant.objects.filter(pk=self.tenant.id).update(ai_enabled=False)
        logged = AiGeneration.objects.count()
        with (
            mock.patch.object(llm.MockLlm, "stream", autospec=True) as model,
            mock.patch.object(hybrid, "passages", autospec=True) as retrieval,
        ):
            response = self.post({"question": question, "lang": "en"})

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("event-stream", response["Content-Type"])
        self.assertEqual(response.json()["code"], "feature_off")
        model.assert_not_called()
        retrieval.assert_not_called()
        self.assertEqual(AiGeneration.objects.count(), logged)

    def test_src_s12(self) -> None:
        """SRC-S12

        A question about a standard's control gets "no answer" (SRC-03, SRC-05, INV-08).

        Given the library holds an invented standard's edition with its conformance duty and
        no clause text, filed under a level whose kind is `standard` and whose key is its
        own, when a reader searches what one of its controls requires, Search finds the
        conformance duty; when they ask the same question, the answer is `noAnswer`, no
        statement, no citation, no model asked and nothing logged, because Ask never gives
        a model an obligation under a standard (D-81). The kind decides and never the key,
        which is why the level here is not the seeded `standard` row. The evaluation set
        holds a question about a standard's control expecting no answer, scored against
        Ask's passages, and it gates the release with every other row.

        Operations: `ask`, `search`.
        """
        question = "What does the Example Security Standard require of a control?"
        with tenancy.platform_zone(), library_write("SRC-S12: an invented standard's edition and its conformance duty"):
            tier = InstrumentLevel.objects.create(
                key="src-s12-standards-tier", kind=InstrumentLevelKind.STANDARD.value, binding_default=False, rank=900
            )
            edition = _instrument(
                key="example-security-standard-2031",
                official_ref="EXS 9999:2031",
                jurisdiction="intl",
                binding=False,
                level=tier.key,
            )
            conformance = _obligation(
                edition,
                key="obl-example-security-standard-conformance",
                ref_label="Conformance",
                duty_type="governance",
                titles={"en": "Conform to the Example Security Standard"},
                versions=((FIRST_DAY, {"en": STANDARD_CONFORMANCE_SUMMARY}),),
            )
        indexing.reindex_all()
        indexing.embed_backlog()

        found = Client().post(
            SEARCH, data={"q": question, "lang": "en"}, content_type="application/json", **self.headers
        )
        self.assertEqual(found.status_code, 200, found.content)
        self.assertIn(
            str(conformance.id),
            [hit["id"] for hit in found.json()["items"]],
            "Search still finds the conformance duty, so the question does reach it",
        )

        with mock.patch.object(llm.MockLlm, "stream", autospec=True) as model:
            events = self.events({"question": question, "lang": "en"})

        model.assert_not_called()
        self.assertEqual([event["event"] for event in events], ["start", "answer"])
        answer = events[-1]["answer"]
        self.assertTrue(answer["noAnswer"])
        self.assertEqual((answer["statements"], answer["citations"]), ([], []))
        self.assertFalse(AiGeneration.objects.exists(), "no model was asked, so nothing is logged as if one had been")

        gate = load_search_eval()
        rows = [row for row in gate.load_jsonl(gate.EVAL / "retrieval.jsonl") if row.get("via") == "ask"]
        self.assertTrue(rows, "the evaluation set holds a question Ask must not answer")
        for row in rows:
            with self.subTest(row=row["id"]):
                self.assertEqual(row["expected"], [], "a question about a standard's control expects no answer")
                self.assertRegex(row["query"], "(?i)control")
