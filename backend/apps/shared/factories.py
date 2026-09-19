"""Test factories (playbook 2.2). Plain functions, no factory library: each takes the
fields a test cares about and fills the rest deterministically. Values come from
arguments or counters, never from `random` (a seed must reproduce)."""

from __future__ import annotations

import itertools
import uuid

from apps.shared.audit import Actor, ActorType
from apps.shared.models import Tenant

_counter = itertools.count(1)


def tenant(*, name: str | None = None, slug: str | None = None, timezone: str = "Europe/Stockholm") -> Tenant:
    n = next(_counter)
    return Tenant.objects.create(
        name=name or f"Test Tenant {n}", slug=slug or f"test-tenant-{n}", timezone=timezone
    )


def user_actor(*, label: str = "Test Person", user_id: uuid.UUID | None = None) -> Actor:
    return Actor(kind=ActorType.USER, id=user_id or uuid.uuid4(), label=label)


def agent_actor(*, label: str = "Test Agent", agent_id: uuid.UUID | None = None) -> Actor:
    return Actor(kind=ActorType.AGENT, id=agent_id or uuid.uuid4(), label=label)
