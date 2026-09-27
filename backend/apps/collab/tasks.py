"""Celery tasks of the collab app (COL-02, playbook 12).

`deliver_mail` is the one door a collab mail leaves through. It is a `@tenant_task`: the
tenant id is its first argument and it runs activated inside its own transaction, so the
`email_message` row and the send commit together. The row is the idempotency key: its
unique `(tenant, user, template, subject_type, subject_id, sent_on)`, with `sent_on` the
bank's local date, makes a second send of the same mail the same day find the row and do
nothing, however many workers retry it. A send the relay refused keeps its row as `failed`
with the error's kind, and the next run tries that row again rather than adding another.

`send_reminders` is the hourly beat entry: it hands on the banks whose local wall time has
just reached `REMINDER_SEND_HOUR`, one `send_tenant_reminders` and one
`send_tenant_escalations` each (fan out, never chain). Each is a `@tenant_task` that runs
`reminders.py` or `escalation.py` for one bank inside its own transaction.

Nothing here logs a recipient's address, a subject or a body (playbook 4.7): the row's id,
its template and its status are all that leave.
"""

from __future__ import annotations

import logging
import smtplib
import uuid

from celery import shared_task
from django.utils import timezone

from apps.collab import escalation, mail, reminders
from apps.collab.models import EmailMessage, EmailStatus
from apps.identity.models import Membership, UserStatus
from apps.library.reading import today_for
from apps.shared import tenancy
from apps.shared.adapters.mailer import get_mailer
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant

logger = logging.getLogger(__name__)

SUBJECT_TYPE = "email_message"
# A row in either state has not reached the relay yet; any other has, so it is never resent.
UNSENT = (EmailStatus.QUEUED.value, EmailStatus.FAILED.value)


@shared_task
@tenancy.tenant_task
def deliver_mail(
    tenant_id: uuid.UUID,
    user_id: str,
    template: mail.Template,
    context: dict[str, str | int],
    subject_type: str | None,
    subject_id: str | None,
) -> None:
    """Compose one member's mail, send it once for its template, record and day, and record
    that it went. A member who left the bank, or whose account is no longer active, between
    the enqueue and now is sent nothing."""
    try:
        # One membership per person per bank (`membership_tenant_user_unique`).
        membership = Membership.objects.select_related("user__locale").get(
            user_id=user_id, deactivated_at__isnull=True, user__status=UserStatus.ACTIVE.value
        )
    except Membership.DoesNotExist:
        return
    outgoing = mail.compose(membership, template, mail.MailContext.from_task(context))
    tenant = Tenant.objects.get(pk=tenant_id)
    key = {
        "tenant": tenant,
        "user": membership.user,
        "template": template,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "sent_on": today_for(tenant),
    }
    # Insert the day's row unless it exists, then lock it: a second worker waits here for
    # the first to commit and then finds the mail already sent.
    EmailMessage.objects.bulk_create(
        [EmailMessage(**key, to_email=outgoing.to, subject=outgoing.subject)], ignore_conflicts=True
    )
    row = EmailMessage.objects.select_for_update().get(**key)
    if row.status not in UNSENT:
        return
    row.to_email, row.subject = outgoing.to, outgoing.subject
    try:
        get_mailer().send(outgoing)
    except (smtplib.SMTPException, OSError) as exc:
        # The error's kind only: a relay's message can echo the address.
        row.status, row.error = EmailStatus.FAILED.value, type(exc).__name__
        logger.warning("collab mail %s (%s) failed: %s", row.id, template, row.error)
    else:
        row.status, row.error, row.sent_at = EmailStatus.SENT.value, "", timezone.now()
    row.save(update_fields=["to_email", "subject", "status", "error", "sent_at"])
    record(
        action=f"mail.{row.status}",
        actor=Actor.system("collab mail"),
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=template,
        summary=f"A {template} mail to a member was {row.status}.",
        tenant_id=tenant.id,
        after={
            "template": template,
            "status": row.status,
            "userId": str(membership.user_id),
            "sentOn": row.sent_on.isoformat(),
        },
    )


@shared_task
def send_reminders() -> None:
    """The beat entry, run hourly: hand on each bank whose own clock reads the send hour."""
    for tenant in reminders.tenants_at_send_hour(timezone.now()):
        send_tenant_reminders.delay(str(tenant.id))
        send_tenant_escalations.delay(str(tenant.id))


@shared_task
@tenancy.tenant_task
def send_tenant_reminders(tenant_id: uuid.UUID) -> None:
    """One bank's reminders for today, in one transaction with their notifications."""
    reminders.send_reminders(Tenant.objects.get(pk=tenant_id))


@shared_task
@tenancy.tenant_task
def send_tenant_escalations(tenant_id: uuid.UUID) -> None:
    """One bank's escalations of overdue actions, in one transaction with their notifications
    and audit rows."""
    escalation.escalate(Tenant.objects.get(pk=tenant_id))
