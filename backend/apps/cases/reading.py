"""What a case needs to know about a library change, read in the library's zone (CAS-01).

Everything here reads and nothing writes, which is the point of the module. The library
fence refuses any production module that both names a library record and calls a write
(`apps/shared/tests_library_fence.py`), because that is how a library write gets smuggled
in beside the proposal door. So `creation.py` writes and never names a library record, and
the reads live here — the same split `apps/library/reading.py` makes for the proposals app.

`ChangeFacts` is also the honest statement of what crosses the boundary between the two
zones: five facts, and nothing else of the library travels into a bank's case.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.taxonomy.models import Urgency
from apps.watch.models import RegulatoryChange

# Dimension key -> the term keys the change carries in it, as the scope rule reads it.
Scope = dict[str, set[str]]


@dataclass(frozen=True)
class ChangeFacts:
    """What one registered change puts into every bank's case."""

    id: uuid.UUID
    title: str
    scope: Scope
    urgency_id: uuid.UUID
    so_what_draft: str


def change_facts(change_id: uuid.UUID) -> ChangeFacts | None:
    """The facts of the change with this id, or None when there is no such change."""
    change = (
        RegulatoryChange.objects.select_related("suggested_urgency")
        .filter(pk=change_id)
        .first()  # ordering: pk lookup, at most one row
    )
    if change is None:
        return None
    return ChangeFacts(
        id=change.id,
        title=change.title,
        scope=_scope_of(change),
        urgency_id=_urgency_for(change).id,
        so_what_draft=change.so_what_draft,
    )


def _scope_of(change: RegulatoryChange) -> Scope:
    """The change's scope as the rule reads it: its taxonomy terms by dimension. A flag is a
    `change_term` row too and is never a scope term — it describes the change, it does not
    say who it reaches (WAT-03). A change with no terms has an empty scope and so falls
    inside every bank's footprint."""
    scope: Scope = {}
    for link in change.term_links.filter(term__isnull=False).select_related("term__dimension"):
        term = link.term
        if term is not None:  # the filter said so; the column is nullable because a flag row carries no term
            scope.setdefault(term.dimension.key, set()).add(term.key)
    return scope


def _urgency_for(change: RegulatoryChange) -> Urgency:
    """The agent's suggestion, or the urgency list's own default row when the change carries
    none. `change_case.urgency` is NOT NULL and the case exists from the moment the change
    does, so a bank always has something to triage from; `urgency_confirmed` stays false
    either way, so neither reads as a person's decision."""
    if change.suggested_urgency is not None:
        return change.suggested_urgency
    default = Urgency.objects.filter(is_default=True).first()  # ordering: Meta.ordering, ordinal first
    if default is None:  # pragma: no cover - the vocabulary guard demands a default per list
        raise RuntimeError(
            "The urgency list has no default row, so a new case has no urgency to start from. "
            "Run the reference seed (apps/shared/tests_vocabulary_integrity.py)."
        )
    return default
