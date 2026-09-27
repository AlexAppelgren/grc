"""The weekly briefing (HOM-02, WAT-05, FP-03, AUD-01): the running week, the snapshot of a
week that was sent, and the job that turns one into the other.

What is proved here, one class per question:

- **The running week.** Which changes belong to it, in which order, and that its lead is the
  same change Today's lead card names.
- **The snapshot.** That a week is read back as it was sent, that a change sighted after the
  mail went out never joins it, and that the database refuses to rewrite it even if code
  tried.
- **The job.** One mail per eligible person in that person's own language, none for anybody
  else, one audit row, and a second run that sends nothing and writes nothing.
- **What may leave by mail.** An unconfirmed "So what?" never does, and no case note, owner
  or other bank's row ever does.

Nothing here depends on the day the suite runs: the clock is frozen at a fixed instant and
every date is written out (playbook 8.3).
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest import mock

from django.conf import settings
from django.db import transaction
from django.db.utils import DatabaseError
from django.test import TestCase

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.home import briefing as briefing_reads
from apps.home import logic, mail, tasks
from apps.home.models import Briefing, BriefingItem
from apps.identity.models import Membership, TenantRole, User
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange

CURRENT = "/api/v1/briefings/current"
D = datetime.date

# A fixed instant, never "now". In Stockholm it is already 1 October 2026, a Thursday, so
# the running week began on Monday 28 September and the week before it on Monday 21st.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
THIS_WEEK_START = D(2026, 9, 28)
LAST_WEEK_START = D(2026, 9, 21)
# When a change was sighted, named rather than derived: which week a change belongs to is
# the whole of the selection rule, and a counter would hide it.
SIGHTED_THIS_WEEK = datetime.datetime(2026, 9, 29, 9, 0, tzinfo=datetime.UTC)
SIGHTED_LAST_WEEK = datetime.datetime(2026, 9, 22, 9, 0, tzinfo=datetime.UTC)
KEY_DATE = D(2026, 10, 15)

# The Monday 07:00 the job runs at, as the designed briefing screen tells people to expect.
# It is 07:00 in Stockholm, which is 05:00 UTC while summer time lasts. This is the Monday
# that opens the running week, so the week it sums up is the one that began on the 21st.
MONDAY_MORNING = datetime.datetime(2026, 9, 28, 5, 0, tzinfo=datetime.UTC)
SENT_AT = "2026-09-28T05:00:00Z"


def a_change(
    *,
    title: str,
    urgency: str = "act_now",
    first_seen_at: datetime.datetime = SIGHTED_THIS_WEEK,
    key_date: datetime.date | None = KEY_DATE,
) -> RegulatoryChange:
    return watch_build.change(
        title=title, urgency=urgency, key_date=key_date, key_date_label="In force", first_seen_at=first_seen_at
    )


class TheRunningWeek(TestCase):
    """`GET /briefings/current` (HOM-02, FP-03)."""

    tenant: Tenant
    reader: User
    lead: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="briefing-now", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        # Every change gets a key date of its own, so what the roadmap makes of them is
        # decided by a date this file names and never by the order of a random uuid.
        cls.lead = cases_build.case(cls.tenant, a_change(title="Research payments", key_date=KEY_DATE))
        cases_build.case(
            cls.tenant,
            a_change(title="Reporting", urgency="six_months_plus", key_date=KEY_DATE + datetime.timedelta(days=1)),
            urgency="six_months_plus",
        )
        # Three that must not be in the week, each for a reason of its own. The first is
        # still on the roadmap: belonging to last week is a reason not to be in this week's
        # briefing, never a reason to leave the calendar.
        cases_build.case(
            cls.tenant,
            a_change(
                title="Last week's news",
                first_seen_at=SIGHTED_LAST_WEEK,
                key_date=KEY_DATE + datetime.timedelta(days=2),
            ),
        )
        cases_build.case(
            cls.tenant,
            a_change(title="Insurance", key_date=KEY_DATE + datetime.timedelta(days=3)),
            footprint_match=False,
        )
        finished = cases_build.case(
            cls.tenant, a_change(title="Settled", key_date=KEY_DATE + datetime.timedelta(days=4))
        )
        cases_build.in_category(finished, CaseStatusCategory.DISMISSED)

    def read(self) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            return briefing_reads.current_briefing(self.tenant, ["en"])

    def test_the_week_is_the_banks_own_monday_to_sunday(self) -> None:
        answer = self.read()
        self.assertEqual((answer.week_start, answer.week_end), (THIS_WEEK_START, D(2026, 10, 4)))

    def test_it_holds_the_weeks_open_in_scope_changes_most_urgent_first(self) -> None:
        self.assertEqual([item.title for item in self.read().items], ["Research payments", "Reporting"])

    def test_what_is_not_in_it_and_why(self) -> None:
        """A change sighted last week belongs to last week's briefing; a case the bank has
        dismissed is finished; a change outside the regulatory scope was never ours (FP-03)."""
        listed = [item.title for item in self.read().items]
        for absent in ("Last week's news", "Insurance", "Settled"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, listed)

    def test_the_lead_is_the_same_change_todays_lead_card_names(self) -> None:
        """The two come from one selector, so the page, the panel and the mail can never
        name three different changes."""
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            today = logic.home_today(self.tenant, ["en"], watch_reader=True)
        lead = self.read().lead
        assert lead is not None and today.lead is not None
        self.assertEqual(lead.id, today.lead.id)
        self.assertEqual(lead.title, "Research payments")

    def test_the_running_week_has_not_been_sent_and_stores_nothing(self) -> None:
        self.assertIsNone(self.read().email_sent_at)
        tenancy.activate(self.tenant.id)
        self.assertEqual(Briefing.objects.count(), 0, "the running week is computed live and stored nowhere")

    def test_it_is_capped_and_what_is_left_out_stays_on_the_feed(self) -> None:
        with mock.patch.object(settings, "BRIEFING_MAX_ITEMS", 1):
            self.assertEqual([item.title for item in self.read().items], ["Research payments"])

    def test_a_quiet_week_is_a_200_with_no_lead_rather_than_a_404(self) -> None:
        quiet = factories.tenant(slug="briefing-quiet", timezone="Europe/Stockholm")
        newcomer = factories.member_user(quiet, roles=("reader",))
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            body = self.client.get(CURRENT, **sign_in(newcomer, tenant=quiet)).json()
        self.assertEqual((body["items"], body["lead"]), ([], None))
        self.assertEqual(body["weekStart"], "2026-09-28")

    def test_a_reader_gets_the_week_in_camel_case(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            response = self.client.get(CURRENT, **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["weekStart"], body["weekEnd"]), ("2026-09-28", "2026-10-04"))
        self.assertEqual(body["lead"]["title"], "Research payments")
        self.assertIsNone(body["emailSentAt"])
        # "Coming up" is the roadmap's own next dates, not the week's: last week's news is
        # dated ahead and belongs on the calendar even though it does not belong in the week.
        self.assertEqual(
            [item["title"] for item in body["comingUp"]],
            ["Research payments", "Reporting", "Last week's news"],
        )


class TheWeeklyJob(TestCase):
    """The `@tenant_task` that snapshots a week and mails it (HOM-02, AUD-01)."""

    tenant: Tenant
    other: Tenant
    reader: User
    swede: User
    limited: User
    gone: User
    lead: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="briefing-job", timezone="Europe/Stockholm")
        cls.other = factories.tenant(slug="briefing-other", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.swede = factories.member_user(cls.tenant, roles=("reader",))
        swedish = factories.language("sv")
        User.objects.filter(pk=cls.swede.pk).update(locale=swedish)
        # One member who may not read the watch feed, and one who has left.
        with transaction.atomic():
            tenancy.activate(cls.tenant.id)
            TenantRole.objects.create(tenant=cls.tenant, key="roadmap-only", permissions=[perms.ROADMAP_READ])
        cls.limited = factories.member(cls.tenant, roles=("roadmap-only",)).user
        leaver = factories.member(cls.tenant, roles=("reader",))
        cls.gone = leaver.user
        with transaction.atomic():
            tenancy.activate(cls.tenant.id)
            Membership.objects.filter(pk=leaver.pk).update(deactivated_at=INSTANT)
        # Last week's changes: the lead with a confirmed "So what?", and a calmer one.
        lead_change = a_change(title="Research payments", first_seen_at=SIGHTED_LAST_WEEK)
        cls.lead = cases_build.case(cls.tenant, lead_change, so_what_text="Three regulations change for us.")
        cases_build.case(
            cls.tenant,
            a_change(title="Reporting", urgency="six_months_plus", first_seen_at=SIGHTED_LAST_WEEK),
            urgency="six_months_plus",
        )
        # The other bank's own week, which must never reach this one's briefing.
        cases_build.case(cls.other, a_change(title="Another bank's reform", first_seen_at=SIGHTED_LAST_WEEK))
        tenancy.activate(cls.tenant.id)
        ChangeCase.objects.filter(pk=cls.lead.pk).update(
            so_what_confirmed=True, so_what_confirmed_by=cls.reader, so_what_confirmed_at=INSTANT
        )

    def setUp(self) -> None:
        MockMailer.reset()

    def run_job(self, tenant: Tenant | None = None) -> None:
        with mock.patch("django.utils.timezone.now", return_value=MONDAY_MORNING):
            tasks.send_weekly_briefing((tenant or self.tenant).id)

    def test_it_snapshots_the_week_that_has_just_ended_with_its_ranks(self) -> None:
        self.run_job()
        tenancy.activate(self.tenant.id)
        briefing = Briefing.objects.get(week_start=LAST_WEEK_START)
        self.assertIsNotNone(briefing.email_sent_at)
        items = list(BriefingItem.objects.filter(briefing=briefing).select_related("case__change"))
        self.assertEqual([(item.rank, item.case.change.title) for item in items], [(1, "Research payments"), (2, "Reporting")])

    def test_each_case_is_stamped_with_the_week_that_first_carried_it(self) -> None:
        self.run_job()
        tenancy.activate(self.tenant.id)
        self.assertEqual(ChangeCase.objects.get(pk=self.lead.pk).briefing_week, LAST_WEEK_START)

    def test_one_mail_per_eligible_member_and_none_for_anybody_else(self) -> None:
        """Permissions, never role names: the member who may not read the watch feed and the
        member who has left both get nothing, because neither may open what the mail links to."""
        self.run_job()
        self.assertEqual(
            sorted(sent.to for sent in MockMailer.sent), sorted([self.reader.email, self.swede.email])
        )

    def test_a_member_who_switched_the_briefing_off_gets_no_mail(self) -> None:
        """COL-02: `weeklyBriefing` off leaves that person out; an explicit true and a key
        never set both still get the mail."""
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(tenant=self.tenant, user=self.swede).update(notification_prefs={"weeklyBriefing": False})
        Membership.objects.filter(tenant=self.tenant, user=self.reader).update(notification_prefs={"weeklyBriefing": True, "mentions": False})

        self.run_job()

        self.assertEqual([sent.to for sent in MockMailer.sent], [self.reader.email])

    def test_each_person_gets_their_own_language(self) -> None:
        self.run_job()
        by_address = {sent.to: sent for sent in MockMailer.sent}
        self.assertIn("This week in regulation", by_address[self.reader.email].subject)
        self.assertIn("Veckans regelnyheter", by_address[self.swede.email].subject)

    def test_the_mail_carries_the_weeks_titles_and_the_confirmed_so_what(self) -> None:
        self.run_job()
        body = MockMailer.sent[0].body
        self.assertIn("Research payments", body)
        self.assertIn("Reporting", body)
        self.assertIn("Three regulations change for us.", body)
        self.assertIn(f"/briefing/{LAST_WEEK_START.isoformat()}", body)

    def test_no_row_of_another_bank_reaches_this_banks_briefing(self) -> None:
        self.run_job()
        tenancy.activate(self.tenant.id)
        briefing = Briefing.objects.get(week_start=LAST_WEEK_START)
        titles = [item.case.change.title for item in BriefingItem.objects.filter(briefing=briefing).select_related("case__change")]
        self.assertNotIn("Another bank's reform", titles)
        self.assertNotIn(b"Another bank's reform", MockMailer.sent[0].body.encode())

    def test_running_it_twice_sends_one_mail_and_writes_one_snapshot(self) -> None:
        self.run_job()
        self.run_job()
        tenancy.activate(self.tenant.id)
        self.assertEqual(Briefing.objects.filter(week_start=LAST_WEEK_START).count(), 1)
        self.assertEqual(len(MockMailer.sent), 2, "two recipients, one mail each, and no second round")

    def test_it_writes_one_audit_row_naming_the_week_and_no_tenant_content(self) -> None:
        self.run_job()
        tenancy.activate(self.tenant.id)
        events = list(AuditEvent.objects.filter(tenant=self.tenant, action=tasks.SENT))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.subject_title, LAST_WEEK_START.isoformat())
        self.assertEqual(event.after, {"weekStart": "2026-09-21", "items": 2, "recipients": 2})
        self.assertNotIn("Research payments", str(event.after) + event.summary)

    def test_a_quiet_week_writes_nothing_and_sends_nothing(self) -> None:
        quiet = factories.tenant(slug="briefing-job-quiet", timezone="Europe/Stockholm")
        factories.member_user(quiet, roles=("reader",))
        self.run_job(quiet)
        tenancy.activate(quiet.id)
        self.assertEqual(Briefing.objects.count(), 0)
        self.assertEqual(MockMailer.sent, [])


class AnUnconfirmedDraftNeverLeavesByMail(TestCase):
    """WAT-05: an agent's "So what?" is labelled on screen until a person confirms it, and a
    mail carries no label a reader can see — so it does not travel at all."""

    tenant: Tenant

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="briefing-draft", timezone="Europe/Stockholm")
        factories.member_user(cls.tenant, roles=("reader",))
        # The same unconfirmed draft on two weeks: last week's goes out by mail, this week's
        # is what the screen renders. One case cannot be in both weeks, and the point of the
        # scenario is that the two surfaces treat the same text differently.
        cases_build.case(
            cls.tenant,
            a_change(title="Research payments", first_seen_at=SIGHTED_LAST_WEEK),
            so_what_text="An agent thinks this changes how we pay for research.",
        )
        cases_build.case(
            cls.tenant,
            a_change(title="Reporting", first_seen_at=SIGHTED_THIS_WEEK),
            so_what_text="An agent thinks this changes how we pay for research.",
        )

    def setUp(self) -> None:
        MockMailer.reset()

    def test_the_draft_is_absent_from_the_body_while_nobody_has_confirmed_it(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=MONDAY_MORNING):
            tasks.send_weekly_briefing(self.tenant.id)
        body = MockMailer.sent[0].body
        self.assertIn("Research payments", body, "the library's own title still travels")
        self.assertNotIn("An agent thinks", body)

    def test_the_screen_still_shows_it_with_the_fact_that_it_is_unconfirmed(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            lead = briefing_reads.current_briefing(self.tenant, ["en"]).lead
        assert lead is not None and lead.case is not None
        self.assertEqual(lead.case.so_what_text, "An agent thinks this changes how we pay for research.")
        self.assertFalse(lead.case.so_what_confirmed)


class TheSnapshotIsWhatWasSent(TestCase):
    """`GET /briefings/{weekStart}` (HOM-02): a week reads back as it was sent, and nothing
    rewrites it."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="briefing-past", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cases_build.case(cls.tenant, a_change(title="Research payments", first_seen_at=SIGHTED_LAST_WEEK))

    def send_last_week(self) -> None:
        MockMailer.reset()
        with mock.patch("django.utils.timezone.now", return_value=MONDAY_MORNING):
            tasks.send_weekly_briefing(self.tenant.id)

    def get(self, week: str) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            return self.client.get(f"/api/v1/briefings/{week}", **sign_in(self.reader, tenant=self.tenant))

    def test_a_sent_week_reads_back_with_its_items_and_the_time_it_went_out(self) -> None:
        self.send_last_week()
        body = self.get("2026-09-21").json()
        self.assertEqual((body["weekStart"], body["weekEnd"]), ("2026-09-21", "2026-09-27"))
        self.assertEqual([item["title"] for item in body["items"]], ["Research payments"])
        self.assertEqual(body["emailSentAt"], SENT_AT)

    def test_a_later_change_to_the_feed_does_not_alter_the_snapshot(self) -> None:
        """The whole point of storing it. A reform sighted inside that week but registered
        after the mail went out is on the feed and not in what anybody was sent.

        The week's items and its lead are what the snapshot fixes. "Coming up" beside them is
        the live roadmap and moves as dates do, which is why the comparison is of the items
        and not of the whole body: a briefing says what a week held, not what the calendar
        looked like the morning it went out.
        """
        self.send_last_week()
        before = self.get("2026-09-21").json()
        cases_build.case(self.tenant, a_change(title="Registered afterwards", first_seen_at=SIGHTED_LAST_WEEK))
        after = self.get("2026-09-21").json()
        self.assertEqual(after["items"], before["items"])
        self.assertEqual(after["lead"], before["lead"])
        self.assertNotIn("Registered afterwards", [item["title"] for item in after["items"]])

    def test_the_database_refuses_to_rewrite_a_sent_briefings_items(self) -> None:
        """Append-only by trigger, not by convention: even code that meant to would fail.
        `_raw_delete` goes round the Python guard on purpose, so what refuses here is the
        database itself."""
        self.send_last_week()
        tenancy.activate(self.tenant.id)
        item = BriefingItem.objects.first()
        assert item is not None
        with self.assertRaisesMessage(DatabaseError, "append-only"), transaction.atomic():
            BriefingItem.objects.filter(pk=item.pk)._raw_delete(using="default")  # noqa: SLF001 the trigger is the subject

    def test_a_week_nobody_was_sent_and_a_date_that_is_not_a_monday_answer_the_same_404(self) -> None:
        self.send_last_week()
        for week in ("2026-09-14", "2026-09-23"):
            with self.subTest(week=week):
                refused = self.get(week)
                self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))

    def test_another_banks_week_is_not_addressable_at_all(self) -> None:
        self.send_last_week()
        elsewhere = factories.tenant(slug="briefing-elsewhere", timezone="Europe/Stockholm")
        stranger = factories.member_user(elsewhere, roles=("reader",))
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            refused = self.client.get(
                "/api/v1/briefings/2026-09-21", **sign_in(stranger, tenant=elsewhere)
            )
        self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))


class TheMailText(TestCase):
    """`home/mail.py` on its own: what the composer puts in and leaves out."""

    def compose(self, **overrides: Any) -> Any:
        fields: dict[str, Any] = {
            "to": "person@test.example",
            "locale": "en",
            "tenant_name": "Example Bank AB",
            "week_start": LAST_WEEK_START,
            "week_end": D(2026, 9, 27),
            "titles": ["Research payments", "Reporting"],
            "confirmed_so_what": "Three regulations change for us.",
        }
        return mail.weekly_briefing(**{**fields, **overrides})

    def test_a_language_the_catalog_does_not_hold_falls_back_to_english(self) -> None:
        """Danish, Norwegian and Finnish arrive with the rest of the product's mail in
        chunk 10; until then a reader gets English rather than nothing."""
        for locale in ("da", "nb", "fi", None):
            with self.subTest(locale=locale):
                self.assertEqual(self.compose(locale=locale).subject, self.compose(locale="en").subject)

    def test_an_empty_so_what_leaves_the_line_out_rather_than_sending_an_empty_one(self) -> None:
        body = self.compose(confirmed_so_what="").body
        self.assertNotIn("What it means for us", body)
        self.assertIn("Research payments", body)

    def test_a_quiet_week_says_so_and_still_links_to_the_briefing(self) -> None:
        body = self.compose(titles=[], confirmed_so_what="").body
        self.assertIn("Nothing new matched your regulatory scope", body)
        self.assertIn("/briefing/2026-09-21", body)
