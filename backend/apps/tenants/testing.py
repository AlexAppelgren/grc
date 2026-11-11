"""Tenants builders for tests (playbook 8.1). A licence's type is a term of the shared
library, which apps/shared/factories.py may not write (the library fence exempts only
`testing.py` modules), so the one term a licence needs is written here."""

from __future__ import annotations

from apps.shared.tenancy import library_write
from apps.taxonomy.models import TaxonomyTerm, TermDimension, TermDimensionKind
from apps.tenants import registers_logic
from apps.tenants.schemas import RegisterFacts


def licence_type_term() -> TaxonomyTerm:
    """A `licence_type` term to point a licence at, reused once it exists."""
    with library_write("test builder"):
        dimension, _ = TermDimension.objects.get_or_create(
            key="licence_type", defaults={"kind": TermDimensionKind.CLASSIFICATION.value, "restricts_footprint": False}
        )
        term, _ = TaxonomyTerm.objects.get_or_create(dimension=dimension, key="credit_institution")
    return term


def entity_term() -> TaxonomyTerm:
    """The seeded `legal_entity:bank` term a legal entity carries; needs the taxonomy seeds."""
    return TaxonomyTerm.objects.get(dimension__key="legal_entity", key="bank")


def split_businesses(authority_key: str, text: str) -> tuple[list[str], list[str]]:
    """The business names the mapping knows, and the comma-separated rest it does not, each in
    the register's order."""
    parts = registers_logic._split(authority_key, text)
    return [name for _, name, known in parts if known], [name for _, name, known in parts if not known]


def branch_jurisdictions(facts: RegisterFacts) -> set[str]:
    """The jurisdiction keys of the countries the company has branches in, matched exactly,
    case aside, on the labels of the library's active countries."""
    names = registers_logic._jurisdictions_by_name()
    return {names[branch.country_name.casefold()] for branch in facts.branches if branch.country_name.casefold() in names}
