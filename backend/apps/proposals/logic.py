"""Business logic of the proposals app (PRO-01, PRO-02, AC-PRO1, AC-PRO2, VOC-07).

A proposal is the only door into the library. People and agents create them here; a
second person approves one here, and apps/proposals/apply.py applies its payload inside
`library_write()` in the same transaction as the approval's audit row. Nothing here writes
a library row, which is why this module names no `LibraryModel` class (the library fence's
AST guard, apps/shared/tests_library_fence.py).

Four eyes (AC-PRO2) is checked here and by the `proposal_four_eyes` check constraint; the
API answers 409 `four_eyes_violation`. An agent's proposal has no proposing user, so any
reviewer may decide it.

Idempotency (playbook 4.3): an agent retries with the same `Idempotency-Key`. The same body
answers the proposal it already made (200, and an audit row saying the retry happened, so
a flapping agent shows in the log); a different body under the same key is 409
`idempotency_conflict`, because silently keeping either version would lose the other.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pydantic
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.proposals.models import OriginType, Proposal, ProposalKind, ProposalStatus
from apps.proposals.schemas import (
    ProposalActorRef,
    ProposalRow,
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
    ProposalVocabularyCreatePayload,
    ProposalVocabularyMergePayload,
    ProposalVocabularyRelabelPayload,
    ProposalVocabularyRetirePayload,
)
from apps.shared.audit import Actor, record

SUBJECT_TYPE = "proposal"

# The named payload schema per kind (PRO-01): apply() never reads a free-form dictionary.
PAYLOAD_SCHEMAS: dict[str, type[pydantic.BaseModel]] = {
    ProposalKind.VOCABULARY_CREATE.value: ProposalVocabularyCreatePayload,
    ProposalKind.VOCABULARY_RELABEL.value: ProposalVocabularyRelabelPayload,
    ProposalKind.VOCABULARY_RETIRE.value: ProposalVocabularyRetirePayload,
    ProposalKind.VOCABULARY_RESTORE.value: ProposalVocabularyRetirePayload,
    ProposalKind.VOCABULARY_MERGE.value: ProposalVocabularyMergePayload,
    ProposalKind.TERM_CREATE.value: ProposalTermCreatePayload,
    ProposalKind.TERM_UPDATE.value: ProposalTermUpdatePayload,
}
VOCABULARY_KINDS = frozenset(
    kind.value
    for kind in (
        ProposalKind.VOCABULARY_CREATE,
        ProposalKind.VOCABULARY_RELABEL,
        ProposalKind.VOCABULARY_RETIRE,
        ProposalKind.VOCABULARY_RESTORE,
        ProposalKind.VOCABULARY_MERGE,
    )
)


@dataclass(frozen=True)
class Proposer:
    """Who proposes: a person (session) or an agent (API key). Exactly one is set."""

    actor: Actor
    user: Any = None
    api_key_id: uuid.UUID | None = None
    agent_run_id: uuid.UUID | None = None

    @property
    def origin(self) -> OriginType:
        return OriginType.USER if self.user is not None else OriginType.AGENT


# ---------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------
def validated_kind(kind: str) -> str:
    valid = [member.value for member in ProposalKind]
    if kind not in valid:
        raise ValidationError(
            f"{kind!r} is not a proposal kind. Valid kinds: {', '.join(valid)}.", code="unknown_key"
        )
    return kind


def validated_payload(kind: str, payload: dict[str, Any]) -> pydantic.BaseModel:
    """The payload as its kind's named schema. A malformed payload is refused when the
    proposal is made, never when it is approved, so the queue holds nothing unappliable."""
    schema = PAYLOAD_SCHEMAS[kind]
    try:
        parsed = schema.model_validate(payload)
    except pydantic.ValidationError as exc:
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        raise ValidationError(f"The payload is incomplete: {fields}.", code="validation_error") from exc
    _validate_target(kind, parsed)
    return parsed


def _validate_target(kind: str, payload: pydantic.BaseModel) -> None:
    """A vocabulary proposal names a library list that can be proposed to; a term proposal
    names a dimension. Tenant lists never enter the queue: their admin writes them."""
    from apps.taxonomy.registry import REGISTRY

    if kind in VOCABULARY_KINDS:
        name = getattr(payload, "list", "")
        entry = REGISTRY.get(name)
        valid = sorted(n for n, e in REGISTRY.items() if e.is_library and e.proposable)
        if entry is None or not entry.is_library or not entry.proposable:
            raise ValidationError(
                f"{name!r} is not a library list a proposal can change. Valid lists: {', '.join(valid)}.",
                code="unknown_key",
            )
        if kind == ProposalKind.VOCABULARY_CREATE.value:
            from apps.taxonomy.tenant_lists_logic import validated_kind as validated_row_kind

            validated_row_kind(entry, getattr(payload, "kind", None))
    else:
        from apps.taxonomy.terms_logic import dimension_by_key

        dimension_by_key(getattr(payload, "dimension", ""))


def payload_dict(payload: pydantic.BaseModel) -> dict[str, Any]:
    return payload.model_dump(by_alias=True, exclude_none=True)


# ---------------------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------------------
def create(
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    proposer: Proposer,
    idempotency_key: str | None = None,
    target_type: str = "",
    target_id: uuid.UUID | None = None,
    change_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
    model: str = "",
    field_sources: dict[str, Any] | None = None,
    source_label: str = "",
    source_url: str = "",
    effective_from: Any = None,
) -> tuple[Proposal, bool]:
    """Create a proposal, or answer the one an earlier identical submission made. Returns
    `(proposal, created)`."""
    validated_kind(kind)
    parsed = validated_payload(kind, payload)
    stored_payload = payload_dict(parsed)
    title = title.strip()
    if not title:
        raise ValidationError("Give the proposal a title.", code="validation_error")
    if idempotency_key:
        existing = Proposal.objects.filter(idempotency_key=idempotency_key).order_by("created_at", "id").first()
        if existing is not None:
            if (existing.kind, existing.title, existing.payload) != (kind, title, stored_payload):
                raise ValidationError(
                    "This Idempotency-Key was already used for a different proposal.",
                    code="idempotency_conflict",
                )
            record(
                action="proposal.replayed",
                actor=proposer.actor,
                subject_type=SUBJECT_TYPE,
                subject_id=existing.id,
                subject_title=existing.title,
                summary="A retried submission answered the proposal it already made.",
                tenant_id=None,
                after={"idempotencyKey": idempotency_key},
            )
            return existing, False
    proposal = Proposal.objects.create(
        kind=kind,
        title=title,
        payload=stored_payload,
        field_sources=field_sources or {},
        target_type=target_type,
        target_id=target_id,
        change_id=change_id,
        model=model,
        source_label=source_label,
        source_url=source_url,
        effective_from=effective_from,
        origin=proposer.origin.value,
        agent_run_id=agent_run_id or proposer.agent_run_id,
        proposed_by_user=proposer.user,
        proposed_by_api_key_id=proposer.api_key_id,
        idempotency_key=idempotency_key or None,
        status=ProposalStatus.OPEN.value,
    )
    record(
        action="proposal.created",
        actor=proposer.actor,
        subject_type=SUBJECT_TYPE,
        subject_id=proposal.id,
        subject_title=proposal.title,
        summary=f"Proposed: {proposal.title}",
        tenant_id=None,
        after={"kind": kind, "payload": stored_payload, "origin": proposal.origin},
    )
    return proposal, True


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def queue(*, status: str | None = None, kind: str | None = None, target_list: str | None = None) -> Any:
    """The review queue, newest last, filtered by comma-separated `status` and `kind` and by
    `target_list`: the vocabulary list a vocabulary proposal changes (`payload.list`) or the
    dimension a term proposal changes (`payload.dimension`). The vocabulary screen's
    "Suggested" tab asks for `?status=open&kind=vocabulary_create,term_create&targetList=flag`."""
    queryset = Proposal.objects.select_related("proposed_by_user", "reviewed_by").order_by("created_at", "id")
    statuses = _csv(status)
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    kinds = _csv(kind)
    if kinds:
        queryset = queryset.filter(kind__in=kinds)
    if target_list:
        queryset = queryset.filter(Q(payload__list=target_list) | Q(payload__dimension=target_list))
    return queryset


def by_id(proposal_id: uuid.UUID) -> Proposal:
    proposal = (
        Proposal.objects.select_related("proposed_by_user", "reviewed_by").filter(pk=proposal_id).first()  # ordering: pk lookup, at most one row
    )
    if proposal is None:
        raise ValidationError("That proposal is not here.", code="not_found")
    return proposal


def _actor_ref(user: Any) -> ProposalActorRef | None:
    return None if user is None else ProposalActorRef(id=user.id, name=user.name)


def row(proposal: Proposal) -> ProposalRow:
    return ProposalRow(
        id=proposal.id,
        kind=proposal.kind,
        status=proposal.status,
        title=proposal.title,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        change_id=proposal.change_id,
        payload=proposal.payload,
        field_sources=proposal.field_sources,
        source_label=proposal.source_label,
        source_url=proposal.source_url,
        effective_from=proposal.effective_from,
        origin=proposal.origin,
        agent_run_id=proposal.agent_run_id,
        model=proposal.model,
        proposed_by=_actor_ref(proposal.proposed_by_user),
        reviewed_by=_actor_ref(proposal.reviewed_by),
        reviewed_at=proposal.reviewed_at,
        rejection_code=proposal.rejection_code,
        review_note=proposal.review_note,
        applied_at=proposal.applied_at,
        created_at=proposal.created_at,
    )


# ---------------------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------------------
def _decidable(proposal: Proposal, reviewer: Any) -> None:
    if proposal.status != ProposalStatus.OPEN.value:
        raise ValidationError("This proposal has already been decided.", code="invalid_transition")
    if proposal.proposed_by_user_id is not None and proposal.proposed_by_user_id == reviewer.id:
        raise ValidationError(
            "A proposal is decided by someone other than the person who made it.",
            code="four_eyes_violation",
        )


def approve(
    *, proposal: Proposal, reviewer: Any, actor: Actor, note: str, step_up_assertion_id: uuid.UUID
) -> Proposal:
    """Apply the payload and approve, in one transaction (PRO-02): the library row, its
    audit row and the proposal's own audit row commit together or not at all."""
    from apps.proposals import apply

    _decidable(proposal, reviewer)
    apply.apply(proposal, actor=actor)
    now = timezone.now()
    proposal.status = ProposalStatus.APPROVED.value
    proposal.reviewed_by = reviewer
    proposal.reviewed_at = now
    proposal.applied_at = now
    proposal.review_note = note.strip()
    proposal.save(update_fields=["status", "reviewed_by", "reviewed_at", "applied_at", "review_note"])
    record(
        action="proposal.approved",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=proposal.id,
        subject_title=proposal.title,
        summary=f"Approved: {proposal.title}",
        tenant_id=None,
        before={"status": ProposalStatus.OPEN.value},
        after={"status": proposal.status, "note": proposal.review_note},
        step_up_assertion_id=step_up_assertion_id,
    )
    return proposal


def reject(*, proposal: Proposal, reviewer: Any, actor: Actor, rejection_code: str, note: str) -> Proposal:
    """A rejection needs a reason (PRO-01): a code the proposer's screen can branch on and a
    sentence they can read. The outbox event is what tells them."""
    code = rejection_code.strip()
    text = note.strip()
    if not code or not text:
        raise ValidationError(
            "Say why: choose a reason and write a note the proposer will read.", code="reason_required"
        )
    _decidable(proposal, reviewer)
    proposal.status = ProposalStatus.REJECTED.value
    proposal.reviewed_by = reviewer
    proposal.reviewed_at = timezone.now()
    proposal.rejection_code = code
    proposal.review_note = text
    proposal.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_code", "review_note"])
    record(
        action="proposal.rejected",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=proposal.id,
        subject_title=proposal.title,
        summary=f"Rejected: {proposal.title}",
        tenant_id=None,
        before={"status": ProposalStatus.OPEN.value},
        after={"status": proposal.status, "rejectionCode": code, "note": text},
        topic="proposal.rejected",
    )
    return proposal
