"""`manage.py reindex_library`: rebuild the whole search index from the library (SRC-01).

Two jobs. After a seed, so the reference library is searchable without waiting for someone
to approve a change to every record; and after a change to how a chunk is built — the
citation line, the validity rule, the metadata a filter compares — which no library write
would otherwise pick up.

It is safe to run at any time and safe to run twice: the rebuild compares what the library
says with what the index holds and touches only what differs, so a second run writes
nothing, keeps every embedding already paid for, and costs one audit row with its counts.
The embeddings the run owes are filled afterwards by the worker, from that row's outbox
event, never inside this transaction.
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
