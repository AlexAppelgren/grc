"""`manage.py seed_reference`: every idempotent reference seed, in dependency order, run on
every deploy by docker-entrypoint.sh (playbook 2.2, 12). Reference rows match on their
immutable key, so a rename survives a deploy.

Each entry names what silently breaks without it. The last repo shipped four reference
seeds that ran nowhere, and every failure was quiet. Phase 0 has no reference rows yet;
the loop exists so chunk 1's permissions and system roles have somewhere to go and the
entrypoint already calls it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

# (name, function, what silently breaks without it). Order is dependency order.
# chunk 1: ("permissions", seed_permissions, "every role is empty and every route 403s")
# chunk 1: ("system_roles", seed_system_roles, "invitations cannot assign a role")
# chunk 2: ("languages", seed_languages, "no label can be stored and every picker is empty")
# chunk 2: ("jurisdictions", seed_jurisdictions, "no instrument can be filed")
# chunk 2: ("library_vocabularies", seed_library_vocabularies, "agents get an empty vocabulary read and every classification is unknown_key")
# chunk 3: ("authorities", seed_authorities, "sources cannot be registered")
# chunk 11: ("agent_definitions", seed_agent_definitions, "no agent can be switched on")
REFERENCE_SEEDS: tuple[tuple[str, Callable[[], int], str], ...] = ()


class Command(BaseCommand):
    help = "Run every idempotent reference seed in dependency order."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        if not REFERENCE_SEEDS:
            self.stdout.write("seed_reference: no reference seeds registered yet (Phase 0)")
            return
        for name, seed, breaks in REFERENCE_SEEDS:
            with transaction.atomic():
                count = seed()
            self.stdout.write(f"{name}: {count} rows (without it: {breaks})")
