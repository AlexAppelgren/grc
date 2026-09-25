"""Triage reminders on the bank's own clock (COL-02; `c10-reminders-core`).

What these pin:

- **Lead days.** A case awaiting triage whose due time falls on the bank's local today plus
  a lead day reminds each triager once; with leads of 1, 3 and 7 it reminds on each of those
  days and on none in between. A due time that passed since the last send moment is
  `overdue`, once.
- **Once.** A second run the same day is silent, because the `email_message` row exists.
- **Who.** Active members whose roles triage cases, never a reader, never someone who muted
  reminders, never a deactivated member; a case that left `new` reminds nobody. An away
  triager's reminder reaches their delegate.
- **Stamped.** Every notification whose mail was queued carries `emailed_at`.
- **Bounded.** The query count per bank is pinned and does not grow with the lead days.
- **One bank per task.** The beat hands each bank on by itself, and a bank's task reads
  none of another bank's cases.

Every date is the bank's local today plus an offset, at a fixed wall time (CHUNK10_TASKS
rule 14): the clock is frozen at the bank's send hour on that day.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.cases import testing as cases_build
from apps.cases.models import CaseStatusCategory, ChangeCase
from apps.collab import reminders, tasks
from apps.collab.models import EmailMessage, Notification
from apps.identity.models import Membership, User
from apps.library.reading import today_for
from apps.shared import factories, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import Tenant
from apps.watch import testing as watch_build

HELSINKI = "Europe/Helsinki"


def at(day: datetime.date, hour: int, zone: str = HELSINKI, minute: int = 0) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=ZoneInfo(zone))


def frozen(moment: datetime.datetime) -> Any:
    return mock.patch("django.utils.timezone.now", return_value=moment.astimezone(datetime.UTC))


def statements(captured: CaptureQueriesContext) -> int:
    """The queries a run sends, without the savepoints each nested transaction adds."""
    return sum(1 for query in captured.captured_queries if "SAVEPOINT" not in query["sql"])


class ReminderTestCase(TestCase):
    tenant: Tenant
    anchor: datetime.date
    officer: User
    second_officer: User
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="reminders", timezone=HELSINKI)
        cls.anchor = today_for(cls.tenant)
        cls.officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.second_officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)
        tenancy.activate(self.tenant.id)

    def day(self, offset: int) -> datetime.date:
        return self.anchor + datetime.timedelta(days=offset)

    def case(self, due: datetime.datetime | None, *, tenant: Tenant | None = None) -> ChangeCase:
        bank = tenant or self.tenant
        case = cases_build.case(bank, watch_build.change(title=f"FI amends rule {ChangeCase.objects.count()}"))
        tenancy.activate(bank.id)
        ChangeCase.objects.filter(pk=case.pk).update(triage_due_at=due)
        tenancy.activate(self.tenant.id)
        return case

    def leads(self, *days: int) -> None:
        Tenant.objects.filter(pk=self.tenant.pk).update(reminder_days_before=list(days))

    def run_on(self, offset: int, *, tenant: Tenant | None = None) -> list[Notification]:
        """The bank's task, as the beat hands it on at the send hour of local today + offset."""
        bank = tenant or self.tenant
        with frozen(at(self.day(offset), settings.REMINDER_SEND_HOUR, bank.timezone)):
            tasks.send_tenant_reminders(str(bank.id))
        tenancy.activate(self.tenant.id)
        return list(Notification.objects.order_by("created_at", "id"))

    def told(self, case: ChangeCase) -> list[tuple[Any, str]]:
        tenancy.activate(self.tenant.id)
        return sorted((row.user_id, row.kind) for row in Notification.objects.filter(subject_id=case.id))


class LeadDays(ReminderTestCase):
    def test_a_case_due_in_three_days_reminds_each_triager_once_and_a_second_run_is_silent(self) -> None:
        case = self.case(at(self.day(3), 12))
        self.run_on(0)
        self.assertEqual(self.told(case), sorted([(self.officer.id, "due_soon"), (self.second_officer.id, "due_soon")]))
        self.assertEqual(len(MockMailer.sent), 2)
        self.assertEqual(
            set(EmailMessage.objects.values_list("user_id", "template", "subject_type", "subject_id", "sent_on")),
            {
                (person.id, "due_soon", "change_case", case.id, self.anchor)
                for person in (self.officer, self.second_officer)
            },
        )
        self.run_on(0)
        self.assertEqual(len(self.told(case)), 2, "the second run the same day writes no row")
        self.assertEqual(len(MockMailer.sent), 2, "and sends no mail")

    def test_a_second_run_is_silent_while_the_first_runs_mail_is_still_queued(self) -> None:
        """In the worker the mail's row is written after commit; today's notification
        already counts, so a redelivered run in between writes nothing."""
        case = self.case(at(self.day(3), 12))
        with mock.patch("apps.collab.mail.send") as queued:
            self.run_on(0)
            self.run_on(0)
        self.assertEqual(queued.call_count, 2)
        self.assertEqual(len(self.told(case)), 2)
        self.assertFalse(EmailMessage.objects.exists())

    def test_the_mail_names_the_change_its_due_date_and_links_to_the_case(self) -> None:
        case = self.case(at(self.day(3), 12))
        self.run_on(0)
        mailed = MockMailer.sent[0]
        self.assertEqual(mailed.subject, f"Due {self.day(3).isoformat()}: {case.change.title}")
        self.assertIn(f"{settings.APP_BASE_URL.rstrip('/')}/watch/{case.change_id}", mailed.body)

    def test_leads_of_one_three_and_seven_remind_on_each_and_not_in_between(self) -> None:
        self.leads(1, 3, 7)
        case = self.case(at(self.day(7), 9))
        reminded = []
        for offset in range(8):
            before = len(self.told(case))
            self.run_on(offset)
            if len(self.told(case)) > before:
                reminded.append(offset)
        self.assertEqual(reminded, [0, 4, 6])

    def test_a_due_time_is_read_on_the_banks_local_date(self) -> None:
        """00:30 in Helsinki is still the previous evening in UTC: the local date decides."""
        case = self.case(at(self.day(3), 0, minute=30))
        self.run_on(0)
        self.assertEqual(len(self.told(case)), 2)
        late = self.case(at(self.day(4), 0) - datetime.timedelta(minutes=1))
        self.run_on(1)
        self.assertEqual(len(self.told(late)), 0, "23:59 on day 3 is due on day 3, not day 4")

    def test_an_overdue_case_is_reminded_once_the_morning_after_its_due_time(self) -> None:
        case = self.case(at(self.day(0), 20))
        self.run_on(0)
        self.assertEqual(self.told(case), [], "not due yet at the send hour")
        self.run_on(1)
        self.assertEqual({kind for _user, kind in self.told(case)}, {"overdue"})
        self.assertEqual(MockMailer.sent[0].subject, f"Overdue since {self.day(0).isoformat()}: {case.change.title}")
        self.run_on(2)
        self.assertEqual(len(self.told(case)), 2, "an overdue case is reminded once, not every day")


class WhoIsReminded(ReminderTestCase):
    def test_a_reader_who_cannot_triage_is_not_reminded(self) -> None:
        case = self.case(at(self.day(3), 12))
        self.run_on(0)
        self.assertNotIn(self.reader.id, {user for user, _kind in self.told(case)})

    def test_a_case_that_left_new_reminds_nobody(self) -> None:
        case = self.case(at(self.day(3), 12))
        ChangeCase.objects.filter(pk=case.pk).update(status=CaseStatusCategory.ASSIGNED.value, owner=self.officer)
        self.assertEqual(self.run_on(0), [])
        self.assertEqual(MockMailer.sent, [])

    def test_a_muted_triager_gets_no_row_and_no_mail(self) -> None:
        Membership.objects.filter(user=self.second_officer).update(notification_prefs={"reminders": False})
        case = self.case(at(self.day(3), 12))
        self.run_on(0)
        self.assertEqual(self.told(case), [(self.officer.id, "due_soon")])
        self.assertEqual([mailed.to for mailed in MockMailer.sent], [self.officer.email])
        self.assertFalse(EmailMessage.objects.filter(user=self.second_officer).exists())

    def test_a_deactivated_triager_gets_neither(self) -> None:
        from django.utils import timezone

        Membership.objects.filter(user=self.second_officer).update(deactivated_at=timezone.now())
        case = self.case(at(self.day(3), 12))
        self.run_on(0)
        self.assertEqual(self.told(case), [(self.officer.id, "due_soon")])
        self.assertEqual([mailed.to for mailed in MockMailer.sent], [self.officer.email])

    def test_an_away_triagers_reminder_reaches_their_delegate(self) -> None:
        Membership.objects.filter(user=self.second_officer).update(
            out_of_office_until=self.day(5), delegate=self.reader
        )
        case = self.case(at(self.day(3), 12))
        self.run_on(0)
        rows = {(row.user_id, row.on_behalf_of_id) for row in Notification.objects.filter(subject_id=case.id)}
        self.assertEqual(rows, {(self.officer.id, None), (self.reader.id, self.second_officer.id)})
        self.assertEqual({mailed.to for mailed in MockMailer.sent}, {self.officer.email, self.reader.email})


class Stamped(ReminderTestCase):
    def test_every_notification_whose_mail_was_queued_carries_emailed_at(self) -> None:
        self.case(at(self.day(3), 12))
        self.case(at(self.day(0), 6))
        rows = self.run_on(0)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row.emailed_at is not None for row in rows))
        mailed = set(EmailMessage.objects.values_list("user_id", "subject_id"))
        unstamped = Notification.objects.filter(emailed_at__isnull=True)
        self.assertFalse(any((row.user_id, row.subject_id) in mailed for row in unstamped))


class QueryCount(ReminderTestCase):
    def queries(self, *leads: int) -> int:
        self.leads(*leads)
        with CaptureQueriesContext(connection) as captured:
            self.run_on(0)
        Notification.objects.all().delete()
        EmailMessage.objects.all().delete()
        return statements(captured)

    def test_the_count_per_bank_is_pinned_and_does_not_grow_with_the_lead_days(self) -> None:
        self.case(at(self.day(3), 12))
        one = self.queries(3)
        three = self.queries(1, 3, 7)
        five = self.queries(1, 2, 3, 7, 30)
        self.assertEqual(one, three)
        self.assertEqual(one, five)
        self.assertEqual(one, 31)

    def test_a_day_with_nothing_due_costs_four_queries(self) -> None:
        with CaptureQueriesContext(connection) as captured:
            with frozen(at(self.day(0), settings.REMINDER_SEND_HOUR)):
                tasks.send_tenant_reminders(str(self.tenant.id))
        # The tenant's activation, the tenant row, the bank's lock and the one case query.
        self.assertEqual(statements(captured), 4)


class OneBankPerTask(ReminderTestCase):
    def test_a_banks_task_reads_none_of_another_banks_cases(self) -> None:
        other = factories.tenant(slug="reminders-other", timezone=HELSINKI)
        stranger = factories.member_user(other, roles=("compliance_officer",))
        theirs = self.case(at(self.day(3), 12), tenant=other)
        self.run_on(0)
        tenancy.activate(other.id)
        self.assertFalse(Notification.objects.filter(subject_id=theirs.id).exists())
        self.assertFalse(Notification.objects.filter(user=stranger).exists())
        self.assertEqual(MockMailer.sent, [])

    def test_the_beat_hands_each_bank_on_by_itself_at_its_own_hour(self) -> None:
        stockholm = factories.tenant(slug="reminders-stockholm", timezone="Europe/Stockholm")
        moment = at(self.day(0), settings.REMINDER_SEND_HOUR)
        with frozen(moment), mock.patch.object(tasks.send_tenant_reminders, "delay") as delay:
            tasks.send_reminders()
        self.assertEqual([call.args for call in delay.call_args_list], [(str(self.tenant.id),)])
        with frozen(at(self.day(0), settings.REMINDER_SEND_HOUR, "Europe/Stockholm")), mock.patch.object(
            tasks.send_tenant_reminders, "delay"
        ) as delay:
            tasks.send_reminders()
        self.assertEqual([call.args for call in delay.call_args_list], [(str(stockholm.id),)])

    def test_a_deactivated_bank_is_not_handed_on(self) -> None:
        from apps.shared.models import TenantStatus

        Tenant.objects.filter(pk=self.tenant.pk).update(status=TenantStatus.DEACTIVATED.value)
        self.assertEqual(reminders.tenants_at_send_hour(at(self.day(0), settings.REMINDER_SEND_HOUR)), [])
