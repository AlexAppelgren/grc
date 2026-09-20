"""Celery tasks of the shared app (playbook 12).

`deliver_outbox` is the beat entry that runs the one ordered cursor over `outbox_event`
(`apps/shared/outbox.py`). A plain `@shared_task`, not a `@tenant_task`: one cursor spans
the library and every tenant, and each row's handlers run inside a `@tenant_task` in that
module, in the row's own zone. The beat entry and its interval are in `config/settings.py`
with the rest of the `CELERY_*` settings, where the worker, beat and the test runner read
one source; `apps/shared/tests_celery_registration.py` walks both.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.shared import outbox

logger = logging.getLogger(__name__)


@shared_task
def deliver_outbox() -> None:
    result = outbox.deliver_batch()
    if result.delivered or result.failed:
        logger.info("outbox batch", extra={"delivered": result.delivered, "failed": result.failed})
