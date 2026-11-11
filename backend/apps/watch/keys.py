"""What a caller named, resolved to the library rows behind it, and those rows rendered back
out (WAT-03, WAT-04, AC-WAT2).

Nothing here writes: the library fence refuses a module that both names a library record
and writes, so `registration.py`, `curation.py` and `sources.py` name none and do their
lookups and responses here.

`resolve_keys()` is the watch app's one key resolver: an unknown key answers 422
`unknown_key` naming every failed key and listing the valid ones, so an agent that typed
`ammendment` learns the vocabulary (AC-WAT2, WAT-S5). It runs before any write.
"""

from __future__ import annotations

import dataclasses
import datetime
import uuid
from collections.abc import Sequence
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery

from apps.library.models import Authority, JurisdictionKind, Obligation, RecordStatus
from apps.library.reading import agent_ref, localized, vocabulary_refs
from apps.shared.errors import not_found
from apps.taxonomy.models import (
    ChangeTypeLabel,
    FlagLabel,
    SourceKindLabel,
    TaxonomyTerm,
    TaxonomyTermLabel,
    TermDimensionKind,
    UrgencyLabel,
)
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.taxonomy.terms_logic import refuse_mirrored
from apps.watch.models import (
    ChangeDocument,
    ChangeEvent,
    CheckStatus,
    RegulatoryChange,
    Source,
    SourceCheck,
    SourceCheckKind,
)
from apps.watch.schemas import (
    ChangeStatus,
    DatePrecision,
    Origin,
    WatchChange,
    WatchChangeDocument,
    WatchChangeEvent,
    WatchObligationLink,
    WatchSourceOut,
)

# The vocabulary lists a change's facts are drawn from: constants, never a caller's string,
# so a caller can neither reach another list nor learn which exist.
CHANGE_TYPE_LIST = "change_type"
FLAG_LIST = "flag"
SOURCE_KIND_LIST = "source_kind"
URGENCY_LIST = "urgency"

# The dimension that says which body of law a record belongs to. Every change carries one of
# its terms (D-39, AC-AGT1): a change with none would reach every bank.
REGIME_DIMENSION = "regime"

# The names the writing modules annotate their helpers with, since the fence refuses them
# the model's own name. That no watch step writes an inventory table is `watch_write()`'s
# runtime refusal.
ChangeRow = RegulatoryChange
EventRow = ChangeEvent
DocumentRow = ChangeDocument
SourceRow = Source


# --- Resolving what a caller named ---
def resolve_keys(list_name: str, keys: Sequence[str]) -> list[Any]:
    """The rows of `list_name` that `keys` name, in the order sent. 422 `unknown_key` naming
    every key that failed, with the list's active keys in `validKeys`. A retired row is not a
    valid key (VOC-02).
    """
    entry = REGISTRY[list_name]
    wanted = list(dict.fromkeys(keys))
    rows = entry.model._default_manager.filter(
        key__in=wanted,
        active=True,
    )
    found = {row.key: row for row in rows}
    unknown = [key for key in wanted if key not in found]
    if unknown:
        valid = list(_active_keys(entry))
        raise VocabularyProblem(
            f"Not a {list_name} key: {', '.join(unknown)}. Valid keys: {', '.join(valid)}.",
            code="unknown_key",
            extra={"vocabulary": list_name, "validKeys": valid},
        )
    return [found[key] for key in keys]


def _active_keys(entry: Any) -> Sequence[str]:
    """Every key the list holds, ordered explicitly (Django drops `Meta.ordering` from some
    queries), so a refusal always lists them the same way."""
    ordering = entry.model._meta.ordering or ("key",)
    return list(entry.model._default_manager.filter(active=True).order_by(*ordering).values_list("key", flat=True))


def resolve_terms(term_ids: Sequence[uuid.UUID]) -> list[TaxonomyTerm]:
    """The active taxonomy terms with these ids, in the order sent, in one query.

    422 `unknown_key` naming every id that is not an active term; the terms are not listed
    back (a taxonomy may hold hundreds), the caller reads `GET /taxonomy/terms` (AGT-02).
    422 `jurisdiction_term_mirrored` for a mirrored dimension's term (FP-S12): a change's
    market comes from its authority (FP-S15).
    """
    wanted = list(dict.fromkeys(term_ids))
    found = {
        term.id: term
        for term in TaxonomyTerm.objects.select_related("dimension").filter(
            id__in=wanted,
            active=True,
            dimension__active=True,
        )
    }
    unknown = [str(term_id) for term_id in wanted if term_id not in found]
    if unknown:
        raise ValidationError(
            f"Not a taxonomy term: {', '.join(unknown)}. GET /taxonomy/terms lists the terms of every dimension.",
            code="unknown_key",
        )
    refuse_mirrored(term.dimension_id for term in found.values())
    return [found[term_id] for term_id in term_ids]


def require_regime(terms: Sequence[TaxonomyTerm]) -> None:
    """422 `regime_required` when none of these terms is a regime (D-39, AC-AGT1), with the
    regime dimension's active keys in `validKeys`."""
    if any(term.dimension.key == REGIME_DIMENSION for term in terms):
        return
    valid = list(
        TaxonomyTerm.objects.filter(dimension__key=REGIME_DIMENSION, dimension__active=True, active=True)
        .order_by("sort_order", "key")
        .values_list("key", flat=True)
    )
    raise VocabularyProblem(
        f"A change needs at least one regime term. Valid regimes: {', '.join(valid)}. "
        "GET /taxonomy/terms gives their ids.",
        code="regime_required",
        extra={"dimension": REGIME_DIMENSION, "validKeys": valid},
    )


def require_standards_body(terms: Sequence[TaxonomyTerm], authority_id: uuid.UUID | None) -> None:
    """422 `standard_term_only_on_standards` when an opt-in term sits on a change whose
    authority names no `international` jurisdiction (D-36, D-38, WAT-07): a law that cites a
    standard is the supervisor's and must reach every bank in scope. Kinds are read, never
    keys."""
    if not any(term.dimension.kind == TermDimensionKind.OPT_IN.value for term in terms):
        return
    if (
        authority_id is not None
        and Authority.objects.filter(id=authority_id, jurisdiction__kind=JurisdictionKind.INTERNATIONAL.value).exists()
    ):
        return
    raise ValidationError(
        "A standard's term belongs only on a change a standards body issued, named in "
        "`authorityCode` with an international jurisdiction. A law or a supervisor's rule "
        "that cites a standard carries its regime, never the standard.",
        code="standard_term_only_on_standards",
    )


def obligations_for(obligation_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Obligation]:
    """The active obligations these ids name, in one query. 422 `unknown_key` for an unknown
    or retired one: a link never creates an obligation (AC-PRO1).
    """
    wanted = list(dict.fromkeys(obligation_ids))
    found = {
        obligation.id: obligation
        for obligation in Obligation.objects.select_related("instrument").filter(
            id__in=wanted,
            status=RecordStatus.ACTIVE.value,
        )
    }
    unknown = [str(obligation_id) for obligation_id in wanted if obligation_id not in found]
    if unknown:
        raise ValidationError(
            f"Not an obligation of the library: {', '.join(unknown)}. "
            "GET /obligations lists the obligations a change may be linked to.",
            code="unknown_key",
        )
    return found


def authority_named(code: str) -> uuid.UUID | None:
    """The library authority a caller named by key, or None when it named none. An unknown
    key is 422 `unknown_key` rather than a silently unrestricted change (FP-S15, D-29).
    """
    if not code:
        return None
    found = Authority.objects.filter(key=code).values_list(
        "id", flat=True
    ).first()  # ordering: `key` is unique, at most one row
    if found is None:
        raise ValidationError(
            f"Not an authority of the library: {code}. GET /authorities lists the ones a change may name.",
            code="unknown_key",
        )
    return found


def authority_with_id(authority_id: uuid.UUID | None) -> uuid.UUID | None:
    """The library authority a caller named by id, or None when it named none. 422
    `unknown_key` for an id the authority list does not hold, so a registry row can never
    point at an authority nobody can open."""
    if authority_id is None:
        return None
    found = Authority.objects.filter(pk=authority_id).values_list(
        "id", flat=True
    ).first()  # ordering: pk lookup, at most one row
    if found is None:
        raise ValidationError(
            f"Not an authority of the library: {authority_id}. GET /authorities lists them.",
            code="unknown_key",
        )
    return found


def change_named(change_id: uuid.UUID) -> uuid.UUID:
    """The id of the change named as the one that replaced this reform; 422 `unknown_key`
    when there is none, rather than a foreign-key error.
    """
    found = RegulatoryChange.objects.filter(pk=change_id).values_list(
        "id", flat=True
    ).first()  # ordering: pk lookup, at most one row
    if found is None:
        raise ValidationError(
            f"Not a change of the library: {change_id}. Register the replacing change before naming it.",
            code="unknown_key",
        )
    return found


def change_for_write(change_id: uuid.UUID) -> ChangeRow:
    """The change this call addresses. A change that is not there answers 404 and never
    403, so no id can be probed for (playbook 4.4)."""
    change = (
        RegulatoryChange.objects.select_related("change_type", "suggested_urgency")
        .filter(pk=change_id)
        .first()  # ordering: pk lookup, at most one row
    )
    if change is None:
        raise not_found()
    return change


def change_for_update(change_id: uuid.UUID) -> ChangeRow:
    """The change this call addresses, locked until its transaction ends, for a write that
    reads what is confirmed and acts on it (D-74); 404 as `change_for_write`. The lock is its
    own query on the change's row alone, then the row is read afresh: a locking read joined to
    the type finds nothing when another call re-typed the row (`tests_curation_races.py`)."""
    if not list(RegulatoryChange.objects.select_for_update().filter(pk=change_id).values_list("pk", flat=True)):
        raise not_found()
    return change_for_write(change_id)


def event_for_write(change: ChangeRow, event_id: uuid.UUID) -> EventRow:
    """One entry of this change's timeline. An entry of another change answers 404 exactly
    as one that never existed does, so a timeline id tells a caller nothing."""
    event = change.events.filter(pk=event_id).first()  # ordering: pk lookup inside one change, at most one row
    if event is None:
        raise not_found()
    return event


def change_with_stable_key(stable_key: str) -> ChangeRow | None:
    """The reform already registered under this key, or None: a second sighting is the same
    reform, never a second row (AC-WAT1).
    """
    return (
        RegulatoryChange.objects.select_related("change_type", "suggested_urgency")
        .filter(stable_key=stable_key)
        .first()  # ordering: `stable_key` is unique, at most one row
    )


def new_change(values: dict[str, Any]) -> ChangeRow:
    """A change row built from resolved values, not yet saved: `registration.py` writes, so it
    may not name a library record (library fence).
    """
    return RegulatoryChange(**values)  # compliance: allow-kwargs the resolved column values


def document_with_url(change: ChangeRow, url: str) -> DocumentRow | None:
    """The page this change already carries under that address, or None when it is new.
    `(change, url)` is unique, which is what makes attaching a page a safe retry."""
    return change.documents.filter(url=url).first()  # ordering: (change, url) is unique, at most one row


def event_with_label(change: ChangeRow, label: str) -> EventRow | None:
    """The milestone this change already carries under that wording, or None: the label is
    the entry's key on its change."""
    return change.events.filter(label=label).first()  # ordering: Meta.ordering, (sort_order, id)


# --- The source registry and its coverage log (WAT-01) ---
@dataclasses.dataclass(frozen=True)
class Coverage:
    """One source and what its coverage log says, before the stale rule in `sources.py`
    judges it (the thresholds are settings that live beside the rule).
    """

    source: WatchSourceOut
    last_checked_at: datetime.datetime | None
    last_status: str | None
    last_error: str
    last_ok_at: datetime.datetime | None
    # When the n-th most recent sweep ran, n being the failures in a row that make a source
    # stale. Newer than `last_ok_at` means all n failed; None means fewer than n sweeps.
    nth_sweep_at: datetime.datetime | None


def new_source(values: dict[str, Any]) -> SourceRow:
    """A registry row built from values already resolved, not yet saved. Built here for the
    same reason `new_change` is: `apps/watch/sources.py` writes and may not name a library
    record."""
    return Source(**values)  # compliance: allow-kwargs the resolved column values


def source_for_write(source_id: uuid.UUID) -> SourceRow:
    """The registry row this call addresses. One that is not there answers 404 and never
    403, so no id can be probed for (playbook 4.4)."""
    source = (
        Source.objects.select_related("kind", "authority")
        .filter(pk=source_id)
        .first()  # ordering: pk lookup, at most one row
    )
    if source is None:
        raise not_found()
    return source


def source_with_name(name: str) -> SourceRow | None:
    """The registered source with that name, or None. `name` is unique across the library,
    which is what lets an agent report on a source by the name it read at run start and
    what makes a second registration under one name a conflict rather than a second row."""
    return (
        Source.objects.select_related("kind", "authority")
        .filter(name=name)
        .first()  # ordering: `name` is unique, at most one row
    )


def source_out(source: SourceRow, order: list[str]) -> WatchSourceOut:
    """One registry row as every bank reads it, with its kind labelled in the reader's
    language. A library fact: the same registry for everyone."""
    return _sources_out([source], order)[0]


def sources_out(order: list[str]) -> list[WatchSourceOut]:
    """The whole registry, by name, in two queries however many sources there are: the rows,
    then one pass over the labels of the distinct kinds they carry."""
    return _sources_out(list(Source.objects.select_related("kind", "authority").all()), order)


def coverage_rows(order: list[str], *, failures_to_stale: int) -> list[Coverage]:
    """Every source with the last line of its coverage log, in two queries (NFR-02). Only
    sweeps count: a re-check says nothing about whether the source was read since.
    """
    sweeps = SourceCheck.objects.filter(source=OuterRef("pk"), kind=SourceCheckKind.SWEEP.value)
    latest = sweeps.order_by("-checked_at", "-id")
    rows = list(
        Source.objects.select_related("kind", "authority").annotate(
            last_checked_at=Subquery(latest.values("checked_at")[:1]),
            last_status=Subquery(latest.values("status")[:1]),
            last_error=Subquery(latest.values("error")[:1]),
            last_ok_at=Subquery(
                latest.filter(status=CheckStatus.OK.value).values("checked_at")[:1]
            ),
            # The n-th most recent sweep, read by offset rather than counted: one more
            # sub-select instead of an aggregate over every check ever logged.
            nth_sweep_at=Subquery(latest.values("checked_at")[failures_to_stale - 1 : failures_to_stale]),
        )
    )
    out = _sources_out(rows, order)
    return [
        Coverage(
            source=out[index],
            last_checked_at=row.last_checked_at,
            last_status=row.last_status,
            last_error=row.last_error or "",
            last_ok_at=row.last_ok_at,
            nth_sweep_at=row.nth_sweep_at,
        )
        for index, row in enumerate(rows)
    ]


def _sources_out(rows: Sequence[SourceRow], order: list[str]) -> list[WatchSourceOut]:
    kinds = vocabulary_refs(SourceKindLabel, [row.kind for row in rows], order)
    return [
        WatchSourceOut(
            id=row.id,
            name=row.name,
            url=row.url or None,
            kind=kinds[row.kind_id],
            authority_id=row.authority_id,
            # The column's choices are the published kind; the cast states what the database fixes.
            check_frequency=cast(Any, row.check_frequency),
            active=row.active,
        )
        for row in rows
    ]


# --- Rendering what a call answers ---
def change_out(change: ChangeRow, order: list[str]) -> WatchChange:
    """One change's library half as every bank reads it: facts, timeline, pages and affected
    obligations, labelled in the reader's language. Nothing of a bank's own case.
    """
    term_links = list(change.term_links.select_related("term", "flag").all())
    flags = [link.flag for link in term_links if link.flag is not None]
    terms = [link.term for link in term_links if link.term is not None]
    flag_refs = vocabulary_refs(FlagLabel, flags, order)
    term_refs = vocabulary_refs(TaxonomyTermLabel, terms, order, field="term")
    type_refs = vocabulary_refs(ChangeTypeLabel, [change.change_type], order)
    urgency = change.suggested_urgency
    urgency_refs = vocabulary_refs(UrgencyLabel, [] if urgency is None else [urgency], order)
    documents = list(change.documents.all())
    return WatchChange(
        id=change.id,
        stable_key=change.stable_key,
        title=change.title,
        change_type=type_refs[change.change_type_id],
        authority_label=change.authority_label,
        authority_id=change.authority_id,
        published_on=change.published_on,
        # The column's choices are the published kind; pydantic validates it again.
        published_precision=cast(DatePrecision, change.published_precision),
        summary=change.summary,
        so_what_draft=change.so_what_draft or None,
        suggested_urgency=None if urgency is None else urgency_refs[urgency.id],
        key_date=change.key_date,
        key_date_precision=cast(DatePrecision, change.key_date_precision),
        key_date_label=change.key_date_label or None,
        recurrence_rule=change.recurrence_rule or None,
        flags=[flag_refs[flag.id] for flag in flags],
        source_label=change.source_label,
        source_url=change.source_url,
        status=cast(ChangeStatus, change.status),
        terms=[term_refs[term.id] for term in terms],
        events=[event_out(event) for event in change.events.all()],
        documents=[document_out(document) for document in documents],
        duplicate_count=sum(1 for document in documents if document.is_duplicate),
        obligations=links_out(change, order),
        origin=cast(Origin, change.origin),
        model=change.model or None,
        agent_run_id=change.agent_run_id,
        first_seen_at=change.first_seen_at,
    )


def event_out(event: EventRow) -> WatchChangeEvent:
    """One timeline entry. The date is a plain date with its precision, so a screen never
    prints a day the source did not state (WAT-02)."""
    return WatchChangeEvent(
        id=event.id,
        label=event.label,
        event_date=event.event_date,
        date_precision=cast(DatePrecision, event.date_precision),
        occurred=event.occurred,
        sort_order=event.sort_order,
        source_url=event.source_url or None,
    )


def provenance(row: Any, prefix: str = "") -> dict[str, Any]:
    """Who suggested a curated fact and who confirmed it, as every read answers it (D-74).
    `row` is a term or obligation link, or a change with `prefix` "change_type_", loaded with
    `CURATION_AGENTS`. A machine confirmation is read off the confirming agent's column alone,
    which the check constraint sets exactly when a key confirmed, so it never reads as a
    person's.
    """
    confirmed = getattr(row, f"{prefix}confirmed_at") is not None
    by_an_agent = getattr(row, f"{prefix}confirmed_by_agent_id") is not None
    origin: Origin | None = None if not confirmed else ("agent" if by_an_agent else "user")
    return {
        "confirmed_origin": origin,
        "suggested_by_agent": agent_ref(getattr(row, f"{prefix}suggested_by_agent")),
        "confirmed_by_agent": agent_ref(getattr(row, f"{prefix}confirmed_by_agent")),
    }


# Joined in the loading query, so naming the agents costs no query per fact (NFR-02).
CURATION_AGENTS = ("suggested_by_agent", "confirmed_by_agent")
CHANGE_TYPE_AGENTS = ("change_type_suggested_by_agent", "change_type_confirmed_by_agent")


def links_out(change: ChangeRow, order: list[str]) -> list[WatchObligationLink]:
    """The obligations this change affects, most confident first. `confirmed` is the shared
    library's confirmation; a bank's own decision lives on its case (WAT-04, ruling C, D-74)."""
    links = list(
        change.obligation_links.select_related("obligation__instrument", *CURATION_AGENTS)
        .prefetch_related("obligation__titles")
        .all()
    )
    return [
        WatchObligationLink(
            obligation_id=link.obligation_id,
            title=_title_of(link.obligation, order),
            instrument_short_name=link.obligation.instrument.shown_short_name,
            ref_label=link.obligation.ref_label,
            origin=cast(Origin, link.origin),
            confidence=None if link.confidence is None else float(link.confidence),
            confirmed=link.confirmed_at is not None,
            **provenance(link),
        )
        for link in links
    ]


def document_out(document: DocumentRow) -> WatchChangeDocument:
    """A source page. The fetched text itself is never in a response: a reader gets the
    address and opens the publisher's own page (AGT-07, WAT-07)."""
    return WatchChangeDocument(
        id=document.id,
        url=document.url,
        title=document.title or None,
        publisher=document.publisher or None,
        fetched_at=document.fetched_at,
        is_primary=document.is_primary,
        is_duplicate=document.is_duplicate,
        risk_flags=list(document.risk_flags),
    )


def _title_of(obligation: Obligation, order: list[str]) -> str:
    """The obligation's title in the reader's language, falling back to its stable key: a
    link still has to render when no translation has been written yet (INV-05)."""
    text = localized(obligation.titles.all(), order)
    return obligation.stable_key if text is None else text.text
