"""Business logic of the proposals app (PRO-01, PRO-02, AC-PRO1, AC-PRO2, VOC-07).

A proposal is the only door into the library. People and agents create them here; a
second person approves one here, and apps/proposals/apply.py applies its payload inside
`library_write()` in the same transaction as the approval's audit row. Nothing here writes
a library row, which is why this module names no `LibraryModel` class (the library fence's
AST guard, apps/shared/tests_library_fence.py); the library rows a proposal points at and
cites are looked up through apps/library/reading.py, which is where every library read
lives.

Four eyes (AC-PRO2) is checked here and by the `proposal_four_eyes` check constraint; the
API answers 409 `four_eyes_violation`. An agent's proposal has no proposing user, so any
reviewer may decide it.

A proposal made inside a tenant (a bank's own person or its agent key) is linked to that
tenant through `ProposalTenant`, a tenant table under forced row-level security, and its
creation is audited under that tenant. The `proposal` row itself carries only the boolean
`proposed_in_tenant`, so the console can withhold the proposer's identity (PRO-03) without
learning which bank they work for.

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
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Q
from django.utils import timezone

from apps.library.models import DatePrecision
from apps.library.reading import active_obligation, terms_of, unknown_provision_keys
from apps.proposals.models import OriginType, Proposal, ProposalKind, ProposalStatus, ProposalTenant
from apps.proposals.schemas import (
    ProposalActorRef,
    ProposalObligationVersionPayload,
    ProposalRow,
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
    ProposalVocabularyCreatePayload,
    ProposalVocabularyMergePayload,
    ProposalVocabularyRelabelPayload,
    ProposalVocabularyRetirePayload,
)
from apps.shared import tenancy
from apps.shared.audit import Actor, record

SUBJECT_TYPE = "proposal"
# What an obligation proposal points at (schema v0.3 `subject_type`).
OBLIGATION_TARGET = "obligation"

# The named payload schema per kind (PRO-01): apply() never reads a free-form dictionary.
PAYLOAD_SCHEMAS: dict[str, type[pydantic.BaseModel]] = {
    ProposalKind.VOCABULARY_CREATE.value: ProposalVocabularyCreatePayload,
    ProposalKind.VOCABULARY_RELABEL.value: ProposalVocabularyRelabelPayload,
    ProposalKind.VOCABULARY_RETIRE.value: ProposalVocabularyRetirePayload,
    ProposalKind.VOCABULARY_RESTORE.value: ProposalVocabularyRetirePayload,
    ProposalKind.VOCABULARY_MERGE.value: ProposalVocabularyMergePayload,
    ProposalKind.TERM_CREATE.value: ProposalTermCreatePayload,
    ProposalKind.TERM_UPDATE.value: ProposalTermUpdatePayload,
    ProposalKind.NEW_OBLIGATION_VERSION.value: ProposalObligationVersionPayload,
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
OBLIGATION_KINDS = frozenset({ProposalKind.NEW_OBLIGATION_VERSION.value})
# The payloads that name a row by key and carry labels: the key must be its own slug and
# the labels real languages, as the vocabulary routes make them.
NAMED_PAYLOADS = (
    ProposalVocabularyCreatePayload,
    ProposalVocabularyRelabelPayload,
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
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


def parsed_payload(kind: str, payload: dict[str, Any]) -> pydantic.BaseModel:
    """The payload as its kind's named schema, or a 422 naming the fields to fix. Run when
    a proposal is made and again when it is applied, so a stored payload that no longer
    parses is a refusal the reviewer can act on, never a 500."""
    try:
        return PAYLOAD_SCHEMAS[kind].model_validate(payload)
    except pydantic.ValidationError as exc:
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        raise ValidationError(f"Fix these payload fields: {fields}.", code="validation_error") from exc


def validated_payload(kind: str, payload: dict[str, Any]) -> pydantic.BaseModel:
    """The payload as its kind's named schema, checked as the vocabulary routes check it. A
    malformed payload is refused when the proposal is made, never when it is approved, so
    the queue holds nothing unappliable."""
    parsed = parsed_payload(kind, payload)
    _validate_target(kind, parsed)
    return parsed


def _validate_target(kind: str, payload: pydantic.BaseModel) -> None:
    """A vocabulary proposal names a library list that can be proposed to; a term proposal
    names a dimension. Tenant lists never enter the queue: their admin writes them. An
    editor or an agent can post a payload without the vocabulary routes, so their checks
    run here too: labels in real languages (stored trimmed), a key that is its own slug,
    and an `extra` that holds only the list's own columns, each a value of its type and
    stored cleaned, so the queue shows what approval writes. That allowlist is also what
    keeps a tone or a colour out of the queue (NFR-S10)."""
    from pydantic.alias_generators import to_camel

    from apps.taxonomy import tenant_lists_logic as lists
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
        if isinstance(payload, ProposalVocabularyCreatePayload):
            lists.validated_kind(entry, payload.kind)
        if isinstance(payload, ProposalVocabularyCreatePayload | ProposalVocabularyRelabelPayload) and payload.extra:
            columns = {to_camel(column) for column in entry.extra_fields} | set(entry.extra_fields)
            unknown = sorted(set(payload.extra) - columns)
            if unknown:
                named = ", ".join(to_camel(column) for column in entry.extra_fields) or "none"
                raise ValidationError(
                    f"{', '.join(unknown)} is not a column of {name!r}. Valid columns: {named}.", code="validation_error"
                )
            payload.extra = lists.extra_payload(entry, payload.extra)
    elif isinstance(payload, ProposalObligationVersionPayload):
        _validate_obligation_payload(payload)
    else:
        from apps.taxonomy.terms_logic import dimension_by_key

        dimension_by_key(getattr(payload, "dimension", ""))
    if isinstance(payload, ProposalVocabularyCreatePayload | ProposalTermCreatePayload):
        payload.labels = lists.validated_labels(payload.labels)
    elif isinstance(payload, ProposalVocabularyRelabelPayload | ProposalTermUpdatePayload) and payload.labels:
        payload.labels = lists.validated_labels(payload.labels)
    if isinstance(payload, NAMED_PAYLOADS) and (not payload.key or lists.key_for(payload.labels, payload.key) != payload.key):
        raise ValidationError(
            f"{payload.key!r} is not a key: use lowercase letters, digits and underscores.", code="validation_error"
        )


def _validate_obligation_payload(payload: ProposalObligationVersionPayload) -> None:
    """A new obligation version carries the summary in real content languages, one of them
    the original it was written in (INV-05), a legal date with a precision (INV-S10), and
    scope terms that exist, written as `dimension:key` (FP-01)."""
    from apps.taxonomy import tenant_lists_logic as lists

    payload.summaries = lists.validated_labels(payload.summaries)
    if payload.original_language not in payload.summaries:
        raise ValidationError(
            f"{payload.original_language!r} is not one of the languages the summary is written in: "
            f"{', '.join(sorted(payload.summaries))}.",
            code="validation_error",
        )
    precisions = [member.value for member in DatePrecision]
    if payload.effective_from_precision not in precisions:
        raise ValidationError(
            f"{payload.effective_from_precision!r} is not a date precision. "
            f"Valid values: {', '.join(precisions)}.",
            code="unknown_key",
        )
    if payload.terms:
        # Stored once each, in the order given: the apply replaces the obligation's term
        # links, and a repeated ref would break its uniqueness constraint after approval.
        payload.terms = list(dict.fromkeys(payload.terms))
        terms_of(payload.terms)


def _validate_obligation_target(kind: str, target_type: str, target_id: uuid.UUID | None) -> None:
    """An obligation proposal says which obligation it versions, and that obligation is
    here and in force. A proposal nobody could ever apply never enters the queue."""
    if kind not in OBLIGATION_KINDS:
        return
    if target_type != OBLIGATION_TARGET or target_id is None:
        raise ValidationError(
            f"Say which obligation this version belongs to: targetType {OBLIGATION_TARGET!r} and its id.",
            code="validation_error",
        )
    active_obligation(target_id)


def sourced_fields(payload: pydantic.BaseModel) -> list[str]:
    """The fields of `payload` that a source has to be given for, named as the console
    names them beside the diff: the summary per language, the effective date and the scope
    terms. A vocabulary payload carries a label a person writes, not a sourced fact from an
    authority, so it names none (its chunk 2 rules are unchanged)."""
    if not isinstance(payload, ProposalObligationVersionPayload):
        return []
    fields = [f"summaries.{language}" for language in sorted(payload.summaries)]
    if payload.effective_from is not None:
        fields.append("effectiveFrom")
    if payload.terms is not None:
        fields.append("terms")
    return fields


def sourceable_fields(payload: pydantic.BaseModel) -> list[str]:
    """The fields `field_sources` may name. For an obligation version they are exactly the
    fields that need a source; for a vocabulary payload, whose wording a person writes,
    they are the payload's own fields and none of them is required. A key naming anything
    else is a source for nothing, so it is refused rather than stored."""
    if isinstance(payload, ProposalObligationVersionPayload):
        return sourced_fields(payload)
    return sorted(payload.model_dump(by_alias=True, exclude_none=True))


# An https link, the shape the library stores a source in (`Obligation.source_url`).
# https only: a source is fetched and shown as the provenance of a legal fact.
_LINK = URLValidator(schemes=["https"])


def check_field_sources(payload: pydantic.BaseModel, field_sources: dict[str, str]) -> None:
    """Every changed field carries the source its value came from, and nothing else does
    (PRO-01, AC-PRO1): 422 `source_missing` for a field without one, 422
    `validation_error` for a source that is not one.

    The one function for that rule: it runs when the proposal is made and again over a
    reviewer's corrections at approval, so a value nobody can trace to a source never
    reaches the library, whoever last touched it.

    An agent writes these values and a reviewer and the console read them, so each one is
    checked here at the boundary rather than trusted: at most
    `PROPOSAL_SOURCE_MAX_CHARS`, and either an https link or the stable key of a provision
    the library holds. "n/a", "see above" and `javascript:` are none of those.
    """
    missing = [field for field in sourced_fields(payload) if not field_sources.get(field, "").strip()]
    if missing:
        raise ValidationError(
            f"Give the source of every changed field. Missing: {', '.join(missing)}.", code="source_missing"
        )
    allowed = sourceable_fields(payload)
    stray = sorted(set(field_sources) - set(allowed))
    if stray:
        raise ValidationError(
            f"{', '.join(stray)}: this proposal changes no such field. "
            f"Fields a source belongs to: {', '.join(allowed) or 'none'}.",
            code="validation_error",
        )
    long = [field for field, source in field_sources.items() if len(source) > settings.PROPOSAL_SOURCE_MAX_CHARS]
    if long:
        raise ValidationError(
            f"A source is at most {settings.PROPOSAL_SOURCE_MAX_CHARS} characters. Too long: {', '.join(long)}.",
            code="validation_error",
        )
    refs = {field: source for field, source in field_sources.items() if not _is_link(source)}
    unknown = unknown_provision_keys(set(refs.values()))
    unfollowable = sorted(field for field, ref in refs.items() if ref in unknown)
    if unfollowable:
        raise ValidationError(
            "A source is an https link or the stable key of a provision in the library. "
            f"Not a source: {', '.join(unfollowable)}.",
            code="validation_error",
        )


def _is_link(value: str) -> bool:
    try:
        _LINK(value)
    except ValidationError:
        return False
    return True


def _agreed_effective_from(payload: pydantic.BaseModel, effective_from: Any) -> Any:
    """The date the proposal row shows the reviewer, which is the date approval will write
    (INV-04). An obligation version holds the date twice, on the row and in the payload,
    so a row saying one date while the payload carries another is refused rather than
    shown; a row that says nothing takes the payload's."""
    if not isinstance(payload, ProposalObligationVersionPayload):
        return effective_from
    if effective_from is not None and effective_from != payload.effective_from:
        raise ValidationError(
            "The proposal's effective date is not the date in its payload: give one date.",
            code="validation_error",
        )
    return payload.effective_from


def payload_dict(payload: pydantic.BaseModel) -> dict[str, Any]:
    """The payload as the JSON column stores it and the API returns it: camelCase keys and
    JSON values, so a legal date is the string the reviewer's screen shows, not a Python
    date the driver would refuse."""
    return payload.model_dump(mode="json", by_alias=True, exclude_none=True)


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
    field_sources: dict[str, str] | None = None,
    source_label: str = "",
    source_url: str = "",
    effective_from: Any = None,
) -> tuple[Proposal, bool]:
    """Create a proposal, or answer the one an earlier identical submission made. Returns
    `(proposal, created)`."""
    validated_kind(kind)
    parsed = validated_payload(kind, payload)
    _validate_obligation_target(kind, target_type, target_id)
    sources = {field: value.strip() for field, value in (field_sources or {}).items()}
    check_field_sources(parsed, sources)
    effective_from = _agreed_effective_from(parsed, effective_from)
    stored_payload = payload_dict(parsed)
    title = title.strip()
    if not title:
        raise ValidationError("Give the proposal a title.", code="validation_error")
    # What the database itself is scoped to, not a process-local mirror: this is the tenant
    # whose rows this transaction may write, so it is the tenant the link row can carry.
    tenant_id = tenancy.database_tenant_id()
    if idempotency_key:
        existing = Proposal.objects.filter(idempotency_key=idempotency_key).order_by("created_at", "id").first()
        if existing is not None:
            submitted = (kind, title, stored_payload, target_type, target_id, sources)
            if (existing.kind, existing.title, existing.payload, existing.target_type, existing.target_id, existing.field_sources) != submitted:
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
                tenant_id=tenant_id,
                after={"idempotencyKey": idempotency_key},
            )
            return existing, False
    proposal = Proposal.objects.create(
        kind=kind,
        title=title,
        payload=stored_payload,
        field_sources=sources,
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
        proposed_in_tenant=tenant_id is not None,
    )
    if tenant_id is not None:
        ProposalTenant.objects.create(tenant_id=tenant_id, proposal=proposal)
    record(
        action="proposal.created",
        actor=proposer.actor,
        subject_type=SUBJECT_TYPE,
        subject_id=proposal.id,
        subject_title=proposal.title,
        summary=f"Proposed: {proposal.title}",
        tenant_id=tenant_id,
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
