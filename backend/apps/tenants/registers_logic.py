"""From a supervisor's register to scope terms (TEN-07, FP-05; PUBLIC_REGISTERS.md 4.1, D-121).

`register_terms.json` beside this module maps a register's own wording to term keys, per
authority: `categories` maps a business name exactly as the register writes it (main or
other business), and `licences` a phrase found in a licence's text, compared
case-insensitively. A company's derived terms are the union over its categories and its
licences: what its licences allow, not what it chooses to do. A name or a licence the file
does not know is listed as unmapped and maps to nothing; nothing is guessed.

Reads only: the functions here name library models (an authority, a jurisdiction, a term) to
read them and never write, so the library fence's AST guard
(apps/shared/tests_library_fence.py) sees no write beside them. The terms the file names are
checked against the seeded taxonomy by apps/tenants/tests_registers_logic.py; a key the live
taxonomy does not hold is dropped where a term is read (`entity_terms`), never created.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from apps.library.models import Authority, JurisdictionKind, JurisdictionLabel
from apps.shared.adapters.registers import LicenceFacts, get_registers
from apps.taxonomy.models import TaxonomyTerm
from apps.taxonomy.schemas import TermRef
from apps.tenants.schemas import RegisterFacts, RegisterFactsBranch, RegisterFactsLicence
from apps.tenants.terms import term_refs

MAPPING_FILE = Path(__file__).with_name("register_terms.json")
ENTITY_DIMENSION = "legal_entity"
_TERM = re.compile(r"([a-z][a-z0-9_]*):([a-z0-9][a-z0-9_]*)")


@dataclass(frozen=True)
class _Mapping:
    categories: dict[str, tuple[tuple[str, str], ...]]
    licences: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]


def _terms(value: object, where: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list) or not all(isinstance(term, str) and _TERM.fullmatch(term) for term in value):
        raise ImproperlyConfigured(f"{MAPPING_FILE.name}: {where} must be a list of `dimension:key` terms")
    return tuple((term.split(":")[0], term.split(":")[1]) for term in value)


@functools.cache
def _mappings() -> dict[str, _Mapping]:
    """The file, read once and checked: a mapping that is not the shape this module reads
    refuses to load rather than mapping part of a register."""
    raw = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    mappings: dict[str, _Mapping] = {}
    for authority, spec in raw.items():
        if authority == "about":
            continue
        if not isinstance(spec, dict) or not isinstance(spec.get("categories"), dict) or not isinstance(spec.get("licences"), list):
            raise ImproperlyConfigured(f"{MAPPING_FILE.name}: {authority} must hold `categories` and `licences`")
        licences = []
        for rule in spec["licences"]:
            if not isinstance(rule, dict) or not isinstance(rule.get("contains"), str) or not rule["contains"].strip():
                raise ImproperlyConfigured(f"{MAPPING_FILE.name}: every licence rule of {authority} needs a phrase in `contains`")
            licences.append((rule["contains"].casefold(), _terms(rule.get("terms"), f"{authority} licence {rule['contains']!r}")))
        mappings[authority] = _Mapping(
            categories={name: _terms(terms, f"{authority} category {name!r}") for name, terms in spec["categories"].items()},
            licences=tuple(licences),
        )
    return mappings


def _mapping(authority_key: str) -> _Mapping:
    return _mappings().get(authority_key) or _Mapping(categories={}, licences=())


def _grouped(terms: list[tuple[str, str]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for dimension, key in terms:
        grouped.setdefault(dimension, set()).add(key)
    return grouped


# ---------------------------------------------------------------------------------------
# Business names
# ---------------------------------------------------------------------------------------
def _split(authority_key: str, text: str) -> list[tuple[int, str, bool]]:
    """Every business name in the register's comma-joined text as (position, name, known), in
    the register's order. Known names are found longest first, each only as a whole
    comma-separated item, so `Riksbolag, livförsäkringar` is one name and not two."""
    found: list[tuple[int, str, bool]] = []
    rest = text
    for name in sorted(_mapping(authority_key).categories, key=len, reverse=True):
        pattern = re.compile(rf"(?:^|(?<=,))\s*{re.escape(name)}\s*(?=,|$)")
        found.extend((match.start(), name, True) for match in pattern.finditer(rest))
        # Blank what was found, keeping its length and its commas, so positions stay put.
        rest = pattern.sub(lambda match: re.sub(r"[^,]", " ", match.group(0)), rest)
    for match in re.finditer(r"[^,]+", rest):
        if match.group(0).strip():
            found.append((match.start(), match.group(0).strip(), False))
    return sorted(found)


def split_businesses(authority_key: str, text: str) -> tuple[list[str], list[str]]:
    """The business names the mapping knows, and the comma-separated rest it does not, each in
    the register's order."""
    parts = _split(authority_key, text)
    return [name for _, name, known in parts if known], [name for _, name, known in parts if not known]


# ---------------------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------------------
def _licence_terms(mapping: _Mapping, text: str) -> list[tuple[str, str]] | None:
    """The terms a licence line gives, or None when it matches no phrase."""
    hits = [terms for phrase, terms in mapping.licences if phrase in text.casefold()]
    return [term for terms in hits for term in terms] if hits else None


def derived_terms(authority_key: str, facts: RegisterFacts) -> dict[str, set[str]]:
    """Dimension key -> term keys the company's main business, other businesses and licences
    give it. Empty for a company the register no longer lists: it holds no licence."""
    if not facts.listed:
        return {}
    mapping = _mapping(authority_key)
    terms: list[tuple[str, str]] = []
    for name in (facts.main_business, *facts.other_businesses):
        terms.extend(mapping.categories.get(name, ()))
    for licence in facts.licences:
        terms.extend(_licence_terms(mapping, licence.text) or ())
    return _grouped(terms)


def term_sources(authority_key: str, facts: RegisterFacts) -> dict[tuple[str, str], list[str]]:
    """(dimension key, term key) -> the register lines that give the term, in the register's
    order: business names and licence texts, as the scope suggestion names its reasons (FP-05).
    Empty for a company the register no longer lists."""
    if not facts.listed:
        return {}
    mapping = _mapping(authority_key)
    sources: dict[tuple[str, str], list[str]] = {}
    for name in (facts.main_business, *facts.other_businesses):
        for term in mapping.categories.get(name, ()):
            sources.setdefault(term, []).append(name)
    for licence in facts.licences:
        for term in _licence_terms(mapping, licence.text) or ():
            sources.setdefault(term, []).append(licence.text)
    return sources


def derivable_terms(authority_key: str) -> dict[str, set[str]]:
    """Dimension key -> every term key the authority's mapping can produce: `D(d)` of
    PUBLIC_REGISTERS.md 4.1. A term outside it is a choice no licence answers."""
    mapping = _mapping(authority_key)
    terms = [term for terms in mapping.categories.values() for term in terms]
    terms.extend(term for _, terms in mapping.licences for term in terms)
    return _grouped(terms)


def entity_type(authority_key: str, facts: RegisterFacts) -> str | None:
    """The company's type: the first `legal_entity` key its main business maps to, or None."""
    terms = _mapping(authority_key).categories.get(facts.main_business, ())
    return next((key for dimension, key in terms if dimension == ENTITY_DIMENSION), None)


def knows_main_business(authority_key: str, facts: RegisterFacts) -> bool:
    """Whether the mapping knows the company's main business while the register lists it. A
    company whose main business is unknown, or that is gone from the register, gets no
    exclusions (4.3): it is never narrowed by a guess."""
    return facts.listed and facts.main_business in _mapping(authority_key).categories


def unmapped(authority_key: str, facts: RegisterFacts) -> list[str]:
    """The business names the mapping does not know and the licence lines that match no
    phrase, in the register's order: shown as not used for the scope."""
    mapping = _mapping(authority_key)
    names = [name for name in (facts.main_business, *facts.other_businesses) if name and name not in mapping.categories]
    return names + [licence.text for licence in facts.licences if _licence_terms(mapping, licence.text) is None]


def entity_terms(keys: set[str], order: list[str]) -> dict[str, TermRef]:
    """Key -> the live `legal_entity` term it names, labelled in the reader's language; a key
    the taxonomy does not hold, or holds retired, is left out."""
    if not keys:
        return {}
    terms = list(TaxonomyTerm.objects.filter(dimension__key=ENTITY_DIMENSION, key__in=keys, active=True).order_by("key"))
    refs = term_refs(terms, order)
    return {term.key: refs[term.id] for term in terms}


# ---------------------------------------------------------------------------------------
# Countries and authorities
# ---------------------------------------------------------------------------------------
def _jurisdictions_by_name() -> dict[str, str]:
    """A country's name in any of its labels, case-folded -> the key of the active country
    jurisdiction it names. A register writes countries in its own language (`Danmark`), which
    is one of the labels."""
    rows = JurisdictionLabel.objects.filter(vocabulary__active=True, vocabulary__kind=JurisdictionKind.COUNTRY.value)
    return {text.casefold(): key for text, key in rows.order_by("vocabulary__sort_order", "language").values_list("text", "vocabulary__key")}


def branch_jurisdictions(facts: RegisterFacts) -> set[str]:
    """The jurisdiction keys of the countries the company has branches in, matched exactly,
    case aside, on the labels of the library's active countries; a country the library does
    not cover is left out."""
    names = _jurisdictions_by_name()
    return {names[branch.country_name.casefold()] for branch in facts.branches if branch.country_name.casefold() in names}


def authority_for_country(country_code: str) -> Authority | None:
    """The library authority whose register is read for companies of `country_code`, or None
    when no register bleqq reads covers that country."""
    if not country_code:
        return None
    return (
        Authority.objects.select_related("jurisdiction")
        .filter(key__in=get_registers().authorities, jurisdiction__key=country_code.lower())
        .order_by("key")
        .first()
    )


def authorities(keys: set[str]) -> dict[str, Authority]:
    """Key -> the library authority it names; a key the library does not hold is left out."""
    return {row.key: row for row in Authority.objects.filter(key__in=keys).order_by("key")}


def register_facts(authority_key: str, facts: LicenceFacts) -> RegisterFacts:
    """A register's read as the facts the bank keeps: the other businesses split into names,
    each branch's country matched to a jurisdiction the library covers."""
    names = _jurisdictions_by_name()
    return RegisterFacts(
        name=facts.name,
        registration_number=facts.registration_number,
        lei=facts.lei,
        main_business=facts.main_business,
        other_businesses=[name for _, name, _ in _split(authority_key, facts.other_businesses)],
        licences=[RegisterFactsLicence(text=licence.text, granted_on=licence.granted_on) for licence in facts.licences],
        branches=[
            RegisterFactsBranch(name=branch.name, country_name=branch.country_name, jurisdiction=names.get(branch.country_name.casefold()))
            for branch in facts.branches
        ],
        listed=True,
    )
