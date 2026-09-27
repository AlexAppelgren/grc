"""Triage, dismissal, restore, starting the assessment and the one-person close
(CAS-02, CAS-03; D-92).

Published ahead of its logic: every function loads the caller's case, so another bank's
case answers 404 exactly as it will, and then answers 501 `not_built` until `c9-triage`
and `c9-close-paths` build it here. Each move goes through `logic.transition()`.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.cases import logic
from apps.cases.schemas import CasesCase, CasesCloseBody, CasesReasonBody, CasesTriageBody
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

NOT_BUILT = "This part of the case workflow is not available yet."


def triage_change(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesTriageBody
) -> CasesCase:
    """`new` to `assigned`, with a confirmed urgency and an owner (CAS-02)."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def dismiss_change(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesReasonBody
) -> CasesCase:
    """`new` to `dismissed`, with a reason from the bank's list (CAS-02)."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def restore_change(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`dismissed`, or a one-person close, back to `new` (CAS-02)."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def start_assessment(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`assigned` to `assessing`, opening an empty assessment (CAS-03)."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def close_without_action(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesCloseBody
) -> CasesCase:
    """`assigned` or `assessing` to `closed` on one person's word, audited (D-92)."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
