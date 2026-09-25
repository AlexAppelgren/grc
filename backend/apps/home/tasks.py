"""The weekly briefing job (HOM-02, AUD-01, playbook 12).

Two tasks, because a bank's Monday is not the server's. `send_weekly_briefings` is the beat
entry and runs every hour; it asks each active bank what time it is where that bank is, and
hands the ones whose own clock has just struck the configured moment to
`send_weekly_briefing`. Picking the tenants here rather than in beat is what lets a bank in
Helsinki and one in Reykjavík each get their mail at seven in the morning from one schedule.

`send_weekly_briefing` is a `@tenant_task`: the tenant id is its first argument and it runs
activated inside its own transaction, so the snapshot, the mail and the audit row either all
happen or none of them does. That is also what makes the job safe to retry — a week that
already has a snapshot writes nothing and sends nothing, which the unique `(tenant,
week_start)` makes true rather than remembered.

**Which week.** The one that has just ended. A week can only be summed up once it is over,
which is why the design's own briefing says the mail goes out on Monday at 07:00 and why a
past week is the thing a mailed link opens. The running week is computed live by
`GET /briefings/current` and is never snapshotted.

Nothing here logs a recipient's address, a subject or a body (playbook 4.7): the audit row
records the week, how many changes it named and how many people it went to, and no title or
judgement travels into it.
"""

from __future__ import annotations

import datetime
import uuid
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.cases.models import ChangeCase
from apps.home import logic, mail
from apps.home.models import Briefing, BriefingItem
from apps.identity.models import Membership, UserStatus
from apps.library.reading import today_for
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.adapters.mailer import get_mailer
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant, TenantStatus

SUBJECT_TYPE = "briefing"
SENT = "briefing.sent"


@shared_task
def send_weekly_briefings() -> None:
    """The beat entry, run hourly: hand on the banks whose own clock has just reached the
    configured weekday and hour. A bank whose moment is not now is simply not enqueued."""
    weekday, hour = settings.BRIEFING_SEND_WEEKDAY, settings.BRIEFING_SEND_HOUR
    for tenant in Tenant.objects.filter(status=TenantStatus.ACTIVE.value):
        local = timezone.now().astimezone(ZoneInfo(tenant.timezone))
        if (local.weekday(), local.hour) == (weekday, hour):
            send_weekly_briefing.delay(str(tenant.id))


@shared_task
@tenancy.tenant_task
def send_weekly_briefing(tenant_id: uuid.UUID) -> None:
    """Snapshot the week that has just ended for one bank and mail it to the people who may
    read the watch feed.

    Everything happens in the one transaction `@tenant_task` opens: the `briefing` row, its
    ranked items, the stamp on each case saying which week first carried it, the mail, the
    time it went out and the audit row. A mail relay that refuses rolls the snapshot back
    with it, so the next run finds the week unsent and tries again rather than leaving a
    briefing nobody received but everybody can reopen.

    A week with nothing inside the bank's regulatory scope writes no snapshot and sends no
    mail. There is nothing to tell anyone, and a week with no snapshot answers 404 rather
    than an empty briefing somebody was supposedly sent.
    """
    tenant = Tenant.objects.get(pk=tenant_id)
    week_start = logic.week_start_of(today_for(tenant)) - datetime.timedelta(days=7)
    if Briefing.objects.filter(week_start=week_start).exists():
        return
    cases = logic.week_cases(tenant, week_start, limit=settings.BRIEFING_MAX_ITEMS)
    if not cases:
        return

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
    _send(tenant, briefing, cases, recipients)
    briefing.email_sent_at = timezone.now()
    briefing.save(update_fields=["email_sent_at"])
    record(
        action=SENT,
        actor=Actor.system("weekly briefing"),
        subject_type=SUBJECT_TYPE,
        subject_id=briefing.id,
        subject_title=week_start.isoformat(),
        summary=f"The weekly briefing for the week of {week_start.isoformat()} went out.",
        tenant_id=tenant.id,
        after={"weekStart": week_start.isoformat(), "items": len(cases), "recipients": len(recipients)},
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
    return list(
        Membership.objects.filter(
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[perms.WATCH_READ],
        )
        .exclude(notification_prefs__contains={"weeklyBriefing": False})
        .select_related("user__locale")
        .distinct()
    )


def _send(tenant: Tenant, briefing: Briefing, cases: list[ChangeCase], recipients: list[Membership]) -> None:
    """One mail per recipient, in that person's own language.

    The lead's "So what?" travels only once a person has confirmed it (WAT-05). An agent's
    draft is labelled on screen and a mail carries no label a reader can see, so an
    unconfirmed one is left out of the body entirely rather than sent unmarked.
    """
    titles = [case.change.title for case in cases]
    lead = cases[0]
    so_what = lead.so_what_text if lead.so_what_confirmed else ""
    mailer = get_mailer()
    for membership in recipients:
        mailer.send(
            mail.weekly_briefing(
                to=membership.user.email,
                locale=membership.user.locale.key if membership.user.locale else None,
                tenant_name=tenant.name,
                week_start=briefing.week_start,
                week_end=briefing.week_start + datetime.timedelta(days=6),
                titles=titles,
                confirmed_so_what=so_what,
            )
        )
