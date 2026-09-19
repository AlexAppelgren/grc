"""Shared routes (playbook 4.1: routes only): `GET /reference/product` (bootstrap) and the
E2E-only mail outbox. `/me` moved to the identity app in chunk 1. The generic vocabulary
endpoints are stubbed in chunk 2 with the first concrete vocabulary."""

from django.http import HttpRequest
from ninja import Router

from apps.shared import logic
from apps.shared.schemas import MailOutboxMessage, ProductInfo

router = Router(tags=["Shared"])


@router.get("/reference/product", response=ProductInfo, auth=None, operation_id="getProduct", by_alias=True)
def get_product(request: HttpRequest) -> ProductInfo:
    # Ungated by design: `bootstrap`. The sign-in page shows the product name first.
    return logic.product_info()


@router.get("/e2e/mail-outbox", response=list[MailOutboxMessage], auth=None, operation_id="e2eMailOutbox", by_alias=True)
def e2e_mail_outbox(request: HttpRequest) -> list[MailOutboxMessage]:
    # Ungated by design: `bootstrap`. Answers 404 unless E2E_MODE is on (playbook 8.3).
    return logic.mail_outbox()
