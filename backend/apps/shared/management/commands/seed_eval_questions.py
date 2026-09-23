"""`manage.py seed_eval_questions`: file the release gate's evaluation questions
(`backend/eval/retrieval.jsonl`) in the console's database, create-only (SRC-05, ADM-02).

A key the table already holds is left exactly as it is, whatever the file now says, so a
question retired in the console stays retired and one added there is never overwritten.
Run it with no tenant active, as every command runs: the tables refuse a tenant session."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.search import eval_sets
from apps.shared.audit import Actor

SEED_ACTOR = Actor.system("seed_eval_questions")


class Command(BaseCommand):
    help = "File the evaluation questions of backend/eval/retrieval.jsonl in the database, create-only."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--path", type=Path, default=eval_sets.RETRIEVAL_SET, help="the JSON Lines file to read")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        with transaction.atomic():
            created = eval_sets.seed_questions(actor=SEED_ACTOR, path=options["path"])
        self.stdout.write(f"seed_eval_questions: {created} questions created")
