"""Applicability per obligation, per legal entity and per unit (REG-01, D-75, D-42, AC-REG1).

One person holding `applicability.approve` sets the answer after a confirmation dialog: no
request, no second approver, no step-up. The value and the reason are stored at once with the
decision time and the person, and one `record()` per row names the value before and after and
the reason. Its subject is the register entry; an entity's answer names the entity in its
title and its `orgUnitId`. Many answers are one call, all stored or none, capped by `REGISTER_BULK_MAX`.

"Applies" and "we comply" are separate facts (CLAUDE.md section 5): nothing here reads or
writes a compliance status or a gap. A read writes nothing: the register entry is created by
`ensure_register_entry()` and an entity's scope row here, both only in the transaction of the
write that needs them.

An obligation spans the bank's active legal entities whose entity term it carries, or all of
them when it carries no term in that entity's dimension, as a standard's conformance
obligation carries none (D-42). Only the entity's own dimension is compared, so an opt-in
term such as the standard's never narrows the span.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection
from typing import NamedTuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.library.reading import RecordHeading, obligation_headings, obligation_scopes
from apps.register import duties
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.register.schemas import (
    RegisterApplicability,
    RegisterApplicabilityBody,
    RegisterApplicabilityMany,
    RegisterApplicabilityManyBody,
    RegisterPersonRef,
)
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.models import ComplianceStatus
from apps.tenants.models import OrgUnit, OrgUnitKind

APPLICABILITY_SET = "register.applicability_set"

# The published words (schemas.Applicability) and the stored kind (models.Applicability).
KIND_OF: dict[str, str] = {
    "applies": Applicability.APPLIES.value,
    "not_applicable": Applicability.DOES_NOT_APPLY.value,
    "under_assessment": Applicability.NOT_ASSESSED.value,
}
WORD_OF: dict[str, str] = {kind: word for word, kind in KIND_OF.items()}


class _Answer(NamedTuple):
    obligation_id: uuid.UUID
    org_unit_id: uuid.UUID | None
    unit_id: uuid.UUID | None
    applicability: str
    reason: str


def set_applicability(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    obligation_id: uuid.UUID,
    body: RegisterApplicabilityBody,
    expected_version: int | None,
) -> RegisterApplicability:
    """`PUT /obligations/{obligationId}/applicability`: one confirmed answer, checked against
    `If-Match` (0 for a row nobody has written yet)."""
    answer = _Answer(obligation_id, body.org_unit_id, body.unit_id, body.applicability, body.reason)
    return _store(tenant=tenant, actor=actor, order=order, answers=[answer], expected_version=expected_version)[0]


def set_applicability_many(
    *, tenant: Tenant, actor: Actor, order: list[str], body: RegisterApplicabilityManyBody
) -> RegisterApplicabilityMany:
    """`POST /applicability`: many confirmed answers, all stored or none, at most
    `REGISTER_BULK_MAX`, each target once."""
    cap = settings.REGISTER_BULK_MAX
    if len(body.rows) > cap:
        raise ValidationError(f"Send at most {cap} answers in one call.", code="validation_error")
    answers = [_Answer(row.obligation_id, row.org_unit_id, row.unit_id, row.applicability, row.reason) for row in body.rows]
    if len({answer[:3] for answer in answers}) < len(answers):
        raise ValidationError("Each obligation, legal entity or unit may be answered once in a call.", code="validation_error")
    return RegisterApplicabilityMany(items=_store(tenant=tenant, actor=actor, order=order, answers=answers, expected_version=None))


def entities_spanned(obligation_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, list[OrgUnit]]:
    """The legal entities each obligation spans, in the organisation's order: a read that
    writes nothing (D-42). Six queries however many obligations."""
    entities = list(
        OrgUnit.objects.filter(kind=OrgUnitKind.LEGAL_ENTITY.value, active=True).select_related("entity_term__dimension")
    )
    carried = {
        obligation_id: {dimension: {term.id for term in terms} for dimension, terms in scope.items()}
        for obligation_id, scope in obligation_scopes(obligation_ids).items()
    }
    return {
        obligation_id: [entity for entity in entities if _spans(carried.get(obligation_id, {}), entity)]
        for obligation_id in obligation_ids
    }


def _spans(carried: dict[str, set[uuid.UUID]], entity: OrgUnit) -> bool:
    term = entity.entity_term
    if term is None:
        return True
    ids = carried.get(term.dimension.key)
    return not ids or term.id in ids


def _units(answers: list[_Answer]) -> None:
    """A unit's answer resolves once the Statement of Applicability's units exist (register
    0003, `c8-reg-units`); until then a unit row stores nothing."""
    if any(answer.unit_id is not None for answer in answers):
        raise ProblemError(status=501, code="not_built", detail="Setting a unit's applicability is not built yet.")


def _store(
    *, tenant: Tenant, actor: Actor, order: list[str], answers: list[_Answer], expected_version: int | None
) -> list[RegisterApplicability]:
    """Check every answer, then lock, then write: a refused row leaves nothing behind."""
    person = actor.id
    if person is None:
        raise ProblemError(status=403, code="permission_denied", detail="A person must do this.")
    _units(answers)
    obligation_ids = {answer.obligation_id for answer in answers}
    headings = obligation_headings(obligation_ids, order)
    if obligation_ids - headings.keys():
        raise ValidationError("That obligation is not here.", code="not_found")
    entity_ids = {answer.org_unit_id for answer in answers if answer.org_unit_id is not None}
    names: dict[uuid.UUID, str] = {}
    if entity_ids:
        spanned = entities_spanned({answer.obligation_id for answer in answers if answer.org_unit_id is not None})
        for answer in answers:
            if answer.org_unit_id is None:
                continue
            entity = next((row for row in spanned[answer.obligation_id] if row.id == answer.org_unit_id), None)
            if entity is None:
                raise ValidationError("That legal entity is not one this obligation spans.", code="not_found")
            names[entity.id] = entity.name

    entries = _locked_entries(obligation_ids)
    scopes = _locked_scopes([entry.id for entry in entries.values()], entity_ids)
    if expected_version is not None:
        _check_version(answers[0], entries, scopes, expected_version)

    missing = obligation_ids - entries.keys()
    for obligation_id in sorted(missing):
        ensure_register_entry(tenant_id=tenant.id, obligation_id=obligation_id, actor=actor)
    if missing:
        entries |= _locked_entries(missing)

    decided_at = timezone.now()
    default_status: ComplianceStatus | None = None
    stored = []
    applied: list[tuple[TenantObligation, TenantObligationScope | None]] = []
    for answer in answers:
        entry = entries[answer.obligation_id]
        row: TenantObligation | TenantObligationScope = entry
        scope = None
        if answer.org_unit_id is not None:
            scope = scopes.get((entry.id, answer.org_unit_id))
            if scope is None:
                default_status = default_status or ComplianceStatus.objects.get(is_default=True, active=True)
                scope = _new_scope(tenant, entry, answer.org_unit_id, default_status)
            row = scope
        stored.append(_write(tenant, person, actor, entry, row, answer, headings[answer.obligation_id], names, decided_at))
        if answer.applicability == "applies":
            applied.append((entry, scope))
    if applied:
        # REG-07 (c8-duty-occurrences): an answer "applies" writes the first occurrence of
        # each recurring duty that has none, in this transaction.
        duties.schedule_first(tenant=tenant, actor=actor, targets=applied, at=decided_at)
    return stored


def _check_version(
    answer: _Answer,
    entries: dict[uuid.UUID, TenantObligation],
    scopes: dict[tuple[uuid.UUID | None, uuid.UUID], TenantObligationScope],
    expected_version: int,
) -> None:
    """`If-Match` against the row the answer lands on, read under its lock; 0 for a row
    nobody has written yet."""
    entry = entries.get(answer.obligation_id)
    row: TenantObligation | TenantObligationScope | None = entry
    if answer.org_unit_id is not None:
        row = scopes.get((entry.id if entry else None, answer.org_unit_id))
    if expected_version != (row.version if row is not None else 0):
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")


def _locked_entries(obligation_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, TenantObligation]:
    rows = TenantObligation.objects.select_for_update().filter(obligation_id__in=obligation_ids)
    return {row.obligation_id: row for row in rows}


def _locked_scopes(
    entry_ids: list[uuid.UUID], entity_ids: set[uuid.UUID]
) -> dict[tuple[uuid.UUID | None, uuid.UUID], TenantObligationScope]:
    if not entry_ids or not entity_ids:
        return {}
    rows = TenantObligationScope.objects.select_for_update().filter(
        tenant_obligation_id__in=entry_ids, org_unit_id__in=entity_ids, product__isnull=True
    )
    return {(row.tenant_obligation_id, row.org_unit_id): row for row in rows}


def _new_scope(tenant: Tenant, entry: TenantObligation, org_unit_id: uuid.UUID, status: ComplianceStatus) -> TenantObligationScope:
    """The entity's scope row, created in this write's transaction and audited by it. Two
    first answers at once meet on the unique key, and the second answers over the first."""
    try:
        with transaction.atomic():
            return TenantObligationScope.objects.create(
                tenant_id=tenant.id, tenant_obligation=entry, org_unit_id=org_unit_id, compliance_status=status, version=0
            )
    except IntegrityError:
        return TenantObligationScope.objects.select_for_update().get(
            tenant_obligation=entry, org_unit_id=org_unit_id, product__isnull=True
        )


def _write(
    tenant: Tenant,
    person: uuid.UUID,
    actor: Actor,
    entry: TenantObligation,
    row: TenantObligation | TenantObligationScope,
    answer: _Answer,
    heading: RecordHeading,
    names: dict[uuid.UUID, str],
    decided_at: datetime.datetime,
) -> RegisterApplicability:
    before = {"applicability": WORD_OF[row.applicability], "reason": row.applicability_reason or None}
    row.applicability = KIND_OF[answer.applicability]
    row.applicability_reason = answer.reason
    row.applicability_decided_at = decided_at
    row.applicability_decided_by_id = person
    row.version += 1
    row.save(
        update_fields=[
            "applicability",
            "applicability_reason",
            "applicability_decided_at",
            "applicability_decided_by",
            "version",
            "updated_at",
        ]
    )
    title = f"{heading.instrument_short_name}, {heading.reference_label}"
    if answer.org_unit_id is not None:
        title = f"{title}, {names[answer.org_unit_id]}"
    record(
        action=APPLICABILITY_SET,
        actor=actor,
        subject_type="tenant_obligation",
        subject_id=entry.id,
        subject_title=title,
        summary=f"Applicability set to {answer.applicability}.",
        tenant_id=tenant.id,
        before=before,
        after={
            "obligationId": str(answer.obligation_id),
            "orgUnitId": None if answer.org_unit_id is None else str(answer.org_unit_id),
            "applicability": answer.applicability,
            "reason": answer.reason,
        },
    )
    return RegisterApplicability(
        obligation_id=answer.obligation_id,
        org_unit_id=answer.org_unit_id,
        unit_id=None,
        applicability=answer.applicability,  # type: ignore[arg-type]
        reason=answer.reason,
        decided_at=decided_at,
        decided_by=RegisterPersonRef(id=person, name=actor.label),
        version=row.version,
    )

