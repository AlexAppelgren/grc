"""`manage.py seed_demo`: the prototype's data for a local demo database (playbook 8.3).
Refuses to run on a deployed environment. Idempotent by stable key: run it twice and the
second run changes nothing. Chunk 3 loads the library; the demo tenant's own rows follow
as their chunks land."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import load_library, seed_authorities
from apps.shared.e2e_seed import refuse_when_deployed
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms


class Command(BaseCommand):
    help = "Load the prototype's library into a local database. Never deployed."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        refuse_when_deployed("seed_demo")
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
            seed_authorities()
            counts = load_library()
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count}")
