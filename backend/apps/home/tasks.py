"""The weekly briefing job (HOM-02, AUD-01, playbook 12).

Three tasks, because a bank's Monday is not the server's and a relay is not always there.

`send_weekly_briefings` is the beat entry and runs every hour. It asks each active bank what
time it is where that bank is, and hands on every bank whose own clock has passed the
configured moment of its week. Picking the tenants here rather than in beat is what lets a
bank in Helsinki and one in Reykjavík each get their mail at seven in the morning from one
schedule; handing a bank on every hour from its moment until its week is over, rather than
in the one matching hour, is what gets a week out that a stopped worker missed (H21).

`send_weekly_briefing` is a `@tenant_task`: the tenant id is its first argument and it runs
activated inside its own transaction. It snapshots the week once, with one queued
`email_message` row per recipient and the audit row, and hands each unsent row to
`deliver_briefing` once that transaction commits. A week that already has a snapshot is not
snapshotted again, which the unique `(tenant, week_start)` makes true rather than
remembered; a later run only hands on the rows that have not gone out yet.

`deliver_briefing` sends one person's copy and marks its row, in its own transaction, the
way collab's `deliver_mail` does. A relay that refuses marks that one row `failed` and
leaves the snapshot and every other mail alone; the next hourly run tries it again. The row
is what makes a retry send nothing twice: a row already `sent` is never sent again.

**Which week.** The one that has just ended. A week can only be summed up once it is over,
which is why the design's own briefing says the mail goes out on Monday at 07:00 and why a
past week is the thing a mailed link opens. The running week is computed live by
`GET /briefings/current` and is never snapshotted.

Nothing here logs a recipient's address, a subject or a body (playbook 4.7): the audit row
records the week, how many changes it named and how many people it went to, and no title or
judgement travels into it, and each mail's own audit row names its row, its status and the
person's id.
"""

from __future__ import annotations

import datetime
import logging
import smtplib
import uuid
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from apps.cases.models import ChangeCase
from apps.collab.models import EmailMessage, EmailStatus
from apps.collab.tasks import UNSENT
from apps.home import logic, mail
from apps.home.models import Briefing, BriefingItem
from apps.identity.models import Membership, UserStatus
from apps.library.reading import today_for
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.adapters.mailer import OutgoingMail, get_mailer
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant, TenantStatus

logger = logging.getLogger(__name__)

SUBJECT_TYPE = "briefing"
SENT = "briefing.sent"
# The `email_message.template` of a briefing mail, beside collab's own templates.
TEMPLATE = "weekly_briefing"
MESSAGE_SUBJECT_TYPE = "email_message"


@shared_task
def send_weekly_briefings() -> None:
    """The beat entry, run hourly: hand on every bank whose own clock has passed the
    configured weekday and hour of its week. From that moment until the bank's Sunday is
    over, each run hands it on again, so a week the moment's own run missed still goes out;
    the task sends nothing for a week that has already gone out."""
    moment = (settings.BRIEFING_SEND_WEEKDAY, settings.BRIEFING_SEND_HOUR)
    for tenant in Tenant.objects.filter(status=TenantStatus.ACTIVE.value):
        local = timezone.now().astimezone(ZoneInfo(tenant.timezone))
        if (local.weekday(), local.hour) >= moment:
            send_weekly_briefing.delay(str(tenant.id))


@shared_task
@tenancy.tenant_task
def send_weekly_briefing(tenant_id: uuid.UUID) -> None:
    """Snapshot the week that has just ended for one bank, once, and hand each of its mails
    that has not gone out yet to the worker.

    The snapshot is one transaction, the one `@tenant_task` opens: the `briefing` row, its
    ranked items, the stamp on each case saying which week first carried it, one queued
    `email_message` row per person who may read the watch feed, and the audit row. No mail
    leaves inside it: each is handed to `deliver_briefing` once it commits, so a relay that
    refuses can no longer roll the week back (H21).

    A week with nothing inside the bank's regulatory scope writes no snapshot and sends no
    mail. There is nothing to tell anyone, and a week with no snapshot answers 404 rather
    than an empty briefing somebody was supposedly sent.
    """
    tenant = Tenant.objects.get(pk=tenant_id)
    week_start = logic.week_start_of(today_for(tenant)) - datetime.timedelta(days=7)
    briefing = Briefing.objects.filter(week_start=week_start).first()  # ordering: unique (tenant, week_start)
    if briefing is None:
        briefing = _snapshot(tenant, week_start)
        if briefing is None:
            return
    # Only rows still unsent, and only for people who may still have the mail: a person who
    # left, lost `watch.read` or switched the briefing off since is not tried again.
    unsent = EmailMessage.objects.filter(
        template=TEMPLATE,
        subject_type=SUBJECT_TYPE,
        subject_id=briefing.id,
        status__in=UNSENT,
        user__in=_eligible().values("user_id"),
    ).values_list("id", flat=True)
    for message_id in unsent:
        mail.send(tenant.id, message_id)


def _snapshot(tenant: Tenant, week_start: datetime.date) -> Briefing | None:
    """Store the week, queue one mail per recipient and audit it; None for a quiet week."""
    cases = logic.week_cases(tenant, week_start, limit=settings.BRIEFING_MAX_ITEMS)
    if not cases:
        return None

    briefing = Briefing.objects.create(tenant=tenant, week_start=week_start)
    for rank, case in enumerate(cases, start=1):
        BriefingItem.objects.create(tenant=tenant, briefing=briefing, case=case, rank=rank)
    # Which week first carried a case, stamped once and never moved: a case that led three
    # briefings still belongs to the week it first reached people (`change_case.briefing_week`).
    ChangeCase.objects.filter(
        pk__in=[case.pk for case in cases],
        briefing_week__isnull=True,
    ).update(briefing_week=week_start)

    recipients = _recipients()
    EmailMessage.objects.bulk_create(
        EmailMessage(
            tenant=tenant,
            user=membership.user,
            to_email=outgoing.to,
            template=TEMPLATE,
            subject=outgoing.subject,
            subject_type=SUBJECT_TYPE,
            subject_id=briefing.id,
            sent_on=today_for(tenant),
        )
        for membership in recipients
        for outgoing in [_compose(tenant, briefing, cases, membership)]
    )
    record(
        action=SENT,
        actor=Actor.system("weekly briefing"),
        subject_type=SUBJECT_TYPE,
        subject_id=briefing.id,
        subject_title=week_start.isoformat(),
        summary=f"The weekly briefing for the week of {week_start.isoformat()} was stored and its mail queued.",
        tenant_id=tenant.id,
        after={"weekStart": week_start.isoformat(), "items": len(cases), "recipients": len(recipients)},
    )
    return briefing


@shared_task
@tenancy.tenant_task
def deliver_briefing(tenant_id: uuid.UUID, message_id: str) -> None:
    """Send one person's copy of a stored week, once, and record whether it went.

    The row is locked first, so a second worker holding the same delivery waits and then
    finds it sent. A person who left the bank, lost `watch.read` or switched the briefing
    off since the week was stored is sent nothing. The first mail that goes out stamps the
    week's `email_sent_at`; a later one does not move it.
    """
    row = EmailMessage.objects.select_for_update().filter(pk=message_id, template=TEMPLATE).first()  # ordering: a primary key, at most one row
    # A briefing row always names its person and its week; the check is for the type.
    if row is None or row.status not in UNSENT or row.user_id is None or row.subject_id is None:
        return
    try:
        membership = _eligible().select_related("user__locale").get(user_id=row.user_id)
    except Membership.DoesNotExist:
        return
    tenant = Tenant.objects.get(pk=tenant_id)
    briefing = Briefing.objects.get(pk=row.subject_id)
    cases = [item.case for item in BriefingItem.objects.filter(briefing=briefing).select_related("case__change")]
    outgoing = _compose(tenant, briefing, cases, membership)
    row.to_email, row.subject = outgoing.to, outgoing.subject
    try:
        get_mailer().send(outgoing)
    except (smtplib.SMTPException, OSError) as exc:
        # The error's kind only: a relay's message can echo the address.
        row.status, row.error = EmailStatus.FAILED.value, type(exc).__name__
        logger.warning("briefing mail %s failed: %s", row.id, row.error)
    else:
        now = timezone.now()
        row.status, row.error, row.sent_at = EmailStatus.SENT.value, "", now
        Briefing.objects.filter(pk=briefing.pk, email_sent_at__isnull=True).update(email_sent_at=now)
    row.save(update_fields=["to_email", "subject", "status", "error", "sent_at"])
    record(
        action=f"mail.{row.status}",
        actor=Actor.system("weekly briefing"),
        subject_type=MESSAGE_SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=TEMPLATE,
        summary=f"A {TEMPLATE} mail to a member was {row.status}.",
        tenant_id=tenant.id,
        after={
            "template": TEMPLATE,
            "status": row.status,
            "userId": str(membership.user_id),
            "weekStart": briefing.week_start.isoformat(),
        },
    )


def _recipients() -> list[Membership]:
    """Who the briefing goes to: every active member of this bank whose roles carry
    `watch.read`, one mail each (chunk 6 default).

    Permissions, never role names — a bank that builds its own role gets the same answer as
    one using the seeded ones. A deactivated member and a person whose account is not active
    are both left out: neither may open the briefing the mail links to, so sending it would
    be telling somebody what they may no longer read. A member who switched
    `weeklyBriefing` off is left out too (COL-02); a member who never set it gets the mail.
    """
    return list(_eligible().select_related("user__locale"))


def _eligible() -> QuerySet[Membership]:
    """The rule `_recipients` states, as a query a delivery can narrow to one person."""
    return (
        Membership.objects.filter(
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[perms.WATCH_READ],
        )
        .exclude(notification_prefs__contains={"weeklyBriefing": False})
        .distinct()
    )


def _compose(tenant: Tenant, briefing: Briefing, cases: list[ChangeCase], membership: Membership) -> OutgoingMail:
    """One recipient's copy, in that person's own language.

    The lead's "So what?" travels only once a person has confirmed it (WAT-05). An agent's
    draft is labelled on screen and a mail carries no label a reader can see, so an
    unconfirmed one is left out of the body entirely rather than sent unmarked.
    """
    lead = cases[0]
    return mail.weekly_briefing(
        to=membership.user.email,
        locale=membership.user.locale.key if membership.user.locale else None,
        tenant_name=tenant.name,
        week_start=briefing.week_start,
        week_end=briefing.week_start + datetime.timedelta(days=6),
        titles=[case.change.title for case in cases],
        confirmed_so_what=lead.so_what_text if lead.so_what_confirmed else "",
    )
