"""Celery tasks of the identity app: the enrolment code, invitation and re-enrolment mails
leave through the worker after the request's transaction commits, so a code request does
the same work whether or not a mail follows (AC-ID1, F12).

A plain `@shared_task`, not `@tenant_task`: no tenant is active during the ceremonies and
the task reads no tenant row. In tests Celery is eager; in E2E the mock mailer's outbox
lives in the cache for `GET /api/v1/e2e/mail-outbox`."""

from __future__ import annotations

from celery import shared_task

from apps.shared.adapters.mailer import OutgoingMail, get_mailer


@shared_task
def deliver_mail(to: str, subject: str, body: str) -> None:
    get_mailer().send(OutgoingMail(to=to, subject=subject, body=body))
