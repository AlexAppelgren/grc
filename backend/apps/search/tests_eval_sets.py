"""The evaluation set in the console's database (SRC-05, ADM-02): the tables refuse a bank's
session, the gate's file and the rows agree, the seed only creates, and a run is scored the
gate's way and recorded where the questions came from.

The refusal is proven on the `app` alias, cw_app with no ownership, the way production
connects: with a tenant active it sees no row of either table and can write none, and with
none it reads and writes both. A TransactionTestCase, because the proof needs committed rows
visible across two connections.

Proven to fail 2026-09-23 by giving `platform_only` a USING of `true` in a scratch copy of
search 0002: the tenant session read every question and the first test named the table.
"""

from __future__ import annotations

import io
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, ProgrammingError, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.library.seeds import seed_languages
from apps.search import eval_sets
from apps.search.models import EvalQuestion, EvalRun
from apps.search.schemas import EvalQuestionInput, SearchMatchKind
from apps.shared import factories, tenancy
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent

ACTOR = Actor.system("tests_eval_sets")


class ExpectedRetriever:
    """Answers every question of the gate's file with exactly what it expects, so each one
    scores 1. Loaded by name in `record_eval_run`'s child process."""

    name = "expected answers (test)"
    is_mock = True

    def __init__(self) -> None:
        self._answers = {(row["query"], row["language"]): row["expected"] for row in eval_sets.file_rows()}

    def search(self, query: str, lang: str, as_of: date | None) -> list[str]:
        return list(self._answers[(query, lang)])


class SilentRetriever:
    name = "returns nothing (test)"
    is_mock = True

    def search(self, query: str, lang: str, as_of: date | None) -> list[str]:
        return []


def _question(key: str = "r-en-99", **fields: Any) -> EvalQuestionInput:  # compliance: allow-kwargs test helper
    values: dict[str, Any] = {
        "key": key,
        "lang": "en",
        "question": "costs and charges before the service",
        "expected": ["obl-costs-charges"],
        "match_kind": SearchMatchKind.CONCEPT,
    }
    values.update(fields)
    return EvalQuestionInput(**values)


class TenantSessionSeesAndWritesNothing(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        seed_languages()
        self.bank = factories.tenant(slug="eval-bank")
        with transaction.atomic(using="app"):
            question = EvalQuestion.objects.using("app").create(
                key="r-en-98", language_id="en", question="FFFS 2017:2", expected=["obl-costs-charges"], match_kind="keyword"
            )
            EvalRun.objects.using("app").create(config={}, metrics={}, results=[])
        self.question_id = question.id

    def test_a_tenant_session_reads_no_row_of_either_table(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.bank.id, using="app")
            self.assertEqual(EvalQuestion.objects.using("app").count(), 0, "eval_question: a bank read the set")
            self.assertEqual(EvalRun.objects.using("app").count(), 0, "eval_run: a bank read the runs")

    def test_a_tenant_session_can_insert_change_or_delete_nothing(self) -> None:
        with self.assertRaises(ProgrammingError), transaction.atomic(using="app"):
            tenancy.activate(self.bank.id, using="app")
            EvalQuestion.objects.using("app").create(key="r-en-97", language_id="en", question="x", match_kind="both")
        with self.assertRaises(ProgrammingError), transaction.atomic(using="app"):
            tenancy.activate(self.bank.id, using="app")
            EvalRun.objects.using("app").create(config={}, metrics={}, results=[])
        with connections["app"].cursor() as cursor, transaction.atomic(using="app"):
            tenancy.activate(self.bank.id, using="app")
            cursor.execute("UPDATE eval_question SET question = 'rewritten'")
            self.assertEqual(cursor.rowcount, 0)
            cursor.execute("DELETE FROM eval_question")
            self.assertEqual(cursor.rowcount, 0)
            cursor.execute("DELETE FROM eval_run")
            self.assertEqual(cursor.rowcount, 0)
        with transaction.atomic(using="app"):
            self.assertEqual(EvalQuestion.objects.using("app").get(id=self.question_id).question, "FFFS 2017:2")
            self.assertEqual(EvalRun.objects.using("app").count(), 1)

    def test_the_platform_zone_reads_both(self) -> None:
        with transaction.atomic(using="app"):
            self.assertIsNone(tenancy.database_tenant_id(using="app"))
            self.assertEqual(EvalQuestion.objects.using("app").count(), 1)
            self.assertEqual(EvalRun.objects.using("app").count(), 1)


class SeedAndDumpAgreeWithTheFile(TestCase):
    def setUp(self) -> None:
        seed_languages()
        self.scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.scratch)
        self.copy = self.scratch / "retrieval.jsonl"
        shutil.copyfile(eval_sets.RETRIEVAL_SET, self.copy)

    def _seed(self) -> str:
        out = io.StringIO()
        call_command("seed_eval_questions", path=self.copy, stdout=out)
        return out.getvalue()

    def test_every_line_becomes_a_row_with_the_same_fields(self) -> None:
        self._seed()

        rows = {row["id"]: row for row in eval_sets.file_rows(self.copy)}
        self.assertEqual(set(EvalQuestion.objects.values_list("key", flat=True)), set(rows))
        for question in EvalQuestion.objects.all():
            line = rows[question.key]
            self.assertEqual(question.language_id, line["language"])
            self.assertEqual(question.question, line["query"])
            self.assertEqual(list(question.expected), line["expected"])
            self.assertEqual(question.match_kind, line["match_kind"])
            self.assertEqual(question.as_of, date.fromisoformat(line["as_of"]) if "as_of" in line else None)
            self.assertEqual(question.notes, line.get("note", ""))
            self.assertTrue(question.active)

    def test_the_seed_only_creates(self) -> None:
        self._seed()
        first = EvalQuestion.objects.order_by("key").first()
        assert first is not None
        EvalQuestion.objects.filter(id=first.id).update(active=False, question="retired in the console")
        count = EvalQuestion.objects.count()

        self.assertIn("0 questions created", self._seed())

        self.assertEqual(EvalQuestion.objects.count(), count)
        kept = EvalQuestion.objects.get(id=first.id)
        self.assertEqual((kept.active, kept.question), (False, "retired in the console"), "the seed overwrote a row")

    def test_a_dump_after_a_seed_rewrites_the_file_byte_for_byte(self) -> None:
        original = self.copy.read_text(encoding="utf-8")
        self._seed()

        call_command("dump_eval_questions", out=self.copy, stdout=io.StringIO())

        self.assertEqual(self.copy.read_text(encoding="utf-8"), original)

    def test_a_dump_adds_a_console_question_last_and_leaves_a_retired_one_out(self) -> None:
        self._seed()
        eval_sets.create_question(actor=ACTOR, body=_question("a-new-question", as_of=date(2026, 6, 30), notes="Why."))
        retired = eval_sets.file_rows(self.copy)[0]["id"]
        EvalQuestion.objects.filter(key=retired).update(active=False)

        eval_sets.dump_questions(self.copy)

        written = eval_sets.file_rows(self.copy)
        self.assertEqual(written[-1]["id"], "a-new-question", "a new key goes after the file's own")
        self.assertEqual(written[-1]["as_of"], "2026-06-30")
        self.assertEqual(written[-1]["note"], "Why.")
        self.assertNotIn(retired, [row["id"] for row in written])
        self.assertTrue(self.copy.read_text(encoding="utf-8").startswith("# Retrieval evaluation set"), "the header was lost")

    def test_every_created_question_is_audited_in_the_platform_zone_without_its_text(self) -> None:
        self._seed()

        events = AuditEvent.objects.filter(action=eval_sets.QUESTION_ADDED)
        self.assertEqual(events.count(), EvalQuestion.objects.count())
        texts = set(EvalQuestion.objects.values_list("question", flat=True))
        for event in events:
            self.assertIsNone(event.tenant_id)
            self.assertEqual(event.subject_type, eval_sets.QUESTION_SUBJECT)
            self.assertFalse(texts & {event.subject_title, event.summary, *map(str, (event.after or {}).values())})

    def test_a_malformed_line_is_refused_and_nothing_is_filed(self) -> None:
        self.copy.write_text('{"id": "Not A Key", "language": "en", "query": "x", "expected": [], "match_kind": "keyword"}\n')

        with self.assertRaises(ValueError):
            self._seed()

        self.assertFalse(EvalQuestion.objects.exists())


class RunsAreScoredTheGatesWayAndRecorded(TestCase):
    def setUp(self) -> None:
        seed_languages()
        eval_sets.seed_questions(actor=ACTOR)

    def test_a_retriever_that_finds_nothing_scores_only_the_questions_with_no_answer(self) -> None:
        rows = eval_sets.active_rows()

        scored = eval_sets.score(SilentRetriever(), rows)

        no_answer = sum(1 for row in rows if not row["expected"])
        self.assertAlmostEqual(scored["metrics"]["overall"]["recall_at_10"], no_answer / len(rows))
        self.assertEqual(scored["config"], {"retriever": SilentRetriever.name, "is_mock": True, "questions": len(rows)})
        self.assertEqual([result["question_key"] for result in scored["results"]], [row["id"] for row in rows])
        self.assertEqual(set(scored["metrics"]["per_language"]), {row["language"] for row in rows})
        self.assertEqual(set(scored["metrics"]["per_match_kind"]), {row["match_kind"] for row in rows})

    def test_the_command_scores_in_a_child_and_records_here(self) -> None:
        out = io.StringIO()

        call_command("record_eval_run", retriever="apps.search.tests_eval_sets:ExpectedRetriever", stdout=out)

        run = EvalRun.objects.get()
        questions = EvalQuestion.objects.count()
        self.assertEqual(run.config, {"retriever": ExpectedRetriever.name, "is_mock": True, "questions": questions})
        self.assertEqual(run.metrics["overall"], {"recall_at_10": 1.0, "mrr": 1.0})
        self.assertEqual(len(run.results), questions)
        self.assertIn(str(run.id), out.getvalue())
        event = AuditEvent.objects.get(action=eval_sets.RUN_RECORDED)
        self.assertEqual((event.subject_id, event.tenant_id), (run.id, None))

    def test_a_retired_question_is_not_asked(self) -> None:
        EvalQuestion.objects.filter(key="r-en-01").update(active=False)

        keys = [row["id"] for row in eval_sets.active_rows()]

        self.assertNotIn("r-en-01", keys)
        self.assertEqual(len(keys), EvalQuestion.objects.count() - 1)
