"""The library terms the bank's organisation and products are described with (TEN-02).
Reads only: the write modules name no library model, so the library fence's AST guard
(apps/shared/tests_library_fence.py) sees no write beside one.

A licence's type and services and a product's scope are terms of the dimensions an
obligation's scope is written with, read from the dimension rows by kind rather than listed
here, so a dimension the library adds by proposal is usable the day it exists.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from django.core.exceptions import ValidationError

from apps.taxonomy.models import TaxonomyTerm, TaxonomyTermLabel, TermDimension, TermDimensionKind
from apps.taxonomy.reading import Labels
from apps.taxonomy.schemas import TermRef
from apps.taxonomy.terms_logic import MAX_KEYS_IN_MESSAGE, mirrored_dimensions, term_ref

# The name the write modules use for a term, so none of them names the library model.
Term = TaxonomyTerm
# The dimension kinds an obligation's scope is written with (D-36): a classification
# dimension never scopes anything, so none of its terms describes an entity or a product.
SCOPE_KINDS = (TermDimensionKind.SCOPE.value, TermDimensionKind.OPT_IN.value)


def scope_terms(keys: Iterable[str]) -> list[TaxonomyTerm]:
    """The active terms these keys name among the dimensions obligations are scoped with,
    in the order given, or 422 `unknown_key` naming each key that names none or more than
    one. A mirrored dimension tags no record (FP-04), so its terms are not offered."""
    wanted = list(dict.fromkeys(keys))
    if not wanted:
        return []
    dimensions = set(TermDimension.objects.filter(active=True, kind__in=SCOPE_KINDS).values_list("id", flat=True))
    dimensions -= mirrored_dimensions(dimensions)
    found: dict[str, list[TaxonomyTerm]] = {}
    for term in TaxonomyTerm.objects.filter(dimension_id__in=dimensions, key__in=wanted, active=True).order_by("dimension_id"):
        found.setdefault(term.key, []).append(term)
    refused = [key for key in wanted if len(found.get(key, [])) != 1]
    if refused:
        listed = ", ".join(refused[:MAX_KEYS_IN_MESSAGE])
        raise ValidationError(
            f"Not a term obligations are scoped with, or a key two dimensions share: {listed}. Read the live terms at GET /taxonomy/terms.",
            code="unknown_key",
        )
    return [found[key][0] for key in wanted]


def term_refs(terms: list[TaxonomyTerm], order: list[str]) -> dict[uuid.UUID, TermRef]:
    """Each term as a reference in the reader's language, labels read in one query."""
    labels = Labels.for_rows(TaxonomyTermLabel, terms, field="term")
    return {term.id: term_ref(term, labels.texts(term.id), order) for term in terms}
