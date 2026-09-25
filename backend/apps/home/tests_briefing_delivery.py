"""How the weekly briefing reaches people (HOM-02, COL-02, HARDENING H21).

What is proved here, one class per question:

- **The snapshot commits first.** The week is stored and committed before any mail is
  handed to the worker, so a relay that refuses keeps the week and marks only the refused
  mail, and the next hourly run sends what did not go out, once, to each person.
- **A missed week is sent.** The hourly beat hands a bank on from its own sending moment
  until the week is over, so a worker that was down at seven on Monday still gets the week
  out on Monday afternoon or on Wednesday.

`tests_briefing.py` holds what the snapshot and the mail say; this module holds only how
and when the mail leaves.
"""

from __future__ import annotations

import datetime
import smtplib
from unittest import mock

from django.test import TestCase, override_settings

from apps.cases import testing as cases_build
from apps.collab.models import EmailMessage, EmailStatus
from apps.home import tasks
from apps.home.models import Briefing
from apps.identity.models import Membership, User
from apps.shared import factories, tenancy
from apps.shared.adapters.mailer import MockMailer, OutgoingMail
from apps.shared.models import AuditEvent, Tenant, TenantStatus
from apps.watch import testing as watch_build

LAST_WEEK_START = datetime.date(2026, 9, 21)
SIGHTED_LAST_WEEK = datetime.datetime(2026, 9, 22, 9, 0, tzinfo=datetime.UTC)
# Monday 28 September 2026, 07:00 in Stockholm (05:00 UTC in summer time): the bank's own
# sending moment under the default settings (Monday, 07:00).
MONDAY_MORNING = datetime.datetime(2026, 9, 28, 5, 0, tzinfo=datetime.UTC)
# The same Wednesday, 14:00 in Stockholm: the moment has passed and the week is not over.
WEDNESDAY = datetime.datetime(2026, 9, 30, 12, 0, tzinfo=datetime.UTC)
# The same Monday, 06:00 in Stockholm: this week's moment has not come yet.
MONDAY_BEFORE = datetime.datetime(2026, 9, 28, 4, 0, tzinfo=datetime.UTC)


class _RefusingMailer:
    """A relay that refuses every mail, the way a relay that is down does."""

    def send(self, mail: OutgoingMail) -> None:
        raise smtplib.SMTPServerDisconnected("relay down")


class _RefusingOne:
    """A relay that refuses one address and delivers the rest to the mock outbox."""

    def __init__(self, address: str) -> None:
        self.address = address

    def send(self, mail: OutgoingMail) -> None:
        if mail.to == self.address:
            raise smtplib.SMTPRecipientsRefused({mail.to: (550, b"mailbox unavailable")})
        MockMailer().send(mail)


class _Week(TestCase):
    tenant: Tenant
    reader: User
    colleague: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="briefing-delivery", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.colleague = factories.member_user(cls.tenant, roles=("reader",))
        change = watch_build.change(
            title="Research payments",
            urgency="act_now",
            key_date=datetime.date(2026, 10, 15),
            key_date_label="In force",
            first_seen_at=SIGHTED_LAST_WEEK,
        )
        cases_build.case(cls.tenant, change)

    def setUp(self) -> None:
        MockMailer.reset()

    def run_job(self, at: datetime.datetime = MONDAY_MORNING) -> None:
        with mock.patch("django.utils.timezone.now", return_value=at):
            tasks.send_weekly_briefing(self.tenant.id)

    def messages(self) -> list[EmailMessage]:
        tenancy.activate(self.tenant.id)
        return list(EmailMessage.objects.filter(template=tasks.TEMPLATE).order_by("to_email"))

    def briefing(self) -> Briefing:
        tenancy.activate(self.tenant.id)
        return Briefing.objects.get(week_start=LAST_WEEK_START)


class TheSnapshotCommitsBeforeAnyMailLeaves(_Week):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_nothing_is_sent_inside_the_transaction_and_each_mail_is_handed_on_on_commit(self) -> None:
        """The worker gets one delivery per person, and only once the week is committed."""
        with mock.patch.object(tasks.deliver_briefing, "delay") as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.run_job()
            self.assertEqual(MockMailer.sent, [], "no mail leaves inside the snapshot's transaction")
            delay.assert_not_called()
            for callback in callbacks:
                callback()

        messages = self.messages()
        self.assertEqual(
            sorted(call.args for call in delay.call_args_list),
            sorted((str(self.tenant.id), str(row.id)) for row in messages),
        )
        self.assertEqual({row.status for row in messages}, {EmailStatus.QUEUED.value})
        self.assertEqual(sorted(row.to_email for row in messages), sorted([self.reader.email, self.colleague.email]))
        self.assertIsNone(self.briefing().email_sent_at, "queued is not sent")

    def test_a_relay_that_refuses_keeps_the_week_and_marks_each_mail_failed(self) -> None:
        with mock.patch.object(tasks, "get_mailer", return_value=_RefusingMailer()):
            self.run_job()

        briefing = self.briefing()
        self.assertIsNone(briefing.email_sent_at)
        messages = self.messages()
        self.assertEqual({(row.status, row.error) for row in messages}, {(EmailStatus.FAILED.value, "SMTPServerDisconnected")})
        failed = AuditEvent.objects.filter(tenant=self.tenant, action="mail.failed", subject_type="email_message")
        self.assertEqual(sorted(str(event.subject_id) for event in failed), sorted(str(row.id) for row in messages))
        self.assertNotIn(self.reader.email, str([event.after for event in failed]))

    def test_the_next_run_sends_what_did_not_go_out_and_nothing_twice(self) -> None:
        with mock.patch.object(tasks, "get_mailer", return_value=_RefusingOne(self.colleague.email)):
            self.run_job()
        self.assertEqual([sent.to for sent in MockMailer.sent], [self.reader.email])
        first_sent_at = self.briefing().email_sent_at
        self.assertEqual(first_sent_at, MONDAY_MORNING, "the week went out when its first mail did")

        self.run_job(at=MONDAY_MORNING + datetime.timedelta(hours=1))

        self.assertEqual(sorted(sent.to for sent in MockMailer.sent), sorted([self.reader.email, self.colleague.email]))
        self.assertEqual({row.status for row in self.messages()}, {EmailStatus.SENT.value})
        self.assertEqual(self.briefing().email_sent_at, first_sent_at, "a later mail does not move the time it went out")
        self.assertEqual(Briefing.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant, action=tasks.SENT).count(), 1)

        self.run_job(at=MONDAY_MORNING + datetime.timedelta(hours=2))
        self.assertEqual(len(MockMailer.sent), 2, "once everybody has it, a run sends nothing")

    def test_a_retry_skips_a_person_who_switched_the_briefing_off_or_left(self) -> None:
        """COL-02: `weeklyBriefing` is read again at every attempt, and so is membership."""
        with mock.patch.object(tasks, "get_mailer", return_value=_RefusingMailer()):
            self.run_job()
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(user=self.colleague).update(notification_prefs={"weeklyBriefing": False})
        Membership.objects.filter(user=self.reader).update(deactivated_at=MONDAY_MORNING)

        self.run_job(at=MONDAY_MORNING + datetime.timedelta(hours=1))

        self.assertEqual(MockMailer.sent, [])
        self.assertIsNone(self.briefing().email_sent_at)

    def test_a_delivery_for_a_mail_already_sent_sends_nothing(self) -> None:
        """Two workers holding the same delivery: the second finds the row sent."""
        self.run_job()
        row = self.messages()[0]
        tasks.deliver_briefing(self.tenant.id, str(row.id))
        self.assertEqual(len(MockMailer.sent), 2)


class AMissedWeekIsSent(_Week):
    def enqueued_at(self, at: datetime.datetime) -> list[str]:
        with (
            mock.patch("django.utils.timezone.now", return_value=at),
            mock.patch.object(tasks.send_weekly_briefing, "delay") as delay,
        ):
            tasks.send_weekly_briefings()
        return [call.args[0] for call in delay.call_args_list]

    def test_the_bank_is_handed_on_from_its_moment_until_the_week_is_over(self) -> None:
        self.assertIn(str(self.tenant.id), self.enqueued_at(MONDAY_MORNING))
        self.assertIn(str(self.tenant.id), self.enqueued_at(WEDNESDAY))
        self.assertNotIn(str(self.tenant.id), self.enqueued_at(MONDAY_BEFORE))

    def test_a_deactivated_bank_is_not_handed_on(self) -> None:
        Tenant.objects.filter(pk=self.tenant.pk).update(status=TenantStatus.DEACTIVATED.value)
        self.assertNotIn(str(self.tenant.id), self.enqueued_at(WEDNESDAY))

    def test_a_week_the_monday_run_missed_goes_out_on_wednesday(self) -> None:
        self.run_job(at=WEDNESDAY)
        self.assertEqual(self.briefing().email_sent_at, WEDNESDAY)
        self.assertEqual(sorted(sent.to for sent in MockMailer.sent), sorted([self.reader.email, self.colleague.email]))
        self.assertIn(f"/briefing/{LAST_WEEK_START.isoformat()}", MockMailer.sent[0].body)
