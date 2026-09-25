"""The roadmap by quarter (HOM-03, FP-03).

One module owns the roadmap query, so no second one is ever written: `roadmap_items()`
answers `GET /roadmap`, `coming_up()` answers Today's "Coming up" panel and
`calendar_items()` a calendar subscription, all three from the same rows, rather than
asking the same question a second way (chunk 6 ruling 5).

A read module: nothing here writes. What it reads is two zones at once — the library's
dated changes beside this bank's own cases — under row-level security with the caller's
tenant activated, never by filtering in Python.

Three rules decide what is on the roadmap, and each belongs to somebody else:

- **The bank has open work on it.** A case in the `closed` or `dismissed` category is
  finished, and a date nobody is working towards any more is not something coming.
- **The date is inside the bank's regulatory scope.** `change_case.footprint_match` is the
  verdict `apps/cases/creation.py` computed from the one scope rule in
  `apps/library/reading.py` and `apps/cases/matching.py` keeps current. It is read here and
  never recomputed, so the roadmap cannot drift from the feed and the inventory (FP-03).
- **The date is still ahead** of the bank's own today, which is `today_for()` and nothing
  else. A date that has passed leaves the roadmap and stays on the change itself. A date the
  source stated as a month, a quarter or a year is stored on some day of that period, so it
  is ahead while its period has not ended (H22): "Q4 2026" stays through 31 December however
  early in the quarter it was stored.

Beside that regulatory branch sit the bank's own deadlines, `internal` and shown as "Our
deadline" with their owner (HOM-03, D-43, AC-TEN1), each one query:

- **Next reviews** of a register entry and of one legal entity's row, a compliant one
  included, unless the answer there is "does not apply".
- **Gap targets** of a gap that is open or being remediated; an accepted or closed gap has
  no target left to meet.
- **A certificate's expiry and its next audit**, from the entity's licence row, left out
  once the row is withdrawn.
- **A recurring duty's open occurrence** (REG-07); completing it drops it, and the next one
  it generates takes its place.
- **An open case's internal deadline** from its impact assessment (CAS-03), and **the due
  date of an action** that is neither done nor removed (CAS-04), each with its owner.

The register branches follow the regulatory scope as the regulatory branch does (FP-03) and
are read only for a reader holding `register.read`; the case branches read the case's own
footprint verdict, as the regulatory branch does, and only for a reader holding
`cases.read`; a certificate is any member's to see, as its own list is. The bank's own
deadlines never reach `calendar_items()`: a calendar carries public facts only (D-43, D-52).
What the screen draws its quarter roster from is computed here as well, because a
quarter near a year boundary is the bank's own question: two banks an hour apart can be in
two quarters, and each reads the one it is in.
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

# The regulatory branch: a change's own key date. Both are tier-one kinds
# (apps/shared/kinds.py, apps/home/schemas.py); the screen picks its pill from the first and
# the calendar builder its summary line from the second.
ITEM_KIND: RoadmapItemKind = "regulatory"
ITEM_TYPE: RoadmapItemType = "change_date"
INTERNAL: RoadmapItemKind = "internal"
DAY: Precision = "day"

# The gaps with a target still to meet (REG-03). Listed rather than excluded, the opposite of
# FINISHED below: a category added later must say it is still open before a count reads it.
OPEN_GAPS = (GapCategory.OPEN.value, GapCategory.REMEDIATING.value)

# The two categories a bank has finished with (D-13). Excluded rather than listed, so a
# category added to the state machine later is on the roadmap unless somebody says it is
# finished, which is the safe direction for a list of what is coming.
FINISHED = (CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value)


def quarter_of(day: datetime.date) -> str:
    """The quarter key `YYYY-Qn` a plain date falls in, for grouping and ordering. The
    screen renders the phrase from its own catalog and never from this string."""
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


# ---------------------------------------------------------------------------------------
# What is on the roadmap
# ---------------------------------------------------------------------------------------
def _dated(rows: QuerySet[Any], field: str, query: HomeRoadmapQuery, today: datetime.date) -> QuerySet[Any]:
    """`rows` whose `field` falls inside the window, earliest first with the row's id as a
    stable tiebreak, so two dates on one day never swap between two reads."""
    return _until(rows.filter(**{f"{field}__gte": _window_start(query, today)}), field, query)


def _window_start(query: HomeRoadmapQuery, today: datetime.date) -> datetime.date:
    """The window starts at the bank's own today even when `from` is earlier: the roadmap
    holds no item whose date has gone, so an earlier `from` widens nothing rather than
    reopening the past."""
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
    """The bank's open work on a dated change inside its regulatory scope.

    A key date stated less exactly than a day stays while its period runs (H22): whatever
    day of the period it was stored on, it is ahead exactly when the period is at or after
    the one the window starts in, so each precision compares with the start of its period.
    """
    since = _window_start(query, today_for(tenant))
    ahead = Q(change__key_date__gte=since)
    for precision in (DatePrecision.MONTH, DatePrecision.QUARTER, DatePrecision.YEAR):
        ahead |= Q(change__key_date_precision=precision.value, change__key_date__gte=_period_start(since, precision))
    return _until(_open_cases().select_related("change", "urgency").filter(ahead), "change__key_date", query)


def _item(case: ChangeCase, urgency: LibraryRef, obligations: list[WatchObligationLink]) -> HomeRoadmapItem:
    """One dated thing on the bank's calendar: library facts (the date, what the date is,
    the reform's title and who published it) beside this bank's own case status."""
    # `_cases()` filters on a key date inside the window, so every row that reaches here
    # has one; the column is nullable because a change may be registered before its date
    # is known.
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
    """The rows as the screen reads them. Four queries however many items there are: the
    urgency rows named by the page and their labels, the confirmed obligation links, and
    those obligations' titles."""
    # Through the watch app's own rule, never `vocabulary_refs()`: an urgency row's `kind`
    # column is its pill tone, and a tone is nobody's to send (NFR-03). Reading it the other
    # way put the tone on every roadmap item until 2026-09-21, against this module's own
    # documented example.
    urgencies = urgency_refs({case.urgency_id for case in cases}, order)
    links = _obligation_links([case.change_id for case in cases], order)
    return [_item(case, urgencies[case.urgency_id], links.get(case.change_id, [])) for case in cases]


def _obligation_links(
    change_ids: Collection[uuid.UUID], order: list[str]
) -> dict[uuid.UUID, list[WatchObligationLink]]:
    """The obligations each change touches, most confident first, as the watch feed answers
    them (WAT-04).

    Only confirmed links: an agent's suggestion is not a checked fact, and the roadmap is
    where a person plans work. Each says who confirmed it exactly as the change page does, so
    a link an independent agent confirmed reads machine-confirmed, naming both agents, and
    never as a person's verification (D-74). A bank's own decision about a link lives on its
    case and never reaches a library row, so nothing here is one bank's judgement.
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
                instrument_short_name=link.obligation.instrument.short_name,
                ref_label=link.obligation.ref_label,
                origin=cast(Origin, link.origin),
                confidence=None if link.confidence is None else float(link.confidence),
                confirmed=True,
                **keys.provenance(link),
            )
        )
    return by_change


# ---------------------------------------------------------------------------------------
# The bank's own deadlines (HOM-03, REG-02, REG-03, REG-07, TEN-02, CAS-03, CAS-04, D-43)
# ---------------------------------------------------------------------------------------
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
    """The ids of the library obligations inside the bank's regulatory scope, as a subquery:
    the inventory's own filter (FP-03), so the register's dates and standing count what the
    inventory lists and nothing else."""
    return in_view(Obligation.objects.all(), tenant, "in").values("id")


# A branch: its rows, and how one row becomes a deadline.
_Branch = tuple[QuerySet[Any], Callable[[Any], _Deadline]]


def _internal_branches(
    tenant: Tenant, query: HomeRoadmapQuery, *, register_reader: bool, cases_reader: bool
) -> list[_Branch]:
    today = today_for(tenant)
    live = Licence.objects.filter(withdrawn_on__isnull=True).select_related("licence_type", "owner_user", "owner_team", "org_unit")
    branches: list[_Branch] = [
        (_dated(live, "valid_until", query, today), lambda row: _certificate("certificate_expiry", row, row.valid_until)),
        (_dated(live, "next_audit_on", query, today), lambda row: _certificate("certificate_audit", row, row.next_audit_on)),
    ]
    if cases_reader:
        branches += _case_branches(query, today)
    if not register_reader:
        return branches
    in_scope = in_scope_obligations(tenant)
    does_not_apply = Applicability.DOES_NOT_APPLY.value
    entries = (
        TenantObligation.objects.filter(obligation_id__in=in_scope)
        .exclude(applicability=does_not_apply)
        .select_related("first_line_owner", "owner_team")
    )
    scopes = (
        TenantObligationScope.objects.filter(tenant_obligation__obligation_id__in=in_scope)
        .exclude(applicability=does_not_apply)
        .exclude(tenant_obligation__applicability=does_not_apply)
        .select_related("tenant_obligation", "owner", "owner_team", "org_unit")
    )
    gaps = Gap.objects.filter(tenant_obligation__obligation_id__in=in_scope, status__kind__in=OPEN_GAPS).select_related(
        "tenant_obligation", "owner", "owner_team", "org_unit"
    )
    # An occurrence on one entity is left out where that entity's answer is "does not apply",
    # as its review is; one on the whole entry where the entry's answer is.
    entity_does_not_apply = TenantObligationScope.objects.filter(
        tenant_obligation_id=OuterRef("tenant_obligation_id"), org_unit_id=OuterRef("org_unit_id"), applicability=does_not_apply
    )
    occurrences = (
        DutyOccurrence.objects.filter(tenant_obligation__obligation_id__in=in_scope, status__in=OPEN_DUTIES)
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
    """The bank's own dates as roadmap items, named in a fixed number of queries however
    many there are: the reviewed obligations' titles (two), the owning teams' labels and the
    certificates' type labels (one each), each skipped when nothing needs it."""
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
    register_reader: bool,
    cases_reader: bool,
    limit: int | None = None,
) -> tuple[list[HomeRoadmapItem], int]:
    """Every branch the filter names, merged in date order, and how many items they hold.

    With `limit`, each branch reads at most that many rows and counts the rest, so the first
    `limit` of the merge are the first `limit` of the whole roadmap without reading all of it:
    one page query and one count per branch, however many rows there are.
    """
    items: list[HomeRoadmapItem] = []
    count = 0

    def page(rows: QuerySet[Any]) -> list[Any]:
        nonlocal count
        taken = list(rows if limit is None else rows[:limit])
        count += len(taken) if limit is None else rows.count()
        return taken

    if query.kind != "internal":
        items += _items(page(_cases(tenant, query)), order)
    if query.kind != "regulatory":
        deadlines = [
            deadline(row)
            for rows, deadline in _internal_branches(tenant, query, register_reader=register_reader, cases_reader=cases_reader)
            for row in page(rows)
        ]
        items += _deadline_items(deadlines, order)
    items.sort(key=lambda item: (item.date, item.id))
    return (items if limit is None else items[:limit]), count


def _quarters(items: Iterable[HomeRoadmapItem]) -> list[str]:
    """The quarter keys present, in date order and each once. The items are already in date
    order, so the roster follows them and never shows an empty heading."""
    return list(dict.fromkeys(item.quarter for item in items))


# ---------------------------------------------------------------------------------------
# The three reads (chunk 6 ruling 5: these are the only roadmap queries there are)
# ---------------------------------------------------------------------------------------
def roadmap_items(
    tenant: Tenant, order: list[str], query: HomeRoadmapQuery, *, register_reader: bool = False, cases_reader: bool = False
) -> HomeRoadmap:
    """`GET /roadmap`: every dated change the bank has open work on and every deadline of
    its own inside the window the filters name, with the quarter keys the screen draws its
    roster from. The register's deadlines only for a `register_reader` and the case
    workflow's only for a `cases_reader`; without the flags a caller gets the dates every
    member may see. An empty answer means nothing is dated
    ahead, not that something failed.
    """
    items, _count = _read(tenant, order, query, register_reader=register_reader, cases_reader=cases_reader)
    return HomeRoadmap(items=items, quarters=_quarters(items))


def coming_up(
    tenant: Tenant, order: list[str], limit: int, *, register_reader: bool = False, cases_reader: bool = False
) -> tuple[list[HomeRoadmapItem], int]:
    """The first `limit` roadmap items and how many there are in all, for Today's "Coming
    up" panel and the count beside it (HOM-01).

    The same branches as `GET /roadmap` with no filter, so the panel and the page can never
    disagree about what is next. `limit` is the caller's, because the length of Today's list
    is Today's decision (`HOME_COMING_UP_ITEMS`).
    """
    return _read(tenant, order, HomeRoadmapQuery(), register_reader=register_reader, cases_reader=cases_reader, limit=limit)


def calendar_items(tenant: Tenant, order: list[str]) -> list[tuple[str, HomeRoadmapItem]]:
    """What a calendar subscription carries (HOM-04, ADR 0045, AC-TEN1): the roadmap's own
    rows, narrowed twice, each beside its change's stable key, which is the event's UID.

    - **The dates the outside world set, and no other.** This reads `_cases()`, the
      regulatory branch, alone. The bank's own deadlines — a next review, a gap target, a
      certificate's expiry or audit, a duty's occurrence, a case's internal deadline or an
      action's due date — come from `_internal_branches()`, which this never
      calls, so none of them reaches a calendar a provider outside the bank can read.
    - **Stated to the day.** An all-day event is one day. A date the source gave as a month
      or a quarter would be pinned to a day nobody published, so it stays on the roadmap
      and off the calendar.

    The stable key rides beside the item rather than in it because it is the calendar's
    identifier and not the screen's: an item's own `id` names the bank's case, and a UID
    leaves the bank.
    """
    cases = list(
        _cases(tenant, HomeRoadmapQuery(kind="regulatory")).filter(change__key_date_precision=DatePrecision.DAY.value)
    )
    return list(zip((case.change.stable_key for case in cases), _items(cases, order), strict=True))
