"""Mailer adapter (playbook 16). `mock` records every message in the cache so a test,
and an E2E journey reading `GET /api/v1/e2e/mail-outbox` from the API process while a
real worker sent the mail, can assert exactly what was (not) sent: that is how AC-ID1
("a code request for an enrolled user sends nothing") is proven. Locmem in tests, Redis
in E2E (security review 2026-09-19, finding F12). `smtp` uses Django's SMTP backend with
the MAIL_* settings. `resend` posts to Resend's HTTP API (the same vendor as ESC) and
either delivers or raises: a failed send fails the worker task visibly, it is never dropped.

Nothing here logs a recipient address or a body (playbook 4.7)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, ABCMeta, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage, get_connection

MOCK_OUTBOX_CACHE_KEY = "mock-mailer:outbox"


@dataclass(frozen=True)
class OutgoingMail:
    to: str
    subject: str
    body: str


class MailerAdapter(ABC):
    name: str

    @abstractmethod
    def send(self, mail: OutgoingMail) -> None: ...


class _OutboxMeta(ABCMeta):
    """`MockMailer.sent` reads the outbox from the cache on every access, so the API
    process sees what the worker process sent."""

    @property
    def sent(cls) -> list[OutgoingMail]:
        return [OutgoingMail(to=to, subject=subject, body=body) for to, subject, body in cache.get(MOCK_OUTBOX_CACHE_KEY) or []]


class MockMailer(MailerAdapter, metaclass=_OutboxMeta):
    """The outbox is one cache entry that never expires; `reset()` between tests."""

    name = "mock"

    def send(self, mail: OutgoingMail) -> None:
        items: list[tuple[str, str, str]] = list(cache.get(MOCK_OUTBOX_CACHE_KEY) or [])
        items.append((mail.to, mail.subject, mail.body))
        cache.set(MOCK_OUTBOX_CACHE_KEY, items, timeout=None)

    @classmethod
    def reset(cls) -> None:
        cache.delete(MOCK_OUTBOX_CACHE_KEY)


class SmtpMailer(MailerAdapter):
    name = "smtp"

    def send(self, mail: OutgoingMail) -> None:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=settings.MAIL_SMTP_HOST,
            port=settings.MAIL_SMTP_PORT,
            username=settings.MAIL_SMTP_USER,
            password=settings.MAIL_SMTP_PASSWORD,
            use_tls=True,
        )
        EmailMessage(
            subject=mail.subject,
            body=mail.body,
            from_email=settings.MAIL_FROM,
            to=[mail.to],
            connection=connection,
        ).send()


class MailDeliveryError(Exception):
    """A send the provider did not accept. The message names the HTTP status and the
    provider's error name only: Resend echoes the recipient and domain inside its error
    text, so that text is never carried (playbook 4.7)."""


class ResendMailer(MailerAdapter):
    """POST https://api.resend.com/emails with a bearer key (RESEND_API_KEY) and a plain
    text body. 2xx is delivered; anything else raises `MailDeliveryError`. Docs:
    https://resend.com/docs/api-reference/emails/send-email"""

    name = "resend"
    API_URL = "https://api.resend.com/emails"

    def send(self, mail: OutgoingMail) -> None:
        if not settings.RESEND_API_KEY:
            raise MailDeliveryError("MAIL_PROVIDER=resend but RESEND_API_KEY is empty")
        payload = {"from": settings.MAIL_FROM, "to": [mail.to], "subject": mail.subject, "text": mail.body}
        request = urllib.request.Request(  # noqa: S310 - fixed https URL
            self.API_URL,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
                # Names the sender instead of urllib's default agent.
                "User-Agent": "grc-mailer/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.MAIL_TIMEOUT_SECONDS):  # noqa: S310
                return
        except urllib.error.HTTPError as exc:
            name = ""
            try:
                name = str(json.loads(exc.read()).get("name") or "")
            except (ValueError, AttributeError):
                pass
            raise MailDeliveryError(f"Resend refused the message: status={exc.code} error={name}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise MailDeliveryError("Resend was unreachable or timed out") from None


PROVIDERS: dict[str, type[MailerAdapter]] = {"mock": MockMailer, "smtp": SmtpMailer, "resend": ResendMailer}


def get_mailer() -> MailerAdapter:
    provider = settings.MAIL_PROVIDER
    if provider not in PROVIDERS:
        raise ValueError(f"MAIL_PROVIDER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider]()
