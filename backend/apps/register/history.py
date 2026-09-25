"""Assessment history and "How we read this rule" (REG-04).

Assessments are append-only; an interpretation is a new version on every save, the previous
one kept and readable, with no approval step. Declared ahead of its logic (chunk 8 plan rule
3): each function answers 501 `not_built` behind its route's real gate until
`c8-reg-history-interpretation` fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.register.schemas import RegisterInterpretationBody
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def list_assessments(
    *, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int
) -> NoReturn:
    """`GET /obligations/{obligationId}/assessments`. Built by `c8-reg-history-interpretation`."""
    raise ProblemError(status=501, code="not_built", detail="The assessment history is not built yet.")


def read_interpretation(*, tenant: Tenant, obligation_id: uuid.UUID) -> NoReturn:
    """`GET /obligations/{obligationId}/interpretation`. Built by `c8-reg-history-interpretation`."""
    raise ProblemError(status=501, code="not_built", detail="Reading how we read this rule is not built yet.")


def save_interpretation(
    *,
    tenant: Tenant,
    actor: Actor,
    obligation_id: uuid.UUID,
    body: RegisterInterpretationBody,
    expected_version: int | None,
) -> NoReturn:
    """`PUT /obligations/{obligationId}/interpretation`. Built by `c8-reg-history-interpretation`."""
    raise ProblemError(status=501, code="not_built", detail="Saving how we read this rule is not built yet.")
