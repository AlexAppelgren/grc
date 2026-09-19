"""Celery tasks of the identity app (security review 2026-09-19, finding F12): the
enrolment code, invitation and re-enrolment mails leave through the worker, enqueued
after the request's transaction commits, so a code request does the same work in the
request whether or not a mail is about to be sent (AC-ID1: the answer, and now the
timing, are neutral).

A plain `@shared_task`, not `@tenant_task`: no tenant is active during the ceremonies
and the task reads no tenant row; it takes the finished message and hands it to the
mailer adapter. In tests Celery is eager and `apps/identity/mail.py` applies the task
inline; in E2E a real worker runs it and the mock mailer's outbox lives in the cache so
the journey can read it from the API process (`GET /api/v1/e2e/mail-outbox`)."""

from __future__ import annotations

from celery import shared_task

from apps.shared.adapters.mailer import OutgoingMail, get_mailer


@shared_task
def deliver_mail(to: str, subject: str, body: str) -> None:
    get_mailer().send(OutgoingMail(to=to, subject=subject, body=body))
