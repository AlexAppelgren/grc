"""`manage.py e2e_restore_leaver`: tenant A's seeded leaver is a member again and owns what
the seed gave them, for TEN-S5's journey teardown (c8-ui-departments-teams-removal). Refuses
to run on a deployed environment, like `seed_e2e`."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.shared.e2e_seed import restore_leaver


class Command(BaseCommand):
    help = "Put back the member TEN-S5 removes, as seeded. Never deployed."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        restore_leaver()
        self.stdout.write("the seeded leaver is restored")
