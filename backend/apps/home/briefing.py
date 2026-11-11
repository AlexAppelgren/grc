"""The weekly briefing, live and from the snapshot (HOM-02, WAT-05, FP-03).

The running week is computed live from `logic.week_cases()` and stored nowhere. A past week
reads which cases that week's mail named, and in which order, from the `briefing` row and its
append-only `briefing_item` ranks, so a later feed change never alters what a person was
sent; the cases themselves resolve as they are now. Reads only: the weekly `@tenant_task` in
`home/tasks.py` writes the snapshot through `record()`.
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

# A briefing is addressed by the Monday of its ISO week (`briefing.week_start`).
MONDAY = 0
WEEK = datetime.timedelta(days=7)


def current_briefing(tenant: Tenant, order: list[str]) -> HomeBriefing:
    """`GET /briefings/current`: the running week, computed live and stored nowhere.
    `emailSentAt` stays null until the week has ended and its mail goes out.
    """
    week_start = logic.week_start_of(today_for(tenant))
    cases = logic.week_cases(tenant, week_start, limit=settings.BRIEFING_MAX_ITEMS)
    return _briefing(tenant, order, week_start, cases, email_sent_at=None)


def briefing_for_week(tenant: Tenant, order: list[str], week_start: datetime.date) -> HomeBriefing:
    """`GET /briefings/{weekStart}`: one past week, read back from the snapshot. A non-Monday,
    a week never sent and another bank's week all answer the same 404, so none can be probed.
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
    """One week as a reader sees it. The lead is the first of the week's cases, the same
    selector Today's lead card uses, so page, panel and mail name the same change."""
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
