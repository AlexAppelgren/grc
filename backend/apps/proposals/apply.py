"""Applying an approved proposal (PRO-02, VOC-07): the only module outside the reference
seeds and the watch pipeline allowed to write a library row (the library fence,
apps/shared/tests_library_fence.py). Every write happens inside `library_write()` naming
the proposal, in the approval's transaction, with its own audit row through `record()`, so
the library change, its audit row and the proposal's decision commit together or not at
all.

Chunk 2 applies the vocabulary and term kinds. Chunk 4 adds instruments, provisions and
obligations, each with a version row rather than an overwrite (playbook 4.3).

A payload is re-checked here against the library as it is now, not as it was when the
proposal was made: a key someone else created in the meantime is 409 `duplicate_key`, a
retired row cannot be relabelled into life, and a system row is never retired.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from apps.proposals.logic import parsed_payload
from apps.proposals.models import Proposal, ProposalKind
from apps.proposals.schemas import (
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
    ProposalVocabularyCreatePayload,
    ProposalVocabularyMergePayload,
    ProposalVocabularyRelabelPayload,
    ProposalVocabularyRetirePayload,
)
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write
from apps.taxonomy.models import TaxonomyTerm, TaxonomyTermLabel, TermDimension
from apps.taxonomy.registry import REGISTRY, VocabularyList
from apps.taxonomy.tenant_lists_logic import extra_columns

ORIGINAL_LANGUAGE = "en"


def apply(proposal: Proposal, *, actor: Actor) -> None:
    payload = parsed_payload(proposal.kind, proposal.payload)
    with library_write(f"proposal:{proposal.id}"):
        if proposal.kind == ProposalKind.VOCABULARY_CREATE.value:
            assert isinstance(payload, ProposalVocabularyCreatePayload)
            _vocabulary_create(payload, proposal, actor)
        elif proposal.kind == ProposalKind.VOCABULARY_RELABEL.value:
            assert isinstance(payload, ProposalVocabularyRelabelPayload)
            _vocabulary_relabel(payload, proposal, actor)
        elif proposal.kind == ProposalKind.VOCABULARY_RETIRE.value:
            assert isinstance(payload, ProposalVocabularyRetirePayload)
            _vocabulary_active(payload, proposal, actor, active=False)
        elif proposal.kind == ProposalKind.VOCABULARY_RESTORE.value:
            assert isinstance(payload, ProposalVocabularyRetirePayload)
            _vocabulary_active(payload, proposal, actor, active=True)
        elif proposal.kind == ProposalKind.VOCABULARY_MERGE.value:
            assert isinstance(payload, ProposalVocabularyMergePayload)
            _vocabulary_merge(payload, proposal, actor)
        elif proposal.kind == ProposalKind.TERM_CREATE.value:
            assert isinstance(payload, ProposalTermCreatePayload)
            _term_create(payload, proposal, actor)
        elif proposal.kind == ProposalKind.TERM_UPDATE.value:
            assert isinstance(payload, ProposalTermUpdatePayload)
            _term_update(payload, proposal, actor)
        else:  # pragma: no cover - parsed_payload already refused an unknown kind
            raise ValidationError(f"{proposal.kind!r} cannot be applied yet.", code="unknown_key")


# ---------------------------------------------------------------------------------------
# Vocabulary rows
# ---------------------------------------------------------------------------------------
def _entry(name: str) -> VocabularyList:
    entry = REGISTRY[name]
    if not entry.is_library:  # pragma: no cover - logic.validated_payload refused it
        raise ValidationError(f"{name!r} is a tenant list; its admin writes it.", code="unknown_key")
    return entry


def _row(entry: VocabularyList, key: str) -> Any:
    row = entry.model._default_manager.filter(key=key).order_by("sort_order", "key").first()
    if row is None:
        raise ValidationError(f"{key!r} is not a row of {entry.name!r}.", code="not_found")
    return row


def _write_labels(entry: VocabularyList, row: Any, labels: dict[str, str]) -> None:
    existing = {label.language: label for label in entry.label_model._default_manager.filter(vocabulary=row)}
    original = None
    if not any(label.is_original for label in existing.values()):
        original = ORIGINAL_LANGUAGE if ORIGINAL_LANGUAGE in labels else next(iter(labels), None)
    for language, text in labels.items():
        label = existing.get(language)
        if label is not None:
            label.text = text
            label.is_machine = False
            label.save(update_fields=["text", "is_machine"])
        else:
            entry.label_model._default_manager.create(
                vocabulary=row, language=language, text=text, is_original=language == original
            )


def _vocabulary_create(payload: ProposalVocabularyCreatePayload, proposal: Proposal, actor: Actor) -> None:
    entry = _entry(payload.list)
    if entry.model._default_manager.filter(key__iexact=payload.key).exists():
        raise ValidationError(f"{payload.key!r} already exists on {payload.list!r}.", code="duplicate_key")
    highest = entry.model._default_manager.order_by("-sort_order").values_list("sort_order", flat=True).first()
    fields: dict[str, Any] = {
        "key": payload.key,
        "kind": payload.kind if entry.kinds else None,
        "usage_note": payload.usage_note,
        "sort_order": payload.sort_order if payload.sort_order is not None else (0 if highest is None else highest + 1),
        "active": True,
        "is_system": False,
        "is_default": False,
    }
    fields.update(extra_columns(entry, payload.extra))
    row = entry.model._default_manager.create(**fields)
    _write_labels(entry, row, payload.labels)
    record(
        action="vocabulary.created",
        actor=actor,
        subject_type="vocabulary",
        subject_id=row.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"Added {payload.key} to {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        after={"list": payload.list, "key": payload.key, "labels": payload.labels, "proposal": str(proposal.id)},
    )


def _vocabulary_relabel(payload: ProposalVocabularyRelabelPayload, proposal: Proposal, actor: Actor) -> None:
    entry = _entry(payload.list)
    row = _row(entry, payload.key)
    before = {label.language: label.text for label in entry.label_model._default_manager.filter(vocabulary=row)}
    if payload.labels:
        _write_labels(entry, row, payload.labels)
    if payload.usage_note is not None:
        row.usage_note = payload.usage_note
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    for name, value in extra_columns(entry, payload.extra).items():
        setattr(row, name, value)
    row.version += 1
    row.save()
    record(
        action="vocabulary.updated",
        actor=actor,
        subject_type="vocabulary",
        subject_id=row.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"Changed {payload.key} on {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        before={"labels": before},
        after={"labels": {**before, **payload.labels}, "proposal": str(proposal.id)},
    )


def _vocabulary_active(payload: ProposalVocabularyRetirePayload, proposal: Proposal, actor: Actor, *, active: bool) -> None:
    entry = _entry(payload.list)
    row = _row(entry, payload.key)
    if not active and row.is_system:
        raise ValidationError(f"{payload.key} is a system value: it can be relabelled but not retired.", code="system_row")
    if row.active == active:
        raise ValidationError(
            f"{payload.key} is already {'active' if active else 'retired'}.", code="invalid_transition"
        )
    row.active = active
    row.version += 1
    row.save(update_fields=["active", "version"])
    record(
        action="vocabulary.restored" if active else "vocabulary.retired",
        actor=actor,
        subject_type="vocabulary",
        subject_id=row.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"{'Restored' if active else 'Retired'} {payload.key} on {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        before={"active": not active},
        after={"active": active, "proposal": str(proposal.id)},
    )


def _vocabulary_merge(payload: ProposalVocabularyMergePayload, proposal: Proposal, actor: Actor) -> None:
    entry = _entry(payload.list)
    source = _row(entry, payload.key)
    target = _row(entry, payload.into)
    if source.is_system:
        raise ValidationError(f"{payload.key} is a system value: it can be relabelled but not merged away.", code="system_row")
    repointed = entry.repoint(source, target, dry_run=False)
    source.active = False
    source.version += 1
    source.save(update_fields=["active", "version"])
    record(
        action="vocabulary.merged",
        actor=actor,
        subject_type="vocabulary",
        subject_id=source.id,
        subject_title=f"{payload.list}:{payload.key}",
        summary=f"Merged {payload.key} into {payload.into} on {payload.list} (proposal {proposal.id}).",
        tenant_id=None,
        before={"from": payload.key, "active": True},
        after={"into": payload.into, "repointed": repointed, "active": False, "proposal": str(proposal.id)},
    )


# ---------------------------------------------------------------------------------------
# Taxonomy terms
# ---------------------------------------------------------------------------------------
def _dimension(key: str) -> TermDimension:
    dimension = TermDimension.objects.filter(key=key, active=True).order_by("sort_order", "key").first()
    if dimension is None:
        raise ValidationError(f"{key!r} is not a taxonomy dimension.", code="unknown_key")
    return dimension


def _term_labels(term: TaxonomyTerm, labels: dict[str, str]) -> None:
    existing = {label.language: label for label in TaxonomyTermLabel.objects.filter(term=term)}
    original = None
    if not any(label.is_original for label in existing.values()):
        original = ORIGINAL_LANGUAGE if ORIGINAL_LANGUAGE in labels else next(iter(labels), None)
    for language, text in labels.items():
        label = existing.get(language)
        if label is not None:
            label.text = text
            label.is_machine = False
            label.save(update_fields=["text", "is_machine"])
        else:
            TaxonomyTermLabel.objects.create(term=term, language=language, text=text, is_original=language == original)


def _term_create(payload: ProposalTermCreatePayload, proposal: Proposal, actor: Actor) -> None:
    dimension = _dimension(payload.dimension)
    if TaxonomyTerm.objects.filter(dimension=dimension, key__iexact=payload.key).exists():
        raise ValidationError(f"{payload.key!r} already exists in {payload.dimension!r}.", code="duplicate_key")
    parent = None
    if payload.parent:
        parent = TaxonomyTerm.objects.filter(dimension=dimension, key=payload.parent).order_by("sort_order", "key").first()
        if parent is None:
            raise ValidationError(f"{payload.parent!r} is not a term of {payload.dimension!r}.", code="unknown_key")
    highest = (
        TaxonomyTerm.objects.filter(dimension=dimension).order_by("-sort_order").values_list("sort_order", flat=True).first()
    )
    term = TaxonomyTerm.objects.create(
        dimension=dimension,
        key=payload.key,
        parent=parent,
        usage_note=payload.usage_note,
        sort_order=0 if highest is None else highest + 1,
        active=True,
        is_system=False,
    )
    _term_labels(term, payload.labels)
    record(
        action="taxonomy.term_created",
        actor=actor,
        subject_type="taxonomy_term",
        subject_id=term.id,
        subject_title=f"{payload.dimension}:{payload.key}",
        summary=f"Added the term {payload.key} to {payload.dimension} (proposal {proposal.id}).",
        tenant_id=None,
        after={"dimension": payload.dimension, "key": payload.key, "labels": payload.labels, "proposal": str(proposal.id)},
    )


def _term_update(payload: ProposalTermUpdatePayload, proposal: Proposal, actor: Actor) -> None:
    dimension = _dimension(payload.dimension)
    term = TaxonomyTerm.objects.filter(dimension=dimension, key=payload.key).order_by("sort_order", "key").first()
    if term is None:
        raise ValidationError(f"{payload.key!r} is not a term of {payload.dimension!r}.", code="not_found")
    before = {label.language: label.text for label in TaxonomyTermLabel.objects.filter(term=term)}
    if payload.labels:
        _term_labels(term, payload.labels)
    if payload.usage_note is not None:
        term.usage_note = payload.usage_note
    if payload.sort_order is not None:
        term.sort_order = payload.sort_order
    term.version += 1
    term.save()
    record(
        action="taxonomy.term_updated",
        actor=actor,
        subject_type="taxonomy_term",
        subject_id=term.id,
        subject_title=f"{payload.dimension}:{payload.key}",
        summary=f"Changed the term {payload.key} in {payload.dimension} (proposal {proposal.id}).",
        tenant_id=None,
        before={"labels": before},
        after={"labels": {**before, **payload.labels}, "proposal": str(proposal.id)},
    )
