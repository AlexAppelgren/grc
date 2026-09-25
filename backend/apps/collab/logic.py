"""Business logic of the collab app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

`notify()` is the only writer of a notification row in the product (CHUNK10_TASKS ruling
1), with D-34's recipient check written once inside it: an active member of the bank, whose
roles read the subject, told once per event, unless they switched the kind off. A guard in
`apps/shared/tests_hardening.py` fails on any other writer.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable

from django.db import connection

from apps.collab import subjects
from apps.collab.models import Notification, NotificationKind
from apps.identity import roles_logic
from apps.identity.models import Membership, UserStatus
from apps.identity.schemas import MembershipNotificationPrefs
from apps.shared.audit import NotInTransaction
from apps.shared.models import Tenant

logger = logging.getLogger(__name__)

# The kinds a person may switch off, and the switch that does it. Every other kind is
# always delivered: an escalation is the bank's control, not the person's (COL-02), and a
# sign-off or an approval request is four eyes waiting on them.
MUTABLE_KINDS: dict[NotificationKind, str] = {
    NotificationKind.MENTION: "mentions",
    NotificationKind.DUE_SOON: "reminders",
    NotificationKind.OVERDUE: "reminders",
    NotificationKind.REVIEW_DUE: "reminders",
    NotificationKind.ASSIGNED: "assignments",
}


def notify(
    *,
    tenant_id: uuid.UUID,
    kind: NotificationKind,
    subject_type: str,
    subject_id: uuid.UUID,
    candidates: Iterable[tuple[uuid.UUID, str]],
) -> list[Notification]:
    """Tell the candidates about one record, and return the rows written.

    `candidates` are `(user id, reason)` pairs: the owner, a participant, a person
    mentioned. A person named for several reasons gets one row. Only active members of the
    bank whose roles hold the subject's read permission are told, and only when their
    preference for the kind is on, read afresh on every call. Each row's title is the
    record's own title in that recipient's language. The rows are written in the caller's
    transaction, so they commit with the write that caused them or not at all.
    """
    if not connection.in_atomic_block:
        raise NotInTransaction(
            "notify() must run inside the transaction of the write that caused it; "
            "requests run under ATOMIC_REQUESTS, tasks use @tenant_task or transaction.atomic()."
        )
    subject = subjects.subject(subject_type)
    wanted = {user_id for user_id, _reason in candidates}
    record = subject.lookup(subject_id) if wanted else None
    if record is None:
        return []
    tenant = Tenant.objects.select_related("default_language").get(pk=tenant_id)
    memberships = (
        Membership.objects.filter(
            tenant_id=tenant_id,
            user_id__in=wanted,
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[subject.read_permission],
        )
        .select_related("user__locale")
        .distinct()
        .order_by("user_id")
    )
    switch = MUTABLE_KINDS.get(kind)
    rows = [
        Notification(
            tenant_id=tenant_id,
            user_id=membership.user_id,
            kind=kind.value,
            subject_type=subject_type,
            subject_id=subject_id,
            title=subject.title(record, roles_logic.language_order(membership.user, tenant)),
        )
        for membership in memberships
        if switch is None or getattr(MembershipNotificationPrefs.model_validate(membership.notification_prefs), switch)
    ]
    Notification.objects.bulk_create(rows)
    logger.info(
        "notified",
        extra={
            "kind": kind.value,
            "subject_type": subject_type,
            "subject_id": str(subject_id),
            "recipients": [str(row.user_id) for row in rows],
        },
    )
    return rows
