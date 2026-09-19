#!/usr/bin/env python
"""Search and classification evaluation gate (playbook 9, 16, SRC-05).

Loads the labelled sets under backend/eval/ (retrieval.jsonl: question, expected chunk
ids; classification.jsonl: text, expected change type, flags and scope), runs them
through the search and classification code, and compares the metrics with the recorded
baseline in eval/baseline.json within the tolerance in eval/tolerance.json. A drop beyond
the tolerance fails.

Phase 0: the sets are empty and the search code does not exist, so the harness records
zero questions, checks that the baseline and tolerance files exist and are well formed,
and passes. Chunk 7 fills the sets and the runner. The harness fails on a malformed set,
a missing baseline or tolerance file, or a metric under baseline minus tolerance.

Proven to fail 2026-09-19 by removing eval/tolerance.json (exit 1, file named), then
restored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
EVAL = BACKEND / "eval"
RETRIEVAL = EVAL / "retrieval.jsonl"
CLASSIFICATION = EVAL / "classification.jsonl"
BASELINE = EVAL / "baseline.json"
TOLERANCE = EVAL / "tolerance.json"
METRICS = ("retrieval_recall_at_10", "retrieval_mrr", "classification_accuracy")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(BACKEND).as_posix()} is missing")
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{number}: not JSON ({exc.msg})") from exc
    return rows


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(BACKEND).as_posix()} is missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    for metric in METRICS:
        if metric not in data:
            raise ValueError(f"{path.name}: metric {metric} missing")
    return data


def evaluate(retrieval: list[dict], classification: list[dict]) -> dict[str, float | None]:
    """Chunk 7 replaces this with the real runner. With no rows, no metric is computed."""
    if not retrieval and not classification:
        return {metric: None for metric in METRICS}
    raise NotImplementedError("the evaluation runner lands in chunk 7 (Search and ask)")


def main() -> int:
    try:
        retrieval = load_jsonl(RETRIEVAL)
        classification = load_jsonl(CLASSIFICATION)
        baseline = load_json(BASELINE)
        tolerance = load_json(TOLERANCE)
        metrics = evaluate(retrieval, classification)
    except (FileNotFoundError, ValueError, NotImplementedError) as exc:
        print(f"search_eval: {exc}")
        return 1
    print(f"search_eval: {len(retrieval)} retrieval questions, {len(classification)} classification rows")
    failures: list[str] = []
    for metric in METRICS:
        value = metrics[metric]
        floor = float(baseline[metric]) - float(tolerance[metric])
        if value is None:
            print(f"  {metric}: not computed (empty set); baseline {baseline[metric]}, tolerance {tolerance[metric]}")
            continue
        mark = "ok" if value >= floor else "BELOW"
        print(f"  {metric}: {value:.3f} (floor {floor:.3f}) {mark}")
        if value < floor:
            failures.append(metric)
    if failures:
        print("search_eval: FAILED: " + ", ".join(failures))
        return 1
    print("search_eval: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
