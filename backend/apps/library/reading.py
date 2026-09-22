"""Reading the library (INV-03, INV-04, INV-05, INV-06, FP-01, FP-03): the helpers every
library read shares, the obligations list, one obligation and the diff between two of its
versions. Nothing here writes.

- `localized()` picks one translation row in the caller's language order (INV-05).
- `partial_date()` is a legal date with its precision (playbook 4.3).
- `vocabulary_refs()` labels every distinct vocabulary row or term of a page from one
  query over its label table.
- `obligation_scopes()` is the one place for the scope rule: an obligation's scope is its
  own terms plus its instrument's regime. Neither inherits a jurisdiction term.
  `scope_term_ids()` is its SQL twin, which the list hands to the database's
  `taxonomy_in_footprint` and to the term filter; the tests pin the two to each other.
- `outside_reasons()` is the footprint verdict and its reason, built on
  `taxonomy.matching`: a record is inside when it has no reason to be outside, and
  `scope_and_verdict()` builds both for a row of the list and for a record's own card.
- `terms_of()` is the one parser of `dimension:key`, for the obligations filter and for
  an obligation proposal's scope.
- `active_obligation()` and `unknown_provision_keys()` are what a proposal points at and
  cites; they live here because the library fence keeps library models out of the
  proposals app (PRO-01).
- "As of" a date is `logic.in_force()` and nothing else (AC-INV1). A version's end date is
  never stored: `version_rows()` derives it from the version that follows (INV-04).
- `_visible()` is the one lookup of a record by id, and `obligation_subject()` and
  `instrument_subject()` are what the write routes address their record through: what
  row-level security does not show the caller is a 404, never a 403, so no id can be
  probed for.

Every response object is validated as it is built, natively by pydantic
(`schemas.LibraryResponse`), and the page validates every row again when it takes them: a
value the database or a later change gets wrong fails the read rather than reaching the
caller.

Every query runs on the request's connection, as cw_app under forced row-level security
in production: an instrument or obligation is shared or the caller's own (INPUT_DELTAS
§5), and child rows are only ever read through an obligation the caller can see.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection, Iterable, Mapping
from typing import Any, NamedTuple, NoReturn, TypeVar
from zoneinfo import ZoneInfo

from django.contrib.postgres.expressions import ArraySubquery
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.lookups import DataContains
from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Exists, F, Func, Model, OuterRef, Q, QuerySet, UUIDField, Value
from django.utils import timezone

from apps.library.logic import in_force, version_diff
from apps.library.models import (
    Authority,
    Instrument,
    JurisdictionLabel,
    Obligation,
    ObligationRelation,
    ObligationTag,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    RecordStatus,
    Translation,
)
from apps.library.schemas import (
    DiffSegment,
    LibraryAuthority,
    LibraryRef,
    LocalizedText,
    ObligationAsOfQuery,
    ObligationDetail,
    ObligationDiffQuery,
    ObligationInstrumentRef,
    ObligationInstrumentSummary,
    ObligationProvenance,
    ObligationProvisionRef,
    ObligationQuery,
    ObligationRow,
    ObligationVersionRef,
    ObligationVersionRow,
    OutsideReason,
    PartialDate,
    RelatedObligation,
    ScopeDimension,
    VersionDiff,
)
from apps.shared.models import Tenant
from apps.shared.errors import ProblemError
from apps.taxonomy import matching, terms_logic
from apps.taxonomy.models import (
    DutyTypeLabel,
    InstrumentLevelLabel,
    LibraryTag,
    LibraryTagLabel,
    RelationTypeLabel,
    TaxonomyTerm,
    TaxonomyTermLabel,
)
from apps.taxonomy.reading import Labels, label_of
from apps.taxonomy.schemas import PersonRef


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
    return None if chosen is None else text_of(chosen)


def text_of(row: Translation) -> LocalizedText:
    """One translation row as the screen reads it: the text, its language, and whether it is
    the original or a machine translation still waiting for a person (INV-05)."""
    return LocalizedText(text=row.text, language=row.language_id, is_original=row.is_original, is_machine=row.is_machine)


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


class RecordHeading(NamedTuple):
    """How a record outside the library app names one of its rows: the record's own title,
    its reference inside its instrument and that instrument's short name. The library's own
    wording, never a proposal's or a case's description of it."""

    title: str
    reference_label: str
    instrument_short_name: str


def obligation_headings(obligation_ids: Collection[uuid.UUID], order: list[str]) -> dict[uuid.UUID, RecordHeading]:
    """How to name each of these duties, in two queries however many ids there are, so a
    list that points at library records stays constant in its row count. An id the caller
    cannot see, or that no longer exists, is simply absent."""
    if not obligation_ids:
        return {}
    rows = list(
        Obligation.objects.filter(id__in=obligation_ids).select_related("instrument").prefetch_related("titles")
    )
    headings = {}
    for row in rows:
        title = localized(row.titles.all(), order)
        headings[row.id] = RecordHeading(
            title="" if title is None else title.text,
            reference_label=row.ref_label,
            instrument_short_name=row.instrument.short_name,
        )
    return headings


def obligation_scope_refs(obligation_id: uuid.UUID) -> list[str]:
    """One duty's own scope facets as `dimension:key`, in the order a reader sees them and
    the spelling a proposal's payload uses. The instrument's regime is deliberately not
    here: a proposal replaces the record's own terms and never the instrument's, so this is
    the list a reviewer compares a proposed scope against."""
    return [
        f"{link.term.dimension.key}:{link.term.key}"
        for link in ObligationTerm.objects.filter(obligation_id=obligation_id).select_related("term__dimension")
    ]


def today_for(tenant: Tenant) -> datetime.date:
    """Today where the tenant is: the default "as of" of every library read."""
    return timezone.localdate(timezone=ZoneInfo(tenant.timezone))


def terms_of(refs: list[str]) -> list[TaxonomyTerm]:
    """The active terms `dimension:key`, resolved in one query however many there are. 422
    for a malformed one, 422 `unknown_key` naming every one that is not a term. The one
    parser: the obligations filter and an obligation proposal's scope read the same
    spelling the same way. `refs` is never empty, because an empty list matches every
    term."""
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


# ---------------------------------------------------------------------------------------
# What a proposal points at (PRO-01). These live here, not in the proposals app, because
# the library fence refuses a module that names a library model beside a write call
# (apps/shared/tests_library_fence.py); both are pure reads.
# ---------------------------------------------------------------------------------------
def active_obligation(obligation_id: uuid.UUID) -> Obligation:
    """The obligation `obligation_id` while it is active, or 422 `unknown_key`.

    A proposal that names an obligation nobody can find, or one that has been retired, is
    refused where it is made rather than left in the queue for a reviewer to discover that
    it can never be applied (PRO-01).
    """
    # INV-07 (R3): once a bank can hold a private obligation of its own, this lookup also
    # finds that bank's own rows, and a library proposal must only ever target a shared
    # record. Add `owner_tenant__isnull=True` with the first row that can carry an owner.
    obligation = Obligation.objects.filter(pk=obligation_id).first()  # ordering: pk lookup, at most one row
    if obligation is None:
        raise ValidationError("That obligation is not here.", code="unknown_key")
    if obligation.status != RecordStatus.ACTIVE.value:
        raise ValidationError("That obligation is retired: propose a change to one that is in force.", code="unknown_key")
    return obligation


def unknown_provision_keys(keys: Collection[str]) -> set[str]:
    """Those of `keys` that name no provision of the library, in one query. A proposal may
    cite its source as a provision's stable key instead of a link (PRO-01), and a key that
    resolves to nothing is a source nobody can follow."""
    found = set(Provision.objects.filter(stable_key__in=keys).values_list("stable_key", flat=True))
    return {key for key in keys if key not in found}


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


def footprint_dimensions(order: list[str]) -> dict[str, tuple[LibraryRef, int]]:
    """Every active dimension by key, labelled, in the picker's order, with the number of
    active terms in it: what `allSelected` is measured against. Read once per request,
    whatever the page size."""
    return {
        ref.key: (LibraryRef(key=ref.key, kind=ref.kind, label=ref.label), term_count)
        for ref, _restricts, term_count in terms_logic.dimensions_for_footprint(order)
    }


def scope_and_verdict(
    scope: Mapping[str, list[TaxonomyTerm]],
    dimensions: Mapping[str, tuple[LibraryRef, int]],
    refs: Mapping[uuid.UUID, LibraryRef],
    footprint: Mapping[str, Collection[str]],
    restricting: Collection[str],
) -> tuple[list[ScopeDimension], list[OutsideReason]]:
    """What one record carries and why the footprint would hide it, built in one place so a
    row of the list and the record's own card can never answer differently (FP-01, FP-03).

    Every active dimension is listed, an empty one too, because it means "no restriction"
    and the screen says so; `allSelected` means every active term of it is carried."""
    carried: list[ScopeDimension] = []
    for key, (dimension, term_count) in dimensions.items():
        terms = scope.get(key, [])
        carried.append(
            ScopeDimension(
                dimension=dimension,
                terms=[refs[term.id] for term in terms],
                all_selected=bool(term_count) and sum(term.active for term in terms) == term_count,
            )
        )
    outside = outside_reasons({key: {term.key for term in terms} for key, terms in scope.items()}, footprint, restricting)
    reasons = [OutsideReason(dimension=dimensions[key][0], terms=[refs[term.id] for term in scope[key]]) for key in outside]
    return carried, reasons


# ---------------------------------------------------------------------------------------
# GET /obligations
# ---------------------------------------------------------------------------------------
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
        wanted = Value([term.id for term in terms_of(query.term)], output_field=ArrayField(UUIDField()))
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
    dimensions = footprint_dimensions(order)
    rows: list[ObligationRow] = []
    for obligation in page:
        scope = scopes.get(obligation.id, {})
        carried, outside = scope_and_verdict(scope, dimensions, term_refs, footprint, restricting)
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
                scope=carried,
                version=_version_ref(in_force(versions, as_of)),
                upcoming_version=_version_ref(upcoming(versions, as_of)),
                in_footprint=not outside,
                outside_reason=outside,
                last_verified_at=obligation.last_verified_at,
                open_change_count=0,
                pending_applicability=None,
                compliance_status=None,
            )
        )
    return rows, total


# ---------------------------------------------------------------------------------------
# Addressing one record: GET /obligations/{id}, its diff, and the writes a record accepts
# ---------------------------------------------------------------------------------------
NOT_FOUND = "There is nothing at this address in your organisation."

_Record = TypeVar("_Record", bound=Model)


def _visible(queryset: QuerySet[_Record], record_id: uuid.UUID) -> _Record:
    """The record as row-level security lets the caller see it: a shared one or their own
    (INPUT_DELTAS §5). A record they cannot see is not there, so another tenant's private
    obligation and an id that never existed answer the same 404 (INV-07)."""
    record = queryset.filter(pk=record_id).first()  # ordering: pk lookup, at most one row
    if record is None:
        raise ValidationError(NOT_FOUND, code="not_found")
    return record


def obligation_subject(obligation_id: uuid.UUID) -> Obligation:
    """The obligation a write acts on (INV-06). It carries no prefetch: a report and a
    re-verification read the record itself, never its versions or its scope."""
    return _visible(Obligation.objects.all(), obligation_id)


def instrument_subject(instrument_id: uuid.UUID) -> Instrument:
    """The instrument a write acts on. A provision is reported through the instrument whose
    card shows it (chunk 3 default), so this one lookup serves both."""
    return _visible(Instrument.objects.all(), instrument_id)


def version_rows(versions: list[ObligationVersion]) -> dict[int, ObligationVersionRow]:
    """Every version by number, in version order. `effectiveTo` is derived: a version runs
    until the day before the next one takes effect, at the precision that next date is known
    to. Nothing is stored, because a version row is written once and never touched (INV-04).
    The last version, one whose successor has no date, and one corrected the same day it
    took effect (`logic.in_force`: the later number wins) have no end, since an end before
    the start would be a lie on the card."""
    rows: dict[int, ObligationVersionRow] = {}
    for index, version in enumerate(versions):
        following = versions[index + 1] if index + 1 < len(versions) else None
        ends = None
        if (
            following is not None
            and following.effective_from is not None
            and (version.effective_from is None or following.effective_from > version.effective_from)
        ):
            ends = partial_date(following.effective_from - datetime.timedelta(days=1), following.effective_from_precision)
        rows[version.version_number] = ObligationVersionRow(
            version_number=version.version_number,
            effective_from=partial_date(version.effective_from, version.effective_from_precision),
            effective_to=ends,
            approved_at=version.approved_at,
        )
    return rows


def _related_obligations(obligation: Obligation, order: list[str]) -> list[RelatedObligation]:
    """The obligations a reader should see beside this one (INV-03). The join to the related
    record runs under the same row-level security, so a relation to a record the caller
    cannot see brings back nothing and is never reported."""
    relations = list(
        ObligationRelation.objects.filter(from_obligation=obligation).select_related("to_obligation__instrument", "relation_type")
    )
    titles: dict[uuid.UUID, list[ObligationTitle]] = {}
    for title in ObligationTitle.objects.filter(obligation_id__in=[relation.to_obligation_id for relation in relations]):
        titles.setdefault(title.obligation_id, []).append(title)
    relation_refs = vocabulary_refs(RelationTypeLabel, (relation.relation_type for relation in relations), order)
    return [
        RelatedObligation(
            id=relation.to_obligation_id,
            title=localized(titles.get(relation.to_obligation_id, []), order),
            instrument=ObligationInstrumentRef(
                key=relation.to_obligation.instrument.stable_key, short_name=relation.to_obligation.instrument.short_name
            ),
            binding=relation.to_obligation.instrument.binding,
            relation=relation_refs[relation.relation_type_id],
        )
        for relation in relations
    ]


def obligation_detail(tenant: Tenant, order: list[str], obligation_id: uuid.UUID, query: ObligationAsOfQuery) -> ObligationDetail:
    """One obligation as of a date (INV-03, INV-04) in the caller's language order (INV-05),
    with the footprint verdict the list gives it (FP-03) and its provenance (INV-06). The
    queries fan out: their number does not grow with the versions, terms, tags, provisions
    or related obligations the record carries."""
    obligation = _visible(
        Obligation.objects.select_related("instrument__level", "duty_type", "verified_by").prefetch_related(
            "titles", "instrument__titles", "versions__summaries", "tags", "provisions"
        ),
        obligation_id,
    )
    as_of = query.as_of or today_for(tenant)
    instrument = obligation.instrument
    versions = list(obligation.versions.all())
    current = in_force(versions, as_of)
    summaries = list(current.summaries.all()) if current is not None else []
    scope = obligation_scopes([obligation.id]).get(obligation.id, {})
    tags = list(obligation.tags.all())
    term_refs = vocabulary_refs(TaxonomyTermLabel, (term for terms in scope.values() for term in terms), order, field="term")
    tag_refs = vocabulary_refs(LibraryTagLabel, tags, order)
    duty_refs = vocabulary_refs(DutyTypeLabel, [obligation.duty_type], order)
    level_refs = vocabulary_refs(InstrumentLevelLabel, [instrument.level], order)
    carried, outside = scope_and_verdict(
        scope, footprint_dimensions(order), term_refs, matching.footprint_of(tenant.id), matching.restricting_dimensions()
    )
    rows = version_rows(versions)
    verifier = obligation.verified_by
    return ObligationDetail(
        id=obligation.id,
        stable_key=obligation.stable_key,
        ref_label=obligation.ref_label,
        title=localized(obligation.titles.all(), order),
        instrument=ObligationInstrumentSummary(
            key=instrument.stable_key,
            short_name=instrument.short_name,
            name=localized(instrument.titles.all(), order),
            official_ref=instrument.official_ref,
            implements_note=instrument.implements_note,
        ),
        regime=term_refs[instrument.regime_id] if instrument.regime_id else None,
        binding_level=level_refs[instrument.level_id],
        binding=instrument.binding,
        duty_type=duty_refs[obligation.duty_type_id],
        trigger_frequency=obligation.trigger_frequency,
        retention=obligation.retention,
        sanction_exposure=obligation.sanction_exposure,
        product_scope=obligation.product_scope,
        tags=[tag_refs[tag.id] for tag in tags],
        scope=carried,
        in_footprint=not outside,
        outside_reason=outside,
        summary=localized(summaries, order),
        translations=[text_of(summary) for summary in summaries],
        version=rows[current.version_number] if current is not None else None,
        versions=list(rows.values()),
        provisions=[
            ObligationProvisionRef(id=provision.id, ref_label=provision.ref_label, path=provision.path)
            for provision in obligation.provisions.all()
        ],
        related=_related_obligations(obligation, order),
        provenance=ObligationProvenance(
            created_origin=obligation.created_origin,
            created_model=obligation.created_model,
            created_at=obligation.created_at,
            verified_by=None if verifier is None else PersonRef(id=verifier.id, name=verifier.name),
            last_verified_at=obligation.last_verified_at,
            source_url=obligation.source_url,
            source_label=obligation.source_label,
        ),
    )


def _numbered(versions: list[ObligationVersion], number: int) -> ObligationVersion:
    """The version the caller named; a number this obligation has no version for is a 422."""
    found = next((version for version in versions if version.version_number == number), None)
    if found is None:
        raise ValidationError(f"This obligation has no version {number}.", code="unknown_key")
    return found


def obligation_diff(order: list[str], obligation_id: uuid.UUID, query: ObligationDiffQuery) -> VersionDiff:
    """"Show what changed" between two versions of one obligation (INV-04, AC-INV1), by
    default the latest against the one before it. The comparison itself is `version_diff`,
    which is pure and writes nothing to a log: the summaries are the library's content."""
    obligation = _visible(Obligation.objects.prefetch_related("versions__summaries"), obligation_id)
    versions = list(obligation.versions.all())
    if len(versions) < 2 and (query.from_version is None or query.to_version is None):
        raise ValidationError("There are not two versions of this obligation to compare.")
    older = _numbered(versions, query.from_version) if query.from_version is not None else versions[-2]
    newer = _numbered(versions, query.to_version) if query.to_version is not None else versions[-1]
    compared = version_diff(older.summaries.all(), newer.summaries.all(), order, query.lang)
    if compared is None:
        raise ValidationError("These two versions have no language in common, so there is nothing to compare.")
    language, is_machine, segments = compared
    return VersionDiff(
        from_version=older.version_number,
        to_version=newer.version_number,
        from_effective=partial_date(older.effective_from, older.effective_from_precision),
        to_effective=partial_date(newer.effective_from, newer.effective_from_precision),
        language=language,
        is_machine=is_machine,
        segments=[DiffSegment(op=op, text=text) for op, text in segments],
    )


# ---------------------------------------------------------------------------------------
# GET /authorities (FP-04, AGT-02, chunk 5 ruling E)
# ---------------------------------------------------------------------------------------
def list_authorities(order: list[str]) -> list[LibraryAuthority]:
    """Every issuing authority the shared library knows, with its jurisdiction labelled in
    the caller's language. Two queries: the authorities with their jurisdiction rows, and
    every jurisdiction label at once.

    It addresses no single record, so it needs no `_visible()` lookup: an authority is a
    shared reference row, the same list for every bank and for every agent key.
    """
    authorities = list(Authority.objects.select_related("jurisdiction"))
    jurisdictions = vocabulary_refs(JurisdictionLabel, (row.jurisdiction for row in authorities), order)
    return [
        LibraryAuthority(
            id=row.id,
            key=row.key,
            short_name=row.short_name,
            name=row.name,
            jurisdiction=jurisdictions[row.jurisdiction_id],
            url=row.url,
        )
        for row in authorities
    ]


# ---------------------------------------------------------------------------------------
# Declared ahead of its logic (chunk 5 plan rule 1)
# ---------------------------------------------------------------------------------------
def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def get_record_sources() -> NoReturn:
    """`GET /obligations/{obligationId}/sources`, the citations a re-check compares against
    (AGT-01, item 3). Built by `c5-library-recheck`.

    It resolves the obligation through `_visible()` above, as every other addressed read in
    this module does, and never through a lookup of its own: that one function is what makes
    a record the caller cannot see answer the same 404 as an id that never existed, so a
    second lookup would be a second chance to leak which of the two it was (INV-07).
    """
    _not_built("A record's citations are not built yet.")
