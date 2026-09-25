"""The Statement of Applicability (REG-08, REG-S15): the register filtered by a standard and a
legal entity. A read that computes no status from the units. Declared ahead of its logic
(chunk 8 plan rule 3): it answers 501 `not_built` behind its route's real gate until f03-T72
fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def statement_of_applicability(
    *, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, entity: uuid.UUID, limit: int, offset: int
) -> NoReturn:
    """`GET /obligations/{obligationId}/statement-of-applicability`. Built by f03-T72."""
    raise ProblemError(status=501, code="not_built", detail="The Statement of Applicability is not built yet.")
