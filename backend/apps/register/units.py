"""Statement of Applicability units (REG-08, D-41): a legal entity's clauses and controls of a
standard, in the bank's own words, one by one or pasted with a dry run. A unit exists only
under a standard the library admitted (422 `units_only_under_standards`), for an entity
whose conformance scope row applies (422 `scope_not_applicable`); its reference and title
are fixed once it has an applicability decision, a status or a gap (409 `unit_has_history`),
and a removal is a stamp, allowed only before then (R2_CROSS_CUTTING (l)). Every write is
one audit event. Nothing here is indexed or sent to a model.

A paste's commit stores every unit, and every answer its lines carry through applicability's
bulk path (`POST /applicability`, D-75, AC-REG1), in the request's one transaction: all of it
or none. A line carrying an answer needs `applicability.approve` as that path does.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone

from apps.library.reading import under_standard
from apps.register import applicability
from apps.register.models import Applicability, Gap, SoaUnit, TenantObligationScope
from apps.register.schemas import (
    UNIT_REFERENCE_MAX,
    UNIT_TITLE_MAX,
    RegisterApplicabilityManyBody,
    RegisterApplicabilityRow,
    RegisterPersonRef,
    RegisterUnit,
    RegisterUnitBody,
    RegisterUnitPage,
    RegisterUnitPaste,
    RegisterUnitPasteBody,
    RegisterUnitPasteLine,
    RegisterUnitPasteRow,
    RegisterUnitPatch,
    RegisterVocabRef,
)
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.vocabulary import label_for
from apps.taxonomy.models import ComplianceCategory, ComplianceStatus
from apps.tenants.models import OrgUnit, OrgUnitKind

SUBJECT_TYPE = "soa_unit"  # applicability.UNIT_SUBJECT, spelled out for the audit guard
UNIT_CREATED = "register.unit_created"
UNIT_RENAMED = "register.unit_renamed"
UNIT_REMOVED = "register.unit_removed"

# The stored kind, as the published contract spells it (`RegisterUnit.applicability`).
WIRE_APPLICABILITY = {
    Applicability.APPLIES.value: "applies",
    Applicability.DOES_NOT_APPLY.value: "not_applicable",
    Applicability.NOT_ASSESSED.value: "under_assessment",
}


# ---------------------------------------------------------------------------------------
# Where a unit may exist
# ---------------------------------------------------------------------------------------
def conformance_scope(obligation_id: uuid.UUID, org_unit_id: uuid.UUID) -> TenantObligationScope:
    """The entity's conformance scope row a unit is listed under, checked in the order a
    caller can act on: an obligation the bank cannot see is 404, one outside a standard 422
    `units_only_under_standards`, an entity that is not the bank's legal entity 404, and an
    entity whose conformance row does not apply, or was never answered, 422
    `scope_not_applicable`."""
    _standard(obligation_id)
    if not OrgUnit.objects.filter(pk=org_unit_id, kind=OrgUnitKind.LEGAL_ENTITY.value, active=True).exists():
        raise ValidationError("That legal entity is not here.", code="not_found")
    scope = TenantObligationScope.objects.filter(
        tenant_obligation__obligation_id=obligation_id, org_unit_id=org_unit_id, product__isnull=True
    ).first()  # ordering: unique per entry, entity and product, at most one row
    if scope is None or scope.applicability != Applicability.APPLIES.value:
        raise ValidationError(
            "Units are listed only for a legal entity that follows the standard. Set its conformance to applies first.",
            code="scope_not_applicable",
        )
    return scope


def _standard(obligation_id: uuid.UUID) -> None:
    standard = under_standard(obligation_id)
    if standard is None:
        raise ValidationError("That obligation is not here.", code="not_found")
    if not standard:
        raise ValidationError(
            "Units are listed only under a standard's conformance obligation.", code="units_only_under_standards"
        )


# ---------------------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------------------
def _live_units() -> QuerySet[SoaUnit]:
    """Live units with everything a row shows, in a constant number of queries."""
    return (
        SoaUnit.objects.filter(removed_at__isnull=True)
        .select_related("scope__tenant_obligation", "applicability_decided_by", "compliance_status")
        .prefetch_related("compliance_status__labels")
        .annotate(has_gap=Exists(Gap.objects.filter(unit_id=OuterRef("pk"))))
    )


def _has_history(unit: SoaUnit) -> bool:
    """A decision, a status or a gap: after any of them the reference and title are fixed,
    so a decision can never be moved to another control by a rename (D-41)."""
    return (
        unit.applicability_decided_at is not None
        or unit.compliance_status.kind != ComplianceCategory.NOT_ASSESSED.value
        or unit.has_gap  # type: ignore[attr-defined]  # annotated by _live_units()
    )


def _unit_out(unit: SoaUnit, order: list[str]) -> RegisterUnit:
    decided_by = unit.applicability_decided_by
    return RegisterUnit(
        id=unit.id,
        obligation_id=unit.scope.tenant_obligation.obligation_id,
        org_unit_id=unit.scope.org_unit_id,
        reference=unit.reference,
        title=unit.title,
        applicability=WIRE_APPLICABILITY[unit.applicability],  # type: ignore[arg-type]
        applicability_reason=unit.applicability_reason or None,
        applicability_decided_at=unit.applicability_decided_at,
        applicability_decided_by=None if decided_by is None else RegisterPersonRef(id=decided_by.id, name=decided_by.name),
        compliance_status=RegisterVocabRef(
            key=unit.compliance_status.key, kind=unit.compliance_status.kind, label=label_for(unit.compliance_status, order)
        ),
        has_history=_has_history(unit),
        version=unit.version,
    )


def list_units(
    *,
    tenant: Tenant,
    order: list[str],
    obligation_id: uuid.UUID,
    entity: uuid.UUID | None,
    limit: int,
    offset: int,
) -> RegisterUnitPage:
    """`GET /obligations/{obligationId}/units`: the live units under the obligation, by
    reference, optionally of one entity. A read writes nothing; no units is an empty page."""
    if under_standard(obligation_id) is None:
        raise ValidationError("That obligation is not here.", code="not_found")
    units = _live_units().filter(scope__tenant_obligation__obligation_id=obligation_id)
    if entity is not None:
        units = units.filter(scope__org_unit_id=entity)
    return RegisterUnitPage(
        items=[_unit_out(unit, order) for unit in units[offset : offset + limit]], total=units.count()
    )


# ---------------------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------------------
def create_unit(
    *, tenant: Tenant, actor: Actor, order: list[str], obligation_id: uuid.UUID, body: RegisterUnitBody
) -> RegisterUnit:
    """`POST /obligations/{obligationId}/units`: one undecided unit, not assessed, with its
    `register.unit_created` event. A live reference the entity already has is 409
    `duplicate_key`."""
    scope = conformance_scope(obligation_id, body.org_unit_id)
    reference, title = _cleaned(body.reference), _cleaned(body.title)
    unit = _insert(tenant=tenant, actor=actor, scope=scope, reference=reference, title=title)
    return _unit_out(_live_units().get(pk=unit.pk), order)


def _cleaned(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("Write a reference and a title in your own words.", code="validation_error")
    return cleaned


def _insert(*, tenant: Tenant, actor: Actor, scope: TenantObligationScope, reference: str, title: str) -> SoaUnit:
    return _insert_many(tenant=tenant, actor=actor, scope=scope, lines=[(reference, title)])[0]


def _insert_many(*, tenant: Tenant, actor: Actor, scope: TenantObligationScope, lines: list[tuple[str, str]]) -> list[SoaUnit]:
    """New undecided units in one INSERT, each with its own `register.unit_created` event. A
    live reference the entity already has, or one another write took first, is 409
    `duplicate_key` and stores none of them."""
    status = ComplianceStatus.objects.get(is_default=True, active=True)
    try:
        with transaction.atomic():
            created = SoaUnit.objects.bulk_create(
                [SoaUnit(tenant_id=tenant.id, scope=scope, reference=reference, title=title, compliance_status=status) for reference, title in lines]
            )
    except IntegrityError:
        listed = lines[0][0] if len(lines) == 1 else "one of these references"
        raise ValidationError(f"This entity already lists {listed}.", code="duplicate_key") from None
    for unit in created:
        record(
            action=UNIT_CREATED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=unit.id,
            subject_title=unit.reference,
            summary="Unit added.",
            tenant_id=tenant.id,
            after={"scopeId": str(scope.id), "orgUnitId": str(scope.org_unit_id), "reference": unit.reference, "title": unit.title},
        )
    return created


def _unit_for_write(unit_id: uuid.UUID, expected_version: int | None) -> SoaUnit:
    """The live unit, locked for the write; a removed or unknown one is 404. `If-Match` is
    required: a versioned write without the version the caller read is 409 `stale_write`."""
    unit = _live_units().select_for_update(of=("self",)).filter(pk=unit_id).first()  # ordering: pk lookup, at most one row
    if unit is None:
        raise ValidationError("That unit is not here.", code="not_found")
    if expected_version is None or expected_version != unit.version:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")
    if _has_history(unit):
        raise ProblemError(
            status=409,
            code="unit_has_history",
            detail="This unit has a decision, a status or a gap, so it stays as it is. Add a new unit instead.",
        )
    return unit


def update_unit(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    unit_id: uuid.UUID,
    body: RegisterUnitPatch,
    expected_version: int | None,
) -> RegisterUnit:
    """`PATCH /units/{unitId}`: a new reference or title for a unit with no history, with
    the values before and after in its event."""
    unit = _unit_for_write(unit_id, expected_version)
    before = {"reference": unit.reference, "title": unit.title}
    if body.reference is not None:
        unit.reference = _cleaned(body.reference)
    if body.title is not None:
        unit.title = _cleaned(body.title)
    unit.version += 1
    try:
        with transaction.atomic():
            unit.save(update_fields=["reference", "title", "version"])
    except IntegrityError:
        raise ValidationError(f"This entity already lists {unit.reference}.", code="duplicate_key") from None
    record(
        action=UNIT_RENAMED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=unit.id,
        subject_title=unit.reference,
        summary="Unit renamed.",
        tenant_id=tenant.id,
        before=before,
        after={"reference": unit.reference, "title": unit.title},
    )
    return _unit_out(_live_units().get(pk=unit.pk), order)


def remove_unit(*, tenant: Tenant, actor: Actor, unit_id: uuid.UUID, expected_version: int | None) -> None:
    """`DELETE /units/{unitId}`: stamps `removed_at` and `removed_by` on a unit with no
    history; the row stays and its reference is free again."""
    unit = _unit_for_write(unit_id, expected_version)
    unit.removed_at = timezone.now()
    unit.removed_by_id = actor.id
    unit.version += 1
    unit.save(update_fields=["removed_at", "removed_by", "version"])
    record(
        action=UNIT_REMOVED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=unit.id,
        subject_title=unit.reference,
        summary="Unit removed.",
        tenant_id=tenant.id,
        before={"removedAt": None},
        after={"removedAt": unit.removed_at.isoformat()},
    )


# ---------------------------------------------------------------------------------------
# Paste
# ---------------------------------------------------------------------------------------
def paste_units(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    obligation_id: uuid.UUID,
    body: RegisterUnitPasteBody,
    may_decide: bool,
) -> RegisterUnitPaste:
    """`POST /obligations/{obligationId}/units/paste`. The dry run answers what each line
    would become and stores nothing: a line with no reference or title, one past the unit
    limits, a reference the paste repeats, one the entity already lists and an answer
    without a reason are refused on their own rows. A field the line does not name, or an
    unknown answer, is refused whole by the schema (422), as is a paste over
    `REGISTER_BULK_MAX`. The commit stores the units and their answers only when no line is
    refused; otherwise it answers as a dry run does."""
    scope = conformance_scope(obligation_id, body.org_unit_id)
    cap = settings.REGISTER_BULK_MAX
    if len(body.lines) > cap:
        raise ValidationError(f"Paste at most {cap} lines in one call.", code="validation_error")
    if not may_decide and any(line.applicability is not None for line in body.lines):
        raise ProblemError(
            status=403,
            code="permission_denied",
            detail="You do not have access to this.",
            required_permission=perms.APPLICABILITY_APPROVE,
        )
    existing = set(SoaUnit.objects.filter(scope=scope, removed_at__isnull=True).values_list("reference", flat=True))
    seen: set[str] = set()
    rows = []
    for line, pasted in enumerate(body.lines, start=1):
        reference, title = pasted.reference.strip(), pasted.title.strip()
        problem = _problem(reference, title, seen, existing) or _half_decided(pasted)
        seen.add(reference)
        rows.append(
            RegisterUnitPasteRow(
                line=line,
                reference=reference,
                title=title,
                outcome="refused" if problem else "will_create",
                problem=problem,  # type: ignore[arg-type]
                unit_id=None,
            )
        )
    if body.dry_run or any(row.problem for row in rows):
        return RegisterUnitPaste(dry_run=True, rows=rows, created=0)

    created = _insert_many(tenant=tenant, actor=actor, scope=scope, lines=[(row.reference, row.title) for row in rows])
    answers = [
        RegisterApplicabilityRow(
            obligation_id=obligation_id, unit_id=unit.id, applicability=pasted.applicability, reason=(pasted.reason or "").strip()
        )
        for unit, pasted in zip(created, body.lines, strict=True)
        if pasted.applicability is not None
    ]
    if answers:
        applicability.set_applicability_many(
            tenant=tenant, actor=actor, order=order, body=RegisterApplicabilityManyBody(rows=answers)
        )
    for row, unit in zip(rows, created, strict=True):
        row.outcome, row.unit_id = "created", unit.id
    return RegisterUnitPaste(dry_run=False, rows=rows, created=len(created))


def _half_decided(pasted: RegisterUnitPasteLine) -> str | None:
    """An answer is stored with its reason, so a line carries both or neither."""
    has_reason = bool((pasted.reason or "").strip())
    return "reason_missing" if (pasted.applicability is not None) != has_reason else None


def _problem(reference: str, title: str, seen: set[str], existing: set[str]) -> str | None:
    if not reference or not title:
        return "empty_line"
    if len(reference) > UNIT_REFERENCE_MAX:
        return "reference_too_long"
    if len(title) > UNIT_TITLE_MAX:
        return "title_too_long"
    if reference in seen:
        return "duplicate_reference"
    if reference in existing:
        return "reference_exists"
    return None
