"""A person's notification inbox (COL-02): their own rows, newest first, and marking them
read.

Every function takes the caller and reads only rows whose `user` is the caller, under the
bank's row-level security, so no parameter reaches another person's or another bank's row.
A row whose record the caller can no longer read is still listed with the title it was
written with: that title was already shown to them, and hiding it would quietly empty the
inbox; its link answers 404 when followed (CHUNK10_TASKS, `c10-notifications-api-b`).

Listing is a read and writes no audit row. The two marks record one `notification.read`
event each, holding ids only, never a title.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.utils import timezone

from apps.collab.models import Notification
from apps.identity.models import User
from apps.shared.audit import Actor, ActorType, record
from apps.shared import tenancy
from apps.shared.errors import ProblemError

logger = logging.getLogger(__name__)


def _own(user: User) -> Any:
    return Notification.objects.filter(user=user)


def list_notifications(*, user: User, unread: bool, limit: int, offset: int) -> dict[str, Any]:
    """`GET /notifications`: the caller's own rows, newest first, one page of them."""
    rows = _own(user)
    if unread:
        rows = rows.filter(read_at__isnull=True)
    return {"items": list(rows[offset : offset + limit]), "total": rows.count()}


def _mark(user: User, ids: list[uuid.UUID]) -> None:
    """Stamp the given unread rows of the caller read in one statement, and record it."""
    read_at = timezone.now()
    marked = _own(user).filter(pk__in=ids, read_at__isnull=True).update(read_at=read_at)
    if not marked:
        return
    one = len(ids) == 1
    record(
        action="notification.read",
        actor=Actor(kind=ActorType.USER, id=user.id, label=user.name),
        subject_type="notification",
        subject_id=ids[0] if one else None,
        subject_title="1 notification" if one else f"{len(ids)} notifications",
        summary=f"{user.name} marked {'a notification' if one else f'{len(ids)} notifications'} read",
        tenant_id=tenancy.active_tenant_id(),
        after={"notificationIds": [str(pk) for pk in ids], "readAt": read_at.isoformat()},
    )
    logger.info("notifications read", extra={"user_id": str(user.id), "count": len(ids)})


def mark_read(*, user: User, notification_id: uuid.UUID) -> None:
    """`POST /notifications/{notificationId}/read`: once; again changes nothing. A row that
    is not the caller's own, in their bank, is 404 and never 403, so no id can be probed."""
    row = _own(user).filter(pk=notification_id).first()  # ordering: pk lookup, at most one row
    if row is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    if row.read_at is None:
        _mark(user, [row.id])


def mark_all_read(*, user: User) -> None:
    """`POST /notifications/read-all`: every unread row of the caller, in one UPDATE."""
    ids = list(_own(user).filter(read_at__isnull=True).values_list("id", flat=True))
    if ids:
        _mark(user, ids)
