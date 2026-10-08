"""The regulatory scope that follows the organisation (FP-04, FP-05, D-122, ADR 0067; the rules
are PUBLIC_REGISTERS.md 4.2 and 4.3, D-121, ADR 0066).

What a bank's organisation and the public registers say about it reaches its scope by itself:
nobody picks it and nobody approves it, because nobody chooses it (Alex, 2026-10-08, D-122).
`follow()` reads the bank's active legal entities and their register facts, works out where
the scope differs, and writes the difference with the same writes an approved request makes,
one history row and one audit event per term, under the system actor and with no request and
no step-up. It runs when a legal entity is added or its country or state changes
(apps/tenants/organisation.py), when a lookup's companies are added and after each nightly
re-read (apps/tenants/registers_jobs.py).

The rules, in short (the brief has the reasons):
- Markets: each legal entity's country and each branch's country that the library covers is an
  operating market. The organisation never removes one, since a bank may serve a country
  without a branch.
- A licence-bound dimension the scope leaves open is closed only when the companies with
  register facts hold part of its licence-bound terms, and then with every term no licence
  answers (AML, tax, execution-only), so it hides only licence-bound rules no company holds a
  licence for. A dimension the scope restricts gains the held terms it lacks and loses the
  licence-bound terms no company holds, unless that would empty it, which would widen it.
- A company whose main business the mapping knows is outside the licence-bound terms its facts
  do not give it.
- A legal entity in a country the library covers is outside every other covered country but
  its branches' (the jurisdiction dimension), so the register offers it EU rules, its own
  country's and its branch countries' (REG-S19). The EU is never outside a company's scope,
  and a company with no country, or one the library does not cover, is never narrowed.
- A person's change wins: a term or a company line whose last change was an approved request is
  left as that request left it. A change by hand still needs a second person with a passkey
  (FP-02).

This module calls no write method itself: the writes are footprint_logic's, which names no
library model, as the library fence demands (apps/shared/tests_library_fence.py).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from apps.library.models import JurisdictionKind
from apps.shared.audit import Actor
from apps.shared.models import Tenant
from apps.taxonomy import footprint_logic, matching
from apps.taxonomy.footprint_logic import ENTITY_SCOPE_DIMENSIONS, MARKET_DIMENSION
from apps.taxonomy.models import EntityScopeExclusion, FootprintAction, FootprintHistory, TaxonomyTerm
from apps.tenants import registers_logic
from apps.tenants.models import OrgUnit, OrgUnitKind, RegisterEntry
from apps.tenants.schemas import RegisterFacts

# Who writes what the organisation gives the scope: the system, on the organisation's word.
ACTOR = Actor.system("organisation")
# One term of the scope, as (dimension key, term key).
Key = tuple[str, str]
# One company line: the legal entity and the term outside its own scope.
Line = tuple[OrgUnit, TaxonomyTerm]


@dataclass
class _Company:
    """What one legal entity's register facts give it."""

    derived: dict[str, set[str]] = field(default_factory=dict)
    known_business: bool = False
    branches: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Differences:
    """Where the scope differs from what the organisation gives it: terms to add to and take out
    of the bank's scope, and company lines to take out of and put back into a company's own."""

    adds: list[TaxonomyTerm]
    removes: list[TaxonomyTerm]
    excludes: list[Line]
    includes: list[Line]


def _facts(units: list[OrgUnit]) -> tuple[dict[uuid.UUID, _Company], dict[str, set[str]]]:
    """Each listed company's register facts, and every term the registers they come from can
    derive (`D(d)`), in one query."""
    companies: dict[uuid.UUID, _Company] = {}
    derivable: dict[str, set[str]] = defaultdict(set)
    for entry in RegisterEntry.objects.filter(org_unit__in=units).select_related("authority").order_by("org_unit_id", "authority__key"):
        facts = RegisterFacts.model_validate(entry.facts)
        authority = entry.authority.key
        for dimension, keys in registers_logic.derivable_terms(authority).items():
            derivable[dimension] |= keys
        if not facts.listed:
            continue
        company = companies.setdefault(entry.org_unit_id, _Company())
        for dimension, keys in registers_logic.derived_terms(authority, facts).items():
            company.derived[dimension] = company.derived.get(dimension, set()) | keys
        company.known_business = company.known_business or registers_logic.knows_main_business(authority, facts)
        company.branches |= {branch.jurisdiction for branch in facts.branches if branch.jurisdiction}
    return companies, derivable


def differences(tenant_id: uuid.UUID) -> Differences:
    """What `follow()` would write for this bank, before a person's changes are set aside."""
    units = list(OrgUnit.objects.filter(tenant_id=tenant_id, kind=OrgUnitKind.LEGAL_ENTITY.value, active=True).order_by("name", "id"))
    companies, derivable = _facts(units)
    restricting = matching.restricting_dimensions()
    dimensions = [dimension for dimension in derivable if dimension in restricting]
    terms: dict[Key, TaxonomyTerm] = {
        (term.dimension.key, term.key): term
        for term in TaxonomyTerm.objects.filter(
            active=True, dimension__active=True, dimension__key__in=[*dimensions, MARKET_DIMENSION]
        ).select_related("dimension", "jurisdiction")
        if term.dimension.key != MARKET_DIMENSION or term.jurisdiction_id is not None
    }
    live: dict[str, set[str]] = defaultdict(set)
    for dimension, key in terms:
        live[dimension].add(key)
    scope = matching.footprint_of(tenant_id)
    adds: set[Key] = set()
    removes: set[Key] = set()

    for dimension in dimensions:
        bound = derivable[dimension] & live[dimension]
        held = {key for company in companies.values() for key in company.derived.get(dimension, ()) if key in live[dimension]}
        current = scope.get(dimension, set())
        if not current:
            if held and bound - held:
                adds |= {(dimension, key) for key in held | (live[dimension] - bound)}
            continue
        adds |= {(dimension, key) for key in held - current}
        gone = (current & bound) - held
        if gone and current - gone:
            removes |= {(dimension, key) for key in gone}

    countries = {
        key
        for (dimension, key), term in terms.items()
        if dimension == MARKET_DIMENSION and term.jurisdiction is not None and term.jurisdiction.kind == JurisdictionKind.COUNTRY.value
    }
    reach: dict[uuid.UUID, set[str]] = {}
    for unit in units:
        branches = companies[unit.id].branches if unit.id in companies else set()
        reach[unit.id] = ({unit.country_code.lower()} | branches) & countries
        adds |= {(MARKET_DIMENSION, key) for key in reach[unit.id] - scope.get(MARKET_DIMENSION, set())}

    outside: dict[uuid.UUID, set[Key]] = defaultdict(set)
    for org_unit_id, dimension, key in EntityScopeExclusion.objects.filter(org_unit__in=units).values_list(
        "org_unit_id", "term__dimension__key", "term__key"
    ):
        outside[org_unit_id].add((dimension, key))
    excludes: list[Line] = []
    includes: list[Line] = []
    for unit in units:
        company = companies.get(unit.id)
        # The company lines this rule decides for the unit, and what they should be.
        ruled: set[str] = {MARKET_DIMENSION}
        should: set[Key] = set()
        if unit.country_code.lower() in countries:
            should |= {(MARKET_DIMENSION, key) for key in countries - reach[unit.id]}
        if company is not None and company.known_business:
            ruled |= set(ENTITY_SCOPE_DIMENSIONS)
            should |= {
                (dimension, key)
                for dimension in ENTITY_SCOPE_DIMENSIONS
                for key in (derivable.get(dimension, set()) & live.get(dimension, set())) - company.derived.get(dimension, set())
            }
        excludes.extend((unit, terms[pair]) for pair in sorted(should - outside[unit.id], key=lambda pair: _order(terms[pair])))
        # A line of a term retired since is left alone: it narrows nothing any more.
        back = (pair for pair in outside[unit.id] - should if pair[0] in ruled and pair in terms)
        includes.extend((unit, terms[pair]) for pair in sorted(back, key=lambda pair: _order(terms[pair])))

    return Differences(
        adds=[terms[pair] for pair in sorted(adds, key=lambda pair: _order(terms[pair]))],
        removes=[terms[pair] for pair in sorted(removes, key=lambda pair: _order(terms[pair]))],
        excludes=excludes,
        includes=includes,
    )


def _by_hand(tenant_id: uuid.UUID) -> set[tuple[uuid.UUID | None, uuid.UUID]]:
    """The bank's terms (no company) and the company lines whose last change was an approved
    request: a person's, which the organisation leaves as they are. One query."""
    latest = (
        FootprintHistory.objects.filter(tenant_id=tenant_id, term__isnull=False)
        .order_by("org_unit_id", "term_id", "-id")
        .distinct("org_unit_id", "term_id")
        .values_list("org_unit_id", "term_id", "request_id")
    )
    return {(org_unit_id, term_id) for org_unit_id, term_id, request_id in latest if request_id is not None}


def follow(*, tenant: Tenant) -> None:
    """Bring the bank's scope and its companies' own scopes in line with the organisation,
    leaving what a person changed by hand as they left it."""
    found = differences(tenant.id)
    if not (found.adds or found.removes or found.excludes or found.includes):
        return
    hand = _by_hand(tenant.id)

    def bank(terms: list[TaxonomyTerm]) -> list[TaxonomyTerm]:
        return [term for term in terms if (None, term.id) not in hand]

    def companies(lines: list[Line]) -> list[Line]:
        return [(unit, term) for unit, term in lines if (unit.id, term.id) not in hand]

    footprint_logic.switch_on(tenant=tenant, actor=ACTOR, terms=bank(found.adds), request=None, step_up_assertion_id=None)
    footprint_logic.switch_off(tenant=tenant, actor=ACTOR, terms=bank(found.removes), request=None, step_up_assertion_id=None)
    for lines, action in ((found.excludes, FootprintAction.REMOVED), (found.includes, FootprintAction.ADDED)):
        footprint_logic.switch_entities(
            tenant=tenant, actor=ACTOR, lines=companies(lines), action=action, request=None, step_up_assertion_id=None, changed_by=None
        )


def _order(term: TaxonomyTerm) -> tuple[int, int, str]:
    """The order the scope page draws terms in: dimension, then term."""
    return (term.dimension.sort_order, term.sort_order, term.key)
