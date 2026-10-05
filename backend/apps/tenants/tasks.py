"""The tenants app's worker tasks (TEN-07, TEN-08): a lookup in the public registers, and the
nightly re-read of every bank's register facts (apps/tenants/registers_jobs.py holds the work).

Each bank's work runs as a `@tenant_task`, activated inside its own transaction. The beat's
fan-out hands every active bank to its own task: register entries sit under row-level security,
so the beat, which runs in no bank's zone, cannot tell which banks hold one, and a bank that
holds none is a single empty read."""

from __future__ import annotations

import uuid

from celery import shared_task

from apps.shared import tenancy
from apps.shared.models import Tenant, TenantStatus
from apps.tenants import registers_jobs


@shared_task
@tenancy.tenant_task
def run_register_lookup(tenant_id: uuid.UUID, lookup_id: str) -> None:
    registers_jobs.run_lookup(tenant_id, lookup_id)


@shared_task
def recheck_registers() -> None:
    """The nightly beat (REGISTERS_RECHECK_HOUR, UTC): each active bank to its own task."""
    for tenant_id in Tenant.objects.filter(status=TenantStatus.ACTIVE.value).values_list("id", flat=True):
        recheck_tenant_registers.delay(str(tenant_id))


@shared_task
@tenancy.tenant_task
def recheck_tenant_registers(tenant_id: uuid.UUID) -> None:
    registers_jobs.recheck(tenant_id)
