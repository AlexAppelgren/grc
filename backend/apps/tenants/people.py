"""The people picker (COL-04, TEN-03, HOM-05): the bank's active members as ids and names,
optionally only those whose roles hold one permission. Nothing else about a person leaves
here; `GET /tenant/members` stays under `members.manage`. Declared ahead of its logic (chunk
8 plan rule 3): the permission is checked, then the function answers 501 `not_built` until
the people package fills it.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.permissions import TENANT_PERMISSIONS


def list_people(*, tenant: Tenant, permission: str | None) -> NoReturn:
    """`GET /reference/people`."""
    if permission is not None and permission not in TENANT_PERMISSIONS:
        raise ProblemError(status=422, code="unknown_key", detail="That is not a permission a bank's roles can hold.")
    raise ProblemError(status=501, code="not_built", detail="Listing people is not built yet.")
