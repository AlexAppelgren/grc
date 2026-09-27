"""What a narrowed entry could not see (ACC-07, AC-ACC1, AGENT_ACCESS.md section 7).

A developer reads silence as "nothing applies", so a narrowed entry never narrows silently.
The description an agent sends is compared against the labels and usage notes of the
bank's footprint terms that lie outside the entry's scope, and every term it touches is
named by its dimension's label and its own: "Licensed activity: Card issuing". Only labels
are compared and only labels are answered, never a record, so nothing crosses the line.

The comparison is a word match and needs no model, so it answers with AI switched off: a
term is touched when every word of one of its labels, in any language, is in the
description, or when its usage note shares `AGENT_ACCESS_NOTE_MATCH_WORDS` words with it.
Words are lower-cased, stripped of a few English endings ("issues" and "issuing" are both
"issu") and of words too short or too common to mean anything. `words()` is also how
what_applies.py ranks the list, so the two read a description the same way.

A term is outside the scope when the entry's terms restrict its dimension and leave it
out: its dimension narrows the footprint (or is opt-in) and the entry names some term in it
(or it is opt-in, which the entry must name to see). A dimension the entry names nothing in
does not restrict (FP-01), so its terms are visible and never named here.
"""

from __future__ import annotations

import re
import uuid

from django.conf import settings
from django.db.models import Prefetch

from apps.agents.schemas import WhatAppliesOutsideTerm
from apps.library.schemas import LibraryRef
from apps.shared.vocabulary import label_for
from apps.taxonomy import matching
from apps.taxonomy.entry_scope import EntryScope
from apps.taxonomy.models import FootprintTerm, TaxonomyTermLabel, TermDimensionLabel

_WORD = re.compile(r"[^\W_]+")
_ENDINGS = ("ing", "es", "ed", "s", "e")
_MIN_LENGTH = 3
# Words that say nothing about what a thing is, in the two languages labels are written in.
_STOP = frozenset(
    {
        "the", "and", "for", "that", "with", "against", "from", "this", "into", "our", "new", "its",
        "are", "was", "which", "will", "has", "have", "not", "all", "any", "can", "use", "used",
        "och", "att", "som", "för", "med", "den", "det", "ett", "till", "inte", "eller", "vid", "har", "ska",
    }
)


def _stem(word: str) -> str:
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= _MIN_LENGTH and not word.endswith("s" + ending):
            return word[: -len(ending)]
    return word


def words(text: str) -> set[str]:
    """The meaningful words of `text`, lower-cased and stemmed."""
    return {_stem(word) for word in _WORD.findall(text.lower()) if len(word) >= _MIN_LENGTH and word not in _STOP}


def _outside(scope: EntryScope, dimension: str, term: str, restricting: matching.Restricting) -> bool:
    if dimension not in restricting:
        return False
    named = scope.terms.get(dimension)
    if not named and dimension not in restricting.opt_in:
        return False
    return term not in (named or ())


def outside_terms(tenant_id: uuid.UUID, scope: EntryScope, description: str, order: list[str]) -> list[WhatAppliesOutsideTerm]:
    """The footprint terms outside `scope` that `description` touches, by label, in the
    footprint's order. Nothing for an entry that narrows nothing. The tenant must be
    activated: the footprint is read under row-level security."""
    if not scope.narrowed:
        return []
    asked = words(description)
    restricting = matching.restricting_dimensions()
    rows = (
        FootprintTerm.objects.filter(tenant_id=tenant_id, term__active=True, term__dimension__active=True)
        .select_related("term__dimension")
        .prefetch_related(
            Prefetch("term__labels", queryset=TaxonomyTermLabel.objects.all()),
            Prefetch("term__dimension__labels", queryset=TermDimensionLabel.objects.all()),
        )
        .order_by("term__dimension__sort_order", "term__dimension__key", "term__sort_order", "term__key")
    )
    touched = []
    for row in rows:
        term, dimension = row.term, row.term.dimension
        if not _outside(scope, dimension.key, term.key, restricting):
            continue
        labels = [words(label.text) for label in term.labels.all()] or [words(term.key.replace("_", " "))]
        by_label = any(label and label <= asked for label in labels)
        by_note = len(words(term.usage_note) & asked) >= settings.AGENT_ACCESS_NOTE_MATCH_WORDS
        if by_label or by_note:
            touched.append(
                WhatAppliesOutsideTerm(
                    dimension=LibraryRef(key=dimension.key, kind=dimension.kind, label=label_for(dimension, order)),
                    term=LibraryRef(key=term.key, kind=None, label=label_for(term, order)),  # type: ignore[arg-type]
                )
            )
    return touched
