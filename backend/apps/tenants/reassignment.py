"""Removing a member who owns open work (TEN-05, TEN-S5, TEN-S9): what they hold, by kind,
and the removal that moves each kind to a new owner, ends their participations and team
memberships and deactivates them, in one audited transaction. Declared ahead of its logic
(chunk 8 plan rule 3): each function loads the member in the caller's bank, then answers
501 `not_built` until the reassignment package fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.identity.members_logic import membership_of
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.tenants.schemas import TenantMemberRemoveBody


def open_work(*, tenant: Tenant, user_id: uuid.UUID) -> NoReturn:
    """`GET /tenant/members/{userId}/open-work`."""
    membership_of(tenant.id, user_id)
    raise ProblemError(status=501, code="not_built", detail="Reading a member's open work is not built yet.")


def remove_member(
    *, tenant: Tenant, actor: Actor, user_id: uuid.UUID, body: TenantMemberRemoveBody, step_up_assertion_id: uuid.UUID
) -> NoReturn:
    """`POST /tenant/members/{userId}/remove`."""
    membership_of(tenant.id, user_id)
    raise ProblemError(status=501, code="not_built", detail="Removing a member with their work is not built yet.")
