"""`manage.py dump_eval_questions`: write the console's active evaluation questions back to
the release gate's file (SRC-05, ADM-02).

The file keeps its comment header and its order; a question added in the console goes after
the others by key, and a retired one is left out. The gate reads only the file, so this is
how a question added in the console reaches the gate: dump, review the diff, commit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.search import eval_sets


class Command(BaseCommand):
    help = "Write the active evaluation questions to backend/eval/retrieval.jsonl."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--out", type=Path, default=eval_sets.RETRIEVAL_SET, help="the JSON Lines file to write")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        written = eval_sets.dump_questions(options["out"])
        self.stdout.write(f"dump_eval_questions: {written} questions written to {options['out']}")
