"""The bank's organisation (TEN-02, D-21, D-43): its groups, legal entities and departments
with a head, and the licences and certificates a legal entity holds. Every row is the bank's
own and is deactivated or withdrawn, never deleted. Declared ahead of its logic (chunk 8 plan
rule 3): each function loads the record its route names in the caller's bank, so another
bank's id answers 404, then answers 501 `not_built` until the organisation package fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.tenants.models import Licence, OrgUnit
from apps.tenants.schemas import TenantLicenceBody, TenantLicencePatch, TenantOrgUnitBody, TenantOrgUnitPatch


def org_unit_of(tenant: Tenant, org_unit_id: uuid.UUID) -> OrgUnit:
    """The unit, in the caller's bank and under its row-level security, or 404."""
    unit = OrgUnit.objects.filter(tenant=tenant, pk=org_unit_id).first()  # ordering: pk lookup, at most one row
    if unit is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return unit


def licence_of(tenant: Tenant, licence_id: uuid.UUID) -> Licence:
    """The licence, in the caller's bank and under its row-level security, or 404."""
    licence = Licence.objects.filter(tenant=tenant, pk=licence_id).first()  # ordering: pk lookup, at most one row
    if licence is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return licence


def list_org_units(*, tenant: Tenant, order: list[str], limit: int, offset: int) -> NoReturn:
    """`GET /tenant/org-units`."""
    raise ProblemError(status=501, code="not_built", detail="Listing the organisation is not built yet.")


def create_org_unit(*, tenant: Tenant, actor: Actor, order: list[str], body: TenantOrgUnitBody) -> NoReturn:
    """`POST /tenant/org-units`."""
    raise ProblemError(status=501, code="not_built", detail="Adding a unit is not built yet.")


def update_org_unit(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    org_unit_id: uuid.UUID,
    body: TenantOrgUnitPatch,
    expected_version: int | None,
) -> NoReturn:
    """`PATCH /tenant/org-units/{orgUnitId}`."""
    org_unit_of(tenant, org_unit_id)
    raise ProblemError(status=501, code="not_built", detail="Changing a unit is not built yet.")


def list_licences(*, tenant: Tenant, order: list[str], org_unit_id: uuid.UUID, limit: int, offset: int) -> NoReturn:
    """`GET /tenant/org-units/{orgUnitId}/licences`."""
    org_unit_of(tenant, org_unit_id)
    raise ProblemError(status=501, code="not_built", detail="Listing licences is not built yet.")


def create_licence(
    *, tenant: Tenant, actor: Actor, order: list[str], org_unit_id: uuid.UUID, body: TenantLicenceBody
) -> NoReturn:
    """`POST /tenant/org-units/{orgUnitId}/licences`."""
    org_unit_of(tenant, org_unit_id)
    raise ProblemError(status=501, code="not_built", detail="Recording a licence is not built yet.")


def update_licence(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    licence_id: uuid.UUID,
    body: TenantLicencePatch,
    expected_version: int | None,
) -> NoReturn:
    """`PATCH /tenant/licences/{licenceId}`."""
    licence_of(tenant, licence_id)
    raise ProblemError(status=501, code="not_built", detail="Changing a licence is not built yet.")
