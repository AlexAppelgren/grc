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
content.

`decide()` is the decision half (PRO-S8): a second person holding `proposals.review`, with a
fresh passkey, approves or rejects rows one by one and gives every row left pending one
decision. Approved rows are written by `apply.apply()` inside the proposal door; a rejected
row names a live reason from the `rejection_reason` list. One audit row per row and one more
naming every row's outcome, the library writes and their re-index commit together or not at
all. Who decides is a person: an agent reviewer is refused with 409
`person_review_required`, and the proposer with 409 `four_eyes_violation` before a single
row moves, beside the row trigger and the parent's `proposal_four_eyes` check, which stay
the database's word on it.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.agents import runs
from apps.agents.screen import screen_all
from apps.library.reading import active_shared_obligations, obligation_headings, obligation_scope_terms, terms_of, unknown_provision_keys
from apps.proposals import logic, standards
from apps.proposals.logic import Proposer, Reviewer
from apps.proposals.models import DECISION_FIELDS, BatchRowDecision, Proposal, ProposalBatchRow, ProposalKind, ProposalStatus
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
from apps.taxonomy.registry import REGISTRY
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


DECISIONS = (BatchRowDecision.APPROVED.value, BatchRowDecision.REJECTED.value)


def _reason(decision: str, code: str, reasons: dict[str, Any]) -> Any:
    """The `rejection_reason` row a rejection names, or None for an approval. A rejection
    without a live reason is 422 `reason_required`, as a single proposal's is; an approval
    that names one is a contradiction, 422 `validation_error`."""
    if decision not in DECISIONS:
        raise ValidationError(f"{decision!r} is not a decision. Valid decisions: {', '.join(DECISIONS)}.", code="validation_error")
    code = code.strip()
    if decision == BatchRowDecision.APPROVED.value:
        if code:
            raise ValidationError("An approval takes no rejection reason.", code="validation_error")
        return None
    if code not in reasons:
        reasons[code] = REGISTRY[logic.REJECTION_REASON_LIST].model.objects.filter(key=code, active=True).first() if code else None  # ordering: unique key, at most one row
    if reasons[code] is None:
        raise ValidationError("Say why: choose a live reason from the rejection reason list for every rejected row.", code="reason_required")
    return reasons[code]


def _decisions(decision: ProposalBatchDecision) -> tuple[dict[uuid.UUID, tuple[str, Any]], tuple[str, Any] | None]:
    """The body as decisions with their reason rows, checked before anything is locked."""
    reasons: dict[str, Any] = {}
    named: dict[uuid.UUID, tuple[str, Any]] = {}
    for row in decision.rows:
        if row.row_id in named:
            raise ValidationError(f"Name each row once. Repeated: {row.row_id}.", code="validation_error")
        named[row.row_id] = (row.decision, _reason(row.decision, row.rejection_code, reasons))
    rest = None if decision.rest is None else (decision.rest, _reason(decision.rest, decision.rest_rejection_code, reasons))
    if decision.rest is None and decision.rest_rejection_code.strip():
        raise ValidationError("restRejectionCode goes with a rest that is rejected.", code="validation_error")
    if not named and rest is None:
        raise ValidationError("Decide at least one row, or give the rest a decision.", code="validation_error")
    return named, rest


def decide(*, proposal: Proposal, decision: ProposalBatchDecision, reviewer: Reviewer, step_up_assertion_id: uuid.UUID | None) -> Proposal:
    """Decide a batch whole or row by row (PRO-04, PRO-S8), in one transaction of its own.

    Refused before anything is locked or written: an agent reviewer (409
    `person_review_required`: a re-tag batch is decided by a person), a caller inside a bank
    (403), and a malformed body. Then, under the batch's lock, a decided batch is 409
    `invalid_transition`, and the batch's proposer is 409 `four_eyes_violation`, the call
    deciding nothing at all. The proposer is the person who asked for the re-tag: the
    console's form files it in their name. A row named that does not belong to the batch is
    422 `unknown_key`, and one already decided is 409 `invalid_transition`.

    A pending row whose record was retired or moved since the batch was filed is stale: named
    for approval it is 409 `stale_write` and nothing is decided; under an approved `rest` it
    is left pending, so the others still apply and the reviewer rejects it. The batch closes
    only when no row is pending: approved if any row was, else rejected with the rows' shared
    reason. The note stays on the proposal row, never in an audit value."""
    from apps.proposals import apply

    if reviewer.user is None:
        raise ValidationError("A person decides a batch: an agent cannot approve or reject its rows.", code="person_review_required")
    if tenancy.database_tenant_id() is not None:
        raise ProblemError(status=403, code="permission_denied", detail="A bank does not decide the shared library's batches.")
    named, rest = _decisions(decision)
    with transaction.atomic():
        proposal.refresh_from_db(from_queryset=Proposal.objects.select_for_update())
        if proposal.status != ProposalStatus.OPEN.value:
            raise ValidationError("This batch has already been decided.", code="invalid_transition")
        if proposal.proposed_by_user_id == reviewer.user.id:
            raise ValidationError("A batch is decided by someone other than the person who asked for it.", code="four_eyes_violation")
        rows = list(
            ProposalBatchRow.objects.select_for_update(of=("self",))
            .select_related("rejection_reason")
            .filter(proposal=proposal)
            .order_by("subject_type", "subject_id")
        )
        unknown = sorted(str(row_id) for row_id in set(named) - {row.id for row in rows})
        if unknown:
            raise ValidationError(f"Not a row of this batch: {', '.join(unknown)}.", code="unknown_key")
        pending = [row for row in rows if row.decision == BatchRowDecision.PENDING.value]
        decided = [row for row in rows if row.id in named and row.decision != BatchRowDecision.PENDING.value]
        if decided:
            raise ValidationError("A row is decided once, and this call names one already decided.", code="invalid_transition")
        ids = [row.subject_id for row in pending]
        in_force = active_shared_obligations(ids)
        live = obligation_scope_terms(ids)
        stale = {row.id for row in pending if row.subject_id not in in_force or sorted(live.get(row.subject_id, {})) != row.before.get("terms", [])}
        chosen: list[tuple[ProposalBatchRow, str, Any]] = []
        for row in pending:
            given = named.get(row.id, rest)
            if given is None:
                continue
            if given[0] == BatchRowDecision.APPROVED.value and row.id in stale:
                if row.id in named:
                    raise ValidationError("A row whose record changed after the batch was filed cannot be approved: reject it.", code="stale_write")
                continue
            chosen.append((row, *given))
        if not chosen:
            raise ValidationError("Every row left to approve changed after the batch was filed: reject them.", code="stale_write")
        approved = [row for row, outcome, _ in chosen if outcome == BatchRowDecision.APPROVED.value]
        if approved:
            apply.apply(proposal, actor=reviewer.actor, reviewer=reviewer, step_up=step_up_assertion_id, rows=approved)
        now = timezone.now()
        for row, outcome, reason in chosen:
            row.decision, row.rejection_reason, row.decided_by, row.decided_at = outcome, reason, reviewer.user, now
            row.save(update_fields=list(DECISION_FIELDS))
            if reason is not None:
                record(
                    action="proposal.batch_row_rejected",
                    actor=reviewer.actor,
                    subject_type=OBLIGATION,
                    subject_id=row.subject_id,
                    subject_title=proposal.title,
                    summary=f"Kept the scope as it is: a row of {proposal.title} was rejected.",
                    tenant_id=None,
                    before={"terms": row.before.get("terms", [])},
                    after={"decision": outcome, "rejectionCode": reason.key, "proposal": str(proposal.id), "batchRow": str(row.id)},
                    step_up_assertion_id=step_up_assertion_id,
                )
        _close(proposal, rows, reviewer, now, decision.note.strip())
        record(
            action="proposal.batch_decided",
            actor=reviewer.actor,
            subject_type=logic.SUBJECT_TYPE,
            subject_id=proposal.id,
            subject_title=proposal.title,
            summary=f"Decided {len(chosen)} of {len(rows)} rows: {proposal.title}",
            tenant_id=None,
            before={"status": ProposalStatus.OPEN.value},
            after={
                "status": proposal.status,
                "rows": [
                    {
                        "rowId": str(row.id),
                        "subjectId": str(row.subject_id),
                        "decision": row.decision,
                        "rejectionCode": "" if row.rejection_reason is None else row.rejection_reason.key,
                    }
                    for row in rows
                ],
            },
            step_up_assertion_id=step_up_assertion_id,
        )
    return proposal


def _close(proposal: Proposal, rows: list[ProposalBatchRow], reviewer: Reviewer, now: Any, note: str) -> None:
    """Keep the reviewer's note on the batch, and close it once no row is pending: approved
    if any row was, else rejected with the reason its rows share (none when they differ).
    The parent's `proposal_four_eyes` check refuses the proposer here too."""
    fields = ["review_note"] if note else []
    proposal.review_note = note or proposal.review_note
    if all(row.decision != BatchRowDecision.PENDING.value for row in rows):
        approved = any(row.decision == BatchRowDecision.APPROVED.value for row in rows)
        reasons = {row.rejection_reason.key for row in rows if row.rejection_reason is not None}
        proposal.status = ProposalStatus.APPROVED.value if approved else ProposalStatus.REJECTED.value
        proposal.reviewed_by = reviewer.user
        proposal.reviewed_at = now
        proposal.applied_at = now if approved else None
        proposal.rejection_code = "" if approved or len(reasons) != 1 else reasons.pop()
        fields += ["status", "reviewed_by", "reviewed_at", "applied_at", "rejection_code"]
    if fields:
        proposal.save(update_fields=fields)
