"""The case file as text that stands alone (CAS-07).

Published ahead of its logic: it loads the caller's case, so another bank's case answers
404 exactly as it will, and then answers 501 `not_built` until `c9-case-file` builds it
here.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.cases import logic
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

NOT_BUILT = "This part of the case workflow is not available yet."


def case_file(*, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID) -> str:
    """The change, the bank's judgement, the work and the sign-off, as plain text."""
    logic.load_case(tenant, change_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
