#!/usr/bin/env python
"""Search and classification evaluation gate (playbook 9, 16, SRC-05, AC-SRC1, AGT-07,
AGT-08, AC-AGT1).

Loads the labelled sets under backend/eval/ and scores two pluggable evaluators:

    Retriever.search(query, lang, as_of) -> [stable keys, best first]
    Retriever.ask(query, lang, as_of) -> [stable keys of Ask's passages, best first]
    Classifier.classify(text) -> {"in_scope", "change_type", "flags", "scope", "risk_flags",
                                  "standard_terms"}

Metrics: retrieval recall@10 and MRR; classification accuracy per field (change type,
flags, scope, the AGT-07 embedded-instruction screen, and AGT-08's two: whether the text is
inside the sector scope, and whether a standard's opt-in term sits on the standard's own
records and nowhere else), each reported per language and per kind of text.
`eval/baseline.json` holds the last accepted values and `eval/tolerance.json` how far
each may fall before the gate fails.

Status rules:
- While `baseline.json` says a track is not recorded, a missing evaluator is reported as
  "not available yet" and the gate passes. A real run records the baseline with
  `--record`, which refuses the mock.
- Once a track is recorded, a missing evaluator (or the mock in its place) fails loudly,
  and any later run that drops below baseline minus tolerance fails.

The mock evaluators read a `predictions` field from the rows when every row has one
(unit tests and dry runs). A real evaluator is named as `module:Class` with
`--retriever` and `--classifier`; chunk 5 supplies the classifier, and the retriever is
`apps.search.eval:Retriever` (hybrid search over the fixture corpus, in a throwaway
database). A retrieval row whose `expected` is empty is a question with no answer: it
scores right only when the retriever returns nothing. A row with `via: "ask"` is scored
on the passages Ask would give a model rather than on the search page (SRC-S12, D-81): a
question about a standard's control is one Search answers with the conformance duty and
Ask must not answer at all. Every run says which tracks have no
recorded baseline, because a drop in those fails nothing yet. Exit 0 when the gate passes,
1 otherwise. `--self-test` runs eval/tests_scoring.py.

Proven to fail 2026-09-19 with a recorded baseline and no evaluator (exit 1, track
named), and with a mock prediction set scoring under the floor (exit 1, metric named);
both through the self-test.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

BACKEND = Path(__file__).resolve().parent.parent
EVAL = BACKEND / "eval"
RETRIEVAL_METRICS = ("retrieval_recall_at_10", "retrieval_mrr")
CLASSIFICATION_METRICS = (
    "classification_change_type_accuracy",
    "classification_flags_accuracy",
    "classification_scope_accuracy",
    "classification_screen_accuracy",
    "classification_in_scope_accuracy",
    "classification_standard_term_accuracy",
)
METRICS = RETRIEVAL_METRICS + CLASSIFICATION_METRICS
TRACKS = {"retrieval": RETRIEVAL_METRICS, "classification": CLASSIFICATION_METRICS}
SCREEN_FLAG = "embedded_instructions"
# The opt-in dimension a standard's term lives in (D-36). Its terms are seeded by the taxonomy
# seeds, not carried by the prototype fixture that `check_prototype_data --eval` reads, so a
# row names them in `standard_terms` rather than in `scope`.
STANDARD_TERM = "standard:"
K = 10
# Where a retrieval row is scored: the search page, or the passages Ask would give a model.
VIA = ("search", "ask")


# ---------------------------------------------------------------- evaluator interfaces
class Retriever(Protocol):
    name: str
    is_mock: bool

    def search(self, query: str, lang: str, as_of: date | None) -> list[str]: ...

    def ask(self, query: str, lang: str, as_of: date | None) -> list[str]: ...


class Classifier(Protocol):
    name: str
    is_mock: bool

    def classify(self, text: str) -> dict: ...


class MockRetriever:
    """Answers from the `predictions` field of the rows. Available only when every row has one."""

    name = "mock (predictions in the set)"
    is_mock = True

    def __init__(self, rows: list[dict]) -> None:
        self._by_query = {(r["query"], r["language"], r.get("as_of")): list(r["predictions"]) for r in rows if "predictions" in r}
        self.available = bool(rows) and all("predictions" in r for r in rows)

    def search(self, query: str, lang: str, as_of: date | None) -> list[str]:
        return self._by_query.get((query, lang, as_of.isoformat() if as_of else None), [])

    ask = search


class MockClassifier:
    name = "mock (predictions in the set)"
    is_mock = True

    def __init__(self, rows: list[dict]) -> None:
        self._by_text = {r["text"]: dict(r["predictions"]) for r in rows if "predictions" in r}
        self.available = bool(rows) and all("predictions" in r for r in rows)

    def classify(self, text: str) -> dict:
        return self._by_text.get(text, {})


def load_evaluator(spec: str) -> object:
    """Instantiates `module:Class` with no arguments. A bad spec is a loud failure."""
    module_name, _, class_name = spec.partition(":")
    if not module_name or not class_name:
        raise ValueError(f"evaluator {spec!r} must be module:Class")
    # The real evaluators live in the Django project (`apps.search.eval:Retriever`), and a
    # script's own directory is what Python puts on the path, not the backend's.
    if str(BACKEND) not in sys.path:
        sys.path.append(str(BACKEND))
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError(f"evaluator {spec!r} cannot be imported ({exc})") from exc
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ValueError(f"evaluator {spec!r}: {class_name} is not in {module_name}")
    return cls()


# ---------------------------------------------------------------- loading
def display(path: Path) -> str:
    return path.relative_to(BACKEND).as_posix() if path.is_relative_to(BACKEND) else path.name


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{display(path)} is missing")
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{number}: not JSON ({exc.msg})") from exc
    return rows


def validate_retrieval(rows: list[dict]) -> None:
    for r in rows:
        for key in ("id", "language", "query", "expected", "match_kind"):
            if key not in r:
                raise ValueError(f"retrieval.jsonl {r.get('id', '?')}: {key} missing")
        # An empty list is a question the library has no answer to (SRC-S12): the retriever
        # must return nothing at all.
        if not isinstance(r["expected"], list):
            raise ValueError(f"retrieval.jsonl {r['id']}: expected must be a list of stable keys")
        if r["match_kind"] not in ("keyword", "concept", "both"):
            raise ValueError(f"retrieval.jsonl {r['id']}: match_kind {r['match_kind']!r}")
        if "as_of" in r:
            date.fromisoformat(r["as_of"])
        if r.get("via", "search") not in VIA:
            raise ValueError(f"retrieval.jsonl {r['id']}: via {r['via']!r} is not one of {', '.join(VIA)}")


def validate_classification(rows: list[dict]) -> None:
    for r in rows:
        for key in ("id", "language", "text", "expected", "injection"):
            if key not in r:
                raise ValueError(f"classification.jsonl {r.get('id', '?')}: {key} missing")
        expected = r["expected"]
        for key in ("in_scope", "change_type", "flags", "scope", "risk_flags"):
            if key not in expected:
                raise ValueError(f"classification.jsonl {r['id']}: expected.{key} missing")
        if r["injection"] != (SCREEN_FLAG in expected["risk_flags"]):
            raise ValueError(f"classification.jsonl {r['id']}: injection and risk_flags disagree")
        # AGT-08: every change carries a regime, so a text inside the scope names one and a
        # text outside it, from which nothing is registered, names none.
        if not isinstance(expected["in_scope"], bool):
            raise ValueError(f"classification.jsonl {r['id']}: expected.in_scope must be true or false")
        if expected["in_scope"] != bool(expected["scope"].get("regime")):
            raise ValueError(f"classification.jsonl {r['id']}: in_scope and regime disagree")
        terms = expected.get("standard_terms", [])
        if not isinstance(terms, list) or not all(isinstance(t, str) and t.startswith(STANDARD_TERM) for t in terms):
            raise ValueError(f"classification.jsonl {r['id']}: standard_terms must be a list of {STANDARD_TERM}<key> terms")
        if terms and (not expected["in_scope"] or r.get("cites_standard")):
            raise ValueError(f"classification.jsonl {r['id']}: a standard term belongs on a standard's own record inside the scope")


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{display(path)} is missing")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_baseline(data: dict) -> None:
    if "recorded" not in data or "tracks" not in data or "metrics" not in data:
        raise ValueError("baseline.json: recorded, tracks and metrics are required")
    for track in TRACKS:
        if track not in data["tracks"] or "recorded" not in data["tracks"][track]:
            raise ValueError(f"baseline.json: tracks.{track}.recorded missing")
    for metric in METRICS:
        if metric not in data["metrics"]:
            raise ValueError(f"baseline.json: metric {metric} missing")
    recorded_tracks = [t for t in TRACKS if data["tracks"][t]["recorded"]]
    if bool(recorded_tracks) != bool(data["recorded"]):
        raise ValueError("baseline.json: recorded must be true exactly when a track is recorded")
    for track in recorded_tracks:
        for metric in TRACKS[track]:
            if not isinstance(data["metrics"][metric], (int, float)):
                raise ValueError(f"baseline.json: {metric} must be a number once {track} is recorded")


def validate_tolerance(data: dict) -> None:
    if "metrics" not in data:
        raise ValueError("tolerance.json: metrics missing")
    for metric in METRICS:
        value = data["metrics"].get(metric)
        if not isinstance(value, (int, float)) or value < 0 or value > 1:
            raise ValueError(f"tolerance.json: {metric} must be a number between 0 and 1")


# ---------------------------------------------------------------- scoring
def recall_at_k(expected: list[str], predicted: list[str], k: int = K) -> float:
    if not expected:  # a no-answer question: right only when nothing at all came back
        return 0.0 if predicted else 1.0
    top = set(predicted[:k])
    return sum(1 for key in expected if key in top) / len(expected)


def reciprocal_rank(expected: list[str], predicted: list[str]) -> float:
    if not expected:  # as recall: the first hit is already one too many
        return 0.0 if predicted else 1.0
    wanted = set(expected)
    for rank, key in enumerate(predicted, start=1):
        if key in wanted:
            return 1.0 / rank
    return 0.0


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def score_classification(expected: dict, predicted: dict) -> dict[str, float]:
    """One row. change_type: exact. flags and screen: set equality. scope: mean Jaccard over
    the dimensions the expectation names (an empty expected list matches an empty or absent one).
    in_scope: equal, so a classifier that does not say is wrong. standard_terms: set equality,
    where a row that states none expects none."""
    scope_expected: dict = expected["scope"]
    scope_predicted: dict = predicted.get("scope") or {}
    scope = (
        sum(jaccard(list(keys), list(scope_predicted.get(dim) or [])) for dim, keys in scope_expected.items()) / len(scope_expected)
        if scope_expected
        else 1.0
    )
    return {
        "classification_change_type_accuracy": 1.0 if predicted.get("change_type") == expected["change_type"] else 0.0,
        "classification_flags_accuracy": 1.0 if set(predicted.get("flags") or []) == set(expected["flags"]) else 0.0,
        "classification_scope_accuracy": scope,
        "classification_screen_accuracy": 1.0 if set(predicted.get("risk_flags") or []) == set(expected["risk_flags"]) else 0.0,
        "classification_in_scope_accuracy": 1.0 if predicted.get("in_scope") == expected["in_scope"] else 0.0,
        "classification_standard_term_accuracy": (
            1.0 if set(predicted.get("standard_terms") or []) == set(expected.get("standard_terms") or []) else 0.0
        ),
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@dataclass
class TrackResult:
    status: str  # "scored" | "not_available"
    evaluator: str
    is_mock: bool
    metrics: dict[str, float] = field(default_factory=dict)
    per_language: dict[str, dict[str, float]] = field(default_factory=dict)
    per_group: dict[str, dict[str, float]] = field(default_factory=dict)
    rows: int = 0


def evaluate_retrieval(rows: list[dict], retriever: Retriever | None) -> TrackResult:
    if retriever is None:
        return TrackResult("not_available", "none", False, rows=len(rows))
    per_row: list[tuple[dict, dict[str, float]]] = []
    for r in rows:
        as_of = date.fromisoformat(r["as_of"]) if r.get("as_of") else None
        read = retriever.ask if r.get("via") == "ask" else retriever.search
        predicted = read(r["query"], r["language"], as_of)
        per_row.append((r, {"retrieval_recall_at_10": recall_at_k(r["expected"], predicted), "retrieval_mrr": reciprocal_rank(r["expected"], predicted)}))
    return TrackResult(
        "scored", retriever.name, retriever.is_mock,
        metrics={m: mean([s[m] for _, s in per_row]) for m in RETRIEVAL_METRICS},
        per_language=_breakdown(per_row, "language", RETRIEVAL_METRICS),
        per_group=_breakdown(per_row, "match_kind", RETRIEVAL_METRICS),
        rows=len(rows),
    )


def evaluate_classification(rows: list[dict], classifier: Classifier | None) -> TrackResult:
    if classifier is None:
        return TrackResult("not_available", "none", False, rows=len(rows))
    per_row = [(r, score_classification(r["expected"], classifier.classify(r["text"]) or {})) for r in rows]
    return TrackResult(
        "scored", classifier.name, classifier.is_mock,
        metrics={m: mean([s[m] for _, s in per_row]) for m in CLASSIFICATION_METRICS},
        per_language=_breakdown(per_row, "language", CLASSIFICATION_METRICS),
        per_group=_breakdown([(dict(r, group=classification_group(r)), s) for r, s in per_row], "group", CLASSIFICATION_METRICS),
        rows=len(rows),
    )


def classification_group(r: dict) -> str:
    """The kind of text a row is, so each rule is read on the rows written for it: the
    AGT-07 injection cases, AGT-08's off-sector texts, laws that cite a standard and a
    standard's own records, and the rest."""
    if r["injection"]:
        return "injection"
    if not r["expected"]["in_scope"]:
        return "off_sector"
    if r.get("cites_standard"):
        return "cites_standard"
    if r["expected"].get("standard_terms"):
        return "standard"
    return "clean"


def _breakdown(per_row: list[tuple[dict, dict[str, float]]], key: str, metrics: tuple[str, ...]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, float]]] = {}
    for r, s in per_row:
        groups.setdefault(str(r.get(key)), []).append(s)
    return {g: {m: mean([s[m] for s in scores]) for m in metrics} for g, scores in sorted(groups.items())}


# ---------------------------------------------------------------- the gate
def decide(track: str, result: TrackResult, baseline: dict, tolerance: dict) -> list[str]:
    """Returns the failures for one track, empty when it passes."""
    recorded = bool(baseline["tracks"][track]["recorded"])
    if result.status != "scored" or result.is_mock:
        if recorded:
            who = baseline["tracks"][track].get("evaluator", "?")
            when = baseline["tracks"][track].get("recorded_at", "?")
            return [f"{track}: baseline recorded {when} with {who}, but no real evaluator ran (got {result.evaluator})"]
        return []
    if not recorded:
        return []
    failures = []
    for metric in TRACKS[track]:
        floor = float(baseline["metrics"][metric]) - float(tolerance["metrics"][metric])
        if result.metrics[metric] < floor:
            failures.append(f"{metric}: {result.metrics[metric]:.3f} is under the floor {floor:.3f}")
    return failures


def record(baseline: dict, results: dict[str, TrackResult], now: datetime | None = None) -> dict:
    """Writes the scored tracks into the baseline. Refuses the mock and an unscored track."""
    stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    scored = {t: r for t, r in results.items() if r.status == "scored" and not r.is_mock}
    if not scored:
        raise ValueError("nothing to record: no real evaluator ran")
    updated = json.loads(json.dumps(baseline))
    for track, result in scored.items():
        updated["tracks"][track] = {"recorded": True, "recorded_at": stamp, "evaluator": result.evaluator, "rows": result.rows}
        for metric in TRACKS[track]:
            updated["metrics"][metric] = round(result.metrics[metric], 4)
    updated["recorded"] = any(updated["tracks"][t]["recorded"] for t in TRACKS)
    return updated


# ---------------------------------------------------------------- reporting
def report(track: str, result: TrackResult, baseline: dict, tolerance: dict) -> list[str]:
    lines = []
    recorded = bool(baseline["tracks"][track]["recorded"])
    if result.status != "scored":
        state = "not available yet" if not recorded else "MISSING"
        lines.append(f"  {track}: {result.rows} rows, evaluator {state}")
        return lines
    lines.append(f"  {track}: {result.rows} rows, evaluator {result.evaluator}")
    for metric in TRACKS[track]:
        value = result.metrics[metric]
        if recorded:
            floor = float(baseline["metrics"][metric]) - float(tolerance["metrics"][metric])
            lines.append(f"    {metric}: {value:.3f} (baseline {float(baseline['metrics'][metric]):.3f}, floor {floor:.3f}) {'ok' if value >= floor else 'BELOW'}")
        else:
            lines.append(f"    {metric}: {value:.3f} (no baseline recorded)")
    for label, groups in (("language", result.per_language), ("group", result.per_group)):
        for name, metrics in groups.items():
            lines.append(f"    by {label} {name}: " + ", ".join(f"{m.split('_', 1)[1]} {v:.3f}" for m, v in metrics.items()))
    return lines


# ---------------------------------------------------------------- entry points
@dataclass
class Paths:
    retrieval: Path = EVAL / "retrieval.jsonl"
    classification: Path = EVAL / "classification.jsonl"
    baseline: Path = EVAL / "baseline.json"
    tolerance: Path = EVAL / "tolerance.json"


def run(argv: list[str], paths: Paths | None = None, out=print) -> int:
    paths = paths or Paths()
    parser = argparse.ArgumentParser(prog="search_eval", description=__doc__.split("\n\n")[0])
    parser.add_argument("--retriever", help="module:Class implementing Retriever.search(query, lang, as_of)")
    parser.add_argument("--classifier", help="module:Class implementing Classifier.classify(text)")
    parser.add_argument("--record", action="store_true", help="write the scored metrics into baseline.json as the new baseline")
    parser.add_argument("--self-test", action="store_true", help="run eval/tests_scoring.py")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        retrieval = load_jsonl(paths.retrieval)
        classification = load_jsonl(paths.classification)
        validate_retrieval(retrieval)
        validate_classification(classification)
        baseline = load_json(paths.baseline)
        tolerance = load_json(paths.tolerance)
        validate_baseline(baseline)
        validate_tolerance(tolerance)
        retriever: Retriever | None = load_evaluator(args.retriever) if args.retriever else None  # type: ignore[assignment]
        classifier: Classifier | None = load_evaluator(args.classifier) if args.classifier else None  # type: ignore[assignment]
        if retriever is None:
            mock_r = MockRetriever(retrieval)
            retriever = mock_r if mock_r.available else None
        if classifier is None:
            mock_c = MockClassifier(classification)
            classifier = mock_c if mock_c.available else None
        results = {
            "retrieval": evaluate_retrieval(retrieval, retriever),
            "classification": evaluate_classification(classification, classifier),
        }
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        out(f"search_eval: {exc}")
        return 1
    out(f"search_eval: {len(retrieval)} retrieval questions, {len(classification)} classification rows")
    failures: list[str] = []
    for track, result in results.items():
        for line in report(track, result, baseline, tolerance):
            out(line)
        failures.extend(decide(track, result, baseline, tolerance))
    unrecorded = [t for t in TRACKS if not baseline["tracks"][t]["recorded"]]
    if unrecorded:
        out("search_eval: no baseline is recorded for " + " or ".join(unrecorded) + ", so a drop there fails nothing yet")
    if args.record:
        try:
            updated = record(baseline, results)
        except ValueError as exc:
            out(f"search_eval: {exc}")
            return 1
        paths.baseline.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        out(f"search_eval: baseline recorded in {paths.baseline.name} for " + ", ".join(t for t in TRACKS if updated["tracks"][t]["recorded"]))
        return 0
    if failures:
        for failure in failures:
            out("  " + failure)
        out("search_eval: FAILED")
        return 1
    pending = [t for t, r in results.items() if r.status == "scored" and not r.is_mock and not baseline["tracks"][t]["recorded"]]
    if pending:
        out("search_eval: scored without a baseline for " + ", ".join(pending) + "; run with --record to record it")
    out("search_eval: ok")
    return 0


def self_test() -> int:
    import unittest

    sys.path.insert(0, str(EVAL))
    suite = unittest.defaultTestLoader.loadTestsFromName("tests_scoring")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
