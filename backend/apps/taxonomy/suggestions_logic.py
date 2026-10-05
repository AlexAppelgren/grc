"""The regulatory scope suggested from the public registers (FP-05, PUBLIC_REGISTERS.md 4.2
and 4.3, D-121, ADR 0066).

A read. It compares the register facts of the bank's legal entities (`RegisterEntry`, read
from Finansinspektionen's register on onboarding and every night after) with the bank's
regulatory scope and its companies' exclusions, and lists what a person may file as one
ordinary request: terms for the bank's scope, markets, and each company's licence-bound
exclusions. Nothing here writes, and nothing a register says reaches the scope until a second
person approves the request with a passkey (FP-02, D-89).

The rules, in short (the brief has the reasons):
- A dimension the scope leaves open is closed only when the companies hold part of its
  licence-bound terms, and then with every term no licence answers (AML, tax, execution-only),
  so the change hides only licence-bound rules no company is licensed for.
- A dimension the scope restricts gains the held terms it lacks, and loses the licence-bound
  terms no company holds unless that would empty it, which would widen it instead.
- Markets: each company's country and each branch's country the library covers; never a
  removal, since a bank may serve a country without a branch.
- A company whose main business the mapping knows is suggested out of the licence-bound terms
  its facts do not give it; a company without facts, or whose business is unknown, never is.
"""

from __future__ import annotations

import datetime
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from apps.taxonomy import matching, terms_logic
from apps.taxonomy.footprint_logic import ENTITY_SCOPE_DIMENSIONS
from apps.taxonomy.models import EntityScopeExclusion, TaxonomyTerm
from apps.taxonomy.schemas import (
    FootprintEntitySuggestion,
    FootprintOrgUnitRef,
    FootprintSuggestionLine,
    FootprintSuggestionReason,
    FootprintSuggestions,
)
from apps.tenants import registers_logic
from apps.tenants.models import OrgUnit, OrgUnitKind, RegisterEntry
from apps.tenants.schemas import RegisterFacts

MARKET_DIMENSION = "jurisdiction"
# One term of the scope, as (dimension key, term key).
Key = tuple[str, str]


@dataclass
class _Company:
    """One legal entity with register facts, and what its facts give it."""

    unit: OrgUnit
    derived: dict[str, set[str]] = field(default_factory=dict)
    sources: dict[Key, list[str]] = field(default_factory=dict)
    known_business: bool = False
    main_business: str = ""
    markets: dict[str, list[str | None]] = field(default_factory=dict)


def _companies(tenant_id: uuid.UUID) -> tuple[list[_Company], dict[str, set[str]], datetime.datetime | None]:
    """The bank's active legal entities that a register lists, what each derives, the terms
    every register they come from can derive, and when the facts were last read."""
    entries = list(
        RegisterEntry.objects.filter(
            tenant_id=tenant_id, org_unit__active=True, org_unit__kind=OrgUnitKind.LEGAL_ENTITY.value
        ).select_related("org_unit", "authority").order_by("org_unit__name", "org_unit_id", "authority__key")
    )
    companies: dict[uuid.UUID, _Company] = {}
    derivable: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        facts = RegisterFacts.model_validate(entry.facts)
        authority = entry.authority.key
        for dimension, keys in registers_logic.derivable_terms(authority).items():
            derivable[dimension] |= keys
        if not facts.listed:
            continue
        company = companies.setdefault(entry.org_unit_id, _Company(unit=entry.org_unit))
        for dimension, keys in registers_logic.derived_terms(authority, facts).items():
            company.derived.setdefault(dimension, set()).update(keys)
        for key, lines in registers_logic.term_sources(authority, facts).items():
            company.sources.setdefault(key, []).extend(lines)
        if registers_logic.knows_main_business(authority, facts):
            company.known_business = True
            company.main_business = facts.main_business
        if entry.org_unit.country_code:
            company.markets.setdefault(entry.org_unit.country_code.lower(), []).append(None)
        for branch in facts.branches:
            if branch.jurisdiction:
                company.markets.setdefault(branch.jurisdiction, []).append(branch.name)
    read_at = max((entry.read_at for entry in entries), default=None)
    return list(companies.values()), derivable, read_at


def suggestions_of(tenant_id: uuid.UUID, order: list[str]) -> FootprintSuggestions:
    """What the register facts suggest for the bank's regulatory scope and its companies'
    own scope, each line with the companies and register lines behind it. Empty when no
    legal entity has register facts or nothing differs."""
    companies, derivable, read_at = _companies(tenant_id)
    if not companies:
        return FootprintSuggestions(read_at=read_at)
    restricting = matching.restricting_dimensions()
    dimensions = [dimension for dimension in derivable if dimension in restricting]
    terms: dict[Key, TaxonomyTerm] = {
        (term.dimension.key, term.key): term
        for term in TaxonomyTerm.objects.filter(
            active=True, dimension__active=True, dimension__key__in=[*dimensions, MARKET_DIMENSION]
        ).select_related("dimension")
        if term.dimension.key != MARKET_DIMENSION or term.jurisdiction_id is not None
    }
    live: dict[str, set[str]] = defaultdict(set)
    for dimension, key in terms:
        live[dimension].add(key)
    scope = matching.footprint_of(tenant_id)

    adds: dict[Key, list[tuple[OrgUnit, str | None]]] = {}
    removes: dict[Key, list[tuple[OrgUnit, str | None]]] = {}

    def reasons(dimension: str, key: str) -> list[tuple[OrgUnit, str | None]]:
        return [
            (company.unit, line)
            for company in companies
            if key in company.derived.get(dimension, ())
            for line in company.sources.get((dimension, key), [None])
        ]

    for dimension in dimensions:
        bound = derivable[dimension] & live[dimension]
        held = {key for company in companies for key in company.derived.get(dimension, ()) if key in live[dimension]}
        current = scope.get(dimension, set())
        if not current:
            if held and bound - held:
                for key in held | (live[dimension] - bound):
                    adds[(dimension, key)] = reasons(dimension, key)
            continue
        for key in held - current:
            adds[(dimension, key)] = reasons(dimension, key)
        gone = (current & bound) - held
        if gone and current - gone:
            for key in gone:
                removes[(dimension, key)] = []
    current_markets = scope.get(MARKET_DIMENSION, set())
    for company in companies:
        for market, lines in company.markets.items():
            if market in live[MARKET_DIMENSION] and market not in current_markets:
                adds.setdefault((MARKET_DIMENSION, market), []).extend((company.unit, line) for line in lines)

    outside: dict[uuid.UUID, set[Key]] = defaultdict(set)
    for org_unit_id, dimension, key in EntityScopeExclusion.objects.filter(
        tenant_id=tenant_id, org_unit__in=[company.unit for company in companies]
    ).values_list("org_unit_id", "term__dimension__key", "term__key"):
        outside[org_unit_id].add((dimension, key))
    excludes: list[tuple[_Company, list[Key]]] = []
    includes: list[tuple[_Company, list[Key]]] = []
    for company in companies:
        if not company.known_business:
            continue
        should = {
            (dimension, key)
            for dimension in ENTITY_SCOPE_DIMENSIONS
            for key in (derivable.get(dimension, set()) & live.get(dimension, set())) - company.derived.get(dimension, set())
        }
        if more := sorted(should - outside[company.unit.id], key=lambda pair: _order(terms[pair])):
            excludes.append((company, more))
        # An exclusion of a term retired since is left alone: it narrows nothing any more.
        if back := sorted((pair for pair in outside[company.unit.id] - should if pair in terms), key=lambda pair: _order(terms[pair])):
            includes.append((company, back))

    used = sorted({*adds, *removes, *(pair for _, pairs in (*excludes, *includes) for pair in pairs)}, key=lambda pair: _order(terms[pair]))
    labelled = dict(zip(used, terms_logic.labelled_term_refs([terms[pair] for pair in used], order), strict=True))

    def line(pair: Key, behind: list[tuple[OrgUnit, str | None]]) -> FootprintSuggestionLine:
        return FootprintSuggestionLine(
            term=labelled[pair],
            reasons=[
                FootprintSuggestionReason(org_unit=FootprintOrgUnitRef(id=unit.id, name=unit.name), register_line=text)
                for unit, text in behind
            ],
        )

    def company_line(company: _Company, pairs: list[Key]) -> FootprintEntitySuggestion:
        return FootprintEntitySuggestion(
            org_unit=FootprintOrgUnitRef(id=company.unit.id, name=company.unit.name),
            main_business=company.main_business,
            terms=[labelled[pair] for pair in pairs],
        )

    return FootprintSuggestions(
        adds=[line(pair, adds[pair]) for pair in used if pair in adds],
        removes=[line(pair, removes[pair]) for pair in used if pair in removes],
        entity_exclusions=[company_line(company, pairs) for company, pairs in excludes],
        entity_inclusions=[company_line(company, pairs) for company, pairs in includes],
        read_at=read_at,
    )


def _order(term: TaxonomyTerm) -> tuple[int, int, str]:
    """The order the scope page draws terms in: dimension, then term."""
    return (term.dimension.sort_order, term.sort_order, term.key)
