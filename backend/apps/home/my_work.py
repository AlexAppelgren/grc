"""My work (HOM-05, TEN-03, D-23, D-24, D-97): what a person or a department is responsible
for or takes part in, bucketed overdue, due soon, changes on your items and the rest.

One definition, read by the page and later by the reminders, the digest and the member
removal preview: ORM queries under the activated tenant, so row-level security applies
exactly as it does everywhere else, and no database view. A read module: nothing here
writes.

1. **Who.** `mine` is the caller and the caller's teams. `unit` is the teams of that
   organisation unit and of every unit below it, with their active members; a department
   view is a filter, never a grant.
2. **What.** Register entries where the person is first-line owner or compliance contact,
   or a team owns it; entity rows, gaps and internal items they or their teams own. Hidden:
   entries and entity rows that do not apply, closed gaps and inactive internal items.
   Participations are the participant package's source, and case ownership chunk 9's.
3. **When.** A person involved in the entry itself is dated by the earliest open date on
   it (its review, every applying entity row's review, every open gap's target); one
   involved only through an entity row or a gap by that child's own date. Compared with the
   bank's own today.
4. **Changes on your items.** Open cases whose change has a confirmed link to an obligation
   in the list (confirmed by a person or by an agent other than the suggesting one, D-97),
   and new obligation versions applied within `MY_WORK_AWARE_DAYS`. Never the caller's own
   confirmation or approval, never an unconfirmed suggestion.
5. **Permissions.** Register and internal-item rows need `register.read`, case rows
   `cases.read`, and a case reached through a link needs both. Rows and counts come from
   the filtered set; a kind the reader may not read is named in `permission_limited`.
6. **The footprint** is never applied (D-24).

The number of queries does not grow with the number of rows (HOM-S12).
"""

from __future__ import annotations

import datetime
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.cases.models import ChangeCase
from apps.home.schemas import (
    HomeWorkCounts,
    HomeWorkDate,
    HomeWorkEntity,
    HomeWorkItem,
    HomeWorkPage,
    HomeWorkQuery,
    HomeWorkReason,
    HomeWorkSubject,
    HomeWorkVia,
    HomeWorkWho,
    WorkBucket,
    WorkDateKind,
    WorkItemKind,
    WorkReason,
)
from apps.identity.models import Membership, User
from apps.library.models import ObligationVersion
from apps.library.reading import obligation_headings, today_for, vocabulary_refs
from apps.register.models import Applicability, Gap, TenantObligation, TenantObligationScope
from apps.shared.authentication import Principal
from apps.shared.models import Tenant
from apps.shared.permissions import CASES_READ, REGISTER_READ
from apps.taxonomy.models import (
    CaseStatusCategory,
    ComplianceStatus,
    ComplianceStatusLabel,
    GapCategory,
    Team,
    TeamLabel,
)
from apps.taxonomy.schemas import PersonRef, TermRef
from apps.tenants.models import InternalItem, OrgUnit, TeamMember
from apps.watch.models import ChangeObligation
from apps.watch.reading import urgency_refs
from apps.watch.schemas import DatePrecision

OBLIGATION: WorkItemKind = "tenant_obligation"
INTERNAL_ITEM: WorkItemKind = "internal_item"
CASE: WorkItemKind = "change_case"
BUCKETS: tuple[WorkBucket, ...] = ("overdue", "due_soon", "aware", "open")
OWNER: WorkReason = "owner"
# The categories a bank has finished with (D-13), as on the roadmap.
FINISHED = (CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value)
DAY: DatePrecision = "day"


@dataclass(frozen=True)
class _Reason:
    """One reason, hashable so a row carries each once. `via` is the linked obligation on a
    change's row."""

    reason: WorkReason
    person_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    via: uuid.UUID | None = None


@dataclass(frozen=True)
class _Date:
    value: datetime.date
    kind: WorkDateKind
    precision: DatePrecision = DAY
    entity_id: uuid.UUID | None = None


@dataclass
class _Row:
    """One record on the list while it is being assembled."""

    kind: WorkItemKind
    subject_id: uuid.UUID
    reasons: set[_Reason] = field(default_factory=set)
    dates: set[_Date] = field(default_factory=set)
    aware: set[_Date] = field(default_factory=set)
    title: str = ""
    status_id: uuid.UUID | None = None
    urgency_id: uuid.UUID | None = None
    urgency_ordinal: int = 0
    open_change_count: int = 0


@dataclass(frozen=True)
class _Who:
    """The people and teams a list is about."""

    people: frozenset[uuid.UUID]
    teams: frozenset[uuid.UUID]


def page(
    tenant: Tenant, principal: Principal, order: list[str], query: HomeWorkQuery
) -> HomeWorkPage:
    """One page of My work for `principal` in the activated `tenant`, labels in `order`."""
    who = _mine(principal) if query.unit is None else _department(query.unit)
    rows, titles = _rows(tenant, principal, order, who)
    today = today_for(tenant)
    placed = []
    for row in rows:
        bucket = _bucket(row, today)
        placed.append((bucket, _shown_date(bucket, row, today), row))
    placed.sort(key=_sort_key)
    counts = {bucket: 0 for bucket in BUCKETS}
    for bucket, _date, _row in placed:
        counts[bucket] += 1
    wanted = [entry for entry in placed if query.bucket in (None, entry[0])]
    return HomeWorkPage(
        scope=query.scope,
        unit=query.unit,
        counts=HomeWorkCounts(
            overdue=counts["overdue"],
            due_soon=counts["due_soon"],
            aware=counts["aware"],
            open=counts["open"],
        ),
        permission_limited=_limited(principal),
        items=_items(wanted[query.offset : query.offset + query.limit], order, titles),
        total=len(wanted),
    )


def _limited(principal: Principal) -> list[WorkItemKind]:
    limited: list[WorkItemKind] = []
    if not principal.has_permission(REGISTER_READ):
        limited += [OBLIGATION, INTERNAL_ITEM]
    if not principal.has_permission(CASES_READ):
        limited.append(CASE)
    return limited


# ---------------------------------------------------------------------------------------
# Who: the caller, or a department
# ---------------------------------------------------------------------------------------
def _mine(principal: Principal) -> _Who:
    teams = TeamMember.objects.filter(user_id=principal.subject_id).values_list(
        "team_id", flat=True
    )
    return _Who(people=frozenset({principal.subject_id}), teams=frozenset(teams))


def _department(unit_id: uuid.UUID) -> _Who:
    """The teams of `unit_id` and every unit below it, with their active members. The whole
    organisation tree is one small query; walking it here keeps the count flat."""
    children: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    known = set()
    for unit, parent in OrgUnit.objects.values_list("id", "parent_id"):
        children[parent].append(unit)
        known.add(unit)
    if unit_id not in known:
        raise ValidationError("That unit is not here.", code="not_found")
    units, stack = set(), [unit_id]
    while stack:
        current = stack.pop()
        if current not in units:
            units.add(current)
            stack.extend(children[current])
    teams = frozenset(Team.objects.filter(org_unit_id__in=units).values_list("id", flat=True))
    active = Membership.objects.filter(user_id=OuterRef("user_id"), deactivated_at__isnull=True)
    people = (
        TeamMember.objects.filter(team_id__in=teams)
        .filter(Exists(active))
        .values_list("user_id", flat=True)
    )
    return _Who(people=frozenset(people), teams=teams)


def _owned_by(who: _Who, person: str, team: str) -> Q:
    return Q(**{f"{person}__in": who.people}) | Q(**{f"{team}__in": who.teams})


def _owner(who: _Who, person_id: uuid.UUID | None, team_id: uuid.UUID | None) -> set[_Reason]:
    """The owner reasons one owner column pair gives, for the people and teams listed."""
    reasons = set()
    if person_id in who.people:
        reasons.add(_Reason(OWNER, person_id=person_id))
    if team_id in who.teams:
        reasons.add(_Reason(OWNER, team_id=team_id))
    return reasons


# ---------------------------------------------------------------------------------------
# What: the sources, each one query
# ---------------------------------------------------------------------------------------
def _rows(
    tenant: Tenant, principal: Principal, order: list[str], who: _Who
) -> tuple[list[_Row], dict[uuid.UUID, str]]:
    """Every row the caller may read, and the titles of the obligations among them."""
    if not principal.has_permission(REGISTER_READ):
        return [], {}
    register = _register(who)
    titles = {
        obligation_id: heading.title
        for obligation_id, heading in obligation_headings(list(register), order).items()
    }
    for obligation_id, row in register.items():
        row.title = titles[obligation_id]
    _versions(tenant, principal, register)
    rows = [*register.values(), *_internal_items(who)]
    if principal.has_permission(CASES_READ):
        rows += _linked_cases(tenant, principal, register)
    return rows, titles


def _register(who: _Who) -> dict[uuid.UUID, _Row]:
    """Register rows keyed by obligation id: entries, entity rows and gaps, merged."""
    rows: dict[uuid.UUID, _Row] = {}

    def row_of(entry: TenantObligation) -> _Row:
        row = rows.get(entry.obligation_id)
        if row is None:
            row = rows[entry.obligation_id] = _Row(
                OBLIGATION, entry.obligation_id, status_id=entry.compliance_status_id
            )
        return row

    applies = ~Q(applicability=Applicability.DOES_NOT_APPLY.value)
    entry_applies = ~Q(tenant_obligation__applicability=Applicability.DOES_NOT_APPLY.value)
    live_scope = applies & entry_applies
    open_gap = entry_applies & ~Q(status__kind=GapCategory.CLOSED.value)

    whole: dict[uuid.UUID, _Row] = {}  # entry id -> row, where someone is on the entry itself
    for entry in TenantObligation.objects.filter(applies).filter(
        _owned_by(who, "first_line_owner_id", "owner_team_id")
        | Q(compliance_contact_id__in=who.people)
    ):
        row = row_of(entry)
        row.reasons |= _owner(who, entry.first_line_owner_id, entry.owner_team_id)
        row.reasons |= _owner(who, entry.compliance_contact_id, None)
        whole[entry.id] = row
        if entry.next_review_date is not None:
            row.dates.add(_Date(entry.next_review_date, "review"))

    owned_scope = _owned_by(who, "owner_id", "owner_team_id")
    owned_gap = _owned_by(who, "owner_id", "owner_team_id")
    for scope in (
        TenantObligationScope.objects.filter(live_scope)
        .filter(owned_scope | Q(tenant_obligation_id__in=whole))
        .select_related("tenant_obligation")
    ):
        row = whole.get(scope.tenant_obligation_id) or row_of(scope.tenant_obligation)
        owners = _owner(who, scope.owner_id, scope.owner_team_id)
        row.reasons |= owners
        if scope.next_review_date is not None and (owners or scope.tenant_obligation_id in whole):
            row.dates.add(_Date(scope.next_review_date, "review", entity_id=scope.org_unit_id))

    for gap in (
        Gap.objects.filter(open_gap)
        .filter(owned_gap | Q(tenant_obligation_id__in=whole))
        .select_related("tenant_obligation")
    ):
        row = whole.get(gap.tenant_obligation_id) or row_of(gap.tenant_obligation)
        owners = _owner(who, gap.owner_id, gap.owner_team_id)
        row.reasons |= owners
        if gap.target_date is not None and (owners or gap.tenant_obligation_id in whole):
            row.dates.add(_Date(gap.target_date, "gap_target", entity_id=gap.org_unit_id))
    return rows


def _internal_items(who: _Who) -> list[_Row]:
    rows = []
    for item in InternalItem.objects.filter(active=True).filter(
        _owned_by(who, "owner_user_id", "owner_team_id")
    ):
        row = _Row(
            INTERNAL_ITEM,
            item.id,
            reasons=_owner(who, item.owner_user_id, item.owner_team_id),
            title=item.name,
        )
        if item.next_review_on is not None:
            row.dates.add(_Date(item.next_review_on, "review"))
        rows.append(row)
    return rows


def _local_day(tenant: Tenant, moment: datetime.datetime) -> datetime.date:
    return timezone.localtime(moment, ZoneInfo(tenant.timezone)).date()


def _versions(tenant: Tenant, principal: Principal, register: dict[uuid.UUID, _Row]) -> None:
    """A new version of an obligation on the list, applied within the window by someone
    other than the caller, marks its row (D-25)."""
    since = timezone.now() - datetime.timedelta(days=settings.MY_WORK_AWARE_DAYS)
    versions = (
        ObligationVersion.objects.filter(
            obligation_id__in=register, version_number__gt=1, created_at__gte=since
        )
        .exclude(approved_by_id=principal.subject_id)
        .exclude(applied_by_proposal__proposed_by_user_id=principal.subject_id)
    )
    for obligation_id, created_at in versions.values_list("obligation_id", "created_at"):
        register[obligation_id].aware.add(_Date(_local_day(tenant, created_at), "version_applied"))


def _linked_cases(
    tenant: Tenant, principal: Principal, register: dict[uuid.UUID, _Row]
) -> list[_Row]:
    """The bank's open cases on changes with a confirmed link to an obligation on the list.
    Every such case counts toward its obligation's `open_change_count`; only a link someone
    other than the caller confirmed puts the case itself on the list."""
    open_cases = ChangeCase.objects.filter(change_id=OuterRef("change_id")).exclude(
        status__in=FINISHED
    )
    links = list(
        ChangeObligation.objects.filter(obligation_id__in=register, confirmed_at__isnull=False)
        .filter(Exists(open_cases))
        .values_list("change_id", "obligation_id", "confirmed_by_id", "confirmed_at")
    )
    cases = {
        case.change_id: case
        for case in ChangeCase.objects.filter(change_id__in={link[0] for link in links})
        .exclude(status__in=FINISHED)
        .select_related("change", "urgency")
    }
    rows: dict[uuid.UUID, _Row] = {}
    for change_id, obligation_id, confirmed_by_id, confirmed_at in links:
        case = cases[change_id]
        register[obligation_id].open_change_count += 1
        if confirmed_by_id == principal.subject_id:
            continue
        row = rows.get(case.id)
        if row is None:
            row = rows[case.id] = _Row(
                CASE,
                case.change_id,
                title=case.change.title,
                urgency_id=case.urgency_id,
                urgency_ordinal=case.urgency.ordinal,
            )
            key_date = case.change.key_date
            if key_date is not None:
                precision = cast(DatePrecision, case.change.key_date_precision or DAY)
                row.dates.add(_Date(key_date, "key_date", precision))
        # The query keeps confirmed links only, so the stamp is always there.
        row.aware.add(_Date(_local_day(tenant, cast(datetime.datetime, confirmed_at)), "linked"))
        for reason in register[obligation_id].reasons:
            row.reasons.add(
                _Reason(reason.reason, reason.person_id, reason.team_id, via=obligation_id)
            )
    return list(rows.values())


# ---------------------------------------------------------------------------------------
# When: the bucket and the date that put a row there
# ---------------------------------------------------------------------------------------
def _earliest(dates: Iterable[_Date]) -> _Date | None:
    return min(
        dates,
        key=lambda date: (date.value, date.kind, date.entity_id is not None, str(date.entity_id)),
        default=None,
    )


def _next(row: _Row, today: datetime.date) -> _Date | None:
    """The earliest open date. A change's key date counts only while it is still ahead: a
    key date in the past means the rule is in force, not that anything is overdue."""
    return _earliest(
        date for date in row.dates if not (date.kind == "key_date" and date.value < today)
    )


def _bucket(row: _Row, today: datetime.date) -> WorkBucket:
    date = _next(row, today)
    if date is not None and date.value < today:
        return "overdue"
    if date is not None and date.value <= today + datetime.timedelta(
        days=settings.MY_WORK_DUE_SOON_DAYS
    ):
        return "due_soon"
    return "aware" if row.aware else "open"


def _shown_date(bucket: WorkBucket, row: _Row, today: datetime.date) -> _Date | None:
    """The date the row shows: the latest change on the item in `aware`, the next date
    elsewhere."""
    if bucket == "aware":
        return max(row.aware, key=lambda date: (date.value, date.kind))
    return _next(row, today)


def _sort_key(
    entry: tuple[WorkBucket, _Date | None, _Row],
) -> tuple[int, bool, datetime.date, int, str]:
    """Section order, then date with undated rows last, then urgency, then identifier, so
    two reads never swap rows."""
    bucket, date, row = entry
    return (
        BUCKETS.index(bucket),
        date is None,
        datetime.date.max if date is None else date.value,
        row.urgency_ordinal,
        str(row.subject_id),
    )


# ---------------------------------------------------------------------------------------
# The rows of one page, named in a fixed number of queries
# ---------------------------------------------------------------------------------------
def _items(
    shown: list[tuple[WorkBucket, _Date | None, _Row]],
    order: list[str],
    titles: dict[uuid.UUID, str],
) -> list[HomeWorkItem]:
    rows = [row for _bucket, _date, row in shown]
    reasons = [reason for row in rows for reason in row.reasons]
    people = dict(
        User.objects.filter(id__in={r.person_id for r in reasons if r.person_id}).values_list(
            "id", "name"
        )
    )
    teams = _terms(
        TeamLabel, Team.objects.filter(id__in={r.team_id for r in reasons if r.team_id}), order
    )
    statuses = _terms(
        ComplianceStatusLabel,
        ComplianceStatus.objects.filter(id__in={row.status_id for row in rows if row.status_id}),
        order,
    )
    urgencies = urgency_refs({row.urgency_id for row in rows if row.urgency_id}, order)
    entities = dict(
        OrgUnit.objects.filter(
            id__in={date.entity_id for _b, date, _r in shown if date and date.entity_id}
        ).values_list("id", "name")
    )

    def reason_out(reason: _Reason) -> HomeWorkReason:
        person = (
            None
            if reason.person_id is None
            else PersonRef(id=reason.person_id, name=people[reason.person_id])
        )
        team = None if reason.team_id is None else teams[reason.team_id]
        via = (
            None
            if reason.via is None
            else HomeWorkVia(obligation_id=reason.via, title=titles[reason.via])
        )
        return HomeWorkReason(
            reason=reason.reason, who=HomeWorkWho(person=person, team=team), via=via
        )

    items = []
    for bucket, date, row in shown:
        ordered = sorted(
            row.reasons, key=lambda r: (r.reason, str(r.person_id), str(r.team_id), str(r.via))
        )
        items.append(
            HomeWorkItem(
                bucket=bucket,
                item_kind=row.kind,
                subject=HomeWorkSubject(
                    obligation_id=row.subject_id if row.kind == OBLIGATION else None,
                    change_id=row.subject_id if row.kind == CASE else None,
                    internal_item_id=row.subject_id if row.kind == INTERNAL_ITEM else None,
                    title=row.title,
                ),
                entity=None
                if date is None or date.entity_id is None
                else HomeWorkEntity(id=date.entity_id, name=entities[date.entity_id]),
                date=None
                if date is None
                else HomeWorkDate(value=date.value, kind=date.kind, precision=date.precision),
                reasons=[reason_out(reason) for reason in ordered],
                status=None if row.status_id is None else statuses[row.status_id],
                urgency=None if row.urgency_id is None else urgencies[row.urgency_id],
                open_change_count=row.open_change_count,
            )
        )
    return items


def _terms(
    label_model: type[TeamLabel] | type[ComplianceStatusLabel],
    rows: Iterable[Team | ComplianceStatus],
    order: list[str],
) -> dict[uuid.UUID, TermRef]:
    """`{key, kind, label}` of the bank's own list rows, labels in one query."""
    return {
        row_id: TermRef(key=ref.key, kind=ref.kind, label=ref.label)
        for row_id, ref in vocabulary_refs(label_model, list(rows), order).items()
    }
