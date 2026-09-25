"""The weekly briefing, live and from the snapshot (HOM-02, WAT-05, FP-03).

The running week is computed live and stored nowhere; a past week is read back from the
`briefing` row and its append-only `briefing_item` ranks, so a later change to the feed can
never alter what a person was sent.

Both reads answer the same shape and choose their cases differently, which is the whole
point of storing one of them:

- **The running week** asks `logic.week_cases()` afresh every time, so it moves as the week
  does. A change sighted an hour ago is in it.
- **A past week** asks the snapshot which cases that week's mail named, and in which order.
  The cases themselves are resolved as they are now — a case that has since been triaged
  shows its new urgency — because the snapshot records what a person was *told about*, not a
  photograph of a case file. What cannot change is the selection and the order, and
  `briefing_item`'s append-only trigger is what makes that structural rather than remembered.

Reads only. The snapshot itself is written by the weekly `@tenant_task` in `home/tasks.py`,
in the transaction that sends the mail and through `record()`, never from a request.
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.cases.models import ChangeCase
from apps.home import logic, roadmap
from apps.home.models import Briefing, BriefingItem
from apps.home.schemas import HomeBriefing
from apps.library.reading import NOT_FOUND, today_for
from apps.shared.models import Tenant

# The ISO week runs Monday to Sunday, so a briefing is addressed by a Monday and by nothing
# else (`briefing.week_start`).
MONDAY = 0
WEEK = datetime.timedelta(days=7)


def current_briefing(tenant: Tenant, order: list[str]) -> HomeBriefing:
    """`GET /briefings/current`: the running week, computed live and stored nowhere.

    `emailSentAt` is null here and stays null while the week is running: the mail for a week
    goes out once the week has ended, which is the only moment a week can be summed up.
    """
    week_start = logic.week_start_of(today_for(tenant))
    cases = logic.week_cases(tenant, week_start, limit=settings.BRIEFING_MAX_ITEMS)
    return _briefing(tenant, order, week_start, cases, email_sent_at=None)


def briefing_for_week(tenant: Tenant, order: list[str], week_start: datetime.date) -> HomeBriefing:
    """`GET /briefings/{weekStart}`: one past week, read back from the snapshot the weekly
    job stored when it sent the mail.

    A date that is not a Monday, a week this bank was never sent a briefing for and a week
    belonging to another bank all answer the same 404, so no week can be probed for.
    """
    if week_start.weekday() != MONDAY:
        raise ValidationError(NOT_FOUND, code="not_found")
    row = Briefing.objects.filter(week_start=week_start).first()  # ordering: unique (tenant, week_start), at most one row
    if row is None:
        raise ValidationError(NOT_FOUND, code="not_found")
    cases = [
        item.case
        for item in BriefingItem.objects.filter(briefing=row).select_related("case__change", "case__urgency")
    ]
    return _briefing(tenant, order, week_start, cases, email_sent_at=row.email_sent_at)


def _briefing(
    tenant: Tenant,
    order: list[str],
    week_start: datetime.date,
    cases: list[ChangeCase],
    *,
    email_sent_at: datetime.datetime | None,
) -> HomeBriefing:
    """One week as a reader sees it. The lead is the first of the week's cases, which is the
    same rule and the same selector Today's lead card uses, so the page, the panel and the
    mail can never name three different changes."""
    items = logic.week_rows(tenant, order, cases)
    coming_up, _ = roadmap.coming_up(tenant, order, settings.HOME_COMING_UP_ITEMS)
    return HomeBriefing(
        week_start=week_start,
        week_end=week_start + WEEK - datetime.timedelta(days=1),
        lead=items[0] if items else None,
        items=items,
        coming_up=coming_up,
        email_sent_at=email_sent_at,
    )
