"""Scenario stubs for the search app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: SRC.
"""

import importlib.util
import json
import sys
import tempfile
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar
from unittest import mock, skip

from django.conf import settings
from django.contrib.postgres.search import SearchQuery
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.identity.models import User
from apps.library.models import ProblemReport, SubjectType
from apps.library.seeds import seed_languages
from apps.search.eval import SPEC, Retriever
from apps.search.indexing import index_write
from apps.search.models import SearchChunk, SearchSource
from apps.search.tests_hybrid import (
    COSTS_TITLE_FI,
    COSTS_TITLE_SV,
    EU_REPORTING_TITLE,
    FFFS,
    REPORTING_TITLE,
    WARNINGS_TITLE,
    CorpusMixin,
)
from apps.shared import factories, tenancy
from apps.shared.adapters import reranker
from apps.shared.models import AuditEvent
from apps.shared.testing import sign_in
from apps.taxonomy.models import DutyType
from apps.shared.tenancy import library_write

SEARCH = "/api/v1/search"


class SearchScenarioTests(TestCase):
    """Scenario tests for apps.search, one method per @integration scenario."""

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
        matches and fails one it falls short of by more than the tolerance, naming the
        metric. That baseline is synthetic: the committed one stays unrecorded until a real
        embedder earns it (docs/TODO_FOR_alex.md, D-09).

        Operations: `rateAnswer`, the reader's verdict the evaluation set reads back.
        It answers 501 not_built until the Ask backend lands.
        """
        gate = _load_search_eval()
        questions = gate.load_jsonl(gate.EVAL / "retrieval.jsonl")
        # The classifier is not this app's; the mock stands in for it so the report shows
        # the classification track's languages beside the retrieval track's.
        texts = [dict(row, predictions=row["expected"]) for row in gate.load_jsonl(gate.EVAL / "classification.jsonl")]
        tolerance = gate.load_json(gate.EVAL / "tolerance.json")["metrics"]
        committed = gate.load_json(gate.EVAL / "baseline.json")

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
                measured = gate.evaluate_retrieval(questions, retriever).metrics
                matched, _ = run(_recorded(committed, measured, rows=len(questions)))
                short = {metric: value + tolerance[metric] + 0.01 for metric, value in measured.items()}
                code, lines = run(_recorded(committed, short, rows=len(questions)))
                with override_settings(RERANKER_PROVIDER="mock"):
                    self.assertTrue(retriever.is_mock, "a mock reranker alone makes the chain a mock")

        self.assertEqual(matched, 0, "a real chain within its tolerance passes")
        self.assertEqual(code, 1, lines)
        self.assertEqual(lines[-1], "search_eval: FAILED")
        for metric in gate.RETRIEVAL_METRICS:
            self.assertTrue(
                any(line.startswith(f"  {metric}: {measured[metric]:.3f} is under the floor ") for line in lines), lines
            )

    @skip("pending: SRC-S9")
    def test_src_s9(self) -> None:
        """SRC-S9

        Search and Ask stay within their budgets and are rate limited (SRC-01, NFR-02).
        """

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
# SRC-S8: the release gate's harness, loaded from scripts/ the way the gate runs it
# ---------------------------------------------------------------------------------------
def _load_search_eval() -> ModuleType:
    script = Path(settings.BASE_DIR) / "scripts" / "search_eval.py"
    spec = importlib.util.spec_from_file_location("search_eval_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {spec.name: module}):  # its dataclasses look themselves up
        spec.loader.exec_module(module)
    return module


def _track_report(lines: list[str], track: str) -> list[str]:
    """One track's lines of the report: its heading and everything indented under it."""
    start = next(index for index, line in enumerate(lines) if line.startswith(f"  {track}: "))
    end = next((index for index in range(start + 1, len(lines)) if not lines[index].startswith("    ")), len(lines))
    return lines[start:end]


def _recorded(baseline: dict[str, Any], metrics: dict[str, float], *, rows: int) -> dict[str, Any]:
    """A synthetic baseline with the retrieval track recorded at these values. It is never
    written to eval/baseline.json, which only a real run's `--record` may change."""
    synthetic = json.loads(json.dumps(baseline))
    synthetic["recorded"] = True
    synthetic["tracks"]["retrieval"] = {"recorded": True, "recorded_at": "SRC-S8", "evaluator": SPEC, "rows": rows}
    synthetic["metrics"].update(metrics)
    return synthetic
