"""Business logic of the collab app.

`notify()` is the only writer of a notification row (CHUNK10_TASKS ruling 1;
`tests_hardening.py` fails on any other), with D-34's recipient check inside it: an active
member whose roles read the subject, told once per event, unless they switched the kind off.
The delegation hop (TEN-04) runs inside it too, after the check and before the rows.
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
from apps.library.reading import today_for
from apps.shared.audit import NotInTransaction
from apps.shared.models import Tenant

logger = logging.getLogger(__name__)

# The kinds a person may switch off. Every other kind always arrives: an escalation is the
# bank's control (COL-02), and a sign-off or approval request is four eyes waiting on them.
MUTABLE_KINDS: dict[NotificationKind, str] = {
    NotificationKind.MENTION: "mentions",
    NotificationKind.DUE_SOON: "reminders",
    NotificationKind.OVERDUE: "reminders",
    NotificationKind.REVIEW_DUE: "reminders",
    NotificationKind.ASSIGNED: "assignments",
}

# The kinds that follow an away person to their delegate (TEN-04): work waiting on someone.
# A mention is addressed to a person and stays with them.
DELEGATED_KINDS = frozenset(
    {
        NotificationKind.DUE_SOON,
        NotificationKind.OVERDUE,
        NotificationKind.REVIEW_DUE,
        NotificationKind.ESCALATION,
        NotificationKind.ASSIGNED,
        NotificationKind.SIGNOFF_REQUESTED,
    }
)


def notify(
    *,
    tenant_id: uuid.UUID,
    kind: NotificationKind,
    subject_type: str,
    subject_id: uuid.UUID,
    candidates: Iterable[tuple[uuid.UUID, str]],
    actor_id: uuid.UUID | None = None,
) -> list[Notification]:
    """Tell the candidates about one record, and return the rows written.

    `candidates` are `(user id, reason)` pairs; a person named twice gets one row. Only active
    members whose roles read the subject and whose preference for the kind is on are told.
    `DELEGATED_KINDS` go to an away person's delegate, with `on_behalf_of` naming them; the
    delegate is never `actor_id`, so a sign-off request cannot land with its requester.
    Titles are the record's own in each recipient's language. Rows are written in the
    caller's transaction.
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
    switch = MUTABLE_KINDS.get(kind)
    passing = [
        membership
        for membership in _readers(tenant_id, wanted, subject.read_permission)
        if switch is None or getattr(MembershipNotificationPrefs.model_validate(membership.notification_prefs), switch)
    ]
    recipients = _delegated(tenant, passing, subject.read_permission, actor_id) if kind in DELEGATED_KINDS else {
        membership.user_id: (membership, None) for membership in passing
    }
    rows = [
        Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind.value,
            subject_type=subject_type,
            subject_id=subject_id,
            title=subject.title(record, roles_logic.language_order(membership.user, tenant)),
            on_behalf_of_id=absent,
        )
        for user_id, (membership, absent) in sorted(recipients.items())
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


def _readers(tenant_id: uuid.UUID, user_ids: Iterable[uuid.UUID], read_permission: str) -> list[Membership]:
    """The recipient check (D-34): the active members of the bank among `user_ids` whose
    roles hold the subject's read permission. Everyone told anything passes through it."""
    return list(
        Membership.objects.filter(
            tenant_id=tenant_id,
            user_id__in=list(user_ids),
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[read_permission],
        )
        .select_related("user__locale")
        .distinct()
        .order_by("user_id")
    )


def _delegated(
    tenant: Tenant, passing: list[Membership], read_permission: str, actor_id: uuid.UUID | None
) -> dict[uuid.UUID, tuple[Membership, uuid.UUID | None]]:
    """The delegation hop (TEN-04): each recipient, keyed by user id, with the absent person
    they are told for, if any.

    A recipient away through the bank's today, with a delegate, is replaced by that delegate,
    who must pass the same check; a delegate who fails it or caused the notice is skipped and
    the absent person keeps it, so nothing is dropped. One hop only, so a cycle ends. The
    absent person's preference decides; the delegate gains no permission.
    """
    today = today_for(tenant)
    away = {
        membership.user_id: membership.delegate_id
        for membership in passing
        if membership.delegate_id is not None
        and membership.delegate_id not in (membership.user_id, actor_id)
        and membership.out_of_office_until is not None
        and membership.out_of_office_until >= today
    }
    delegates = {m.user_id: m for m in _readers(tenant.id, set(away.values()), read_permission)} if away else {}
    recipients: dict[uuid.UUID, tuple[Membership, uuid.UUID | None]] = {
        membership.user_id: (membership, None) for membership in passing if membership.user_id not in away
    }
    for membership in passing:
        delegate = delegates.get(away[membership.user_id]) if membership.user_id in away else None
        if delegate is None:
            recipients.setdefault(membership.user_id, (membership, None))
        else:
            recipients.setdefault(delegate.user_id, (delegate, membership.user_id))
    return recipients
