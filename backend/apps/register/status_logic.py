"""Compliance status on the register entry and per legal entity (REG-02, D-42).

Declared ahead of its logic (chunk 8 plan rule 3): each function answers 501 `not_built`
behind its route's real gate until `c8-reg-status` and `c8-reg-entity-status` fill it. A read
never writes; a write goes through `ensure_register_entry()` and `record()`, with `If-Match`.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.register.schemas import RegisterEntityPatch, RegisterPatch
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def read_register(*, tenant: Tenant, order: list[str], obligation_id: uuid.UUID) -> NoReturn:
    """`GET /obligations/{obligationId}/register`. Built by `c8-reg-status`."""
    raise ProblemError(status=501, code="not_built", detail="Reading the register entry is not built yet.")


def update_register(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    obligation_id: uuid.UUID,
    body: RegisterPatch,
    expected_version: int | None,
) -> NoReturn:
    """`PATCH /obligations/{obligationId}/register`. Built by `c8-reg-status`."""
    raise ProblemError(status=501, code="not_built", detail="Saving the register entry is not built yet.")


def update_entity_status(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    obligation_id: uuid.UUID,
    org_unit_id: uuid.UUID,
    body: RegisterEntityPatch,
    expected_version: int | None,
) -> NoReturn:
    """`PATCH /obligations/{obligationId}/register/entities/{orgUnitId}`. Built by
    `c8-reg-entity-status`."""
    raise ProblemError(status=501, code="not_built", detail="Saving a legal entity's status is not built yet.")
