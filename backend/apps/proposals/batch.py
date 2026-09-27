"""Batch proposals (PRO-04, AGT-05): one request that changes many library records, filed as
one proposal with a row per record.

A batch is a `proposal` with `is_batch` set, so four eyes, the rejection reason, the audit
row and the queue are the ones every proposal has: the queue lists a batch once. Each
`proposal_batch_row` carries the preview the reviewer decides on, computed here when the
batch is filed and never again, so a reviewer decides on what was proposed rather than on
what the library says now. A row whose record moved since is `stale` when read, and cannot be
approved: the `If-Match` rule, applied to a batch.

`create_batch()` is the one writer: the console route, the re-tag request's platform run and
the seed all file through it. It writes proposal rows only; a preview writes nothing into
the library, whose rows are read through apps/library/reading.py. Re-tagging is the
platform's (AGT-05): a bank's session or key never reaches it, and the rows carry no tenant
content. `decide()` is declared and answers 501 until the decision half is built.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.agents import runs
from apps.agents.screen import screen_all
from apps.library.reading import active_shared_obligations, obligation_headings, obligation_scope_terms, terms_of, unknown_provision_keys
from apps.proposals import logic, standards
from apps.proposals.logic import Proposer
from apps.proposals.models import BatchRowDecision, Proposal, ProposalBatchRow, ProposalKind, ProposalStatus
from apps.proposals.schemas import (
    ObligationScopePayload,
    ProposalActorRef,
    ProposalBatch,
    ProposalBatchDecision,
    ProposalBatchRow as ProposalBatchRowOut,
    ProposalBatchRowPayload,
    ProposalTarget,
)
from apps.shared import tenancy
from apps.shared.audit import record
from apps.shared.errors import ProblemError
from apps.taxonomy.terms_logic import refuse_mirrored

# What a re-tag row changes, as `target_type` names a single proposal's record.
OBLIGATION = logic.OBLIGATION_TARGET
BATCH_KINDS = (ProposalKind.OBLIGATION_SCOPE.value,)


def _normalized(payload: ObligationScopePayload) -> ObligationScopePayload:
    """The payload as it is stored and compared on a retry: sources trimmed, each term named
    once. Checks only what needs no database: the cap, one entry per obligation, a source on
    every entry and no term both added and removed."""
    changes = payload.changes
    cap = settings.PROPOSAL_BATCH_MAX_ROWS
    if len(changes) > cap:
        raise ValidationError(
            f"A batch changes at most {cap} records; this one names {len(changes)}. File it as more than one batch.",
            code="batch_too_large",
        )
    seen: set[uuid.UUID] = set()
    for change in changes:
        if change.obligation_id in seen:
            raise ValidationError(f"Name each obligation once. Repeated: {change.obligation_id}.", code="validation_error")
        seen.add(change.obligation_id)
        change.source = change.source.strip()
        if not change.source:
            raise ValidationError(f"Give the source of the new scope of {change.obligation_id}.", code="source_missing")
        change.add, change.remove = list(dict.fromkeys(change.add)), list(dict.fromkeys(change.remove))
        both = sorted(set(change.add) & set(change.remove))
        if both:
            raise ValidationError(f"A term is added or removed, not both: {', '.join(both)}.", code="validation_error")
    return payload


def _preview(payload: ObligationScopePayload, source_label: str) -> list[ProposalBatchRow]:
    """One unsaved row per obligation, its scope before (the live `obligation_term` rows) and
    after, once every rule a proposal's scope answers to has passed: live shared obligations,
    live terms, no term of a dimension mirroring the jurisdiction list, a source a reader can
    follow, and the standards rule (a standard's term only on a standard's obligation, which
    keeps exactly one, and only links as a standard's sources). An entry that would change
    nothing is refused rather than queued."""
    ids = [change.obligation_id for change in payload.changes]
    obligations = active_shared_obligations(ids)
    missing = [str(obligation_id) for obligation_id in ids if obligation_id not in obligations]
    if missing:
        raise ValidationError(
            f"Not an obligation of the library in force: {', '.join(missing)}.", code="unknown_key"
        )
    refs = sorted({ref for change in payload.changes for ref in (*change.add, *change.remove)})
    terms = terms_of(refs) if refs else []
    refuse_mirrored(term.dimension_id for term in terms)
    term_ids = {f"{term.dimension.key}:{term.key}": term.id for term in terms}
    scopes = obligation_scope_terms(ids)
    rows = []
    unchanged = []
    for change in payload.changes:
        before = scopes.get(change.obligation_id, {})
        after = {ref: term_id for ref, term_id in before.items() if ref not in change.remove}
        after.update({ref: term_ids[ref] for ref in change.add})
        if after.keys() == before.keys():
            unchanged.append(str(change.obligation_id))
            continue
        standards.check(
            ProposalKind.OBLIGATION_SCOPE.value,
            obligations[change.obligation_id].instrument,
            list(after.values()),
            {"terms": change.source},
            source_label=source_label,
        )
        rows.append(
            ProposalBatchRow(
                subject_type=OBLIGATION,
                subject_id=change.obligation_id,
                before={"terms": sorted(before)},
                after={"terms": sorted(after)},
            )
        )
    if unchanged:
        raise ValidationError(
            f"These entries leave the scope as it is; take them out: {', '.join(unchanged)}.", code="validation_error"
        )
    # After the standards check, so a standard's clause pasted as a source answers
    # `licensed_text`, the rule it breaks, as a single proposal's does (D-35).
    unknown = unknown_provision_keys({change.source for change in payload.changes if not logic.is_link(change.source)})
    if unknown:
        raise ValidationError(
            "A source is an https link or the stable key of a provision in the library. "
            f"Not a source: {', '.join(sorted(unknown))}.",
            code="validation_error",
        )
    return rows


def create_batch(
    *,
    kind: str,
    title: str,
    payload: ObligationScopePayload,
    proposer: Proposer,
    agent_run_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    model: str = "",
    source_label: str = "",
    source_url: str = "",
) -> tuple[Proposal, bool]:
    """File a batch, or answer the one an earlier identical submission filed. Returns
    `(proposal, created)`.

    A key names an open run of its own (AGT-01), checked first, as for a single proposal;
    a person names none. The same `Idempotency-Key` from the same proposer with the same
    body answers the batch it already made and records the retry; with another body it is
    409 `idempotency_conflict`. Every text the proposer sent is read by the injection screen
    and stored as it arrived. The proposal, its rows and its audit row are written in one
    transaction."""
    if tenancy.database_tenant_id() is not None:
        # AGT-05: re-tagging the library is the platform console's; the route refuses a bank
        # first, and this refuses any other caller writing from inside a bank.
        raise ProblemError(status=403, code="permission_denied", detail="A bank does not re-tag the shared library.")
    run = None
    if proposer.api_key_id is not None or agent_run_id is not None:
        run = runs.require_open_run_of_key(proposer.api_key_id, agent_run_id)
    if kind not in BATCH_KINDS:
        raise ValidationError(f"{kind!r} is not a batch kind. Valid kinds: {', '.join(BATCH_KINDS)}.", code="unknown_key")
    title = title.strip()
    if not title:
        raise ValidationError("Give the batch a title.", code="validation_error")
    source_label, source_url = source_label.strip(), source_url.strip()
    if source_url and not logic.is_link(source_url):
        raise ValidationError("sourceUrl is an https link to the authority's page, or left out.", code="validation_error")
    stored: dict[str, Any] = logic.payload_dict(_normalized(payload))
    if idempotency_key:
        if len(idempotency_key) > logic.IDEMPOTENCY_KEY_MAX_CHARS:
            raise ValidationError(
                f"An Idempotency-Key is at most {logic.IDEMPOTENCY_KEY_MAX_CHARS} characters.", code="validation_error"
            )
        own = Q(proposed_by_user=proposer.user) if proposer.user is not None else Q(proposed_by_api_key_id=proposer.api_key_id)
        existing = Proposal.objects.filter(own, idempotency_key=idempotency_key).order_by("created_at", "id").first()
        if existing is not None:
            if (existing.is_batch, existing.kind, existing.title, existing.payload) != (True, kind, title, stored):
                raise ValidationError("This Idempotency-Key was already used for a different proposal.", code="idempotency_conflict")
            record(
                action="proposal.replayed",
                actor=proposer.actor,
                subject_type=logic.SUBJECT_TYPE,
                subject_id=existing.id,
                subject_title=existing.title,
                summary="A retried submission answered the batch it already made.",
                tenant_id=None,
                after={"idempotencyKey": idempotency_key},
            )
            return existing, False
    rows = _preview(payload, source_label)
    risk_flags = screen_all([title, model, source_label, source_url, *(change.source for change in payload.changes)])
    with transaction.atomic():
        if run is not None:
            runs.spend(run, Proposal.objects.filter(agent_run_id=run.id), limit=settings.WATCH_RUN_MAX_PROPOSALS, what=("proposal", "proposals"))
        proposal = Proposal.objects.create(
            kind=kind,
            title=title,
            payload=stored,
            model=model,
            source_label=source_label,
            source_url=source_url,
            risk_flags=risk_flags,
            origin=proposer.origin.value,
            agent_run_id=agent_run_id,
            proposed_by_user=proposer.user,
            proposed_by_api_key_id=proposer.api_key_id,
            proposed_by_agent_id=proposer.agent_id,
            idempotency_key=idempotency_key or None,
            status=ProposalStatus.OPEN.value,
            is_batch=True,
            row_count=len(rows),
        )
        for row in rows:
            row.proposal = proposal
        ProposalBatchRow.objects.bulk_create(rows)
        record(
            action="proposal.created",
            actor=proposer.actor,
            subject_type=logic.SUBJECT_TYPE,
            subject_id=proposal.id,
            subject_title=proposal.title,
            summary=f"Proposed a batch of {len(rows)}: {proposal.title}",
            tenant_id=None,
            after={
                "kind": kind,
                "origin": proposal.origin,
                "isBatch": True,
                "rowCount": len(rows),
                "subjectIds": [str(row.subject_id) for row in rows],
                **({"riskFlags": risk_flags} if risk_flags else {}),
            },
        )
    return proposal, True


def by_id(batch_id: uuid.UUID) -> Proposal:
    """The batch `batch_id`, or 404 for anything else, a single proposal included."""
    proposal = (
        Proposal.objects.select_related("proposed_by_user", "reviewed_by", "proposed_by_agent", "reviewed_by_agent", "corrected_by")
        .filter(pk=batch_id, is_batch=True)
        .first()  # ordering: pk lookup, at most one row
    )
    if proposal is None:
        raise ValidationError("That batch is not here.", code="not_found")
    return proposal


def read(proposal: Proposal, order: list[str]) -> ProposalBatch:
    """The batch with every row and its preview, in a handful of queries however many rows
    it holds: the rows, the records' headings and their live scope, which marks a pending row
    `stale` when it no longer matches what the row was previewed against."""
    rows = list(ProposalBatchRow.objects.filter(proposal=proposal).select_related("decided_by", "rejection_reason"))
    ids = [row.subject_id for row in rows]
    live = obligation_scope_terms(ids)
    headings = obligation_headings(ids, order)
    sources = {change["obligationId"]: change["source"] for change in proposal.payload.get("changes", [])}
    out = []
    for row in rows:
        heading = headings.get(row.subject_id)
        pending = row.decision == BatchRowDecision.PENDING.value
        out.append(
            ProposalBatchRowOut(
                id=row.id,
                subject_type=row.subject_type,
                subject_id=row.subject_id,
                target=None
                if heading is None
                else ProposalTarget(
                    id=row.subject_id,
                    title=heading.title,
                    reference_label=heading.reference_label,
                    instrument_short_name=heading.instrument_short_name,
                ),
                before=ProposalBatchRowPayload.model_validate(row.before),
                after=ProposalBatchRowPayload.model_validate(row.after),
                source=sources.get(str(row.subject_id), ""),
                stale=pending and sorted(live.get(row.subject_id, {})) != row.before.get("terms", []),
                decision=row.decision,
                rejection_code="" if row.rejection_reason is None else row.rejection_reason.key,
                decided_by=None if row.decided_by is None else ProposalActorRef(id=row.decided_by.id, name=row.decided_by.name),
                decided_at=row.decided_at,
            )
        )
    return ProposalBatch(**dict(logic.row(proposal)), rows=out)


def decide(*, proposal: Proposal, decision: ProposalBatchDecision, reviewer: Any, step_up_assertion_id: uuid.UUID) -> Proposal:
    """Decide a batch whole or row by row (PRO-S8). Declared ahead of its logic, which the
    decision half of the batch work fills: until then it answers 501 `not_built`, behind the
    route's real gate."""
    raise ProblemError(status=501, code="not_built", detail="Deciding a batch is not built yet.")
