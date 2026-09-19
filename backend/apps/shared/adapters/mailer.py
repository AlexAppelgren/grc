"""Mailer adapter (playbook 16). `mock` records every message in memory so a test can
assert exactly what was (not) sent, which is how AC-ID1 ("a code request for an enrolled
user sends nothing") is proven. `smtp` uses Django's SMTP backend with the MAIL_* settings.

Nothing here logs a recipient address or a body (playbook 4.7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMessage, get_connection


@dataclass(frozen=True)
class OutgoingMail:
    to: str
    subject: str
    body: str


class MailerAdapter(ABC):
    name: str

    @abstractmethod
    def send(self, mail: OutgoingMail) -> None: ...


class MockMailer(MailerAdapter):
    """Class-level outbox so the instance the code under test builds and the instance the
    test inspects see the same list. `reset()` between tests."""

    name = "mock"
    sent: list[OutgoingMail] = []

    def send(self, mail: OutgoingMail) -> None:
        MockMailer.sent.append(mail)

    @classmethod
    def reset(cls) -> None:
        cls.sent.clear()


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
