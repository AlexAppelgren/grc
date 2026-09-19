"""Shared logic: what the shared routes return. No HTTP here (playbook 4.1)."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.shared.adapters.mailer import MockMailer
from apps.shared.schemas import MailOutboxMessage, ProductInfo


def product_info() -> ProductInfo:
    return ProductInfo(product_name=settings.PRODUCT_NAME)


def mail_outbox() -> list[MailOutboxMessage]:
    """The mock mailer's sent messages, for E2E journeys only (AC-ID1: prove nothing was
    sent). Outside E2E_MODE the route does not exist as far as a caller can tell."""
    if not settings.E2E_MODE or settings.MAIL_PROVIDER != "mock":
        raise ValidationError("Not found.", code="not_found")
    return [MailOutboxMessage(to=mail.to, subject=mail.subject, body=mail.body) for mail in MockMailer.sent]
