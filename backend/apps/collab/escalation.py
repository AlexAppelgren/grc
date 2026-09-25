"""Escalation of overdue actions to the head of the owner's department, once (COL-02, D-21,
CHUNK10_TASKS ruling 7).

`tasks.send_tenant_escalations` runs this for one bank at its local `REMINDER_SEND_HOUR`,
beside the reminders and in the same fan-out. An open action (not done, not removed) whose
due date is at least the bank's `escalate_after_days` behind its local today escalates with
kind `escalation` to:

- the head of each department the owner's teams belong to (`team.org_unit`, whose
  `head_user` is the head, D-21);
- every active member holding the bank's `escalate_to_role`, compared as a role key;
- the owner, because an escalation about your work that you do not see is a surprise in a
  meeting.

Each person is told once through `notify()`'s recipient check, whatever their
notification preferences (an escalation is the bank's control, not the person's), and the
delegation hop applies. Where the owner is in no team, no team has a department, or no
department has a head, the role holders alone are told and the audit row says so, so the
missing head is visible rather than silent.

**Once.** The `action.escalated` audit row, written through `record()` in the same
transaction as the notifications, is the mark: an action with one is never escalated again,
so an action that stays overdue does not escalate every day, and an escalation that found
nobody to tell is not retried. A per-bank advisory lock makes an overlapping run wait for
the first one's rows. The audit row carries ids, dates and counts, never the action's title.
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
from apps.shared.audit import Actor, record
from apps.shared.models import AuditEvent, Tenant
from apps.taxonomy.models import Team

ESCALATED = "action.escalated"


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
