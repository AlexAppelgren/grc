"""Escalation of overdue actions to the head of the owner's department, once (COL-02, D-21,
CHUNK10_TASKS ruling 7).

Runs per bank at its local `REMINDER_SEND_HOUR`. An open action overdue by at least the
bank's `escalate_after_days` escalates to the heads of the owner's teams' departments
(`org_unit.head_user`, D-21), every active holder of `escalate_to_role` (by key), and the
owner. Each is told once through `notify()`, whatever their preferences (an escalation is
the bank's control), with the delegation hop. With no head to find, the role holders alone
are told and the audit row says so.

Once: the `action.escalated` audit row, written with the notifications, marks the action, so
it never escalates again and an escalation that found nobody is not retried. A per-bank
advisory lock serialises overlapping runs. The audit row carries ids, dates and counts only.
"""

from __future__ import annotations

import datetime

from django.db import connection

from apps.cases.models import Action
from apps.collab import mail
from apps.collab.logic import notify
from apps.collab.models import Notification, NotificationKind
from apps.collab.reminders import Send, link, owner_teams, send_mails
from apps.identity.models import Membership, UserStatus
from apps.library.reading import today_for
from apps.shared.audit import Actor, batched, record
from apps.shared.models import AuditEvent, Tenant
from apps.taxonomy.models import Team

ESCALATED = "action.escalated"


@batched()
def escalate(tenant: Tenant) -> list[Notification]:
    """Escalate each open action overdue by the bank's threshold that has never escalated,
    and return the rows written. Runs inside the tenant task's transaction."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"collab-escalation:{tenant.id}"])
    today = today_for(tenant)
    cutoff = today - datetime.timedelta(days=tenant.escalate_after_days)
    actions = list(
        Action.objects.filter(tenant_id=tenant.id, done_at__isnull=True, removed_at__isnull=True, due_date__lte=cutoff)
        .exclude(
            pk__in=AuditEvent.objects.filter(
                tenant_id=tenant.id, action=ESCALATED, subject_type="action", subject_id__isnull=False
            ).values("subject_id")
        )
        .select_related("case__change", "owner")
        .order_by("id")
    )
    if not actions:
        return []
    teams = owner_teams(tenant, {action.owner_id for action in actions})
    heads = dict(
        Team.objects.filter(
            tenant_id=tenant.id, pk__in={team for ids in teams.values() for team in ids}, org_unit__head_user__isnull=False
        ).values_list("id", "org_unit__head_user_id")
    )
    role_holders = list(
        Membership.objects.filter(
            tenant_id=tenant.id,
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__key=tenant.escalate_to_role,
        )
        .values_list("user_id", flat=True)
        .distinct()
        .order_by("user_id")
    )
    sends: list[Send] = []
    for action in actions:
        action_heads = sorted({heads[team] for team in teams[action.owner_id] if team in heads})
        candidates = [
            (action.owner_id, "owner"),
            *((user_id, "department_head") for user_id in action_heads),
            *((user_id, "escalation_role") for user_id in role_holders),
        ]
        rows = notify(
            tenant_id=tenant.id,
            kind=NotificationKind.ESCALATION,
            subject_type="action",
            subject_id=action.id,
            candidates=candidates,
        )
        overdue = (today - action.due_date).days
        context = mail.MailContext(
            title=action.case.change.title,
            name=action.owner.name,
            date=action.due_date,
            count=overdue,
            link=link(f"watch/{action.case.change_id}"),
        )
        sends.extend((row, "escalation", context) for row in rows)
        record(
            action=ESCALATED,
            actor=Actor.system("collab escalation"),
            subject_type="action",
            subject_id=action.id,
            subject_title=action.case.change.title,
            summary=f"An action {overdue} days overdue was escalated.",
            tenant_id=tenant.id,
            after={
                "dueDate": action.due_date.isoformat(),
                "daysOverdue": overdue,
                "departmentHeadIds": [str(user_id) for user_id in action_heads],
                "departmentHeadMissing": not action_heads,
                "escalateToRole": tenant.escalate_to_role,
                "recipientIds": [str(row.user_id) for row in rows],
            },
        )
    send_mails(tenant, sends)
    return [row for row, _template, _context in sends]
