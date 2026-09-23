"""The standards check (INV-08, FP-01, D-36, D-37): what a proposal may say about a standard.

A term of an opt-in dimension (the standards a bank follows) shows a record only to a bank
whose regulatory scope names that term. Put on a law's obligation, it would hide binding law
from every bank that follows no standard, so such a term sits only on an obligation whose
instrument's level is a standard. The dimension and
the level are told apart by their kind, never by a key.

`check()` runs where a proposal is made, where a reviewer corrects it and where it is
applied, because a proposal filed before this rule may still wait in the queue. It takes
the proposal's kind, the instrument the obligation belongs to and the resolved term ids, so
the rules of the kinds that create a standard's obligations can join it here.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

import pydantic
from django.core.exceptions import ValidationError

from apps.library.models import Instrument
from apps.library.reading import active_obligation, terms_of
from apps.proposals.schemas import ProposalObligationVersionPayload
from apps.taxonomy.models import InstrumentLevelKind, TaxonomyTerm, TermDimensionKind

STANDARD_TERM_REFUSAL = (
    "A standard's term sits only on a standard's own obligation: on a law's obligation it would hide "
    "the law from every bank that follows no standard. Leave the term out."
)


def check(kind: str, instrument: Instrument, term_ids: Iterable[uuid.UUID]) -> None:
    """422 `standard_term_only_on_standards` when `term_ids` holds a term of an opt-in
    dimension and `instrument`'s level is not a standard. `kind` is the proposal's kind."""
    if instrument.level.kind == InstrumentLevelKind.STANDARD.value:
        return
    ids = list(term_ids)
    if ids and TaxonomyTerm.objects.filter(pk__in=ids, dimension__kind=TermDimensionKind.OPT_IN.value).exists():
        raise ValidationError(STANDARD_TERM_REFUSAL, code="standard_term_only_on_standards")


def check_payload(kind: str, obligation_id: uuid.UUID | None, payload: pydantic.BaseModel) -> None:
    """`check()` over a parsed payload, for creation and correction: the obligation it
    versions, read as it is now, and the scope it asks for. A payload that leaves the scope
    alone adds no term, so there is nothing to check."""
    if not isinstance(payload, ProposalObligationVersionPayload) or not payload.terms or obligation_id is None:
        return
    check(kind, active_obligation(obligation_id).instrument, [term.id for term in terms_of(payload.terms)])
