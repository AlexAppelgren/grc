"""Statement of Applicability units (REG-08, D-41): a legal entity's clauses and controls of a
standard, in the bank's own words, one by one or pasted with a dry run. A unit exists only
under a standard, for an entity whose conformance row applies; its reference and title are
fixed once it has history; a removal is soft. Declared ahead of its logic (chunk 8 plan rule
3): each function answers 501 `not_built` behind its route's real gate until f03-T68 and
f03-T69 fill it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.register.schemas import RegisterUnitBody, RegisterUnitPasteBody, RegisterUnitPatch
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def list_units(
    *,
    tenant: Tenant,
    order: list[str],
    obligation_id: uuid.UUID,
    entity: uuid.UUID | None,
    limit: int,
    offset: int,
) -> NoReturn:
    """`GET /obligations/{obligationId}/units`. Built by f03-T68."""
    raise ProblemError(status=501, code="not_built", detail="Listing units is not built yet.")


def create_unit(
    *, tenant: Tenant, actor: Actor, order: list[str], obligation_id: uuid.UUID, body: RegisterUnitBody
) -> NoReturn:
    """`POST /obligations/{obligationId}/units`. Built by f03-T68."""
    raise ProblemError(status=501, code="not_built", detail="Adding a unit is not built yet.")


def update_unit(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    unit_id: uuid.UUID,
    body: RegisterUnitPatch,
    expected_version: int | None,
) -> NoReturn:
    """`PATCH /units/{unitId}`. Built by f03-T68."""
    raise ProblemError(status=501, code="not_built", detail="Renaming a unit is not built yet.")


def remove_unit(*, tenant: Tenant, actor: Actor, unit_id: uuid.UUID, expected_version: int | None) -> NoReturn:
    """`DELETE /units/{unitId}`. Built by f03-T68."""
    raise ProblemError(status=501, code="not_built", detail="Removing a unit is not built yet.")


def paste_units(
    *, tenant: Tenant, actor: Actor, obligation_id: uuid.UUID, body: RegisterUnitPasteBody
) -> NoReturn:
    """`POST /obligations/{obligationId}/units/paste`. Built by f03-T69."""
    raise ProblemError(status=501, code="not_built", detail="Pasting units is not built yet.")
