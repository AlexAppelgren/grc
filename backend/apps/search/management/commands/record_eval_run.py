"""`manage.py record_eval_run`: ask the console's active evaluation questions through a
retriever, score them the release gate's way, and record the run (SRC-05, ADM-02).

The retriever is the gate's own, `apps.search.eval:Retriever` unless `--retriever` names
another `module:Class`. It builds the sample corpus in a database of its own and points its
process's connection there for good, so it runs in a child process: the questions are read
here first, the child scores them and exits (dropping its database), and the run is written
here, to the database the questions came from. Nothing the retriever does can reach it.
The child is a plain interpreter rather than a multiprocessing worker, because a test
runner's parallel workers may not start one of those."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.search import eval_sets
from apps.shared.audit import Actor

DEFAULT_RETRIEVER = "apps.search.eval:Retriever"
# The child's whole job, with Django set up from the settings module this process passes on
# in the environment. The answer goes to a file, so nothing the retriever prints can corrupt it.
CHILD = (
    "import json, sys, django; django.setup(); from apps.search import eval_sets; "
    "rows = json.loads(open(sys.argv[2], encoding='utf-8').read()); "
    "scored = eval_sets.score(eval_sets.harness().load_evaluator(sys.argv[1]), rows); "
    "open(sys.argv[3], 'w', encoding='utf-8').write(json.dumps(scored))"
)


def score_in_child(spec: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as scratch:
        asked, answered = Path(scratch) / "rows.json", Path(scratch) / "scored.json"
        asked.write_text(json.dumps(rows), encoding="utf-8")
        child = subprocess.run(  # noqa: S603 - our own interpreter and a fixed program; the spec is an argument
            [sys.executable, "-c", CHILD, spec, str(asked), str(answered)],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if child.returncode != 0:
            raise CommandError(f"The retriever {spec} could not score the set:\n{child.stderr[-4000:]}")
        scored: dict[str, Any] = json.loads(answered.read_text(encoding="utf-8"))
        return scored


class Command(BaseCommand):
    help = "Score the active evaluation questions with a retriever and record the run."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--retriever", default=DEFAULT_RETRIEVER, help="module:Class of the retriever to score")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        rows = eval_sets.active_rows()
        if not rows:
            raise CommandError("The evaluation set holds no active question. Run seed_eval_questions first.")
        scored = score_in_child(options["retriever"], rows)
        with transaction.atomic():
            run = eval_sets.record_run(actor=Actor.system("record_eval_run"), scored=scored)
        self.stdout.write(f"record_eval_run: run {run.id} recorded over {len(rows)} questions")
