"""Watch builders for tests (playbook 8.1): the source registry and its coverage log, a
change with its timeline, its pages, its classification and its obligation links, plus the
two assertions every watch test repeats.

Every builder writes inside `watch_write()`, the one door to the seven watch tables
(apps/watch/write.py). This module may open it because the library fence exempts
`testing.py` modules (apps/shared/tests_library_fence.py), exactly as it exempts
`apps/library/testing.py`. That is also why these builders are not in
`apps/shared/factories.py`: that module is a production module to the fence guard, so it
may neither open the door nor name a library model beside a write.

The values are the prototype's (`backend/apps/library/fixtures/prototype_data.json`) —
Finansinspektionen, fi.se, the research-payments reform — so a test reads data a person
would recognise, and they are deterministic: a key gets a suffix from a counter, never
from `random`, and every date is a fixed date rather than one derived from "now".

Nothing here creates a case. `c5-cases-creation` owns that, and a fixture that quietly
made one would hide the very thing CAS-01 has to prove.
"""

from __future__ import annotations

import datetime
import zlib
import itertools
from collections.abc import Iterable, Sequence
from typing import Any

from django.db import transaction

from apps.agents.models import AgentRun
from apps.library.models import Authority, DatePrecision, Obligation, SubjectType
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals.models import OriginType
from apps.taxonomy.models import ChangeType, Flag, SourceKind, TaxonomyTerm, Urgency
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.watch.models import (
    ChangeDocument,
    ChangeEvent,
    ChangeObligation,
    ChangeStatus,
    ChangeTerm,
    CheckFrequency,
    CheckStatus,
    RegulatoryChange,
    Source,
    SourceCheck,
    SourceCheckKind,
)
from apps.shared import tenancy
from apps.watch.write import watch_write

REASON = "test builder"

# A fixed anchor rather than `timezone.now()`, so a fixture cannot drift into or out of a
# window as the clock moves (playbook 8.3). It is the prototype's own anchor week.
ANCHOR = datetime.datetime(2026, 9, 16, 6, 2, tzinfo=datetime.UTC)


def _sighted_at(stable_key: str) -> datetime.datetime:
    """A sighting time of this change's own, derived from its key.

    Every change used to be sighted at `ANCHOR` exactly, and the feed orders by sighting
    time and then by id. An id is a random uuid, so which change landed on page one changed
    from run to run, and a query whose `IN` clause is empty does not execute: the console's
    query-count test counted 16 here and 15 in CI, for a page holding a different change
    (2026-09-21). Derived from the key rather than a counter, so the same key is the same
    moment in every run, on every machine, whatever order the rows were built in."""
    return ANCHOR - datetime.timedelta(seconds=zlib.crc32(stable_key.encode()) % 3600)
PUBLISHED_ON = datetime.date(2026, 9, 15)
KEY_DATE = datetime.date(2026, 10, 1)

_counter = itertools.count(1)


def seed_watch_reference() -> None:
    """The vocabulary and reference rows every chunk 5 test needs — languages,
    jurisdictions, the library vocabularies (change types, flags, source kinds, urgency
    levels), the taxonomy terms including the regimes, and the authorities — through the
    reference seeds themselves, so a test never invents a key the product does not have.
    Idempotent: call it from `setUpTestData` in every watch, case or agent test."""
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()
    seed_authorities()


def term(ref: str) -> TaxonomyTerm:
    """The taxonomy term `dimension:key`, addressed exactly as the API addresses it."""
    dimension, _, key = ref.partition(":")
    return TaxonomyTerm.objects.select_related("dimension").get(dimension__key=dimension, key=key)


# ---------------------------------------------------------------------------------------
# WAT-01: the registry and the coverage log
# ---------------------------------------------------------------------------------------
def source(
    *,
    name: str | None = None,
    kind: str = "authority_site",
    authority: str | None = "fi",
    url: str = "https://www.fi.se/",
    check_frequency: CheckFrequency = CheckFrequency.WEEKLY,
    active: bool = True,
) -> Source:
    """A registered source. A shared source is written with no tenant activated, which is
    the only session the `source` write rule accepts a library row from (WAT-06, H15)."""
    with watch_write(REASON):
        return Source.objects.create(
            name=name or f"fi.se {next(_counter)}",
            url=url,
            kind=SourceKind.objects.get(key=kind),
            authority=None if authority is None else Authority.objects.get(key=authority),
            check_frequency=check_frequency.value,
            active=active,
        )


def source_check(
    row: Source,
    *,
    run: AgentRun | None = None,
    status: CheckStatus = CheckStatus.OK,
    items_found: int = 3,
    error: str = "",
    kind: SourceCheckKind = SourceCheckKind.SWEEP,
    subject: Obligation | None = None,
    checked_at: datetime.datetime | None = None,
) -> SourceCheck:
    """One line of the coverage log. A failed check carries an error and no items; a
    re-check names the library record it re-checked, which a sweep never does."""
    with watch_write(REASON):
        return SourceCheck.objects.create(
            source=row,
            agent_run=run,
            checked_at=checked_at or ANCHOR,
            status=status.value,
            items_found=0 if status is CheckStatus.FAILED else items_found,
            error=error,
            kind=kind.value,
            subject_type="" if subject is None else SubjectType.OBLIGATION.value,
            subject_id=None if subject is None else subject.id,
        )


# ---------------------------------------------------------------------------------------
# WAT-02, WAT-03, WAT-04: the change and everything on it
# ---------------------------------------------------------------------------------------
def change(
    *,
    stable_key: str | None = None,
    title: str = "FI adopts amended rules on paying for investment research",
    change_type: str = "adopted",
    authority: str | None = "fi",
    authority_label: str = "Finansinspektionen",
    urgency: str | None = "act_now",
    key_date: datetime.date | None = KEY_DATE,
    key_date_label: str = "In force",
    status: ChangeStatus = ChangeStatus.ACTIVE,
    run: AgentRun | None = None,
    so_what_draft: str = "",
    first_seen_at: datetime.datetime | None = None,
) -> RegulatoryChange:
    """One reform, as the prototype's lead change reads. `stable_key` is the merge key, so
    two builds in one test get two keys unless a test names one on purpose (AC-WAT1). The
    type is a suggestion by `run`'s agent and key, as the registration copies them (D-74)."""
    key = stable_key or f"chg-fi-2026-research-payments-{next(_counter)}"
    with watch_write(REASON):
        return RegulatoryChange.objects.create(
            stable_key=key,
            title=title,
            change_type=ChangeType.objects.get(key=change_type),
            change_type_suggested_by_agent_id=None if run is None else run.agent_id,
            change_type_suggested_by_api_key_id=None if run is None else run.api_key_id,
            authority=None if authority is None else Authority.objects.get(key=authority),
            authority_label=authority_label,
            published_on=PUBLISHED_ON,
            published_precision=DatePrecision.DAY.value,
            summary="FI's board decided to amend three regulations in the securities area.",
            so_what_draft=so_what_draft,
            suggested_urgency=None if urgency is None else Urgency.objects.get(key=urgency),
            key_date=key_date,
            key_date_precision=DatePrecision.DAY.value,
            key_date_label=key_date_label,
            source_label="Finansinspektionen",
            source_url="https://www.fi.se/",
            status=status.value,
            origin=OriginType.AGENT.value,
            agent_run=run,
            model="agent pipeline 0.4",
            first_seen_at=first_seen_at or _sighted_at(key),
        )


def event(
    row: RegulatoryChange,
    *,
    label: str = "Consultation closed",
    event_date: datetime.date | None = datetime.date(2026, 6, 1),
    precision: DatePrecision = DatePrecision.DAY,
    occurred: bool = True,
    sort_order: int = 1,
) -> ChangeEvent:
    """One entry of the timeline, with its own precision: a legal date is a plain date and
    the screen never prints a day the source did not state."""
    with watch_write(REASON):
        return ChangeEvent.objects.create(
            change=row,
            label=label,
            event_date=event_date,
            date_precision=precision.value,
            occurred=occurred,
            sort_order=sort_order,
        )


def document(
    row: RegulatoryChange,
    *,
    url: str = "https://www.fi.se/en/published/news/2026/reporting/",
    title: str = "FI adopts amended rules on paying for investment research",
    is_primary: bool = True,
    is_duplicate: bool = False,
    risk_flags: Sequence[str] = (),
    content_hash: str = "",
) -> ChangeDocument:
    """A fetched page. The text itself is never stored here: the address, the hash and what
    the injection screen found (AGT-07, WAT-07)."""
    with watch_write(REASON):
        return ChangeDocument.objects.create(
            change=row,
            url=url,
            title=title,
            publisher="Finansinspektionen",
            fetched_at=ANCHOR,
            content_hash=content_hash,
            is_primary=is_primary,
            is_duplicate=is_duplicate,
            risk_flags=list(risk_flags),
        )


def term_link(
    row: RegulatoryChange,
    *,
    term_ref: str | None = None,
    flag_key: str | None = None,
    confidence: float | None = 0.74,
    suggested: bool = True,
) -> ChangeTerm:
    """A flag or a scope term on a change — exactly one of the two, never a `text[]`
    (INPUT_DELTAS §1). It arrives as a suggestion with the agent's confidence and stays one
    until it is confirmed (WAT-03), suggested by the agent and key of the change's own run,
    as the registration copies them (D-74)."""
    if (term_ref is None) == (flag_key is None):
        raise ValueError("A change term link names exactly one of a taxonomy term or a flag.")
    with watch_write(REASON):
        return ChangeTerm.objects.create(
            change=row,
            term=None if term_ref is None else term(term_ref),
            flag=None if flag_key is None else Flag.objects.get(key=flag_key),
            confidence=confidence,
            suggested=suggested,
            suggested_by_id=row.change_type_suggested_by_id,
            suggested_by_agent_id=row.change_type_suggested_by_agent_id,
            suggested_by_api_key_id=row.change_type_suggested_by_api_key_id,
        )


def obligation_link(
    row: RegulatoryChange,
    obligation: Obligation,
    *,
    origin: OriginType = OriginType.AGENT,
    confidence: float | None = 0.82,
) -> ChangeObligation:
    """An obligation the change affects, as the agent of the change's own run suggested it.
    A bank's own decision about the link lives on its case and never here (WAT-04, ruling
    C). Written in the obligation's zone, as its child (library 0012): the shared library's
    from a session with no bank, a bank's own record's from that bank."""
    with transaction.atomic(), tenancy.platform_zone(), watch_write(REASON):
        if obligation.owner_tenant_id is not None:
            tenancy.activate(obligation.owner_tenant_id)
        return ChangeObligation.objects.create(
            change=row,
            obligation=obligation,
            origin=origin.value,
            confidence=confidence,
            suggested_by_id=row.change_type_suggested_by_id,
            suggested_by_agent_id=row.change_type_suggested_by_agent_id,
            suggested_by_api_key_id=row.change_type_suggested_by_api_key_id,
        )


def change_with_timeline(
    *,
    terms: Iterable[str] = ("regime:securities",),
    flags: Iterable[str] = ("advice_perimeter",),
    run: AgentRun | None = None,
    **change_fields: Any,  # compliance: allow-kwargs test helper forwarding `change()` fields
) -> RegulatoryChange:
    """The change most chunk 5 tests want: a reform with a two-entry timeline, its primary
    page, a regime term and a flag, every classification still a suggestion. Its scope is
    what a footprint is matched against, which is why the regime is explicit."""
    row = change(run=run, **change_fields)
    event(row, label="Consultation closed", event_date=datetime.date(2026, 6, 1), sort_order=1)
    event(row, label="In force", event_date=KEY_DATE, precision=DatePrecision.DAY, occurred=False, sort_order=2)
    document(row)
    for ref in terms:
        term_link(row, term_ref=ref)
    for key in flags:
        term_link(row, flag_key=key)
    return row


# ---------------------------------------------------------------------------------------
# The two assertions every watch test repeats
# ---------------------------------------------------------------------------------------
def is_a_suggestion(link: ChangeTerm | ChangeObligation) -> bool:
    """True while nobody has confirmed the link: no person, key or agent is named and no
    time is stamped. A `ChangeTerm` also says so on its `suggested` column, and they must
    all agree — the database's check constraint is what makes that true (WAT-03, D-74)."""
    unconfirmed = (
        link.confirmed_by_id is None
        and link.confirmed_by_api_key_id is None
        and link.confirmed_by_agent_id is None
        and link.confirmed_at is None
    )
    if isinstance(link, ChangeTerm):
        return unconfirmed and link.suggested
    return unconfirmed


def cases_per_tenant(row: RegulatoryChange, tenants: Iterable[Any]) -> dict[Any, int]:
    """How many cases each of `tenants` holds for the change, each counted with that
    tenant activated. CAS-01's "exactly one case per bank per change" reads as
    `{tenant: 1 for tenant in tenants}`.

    Counted one tenant at a time on purpose: FORCE ROW LEVEL SECURITY applies to the test
    runner's own connection as well as to cw_app, so a single unactivated count answers
    whatever the last activated tenant could see — which once made a two-bank fixture look
    like a one-bank one. Activating each in turn is the only honest count.

    A watch fixture creates none of these rows: case creation is `c5-cases-creation`'s job
    and CAS-01 has to be proved, not assumed.
    """
    from django.db import transaction

    from apps.cases.models import ChangeCase
    from apps.shared import tenancy

    counts: dict[Any, int] = {}
    for tenant in tenants:
        with transaction.atomic():
            tenancy.activate(tenant.id)
            counts[tenant] = ChangeCase.objects.filter(change=row).count()
    return counts
