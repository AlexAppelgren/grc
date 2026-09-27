"""Business logic of the collab app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

`notify()` is the only writer of a notification row in the product (CHUNK10_TASKS ruling
1), with D-34's recipient check written once inside it: an active member of the bank, whose
roles read the subject, told once per event, unless they switched the kind off. A guard in
`apps/shared/tests_hardening.py` fails on any other writer. The delegation hop (TEN-04) is
written once inside it too, after the check and before the rows.
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

# The kinds that follow an away person to their delegate (TEN-04): work waiting on someone.
# A mention is addressed to a human being and stays with them, as does anything else.
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

    `candidates` are `(user id, reason)` pairs: the owner, a participant, a person
    mentioned. A person named for several reasons gets one row. Only active members of the
    bank whose roles hold the subject's read permission are told, and only when their
    preference for the kind is on, read afresh on every call. Work waiting on someone away
    (`DELEGATED_KINDS`) goes to their delegate instead, with `on_behalf_of` naming them
    (`_delegated`); `actor_id`, the person whose write caused the notice, is never that
    delegate, so a sign-off request cannot land with the person who asked. Each row's title is the record's own title in that recipient's
    language. The rows are written in the caller's transaction, so they commit with the
    write that caused them or not at all.
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
    """The delegation hop (TEN-04), the one place that knows about out of office: each
    recipient, keyed by user id, with the absent person they are told for, if any.

    A recipient away through the bank's local today, with a delegate, is replaced by that
    delegate, who must pass the same recipient check; a delegate who does not, or who
    caused the notice (`actor_id`), is skipped and the absent person keeps the notice, so
    it is never dropped. One hop only: the delegate's own absence is not followed, so a
    cycle ends after one step. The absent
    person's preference decides, because it is their notice; the delegate gains no
    permission, and a delegate told on their own account gets one row, without the stamp.
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
