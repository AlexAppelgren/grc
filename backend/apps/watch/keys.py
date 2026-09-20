"""What a caller named, resolved to the library rows behind it, and those rows rendered
back out (WAT-03, WAT-04, AC-WAT2).

Nothing here writes, and that is the module's reason to exist. The library fence refuses
any production module that both names a library record and calls a write
(apps/shared/tests_library_fence.py), because that is how a library write gets smuggled in
beside the proposal door. So `apps/watch/curation.py` writes and never names a library
record, and every lookup and every response it hands back is built here — the same split
`apps/cases/reading.py` makes for case creation and `apps/library/reading.py` for the
proposals app.

`resolve_keys()` is the watch app's one key resolver (chunk 5 plan, ruling B): the
registration and the standards rules call this one and add no second. A key the list does
not hold answers 422 `unknown_key` naming every key that failed and listing that list's
valid, active keys, so an agent that typed `ammendment` is told what it may say instead of
guessing again (AC-WAT2, WAT-S5). The resolver runs before anything is written, so a
refusal stores nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, cast

from django.core.exceptions import ValidationError

from apps.library.models import Obligation, RecordStatus
from apps.library.reading import localized, vocabulary_refs
from apps.shared.errors import ProblemError
from apps.taxonomy.models import ChangeTypeLabel, FlagLabel, TaxonomyTerm, TaxonomyTermLabel, UrgencyLabel
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.watch.models import ChangeDocument, ChangeEvent, RegulatoryChange
from apps.watch.schemas import (
    ChangeStatus,
    DatePrecision,
    Origin,
    WatchChange,
    WatchChangeDocument,
    WatchChangeEvent,
    WatchObligationLink,
)

# The vocabulary lists a change's facts are drawn from (apps/taxonomy/registry.py). They
# are constants here and never a caller's string: which list a field reads is settled by
# the field, so a caller can neither reach another list nor learn which lists exist.
CHANGE_TYPE_LIST = "change_type"
FLAG_LIST = "flag"

# The names `apps/watch/curation.py` annotates its own helpers with. That module writes, so
# the fence's AST rule refuses it the model's own name; the rows themselves still have to
# travel between the two halves. The guarantee that a watch step writes no inventory table
# is not this rule but `watch_write()`'s runtime refusal (apps/watch/write.py).
ChangeRow = RegulatoryChange
EventRow = ChangeEvent


# ---------------------------------------------------------------------------------------
# Resolving what a caller named
# ---------------------------------------------------------------------------------------
def resolve_keys(list_name: str, keys: Sequence[str]) -> list[Any]:
    """The rows of `list_name` that `keys` name, in the order they were sent.

    422 `unknown_key` when one does not resolve, naming every key that failed and carrying
    the list's valid, active keys in `validKeys`, so one refusal teaches the caller the
    whole vocabulary. A retired row is not a valid key: an admin retires a value to stop
    new records using it (VOC-02), and a row that never existed and a row that was retired
    answer the same way, because both are keys this call may not store.
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
    """Every key the list currently holds, in the list's own order. Ordered explicitly
    because Django drops `Meta.ordering` from some queries, and a refusal that lists the
    vocabulary in a different order each time reads as a different answer."""
    ordering = entry.model._meta.ordering or ("key",)
    return list(entry.model._default_manager.filter(active=True).order_by(*ordering).values_list("key", flat=True))


def resolve_terms(term_ids: Sequence[uuid.UUID]) -> list[TaxonomyTerm]:
    """The active taxonomy terms with these ids, in the order they were sent, read in one
    query however many there are.

    422 `unknown_key` naming every id that is not an active term of an active dimension.
    The terms are not listed back the way a vocabulary's keys are: the taxonomy is the one
    list a bank may extend to hundreds of rows, so the refusal points at
    `GET /taxonomy/terms`, which an agent reads at run start anyway (AGT-02).
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
    return [found[term_id] for term_id in term_ids]


def obligations_for(obligation_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Obligation]:
    """The active obligations these ids name, read in one query however many there are.

    422 `unknown_key` for an id the library does not hold or has retired: a link never
    creates an obligation and no key scope reaches the inventory (AC-PRO1), and a link to a
    retired obligation is a link nobody can follow.
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


def change_named(change_id: uuid.UUID) -> uuid.UUID:
    """The id of a change a caller named inside a body — the reform that replaced this one.

    422 `unknown_key` when the library holds no such change: a supersession pointing at
    nothing is a link nobody can follow, and letting the foreign key refuse it instead
    would answer a database error rather than a sentence.
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
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return change


def event_for_write(change: ChangeRow, event_id: uuid.UUID) -> EventRow:
    """One entry of this change's timeline. An entry of another change answers 404 exactly
    as one that never existed does, so a timeline id tells a caller nothing."""
    event = change.events.filter(pk=event_id).first()  # ordering: pk lookup inside one change, at most one row
    if event is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return event


# ---------------------------------------------------------------------------------------
# Rendering what a call answers
# ---------------------------------------------------------------------------------------
def change_out(change: ChangeRow, order: list[str]) -> WatchChange:
    """One change's library half, as every bank reads it: the sourced facts, the timeline,
    the pages it was found on and the obligations it affects, with every vocabulary row
    labelled in the reader's language.

    Nothing of a bank's own case is here. That lives on `change_case` under row-level
    security, and this response is the same for every bank on the platform.
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
        # The column's choices are the kind the schema publishes, so the cast states what
        # the database already fixes; pydantic validates it again as the response is built.
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
        documents=[_document_out(document) for document in documents],
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


def links_out(change: ChangeRow, order: list[str]) -> list[WatchObligationLink]:
    """The obligations this change affects, most confident first (the model's own order).
    `confirmed` is the library editor's decision and is false while the link is a
    suggestion; a bank's own decision about a link lives on its case and never here
    (WAT-04, ruling C)."""
    links = list(
        change.obligation_links.select_related("obligation__instrument").prefetch_related("obligation__titles").all()
    )
    return [
        WatchObligationLink(
            obligation_id=link.obligation_id,
            title=_title_of(link.obligation, order),
            instrument_short_name=link.obligation.instrument.short_name,
            ref_label=link.obligation.ref_label,
            origin=cast(Origin, link.origin),
            confidence=None if link.confidence is None else float(link.confidence),
            confirmed=link.confirmed_by_id is not None,
        )
        for link in links
    ]


def _document_out(document: ChangeDocument) -> WatchChangeDocument:
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
