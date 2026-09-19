"""The E2E seed (playbook 8.3): idempotent (natural keys), deterministic (no randomness),
realistic, built from the prototype's sample data so journeys match the design.

Phase 0 seeds tenants only. Chunk 1 adds one login per system role, a platform editor
and the one user still awaiting enrolment; chunk 3 the prototype's library data.
`EXPECTED` is what the seed-integrity guard (apps/shared/tests_seed_integrity.py)
demands, so a seed change cannot quietly hollow out a journey.

Fixed ids: journeys and the guard address tenants by slug, but fixed ids keep audit
rows and URLs stable across reseeds, which makes traces comparable run to run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.shared.audit import Actor, record
from apps.shared.models import Tenant


@dataclass(frozen=True)
class SeedTenant:
    id: uuid.UUID
    name: str
    slug: str
    timezone: str


# Tenant A is the prototype's company ("Example Bank AB"). Tenant B exists so J-8 can prove
# isolation; it is plainly a second bank and never the subject of a journey's own data.
TENANT_A = SeedTenant(
    id=uuid.UUID("00000000-0000-4000-8000-00000000000a"),
    name="Example Bank AB",
    slug="example-bank",
    timezone="Europe/Stockholm",
)
TENANT_B = SeedTenant(
    id=uuid.UUID("00000000-0000-4000-8000-00000000000b"),
    name="Second Bank A/S",
    slug="second-bank",
    timezone="Europe/Copenhagen",
)
EXPECTED_TENANTS: tuple[SeedTenant, ...] = (TENANT_A, TENANT_B)


class SeedRefused(ImproperlyConfigured):
    """seed_e2e on a deployed environment (playbook 8.3, 12)."""


def refuse_when_deployed() -> None:
    if settings.IS_DEPLOYED_ENVIRONMENT:
        raise SeedRefused(
            f"seed_e2e refuses to run on deployed environment {settings.ENVIRONMENT!r}: "
            "test-only data changes never execute where a real tenant could live."
        )


def seed_tenants() -> list[Tenant]:
    tenants: list[Tenant] = []
    for spec in EXPECTED_TENANTS:
        row, created = Tenant.objects.update_or_create(
            slug=spec.slug,
            defaults={"id": spec.id, "name": spec.name, "timezone": spec.timezone},
        )
        if created:
            record(
                action="tenant.seeded",
                actor=Actor.system("seed_e2e"),
                subject_type="tenant",
                subject_id=row.id,
                subject_title=row.name,
                summary="Seeded for E2E journeys.",
                tenant_id=None,
                after={"slug": row.slug, "timezone": row.timezone},
            )
        tenants.append(row)
    return tenants


def seed_e2e() -> dict[str, int]:
    """Run the whole seed. Returns counts the command prints and the guard asserts."""
    refuse_when_deployed()
    with transaction.atomic():
        tenants = seed_tenants()
    return {"tenants": len(tenants)}
