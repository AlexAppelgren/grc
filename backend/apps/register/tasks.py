"""The register app's worker task: one chunk of a Decide all run (REG-01, D-128; the work is
in apps/register/decide_all.py).

`decide_listed` is a `@tenant_task`, so each chunk is one transaction in the bank's own zone,
committed before the next chunk's task is queued. It takes ids and the answer, never the
reason: Celery's failure line and an error tracker print a task's arguments. A chunk whose
task fails, at its commit as well as in its body, ends its run as failed (`_ended_by`).
"""

from __future__ import annotations

import uuid
from typing import Any

from celery import Task, shared_task

from apps.register import decide_all
from apps.shared import tenancy


def _ended_by(task: Task, exc: BaseException, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], einfo: Any) -> None:
    """Celery's failure hook: the run of the failed chunk ends as failed, unless its body
    already said so."""
    tenant_id, user_id, _, _, _, run_id = args
    decide_all.fail(tenant_id=uuid.UUID(str(tenant_id)), user_id=uuid.UUID(user_id), run_id=run_id)


@shared_task(on_failure=_ended_by)
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
