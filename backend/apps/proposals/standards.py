"""The standards check (INV-08, FP-01, D-35, D-36, D-37): what a proposal may say about a standard.

A standard's text is licensed, so the library holds only its public facts and exactly one
conformance obligation per edition, in our own words, carrying exactly one term of an
opt-in dimension (the standards a bank follows). Four rules, each with its own code:

- `licensed_text`: no provision and no provision version under a standard, every field
  source on a standard's obligation an https link, never a pasted clause or a provision key,
  and a new obligation's `ref_label` and any proposal's `source_label` the standard's
  official reference, never a clause (the label lands on the obligation, H35).
- `one_conformance_obligation`: a new obligation under a standard that already holds an
  active one.
- `standard_term_required`: a standard's obligation whose scope holds no opt-in term, or
  more than one.
- `standard_term_only_on_standards`: an opt-in term on an obligation whose instrument is
  not a standard. Put on a law's obligation, it would hide binding law from every bank that
  follows no standard.

The level and the dimension are told apart by their kind, never by a key.

`check()` runs where a proposal is made, where a reviewer corrects it and where it is
applied, because a proposal filed before a rule may still wait in the queue. A payload is
stored at creation, so a check only at apply would leave licensed text in the platform
database (D-35).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping

import pydantic
from django.core.exceptions import ValidationError

from apps.library.models import Instrument, Obligation, RecordStatus
from apps.library.reading import active_obligation, active_provision, shared_instrument, terms_of
from apps.proposals.models import ProposalKind
from apps.proposals.schemas import (
    ProposalObligationPayload,
    ProposalObligationVersionPayload,
    ProposalProvisionPayload,
    ProposalProvisionVersionPayload,
)
from apps.taxonomy.models import InstrumentLevelKind, TaxonomyTerm, TermDimensionKind

PROVISION_KINDS = frozenset({ProposalKind.NEW_PROVISION.value, ProposalKind.NEW_PROVISION_VERSION.value})
# The kinds that set an obligation's scope, which under a standard keeps exactly one standard
# term: a new obligation, a new version, and a batch's re-tag (PRO-04).
OBLIGATION_KINDS = frozenset(
    {ProposalKind.NEW_OBLIGATION.value, ProposalKind.NEW_OBLIGATION_VERSION.value, ProposalKind.OBLIGATION_SCOPE.value}
)

STANDARD_TERM_REFUSAL = (
    "A standard's term sits only on a standard's own obligation: on a law's obligation it would hide "
    "the law from every bank that follows no standard. Leave the term out."
)
LICENSED_PROVISION_REFUSAL = (
    "A standard's text is licensed, so the library holds no provision of it. Propose its public facts "
    "and its one conformance obligation instead."
)
LICENSED_SOURCE_REFUSAL = (
    "A standard's records are sourced by https links to public pages only, never by quoted text or a "
    "provision. Not a link: {fields}."
)
ONE_CONFORMANCE_REFUSAL = (
    "A standard holds exactly one conformance obligation, and this one already has it. Propose a new "
    "version of that obligation instead."
)
OFFICIAL_REFERENCE_ONLY = (
    "A standard's obligation is labelled by the standard's official reference, {ref}, and never by a "
    "clause or a control."
)
OFFICIAL_SOURCE_LABEL_ONLY = (
    "A standard's source is named by its official reference, {ref}, and never by a clause, a control or "
    "quoted text. Give that reference as sourceLabel, or leave it out."
)
STANDARD_TERM_REQUIRED = (
    "A standard's obligation carries exactly one standard term, the standard it is for. It carries {count}."
)


def check(
    kind: str,
    instrument: Instrument,
    term_ids: Collection[uuid.UUID] | None,
    field_sources: Mapping[str, str],
    ref_label: str | None = None,
    source_label: str = "",
) -> None:
    """Refuse what `kind` may not say about `instrument` (see the module docstring for the
    four codes, all 422). `term_ids` is the obligation's scope as the proposal sets it,
    resolved, or None when it leaves the scope alone; `field_sources` and `source_label` are
    the proposal's; `ref_label` is a new obligation's. Under a standard both labels are its
    official reference, and the source label may be left empty."""
    from apps.proposals.logic import is_link

    opt_in = 0
    if term_ids:
        opt_in = TaxonomyTerm.objects.filter(pk__in=list(term_ids), dimension__kind=TermDimensionKind.OPT_IN.value).count()
    if instrument.level.kind != InstrumentLevelKind.STANDARD.value:
        if opt_in:
            raise ValidationError(STANDARD_TERM_REFUSAL, code="standard_term_only_on_standards")
        return
    if kind in PROVISION_KINDS:
        raise ValidationError(LICENSED_PROVISION_REFUSAL, code="licensed_text")
    unlinked = sorted(field for field, source in field_sources.items() if not is_link(source))
    if unlinked:
        raise ValidationError(LICENSED_SOURCE_REFUSAL.format(fields=", ".join(unlinked)), code="licensed_text")
    if ref_label is not None and ref_label.strip() != instrument.official_ref:
        raise ValidationError(OFFICIAL_REFERENCE_ONLY.format(ref=instrument.official_ref), code="licensed_text")
    if kind == ProposalKind.NEW_OBLIGATION.value and Obligation.objects.filter(
        instrument=instrument, status=RecordStatus.ACTIVE.value
    ).exists():
        raise ValidationError(ONE_CONFORMANCE_REFUSAL, code="one_conformance_obligation")
    if kind in OBLIGATION_KINDS and term_ids is not None and opt_in != 1:
        raise ValidationError(STANDARD_TERM_REQUIRED.format(count=opt_in), code="standard_term_required")
    if source_label.strip() not in ("", instrument.official_ref):
        raise ValidationError(OFFICIAL_SOURCE_LABEL_ONLY.format(ref=instrument.official_ref), code="licensed_text")


def check_payload(
    kind: str,
    target_id: uuid.UUID | None,
    payload: pydantic.BaseModel,
    field_sources: Mapping[str, str],
    source_label: str = "",
) -> None:
    """`check()` over a parsed payload, for creation and correction: the instrument the
    record sits under, read as the library holds it now, and the scope the payload asks
    for. A version that leaves the scope alone passes None; a new obligation always sets
    its scope, an empty one included."""
    ref_label = None
    if isinstance(payload, ProposalObligationVersionPayload) and target_id is not None:
        instrument, terms = active_obligation(target_id).instrument, payload.terms
    elif isinstance(payload, ProposalObligationPayload):
        instrument, terms, ref_label = shared_instrument(payload.instrument), payload.terms or [], payload.ref_label
    elif isinstance(payload, ProposalProvisionPayload):
        instrument, terms = shared_instrument(payload.instrument), None
    elif isinstance(payload, ProposalProvisionVersionPayload) and target_id is not None:
        instrument, terms = active_provision(target_id).instrument, None
    else:
        return
    term_ids = None if terms is None else [term.id for term in terms_of(terms)] if terms else []
    check(kind, instrument, term_ids, field_sources, ref_label, source_label)
