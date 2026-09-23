"""The watch reads: the bank's feed, one change, an obligation's related changes and the
console's Change facts queue (WAT-02, WAT-03, WAT-04, CAS-01, FP-03, FP-04).

`c5-watch-feed-read` built the feed and the console list, `c5-watch-change-reads` the
change read and the obligation's related changes.

A read module: nothing here writes, so it neither opens the watch door nor calls
`library_write()`. What it joins is two zones at once — the library's change beside the
reader's own case — and the tenant half is read under row-level security with the caller's
tenant activated, never by filtering in Python. The one join is a `FilteredRelation`: the
condition sits on the JOIN rather than in the WHERE, so a change this bank has no case for
still answers a row, with a null case.

The console list is the same read with that join left out. A platform console session
belongs to no tenant, so there is no case to join and `WatchConsoleChangeRow` carries no
`case` member at all — a member that were merely null would invite a console screen to
render one bank's judgement.

Nothing here is a settled fact until somebody confirms it. A change is what an agent
sighted: its type and classification carry the agent's confidence and a `suggested` marker
until an independent agent or a person confirms them (WAT-03, D-74), a link is a
suggestion until then (WAT-04), each fact names who suggested and who confirmed it, an
agent's confirmation reads machine-confirmed and never as a person's verification, and
`inFootprint` says only that the change is worth this bank's attention — never that an
obligation applies to it or that it complies, which are separate facts (REG-01, REG-02).

The footprint rule is the one in `apps/library/reading.py` and the SQL function behind it,
used exactly as the obligations list uses them: `taxonomy_in_footprint` narrows the query
and `outside_reasons()` gives the verdict on the rows that come back. There is no second
rule here. A change's scope is its own terms plus the jurisdictions its authority reaches,
derived at match time by the instruments' own `reaching()` and never stored (FP-04, D-28,
D-29); a change with no authority is not restricted by jurisdiction.

"Markets we watch" (`footprint=watched`) shows only what watching adds: a change outside
the footprint whose own terms still match it and whose authority reaches a market this bank
watches. Watching sets no urgency and opens nothing (D-30): the view reads the cases, it
never writes one.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection, Mapping, Sequence
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.contrib.postgres.expressions import ArraySubquery
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db.models import (
    BooleanField,
    Exists,
    ExpressionWrapper,
    F,
    FilteredRelation,
    Func,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    UUIDField,
    Value,
)

from apps.cases.models import CaseLinkDecision as CaseLinkDecisionKind
from apps.cases.models import CaseObligationLink, ChangeCase
from apps.library.models import ObligationTitle
from apps.library.reading import (
    NOT_FOUND,
    jurisdiction_scopes,
    localized,
    obligation_subject,
    outside_reasons,
    reaching,
    vocabulary_refs,
)
from apps.library.schemas import LibraryRef
from apps.shared.models import Tenant
from apps.shared.schemas import PageQuery
from apps.taxonomy import matching
from apps.taxonomy.models import (
    CaseStatusCategory,
    ChangeTypeLabel,
    FlagLabel,
    TaxonomyTerm,
    TaxonomyTermLabel,
    Urgency,
    UrgencyLabel,
    WatchedMarket,
)
from apps.taxonomy.reading import Labels, label_of
from apps.watch import keys
from apps.watch.models import ChangeObligation, ChangeTerm, RegulatoryChange
from apps.watch.schemas import (
    CaseCategory,
    CaseLinkDecision,
    ChangeStatus,
    DatePrecision,
    Origin,
    WatchCaseObligationDecision,
    WatchChangeCase,
    WatchChangeDetail,
    WatchChangeDocument,
    WatchChangeEvent,
    WatchChangePage,
    WatchChangeQuery,
    WatchChangeRow,
    WatchConsoleChangePage,
    WatchConsoleChangeQuery,
    WatchConsoleChangeRow,
    WatchFact,
    WatchObligationChangePage,
    WatchObligationLink,
)

# The columns of the reader's own case the feed answers, read off the one left join, by
# the name each is read under and its path from the case. A foreign key is named without
# its `_id` suffix on purpose: `F("own_case__urgency")` resolves to the column on
# `change_case` and adds no second join. The confirming person's name is the one path that
# does join, a left join to `app_user` in the same query, so naming them costs no query
# per row (WAT-05).
_CASE_COLUMNS = {
    "id": "id",
    "status": "status",
    "urgency": "urgency",
    "urgency_confirmed": "urgency_confirmed",
    "owner": "owner",
    "footprint_match": "footprint_match",
    "so_what_text": "so_what_text",
    "so_what_confirmed": "so_what_confirmed",
    "so_what_confirmed_at": "so_what_confirmed_at",
    "so_what_confirmed_by_name": "so_what_confirmed_by__name",
}
# Beside the case, where a change's jurisdiction comes from (its authority's) and the first
# term it reaches that mirrors a market this bank watches (FP-04).
_JURISDICTION = "authority_jurisdiction_id"
_WATCHED_TERM = "watched_term_id"


# ---------------------------------------------------------------------------------------
# The pieces both lists are built from
# ---------------------------------------------------------------------------------------
# What every change row is loaded with: its type, and the two agents behind the type's
# suggestion and confirmation, so a row names them without a query of its own (D-74).
_CHANGE_JOINS = ("change_type", *keys.CHANGE_TYPE_AGENTS)


def _own_term_ids() -> ArraySubquery:
    """A change's own scope term ids as one `uuid[]`. A flag is a `change_term` row too and
    never scopes a change: it says what the reform is about, not who it reaches (WAT-03)."""
    return ArraySubquery(
        ChangeTerm.objects.filter(change=OuterRef("pk"), term__isnull=False).order_by().values("term_id"),
        output_field=ArrayField(UUIDField()),
    )


def _scope_term_ids() -> Func:
    """A change's scope term ids as one `uuid[]`, for the database's footprint function: its
    own terms and the jurisdiction terms its authority reaches (`reaching()`), none without
    an authority. The SQL twin of `_Scopes`."""
    reached = ArraySubquery(
        TaxonomyTerm.objects.filter(reaching(OuterRef("authority__jurisdiction_id"))).order_by().values("id"),
        output_field=ArrayField(UUIDField()),
    )
    return Func(_own_term_ids(), reached, function="array_cat", output_field=ArrayField(UUIDField()))


def _in_footprint(tenant: Tenant, term_ids: Func | ArraySubquery) -> Func:
    """The database's footprint function over one row's term ids."""
    return Func(Value(tenant.id, output_field=UUIDField()), term_ids, function=matching.SQL_FUNCTION, output_field=BooleanField())


def urgency_refs(ids: Collection[uuid.UUID], order: list[str]) -> dict[uuid.UUID, LibraryRef]:
    """`{key, kind, label}` per urgency row named by a page, from two queries.

    `kind` is null on purpose. An urgency row's own `kind` column is its pill tone, and a
    tone is nobody's to send (NFR-03): the screen takes the tone from the key's fixed
    severity order. This is why the urgency reference is built here rather than through
    `vocabulary_refs()`, which answers the row's stored kind.

    Public because it is the one rule, and every surface that shows an urgency has to obey
    it: the feed and the change page here, the roadmap and Today's "Coming up" through
    `apps/home/roadmap.py`, and the public list of dates through `apps/home/calendar.py`.
    Reaching for `vocabulary_refs()` instead is how a pill tone leaves the API, which it did
    on the roadmap until 2026-09-21.
    """
    rows = list(Urgency.objects.filter(id__in=ids))
    labels = Labels.for_rows(UrgencyLabel, rows)
    return {
        row.id: LibraryRef(
            key=row.key, kind=None, label=label_of(labels.texts(row.id), order, original=labels.original(row.id), key=row.key)
        )
        for row in rows
    }


class _Classification:
    """The flags and scope terms of a page of changes, labelled, from three queries and
    grouped by change once: a lookup per row rather than a scan, so the work a page costs
    grows with the page and not with its square (NFR-02)."""

    def __init__(self, change_ids: Collection[uuid.UUID], order: list[str]) -> None:
        links = list(
            ChangeTerm.objects.filter(change_id__in=change_ids).select_related("term__dimension", "flag", *keys.CURATION_AGENTS)
        )
        flag_refs = vocabulary_refs(FlagLabel, (link.flag for link in links if link.flag is not None), order)
        term_refs = vocabulary_refs(
            TaxonomyTermLabel, (link.term for link in links if link.term is not None), order, field="term"
        )
        self.flags: dict[uuid.UUID, list[WatchFact]] = {}
        self.terms: dict[uuid.UUID, list[WatchFact]] = {}
        # What the footprint is matched against: the change's taxonomy terms by dimension,
        # exactly as `apps/cases/reading.py` reads them for a case. A flag is a
        # `change_term` row too and never scopes the change.
        self.scope: dict[uuid.UUID, dict[str, set[str]]] = {}
        self.unconfirmed: dict[uuid.UUID, int] = {}
        for link in links:
            confidence = None if link.confidence is None else float(link.confidence)
            if link.flag_id is not None:
                fact = WatchFact(
                    ref=flag_refs[link.flag_id], confidence=confidence, suggested=link.suggested, **keys.provenance(link)
                )
                self.flags.setdefault(link.change_id, []).append(fact)
            elif link.term is not None:
                fact = WatchFact(
                    ref=term_refs[link.term.id], confidence=confidence, suggested=link.suggested, **keys.provenance(link)
                )
                self.terms.setdefault(link.change_id, []).append(fact)
                self.scope.setdefault(link.change_id, {}).setdefault(link.term.dimension.key, set()).add(link.term.key)
            if link.suggested:
                self.unconfirmed[link.change_id] = self.unconfirmed.get(link.change_id, 0) + 1


class _Scopes:
    """The footprint verdict of a page of changes and, beside it, the market this bank
    watches that each one comes from, from one query for the jurisdictions the page's
    authorities reach (FP-04). The watched market's term came with the page itself
    (`_with_own_case()`).

    A change's scope is its own terms plus those jurisdictions, as `_scope_term_ids()` hands
    them to the database. `market` is set only where watching adds the row: outside the
    footprint, inside it on the change's own terms, and reaching a watched market."""

    def __init__(self, tenant: Tenant, page: Sequence[RegulatoryChange], classification: _Classification) -> None:
        footprint, restricting = matching.footprint_of(tenant.id), matching.restricting_dimensions()
        # Read by name, because a query annotation is not a field of the model.
        jurisdiction = {change.id: getattr(change, _JURISDICTION) for change in page}
        reached = jurisdiction_scopes(set(jurisdiction.values()) - {None})
        self.inside: dict[uuid.UUID, bool] = {}
        self.market: dict[uuid.UUID, TaxonomyTerm] = {}
        for change in page:
            own = classification.scope.get(change.id, {})
            scope = {dimension: set(keys) for dimension, keys in own.items()}
            terms = reached.get(jurisdiction[change.id], [])
            for term in terms:
                scope.setdefault(term.dimension.key, set()).add(term.key)
            self.inside[change.id] = not outside_reasons(scope, footprint, restricting)
            if self.inside[change.id] or outside_reasons(own, footprint, restricting):
                continue
            market = next((term for term in terms if term.id == getattr(change, _WATCHED_TERM)), None)
            if market is not None:
                self.market[change.id] = market


def _change_type_fact(change: RegulatoryChange, refs: Mapping[uuid.UUID, LibraryRef]) -> WatchFact:
    """The change's type as a fact with its provenance, read off the type's own columns
    (watch 0002, D-74) exactly as a flag's are read off its link. The change must be loaded
    with `keys.CHANGE_TYPE_AGENTS`, so naming the agents costs no query."""
    confidence = change.change_type_confidence
    return WatchFact(
        ref=refs[change.change_type_id],
        confidence=None if confidence is None else float(confidence),
        suggested=change.change_type_suggested,
        **keys.provenance(change, "change_type_"),
    )


class _SuggestedLinks:
    """The obligation links of a page of changes, with the title, instrument and reference
    label a reader needs, from two queries and grouped by change once.

    Most confident first, which is `ChangeObligation.Meta`'s own order: a link nobody
    scored — a person's own — sorts after the agent's scored ones rather than ahead of
    them."""

    def __init__(self, change_ids: Collection[uuid.UUID], order: list[str]) -> None:
        links = list(
            ChangeObligation.objects.filter(change_id__in=change_ids).select_related("obligation__instrument", *keys.CURATION_AGENTS)
        )
        titles: dict[uuid.UUID, list[ObligationTitle]] = {}
        for title in ObligationTitle.objects.filter(obligation_id__in={link.obligation_id for link in links}):
            titles.setdefault(title.obligation_id, []).append(title)
        self.links: dict[uuid.UUID, list[WatchObligationLink]] = {}
        self.unconfirmed: dict[uuid.UUID, int] = {}
        for link in links:
            text = localized(titles.get(link.obligation_id, []), order)
            self.links.setdefault(link.change_id, []).append(
                WatchObligationLink(
                    obligation_id=link.obligation_id,
                    title="" if text is None else text.text,
                    instrument_short_name=link.obligation.instrument.short_name,
                    ref_label=link.obligation.ref_label,
                    origin=cast(Origin, link.origin),
                    confidence=None if link.confidence is None else float(link.confidence),
                    confirmed=link.confirmed_at is not None,
                    **keys.provenance(link),
                )
            )
            if link.confirmed_at is None:
                self.unconfirmed[link.change_id] = self.unconfirmed.get(link.change_id, 0) + 1


def _week_window(week: datetime.date, tenant: Tenant) -> tuple[datetime.datetime, datetime.datetime]:
    """The ISO week `week` falls in, Monday to Sunday, in the bank's own time zone. A
    sighting is a timestamp, which is why the week needs a zone to be resolved at all; a
    key date is a plain date and needs none."""
    zone = ZoneInfo(tenant.timezone)
    monday = week - datetime.timedelta(days=week.weekday())
    start = datetime.datetime.combine(monday, datetime.time.min, tzinfo=zone)
    return start, start + datetime.timedelta(days=7)


# ---------------------------------------------------------------------------------------
# The reader's own case, joined once
# ---------------------------------------------------------------------------------------
def _with_own_case(tenant: Tenant) -> QuerySet[RegulatoryChange]:
    """Every change with this bank's own case beside it, in one left join. The condition
    sits on the JOIN, so a change the bank has no case for is still a row; the tenant is
    named as well as left to row-level security, which is the belt to the policy's
    braces.

    Beside the case, where the change's jurisdiction comes from (its authority's) and the
    first term it reaches that mirrors a market this bank watches, or null (FP-04)."""
    watched = WatchedMarket.objects.filter(tenant=tenant).values("jurisdiction")
    queryset: QuerySet[RegulatoryChange] = RegulatoryChange.objects.annotate(
        own_case=FilteredRelation("cases", condition=Q(cases__tenant=tenant)),
        **{
            _JURISDICTION: F("authority__jurisdiction"),
            _WATCHED_TERM: Subquery(
                TaxonomyTerm.objects.filter(reaching(OuterRef("authority__jurisdiction_id")), jurisdiction__in=watched)
                .order_by("sort_order", "key")
                .values("id")[:1]
            ),
        },
    ).annotate(**{f"case_{name}": F(f"own_case__{path}") for name, path in _CASE_COLUMNS.items()})
    return queryset


# ---------------------------------------------------------------------------------------
# GET /changes: one bank's feed
# ---------------------------------------------------------------------------------------
def _feed_queryset(tenant: Tenant, query: WatchChangeQuery) -> QuerySet[RegulatoryChange]:
    """The feed's rows, with every filter applied in the database. The order is the
    model's own (`RegulatoryChange.Meta`): the key date, then when the reform was first
    seen, both newest first, with the row id as a stable tiebreak and no key date last."""
    queryset = _with_own_case(tenant)
    if query.tab != "all":
        queryset = queryset.filter(Q(own_case__status=query.tab))
    if query.status:
        queryset = queryset.filter(status=query.status)
    if query.urgency:
        # This bank's own urgency where it has a case, the library's suggestion otherwise,
        # so a filter reads the same value the row shows.
        queryset = queryset.filter(
            Q(own_case__urgency__key=query.urgency)
            | Q(own_case__id__isnull=True, suggested_urgency__key=query.urgency)
        )
    if query.change_type:
        queryset = queryset.filter(change_type__key=query.change_type)
    if query.owner_id:
        queryset = queryset.filter(Q(own_case__owner=query.owner_id))
    if query.term_id:
        # A change matches when it carries any one of them. `Exists` rather than a join, so
        # a change carrying two of the wanted terms is still one row.
        queryset = queryset.filter(Exists(ChangeTerm.objects.filter(change=OuterRef("pk"), term_id__in=query.term_id)))
    if query.week:
        seen_from, seen_until = _week_window(query.week, tenant)
        queryset = queryset.filter(first_seen_at__gte=seen_from, first_seen_at__lt=seen_until)
    if query.unconfirmed_so_what is not None:
        queryset = queryset.filter(Q(own_case__so_what_confirmed=not query.unconfirmed_so_what))
    if query.q:
        queryset = queryset.filter(Q(title__icontains=query.q) | Q(summary__icontains=query.q))
    if query.footprint == "in":
        queryset = queryset.filter(_in_footprint(tenant, _scope_term_ids()))
    elif query.footprint == "watched":
        # FP-04's "Markets we watch": only what watching adds, the rule `_Scopes` gives
        # each row its market by. Outside the footprint, inside it on the change's own terms,
        # and from an authority whose jurisdiction reaches a market this bank watches.
        queryset = queryset.filter(Q(**{f"{_WATCHED_TERM}__isnull": False}), _in_footprint(tenant, _own_term_ids()))
        queryset = queryset.exclude(_in_footprint(tenant, _scope_term_ids()))
    return queryset


def _case_columns(change: RegulatoryChange) -> dict[str, Any]:
    """The reader's own case as the left join annotated it onto the change row. Read by
    name, because a query annotation is not a field of the model."""
    return {column: getattr(change, f"case_{column}") for column in _CASE_COLUMNS}


def _case_of(
    case: Mapping[str, Any],
    urgencies: Mapping[uuid.UUID, LibraryRef],
    decisions: Mapping[uuid.UUID, list[WatchCaseObligationDecision]],
) -> WatchChangeCase | None:
    """This bank's case, built from those columns. None where the bank has none: a change
    reaches the library before any bank has looked at it."""
    if case["id"] is None:
        return None
    return WatchChangeCase(
        id=case["id"],
        category=cast(CaseCategory, case["status"]),
        urgency=None if case["urgency"] is None else urgencies[case["urgency"]],
        urgency_confirmed=case["urgency_confirmed"],
        owner_id=case["owner"],
        footprint_match=case["footprint_match"],
        so_what_text=case["so_what_text"] or None,
        so_what_confirmed=case["so_what_confirmed"],
        so_what_confirmed_at=case["so_what_confirmed_at"],
        so_what_confirmed_by_name=case["so_what_confirmed_by_name"],
        obligation_decisions=decisions.get(case["id"], []),
        # The state machine that would move a case is chunk 9, so nothing is offered yet.
        # Empty means "no move is offered here", never "the case is stuck".
        allowed_transitions=[],
    )


def _decisions_by_case(case_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, list[WatchCaseObligationDecision]]:
    """What this bank decided about the suggested links, its own rows under row-level
    security, with the deciding person's name joined in. One query for the page."""
    by_case: dict[uuid.UUID, list[WatchCaseObligationDecision]] = {}
    rows = CaseObligationLink.objects.filter(case_id__in=case_ids).annotate(decided_by_name=F("decided_by__name"))
    for row in rows:
        by_case.setdefault(row.case_id, []).append(
            WatchCaseObligationDecision(
                obligation_id=row.obligation_id,
                decision=cast(CaseLinkDecision, row.decision),
                decided_at=row.decided_at,
                decided_by_name=row.decided_by_name,
            )
        )
    return by_case


def change_rows(tenant: Tenant, order: list[str], change_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, WatchChangeRow]:
    """The feed's own row for each of `change_ids`, keyed by change id so the caller keeps
    its own order (WAT-02, HOM-01, HOM-02).

    Today's lead card and the weekly briefing show a change as the feed shows it, and one
    shape has one owner (API_DOCUMENTATION §4b): they choose *which* changes by their own
    rule and ask here for the rows, rather than building a second feed row that could drift
    from this one. A change the caller cannot see is simply absent from the answer, which is
    row-level security doing its job rather than a filter in Python.

    The same fixed number of queries whatever is asked for, exactly as a page of the feed
    costs (NFR-02).
    """
    page = list(_with_own_case(tenant).select_related(*_CHANGE_JOINS).filter(id__in=change_ids))
    return {row.id: row for row in _feed_rows(tenant, page, order)}


def list_changes(tenant: Tenant, order: list[str], query: WatchChangeQuery) -> WatchChangePage:
    """`GET /changes`: the reforms that reach this bank, with its own case beside each one
    (WAT-02, WAT-03, CAS-01, FP-03). The same number of queries whatever the page size."""
    queryset = _feed_queryset(tenant, query)
    total = queryset.count()
    page = list(queryset.select_related(*_CHANGE_JOINS)[query.offset : query.offset + query.limit])

    return WatchChangePage(items=_feed_rows(tenant, page, order), total=total)


def _feed_rows(tenant: Tenant, page: Sequence[RegulatoryChange], order: list[str]) -> list[WatchChangeRow]:
    """One page of feed rows, each the library's facts about a reform beside the reader's
    own case. The same number of queries for the page, whatever its size (NFR-02): one more
    for the markets' labels when a row comes from a watched market."""
    ids = [change.id for change in page]
    classification = _Classification(ids, order)
    scopes = _Scopes(tenant, page, classification)
    markets = vocabulary_refs(TaxonomyTermLabel, scopes.market.values(), order, field="term")
    cases = [_case_columns(change) for change in page]
    case_ids = [case["id"] for case in cases if case["id"] is not None]
    urgencies = urgency_refs(
        {change.suggested_urgency_id for change in page if change.suggested_urgency_id is not None}
        | {case["urgency"] for case in cases if case["urgency"] is not None},
        order,
    )
    type_refs = vocabulary_refs(ChangeTypeLabel, (change.change_type for change in page), order)
    decisions = _decisions_by_case(case_ids)

    return [
        WatchChangeRow(
            id=change.id,
            stable_key=change.stable_key,
            title=change.title,
            change_type=_change_type_fact(change, type_refs),
            authority_label=change.authority_label,
            authority_id=change.authority_id,
            published_on=change.published_on,
            published_precision=change.published_precision,
            key_date=change.key_date,
            key_date_precision=change.key_date_precision,
            key_date_label=change.key_date_label or None,
            status=cast(ChangeStatus, change.status),
            flags=classification.flags.get(change.id, []),
            terms=classification.terms.get(change.id, []),
            suggested_urgency=None if change.suggested_urgency_id is None else urgencies[change.suggested_urgency_id],
            in_footprint=scopes.inside[change.id],
            market=markets[scopes.market[change.id].id] if change.id in scopes.market else None,
            first_seen_at=change.first_seen_at,
            case=_case_of(case, urgencies, decisions),
        )
        for change, case in zip(page, cases, strict=True)
    ]


# ---------------------------------------------------------------------------------------
# GET /console/changes: the library editor's queue
# ---------------------------------------------------------------------------------------
def _console_queryset(query: WatchConsoleChangeQuery) -> QuerySet[RegulatoryChange]:
    """The queue, newest sighting first. No case is joined: a console session belongs to no
    bank (NFR-01)."""
    queryset = RegulatoryChange.objects.all()
    if query.confirmed == "false":
        queryset = queryset.filter(
            # The type, the flags, the scope terms and the links each say on their own
            # columns whether anybody has stood behind them yet (D-74).
            Q(change_type_suggested=True)
            | Exists(ChangeTerm.objects.filter(change=OuterRef("pk"), suggested=True))
            | Exists(ChangeObligation.objects.filter(change=OuterRef("pk"), confirmed_at__isnull=True))
        )
    if query.authority_id:
        queryset = queryset.filter(authority_id=query.authority_id)
    if query.q:
        queryset = queryset.filter(Q(title__icontains=query.q) | Q(summary__icontains=query.q))
    return queryset.order_by("-first_seen_at", "id")


def list_console_changes(order: list[str], query: WatchConsoleChangeQuery) -> WatchConsoleChangePage:
    """`GET /console/changes`: the changes carrying a fact nobody has confirmed
    (WAT-02, WAT-03, WAT-04, PRO-01)."""
    queryset = _console_queryset(query)
    total = queryset.count()
    page = list(queryset.select_related(*_CHANGE_JOINS)[query.offset : query.offset + query.limit])
    return WatchConsoleChangePage(items=_console_rows(page, order), total=total)


def console_change(order: list[str], change_id: uuid.UUID) -> WatchConsoleChangeRow:
    """One change as the console's queue shows it, which is what a curation confirmation
    answers: the facts with who suggested and who confirmed each (D-74). No case is joined,
    because the confirmer is a platform key or a console session and belongs to no bank."""
    change = RegulatoryChange.objects.select_related(*_CHANGE_JOINS).get(pk=change_id)
    return _console_rows([change], order)[0]


def _console_rows(page: Sequence[RegulatoryChange], order: list[str]) -> list[WatchConsoleChangeRow]:
    """The console's rows for a page of changes, from the same fixed number of queries
    whatever its size (NFR-02)."""
    ids = [change.id for change in page]
    classification = _Classification(ids, order)
    links = _SuggestedLinks(ids, order)
    type_refs = vocabulary_refs(ChangeTypeLabel, (change.change_type for change in page), order)
    return [
        WatchConsoleChangeRow(
            id=change.id,
            stable_key=change.stable_key,
            title=change.title,
            change_type=_change_type_fact(change, type_refs),
            authority_label=change.authority_label,
            authority_id=change.authority_id,
            published_on=change.published_on,
            published_precision=change.published_precision,
            status=cast(ChangeStatus, change.status),
            flags=classification.flags.get(change.id, []),
            terms=classification.terms.get(change.id, []),
            obligations=links.links.get(change.id, []),
            unconfirmed_count=(
                int(change.change_type_suggested)
                + classification.unconfirmed.get(change.id, 0)
                + links.unconfirmed.get(change.id, 0)
            ),
            first_seen_at=change.first_seen_at,
        )
        for change in page
    ]


# ---------------------------------------------------------------------------------------
# GET /changes/{changeId}: the whole change page
# ---------------------------------------------------------------------------------------
def get_change(tenant: Tenant, order: list[str], change_id: uuid.UUID) -> WatchChangeDetail:
    """`GET /changes/{changeId}`: the reform's sourced facts — its type, its flags, its
    scope, its timeline, the pages it was found on and the obligations it affects — and
    beside them the reader's own bank's case (WAT-02, WAT-03, WAT-04, CAS-01).

    A change nobody registered and a change the caller cannot see answer the same 404, so
    no id can be probed for."""
    change = _with_own_case(tenant).select_related(*_CHANGE_JOINS).filter(pk=change_id).first()  # ordering: pk lookup, at most one row
    if change is None:
        raise ValidationError(NOT_FOUND, code="not_found")

    classification = _Classification([change.id], order)
    case = _case_columns(change)
    urgencies = urgency_refs(
        {value for value in (change.suggested_urgency_id, case["urgency"]) if value is not None}, order
    )
    type_refs = vocabulary_refs(ChangeTypeLabel, [change.change_type], order)
    links = _SuggestedLinks([change.id], order)
    documents = list(change.documents.all())
    return WatchChangeDetail(
        id=change.id,
        stable_key=change.stable_key,
        title=change.title,
        change_type=type_refs[change.change_type_id],
        change_type_fact=_change_type_fact(change, type_refs),
        authority_label=change.authority_label,
        authority_id=change.authority_id,
        published_on=change.published_on,
        published_precision=change.published_precision,
        summary=change.summary,
        so_what_draft=change.so_what_draft or None,
        suggested_urgency=None if change.suggested_urgency_id is None else urgencies[change.suggested_urgency_id],
        key_date=change.key_date,
        key_date_precision=change.key_date_precision,
        key_date_label=change.key_date_label or None,
        recurrence_rule=change.recurrence_rule or None,
        # The same facts the feed row carries, provenance and all. The change page is where
        # a person judges the change, so an individual flag or scope term an agent
        # suggested has to read as a suggestion here too (WAT-03).
        flags=classification.flags.get(change.id, []),
        source_label=change.source_label,
        source_url=change.source_url,
        status=cast(ChangeStatus, change.status),
        terms=classification.terms.get(change.id, []),
        events=[
            WatchChangeEvent(
                id=event.id,
                label=event.label,
                event_date=event.event_date,
                date_precision=cast(DatePrecision, event.date_precision),
                occurred=event.occurred,
                sort_order=event.sort_order,
                source_url=event.source_url or None,
            )
            for event in change.events.all()
        ],
        documents=[
            WatchChangeDocument(
                id=document.id,
                url=document.url,
                title=document.title or None,
                publisher=document.publisher or None,
                fetched_at=document.fetched_at,
                is_primary=document.is_primary,
                is_duplicate=document.is_duplicate,
                risk_flags=document.risk_flags,
            )
            for document in documents
        ],
        duplicate_count=sum(1 for document in documents if document.is_duplicate),
        obligations=links.links.get(change.id, []),
        origin=cast(Origin, change.origin),
        model=change.model or None,
        agent_run_id=change.agent_run_id,
        first_seen_at=change.first_seen_at,
        in_footprint=_Scopes(tenant, [change], classification).inside[change.id],
        case=_case_of(case, urgencies, _decisions_by_case([case["id"]] if case["id"] is not None else [])),
    )


# ---------------------------------------------------------------------------------------
# GET /obligations/{obligationId}/changes: the related-changes panel
# ---------------------------------------------------------------------------------------
def list_obligation_changes(tenant: Tenant, order: list[str], obligation_id: uuid.UUID, page_query: PageQuery) -> WatchObligationChangePage:
    """`GET /obligations/{obligationId}/changes`: the changes linked to one obligation,
    the library editor's confirmed links first, and how many of them still have work open
    for this bank (WAT-04, WAT-S6).

    `openCount` is counted by the database over every linked change and never over the
    page, so paging cannot change it. It counts this bank's own cases that are neither
    closed nor dismissed: it says the work is open, never that the bank does not comply,
    which is a separate fact in the register (REG-02).

    A change this bank removed the link to — "not related to us" on its own case — is left
    out of the items, the total and the open count alike. Its removal is this bank's alone:
    the library link stays, and another bank still sees the change (WAT-04, ruling C)."""
    obligation = obligation_subject(obligation_id)
    removed = CaseObligationLink.objects.filter(
        tenant=tenant, obligation=obligation, decision=CaseLinkDecisionKind.REMOVED.value
    )
    queryset = (
        _with_own_case(tenant)
        .annotate(link=FilteredRelation("obligation_links", condition=Q(obligation_links__obligation=obligation)))
        .filter(link__obligation=obligation)
        .exclude(Exists(removed.filter(case_id=OuterRef("case_id"))))
        # A link a library editor confirmed comes first; the rest keep the feed's order.
        .annotate(link_confirmed=ExpressionWrapper(Q(link__confirmed_at__isnull=False), output_field=BooleanField()))
        .order_by("-link_confirmed", F("key_date").desc(nulls_last=True), "-first_seen_at", "id")
    )
    total = queryset.count()
    open_count = (
        ChangeCase.objects.filter(tenant=tenant, change__obligation_links__obligation=obligation)
        .exclude(status__in=(CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value))
        .exclude(Exists(removed.filter(case_id=OuterRef("pk"))))
        .count()
    )
    page = list(queryset.select_related(*_CHANGE_JOINS)[page_query.offset : page_query.offset + page_query.limit])
    return WatchObligationChangePage(items=_feed_rows(tenant, page, order), total=total, open_count=open_count)
