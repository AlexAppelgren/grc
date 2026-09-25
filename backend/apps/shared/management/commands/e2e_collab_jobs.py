"""`manage.py e2e_collab_jobs`: tenant A of the E2E dataset gets its reminders, escalations
and weekly digests now, as the worker's beat hands them on at the bank's send hours, for
COL-S2's journey (c10-digest-beat-and-journeys). Refuses to run on a deployed environment,
like `seed_e2e`."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.shared.e2e_seed import run_collab_jobs


class Command(BaseCommand):
    help = "Run tenant A's reminder, escalation and digest jobs for an E2E journey. Never deployed."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        run_collab_jobs()
        self.stdout.write("tenant A's reminders, escalations and digests ran")
