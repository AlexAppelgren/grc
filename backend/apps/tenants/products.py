"""The bank's products, described in the terms obligations are scoped with (TEN-02). A
product is retired, never deleted, and a retired product scopes nothing. Declared ahead of
its logic (chunk 8 plan rule 3): each function loads the record its route names in the
caller's bank, then answers 501 `not_built` until the organisation package fills it.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.tenants.models import TenantProduct
from apps.tenants.schemas import TenantProductBody, TenantProductPatch


def product_of(tenant: Tenant, product_id: uuid.UUID) -> TenantProduct:
    """The product, in the caller's bank and under its row-level security, or 404."""
    product = TenantProduct.objects.filter(tenant=tenant, pk=product_id).first()  # ordering: pk lookup, at most one row
    if product is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return product


def list_products(*, tenant: Tenant, order: list[str], limit: int, offset: int) -> NoReturn:
    """`GET /tenant/products`."""
    raise ProblemError(status=501, code="not_built", detail="Listing products is not built yet.")


def create_product(*, tenant: Tenant, actor: Actor, order: list[str], body: TenantProductBody) -> NoReturn:
    """`POST /tenant/products`."""
    raise ProblemError(status=501, code="not_built", detail="Adding a product is not built yet.")


def update_product(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    product_id: uuid.UUID,
    body: TenantProductPatch,
    expected_version: int | None,
) -> NoReturn:
    """`PATCH /tenant/products/{productId}`."""
    product_of(tenant, product_id)
    raise ProblemError(status=501, code="not_built", detail="Changing a product is not built yet.")
