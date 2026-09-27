"""The impact assessment (CAS-03).

Published ahead of its logic: the save loads the caller's case, so another bank's case
answers 404 exactly as it will, and then answers 501 `not_built` until `c9-assessment`
builds it here. Saving moves the case to no other category (R2_CROSS_CUTTING (j)).
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.cases import logic
from apps.cases.schemas import CasesAssessmentBody, CasesCase
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

NOT_BUILT = "This part of the case workflow is not available yet."


def save_assessment(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesAssessmentBody
) -> CasesCase:
    """The whole assessment, replacing what was saved, under the case's `If-Match`."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
