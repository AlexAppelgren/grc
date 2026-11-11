"""The tenants app's worker tasks (TEN-07, TEN-08): a register lookup and the nightly re-read
(the work is in apps/tenants/registers_jobs.py). The beat fans out one `@tenant_task` per
active bank, because register entries sit under row-level security and the beat sees none."""

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
