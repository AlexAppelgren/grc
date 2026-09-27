"""`manage.py e2e_reach_off`: no agent access entry of tenant A in the E2E dataset reaches
the bank's register any more, for J-11's teardown (acc-e2e-seed). Refuses to run on a
deployed environment, like `seed_e2e`."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.shared.e2e_seed import switch_reach_off


class Command(BaseCommand):
    help = "Switch tenant reach off on every agent access entry of tenant A. Never deployed."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        self.stdout.write(f"agent access entries switched off: {switch_reach_off()}")
