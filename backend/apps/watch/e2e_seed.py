"""Watch-zone rows for `seed_e2e` (c6-e2e-seed, c5-seed-watch, WAT-01 to WAT-05, WAT-06,
H15): sources, their coverage checks, regulatory changes and everything a change carries —
its timeline, its pages, its classification and the obligations it affects — idempotent by
natural key and built from the prototype's own data, exactly as `apps/watch/testing.py`
builds them for the backend suite.

Why this exists rather than `apps/shared/e2e_seed.py` writing these rows itself: `source`,
`regulatory_change` and the rest of the seven watch tables are library tables, and the
library fence (`apps/shared/tests_library_fence.py`) restricts a write of one to the watch
pipeline's own steps — registration, curation, the source registry, the So what draft —
through `watch_write()`. This module is the seed's own step, through `write.upsert()`
(`apps/watch/write.py`'s generic natural-key upsert, added for exactly this): `watch_write()`
itself says in its own docstring that the door exists for `c5-seed-watch` and `seed_e2e` to
use it.

Idempotent by the natural keys the rest of the seed already uses: a source by its `name`, a
change by its `stable_key`, an event by its `label` on that change, a document by its `url`
on that change, a term link by its `flag` or `term` on that change, an obligation link by its
`obligation` on that change. `seed_e2e` may run twice against one database (a developer's
own, never a deployed one, `refuse_when_deployed()`), and a second run must find the same
rows rather than doubling them. A source's coverage check is the one exception with no
natural key of its own: this module keeps one sweep check per source (`kind=SWEEP`), updated
to `timezone.now()` on every run, because "the last check happened just now" is the fact a
reseed should keep true and a fixed timestamp would go stale the day after it was written. A
`recheck` check is instead kept one per `(source, subject)`, because it names a record and
not "the last look at this source".
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence

from django.utils import timezone

from apps.agents.models import AgentRun
from apps.library.models import Authority, DatePrecision, Obligation, SubjectType
from apps.proposals.models import OriginType
from apps.taxonomy.models import ChangeType, Flag, SourceKind, TaxonomyTerm, Urgency
from apps.watch import write
from apps.watch.models import (
    ChangeDocument,
    ChangeEvent,
    ChangeObligation,
    ChangeTerm,
    CheckFrequency,
    CheckStatus,
    RegulatoryChange,
    Source,
    SourceCheck,
    SourceCheckKind,
)


def seed_source(
    *,
    name: str,
    active: bool = True,
    kind: str = "authority_site",
    authority: str | None = "fi",
    url: str = "https://www.fi.se/",
    check_frequency: CheckFrequency = CheckFrequency.WEEKLY,
) -> Source:
    """A registered source, shared by every bank (WAT-06): written with no tenant
    activated, which is the only session the `source` write rule accepts one from."""
    return write.upsert(
        Source,
        "seed_e2e",
        lookup={"name": name},
        defaults={
            "url": url,
            "kind": SourceKind.objects.get(key=kind),
            "authority": None if authority is None else Authority.objects.get(key=authority),
            "check_frequency": check_frequency.value,
            "active": active,
        },
    )


def seed_source_check(
    source: Source, *, status: CheckStatus, error: str = "", run: AgentRun | None = None
) -> SourceCheck:
    """The one sweep line this seed keeps for a source, refreshed to "now" on every run so a
    healthy source never reads stale and a failed one always reads recent."""
    return write.upsert(
        SourceCheck,
        "seed_e2e",
        lookup={"source": source, "kind": SourceCheckKind.SWEEP.value},
        defaults={
            "checked_at": timezone.now(),
            "status": status.value,
            "items_found": 0 if status is CheckStatus.FAILED else 1,
            "error": error,
            "agent_run": run,
        },
    )


def seed_recheck(
    source: Source, obligation: Obligation, *, status: CheckStatus = CheckStatus.OK, run: AgentRun | None = None
) -> SourceCheck:
    """One re-check line (AGT-01, item 3): the agent looked again at `obligation`'s source
    and found this. Kept one per `(source, obligation)` rather than refreshed to "now" like a
    sweep, because what matters here is that the log can tell a re-check from a sweep at all
    (`c5-library-recheck`'s own drift path is a later task; this seed gives its coverage log
    a row to find, not the proposal the drift would open)."""
    return write.upsert(
        SourceCheck,
        "seed_e2e",
        lookup={"source": source, "kind": SourceCheckKind.RECHECK.value, "subject_id": obligation.id},
        defaults={
            "checked_at": timezone.now(),
            "status": status.value,
            "items_found": 0,
            "error": "",
            "subject_type": SubjectType.OBLIGATION.value,
            "agent_run": run,
        },
    )


def seed_change(
    *,
    stable_key: str,
    title: str,
    key_date: datetime.date,
    key_date_label: str,
    urgency: str,
    first_seen_at: datetime.datetime,
    so_what_draft: str = "Confirm the affected process before the date falls due.",
    change_type: str = "adopted",
    authority: str | None = "fi",
    authority_label: str = "Finansinspektionen",
    published_on: datetime.date | None = None,
    published_precision: DatePrecision = DatePrecision.DAY,
    key_date_precision: DatePrecision = DatePrecision.DAY,
    source_url: str = "https://www.fi.se/",
    summary: str = "FI's board decided to amend rules in the securities area.",
) -> RegulatoryChange:
    """One reform, merged on `stableKey` exactly as a sweep's retry would merge it
    (AC-WAT1): a second run updates the seed's own row rather than writing a duplicate."""
    return write.upsert(
        RegulatoryChange,
        "seed_e2e",
        lookup={"stable_key": stable_key},
        defaults={
            "title": title,
            "change_type": ChangeType.objects.get(key=change_type),
            "authority": None if authority is None else Authority.objects.get(key=authority),
            "authority_label": authority_label,
            "published_on": published_on or key_date,
            "published_precision": published_precision.value,
            "summary": summary,
            "so_what_draft": so_what_draft,
            "suggested_urgency": Urgency.objects.get(key=urgency),
            "key_date": key_date,
            "key_date_precision": key_date_precision.value,
            "key_date_label": key_date_label,
            "source_label": authority_label,
            "source_url": source_url,
            "status": "active",
            "origin": OriginType.AGENT.value,
            "model": "agent pipeline 0.4",
            "first_seen_at": first_seen_at,
        },
    )


def seed_event(
    change: RegulatoryChange,
    *,
    label: str,
    event_date: datetime.date | None,
    precision: DatePrecision = DatePrecision.DAY,
    occurred: bool = True,
    sort_order: int = 1,
) -> ChangeEvent:
    """One entry of the timeline, kept one per `(change, label)`: a milestone is named by its
    wording on that change, exactly as a registration's own retry is merged (WAT-02)."""
    return write.upsert(
        ChangeEvent,
        "seed_e2e",
        lookup={"change": change, "label": label},
        defaults={
            "event_date": event_date,
            "date_precision": precision.value,
            "occurred": occurred,
            "sort_order": sort_order,
        },
    )


def seed_document(
    change: RegulatoryChange,
    *,
    url: str,
    title: str = "",
    publisher: str = "",
    is_primary: bool = False,
    is_duplicate: bool = False,
    risk_flags: Sequence[str] = (),
    content_hash: str = "",
) -> ChangeDocument:
    """A page the reform was found on, kept one per `(change, url)` (WAT-02, AGT-07)."""
    return write.upsert(
        ChangeDocument,
        "seed_e2e",
        lookup={"change": change, "url": url},
        defaults={
            "title": title,
            "publisher": publisher,
            "fetched_at": timezone.now(),
            "content_hash": content_hash,
            "is_primary": is_primary,
            "is_duplicate": is_duplicate,
            "risk_flags": list(risk_flags),
        },
    )


def seed_flag_link(
    change: RegulatoryChange,
    *,
    flag_key: str,
    confidence: float | None = 0.8,
    confirmed_by_id: uuid.UUID | None = None,
    confirmed_at: datetime.datetime | None = None,
) -> ChangeTerm:
    """A flag on a change, a suggestion until `confirmed_by_id` names a library editor
    (WAT-03). Kept one per `(change, flag)`."""
    suggested = confirmed_by_id is None
    return write.upsert(
        ChangeTerm,
        "seed_e2e",
        lookup={"change": change, "flag": Flag.objects.get(key=flag_key)},
        defaults={
            "confidence": confidence,
            "suggested": suggested,
            "confirmed_by_id": confirmed_by_id,
            "confirmed_at": None if suggested else (confirmed_at or timezone.now()),
        },
    )


def seed_scope_term_link(
    change: RegulatoryChange,
    *,
    term_ref: str,
    confidence: float | None = 0.8,
    confirmed_by_id: uuid.UUID | None = None,
    confirmed_at: datetime.datetime | None = None,
) -> ChangeTerm:
    """A scope term on a change (`dimension:key`), a suggestion until `confirmed_by_id`
    names a library editor (WAT-03). Kept one per `(change, term)`."""
    dimension, _, key = term_ref.partition(":")
    term = TaxonomyTerm.objects.select_related("dimension").get(dimension__key=dimension, key=key)
    suggested = confirmed_by_id is None
    return write.upsert(
        ChangeTerm,
        "seed_e2e",
        lookup={"change": change, "term": term},
        defaults={
            "confidence": confidence,
            "suggested": suggested,
            "confirmed_by_id": confirmed_by_id,
            "confirmed_at": None if suggested else (confirmed_at or timezone.now()),
        },
    )


def seed_obligation_link(
    change: RegulatoryChange,
    obligation: Obligation,
    *,
    confidence: float | None = 0.8,
    confirmed_by_id: uuid.UUID | None = None,
    confirmed_at: datetime.datetime | None = None,
) -> ChangeObligation:
    """An obligation the change affects, a suggestion until `confirmed_by_id` names a
    library editor (WAT-04). A bank's own decision about the link lives on its case and
    never here. Kept one per `(change, obligation)`."""
    return write.upsert(
        ChangeObligation,
        "seed_e2e",
        lookup={"change": change, "obligation": obligation},
        defaults={
            "origin": OriginType.AGENT.value,
            "confidence": confidence,
            "confirmed_by_id": confirmed_by_id,
            "confirmed_at": confirmed_at if confirmed_by_id is not None else None,
        },
    )
