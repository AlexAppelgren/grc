"""A change's library facts: its type, its flags, its scope terms, its timeline and the
obligations it affects (WAT-03, WAT-04, AGT-01, AUD-01).

An agent proposes and a person decides. Everything filed here is stored as a suggestion —
a term link with `suggested` true and nobody named in `confirmed_by`, an obligation link
with no confirmation on it — and no line of this module writes `suggested = false`,
`confirmed_by` or `confirmed_at`. A library editor holding `proposals.review` may correct a
suggestion, and the correction is a suggestion too.

The confirmation is missing rather than merely unbuilt. Whether one person may settle a
change's library facts with no proposal, no second pair of eyes and no step-up is the open
question `q-editor-confirm`, which CLAUDE.md section 5 reserves to the owner, so it is the
held task `c5-watch-curation-confirm`. Until it is answered, a call that would move a fact
somebody has already confirmed answers 501 `not_built` for that editor, and is refused
outright for an agent's key, which may never unmake a person's decision.

What each principal may move:

- **An agent's key** (`changes:write`) files what a sweep read off the source: the title,
  the type, the summary, the key date, the flags and the scope terms, plus the timeline and
  the obligations the change touches. It may not set `status` or `supersededBy`, because
  deciding that a reform has been replaced or withdrawn is a reading of the law and not a
  sighting of it.
- **A library editor's session** (`proposals.review`) may move all of that and those two
  fields as well. No tenant role holds that permission (PRO-01).

Every write goes through `watch_write()` (apps/watch/write.py), which reaches the seven
watch tables and no inventory table, and through `record()` in the same transaction, so no
fact moves without its audit row and its outbox row beside it (AUD-01).

This module writes, so it names no library record: `apps/watch/keys.py` resolves what a
caller named and renders what a call answers, which is the split the library fence's AST
guard demands (apps/shared/tests_library_fence.py).
"""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.core.exceptions import ValidationError
from django.db import transaction
from pydantic.alias_generators import to_camel

from apps.library.models import DatePrecision
from apps.proposals.models import OriginType
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError
from apps.watch import keys
from apps.watch.schemas import (
    WatchChange,
    WatchChangeEvent,
    WatchChangeEventInput,
    WatchChangePatch,
    WatchObligationLink,
    WatchObligationLinkInput,
)
from apps.watch.write import watch_write

SUBJECT_TYPE = "regulatory_change"

FACTS_UPDATED = "regulatory_change.facts_updated"
EVENT_ADDED = "regulatory_change.event_added"
EVENT_REPLAYED = "regulatory_change.event_replayed"
EVENT_UPDATED = "regulatory_change.event_updated"
LINKS_REPLACED = "regulatory_change.obligations_replaced"

# The columns of `WatchChangePatch` that carry a plain value, written straight onto the row.
# `changeType`, `supersededBy`, `flags` and `termIds` each name a library row and are
# resolved first, so they are not in this list.
PLAIN_FIELDS = ("title", "summary", "key_date", "key_date_precision", "key_date_label", "status")

# What only a library editor may move (see the module docstring).
EDITOR_ONLY_FIELDS = ("status", "superseded_by")


# ---------------------------------------------------------------------------------------
# PATCH /changes/{changeId}
# ---------------------------------------------------------------------------------------
def update_change_facts(
    *, who: Principal, actor: Actor, order: list[str], change_id: uuid.UUID, body: WatchChangePatch
) -> WatchChange:
    """Correct the library facts of a registered change.

    Every key is resolved and every refusal raised before the write opens, so a call that
    names a key the library does not hold stores nothing at all (AC-WAT2). `flags` and
    `termIds` each replace the whole set they name rather than adding to it.
    """
    change = keys.change_for_write(change_id)
    # A field the caller did not send, and a field sent as null, both mean "leave it
    # alone": this route corrects facts and never clears them (`WatchChangePatch`).
    sent = {name: value for name, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if who.kind is PrincipalKind.AGENT:
        _refuse_editor_only(sent)
    change_type = keys.resolve_keys(keys.CHANGE_TYPE_LIST, [sent["change_type"]])[0] if "change_type" in sent else None
    flags = keys.resolve_keys(keys.FLAG_LIST, sent["flags"]) if "flags" in sent else None
    terms = keys.resolve_terms(sent["term_ids"]) if "term_ids" in sent else None
    superseded_by = _superseding(change, sent) if "superseded_by" in sent else None
    if flags is not None:
        _refuse_dropping_confirmed(who, change, "flag", {row.id for row in flags}, "a flag")
    if terms is not None:
        _refuse_dropping_confirmed(who, change, "term", {row.id for row in terms}, "a scope term")
    before = _facts_of(change)
    with watch_write("a change's facts"), transaction.atomic():
        _apply_columns(change, sent, change_type=change_type, superseded_by=superseded_by)
        if flags is not None:
            _replace_term_links(change, "flag", flags)
        if terms is not None:
            _replace_term_links(change, "term", terms)
        record(
            action=FACTS_UPDATED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} corrected the facts of a registered change.",
            tenant_id=None,
            before=before,
            after=_facts_of(change),
        )
    return keys.change_out(change, order)


def _refuse_editor_only(sent: dict[str, Any]) -> None:
    """A key filing what it read off a source never decides that a reform has been replaced
    or withdrawn: that is a reading of the law, and it stays with `proposals.review`."""
    named = [to_camel(name) for name in EDITOR_ONLY_FIELDS if name in sent]
    if named:
        raise ValidationError(
            f"{', '.join(named)} is a library editor's to set, not an agent's. Register the "
            "replacing change and leave the supersession to review.",
            code="editor_only_field",
        )


def _superseding(change: keys.ChangeRow, sent: dict[str, Any]) -> uuid.UUID:
    """The change named as the one that replaced this reform. A change may not supersede
    itself: the database refuses it, and refusing it here says so in words rather than
    letting a database error reach the caller."""
    named: uuid.UUID = sent["superseded_by"]
    if named == change.id:
        raise ValidationError("A change cannot supersede itself.", code="validation_error")
    return keys.change_named(named)


def _apply_columns(
    change: keys.ChangeRow, sent: dict[str, Any], *, change_type: Any, superseded_by: uuid.UUID | None
) -> None:
    """The change's own columns, written once. Only what the caller sent moves, so
    correcting one fact never restates another."""
    fields = [name for name in PLAIN_FIELDS if name in sent]
    for name in fields:
        setattr(change, name, sent[name])
    if change_type is not None:
        change.change_type = change_type
        fields.append("change_type")
    if superseded_by is not None:
        change.superseded_by_id = superseded_by
        fields.append("superseded_by")
    if fields:
        change.save(update_fields=fields)


def _confirmed_term_ids(change: keys.ChangeRow, column: str) -> set[uuid.UUID]:
    """The rows of one kind a library editor has already confirmed on this change.
    `suggested` and the two confirmation columns are kept in step by a check constraint
    (`change_term_confirmation_names_a_person`), so reading one reads all three."""
    stored = change.term_links.filter(**{f"{column}__isnull": False})
    return {getattr(link, f"{column}_id") for link in stored.filter(suggested=False)}


def _replace_term_links(change: keys.ChangeRow, column: str, rows: list[Any]) -> None:
    """One kind of term link — the flags, or the scope terms — replaced by the set the
    caller sent.

    Every row written is a suggestion: `suggested` true, nobody in `confirmed_by` and no
    time in `confirmed_at`, whoever sent it (WAT-03). A row a library editor confirmed is
    kept exactly as it is, and the call that would have dropped one was refused before this
    write opened. A term link's `confidence` is not on this call's shape — a patch carries
    bare keys — so a correction stores none; an agent's own number arrives with the
    registration.
    """
    stored = change.term_links.filter(**{f"{column}__isnull": False})
    stored.filter(suggested=True).delete()
    confirmed = {getattr(link, f"{column}_id") for link in stored}
    for row in rows:
        if row.id not in confirmed:
            link = {column: row, "suggested": True}
            change.term_links.create(**link)


def _facts_of(change: keys.ChangeRow) -> dict[str, Any]:
    """A change's classification as the audit records it: the facts a reader would see
    move. Library rows only, so nothing here is a bank's own (playbook 4.7)."""
    links = list(change.term_links.select_related("term", "flag").all())
    return {
        "title": change.title,
        "changeType": change.change_type.key,
        "status": change.status,
        "keyDate": None if change.key_date is None else change.key_date.isoformat(),
        "flags": sorted(link.flag.key for link in links if link.flag is not None),
        "terms": sorted(link.term.key for link in links if link.term is not None),
    }


# ---------------------------------------------------------------------------------------
# POST /changes/{changeId}/events and PATCH /changes/{changeId}/events/{eventId}
# ---------------------------------------------------------------------------------------
def add_event(*, actor: Actor, change_id: uuid.UUID, body: WatchChangeEventInput) -> WatchChangeEvent:
    """Add one milestone to a change's timeline, consultation to in force (WAT-02).

    The date is a plain date with a precision and never a timestamp, so a screen never
    prints a day the source did not state.
    """
    change = keys.change_for_write(change_id)
    existing = change.events.filter(label=body.label).first()  # ordering: Meta.ordering, (sort_order, id)
    if existing is not None:
        return _replayed_event(existing, actor, change, body)
    with watch_write("a change's timeline"), transaction.atomic():
        event = change.events.create(
            label=body.label,
            event_date=body.event_date,
            date_precision=body.date_precision or DatePrecision.DAY.value,
            occurred=body.occurred,
            sort_order=body.sort_order,
            source_url=_url(body.source_url),
        )
        record(
            action=EVENT_ADDED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} added a milestone to a change's timeline.",
            tenant_id=None,
            after=_event_values(event),
        )
    return keys.event_out(event)


def _replayed_event(
    existing: keys.EventRow, actor: Actor, change: keys.ChangeRow, body: WatchChangeEventInput
) -> WatchChangeEvent:
    """A milestone this change already carries.

    An agent retries, so posting the same entry again answers the entry it already added
    rather than doubling the timeline. `change_event` holds no idempotency column, so the
    label is the entry's key on its change: a reform has one "Consultation closed". The same
    label with different dates is a conflict, because storing either version would lose the
    other, and the caller can correct the entry it already has instead.
    """
    if _event_values(existing) != _posted_values(body):
        raise ValidationError(
            f"This change already has a milestone called {existing.label!r} with other dates. "
            "Correct that entry instead of adding a second one with the same label.",
            code="duplicate_key",
        )
    with transaction.atomic():
        record(
            action=EVENT_REPLAYED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} retried a milestone the timeline already had.",
            tenant_id=None,
            after=_event_values(existing),
        )
    return keys.event_out(existing)


def update_event(
    *, actor: Actor, change_id: uuid.UUID, event_id: uuid.UUID, body: WatchChangeEventInput
) -> WatchChangeEvent:
    """Correct one milestone: its wording, its date and precision, where it sits in the
    timeline, and whether the source says it has happened.

    The body is the entry as it should now read, not a delta: `WatchChangeEventInput` is the
    same shape that adds one, so a field left out takes that shape's default.
    """
    change = keys.change_for_write(change_id)
    event = keys.event_for_write(change, event_id)
    before = _event_values(event)
    with watch_write("a change's timeline"), transaction.atomic():
        event.label = body.label
        event.event_date = body.event_date
        event.date_precision = body.date_precision or DatePrecision.DAY.value
        event.occurred = body.occurred
        event.sort_order = body.sort_order
        event.source_url = _url(body.source_url)
        event.save(update_fields=["label", "event_date", "date_precision", "occurred", "sort_order", "source_url"])
        record(
            action=EVENT_UPDATED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} corrected a milestone on a change's timeline.",
            tenant_id=None,
            before=before,
            after=_event_values(event),
        )
    return keys.event_out(event)


def _event_values(event: keys.EventRow) -> dict[str, Any]:
    """One timeline entry as the audit records it and as a retry is compared against."""
    return {
        "label": event.label,
        "eventDate": None if event.event_date is None else event.event_date.isoformat(),
        "datePrecision": event.date_precision,
        "occurred": event.occurred,
        "sortOrder": event.sort_order,
        "sourceUrl": event.source_url or None,
    }


def _posted_values(body: WatchChangeEventInput) -> dict[str, Any]:
    """The same shape from the request body, so a retry compares like with like."""
    return {
        "label": body.label,
        "eventDate": None if body.event_date is None else body.event_date.isoformat(),
        "datePrecision": body.date_precision or DatePrecision.DAY.value,
        "occurred": body.occurred,
        "sortOrder": body.sort_order,
        "sourceUrl": _url(body.source_url) or None,
    }


def _url(value: Any) -> str:
    """A URL as the column stores it, or the empty string the column uses for "none". It is
    what pydantic parsed and never the caller's raw string: an address an agent sent is
    untrusted until the schema has read it (playbook 11.2)."""
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------------------
# PUT /changes/{changeId}/obligations
# ---------------------------------------------------------------------------------------
def set_obligation_links(
    *, who: Principal, actor: Actor, order: list[str], change_id: uuid.UUID, body: list[WatchObligationLinkInput]
) -> list[WatchObligationLink]:
    """Replace the library-side set of obligations a change affects (WAT-04).

    Library facts only: a bank's own decision about a suggested link lives on that bank's
    case and changes nothing here, so one bank removing a link leaves every other bank still
    seeing it (ruling C).
    """
    change = keys.change_for_write(change_id)
    wanted = _one_link_per_obligation(body)
    # Read for its refusal, before the write opens: an obligation the library does not
    # hold, or has retired, never reaches a link (AC-PRO1).
    keys.obligations_for(list(wanted))
    stored = {link.obligation_id: link for link in change.obligation_links.all()}
    confirmed = {obligation_id for obligation_id, link in stored.items() if link.confirmed_by_id is not None}
    if confirmed - set(wanted):
        _refuse_confirmed(who, "an obligation link")
    origin = OriginType.AGENT.value if who.kind is PrincipalKind.AGENT else OriginType.USER.value
    before = sorted(str(obligation_id) for obligation_id in stored)
    with watch_write("the obligations a change affects"), transaction.atomic():
        # Confirmed links are kept: the set being replaced is the set of suggestions, and
        # the call that would have dropped a confirmed link was refused above.
        change.obligation_links.filter(confirmed_by__isnull=True).delete()
        for obligation_id, link in wanted.items():
            if obligation_id not in confirmed:
                change.obligation_links.create(
                    obligation_id=obligation_id,
                    origin=origin,
                    confidence=link.confidence,
                )
        record(
            action=LINKS_REPLACED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} set the obligations a registered change affects.",
            tenant_id=None,
            before={"obligations": before},
            after={"obligations": sorted(str(obligation_id) for obligation_id in wanted)},
        )
    return keys.links_out(change, order)


def _one_link_per_obligation(
    body: list[WatchObligationLinkInput],
) -> dict[uuid.UUID, WatchObligationLinkInput]:
    """The links the caller sent, keyed by obligation. The same obligation twice in one body
    is refused rather than quietly resolved: the two entries carry two confidences and
    keeping either would lose the other."""
    links: dict[uuid.UUID, WatchObligationLinkInput] = {}
    for link in body:
        if link.obligation_id in links:
            raise ValidationError(
                f"The obligation {link.obligation_id} is named twice in one set of links.",
                code="validation_error",
            )
        links[link.obligation_id] = link
    return links


# ---------------------------------------------------------------------------------------
# The one refusal both halves share
# ---------------------------------------------------------------------------------------
def _refuse_dropping_confirmed(
    who: Principal, change: keys.ChangeRow, column: str, wanted: set[uuid.UUID], what: str
) -> None:
    """A replacing set that leaves out a row a library editor confirmed is that
    confirmation being unmade, whatever else the call says."""
    if _confirmed_term_ids(change, column) - wanted:
        _refuse_confirmed(who, what)


def _refuse_confirmed(who: Principal, what: str) -> NoReturn:
    """A call that would move a fact a library editor has already confirmed.

    An agent's key is refused outright: an agent proposes, and it never unmakes a person's
    decision (WAT-03). For the editor it is the held half of this feature — whether one
    person may settle a library fact with no proposal at all is `q-editor-confirm`, which
    CLAUDE.md section 5 reserves to the owner — so it answers 501 rather than pretending
    the confirmation is not there.
    """
    if who.kind is PrincipalKind.AGENT:
        raise ValidationError(
            f"{what} on this change has been confirmed by a library editor, so it is not an "
            "agent's to remove. File what you found as a new suggestion instead.",
            code="confirmed_fact",
        )
    raise ProblemError(
        status=501,
        code="not_built",
        detail=f"Changing {what} once a library editor has confirmed it is not built yet.",
    )
