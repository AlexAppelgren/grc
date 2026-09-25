"""The Statement of Applicability (REG-08, REG-S15, D-41, D-42): the register filtered by a
standard and a legal entity. The entity's conformance row with its own assessed status, and
its live units by reference, each with its answer, reason, status, who set it and when, and
its history of answers. A read that writes nothing and computes no status from the units.

It exists where a unit may: under a standard, for an entity that follows it (`units.py`). A
standard outside the bank's regulatory scope is hidden, as the register hides it (FP-03,
D-42): 404, with every row kept for when the standard is added back.
"""

from __future__ import annotations

import uuid
from typing import cast

from django.core.exceptions import ValidationError

from apps.library.reading import obligation_scopes, outside_reasons
from apps.register import applicability, status_logic, units
from apps.register.schemas import (
    RegisterPersonRef,
    RegisterStatementOfApplicability,
    RegisterStatementUnit,
    RegisterUnitDecision,
)
from apps.shared.models import AuditEvent, Tenant
from apps.taxonomy import matching


def statement_of_applicability(
    *, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, entity: uuid.UUID, limit: int, offset: int
) -> RegisterStatementOfApplicability:
    """`GET /obligations/{obligationId}/statement-of-applicability`: a fixed number of queries
    however many units are on the page."""
    units.conformance_scope(obligation_id, entity)
    if not _in_regulatory_scope(tenant, obligation_id):
        raise ValidationError("That standard is not in your regulatory scope.", code="not_found")
    register = status_logic.read_register(tenant=tenant, order=order, obligation_id=obligation_id)
    conformance = next(row for row in register.entities if row.org_unit_id == entity)
    page = units.list_units(tenant=tenant, order=order, obligation_id=obligation_id, entity=entity, limit=limit, offset=offset)
    history = _history([unit.id for unit in page.items])
    return RegisterStatementOfApplicability(
        obligation_id=obligation_id,
        conformance=conformance,
        units=[RegisterStatementUnit(**dict(unit), history=history.get(unit.id, [])) for unit in page.items],
        total=page.total,
    )


def _in_regulatory_scope(tenant: Tenant, obligation_id: uuid.UUID) -> bool:
    """The inventory's own verdict on the standard's conformance duty (FP-03): inside when it
    falls outside no dimension of the bank's regulatory scope."""
    scope = obligation_scopes([obligation_id]).get(obligation_id, {})
    carried = {dimension: {term.key for term in terms} for dimension, terms in scope.items()}
    return not outside_reasons(carried, matching.footprint_of(tenant.id), matching.restricting_dimensions())


def _history(unit_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[RegisterUnitDecision]]:
    """Each unit's answers, oldest first, from the events that stored them: the unit is their
    subject (`applicability.py`), so this is one query for the page."""
    events = (
        AuditEvent.objects.filter(
            action=applicability.APPLICABILITY_SET, subject_type=applicability.UNIT_SUBJECT, subject_id__in=unit_ids
        )
        .order_by("created", "id")
        .values_list("subject_id", "actor_id", "actor_label", "created", "after")
    )
    history: dict[uuid.UUID, list[RegisterUnitDecision]] = {}
    # Both ids are set: the subject is the unit, and `applicability._store()` takes only a person.
    for unit_id, person_id, name, created, after in events:
        history.setdefault(cast(uuid.UUID, unit_id), []).append(
            RegisterUnitDecision(
                applicability=after["applicability"],
                reason=after["reason"],
                decided_at=created,
                decided_by=RegisterPersonRef(id=cast(uuid.UUID, person_id), name=name),
            )
        )
    return history
