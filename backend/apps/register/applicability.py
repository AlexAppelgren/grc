"""Applicability per obligation, per legal entity and per unit (REG-01, D-75, D-42, AC-REG1).

One person holding `applicability.approve` sets the answer after a confirmation dialog: no
request, no second approver, no step-up. The value and the reason are stored at once with the
decision time and the person, and one `record()` per row names the value before and after and
the reason. Its subject is the register entry; an entity's answer names the entity in its
title and its `orgUnitId`. A unit's answer is stored on the unit and its subject is the unit,
so the unit's history is its own events (REG-08, D-41); the unit must be live under the
obligation, 404 otherwise, and its entity must still follow the standard (422
`scope_not_applicable`). Many answers are one call, all stored or none, capped by
`REGISTER_BULK_MAX`.

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
from collections.abc import Collection, Iterable
from typing import NamedTuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.library.reading import RecordHeading, obligation_headings, obligation_scopes
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, SoaUnit, TenantObligation, TenantObligationScope
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
UNIT_SUBJECT = "soa_unit"

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


def _locked_units(answers: list[_Answer]) -> dict[uuid.UUID, SoaUnit]:
    """The live units the answers name, locked and read in one query: a unit the bank does
    not have, a removed one or one under another obligation is 404, and one whose entity no
    longer follows the standard 422 `scope_not_applicable`."""
    wanted = {answer.unit_id: answer.obligation_id for answer in answers if answer.unit_id is not None}
    if not wanted:
        return {}
    units = {
        unit.id: unit
        for unit in SoaUnit.objects.select_for_update(of=("self",))
        .select_related("scope__tenant_obligation", "scope__org_unit")
        .filter(pk__in=wanted, removed_at__isnull=True)
    }
    for unit_id, obligation_id in wanted.items():
        unit = units.get(unit_id)
        if unit is None or unit.scope.tenant_obligation.obligation_id != obligation_id:
            raise ValidationError("That unit is not here.", code="not_found")
        if unit.scope.applicability != Applicability.APPLIES.value:
            raise ValidationError(
                "This unit's legal entity does not follow the standard. Set its conformance to applies first.",
                code="scope_not_applicable",
            )
    return units


def _store(
    *, tenant: Tenant, actor: Actor, order: list[str], answers: list[_Answer], expected_version: int | None
) -> list[RegisterApplicability]:
    """Check every answer, then lock, then write: a refused row leaves nothing behind."""
    person = actor.id
    if person is None:
        raise ProblemError(status=403, code="permission_denied", detail="A person must do this.")
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
    units = _locked_units(answers)
    if expected_version is not None:
        _check_version(answers[0], entries, scopes, units, expected_version)

    missing = obligation_ids - entries.keys()
    for obligation_id in sorted(missing):
        ensure_register_entry(tenant_id=tenant.id, obligation_id=obligation_id, actor=actor)
    if missing:
        entries |= _locked_entries(missing)

    decided_at = timezone.now()
    default_status: ComplianceStatus | None = None
    stored = []
    for answer in answers:
        entry = entries[answer.obligation_id]
        row: TenantObligation | TenantObligationScope | SoaUnit = entry
        if answer.unit_id is not None:
            row = units[answer.unit_id]
        elif answer.org_unit_id is not None:
            scope = scopes.get((entry.id, answer.org_unit_id))
            if scope is None:
                default_status = default_status or ComplianceStatus.objects.get(is_default=True, active=True)
                scope = _new_scope(tenant, entry, answer.org_unit_id, default_status)
            row = scope
        stored.append(_write(tenant, person, actor, entry, row, answer, headings[answer.obligation_id], names, decided_at))
    _write_units(units.values(), person, decided_at)
    return stored


def _write_units(units: Iterable[SoaUnit], person: uuid.UUID, decided_at: datetime.datetime) -> None:
    """One UPDATE per distinct answer and reason rather than one per unit: a pasted Statement
    of Applicability answers up to `REGISTER_BULK_MAX` units in one call, inside the API
    budget (AC-REG1). Each unit was read under its lock, so its version moves by one."""
    same: dict[tuple[str, str], list[uuid.UUID]] = {}
    for unit in units:
        same.setdefault((unit.applicability, unit.applicability_reason), []).append(unit.id)
    for (value, reason), ids in same.items():
        SoaUnit.objects.filter(pk__in=ids).update(
            applicability=value,
            applicability_reason=reason,
            applicability_decided_at=decided_at,
            applicability_decided_by_id=person,
            version=F("version") + 1,
        )


def _check_version(
    answer: _Answer,
    entries: dict[uuid.UUID, TenantObligation],
    scopes: dict[tuple[uuid.UUID | None, uuid.UUID], TenantObligationScope],
    units: dict[uuid.UUID, SoaUnit],
    expected_version: int,
) -> None:
    """`If-Match` against the row the answer lands on, read under its lock; 0 for a row
    nobody has written yet."""
    entry = entries.get(answer.obligation_id)
    row: TenantObligation | TenantObligationScope | SoaUnit | None = entry
    if answer.unit_id is not None:
        row = units[answer.unit_id]
    elif answer.org_unit_id is not None:
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
    row: TenantObligation | TenantObligationScope | SoaUnit,
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
    if not isinstance(row, SoaUnit):  # the units are written together by _write_units()
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
    summary = f"Applicability set to {answer.applicability}."
    after = {
        "obligationId": str(answer.obligation_id),
        "orgUnitId": None if answer.org_unit_id is None else str(answer.org_unit_id),
        "applicability": answer.applicability,
        "reason": answer.reason,
    }
    if isinstance(row, SoaUnit):
        # The unit is the subject, so its history is its own events (REG-S15).
        record(
            action=APPLICABILITY_SET,
            actor=actor,
            subject_type=UNIT_SUBJECT,
            subject_id=row.id,
            subject_title=f"{title}, {row.scope.org_unit.name}, {row.reference}",
            summary=summary,
            tenant_id=tenant.id,
            before=before,
            after=after | {"orgUnitId": str(row.scope.org_unit_id), "unitId": str(row.id)},
        )
    else:
        if answer.org_unit_id is not None:
            title = f"{title}, {names[answer.org_unit_id]}"
        record(
            action=APPLICABILITY_SET,
            actor=actor,
            subject_type="tenant_obligation",
            subject_id=entry.id,
            subject_title=title,
            summary=summary,
            tenant_id=tenant.id,
            before=before,
            after=after,
        )
    return RegisterApplicability(
        obligation_id=answer.obligation_id,
        org_unit_id=answer.org_unit_id,
        unit_id=answer.unit_id,
        applicability=answer.applicability,  # type: ignore[arg-type]
        reason=answer.reason,
        decided_at=decided_at,
        decided_by=RegisterPersonRef(id=person, name=actor.label),
        version=row.version,
    )

