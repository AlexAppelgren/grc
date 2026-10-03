"""`manage.py seed_public_demo`: the public page's demo data (design/public/README.md "The
demo", D-119): the real library baseline through the proposal door, and Example Bank AB's
own made-up work on top of it (apps/shared/demo_seed.py). Refuses to run on a deployed
environment. Idempotent: run it twice and the second run files and writes nothing new."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.shared.demo_seed import DemoSeedStopped, seed_public_demo


class Command(BaseCommand):
    help = "Seed the public demo: the real library baseline and a made-up bank. Never deployed."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        try:
            counts = seed_public_demo()
        except DemoSeedStopped as stopped:
            raise CommandError(str(stopped)) from stopped
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count}")
