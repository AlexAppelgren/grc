"""The roadmap by quarter (HOM-03, FP-03, NFR-02): what reaches a bank's calendar of
regulation, what never does, and the two questions the quarter roster turns on.

What is proved here, one class per question:

- **What is on it.** A dated change the bank has open, in-scope work on. A case that is
  closed or dismissed, one outside the bank's regulatory scope and a date that has gone are
  each absent, and each for its own reason rather than by accident.
- **Whose today it is.** The window starts at the bank's own calendar day, so two banks
  reading at one instant from two time zones can be in two quarters and see two rosters.
  Nothing here depends on the day the suite runs: the clock is frozen at a fixed instant
  and every date is written out (playbook 8.3).
- **Whose rows they are.** Another bank's case never reaches this bank's roadmap, which is
  row-level security doing its job rather than a filter in Python.
- **What it costs.** The read runs the same queries for one item and for thirty, and
  the route stays inside the API budget on a roadmap a real bank would have.
- **Our own deadlines.** Next reviews, gap targets and a certificate's expiry and next
  audit, each once with its owner and its record, each gone when its row closes, the
  register's only for a `register.read` holder, and none of them on a calendar.

`coming_up()` is proved against `roadmap_items()` rather than on its own: Today's panel and
the roadmap page answer from one query (chunk 6 ruling 5), so the test that matters is that
they agree.
"""

from __future__ import annotations

import datetime
import sys
import time
from typing import Any
from unittest import mock

from django.conf import settings
from django.test import TestCase

from apps.agents import testing as agent_build
from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.home import roadmap
from apps.home.schemas import HomeRoadmapItem, HomeRoadmapQuery
from apps.home.tests_my_work import Bank, obligation
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import DatePrecision, Obligation
from apps.register import logic as register_logic
from apps.register.models import Applicability, TenantObligation
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import CaseStatusCategory, FootprintTerm, RiskAcceptanceReason
from apps.tenants.models import Licence
from apps.tenants.testing import licence_type_term
from apps.watch import testing as watch_build
from apps.watch.models import ChangeObligation, RegulatoryChange
from apps.watch.write import watch_write

URL = "/api/v1/roadmap"
D = datetime.date

# A fixed instant, never "now": at 22:30 UTC on 30 September it is already 1 October in
# Stockholm, so one bank's today is in Q4 while the other's is still in Q3. That is the
# whole of the time-zone question in one number, and it does not move with the suite.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
STOCKHOLM_TODAY = D(2026, 10, 1)
UTC_TODAY = D(2026, 9, 30)

THIS_QUARTER = D(2026, 10, 15)  # 2026-Q4
NEXT_QUARTER = D(2027, 1, 20)  # 2027-Q1
GONE = D(2026, 9, 29)  # yesterday in both zones

# Seven queries, measured 2026-09-25 and pinned so an N+1 shows up as a number (playbook 10):
# the cases with their change and urgency (1); the urgency rows on the page and their labels
# (2, through the watch app's own rule, which is what keeps the pill tone out of the answer);
# the confirmed obligation links of every change on the page with their obligation and
# instrument (1); the titles of those obligations (1); the certificates whose expiry and whose
# next audit fall in the window (2), which every member reads. None of them grows with the
# number of items, which is what the test below demands.
ROADMAP_QUERIES = 7
# The bank's own deadlines for a `register.read` holder, measured 2026-09-25: the two
# certificate branches, the entries', entity rows' and gaps' dates (5), the reviewed
# obligations' titles (2), the owning teams' labels (1) and the certificates' type labels (1).
INTERNAL_QUERIES = 9


def a_change(*, key_date: datetime.date | None, title: str = "A reform", urgency: str = "act_now") -> RegulatoryChange:
    return watch_build.change(title=title, urgency=urgency, key_date=key_date, key_date_label="In force")


class RoadmapContents(TestCase):
    """What reaches the roadmap and what does not (HOM-03, FP-03)."""

    tenant: Tenant
    reader: User
    soon: ChangeCase
    later: ChangeCase
    outside: ChangeCase
    closed: ChangeCase
    dismissed: ChangeCase
    passed: ChangeCase
    undated: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="roadmap-a", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.soon = cases_build.case(cls.tenant, a_change(key_date=THIS_QUARTER, title="Research payments"))
        cls.later = cases_build.case(
            cls.tenant, a_change(key_date=NEXT_QUARTER, title="Reporting", urgency="within_3_months")
        )
        # Each of these is absent for its own reason, and the reasons are tested apart.
        cls.outside = cases_build.case(
            cls.tenant, a_change(key_date=THIS_QUARTER, title="Insurance"), footprint_match=False
        )
        cls.closed = cases_build.case(cls.tenant, a_change(key_date=THIS_QUARTER, title="Settled"))
        cls.dismissed = cases_build.case(cls.tenant, a_change(key_date=THIS_QUARTER, title="Not for us"))
        cls.passed = cases_build.case(cls.tenant, a_change(key_date=GONE, title="Yesterday"))
        cls.undated = cases_build.case(cls.tenant, a_change(key_date=None, title="No date yet"))
        for case, status in ((cls.closed, CaseStatusCategory.CLOSED), (cls.dismissed, CaseStatusCategory.DISMISSED)):
            cases_build.in_category(case, status)

    def read(self, **filters: Any) -> Any:
        """The roadmap as this bank reads it at the frozen instant."""
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            return roadmap.roadmap_items(self.tenant, ["en"], HomeRoadmapQuery(**filters))

    def titles(self, **filters: Any) -> list[str]:
        return [item.title for item in self.read(**filters).items]

    def test_open_in_scope_dated_work_is_listed_earliest_first(self) -> None:
        self.assertEqual(self.titles(), ["Research payments", "Reporting"])

    def test_what_the_bank_has_finished_with_or_never_had_is_absent(self) -> None:
        """Four rows that must not appear, each for a reason of its own: work the bank has
        closed, work it said is not for it, a date that has gone, and a change registered
        before anybody published its date."""
        listed = self.titles()
        for absent in ("Settled", "Not for us", "Yesterday", "No date yet"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, listed)

    def test_a_change_outside_the_regulatory_scope_is_absent(self) -> None:
        """FP-03. The verdict is the one `apps/cases/creation.py` computed from the scope
        rule and stored on the case; the roadmap reads it and never recomputes it, so the
        roadmap, the feed and the inventory can never disagree about the footprint."""
        self.assertNotIn("Insurance", self.titles())
        tenancy.activate(self.tenant.id)
        ChangeCase.objects.filter(pk=self.outside.pk).update(footprint_match=True)
        self.assertIn("Insurance", self.titles(), "the scope widened and the date arrived with it")

    def test_a_row_carries_keys_and_kinds_and_never_a_phrase_of_its_own(self) -> None:
        item = self.read().items[0]
        self.assertEqual(
            (item.id, item.kind, item.item_type, item.date, item.quarter),
            (f"change_date:{self.soon.id}", "regulatory", "change_date", THIS_QUARTER, "2026-Q4"),
        )
        self.assertEqual((item.status, item.change_id), ("new", self.soon.change_id))
        self.assertEqual((item.urgency.key, item.urgency.label), ("act_now", "Act now"))
        # NFR-03: an urgency row's own `kind` column is its pill tone, and a tone is nobody's
        # to send — the screen takes it from the key's fixed severity order. Reading the
        # vocabulary the ordinary way answers that column, which put `"kind": "negative"` on
        # every roadmap item until 2026-09-21, against this module's own documented example.
        self.assertIsNone(item.urgency.kind)
        self.assertEqual((item.label, item.source_label), ("In force", "Finansinspektionen"))

    def test_a_row_carries_its_dates_precision_so_a_quarter_never_reads_as_a_day(self) -> None:
        """HOM-03, INV-S10: a legal date is a plain date with a precision. A date the source
        stated as a quarter is stored on a day, and without its precision beside it the
        roadmap printed that day and counted the days left to it (calendar-feed-hardening
        ND1). The precision is the change's own library column, served as it stands."""
        self.assertEqual(self.read().items[0].date_precision, "day")
        with watch_write("test: a key date stated as a quarter"):
            RegulatoryChange.objects.filter(pk=self.soon.change_id).update(key_date_precision=DatePrecision.QUARTER.value)
        item = self.read().items[0]
        self.assertEqual((item.title, item.date, item.date_precision), ("Research payments", THIS_QUARTER, "quarter"))

    def test_the_quarter_roster_holds_each_quarter_once_in_date_order(self) -> None:
        answer = self.read()
        self.assertEqual(answer.quarters, ["2026-Q4", "2027-Q1"])
        self.assertEqual([item.quarter for item in answer.items], ["2026-Q4", "2027-Q1"])

    def test_the_window_filters_and_a_from_before_today_widens_nothing(self) -> None:
        self.assertEqual(self.titles(date_from=NEXT_QUARTER), ["Reporting"])
        self.assertEqual(self.titles(date_to=THIS_QUARTER), ["Research payments"])
        self.assertEqual(self.titles(date_from=THIS_QUARTER, date_to=NEXT_QUARTER), ["Research payments", "Reporting"])
        self.assertEqual(self.titles(date_from=D(2020, 1, 1)), ["Research payments", "Reporting"], "yesterday stays gone")
        self.assertEqual(self.titles(date_to=D(2020, 1, 1)), [], "a window that holds nothing is empty, not an error")

    def test_a_bank_with_no_deadline_of_its_own_gets_an_empty_internal_roadmap(self) -> None:
        """An empty list is the honest answer; a 422 would tell a client the filter does not
        exist."""
        internal = self.read(kind="internal")
        self.assertEqual((internal.items, internal.quarters), ([], []))
        self.assertEqual(self.titles(kind="regulatory"), self.titles(kind="all"))

    def test_coming_up_answers_the_roadmaps_own_first_items_and_its_whole_count(self) -> None:
        """Ruling 5: Today's panel and the roadmap page come from one query, so the panel
        can never name a date the page does not hold."""
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            items, count = roadmap.coming_up(self.tenant, ["en"], 1)
        whole = self.read().items
        self.assertEqual([item.id for item in items], [whole[0].id])
        self.assertEqual(count, len(whole))


class RoadmapObligations(TestCase):
    """The obligations a dated change touches (WAT-04): confirmed links only, because the
    roadmap is where a person plans work and a suggestion is not a checked fact."""

    tenant: Tenant
    case: ChangeCase
    confirmed: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="roadmap-links", timezone="Europe/Stockholm")
        editor = factories.platform_user()
        instrument = library_build.instrument(key="fffs-2017-2", short_name="FFFS 2017:2", regime="regime:securities")
        cls.confirmed = library_build.obligation(
            instrument, key="obl-research", titles={"en": "Assess the research paid for"}, ref_label="11 kap. 4 §"
        )
        suggested = library_build.obligation(instrument, key="obl-suggested", titles={"en": "Still a suggestion"})
        change = a_change(key_date=THIS_QUARTER)
        watch_build.obligation_link(change, cls.confirmed, confidence=0.82)
        watch_build.obligation_link(change, suggested, confidence=0.4)
        with watch_write("test setup"):
            ChangeObligation.objects.filter(change=change).filter(obligation=cls.confirmed).update(
                confirmed_by=editor, confirmed_at=INSTANT
            )
        cls.case = cases_build.case(cls.tenant, change)

    def test_only_a_confirmed_link_is_listed_and_it_carries_where_the_duty_sits(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            answer = roadmap.roadmap_items(self.tenant, ["en"], HomeRoadmapQuery())
        links = answer.items[0].obligations
        self.assertEqual([link.obligation_id for link in links], [self.confirmed.id])
        link = links[0]
        self.assertEqual(
            (link.title, link.instrument_short_name, link.ref_label),
            ("Assess the research paid for", "FFFS 2017:2", "11 kap. 4 §"),
        )
        self.assertEqual((link.origin, link.confidence, link.confirmed), ("agent", 0.82, True))
        self.assertEqual((link.confirmed_origin, link.confirmed_by_agent), ("user", None))

    def test_a_link_an_agent_confirmed_reads_machine_confirmed_naming_the_agent(self) -> None:
        """D-74: the roadmap says who confirmed a link as the change page does, so a
        machine's confirmation never reaches a bank's plan as a person's verification."""
        tenancy.clear_tenant()
        confirmer = agent_build.agent_key(agent_row=agent_build.agent(key="library-confirmer"))
        with watch_write("test setup"):
            ChangeObligation.objects.filter(obligation=self.confirmed).update(
                confirmed_by=None, confirmed_by_api_key_id=confirmer.id, confirmed_by_agent_id=confirmer.agent.id
            )
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(self.tenant.id)
            link = roadmap.roadmap_items(self.tenant, ["en"], HomeRoadmapQuery()).items[0].obligations[0]
        self.assertEqual((link.confirmed, link.confirmed_origin), (True, "agent"))
        self.assertEqual(link.confirmed_by_agent.key if link.confirmed_by_agent else None, "library-confirmer")


class RoadmapQuartersAreTheBanksOwn(TestCase):
    """Two banks, one instant, two calendar days (HOM-03). The quarter roster is the bank's
    own question, not the server's."""

    stockholm: Tenant
    utc: Tenant
    boundary: RegulatoryChange

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.stockholm = factories.tenant(slug="roadmap-se", timezone="Europe/Stockholm")
        cls.utc = factories.tenant(slug="roadmap-utc", timezone="UTC")
        # One library change, dated the day that is today in one zone and tomorrow in the
        # other, and one case per bank: the same fact, two calendars.
        cls.boundary = a_change(key_date=STOCKHOLM_TODAY, title="In force from October")
        for tenant in (cls.stockholm, cls.utc):
            cases_build.case(tenant, cls.boundary)

    def read(self, tenant: Tenant) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            tenancy.activate(tenant.id)
            return roadmap.roadmap_items(tenant, ["en"], HomeRoadmapQuery())

    def test_each_bank_reads_the_quarter_it_is_in(self) -> None:
        """At the frozen instant the Stockholm bank's today is 1 October and the UTC bank's
        is 30 September, so the same date opens one bank's Q4 and is still ahead for the
        other. Both list it; the point is that the window's floor is each bank's own day."""
        self.assertEqual(
            (roadmap.quarter_of(STOCKHOLM_TODAY), roadmap.quarter_of(UTC_TODAY)), ("2026-Q4", "2026-Q3")
        )
        for tenant in (self.stockholm, self.utc):
            with self.subTest(timezone=tenant.timezone):
                self.assertEqual([item.quarter for item in self.read(tenant).items], ["2026-Q4"])

    def test_the_floor_is_the_banks_own_day_and_not_the_servers(self) -> None:
        """A date of 30 September has gone for the bank in Stockholm, where it is already
        October, and is still today for the bank in UTC. One roadmap holds it, the other
        does not, from one row and one instant."""
        gone_in_stockholm = a_change(key_date=UTC_TODAY, title="In force from 30 September")
        for tenant in (self.stockholm, self.utc):
            cases_build.case(tenant, gone_in_stockholm)
        self.assertEqual([item.title for item in self.read(self.stockholm).items], ["In force from October"])
        self.assertEqual(
            [item.title for item in self.read(self.utc).items],
            ["In force from 30 September", "In force from October"],
        )

    def test_another_banks_case_never_reaches_this_banks_roadmap(self) -> None:
        """Row-level security, not a filter in Python: the case rows of the other bank are
        invisible to this one even though both hold a case for the same change."""
        stockholm_ids = {item.id for item in self.read(self.stockholm).items}
        utc_ids = {item.id for item in self.read(self.utc).items}
        self.assertEqual(len(stockholm_ids), 1)
        self.assertEqual(stockholm_ids & utc_ids, set(), "two banks, two case ids, one change")


class RoadmapCost(TestCase):
    """NFR-02, playbook 10: the read costs the same four queries whatever is on the roadmap,
    and the route answers inside the API budget on a roadmap a real bank would have."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="roadmap-cost", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        instrument = library_build.instrument(key="fffs-cost", short_name="FFFS 2026:1", regime="regime:securities")
        editor = factories.platform_user()
        for number in range(30):
            change = a_change(key_date=THIS_QUARTER + datetime.timedelta(days=number), title=f"Reform {number}")
            obligation = library_build.obligation(instrument, key=f"obl-cost-{number}")
            watch_build.obligation_link(change, obligation)
            with watch_write("test setup"):
                ChangeObligation.objects.filter(change=change).update(confirmed_by=editor, confirmed_at=INSTANT)
            cases_build.case(cls.tenant, change)

    def test_the_query_count_does_not_grow_with_the_number_of_items(self) -> None:
        for window, expected in ((THIS_QUARTER, 1), (THIS_QUARTER + datetime.timedelta(days=29), 30)):
            with mock.patch("django.utils.timezone.now", return_value=INSTANT):
                # Activating the tenant is the request's own work and costs a `set_config`
                # round trip; what is counted here is the read itself.
                tenancy.activate(self.tenant.id)
                with self.subTest(items=expected), self.assertNumQueries(ROADMAP_QUERIES):
                    answer = roadmap.roadmap_items(self.tenant, ["en"], HomeRoadmapQuery(to=window))
            self.assertEqual(len(answer.items), expected)

    def test_a_full_roadmap_stays_inside_the_budget(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            headers = sign_in(self.reader, tenant=self.tenant)
            response = self.client.get(URL, **headers)
            self.assertEqual(len(response.json()["items"]), 30)
            self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
            # CPU time on the request thread, the best of five: what the read costs without
            # the waits a loaded machine adds, so the bound holds on a busy runner too. The
            # suite runs under coverage, whose tracer is paused for the timed requests only;
            # the traced one above keeps coverage unchanged.
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


class RoadmapRoute(TestCase):
    """`GET /roadmap` end to end: what a signed-in reader gets, and what the filters refuse
    before anything is read."""

    tenant: Tenant
    reader: User
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="roadmap-route", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.case = cases_build.case(cls.tenant, a_change(key_date=THIS_QUARTER, title="Research payments"))

    def get(self, query: str = "") -> Any:
        """A real session signed in at the frozen instant: a session minted at the real
        clock would be days old to the request and answer 401 (playbook 8.3)."""
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            headers = sign_in(self.reader, tenant=self.tenant)
            return self.client.get(f"{URL}{query}", **headers)

    def test_a_reader_gets_the_roadmap_in_camel_case_with_its_roster(self) -> None:
        response = self.get()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["quarters"], ["2026-Q4"])
        item = body["items"][0]
        self.assertEqual(item["itemType"], "change_date")
        self.assertEqual(item["sourceLabel"], "Finansinspektionen")
        self.assertEqual(item["changeId"], str(self.case.change_id))
        self.assertEqual(item["urgency"]["key"], "act_now")
        self.assertEqual(item["datePrecision"], "day")

    def test_a_reader_gets_the_banks_own_deadlines_too(self) -> None:
        """The route passes the reader's `register.read`: a reader, who holds it, sees a
        next review beside the regulatory date."""
        tenancy.activate(self.tenant.id)
        entry = register_logic.ensure_register_entry(
            tenant_id=self.tenant.id, obligation_id=obligation("Reviewed").id, actor=factories.user_actor()
        )
        TenantObligation.objects.filter(pk=entry.pk).update(applicability="applies", next_review_date=NEXT_QUARTER)
        items = self.get().json()["items"]
        self.assertEqual([item["itemType"] for item in items], ["change_date", "review_due"])
        self.assertEqual(
            {key: items[1][key] for key in ("kind", "status", "urgency", "label", "sourceLabel", "changeId", "obligations")},
            {"kind": "internal", "status": None, "urgency": None, "label": None, "sourceLabel": None, "changeId": None, "obligations": []},
        )
        self.assertEqual(items[1]["subject"]["obligationId"], str(entry.obligation_id))

    def test_an_empty_roadmap_is_a_200_and_never_a_404(self) -> None:
        self.assertEqual(self.get("?kind=internal").json(), {"items": [], "quarters": []})

    def test_a_filter_this_route_does_not_read_is_ignored_and_the_contract_says_so(self) -> None:
        """A query parameter the route does not name is dropped before the schema sees it,
        so a misspelt filter answers the unfiltered roadmap rather than a 422. That is what
        the operation's description tells an integrator to check for, and it is pinned here
        so the sentence and the behaviour cannot drift apart."""
        self.assertEqual(self.get("?kindd=regulatory").json(), self.get().json())

    def test_a_filter_value_the_schema_refuses_is_422_with_a_code_to_branch_on(self) -> None:
        for query in ("?kind=ours", "?from=last-week"):
            with self.subTest(query=query):
                refused = self.get(query)
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"))


class RoadmapOwnDeadlines(TestCase):
    """The bank's own deadlines (HOM-03, REG-02, REG-03, TEN-02, D-43, AC-TEN1): each branch
    once with its owner and its record, each gone when its row closes, and none on a
    calendar. Every date is the bank's own today plus an offset (playbook 8.3)."""

    bank: Bank
    entry_review: TenantObligation
    certificate: Licence
    expected: dict[str, str]

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("roadmap-own")
        today = bank.today()

        def day(offset: int) -> datetime.date:
            return today + datetime.timedelta(days=offset)

        cases_build.case(bank.tenant, a_change(key_date=day(5), title="Research payments"))
        # A compliant entry's own review, owned by a person and a team.
        cls.entry_review = bank.entry(
            obligation("Complies"), compliance_status=bank.compliant, first_line_owner=bank.anna, owner_team=bank.retail_team, next_review_date=day(20)
        )
        # One legal entity's review, owned by a team; the other entity does not apply.
        spanning = bank.entry(obligation("Spans two entities"))
        fund = bank.scope(spanning, bank.fund_ab, owner_team=bank.cards, next_review_date=day(30))
        bank.scope(spanning, bank.bank_ab, applicability=Applicability.DOES_NOT_APPLY.value, next_review_date=day(31))
        # Gaps: open and remediating have a target to meet; closed and accepted do not.
        opened = bank.gap(cls.entry_review, owner=bank.erik, org_unit=bank.fund_ab, target_date=day(40))
        remediating = bank.gap(cls.entry_review, status="remediating", owner_team=bank.cards, target_date=day(50))
        bank.gap(cls.entry_review, status="closed", owner=bank.erik, target_date=day(45))
        bank.gap(
            cls.entry_review,
            status="risk_accepted",
            target_date=day(46),
            acceptance_reason=RiskAcceptanceReason.objects.get(key="other"),
            acceptance_requested_by=bank.anna,
            acceptance_requested_at=INSTANT,
            accepted_by=bank.officer,
            accepted_at=INSTANT,
        )
        # Absent each for its own reason: an entry that does not apply, a review that has
        # gone, and one outside the regulatory scope (FP-03).
        bank.entry(obligation("Not ours"), applicability=Applicability.DOES_NOT_APPLY.value, next_review_date=day(10))
        bank.entry(obligation("Overdue"), next_review_date=day(-1))
        bank.entry(obligation("Advice", terms=["service_type:advice"]), next_review_date=day(15))
        bank.activate()
        FootprintTerm.objects.create(tenant=bank.tenant, term=library_build.term("service_type:custody"))
        # A certificate with an expiry and a next audit, and a withdrawn one.
        term = licence_type_term()
        cls.certificate = Licence.objects.create(
            tenant=bank.tenant, org_unit=bank.bank_ab, licence_type=term, valid_until=day(400), next_audit_on=day(100), owner_user=bank.anna
        )
        Licence.objects.create(
            tenant=bank.tenant, org_unit=bank.fund_ab, licence_type=term, valid_until=day(200), next_audit_on=day(60), withdrawn_on=day(-3)
        )
        cls.expected = {
            f"review_due:{cls.entry_review.id}": "review_due",
            f"review_due:{fund.id}": "review_due",
            f"gap_target:{opened.id}": "gap_target",
            f"gap_target:{remediating.id}": "gap_target",
            f"certificate_audit:{cls.certificate.id}": "certificate_audit",
            f"certificate_expiry:{cls.certificate.id}": "certificate_expiry",
        }

    def read(self, *, register_reader: bool = True, **filters: Any) -> list[HomeRoadmapItem]:
        self.bank.activate()
        return roadmap.roadmap_items(self.bank.tenant, ["en"], HomeRoadmapQuery(**filters), register_reader=register_reader).items

    def by_id(self) -> dict[str, HomeRoadmapItem]:
        return {item.id: item for item in self.read(kind="internal")}

    def test_each_deadline_is_listed_once_as_internal_in_date_order(self) -> None:
        items = self.read(kind="internal")
        self.assertEqual({item.id: item.item_type for item in items}, self.expected)
        self.assertEqual(len(items), len(self.expected))
        self.assertEqual(items, sorted(items, key=lambda item: (item.date, item.id)))
        self.assertEqual({item.kind for item in items}, {"internal"})

    def test_each_names_its_owner_and_its_record(self) -> None:
        items = self.by_id()
        review = items[f"review_due:{self.entry_review.id}"]
        assert review.owner is not None and review.subject is not None
        self.assertEqual((review.owner.person.id if review.owner.person else None, review.owner.team.key if review.owner.team else None), (self.bank.anna.id, "retail_compliance"))
        self.assertEqual((review.title, review.subject.obligation_id, review.subject.entity), ("Complies", self.entry_review.obligation_id, None))
        gap = next(item for key, item in items.items() if key.startswith("gap_target") and item.subject and item.subject.entity)
        assert gap.owner is not None and gap.subject is not None and gap.subject.entity is not None
        self.assertEqual((gap.title, gap.owner.person.name if gap.owner.person else None, gap.subject.entity.name), ("Reconciliation is weekly", "Erik Holm", "Fund AB"))
        self.assertEqual(gap.subject.obligation_id, self.entry_review.obligation_id)
        audit = items[f"certificate_audit:{self.certificate.id}"]
        assert audit.owner is not None and audit.subject is not None and audit.subject.entity is not None
        self.assertEqual((audit.subject.licence_id, audit.subject.entity.name), (self.certificate.id, "Bank AB"))
        self.assertEqual(audit.owner.person.name if audit.owner.person else None, "Anna Berg")
        self.assertEqual(audit.title, "credit_institution", "the type's label, which falls back to its key here")

    def test_a_row_that_closes_leaves_the_roadmap(self) -> None:
        self.bank.activate()
        Licence.objects.filter(pk=self.certificate.pk).update(withdrawn_on=self.bank.today())
        TenantObligation.objects.filter(pk=self.entry_review.pk).update(applicability=Applicability.DOES_NOT_APPLY.value)
        self.assertEqual({item.item_type for item in self.read(kind="internal")}, {"review_due", "gap_target"})
        self.assertNotIn(f"review_due:{self.entry_review.id}", self.by_id())

    def test_the_registers_deadlines_need_register_read_and_a_certificate_does_not(self) -> None:
        self.assertEqual(
            {item.item_type for item in self.read(kind="internal", register_reader=False)},
            {"certificate_audit", "certificate_expiry"},
        )

    def test_the_filters_split_the_branches_and_all_holds_both(self) -> None:
        regulatory = self.read(kind="regulatory")
        self.assertEqual([item.item_type for item in regulatory], ["change_date"])
        whole = {item.id for item in self.read()}
        self.assertEqual(whole, {regulatory[0].id, *self.expected})

    def test_the_window_bounds_the_banks_own_deadlines_too(self) -> None:
        today = self.bank.today()
        items = self.read(kind="internal", date_from=today + datetime.timedelta(days=35), date_to=today + datetime.timedelta(days=100))
        self.assertEqual([item.item_type for item in items], ["gap_target", "gap_target", "certificate_audit"])

    def test_coming_up_answers_the_roadmaps_own_first_items_and_its_whole_count(self) -> None:
        """Today's panel and the roadmap page share every branch."""
        self.bank.activate()
        items, count = roadmap.coming_up(self.bank.tenant, ["en"], 3, register_reader=True)
        whole = self.read()
        self.assertEqual([item.id for item in items], [item.id for item in whole[:3]])
        self.assertEqual(count, len(whole))

    def test_the_calendar_carries_the_regulatory_date_and_none_of_our_own(self) -> None:
        """D-43, D-52: a calendar leaves the bank, so it carries public facts only; each of
        the internal branches is absent from it."""
        self.bank.activate()
        on_the_calendar = [item for _key, item in roadmap.calendar_items(self.bank.tenant, ["en"])]
        self.assertEqual([item.item_type for item in on_the_calendar], ["change_date"])
        for key in self.expected:
            with self.subTest(branch=key.split(":")[0]):
                self.assertNotIn(key, {item.id for item in on_the_calendar})


class RoadmapOwnDeadlinesCost(TestCase):
    """NFR-02: one query per branch and a fixed few to name them, whatever the number of rows."""

    bank: Bank

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("roadmap-own-cost")
        today = bank.today()
        term = licence_type_term()
        for number in range(10):
            entry = bank.entry(obligation(f"Duty {number}"), owner_team=bank.retail_team, next_review_date=today + datetime.timedelta(days=10 + number))
            bank.scope(entry, bank.fund_ab, owner=bank.erik, next_review_date=today + datetime.timedelta(days=10 + number))
            bank.gap(entry, owner_team=bank.cards, target_date=today + datetime.timedelta(days=10 + number))
            bank.activate()
            Licence.objects.create(
                tenant=bank.tenant, org_unit=bank.bank_ab, licence_type=term, valid_until=today + datetime.timedelta(days=10 + number), next_audit_on=today + datetime.timedelta(days=10 + number)
            )

    def test_the_query_count_does_not_grow_with_the_number_of_deadlines(self) -> None:
        today = self.bank.today()
        for last, expected in ((10, 5), (19, 50)):
            self.bank.activate()
            with self.subTest(items=expected), self.assertNumQueries(INTERNAL_QUERIES):
                items = roadmap.roadmap_items(
                    self.bank.tenant, ["en"], HomeRoadmapQuery(kind="internal", to=today + datetime.timedelta(days=last)), register_reader=True
                ).items
            self.assertEqual(len(items), expected)
