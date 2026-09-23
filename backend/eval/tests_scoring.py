"""Unit tests for the scoring and gate logic of scripts/search_eval.py.

Run with `python scripts/search_eval.py --self-test`. This directory is not a Django app and
the harness needs no database, so `manage.py test apps` does not find these tests itself;
`apps/search/tests_eval.py` runs the self-test instead, because CI runs the gate without
`--self-test` and nothing that blocks a build would run them otherwise."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "scripts"))

import search_eval as se  # noqa: E402

EXPECTED = {"change_type": "adopted", "flags": ["ai"], "scope": {"regime": ["securities", "ai_ict"], "service_type": ["advice"]}, "risk_flags": []}


def blank_baseline() -> dict:
    return {
        "recorded": False,
        "tracks": {"retrieval": {"recorded": False}, "classification": {"recorded": False}},
        "metrics": {m: None for m in se.METRICS},
    }


def recorded_baseline() -> dict:
    return {
        "recorded": True,
        "tracks": {
            "retrieval": {"recorded": True, "recorded_at": "2026-10-01T00:00:00+00:00", "evaluator": "apps.search.eval:Retriever", "rows": 2},
            "classification": {"recorded": True, "recorded_at": "2026-10-01T00:00:00+00:00", "evaluator": "apps.agents.eval:Classifier", "rows": 2},
        },
        "metrics": {m: 0.9 for m in se.METRICS},
    }


def tolerance() -> dict:
    return {"metrics": {m: 0.05 for m in se.METRICS}}


class RetrievalScoring(unittest.TestCase):
    def test_recall_at_k_counts_expected_keys_in_the_top_k(self) -> None:
        self.assertEqual(se.recall_at_k(["a", "b"], ["b", "x", "a"]), 1.0)
        self.assertEqual(se.recall_at_k(["a", "b"], ["x", "a"]), 0.5)
        self.assertEqual(se.recall_at_k(["a"], ["x"] * 10 + ["a"]), 0.0)
        self.assertEqual(se.recall_at_k(["a"], []), 0.0)
        self.assertEqual(se.recall_at_k([], ["a"]), 0.0)

    def test_reciprocal_rank_uses_the_first_relevant_hit(self) -> None:
        self.assertEqual(se.reciprocal_rank(["a", "b"], ["b", "a"]), 1.0)
        self.assertEqual(se.reciprocal_rank(["a"], ["x", "y", "a"]), 1 / 3)
        self.assertEqual(se.reciprocal_rank(["a"], ["x"]), 0.0)

    def test_evaluate_retrieval_reports_overall_per_language_and_per_match_kind(self) -> None:
        rows = [
            {"id": "1", "language": "en", "query": "q1", "expected": ["a"], "match_kind": "keyword", "predictions": ["a"]},
            {"id": "2", "language": "sv", "query": "q2", "expected": ["b"], "match_kind": "concept", "as_of": "2026-09-01", "predictions": ["x", "b"]},
        ]
        result = se.evaluate_retrieval(rows, se.MockRetriever(rows))
        self.assertEqual(result.status, "scored")
        self.assertTrue(result.is_mock)
        self.assertEqual(result.metrics["retrieval_recall_at_10"], 1.0)
        self.assertAlmostEqual(result.metrics["retrieval_mrr"], 0.75)
        self.assertEqual(result.per_language["sv"]["retrieval_mrr"], 0.5)
        self.assertEqual(result.per_group["keyword"]["retrieval_mrr"], 1.0)

    def test_mock_retriever_is_available_only_when_every_row_predicts(self) -> None:
        rows = [{"id": "1", "language": "en", "query": "q", "expected": ["a"], "match_kind": "keyword"}]
        self.assertFalse(se.MockRetriever(rows).available)
        self.assertFalse(se.MockRetriever([]).available)
        rows[0]["predictions"] = ["a"]
        mock = se.MockRetriever(rows)
        self.assertTrue(mock.available)
        self.assertEqual(mock.search("q", "en", None), ["a"])
        self.assertEqual(mock.search("q", "en", date(2026, 1, 1)), [])


class ClassificationScoring(unittest.TestCase):
    def test_exact_prediction_scores_one_on_every_field(self) -> None:
        self.assertEqual(se.score_classification(EXPECTED, json.loads(json.dumps(EXPECTED))), {m: 1.0 for m in se.CLASSIFICATION_METRICS})

    def test_each_field_is_scored_on_its_own(self) -> None:
        predicted = {"change_type": "proposal", "flags": [], "scope": {"regime": ["securities"], "service_type": ["advice"]}, "risk_flags": ["embedded_instructions"]}
        scores = se.score_classification(EXPECTED, predicted)
        self.assertEqual(scores["classification_change_type_accuracy"], 0.0)
        self.assertEqual(scores["classification_flags_accuracy"], 0.0)
        self.assertAlmostEqual(scores["classification_scope_accuracy"], (0.5 + 1.0) / 2)
        self.assertEqual(scores["classification_screen_accuracy"], 0.0)

    def test_empty_scope_matches_empty_or_missing_dimension(self) -> None:
        expected = dict(EXPECTED, scope={"regime": [], "account_type": []})
        self.assertEqual(se.score_classification(expected, {"change_type": "adopted", "flags": ["ai"], "scope": {"regime": []}})["classification_scope_accuracy"], 1.0)
        self.assertEqual(se.score_classification(expected, {})["classification_scope_accuracy"], 1.0)

    def test_evaluate_classification_splits_clean_and_injection_rows(self) -> None:
        rows = [
            {"id": "c", "language": "en", "text": "clean", "injection": False, "expected": EXPECTED, "predictions": EXPECTED},
            {"id": "i", "language": "da", "text": "dirty", "injection": True, "expected": dict(EXPECTED, risk_flags=["embedded_instructions"]), "predictions": EXPECTED},
        ]
        result = se.evaluate_classification(rows, se.MockClassifier(rows))
        self.assertEqual(result.metrics["classification_screen_accuracy"], 0.5)
        self.assertEqual(result.per_group["injection"]["classification_screen_accuracy"], 0.0)
        self.assertEqual(result.per_group["clean"]["classification_screen_accuracy"], 1.0)
        self.assertEqual(result.per_language["da"]["classification_change_type_accuracy"], 1.0)


class Gate(unittest.TestCase):
    def test_not_available_passes_only_while_unrecorded(self) -> None:
        missing = se.TrackResult("not_available", "none", False)
        self.assertEqual(se.decide("retrieval", missing, blank_baseline(), tolerance()), [])
        failures = se.decide("retrieval", missing, recorded_baseline(), tolerance())
        self.assertEqual(len(failures), 1)
        self.assertIn("apps.search.eval:Retriever", failures[0])

    def test_mock_never_satisfies_a_recorded_baseline(self) -> None:
        mocked = se.TrackResult("scored", "mock", True, metrics={m: 1.0 for m in se.RETRIEVAL_METRICS})
        self.assertEqual(se.decide("retrieval", mocked, blank_baseline(), tolerance()), [])
        self.assertEqual(len(se.decide("retrieval", mocked, recorded_baseline(), tolerance())), 1)

    def test_drop_beyond_tolerance_fails_and_within_passes(self) -> None:
        within = se.TrackResult("scored", "real", False, metrics={"retrieval_recall_at_10": 0.86, "retrieval_mrr": 0.9})
        self.assertEqual(se.decide("retrieval", within, recorded_baseline(), tolerance()), [])
        below = se.TrackResult("scored", "real", False, metrics={"retrieval_recall_at_10": 0.84, "retrieval_mrr": 0.9})
        failures = se.decide("retrieval", below, recorded_baseline(), tolerance())
        self.assertEqual(len(failures), 1)
        self.assertIn("retrieval_recall_at_10", failures[0])

    def test_zero_tolerance_on_the_screen_fails_any_drop(self) -> None:
        tol = tolerance()
        tol["metrics"]["classification_screen_accuracy"] = 0.0
        result = se.TrackResult("scored", "real", False, metrics={m: 0.9 for m in se.CLASSIFICATION_METRICS})
        self.assertEqual(se.decide("classification", result, recorded_baseline(), tol), [])
        result.metrics["classification_screen_accuracy"] = 0.899
        self.assertEqual(len(se.decide("classification", result, recorded_baseline(), tol)), 1)

    def test_record_writes_scored_real_tracks_and_refuses_mock(self) -> None:
        real = se.TrackResult("scored", "apps.search.eval:Retriever", False, metrics={"retrieval_recall_at_10": 0.91234, "retrieval_mrr": 0.8}, rows=53)
        mocked = se.TrackResult("scored", "mock", True, metrics={m: 1.0 for m in se.CLASSIFICATION_METRICS})
        updated = se.record(blank_baseline(), {"retrieval": real, "classification": mocked}, now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertTrue(updated["recorded"])
        self.assertTrue(updated["tracks"]["retrieval"]["recorded"])
        self.assertFalse(updated["tracks"]["classification"]["recorded"])
        self.assertEqual(updated["metrics"]["retrieval_recall_at_10"], 0.9123)
        self.assertEqual(updated["tracks"]["retrieval"]["recorded_at"], "2026-10-01T00:00:00+00:00")
        with self.assertRaises(ValueError):
            se.record(blank_baseline(), {"retrieval": mocked, "classification": mocked})

    def test_baseline_validation_catches_inconsistent_flags(self) -> None:
        bad = blank_baseline()
        bad["recorded"] = True
        with self.assertRaises(ValueError):
            se.validate_baseline(bad)
        bad = recorded_baseline()
        bad["metrics"]["retrieval_mrr"] = None
        with self.assertRaises(ValueError):
            se.validate_baseline(bad)
        se.validate_baseline(recorded_baseline())
        se.validate_baseline(blank_baseline())


class EndToEnd(unittest.TestCase):
    """Runs the CLI against temporary copies of the sets."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = se.Paths(root / "retrieval.jsonl", root / "classification.jsonl", root / "baseline.json", root / "tolerance.json")
        self.output: list[str] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, retrieval: list[dict], classification: list[dict], baseline: dict, tol: dict | None = None) -> None:
        self.paths.retrieval.write_text("# c\n" + "\n".join(json.dumps(r) for r in retrieval) + "\n", encoding="utf-8")
        self.paths.classification.write_text("\n".join(json.dumps(r) for r in classification) + "\n", encoding="utf-8")
        self.paths.baseline.write_text(json.dumps(baseline), encoding="utf-8")
        self.paths.tolerance.write_text(json.dumps(tol or tolerance()), encoding="utf-8")

    def run_cli(self, *argv: str) -> int:
        return se.run(list(argv), self.paths, out=self.output.append)

    def rows(self, predict: bool) -> tuple[list[dict], list[dict]]:
        r = {"id": "1", "language": "en", "query": "q", "expected": ["a"], "match_kind": "keyword"}
        c = {"id": "c", "language": "en", "text": "t", "injection": False, "expected": EXPECTED}
        if predict:
            r["predictions"] = ["a"]
            c["predictions"] = EXPECTED
        return [r], [c]

    def test_unrecorded_baseline_without_evaluators_passes_as_not_available(self) -> None:
        self.write(*self.rows(False), blank_baseline())
        self.assertEqual(self.run_cli(), 0)
        self.assertTrue(any("not available yet" in line for line in self.output))
        self.assertEqual(self.output[-1], "search_eval: ok")

    def test_recorded_baseline_without_evaluators_fails_loudly(self) -> None:
        self.write(*self.rows(False), recorded_baseline())
        self.assertEqual(self.run_cli(), 1)
        self.assertEqual(self.output[-1], "search_eval: FAILED")
        self.assertTrue(any("retrieval: baseline recorded" in line for line in self.output))
        self.assertTrue(any("classification: baseline recorded" in line for line in self.output))

    def test_mock_predictions_score_but_cannot_be_recorded(self) -> None:
        self.write(*self.rows(True), blank_baseline())
        self.assertEqual(self.run_cli(), 0)
        self.assertTrue(any("retrieval_recall_at_10: 1.000" in line for line in self.output))
        self.assertEqual(self.run_cli("--record"), 1)
        self.assertFalse(json.loads(self.paths.baseline.read_text(encoding="utf-8"))["recorded"])

    def test_real_evaluator_records_then_gates(self) -> None:
        self.write(*self.rows(False), blank_baseline())
        self.assertEqual(self.run_cli("--retriever", "tests_scoring:PerfectRetriever", "--classifier", "tests_scoring:PerfectClassifier", "--record"), 0)
        baseline = json.loads(self.paths.baseline.read_text(encoding="utf-8"))
        self.assertTrue(baseline["recorded"])
        self.assertEqual(baseline["metrics"]["classification_screen_accuracy"], 1.0)
        self.assertEqual(self.run_cli("--retriever", "tests_scoring:PerfectRetriever", "--classifier", "tests_scoring:PerfectClassifier"), 0)
        self.assertEqual(self.run_cli("--retriever", "tests_scoring:EmptyRetriever", "--classifier", "tests_scoring:PerfectClassifier"), 1)
        self.assertTrue(any("retrieval_recall_at_10: 0.000 is under the floor" in line for line in self.output))
        self.assertEqual(self.run_cli("--classifier", "tests_scoring:PerfectClassifier"), 1)

    def test_malformed_inputs_fail_with_the_file_named(self) -> None:
        retrieval, classification = self.rows(False)
        self.write(retrieval, classification, blank_baseline())
        self.paths.retrieval.write_text('{"id": "1"\n', encoding="utf-8")
        self.assertEqual(self.run_cli(), 1)
        self.assertIn("retrieval.jsonl:1", self.output[-1])
        self.write(retrieval, classification, blank_baseline())
        self.paths.tolerance.unlink()
        self.assertEqual(self.run_cli(), 1)
        self.assertIn("tolerance.json is missing", self.output[-1])
        classification[0]["injection"] = True
        self.write(retrieval, classification, blank_baseline())
        self.assertEqual(self.run_cli(), 1)
        self.assertIn("injection and risk_flags disagree", self.output[-1])

    def test_unknown_evaluator_spec_fails(self) -> None:
        self.write(*self.rows(False), blank_baseline())
        self.assertEqual(self.run_cli("--retriever", "no.such.module:Thing"), 1)
        self.assertIn("cannot be imported", self.output[-1])
        self.assertEqual(self.run_cli("--retriever", "tests_scoring:Missing"), 1)

    def test_a_backend_module_can_be_named_from_the_script(self) -> None:
        """`apps.search.eval:Retriever` is found although Python puts only scripts/ on the path."""
        self.write(*self.rows(False), blank_baseline())
        self.assertEqual(self.run_cli("--retriever", "apps.shared.kinds:Missing"), 1)
        self.assertIn("Missing is not in apps.shared.kinds", self.output[-1])

    def test_every_run_names_the_tracks_that_do_not_gate_yet(self) -> None:
        self.write(*self.rows(False), blank_baseline())
        self.assertEqual(self.run_cli(), 0)
        self.assertIn("search_eval: no baseline is recorded for retrieval or classification, so a drop there fails nothing yet", self.output)

        half = recorded_baseline()
        half["tracks"]["retrieval"] = {"recorded": False}
        half["metrics"].update({m: None for m in se.RETRIEVAL_METRICS})
        self.write(*self.rows(False), half)
        self.output.clear()
        self.assertEqual(self.run_cli("--classifier", "tests_scoring:PerfectClassifier"), 0)
        self.assertIn("search_eval: no baseline is recorded for retrieval, so a drop there fails nothing yet", self.output)

        self.write(*self.rows(False), recorded_baseline())
        self.output.clear()
        self.assertEqual(self.run_cli("--retriever", "tests_scoring:PerfectRetriever", "--classifier", "tests_scoring:PerfectClassifier"), 0)
        self.assertFalse(any("no baseline is recorded" in line for line in self.output))


class PerfectRetriever:
    name = "tests_scoring:PerfectRetriever"
    is_mock = False

    def search(self, query: str, lang: str, as_of: date | None) -> list[str]:
        return ["a"]


class EmptyRetriever(PerfectRetriever):
    name = "tests_scoring:EmptyRetriever"

    def search(self, query: str, lang: str, as_of: date | None) -> list[str]:
        return []


class PerfectClassifier:
    name = "tests_scoring:PerfectClassifier"
    is_mock = False

    def classify(self, text: str) -> dict:
        return json.loads(json.dumps(EXPECTED))


class RealSets(unittest.TestCase):
    """The committed sets load, validate and meet the minimum sizes the gate promises."""

    def test_committed_sets_are_well_formed(self) -> None:
        retrieval = se.load_jsonl(se.EVAL / "retrieval.jsonl")
        classification = se.load_jsonl(se.EVAL / "classification.jsonl")
        se.validate_retrieval(retrieval)
        se.validate_classification(classification)
        self.assertGreaterEqual(len(retrieval), 40)
        self.assertEqual({r["language"] for r in retrieval}, {"en", "sv", "da", "nb", "fi"})
        self.assertGreaterEqual(len([r for r in classification if not r["injection"]]), 40)
        self.assertGreaterEqual(len([r for r in classification if r["injection"]]), 10)
        self.assertTrue(all("predictions" not in r for r in retrieval + classification), "committed sets carry no mock predictions")
        se.validate_baseline(se.load_json(se.EVAL / "baseline.json"))
        se.validate_tolerance(se.load_json(se.EVAL / "tolerance.json"))


class NoAnswerQuestions(unittest.TestCase):
    """A retrieval row with no expected keys is a question the library has no answer to
    (SRC-S12): scored right only when the retriever returns nothing at all."""

    def row(self, **fields: object) -> dict:
        return {"id": "n", "language": "en", "query": "what does control 5.1 require", "expected": [], "match_kind": "concept", **fields}

    def test_an_empty_expectation_is_right_only_on_an_empty_answer(self) -> None:
        self.assertEqual(se.recall_at_k([], []), 1.0)
        self.assertEqual(se.reciprocal_rank([], []), 1.0)
        self.assertEqual(se.recall_at_k([], ["a"]), 0.0)
        self.assertEqual(se.reciprocal_rank([], ["a"]), 0.0)
        self.assertEqual(se.recall_at_k([], ["x"] * se.K + ["a"]), 0.0, "a hit below the top ten is still an answer")

    def test_the_row_validates_and_scores_through_the_harness(self) -> None:
        rows = [self.row(id="silent", predictions=[]), self.row(id="answers", language="sv", predictions=["obl-costs-charges"])]
        se.validate_retrieval(rows)
        result = se.evaluate_retrieval(rows, se.MockRetriever(rows))
        self.assertEqual(result.per_language["en"], {"retrieval_recall_at_10": 1.0, "retrieval_mrr": 1.0})
        self.assertEqual(result.per_language["sv"], {"retrieval_recall_at_10": 0.0, "retrieval_mrr": 0.0})

    def test_expected_must_still_be_a_list(self) -> None:
        for bad in (None, "obl-costs-charges", {}):
            with self.subTest(expected=bad), self.assertRaises(ValueError):
                se.validate_retrieval([self.row(expected=bad)])
        row = self.row()
        del row["expected"]
        with self.assertRaisesRegex(ValueError, "expected missing"):
            se.validate_retrieval([row])


if __name__ == "__main__":
    unittest.main()
