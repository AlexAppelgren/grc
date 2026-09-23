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
  else. A date that has passed leaves the roadmap and stays on the change itself.

R1 fills the regulatory branch alone. `internal` is a real answer and not a refusal: the
branches that produce the bank's own deadlines read tables this release does not have, and
they arrive with the register (chunk 8) and the case workflow (chunk 9). What the screen
draws its quarter roster from is computed here as well, because a quarter near a year
boundary is the bank's own question: two banks an hour apart can be in two quarters, and
each reads the one it is in.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection, Iterable, Sequence
from typing import cast

from django.db.models import QuerySet

from apps.cases.models import ChangeCase
from apps.home.schemas import (
    HomeRoadmap,
    HomeRoadmapItem,
    HomeRoadmapQuery,
    RoadmapItemKind,
    RoadmapItemType,
)
from apps.library.models import DatePrecision, ObligationTitle
from apps.library.reading import localized, today_for
from apps.library.schemas import LibraryRef
from apps.shared.models import Tenant
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import keys
from apps.watch.models import ChangeObligation
from apps.watch.reading import urgency_refs
from apps.watch.schemas import CaseCategory, Origin, WatchObligationLink
from apps.watch.schemas import DatePrecision as Precision

# What this release puts on the roadmap: a regulatory change's own key date. Both are
# tier-one kinds (apps/shared/kinds.py, apps/home/schemas.py); the screen picks its pill
# from the first and the calendar builder its summary line from the second.
ITEM_KIND: RoadmapItemKind = "regulatory"
ITEM_TYPE: RoadmapItemType = "change_date"

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
def _cases(tenant: Tenant, query: HomeRoadmapQuery) -> QuerySet[ChangeCase]:
    """The bank's open work on a dated change inside its regulatory scope, earliest date
    first with the case id as a stable tiebreak — so two dates on one day never swap
    between two reads.

    The window starts at the bank's own today even when `from` is earlier: the roadmap
    holds no item whose date has gone, so an earlier `from` widens nothing rather than
    reopening the past.
    """
    today = today_for(tenant)
    since = today if query.date_from is None else max(today, query.date_from)
    rows = (
        ChangeCase.objects.select_related("change", "urgency")
        .filter(
            footprint_match=True,
            change__key_date__gte=since,
        )
        .exclude(status__in=FINISHED)
    )
    if query.date_to is not None:
        rows = rows.filter(change__key_date__lte=query.date_to)
    return rows.order_by("change__key_date", "id")


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


def _quarters(items: Iterable[HomeRoadmapItem]) -> list[str]:
    """The quarter keys present, in date order and each once. The items are already in date
    order, so the roster follows them and never shows an empty heading."""
    return list(dict.fromkeys(item.quarter for item in items))


# ---------------------------------------------------------------------------------------
# The three reads (chunk 6 ruling 5: these are the only roadmap queries there are)
# ---------------------------------------------------------------------------------------
def roadmap_items(tenant: Tenant, order: list[str], query: HomeRoadmapQuery) -> HomeRoadmap:
    """`GET /roadmap`: every dated change the bank has open work on inside the window the
    filters name, with the quarter keys the screen draws its roster from.

    `kind=internal` answers an empty roadmap with a 200 and never a 422: the filter is real
    and the branches behind it have not shipped. An empty answer means nothing is dated
    ahead, not that something failed.
    """
    if query.kind == "internal":
        return HomeRoadmap(items=[], quarters=[])
    items = _items(list(_cases(tenant, query)), order)
    return HomeRoadmap(items=items, quarters=_quarters(items))


def coming_up(tenant: Tenant, order: list[str], limit: int) -> tuple[list[HomeRoadmapItem], int]:
    """The first `limit` roadmap items and how many there are in all, for Today's "Coming
    up" panel and the count beside it (HOM-01).

    The same rows as `GET /roadmap` with no filter, from the same query, so the panel and
    the page can never disagree about what is next. `limit` is the caller's, because the
    length of Today's list is Today's decision (`HOME_COMING_UP_ITEMS`).
    """
    cases = _cases(tenant, HomeRoadmapQuery())
    return _items(list(cases[:limit]), order), cases.count()


def calendar_items(tenant: Tenant, order: list[str]) -> list[tuple[str, HomeRoadmapItem]]:
    """What a calendar subscription carries (HOM-04, ADR 0045, AC-TEN1): the roadmap's own
    rows, narrowed twice, each beside its change's stable key, which is the event's UID.

    - **The dates the outside world set, and no other.** The query names
      `kind=regulatory` and this reads `_cases()`, the regulatory branch, alone. The bank's
      own deadlines — a certificate's expiry, an action falling due — join the roadmap in
      branches of their own (chunks 8 and 9) that this never calls, so none of them reaches
      a calendar a provider outside the bank can read.
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
