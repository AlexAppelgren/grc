"""Watch-zone rows for `seed_e2e` (WAT-01 to WAT-06, H15): sources, coverage checks,
regulatory changes and their timeline, pages, classification and obligation links, built
from the prototype's data as `testing.py` builds them for the backend suite.

These are library tables the library fence opens only to the watch pipeline's steps through
`watch_write()`; this module is the seed's step, through `write.upsert()`.

Idempotent by natural key (a source by `name`, a change by `stable_key`, an event by
`label`, a document by `url`, a term link by flag or term, an obligation link by obligation,
each on its change), since `seed_e2e` may run twice on one database (never a deployed one).
A source keeps one sweep check refreshed to now on every run, so a reseed never goes stale;
a `recheck` is kept one per `(source, subject)`.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from django.utils import timezone

from apps.agents.models import AgentRun
from apps.identity.models import ApiKey
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
    """One re-check line (AGT-01): the agent looked again at `obligation`'s source. Kept one
    per `(source, obligation)`, so the log can tell a re-check from a sweep."""
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
    published_unknown: bool = False,
    published_precision: DatePrecision = DatePrecision.DAY,
    key_date_precision: DatePrecision = DatePrecision.DAY,
    source_url: str = "https://www.fi.se/",
    summary: str = "FI's board decided to amend rules in the securities area.",
    suggester: ApiKey | None = None,
    type_confidence: float | None = None,
    type_confirmer: ApiKey | None = None,
    confirmed_at: datetime.datetime | None = None,
) -> RegulatoryChange:
    """One reform, merged on `stableKey` as a sweep's retry would be (AC-WAT1). Its type is
    `suggester`'s suggestion until `type_confirmer` confirms it. A change whose publication
    day is unknown (`published_unknown`) carries none."""
    type_curation = curation(suggester, type_confirmer, confirmed_at, "change_type_")
    return write.upsert(
        RegulatoryChange,
        "seed_e2e",
        lookup={"stable_key": stable_key},
        defaults={
            "title": title,
            "change_type": ChangeType.objects.get(key=change_type),
            "authority": None if authority is None else Authority.objects.get(key=authority),
            "authority_label": authority_label,
            "published_on": None if published_unknown else (published_on or key_date),
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
            "change_type_suggested": type_confirmer is None,
            "change_type_confidence": type_confidence,
            **type_curation,
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


def curation(
    suggester: ApiKey | None, confirmer: ApiKey | None, confirmed_at: datetime.datetime | None, prefix: str = ""
) -> dict[str, object]:
    """Who suggested and who confirmed a curated fact (D-74), as the curation constraints'
    columns. The seed's confirmations are an independent agent's, never a person's, so every
    suggestion stays free for a person to confirm in a journey."""
    return {
        f"{prefix}suggested_by": None,
        f"{prefix}suggested_by_api_key": suggester,
        f"{prefix}suggested_by_agent": None if suggester is None else suggester.agent,
        f"{prefix}confirmed_by": None,
        f"{prefix}confirmed_by_api_key": confirmer,
        f"{prefix}confirmed_by_agent": None if confirmer is None else confirmer.agent,
        f"{prefix}confirmed_at": None if confirmer is None else (confirmed_at or timezone.now()),
    }


def seed_flag_link(
    change: RegulatoryChange,
    *,
    flag_key: str,
    confidence: float | None = 0.8,
    suggester: ApiKey | None = None,
    confirmer: ApiKey | None = None,
    confirmed_at: datetime.datetime | None = None,
) -> ChangeTerm:
    """A flag on a change, `suggester`'s suggestion until `confirmer` confirms it (WAT-03,
    D-74). Kept one per `(change, flag)`."""
    return write.upsert(
        ChangeTerm,
        "seed_e2e",
        lookup={"change": change, "flag": Flag.objects.get(key=flag_key)},
        defaults={
            "confidence": confidence,
            "suggested": confirmer is None,
            **curation(suggester, confirmer, confirmed_at),
        },
    )


def seed_scope_term_link(
    change: RegulatoryChange,
    *,
    term_ref: str,
    confidence: float | None = 0.8,
    suggester: ApiKey | None = None,
    confirmer: ApiKey | None = None,
    confirmed_at: datetime.datetime | None = None,
) -> ChangeTerm:
    """A scope term on a change (`dimension:key`), `suggester`'s suggestion until
    `confirmer` confirms it (WAT-03, D-74). Kept one per `(change, term)`."""
    dimension, _, key = term_ref.partition(":")
    term = TaxonomyTerm.objects.select_related("dimension").get(dimension__key=dimension, key=key)
    return write.upsert(
        ChangeTerm,
        "seed_e2e",
        lookup={"change": change, "term": term},
        defaults={
            "confidence": confidence,
            "suggested": confirmer is None,
            **curation(suggester, confirmer, confirmed_at),
        },
    )


def seed_obligation_link(
    change: RegulatoryChange,
    obligation: Obligation,
    *,
    confidence: float | None = 0.8,
    suggester: ApiKey | None = None,
    confirmer: ApiKey | None = None,
    confirmed_at: datetime.datetime | None = None,
) -> ChangeObligation:
    """An obligation the change affects, `suggester`'s suggestion until `confirmer`
    confirms it (WAT-04, D-74). A bank's own decision about the link lives on its case and
    never here. Kept one per `(change, obligation)`."""
    return write.upsert(
        ChangeObligation,
        "seed_e2e",
        lookup={"change": change, "obligation": obligation},
        defaults={
            "origin": OriginType.AGENT.value,
            "confidence": confidence,
            **curation(suggester, confirmer, confirmed_at),
        },
    )
