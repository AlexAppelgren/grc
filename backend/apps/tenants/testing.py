"""Tenants builders for tests (playbook 8.1). A licence's type is a term of the shared
library, which apps/shared/factories.py may not write (the library fence exempts only
`testing.py` modules), so the one term a licence needs is written here."""

from __future__ import annotations

from apps.shared.tenancy import library_write
from apps.taxonomy.models import TaxonomyTerm, TermDimension, TermDimensionKind


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
