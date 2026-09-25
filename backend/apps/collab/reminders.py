"""Reminders before and after a due date, on the bank's own clock (COL-02, playbook 12).

One hourly beat entry (`tasks.send_reminders`) hands on the banks whose local wall time has
just reached `REMINDER_SEND_HOUR`, one `@tenant_task` each; this module is what that task
computes. A daylight saving change moves the UTC hour a bank is served at, never its local
hour, because the hour is read in the bank's own zone.

The triage branch: a case still `new` whose `triage_due_at` falls on the bank's local today
plus one of its `reminder_days_before` is `due_soon`; one whose due time passed since the
previous send moment is `overdue`, once. The people responsible are the members whose roles
triage cases, since a new case has no owner yet. `notify()` decides who is told (and routes
work to a delegate), and each person told is mailed through `collab/mail.py`.

**Once.** The `email_message` row is the idempotency key: a reminder about a case whose
mail already has a row for this template on the bank's local today is not sent again, so
a second run the same day is silent. Because that row is written by the delivery task after
commit, today's notification of the same kind counts too, and a per-bank advisory lock
makes an overlapping run wait for the first one's rows. A person who muted reminders gets no row and no mail.
Every notification whose mail was queued carries `emailed_at`, in the same transaction.

The query count per bank does not grow with the number of lead days: every due window is
one clause of one query.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from apps.cases.models import CaseStatusCategory, ChangeCase
from apps.collab import mail
from apps.collab.logic import notify
from apps.collab.models import EmailMessage, Notification, NotificationKind
from apps.identity.models import Membership, UserStatus
from apps.library.reading import today_for
from apps.shared import permissions as perms
from apps.shared.models import Tenant, TenantStatus

SUBJECT_TYPE = "change_case"


def tenants_at_send_hour(now: datetime.datetime) -> list[Tenant]:
    """The active banks whose own clock reads `REMINDER_SEND_HOUR` at `now`."""
    return [
        tenant
        for tenant in Tenant.objects.filter(status=TenantStatus.ACTIVE.value).order_by("id")
        if now.astimezone(ZoneInfo(tenant.timezone)).hour == settings.REMINDER_SEND_HOUR
    ]


def _at(day: datetime.date, hour: int, zone: ZoneInfo) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(hour), tzinfo=zone)


def send_triage_reminders(tenant: Tenant) -> list[Notification]:
    """Remind the bank's triagers about the cases due at a lead day or just overdue, and
    return the rows written. Runs inside the tenant task's transaction."""
    zone = ZoneInfo(tenant.timezone)
    today = today_for(tenant)
    moment = _at(today, settings.REMINDER_SEND_HOUR, zone)
    previous = _at(today - datetime.timedelta(days=1), settings.REMINDER_SEND_HOUR, zone)
    due = Q(triage_due_at__gt=previous, triage_due_at__lte=moment)
    for lead in tenant.reminder_days_before:
        day = today + datetime.timedelta(days=lead)
        due |= Q(triage_due_at__gte=_at(day, 0, zone), triage_due_at__lt=_at(day + datetime.timedelta(days=1), 0, zone))
    # Overlapping runs for one bank (a redelivered task) wait here for each other, so the
    # second finds the first one's rows below.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"collab-reminders:{tenant.id}"])
    cases = list(
        ChangeCase.objects.filter(due, tenant_id=tenant.id, status=CaseStatusCategory.NEW.value)
        .select_related("change")
        .order_by("id")
    )
    if not cases:
        return []
    ids = [case.id for case in cases]
    # The mail's row, or today's notification when its mail is still queued after commit.
    already = set(
        EmailMessage.objects.filter(
            tenant_id=tenant.id, sent_on=today, subject_type=SUBJECT_TYPE, subject_id__in=ids
        ).values_list("template", "subject_id")
    ) | set(
        Notification.objects.filter(
            tenant_id=tenant.id, subject_type=SUBJECT_TYPE, subject_id__in=ids, created_at__gte=_at(today, 0, zone)
        ).values_list("kind", "subject_id")
    )
    triagers = [
        (user_id, "triage")
        for user_id in Membership.objects.filter(
            tenant_id=tenant.id,
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[perms.CASES_TRIAGE],
        )
        .values_list("user_id", flat=True)
        .distinct()
    ]
    sends: list[tuple[Notification, mail.Template, mail.MailContext]] = []
    for case in cases:
        assert case.triage_due_at is not None  # the filter above matched it
        template: mail.Template = "overdue" if case.triage_due_at <= moment else "due_soon"
        if (template, case.id) in already:
            continue
        context = mail.MailContext(
            title=case.change.title,
            date=case.triage_due_at.astimezone(zone).date(),
            link=f"{settings.APP_BASE_URL.rstrip('/')}/watch/{case.change_id}",
        )
        rows = notify(
            tenant_id=tenant.id,
            kind=NotificationKind(template),
            subject_type=SUBJECT_TYPE,
            subject_id=case.id,
            candidates=triagers,
        )
        sends.extend((row, template, context) for row in rows)
    _mail(tenant, sends)
    return [row for row, _template, _context in sends]


def _mail(tenant: Tenant, sends: list[tuple[Notification, mail.Template, mail.MailContext]]) -> None:
    """Queue one mail per notification and stamp the rows that were mailed, in one pass."""
    if not sends:
        return
    members = {
        membership.user_id: membership
        for membership in Membership.objects.filter(
            tenant_id=tenant.id, user_id__in={row.user_id for row, _t, _c in sends}
        ).select_related("user__locale")
    }
    for row, template, context in sends:
        mail.send(members[row.user_id], template, context, subject_type=SUBJECT_TYPE, subject_id=row.subject_id)
    Notification.objects.filter(pk__in=[row.pk for row, _t, _c in sends]).update(emailed_at=timezone.now())
