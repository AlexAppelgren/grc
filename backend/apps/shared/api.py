"""Shared routes (playbook 4.1: routes only). The minimal Phase 0 surface so the guards
have something to enumerate: `GET /me` and `GET /reference/product`. Both are in
UNGATED_BY_DESIGN with their reasons. The generic vocabulary endpoints are stubbed in
chunk 2 with the first concrete vocabulary; a route that can only 404 would be a route
the tenant-isolation guard cannot exercise."""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.shared import logic
from apps.shared.authentication import EnrolmentAuth, SessionAuth
from apps.shared.schemas import MeResponse, ProductInfo

router = Router(tags=["Shared"])


@router.get("/me", response=MeResponse, auth=[SessionAuth(), EnrolmentAuth()], by_alias=True)
def get_me(request: HttpRequest) -> MeResponse:
    # Ungated by design: `self`. The enrolment session may call it (AC-ID2).
    return logic.me(request.auth)  # type: ignore[attr-defined]


@router.get("/reference/product", response=ProductInfo, auth=None, by_alias=True)
def get_product(request: HttpRequest) -> ProductInfo:
    # Ungated by design: `bootstrap`. The sign-in page shows the product name first.
    return logic.product_info()
