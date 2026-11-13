"""What applies, company by company (REG-01, FP-05, D-75, REG-S18, REG-S19): the reads behind
the "What applies" page and the regulation page's roll-up. Nothing here writes, and nothing
suggests an answer: whether an obligation applies stays a person's decision (D-28, D-89).

Three definitions, each the obligation page's own, so what a list says here is what the page
says there:

- OFFERED. An obligation is offered for an active legal entity when it is in the bank's
  working inventory (`library.reading.in_view`, the rows `GET /obligations` lists) and spans
  the entity: `applicability._spans`, here as SQL (`spans_expression()`).
- TARGET. What an answer must name: the entity where the obligation spans two or more of the
  bank's legal entities, the obligation as a whole where it spans fewer, which is how the
  obligation page asks and `applicability._store` stores.
- ANSWER. The applicability of the row the target names, not assessed when there is none.

The regulation's roll-up counts the bank-level answer instead (`overlay._entries()`), so each
count equals the total of `GET /obligations` under the same filter.

The target needs every company's span, so `_offers()` reads obligations with all of them in
one query and the answers are folded in Python: a fixed number of queries whatever the page,
the library and the organisation hold. The companies and the regulations lists read the
whole working inventory once per request; the rows and the roll-up read one regulation.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable
from typing import Any, NamedTuple

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Func, OuterRef, QuerySet, Subquery, UUIDField, Value
from django.db.models.functions import Coalesce

from apps.library import reading
from apps.library.models import Instrument, JurisdictionLabel, Obligation, ObligationTerm
from apps.register import overlay
from apps.register.applicability import KIND_OF, WORD_OF
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.register.schemas import (
    RegisterApplicabilityAnswer,
    RegisterApplicabilityAnswerPage,
    RegisterApplicabilityAnswerQuery,
    RegisterApplicabilityCompany,
    RegisterApplicabilityInstrument,
    RegisterApplicabilityRegulation,
    RegisterApplicabilityRegulationPage,
    RegisterApplicabilityRegulationQuery,
    RegisterApplicabilityStatusCount,
    RegisterApplicabilityThrough,
    RegisterInstrumentApplicability,
    RegisterPersonRef,
)
from apps.shared.models import Tenant
from apps.shared.people import person_ref
from apps.taxonomy import terms_logic
from apps.taxonomy.models import ComplianceStatus, ComplianceStatusLabel, EntityScopeExclusion, TaxonomyTerm
from apps.taxonomy.schemas import FootprintTermRef
from apps.tenants import registers_logic
from apps.tenants.models import OrgUnit, OrgUnitKind, RegisterEntry
from apps.tenants.schemas import RegisterFacts

NOT_ASSESSED = Applicability.NOT_ASSESSED.value
_UUIDS = ArrayField(UUIDField())
# One boolean per entity over a row's scope terms. The terms sit behind OFFSET 0, which
# keeps the planner from copying their two sub-selects into every check: they are read once
# per row however many entities and dimensions there are.
_SPANS = "(SELECT ARRAY[%(checks)s] FROM (SELECT %(expressions)s OFFSET 0) AS scope (%(columns)s))"
# One check of `_spans`: the row carries no term of the dimension, or one that is allowed.
_PASSES = "(NOT scope.terms && scope.a{dimension} OR scope.terms && scope.a{allowed})"


# --- The span as SQL ---
def spans_expression(entities: list[OrgUnit]) -> Func:
    """`applicability._spans` as SQL (apps/register/tests_company_view.py pins the two against
    each other): over an obligation row, a `boolean[]` saying for each of `entities`, in
    order, whether the obligation spans it. The entities carry their `entity_term`, and
    there is at least one. Two queries however many entities.

    `_spans` makes one check per dimension: the entity's own type among the types the
    obligation carries, and, for each dimension the entity has exclusions in, a carried term
    its exclusions leave. Each is what `taxonomy_scope_admits` answers over a guard of that
    one dimension. It is written here as two array overlaps on terms read once, because a
    pass over the working inventory asks it for every row and entity: on the library
    baseline's 1,894 obligations with six entities the function took 11 to 19 microseconds a
    call, 170 ms a pass, and the overlaps 2 microseconds."""
    outside: dict[uuid.UUID, dict[uuid.UUID, set[uuid.UUID]]] = defaultdict(lambda: defaultdict(set))
    excluded = EntityScopeExclusion.objects.filter(org_unit__in=entities).order_by().values_list("org_unit_id", "term__dimension_id", "term_id")
    for org_unit_id, dimension_id, term_id in excluded:
        outside[org_unit_id][dimension_id].add(term_id)
    guarded = {entity.entity_term.dimension_id for entity in entities if entity.entity_term is not None}
    guarded |= {dimension_id for dimensions in outside.values() for dimension_id in dimensions}
    terms_of: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    mirrors = False  # whether a guarded dimension holds a term that mirrors a jurisdiction
    for term_id, dimension_id, jurisdiction_id in TaxonomyTerm.objects.filter(dimension_id__in=guarded).order_by().values_list("id", "dimension_id", "jurisdiction_id"):
        terms_of[dimension_id].add(term_id)
        mirrors = mirrors or jurisdiction_id is not None
    arrays: list[Value] = []
    checks: list[str] = []
    for entity in entities:
        guard = [(terms_of[dimension_id], terms_of[dimension_id] - gone) for dimension_id, gone in outside.get(entity.id, {}).items()]
        if entity.entity_term is not None:
            guard.append((terms_of[entity.entity_term.dimension_id], {entity.entity_term.id}))
        passes = []
        for dimension_terms, allowed in guard:
            arrays += [Value(sorted(dimension_terms), output_field=_UUIDS), Value(sorted(allowed), output_field=_UUIDS)]
            passes.append(_PASSES.format(dimension=len(arrays) - 1, allowed=len(arrays)))
        checks.append(" AND ".join(passes) or "TRUE")
    return Func(
        # The jurisdictions a rule reaches are the costly half of its scope, and no check
        # reads them unless a guarded dimension holds one.
        reading.scope_term_ids(reach=mirrors),
        *arrays,
        template=_SPANS,
        checks=", ".join(checks),
        columns=", ".join(["terms", *(f"a{number}" for number in range(1, len(arrays) + 1))]),
        output_field=ArrayField(BooleanField()),
    )


# --- What is offered, and the answer so far ---
class _Offer(NamedTuple):
    """One obligation of the working inventory and the legal entities it spans, in the
    organisation's order."""

    obligation_id: uuid.UUID
    instrument_id: uuid.UUID
    spanned: tuple[uuid.UUID, ...]

    def target(self, entity_id: uuid.UUID) -> uuid.UUID | None:
        """What an answer for `entity_id` names: the entity, or the obligation as a whole."""
        return entity_id if len(self.spanned) >= 2 else None


# The bank's answers as stored kinds: obligation, then target (a legal entity, or None for
# the obligation as a whole). What is missing is not assessed.
_Answers = dict[uuid.UUID, dict[uuid.UUID | None, str]]
_NO_ANSWER: dict[uuid.UUID | None, str] = {}


def _entities() -> list[OrgUnit]:
    """The bank's active legal entities in the organisation's order, as
    `applicability.entities_spanned()` reads them."""
    return list(
        OrgUnit.objects.filter(kind=OrgUnitKind.LEGAL_ENTITY.value, active=True).select_related("entity_term__dimension").order_by("name", "id")
    )


def _company(entities: list[OrgUnit], org_unit_id: uuid.UUID) -> OrgUnit:
    """The legal entity asked for. Another bank's, a department and a deactivated entity are
    all the same `not_found`."""
    company = next((entity for entity in entities if entity.id == org_unit_id), None)
    if company is None:
        raise ValidationError("That legal entity is not here.", code="not_found")
    return company


def _offers(tenant: Tenant, entities: list[OrgUnit], obligations: QuerySet[Obligation]) -> list[_Offer]:
    """Those of `obligations` in the bank's working inventory, in the inventory's order, each
    with the entities it spans: one query, after `spans_expression()`'s two."""
    rows = (
        reading.in_view(obligations, tenant, "in")
        .annotate(spans=spans_expression(entities))
        .order_by("stable_key")
        .values_list("id", "instrument_id", "spans")
    )
    return [
        _Offer(obligation_id, instrument_id, tuple(entity.id for entity, spanned in zip(entities, spans, strict=True) if spanned))
        for obligation_id, instrument_id, spans in rows
    ]


def _stored(tenant: Tenant, *, obligation_ids: Collection[uuid.UUID] | None = None, company: OrgUnit | None = None) -> _Answers:
    """The answers the bank has given: on these obligations or on all of them, for every legal
    entity or for one. Two queries; a row still not assessed reads as no row."""
    entries = TenantObligation.objects.filter(tenant_id=tenant.id).exclude(applicability=NOT_ASSESSED)
    rows = TenantObligationScope.objects.filter(tenant_id=tenant.id, product__isnull=True).exclude(applicability=NOT_ASSESSED)
    if obligation_ids is not None:
        entries = entries.filter(obligation_id__in=obligation_ids)
        rows = rows.filter(tenant_obligation__obligation_id__in=obligation_ids)
    if company is not None:
        rows = rows.filter(org_unit=company)
    answers: _Answers = defaultdict(dict)
    for obligation_id, kind in entries.order_by().values_list("obligation_id", "applicability"):
        answers[obligation_id][None] = kind
    for obligation_id, org_unit_id, kind in rows.order_by().values_list("tenant_obligation__obligation_id", "org_unit_id", "applicability"):
        answers[obligation_id][org_unit_id] = kind
    return answers


def _counts(counted: Counter[str]) -> dict[str, int]:
    """Answers counted by stored kind, as the four counts a company or a regulation carries."""
    return {
        "offered": counted.total(),
        "applies": counted[Applicability.APPLIES.value],
        "not_applicable": counted[Applicability.DOES_NOT_APPLY.value],
        "under_assessment": counted[NOT_ASSESSED],
    }


def _companies(entities: list[OrgUnit], offers: Iterable[_Offer], answers: _Answers) -> list[RegisterApplicabilityCompany]:
    counted: dict[uuid.UUID, Counter[str]] = {entity.id: Counter() for entity in entities}
    for offer in offers:
        given = answers.get(offer.obligation_id, _NO_ANSWER)
        for entity_id in offer.spanned:
            counted[entity_id][given.get(offer.target(entity_id), NOT_ASSESSED)] += 1
    return [
        RegisterApplicabilityCompany(org_unit=RegisterPersonRef(id=entity.id, name=entity.name), **_counts(counted[entity.id]))
        for entity in entities
    ]


def _facts(company: OrgUnit) -> list[tuple[str, RegisterFacts]]:
    """What each authority's register says about the company, by authority: one query."""
    rows = RegisterEntry.objects.filter(org_unit=company).select_related("authority").order_by("authority__key", "id")
    return [(row.authority.key, RegisterFacts.model_validate(row.facts)) for row in rows]


def _term_refs(terms: Iterable[TaxonomyTerm], order: list[str]) -> dict[uuid.UUID, FootprintTermRef]:
    """Each term as a reference with its dimension, in the scope page's order, labelled in
    one query. The terms carry their dimension."""
    listed = sorted(terms, key=lambda term: (term.dimension.sort_order, term.sort_order, term.key))
    return dict(zip((term.id for term in listed), terms_logic.labelled_term_refs(listed, order), strict=True))


# --- GET /applicability/companies ---
def list_companies(*, tenant: Tenant) -> list[RegisterApplicabilityCompany]:
    """Every active legal entity with how its answers stand over the whole working
    inventory: one pass over it, whatever the number of entities."""
    entities = _entities()
    if not entities:
        return []
    return _companies(entities, _offers(tenant, entities, Obligation.objects.all()), _stored(tenant))


# --- GET /applicability/regulations ---
def list_regulations(
    *, tenant: Tenant, order: list[str], query: RegisterApplicabilityRegulationQuery, limit: int, offset: int
) -> RegisterApplicabilityRegulationPage:
    """The regulations with an obligation offered for one company, by stable key.

    The working inventory is read once, as `list_companies()` reads it, and the regulations
    are paged after. Paging them first saves nothing: to count the regulations PostgreSQL
    plans the per-regulation EXISTS as a hash semi join and runs both rules on every
    obligation anyway (measured), and `answer` needs every company's span on each."""
    entities = _entities()
    company = _company(entities, query.org_unit_id)
    answers = _stored(tenant, company=company)
    counted: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    for offer in _offers(tenant, entities, Obligation.objects.all()):
        if company.id in offer.spanned:
            given = answers.get(offer.obligation_id, _NO_ANSWER)
            counted[offer.instrument_id][given.get(offer.target(company.id), NOT_ASSESSED)] += 1
    kept = {instrument_id for instrument_id, answered in counted.items() if query.answer is None or answered[KIND_OF[query.answer]]}
    # The regulations in key order, then the page's rows by id: a list of several hundred ids
    # costs more to send than both of these queries.
    in_order = Instrument.objects.order_by("stable_key")
    if query.q:
        in_order = reading.instruments_matching(in_order, query.q)
    listed = [instrument_id for instrument_id in in_order.values_list("pk", flat=True) if instrument_id in kept]
    page = list(
        Instrument.objects.filter(pk__in=listed[offset : offset + limit]).order_by("stable_key").select_related("jurisdiction", "regime__dimension")
    )
    jurisdictions = reading.vocabulary_refs(JurisdictionLabel, (instrument.jurisdiction for instrument in page), order)
    regimes = _term_refs({instrument.regime for instrument in page}, order)
    lines: dict[tuple[str, str], list[str]] = defaultdict(list)
    for authority, facts in _facts(company):
        for term, sources in registers_logic.term_sources(authority, facts).items():
            lines[term].extend(sources)
    return RegisterApplicabilityRegulationPage(
        items=[
            RegisterApplicabilityRegulation(
                instrument=RegisterApplicabilityInstrument(
                    id=instrument.id,
                    key=instrument.stable_key,
                    short_name=instrument.shown_short_name,
                    jurisdiction=jurisdictions[instrument.jurisdiction_id],
                ),
                through=RegisterApplicabilityThrough(
                    term=regimes[instrument.regime_id],
                    lines=lines.get((instrument.regime.dimension.key, instrument.regime.key), []),
                ),
                **_counts(counted[instrument.id]),
            )
            for instrument in page
        ],
        total=len(listed),
    )


# --- GET /applicability/rows ---
def list_rows(*, tenant: Tenant, order: list[str], query: RegisterApplicabilityAnswerQuery, limit: int, offset: int) -> RegisterApplicabilityAnswerPage:
    """One regulation's obligations offered for one company, in the inventory's order, each
    with the answer so far and the target an answer must name."""
    entities = _entities()
    company = _company(entities, query.org_unit_id)
    offers = [
        offer
        for offer in _offers(tenant, entities, Obligation.objects.filter(instrument__stable_key=query.instrument))
        if company.id in offer.spanned
    ]
    ids = [offer.obligation_id for offer in offers]
    entries = {
        row.obligation_id: row
        for row in TenantObligation.objects.filter(tenant_id=tenant.id, obligation_id__in=ids).select_related("applicability_decided_by")
    }
    own_rows = {
        row.tenant_obligation.obligation_id: row
        for row in TenantObligationScope.objects.filter(
            tenant_id=tenant.id, tenant_obligation__obligation_id__in=ids, org_unit=company, product__isnull=True
        ).select_related("tenant_obligation", "applicability_decided_by")
    }
    answered: list[tuple[_Offer, Any]] = []
    for offer in offers:
        row = own_rows.get(offer.obligation_id) if offer.target(company.id) else entries.get(offer.obligation_id)
        if query.answer is None or query.answer == WORD_OF[row.applicability if row is not None else NOT_ASSESSED]:
            answered.append((offer, row))
    page = answered[offset : offset + limit]
    page_ids = [offer.obligation_id for offer, _ in page]
    headings = reading.obligation_headings(page_ids, order)
    # The obligations' own terms the company carries: its type, or what its register facts derive.
    derived = {(dimension, key) for authority, facts in _facts(company) for dimension, keys in registers_logic.derived_terms(authority, facts).items() for key in keys}
    matched: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    terms: dict[uuid.UUID, TaxonomyTerm] = {}
    for link in ObligationTerm.objects.filter(obligation_id__in=page_ids).select_related("term__dimension"):
        if link.term_id == company.entity_term_id or (link.term.dimension.key, link.term.key) in derived:
            matched[link.obligation_id].add(link.term_id)
            terms[link.term_id] = link.term
    refs = _term_refs(terms.values(), order)
    return RegisterApplicabilityAnswerPage(
        items=[
            RegisterApplicabilityAnswer(
                obligation_id=offer.obligation_id,
                ref_label=headings[offer.obligation_id].reference_label,
                title=headings[offer.obligation_id].title,
                org_unit_id=offer.target(company.id),
                applicability=WORD_OF[row.applicability if row is not None else NOT_ASSESSED],  # type: ignore[arg-type]
                reason=(row.applicability_reason or None) if row is not None else None,
                decided_at=row.applicability_decided_at if row is not None else None,
                decided_by=person_ref(row.applicability_decided_by, RegisterPersonRef) if row is not None else None,
                version=row.version if row is not None else 0,
                matched_terms=[ref for term_id, ref in refs.items() if term_id in matched[offer.obligation_id]],
            )
            for offer, row in page
        ],
        total=len(answered),
    )


# --- GET /instruments/{instrumentId}/applicability ---
def instrument_applicability(*, tenant: Tenant, order: list[str], instrument_id: uuid.UUID) -> RegisterInstrumentApplicability:
    """One regulation rolled up for the bank: the bank-level answers and shown statuses of its
    obligations in the working inventory, as the inventory's own overlay reads them, and the
    companies' rows narrowed to it."""
    instrument = reading.instrument_subject(instrument_id)
    obligations = Obligation.objects.filter(instrument=instrument)
    mine = overlay._entries(tenant).filter(obligation_id=OuterRef("pk"))
    judged = list(
        reading.in_view(obligations, tenant, "in")
        .annotate(
            answer=Coalesce(Subquery(mine.values("answer")[:1]), Value(overlay.NOT_ASSESSED)),
            shown_status_id=Subquery(mine.values("shown_status_id")[:1]),
        )
        .values_list("answer", "shown_status_id")
    )
    answered = Counter(answer for answer, _ in judged)
    shown = Counter(status_id for answer, status_id in judged if answer == "applies")
    statuses = list(ComplianceStatus.objects.filter(pk__in=shown))
    refs = reading.vocabulary_refs(ComplianceStatusLabel, statuses, order)
    companies: list[RegisterApplicabilityCompany] = []
    if entities := _entities():
        offers = _offers(tenant, entities, obligations)
        companies = _companies(entities, offers, _stored(tenant, obligation_ids=[offer.obligation_id for offer in offers]))
    return RegisterInstrumentApplicability(
        in_scope=len(judged),
        applies=answered["applies"],
        not_applicable=answered["not_applicable"],
        under_assessment=answered["under_assessment"],
        statuses=[RegisterApplicabilityStatusCount(status=refs[status.id], count=shown[status.id]) for status in statuses],
        companies=[company for company in companies if company.offered],
    )
