"""A change's library facts: its type, flags, scope terms, timeline and affected obligations,
and their confirmation (WAT-03, WAT-04, AGT-01, AUD-01, D-74).

An agent suggests and somebody else confirms. Everything filed here is a suggestion naming
its suggester (person, or agent and key); only `confirm_curation` writes a confirmation. A
`proposals.review` editor's correction is a suggestion too.

Who confirms (D-74): an agent of a different definition and key holding
`proposals:review` (the fact then reads machine-confirmed, naming both agents), or a
`proposals.review` person with a fresh passkey. Not four eyes, but the database holds that
the confirmer is never the suggester. Dropping or replacing a confirmed fact is refused for
an agent's key and needs a passkey from a person. The three writes that read what is
confirmed lock the change first (`keys.change_for_update`).

An agent's key (`changes:write`) files what a sweep read; it may not set `status` or
`supersededBy`, which are readings of the law. An editor's session (`proposals.review`, no
tenant role holds it, PRO-01) may. Every write goes through `watch_write()` and `record()`
(AUD-01). This module writes, so `keys.py` resolves and renders the library rows (library
fence).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from pydantic.alias_generators import to_camel

from apps.agents import runs
from apps.agents.screen import screen
from apps.governance import ai_log
from apps.governance.ai_log import log_generation
from apps.governance.models import AiPurpose
from apps.library.models import DatePrecision
from apps.proposals.models import OriginType
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError
from apps.watch import keys, reading, so_what_draft
from apps.watch.schemas import (
    WatchChange,
    WatchChangeEvent,
    WatchChangeEventInput,
    WatchChangePatch,
    WatchConsoleChangeRow,
    WatchCurationConfirmInput,
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
CURATION_CONFIRMED = "regulatory_change.curation_confirmed"

# Columns of `WatchChangePatch` written straight onto the row; the ones naming a library row
# are resolved first.
PLAIN_FIELDS = ("title", "summary", "key_date", "key_date_precision", "key_date_label", "status")

# What only a library editor may move (see the module docstring).
EDITOR_ONLY_FIELDS = ("status", "superseded_by")


# --- PATCH /changes/{changeId} ---
def update_change_facts(
    *,
    who: Principal,
    actor: Actor,
    order: list[str],
    change_id: uuid.UUID,
    body: WatchChangePatch,
    step_up_assertion_id: uuid.UUID | None,
) -> WatchChange:
    """Correct the library facts of a registered change.

    Every key is resolved and every refusal raised before anything is written, under the lock
    on the change, so an unknown key stores nothing (AC-WAT2). `flags` and `termIds` replace
    their whole set. `step_up_assertion_id` is needed only to overturn a confirmation, and is
    recorded on the audit row.
    """
    # Unsent and null both mean "leave it alone": this route corrects facts, never clears them.
    sent = {name: value for name, value in body.model_dump(exclude_unset=True).items() if value is not None}
    suggester = _suggester(who)
    may_overturn = _may_overturn(who, step_up_assertion_id)
    with watch_write("a change's facts"), transaction.atomic():
        change = keys.change_for_update(change_id)
        if who.kind is PrincipalKind.AGENT:
            _refuse_editor_only(sent)
        change_type = keys.resolve_keys(keys.CHANGE_TYPE_LIST, [sent["change_type"]])[0] if "change_type" in sent else None
        flags = keys.resolve_keys(keys.FLAG_LIST, sent["flags"]) if "flags" in sent else None
        terms = keys.resolve_terms(sent["term_ids"]) if "term_ids" in sent else None
        if terms is not None:
            keys.require_regime(terms)
            keys.require_standards_body(terms, change.authority_id)
        superseded_by = _superseding(change, sent) if "superseded_by" in sent else None
        if change_type is not None and change_type.id != change.change_type_id and not change.change_type_suggested:
            _refuse_confirmed(who, "the type", step_up_assertion_id)
        if flags is not None:
            _refuse_dropping_confirmed(who, change, "flag", {row.id for row in flags}, "a flag", step_up_assertion_id)
        if terms is not None:
            _refuse_dropping_confirmed(who, change, "term", {row.id for row in terms}, "a scope term", step_up_assertion_id)
        before = _facts_of(change)
        risk_flags = _screen_corrected_text(change, sent)
        _apply_columns(change, sent, change_type=change_type, superseded_by=superseded_by, suggester=suggester)
        if flags is not None:
            _replace_term_links(change, "flag", flags, suggester, may_overturn=may_overturn)
        if terms is not None:
            _replace_term_links(change, "term", terms, suggester, may_overturn=may_overturn)
        if body.so_what is not None:
            # The words, their model and the event to every bank's unedited copy are
            # `so_what_draft.store()`'s (D-66, WAT-05).
            so_what_draft.store(change, body.so_what, actor=actor, agent_run_id=None)
        record(
            action=FACTS_UPDATED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} corrected the facts of a registered change.",
            tenant_id=None,
            before=before,
            after={**_facts_of(change), **({"riskFlags": risk_flags} if risk_flags else {})},
            step_up_assertion_id=step_up_assertion_id,
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
    """The change named as the one that replaced this reform; never itself, refused here in
    words before the database would."""
    named: uuid.UUID = sent["superseded_by"]
    if named == change.id:
        raise ValidationError("A change cannot supersede itself.", code="validation_error")
    return keys.change_named(named)


def _screen_corrected_text(change: keys.ChangeRow, sent: dict[str, Any]) -> list[str]:
    """What the injection screen finds in a corrected title or summary (AGT-07), added to every
    page of the change as registration does. The text is stored as it arrived."""
    found = sorted({flag for field in ("title", "summary") if field in sent for flag in screen(sent[field])})
    if found:
        for document in change.documents.all():
            merged = sorted({*document.risk_flags, *found})
            if merged != document.risk_flags:
                document.risk_flags = merged
                document.save(update_fields=["risk_flags"])
    return found


def _suggester(who: Principal) -> dict[str, uuid.UUID | None]:
    """The three suggester columns for a fact this call files (D-74): a person's id, or an
    agent-bound key and its agent, or nobody for an unbound key (which can confirm nothing).
    Set here because a check constraint cannot read a key's agent."""
    bound = who.kind is PrincipalKind.AGENT and who.agent_id is not None
    return {
        "suggested_by_id": who.subject_id if who.kind is PrincipalKind.USER else None,
        "suggested_by_agent_id": who.agent_id if bound else None,
        "suggested_by_api_key_id": who.subject_id if bound else None,
    }


def _may_overturn(who: Principal, step_up_assertion_id: uuid.UUID | None) -> bool:
    """Whether this call's replacing set may delete a confirmed row it leaves out: only a
    person's, with a fresh passkey. A key never unmakes a confirmation (D-74)."""
    return who.kind is PrincipalKind.USER and step_up_assertion_id is not None


def _apply_columns(
    change: keys.ChangeRow,
    sent: dict[str, Any],
    *,
    change_type: Any,
    superseded_by: uuid.UUID | None,
    suggester: dict[str, uuid.UUID | None],
) -> None:
    """The change's own columns, only what the caller sent. A new type is this caller's
    suggestion, and the old type's confirmation goes with it (already refused for a key, or
    stepped up for a person)."""
    fields = [name for name in PLAIN_FIELDS if name in sent]
    for name in fields:
        setattr(change, name, sent[name])
    if change_type is not None and change_type.id != change.change_type_id:
        change.change_type = change_type
        change.change_type_suggested = True
        change.change_type_confidence = None
        change.change_type_suggested_by_id = suggester["suggested_by_id"]
        change.change_type_suggested_by_agent_id = suggester["suggested_by_agent_id"]
        change.change_type_suggested_by_api_key_id = suggester["suggested_by_api_key_id"]
        change.change_type_confirmed_by_id = None
        change.change_type_confirmed_by_api_key_id = None
        change.change_type_confirmed_by_agent_id = None
        change.change_type_confirmed_at = None
        fields += [
            "change_type",
            "change_type_suggested",
            "change_type_confidence",
            "change_type_suggested_by",
            "change_type_suggested_by_agent",
            "change_type_suggested_by_api_key",
            "change_type_confirmed_by",
            "change_type_confirmed_by_api_key",
            "change_type_confirmed_by_agent",
            "change_type_confirmed_at",
        ]
    if superseded_by is not None:
        change.superseded_by_id = superseded_by
        fields.append("superseded_by")
    if fields:
        change.save(update_fields=fields)


def _confirmed_term_ids(change: keys.ChangeRow, column: str) -> set[uuid.UUID]:
    """The rows of one kind already confirmed on this change; a check constraint keeps
    `suggested` and the confirmation columns in step."""
    stored = change.term_links.filter(**{f"{column}__isnull": False})
    return {getattr(link, f"{column}_id") for link in stored.filter(suggested=False)}


def _replace_term_links(
    change: keys.ChangeRow, column: str, rows: list[Any], suggester: dict[str, uuid.UUID | None], *, may_overturn: bool
) -> None:
    """One kind of term link (flags or scope terms) replaced by the set the caller sent.

    Every row written is this caller's suggestion (WAT-03, D-74). A confirmed row the set keeps
    stays as it is; one it leaves out goes only when `may_overturn`. A patch carries bare
    keys, so a correction stores no `confidence`.
    """
    wanted = {row.id for row in rows}
    stored = change.term_links.filter(**{f"{column}__isnull": False})
    stored.filter(suggested=True).delete()
    if may_overturn:
        stored.exclude(**{f"{column}_id__in": wanted}).delete()
    confirmed = {getattr(link, f"{column}_id") for link in stored}
    for row in rows:
        if row.id not in confirmed:
            change.term_links.create(**{column: row, "suggested": True, **suggester})


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


# --- POST /changes/{changeId}/events and PATCH /changes/{changeId}/events/{eventId} ---
def add_event(*, actor: Actor, change_id: uuid.UUID, body: WatchChangeEventInput) -> WatchChangeEvent:
    """Add one milestone to a change's timeline (WAT-02). The date is a plain date with a
    precision, so no screen prints a day the source did not state.
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
    """A milestone this change already carries. An agent retries, so the same entry posted
    again answers the existing one; the label is the entry's key on its change. The same label
    with different dates is a conflict, since storing either would lose the other.
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
    """Correct one milestone: the body is the whole entry as it should now read."""
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
    """A URL as the column stores it ("" for none), always pydantic's parse and never the
    raw string: an agent's address is untrusted (playbook 11.2)."""
    return "" if value is None else str(value)


# --- PUT /changes/{changeId}/obligations ---
def set_obligation_links(
    *,
    who: Principal,
    actor: Actor,
    order: list[str],
    change_id: uuid.UUID,
    body: list[WatchObligationLinkInput],
    step_up_assertion_id: uuid.UUID | None,
) -> list[WatchObligationLink]:
    """Replace the library-side set of obligations a change affects (WAT-04). A bank's own
    decision about a link lives on its case (ruling C). `step_up_assertion_id` is needed only
    to drop a confirmed link; check and write share the lock on the change.
    """
    origin = OriginType.AGENT.value if who.kind is PrincipalKind.AGENT else OriginType.USER.value
    suggester = _suggester(who)
    with watch_write("the obligations a change affects"), transaction.atomic():
        change = keys.change_for_update(change_id)
        wanted = one_link_per_obligation(body)
        # Refused before any write: an unknown or retired obligation never gets a link (AC-PRO1).
        keys.obligations_for(list(wanted))
        stored = {link.obligation_id: link for link in change.obligation_links.all()}
        confirmed = {obligation_id for obligation_id, link in stored.items() if link.confirmed_at is not None}
        if confirmed - set(wanted):
            _refuse_confirmed(who, "an obligation link", step_up_assertion_id)
        before = sorted(str(obligation_id) for obligation_id in stored)
        # Confirmed links the set keeps stay; suggestions are replaced, plus any confirmed link
        # a stepped-up person dropped.
        change.obligation_links.filter(confirmed_at__isnull=True).delete()
        if _may_overturn(who, step_up_assertion_id):
            change.obligation_links.exclude(obligation_id__in=list(wanted)).delete()
        for obligation_id, link in wanted.items():
            if obligation_id not in confirmed:
                change.obligation_links.create(
                    obligation_id=obligation_id, origin=origin, confidence=link.confidence, **suggester
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
            step_up_assertion_id=step_up_assertion_id,
        )
    return keys.links_out(change, order)


def one_link_per_obligation(
    body: list[WatchObligationLinkInput],
) -> dict[uuid.UUID, WatchObligationLinkInput]:
    """The links sent, keyed by obligation, for this route and registration alike. The same
    obligation twice is refused, since keeping either confidence would lose the other."""
    links: dict[uuid.UUID, WatchObligationLinkInput] = {}
    for link in body:
        if link.obligation_id in links:
            raise ValidationError(
                f"The obligation {link.obligation_id} is named twice in one set of links.",
                code="validation_error",
            )
        links[link.obligation_id] = link
    return links


# --- The one refusal both halves share ---
def _refuse_dropping_confirmed(
    who: Principal, change: keys.ChangeRow, column: str, wanted: set[uuid.UUID], what: str, step_up: uuid.UUID | None
) -> None:
    """A replacing set that leaves out a row somebody confirmed is that confirmation being
    unmade, whatever else the call says."""
    if _confirmed_term_ids(change, column) - wanted:
        _refuse_confirmed(who, what, step_up)


def _refuse_confirmed(who: Principal, what: str, step_up: uuid.UUID | None) -> None:
    """A call that would drop or replace a confirmed fact (D-74). An agent's key is refused
    outright (WAT-03). A `proposals.review` person may overturn one, since a wrong
    confirmation must be correctable, but only with a fresh passkey, recorded on the audit
    row. Returns when the call may go on.
    """
    if who.kind is PrincipalKind.AGENT:
        raise ValidationError(
            f"{what.capitalize()} on this change has been confirmed, so it is not an agent's to "
            "remove. File what you found as a new suggestion instead.",
            code="confirmed_fact",
        )
    if step_up is None:
        raise ProblemError(
            status=403,
            code="step_up_required",
            detail=f"{what.capitalize()} on this change has been confirmed. Confirm with your passkey to change it.",
        )


# --- POST /changes/{changeId}/confirmation ---
def confirm_curation(
    *,
    who: Principal,
    actor: Actor,
    order: list[str],
    change_id: uuid.UUID,
    body: WatchCurationConfirmInput,
    step_up_assertion_id: uuid.UUID | None,
) -> WatchConsoleChangeRow:
    """Confirm the named curated facts of a change for the shared library (WAT-03, WAT-04,
    D-74); the only writer of a confirmation in this module.

    The confirmer is an agent-bound platform key with `proposals:review`, sending its model
    call and open run (logged as `agent_review`, D-80), or a `proposals.review` person with a
    fresh passkey. Nobody confirms their own suggestion (409 `own_suggestion`) and an agent
    never confirms another key of its own agent's (409 `same_agent`); check constraints say
    the same. An agent never confirms a change with a risk-flagged page (409 `risk_flagged`,
    H40). All under the change's lock: a type that moved since is refused, a confirmed fact
    is left alone, and nothing new to confirm writes nothing unless it is the run's first
    decision here. Every refusal precedes the write.
    """
    with watch_write("a confirmation of a change's curated facts"), transaction.atomic():
        change = keys.change_for_update(change_id)
        run = _decision_run(who, body)
        if run is not None and change.documents.exclude(risk_flags=[]).exists():
            raise ValidationError(
                "A page of this change carries a flag from the injection screen, so an agent "
                "cannot confirm its facts: a person reads the flag and decides.",
                code="risk_flagged",
            )
        type_named, term_links, obligation_links = _named_facts(change, body)
        suggesters = [(link.suggested_by_id, link.suggested_by_api_key_id, link.suggested_by_agent_id) for link in term_links + obligation_links]
        if type_named:
            suggesters.append(
                (change.change_type_suggested_by_id, change.change_type_suggested_by_api_key_id, change.change_type_suggested_by_agent_id)
            )
        _refuse_own_suggestion(who, suggesters)
        confirmed = _names(change, type_named, term_links, obligation_links)
        if not confirmed and (run is None or _decided_in(run, change)):
            # Nothing to confirm and nothing new to log: a retry. Answer the change as it stands.
            return reading.console_change(order, change.id)
        by_person = who.subject_id if who.kind is PrincipalKind.USER else None
        by_key = who.subject_id if who.kind is PrincipalKind.AGENT else None
        by_agent = who.agent_id if who.kind is PrincipalKind.AGENT else None
        now = timezone.now()
        if type_named and change.change_type_suggested:
            change.change_type_suggested = False
            change.change_type_confirmed_by_id = by_person
            change.change_type_confirmed_by_api_key_id = by_key
            change.change_type_confirmed_by_agent_id = by_agent
            change.change_type_confirmed_at = now
            change.save(
                update_fields=[
                    "change_type_suggested",
                    "change_type_confirmed_by",
                    "change_type_confirmed_by_api_key",
                    "change_type_confirmed_by_agent",
                    "change_type_confirmed_at",
                ]
            )
        change.term_links.filter(id__in=[link.id for link in term_links], suggested=True).update(
            suggested=False,
            confirmed_by_id=by_person,
            confirmed_by_api_key_id=by_key,
            confirmed_by_agent_id=by_agent,
            confirmed_at=now,
        )
        change.obligation_links.filter(id__in=[link.id for link in obligation_links], confirmed_at__isnull=True).update(
            confirmed_by_id=by_person,
            confirmed_by_api_key_id=by_key,
            confirmed_by_agent_id=by_agent,
            confirmed_at=now,
        )
        decided: dict[str, Any] = {}
        if run is not None and body.decision is not None:
            # D-80: an agent's decision is a model call, logged in the platform's zone.
            generation = log_generation(
                purpose=AiPurpose.AGENT_REVIEW,
                model=body.decision.model,
                model_version=body.decision.model_version,
                output=body.decision.output,
                citations=body.decision.citations,
                agent_run_id=run.id,
                subject_type=SUBJECT_TYPE,
                subject_id=change.id,
                prompt_template=body.decision.prompt_template or "",
                prompt_hash=body.decision.prompt_hash or "",
                metadata_reported_by_agent=True,
            )
            decided = {"agentRunId": str(run.id), "generationId": str(generation.id)}
        record(
            action=CURATION_CONFIRMED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} confirmed facts of a registered change for the shared library.",
            tenant_id=None,
            before={"suggested": confirmed},
            after={
                "confirmed": confirmed,
                "confirmedOrigin": OriginType.AGENT.value if by_agent is not None else OriginType.USER.value,
                **decided,
            },
            step_up_assertion_id=step_up_assertion_id,
        )
    return reading.console_change(order, change.id)


def _decided_in(run: Any, change: keys.ChangeRow) -> bool:
    """Whether this run already logged a decision on this change, so a retry is not counted
    as a second model call (D-80)."""
    return ai_log.logged_for(agent_run_id=run.id, purpose=AiPurpose.AGENT_REVIEW, subject_type=SUBJECT_TYPE, subject_id=change.id)


def _decision_run(who: Principal, body: WatchCurationConfirmInput) -> Any:
    """The open run an agent's decision was made in, or None for a person, whose confirmation
    is no model call (D-80)."""
    if who.kind is PrincipalKind.AGENT:
        if body.decision is None:
            raise ValidationError(
                "An agent confirms with the model call behind its decision: send decision with "
                "the model, its version, what it concluded and the pages it rests on.",
                code="validation_error",
            )
        return runs.require_open_run(who, body.agent_run_id)
    if body.decision is not None or body.agent_run_id is not None:
        raise ValidationError(
            "A person's confirmation carries no model decision and no agent run. Leave out "
            "decision and agentRunId.",
            code="validation_error",
        )
    return None


def _named_facts(change: keys.ChangeRow, body: WatchCurationConfirmInput) -> tuple[bool, list[Any], list[Any]]:
    """The facts the call names, each of which must be on the change now: a confirmation
    never creates one. A type key other than the change's current type is refused. Naming
    nothing is refused too."""
    term_links = list(change.term_links.select_related("flag").filter(flag__key__in=body.flags))
    term_links += list(change.term_links.filter(term_id__in=body.term_ids))
    obligation_links = list(change.obligation_links.filter(obligation_id__in=body.obligation_ids))
    type_named = body.change_type is not None
    missing = (
        ([f"the type {body.change_type}"] if type_named and body.change_type != change.change_type.key else [])
        + [f"the flag {key}" for key in body.flags if key not in {link.flag.key for link in term_links if link.flag is not None}]
        + [f"the term {term_id}" for term_id in body.term_ids if term_id not in {link.term_id for link in term_links}]
        + [
            f"the obligation {obligation_id}"
            for obligation_id in body.obligation_ids
            if obligation_id not in {link.obligation_id for link in obligation_links}
        ]
    )
    if missing:
        raise ValidationError(
            f"This change does not carry {', '.join(missing)}. Confirm only what the change "
            "carries now; read it again, and a type, a link or a term is corrected through the "
            "curation routes first.",
            code="validation_error",
        )
    if not (type_named or term_links or obligation_links):
        raise ValidationError(
            "Name at least one fact to confirm: the type, a flag, a scope term or a linked obligation.",
            code="validation_error",
        )
    return type_named, term_links, obligation_links


def _refuse_own_suggestion(who: Principal, suggesters: list[tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]]) -> None:
    """Nobody confirms their own suggestion, and an agent's key never confirms one filed by
    another key of the same agent definition (D-74). Person or key is checked first, as the
    narrower fact."""
    for person_id, api_key_id, agent_id in suggesters:
        if who.subject_id in (person_id, api_key_id):
            raise ValidationError(
                "You filed that fact yourself. A confirmation comes from somebody else: an agent "
                "of another definition, or another person."
                if who.kind is PrincipalKind.USER
                else "This key suggested that fact itself. A confirmation comes from an agent of "
                "another definition and key.",
                code="own_suggestion",
            )
        if agent_id is not None and agent_id == who.agent_id:
            raise ValidationError(
                "Another key of the same agent suggested that fact. A confirmation comes from "
                "an agent of another definition.",
                code="same_agent",
            )


def _names(change: keys.ChangeRow, type_named: bool, term_links: list[Any], obligation_links: list[Any]) -> list[str]:
    """The named facts nobody has confirmed yet, as the audit records them: kind and key,
    library rows only (playbook 4.7)."""
    names = [f"changeType:{change.change_type.key}"] if type_named and change.change_type_suggested else []
    names += [f"flag:{link.flag.key}" if link.flag_id else f"term:{link.term_id}" for link in term_links if link.suggested]
    names += [f"obligation:{link.obligation_id}" for link in obligation_links if link.confirmed_at is None]
    return names
