"""Business logic of the proposals app (PRO-01, PRO-02, AC-PRO1, AC-PRO2, VOC-07).

A proposal is the only door into the library. People and agents create them here; a
second, independent principal decides one here — a person, or a platform key bound to an
agent and holding `proposals:review` (PRO-S13, D-62, ADR 0054) — and apps/proposals/apply.py
applies its payload inside `library_write()` in the same transaction as the approval's
audit row. Nothing here writes a library row, which is why this module names no
`LibraryModel` class (the library fence's AST guard, apps/shared/tests_library_fence.py);
the library rows a proposal points at and cites are looked up through
apps/library/reading.py, which is where every library read lives.

Four eyes (AC-PRO2) is checked here, in `_decidable`, and by the widened
`proposal_four_eyes` check constraint on the same three pairs of columns; the API answers
409 `four_eyes_violation`. The `Reviewer` below is who decided, a person or an agent, never
a bare `User`; `_decidable` refuses a repeated user, a repeated key or a repeated agent
definition, and a reviewing key that names no agent, so an unbound platform key can never
stand in for the independent second agent the scope is for. A proposal with no proposing
user, key or agent (none of the three match) may be decided by any reviewer.

A proposal made inside a tenant (a bank's own person or its agent key) is linked to that
tenant through `ProposalTenant`, a tenant table under forced row-level security, and its
creation is audited under that tenant. The `proposal` row itself carries only the boolean
`proposed_in_tenant`, so the console can withhold the proposer's identity (PRO-03) without
learning which bank they work for.

Idempotency (playbook 4.3): an agent retries with the same `Idempotency-Key`. The same body
answers the proposal it already made (200, and an audit row saying the retry happened, so
a flapping agent shows in the log); a different body under the same key is 409
`idempotency_conflict`, because silently keeping either version would lose the other.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pydantic
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.agents import runs
from apps.agents.models import AgentRun
from apps.agents.screen import screen_all
from apps.governance import ai_log
from apps.governance.models import AiPurpose
from apps.library.models import DatePrecision, SubjectType
from apps.library.reading import (
    InstrumentRefs,
    active_obligation,
    active_provision,
    instrument_refs,
    live_duty_type,
    live_provision_kind,
    parent_provision,
    shared_instrument,
    stable_key_taken,
    terms_of,
    unknown_provision_keys,
)
from apps.proposals import standards
from apps.proposals.models import OriginType, Proposal, ProposalKind, ProposalStatus, ProposalTenant
from apps.proposals.schemas import (
    ProposalActorRef,
    ProposalAgentRef,
    ProposalInstrumentPayload,
    ProposalObligationPayload,
    ProposalObligationVersionPayload,
    ProposalProvisionPayload,
    ProposalProvisionVersionPayload,
    ProposalRow,
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
    ProposalVocabularyCreatePayload,
    ProposalVocabularyMergePayload,
    ProposalVocabularyRelabelPayload,
    ProposalVocabularyRetirePayload,
)
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.schemas import AgentDecision

SUBJECT_TYPE = "proposal"
# The widest retry key the column holds, so a longer one is a 422 rather than a failed insert.
IDEMPOTENCY_KEY_MAX_CHARS: int = Proposal._meta.get_field("idempotency_key").max_length or 0
# What an obligation proposal points at (schema v0.3 `subject_type`).
OBLIGATION_TARGET = "obligation"
# What a provision version proposal points at.
PROVISION_TARGET = "provision"
# The library list a rejection's reason is a row of (PRO-01, VOC-07).
REJECTION_REASON_LIST = "rejection_reason"

# The named payload schema per kind (PRO-01): apply() never reads a free-form dictionary.
PAYLOAD_SCHEMAS: dict[str, type[pydantic.BaseModel]] = {
    ProposalKind.VOCABULARY_CREATE.value: ProposalVocabularyCreatePayload,
    ProposalKind.VOCABULARY_RELABEL.value: ProposalVocabularyRelabelPayload,
    ProposalKind.VOCABULARY_RETIRE.value: ProposalVocabularyRetirePayload,
    ProposalKind.VOCABULARY_RESTORE.value: ProposalVocabularyRetirePayload,
    ProposalKind.VOCABULARY_MERGE.value: ProposalVocabularyMergePayload,
    ProposalKind.TERM_CREATE.value: ProposalTermCreatePayload,
    ProposalKind.TERM_UPDATE.value: ProposalTermUpdatePayload,
    ProposalKind.NEW_OBLIGATION_VERSION.value: ProposalObligationVersionPayload,
    ProposalKind.NEW_INSTRUMENT.value: ProposalInstrumentPayload,
    ProposalKind.NEW_OBLIGATION.value: ProposalObligationPayload,
    ProposalKind.NEW_PROVISION.value: ProposalProvisionPayload,
    ProposalKind.NEW_PROVISION_VERSION.value: ProposalProvisionVersionPayload,
}
VOCABULARY_KINDS = frozenset(
    kind.value
    for kind in (
        ProposalKind.VOCABULARY_CREATE,
        ProposalKind.VOCABULARY_RELABEL,
        ProposalKind.VOCABULARY_RETIRE,
        ProposalKind.VOCABULARY_RESTORE,
        ProposalKind.VOCABULARY_MERGE,
    )
)
OBLIGATION_KINDS = frozenset({ProposalKind.NEW_OBLIGATION_VERSION.value})
# The kinds that version a record which exists, by the target type each one names.
VERSION_TARGETS = {
    ProposalKind.NEW_OBLIGATION_VERSION.value: OBLIGATION_TARGET,
    ProposalKind.NEW_PROVISION_VERSION.value: PROVISION_TARGET,
}
# The kinds that bring a new record into the library. They name no target, since the record
# does not exist yet, and every fact they carry is sourced by an https link: a new record
# has no provision of its own to cite (PRO-01).
NEW_RECORD_KINDS = frozenset(
    {ProposalKind.NEW_INSTRUMENT.value, ProposalKind.NEW_OBLIGATION.value, ProposalKind.NEW_PROVISION.value}
)
NEW_RECORD_PAYLOADS = (ProposalInstrumentPayload, ProposalObligationPayload, ProposalProvisionPayload)
# The kinds a reviewer may correct: each carries sourced facts from an authority, which a
# reviewer checks against the same source (PRO-02).
CORRECTABLE_KINDS = frozenset(VERSION_TARGETS) | NEW_RECORD_KINDS
# The dimension an instrument's regime is a term of (D-39).
REGIME_DIMENSION = "regime"
# The fields of a new record's payload that say how it is written rather than what the
# record says, so they need no source.
UNSOURCED_FIELDS = frozenset(
    {"key", "originalLanguage", "isMachine", "effectiveFromPrecision", "inForceFromPrecision", "inForceToPrecision", "sortOrder"}
)
TERM_KINDS = frozenset({ProposalKind.TERM_CREATE.value, ProposalKind.TERM_UPDATE.value})
# The kinds whose applied record can say an agent confirmed it (`verified_origin` and
# `verified_by_agent`): an obligation version, every library list row and taxonomy term
# (taxonomy 0007), a new instrument, and a new obligation with its first version. Only these
# may an independent agent approve (INV-05, D-62, D-79). A provision and its versions have no
# such column, so `new_provision` and `new_provision_version` wait for a person, as does any
# kind added later without that provenance.
AGENT_CONFIRMABLE_KINDS = (
    OBLIGATION_KINDS
    | VOCABULARY_KINDS
    | TERM_KINDS
    | frozenset({ProposalKind.NEW_INSTRUMENT.value, ProposalKind.NEW_OBLIGATION.value})
)
# The payloads that name a row by key and carry labels: the key must be its own slug and
# the labels real languages, as the vocabulary routes make them.
NAMED_PAYLOADS = (
    ProposalVocabularyCreatePayload,
    ProposalVocabularyRelabelPayload,
    ProposalTermCreatePayload,
    ProposalTermUpdatePayload,
)


@dataclass(frozen=True)
class Proposer:
    """Who proposes: a person (session) or an agent (API key). Exactly one is set. The run
    a proposal was filed under is not part of who proposes: `create()` takes it on its own,
    and checks it, so there is one way to name a run and it is always checked."""

    actor: Actor
    user: Any = None
    api_key_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None

    @property
    def origin(self) -> OriginType:
        return OriginType.USER if self.user is not None else OriginType.AGENT


@dataclass(frozen=True)
class Reviewer:
    """Who decides: a person (session) holding `proposals.review`, or an agent (a platform
    API key) holding the scope `proposals:review` (PRO-S13, D-62, ADR 0054). Exactly one of
    `user` and `api_key_id` is set; `agent_id` names the key's agent definition, which the
    widened `proposal_four_eyes` constraint compares against the proposer's own.

    `Principal.has_permission` and `has_scope` are kind-exclusive, so one decorator cannot
    express "a session or a key"; `apps.proposals.api.require_reviewer` builds this from
    whichever principal called, and every function below decides on it rather than on a
    bare `User`."""

    actor: Actor
    user: Any = None
    api_key_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    api_key_prefix: str = ""


# ---------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------
def validated_kind(kind: str) -> str:
    valid = [member.value for member in ProposalKind]
    if kind not in valid:
        raise ValidationError(
            f"{kind!r} is not a proposal kind. Valid kinds: {', '.join(valid)}.", code="unknown_key"
        )
    return kind


def parsed_payload(kind: str, payload: dict[str, Any]) -> pydantic.BaseModel:
    """The payload as its kind's named schema, or a 422 naming the fields to fix. Run when
    a proposal is made and again when it is applied, so a stored payload that no longer
    parses is a refusal the reviewer can act on, never a 500."""
    try:
        return PAYLOAD_SCHEMAS[kind].model_validate(payload)
    except pydantic.ValidationError as exc:
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        raise ValidationError(f"Fix these payload fields: {fields}.", code="validation_error") from exc


def validated_payload(kind: str, payload: dict[str, Any]) -> pydantic.BaseModel:
    """The payload as its kind's named schema, checked as the vocabulary routes check it. A
    malformed payload is refused when the proposal is made, never when it is approved, so
    the queue holds nothing unappliable."""
    parsed = parsed_payload(kind, payload)
    _validate_target(kind, parsed)
    return parsed


def _validate_target(kind: str, payload: pydantic.BaseModel) -> None:
    """A vocabulary proposal names a library list that can be proposed to; a term proposal
    names a dimension. Tenant lists never enter the queue: their admin writes them. An
    editor or an agent can post a payload without the vocabulary routes, so their checks
    run here too: labels in real languages (stored trimmed), a key that is its own slug,
    and an `extra` that holds only the list's own columns, each a value of its type and
    stored cleaned, so the queue shows what approval writes. That allowlist is also what
    keeps a tone or a colour out of the queue (NFR-S10)."""
    from pydantic.alias_generators import to_camel

    from apps.taxonomy import tenant_lists_logic as lists
    from apps.taxonomy.registry import REGISTRY

    if kind in VOCABULARY_KINDS:
        name = getattr(payload, "list", "")
        entry = REGISTRY.get(name)
        valid = sorted(n for n, e in REGISTRY.items() if e.is_library and e.proposable)
        if entry is None or not entry.is_library or not entry.proposable:
            raise ValidationError(
                f"{name!r} is not a library list a proposal can change. Valid lists: {', '.join(valid)}.",
                code="unknown_key",
            )
        if isinstance(payload, ProposalVocabularyCreatePayload):
            lists.validated_kind(entry, payload.kind)
        if isinstance(payload, ProposalVocabularyMergePayload):
            merge_pair(entry, payload.key, payload.into)
        if isinstance(payload, ProposalVocabularyCreatePayload | ProposalVocabularyRelabelPayload) and payload.extra:
            columns = {to_camel(column) for column in entry.extra_fields} | set(entry.extra_fields)
            unknown = sorted(set(payload.extra) - columns)
            if unknown:
                named = ", ".join(to_camel(column) for column in entry.extra_fields) or "none"
                raise ValidationError(
                    f"{', '.join(unknown)} is not a column of {name!r}. Valid columns: {named}.", code="validation_error"
                )
            payload.extra = lists.extra_payload(entry, payload.extra)
    elif isinstance(payload, ProposalObligationVersionPayload):
        _validate_obligation_payload(payload)
    elif isinstance(payload, ProposalInstrumentPayload):
        validated_instrument(payload)
    elif isinstance(payload, ProposalObligationPayload):
        validated_obligation(payload)
    elif isinstance(payload, ProposalProvisionPayload):
        validated_provision(payload)
    elif isinstance(payload, ProposalProvisionVersionPayload):
        _validate_text_payload(payload)
    else:
        from apps.taxonomy.terms_logic import dimension_by_key, refuse_mirrored

        refuse_mirrored([dimension_by_key(getattr(payload, "dimension", "")).id])
    if isinstance(payload, ProposalVocabularyCreatePayload | ProposalTermCreatePayload):
        payload.labels = lists.validated_labels(payload.labels)
    elif isinstance(payload, ProposalVocabularyRelabelPayload | ProposalTermUpdatePayload) and payload.labels:
        payload.labels = lists.validated_labels(payload.labels)
    if isinstance(payload, NAMED_PAYLOADS) and (not payload.key or lists.key_for(payload.labels, payload.key) != payload.key):
        raise ValidationError(
            f"{payload.key!r} is not a key: use lowercase letters, digits and underscores.", code="validation_error"
        )


def merge_pair(entry: Any, key: str, into: str) -> tuple[Any, Any]:
    """The two rows a merge joins, checked against the list as it is now, when the merge is
    proposed and again when it is applied (VOC-02, INV-08, D-36). A value merges only into
    another active value of the same kind: a row's kind is what the rules read (a level of
    the kind `standard` holds licensed text and one conformance obligation, D-35), so a
    merge across kinds would move records from under one rule to another with no check of
    either. Returns the source and the target."""

    def row(value: str) -> Any:
        found = entry.model._default_manager.filter(key=value).order_by("sort_order", "key").first()
        if found is None:
            raise ValidationError(f"{value!r} is not a row of {entry.name!r}.", code="not_found")
        return found

    source, target = row(key), row(into)
    if source.pk == target.pk:
        raise ValidationError("Choose a different value to merge into.", code="validation_error")
    if not target.active:
        raise ValidationError(f"{into} is retired: restore it before merging into it.", code="invalid_transition")
    if (getattr(source, "kind", None) or "") != (getattr(target, "kind", None) or ""):
        raise ValidationError(
            f"{key} and {into} are values of different kinds, so the records carrying {key} cannot take {into}.",
            code="invalid_transition",
        )
    return source, target


def _validate_obligation_payload(payload: ProposalObligationVersionPayload | ProposalObligationPayload) -> list[Any]:
    """A new obligation version carries the summary in real content languages, one of them
    the original it was written in (INV-05), a legal date with a precision (INV-S10), and
    scope terms that exist, written as `dimension:key` (FP-01), none of them a mirrored
    jurisdiction term: an obligation's market comes from its instrument (FP-S9, FP-S12).
    Returns the scope's terms, resolved."""
    from apps.taxonomy import tenant_lists_logic as lists
    from apps.taxonomy.terms_logic import refuse_mirrored

    payload.summaries = lists.validated_labels(payload.summaries)
    _written_in(payload.original_language, payload.summaries, "summary")
    _validated_precision(payload.effective_from_precision)
    if not payload.terms:
        return []
    # Stored once each, in the order given: the apply replaces the obligation's term
    # links, and a repeated ref would break its uniqueness constraint after approval.
    payload.terms = list(dict.fromkeys(payload.terms))
    terms = terms_of(payload.terms)
    refuse_mirrored(term.dimension_id for term in terms)
    return terms


def _written_in(language: str, texts: dict[str, str], what: str) -> None:
    if language not in texts:
        raise ValidationError(
            f"{language!r} is not one of the languages the {what} is written in: {', '.join(sorted(texts))}.",
            code="validation_error",
        )


def _validated_precision(precision: str) -> None:
    precisions = [member.value for member in DatePrecision]
    if precision not in precisions:
        raise ValidationError(
            f"{precision!r} is not a date precision. Valid values: {', '.join(precisions)}.", code="unknown_key"
        )


def regime_term(ref: str) -> Any:
    """The term `ref` names as an instrument's regime, which must be a term of the regime
    dimension (D-39, INV-S12): the regime is the sector boundary, and a term of another
    dimension would file the instrument outside every bank's regulatory scope, or inside
    all of them. 422 `not_a_regime` otherwise. The one check, run at creation, over a
    reviewer's correction and again at apply."""
    term = terms_of([ref])[0]
    if term.dimension.key != REGIME_DIMENSION:
        raise ValidationError(
            f"{ref!r} is not a regime: an instrument's regime is a term of the {REGIME_DIMENSION!r} dimension, "
            f"written {REGIME_DIMENSION}:<key>. GET /taxonomy/terms lists them.",
            code="not_a_regime",
        )
    return term


def validated_instrument(payload: ProposalInstrumentPayload) -> tuple[InstrumentRefs, Any]:
    """A new instrument (INV-01): a key no record carries, an official name in real content
    languages with the original among them (INV-05), live level, jurisdiction and authority
    rows, a regime from the regime dimension (D-39), and in-force dates with a precision,
    the end after the start. Returns the rows it names and its regime term, resolved, for
    the apply."""
    from apps.taxonomy import tenant_lists_logic as lists

    payload.titles = lists.validated_labels(payload.titles)
    _written_in(payload.original_language, payload.titles, "title")
    _validated_precision(payload.in_force_from_precision)
    _validated_precision(payload.in_force_to_precision)
    if payload.in_force_from and payload.in_force_to and payload.in_force_to <= payload.in_force_from:
        raise ValidationError("An instrument stops being in force after it starts: fix inForceTo.", code="validation_error")
    if payload.eli_uri and not is_link(payload.eli_uri):
        raise ValidationError("eliUri is the instrument's ELI as an https link.", code="validation_error")
    if stable_key_taken(SubjectType.INSTRUMENT.value, payload.key):
        raise ValidationError(f"{payload.key!r} is already an instrument's key.", code="duplicate_key")
    refs = instrument_refs(level=payload.level, jurisdiction=payload.jurisdiction, authority=payload.authority)
    return refs, regime_term(payload.regime)


def validated_obligation(payload: ProposalObligationPayload) -> tuple[Any, list[Any]]:
    """A new obligation (INV-03): a key no record carries, a shared instrument in force, a
    live duty type, a title and a first summary in real content languages written in the
    same original (INV-05), and a scope as a version's is checked. Returns the instrument
    and the scope's terms, resolved, so the apply and the standards check read the same
    rows the creation check did."""
    from apps.taxonomy import tenant_lists_logic as lists

    payload.titles = lists.validated_labels(payload.titles)
    _written_in(payload.original_language, payload.titles, "title")
    terms = _validate_obligation_payload(payload)
    if stable_key_taken(SubjectType.OBLIGATION.value, payload.key):
        raise ValidationError(f"{payload.key!r} is already an obligation's key.", code="duplicate_key")
    instrument = shared_instrument(payload.instrument)
    live_duty_type(payload.duty_type)
    return instrument, terms


def _validate_text_payload(payload: ProposalProvisionPayload | ProposalProvisionVersionPayload) -> None:
    """A provision's verbatim text in real content languages, one of them the original the
    authority published (INV-05), and a legal date with a precision (INV-S10)."""
    from apps.taxonomy import tenant_lists_logic as lists

    payload.texts = lists.validated_labels(payload.texts)
    _written_in(payload.original_language, payload.texts, "text")
    _validated_precision(payload.effective_from_precision)


def validated_provision(payload: ProposalProvisionPayload) -> tuple[Any, Any, Any]:
    """A new provision (INV-02): a key no provision carries, a shared instrument in force, a
    parent that is a provision of that same instrument, a live provision kind, and its text
    checked as a version's is. Returns the instrument, the parent (or None) and the kind,
    resolved, for the apply and the standards check."""
    _validate_text_payload(payload)
    if stable_key_taken(SubjectType.PROVISION.value, payload.key):
        raise ValidationError(f"{payload.key!r} is already a provision's key.", code="duplicate_key")
    instrument = shared_instrument(payload.instrument)
    parent = parent_provision(instrument, payload.parent) if payload.parent else None
    return instrument, parent, live_provision_kind(payload.provision_kind)


def _validate_obligation_target(kind: str, target_type: str, target_id: uuid.UUID | None) -> None:
    """A version proposal says which obligation or provision it versions, and that record
    is here and in force. A proposal nobody could ever apply never enters the queue. A new
    record names no target: it does not exist until the proposal is approved."""
    if kind in NEW_RECORD_KINDS and (target_type or target_id is not None):
        raise ValidationError(
            "A new record names no target: leave targetType and targetId out.", code="validation_error"
        )
    expected = VERSION_TARGETS.get(kind)
    if expected is None:
        return
    if target_type != expected or target_id is None:
        raise ValidationError(
            f"Say which {expected} this version belongs to: targetType {expected!r} and its id.",
            code="validation_error",
        )
    if expected == OBLIGATION_TARGET:
        active_obligation(target_id)
    else:
        active_provision(target_id)


def sourced_fields(payload: pydantic.BaseModel) -> list[str]:
    """The fields of `payload` that a source has to be given for, named as the console
    names them beside the diff: the summary per language, the effective date and the scope
    terms. A vocabulary payload carries a label a person writes, not a sourced fact from an
    authority, so it names none (its chunk 2 rules are unchanged). A new record's are every
    fact it sets, its texts one per language, and never how it is written
    (`UNSOURCED_FIELDS`)."""
    if isinstance(payload, NEW_RECORD_PAYLOADS):
        fields: list[str] = []
        for name, value in payload.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True).items():
            if name in UNSOURCED_FIELDS:
                continue
            fields += [f"{name}.{language}" for language in sorted(value)] if isinstance(value, dict) else [name]
        return fields
    if isinstance(payload, ProposalProvisionVersionPayload):
        fields = [f"texts.{language}" for language in sorted(payload.texts)]
    elif isinstance(payload, ProposalObligationVersionPayload):
        fields = [f"summaries.{language}" for language in sorted(payload.summaries)]
    else:
        return []
    if payload.effective_from is not None:
        fields.append("effectiveFrom")
    if isinstance(payload, ProposalObligationVersionPayload) and payload.terms is not None:
        fields.append("terms")
    return fields


def sourceable_fields(payload: pydantic.BaseModel) -> list[str]:
    """The fields `field_sources` may name. For an obligation version and a new record they
    are exactly the fields that need a source; for a vocabulary payload, whose wording a
    person writes, they are the payload's own fields and none of them is required. A key
    naming anything else is a source for nothing, so it is refused rather than stored."""
    if isinstance(payload, (ProposalObligationVersionPayload, ProposalProvisionVersionPayload, *NEW_RECORD_PAYLOADS)):
        return sourced_fields(payload)
    return sorted(payload.model_dump(by_alias=True, exclude_none=True))


# An https link, the shape the library stores a source in (`Obligation.source_url`).
# https only: a source is fetched and shown as the provenance of a legal fact.
_LINK = URLValidator(schemes=["https"])


def check_field_sources(payload: pydantic.BaseModel, field_sources: dict[str, str]) -> None:
    """Every changed field carries the source its value came from, and nothing else does
    (PRO-01, AC-PRO1): 422 `source_missing` for a field without one, 422
    `validation_error` for a source that is not one.

    The one function for that rule: it runs when the proposal is made and again over a
    reviewer's corrections at approval, so a value nobody can trace to a source never
    reaches the library, whoever last touched it.

    An agent writes these values and a reviewer and the console read them, so each one is
    checked here at the boundary rather than trusted: at most
    `PROPOSAL_SOURCE_MAX_CHARS`, and either an https link or the stable key of a provision
    the library holds. "n/a", "see above" and `javascript:` are none of those.
    """
    missing = [field for field in sourced_fields(payload) if not field_sources.get(field, "").strip()]
    if missing:
        raise ValidationError(
            f"Give the source of every changed field. Missing: {', '.join(missing)}.", code="source_missing"
        )
    allowed = sourceable_fields(payload)
    stray = sorted(set(field_sources) - set(allowed))
    if stray:
        raise ValidationError(
            f"{', '.join(stray)}: this proposal changes no such field. "
            f"Fields a source belongs to: {', '.join(allowed) or 'none'}.",
            code="validation_error",
        )
    long = [field for field, source in field_sources.items() if len(source) > settings.PROPOSAL_SOURCE_MAX_CHARS]
    if long:
        raise ValidationError(
            f"A source is at most {settings.PROPOSAL_SOURCE_MAX_CHARS} characters. Too long: {', '.join(long)}.",
            code="validation_error",
        )
    if isinstance(payload, NEW_RECORD_PAYLOADS):
        # A record that does not exist yet has no provision of its own to cite: its facts
        # come from the authority's page.
        unlinked = sorted(field for field, source in field_sources.items() if not is_link(source))
        if unlinked:
            raise ValidationError(
                f"A new record's sources are https links to the authority's page. Not a link: {', '.join(unlinked)}.",
                code="validation_error",
            )
        return
    refs = {field: source for field, source in field_sources.items() if not is_link(source)}
    unknown = unknown_provision_keys(set(refs.values()))
    unfollowable = sorted(field for field, ref in refs.items() if ref in unknown)
    if unfollowable:
        raise ValidationError(
            "A source is an https link or the stable key of a provision in the library. "
            f"Not a source: {', '.join(unfollowable)}.",
            code="validation_error",
        )


def is_link(value: str) -> bool:
    """Whether `value` is an https link, the one shape a source may take on a new record
    and on every record of a standard (D-35)."""
    try:
        _LINK(value)
    except ValidationError:
        return False
    return True


def _agreed_effective_from(payload: pydantic.BaseModel, effective_from: Any) -> Any:
    """The date the proposal row shows the reviewer, which is the date approval will write
    (INV-04). An obligation version holds the date twice, on the row and in the payload,
    so a row saying one date while the payload carries another is refused rather than
    shown; a row that says nothing takes the payload's. A new obligation's first version
    holds it the same way."""
    if not isinstance(payload, ProposalObligationVersionPayload | ProposalObligationPayload | ProposalProvisionPayload | ProposalProvisionVersionPayload):
        return effective_from
    if effective_from is not None and effective_from != payload.effective_from:
        raise ValidationError(
            "The proposal's effective date is not the date in its payload: give one date.",
            code="validation_error",
        )
    return payload.effective_from


def _texts(value: Any) -> list[str]:
    """Every string in a stored payload, however deep, for the injection screen."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _texts(item)]
    if isinstance(value, list):
        return [text for item in value for text in _texts(item)]
    return []


def payload_dict(payload: pydantic.BaseModel) -> dict[str, Any]:
    """The payload as the JSON column stores it and the API returns it: camelCase keys and
    JSON values, so a legal date is the string the reviewer's screen shows, not a Python
    date the driver would refuse."""
    return payload.model_dump(mode="json", by_alias=True, exclude_none=True)


# ---------------------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------------------
def create(
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    proposer: Proposer,
    idempotency_key: str | None = None,
    target_type: str = "",
    target_id: uuid.UUID | None = None,
    change_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
    model: str = "",
    field_sources: dict[str, str] | None = None,
    source_label: str = "",
    source_url: str = "",
    effective_from: Any = None,
) -> tuple[Proposal, bool]:
    """Create a proposal, or answer the one an earlier identical submission made. Returns
    `(proposal, created)`.

    A key bound to an agent names an open run of its own, so every proposal an agent filed
    traces to the night that produced it (AGT-01); a run anyone else names is checked the
    same way, and so is never one they did not open. That is asked first, before anything
    else is read, so a retry must arrive while its run is still open: once the run is
    closed, a retry answers `run_not_open` as any new filing against that run would. A new
    proposal past the run's budget (`WATCH_RUN_MAX_PROPOSALS`) is refused with
    `run_budget_exhausted`; a retry files nothing new, so it still answers (H41).

    Every text the proposer sent, from a fetched page as often as not, is read by the
    injection screen (AGT-07, H40) and stored exactly as it arrived; what the screen finds
    is kept on the proposal, which the queue shows, and keeps the approval for a person."""
    run = None
    if proposer.agent_id is not None or agent_run_id is not None:
        run = runs.require_open_run_of_key(proposer.api_key_id, agent_run_id)
    validated_kind(kind)
    parsed = validated_payload(kind, payload)
    _validate_obligation_target(kind, target_type, target_id)
    sources = {field: value.strip() for field, value in (field_sources or {}).items()}
    # Before the source check, so a standard's clause pasted as a source answers
    # `licensed_text`, the rule it breaks, rather than a generic refusal (D-35).
    standards.check_payload(kind, target_id, parsed, sources)
    check_field_sources(parsed, sources)
    source_url = source_url.strip()
    if kind in NEW_RECORD_KINDS and not is_link(source_url):
        # The link the new record itself carries as its source (INV-06); a proposal keeps its
        # sources field by field, and the record keeps this one.
        raise ValidationError(
            "Give sourceUrl, the https link to the authority's page the new record is read from.",
            code="source_missing",
        )
    effective_from = _agreed_effective_from(parsed, effective_from)
    stored_payload = payload_dict(parsed)
    title = title.strip()
    if not title:
        raise ValidationError("Give the proposal a title.", code="validation_error")
    # What the database itself is scoped to, not a process-local mirror: this is the tenant
    # whose rows this transaction may write, so it is the tenant the link row can carry.
    tenant_id = tenancy.database_tenant_id()
    if idempotency_key:
        if len(idempotency_key) > IDEMPOTENCY_KEY_MAX_CHARS:
            raise ValidationError(
                f"An Idempotency-Key is at most {IDEMPOTENCY_KEY_MAX_CHARS} characters.", code="validation_error"
            )
        # The key is the proposer's own: another bank or agent sending the same value files
        # its own proposal and is never answered this one (playbook 4.3). The same person in
        # another bank is the same proposer, so there it is a conflict, never a replay.
        own = Q(proposed_by_user=proposer.user) if proposer.user is not None else Q(proposed_by_api_key_id=proposer.api_key_id)
        existing = Proposal.objects.filter(own, idempotency_key=idempotency_key).order_by("created_at", "id").first()
        if existing is not None:
            same_zone = (
                ProposalTenant.objects.filter(proposal=existing, tenant_id=tenant_id).exists()
                if tenant_id is not None
                else not existing.proposed_in_tenant
            )
            submitted = (kind, title, stored_payload, target_type, target_id, sources)
            if not same_zone or (existing.kind, existing.title, existing.payload, existing.target_type, existing.target_id, existing.field_sources) != submitted:
                raise ValidationError(
                    "This Idempotency-Key was already used for a different proposal.",
                    code="idempotency_conflict",
                )
            record(
                action="proposal.replayed",
                actor=proposer.actor,
                subject_type=SUBJECT_TYPE,
                subject_id=existing.id,
                subject_title=existing.title,
                summary="A retried submission answered the proposal it already made.",
                tenant_id=tenant_id,
                after={"idempotencyKey": idempotency_key},
            )
            return existing, False
    # The model's name too: the queue shows it as the proposer.
    risk_flags = screen_all([title, model, source_label, source_url, *_texts(stored_payload), *sources.values()])
    with transaction.atomic():
        if run is not None:
            runs.spend(run, Proposal.objects.filter(agent_run_id=run.id), limit=settings.WATCH_RUN_MAX_PROPOSALS, what=("proposal", "proposals"))
        proposal = Proposal.objects.create(
            kind=kind,
            title=title,
            payload=stored_payload,
            field_sources=sources,
            target_type=target_type,
            target_id=target_id,
            change_id=change_id,
            model=model,
            source_label=source_label,
            source_url=source_url,
            risk_flags=risk_flags,
            effective_from=effective_from,
            origin=proposer.origin.value,
            agent_run_id=agent_run_id,
            proposed_by_user=proposer.user,
            proposed_by_api_key_id=proposer.api_key_id,
            proposed_by_agent_id=proposer.agent_id,
            idempotency_key=idempotency_key or None,
            status=ProposalStatus.OPEN.value,
            proposed_in_tenant=tenant_id is not None,
        )
        if tenant_id is not None:
            ProposalTenant.objects.create(tenant_id=tenant_id, proposal=proposal)
        record(
            action="proposal.created",
            actor=proposer.actor,
            subject_type=SUBJECT_TYPE,
            subject_id=proposal.id,
            subject_title=proposal.title,
            summary=f"Proposed: {proposal.title}",
            tenant_id=tenant_id,
            after={
                "kind": kind,
                "payload": stored_payload,
                "origin": proposal.origin,
                **({"riskFlags": risk_flags} if risk_flags else {}),
            },
        )
    return proposal, True


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def filtered(queryset: Any, *, status: str | None = None, kind: str | None = None, target_list: str | None = None) -> Any:
    """The filters every list of proposals shares, oldest first: comma-separated `status`
    and `kind`, and `target_list`, the vocabulary list a vocabulary proposal changes
    (`payload.list`) or the dimension a term proposal changes (`payload.dimension`). The
    vocabulary screen's "Suggested" tab asks for
    `?status=open&kind=vocabulary_create,term_create&targetList=flag`."""
    queryset = queryset.select_related("proposed_by_user", "reviewed_by").order_by("created_at", "id")
    statuses = _csv(status)
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    kinds = _csv(kind)
    if kinds:
        queryset = queryset.filter(kind__in=kinds)
    if target_list:
        queryset = queryset.filter(Q(payload__list=target_list) | Q(payload__dimension=target_list))
    return queryset


def validated_origin(origin: str | None) -> str | None:
    """`origin` names who filed a proposal, and there are two kinds of proposer. A value
    that is neither is refused rather than answering an empty queue that looks like a fact."""
    if origin is None or origin == "":
        return None
    valid = [member.value for member in OriginType]
    if origin not in valid:
        raise ValidationError(f"{origin!r} is not an origin. Valid values: {', '.join(valid)}.", code="unknown_key")
    return origin


def filed_by(reviewer: Reviewer) -> Q:
    """The proposals `reviewer` filed, which are the ones four eyes will not let them decide
    (AC-PRO2, D-62): a person's own, or for an agent's key the key's own and those of any
    other key of the same agent definition. A proposal made inside a bank is never a platform
    reviewer's. `apps.proposals.reading._is_mine` asks the same question of one row."""
    if reviewer.user is not None:
        mine = Q(proposed_by_user_id=reviewer.user.id)
    else:
        mine = Q(proposed_by_api_key_id=reviewer.api_key_id)
        if reviewer.agent_id is not None:
            mine |= Q(proposed_by_agent_id=reviewer.agent_id)
    return mine & Q(proposed_in_tenant=False)


QUEUE_ORDERS = {"oldest": ("created_at", "id"), "newest": ("-created_at", "-id")}


def queue(
    *,
    reviewer: Reviewer,
    status: str | None = None,
    kind: str | None = None,
    target_list: str | None = None,
    origin: str | None = None,
    not_mine: bool = False,
    order: str | None = None,
) -> Any:
    """The console review queue, read by a person or by an agent's key alike (PRO-S13, D-62),
    with the people and agents each row names joined in, so a page costs the same whatever
    it holds. `origin` keeps an agent's proposals or a person's; `not_mine` drops the ones
    `reviewer` filed (`filed_by`). `order` is `oldest` (the default, `filtered`'s own order)
    or `newest`, for the decided tabs; the id breaks a tie either way. It orders this answer
    only, so a bank's own list stays oldest first."""
    order = order or "oldest"
    if order not in QUEUE_ORDERS:
        raise ValidationError(f"{order!r} is not an order. Valid values: {', '.join(QUEUE_ORDERS)}.", code="unknown_key")
    queryset = filtered(Proposal.objects.all(), status=status, kind=kind, target_list=target_list)
    queryset = queryset.select_related("proposed_by_agent", "reviewed_by_agent", "corrected_by")
    origin = validated_origin(origin)
    if origin is not None:
        queryset = queryset.filter(origin=origin)
    if not_mine:
        queryset = queryset.exclude(filed_by(reviewer))
    return queryset.order_by(*QUEUE_ORDERS[order])


def by_id(proposal_id: uuid.UUID) -> Proposal:
    proposal = (
        Proposal.objects.select_related("proposed_by_user", "reviewed_by").filter(pk=proposal_id).first()  # ordering: pk lookup, at most one row
    )
    if proposal is None:
        raise ValidationError("That proposal is not here.", code="not_found")
    return proposal


def _actor_ref(user: Any) -> ProposalActorRef | None:
    """A platform person named on a proposal, by id and name."""
    return None if user is None else ProposalActorRef(id=user.id, name=user.name)


def _agent_ref(agent: Any) -> ProposalAgentRef | None:
    """A platform agent named on a proposal, by its definition key and the version the
    platform runs now. The version it ran when it decided is the decision's audit row's to
    keep; nothing on the proposal holds it, so nothing here claims it."""
    if agent is None:
        return None
    return ProposalAgentRef(key=agent.key, version=agent.current_version)


def row(proposal: Proposal) -> ProposalRow:
    """One proposal as every answer carrying one returns it. A proposal made inside a bank
    names no proposer (PRO-03): the console is told `from_organisation` and nothing more, so
    a bank member's name and id reach no platform reader, whichever route answers.

    Who decided is a person or an agent, never both: a `Reviewer` carries exactly one of a
    user and a key. A correction is only ever made on the way to approving it (`approve`),
    so its author is the approver: `corrected_by` names a person, and a correction with no
    person on it was the approving agent's, which is named from `reviewed_by_agent` rather
    than a column of its own."""
    agent_corrected = proposal.corrected_payload is not None and proposal.corrected_by_id is None
    return ProposalRow(
        id=proposal.id,
        kind=proposal.kind,
        status=proposal.status,
        title=proposal.title,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        change_id=proposal.change_id,
        payload=proposal.payload,
        field_sources=proposal.field_sources,
        source_label=proposal.source_label,
        source_url=proposal.source_url,
        risk_flags=proposal.risk_flags,
        effective_from=proposal.effective_from,
        origin=proposal.origin,
        agent_run_id=proposal.agent_run_id,
        model=proposal.model,
        proposed_by=None if proposal.proposed_in_tenant else _actor_ref(proposal.proposed_by_user),
        proposed_by_agent=None if proposal.proposed_in_tenant else _agent_ref(proposal.proposed_by_agent),
        from_organisation=proposal.proposed_in_tenant,
        reviewed_by=_actor_ref(proposal.reviewed_by),
        reviewed_by_agent=_agent_ref(proposal.reviewed_by_agent),
        corrected_by=_actor_ref(proposal.corrected_by),
        corrected_by_agent=_agent_ref(proposal.reviewed_by_agent) if agent_corrected else None,
        reviewed_at=proposal.reviewed_at,
        rejection_code=proposal.rejection_code,
        review_note=proposal.review_note,
        applied_at=proposal.applied_at,
        created_at=proposal.created_at,
    )


def proposer_row(proposal: Proposal) -> ProposalRow:
    """The row a proposer's own create call answers, a retry after the decision included. A
    bank's proposer is told how far its request got and never which platform person or
    agent decided or corrected it, as its own list never is (`TenantProposalRow`, PRO-03)."""
    answer = row(proposal)
    if not proposal.proposed_in_tenant:
        return answer
    return answer.model_copy(update={"reviewed_by": None, "reviewed_by_agent": None, "corrected_by": None, "corrected_by_agent": None})


# ---------------------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------------------
def _decidable(proposal: Proposal, reviewer: Reviewer) -> None:
    """Lock the row, then check it under the lock (PRO-02). Two decisions on one proposal
    queue on the lock and the second reads what the first committed: 409
    `invalid_transition`, never a stale "open" that lets a rejection land on top of an
    applied approval or a proposal apply twice (apps/proposals/tests_decide.py).

    Four eyes, checked here so the API answers before the database does (AC-PRO2); the
    widened `proposal_four_eyes` constraint is the same rule and answers on its own if this
    is ever bypassed. A repeated user, a repeated key or a repeated agent definition is the
    same principal twice by construction, whichever pair of columns it shows up on; a
    reviewing key that names no agent is refused too, so an unbound platform key can never
    stand in for independence (PRO-S13, PRO-S14, D-62, ADR 0054). The API's gate refuses
    that key first, with `agent_not_bound`; this is the same rule for any other caller."""
    proposal.refresh_from_db(from_queryset=Proposal.objects.select_for_update())
    if proposal.status != ProposalStatus.OPEN.value:
        raise ValidationError("This proposal has already been decided.", code="invalid_transition")
    if reviewer.api_key_id is not None and reviewer.agent_id is None:
        raise ValidationError(
            "A reviewing key must be bound to an agent definition.",
            code="four_eyes_violation",
        )
    same_user = reviewer.user is not None and proposal.proposed_by_user_id == reviewer.user.id
    same_key = reviewer.api_key_id is not None and proposal.proposed_by_api_key_id == reviewer.api_key_id
    same_agent = reviewer.agent_id is not None and proposal.proposed_by_agent_id == reviewer.agent_id
    if same_user or same_key or same_agent:
        raise ValidationError(
            "A proposal is decided by someone other than the person, key or agent who made it.",
            code="four_eyes_violation",
        )


def as_reviewer(reviewer: "Reviewer | Any", actor: Actor) -> Reviewer:
    """Every caller before T25 passed the deciding person as a bare `User`; the queue and
    the tests built against that contract still do. Normalize it into a `Reviewer` with no
    key and no agent, rather than pushing the change out to every existing call site."""
    if isinstance(reviewer, Reviewer):
        return reviewer
    return Reviewer(actor=actor, user=reviewer)


def _reviewer_facts(reviewer: Reviewer, run: AgentRun | None) -> dict[str, Any]:
    """What a decision's audit row names beside the actor label (AUD-01, AUD-02, AUD-S9):
    the key an agent used, by its public prefix and never its internal id alone, and the
    run the decision was made in, which its logged model call names too (D-80). Empty for a
    person, whose audit row carries no key and no run at all. The key is named whether or not
    a run came with it, so no decision by a key ever loses the prefix AUD-S9 reads."""
    if reviewer.api_key_id is None:
        return {}
    facts: dict[str, Any] = {"reviewingApiKeyPrefix": reviewer.api_key_prefix}
    if run is not None:
        facts["agentRunId"] = str(run.id)
    return facts


def _decision_run(reviewer: Reviewer, decision: AgentDecision | None, agent_run_id: uuid.UUID | None) -> AgentRun | None:
    """The open run an agent's decision is made in, once the decision says what model call
    is behind it (AUD-02, AGT-01, D-80); None for a person, who sends neither.

    An agent's approval or rejection is a model call, and every model call is logged, so a
    key's decision without its `AgentDecision` is refused rather than recorded as one nobody
    can attribute or check. The run must be an open run of the deciding key itself
    (`runs.require_open_run_of_key`): none, or a closed one, is `run_not_open`, and another
    key's, another agent's included, is `not_found` as a run that never existed is, so no
    agent counts its decisions in somebody else's run. A person's decision is not a model
    call, so a body that says it was one is refused rather than logged as a machine's."""
    if reviewer.user is not None:
        if decision is not None or agent_run_id is not None:
            raise ValidationError(
                "A person's decision names no model call and no run: leave out decision and agentRunId.",
                code="validation_error",
            )
        return None
    if decision is None:
        raise ValidationError(
            "Send the model call behind this decision in decision: the model, its version, the output and at least one citation.",
            code="validation_error",
        )
    return runs.require_open_run_of_key(reviewer.api_key_id, agent_run_id)


def _log_decision(proposal: Proposal, decision: AgentDecision | None, run: AgentRun | None) -> None:
    """The model call behind an agent's decision, as one `agent_review` row of the AI output
    log in the decision's own transaction: the agent's report of itself, about this proposal,
    counted in its run (AUD-02, D-80). Nothing for a person's decision."""
    if decision is None or run is None:
        return
    ai_log.log_generation(
        purpose=AiPurpose.AGENT_REVIEW,
        model=decision.model,
        model_version=decision.model_version,
        output=decision.output,
        citations=decision.citations,
        agent_run_id=run.id,
        subject_type=SUBJECT_TYPE,
        subject_id=proposal.id,
        prompt_template=decision.prompt_template or "",
        prompt_hash=decision.prompt_hash or "",
        metadata_reported_by_agent=True,
    )


def corrected(proposal: Proposal, reviewer: Reviewer, overrides: dict[str, Any]) -> dict[str, Any]:
    """The payload as the reviewer corrected it, checked as firmly as the one that arrived
    (PRO-02, AC-PRO1).

    Corrections merge field by field over what was proposed, so a reviewer who rewrites the
    wording keeps the date and the scope that came with it. The merged result goes through
    the kind's own schema and through the same source check the proposal passed when it was
    made: a correction that introduces a field the proposal never sourced is 422
    `source_missing`, because the rule is that no value reaches the library without a source
    a reader can follow, whoever typed it last.

    Only a version of an obligation or a provision, or a new record, may be corrected
    (`CORRECTABLE_KINDS`). A vocabulary row's labels are wording a person writes rather than
    a fact from an authority, so there is nothing to correct against a source, and a
    reviewer who disagrees rejects with a reason instead.

    An agent's correction may reword a summary but not move `originalLanguage`: the
    original is the one text stored without the machine label, so moving it would store a
    machine translation as unlabelled and label the source-language text machine-made
    (INV-05). It is compared as parsed, whichever spelling of the field arrived.
    """
    if proposal.kind not in CORRECTABLE_KINDS:
        raise ValidationError(
            "Corrections belong to a version or a new record. Reject this one with a reason instead.",
            code="validation_error",
        )
    merged = {**proposal.payload, **overrides}
    parsed = validated_payload(proposal.kind, merged)
    standards.check_payload(proposal.kind, proposal.target_id, parsed, proposal.field_sources)
    check_field_sources(parsed, proposal.field_sources)
    stored = payload_dict(parsed)
    if reviewer.user is None and stored.get("originalLanguage") != proposal.payload.get("originalLanguage"):
        raise ValidationError(
            "An agent cannot change which language a summary was written in. Reject it with a reason instead.",
            code="validation_error",
        )
    proposal.corrected_payload = stored
    proposal.corrected_by = reviewer.user
    proposal.corrected_at = timezone.now()
    # The row's own date follows the correction, because a queue row that showed one date
    # while the version carried another would be a proposal nobody could read straight
    # (the same rule `_agreed_effective_from()` holds the proposer to).
    proposal.effective_from = getattr(parsed, "effective_from", proposal.effective_from)
    return proposal.corrected_payload


def approve(
    *,
    proposal: Proposal,
    reviewer: "Reviewer | Any",
    actor: Actor,
    note: str,
    payload_overrides: dict[str, Any] | None = None,
    step_up_assertion_id: uuid.UUID | None,
    decision: AgentDecision | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> Proposal:
    """Apply the payload and approve, in one transaction of its own (PRO-02): the library
    row, its audit row, the proposal's own audit row and an agent's logged model call commit
    together or not at all, whether or not a request opened a transaction around the call. A
    worker or a shell caller that fails part way writes nothing, so its retry writes the
    version once (apps/proposals/tests_decide.py, DecidingOutsideARequest).

    A reviewer may correct the payload on the way through (`payload_overrides`). What they
    approved is stored beside what was proposed, as their own correction, so the queue and
    the audit trail keep both. `step_up_assertion_id` is null for an agent's decision: a key
    holds no passkey assertion (PRO-S13, D-62, ADR 0054).

    An agent's approval carries the model call behind it (`decision`) and the open run of
    its own key it was made in (`agent_run_id`), checked before anything else is read; the
    call is logged as one `agent_review` row and the audit row names the run (`_decision_run`,
    AUD-02, D-80). A person sends neither.

    An agent approves only a kind whose record can say an agent confirmed it
    (`AGENT_CONFIRMABLE_KINDS`, INV-05, D-79): an obligation version, a new instrument, a new
    obligation, and since Alex lifted D-79's interim refusal on 2026-09-23 every vocabulary
    and term kind, whose rows `apply` stamps with the confirming agent and whose every label
    it writes machine-made. A kind without that provenance, today a new provision or a
    provision's new text, is refused to an agent with 409 `person_review_required` and waits
    for a person. Rejecting writes no library row, so an agent may reject any kind.

    `reviewer` is a `Reviewer` from the API's dual-principal gate, or a bare `User` from an
    older caller; `as_reviewer` normalizes either into the same shape below.
    """
    from apps.proposals import apply

    reviewer = as_reviewer(reviewer, actor)
    with transaction.atomic():
        run = _decision_run(reviewer, decision, agent_run_id)
        _decidable(proposal, reviewer)
        if reviewer.user is None and proposal.kind not in AGENT_CONFIRMABLE_KINDS:
            raise ValidationError(
                "An agent cannot approve this kind of change: a person has to approve it.",
                code="person_review_required",
            )
        if reviewer.user is None and (proposal.risk_flags or screen_all(_texts(payload_overrides))):
            raise ValidationError(
                "This proposal carries text the injection screen flagged, so an agent cannot "
                "approve it: a person reads the flag and decides.",
                code="risk_flagged",
            )
        decided = ["status", "reviewed_by", "reviewed_by_api_key", "reviewed_by_agent", "reviewed_at", "applied_at", "review_note"]
        if payload_overrides:
            corrected(proposal, reviewer, payload_overrides)
            decided += ["corrected_payload", "corrected_by", "corrected_at", "effective_from"]
        apply.apply(proposal, actor=actor, reviewer=reviewer, step_up=step_up_assertion_id)
        now = timezone.now()
        proposal.status = ProposalStatus.APPROVED.value
        proposal.reviewed_by = reviewer.user
        proposal.reviewed_by_api_key_id = reviewer.api_key_id
        proposal.reviewed_by_agent_id = reviewer.agent_id
        proposal.reviewed_at = now
        proposal.applied_at = now
        proposal.review_note = note.strip()
        proposal.save(update_fields=decided)
        _log_decision(proposal, decision, run)
        record(
            action="proposal.approved",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=proposal.id,
            subject_title=proposal.title,
            summary=f"Approved: {proposal.title}",
            tenant_id=None,
            before={"status": ProposalStatus.OPEN.value},
            after={
                "status": proposal.status,
                "note": proposal.review_note,
                "corrected": proposal.corrected_payload is not None,
                **_reviewer_facts(reviewer, run),
            },
            step_up_assertion_id=step_up_assertion_id,
        )
    return proposal


def reject(
    *,
    proposal: Proposal,
    reviewer: "Reviewer | Any",
    actor: Actor,
    rejection_code: str,
    note: str,
    decision: AgentDecision | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> Proposal:
    """A rejection needs a reason (PRO-01): a code the proposer's screen can branch on and a
    sentence they can read. The code is a live row of the `rejection_reason` library list, an
    admin's to extend and retire, so a code from an older screen or a retired row is refused
    rather than stored as a reason nobody can look up. The outbox event is what tells them.

    It runs in one transaction of its own, as `approve` does, and an agent's rejection carries
    the model call behind it and the open run it was made in, logged and named the same way
    (`_decision_run`, AUD-02, D-80).

    `reviewer` is a `Reviewer` from the API's dual-principal gate, or a bare `User` from an
    older caller; `as_reviewer` normalizes either into the same shape below."""
    from apps.taxonomy.registry import REGISTRY

    reviewer = as_reviewer(reviewer, actor)
    with transaction.atomic():
        run = _decision_run(reviewer, decision, agent_run_id)
        code = rejection_code.strip()
        text = note.strip()
        if not code or not text:
            raise ValidationError(
                "Say why: choose a reason and write a note the proposer will read.", code="reason_required"
            )
        # Through the registry rather than by naming the model: this module writes (it creates
        # proposals), and the library fence's static guard fails closed on any module that both
        # writes and names a concrete LibraryModel, whether or not the two are related
        # (apps/shared/tests_library_fence.py). The reason list is a library vocabulary and this
        # is a read of it.
        reasons = REGISTRY[REJECTION_REASON_LIST].model
        known = reasons.objects.filter(
            key=code,
            active=True,
        ).exists()
        if not known:
            raise ValidationError(
                f"{code!r} is not a reason the rejection reason list offers. Choose one of its live rows.",
                code="reason_required",
            )
        _decidable(proposal, reviewer)
        proposal.status = ProposalStatus.REJECTED.value
        proposal.reviewed_by = reviewer.user
        proposal.reviewed_by_api_key_id = reviewer.api_key_id
        proposal.reviewed_by_agent_id = reviewer.agent_id
        proposal.reviewed_at = timezone.now()
        proposal.rejection_code = code
        proposal.review_note = text
        proposal.save(
            update_fields=["status", "reviewed_by", "reviewed_by_api_key", "reviewed_by_agent", "reviewed_at", "rejection_code", "review_note"]
        )
        _log_decision(proposal, decision, run)
        record(
            action="proposal.rejected",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=proposal.id,
            subject_title=proposal.title,
            summary=f"Rejected: {proposal.title}",
            tenant_id=None,
            before={"status": ProposalStatus.OPEN.value},
            after={"status": proposal.status, "rejectionCode": code, "note": text, **_reviewer_facts(reviewer, run)},
            topic="proposal.rejected",
        )
    return proposal
