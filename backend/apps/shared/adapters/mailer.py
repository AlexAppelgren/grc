"""Mailer adapter (playbook 16). `mock` records every message in the cache so a test,
and an E2E journey reading `GET /api/v1/e2e/mail-outbox` from the API process while a
real worker sent the mail, can assert exactly what was (not) sent: that is how AC-ID1
("a code request for an enrolled user sends nothing") is proven. Locmem in tests, Redis
in E2E (security review 2026-09-19, finding F12). `smtp` uses Django's SMTP backend with
the MAIL_* settings.

Nothing here logs a recipient address or a body (playbook 4.7)."""

from __future__ import annotations

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


PROVIDERS: dict[str, type[MailerAdapter]] = {"mock": MockMailer, "smtp": SmtpMailer}


def get_mailer() -> MailerAdapter:
    provider = settings.MAIL_PROVIDER
    if provider not in PROVIDERS:
        raise ValueError(f"MAIL_PROVIDER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider]()
