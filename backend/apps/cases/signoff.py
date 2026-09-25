"""Sign-off: requested by one person, approved by a second with a passkey, or sent back
(CAS-06).

Published ahead of its logic: every function loads the caller's case, so another bank's
case answers 404 exactly as it will, and then answers 501 `not_built` until
`c9-signoff-request` and `c9-signoff` build it here. Each move goes through
`logic.transition()`, whose guard and the database's CHECK both refuse the requester's
own approval.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.cases import logic
from apps.cases.schemas import CasesCase, CasesNoteBody
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

NOT_BUILT = "This part of the case workflow is not available yet."


def request_signoff(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`implementing` to `signoff`, with no open action and clean evidence."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def approve_signoff(
    *,
    tenant: Tenant,
    actor: Actor,
    user: Any,
    order: list[str],
    change_id: uuid.UUID,
    expected_version: int | None,
    body: CasesNoteBody,
    step_up_assertion_id: uuid.UUID,
) -> CasesCase:
    """`signoff` to `closed` by a second person, the step-up named on the audit row."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def send_back_signoff(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesNoteBody
) -> CasesCase:
    """`signoff` back to `implementing`, with the second person's note."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
