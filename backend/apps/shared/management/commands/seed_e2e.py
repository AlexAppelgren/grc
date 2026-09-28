"""`manage.py seed_e2e`: the deterministic E2E dataset (playbook 8.3). Refuses to run on a
deployed environment. Idempotent: run it twice and the second run changes nothing.

`--run-minutes N` is what the E2E webServer passes: the seed refuses a run of N minutes that
would cross a seeded tenant's midnight (H114)."""

from __future__ import annotations

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from apps.shared.e2e_seed import refuse_across_midnight, seed_e2e


class Command(BaseCommand):
    help = "Seed the deterministic E2E dataset (two tenants; more as chunks land). Never deployed."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--run-minutes", type=int, help="Refuse to seed a run of this many minutes that would cross a tenant's midnight.")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        if options["run_minutes"] is not None:
            refuse_across_midnight(options["run_minutes"])
        counts = seed_e2e()
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count}")
