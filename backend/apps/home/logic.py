"""Business logic of the home app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

Today is the one screen that must not chain: `home_today()` fans out the reads it needs and
answers them in one object (HOM-01, playbook 10). Four independent reads — the bank's own
date, the roadmap's first items with its count, the week's lead change and the health of the
sources — and none of them is the input to another, so the query count is fixed and a test
pins it at two sizes.

A read module: nothing here writes, so no `record()` call belongs in it. What it reads is
two zones at once — the library's changes beside this bank's own cases — and the tenant half
is read under row-level security with the caller's tenant activated, never by filtering in
Python.

Two things live here rather than in `briefing.py` because Today and the weekly briefing must
never disagree about them, and the way to make that true is one function rather than two:

- **Which week it is.** The ISO week, Monday to Sunday, resolved in the bank's own time
  zone, which is what `briefing.week_start` stores.
- **What leads it.** `week_cases()` is the one selector: the week's open, in-scope cases,
  most urgent first and then by key date. Today's lead card is its first row and the
  briefing's items are the same list capped; that is why the lead card and the mail can
  never name two different changes.

Each panel is filtered by the reader's own permissions rather than the page being refused. A
reader without `watch.read` gets a 200 with `lead` and `sources` null and the screen hides
those panels, because a 403 would take the whole of Today away from somebody who is allowed
to see most of it.
"""

from __future__ import annotations

import datetime
from typing import NoReturn
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import F

from apps.cases.models import ChangeCase
from apps.home import roadmap
from apps.home.schemas import Home, HomeSourceHealth
from apps.library.reading import today_for
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.watch import reading as watch_reads
from apps.watch import sources as watch_sources
from apps.watch.models import CheckStatus
from apps.watch.schemas import WatchChangeRow


def not_built(detail: str) -> NoReturn:
    """The one 501 the home app answers while a route is declared ahead of its logic. RFC
    9457 like every other refusal, with `not_built` as the code a caller branches on."""
    raise ProblemError(status=501, code="not_built", detail=detail)


# ---------------------------------------------------------------------------------------
# The week, as the bank reads it (HOM-01, HOM-02)
# ---------------------------------------------------------------------------------------
def week_start_of(day: datetime.date) -> datetime.date:
    """The Monday of the ISO week `day` falls in. A plain date, because a week a bank reads
    is the week its own calendar shows and not a moment."""
    return day - datetime.timedelta(days=day.weekday())


def week_window(tenant: Tenant, week_start: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """Monday 00:00 to the following Monday 00:00 in the bank's own time zone, as the two
    instants a sighting is compared against. A sighting is a timestamp, which is why the
    week needs a zone to be resolved at all; a key date is a plain date and needs none."""
    start = datetime.datetime.combine(week_start, datetime.time.min, tzinfo=ZoneInfo(tenant.timezone))
    return start, start + datetime.timedelta(days=7)


def week_cases(tenant: Tenant, week_start: datetime.date, *, limit: int) -> list[ChangeCase]:
    """The week's open, in-scope cases, most urgent first and then by key date (HOM-01,
    HOM-02, FP-03).

    The one selector behind Today's lead card and the weekly briefing's items, so the two
    can never name different changes. Three rules decide what is in it, and each belongs to
    somebody else:

    - **The change was sighted this week.** `first_seen_at` inside the ISO week in the
      bank's own time zone, which is the same window the feed's `?week=` filter uses.
    - **The bank still has work on it.** A case in the `closed` or `dismissed` category is
      finished, and a finished case does not lead a week.
    - **It is inside the bank's regulatory scope.** `change_case.footprint_match` is the
      verdict `apps/cases/creation.py` computed from the one scope rule; it is read here and
      never recomputed, so the briefing cannot drift from the feed (FP-03).

    Most urgent first is the urgency row's own `ordinal`, the fixed severity order the whole
    product reads, and never a phrase. A change registered before anybody published its date
    sorts last rather than first, because a missing date is not an early one.
    """
    sighted_from, sighted_until = week_window(tenant, week_start)
    return list(
        ChangeCase.objects.select_related("change", "urgency")
        .filter(
            footprint_match=True,
            change__first_seen_at__gte=sighted_from,
            change__first_seen_at__lt=sighted_until,
        )
        .exclude(status__in=roadmap.FINISHED)
        .order_by("urgency__ordinal", F("change__key_date").asc(nulls_last=True), "id")[:limit]
    )


def week_rows(tenant: Tenant, order: list[str], cases: list[ChangeCase]) -> list[WatchChangeRow]:
    """Those cases as the watch feed shows them, in the order they were chosen. One shape
    has one owner: the row is built by `apps/watch/reading.py`, so the lead card, the
    briefing and the feed can never render one reform three ways."""
    rows = watch_reads.change_rows(tenant, order, [case.change_id for case in cases])
    return [rows[case.change_id] for case in cases]


# ---------------------------------------------------------------------------------------
# How the watching is going (HOM-01)
# ---------------------------------------------------------------------------------------
def source_health(order: list[str]) -> HomeSourceHealth:
    """The source panel's three numbers, from chunk 5's coverage read (WAT-01).

    A source whose automated checks are switched off is counted in neither figure: it is
    meant not to be checked, so counting it would make a deliberate choice look like a gap.
    Everything else is either healthy or named in `failed`, so `checked` below `total`
    always means a real gap and the panel never says a number it cannot explain. A source
    nobody has checked yet is a gap too: it is not stale — nothing has failed — but we
    cannot say a change was not missed, which is the question this panel answers.
    """
    rows = [row for row in watch_sources.source_coverage(order) if row.source.active]
    failed = [row for row in rows if row.overdue or row.last_status != CheckStatus.OK.value]
    return HomeSourceHealth(checked=len(rows) - len(failed), total=len(rows), failed=failed)


# ---------------------------------------------------------------------------------------
# GET /home (HOM-01, NFR-02)
# ---------------------------------------------------------------------------------------
def home_today(tenant: Tenant, order: list[str], *, watch_reader: bool) -> Home:
    """Everything the timeline home shows, in one call (HOM-01).

    Four independent reads, none of them chained behind another: a fixed number of queries
    however many dates the bank has ahead of it, which `tests_home.py` pins at two sizes.

    `lead` and `sources` are null for a reader without `watch.read`, and the two reads
    behind them are not made at all — the permission decides before the query, so a reader
    who may not see a panel never pays for it either.
    """
    today = today_for(tenant)
    coming_up, roadmap_count = roadmap.coming_up(tenant, order, settings.HOME_COMING_UP_ITEMS)
    lead = _lead(tenant, order, week_start_of(today)) if watch_reader else None
    return Home(
        date=today,
        coming_up=coming_up,
        roadmap_count=roadmap_count,
        lead=lead,
        sources=source_health(order) if watch_reader else None,
    )


def _lead(tenant: Tenant, order: list[str], week_start: datetime.date) -> WatchChangeRow | None:
    """The change of the running week that most deserves attention: `week_cases()`'s first
    row, which is the same change the week's briefing leads with. Null in a week with
    nothing open and in scope, which is a quiet week rather than a failure."""
    cases = week_cases(tenant, week_start, limit=1)
    return week_rows(tenant, order, cases)[0] if cases else None
