"""Taxonomy terms and dimensions: reads only (VOC-07, FP-01).

Every write to a term or a dimension is a proposal applied by apps/proposals/apply.py, so
this module never calls a write method. That is also what keeps the library fence's AST
guard quiet: it refuses any module outside the allowlist that names a `LibraryModel` and
calls `save`, `create`, `update`, `delete` or their bulk and get-or-create forms
(apps/shared/tests_library_fence.py).

`term_by_ref()` is the one place a `dimension:key` pair becomes a row. An unknown pair is
422 `unknown_key` naming the keys that would have worked, because an agent (AGT-02) and a
person both need to be told what they may say, not merely that they were wrong.

`refuse_mirrored()` is the one rule that keeps a mirrored dimension out of every write
(FP-04, FP-S12, D-28, ADR 0026): no proposal adds or changes one of its terms, and no
record is tagged with one, because the reference seed owns them and a record's market
comes from its instrument or its authority. It reads the data, the `jurisdiction` link a
mirrored term carries, and never a dimension key. The term list marks the same terms
`mirrored`, so an agent or a picker leaves them out before it is ever refused.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError

from apps.taxonomy.models import TaxonomyTerm, TermDimension
from apps.taxonomy.reading import CONFIRMATION_JOINS, Labels, confirmation_of, label_of
from apps.taxonomy.schemas import TaxonomyDimensionRef, TaxonomyTermRow, TermRef

MAX_KEYS_IN_MESSAGE = 12
# Says what the rule is and where the fact comes from instead, and names no dimension and
# no country: the rule is keyed on data, so its sentence is too.
MIRRORED_REFUSAL = (
    "Those terms mirror the markets the platform covers and follow them on every deploy: none is "
    "added or renamed through a proposal, and a record is never tagged with one. A record's "
    "market comes from its instrument or its authority."
)


def mirrored_dimensions(dimension_ids: Iterable[Any]) -> set[Any]:
    """The ids among these of the dimensions that hold a term mirroring a jurisdiction row
    (FP-04). One query however many dimensions are named.

    Keyed on the dimension rather than on the term alone, so a term of a mirrored dimension
    that carries no link of its own counts as firmly as a linked one. `refuse_mirrored`
    refuses a write with it, and `term_rows` marks the terms it reads with it, so the list
    an agent reads at run start and the rule it is held to are the same fact."""
    wanted = set(dimension_ids)
    if not wanted:
        return set()
    return set(
        TaxonomyTerm.objects.filter(dimension_id__in=wanted, jurisdiction__isnull=False)
        .values_list("dimension_id", flat=True)
        .distinct()
    )


def refuse_mirrored(dimension_ids: Iterable[Any]) -> None:
    """422 `jurisdiction_term_mirrored` when any of these dimensions is mirrored (FP-04,
    FP-S12). Called where a proposal is made and again where it is applied, since a proposal
    filed before this rule existed still waits in the queue, and wherever a record is tagged."""
    if mirrored_dimensions(dimension_ids):
        raise ValidationError(MIRRORED_REFUSAL, code="jurisdiction_term_mirrored")


def dimension_by_key(key: str) -> TermDimension:
    dimension = TermDimension.objects.filter(key=key, active=True).order_by("sort_order", "key").first()
    if dimension is None:
        valid = list(TermDimension.objects.filter(active=True).order_by("sort_order", "key").values_list("key", flat=True))
        raise ValidationError(
            f"{key!r} is not a taxonomy dimension. Valid dimensions: {', '.join(valid)}.",
            code="unknown_key",
        )
    return dimension


def term_by_ref(dimension_key: str, key: str) -> TaxonomyTerm:
    """The term `dimension_key:key`, or 422 `unknown_key` listing what would have worked."""
    dimension = dimension_by_key(dimension_key)
    term = TaxonomyTerm.objects.filter(dimension=dimension, key=key, active=True).order_by("sort_order", "key").first()
    if term is None:
        valid = list(
            TaxonomyTerm.objects.filter(dimension=dimension, active=True)
            .order_by("sort_order", "key")
            .values_list("key", flat=True)[:MAX_KEYS_IN_MESSAGE]
        )
        raise ValidationError(
            f"{key!r} is not a term of {dimension_key!r}. Valid keys: {', '.join(valid)}.",
            code="unknown_key",
        )
    return term


def term_exists(dimension_key: str, key: str) -> bool:
    """Case-insensitively, retired terms included: a retired key is still taken (playbook
    4.3: stable keys are never reused for something else)."""
    return TaxonomyTerm.objects.filter(dimension__key=dimension_key, key__iexact=key).exists()


def term_by_id(term_id: Any) -> TaxonomyTerm:
    term = TaxonomyTerm.objects.select_related("dimension").filter(pk=term_id).first()  # ordering: pk lookup, at most one row
    if term is None:
        raise ValidationError("That term is not here.", code="not_found")
    return term


def terms_of(dimension_key: str | None, *, include_retired: bool = False) -> list[TaxonomyTerm]:
    queryset = TaxonomyTerm.objects.select_related("dimension", "parent", *CONFIRMATION_JOINS).order_by(
        "dimension__sort_order", "sort_order", "key"
    )
    if dimension_key:
        queryset = queryset.filter(dimension=dimension_by_key(dimension_key))
    if not include_retired:
        queryset = queryset.filter(active=True)
    return list(queryset)


def dimension_ref(dimension: TermDimension, labels: dict[str, str], order: list[str]) -> TaxonomyDimensionRef:
    return TaxonomyDimensionRef(
        key=dimension.key,
        kind=dimension.kind,
        label=label_of(labels, order, original=None, key=dimension.key),
    )


def dimension_labels(dimensions: list[Any]) -> Labels:
    from apps.taxonomy.models import TermDimensionLabel

    return Labels.for_rows(TermDimensionLabel, dimensions)


def term_ref(term: TaxonomyTerm, labels: dict[str, str], order: list[str]) -> TermRef:
    # A term carries no kind of its own: its dimension is its kind (models.py). The picker
    # still reads `kind` so one pill component renders a term like any other vocabulary row.
    return TermRef(key=term.key, kind=None, label=label_of(labels, order, original=None, key=term.key))


def term_rows(terms: list[TaxonomyTerm], order: list[str]) -> list[TaxonomyTermRow]:
    from apps.taxonomy.models import TaxonomyTermLabel

    labels = Labels.for_rows(TaxonomyTermLabel, terms, field="term")
    dimensions = {term.dimension_id: term.dimension for term in terms}
    dimension_texts = dimension_labels(list(dimensions.values()))
    mirrored = mirrored_dimensions(dimensions)
    rows: list[TaxonomyTermRow] = []
    for term in terms:
        texts = labels.texts(term.id)
        rows.append(
            TaxonomyTermRow(
                id=term.id,
                key=term.key,
                kind=None,
                label=label_of(texts, order, original=labels.original(term.id), key=term.key),
                labels=texts,
                dimension=dimension_ref(term.dimension, dimension_texts.texts(term.dimension_id), order),
                parent_key=term.parent.key if term.parent is not None else None,
                usage_note=term.usage_note,
                sort_order=term.sort_order,
                active=term.active,
                is_system=term.is_system,
                version=term.version,
                mirrored=term.dimension_id in mirrored,
                **confirmation_of(term),
            )
        )
    return rows


def terms_by_selectors(selectors: list[Any]) -> list[TaxonomyTerm]:
    """`[{dimension, key}, …]` as rows, in the order given, each validated (FP-02)."""
    return [term_by_ref(selector.dimension, selector.key) for selector in selectors]


# ---------------------------------------------------------------------------------------
# The footprint read (FP-01). It lives here rather than in footprint_logic.py because it
# names the library term and dimension tables, and footprint_logic.py writes: a module may
# do one or the other, never both, or the library fence cannot tell them apart.
# ---------------------------------------------------------------------------------------
def dimensions_for_footprint(order: list[str]) -> list[tuple[TaxonomyDimensionRef, bool, int]]:
    """Every active dimension as `(ref, restricts_footprint, active term count)`, in the
    picker's order. The count is what `allSelected` is measured against."""
    from django.db.models import Count, Q

    rows = list(
        TermDimension.objects.filter(active=True)
        .annotate(term_count=Count("terms", filter=Q(terms__active=True)))
        .order_by("sort_order", "key")
    )
    texts = dimension_labels(rows)
    return [
        (dimension_ref(row, texts.texts(row.id), order), row.restricts_footprint, row.term_count)
        for row in rows
    ]


def selected_terms_by_dimension(tenant_id: Any, order: list[str]) -> dict[str, list[TermRef]]:
    """The activated tenant's footprint as dimension key -> term references, labelled. Reads
    under row-level security; the id is the belt to the policy's braces."""
    from apps.taxonomy.models import FootprintTerm, TaxonomyTermLabel

    rows = list(
        FootprintTerm.objects.filter(tenant_id=tenant_id)
        .select_related("term", "term__dimension")
        .order_by("term__dimension__sort_order", "term__sort_order", "term__key")
    )
    terms = [row.term for row in rows]
    labels = Labels.for_rows(TaxonomyTermLabel, terms, field="term")
    selected: dict[str, list[TermRef]] = {}
    for row in rows:
        selected.setdefault(row.term.dimension.key, []).append(
            term_ref(row.term, labels.texts(row.term.id), order)
        )
    return selected


def labelled_term_refs(terms: list[Any], order: list[str]) -> list[Any]:
    """`FootprintTermRef`s for the terms of one change request (FP-02): the key, the label
    a person reads in the decision mail and on the screen, and the dimension."""
    from apps.taxonomy.models import TaxonomyTermLabel
    from apps.taxonomy.schemas import FootprintTermRef

    labels = Labels.for_rows(TaxonomyTermLabel, terms, field="term")
    return [
        FootprintTermRef(
            key=term.key,
            kind=None,
            label=label_of(labels.texts(term.id), order, original=labels.original(term.id), key=term.key),
            dimension=term.dimension.key,
        )
        for term in terms
    ]
