"""`manage.py seed_e2e`: the deterministic E2E dataset (playbook 8.3). Refuses to run on a
deployed environment. Idempotent: run it twice and the second run changes nothing."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.shared.e2e_seed import seed_e2e


class Command(BaseCommand):
    help = "Seed the deterministic E2E dataset (two tenants; more as chunks land). Never deployed."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        counts = seed_e2e()
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count}")
