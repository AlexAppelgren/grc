"""Footprint matching (FP-01, D-36, data-model.md §4): the one rule every surface applies,
as a pure function and as the SQL function `taxonomy_in_footprint(tenant, term_ids[])`,
tested against each other (apps/taxonomy/tests_matching.py). A list filters with
`in_footprint_expression()`, so the footprint is read once per query.

The rule: for every dimension the record carries terms in, at least one of them must be in
the footprint. A dimension the footprint names no term in does not restrict (playbook 4.5),
except an opt-in dimension (the standards a bank follows): a record carrying one of its terms
matches only when the footprint names that term. A dimension whose `restricts_footprint` is
false never narrows; an opt-in dimension restricts whatever that flag says. A record with no
terms matches every tenant. An obligation's instrument regime is folded into its scope by
the caller (apps/library/reading.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable, Mapping

from django.contrib.postgres.fields import ArrayField
from django.db.models import BooleanField, Func, Q, UUIDField, Value
from django.db.models.expressions import BaseExpression

from apps.taxonomy.models import FootprintTerm, TermDimension, TermDimensionKind

SQL_FUNCTION = "taxonomy_in_footprint"
# taxonomy_footprint_guard's three columns, each read by an uncorrelated subquery.
GUARD_TEMPLATES = (
    "(SELECT terms FROM taxonomy_footprint_guard(%(expressions)s))",
    "(SELECT dimensions FROM taxonomy_footprint_guard(%(expressions)s))",
    "(SELECT allowed FROM taxonomy_footprint_guard(%(expressions)s))",
)


class Restricting(frozenset[str]):
    """The dimensions whose terms narrow the footprint, with `opt_in` naming those among them
    that match only what the footprint names. Every opt-in dimension restricts, so it is in
    the set too. `in_footprint` accepts nothing else: a plain set of keys carries no opt-in
    dimensions and would silently show every standard to every bank."""

    opt_in: frozenset[str]

    def __new__(cls, keys: Iterable[str], *, opt_in: Iterable[str]) -> Restricting:
        opted = frozenset(opt_in)
        restricting = super().__new__(cls, frozenset(keys) | opted)
        restricting.opt_in = opted
        return restricting


def in_footprint(
    record_terms: Mapping[str, Collection[str]],
    footprint: Mapping[str, Collection[str]],
    *,
    restricting: Collection[str],
) -> bool:
    """`record_terms` and `footprint` map a dimension key to term keys. `restricting` must be
    a `Restricting`, `restricting_dimensions()`'s answer, the only thing that knows which
    dimensions are opt-in."""
    if not isinstance(restricting, Restricting):
        raise TypeError("in_footprint needs restricting_dimensions()'s answer, which names the opt-in dimensions.")
    for dimension, keys in record_terms.items():
        if dimension not in restricting or not keys:
            continue
        have = footprint.get(dimension)
        if not have:
            if dimension in restricting.opt_in:
                return False
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


def restricting_dimensions() -> Restricting:
    """Every active dimension whose terms narrow the footprint: those whose flag says so and
    every opt-in dimension, whatever its flag says. One query."""
    opt_in = TermDimensionKind.OPT_IN.value
    rows = list(
        TermDimension.objects.filter(Q(restricts_footprint=True) | Q(kind=opt_in), active=True).values_list("key", "kind")
    )
    return Restricting((key for key, _kind in rows), opt_in=(key for key, kind in rows if kind == opt_in))


def in_footprint_expression(tenant_id: uuid.UUID, term_ids: BaseExpression) -> Func:
    """`taxonomy_in_footprint(tenant, term_ids)` as a list's filter: the per-row check over
    `term_ids`, handed the bank's guard as uncorrelated subqueries that PostgreSQL runs once
    per query (taxonomy 0008), instead of re-reading the footprint for every row."""
    tenant = Value(tenant_id, output_field=UUIDField())
    guard = [Func(tenant, template=template, output_field=ArrayField(UUIDField())) for template in GUARD_TEMPLATES]
    return Func(term_ids, *guard, function="taxonomy_scope_admits", output_field=BooleanField())


