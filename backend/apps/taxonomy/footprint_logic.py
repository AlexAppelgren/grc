"""The footprint and its change requests (FP-01, FP-02, AC-FP1, J-6).

A footprint change has a wide blast radius: every feed, inventory, roadmap, briefing and
report is filtered by it (FP-03). So it is never a direct write. A requester creates a
`FootprintChangeRequest` with a preview of what the change would hide and reveal; a second
person approves it with a fresh passkey assertion; the approval switches the terms, writes
one audit event and one `footprint_history` row per term, in one transaction.

This module writes, so it names no library model class: the terms it adds and removes
arrive as rows from apps/taxonomy/terms_logic.py, and the read half of the footprint lives
there too. The library fence's AST guard refuses any module that both names a
`LibraryModel` and calls a write method (apps/shared/tests_library_fence.py).

The preview counts per record kind. Obligations are counted; cases answer zero with
`available: false` until chunk 9 builds them, because "not counted" and "none" are
different answers and a screen that cannot tell them apart would lie to the person
deciding (playbook 4.4).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.library import reading
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy import markets_logic, matching, terms_logic
from apps.taxonomy.models import (
    ApprovalStatus,
    FootprintAction,
    FootprintChangeAdd,
    FootprintChangeRemove,
    FootprintChangeRequest,
    FootprintHistory,
    FootprintTerm,
)
from apps.taxonomy.schemas import (
    FootprintDimension,
    FootprintDryRun,
    FootprintPreview,
    FootprintPreviewCount,
    FootprintRequestRow,
    FootprintView,
    PersonRef,
    TermRef,
)

SUBJECT_TYPE = "footprint"
REQUEST_SUBJECT_TYPE = "footprint_change_request"


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def view(tenant_id: uuid.UUID, order: list[str]) -> FootprintView:
    """The footprint screen's data (FP-01): every dimension, the terms this company carries
    in it, whether it restricts the footprint at all, the pending request if one waits, and
    every active country's market level (FP-04). A dimension with no terms is not an error
    and not an omission: it means "no restriction", which the screen says in words
    (playbook 4.5)."""
    selected = terms_logic.selected_terms_by_dimension(tenant_id, order)
    dimensions: list[FootprintDimension] = []
    for ref, restricts, term_count in terms_logic.dimensions_for_footprint(order):
        terms: list[TermRef] = selected.get(ref.key, [])
        dimensions.append(
            FootprintDimension(
                dimension=ref,
                restricts_footprint=restricts,
                terms=terms,
                all_selected=bool(term_count) and len(terms) == term_count,
            )
        )
    return FootprintView(
        dimensions=dimensions,
        pending_request=pending_row(tenant_id, order),
        markets=markets_logic.markets_of(tenant_id, order),
    )


def pending(tenant_id: uuid.UUID) -> FootprintChangeRequest | None:
    return (
        FootprintChangeRequest.objects.filter(tenant_id=tenant_id, status=ApprovalStatus.PENDING.value)
        .order_by("requested_at", "id")
        .first()
    )


def pending_row(tenant_id: uuid.UUID, order: list[str]) -> FootprintRequestRow | None:
    request = pending(tenant_id)
    return None if request is None else request_row(request, order)


def requests_of(tenant_id: uuid.UUID) -> list[FootprintChangeRequest]:
    return list(
        FootprintChangeRequest.objects.filter(tenant_id=tenant_id)
        .select_related("requested_by", "decided_by")
        .order_by("-requested_at", "id")
    )


def _person(user: Any) -> PersonRef | None:
    # A person's name and id may be logged and shown; nothing else about them (playbook 4.7).
    return None if user is None else PersonRef(id=user.id, name=user.name)


def request_row(request: FootprintChangeRequest, order: list[str]) -> FootprintRequestRow:
    adds, removes = _changes(request)
    return FootprintRequestRow(
        id=request.id,
        status=request.status,
        requested_by=_person(request.requested_by),
        requested_at=request.requested_at,
        adds=terms_logic.labelled_term_refs(adds, order),
        removes=terms_logic.labelled_term_refs(removes, order),
        preview=_preview_now(request, adds, removes),
        decided_by=_person(request.decided_by),
        decided_at=request.decided_at,
        decision_note=request.decision_note,
        version=request.version,
    )


# ---------------------------------------------------------------------------------------
# The preview (AC-FP1)
# ---------------------------------------------------------------------------------------
def _after(now: dict[str, set[str]], adds: list[Any], removes: list[Any]) -> dict[str, set[str]]:
    """The footprint the change would leave behind."""
    after = {dimension: set(keys) for dimension, keys in now.items()}
    for term in adds:
        after.setdefault(term.dimension.key, set()).add(term.key)
    for term in removes:
        after.get(term.dimension.key, set()).discard(term.key)
    return after


def preview_of(tenant_id: uuid.UUID, adds: list[Any], removes: list[Any]) -> FootprintPreview:
    """What the change would hide and reveal, per record kind (AC-FP1). Hidden means in
    scope now and out of it afterwards; revealed is the other way. The count runs the pure
    matching rule twice over the scope of every obligation this company can see (the
    library's one scope rule, `reading.obligation_scopes`, under row-level security),
    because the SQL function reads the stored footprint and this asks about one that does
    not exist yet. An obligation with no scope matches both and is not listed. Cases answer
    `available: false` until chunk 9, and this function grows one branch per kind as they
    land."""
    now = matching.footprint_of(tenant_id)
    after = _after(now, adds, removes)
    restricting = matching.restricting_dimensions()
    hidden = revealed = 0
    for scope in reading.obligation_scopes().values():
        record_terms = {dimension: {term.key for term in terms} for dimension, terms in scope.items()}
        was_in = matching.in_footprint(record_terms, now, restricting=restricting)
        is_in = matching.in_footprint(record_terms, after, restricting=restricting)
        if was_in and not is_in:
            hidden += 1
        elif is_in and not was_in:
            revealed += 1
    return FootprintPreview(
        obligations=FootprintPreviewCount(hidden=hidden, revealed=revealed, available=True),
        cases=FootprintPreviewCount(hidden=0, revealed=0, available=False),
    )


def _changes(request: FootprintChangeRequest) -> tuple[list[Any], list[Any]]:
    """The terms a request would switch on and off, in the picker's order."""
    order = ("dimension__sort_order", "sort_order", "key")
    return (
        list(request.adds.select_related("dimension").order_by(*order)),
        list(request.removes.select_related("dimension").order_by(*order)),
    )


def _preview_now(request: FootprintChangeRequest, adds: list[Any], removes: list[Any]) -> FootprintPreview:
    """A waiting request is recounted every time it is read, so the approver decides against
    today's library rather than against whatever it held when the request was made. A
    decided request keeps the counts it was decided against."""
    if request.status == ApprovalStatus.PENDING.value:
        return preview_of(request.tenant_id, adds, removes)
    return FootprintPreview(**request.preview) if request.preview else FootprintPreview()


def dry_run(tenant_id: uuid.UUID, adds: list[Any], removes: list[Any], order: list[str]) -> FootprintDryRun:
    """The requester's preview before sending (playbook 15: dry run, preview, commit). The
    same validation as a real request, the same preview, and nothing written: no request
    row, no audit event, no approval started. A preview is a read that needs a body."""
    _validate_change(tenant_id, adds, removes)
    return FootprintDryRun(
        adds=terms_logic.labelled_term_refs(adds, order),
        removes=terms_logic.labelled_term_refs(removes, order),
        preview=preview_of(tenant_id, adds, removes),
        dry_run=True,
    )


def _validate_change(tenant_id: uuid.UUID, adds: list[Any], removes: list[Any]) -> None:
    if not adds and not removes:
        raise ValidationError("Choose at least one term to add or remove.", code="validation_error")
    both = {term.id for term in adds} & {term.id for term in removes}
    if both:
        raise ValidationError("A term cannot be added and removed in the same change.", code="validation_error")


# ---------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------
def _term_state(term: Any, request: FootprintChangeRequest | None) -> dict[str, str]:
    """A term event's before or after: the term, and the request that caused it when one
    did, so the audit log ties each term to its request without matching step-up ids."""
    state = {"dimension": term.dimension.key, "term": term.key}
    if request is not None:
        state["request"] = str(request.id)
    return state


def _switch_on(
    *,
    tenant: Tenant,
    actor: Actor,
    terms: list[Any],
    request: FootprintChangeRequest | None,
    step_up_assertion_id: uuid.UUID | None,
    added_by: Any = None,
) -> int:
    """Add terms to the footprint: one `footprint_term` row, one history row and one audit
    event per term (FP-02: "one audit event per term", so the log reads as decisions about
    one term each rather than a blob nobody can diff)."""
    count = 0
    for term in terms:
        row, created = FootprintTerm.objects.get_or_create(
            tenant=tenant, term=term, defaults={"added_by": added_by}
        )
        if not created:
            continue
        FootprintHistory.objects.create(
            tenant=tenant,
            term=term,
            action=FootprintAction.ADDED.value,
            request=request,
            changed_by=added_by,
            step_up_assertion_id=step_up_assertion_id,
        )
        record(
            action="footprint.term_added",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=row.id,
            subject_title=f"{term.dimension.key}:{term.key}",
            summary=f"Added {term.dimension.key}:{term.key} to the footprint.",
            tenant_id=tenant.id,
            after=_term_state(term, request),
            step_up_assertion_id=step_up_assertion_id,
        )
        count += 1
    return count


def _switch_off(
    *,
    tenant: Tenant,
    actor: Actor,
    terms: list[Any],
    request: FootprintChangeRequest | None,
    step_up_assertion_id: uuid.UUID | None,
    changed_by: Any = None,
) -> int:
    count = 0
    for term in terms:
        row = FootprintTerm.objects.filter(tenant=tenant, term=term).order_by("added_at", "id").first()
        if row is None:
            continue
        row.delete()
        FootprintHistory.objects.create(
            tenant=tenant,
            term=term,
            action=FootprintAction.REMOVED.value,
            request=request,
            changed_by=changed_by,
            step_up_assertion_id=step_up_assertion_id,
        )
        record(
            action="footprint.term_removed",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=row.id,
            subject_title=f"{term.dimension.key}:{term.key}",
            summary=f"Removed {term.dimension.key}:{term.key} from the footprint.",
            tenant_id=tenant.id,
            before=_term_state(term, request),
            step_up_assertion_id=step_up_assertion_id,
        )
        count += 1
    return count


def seed_terms(*, tenant: Tenant, actor: Actor, terms: list[Any]) -> int:
    """The E2E seed's way in (playbook 8.3): the same writes an approval makes, with a
    system actor and no step-up assertion, so a seeded footprint has the same history rows
    as one a person built and the "as of" reconstruction never has a hole."""
    return _switch_on(tenant=tenant, actor=actor, terms=terms, request=None, step_up_assertion_id=None)


def create_request(
    *,
    tenant: Tenant,
    requester: Any,
    actor: Actor,
    adds: list[Any],
    removes: list[Any],
) -> FootprintChangeRequest:
    """One pending request at a time (409 `request_pending`): two people editing the same
    footprint from two previews would each approve a change the other's preview never
    counted. The partial unique constraint `footprint_change_request_one_pending` decides,
    so two requests sent at the same moment cannot both wait; the savepoint keeps the
    caller's transaction usable after the refusal."""
    _validate_change(tenant.id, adds, removes)
    try:
        with transaction.atomic():
            request = FootprintChangeRequest.objects.create(
                tenant=tenant,
                requested_by=requester,
                preview=preview_of(tenant.id, adds, removes).model_dump(by_alias=True),
            )
    except IntegrityError as exc:
        # Only our constraint means "a change already waits"; any other refusal is a fault.
        diag = getattr(exc.__cause__, "diag", None)
        if getattr(diag, "constraint_name", None) != "footprint_change_request_one_pending":
            raise
        raise ValidationError(
            "A footprint change is already waiting for a decision.", code="request_pending"
        ) from exc
    for term in adds:
        FootprintChangeAdd.objects.create(tenant=tenant, request=request, term=term)
    for term in removes:
        FootprintChangeRemove.objects.create(tenant=tenant, request=request, term=term)
    record(
        action="footprint.change_requested",
        actor=actor,
        subject_type=REQUEST_SUBJECT_TYPE,
        subject_id=request.id,
        subject_title=f"{len(adds)} added, {len(removes)} removed",
        summary="Requested a footprint change.",
        tenant_id=tenant.id,
        after={
            "adds": [f"{term.dimension.key}:{term.key}" for term in adds],
            "removes": [f"{term.dimension.key}:{term.key}" for term in removes],
        },
    )
    return request


def _decidable(request: FootprintChangeRequest, expected_version: int | None) -> None:
    """Lock the row, then check status and version under the lock (FP-S6). Two decisions on
    one request queue on the lock, and the second reads what the first committed: 409
    `invalid_transition`, never a stale "pending" that lets both land."""
    request.refresh_from_db(from_queryset=FootprintChangeRequest.objects.select_for_update())
    if request.status != ApprovalStatus.PENDING.value:
        raise ValidationError(
            "This footprint change has already been decided.", code="invalid_transition"
        )
    if expected_version is not None and expected_version != request.version:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")


def approve(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    decider: Any,
    actor: Actor,
    note: str,
    step_up_assertion_id: uuid.UUID,
    expected_version: int | None = None,
) -> FootprintChangeRequest:
    """The second person's decision (FP-02, AC-FP1). Four eyes is checked here and by the
    `footprint_change_request_four_eyes` check constraint, which is the database's word on
    it; the API answers 409 `four_eyes_violation`."""
    _decidable(request, expected_version)
    if request.requested_by_id == decider.id:
        raise ValidationError(
            "A footprint change is approved by someone other than the person who asked for it.",
            code="four_eyes_violation",
        )
    adds, removes = _changes(request)
    # Counted before the switch, against the footprint the approver was looking at.
    counted = preview_of(tenant.id, adds, removes)
    _switch_on(
        tenant=tenant,
        actor=actor,
        terms=adds,
        request=request,
        step_up_assertion_id=step_up_assertion_id,
        added_by=decider,
    )
    _switch_off(
        tenant=tenant,
        actor=actor,
        terms=removes,
        request=request,
        step_up_assertion_id=step_up_assertion_id,
        changed_by=decider,
    )
    return _decide(
        tenant=tenant,
        request=request,
        decider=decider,
        actor=actor,
        note=note,
        status=ApprovalStatus.APPROVED,
        action="footprint.change_approved",
        step_up_assertion_id=step_up_assertion_id,
        preview=counted,
    )


def reject(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    decider: Any,
    actor: Actor,
    note: str,
    expected_version: int | None = None,
) -> FootprintChangeRequest:
    _decidable(request, expected_version)
    if request.requested_by_id == decider.id:
        raise ValidationError(
            "A footprint change is decided by someone other than the person who asked for it.",
            code="four_eyes_violation",
        )
    return _decide(
        tenant=tenant,
        request=request,
        decider=decider,
        actor=actor,
        note=note,
        status=ApprovalStatus.REJECTED,
        action="footprint.change_rejected",
        step_up_assertion_id=None,
        preview=preview_of(tenant.id, *_changes(request)),
    )


def withdraw(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    requester: Any,
    actor: Actor,
    expected_version: int | None = None,
) -> FootprintChangeRequest:
    """Only the person who asked may take it back; anyone else gets 403 (the route checks
    it), because withdrawing is not a decision and must not become a way around four eyes."""
    _decidable(request, expected_version)
    return _decide(
        tenant=tenant,
        request=request,
        decider=None,
        actor=actor,
        note="",
        status=ApprovalStatus.WITHDRAWN,
        action="footprint.change_withdrawn",
        step_up_assertion_id=None,
        preview=preview_of(tenant.id, *_changes(request)),
    )


def _decide(
    *,
    tenant: Tenant,
    request: FootprintChangeRequest,
    decider: Any,
    actor: Actor,
    note: str,
    status: ApprovalStatus,
    action: str,
    step_up_assertion_id: uuid.UUID | None,
    preview: FootprintPreview,
) -> FootprintChangeRequest:
    """Every decision — approved, rejected, withdrawn — stores the counts it was taken
    against on the request and in its audit row, so a decided request never shows the
    counts from when it was sent."""
    before = {"status": request.status, "version": request.version}
    request.status = status.value
    request.decided_by = decider
    request.decided_at = timezone.now()
    request.decision_note = note
    request.version += 1
    request.preview = preview.model_dump(by_alias=True)
    request.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "version", "preview"])
    after: dict[str, Any] = {"status": status.value, "version": request.version, "note": note, "preview": request.preview}
    record(
        action=action,
        actor=actor,
        subject_type=REQUEST_SUBJECT_TYPE,
        subject_id=request.id,
        subject_title=str(request.id),
        summary=f"Footprint change {status.value}.",
        tenant_id=tenant.id,
        before=before,
        after=after,
        step_up_assertion_id=step_up_assertion_id,
    )
    return request
