"""Support access, requested by the platform and granted by the bank (TEN-06, D-49, ADR
0042). A request grants nothing; a tenant admin approves it with a passkey, declines it or
revokes it, and support then reads under it and never writes. Declared ahead of its logic
(chunk 8 plan rule 3): each tenant-side function loads the request in the caller's bank, so
another bank's id answers 404, then every function answers 501 `not_built` until
`c8-ten-support-grants`, `c8-support-access-mechanism` and `c8-support-access-console-list`
fill them.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.tenants.models import SupportAccess
from apps.tenants.schemas import ConsoleSupportAccessBody


def grant_of(tenant: Tenant, grant_id: uuid.UUID) -> SupportAccess:
    """The request, in the caller's bank and under its row-level security, or 404."""
    grant = SupportAccess.objects.filter(tenant=tenant, pk=grant_id).first()  # ordering: pk lookup, at most one row
    if grant is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return grant


def request_access(*, tenant_id: uuid.UUID, actor: Actor, body: ConsoleSupportAccessBody) -> NoReturn:
    """`POST /console/tenants/{tenantId}/support-access`: the bank must exist."""
    if not Tenant.objects.filter(pk=tenant_id).exists():
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    raise ProblemError(status=501, code="not_built", detail="Requesting support access is not built yet.")


def my_grants(*, actor: Actor, limit: int, offset: int) -> NoReturn:
    """`GET /console/support-access`: the caller's own requests only."""
    raise ProblemError(status=501, code="not_built", detail="Listing your support access is not built yet.")


def enter(*, actor: Actor, grant_id: uuid.UUID, step_up_assertion_id: uuid.UUID) -> NoReturn:
    """`POST /console/support-access/{grantId}/enter`. The grant is read through the policy
    keyed on the caller's own platform user id, which `c8-support-access-mechanism` sets."""
    raise ProblemError(status=501, code="not_built", detail="Entering a bank under support access is not built yet.")


def list_for_tenant(*, tenant: Tenant, limit: int, offset: int) -> NoReturn:
    """`GET /tenant/support-access`."""
    raise ProblemError(status=501, code="not_built", detail="Listing support access is not built yet.")


def approve(*, tenant: Tenant, actor: Actor, grant_id: uuid.UUID, step_up_assertion_id: uuid.UUID) -> NoReturn:
    """`POST /tenant/support-access/{grantId}/approve`."""
    grant_of(tenant, grant_id)
    raise ProblemError(status=501, code="not_built", detail="Approving support access is not built yet.")


def decline(*, tenant: Tenant, actor: Actor, grant_id: uuid.UUID) -> NoReturn:
    """`POST /tenant/support-access/{grantId}/decline`."""
    grant_of(tenant, grant_id)
    raise ProblemError(status=501, code="not_built", detail="Declining support access is not built yet.")


def revoke(*, tenant: Tenant, actor: Actor, grant_id: uuid.UUID) -> NoReturn:
    """`POST /tenant/support-access/{grantId}/revoke`."""
    grant_of(tenant, grant_id)
    raise ProblemError(status=501, code="not_built", detail="Revoking support access is not built yet.")
