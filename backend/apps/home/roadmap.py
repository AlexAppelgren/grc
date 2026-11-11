"""The roadmap by quarter (HOM-03, FP-03): the one roadmap query. `roadmap_items()` answers
`GET /roadmap`, `coming_up()` Today's "Coming up" and `calendar_items()` a calendar
subscription, all from the same branches. Reads only, under row-level security.

The regulatory branch lists a change while the bank has an open case on it (not `closed` or
`dismissed`), the case's stored `footprint_match` says it is in scope (never recomputed,
FP-03), and its date is ahead of `today_for()`. A date stated as a month, quarter or year
stays while its period runs (H22).

The bank's own deadlines (`internal`, "Our deadline", HOM-03, D-43, AC-TEN1), one query each:
next reviews of entries and entity rows that apply, targets of open or remediating gaps,
certificate expiry and next audit, a duty's open occurrence (REG-07), an open case's internal
deadline (CAS-03) and live actions' due dates (CAS-04). Register branches need
`register.read` and follow the regulatory scope; case branches need `cases.read`. None
reaches `calendar_items()`: a calendar carries public facts only (D-43, D-52).
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from django.db.models import Exists, OuterRef, Q, QuerySet

from apps.cases.models import Action, ChangeCase, ImpactAssessment
from apps.home.schemas import (
    HomeRoadmap,
    HomeRoadmapEntity,
    HomeRoadmapItem,
    HomeRoadmapOwner,
    HomeRoadmapQuery,
    HomeRoadmapSubject,
    RoadmapItemKind,
    RoadmapItemType,
)
from apps.identity.models import User
from apps.library.models import DatePrecision, Obligation, ObligationTitle
from apps.library.reading import in_view, localized, obligation_headings, today_for, vocabulary_refs
from apps.library.schemas import LibraryRef
from apps.register.duties import OPEN as OPEN_DUTIES
from apps.register.models import Applicability, DutyOccurrence, Gap, TenantObligation, TenantObligationScope
from apps.shared.models import Tenant
from apps.taxonomy.models import CaseStatusCategory, GapCategory, Team, TeamLabel
from apps.taxonomy.schemas import PersonRef, TermRef
from apps.tenants.models import Licence, OrgUnit
from apps.tenants.terms import term_refs
from apps.watch import keys
from apps.watch.models import ChangeObligation
from apps.watch.reading import urgency_refs
from apps.watch.schemas import CaseCategory, Origin, WatchObligationLink
from apps.watch.schemas import DatePrecision as Precision

# The regulatory branch's tier-one kinds (apps/shared/kinds.py): the screen's pill and the
# calendar's summary line.
ITEM_KIND: RoadmapItemKind = "regulatory"
ITEM_TYPE: RoadmapItemType = "change_date"
INTERNAL: RoadmapItemKind = "internal"
DAY: Precision = "day"

# Gaps with a target still to meet (REG-03). Listed, so a new category must say it is open.
OPEN_GAPS = (GapCategory.OPEN.value, GapCategory.REMEDIATING.value)

# The categories a bank has finished with (D-13). Excluded, so a new category stays on the
# roadmap unless someone says it is finished: the safe direction for what is coming.
FINISHED = (CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value)


def quarter_of(day: datetime.date) -> str:
    """The quarter key `YYYY-Qn` a plain date falls in, for grouping and ordering. The
    screen renders the phrase from its own catalog and never from this string."""
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


# --- What is on the roadmap ---
def _dated(rows: QuerySet[Any], field: str, query: HomeRoadmapQuery, today: datetime.date) -> QuerySet[Any]:
    """`rows` whose `field` falls inside the window, earliest first with the row's id as a
    stable tiebreak, so two dates on one day never swap between two reads."""
    return _until(rows.filter(**{f"{field}__gte": _window_start(query, today)}), field, query)


def _window_start(query: HomeRoadmapQuery, today: datetime.date) -> datetime.date:
    """The bank's own today, even when `from` is earlier: an earlier `from` never reopens
    the past."""
    return today if query.date_from is None else max(today, query.date_from)


def _until(rows: QuerySet[Any], field: str, query: HomeRoadmapQuery) -> QuerySet[Any]:
    """`rows` up to the window's end, earliest first."""
    if query.date_to is not None:
        rows = rows.filter(**{f"{field}__lte": query.date_to})
    return rows.order_by(field, "id")


def _period_start(day: datetime.date, precision: DatePrecision) -> datetime.date:
    """The first day of the month, quarter or year `day` falls in."""
    if precision is DatePrecision.MONTH:
        return day.replace(day=1)
    if precision is DatePrecision.QUARTER:
        return datetime.date(day.year, (day.month - 1) // 3 * 3 + 1, 1)
    return datetime.date(day.year, 1, 1)


def _open_cases() -> QuerySet[ChangeCase]:
    """The bank's cases still open inside its regulatory scope, by the verdict stored on the
    case (FP-03)."""
    return ChangeCase.objects.filter(footprint_match=True).exclude(status__in=FINISHED)


def _cases(tenant: Tenant, query: HomeRoadmapQuery) -> QuerySet[ChangeCase]:
    """The bank's open work on a dated change inside its regulatory scope. A key date stated
    less exactly than a day compares by the start of its period, so it stays while its period
    runs (H22).
    """
    since = _window_start(query, today_for(tenant))
    ahead = Q(change__key_date__gte=since)
    for precision in (DatePrecision.MONTH, DatePrecision.QUARTER, DatePrecision.YEAR):
        ahead |= Q(change__key_date_precision=precision.value, change__key_date__gte=_period_start(since, precision))
    return _until(_open_cases().select_related("change", "urgency").filter(ahead), "change__key_date", query)


def _item(case: ChangeCase, urgency: LibraryRef, obligations: list[WatchObligationLink]) -> HomeRoadmapItem:
    """One dated thing on the bank's calendar: library facts (the date, what the date is,
    the reform's title and who published it) beside this bank's own case status."""
    # `_cases()` guarantees a key date; the column is nullable for undated changes.
    day = cast(datetime.date, case.change.key_date)
    return HomeRoadmapItem(
        id=f"{ITEM_TYPE}:{case.id}",
        kind=ITEM_KIND,
        item_type=ITEM_TYPE,
        date=day,
        date_precision=cast(Precision, case.change.key_date_precision),
        quarter=quarter_of(day),
        label=case.change.key_date_label,
        title=case.change.title,
        status=cast(CaseCategory, case.status),
        urgency=urgency,
        source_label=case.change.source_label,
        change_id=case.change_id,
        owner=None,
        subject=None,
        obligations=obligations,
    )


def _items(cases: Sequence[ChangeCase], order: list[str]) -> list[HomeRoadmapItem]:
    """The rows as the screen reads them, in four queries however many items there are."""
    # Through the watch app's own rule, never `vocabulary_refs()`: an urgency row's `kind` is
    # its pill tone, and a tone is nobody's to send (NFR-03).
    urgencies = urgency_refs({case.urgency_id for case in cases}, order)
    links = _obligation_links([case.change_id for case in cases], order)
    return [_item(case, urgencies[case.urgency_id], links.get(case.change_id, [])) for case in cases]


def _obligation_links(
    change_ids: Collection[uuid.UUID], order: list[str]
) -> dict[uuid.UUID, list[WatchObligationLink]]:
    """The obligations each change touches, most confident first, as the watch feed answers
    them (WAT-04). Confirmed links only, since a person plans work here; an agent-confirmed
    link reads machine-confirmed, never as a person's verification (D-74). No bank's own
    judgement is read.
    """
    links = list(
        ChangeObligation.objects.filter(change_id__in=change_ids)
        .filter(confirmed_at__isnull=False)
        .select_related("obligation__instrument", *keys.CURATION_AGENTS)
    )
    titles: dict[uuid.UUID, list[ObligationTitle]] = {}
    for title in ObligationTitle.objects.filter(obligation_id__in=[link.obligation_id for link in links]):
        titles.setdefault(title.obligation_id, []).append(title)
    by_change: dict[uuid.UUID, list[WatchObligationLink]] = {}
    for link in links:
        text = localized(titles.get(link.obligation_id, []), order)
        by_change.setdefault(link.change_id, []).append(
            WatchObligationLink(
                obligation_id=link.obligation_id,
                title="" if text is None else text.text,
                instrument_short_name=link.obligation.instrument.shown_short_name,
                ref_label=link.obligation.ref_label,
                origin=cast(Origin, link.origin),
                confidence=None if link.confidence is None else float(link.confidence),
                confirmed=True,
                **keys.provenance(link),
            )
        )
    return by_change


# --- The bank's own deadlines (HOM-03, REG-02, REG-03, REG-07, TEN-02, CAS-03, CAS-04, D-43) ---
@dataclass(frozen=True)
class _Deadline:
    """One of the bank's own dates while it is being assembled: what produced it, the
    record it belongs to and its owner. The names are resolved for every branch at once."""

    item_type: RoadmapItemType
    record_id: uuid.UUID
    date: datetime.date
    person: User | None
    team: Team | None
    entity: OrgUnit | None = None
    obligation_id: uuid.UUID | None = None
    gap: Gap | None = None
    licence: Licence | None = None
    # A duty's, a case's or an action's own title, and the change a case item links to.
    title: str | None = None
    change_id: uuid.UUID | None = None


def in_scope_obligations(tenant: Tenant) -> QuerySet[Obligation, Any]:
    """The library obligations inside the bank's regulatory scope, as a subquery: the
    inventory's own filter (FP-03)."""
    return in_view(Obligation.objects.all(), tenant, "in").values("id")


def in_scope_entries(tenant: Tenant) -> list[uuid.UUID]:
    """The ids of the bank's register entries whose obligation is inside its regulatory
    scope. The costliest condition, asked once for every register branch and Today's standing
    panel (H115)."""
    return list(TenantObligation.objects.filter(obligation_id__in=in_scope_obligations(tenant)).values_list("id", flat=True))


# A branch: its rows, and how one row becomes a deadline.
_Branch = tuple[QuerySet[Any], Callable[[Any], _Deadline]]


def _internal_branches(
    tenant: Tenant, query: HomeRoadmapQuery, *, in_scope: list[uuid.UUID] | None, cases_reader: bool
) -> list[_Branch]:
    today = today_for(tenant)
    live = Licence.objects.filter(withdrawn_on__isnull=True).select_related("licence_type", "owner_user", "owner_team", "org_unit")
    branches: list[_Branch] = [
        (_dated(live, "valid_until", query, today), lambda row: _certificate("certificate_expiry", row, row.valid_until)),
        (_dated(live, "next_audit_on", query, today), lambda row: _certificate("certificate_audit", row, row.next_audit_on)),
    ]
    if cases_reader:
        branches += _case_branches(query, today)
    if in_scope is None:
        return branches
    does_not_apply = Applicability.DOES_NOT_APPLY.value
    entries = (
        TenantObligation.objects.filter(id__in=in_scope)
        .exclude(applicability=does_not_apply)
        .select_related("first_line_owner", "owner_team")
    )
    scopes = (
        TenantObligationScope.objects.filter(tenant_obligation_id__in=in_scope)
        .exclude(applicability=does_not_apply)
        .exclude(tenant_obligation__applicability=does_not_apply)
        .select_related("tenant_obligation", "owner", "owner_team", "org_unit")
    )
    gaps = Gap.objects.filter(tenant_obligation_id__in=in_scope, status__kind__in=OPEN_GAPS).select_related(
        "tenant_obligation", "owner", "owner_team", "org_unit"
    )
    # An occurrence on one entity is left out where that entity's answer is "does not apply",
    # as its review is; one on the whole entry where the entry's answer is.
    entity_does_not_apply = TenantObligationScope.objects.filter(
        tenant_obligation_id=OuterRef("tenant_obligation_id"), org_unit_id=OuterRef("org_unit_id"), applicability=does_not_apply
    )
    occurrences = (
        DutyOccurrence.objects.filter(tenant_obligation_id__in=in_scope, status__in=OPEN_DUTIES)
        .exclude(tenant_obligation__applicability=does_not_apply)
        .exclude(Exists(entity_does_not_apply))
        .select_related("recurring_duty", "tenant_obligation", "owner", "owner_team", "org_unit")
    )
    return [
        *branches,
        (
            _dated(entries, "next_review_date", query, today),
            lambda row: _Deadline(
                "review_due", row.id, row.next_review_date, row.first_line_owner, row.owner_team, obligation_id=row.obligation_id
            ),
        ),
        (
            _dated(scopes, "next_review_date", query, today),
            lambda row: _Deadline(
                "review_due",
                row.id,
                row.next_review_date,
                row.owner,
                row.owner_team,
                entity=row.org_unit,
                obligation_id=row.tenant_obligation.obligation_id,
            ),
        ),
        (
            _dated(gaps, "target_date", query, today),
            lambda row: _Deadline(
                "gap_target",
                row.id,
                row.target_date,
                row.owner,
                row.owner_team,
                entity=row.org_unit,
                obligation_id=row.tenant_obligation.obligation_id,
                gap=row,
            ),
        ),
        (
            _dated(occurrences, "due_date", query, today),
            lambda row: _Deadline(
                "duty_due",
                row.id,
                row.due_date,
                row.owner,
                row.owner_team,
                entity=row.org_unit,
                obligation_id=row.tenant_obligation.obligation_id,
                title=row.recurring_duty.title,
            ),
        ),
    ]


def _case_branches(query: HomeRoadmapQuery, today: datetime.date) -> list[_Branch]:
    """An open case's internal deadline and its live, open actions' due dates, on the cases
    the regulatory branch would list (FP-03). A case in `closed` or `dismissed` takes both
    with it; a done or removed action leaves on its own."""
    cases = _open_cases()
    deadlines = ImpactAssessment.objects.filter(case__in=cases).select_related("case__change", "case__owner")
    actions = Action.objects.filter(case__in=cases, done_at__isnull=True, removed_at__isnull=True).select_related("case", "owner")
    return [
        (
            _dated(deadlines, "internal_deadline", query, today),
            lambda row: _Deadline(
                "internal_deadline",
                row.id,
                row.internal_deadline,
                row.case.owner,
                None,
                title=row.case.change.title,
                change_id=row.case.change_id,
            ),
        ),
        (
            _dated(actions, "due_date", query, today),
            lambda row: _Deadline("action_due", row.id, row.due_date, row.owner, None, title=row.title, change_id=row.case.change_id),
        ),
    ]


def _certificate(item_type: RoadmapItemType, licence: Licence, day: datetime.date) -> _Deadline:
    return _Deadline(item_type, licence.id, day, licence.owner_user, licence.owner_team, entity=licence.org_unit, licence=licence)


def _deadline_items(deadlines: Sequence[_Deadline], order: list[str]) -> list[HomeRoadmapItem]:
    """The bank's own dates as roadmap items, in a fixed number of queries, each skipped when
    nothing needs it."""
    reviewed = {deadline.obligation_id for deadline in deadlines if deadline.item_type == "review_due"}
    headings = obligation_headings(cast(set[uuid.UUID], reviewed), order)
    teams = vocabulary_refs(TeamLabel, [deadline.team for deadline in deadlines if deadline.team is not None], order)
    types = term_refs(
        list({deadline.licence.licence_type_id: deadline.licence.licence_type for deadline in deadlines if deadline.licence}.values()),
        order,
    )

    def title(deadline: _Deadline) -> str:
        if deadline.title is not None:
            return deadline.title
        if deadline.gap is not None:
            return deadline.gap.title
        if deadline.licence is not None:
            return types[deadline.licence.licence_type_id].label
        return headings[cast(uuid.UUID, deadline.obligation_id)].title

    def team(ref: LibraryRef) -> TermRef:
        return TermRef(key=ref.key, kind=ref.kind, label=ref.label)

    return [
        HomeRoadmapItem(
            id=f"{deadline.item_type}:{deadline.record_id}",
            kind=INTERNAL,
            item_type=deadline.item_type,
            date=deadline.date,
            date_precision=DAY,
            quarter=quarter_of(deadline.date),
            label=None,
            title=title(deadline),
            status=None,
            urgency=None,
            source_label=None,
            change_id=deadline.change_id,
            owner=None
            if deadline.person is None and deadline.team is None
            else HomeRoadmapOwner(
                person=None if deadline.person is None else PersonRef(id=deadline.person.id, name=deadline.person.name),
                team=None if deadline.team is None else team(teams[deadline.team.id]),
            ),
            # A case's items name their record by `changeId`, the bank's page for its case.
            subject=None
            if deadline.change_id is not None
            else HomeRoadmapSubject(
                obligation_id=deadline.obligation_id,
                gap_id=None if deadline.gap is None else deadline.gap.id,
                licence_id=None if deadline.licence is None else deadline.licence.id,
                entity=None if deadline.entity is None else HomeRoadmapEntity(id=deadline.entity.id, name=deadline.entity.name),
            ),
            obligations=[],
        )
        for deadline in deadlines
    ]


def _read(
    tenant: Tenant,
    order: list[str],
    query: HomeRoadmapQuery,
    *,
    in_scope: list[uuid.UUID] | None,
    cases_reader: bool,
    limit: int | None = None,
) -> tuple[list[HomeRoadmapItem], int]:
    """Every branch the filter names, merged in date order, and the total. The register
    branches only with `in_scope` (`in_scope_entries()`), never passed without
    `register.read`. With `limit`, each branch reads at most that many rows and one count
    spans every branch: a page query per branch and a single count (H115).
    """
    items: list[HomeRoadmapItem] = []
    branches: list[QuerySet[Any]] = []

    def page(rows: QuerySet[Any]) -> list[Any]:
        branches.append(rows)
        return list(rows if limit is None else rows[:limit])

    if query.kind != "internal":
        items += _items(page(_cases(tenant, query)), order)
    if query.kind != "regulatory":
        deadlines = [
            deadline(row)
            for rows, deadline in _internal_branches(tenant, query, in_scope=in_scope, cases_reader=cases_reader)
            for row in page(rows)
        ]
        items += _deadline_items(deadlines, order)
    items.sort(key=lambda item: (item.date, item.id))
    if limit is None:
        return items, len(items)
    # Every branch row is one uuid-keyed record, so the ids stack into one count; Django drops
    # an empty `IN` branch from the union.
    first, *rest = [rows.order_by().values_list("pk") for rows in branches]
    return items[:limit], first.union(*rest, all=True).count()


def _quarters(items: Iterable[HomeRoadmapItem]) -> list[str]:
    """The quarter keys present, in date order and each once, so no heading is empty."""
    return list(dict.fromkeys(item.quarter for item in items))


# --- The three reads (the only roadmap queries there are) ---
def roadmap_items(
    tenant: Tenant, order: list[str], query: HomeRoadmapQuery, *, register_reader: bool = False, cases_reader: bool = False
) -> HomeRoadmap:
    """`GET /roadmap`: every dated change the bank has open work on and its own deadlines in
    the window, with the quarter keys for the roster. Register deadlines only for a
    `register_reader`, case deadlines only for a `cases_reader`. Empty means nothing ahead.
    """
    in_scope = in_scope_entries(tenant) if register_reader else None
    items, _count = _read(tenant, order, query, in_scope=in_scope, cases_reader=cases_reader)
    return HomeRoadmap(items=items, quarters=_quarters(items))


def coming_up(
    tenant: Tenant, order: list[str], limit: int, *, in_scope: list[uuid.UUID] | None = None, cases_reader: bool = False
) -> tuple[list[HomeRoadmapItem], int]:
    """The first `limit` roadmap items and the total, for Today's "Coming up" (HOM-01): the
    same branches as `GET /roadmap`, so panel and page agree. `limit` is Today's setting
    (`HOME_COMING_UP_ITEMS`); register deadlines only with `in_scope` (H115).
    """
    return _read(tenant, order, HomeRoadmapQuery(), in_scope=in_scope, cases_reader=cases_reader, limit=limit)


def calendar_items(tenant: Tenant, order: list[str]) -> list[tuple[str, HomeRoadmapItem]]:
    """What a calendar subscription carries (HOM-04, ADR 0045, AC-TEN1): the regulatory
    branch `_cases()` alone, never `_internal_branches()`, so no bank deadline reaches a
    calendar; and only dates stated to the day, since an all-day event must not pin a day
    nobody published. Each item comes with its change's stable key, the event UID, because
    the item's own `id` names the bank's case.
    """
    cases = list(
        _cases(tenant, HomeRoadmapQuery(kind="regulatory")).filter(change__key_date_precision=DatePrecision.DAY.value)
    )
    return list(zip((case.change.stable_key for case in cases), _items(cases, order), strict=True))
