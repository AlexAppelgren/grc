"""Applicability per obligation, per legal entity and per unit (REG-01, D-75, AC-REG1).

One person holding `applicability.approve` sets the answer after a confirmation dialog: no
request, no second approver, no step-up, one `record()` per row naming the value before and
after and the reason. Declared ahead of its logic (chunk 8 plan rule 3): each function
answers 501 `not_built` behind its route's real gate until `c8-reg-applicability` fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.register.schemas import RegisterApplicabilityBody, RegisterApplicabilityManyBody
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def set_applicability(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    obligation_id: uuid.UUID,
    body: RegisterApplicabilityBody,
    expected_version: int | None,
) -> NoReturn:
    """`PUT /obligations/{obligationId}/applicability`. Built by `c8-reg-applicability`."""
    raise ProblemError(status=501, code="not_built", detail="Setting applicability is not built yet.")


def set_applicability_many(
    *, tenant: Tenant, actor: Actor, order: list[str], body: RegisterApplicabilityManyBody
) -> NoReturn:
    """`POST /applicability`. Built by `c8-reg-applicability` and f03-T70."""
    raise ProblemError(status=501, code="not_built", detail="Setting many applicability answers is not built yet.")
