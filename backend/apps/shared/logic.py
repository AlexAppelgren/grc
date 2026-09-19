"""Shared logic: what the shared routes return. No HTTP here (playbook 4.1)."""

from __future__ import annotations

from django.conf import settings

from apps.shared.authentication import Principal
from apps.shared.schemas import MeResponse, ProductInfo


def product_info() -> ProductInfo:
    return ProductInfo(product_name=settings.PRODUCT_NAME)


def me(principal: Principal) -> MeResponse:
    return MeResponse(
        kind=principal.kind.value,
        subject_id=principal.subject_id,
        tenant_id=principal.tenant_id,
        permissions=sorted(principal.permissions),
        scopes=sorted(principal.scopes),
    )
