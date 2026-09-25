"""Reminders before and after a due date, and before a next review, on the bank's own clock
(COL-02, HOM-05, playbook 12).

One hourly beat entry (`tasks.send_reminders`) hands on the banks whose local wall time has
just reached `REMINDER_SEND_HOUR`, one `@tenant_task` each; this module is what that task
computes. A daylight saving change moves the UTC hour a bank is served at, never its local
hour, because the hour is read in the bank's own zone.

Three branches, each read straight off its rows:

- **Triage.** A case still `new` whose `triage_due_at` falls on the bank's local today plus
  one of its `reminder_days_before` is `due_soon`; one whose due time passed since the
  previous send moment is `overdue`, once. The people responsible are the members whose
  roles triage cases, since a new case has no owner yet.
- **Actions.** An open action (not done, not removed) due on local today plus a lead day is
  `due_soon`; one whose due date was yesterday is `overdue`, once. Its owner is told, and
  so is every member of the owner's teams (D-1xx, c10-reminders-escalation-reviews: an
  action has no team of its own).
- **Reviews.** A register entry, or one of its rows for a legal entity, whose
  `next_review_date` is local today plus one of `review_reminder_days_before` is
  `review_due`, whatever its compliance status: a compliant obligation is reviewed too. The
  entry's first-line owner and owning team, and the row's owner or owning team, are told
  once per entry, however many of them are due.

`notify()` decides who is told (and routes work to a delegate), and each person told is
mailed through `collab/mail.py`, in their own language.

**Once.** The `email_message` row is the idempotency key: a reminder about a record whose
mail already has a row for this template on the bank's local today is not sent again, so
a second run the same day is silent. Because that row is written by the delivery task after
commit, today's notification of the same kind counts too, and a per-bank advisory lock
makes an overlapping run wait for the first one's rows. A person who muted reminders gets no row and no mail.
Every notification whose mail was queued carries `emailed_at`, in the same transaction.

The query count per bank does not grow with the number of lead days, nor with the number of
people told: every due window of a branch is one clause of one query, and the people of
every team are read at once.
"""

from __future__ import annotations

import dataclasses
import datetime
import uuid
from collections import defaultdict
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from apps.cases.models import Action, CaseStatusCategory, ChangeCase
from apps.collab import mail
from apps.collab.logic import notify
from apps.collab.models import EmailMessage, Notification, NotificationKind
from apps.identity.models import Membership, UserStatus
from apps.library.reading import today_for
from apps.register.models import TenantObligation, TenantObligationScope
from apps.shared import permissions as perms
from apps.shared.models import Tenant, TenantStatus
from apps.tenants.models import TeamMember

Send = tuple[Notification, mail.Template, mail.MailContext]


def tenants_at_send_hour(now: datetime.datetime) -> list[Tenant]:
    """The active banks whose own clock reads `REMINDER_SEND_HOUR` at `now`."""
    return [
        tenant
        for tenant in Tenant.objects.filter(status=TenantStatus.ACTIVE.value).order_by("id")
        if now.astimezone(ZoneInfo(tenant.timezone)).hour == settings.REMINDER_SEND_HOUR
    ]


def _at(day: datetime.date, hour: int, zone: ZoneInfo) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(hour), tzinfo=zone)


def link(path: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/{path}"


def send_reminders(tenant: Tenant) -> list[Notification]:
    """Every reminder the bank is owed today, and return the rows written. Runs inside the
    tenant task's transaction."""
    # Overlapping runs for one bank (a redelivered task) wait here for each other, so the
    # second finds the first one's rows below.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"collab-reminders:{tenant.id}"])
    sends = [*_triage(tenant), *_actions(tenant), *_reviews(tenant)]
    send_mails(tenant, sends)
    return [row for row, _template, _context in sends]


def _already(tenant: Tenant, subject_type: str, ids: list[uuid.UUID]) -> set[tuple[str, uuid.UUID | None]]:
    """The (template, record) pairs already reminded on the bank's local today: the mail's
    row, or today's notification when its mail is still queued after commit."""
    today = today_for(tenant)
    return set(
        EmailMessage.objects.filter(
            tenant_id=tenant.id, sent_on=today, subject_type=subject_type, subject_id__in=ids
        ).values_list("template", "subject_id")
    ) | set(
        Notification.objects.filter(
            tenant_id=tenant.id,
            subject_type=subject_type,
            subject_id__in=ids,
            created_at__gte=_at(today, 0, ZoneInfo(tenant.timezone)),
        ).values_list("kind", "subject_id")
    )


def team_members(tenant: Tenant, team_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Each team's people, in one query; `notify()` keeps only the active readers."""
    people: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    ids = set(team_ids)
    if ids:
        for team_id, user_id in TeamMember.objects.filter(tenant_id=tenant.id, team_id__in=ids).values_list(
            "team_id", "user_id"
        ):
            people[team_id].append(user_id)
    return people


def owner_teams(tenant: Tenant, owner_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """The teams each owner is a member of, in one query."""
    teams: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    ids = set(owner_ids)
    if ids:
        for user_id, team_id in TeamMember.objects.filter(tenant_id=tenant.id, user_id__in=ids).values_list(
            "user_id", "team_id"
        ):
            teams[user_id].append(team_id)
    return teams


def _notify(
    tenant: Tenant,
    template: mail.Template,
    subject_type: str,
    subject_id: uuid.UUID,
    candidates: list[tuple[uuid.UUID, str]],
    context: mail.MailContext,
) -> list[Send]:
    rows = notify(
        tenant_id=tenant.id,
        kind=NotificationKind(template),
        subject_type=subject_type,
        subject_id=subject_id,
        candidates=candidates,
    )
    return [(row, template, context) for row in rows]


def _triage(tenant: Tenant) -> list[Send]:
    """Remind the bank's triagers about the cases due at a lead day or just overdue."""
    zone = ZoneInfo(tenant.timezone)
    today = today_for(tenant)
    moment = _at(today, settings.REMINDER_SEND_HOUR, zone)
    previous = _at(today - datetime.timedelta(days=1), settings.REMINDER_SEND_HOUR, zone)
    due = Q(triage_due_at__gt=previous, triage_due_at__lte=moment)
    for lead in tenant.reminder_days_before:
        day = today + datetime.timedelta(days=lead)
        due |= Q(triage_due_at__gte=_at(day, 0, zone), triage_due_at__lt=_at(day + datetime.timedelta(days=1), 0, zone))
    cases = list(
        ChangeCase.objects.filter(due, tenant_id=tenant.id, status=CaseStatusCategory.NEW.value)
        .select_related("change")
        .order_by("id")
    )
    if not cases:
        return []
    already = _already(tenant, "change_case", [case.id for case in cases])
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
    sends: list[Send] = []
    for case in cases:
        assert case.triage_due_at is not None  # the filter above matched it
        template: mail.Template = "overdue" if case.triage_due_at <= moment else "due_soon"
        if (template, case.id) in already:
            continue
        context = mail.MailContext(
            title=case.change.title, date=case.triage_due_at.astimezone(zone).date(), link=link(f"watch/{case.change_id}")
        )
        sends.extend(_notify(tenant, template, "change_case", case.id, triagers, context))
    return sends


def _actions(tenant: Tenant) -> list[Send]:
    """Remind each open action's owner and the owner's teams at a lead day, and once the
    day after it fell due."""
    today = today_for(tenant)
    yesterday = today - datetime.timedelta(days=1)
    days = [today + datetime.timedelta(days=lead) for lead in tenant.reminder_days_before]
    actions = list(
        Action.objects.filter(
            tenant_id=tenant.id, done_at__isnull=True, removed_at__isnull=True, due_date__in=[*days, yesterday]
        )
        .select_related("case__change")
        .order_by("id")
    )
    if not actions:
        return []
    already = _already(tenant, "action", [action.id for action in actions])
    teams = owner_teams(tenant, {action.owner_id for action in actions})
    people = team_members(tenant, {team for ids in teams.values() for team in ids})
    sends: list[Send] = []
    for action in actions:
        template: mail.Template = "overdue" if action.due_date == yesterday else "due_soon"
        if (template, action.id) in already:
            continue
        candidates = [(action.owner_id, "owner")] + [
            (user_id, "team") for team in teams[action.owner_id] for user_id in people[team]
        ]
        context = mail.MailContext(
            title=action.case.change.title, date=action.due_date, link=link(f"watch/{action.case.change_id}")
        )
        sends.extend(_notify(tenant, template, "action", action.id, candidates, context))
    return sends


def _reviews(tenant: Tenant) -> list[Send]:
    """Remind the people responsible for each register entry, or entity row, whose next
    review falls on local today plus a review lead day, once per entry."""
    days = [today_for(tenant) + datetime.timedelta(days=lead) for lead in tenant.review_reminder_days_before]
    # Per entry: the earliest due review date and the people and teams responsible for it.
    due: dict[uuid.UUID, datetime.date] = {}
    people: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    teams: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)

    obligations: dict[uuid.UUID, uuid.UUID] = {}
    rows = [
        *TenantObligation.objects.filter(tenant_id=tenant.id, next_review_date__in=days).values_list(
            "id", "obligation_id", "next_review_date", "first_line_owner_id", "owner_team_id"
        ),
        *TenantObligationScope.objects.filter(tenant_id=tenant.id, next_review_date__in=days).values_list(
            "tenant_obligation_id", "tenant_obligation__obligation_id", "next_review_date", "owner_id", "owner_team_id"
        ),
    ]
    for entry_id, obligation_id, day, owner, team in rows:
        assert day is not None  # the filter above matched it
        obligations[entry_id] = obligation_id
        due[entry_id] = min(day, due.get(entry_id, day))
        if owner is not None:
            people[entry_id].add(owner)
        if team is not None:
            teams[entry_id].add(team)
    if not due:
        return []
    ids = sorted(due)
    already = _already(tenant, "tenant_obligation", ids)
    members = team_members(tenant, {team for entry in teams.values() for team in entry})
    sends: list[Send] = []
    for entry_id in ids:
        if ("review_due", entry_id) in already:
            continue
        candidates = [(user_id, "owner") for user_id in people[entry_id]] + [
            (user_id, "team") for team in teams[entry_id] for user_id in members[team]
        ]
        # The mail carries the date; `notify()` gives each person the obligation's title in their order.
        context = mail.MailContext(date=due[entry_id], link=link(f"inventory/obligations/{obligations[entry_id]}"))
        sends.extend(_notify(tenant, "review_due", "tenant_obligation", entry_id, candidates, context))
    return sends


def send_mails(tenant: Tenant, sends: list[Send]) -> None:
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
        if context.title is None:
            # The title the recipient's notification carries, in their own language order.
            context = dataclasses.replace(context, title=row.title)
        mail.send(members[row.user_id], template, context, subject_type=row.subject_type, subject_id=row.subject_id)
    Notification.objects.filter(pk__in=[row.pk for row, _t, _c in sends]).update(emailed_at=timezone.now())
