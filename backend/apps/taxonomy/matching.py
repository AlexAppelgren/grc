"""Footprint matching (FP-01, data-model.md §4): the one rule every surface applies from
chunk 3 on, as a pure function and as the SQL function `taxonomy_in_footprint(tenant,
term_ids[])` the taxonomy migration creates. The two are tested against each other
(apps/taxonomy/tests_matching.py).

The rule: for every dimension the record carries terms in, at least one of them must be
in the footprint. A dimension the footprint has no terms in does not restrict (an empty
restriction list means "no restriction", playbook 4.5). A dimension whose
`restricts_footprint` is false (theme, channel, lifecycle stage) describes the record
and never narrows the footprint. A record with no terms matches every tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable, Mapping

from django.db import connection

from apps.taxonomy.models import FootprintTerm, TermDimension

SQL_FUNCTION = "taxonomy_in_footprint"


def in_footprint(
    record_terms: Mapping[str, Collection[str]],
    footprint: Mapping[str, Collection[str]],
    *,
    restricting: Collection[str] | None = None,
) -> bool:
    """`record_terms` and `footprint` map a dimension key to term keys. `restricting`
    names the dimensions whose terms narrow the footprint; None means every dimension
    the record carries does (the caller has already filtered by the dimension flag)."""
    for dimension, keys in record_terms.items():
        if restricting is not None and dimension not in restricting:
            continue
        if not keys:
            continue
        have = footprint.get(dimension)
        if not have:
            continue
        if set(keys).isdisjoint(have):
            return False
    return True


def footprint_of(tenant_id: uuid.UUID) -> dict[str, set[str]]:
    """The activated tenant's footprint as dimension key -> term keys. Reads under RLS, so
    the tenant must be activated; the id is the belt to the policy's braces."""
    result: dict[str, set[str]] = {}
    rows = FootprintTerm.objects.filter(tenant_id=tenant_id).select_related("term__dimension").order_by("term__dimension__sort_order", "term__sort_order")
    for row in rows:
        result.setdefault(row.term.dimension.key, set()).add(row.term.key)
    return result


def restricting_dimensions() -> set[str]:
    return set(TermDimension.objects.filter(active=True, restricts_footprint=True).values_list("key", flat=True))


def in_footprint_sql(tenant_id: uuid.UUID, term_ids: Iterable[uuid.UUID]) -> bool:
    """The database's answer, from the SQL function the migration created. Every list
    query from chunk 3 on uses the function inside its WHERE clause; this wrapper is for
    the surfaces that decide one record at a time and for the tests that pin the mirror."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {SQL_FUNCTION}(%s, %s::uuid[])", [str(tenant_id), [str(term_id) for term_id in term_ids]])
        row = cursor.fetchone()
    return bool(row and row[0])

