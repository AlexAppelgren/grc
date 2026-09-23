"""The two lists of changes (WAT-02, WAT-03, CAS-01, FP-01, FP-03, FP-04, NFR-02): the
bank's feed, with that bank's own case beside every row, and the platform console's queue
of change facts, which joins no case at all.

The two are separate reads on purpose and this file pins why. `GET /changes` is one bank's
feed: the library's facts about a reform and, beside them, that bank's own case, which no
other bank and no bleqq person ever sees. `GET /console/changes` is the library editor's
queue: a console session belongs to no tenant, so a case cannot be joined, and the answer
must carry no `case` member at all rather than a null one — a null would invite a screen to
render a bank's judgement in the console.

Nothing here is a settled fact until it is confirmed. A change is what an agent sighted: its
type stays the agent's suggestion until an agent of another definition or a person confirms
it (D-74), its links carry a confidence, and
`inFootprint` says the change is worth this bank's attention, never that an obligation
applies to it or that it complies (REG-01, REG-02).

Every date is pinned to the prototype's anchor week (`apps/watch/testing.py`), so nothing
here depends on the day the suite runs (playbook 8.3).
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from typing import Any

from django.conf import settings
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import CaseLinkDecision, ChangeCase
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import Obligation
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import testing as build
from apps.watch.models import ChangeObligation, ChangeTerm, RegulatoryChange
from apps.watch.write import watch_write

FEED = "/api/v1/changes"
CONSOLE = "/api/v1/console/changes"

D = datetime.date
LATER = D(2026, 10, 1)  # the lead reform comes into force
EARLIER = D(2026, 8, 1)  # a reform that already came into force
BETWEEN = D(2026, 9, 20)  # a reform of another regime, between the two, so the order is pinned
# The Monday of the ISO week the anchor sits in, in the bank's own time zone: the anchor is
# 2026-09-16 06:02 UTC, which is a Wednesday morning in Stockholm.
ANCHOR_WEEK = D(2026, 9, 14)
OTHER_WEEK = D(2026, 9, 7)

# Queries per feed read with a real session, measured 2026-09-21 and pinned so an N+1 shows
# up as a number (playbook 10). The request's savepoint pair (2); the session (identity flag
# on, the session row, flag off, the tenant activation, the tenant role permissions, the
# latest step-up: 6, hardening H13); the caller's tenant and locale (2); the footprint and
# its restricting dimensions (2); the count and the page, the page carrying the reader's own
# case in the same left join (2); the page's classification links (1); the urgency rows the
# page and the cases name (1); one label query each for change types, urgencies, flags and
# terms (4); the banks' own decisions about the suggested links (1); the jurisdiction terms
# the page's authorities reach (1, FP-04).
FEED_QUERIES = 2 + 6 + 2 + 2 + 2 + 1 + 1 + 4 + 1 + 1

# Queries per console read, measured the same way. The savepoint pair (2); the session of a
# platform person (the identity flag on, the session row, the flag off, the platform roles,
# the latest step-up: 5, one fewer than a bank's session, which also activates its tenant);
# the caller's locale (1); the count and the page (2); the page's classification links and
# one label query each for flags and terms (3); the suggested obligation links with their
# obligations, and those obligations' titles (2); the change types' labels (1). No
# footprint and no case: a console session belongs to no bank and has neither.
CONSOLE_QUERIES = 2 + 5 + 1 + 2 + 3 + 2 + 1


# A fact nobody has confirmed, filed by a builder that names no run, so no agent (D-74).
UNCONFIRMED: dict[str, Any] = {
    "confidence": None,
    "suggested": True,
    "confirmedOrigin": None,
    "suggestedByAgent": None,
    "confirmedByAgent": None,
}


def keys(response: Any) -> list[str]:
    return [row["stableKey"] for row in response.json()["items"]]


def text_of(row: Any) -> str:
    """One row as it leaves the server, for the assertions that are about what is *not* in
    it — a tone, another bank's words."""
    return json.dumps(row)


def set_status(case: ChangeCase, status: CaseStatusCategory) -> None:
    """Move a case out of `new`. Chunk 5 creates every case in `new` and the workflow that
    would move it is chunk 9, so the feed's tab filter has nothing else to read yet."""
    with transaction.atomic():
        tenancy.activate(case.tenant_id)
        ChangeCase.objects.filter(pk=case.pk).update(status=status.value)


def confirm_so_what(case: ChangeCase, person: User) -> None:
    """A person in the bank stood behind the wording. The check constraint makes a
    confirmation name a person and a time, so both are written."""
    with transaction.atomic():
        tenancy.activate(case.tenant_id)
        ChangeCase.objects.filter(pk=case.pk).update(
            so_what_text="Our own words.", so_what_confirmed=True, so_what_confirmed_by=person, so_what_confirmed_at=timezone.now()
        )


def set_first_seen(change: RegulatoryChange, seen: datetime.datetime) -> None:
    """Move a change's first sighting, for the week filter. Through the watch door, because
    a change is a library row and there is exactly one way to write one."""
    with watch_write("test fixture"):
        RegulatoryChange.objects.filter(pk=change.pk).update(first_seen_at=seen)


class WatchReadFixture(TestCase):
    """Four reforms, two banks whose footprints do not overlap, and the cases one of them
    holds. Built once: every read below is a read."""

    tenants: Any
    inside: Tenant
    outside: Tenant
    reader: User
    other_reader: User
    editor: User
    lead: RegulatoryChange
    earlier: RegulatoryChange
    undated: RegulatoryChange
    elsewhere: RegulatoryChange
    obligation: Obligation
    lead_case: ChangeCase
    earlier_case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        build.seed_watch_reference()
        # Library rows first, while no tenant is activated: a change is a shared fact and a
        # case is a bank's own, and the order here keeps the two zones apart in the fixture
        # exactly as the product keeps them apart at runtime.
        instrument = library_build.instrument(key="lvm", short_name="LVM", regime="regime:securities")
        cls.obligation = library_build.obligation(
            instrument,
            key="obl-research-payments",
            titles={"en": "Assess the quality of investment research paid for"},
            ref_label="11 kap. 4 §",
        )
        cls.lead = build.change_with_timeline(
            stable_key="chg-lead",
            first_seen_at=build.ANCHOR - datetime.timedelta(seconds=0),
            title="FI adopts amended rules on paying for investment research",
            key_date=LATER,
            urgency="act_now",
        )
        build.obligation_link(cls.lead, cls.obligation, confidence=0.82)
        cls.earlier = build.change_with_timeline(
            stable_key="chg-earlier",
            first_seen_at=build.ANCHOR - datetime.timedelta(seconds=60),
            title="FI reports on its supervision of research payments",
            change_type="supervision",
            key_date=EARLIER,
            urgency="monitor",
        )
        cls.undated = build.change_with_timeline(
            stable_key="chg-undated",
            first_seen_at=build.ANCHOR - datetime.timedelta(seconds=120),
            title="FI consults on client categorisation",
            change_type="proposal",
            key_date=None,
            urgency="within_3_months",
        )
        cls.elsewhere = build.change_with_timeline(
            stable_key="chg-elsewhere",
            first_seen_at=build.ANCHOR - datetime.timedelta(seconds=180),
            title="New rules on reporting suspicious transactions",
            terms=("regime:aml",),
            flags=(),
            key_date=BETWEEN,
            urgency="act_now",
        )
        # Every reform an agent registered suggests the duty it touches, so a page always
        # carries links and its query count is the same whatever the page size.
        for change in (cls.earlier, cls.undated, cls.elsewhere):
            build.obligation_link(change, cls.obligation, confidence=0.4)
        set_first_seen(cls.undated, datetime.datetime(2026, 9, 9, 7, 0, tzinfo=datetime.UTC))

        cls.tenants = cases_build.two_tenants_with_different_footprints()
        cls.inside, cls.outside = cls.tenants.inside, cls.tenants.outside
        cls.reader = factories.member_user(cls.inside, roles=("compliance_officer",))
        cls.other_reader = factories.member_user(cls.outside, roles=("reader",))
        cls.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")

        cls.lead_case = cases_build.case(
            cls.inside, cls.lead, urgency="act_now", so_what_text="Confirm the documented criteria exist."
        )
        cases_build.link_decision(cls.lead_case, cls.obligation, decision=CaseLinkDecision.ACCEPTED)
        cls.earlier_case = cases_build.case(cls.inside, cls.earlier, urgency="monitor", owner=cls.reader)
        set_status(cls.earlier_case, CaseStatusCategory.ASSIGNED)
        confirm_so_what(cls.earlier_case, cls.reader)
        cases_build.case(cls.inside, cls.undated, urgency="within_3_months")
        # The other bank's own case for the change that is in its footprint and not in the
        # first bank's: the feed must never carry it into the first bank's answer.
        cases_build.case(cls.outside, cls.elsewhere, urgency="act_now", so_what_text="Not for the other bank to read.")

    def feed(self, params: Any = None, headers: Any = None) -> Any:
        return self.client.get(FEED, params or {}, **(headers if headers is not None else sign_in(self.reader, tenant=self.inside)))

    def console(self, params: Any = None, headers: Any = None) -> Any:
        return self.client.get(CONSOLE, params or {}, **(headers if headers is not None else sign_in(self.editor)))


class FeedTests(WatchReadFixture):
    """`GET /changes`: one bank's feed."""

    def test_the_feed_answers_the_changes_that_reach_this_bank(self) -> None:
        response = self.feed()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([row["stableKey"] for row in body["items"]], ["chg-lead", "chg-earlier", "chg-undated"])
        self.assertEqual(body["total"], 3)

    def test_the_order_is_the_key_date_then_the_first_sighting_with_no_date_last(self) -> None:
        """A change with no key date sorts last, not first: PostgreSQL puts nulls first on a
        descending sort, which would open the feed with the reforms nobody has dated."""
        self.assertEqual(keys(self.feed({"footprint": "all"})), ["chg-lead", "chg-elsewhere", "chg-earlier", "chg-undated"])

    def test_a_row_carries_the_librarys_facts_and_this_banks_own_case(self) -> None:
        row = next(item for item in self.feed().json()["items"] if item["stableKey"] == "chg-lead")
        self.assertEqual(row["title"], "FI adopts amended rules on paying for investment research")
        self.assertEqual(row["authorityLabel"], "Finansinspektionen")
        self.assertEqual(row["status"], "active")
        self.assertEqual((row["keyDate"], row["keyDatePrecision"], row["keyDateLabel"]), ("2026-10-01", "day", "In force"))
        self.assertEqual((row["publishedOn"], row["publishedPrecision"]), ("2026-09-15", "day"))
        self.assertTrue(row["inFootprint"])
        case = row["case"]
        self.assertEqual(case["id"], str(self.lead_case.id))
        self.assertEqual(case["category"], "new")
        self.assertEqual(case["urgency"]["key"], "act_now")
        self.assertFalse(case["urgencyConfirmed"])
        self.assertTrue(case["footprintMatch"])
        self.assertEqual(case["soWhatText"], "Confirm the documented criteria exist.")
        self.assertFalse(case["soWhatConfirmed"])
        self.assertIsNone(case["soWhatConfirmedAt"])
        self.assertIsNone(case["ownerId"])
        self.assertEqual(case["allowedTransitions"], [], "the workflow that would move a case is chunk 9")
        self.assertEqual(
            case["obligationDecisions"],
            [{"obligationId": str(self.obligation.id), "decision": "accepted", "decidedAt": case["obligationDecisions"][0]["decidedAt"], "decidedByName": None}],
        )

    def test_a_change_the_bank_has_no_case_for_answers_a_null_case(self) -> None:
        row = next(item for item in self.feed({"footprint": "all"}).json()["items"] if item["stableKey"] == "chg-elsewhere")
        self.assertIsNone(row["case"], "the other bank's case is not this bank's, and null is the honest answer")
        self.assertFalse(row["inFootprint"])

    def test_the_facts_are_keys_and_kinds_with_their_suggestion_marker_and_never_a_tone(self) -> None:
        row = next(item for item in self.feed().json()["items"] if item["stableKey"] == "chg-lead")
        self.assertEqual(row["changeType"], {"ref": {"key": "adopted", "kind": "adopted", "label": "Adopted"}, **UNCONFIRMED})
        self.assertEqual([fact["ref"]["key"] for fact in row["flags"]], ["advice_perimeter"])
        self.assertEqual([fact["ref"]["key"] for fact in row["terms"]], ["securities"])
        for fact in row["flags"] + row["terms"]:
            self.assertEqual(sorted(fact), ["confidence", "confirmedByAgent", "confirmedOrigin", "ref", "suggested", "suggestedByAgent"])
            self.assertEqual(sorted(fact["ref"]), ["key", "kind", "label"])
            self.assertTrue(fact["suggested"], "an agent's classification is a suggestion until an editor confirms it")
        # An urgency row's own `kind` column is its pill tone, and a tone is nobody's to
        # send (NFR-03): the reference carries the key the screen reads its tone from.
        self.assertEqual(row["suggestedUrgency"], {"key": "act_now", "kind": None, "label": "Act now"})
        self.assertEqual(row["case"]["urgency"]["kind"], None)
        for text in ("negative", "warning", "positive", "brand", "notice", "information"):
            self.assertNotIn(f'"{text}"', text_of(row))

    def test_the_footprint_filter(self) -> None:
        self.assertEqual(keys(self.feed()), ["chg-lead", "chg-earlier", "chg-undated"], "footprint=in is the default")
        self.assertEqual(keys(self.feed({"footprint": "in"})), ["chg-lead", "chg-earlier", "chg-undated"])
        self.assertEqual(keys(self.feed({"footprint": "all"})), ["chg-lead", "chg-elsewhere", "chg-earlier", "chg-undated"])
        self.assertEqual(self.feed({"footprint": "watched"}).json(), {"items": [], "total": 0})
        self.assertEqual(self.feed({"footprint": "inside"}).status_code, 422)
        self.assertEqual(self.feed({"inFootprint": "true"}).status_code, 422)

    def test_every_filter(self) -> None:
        self.assertEqual(keys(self.feed({"tab": "assigned"})), ["chg-earlier"])
        self.assertEqual(keys(self.feed({"tab": "closed"})), [])
        self.assertEqual(keys(self.feed({"status": "active"})), ["chg-lead", "chg-earlier", "chg-undated"])
        self.assertEqual(keys(self.feed({"status": "withdrawn"})), [])
        self.assertEqual(keys(self.feed({"urgency": "monitor"})), ["chg-earlier"])
        self.assertEqual(keys(self.feed({"changeType": "supervision"})), ["chg-earlier"])
        self.assertEqual(keys(self.feed({"ownerId": str(self.reader.id)})), ["chg-earlier"])
        self.assertEqual(keys(self.feed({"termId": str(build.term("regime:securities").id)})), ["chg-lead", "chg-earlier", "chg-undated"])
        self.assertEqual(keys(self.feed({"termId": str(build.term("regime:aml").id), "footprint": "all"})), ["chg-elsewhere"])
        self.assertEqual(keys(self.feed({"q": "RESEARCH"})), ["chg-lead", "chg-earlier"], "the title or the summary, any case")
        self.assertEqual(keys(self.feed({"q": "nothing like this"})), [])
        self.assertEqual(keys(self.feed({"unconfirmedSoWhat": "true"})), ["chg-lead", "chg-undated"], "only what is still an AI draft")
        self.assertEqual(keys(self.feed({"unconfirmedSoWhat": "false"})), ["chg-earlier"], "and only what a person stood behind")
        self.assertEqual(keys(self.feed({"week": ANCHOR_WEEK.isoformat()})), ["chg-lead", "chg-earlier"])
        self.assertEqual(keys(self.feed({"week": OTHER_WEEK.isoformat()})), ["chg-undated"])
        self.assertEqual(self.feed({"q": "x" * 201}).status_code, 422)

    def test_a_tab_other_than_all_answers_nothing_for_a_bank_with_no_case(self) -> None:
        headers = sign_in(self.other_reader, tenant=self.outside)
        self.assertEqual(keys(self.feed({"tab": "new", "footprint": "all"}, headers)), ["chg-elsewhere"])
        self.assertEqual(keys(self.feed({"tab": "assessing", "footprint": "all"}, headers)), [])

    def test_another_banks_case_never_reaches_this_banks_feed(self) -> None:
        """The join is the reader's own zone. A change both banks hold a case for answers
        each of them its own case and never the other's (NFR-01)."""
        both = build.change_with_timeline(stable_key="chg-both", title="Both banks watch this one", key_date=LATER)
        mine = cases_build.case(self.inside, both, so_what_text="Ours.")
        theirs = cases_build.case(self.outside, both, footprint_match=False, so_what_text="Theirs.")

        row = next(item for item in self.feed().json()["items"] if item["stableKey"] == "chg-both")
        self.assertEqual(row["case"]["id"], str(mine.id))
        self.assertEqual(row["case"]["soWhatText"], "Ours.")
        self.assertNotIn("Theirs.", text_of(row))

        other = self.feed({"footprint": "all"}, sign_in(self.other_reader, tenant=self.outside)).json()
        theirs_row = next(item for item in other["items"] if item["stableKey"] == "chg-both")
        self.assertEqual(theirs_row["case"]["id"], str(theirs.id))
        self.assertEqual(theirs_row["case"]["soWhatText"], "Theirs.")
        self.assertFalse(theirs_row["case"]["footprintMatch"])

    def test_pagination(self) -> None:
        first = self.feed({"limit": 2}).json()
        self.assertEqual(([row["stableKey"] for row in first["items"]], first["total"]), (["chg-lead", "chg-earlier"], 3))
        self.assertEqual(keys(self.feed({"limit": 2, "offset": 2})), ["chg-undated"])
        self.assertEqual(self.feed({"offset": 50}).json(), {"items": [], "total": 3}, "an empty page is 200")
        self.assertEqual(self.feed({"limit": settings.API_PAGE_SIZE_MAX}).status_code, 200)
        self.assertEqual(self.feed({"limit": settings.API_PAGE_SIZE_MAX + 1}).status_code, 422)
        self.assertEqual(self.feed({"limit": 0}).status_code, 422)

    def test_a_bank_nothing_reaches_reads_an_empty_feed_and_not_an_error(self) -> None:
        """A bank whose footprint no registered reform touches. Not a bank with no
        footprint at all: an empty restriction list means "no restriction", so that bank
        would see everything (playbook 4.5)."""
        elsewhere = cases_build.two_tenants_with_different_footprints(inside="regime:insurance", outside="regime:tax").inside
        reader = factories.member_user(elsewhere, roles=("reader",))
        response = self.feed(None, sign_in(reader, tenant=elsewhere))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    def test_the_query_count_does_not_grow_with_the_page(self) -> None:
        for limit in (1, 3):
            headers = sign_in(self.reader, tenant=self.inside)
            with self.subTest(limit=limit), self.assertNumQueries(FEED_QUERIES):
                response = self.feed({"limit": limit}, headers)
            self.assertEqual(len(response.json()["items"]), limit)


class FeedPerformanceTests(TestCase):
    """NFR-02, playbook 10: a full page of the feed stays inside the API budget and reports
    what it spent in `Server-Timing`."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        build.seed_watch_reference()
        instrument = library_build.instrument(key="lvm", short_name="LVM", regime="regime:securities")
        obligation = library_build.obligation(instrument, key="obl-bulk", titles={"en": "A duty"})
        changes = [
            build.change_with_timeline(stable_key=f"chg-bulk-{index:03d}", key_date=LATER - datetime.timedelta(days=index))
            for index in range(settings.API_PAGE_SIZE_MAX + 5)
        ]
        for change in changes:
            build.obligation_link(change, obligation, confidence=0.5)
        cls.tenant = cases_build.two_tenants_with_different_footprints().inside
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        for change in changes:
            cases_build.case(cls.tenant, change)

    def test_a_full_page_stays_inside_the_budget(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        params = {"limit": settings.API_PAGE_SIZE_MAX}
        response = self.client.get(FEED, params, **headers)
        self.assertEqual(len(response.json()["items"]), settings.API_PAGE_SIZE_MAX)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        # CPU time on the request thread, the best of five: what the read costs, without the
        # waits a loaded machine adds, so the bound holds on a busy CI runner too. The suite
        # runs under coverage, whose tracer is paused for the timed requests only; the one
        # above stays traced, so coverage is unchanged.
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.client.get(FEED, params, **headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)


class ConsoleChangeQueueTests(WatchReadFixture):
    """`GET /console/changes`: the library editor's queue. No tenant, so no case."""

    def test_the_queue_holds_every_change_with_a_fact_nobody_has_confirmed(self) -> None:
        response = self.console()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(sorted(row["stableKey"] for row in body["items"]), ["chg-earlier", "chg-elsewhere", "chg-lead", "chg-undated"])
        self.assertEqual(body["total"], 4)

    def test_a_console_row_carries_no_case_member_at_all(self) -> None:
        """Not a null case: a console session belongs to no bank, and a member that is
        merely null invites a screen to render one bank's judgement in the console."""
        for row in self.console().json()["items"]:
            self.assertNotIn("case", row)
            self.assertNotIn("inFootprint", row)

    def test_a_row_names_the_facts_the_agent_put_forward_and_counts_them(self) -> None:
        row = next(item for item in self.console().json()["items"] if item["stableKey"] == "chg-lead")
        self.assertEqual(row["changeType"], {"ref": {"key": "adopted", "kind": "adopted", "label": "Adopted"}, **UNCONFIRMED})
        self.assertEqual([fact["ref"]["key"] for fact in row["flags"]], ["advice_perimeter"])
        self.assertEqual([fact["ref"]["key"] for fact in row["terms"]], ["securities"])
        link = row["obligations"][0]
        self.assertEqual(link["obligationId"], str(self.obligation.id))
        self.assertEqual(link["title"], "Assess the quality of investment research paid for")
        self.assertEqual(link["instrumentShortName"], "LVM")
        self.assertEqual(link["refLabel"], "11 kap. 4 §")
        self.assertEqual((link["origin"], link["confidence"], link["confirmed"]), ("agent", 0.82, False))
        # Its type, its flag, its scope term and its obligation link: four facts waiting.
        self.assertEqual(row["unconfirmedCount"], 4)

    def test_the_queue_is_newest_first_by_when_the_reform_was_seen(self) -> None:
        order = [row["stableKey"] for row in self.console().json()["items"]]
        self.assertEqual(order[-1], "chg-undated", "the oldest sighting comes last")

    def test_every_filter(self) -> None:
        authority = self.lead.authority_id
        self.assertEqual(len(self.console({"confirmed": "all"}).json()["items"]), 4)
        self.assertEqual(sorted(keys(self.console({"authorityId": str(authority)}))), ["chg-earlier", "chg-elsewhere", "chg-lead", "chg-undated"])
        self.assertEqual(keys(self.console({"q": "suspicious"})), ["chg-elsewhere"])
        self.assertEqual(keys(self.console({"q": "nothing like this"})), [])
        self.assertEqual(self.console({"confirmed": "true"}).status_code, 422)
        self.assertEqual(self.console({"q": "x" * 201}).status_code, 422)

    def test_a_change_whose_every_fact_is_confirmed_is_not_in_the_queue(self) -> None:
        """A change whose type, flags, scope terms and links somebody has confirmed has
        nothing left to confirm and is not work, whoever registered it: a person's filing is
        a suggestion too (D-74). `confirmed=all` still finds it."""
        with watch_write("test fixture"):
            RegulatoryChange.objects.filter(pk=self.undated.pk).update(
                origin="user", change_type_suggested=False, change_type_confirmed_by=self.editor, change_type_confirmed_at=timezone.now()
            )
            ChangeTerm.objects.filter(change=self.undated).update(
                suggested=False, confirmed_by=self.editor, confirmed_at=timezone.now()
            )
            ChangeObligation.objects.filter(change=self.undated).update(
                confirmed_by=self.editor, confirmed_at=timezone.now()
            )
        self.assertNotIn("chg-undated", keys(self.console()))
        self.assertIn("chg-undated", keys(self.console({"confirmed": "all"})))

    def test_pagination(self) -> None:
        first = self.console({"limit": 2}).json()
        self.assertEqual((len(first["items"]), first["total"]), (2, 4))
        self.assertEqual(self.console({"offset": 50}).json(), {"items": [], "total": 4}, "an empty page is 200")
        self.assertEqual(self.console({"limit": settings.API_PAGE_SIZE_MAX + 1}).status_code, 422)

    def test_the_query_count_does_not_grow_with_the_page(self) -> None:
        for limit in (1, 4):
            headers = sign_in(self.editor)
            with self.subTest(limit=limit), self.assertNumQueries(CONSOLE_QUERIES):
                response = self.console({"limit": limit, "confirmed": "all"}, headers)
            self.assertEqual(len(response.json()["items"]), min(limit, 4))
