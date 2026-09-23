"""`manage.py e2e_follow_standard on|off`: tenant A of the E2E dataset starts or stops
following ISO/IEC 27001, for WAT-S10's journey and its restore (watch-standards). Refuses
to run on a deployed environment, like `seed_e2e`."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.shared.e2e_seed import follow_the_standard


class Command(BaseCommand):
    help = "Switch tenant A's standard term on or off for an E2E journey. Never deployed."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("state", choices=("on", "off"))

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        follow_the_standard(options["state"] == "on")
        self.stdout.write(f"tenant A follows the standard: {options['state']}")
