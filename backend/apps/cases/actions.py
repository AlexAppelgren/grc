"""Actions with an owner and a due date, locked while the case waits for sign-off (CAS-04).

Published ahead of its logic: every function loads the caller's case or action, so
another bank's answers 404 exactly as it will, and then answers 501 `not_built` until
`c9-actions` builds it here. Adding the first action moves an assessing case to
implementing through `logic.transition()` (R2_CROSS_CUTTING (j)); removal sets
`removed_at` and never deletes.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.cases import logic
from apps.cases.schemas import CasesAction, CasesActionBody, CasesActionPage, CasesActionPatch
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.schemas import PageQuery

NOT_BUILT = "This part of the case workflow is not available yet."


def list_actions(*, tenant: Tenant, change_id: uuid.UUID, page: PageQuery) -> CasesActionPage:
    """One page of the case's live actions."""
    logic.load_case(tenant, change_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def add_action(
    *, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID, expected_version: int | None, body: CasesActionBody
) -> CasesAction:
    """A new action on the case, under the case's `If-Match`."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def update_action(
    *, tenant: Tenant, actor: Actor, user: Any, action_id: uuid.UUID, expected_version: int | None, body: CasesActionPatch
) -> CasesAction:
    """Edit, complete or reopen an action, under the action's own `If-Match`."""
    logic.load_action(tenant, action_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def delete_action(*, tenant: Tenant, actor: Actor, user: Any, action_id: uuid.UUID, expected_version: int | None) -> None:
    """Remove an action: `removed_at` and `removed_by` are set, and the row stays."""
    logic.load_action(tenant, action_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
