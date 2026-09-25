"""Recurring duties in the bank's calendar (REG-07): the library's recurring duty, the bank's
dated occurrences, and completing one generates only the next, in the bank's time zone.
Declared ahead of its logic (chunk 8 plan rule 3): each function answers 501 `not_built`
behind its route's real gate until `c8-reg-duty-occurrences` fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.register.schemas import RegisterDutyCompleteBody
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def list_duties(*, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int) -> NoReturn:
    """`GET /obligations/{obligationId}/duties`. Built by `c8-reg-duty-occurrences`."""
    raise ProblemError(status=501, code="not_built", detail="Listing recurring duties is not built yet.")


def complete_occurrence(
    *, tenant: Tenant, actor: Actor, occurrence_id: uuid.UUID, body: RegisterDutyCompleteBody
) -> NoReturn:
    """`POST /duty-occurrences/{occurrenceId}/complete`. Built by `c8-reg-duty-occurrences`."""
    raise ProblemError(status=501, code="not_built", detail="Completing a duty is not built yet.")
