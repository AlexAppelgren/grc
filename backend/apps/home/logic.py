"""Today (HOM-01): `home_today()` fans out five independent reads into one answer, so the
query count is fixed (playbook 10, pinned at two sizes). The bank's in-scope register entries
are resolved once first, since the scope rule is Today's costliest condition (H115). Reads
only; the tenant half under row-level security.

The ISO week (in the bank's time zone) and `week_cases()`, the one selector of a week's lead,
live here so Today and the weekly briefing can never disagree.

Each panel is filtered by the reader's permissions rather than the page refused: without
`watch.read`, `lead` and `sources` are null; without `register.read`, `standing` is null and
"Coming up" carries no register deadline.
"""

from __future__ import annotations

import datetime
import uuid
from typing import cast
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import F

from apps.cases.models import ChangeCase
from apps.home import roadmap
from apps.home.schemas import Home, HomeSourceHealth, HomeStanding
from apps.library.reading import today_for
from apps.register.models import Applicability, Gap, TenantObligation, TenantObligationScope
from apps.register.status_logic import worst_of
from apps.shared.models import Tenant
from apps.taxonomy.models import ComplianceCategory, ComplianceStatus
from apps.watch import reading as watch_reads
from apps.watch import sources as watch_sources
from apps.watch.models import CheckStatus
from apps.watch.schemas import WatchChangeRow


# --- The week, as the bank reads it (HOM-01, HOM-02) ---
def week_start_of(day: datetime.date) -> datetime.date:
    """The Monday of the ISO week `day` falls in. A plain date, because a week a bank reads
    is the week its own calendar shows and not a moment."""
    return day - datetime.timedelta(days=day.weekday())


def week_window(tenant: Tenant, week_start: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """Monday 00:00 to the next Monday 00:00 in the bank's time zone, the two instants a
    sighting timestamp is compared against."""
    start = datetime.datetime.combine(week_start, datetime.time.min, tzinfo=ZoneInfo(tenant.timezone))
    return start, start + datetime.timedelta(days=7)


def week_cases(tenant: Tenant, week_start: datetime.date, *, limit: int) -> list[ChangeCase]:
    """The week's open, in-scope cases, most urgent first and then by key date (HOM-01,
    HOM-02, FP-03); the one selector behind Today's lead card and the briefing's items.

    - Sighted this week: `first_seen_at` in the ISO week, the window of the feed's `?week=`.
    - Still open: not in the `closed` or `dismissed` category.
    - In scope: `change_case.footprint_match`, read and never recomputed, so the briefing
      cannot drift from the feed (FP-03).

    Urgency sorts by the row's `ordinal`; an undated change sorts last.
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
    """Those cases as the watch feed shows them, in the order chosen, built by
    `apps/watch/reading.py` so a reform renders one way everywhere."""
    rows = watch_reads.change_rows(tenant, order, [case.change_id for case in cases])
    return [rows[case.change_id] for case in cases]


# --- How the watching is going (HOM-01) ---
def source_health(order: list[str]) -> HomeSourceHealth:
    """The source panel's three numbers (WAT-01). A source with automated checks switched off
    counts in neither figure, so `checked` below `total` always means a real gap; a source
    nobody has checked yet is a gap too, since we cannot say a change was not missed.
    """
    rows = [row for row in watch_sources.source_coverage(order) if row.source.active]
    failed = [row for row in rows if row.overdue or row.last_status != CheckStatus.OK.value]
    return HomeSourceHealth(checked=len(rows) - len(failed), total=len(rows), failed=failed)


# --- Where the bank stands (HOM-01, REG-02, REG-03, FP-03) ---
def standing(in_scope: list[uuid.UUID]) -> HomeStanding:
    """How many in-scope obligations apply, per compliance category, and how many gaps on
    them are open. Three queries however large the register is.

    One count per register entry, applying when the entry or any entity row says so, in the
    worst category of the applying entity rows (`worst_of()`, the pill's rule), else the
    entry's own. Product rows are left out, as on the page. Gaps count whatever the answer,
    because "applies" and "we comply" are separate facts. `in_scope` comes from
    `roadmap.in_scope_entries()`, asked once for both panels (H115).
    """
    entries = TenantObligation.objects.filter(id__in=in_scope)
    applying_scopes: dict[uuid.UUID, list[ComplianceStatus]] = {}
    for scope in TenantObligationScope.objects.filter(
        tenant_obligation_id__in=in_scope, product__isnull=True, applicability=Applicability.APPLIES.value
    ).select_related("compliance_status"):
        applying_scopes.setdefault(scope.tenant_obligation_id, []).append(scope.compliance_status)
    counts = dict.fromkeys(ComplianceCategory, 0)
    for entry in entries.select_related("compliance_status"):
        scopes = applying_scopes.get(entry.id, [])
        if scopes or entry.applicability == Applicability.APPLIES.value:
            shown = worst_of(scopes) or entry.compliance_status
            counts[ComplianceCategory(cast(str, shown.kind))] += 1
    return HomeStanding(
        applying=sum(counts.values()),
        compliant=counts[ComplianceCategory.COMPLIANT],
        partly=counts[ComplianceCategory.PARTLY],
        gap=counts[ComplianceCategory.GAP],
        not_assessed=counts[ComplianceCategory.NOT_ASSESSED],
        open_gaps=Gap.objects.filter(tenant_obligation_id__in=in_scope, status__kind__in=roadmap.OPEN_GAPS).count(),
    )


# --- GET /home (HOM-01, NFR-02) ---
def home_today(
    tenant: Tenant, order: list[str], *, watch_reader: bool, register_reader: bool = False, cases_reader: bool = False
) -> Home:
    """Everything the timeline home shows, in one call (HOM-01): five independent reads with
    a fixed query count (`tests_home.py`).

    The week's briefing items are read once, up to `BRIEFING_MAX_ITEMS`: the first is the lead
    and their number is `briefingCount`, so the screen never chains `GET /briefings/current`.
    A panel the reader may not see is null and its read is never made: `watch.read` for
    `lead`, `briefingCount` and `sources`, `register.read` for `standing` and the register's
    deadlines, `cases.read` for the case workflow's.
    """
    today = today_for(tenant)
    in_scope = roadmap.in_scope_entries(tenant) if register_reader else None
    coming_up, roadmap_count = roadmap.coming_up(
        tenant, order, settings.HOME_COMING_UP_ITEMS, in_scope=in_scope, cases_reader=cases_reader
    )
    week = week_cases(tenant, week_start_of(today), limit=settings.BRIEFING_MAX_ITEMS) if watch_reader else None
    return Home(
        date=today,
        coming_up=coming_up,
        roadmap_count=roadmap_count,
        lead=None if week is None else _lead(tenant, order, week),
        briefing_count=None if week is None else len(week),
        sources=source_health(order) if watch_reader else None,
        standing=None if in_scope is None else standing(in_scope),
    )


def _lead(tenant: Tenant, order: list[str], week: list[ChangeCase]) -> WatchChangeRow | None:
    """The running week's lead: the first briefing item. Null in a quiet week."""
    return week_rows(tenant, order, week[:1])[0] if week else None
