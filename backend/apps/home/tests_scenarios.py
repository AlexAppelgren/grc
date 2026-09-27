"""Scenario stubs for the home app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: HOM.
"""

import datetime
from unittest import mock, skip
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase

from apps.cases import testing as cases_build
from apps.home import tasks
from apps.home.tests_my_work_api import run_hom_s7, run_hom_s8, run_hom_s9, run_hom_s10, run_hom_s11, run_hom_s12
from apps.home.tests_my_work_cases import run_hom_s14
from apps.shared import factories, permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import AuditEvent
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    agent_principal,
    sign_in,
    stub_api_key,
)
from apps.watch import testing as watch_build
from apps.watch.models import CheckStatus

# A fixed instant and fixed dates, never "now": a quarter boundary must not decide what a
# scenario sees (playbook 8.3). At this instant the bank's own day is 1 October 2026, and
# the ISO week it falls in began on Monday 28 September.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
SIGHTED_THIS_WEEK = datetime.datetime(2026, 9, 29, 9, 0, tzinfo=datetime.UTC)
SIGHTED_LAST_WEEK = datetime.datetime(2026, 9, 22, 9, 0, tzinfo=datetime.UTC)
# The Monday 07:00 the weekly job runs at, as the designed briefing screen tells people to
# expect. It is 07:00 in Stockholm, which is 05:00 UTC while summer time lasts. This is the
# Monday that opens the running week, so the week it sums up began on the 21st.
MONDAY_MORNING = datetime.datetime(2026, 9, 28, 5, 0, tzinfo=datetime.UTC)
THIS_QUARTER = datetime.date(2026, 10, 15)
NEXT_QUARTER = datetime.date(2027, 1, 20)


class HomeScenarioTests(TestCase):
    """Scenario tests for apps.home, one method per @integration scenario."""

    def test_hom_s1(self) -> None:
        """HOM-S1

        Today shows the next dates, the lead item, what needs a decision and source
        health (HOM-01).

        The pills and the panels are the journey's half. What is proved here is what the
        screen draws them from: the next dates in the roadmap's own order with this bank's
        urgency on each, the week's lead change, how the source watching is going, and that
        a reader who may not see a panel still gets the page.

        Two notes on the steps that are not asserted here. Where the bank stands arrives
        with the register in chunk 8 (the note under HOM-S1 in app.md), so `Home` carries no
        such field and this test pins its absence rather than a zero. What needs a decision
        is the `counts` object on `GET /me` (D-23), which `f03-T48` builds and proves in
        `apps/identity/tests_me_counts.py`; the half that belongs to this route is that
        `Home` does not answer it a second time.
        """
        watch_build.seed_watch_reference()
        # The registry before any bank: a source is a library row, and the only session its
        # write rule accepts is one with no tenant activated (WAT-06, H15).
        healthy = watch_build.source(name="fi.se hom-s1 healthy")
        watch_build.source_check(healthy, status=CheckStatus.OK, checked_at=INSTANT)
        broken = watch_build.source(name="fi.se hom-s1 broken")
        watch_build.source_check(broken, status=CheckStatus.FAILED, error="502 after three retries", checked_at=INSTANT)
        tenant = factories.tenant(slug="hom-s1", timezone="Europe/Stockholm")
        reader = factories.member_user(tenant, roles=("reader",))
        lead = watch_build.change(
            title="FI adopts amended rules on paying for investment research",
            key_date=THIS_QUARTER,
            key_date_label="In force",
            first_seen_at=SIGHTED_THIS_WEEK,
        )
        later = watch_build.change(
            title="Amended reporting of securities financing transactions",
            key_date=NEXT_QUARTER,
            key_date_label="Applies",
            urgency="six_months_plus",
            first_seen_at=SIGHTED_THIS_WEEK,
        )
        cases_build.case(tenant, lead)
        cases_build.case(tenant, later, urgency="six_months_plus")

        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            response = self.client.get("/api/v1/home", **sign_in(reader, tenant=tenant))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["date"], "2026-10-01")
        # The next dates in order, each with the bank's own urgency for the pill.
        self.assertEqual([item["title"] for item in body["comingUp"]], [lead.title, later.title])
        self.assertEqual([item["urgency"]["key"] for item in body["comingUp"]], ["act_now", "six_months_plus"])
        self.assertEqual(body["roadmapCount"], 2)
        # The lead change the screen marks with the brand pill "Lead".
        self.assertEqual(body["lead"]["title"], lead.title)
        self.assertEqual(body["lead"]["case"]["urgency"]["key"], "act_now")
        # Source coverage: one source checked, one failure named.
        self.assertEqual((body["sources"]["checked"], body["sources"]["total"]), (1, 2))
        self.assertEqual([row["source"]["name"] for row in body["sources"]["failed"]], [broken.name])
        # Neither panel that belongs to another chunk is answered here.
        self.assertNotIn("decideNow", body)
        self.assertNotIn("standing", body)
        # One fan-out of independent calls: the four reads cost a fixed number of queries
        # and none of them is the input to another (apps/home/tests_home.py pins the number
        # at two sizes; here the point is that the route answers from one call at all).
        self.assertEqual(response["Server-Timing"].split(";")[0], "app")

    def test_hom_s3(self) -> None:
        """HOM-S3

        The weekly briefing is reachable from home and snapshotted when emailed (HOM-02).

        Opening the briefing from Today's panel is the journey's half. What is proved here
        is the chain behind it: the running week the panel shows, the job that snapshots the
        week just ended and mails a link to it, and the last line of the scenario — that a
        later change to the feed leaves what was sent exactly as it was.
        """
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="hom-s3", timezone="Europe/Stockholm")
        reader = factories.member_user(tenant, roles=("reader",))
        last_week = watch_build.change(
            title="FI adopts amended rules on paying for investment research",
            key_date=THIS_QUARTER,
            key_date_label="In force",
            first_seen_at=SIGHTED_LAST_WEEK,
        )
        cases_build.case(tenant, last_week, so_what_text="Three regulations change for us.")
        this_week = watch_build.change(
            title="Amended reporting of securities financing transactions",
            key_date=NEXT_QUARTER,
            key_date_label="Applies",
            first_seen_at=SIGHTED_THIS_WEEK,
        )
        cases_build.case(tenant, this_week)

        # Today's panel shows the running week, computed live and stored nowhere. The
        # session is minted at the frozen instant too: one created at the real clock would
        # be days old to the request and answer 401 (playbook 8.3).
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            headers = sign_in(reader, tenant=tenant)
            running = self.client.get("/api/v1/briefings/current", **headers)
        self.assertEqual(running.status_code, 200)
        self.assertEqual(running.json()["weekStart"], "2026-09-28")
        self.assertEqual([item["title"] for item in running.json()["items"]], [this_week.title])
        self.assertIsNone(running.json()["emailSentAt"])

        # The weekly job runs on the bank's own Monday morning and snapshots the week that
        # has just ended, mailing a link to it.
        MockMailer.reset()
        with mock.patch("django.utils.timezone.now", return_value=MONDAY_MORNING):
            tasks.send_weekly_briefing(tenant.id)
        self.assertEqual([sent.to for sent in MockMailer.sent], [reader.email])
        self.assertIn("/briefing/2026-09-21", MockMailer.sent[0].body)

        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            snapshot = self.client.get("/api/v1/briefings/2026-09-21", **headers)
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual([item["title"] for item in snapshot.json()["items"]], [last_week.title])
        self.assertEqual(snapshot.json()["emailSentAt"], "2026-09-28T05:00:00Z")

        # A later change to the feed does not alter what was sent: a reform sighted inside
        # that week but registered after the mail went out is on the feed and not in the
        # snapshot. What the snapshot fixes is the week's items and its lead; "Coming up"
        # beside them is the live roadmap and moves as dates do.
        afterwards = watch_build.change(
            title="Guidance on outsourcing arrangements",
            key_date=THIS_QUARTER + datetime.timedelta(days=1),
            first_seen_at=SIGHTED_LAST_WEEK,
        )
        cases_build.case(tenant, afterwards)
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            again = self.client.get("/api/v1/briefings/2026-09-21", **headers)
        self.assertEqual(again.json()["items"], snapshot.json()["items"])
        self.assertEqual(again.json()["lead"], snapshot.json()["lead"])
        self.assertNotIn(afterwards.title, [item["title"] for item in again.json()["items"]])

    def test_hom_s4(self) -> None:
        """HOM-S4

        The roadmap shows the quarters ahead with their regulatory dates (HOM-03, FP-03).

        The expanding card is the journey's half. What is proved here is what the screen
        draws it from: two quarters in one roster, the items inside each in date order with
        the bank's own urgency on every one, and a dated change outside the bank's
        regulatory scope absent from both.
        """
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="hom-s4", timezone="Europe/Stockholm")
        reader = factories.member_user(tenant, roles=("reader",))
        soon = watch_build.change(
            title="FI adopts amended rules on paying for investment research",
            key_date=THIS_QUARTER,
            key_date_label="In force",
        )
        later = watch_build.change(
            title="Amended reporting of securities financing transactions",
            key_date=NEXT_QUARTER,
            key_date_label="Applies",
            urgency="six_months_plus",
        )
        elsewhere = watch_build.change(title="Insurance distribution guidance", key_date=THIS_QUARTER)
        cases_build.case(tenant, soon)
        cases_build.case(tenant, later, urgency="six_months_plus")
        cases_build.case(tenant, elsewhere, footprint_match=False)

        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            response = self.client.get("/api/v1/roadmap", **sign_in(reader, tenant=tenant))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["quarters"], ["2026-Q4", "2027-Q1"])
        self.assertEqual([item["title"] for item in body["items"]], [soon.title, later.title])
        self.assertEqual([item["quarter"] for item in body["items"]], ["2026-Q4", "2027-Q1"])
        self.assertEqual([item["urgency"]["key"] for item in body["items"]], ["act_now", "six_months_plus"])
        self.assertEqual([item["label"] for item in body["items"]], ["In force", "Applies"])
        self.assertNotIn(elsewhere.title, [item["title"] for item in body["items"]])

    def test_hom_s5(self) -> None:
        """HOM-S5

        Upcoming changes are public facts and the calendar feed is revocable (HOM-04).
        Operations: `listUpcoming`, `listCalendarFeeds`, `createCalendarFeed`,
        `revokeCalendarFeed`, `getCalendarIcs`.

        Both halves, end to end and in the scenario's own order: an agent's key reads the
        public list and finds library facts and no bank in them, a person subscribes and
        gets one address that serves their bank's roadmap as a calendar, and revoking it
        makes that address answer 404 from the next fetch on.

        What each half rests on is proved next door and not repeated here:
        `tests_calendar.py` holds the shape of the public row and two banks reading
        byte-identical bodies; `tests_feed.py` holds the one 404 an unknown, revoked or
        expired token shares, the four rules that stop a subscription by themselves, what a
        calendar event may carry, the cap and the proof that no token, prefix or secret
        reaches a log line.

        Every step runs under one frozen clock: the session is minted at the instant, and
        a call made on the real clock would find it older than a session may be as soon
        as the real clock passed that instant (playbook 8.3).
        """
        watch_build.seed_watch_reference()
        tenant = factories.tenant(slug="hom-s5", timezone="Europe/Stockholm")
        reader = factories.member_user(tenant, roles=("reader",))
        change = watch_build.change(
            title="FI adopts amended rules on paying for investment research",
            key_date=THIS_QUARTER,
            key_date_label="In force",
        )
        # The bank's own judgement on that reform. Nothing below may carry it out.
        cases_build.case(tenant, change, so_what_text="Three regulations change for us.")

        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            # The agent reads the public list with its own key: library facts, and no case,
            # footprint or judgement of this bank's.
            with stub_api_key(agent_principal(scopes={perms.SCOPE_UPCOMING_READ})):
                public = self.client.get("/api/v1/upcoming", HTTP_X_API_KEY=API_KEY_FOR_TESTS)
            self.assertEqual(public.status_code, 200)
            row = public.json()[0]
            self.assertEqual((row["title"], row["keyDate"]), (change.title, "2026-10-15"))
            self.assertEqual(row["changeType"]["key"], "adopted")
            self.assertNotIn(b"Three regulations change for us.", public.content)

            # The person subscribes. The address comes back once and carries the token.
            headers = sign_in(reader, tenant=tenant)
            created = self.client.post(
                "/api/v1/calendar-feeds", data={}, content_type="application/json", **headers
            )
            self.assertEqual(created.status_code, 201)
            feed_id = created.json()["feed"]["id"]
            token = parse_qs(urlsplit(created.json()["url"]).query)["token"][0]
            self.assertEqual(
                {event.action for event in AuditEvent.objects.filter(subject_type="calendar_feed")},
                {"calendar_feed.created"},
            )

            # The address serves their roadmap as a calendar: the date, what the date is and
            # the reform's title, and nothing the bank decided about it.
            calendar = self.client.get("/api/v1/calendar/feed.ics", {"token": token})
            self.assertEqual(calendar.status_code, 200)
            self.assertEqual(calendar.headers["Content-Type"], "text/calendar; charset=utf-8")
            body = calendar.content.decode()
            self.assertIn("DTSTART;VALUE=DATE:20261015", body)
            self.assertIn(f"SUMMARY:In force: {change.title}", body)
            self.assertNotIn("Three regulations change for us.", body)
            self.assertNotIn(tenant.name, body)

            # The list shows the subscription and never the address.
            listed = self.client.get("/api/v1/calendar-feeds", **headers).json()
            self.assertEqual([feed["id"] for feed in listed], [feed_id])
            self.assertNotIn(token, str(listed))

            # Revoking it makes the address answer 404 from the next fetch on.
            revoked = self.client.delete(f"/api/v1/calendar-feeds/{feed_id}", **headers)
            self.assertEqual(revoked.status_code, 204)
            gone = self.client.get("/api/v1/calendar/feed.ics", {"token": token})
            self.assertEqual((gone.status_code, gone.json()["code"]), (404, "not_found"))

    def test_hom_s7(self) -> None:
        """HOM-S7

        My work lists what I'm responsible for or take part in, most urgent first (HOM-05, AC-HOM1).
        Operations: `getMyWork`.
        """
        run_hom_s7(self)

    def test_hom_s8(self) -> None:
        """HOM-S8

        Compliant and per-entity reviews reach My work (HOM-05, AC-HOM1).
        Operations: `getMyWork`.
        """
        run_hom_s8(self)

    def test_hom_s9(self) -> None:
        """HOM-S9

        A department head sees the department's work, naming who is responsible (HOM-05, TEN-02, TEN-03).
        Operations: `getMyWork`.
        """
        run_hom_s9(self)

    def test_hom_s10(self) -> None:
        """HOM-S10

        My work applies each record's read permission to rows and counts, and ignores the footprint (HOM-05, AC-HOM1).
        Operations: `getMyWork`.
        """
        run_hom_s10(self)

    def test_hom_s11(self) -> None:
        """HOM-S11

        Changes on your items are confirmed links, new versions and colleagues' comments only (HOM-05).
        Operations: `getMyWork`.
        """
        run_hom_s11(self)

    def test_hom_s12(self) -> None:
        """HOM-S12

        My work answers within budget for a fifty-member department (HOM-05, NFR-02).
        Operations: `getMyWork`.
        """
        run_hom_s12(self)

    def test_hom_s14(self) -> None:
        """HOM-S14

        Case work reaches My work (HOM-05).
        """
        run_hom_s14(self)

    @skip("pending: HOM-S15 (HOM-03, TEN-02, chunk 8)")
    def test_hom_s15(self) -> None:
        """HOM-S15

        A certificate's expiry and next audit are our deadlines, never in the calendar feed (HOM-03, HOM-04, TEN-02, AC-TEN1).
        """
