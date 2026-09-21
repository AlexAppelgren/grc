"""Today in one fan-out (HOM-01, FP-03, NFR-02): what the screen is given, what a reader
who may not see a panel is given instead, and what the call costs.

What is proved here, one class per question:

- **What is on it.** The bank's own date, the roadmap's first items with the whole count
  beside them, the week's lead change and the health of the sources — and `comingUp` is the
  same rows `GET /roadmap` answers, proved by calling both.
- **Which week leads.** The lead is the most urgent open, in-scope change sighted inside the
  running ISO week in the bank's own time zone. A change from last week, a finished case and
  a change outside the scope each fail to lead, and each for its own reason.
- **What a reader may see.** A person without `watch.read` gets Today with `lead` and
  `sources` null and a 200, never a 403 that would take the whole page away.
- **What it costs.** The same queries for one date and for thirty, pinned at two sizes so an
  N+1 shows up as a number, and the route inside the API budget on a real bank's Today.

Nothing here depends on the day the suite runs: the clock is frozen at a fixed instant and
every date is written out (playbook 8.3).
"""

from __future__ import annotations

import datetime
import sys
import time
from typing import Any
from unittest import mock

from django.conf import settings
from django.db import transaction
from django.test import TestCase

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.home import logic, roadmap
from apps.home.schemas import HomeRoadmapQuery
from apps.identity.models import TenantRole, User
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import testing as watch_build
from apps.watch.models import CheckFrequency, CheckStatus, RegulatoryChange

URL = "/api/v1/home"
D = datetime.date

# A fixed instant, never "now": at 22:30 UTC on 30 September it is already 1 October in
# Stockholm, and the ISO week that day falls in began on Monday 28 September.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
STOCKHOLM_TODAY = D(2026, 10, 1)
WEEK_START = D(2026, 9, 28)

# When a change was sighted. Named rather than derived, because which week a change belongs
# to is the whole of the lead rule and a counter would hide it.
THIS_WEEK = datetime.datetime(2026, 9, 29, 9, 0, tzinfo=datetime.UTC)
LAST_WEEK = datetime.datetime(2026, 9, 22, 9, 0, tzinfo=datetime.UTC)

THIS_QUARTER = D(2026, 10, 15)
NEXT_QUARTER = D(2027, 1, 20)

# Sixteen queries on this file's fixture, measured 2026-09-21 and pinned so an N+1 shows up
# as a number (playbook 10). What the test below demands is not the number itself but that
# it does not move between one case and thirty, which is why it asks at both sizes:
#   the roadmap's first items and its count (5): the page of cases with their change and
#     urgency, the urgency rows and their labels, the confirmed obligation links, and the
#     count over the whole roadmap. A sixth — those obligations' titles — is not sent, because
#     this bank has no confirmed link and a query whose `IN` clause is empty never executes.
#   the lead (9): the week's cases ordered by urgency (1), then the feed's own row for the one
#     change it chose (8) — the change with this bank's case joined, its classification in
#     three, the urgency rows and their labels, the change type's labels and this bank's
#     obligation-link decisions.
#   source health (2): every source with the last line of its log, and those sources' labels.
HOME_QUERIES = 16


def a_change(
    *,
    title: str,
    key_date: datetime.date | None = THIS_QUARTER,
    urgency: str = "act_now",
    first_seen_at: datetime.datetime = THIS_WEEK,
) -> RegulatoryChange:
    return watch_build.change(
        title=title, urgency=urgency, key_date=key_date, key_date_label="In force", first_seen_at=first_seen_at
    )


def roadmap_only_reader(tenant: Tenant) -> User:
    """A member who may read the roadmap and not the watch feed. Every system role holds
    both (PRD §6), so the one reader who tests the permission filter needs a role of its
    own — which is also the honest shape, since a bank may build exactly this role."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        TenantRole.objects.create(tenant=tenant, key="roadmap-only", permissions=[perms.ROADMAP_READ])
    return factories.member(tenant, roles=("roadmap-only",)).user


class HomeContents(TestCase):
    """What Today is given, and why each panel holds what it holds (HOM-01, FP-03)."""

    tenant: Tenant
    reader: User
    lead: ChangeCase
    quieter: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="home-a", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        # Sighted this week: the urgent one leads, the calmer one follows it. The key dates
        # put them on the roadmap in the same order, so "Coming up" is readable too.
        cls.lead = cases_build.case(cls.tenant, a_change(title="Research payments"))
        cls.quieter = cases_build.case(
            cls.tenant,
            a_change(title="Reporting", key_date=NEXT_QUARTER, urgency="six_months_plus"),
            urgency="six_months_plus",
        )
        # Three changes that must not lead the week, each for a reason of its own. The first
        # is dated later than both of the above, so it is still on the roadmap — being old
        # news is a reason not to lead a week, never a reason to leave the calendar.
        cases_build.case(
            cls.tenant,
            a_change(title="Last week's news", key_date=NEXT_QUARTER + datetime.timedelta(days=1), first_seen_at=LAST_WEEK),
        )
        cases_build.case(cls.tenant, a_change(title="Insurance"), footprint_match=False)
        finished = cases_build.case(cls.tenant, a_change(title="Settled"))
        tenancy.activate(cls.tenant.id)
        ChangeCase.objects.filter(pk=finished.pk).update(status=CaseStatusCategory.CLOSED.value)

    def read(self, *, watch_reader: bool = True) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            return logic.home_today(self.tenant, ["en"], watch_reader=watch_reader)

    def test_the_date_is_the_banks_own_calendar_day(self) -> None:
        """Today is the day the bank is in, not the server's: at the frozen instant it is
        still 30 September in UTC and already 1 October in Stockholm."""
        self.assertEqual(self.read().date, STOCKHOLM_TODAY)
        self.assertEqual(logic.week_start_of(STOCKHOLM_TODAY), WEEK_START)

    def test_coming_up_is_the_roadmaps_own_first_items_and_its_whole_count(self) -> None:
        """Ruling 5: the panel and the roadmap page come from one query, so the panel can
        never name a date the page does not hold."""
        answer = self.read()
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            whole = roadmap.roadmap_items(self.tenant, ["en"], HomeRoadmapQuery())
        self.assertEqual([item.id for item in answer.coming_up], [item.id for item in whole.items])
        self.assertEqual(answer.roadmap_count, len(whole.items))
        self.assertEqual(
            [item.title for item in answer.coming_up], ["Research payments", "Reporting", "Last week's news"]
        )

    def test_coming_up_is_cut_to_the_settings_length_and_the_count_still_says_how_many(self) -> None:
        with mock.patch.object(settings, "HOME_COMING_UP_ITEMS", 1):
            answer = self.read()
        self.assertEqual([item.title for item in answer.coming_up], ["Research payments"])
        self.assertEqual(answer.roadmap_count, 3, "the count is the whole roadmap, never the panel's length")

    def test_the_week_is_led_by_its_most_urgent_open_in_scope_change(self) -> None:
        lead = self.read().lead
        self.assertIsNotNone(lead)
        assert lead is not None
        self.assertEqual(lead.title, "Research payments")
        self.assertEqual(lead.id, self.lead.change_id)
        self.assertEqual(lead.case.category, "new")
        self.assertEqual(lead.case.urgency.key, "act_now")

    def test_what_cannot_lead_the_week_and_why(self) -> None:
        """Three rows that must not lead, each refused by its own rule: a change sighted
        last week, one the bank has closed, and one outside its regulatory scope (FP-03)."""
        led = [case.change.title for case in logic.week_cases(self.tenant, WEEK_START, limit=10)]
        self.assertEqual(led, ["Research payments", "Reporting"])
        for absent in ("Last week's news", "Settled", "Insurance"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, led)

    def test_a_quiet_week_leads_with_nothing_and_that_is_not_a_failure(self) -> None:
        """A week nothing was sighted in has no lead. Null there is a real and quiet week,
        which the screen says in words rather than treating as a failed read."""
        tenancy.activate(self.tenant.id)
        self.assertEqual(logic.week_cases(self.tenant, D(2026, 9, 14), limit=10), [])

    def test_an_unconfirmed_so_what_travels_labelled_rather_than_hidden(self) -> None:
        """WAT-05: the lead card shows the agent's draft with its label until a person
        confirms it. The row carries both facts, so the screen never has to guess."""
        tenancy.activate(self.tenant.id)
        ChangeCase.objects.filter(pk=self.lead.pk).update(so_what_text="Three regulations change.")
        lead = self.read().lead
        assert lead is not None and lead.case is not None
        self.assertEqual(lead.case.so_what_text, "Three regulations change.")
        self.assertFalse(lead.case.so_what_confirmed)
        self.assertIsNone(lead.case.so_what_confirmed_at)


class HomeSourcePanel(TestCase):
    """How the watching is going (HOM-01, WAT-01): every source is either counted as healthy
    or named as a gap, so `checked` below `total` always means something a person can act on."""

    tenant: Tenant

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        # The registry before any bank: a source is a library row, and the only session its
        # write rule accepts is one with no tenant activated (WAT-06, H15). A factory that
        # made a tenant first would leave one on and this fixture would be refused.
        healthy = watch_build.source(name="fi.se healthy", check_frequency=CheckFrequency.WEEKLY)
        watch_build.source_check(healthy, status=CheckStatus.OK, checked_at=INSTANT)
        broken = watch_build.source(name="fi.se broken", check_frequency=CheckFrequency.WEEKLY)
        watch_build.source_check(
            broken, status=CheckStatus.FAILED, error="502 from the publisher after three retries", checked_at=INSTANT
        )
        watch_build.source(name="fi.se never checked", check_frequency=CheckFrequency.WEEKLY)
        watch_build.source(name="fi.se left alone", check_frequency=CheckFrequency.WEEKLY, active=False)
        cls.tenant = factories.tenant(slug="home-sources", timezone="Europe/Stockholm")

    def read(self) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            return logic.source_health(["en"])

    def test_every_source_is_either_counted_healthy_or_named_as_a_gap(self) -> None:
        health = self.read()
        self.assertEqual((health.checked, health.total), (1, 3))
        self.assertEqual(
            sorted(row.source.name for row in health.failed), ["fi.se broken", "fi.se never checked"]
        )
        self.assertEqual(health.checked + len(health.failed), health.total)

    def test_a_source_whose_checks_are_switched_off_is_in_neither_figure(self) -> None:
        """It is deliberately not being checked, so counting it would make a choice look
        like a gap and would put a row on the panel nobody can act on."""
        health = self.read()
        self.assertNotIn("fi.se left alone", [row.source.name for row in health.failed])
        self.assertEqual(health.total, 3, "the registry holds four; one is not checked on purpose")

    def test_a_failed_check_carries_what_went_wrong(self) -> None:
        broken = next(row for row in self.read().failed if row.source.name == "fi.se broken")
        self.assertEqual(broken.last_status, "failed")
        self.assertEqual(broken.last_error, "502 from the publisher after three retries")


class HomeIsFilteredByPermission(TestCase):
    """A panel a reader may not see is null inside a 200, never a 403 (chunk 6 defaults):
    Today is mostly readable by everyone, and refusing the page would take the readable part
    away too."""

    tenant: Tenant
    reader: User
    limited: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        # The registry first: a source is written with no tenant activated (WAT-06, H15).
        watch_build.source_check(watch_build.source(name="fi.se perms"), status=CheckStatus.OK, checked_at=INSTANT)
        cls.tenant = factories.tenant(slug="home-perms", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.limited = roadmap_only_reader(cls.tenant)
        cases_build.case(cls.tenant, a_change(title="Research payments"))

    def get(self, user: User) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            return self.client.get(URL, **sign_in(user, tenant=self.tenant))

    def test_a_reader_with_watch_read_gets_both_panels(self) -> None:
        body = self.get(self.reader).json()
        self.assertIsNotNone(body["lead"])
        self.assertEqual(body["sources"]["total"], 1)

    def test_a_reader_without_watch_read_gets_the_page_with_those_panels_null(self) -> None:
        response = self.get(self.limited)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["lead"])
        self.assertIsNone(body["sources"])
        self.assertEqual([item["title"] for item in body["comingUp"]], ["Research payments"])

    def test_the_panels_a_reader_may_not_see_are_not_even_read(self) -> None:
        """Null is decided by the permission before the query, not by emptying a result:
        the reader without `watch.read` pays for neither the lead nor the coverage log.

        Five queries, which is the roadmap read and its count and nothing else: eleven fewer
        than the sixteen above, and every one of the eleven belongs to a panel this reader
        may not see.
        """
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            with self.assertNumQueries(5):
                logic.home_today(self.tenant, ["en"], watch_reader=False)

    def test_the_answer_carries_no_decide_now_and_no_standing(self) -> None:
        """Ruling 1 and ruling 2: what needs a decision has one source, the `counts` object
        on `GET /me`, and the standing panel arrives with the register in chunk 8 rather than
        reading zeros here."""
        self.assertEqual(
            sorted(self.get(self.reader).json()), ["comingUp", "date", "lead", "roadmapCount", "sources"]
        )


class HomeCost(TestCase):
    """NFR-02, playbook 10: four independent reads, none chained, and the same query count
    whatever the bank has ahead of it."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        # The registry first: a source is written with no tenant activated (WAT-06, H15).
        watch_build.source_check(watch_build.source(name="fi.se cost"), status=CheckStatus.OK, checked_at=INSTANT)
        cls.tenant = factories.tenant(slug="home-cost", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        for number in range(30):
            cases_build.case(
                cls.tenant,
                a_change(title=f"Reform {number}", key_date=THIS_QUARTER + datetime.timedelta(days=number)),
            )

    def test_the_query_count_does_not_grow_with_the_number_of_cases(self) -> None:
        """Asked at two sizes: thirty cases and then one. The same number both times is what
        "fan out, never chain" means in queries rather than in prose."""
        for expected_count in (30, 1):
            with mock.patch("django.utils.timezone.now", return_value=INSTANT):
                tenancy.activate(self.tenant.id)
                with self.subTest(cases=expected_count), self.assertNumQueries(HOME_QUERIES):
                    answer = logic.home_today(self.tenant, ["en"], watch_reader=True)
            self.assertEqual(answer.roadmap_count, expected_count)
            self.assertEqual(len(answer.coming_up), min(expected_count, settings.HOME_COMING_UP_ITEMS))
            self.assertIsNotNone(answer.lead)
            if expected_count == 30:
                # Close all but the earliest, so the second pass runs the same code over
                # one row instead of thirty.
                tenancy.activate(self.tenant.id)
                keep = list(ChangeCase.objects.order_by("change__key_date", "id").values_list("pk", flat=True)[:1])
                ChangeCase.objects.exclude(pk__in=keep).update(status=CaseStatusCategory.CLOSED.value)

    def test_today_stays_inside_the_budget(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            headers = sign_in(self.reader, tenant=self.tenant)
            response = self.client.get(URL, **headers)
            self.assertEqual(response.status_code, 200)
            self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
            # CPU time on the request thread, the best of five: what the reads cost without
            # the waits a loaded machine adds. Coverage's tracer is paused for the timed
            # requests only, so the traced one above keeps coverage unchanged.
            spent = []
            tracer = sys.gettrace()
            sys.settrace(None)
            try:
                for _ in range(5):
                    started = time.thread_time()
                    self.client.get(URL, **headers)
                    spent.append((time.thread_time() - started) * 1000)
            finally:
                sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)


class HomeRoute(TestCase):
    """`GET /home` end to end: what a signed-in reader gets, and what happens without one."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="home-route", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cases_build.case(cls.tenant, a_change(title="Research payments"))

    def test_a_reader_gets_today_in_camel_case(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            response = self.client.get(URL, **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["date"], "2026-10-01")
        self.assertEqual(body["roadmapCount"], 1)
        self.assertEqual(body["comingUp"][0]["itemType"], "change_date")
        self.assertEqual(body["lead"]["title"], "Research payments")

    def test_without_a_session_it_is_401_and_reads_nothing(self) -> None:
        refused = self.client.get(URL)
        self.assertEqual((refused.status_code, refused.json()["code"]), (401, "unauthenticated"))

    def test_a_bank_with_nothing_yet_gets_a_200_and_empty_panels(self) -> None:
        empty = factories.tenant(slug="home-empty", timezone="Europe/Stockholm")
        newcomer = factories.member_user(empty, roles=("reader",))
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            body = self.client.get(URL, **sign_in(newcomer, tenant=empty)).json()
        self.assertEqual((body["comingUp"], body["roadmapCount"], body["lead"]), ([], 0, None))
        self.assertEqual(body["sources"], {"checked": 0, "total": 0, "failed": []})
