"""Registering a reform a run sighted, and the pages it was found on (WAT-02, AGT-01,
AGT-07, CAS-01, AUD-01). Its outbox row opens a case in every bank (`apps/cases/creation.py`).

- One record per reform: `stable_key` is the reform's permanent name. A known key is the
  merge of AC-WAT1: 200 with the existing change, new pages attached as duplicates, missing
  milestones added, no stored field overwritten. Idempotent without an idempotency key; a
  merge writes `change.updated`, never `change.registered`, so no second case is attempted.
- Only against an open run: no run or a closed one is 422 `run_not_open`, another key's run
  404. A bank's key writes nothing (403 `tenant_agents_not_available`).
- Fetched content is untrusted (AGT-07, playbook 11.2): every string read off a page goes
  through `agents/screen.py`, and what it finds goes in `change_document.risk_flags`. The
  text is stored as it arrived, as evidence, never executed or followed. A flag marks the
  page suspicious, not the reform.
- Everything a run files is a suggestion naming its suggester (WAT-03, WAT-04, D-74); nothing
  here writes `suggested = false`.

Writes go through `watch_write()` and `record()`; `keys.py` resolves and renders the library
rows (library fence).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.agents import runs
from apps.agents.models import AgentRun
from apps.agents.screen import screen
from apps.governance.ai_log import log_generation
from apps.governance.models import AiPurpose
from apps.library.models import DatePrecision
from apps.proposals.models import OriginType
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.schemas import AiCitation
from apps.watch import curation, keys, so_what_draft
from apps.watch.schemas import (
    WatchChange,
    WatchChangeDocument,
    WatchChangeDocumentInput,
    WatchChangeEventInput,
    WatchChangeInput,
)
from apps.watch.write import watch_write

SUBJECT_TYPE = "regulatory_change"

# The kind `apps/cases/creation.py` listens for: a new reform, one case per active bank. A
# merge is `UPDATED`, which nothing fans out.
REGISTERED = "change.registered"
UPDATED = "change.updated"
DOCUMENT_ADDED = "regulatory_change.document_added"
DOCUMENT_REPLAYED = "regulatory_change.document_replayed"


# --- POST /changes ---
def register_change(
    *, who: Principal, actor: Actor, order: list[str], body: WatchChangeInput
) -> tuple[int, WatchChange]:
    """File a reform a run sighted: 201 with the new change, or 200 with the one the library
    already holds under this stable key.

    Every refusal comes before the write, so an unknown vocabulary key stores nothing
    (AC-WAT2). A key must name an open run of its own; a bank's key is refused; a library
    editor names none. A new change past `WATCH_RUN_MAX_CHANGES` is `run_budget_exhausted`; a
    second sighting is not counted (H41).
    """
    run = (
        runs.require_open_run(who, body.agent_run_id)
        if who.kind is PrincipalKind.AGENT or body.agent_run_id is not None
        else None
    )
    change_type = keys.resolve_keys(keys.CHANGE_TYPE_LIST, [body.change_type])[0]
    flags = keys.resolve_keys(keys.FLAG_LIST, body.flags)
    terms = keys.resolve_terms(body.term_ids)
    urgency = (
        keys.resolve_keys(keys.URGENCY_LIST, [body.suggested_urgency])[0]
        if body.suggested_urgency is not None
        else None
    )
    authority_id = keys.authority_named(body.authority_code or "")
    links = curation.one_link_per_obligation(body.obligation_links)
    # Refused before the write: an unknown or retired obligation never gets a link (AC-PRO1).
    keys.obligations_for(list(links))
    risk_flags = _screened([body.title, body.summary])
    _at_most_one_primary(body.documents)

    existing = keys.change_with_stable_key(body.stable_key)
    if existing is not None:
        return 200, _merge(existing, actor=actor, order=order, body=body, risk_flags=risk_flags, run=run)
    # A merge touches no stored term, so only a new change must name its regime (D-39) and
    # take a standard term only from a standards body (D-38).
    keys.require_regime(terms)
    keys.require_standards_body(terms, authority_id)

    origin = OriginType.AGENT.value if who.kind is PrincipalKind.AGENT else OriginType.USER.value
    # The suggester, copied here because a check constraint cannot read a key's agent (D-74):
    # the run's agent and key, or the editor filing by hand, who then cannot confirm alone.
    suggester = {
        "suggested_by_id": who.subject_id if who.kind is PrincipalKind.USER else None,
        "suggested_by_agent_id": None if run is None else run.agent_id,
        "suggested_by_api_key_id": None if run is None else run.api_key_id,
    }
    change = keys.new_change(
        {
            "stable_key": body.stable_key,
            "title": body.title,
            "change_type": change_type,
            "change_type_confidence": body.change_type_confidence,
            **{f"change_type_{column}": value for column, value in suggester.items()},
            "authority_id": authority_id,
            "authority_label": body.authority_label,
            "published_on": body.published_on,
            "published_precision": body.published_precision or DatePrecision.DAY.value,
            "summary": body.summary,
            "suggested_urgency": urgency,
            "key_date": body.key_date,
            "key_date_precision": body.key_date_precision or DatePrecision.DAY.value,
            "key_date_label": body.key_date_label or "",
            "recurrence_rule": body.recurrence_rule or "",
            "source_label": body.source_label,
            "source_url": str(body.source_url),
            "origin": origin,
            "agent_run": run,
            "model": body.model or "",
        }
    )
    with watch_write("a change a run sighted"), transaction.atomic():
        if run is not None:
            runs.spend(run, run.changes.all(), limit=settings.WATCH_RUN_MAX_CHANGES, what=("change", "changes"))
        change.save()
        for entry in body.events:
            _add_event(change, entry)
        for page in body.documents:
            _add_document(change, page, risk_flags=risk_flags, duplicate=page.is_duplicate)
        for flag in flags:
            change.term_links.create(flag=flag, suggested=True, **suggester)
        for term in terms:
            change.term_links.create(term=term, suggested=True, **suggester)
        for obligation_id, link in links.items():
            change.obligation_links.create(
                obligation_id=obligation_id, origin=origin, confidence=link.confidence, **suggester
            )
        if body.so_what is not None:
            # The one writer of the draft, recording its model call as the agent reported it
            # (D-66, AUD-02, WAT-05).
            so_what_draft.store(
                change, body.so_what, actor=actor, agent_run_id=None if run is None else run.id
            )
        if run is not None:
            _log_suggested_classification(
                change,
                body,
                run=run,
                parts=[
                    f"change_type:{change_type.key}",
                    *(f"flag:{flag.key}" for flag in flags),
                    *(f"{term.dimension.key}:{term.key}" for term in terms),
                    *([] if urgency is None else [f"urgency:{urgency.key}"]),
                ],
            )
        record(
            action=REGISTERED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} registered a regulatory change.",
            tenant_id=None,
            after=_values_of(change, risk_flags),
        )
    return 201, keys.change_out(change, order)


def _log_suggested_classification(
    change: keys.ChangeRow, body: WatchChangeInput, *, run: AgentRun, parts: list[str]
) -> None:
    """The run's classification of a new change as the one `scope_suggestion` AI log row
    AUD-02 asks for (D-66). bleqq made no model call here, so the model metadata is the run's
    own account (`model_metadata_reported_by_agent`). An editor's registration and a merge
    write none.
    """
    model, version = (
        (run.model, run.pipeline_version)
        if body.so_what is None
        else (body.so_what.model, body.so_what.model_version)
    )
    log_generation(
        purpose=AiPurpose.SCOPE_SUGGESTION,
        model=model,
        model_version=version,
        output="\n".join(parts),
        citations=[AiCitation(label=body.source_label, url=str(body.source_url))],
        agent_run_id=run.id,
        subject_type=SUBJECT_TYPE,
        subject_id=change.id,
        metadata_reported_by_agent=True,
    )


def _merge(
    change: keys.ChangeRow,
    *,
    actor: Actor,
    order: list[str],
    body: WatchChangeInput,
    risk_flags: list[str],
    run: AgentRun | None,
) -> WatchChange:
    """A second sighting of a reform the library already holds (AC-WAT1). It adds and never
    replaces: missing pages, milestones and a missing drafted "So what?" are added; the
    change's own fields stay. Correcting a fact is `PATCH /changes/{changeId}`, never a retry's
    side effect.
    """
    added_documents: list[str] = []
    added_events: list[str] = []
    with watch_write("a second sighting of a registered change"), transaction.atomic():
        for entry in body.events:
            if keys.event_with_label(change, entry.label) is None:
                _add_event(change, entry)
                added_events.append(entry.label)
        for page in body.documents:
            url = str(page.url)
            if keys.document_with_url(change, url) is None:
                _add_document(change, page, risk_flags=risk_flags, duplicate=True)
                added_documents.append(url)
        if body.so_what is not None and not change.so_what_draft:
            # As for pages and milestones: take what is missing, keep what is there (D-66).
            so_what_draft.store(change, body.so_what, actor=actor, agent_run_id=None if run is None else run.id)
        record(
            action=UPDATED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} sighted a registered change again.",
            tenant_id=None,
            after={"stableKey": change.stable_key, "documents": added_documents, "events": added_events},
        )
    return keys.change_out(change, order)


# --- POST /changes/{changeId}/documents ---
def add_document(
    *, who: Principal, actor: Actor, order: list[str], change_id: uuid.UUID, body: WatchChangeDocumentInput
) -> tuple[int, WatchChangeDocument]:
    """Attach one fetched page to a registered change; a bank's key is refused first.
    `(change, url)` is unique, so a retry answers the existing page.
    """
    runs.refuse_tenant_key(who)
    change = keys.change_for_write(change_id)
    url = str(body.url)
    existing = keys.document_with_url(change, url)
    if existing is not None:
        with transaction.atomic():
            record(
                action=DOCUMENT_REPLAYED,
                actor=actor,
                subject_type=SUBJECT_TYPE,
                subject_id=change.id,
                subject_title=change.title,
                summary=f"{actor.label} retried a page the change already carried.",
                tenant_id=None,
                after={"url": url},
            )
        return 201, keys.document_out(existing)
    if body.is_primary and change.documents.filter(is_primary=True).exists():
        raise ValidationError(
            "This change already has a primary page. Attach the new one as a further page, or "
            "correct the one that is already there.",
            code="validation_error",
        )
    risk_flags = _screened([change.title, change.summary])
    with watch_write("a page a change was found on"), transaction.atomic():
        document = _add_document(change, body, risk_flags=risk_flags, duplicate=body.is_duplicate)
        record(
            action=DOCUMENT_ADDED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} attached a page a change was found on.",
            tenant_id=None,
            after={"url": url, "riskFlags": list(document.risk_flags)},
        )
    return 201, keys.document_out(document)


# --- The rows themselves ---
def _add_event(change: keys.ChangeRow, entry: WatchChangeEventInput) -> None:
    """One milestone of the reform's path. The date is a plain date with a precision and
    never a timestamp, so a screen never prints a day the source did not state (WAT-02)."""
    change.events.create(
        label=entry.label,
        event_date=entry.event_date,
        date_precision=entry.date_precision or DatePrecision.DAY.value,
        occurred=entry.occurred,
        sort_order=entry.sort_order,
        source_url="" if entry.source_url is None else str(entry.source_url),
    )


def _add_document(
    change: keys.ChangeRow, page: WatchChangeDocumentInput, *, risk_flags: list[str], duplicate: bool
) -> keys.DocumentRow:
    """One page the reform was found on, with the screen's findings on the title, summary and
    this page's headline plus whatever the run reported from the body. The run's list can
    only add to ours.
    """
    return change.documents.create(
        url=str(page.url),
        title=page.title or "",
        publisher=page.publisher or "",
        fetched_at=page.fetched_at,
        content_hash=page.content_hash or "",
        is_primary=page.is_primary and not duplicate,
        is_duplicate=duplicate,
        risk_flags=sorted({*risk_flags, *page.risk_flags, *screen(page.title or "")}),
    )


def _screened(texts: Iterable[str]) -> list[str]:
    """What the injection screen finds in everything a run read off a page (AGT-07). The
    text is never altered: the screen reads a normalised copy and the caller's string is
    stored exactly as it arrived."""
    found: set[str] = set()
    for text in texts:
        found.update(screen(text))
    return sorted(found)


def _at_most_one_primary(documents: list[WatchChangeDocumentInput]) -> None:
    """A reform is chiefly about one page. Two primaries in one call is a caller's mistake
    worth a sentence, because storing either would silently drop the other."""
    if sum(1 for page in documents if page.is_primary) > 1:
        raise ValidationError(
            "Only one page of a change is the primary one. Mark the page the reform is "
            "chiefly about and attach the rest beside it.",
            code="validation_error",
        )


def _values_of(change: keys.ChangeRow, risk_flags: list[str]) -> dict[str, Any]:
    """A registered change as the audit records it: the facts a reader would see, and what
    the screen found in the text the run read. Library rows only, so nothing here is a
    bank's own (playbook 4.7)."""
    return {
        "stableKey": change.stable_key,
        "title": change.title,
        "authorityLabel": change.authority_label,
        "keyDate": None if change.key_date is None else change.key_date.isoformat(),
        "sourceUrl": change.source_url,
        "riskFlags": risk_flags,
    }
