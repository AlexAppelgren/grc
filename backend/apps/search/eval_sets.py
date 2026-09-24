"""The evaluation set kept in the console's database (SRC-05, ADM-02).

`backend/eval/retrieval.jsonl` is what the release gate reads, and it stays the gate's
source: CI has no console database. The tables of search 0002 hold the same questions so
platform staff can read them, add one and see the runs, and three commands keep the two in
step:

- `seed_eval_questions` files every line of the file as a row, create-only: a key already
  in the table is left exactly as it is, so a question retired in the console stays retired.
- `dump_eval_questions` writes the active rows back over the file, keeping its comment
  header and its order, new keys last, so a question added in the console reaches the gate
  through a reviewed commit.
- `record_eval_run` asks the active questions through a retriever, scored by the gate's own
  functions, and records the run.

Both tables refuse any session with a tenant active (search 0002), so every function here
runs in the platform's zone: the console's session, a command, a seed. The audit rows carry
keys and counts, never a question's text: a row with no tenant is in the shared zone.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.library.models import Language
from apps.search.models import EvalQuestion, EvalRun
from apps.search.schemas import (
    EvalBaselineOut,
    EvalQuestionInput,
    EvalQuestionOut,
    EvalQuestionResult,
    EvalRunConfig,
    EvalRunMetrics,
    EvalRunOut,
    EvalScores,
    EvalVia,
    SearchMatchKind,
)
from apps.shared import tenancy
from apps.shared.audit import Actor, record

RETRIEVAL_SET = Path(settings.BASE_DIR) / "eval" / "retrieval.jsonl"
HARNESS = Path(settings.BASE_DIR) / "scripts" / "search_eval.py"
BASELINE = Path(settings.BASE_DIR) / "eval" / "baseline.json"
QUESTION_SUBJECT = "eval_question"
RUN_SUBJECT = "eval_run"
QUESTION_ADDED = "eval_question.created"
RUN_RECORDED = "eval_run.recorded"
# The gate scores the first ten hits (recall@10); a run keeps what it scored.
RESULT_DEPTH = 10


class Retriever(Protocol):
    """The release gate's evaluator interface (`backend/eval/README.md`)."""

    name: str
    is_mock: bool

    def search(self, query: str, lang: str, as_of: Any) -> list[str]: ...

    def ask(self, query: str, lang: str, as_of: Any) -> list[str]: ...


# ---------------------------------------------------------------------------------------
# The file the gate reads
# ---------------------------------------------------------------------------------------
def _is_row(line: str) -> bool:
    return bool(line.strip()) and not line.startswith("#")


def file_rows(path: Path = RETRIEVAL_SET) -> list[dict[str, Any]]:
    """The labelled questions of the gate's file, in file order, comments skipped."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if _is_row(line)]


@functools.cache
def _keys_in_gate() -> frozenset[str]:
    """The keys the gate that built this deployment scores. The file ships in the image and
    never changes while it runs, so it is read once."""
    return frozenset(row["id"] for row in file_rows())


def _as_row(question: EvalQuestion) -> dict[str, Any]:
    """A question as a line of the gate's file, with the file's key order: `as_of`, `via`
    and `note` only when set, as the file writes them."""
    row: dict[str, Any] = {
        "id": question.key,
        "language": question.language_id,
        "query": question.question,
        "expected": list(question.expected),
        "match_kind": question.match_kind,
    }
    if question.as_of is not None:
        row["as_of"] = question.as_of.isoformat()
    if question.via != EvalVia.SEARCH.value:
        row["via"] = question.via
    if question.notes:
        row["note"] = question.notes
    return row


def active_rows() -> list[dict[str, Any]]:
    """Every active question as a line of the gate's file, by key."""
    return [_as_row(question) for question in EvalQuestion.objects.filter(active=True)]


def seed_questions(*, actor: Actor, path: Path = RETRIEVAL_SET) -> int:
    """File every line of the gate's file whose key the table does not hold yet. Create-only:
    an existing row is never changed, whatever the file now says about it. Returns how many
    were created."""
    known = set(EvalQuestion.objects.values_list("key", flat=True))
    created = 0
    for row in file_rows(path):
        if row["id"] in known:
            continue
        # The file is checked by the same schema as a console request, so a malformed line
        # is refused rather than filed.
        body = EvalQuestionInput(
            key=row["id"],
            lang=row["language"],
            question=row["query"],
            expected=row["expected"],
            match_kind=row["match_kind"],
            as_of=row.get("as_of"),
            via=row.get("via", EvalVia.SEARCH.value),
            notes=row.get("note", ""),
        )
        create_question(actor=actor, body=body)
        created += 1
    return created


def dump_questions(path: Path = RETRIEVAL_SET) -> int:
    """Write the active questions over the gate's file: its comment header kept, the keys it
    already lists in their order, new keys after them by key, and a key no longer active left
    out. Returns how many lines were written."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    header = []
    for line in lines:
        if _is_row(line):
            break
        header.append(line)
    rows = {row["id"]: row for row in active_rows()}
    listed = [json.loads(line)["id"] for line in lines if _is_row(line)]
    order = [key for key in listed if key in rows] + sorted(rows.keys() - set(listed))
    body = [json.dumps(rows[key], ensure_ascii=False) for key in order]
    path.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    return len(body)


# ---------------------------------------------------------------------------------------
# The console's routes
# ---------------------------------------------------------------------------------------
def _question_out(question: EvalQuestion) -> EvalQuestionOut:
    return EvalQuestionOut(
        id=question.id,
        key=question.key,
        lang=question.language_id,
        question=question.question,
        expected=list(question.expected),
        match_kind=SearchMatchKind(question.match_kind),
        as_of=question.as_of,
        via=EvalVia(question.via),
        notes=question.notes,
        active=question.active,
        in_gate=question.key in _keys_in_gate(),
    )


def list_questions(*, limit: int, offset: int) -> tuple[list[EvalQuestionOut], int]:
    """One page of the set by key, retired questions included. A read: no audit row."""
    rows = EvalQuestion.objects.all()
    return [_question_out(question) for question in rows[offset : offset + limit]], rows.count()


def create_question(*, actor: Actor, body: EvalQuestionInput) -> EvalQuestionOut:
    """Add one question to the set, and its audit row, in one transaction; every refusal is
    raised before the write. The gate does not score the question until it is dumped to the
    file and shipped, which `inGate` says."""
    if not Language.objects.filter(key=body.lang).exists():
        raise ValidationError(
            f"There is no content language {body.lang!r}. Use a key from GET /reference/languages.",
            code="unknown_key",
        )
    if EvalQuestion.objects.filter(key=body.key).exists():
        raise ValidationError(
            f"The evaluation set already has a question {body.key!r}. A key names one question "
            "for good; choose another.",
            code="duplicate_key",
        )
    # The evaluation door (search 0003, H16) opens these two tables and nothing else, in a
    # transaction of its own or a savepoint.
    with tenancy.library_door("eval"):
        question = EvalQuestion.objects.create(
            key=body.key,
            language_id=body.lang,
            question=body.question,
            expected=body.expected,
            match_kind=body.match_kind.value,
            as_of=body.as_of,
            via=body.via.value,
            notes=body.notes,
        )
        record(
            action=QUESTION_ADDED,
            actor=actor,
            subject_type=QUESTION_SUBJECT,
            subject_id=question.id,
            subject_title=question.key,
            summary=f"{actor.label} added a question to the search evaluation set.",
            tenant_id=None,
            after={"key": question.key, "lang": body.lang, "match_kind": question.match_kind, "expected": len(body.expected)},
        )
    return _question_out(question)


def list_runs(*, limit: int, offset: int) -> tuple[list[EvalRunOut], int]:
    """One page of recorded runs, newest first. A read: no audit row."""
    runs = EvalRun.objects.all()
    return [
        EvalRunOut(
            id=run.id,
            run_at=run.run_at,
            config=EvalRunConfig.model_validate(run.config),
            metrics=EvalRunMetrics.model_validate(run.metrics),
            results=[EvalQuestionResult.model_validate(result) for result in run.results],
        )
        for run in runs[offset : offset + limit]
    ], runs.count()


def retrieval_baseline() -> EvalBaselineOut:
    """The retrieval track of the gate's baseline file in this build. A score nobody recorded
    stays null, so the console can never show it as zero. A read: no audit row."""
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    track = data["tracks"]["retrieval"]
    return EvalBaselineOut(
        recorded=track["recorded"],
        recorded_at=track["recorded_at"],
        recall_at_10=data["metrics"]["retrieval_recall_at_10"],
        mrr=data["metrics"]["retrieval_mrr"],
    )


# ---------------------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------------------
@functools.cache
def harness() -> ModuleType:
    """`scripts/search_eval.py`, the release gate itself, so a recorded run is scored by the
    same functions that fail a build."""
    spec = importlib.util.spec_from_file_location("search_eval", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def score(retriever: Retriever, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Ask every row through `retriever` and score it the gate's way. Touches no database of
    its own, so it runs wherever the retriever's corpus is. Returns the run's three columns."""
    gate = harness()
    returned: list[list[str]] = []

    class Recording:
        name = retriever.name
        is_mock = retriever.is_mock

        def search(self, query: str, lang: str, as_of: Any) -> list[str]:
            keys = retriever.search(query, lang, as_of)
            returned.append(keys)
            return keys

        def ask(self, query: str, lang: str, as_of: Any) -> list[str]:
            keys = retriever.ask(query, lang, as_of)
            returned.append(keys)
            return keys

    result = gate.evaluate_retrieval(rows, Recording())

    def scores(metrics: dict[str, float]) -> dict[str, float]:
        return EvalScores(recall_at_10=metrics["retrieval_recall_at_10"], mrr=metrics["retrieval_mrr"]).model_dump()

    return {
        "config": EvalRunConfig(retriever=result.evaluator, is_mock=result.is_mock, questions=len(rows)).model_dump(),
        "metrics": EvalRunMetrics.model_validate(
            {
                "overall": scores(result.metrics),
                "per_language": {key: scores(value) for key, value in result.per_language.items()},
                "per_match_kind": {key: scores(value) for key, value in result.per_group.items()},
            }
        ).model_dump(),
        "results": [
            EvalQuestionResult(
                question_key=row["id"],
                returned=keys[:RESULT_DEPTH],
                recall_at_10=gate.recall_at_k(row["expected"], keys),
                mrr=gate.reciprocal_rank(row["expected"], keys),
            ).model_dump()
            for row, keys in zip(rows, returned, strict=True)
        ],
    }


def record_run(*, actor: Actor, scored: dict[str, Any]) -> EvalRun:
    """File a scored run and its audit row in one transaction."""
    with tenancy.library_door("eval"):
        run = EvalRun.objects.create(config=scored["config"], metrics=scored["metrics"], results=scored["results"])
        record(
            action=RUN_RECORDED,
            actor=actor,
            subject_type=RUN_SUBJECT,
            subject_id=run.id,
            subject_title=str(run.id),
            summary=f"{actor.label} recorded a run of the search evaluation set.",
            tenant_id=None,
            after={"questions": scored["config"]["questions"], "is_mock": scored["config"]["is_mock"]},
        )
    return run
