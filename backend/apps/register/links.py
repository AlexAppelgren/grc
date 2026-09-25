"""Linked internal items (REG-05): the bank's own policies, procedures and controls, with the
references an outside GRC system knows them by. A removal is soft; the item survives the link.
Declared ahead of its logic (chunk 8 plan rule 3): each function answers 501 `not_built`
behind its route's real gate until `c8-reg-internal-links` fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.register.schemas import RegisterInternalLinkBody
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def list_links(*, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int) -> NoReturn:
    """`GET /obligations/{obligationId}/internal-links`. Built by `c8-reg-internal-links`."""
    raise ProblemError(status=501, code="not_built", detail="Listing linked internal items is not built yet.")


def add_link(
    *, tenant: Tenant, actor: Actor, order: list[str], obligation_id: uuid.UUID, body: RegisterInternalLinkBody
) -> NoReturn:
    """`POST /obligations/{obligationId}/internal-links`. Built by `c8-reg-internal-links`."""
    raise ProblemError(status=501, code="not_built", detail="Linking an internal item is not built yet.")


def remove_link(*, tenant: Tenant, actor: Actor, link_id: uuid.UUID) -> NoReturn:
    """`DELETE /internal-links/{linkId}`. Built by `c8-reg-internal-links`."""
    raise ProblemError(status=501, code="not_built", detail="Removing a link is not built yet.")
