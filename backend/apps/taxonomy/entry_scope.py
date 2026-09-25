"""An agent access entry's scope (ACC-02, D-70, AC-ACC1), beside the footprint matcher.

The entry's terms are the terms of the products it names and of the products under each
department it names and every unit below it, intersected with the tenant's footprint. They
are derived per request by the SQL function `taxonomy_entry_scope` (taxonomy 0011), never
stored and never taken from the caller, so an entry can only narrow what the bank itself
sees. A record is in scope when it passes the footprint rule and then the same rule again,
`matching.in_footprint`, against the entry's term map: an empty dimension does not restrict
and an opt-in dimension matches only what the entry's terms name (FP-01).

Naming no department and no product narrows nothing: the entry's terms are then the whole
footprint and the second pass repeats the first, through the same code. Naming departments
or products that derive no term inside the footprint reads nothing, and says why
(`EMPTY_SCOPE`), because an entry that silently saw everything would be the widening this
rule exists to prevent. `admits` is the pure rule and `admits_sql` the database's, and
apps/taxonomy/tests_entry_scope.py pins the two to each other."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable, Mapping
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


def admits_sql(tenant_id: uuid.UUID, entry_id: uuid.UUID, term_ids: Iterable[uuid.UUID]) -> bool:
    """The database's verdict on one record, from `taxonomy_entry_admits` (taxonomy 0011)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT taxonomy_entry_admits(%s, %s, %s::uuid[])",
            [str(tenant_id), str(entry_id), [str(term_id) for term_id in term_ids]],
        )
        row = cursor.fetchone()
    return bool(row and row[0])
