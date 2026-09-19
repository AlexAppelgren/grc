"""`manage.py seed_reference`: every idempotent reference seed, in dependency order, run on
every deploy by docker-entrypoint.sh (playbook 2.2, 12). Reference rows match on their
immutable key, so a rename survives a deploy.

Each entry names what silently breaks without it. The last repo shipped four reference
seeds that ran nowhere, and every failure was quiet."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.identity.roles_logic import ensure_platform_roles, ensure_system_roles
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.shared import tenancy
from apps.shared.models import Tenant
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies


def seed_tenant_system_roles() -> int:
    """Every existing tenant gets the system roles of PRD §6, and their permissions follow
    the code after a PRD bump. New tenants get them when they are created."""
    count = 0
    for tenant in Tenant.objects.all():
        tenancy.activate(tenant.id)
        count += ensure_system_roles(tenant)
    return count


def seed_tenant_vocabularies() -> int:
    """Every existing tenant gets the system rows of every tier-3 list (VOC-01, VOC-04);
    kinds and defaults follow the code, labels stay the tenant's. New tenants get them from
    the tenant-creation hook (apps/taxonomy/tenant_hooks.py)."""
    count = 0
    for tenant in Tenant.objects.all():
        tenancy.activate(tenant.id)
        count += ensure_tenant_vocabularies(tenant)
    return count


# (name, function, what silently breaks without it). Order is dependency order.
# chunk 11: ("agent_definitions", seed_agent_definitions, "no agent can be switched on")
REFERENCE_SEEDS: tuple[tuple[str, Callable[[], int], str], ...] = (
    ("languages", seed_languages, "no label can be stored and every picker is empty"),
    ("jurisdictions", seed_jurisdictions, "no instrument can be filed and provision kinds have no jurisdiction"),
    ("library_vocabularies", seed_library_vocabularies, "agents get an empty vocabulary read and every classification is unknown_key"),
    ("taxonomy_terms", seed_taxonomy_terms, "no footprint can be set and no obligation can be scoped"),
    ("authorities", seed_authorities, "no instrument or source can name who issued it"),
    ("platform_roles", ensure_platform_roles, "nobody can be a platform editor or admin"),
    ("tenant_system_roles", seed_tenant_system_roles, "invitations cannot assign a role"),
    ("tenant_vocabularies", seed_tenant_vocabularies, "a tenant's pickers are empty and a case has no status to start in"),
)


class Command(BaseCommand):
    help = "Run every idempotent reference seed in dependency order."

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        if not REFERENCE_SEEDS:
            self.stdout.write("seed_reference: no reference seeds registered yet")
            return
        for name, seed, breaks in REFERENCE_SEEDS:
            with transaction.atomic():
                count = seed()
            self.stdout.write(f"{name}: {count} rows (without it: {breaks})")
