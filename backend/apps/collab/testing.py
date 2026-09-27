"""Participant builders for tests (playbook 8.1). They live here rather than in
`apps/shared/factories.py` because a participant hangs on a register entry, and a register
entry on a library obligation, which the library fence lets only a `testing.py` write
(apps/shared/tests_library_fence.py)."""

from __future__ import annotations

import itertools
from types import SimpleNamespace

from django.db import transaction

from apps.collab.models import Participant
from apps.library import testing as library_testing
from apps.library.models import Obligation
from apps.register import logic as register_logic
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.models import Team, TeamLabel
from apps.watch import testing as watch_build

_counter = itertools.count(1)


def obligation(*, owner_tenant: Tenant | None = None) -> Obligation:
    """An obligation, shared by default or private to `owner_tenant`, with the reference rows
    it needs seeded first (idempotent)."""
    with transaction.atomic():
        watch_build.seed_watch_reference()
    # A private record is written in its bank's zone and a shared one in none (INV-07).
    if owner_tenant is not None:
        tenancy.activate(owner_tenant.id)
    else:
        tenancy.clear_tenant()
    n = next(_counter)
    act = library_testing.instrument(key=f"participant-act-{n}", regime="regime:securities", owner_tenant=owner_tenant)
    return library_testing.obligation(act, key=f"participant-duty-{n}", owner_tenant=owner_tenant)


def team(tenant: Tenant, key: str, label: str) -> Team:
    """A row of `tenant`'s team list with an English label."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        row = Team.objects.create(tenant=tenant, key=key)
        TeamLabel.objects.create(tenant=tenant, vocabulary=row, language="en", text=label, is_original=True)
    return row


def participant_on_private_obligation(tenant: Tenant) -> SimpleNamespace:
    """A member of `tenant` taking part in `tenant`'s register entry for an obligation only
    `tenant` can see. `.id` is the participation, `.params` names the obligation."""
    private = obligation(owner_tenant=tenant)
    officer = factories.member_user(tenant, roles=("compliance_officer",))
    person = factories.member_user(tenant)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        entry = register_logic.ensure_register_entry(
            tenant_id=tenant.id, obligation_id=private.id, actor=factories.user_actor(user_id=officer.id)
        )
        row = Participant.objects.create(tenant=tenant, tenant_obligation=entry, user=person, added_by=officer)
    return SimpleNamespace(id=row.id, params={"obligation_id": private.id})
