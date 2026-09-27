"""The chunk 10 security review's fixes (security-review-c10, docs/reviews/CHUNK10_REVIEW.md).

Each class pins one finding, red before its fix:

- **M1, the delegation hop reaches the person who caused the notice.** A sign-off request
  and an assignment name the person who made the move, so an away recipient whose delegate
  is that person keeps the notice (TEN-04, CAS-06): a four-eyes request never lands only
  with the one person who may not approve it.
- **M2, a failed worker task logs its exception's message and its arguments.** Celery's
  failure line interpolates the exception's repr into the message and attaches the formatted
  traceback and the task's arguments as `data`, and the worker replaced the JSON handler
  with its own; a database error's message holds the failing row, an address or a subject
  among it (playbook 4.7). The worker keeps the JSON handler, and the line names the task,
  its id and what happened, never the exception's text or the arguments.
- **The planted-string sweep.** One string, planted in everything a bank types about a case
  (a comment and its mention, each action's title, a ledger note, the assessment, an
  unconfirmed "So what?" draft and a register entry's notes), reaches none of the sinks after a comment is written and
  the reminder, escalation and digest jobs run for the bank: the log, what Sentry would send
  for each log line, the audit rows, the outbox, the notification titles, the mail rows and
  every mail's subject and body, links included.
"""

from __future__ import annotations

import datetime
import io
import json
import logging
from typing import Any, cast

from django.db import transaction
from django.test import TestCase

from apps.cases import testing as cases_build
from apps.cases.models import Action, CaseTransition, ImpactAssessment
from apps.cases.tests_signoff import Bank
from apps.cases.tests_triage import CaseMoves, triage_bank
from apps.collab import tasks
from apps.collab.models import EmailMessage, Notification, NotificationKind
from apps.home.tests_my_work import obligation
from apps.identity.models import Membership
from apps.register.models import TenantObligation
from apps.library.reading import today_for
from apps.shared import factories, sentry_scrub, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.logging import JsonFormatter
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import AuditAssertingClient, sign_in
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import testing as watch_build
from config.celery import app as celery_app


def _away(tenant: Any, person: Any, delegate: Any) -> None:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        Membership.objects.filter(tenant=tenant, user=person).update(out_of_office_until=today_for(tenant), delegate=delegate)


def _told(tenant: Any, kind: NotificationKind) -> list[tuple[Any, Any]]:
    tenancy.activate(tenant.id)
    return sorted(Notification.objects.filter(kind=kind.value).values_list("user_id", "on_behalf_of_id"))


class TheMoverIsNeverTheDelegate(CaseMoves, TestCase):
    client_class = AuditAssertingClient

    def test_a_signoff_request_stays_with_the_away_approver_whose_delegate_asked(self) -> None:
        """The approver is away and named the case's owner as delegate; the owner asks for
        sign-off. The approver keeps the request, and the owner is not told on their behalf."""
        bank = Bank()
        _away(bank.tenant, bank.approver, bank.owner)
        bank.ready_for_signoff(self.client)
        self.assertEqual(_told(bank.tenant, NotificationKind.SIGNOFF_REQUESTED), [(bank.approver.id, None)])

    def test_an_assignment_stays_with_the_away_owner_whose_delegate_triaged(self) -> None:
        """The new owner is away and named the officer as delegate; the officer triages the
        case to them. The owner keeps the assignment rather than the officer taking it."""
        bank = triage_bank()
        _away(bank.tenant, bank.owner, bank.officer)
        response = self.move(bank, "triage", {"urgency": "within_3_months", "ownerId": str(bank.owner.id)})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_told(bank.tenant, NotificationKind.ASSIGNED), [(bank.owner.id, None)])


class AFailedTaskLogsNoText(TestCase):
    PLANTED = "planted-7c4e anna@bank.example Failing row contains"

    def test_the_worker_keeps_the_json_handler(self) -> None:
        self.assertIs(celery_app.conf.worker_hijack_root_logger, False)

    def test_the_failure_line_names_the_task_and_never_its_text_or_arguments(self) -> None:
        planted = self.PLANTED

        def fails(title: str) -> None:
            raise ValueError(planted)

        task = celery_app.task(name="tests_review_c10.fails")(fails)
        self.addCleanup(celery_app.tasks.pop, task.name, None)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        trace_logger = logging.getLogger("celery.app.trace")
        trace_logger.addHandler(handler)
        self.addCleanup(trace_logger.removeHandler, handler)

        task.apply(args=("planted-args-91b2 a bank's own title",), throw=False)

        written = stream.getvalue()
        self.assertIn("tests_review_c10.fails", written, "the line still names the task")
        self.assertIn("builtins.ValueError", written, "and the exception's type")
        self.assertNotIn("planted-7c4e", written)
        self.assertNotIn("anna@bank.example", written)
        self.assertNotIn("planted-args-91b2", written)


class APlantedStringReachesNoSink(TestCase):
    PLANTED = "planted-c10-5d9a"

    def test_a_banks_text_reaches_no_log_sentry_audit_outbox_title_mail_or_link(self) -> None:
        planted = self.PLANTED
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="planted-sweep")
        officer = factories.member_user(tenant, roles=("compliance_officer",))
        owner = factories.member_user(tenant, roles=("compliance_officer",))
        reader = factories.member_user(tenant, roles=("reader",))
        case = cases_build.case(tenant, watch_build.change(title="FI amends the custody rules"), owner=owner, so_what_text=planted)
        cases_build.in_category(case, CaseStatusCategory.IMPLEMENTING)
        today = today_for(tenant)
        due = [
            today + datetime.timedelta(days=tenant.reminder_days_before[0]),  # the due-soon reminder
            today - datetime.timedelta(days=1),  # the overdue reminder
            today - datetime.timedelta(days=tenant.escalate_after_days),  # the escalation
        ]
        with transaction.atomic():
            tenancy.activate(tenant.id)
            for day in due:
                Action.objects.create(tenant=tenant, case=case, title=f"{planted} action", owner=owner, due_date=day, created_by=owner)
            CaseTransition.objects.create(tenant=tenant, case=case, from_status="assessing", to_status="implementing", by_user=owner, note=planted)
            ImpactAssessment.objects.create(tenant=tenant, case=case, applies="yes", why=planted, what_must_change=planted)
        # A duty of the owner's due for review, so the digest has a row to send.
        entry = factories.register_entry(
            tenant, obligation("Safeguard client assets").id, first_line_owner=owner, next_review_date=today + datetime.timedelta(days=3)
        )
        with transaction.atomic():
            tenancy.activate(tenant.id)
            TenantObligation.objects.filter(pk=entry.pk).update(status_note=planted, applicability_reason=planted)
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        loggers = [logging.getLogger(name) for name in ("", "apps", "django", "celery")]
        for logger in loggers:
            logger.addHandler(handler)
            self.addCleanup(logger.removeHandler, handler)
        client = AuditAssertingClient()
        body = {"subjectType": "change_case", "subjectId": str(case.id), "body": f"{planted} comment", "mentionUserIds": [str(reader.id)]}
        created = client.post("/api/v1/comments", data=body, content_type="application/json", **sign_in(officer, tenant=tenant))
        self.assertEqual(created.status_code, 201, created.content)
        for task in (tasks.send_tenant_reminders, tasks.send_tenant_escalations, tasks.send_tenant_digests):
            task.apply(args=(str(tenant.id),))

        tenancy.activate(tenant.id)
        self.assertEqual(
            set(EmailMessage.objects.values_list("template", flat=True)),
            {"due_soon", "overdue", "escalation", "weekly_digest"},
            "every collab mail went out, so the sweep read each of them",
        )
        self.assertTrue(Notification.objects.filter(kind=NotificationKind.MENTION.value).exists())
        lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
        sinks = {
            "log": stream.getvalue(),
            "sentry": json.dumps(
                [sentry_scrub.before_send(cast(Any, {"message": line["message"], "extra": line}), {}) for line in lines]
            ),
            "audit": " ".join(f"{e.summary} {e.subject_title} {e.before} {e.after}" for e in AuditEvent.objects.all()),
            "outbox": " ".join(str(p) for p in OutboxEvent.objects.values_list("payload", flat=True)),
            "notification": " ".join(Notification.objects.values_list("title", flat=True)),
            "mail row": " ".join(f"{m.subject} {m.to_email}" for m in EmailMessage.objects.all()),
            "mail": " ".join(f"{m.subject} {m.body}" for m in MockMailer.sent),
        }
        for sink, text in sinks.items():
            with self.subTest(sink=sink):
                self.assertNotIn(planted, text)
