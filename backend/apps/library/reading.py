"""Reading the library (INV-03, INV-04, INV-05, FP-01, FP-03): the helpers every library
read shares, and the obligations list. Nothing here writes.

- `localized()` picks one translation row in the caller's language order (INV-05).
- `partial_date()` is a legal date with its precision (playbook 4.3).
- `vocabulary_refs()` labels every distinct vocabulary row or term of a page from one
  query over its label table.
- `obligation_scopes()` is the one place for the scope rule: an obligation's scope is its
  own terms plus its instrument's regime. Neither inherits a jurisdiction term.
  `scope_term_ids()` is its SQL twin, which the list hands to the database's
  `taxonomy_in_footprint` and to the term filter; the tests pin the two to each other.
- `outside_reasons()` is the footprint verdict and its reason, built on
  `taxonomy.matching`: a record is inside when it has no reason to be outside.
- "As of" a date is `logic.in_force()` and nothing else (AC-INV1).

Every response object is validated as it is built, natively by pydantic
(`schemas.LibraryResponse`), and the page validates every row again when it takes them.

Every query runs on the request's connection, as cw_app under forced row-level security
in production: an instrument or obligation is shared or the caller's own (INPUT_DELTAS
§5), and child rows are only ever read through an obligation the caller can see.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection, Iterable, Mapping
from typing import Any
from zoneinfo import ZoneInfo

from django.contrib.postgres.expressions import ArraySubquery
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.lookups import DataContains
from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Exists, F, Func, OuterRef, Q, UUIDField, Value
from django.utils import timezone

from apps.library.logic import in_force
from apps.library.models import Obligation, ObligationTag, ObligationTerm, ObligationTitle, ObligationVersion, Translation
from apps.library.schemas import (
    LibraryRef,
    LocalizedText,
    ObligationInstrumentRef,
    ObligationQuery,
    ObligationRow,
    ObligationVersionRef,
    OutsideReason,
    PartialDate,
    ScopeDimension,
)
from apps.shared.models import Tenant
from apps.taxonomy import matching, terms_logic
from apps.taxonomy.models import DutyTypeLabel, InstrumentLevelLabel, LibraryTag, LibraryTagLabel, TaxonomyTerm, TaxonomyTermLabel
from apps.taxonomy.reading import Labels, label_of


# ---------------------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------------------
def localized(rows: Iterable[Translation], order: list[str]) -> LocalizedText | None:
    """The text in the first language of `order` that has one, then the original, then any
    (INV-05). Says which language it is and whether a machine wrote it."""
    by_language = {row.language_id: row for row in rows}
    chosen = next((by_language[code] for code in order if code in by_language), None)
    chosen = chosen or next((row for row in by_language.values() if row.is_original), None)
    chosen = chosen or next(iter(by_language.values()), None)
    if chosen is None:
        return None
    return LocalizedText(text=chosen.text, language=chosen.language_id, is_original=chosen.is_original, is_machine=chosen.is_machine)


def partial_date(value: datetime.date | None, precision: str) -> PartialDate | None:
    return None if value is None else PartialDate(date=value, precision=precision)


def vocabulary_refs(label_model: type[Any], rows: Iterable[Any], order: list[str], *, field: str = "vocabulary") -> dict[uuid.UUID, LibraryRef]:
    """`{key, kind, label}` per distinct vocabulary row or term, however many records carry
    it, from one query over `label_model`. A term has no kind of its own: its dimension is
    its kind."""
    distinct = list({row.id: row for row in rows}.values())
    labels = Labels.for_rows(label_model, distinct, field=field)
    return {
        row.id: LibraryRef(
            key=row.key,
            kind=getattr(row, "kind", None),
            label=label_of(labels.texts(row.id), order, original=labels.original(row.id), key=row.key),
        )
        for row in distinct
    }


def today_for(tenant: Tenant) -> datetime.date:
    """Today where the tenant is: the default "as of" of every library read."""
    return timezone.localdate(timezone=ZoneInfo(tenant.timezone))


# ---------------------------------------------------------------------------------------
# Scope and footprint (FP-01, FP-03)
# ---------------------------------------------------------------------------------------
def obligation_scopes(obligation_ids: Collection[uuid.UUID] | None = None) -> dict[uuid.UUID, dict[str, list[TaxonomyTerm]]]:
    """The scope rule, in one place: an obligation's own terms plus its instrument's regime,
    grouped by dimension key in the terms' order. For the given obligations, or for every
    one the caller can see; three queries either way. An obligation with no terms has no
    entry: it matches every footprint."""
    obligations = Obligation.objects.all() if obligation_ids is None else Obligation.objects.filter(id__in=obligation_ids)
    pairs = {
        *ObligationTerm.objects.filter(obligation__in=obligations).order_by().values_list("obligation_id", "term_id"),
        *obligations.filter(instrument__regime__isnull=False).order_by().values_list("id", "instrument__regime_id"),
    }
    terms = TaxonomyTerm.objects.select_related("dimension").in_bulk({term_id for _, term_id in pairs})
    scopes: dict[uuid.UUID, dict[str, list[TaxonomyTerm]]] = {}
    for obligation_id, term_id in sorted(pairs, key=lambda pair: (terms[pair[1]].sort_order, terms[pair[1]].key)):
        term = terms[term_id]
        scopes.setdefault(obligation_id, {}).setdefault(term.dimension.key, []).append(term)
    return scopes


def scope_term_ids() -> Func:
    """The SQL twin of `obligation_scopes()`: the obligation's own term ids plus its
    instrument's regime id, as one uuid[]."""
    own = ArraySubquery(ObligationTerm.objects.filter(obligation=OuterRef("pk")).order_by().values("term_id"))
    regime = Func(F("instrument__regime_id"), template="array_remove(ARRAY[%(expressions)s], NULL)", output_field=ArrayField(UUIDField()))
    return Func(own, regime, function="array_cat", output_field=ArrayField(UUIDField()))


def outside_reasons(
    scope: Mapping[str, Collection[str]], footprint: Mapping[str, Collection[str]], restricting: Collection[str]
) -> list[str]:
    """The dimensions in which a record falls outside the footprint, one at a time through
    `taxonomy.matching.in_footprint`; an empty list is the verdict "inside"."""
    return [
        dimension
        for dimension, keys in scope.items()
        if not matching.in_footprint({dimension: keys}, footprint, restricting=restricting)
    ]


def scope_rows(
    scope: Mapping[str, list[TaxonomyTerm]],
    dimensions: list[tuple[LibraryRef, int]],
    refs: Mapping[uuid.UUID, LibraryRef],
) -> list[ScopeDimension]:
    """Every active dimension with the record's terms in it, in the picker's order: an empty
    one is listed too, because it means "no restriction" and the screen says so."""
    rows: list[ScopeDimension] = []
    for dimension, term_count in dimensions:
        terms = scope.get(dimension.key, [])
        rows.append(
            ScopeDimension(
                dimension=dimension,
                terms=[refs[term.id] for term in terms],
                all_selected=bool(term_count) and sum(term.active for term in terms) == term_count,
            )
        )
    return rows


# ---------------------------------------------------------------------------------------
# GET /obligations
# ---------------------------------------------------------------------------------------
def _terms_of(refs: list[str]) -> list[TaxonomyTerm]:
    """The active terms `dimension:key`, resolved in one query. 422 for a malformed one, 422
    `unknown_key` naming every one that is not a term."""
    wanted = Q()
    for ref in refs:
        dimension, separator, key = ref.partition(":")
        if not separator:
            raise ValidationError(f"{ref!r} is not a term. Write it as dimension:key, for example service_type:advice.", code="validation_error")
        wanted |= Q(dimension__key=dimension, key=key)
    found = {
        f"{term.dimension.key}:{term.key}": term
        for term in TaxonomyTerm.objects.select_related("dimension").filter(wanted, active=True, dimension__active=True)
    }
    unknown = [ref for ref in refs if ref not in found]
    if unknown:
        raise ValidationError(
            f"Not a term: {', '.join(unknown)}. GET /taxonomy/terms lists the terms of every dimension.", code="unknown_key"
        )
    return list(found.values())


def _version_ref(version: ObligationVersion | None) -> ObligationVersionRef | None:
    if version is None:
        return None
    return ObligationVersionRef(
        version_number=version.version_number,
        effective_from=partial_date(version.effective_from, version.effective_from_precision),
    )


def upcoming(versions: Iterable[ObligationVersion], on: datetime.date) -> ObligationVersion | None:
    """The next version to take effect after `on`, the one `in_force()` will return next."""
    later = [v for v in versions if v.effective_from is not None and v.effective_from > on]
    return min(later, key=lambda v: (v.effective_from, v.version_number), default=None)


def obligation_page(tenant: Tenant, order: list[str], query: ObligationQuery, *, limit: int, offset: int) -> tuple[list[ObligationRow], int]:
    """The obligations the tenant sees (INV-03), filtered, as of a date (INV-04), inside
    its footprint unless `outsideFootprint` asks for everything (FP-03). The same number of
    queries whatever the page size (NFR-02)."""
    as_of = query.as_of or today_for(tenant)
    footprint = matching.footprint_of(tenant.id)
    restricting = matching.restricting_dimensions()
    scope_ids = scope_term_ids()
    queryset = Obligation.objects.all()
    if query.instrument:
        queryset = queryset.filter(instrument__stable_key=query.instrument)
    if query.duty_type:
        queryset = queryset.filter(duty_type__key=query.duty_type)
    if query.term:
        wanted = Value([term.id for term in _terms_of(query.term)], output_field=ArrayField(UUIDField()))
        queryset = queryset.filter(DataContains(scope_ids, wanted))
    if query.q:
        titled = ObligationTitle.objects.filter(obligation=OuterRef("pk"), text__icontains=query.q)
        queryset = queryset.filter(Q(ref_label__icontains=query.q) | Exists(titled))
    if not query.outside_footprint:
        queryset = queryset.filter(
            Func(Value(tenant.id, output_field=UUIDField()), scope_ids, function=matching.SQL_FUNCTION, output_field=BooleanField())
        )
    total = queryset.count()
    page = list(
        queryset.order_by("stable_key").select_related("instrument__level", "duty_type").prefetch_related("titles", "versions")[
            offset : offset + limit
        ]
    )
    ids = [obligation.id for obligation in page]
    scopes = obligation_scopes(ids)
    tag_pairs = list(ObligationTag.objects.filter(obligation_id__in=ids).values_list("obligation_id", "tag_id"))
    term_refs = vocabulary_refs(
        TaxonomyTermLabel, (term for scope in scopes.values() for terms in scope.values() for term in terms), order, field="term"
    )
    tag_refs = vocabulary_refs(LibraryTagLabel, LibraryTag.objects.filter(id__in={tag_id for _, tag_id in tag_pairs}), order)
    duty_refs = vocabulary_refs(DutyTypeLabel, (obligation.duty_type for obligation in page), order)
    level_refs = vocabulary_refs(InstrumentLevelLabel, (obligation.instrument.level for obligation in page), order)
    tags_of: dict[uuid.UUID, list[LibraryRef]] = {}
    for obligation_id, tag_id in tag_pairs:
        tags_of.setdefault(obligation_id, []).append(tag_refs[tag_id])
    dimensions = [
        (LibraryRef(key=ref.key, kind=ref.kind, label=ref.label), term_count)
        for ref, _restricts, term_count in terms_logic.dimensions_for_footprint(order)
    ]
    by_key = {dimension.key: dimension for dimension, _count in dimensions}
    rows: list[ObligationRow] = []
    for obligation in page:
        scope = scopes.get(obligation.id, {})
        outside = outside_reasons({key: {term.key for term in terms} for key, terms in scope.items()}, footprint, restricting)
        versions = list(obligation.versions.all())
        instrument = obligation.instrument
        rows.append(
            ObligationRow(
                id=obligation.id,
                stable_key=obligation.stable_key,
                ref_label=obligation.ref_label,
                title=localized(obligation.titles.all(), order),
                instrument=ObligationInstrumentRef(key=instrument.stable_key, short_name=instrument.short_name),
                binding_level=level_refs[instrument.level_id],
                binding=instrument.binding,
                duty_type=duty_refs[obligation.duty_type_id],
                tags=tags_of.get(obligation.id, []),
                scope=scope_rows(scope, dimensions, term_refs),
                version=_version_ref(in_force(versions, as_of)),
                upcoming_version=_version_ref(upcoming(versions, as_of)),
                in_footprint=not outside,
                outside_reason=[
                    OutsideReason(dimension=by_key[key], terms=[term_refs[term.id] for term in scope[key]])
                    for key in outside
                ],
                last_verified_at=obligation.last_verified_at,
                open_change_count=0,
                pending_applicability=None,
                compliance_status=None,
            )
        )
    return rows, total
