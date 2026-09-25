"""Gaps and risk acceptance (REG-03).

A gap is a fact about how the bank complies, never about whether a rule applies. Accepting a
gap's risk keeps its four eyes: a second person holding `risk.accept.approve`, with a fresh
passkey step-up, who is not the person who identified the gap. Declared ahead of its logic
(chunk 8 plan rule 3): each function answers 501 `not_built` behind its route's real gate
until `c8-reg-gaps` and `c8-reg-risk-acceptance` fill it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.register.schemas import RegisterGapBody, RegisterGapPatch, RegisterGapQuery, RegisterRiskAcceptanceBody
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def list_obligation_gaps(
    *, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int
) -> NoReturn:
    """`GET /obligations/{obligationId}/gaps`. Built by `c8-reg-gaps`."""
    raise ProblemError(status=501, code="not_built", detail="Listing an obligation's gaps is not built yet.")


def create_gap(
    *, tenant: Tenant, actor: Actor, order: list[str], obligation_id: uuid.UUID, body: RegisterGapBody
) -> NoReturn:
    """`POST /obligations/{obligationId}/gaps`. Built by `c8-reg-gaps`."""
    raise ProblemError(status=501, code="not_built", detail="Recording a gap is not built yet.")


def list_gaps(*, tenant: Tenant, order: list[str], filters: RegisterGapQuery, limit: int, offset: int) -> NoReturn:
    """`GET /gaps`. Built by `c8-reg-gaps`."""
    raise ProblemError(status=501, code="not_built", detail="Listing the bank's gaps is not built yet.")


def update_gap(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    gap_id: uuid.UUID,
    body: RegisterGapPatch,
    expected_version: int | None,
) -> NoReturn:
    """`PATCH /gaps/{gapId}`. Built by `c8-reg-gaps`."""
    raise ProblemError(status=501, code="not_built", detail="Amending a gap is not built yet.")


def request_risk_acceptance(
    *, tenant: Tenant, actor: Actor, order: list[str], gap_id: uuid.UUID, body: RegisterRiskAcceptanceBody
) -> NoReturn:
    """`POST /gaps/{gapId}/accept-risk`. Built by `c8-reg-risk-acceptance`."""
    raise ProblemError(status=501, code="not_built", detail="Asking to accept a risk is not built yet.")


def approve_risk_acceptance(
    *, tenant: Tenant, actor: Actor, order: list[str], gap_id: uuid.UUID, step_up_assertion_id: uuid.UUID
) -> NoReturn:
    """`POST /gaps/{gapId}/accept-risk/approve`. Built by `c8-reg-risk-acceptance`."""
    raise ProblemError(status=501, code="not_built", detail="Approving a risk acceptance is not built yet.")


def reopen_gap(*, tenant: Tenant, actor: Actor, order: list[str], gap_id: uuid.UUID) -> NoReturn:
    """`POST /gaps/{gapId}/reopen`. Built by `c8-reg-risk-acceptance`."""
    raise ProblemError(status=501, code="not_built", detail="Reopening a gap is not built yet.")
