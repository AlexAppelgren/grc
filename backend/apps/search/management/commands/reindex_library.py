"""`manage.py reindex_library`: rebuild the whole search index from the library (SRC-01),
after a seed or after a change to how a chunk is built.

Safe to run any time and twice: only what differs is written, embeddings are kept, and the
run costs one audit row whose outbox event has the worker fill the owed embeddings.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.search import indexing


class Command(BaseCommand):
    help = "Rebuild the search index from the library. Idempotent; embeddings follow through the outbox."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django BaseCommand signature
        with transaction.atomic():
            counts = indexing.reindex_all()
        self.stdout.write(
            f"search index rebuilt: {counts.created} written, {counts.updated} rewritten, "
            f"{counts.unchanged} unchanged, {counts.deleted} removed"
        )
