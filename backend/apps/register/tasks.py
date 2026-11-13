"""The register app's worker task: one chunk of a Decide all run (REG-01, D-128; the work is
in apps/register/decide_all.py).

`decide_listed` is a `@tenant_task`, so each chunk is one transaction in the bank's own zone,
committed before the next chunk's task is queued. It takes ids and the answer, never the
reason: Celery's failure line and an error tracker print a task's arguments.
"""

from __future__ import annotations

import uuid

from celery import shared_task

from apps.register import decide_all
from apps.shared import tenancy


@shared_task
@tenancy.tenant_task
def decide_listed(tenant_id: uuid.UUID, user_id: str, org_unit_id: str, obligation_ids: list[str], applicability: str, run_id: str) -> None:
    decide_all.decide_chunk(
        tenant_id=tenant_id,
        user_id=uuid.UUID(user_id),
        company_id=uuid.UUID(org_unit_id),
        obligation_ids=obligation_ids,
        word=applicability,
        run_id=run_id,
    )
