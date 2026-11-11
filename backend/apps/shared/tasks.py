"""Celery tasks of the shared app (playbook 12).

`deliver_outbox` runs the one ordered cursor over `outbox_event` (`apps/shared/outbox.py`). A
plain `@shared_task`: the cursor spans every zone, and each row's handlers run in a
`@tenant_task` in the row's own zone. The beat entry lives in `config/settings.py`;
`apps/shared/tests_celery_registration.py` walks both.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import Task, shared_task
from django.conf import settings
from django.db import transaction

from apps.shared import outbox

logger = logging.getLogger(__name__)


@shared_task
def deliver_outbox() -> None:
    result = outbox.deliver_batch()
    if result.delivered or result.failed:
        logger.info("outbox batch", extra={"delivered": result.delivered, "failed": result.failed})


def queue_after_commit(task: Task, args: tuple[Any, ...]) -> None:
    """Hand `task` to the worker once the caller's transaction commits, so a request never
    waits on a relay and nothing leaves for a write that rolled back (F12). Under eager
    Celery it runs inline at once: `on_commit` never fires inside a TestCase transaction."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        task.apply(args=args)
        return
    transaction.on_commit(lambda: task.delay(*args))
