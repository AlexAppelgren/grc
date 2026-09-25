"""Reading the library (INV-01, INV-03, INV-04, INV-05, INV-06, FP-01, FP-03): the helpers
every library read shares, the obligations list and card, the instruments list and card,
and the diffs between two versions. Nothing here writes.

- `localized()` picks one translation row in the caller's language order (INV-05).
- `partial_date()` is a legal date with its precision (playbook 4.3).
- `vocabulary_refs()` labels every distinct vocabulary row or term of a page from one
  query over its label table.
- `instrument_scopes()` is the one place for an instrument's own scope: its regime and
  the jurisdictions its rules reach, derived from its jurisdiction and never stored
  (D-28, D-29). `obligation_scopes()` inherits through it: an obligation's scope is its
  own terms plus its instrument's scope. `instrument_scope_term_ids()` and
  `scope_term_ids()` are their SQL twins, which the lists and search hand to the
  database's `taxonomy_in_footprint`, unchanged, and to the term filter; the tests pin
  them to their Python counterparts.
- `in_view()` is the lists' one footprint filter (FP-03, FP-04): `in`, `all`, or
  `watched`, what the watched markets add, asked of the same database function twice.
- `outside_reasons()` is the footprint verdict and its reason, built on
  `taxonomy.matching`: a record is inside when it has no reason to be outside, and
  `scope_and_verdict()` builds both for a row of the list and for a record's own card.
- `terms_of()` is the one parser of `dimension:key`, for the obligations filter and for
  an obligation proposal's scope.
- `tenant_tags()` is the caller's bank's own tags on a page of obligations, from one query
  (VOC-08); `tagged()` is the `tag` and `tenantTag` filters, each key resolved against its
  own list first so a key that names nothing is a 422, never an empty page.
- `active_obligation()` and `unknown_provision_keys()` are what a proposal points at and
  cites; they live here because the library fence keeps library models out of the
  proposals app (PRO-01). `instrument_refs()`, `shared_instrument()`, `live_duty_type()`
  and `stable_key_taken()` are what a new instrument or obligation names, for the same
  reason.
- "As of" a date is `logic.in_force()` and nothing else (AC-INV1). A version's end date is
  never stored: `version_rows()` derives it from the version that follows (INV-04).
- `confirmation_of()` is who confirmed each version's approval and which agent proposed it
  (INV-05, PRO-02, D-62), read the same way wherever a version appears: the list's
  versions, the card's version list and provenance, and both sides of a diff. Every read
  that names a version fetches it through `versions_with_confirmation()`, so naming both
  agents costs no query per version.
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
from typing import Any, NamedTuple, TypeVar
from zoneinfo import ZoneInfo

from django.contrib.postgres.expressions import ArraySubquery
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.lookups import DataContains
from django.core.exceptions import ValidationError
from django.db.models import Count, Exists, F, Func, Model, OuterRef, Prefetch, Q, QuerySet, UUIDField, Value
from django.db.models.functions import JSONObject
from django.utils import timezone

from apps.library.logic import in_force, version_diff
from apps.library.models import (
    Authority,
    Instrument,
    InstrumentRelation,
    InstrumentTitle,
    JurisdictionLabel,
    Obligation,
    ObligationProvision,
    ObligationRelation,
    ObligationTag,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
    RecordStatus,
    SubjectType,
    Translation,
)
from apps.library.schemas import (
    DiffSegment,
    FootprintFilter,
    InstrumentAuthorityRef,
    InstrumentDetail,
    InstrumentLineageRef,
    InstrumentProvisionsQuery,
    InstrumentQuery,
    InstrumentRow,
    LibraryAuthority,
    LibraryRecordSource,
    LibraryRecordSources,
    LibraryRef,
    LocalizedText,
    ObligationAsOfQuery,
    ObligationDetail,
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
    ProvisionCitedObligation,
    ProvisionNode,
    ProvisionVersionRow,
    RelatedObligation,
    ScopeDimension,
    VersionConfirmation,
    VersionDiff,
    VersionDiffQuery,
)
from apps.shared.models import Tenant
from apps.taxonomy import matching, terms_logic
from apps.taxonomy.models import (
    DutyTypeLabel,
    InstrumentLevelLabel,
    LibraryTag,
    LibraryTagLabel,
    ProvisionKindLabel,
    RelationTypeLabel,
    Tagging,
    TaxonomyTerm,
    TaxonomyTermLabel,
    TenantTag,
    TenantTagLabel,
    WatchedMarket,
)
from apps.taxonomy.reading import Labels, agent_ref, label_of, proposing_agent
from apps.taxonomy.schemas import PersonRef, TaggingTagRef


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


def instrument_headings(instrument_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, RecordHeading]:
    """How to name each of these instruments, in one query: its short name as the title and
    its official reference. An id the caller cannot see is simply absent."""
    if not instrument_ids:
        return {}
    return {
        row.id: RecordHeading(title=row.short_name, reference_label=row.official_ref, instrument_short_name=row.short_name)
        for row in Instrument.objects.filter(id__in=instrument_ids)
    }


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
# The tags on an obligation: the library's own and the bank's own (VOC-08)
# ---------------------------------------------------------------------------------------
_Listed = TypeVar("_Listed", bound=QuerySet[Any])


def tenant_tags(tenant: Tenant, obligation_ids: Collection[uuid.UUID], order: list[str]) -> dict[uuid.UUID, list[TaggingTagRef]]:
    """The caller's bank's own tags on each obligation, in the tag list's order, from one
    query whatever the page size: the taggings with their tags and every label of each tag.
    Read by the bank's id as well as under row-level security, so another bank's tag on the
    same shared record never reaches this one."""
    labels = ArraySubquery(
        TenantTagLabel.objects.filter(vocabulary_id=OuterRef("tag_id"))
        .order_by("language")
        .values(row=JSONObject(language="language", text="text", original="is_original"))
    )
    rows = (
        Tagging.objects.filter(tenant_id=tenant.id, subject_type=SubjectType.OBLIGATION, subject_id__in=obligation_ids)
        .annotate(tag_labels=labels)
        .order_by("tag__sort_order", "tag__key")
        .values_list("subject_id", "tag__key", "tag_labels")
    )
    found: dict[uuid.UUID, list[TaggingTagRef]] = {}
    for subject_id, key, tag_labels in rows:
        texts = {label["language"]: label["text"] for label in tag_labels}
        original = next((label["language"] for label in tag_labels if label["original"]), None)
        found.setdefault(subject_id, []).append(TaggingTagRef(key=key, kind=None, label=label_of(texts, order, original=original, key=key)))
    return found


def _tag_ids(tags: QuerySet[Any], keys: list[str], unknown_detail: str) -> list[uuid.UUID]:
    """The ids of the tags `keys` names in one query; 422 `unknown_key` naming every key
    that is not one."""
    found = dict(tags.filter(key__in=keys).values_list("key", "id"))
    unknown = [key for key in dict.fromkeys(keys) if key not in found]
    if unknown:
        raise ValidationError(unknown_detail.format(keys=", ".join(unknown)), code="unknown_key")
    return [found[key] for key in dict.fromkeys(keys)]


def refuse_bank_filters(tenant_id: uuid.UUID | None, query: ObligationQuery) -> None:
    """A caller that belongs to no bank, a platform key or session, has no tags of its own
    (VOC-08), so its `tenantTag` is refused by name rather than read against nobody's
    list."""
    if tenant_id is None and query.tenant_tag:
        raise ValidationError("tenantTag filters by a bank's own tags, and this caller belongs to no bank.", code="unknown_filter")


def tagged(queryset: _Listed, tenant: Tenant, query: ObligationQuery) -> _Listed:
    """The `tag` and `tenantTag` filters: every tag named must be on the obligation."""
    if query.tag:
        detail = "Not a library tag: {keys}. GET /vocab/library_tag lists the library's tags."
        for tag_id in _tag_ids(LibraryTag.objects.all(), query.tag, detail):
            queryset = queryset.filter(Exists(ObligationTag.objects.filter(obligation=OuterRef("pk"), tag_id=tag_id)))
    if query.tenant_tag:
        detail = "Not one of your organisation's tags: {keys}. GET /vocab/tenant_tag lists them."
        for tag_id in _tag_ids(TenantTag.objects.filter(tenant_id=tenant.id), query.tenant_tag, detail):
            bank_tagged = Tagging.objects.filter(
                tenant_id=tenant.id, tag_id=tag_id, subject_type=SubjectType.OBLIGATION, subject_id=OuterRef("pk")
            )
            queryset = queryset.filter(Exists(bank_tagged))
    return queryset


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
    # INV-07: a bank's own private obligation is visible to that bank under row-level
    # security, and a library proposal only ever targets a shared record.
    obligation = Obligation.objects.filter(pk=obligation_id, owner_tenant__isnull=True).first()  # ordering: pk lookup, at most one row
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
# What a new instrument or obligation names (PRO-01, INV-01, INV-03)
# ---------------------------------------------------------------------------------------
class InstrumentRefs(NamedTuple):
    """The library rows a new instrument's payload names, resolved once for the creation
    check and again for the apply."""

    level: Any
    jurisdiction: Any
    authority: Authority | None


def _live_row(model: Any, key: str, what: str) -> Any:
    row = model.objects.filter(key=key, active=True).first()  # ordering: a list holds one row per key
    if row is None:
        raise ValidationError(f"{key!r} is not {what} the library holds.", code="unknown_key")
    return row


def instrument_refs(*, level: str, jurisdiction: str, authority: str | None) -> InstrumentRefs:
    """The live instrument level, jurisdiction and authority a new instrument names, or
    422 `unknown_key` for the first one the library does not hold."""
    from apps.library.models import Jurisdiction
    from apps.taxonomy.models import InstrumentLevel

    found = None
    if authority:
        found = Authority.objects.filter(key=authority).first()  # ordering: a unique key
        if found is None:
            raise ValidationError(f"{authority!r} is not an authority the library holds.", code="unknown_key")
    return InstrumentRefs(
        level=_live_row(InstrumentLevel, level, "an instrument level"),
        jurisdiction=_live_row(Jurisdiction, jurisdiction, "a jurisdiction"),
        authority=found,
    )


def shared_instrument(key: str) -> Instrument:
    """The active shared instrument `key`, which a new obligation is broken out of, or 422
    `unknown_key`. A bank's private instrument is never one (INV-07)."""
    instrument = Instrument.objects.filter(stable_key=key, owner_tenant__isnull=True).first()  # ordering: a unique key
    if instrument is None:
        raise ValidationError(f"{key!r} is not an instrument the library holds.", code="unknown_key")
    if instrument.status != RecordStatus.ACTIVE.value:
        raise ValidationError(f"{key!r} is retired: propose the duty under an instrument in force.", code="unknown_key")
    return instrument


def live_duty_type(key: str) -> Any:
    """The live duty type `key`, or 422 `unknown_key`."""
    from apps.taxonomy.models import DutyType

    return _live_row(DutyType, key, "a duty type")


def stable_key_taken(subject: str, key: str) -> bool:
    """Whether an instrument, provision or obligation (`subject`) already carries `key`,
    whoever owns it: a stable key is unique across the library and is never reused."""
    models: dict[str, Any] = {SubjectType.INSTRUMENT.value: Instrument, SubjectType.PROVISION.value: Provision}
    return bool(models.get(subject, Obligation).objects.filter(stable_key__iexact=key).exists())


# ---------------------------------------------------------------------------------------
# What a provision proposal names (PRO-01, INV-02)
# ---------------------------------------------------------------------------------------
def active_provision(provision_id: uuid.UUID) -> Provision:
    """The shared provision `provision_id` while it is active, with its instrument, or 422
    `unknown_key`: a version of a provision nobody can find is never applied."""
    provision = (
        Provision.objects.select_related("instrument__level")
        .filter(pk=provision_id, instrument__owner_tenant__isnull=True)
        .first()  # ordering: pk lookup, at most one row
    )
    if provision is None:
        raise ValidationError("That provision is not here.", code="unknown_key")
    if provision.status != RecordStatus.ACTIVE.value:
        raise ValidationError("That provision is retired: propose a change to one that is in force.", code="unknown_key")
    return provision


def parent_provision(instrument: Instrument, key: str) -> Provision:
    """The active provision `key` of `instrument` a new provision sits under, or 422
    `unknown_key`: a node never hangs under another instrument's tree."""
    parent = Provision.objects.filter(stable_key=key, instrument=instrument, status=RecordStatus.ACTIVE.value).first()  # ordering: a unique key
    if parent is None:
        raise ValidationError(f"{key!r} is not a provision of {instrument.stable_key!r} in force.", code="unknown_key")
    return parent


def live_provision_kind(key: str) -> Any:
    """The live provision kind `key` (chapter, section, article), or 422 `unknown_key`."""
    from apps.taxonomy.models import ProvisionKind

    return _live_row(ProvisionKind, key, "a provision kind")


# ---------------------------------------------------------------------------------------
# Scope and footprint (FP-01, FP-03)
# ---------------------------------------------------------------------------------------
def instrument_scopes(instrument_ids: Collection[uuid.UUID] | None = None) -> dict[uuid.UUID, dict[str, list[TaxonomyTerm]]]:
    """An instrument's own scope, in one place (INV-01, FP-03, FP-04): its regime, and the
    jurisdictions its rules reach. `obligation_scopes()` inherits through this, so the
    list's footprint verdict and the instrument's own can never disagree. For the given
    instruments, or for every one the caller can see; two queries either way.

    The jurisdictions are derived here, at match time, and never stored (D-28, D-29): the
    term that mirrors the instrument's own jurisdiction and the terms that mirror every
    jurisdiction whose parent that one is, read from the mirror link and the parent link
    alone, so a Union rule reaches each member country and Norway and a national rule its
    own country only. A jurisdiction that no term mirrors derives nothing (D-38)."""
    instruments = Instrument.objects.all() if instrument_ids is None else Instrument.objects.filter(id__in=instrument_ids)
    rows = list(instruments.order_by().values_list("id", "regime_id", "jurisdiction_id"))
    jurisdictions = {jurisdiction_id for _, _, jurisdiction_id in rows}
    terms = (
        TaxonomyTerm.objects.select_related("dimension")
        .annotate(parent_jurisdiction_id=F("jurisdiction__parent"))
        .filter(Q(id__in={regime_id for _, regime_id, _ in rows}) | Q(jurisdiction__in=jurisdictions) | Q(jurisdiction__parent__in=jurisdictions))
        .order_by("sort_order", "key")
    )
    by_id: dict[uuid.UUID, TaxonomyTerm] = {}
    derived_for: dict[uuid.UUID, list[TaxonomyTerm]] = {}  # a jurisdiction's id: the terms its instruments derive
    for term in terms:
        by_id[term.id] = term
        for jurisdiction_id in {term.jurisdiction_id, term.parent_jurisdiction_id} - {None}:
            derived_for.setdefault(jurisdiction_id, []).append(term)
    scopes: dict[uuid.UUID, dict[str, list[TaxonomyTerm]]] = {}
    for instrument_id, regime_id, jurisdiction_id in rows:
        regime = by_id[regime_id]
        scope = scopes[instrument_id] = {regime.dimension.key: [regime]}
        for derived in derived_for.get(jurisdiction_id, []):
            scope.setdefault(derived.dimension.key, []).append(derived)
    return scopes


def obligation_scopes(obligation_ids: Collection[uuid.UUID] | None = None) -> dict[uuid.UUID, dict[str, list[TaxonomyTerm]]]:
    """The scope rule, in one place: an obligation's own terms plus its instrument's own
    scope (`instrument_scopes()`: its regime and the jurisdictions it reaches), grouped by
    dimension key in the terms' order, each term once. For the given obligations, or for
    every one the caller can see; five queries either way."""
    obligations = Obligation.objects.all() if obligation_ids is None else Obligation.objects.filter(id__in=obligation_ids)
    own_pairs = set(ObligationTerm.objects.filter(obligation__in=obligations).order_by().values_list("obligation_id", "term_id"))
    by_instrument = dict(obligations.order_by().values_list("id", "instrument_id"))
    inherited = instrument_scopes(set(by_instrument.values()))
    terms = TaxonomyTerm.objects.select_related("dimension").in_bulk({term_id for _, term_id in own_pairs})
    scopes: dict[uuid.UUID, dict[str, list[TaxonomyTerm]]] = {}
    for obligation_id, term_id in sorted(own_pairs, key=lambda pair: (terms[pair[1]].sort_order, terms[pair[1]].key)):
        term = terms[term_id]
        scopes.setdefault(obligation_id, {}).setdefault(term.dimension.key, []).append(term)
    for obligation_id, instrument_id in by_instrument.items():
        for dimension_key, dimension_terms in inherited.get(instrument_id, {}).items():
            carried = scopes.setdefault(obligation_id, {}).setdefault(dimension_key, [])
            known = {term.id for term in carried}
            carried.extend(term for term in dimension_terms if term.id not in known)
    return scopes


def _reach(path: str) -> Q:
    """The terms that mirror a jurisdiction the instrument's rules reach: its own, and every
    one whose parent it is. `path` leads from the outer row to the instrument: nothing from
    an instrument, `instrument__` from an obligation."""
    return reaching(OuterRef(f"{path}jurisdiction_id"))


def _instrument_scope(path: str, *, reach: bool = True) -> ArraySubquery:
    """The SQL half of `instrument_scopes()`, shared by both SQL twins below: the term that
    is the instrument's regime and, unless `reach` is false, the terms that mirror a
    jurisdiction its rules reach, read from the same two links, as one uuid[]."""
    wanted = Q(id=OuterRef(f"{path}regime_id"))
    return ArraySubquery(TaxonomyTerm.objects.filter(wanted | _reach(path) if reach else wanted).order_by().values("id"))


def reaching(jurisdiction: Any) -> Q:
    """The terms a record filed under `jurisdiction` derives (D-28, D-29): the term that
    mirrors it and the terms that mirror every jurisdiction whose parent it is, read from
    the mirror link and the parent link alone. `jurisdiction` is whatever names the
    jurisdiction's id in the query: an `OuterRef`, a subquery or an id. A null derives
    nothing, so a record without a jurisdiction is not restricted by it.

    The instruments' SQL half above and a change's, which comes from its authority
    (`apps/watch/reading.py`, `apps/cases/reading.py`), are built from this one condition;
    `jurisdiction_scopes()` is its Python twin."""
    return Q(jurisdiction=jurisdiction) | Q(jurisdiction__parent=jurisdiction)


def jurisdiction_scopes(jurisdiction_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, list[TaxonomyTerm]]:
    """The Python twin of `reaching()`: the terms each of these jurisdictions derives, with
    their dimension, in the terms' order. One query, none for no jurisdiction."""
    if not jurisdiction_ids:
        return {}
    terms = (
        TaxonomyTerm.objects.select_related("dimension")
        .annotate(parent_jurisdiction_id=F("jurisdiction__parent"))
        .filter(Q(jurisdiction__in=jurisdiction_ids) | Q(jurisdiction__parent__in=jurisdiction_ids))
        .order_by("sort_order", "key")
    )
    derived: dict[uuid.UUID, list[TaxonomyTerm]] = {}
    for term in terms:
        for jurisdiction_id in {term.jurisdiction_id, term.parent_jurisdiction_id} & set(jurisdiction_ids):
            derived.setdefault(jurisdiction_id, []).append(term)
    return derived


def instrument_scope_term_ids(*, reach: bool = True) -> ArraySubquery:
    """The SQL twin of `instrument_scopes()`: an instrument's own scope, as one uuid[];
    without the jurisdictions its rules reach when `reach` is false."""
    return _instrument_scope("", reach=reach)


def scope_term_ids(*, reach: bool = True) -> Func:
    """The SQL twin of `obligation_scopes()`: the obligation's own term ids plus its
    instrument's own scope, as one uuid[]; with no term that mirrors a jurisdiction when
    `reach` is false."""
    own_terms = ObligationTerm.objects.filter(obligation=OuterRef("pk"))
    if not reach:
        own_terms = own_terms.filter(term__jurisdiction__isnull=True)
    own = ArraySubquery(own_terms.order_by().values("term_id"))
    return Func(own, _instrument_scope("instrument__", reach=reach), function="array_cat", output_field=ArrayField(UUIDField()))


def _matches(tenant: Tenant, term_ids: Func | ArraySubquery) -> Func:
    """`taxonomy_in_footprint(tenant, term_ids)`, the database's rule, with the footprint read once per query."""
    return matching.in_footprint_expression(tenant.id, term_ids)


def in_view(queryset: _Listed, tenant: Tenant, footprint: FootprintFilter) -> _Listed:
    """The lists' one footprint filter (FP-03, FP-04). `in` is the working inventory and
    `all` lifts it. `watched` is only what the watched markets add: a record the footprint
    hides, that the footprint allows once the jurisdictions it reaches are set aside, and
    that reaches a market the bank watches. So a Union rule, which reaches every market the
    bank operates in, never shows there, and a Danish duty for a service the bank does not
    provide stays out. Each half asks the same database function; nothing names a market."""
    if footprint == "all":
        return queryset
    of_obligations = queryset.model is Obligation
    scope = scope_term_ids if of_obligations else instrument_scope_term_ids
    if footprint == "in":
        return queryset.filter(_matches(tenant, scope()))
    watched = WatchedMarket.objects.filter(tenant_id=tenant.id).values("jurisdiction_id")
    reaches_watched = TaxonomyTerm.objects.filter(_reach("instrument__" if of_obligations else ""), jurisdiction__in=watched)
    return queryset.exclude(_matches(tenant, scope())).filter(_matches(tenant, scope(reach=False)), Exists(reaches_watched))


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
def versions_with_confirmation() -> Prefetch[Any]:
    """An obligation's versions with the confirming agent and the proposing agent joined in
    the same query, so `confirmation_of()` never costs a query per version (playbook 10)."""
    return Prefetch(
        "versions", queryset=ObligationVersion.objects.select_related("verified_by_agent", "applied_by_proposal__proposed_by_agent")
    )


def confirmation_of(version: ObligationVersion) -> VersionConfirmation:
    """Who confirmed the approval that wrote `version`, and which agent proposed it, as
    stored (INV-05, PRO-02, D-62). The version names its confirmer; the proposer is read
    through the proposal that wrote it, and withheld when a bank made that proposal
    (PRO-03). The label is the screen's to decide: a later re-verification by a person is
    on the record, not here."""
    return VersionConfirmation(
        verified_origin=version.verified_origin,
        confirmed_by_agent=agent_ref(version.verified_by_agent),
        proposed_by_agent=proposing_agent(version.applied_by_proposal),
    )


def _version_ref(version: ObligationVersion | None) -> ObligationVersionRef | None:
    if version is None:
        return None
    confirmed = confirmation_of(version)
    return ObligationVersionRef(
        version_number=version.version_number,
        effective_from=partial_date(version.effective_from, version.effective_from_precision),
        approved_at=version.approved_at,
        verified_origin=confirmed.verified_origin,
        confirmed_by_agent=confirmed.confirmed_by_agent,
        proposed_by_agent=confirmed.proposed_by_agent,
    )


def upcoming(versions: Iterable[ObligationVersion], on: datetime.date) -> ObligationVersion | None:
    """The next version to take effect after `on`, the one `in_force()` will return next."""
    later = [v for v in versions if v.effective_from is not None and v.effective_from > on]
    return min(later, key=lambda v: (v.effective_from, v.version_number), default=None)


def obligation_page(tenant: Tenant, order: list[str], query: ObligationQuery, *, limit: int, offset: int) -> tuple[list[ObligationRow], int]:
    """The obligations the tenant sees (INV-03), filtered, as of a date (INV-04), inside
    its footprint unless `footprint` asks for everything or for what the watched markets
    add (FP-03, FP-04). The same number of queries whatever the page size (NFR-02)."""
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
    queryset = tagged(in_view(queryset, tenant, query.footprint), tenant, query)
    total = queryset.count()
    page = list(
        queryset.order_by("stable_key").select_related("instrument__level", "instrument__jurisdiction", "duty_type", "verified_by").prefetch_related("titles", versions_with_confirmation())[
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
    jurisdiction_refs = vocabulary_refs(JurisdictionLabel, (obligation.instrument.jurisdiction for obligation in page), order)
    tags_of: dict[uuid.UUID, list[LibraryRef]] = {}
    for obligation_id, tag_id in tag_pairs:
        tags_of.setdefault(obligation_id, []).append(tag_refs[tag_id])
    bank_tags = tenant_tags(tenant, ids, order)
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
                tenant_tags=bank_tags.get(obligation.id, []),
                private_to_us=obligation.owner_tenant_id == tenant.id,
                scope=carried,
                version=_version_ref(in_force(versions, as_of)),
                upcoming_version=_version_ref(upcoming(versions, as_of)),
                jurisdiction=jurisdiction_refs[instrument.jurisdiction_id],
                in_footprint=not outside,
                outside_reason=outside,
                last_verified_at=obligation.last_verified_at,
                verified_by=None if obligation.verified_by is None else PersonRef(id=obligation.verified_by.id, name=obligation.verified_by.name),
                open_change_count=0,
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
        confirmed = confirmation_of(version)
        rows[version.version_number] = ObligationVersionRow(
            version_number=version.version_number,
            effective_from=partial_date(version.effective_from, version.effective_from_precision),
            effective_to=ends,
            approved_at=version.approved_at,
            verified_origin=confirmed.verified_origin,
            confirmed_by_agent=confirmed.confirmed_by_agent,
            proposed_by_agent=confirmed.proposed_by_agent,
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
            "titles", "instrument__titles", versions_with_confirmation(), "versions__summaries", "tags", "provisions"
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
    # The provenance repeats who confirmed the version in force; the row already says it.
    in_force_row = rows[current.version_number] if current is not None else None
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
        regime=term_refs[instrument.regime_id],
        binding_level=level_refs[instrument.level_id],
        binding=instrument.binding,
        duty_type=duty_refs[obligation.duty_type_id],
        trigger_frequency=obligation.trigger_frequency,
        retention=obligation.retention,
        sanction_exposure=obligation.sanction_exposure,
        product_scope=obligation.product_scope,
        tags=[tag_refs[tag.id] for tag in tags],
        tenant_tags=tenant_tags(tenant, [obligation.id], order).get(obligation.id, []),
        private_to_us=obligation.owner_tenant_id == tenant.id,
        scope=carried,
        in_footprint=not outside,
        outside_reason=outside,
        summary=localized(summaries, order),
        translations=[text_of(summary) for summary in summaries],
        version=in_force_row,
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
            verified_origin="" if in_force_row is None else in_force_row.verified_origin,
            confirmed_by_agent=None if in_force_row is None else in_force_row.confirmed_by_agent,
            proposed_by_agent=None if in_force_row is None else in_force_row.proposed_by_agent,
        ),
    )


def _numbered(versions: list[ObligationVersion], number: int) -> ObligationVersion:
    """The version the caller named; a number this obligation has no version for is a 422."""
    found = next((version for version in versions if version.version_number == number), None)
    if found is None:
        raise ValidationError(f"This obligation has no version {number}.", code="unknown_key")
    return found


def obligation_diff(order: list[str], obligation_id: uuid.UUID, query: VersionDiffQuery) -> VersionDiff:
    """"Show what changed" between two versions of one obligation (INV-04, AC-INV1), by
    default the latest against the one before it. The comparison itself is `version_diff`,
    which is pure and writes nothing to a log: the summaries are the library's content."""
    obligation = _visible(Obligation.objects.prefetch_related(versions_with_confirmation(), "versions__summaries"), obligation_id)
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
        from_confirmation=confirmation_of(older),
        to_confirmation=confirmation_of(newer),
        language=language,
        is_machine=is_machine,
        segments=[DiffSegment(op=op, text=text) for op, text in segments],
    )


# ---------------------------------------------------------------------------------------
# GET /instruments and GET /instruments/{id} (INV-01, INV-06, FP-03)
# ---------------------------------------------------------------------------------------
def _authority_ref(authority: Authority | None) -> InstrumentAuthorityRef | None:
    if authority is None:
        return None
    return InstrumentAuthorityRef(key=authority.key, name=authority.name, short_name=authority.short_name, url=authority.url)


def instrument_page(tenant: Tenant, order: list[str], query: InstrumentQuery, *, limit: int, offset: int) -> tuple[list[InstrumentRow], int]:
    """The instruments the tenant sees (INV-01), inside its footprint unless `footprint`
    asks for everything or for what the watched markets add (FP-03, FP-04). The same number
    of queries whatever the page size (NFR-02)."""
    footprint = matching.footprint_of(tenant.id)
    restricting = matching.restricting_dimensions()
    queryset = Instrument.objects.all()
    if query.regime:
        queryset = queryset.filter(regime__key=query.regime)
    if query.q:
        titled = InstrumentTitle.objects.filter(instrument=OuterRef("pk"), text__icontains=query.q)
        queryset = queryset.filter(Q(official_ref__icontains=query.q) | Q(short_name__icontains=query.q) | Exists(titled))
    queryset = in_view(queryset, tenant, query.footprint)
    total = queryset.count()
    page = list(queryset.order_by("stable_key").select_related("level", "authority", "jurisdiction").prefetch_related("titles")[offset : offset + limit])
    ids = [instrument.id for instrument in page]
    scopes = instrument_scopes(ids)
    regime_refs = vocabulary_refs(
        TaxonomyTermLabel, (term for scope in scopes.values() for terms in scope.values() for term in terms), order, field="term"
    )
    level_refs = vocabulary_refs(InstrumentLevelLabel, (instrument.level for instrument in page), order)
    jurisdiction_refs = vocabulary_refs(JurisdictionLabel, (instrument.jurisdiction for instrument in page), order)
    dimensions = footprint_dimensions(order)
    obligation_counts = _obligation_counts(ids, tenant, query.footprint)
    rows: list[InstrumentRow] = []
    for instrument in page:
        scope = scopes.get(instrument.id, {})
        _carried, outside = scope_and_verdict(scope, dimensions, regime_refs, footprint, restricting)
        rows.append(
            InstrumentRow(
                id=instrument.id,
                stable_key=instrument.stable_key,
                short_name=instrument.short_name,
                name=localized(instrument.titles.all(), order),
                level=level_refs[instrument.level_id],
                binding=instrument.binding,
                jurisdiction=jurisdiction_refs[instrument.jurisdiction_id],
                authority=_authority_ref(instrument.authority),
                regime=regime_refs[instrument.regime_id],
                official_ref=instrument.official_ref,
                in_force_from=partial_date(instrument.in_force_from, instrument.in_force_from_precision),
                in_force_to=partial_date(instrument.in_force_to, instrument.in_force_to_precision),
                implements_note=instrument.implements_note,
                obligation_count=obligation_counts.get(instrument.id, 0),
                in_footprint=not outside,
                private_to_us=instrument.owner_tenant_id == tenant.id,
                last_verified_at=instrument.last_verified_at,
                source_url=instrument.source_url,
            )
        )
    return rows, total


def _obligation_counts(instrument_ids: Collection[uuid.UUID], tenant: Tenant, footprint: FootprintFilter) -> dict[uuid.UUID, int]:
    """How many obligations of each instrument this read would show: one query, whatever
    the page size (INV-01), under the same `footprint` value, matching what
    `GET /obligations` itself would list."""
    queryset = in_view(Obligation.objects.filter(instrument_id__in=instrument_ids), tenant, footprint)
    counted = queryset.order_by().values("instrument_id").annotate(n=Count("id"))
    return {row["instrument_id"]: row["n"] for row in counted}


def _lineage(instrument: Instrument, order: list[str]) -> list[InstrumentLineageRef]:
    """What this instrument implements or elaborates, and what implements, elaborates or
    amends it in turn (INV-01): both directions of `InstrumentRelation`, so the designed
    `GET /instruments/{instrumentId}/relations` is served here instead. Row-level security
    runs the same join either way, so a relation to an instrument the caller cannot see
    drops the row entirely rather than answering it with a null (INV-07, R3).

    `from_ref` and `to_ref` keep the relation's own meaning from either side, as the designed
    `InstrumentRelation` has them: the place in the instrument relating and the place in
    the one related to, so an incoming reference to this instrument's own text is kept."""
    outgoing = list(InstrumentRelation.objects.filter(from_instrument=instrument).select_related("to_instrument", "relation_type"))
    incoming = list(InstrumentRelation.objects.filter(to_instrument=instrument).select_related("from_instrument", "relation_type"))
    relation_refs = vocabulary_refs(RelationTypeLabel, (relation.relation_type for relation in (*outgoing, *incoming)), order)
    lineage = [
        InstrumentLineageRef(
            relation=relation_refs[relation.relation_type_id],
            direction="outgoing",
            instrument=ObligationInstrumentRef(key=relation.to_instrument.stable_key, short_name=relation.to_instrument.short_name),
            note=relation.note,
            from_ref=relation.from_ref,
            to_ref=relation.to_ref,
        )
        for relation in outgoing
    ]
    lineage.extend(
        InstrumentLineageRef(
            relation=relation_refs[relation.relation_type_id],
            direction="incoming",
            instrument=ObligationInstrumentRef(key=relation.from_instrument.stable_key, short_name=relation.from_instrument.short_name),
            note=relation.note,
            from_ref=relation.from_ref,
            to_ref=relation.to_ref,
        )
        for relation in incoming
    )
    return lineage


def instrument_detail(tenant: Tenant, order: list[str], instrument_id: uuid.UUID) -> InstrumentDetail:
    """One instrument as the card reads it (INV-01, INV-06): its identity, dates, lineage
    and re-verification stamp. The card carries no footprint verdict of its own (the
    Instruments tab and its filter read that from the row); the queries fan out, so their
    number does not grow with the lineage the record carries."""
    instrument = _visible(
        Instrument.objects.select_related("level", "authority", "jurisdiction", "regime__dimension", "verified_by").prefetch_related("titles"),
        instrument_id,
    )
    regime_refs = vocabulary_refs(TaxonomyTermLabel, [instrument.regime], order, field="term")
    level_refs = vocabulary_refs(InstrumentLevelLabel, [instrument.level], order)
    jurisdiction_refs = vocabulary_refs(JurisdictionLabel, [instrument.jurisdiction], order)
    verifier = instrument.verified_by
    return InstrumentDetail(
        id=instrument.id,
        stable_key=instrument.stable_key,
        short_name=instrument.short_name,
        name=localized(instrument.titles.all(), order),
        level=level_refs[instrument.level_id],
        binding=instrument.binding,
        jurisdiction=jurisdiction_refs[instrument.jurisdiction_id],
        authority=_authority_ref(instrument.authority),
        regime=regime_refs[instrument.regime_id],
        official_ref=instrument.official_ref,
        eli_uri=instrument.eli_uri,
        in_force_from=partial_date(instrument.in_force_from, instrument.in_force_from_precision),
        in_force_to=partial_date(instrument.in_force_to, instrument.in_force_to_precision),
        implements_note=instrument.implements_note,
        source_url=instrument.source_url,
        last_verified_at=instrument.last_verified_at,
        verified_by=None if verifier is None else PersonRef(id=verifier.id, name=verifier.name),
        private_to_us=instrument.owner_tenant_id == tenant.id,
        lineage=_lineage(instrument, order),
    )


# ---------------------------------------------------------------------------------------
# GET /instruments/{id}/provisions and GET /provisions/{id}/diff (INV-02, INV-04, INV-05)
# ---------------------------------------------------------------------------------------
def _provision_version_rows(versions: list[ProvisionVersion], texts: Mapping[uuid.UUID, list[ProvisionText]], order: list[str]) -> list[ProvisionVersionRow]:
    """A provision's own version list (INV-02, INV-04): the same `effectiveTo` derivation
    as `version_rows()`, plus each version's transitional note and text. Kept apart from
    `version_rows()` because an obligation's version carries neither."""
    rows: list[ProvisionVersionRow] = []
    for index, version in enumerate(versions):
        following = versions[index + 1] if index + 1 < len(versions) else None
        ends = None
        if (
            following is not None
            and following.effective_from is not None
            and (version.effective_from is None or following.effective_from > version.effective_from)
        ):
            ends = partial_date(following.effective_from - datetime.timedelta(days=1), following.effective_from_precision)
        rows.append(
            ProvisionVersionRow(
                version_number=version.version_number,
                effective_from=partial_date(version.effective_from, version.effective_from_precision),
                effective_to=ends,
                transitional_note=version.transitional_note,
                text=localized(texts.get(version.id, []), order),
            )
        )
    return rows


def provision_tree(tenant: Tenant, instrument_id: uuid.UUID, order: list[str], query: InstrumentProvisionsQuery) -> list[ProvisionNode]:
    """The provision tree of one instrument (INV-02), as of a date (AC-INV1): a bounded
    number of queries however many provisions, versions or citing obligations the
    instrument carries, because every table is read once for the whole tree rather than
    once per node. An instrument the caller cannot see answers 404 (INV-07)."""
    instrument = _visible(Instrument.objects.all(), instrument_id)
    as_of = query.as_of or today_for(tenant)
    provisions = list(Provision.objects.filter(instrument=instrument).select_related("kind").order_by("sort_order", "stable_key"))
    kind_refs = vocabulary_refs(ProvisionKindLabel, (provision.kind for provision in provisions), order)
    provision_ids = [provision.id for provision in provisions]
    versions_by_provision: dict[uuid.UUID, list[ProvisionVersion]] = {provision_id: [] for provision_id in provision_ids}
    for version in ProvisionVersion.objects.filter(provision_id__in=provision_ids).order_by("version_number"):
        versions_by_provision[version.provision_id].append(version)
    all_versions = [version for versions in versions_by_provision.values() for version in versions]
    texts_by_version: dict[uuid.UUID, list[ProvisionText]] = {version.id: [] for version in all_versions}
    for text in ProvisionText.objects.filter(version_id__in=texts_by_version):
        texts_by_version[text.version_id].append(text)
    links = list(ObligationProvision.objects.filter(provision_id__in=provision_ids).select_related("obligation"))
    obligation_ids = {link.obligation_id for link in links}
    titles_by_obligation: dict[uuid.UUID, list[ObligationTitle]] = {obligation_id: [] for obligation_id in obligation_ids}
    for title in ObligationTitle.objects.filter(obligation_id__in=obligation_ids):
        titles_by_obligation[title.obligation_id].append(title)
    cites_by_provision: dict[uuid.UUID, list[ObligationProvision]] = {}
    for link in links:
        cites_by_provision.setdefault(link.provision_id, []).append(link)
    children_of: dict[uuid.UUID | None, list[Provision]] = {}
    for provision in provisions:
        children_of.setdefault(provision.parent_id, []).append(provision)

    def node(provision: Provision) -> ProvisionNode:
        versions = versions_by_provision[provision.id]
        current = in_force(versions, as_of)
        return ProvisionNode(
            id=provision.id,
            stable_key=provision.stable_key,
            kind=kind_refs[provision.kind_id],
            ref_label=provision.ref_label,
            heading=provision.heading,
            path=provision.path,
            children=[node(child) for child in children_of.get(provision.id, [])],
            versions=_provision_version_rows(versions, texts_by_version, order),
            in_force_version=current.version_number if current else None,
            obligations=[
                ProvisionCitedObligation(
                    id=link.obligation_id,
                    title=localized(titles_by_obligation[link.obligation_id], order),
                    ref_label=link.obligation.ref_label,
                )
                for link in cites_by_provision.get(provision.id, [])
            ],
        )

    return [node(root) for root in children_of.get(None, [])]


def provision_diff(order: list[str], provision_id: uuid.UUID, query: VersionDiffQuery) -> VersionDiff:
    """"Show what changed" between two versions of one provision (INV-02, INV-04,
    AC-INV1), by default the latest against the one before it. Serialises `logic.
    version_diff` exactly as `obligation_diff()` does, because a provision's text and an
    obligation's summary are compared the same way."""
    provision = _visible(Provision.objects.prefetch_related("versions__texts"), provision_id)
    versions = list(provision.versions.all())
    if len(versions) < 2 and (query.from_version is None or query.to_version is None):
        raise ValidationError("There are not two versions of this provision to compare.")
    older = _numbered_provision(versions, query.from_version) if query.from_version is not None else versions[-2]
    newer = _numbered_provision(versions, query.to_version) if query.to_version is not None else versions[-1]
    compared = version_diff(older.texts.all(), newer.texts.all(), order, query.lang)
    if compared is None:
        raise ValidationError("These two versions have no language in common, so there is nothing to compare.")
    language, is_machine, segments = compared
    return VersionDiff(
        from_version=older.version_number,
        to_version=newer.version_number,
        from_effective=partial_date(older.effective_from, older.effective_from_precision),
        to_effective=partial_date(newer.effective_from, newer.effective_from_precision),
        # No proposal kind writes a provision's text, so its versions record no approval.
        from_confirmation=None,
        to_confirmation=None,
        language=language,
        is_machine=is_machine,
        segments=[DiffSegment(op=op, text=text) for op, text in segments],
    )


def _numbered_provision(versions: list[ProvisionVersion], number: int) -> ProvisionVersion:
    """The version the caller named; a number this provision has no version for is a 422."""
    found = next((version for version in versions if version.version_number == number), None)
    if found is None:
        raise ValidationError(f"This provision has no version {number}.", code="unknown_key")
    return found


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
# GET /obligations/{id}/sources
# ---------------------------------------------------------------------------------------
def today_of(tenant_id: uuid.UUID | None) -> datetime.date:
    """Today for the caller: where its tenant is, or the platform's day for a platform key,
    which belongs to no tenant."""
    tenant = None if tenant_id is None else Tenant.objects.filter(pk=tenant_id).first()  # ordering: pk lookup, at most one row
    return timezone.localdate() if tenant is None else today_for(tenant)


def get_record_sources(obligation_id: uuid.UUID, on: datetime.date) -> LibraryRecordSources:
    """`GET /obligations/{obligationId}/sources`, the citations a re-check compares against
    (INV-06, AGT-01 item 3): one per field the approved proposal behind the version in force
    on `on` sourced, or the record's own source as one `summary` citation for a version no
    proposal wrote (a seeded one). A record whose versions all lie ahead is read by its
    first.

    It resolves the obligation through `_visible()` above, as every other addressed read in
    this module does, and never through a lookup of its own: that one function is what makes
    a record the caller cannot see answer the same 404 as an id that never existed, so a
    second lookup would be a second chance to leak which of the two it was (INV-07).
    """
    obligation = _visible(
        Obligation.objects.prefetch_related(Prefetch("versions", queryset=ObligationVersion.objects.select_related("applied_by_proposal"))),
        obligation_id,
    )
    versions = list(obligation.versions.all())
    # Every obligation is created with its first version, so there is always one to read.
    version = in_force(versions, on) or min(versions, key=lambda v: v.version_number)
    proposal = version.applied_by_proposal
    if proposal is None:
        cited = [("summary", obligation.source_url, obligation.source_label)]
    else:
        cited = [(field, source, proposal.source_label or source) for field, source in proposal.field_sources.items()]
    return LibraryRecordSources(
        obligation_id=obligation.id,
        version_number=version.version_number,
        items=[
            LibraryRecordSource(field=field, url=url, label=label, content_hash=None, fetched_at=None, document_id=None)
            for field, url, label in cited
        ],
    )


# ---------------------------------------------------------------------------------------
# What a batch proposal re-tags (PRO-04; c11-proposal-batches-create): many obligations
# read at once, so a batch's preview costs the same few queries however many rows it has.
# ---------------------------------------------------------------------------------------
def active_shared_obligations(obligation_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, Obligation]:
    """Those of `obligation_ids` that are the library's own (never a bank's private record,
    INV-07) and in force, with their instrument and its level, in one query. An id that is
    missing, private or retired is simply absent, for the caller to refuse by name."""
    rows = Obligation.objects.filter(
        pk__in=obligation_ids, owner_tenant__isnull=True, status=RecordStatus.ACTIVE.value
    ).select_related("instrument__level")
    return {row.id: row for row in rows}


def obligation_scope_terms(obligation_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, dict[str, uuid.UUID]]:
    """Each obligation's own scope as the live `obligation_term` rows hold it, as
    `dimension:key` to the term's id, in one query. An obligation with no terms is absent."""
    scopes: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
    links = ObligationTerm.objects.filter(obligation_id__in=obligation_ids).select_related("term__dimension").order_by()
    for link in links:
        scopes.setdefault(link.obligation_id, {})[f"{link.term.dimension.key}:{link.term.key}"] = link.term_id
    return scopes
