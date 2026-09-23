"""Registering a reform a run sighted, and the pages it was found on (WAT-02, AGT-01,
AGT-07, CAS-01, AUD-01).

This is where a sweep's finding becomes a library row, and it is the one call in the watch
pipeline that starts something in every bank: the outbox row it writes is what opens a case
for each of them (`apps/cases/creation.py`, ruling 32). So four rules shape it.

**One record per reform, and a retry is not a second one.** `stable_key` is the reform's
permanent name, chosen by the agent and never changed. Posting a key the library already
holds is the merge of AC-WAT1: the answer is 200 with the change that exists, the new pages
are attached to it as duplicates, a milestone it did not have is added, and not one field
of the change already stored is overwritten. That is what makes the call idempotent without
a stored idempotency key — an agent retries, and `stableKey` is the natural key a retry
carries. A merge writes `change.updated` and never `change.registered`, so no second case
is attempted anywhere.

**Nothing is registered against a run that is not open.** A change points at the run that
found it, so a key's registration that names no run, or a closed one, is refused (422
`run_not_open`), another key's run is not found (404), and either stores nothing: a finished
account of a night's work is not something anything may be added to afterwards. A bank's
key writes nothing here at all (403 `tenant_agents_not_available`, `runs.refuse_tenant_key`):
in R1 every run and everything it files is the platform's.

**Fetched content is untrusted** (AGT-07, playbook 11.2). Every string the run read off a
page — the reform's title and summary, and each page's own headline — goes through
`agents/screen.py` before it is stored, and what the screen finds is recorded in
`change_document.risk_flags` beside the page it came from. The text itself is stored
exactly as it arrived, because it is evidence: it is never executed, never rendered as
HTML, and never followed as an instruction. A flag says the page is suspicious, never that
the reform is.

**Everything a run files is a suggestion.** The type, the flags, the scope terms and the
obligation links all arrive with `suggested` true and nobody named as having confirmed
them, whoever sent them (WAT-03, WAT-04). No line of this module writes `suggested = false`.

Every write goes through `watch_write()` (apps/watch/write.py), which reaches the seven
watch tables and no inventory table, and through `record()` in the same transaction. This
module writes, so it names no library record: `apps/watch/keys.py` resolves what a caller
named and renders what a call answers, which is the split the library fence's AST guard
demands (apps/shared/tests_library_fence.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

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
from apps.watch import keys, so_what_draft
from apps.watch.schemas import (
    WatchChange,
    WatchChangeDocument,
    WatchChangeDocumentInput,
    WatchChangeEventInput,
    WatchChangeInput,
    WatchObligationLinkInput,
)
from apps.watch.write import watch_write

SUBJECT_TYPE = "regulatory_change"

# The kind `apps/cases/creation.py` listens for on the outbox cursor: a reform nobody had
# seen before, which opens one case in every active bank. A merge is `UPDATED`, which
# nothing fans out, so re-registering the same reform opens no second case anywhere.
REGISTERED = "change.registered"
UPDATED = "change.updated"
DOCUMENT_ADDED = "regulatory_change.document_added"
DOCUMENT_REPLAYED = "regulatory_change.document_replayed"


# ---------------------------------------------------------------------------------------
# POST /changes
# ---------------------------------------------------------------------------------------
def register_change(
    *, who: Principal, actor: Actor, order: list[str], body: WatchChangeInput
) -> tuple[int, WatchChange]:
    """File a reform a run sighted: 201 with the new change, or 200 with the one the
    library already holds under this stable key.

    Every key is resolved and every refusal raised before the write opens, so a call naming
    a vocabulary row the library does not hold stores nothing at all (AC-WAT2). A key must
    name an open run of its own, and a bank's key is refused outright; a library editor
    names none, and a run one names is not theirs.
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
    links = _one_link_per_obligation(body.obligation_links)
    # Read for its refusal, before the write opens: an obligation the library does not hold,
    # or has retired, never reaches a link, and no key scope reaches the inventory (AC-PRO1).
    keys.obligations_for(list(links))
    risk_flags = _screened([body.title, body.summary])
    _at_most_one_primary(body.documents)

    existing = keys.change_with_stable_key(body.stable_key)
    if existing is not None:
        return 200, _merge(existing, actor=actor, order=order, body=body, risk_flags=risk_flags)
    # A merge touches no stored term, so only a new change must name its regime (D-39), and
    # only a new change's standard term must come from a standards body (D-38).
    keys.require_regime(terms)
    keys.require_standards_body(terms, authority_id)

    origin = OriginType.AGENT.value if who.kind is PrincipalKind.AGENT else OriginType.USER.value
    change = keys.new_change(
        {
            "stable_key": body.stable_key,
            "title": body.title,
            "change_type": change_type,
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
        change.save()
        for entry in body.events:
            _add_event(change, entry)
        for page in body.documents:
            _add_document(change, page, risk_flags=risk_flags, duplicate=page.is_duplicate)
        for flag in flags:
            change.term_links.create(flag=flag, suggested=True)
        for term in terms:
            change.term_links.create(term=term, suggested=True)
        for obligation_id, link in links.items():
            change.obligation_links.create(obligation_id=obligation_id, origin=origin, confidence=link.confidence)
        if body.so_what is not None:
            # The one writer of the draft column, which also records the call that produced
            # it, in this transaction, as the agent reported it (D-66, AUD-02, WAT-05).
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
    """The run's classification of a new change — its type, flags, scope terms and urgency —
    as the one `scope_suggestion` row AUD-02 asks for, in this transaction (D-66).

    bleqq made no model call here, so the model metadata is the run's own account: the
    model and version it filed a “So what?” under when the filing carries one, else the
    model and pipeline version it opened the run with. The row says so
    (`model_metadata_reported_by_agent`). A library editor's registration is a person's
    classification and a merge stores no scope, so neither writes one.
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
    change: keys.ChangeRow, *, actor: Actor, order: list[str], body: WatchChangeInput, risk_flags: list[str]
) -> WatchChange:
    """A second sighting of a reform the library already holds (AC-WAT1).

    It adds and never replaces: a page the change does not carry is attached as a duplicate,
    a milestone it does not carry is added, a drafted “So what?” is filed only when the
    change has none, and every field of the change itself is left as it was. Correcting a
    stored fact is `PATCH /changes/{changeId}`, which is a deliberate act by a run that read
    the source again or by a library editor — not a side effect of a retry.
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
            # The same rule as a page and a milestone: a reform the library already holds
            # takes what it is missing and keeps what it has, so a retry cannot rewrite a
            # draft and a run that has one to give is not silently ignored (D-66).
            so_what_draft.store(change, body.so_what, actor=actor, agent_run_id=None)
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


# ---------------------------------------------------------------------------------------
# POST /changes/{changeId}/documents
# ---------------------------------------------------------------------------------------
def add_document(
    *, who: Principal, actor: Actor, order: list[str], change_id: uuid.UUID, body: WatchChangeDocumentInput
) -> tuple[int, WatchChangeDocument]:
    """Attach one fetched page to a change already registered. A bank's key is refused
    before anything is read.

    `(change, url)` is unique, so the same page posted twice answers the page that is
    already there rather than doubling it — which is what makes this safe for a run to
    retry.
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


# ---------------------------------------------------------------------------------------
# The rows themselves
# ---------------------------------------------------------------------------------------
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
    """One page the reform was found on, with what the screen found in everything this call
    read off it.

    The stored flags are the screen's own findings on the reform's title and summary and on
    this page's headline, plus whatever the run reported from the body text the server never
    sees. The run's list can only add to ours, never remove from it.
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


def _one_link_per_obligation(
    body: list[WatchObligationLinkInput],
) -> dict[uuid.UUID, WatchObligationLinkInput]:
    """The links the call carries, keyed by obligation. The same obligation twice is refused
    rather than quietly resolved, exactly as it is on `PUT /changes/{changeId}/obligations`:
    the two entries carry two confidences and keeping either would lose the other."""
    links: dict[uuid.UUID, WatchObligationLinkInput] = {}
    for link in body:
        if link.obligation_id in links:
            raise ValidationError(
                f"The obligation {link.obligation_id} is named twice in one set of links.",
                code="validation_error",
            )
        links[link.obligation_id] = link
    return links


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
