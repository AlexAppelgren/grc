"""An agent access entry's scope (ACC-02, D-70, AC-ACC1), beside the footprint matcher.

The entry's terms are those of the products and departments (with every unit below) it
names, intersected with the footprint, derived per request by `taxonomy_entry_scope` and
never stored or taken from the caller, so an entry only narrows what the bank sees. A record
is in scope when it passes `matching.in_footprint` against the footprint and then against
the entry's terms (FP-01).

Naming nothing narrows nothing. Naming departments or products that derive no term reads
nothing and says why (`EMPTY_SCOPE`): an entry that silently saw everything would be the
widening this rule prevents. `admits` and `taxonomy_entry_admits` are pinned to each other
(apps/taxonomy/tests_entry_scope.py)."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from django.db import connection

from apps.taxonomy import matching
from apps.taxonomy.models import TaxonomyTerm

# Why a narrowed entry reads nothing: its departments and products derive no term inside the
# footprint (a retired product, a deactivated unit, or products the bank has not described).
EMPTY_SCOPE = "entry_scope_empty"


@dataclass(frozen=True)
class EntryScope:
    """What one entry may read: `terms` maps a dimension key to term keys, all of them in
    the footprint. `narrowed` is false when the entry names no department and no product."""

    narrowed: bool
    terms: dict[str, frozenset[str]]

    @property
    def empty_reason(self) -> str | None:
        """`EMPTY_SCOPE` when the entry reads nothing, else None."""
        return EMPTY_SCOPE if self.narrowed and not self.terms else None


def scope_of(tenant_id: uuid.UUID, entry_id: uuid.UUID) -> EntryScope:
    """The entry's scope, read under row-level security: the tenant must be activated, and
    another bank's entry derives nothing and narrows nothing it can see."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT narrowed, terms FROM taxonomy_entry_scope(%s, %s)", [str(tenant_id), str(entry_id)])
        narrowed, term_ids = cursor.fetchone()
    terms: dict[str, set[str]] = {}
    for dimension, key in TaxonomyTerm.objects.filter(id__in=term_ids).values_list("dimension__key", "key"):
        terms.setdefault(dimension, set()).add(key)
    return EntryScope(narrowed=bool(narrowed), terms={dimension: frozenset(keys) for dimension, keys in terms.items()})


def admits(
    record_terms: Mapping[str, Collection[str]],
    footprint: Mapping[str, Collection[str]],
    scope: EntryScope,
    *,
    restricting: Collection[str],
) -> bool:
    """The pure rule: the footprint's verdict, then the same verdict against the entry's
    terms. `restricting` is `matching.restricting_dimensions()`'s answer, as for the
    footprint alone."""
    if scope.empty_reason is not None:
        return False
    return matching.in_footprint(record_terms, footprint, restricting=restricting) and matching.in_footprint(
        record_terms, scope.terms, restricting=restricting
    )


