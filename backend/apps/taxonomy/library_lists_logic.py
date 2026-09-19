"""Library vocabulary and taxonomy term changes as proposals (VOC-07, PRO-01, AC-PRO1).

A tier-2 list is shared by every tenant: a new change type moves every tenant's feed, a
renamed urgency every tenant's pill. So nobody writes one directly, not a tenant admin with
every permission and not a platform editor: every write on a library list, through the same
routes a tenant list uses, answers 202 with a proposal, and a second person's approval in
the console applies it (apps/proposals/apply.py).

The same checks a tenant write makes run here before the proposal exists: the labels are
in real languages, the kind is one the list knows, the key is not taken, the value is not a
near-duplicate, a system row is not retired. A proposal the reviewer could only reject for
a reason the proposer could have been told at once wastes both people's time.

This module writes proposals, never library rows, and names no `LibraryModel` class.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError

from apps.proposals import logic as proposals
from apps.proposals.models import Proposal, ProposalKind
from apps.taxonomy import tenant_lists_logic as lists
from apps.taxonomy import terms_logic
from apps.taxonomy.schemas import VocabularyMerged


def _proposable(list_name: str) -> Any:
    entry = lists.entry_for(list_name)
    if not entry.is_library:  # pragma: no cover - the route sends tenant lists elsewhere
        raise ValidationError(f"{list_name!r} is a tenant list; its admin changes it directly.", code="validation_error")
    if not entry.proposable:
        raise ValidationError(
            f"{list_name!r} is reference data seeded with every deploy; it is not changed through proposals.",
            code="validation_error",
        )
    return entry


def _extra_payload(entry: Any, extra: dict[str, Any] | None) -> dict[str, Any]:
    """The list's own columns as the proposal shows them: camelCased like every other name
    the reviewer reads. apply.py maps them back to columns."""
    from pydantic.alias_generators import to_camel

    return {to_camel(name): value for name, value in lists.extra_columns(entry, extra).items()}


def _label(labels: dict[str, str]) -> str:
    return labels.get(lists.ORIGINAL_LANGUAGE) or next(iter(labels.values()), "")


def propose_create(
    *,
    list_name: str,
    proposer: proposals.Proposer,
    labels: dict[str, str],
    key: str | None = None,
    usage_note: str = "",
    kind: str | None = None,
    sort_order: int | None = None,
    extra: dict[str, Any] | None = None,
    force: bool = False,
) -> Proposal:
    entry = _proposable(list_name)
    cleaned = lists.validated_labels(labels)
    row_key = lists.key_for(cleaned, key)
    lists.check_duplicate(entry, None, row_key)
    lists.check_near_duplicate(entry, None, cleaned, force=force)
    payload: dict[str, Any] = {
        "list": list_name,
        "key": row_key,
        "labels": cleaned,
        "usageNote": usage_note.strip(),
        "kind": lists.validated_kind(entry, kind),
        "sortOrder": sort_order,
        "extra": _extra_payload(entry, extra),
    }
    proposal, _created = proposals.create(
        kind=ProposalKind.VOCABULARY_CREATE.value,
        title=f"Add {_label(cleaned)} to {list_name}",
        payload=payload,
        proposer=proposer,
        target_type=list_name,
    )
    return proposal


def propose_relabel(
    *,
    list_name: str,
    proposer: proposals.Proposer,
    key: str,
    labels: dict[str, str] | None,
    usage_note: str | None,
    sort_order: int | None,
    extra: dict[str, Any] | None,
    expected_version: int | None,
) -> Proposal:
    entry = _proposable(list_name)
    row = lists.row_by_key(list_name, key, None)
    if expected_version is not None and expected_version != row.version:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")
    cleaned = lists.validated_labels(labels) if labels else {}
    payload: dict[str, Any] = {
        "list": list_name,
        "key": key,
        "labels": cleaned,
        "usageNote": usage_note,
        "sortOrder": sort_order,
        "extra": _extra_payload(entry, extra) or None,
    }
    proposal, _created = proposals.create(
        kind=ProposalKind.VOCABULARY_RELABEL.value,
        title=f"Change {key} on {list_name}",
        payload=payload,
        proposer=proposer,
        target_type=list_name,
        target_id=row.id,
    )
    return proposal


def propose_retire(*, list_name: str, proposer: proposals.Proposer, key: str, confirm: bool) -> Proposal:
    _proposable(list_name)
    row = lists.row_by_key(list_name, key, None)
    if row.is_system:
        raise ValidationError(f"{key} is a system value: it can be relabelled but not retired.", code="system_row")
    count = int(getattr(row, "usage_count", 0))
    if count and not confirm:
        raise lists.VocabularyProblem(
            f"{key} is used by {count} records. Retiring keeps them readable and removes it from pickers.",
            code="in_use",
            extra={"usageCount": count},
        )
    if not row.active:
        raise ValidationError(f"{key} is already retired.", code="invalid_transition")
    proposal, _created = proposals.create(
        kind=ProposalKind.VOCABULARY_RETIRE.value,
        title=f"Retire {key} from {list_name}",
        payload={"list": list_name, "key": key},
        proposer=proposer,
        target_type=list_name,
        target_id=row.id,
    )
    return proposal


def propose_restore(*, list_name: str, proposer: proposals.Proposer, key: str) -> Proposal:
    _proposable(list_name)
    row = lists.row_by_key(list_name, key, None)
    if row.active:
        raise ValidationError(f"{key} is not retired.", code="invalid_transition")
    proposal, _created = proposals.create(
        kind=ProposalKind.VOCABULARY_RESTORE.value,
        title=f"Restore {key} to {list_name}",
        payload={"list": list_name, "key": key},
        proposer=proposer,
        target_type=list_name,
        target_id=row.id,
    )
    return proposal


def propose_merge(
    *, list_name: str, proposer: proposals.Proposer, key: str, into: str, dry_run: bool
) -> VocabularyMerged | Proposal:
    entry = _proposable(list_name)
    source = lists.row_by_key(list_name, key, None)
    target = lists.row_by_key(list_name, into, None)
    if source.pk == target.pk:
        raise ValidationError("Choose a different value to merge into.", code="validation_error")
    if source.is_system:
        raise ValidationError(f"{key} is a system value: it can be relabelled but not merged away.", code="system_row")
    count = int(getattr(source, "usage_count", 0))
    if dry_run:
        return VocabularyMerged(
            **{"from": key}, into=into, usage_count=count, repointed=entry.repoint(source, target, dry_run=True), dry_run=True
        )
    proposal, _created = proposals.create(
        kind=ProposalKind.VOCABULARY_MERGE.value,
        title=f"Merge {key} into {into} on {list_name}",
        payload={"list": list_name, "key": key, "into": into},
        proposer=proposer,
        target_type=list_name,
        target_id=source.id,
    )
    return proposal


def propose_term_create(
    *,
    proposer: proposals.Proposer,
    dimension: str,
    labels: dict[str, str],
    key: str | None = None,
    usage_note: str = "",
    parent: str | None = None,
) -> Proposal:
    terms_logic.dimension_by_key(dimension)
    cleaned = lists.validated_labels(labels)
    term_key = lists.key_for(cleaned, key)
    if terms_logic.term_exists(dimension, term_key):
        raise ValidationError(f"{term_key!r} already exists in {dimension!r}.", code="duplicate_key")
    if parent:
        terms_logic.term_by_ref(dimension, parent)
    proposal, _created = proposals.create(
        kind=ProposalKind.TERM_CREATE.value,
        title=f"Add the term {_label(cleaned)} to {dimension}",
        payload={"dimension": dimension, "key": term_key, "labels": cleaned, "usageNote": usage_note.strip(), "parent": parent},
        proposer=proposer,
        target_type="taxonomy_term",
    )
    return proposal


def propose_term_update(
    *,
    proposer: proposals.Proposer,
    term_id: uuid.UUID,
    labels: dict[str, str] | None,
    usage_note: str | None,
    sort_order: int | None,
    expected_version: int | None,
) -> Proposal:
    term = terms_logic.term_by_id(term_id)
    if expected_version is not None and expected_version != term.version:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")
    cleaned = lists.validated_labels(labels) if labels else {}
    proposal, _created = proposals.create(
        kind=ProposalKind.TERM_UPDATE.value,
        title=f"Change the term {term.key} in {term.dimension.key}",
        payload={
            "dimension": term.dimension.key,
            "key": term.key,
            "labels": cleaned,
            "usageNote": usage_note,
            "sortOrder": sort_order,
        },
        proposer=proposer,
        target_type="taxonomy_term",
        target_id=term.id,
    )
    return proposal
