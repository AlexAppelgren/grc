"""The people picker (COL-04, TEN-03, HOM-05): the bank's current members as ids and names,
optionally only those whose roles hold one permission. Nothing else about a person leaves
here; `GET /tenant/members` stays under `members.manage`.
"""

from __future__ import annotations

from typing import Any

from apps.identity.models import Membership
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.permissions import TENANT_PERMISSIONS


def list_people(*, tenant: Tenant, permission: str | None) -> list[dict[str, Any]]:
    """`GET /reference/people`. A permission narrows the list to the members one of whose roles
    grants it, read exactly as `session_logic.build_principal` reads a session's grants: every
    role of the current membership, retired or not, intersected with the bank's permissions."""
    if permission is not None and permission not in TENANT_PERMISSIONS:
        raise ProblemError(status=422, code="unknown_key", detail="That is not a permission a bank's roles can hold.")
    memberships = Membership.objects.filter(tenant=tenant, deactivated_at__isnull=True)
    if permission is not None:
        memberships = memberships.filter(roles__permissions__contains=[permission])
    rows = memberships.order_by("user__name", "user_id").values_list("user_id", "user__name").distinct()
    return [{"id": user_id, "name": name} for user_id, name in rows]
