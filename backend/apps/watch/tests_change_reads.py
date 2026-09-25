"""Reading one change and an obligation's related changes (WAT-02, WAT-03, WAT-04,
CAS-01, INV-06, NFR-02).

`GET /changes/{changeId}` is the whole change page: the reform's sourced facts — its
type, its flags, its scope, its timeline from consultation to in force, the pages it was
found on and the obligations it affects — and beside them the reader's own bank's case.
`GET /obligations/{obligationId}/changes` is the panel an obligation shows, with the
count of changes still open for this bank.

What both have to keep apart, and what this file pins: everything outside `case` is a
library fact every bank shares, everything inside it is this bank's own and another
bank's never appears; a link a library editor has not confirmed carries `confirmed:
false`, which means "not checked" and never "not related"; and `openCount` counts this
bank's open cases and says nothing about whether the bank complies (REG-02).

An id nobody can reach answers 404 rather than a filtered answer, so no id can be probed
for. Every date is the prototype's anchor week, never one derived from "now".
"""

from __future__ import annotations

import datetime
import json
import sys
import time
import uuid
from typing import Any

from django.conf import settings
from django.test import TestCase

from apps.cases import testing as cases_build
from apps.cases.models import CaseLinkDecision, ChangeCase
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import Obligation
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.models import Tenant
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, sign_in, stub_session, user_principal
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import testing as build
from apps.watch.models import ChangeObligation, ChangeTerm, RegulatoryChange
from apps.watch.tests_reading import set_status
from apps.watch.write import watch_write

CHANGES = "/api/v1/changes"
OBLIGATIONS = "/api/v1/obligations"

D = datetime.date
LATER = D(2026, 10, 1)
EARLIER = D(2026, 8, 1)

# Queries per change read with a real session, measured 2026-09-21 and pinned so an N+1
# shows up as a number (playbook 10). The request's savepoint pair (2); the session (6,
# hardening H13); the caller's tenant and locale (2); the footprint and its restricting
# dimensions (2); the change with its type and the reader's own case in one left join (1);
# its classification links and one label query each for flags and terms (3); its suggested
# obligation links with their obligations, and those obligations' titles (2); the urgency
# rows the change and the case name, with their labels (2); the change type's labels (1);
# its timeline (1); its pages (1); the bank's own decisions about the links (1); the
# jurisdiction terms its authority reaches (1, FP-04); the case's workflow block, the case
# with its people and reasons joined and the guards' facts (2, c9-case-contract).
CHANGE_QUERIES = 2 + 6 + 2 + 2 + 1 + 3 + 2 + 2 + 1 + 1 + 1 + 1 + 1 + 2

# Queries per related-changes read, measured the same way: the savepoint pair (2); the
# session (6); the caller's tenant and locale (2); the footprint and its restricting
# dimensions (2); the obligation itself (1); the count and the page (2); the open-change
# count (1); the classification links and two label queries (3); the urgency rows and
# their labels (2); the change type's labels (1); the bank's own link decisions (1); the
# jurisdiction terms the page's authorities reach (1, FP-04).
RELATED_QUERIES = 2 + 6 + 2 + 2 + 1 + 2 + 1 + 3 + 2 + 1 + 1 + 1


def confirm_link(change: RegulatoryChange, obligation: Obligation, editor: User) -> None:
    """A person confirms the link for the shared library, as a library editor still may
    with a passkey (D-74). Through the watch door, because `change_obligation` is a library
    row."""
    with watch_write("test fixture"):
        ChangeObligation.objects.filter(change=change, obligation=obligation).update(
            confirmed_by=editor, confirmed_at=build.ANCHOR
        )


def confirm_flag(change: RegulatoryChange, flag_key: str, editor: User) -> None:
    """A person confirms one flag of a change for the shared library, as a library editor
    still may with a passkey (D-74). `suggested` and the confirmation columns move together
    because `change_term`'s check constraint refuses any other combination (WAT-03)."""
    with watch_write("test fixture"):
        ChangeTerm.objects.filter(
            change=change,
            flag__key=flag_key,
        ).update(suggested=False, confirmed_by=editor, confirmed_at=build.ANCHOR)


class ChangeReadFixture(TestCase):
    inside: Tenant
    outside: Tenant
    reader: User
    other_reader: User
    editor: User
    lead: RegulatoryChange
    later_change: RegulatoryChange
    research: Obligation
    reporting: Obligation
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        build.seed_watch_reference()
        instrument = library_build.instrument(key="lvm", short_name="LVM", regime="regime:securities")
        cls.research = library_build.obligation(
            instrument,
            key="obl-research-payments",
            titles={"sv": "Bedöm kvaliteten på analysen", "en": "Assess the quality of investment research paid for"},
            ref_label="11 kap. 4 §",
        )
        cls.reporting = library_build.obligation(
            instrument, key="obl-reporting", titles={"en": "Report quarterly"}, ref_label="12 kap. 1 §"
        )
        cls.lead = build.change_with_timeline(stable_key="chg-lead", key_date=LATER, urgency="act_now")
        build.document(cls.lead, url="https://www.fi.se/en/published/news/2026/again/", is_primary=False, is_duplicate=True)
        build.obligation_link(cls.lead, cls.research, confidence=0.82)
        build.obligation_link(cls.lead, cls.reporting, confidence=0.41)
        cls.later_change = build.change_with_timeline(
            stable_key="chg-second", title="FI returns to research payments", key_date=EARLIER, urgency="monitor"
        )
        build.obligation_link(cls.later_change, cls.research, confidence=0.6)

        tenants = cases_build.two_tenants_with_different_footprints()
        cls.inside, cls.outside = tenants.inside, tenants.outside
        cls.reader = factories.member_user(cls.inside, roles=("compliance_officer",))
        cls.other_reader = factories.member_user(cls.outside, roles=("reader",))
        cls.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        confirm_link(cls.lead, cls.research, cls.editor)

        cls.case = cases_build.case(cls.inside, cls.lead, urgency="act_now", so_what_text="Check the criteria.")
        cases_build.link_decision(cls.case, cls.reporting, decision=CaseLinkDecision.REMOVED)
        cases_build.case(cls.inside, cls.later_change, urgency="monitor")
        # The other bank's own case for the same reform, so every assertion below about
        # "never another bank's" has something real to be wrong about.
        cases_build.case(cls.outside, cls.lead, footprint_match=False, so_what_text="Theirs, not yours.")

    def read(self, change: RegulatoryChange, headers: Any = None) -> Any:
        return self.client.get(
            f"{CHANGES}/{change.id}", **(headers if headers is not None else sign_in(self.reader, tenant=self.inside))
        )

    def feed(self, headers: Any = None) -> Any:
        """The same bank's watch feed, so a detail read can be held against the row a
        reader saw before opening it."""
        return self.client.get(CHANGES, **(headers if headers is not None else sign_in(self.reader, tenant=self.inside)))

    def related(self, obligation: Obligation, params: Any = None, headers: Any = None) -> Any:
        return self.client.get(
            f"{OBLIGATIONS}/{obligation.id}/changes",
            params or {},
            **(headers if headers is not None else sign_in(self.reader, tenant=self.inside)),
        )


class ChangeDetailTests(ChangeReadFixture):
    """`GET /changes/{changeId}`."""

    def test_the_change_carries_its_sourced_facts(self) -> None:
        body = self.read(self.lead).json()
        self.assertEqual(body["id"], str(self.lead.id))
        self.assertEqual(body["stableKey"], "chg-lead")
        self.assertEqual(body["title"], "FI adopts amended rules on paying for investment research")
        self.assertEqual(body["changeType"], {"key": "adopted", "kind": "adopted", "label": "Adopted"})
        self.assertEqual(body["authorityLabel"], "Finansinspektionen")
        self.assertEqual(body["authorityId"], str(self.lead.authority_id))
        self.assertEqual((body["keyDate"], body["keyDatePrecision"], body["keyDateLabel"]), ("2026-10-01", "day", "In force"))
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["origin"], "agent")
        self.assertEqual(body["model"], "agent pipeline 0.4")
        self.assertEqual([fact["ref"]["key"] for fact in body["flags"]], ["advice_perimeter"])
        self.assertEqual([fact["ref"]["key"] for fact in body["terms"]], ["securities"])
        self.assertEqual(body["suggestedUrgency"], {"key": "act_now", "kind": None, "label": "Act now"})
        self.assertIsNone(body["soWhatDraft"], "nothing has drafted one yet")
        self.assertTrue(body["inFootprint"])

    def test_the_detail_answers_the_same_provenance_for_a_fact_as_the_feed_row(self) -> None:
        """A flag an agent suggested and a flag a library editor confirmed read the same on
        the change page as in the feed.

        The regression this pins: the change page built the same facts and then kept only
        each one's vocabulary reference, so on the one screen where a person judges a
        change an individual flag or scope term could not be shown as the agent's reading
        (WAT-03, 2026-09-21).
        """
        confirm_flag(self.lead, "advice_perimeter", self.editor)
        detail = self.read(self.lead).json()
        row = next(item for item in self.feed().json()["items"] if item["id"] == str(self.lead.id))
        # Keyed by the vocabulary key rather than by position: what a page happens to order
        # first must never decide what a provenance assertion compares.
        facts = {fact["ref"]["key"]: fact for fact in detail["flags"] + detail["terms"]}
        self.assertEqual(facts, {fact["ref"]["key"]: fact for fact in row["flags"] + row["terms"]})
        self.assertEqual(
            facts["advice_perimeter"],
            {
                "ref": {"key": "advice_perimeter", "kind": None, "label": "Advice perimeter"},
                "confidence": 0.74,
                "suggested": False,
                # A person confirmed it, so it reads as a person's and names no agent (D-74).
                "confirmedOrigin": "user",
                "suggestedByAgent": None,
                "confirmedByAgent": None,
            },
        )
        self.assertEqual(
            facts["securities"],
            {
                "ref": {"key": "securities", "kind": None, "label": "Securities"},
                "confidence": 0.74,
                "suggested": True,
                "confirmedOrigin": None,
                "suggestedByAgent": None,
                "confirmedByAgent": None,
            },
        )

    def test_the_timeline_is_in_sort_order_with_each_date_precision(self) -> None:
        events = self.read(self.lead).json()["events"]
        self.assertEqual([event["label"] for event in events], ["Consultation closed", "In force"])
        self.assertEqual([event["sortOrder"] for event in events], [1, 2])
        self.assertEqual([event["eventDate"] for event in events], ["2026-06-01", "2026-10-01"])
        self.assertEqual({event["datePrecision"] for event in events}, {"day"})
        self.assertEqual([event["occurred"] for event in events], [True, False])

    def test_the_pages_come_with_the_primary_first_and_the_duplicates_counted(self) -> None:
        body = self.read(self.lead).json()
        self.assertEqual([document["isPrimary"] for document in body["documents"]], [True, False])
        self.assertEqual([document["isDuplicate"] for document in body["documents"]], [False, True])
        self.assertEqual(body["duplicateCount"], 1)
        self.assertEqual(body["documents"][0]["publisher"], "Finansinspektionen")
        self.assertEqual(body["documents"][0]["riskFlags"], [])

    def test_a_link_says_whether_an_editor_confirmed_it_and_never_that_it_is_unrelated(self) -> None:
        links = {link["obligationId"]: link for link in self.read(self.lead).json()["obligations"]}
        confirmed = links[str(self.research.id)]
        self.assertEqual(confirmed["title"], "Assess the quality of investment research paid for")
        self.assertEqual((confirmed["instrumentShortName"], confirmed["refLabel"]), ("LVM", "11 kap. 4 §"))
        self.assertEqual((confirmed["origin"], confirmed["confidence"], confirmed["confirmed"]), ("agent", 0.82, True))
        # This bank said "not related to us" about the other link. The library row is
        # untouched: it is still a suggestion for every other bank (WAT-04, ruling C).
        self.assertFalse(links[str(self.reporting.id)]["confirmed"])
        self.assertEqual(links[str(self.reporting.id)]["confidence"], 0.41)

    def test_the_reader_sees_its_own_case_and_never_another_banks(self) -> None:
        case = self.read(self.lead).json()["case"]
        self.assertEqual(case["id"], str(self.case.id))
        self.assertEqual(case["soWhatText"], "Check the criteria.")
        self.assertTrue(case["footprintMatch"])
        self.assertEqual(
            [(d["obligationId"], d["decision"]) for d in case["obligationDecisions"]],
            [(str(self.reporting.id), "removed")],
        )
        self.assertNotIn("Theirs, not yours.", json.dumps(self.read(self.lead).json()))

        theirs = self.read(self.lead, sign_in(self.other_reader, tenant=self.outside)).json()
        self.assertEqual(theirs["case"]["soWhatText"], "Theirs, not yours.")
        self.assertFalse(theirs["case"]["footprintMatch"])
        self.assertFalse(theirs["inFootprint"], "the same library record, a different bank's scope")

    def test_a_change_this_bank_has_no_case_for_answers_a_null_case(self) -> None:
        alone = build.change_with_timeline(stable_key="chg-alone", key_date=LATER)
        body = self.read(alone).json()
        self.assertIsNone(body["case"])
        self.assertEqual(body["obligations"], [])
        self.assertEqual(body["duplicateCount"], 0)

    def test_an_id_that_is_not_there_is_404_and_never_a_trace(self) -> None:
        response = self.client.get(f"{CHANGES}/{uuid.uuid4()}", **sign_in(self.reader, tenant=self.inside))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")
        self.assertEqual(response.headers["Content-Type"], "application/problem+json")
        self.assertNotIn("traceback", response.content.decode().lower())

    def test_the_gate_is_watch_read(self) -> None:
        self.assertEqual(self.client.get(f"{CHANGES}/{self.lead.id}").status_code, 401)
        without = user_principal(permissions={perms.CASES_READ}, tenant_id=self.inside.id)
        with stub_session(without):
            refused = self.client.get(f"{CHANGES}/{self.lead.id}", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.WATCH_READ))

    def test_the_query_count_is_pinned_and_the_read_stays_inside_the_budget(self) -> None:
        headers = sign_in(self.reader, tenant=self.inside)
        with self.assertNumQueries(CHANGE_QUERIES):
            response = self.read(self.lead, headers)
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.read(self.lead, headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)


class RelatedChangesTests(ChangeReadFixture):
    """`GET /obligations/{obligationId}/changes`."""

    def test_the_confirmed_link_comes_first_then_the_newest_key_date(self) -> None:
        body = self.related(self.research).json()
        self.assertEqual([row["stableKey"] for row in body["items"]], ["chg-lead", "chg-second"])
        self.assertEqual(body["total"], 2)

    def test_a_row_carries_the_change_type_urgency_and_key_date_with_this_banks_case(self) -> None:
        row = self.related(self.research).json()["items"][0]
        self.assertEqual(row["changeType"]["ref"], {"key": "adopted", "kind": "adopted", "label": "Adopted"})
        self.assertTrue(row["changeType"]["suggested"])
        self.assertEqual(row["suggestedUrgency"], {"key": "act_now", "kind": None, "label": "Act now"})
        self.assertEqual((row["keyDate"], row["keyDatePrecision"]), ("2026-10-01", "day"))
        self.assertEqual(row["case"]["urgency"], {"key": "act_now", "kind": None, "label": "Act now"})

    def test_the_open_count_is_this_banks_own_and_counts_cases_not_compliance(self) -> None:
        self.assertEqual(self.related(self.research).json()["openCount"], 2)
        set_status(self.case, CaseStatusCategory.CLOSED)
        self.assertEqual(self.related(self.research).json()["openCount"], 1, "a closed case is no longer open work")
        # Another bank reading the same obligation counts its own cases and no others.
        other = self.related(self.research, headers=sign_in(self.other_reader, tenant=self.outside)).json()
        self.assertEqual(other["openCount"], 1)
        self.assertEqual(other["total"], 2, "the links themselves are library facts, the same for every bank")

    def test_the_open_count_comes_from_the_query_and_not_from_the_page(self) -> None:
        first = self.related(self.research, {"limit": 1}).json()
        self.assertEqual((len(first["items"]), first["total"], first["openCount"]), (1, 2, 2))

    def test_an_obligation_no_change_touches_is_an_empty_answer_and_not_a_404(self) -> None:
        quiet = library_build.obligation(
            library_build.instrument(key="quiet", short_name="QUIET", regime="regime:securities"), key="obl-quiet", titles={"en": "Nothing yet"}
        )
        self.assertEqual(self.related(quiet).json(), {"items": [], "total": 0, "openCount": 0})

    def test_an_id_that_is_not_there_is_404(self) -> None:
        response = self.client.get(f"{OBLIGATIONS}/{uuid.uuid4()}/changes", **sign_in(self.reader, tenant=self.inside))
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_another_banks_private_obligation_is_404_and_never_403(self) -> None:
        """A record row-level security does not show the caller is not there, so it answers
        exactly as an id that never existed (INV-07)."""
        private = library_build.obligation(
            library_build.instrument(key="theirs", short_name="THEIRS", regime="regime:securities", owner_tenant=self.outside),
            key="obl-theirs",
            titles={"en": "Their own duty"},
            owner_tenant=self.outside,
        )
        response = self.related(private)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_pagination(self) -> None:
        self.assertEqual(len(self.related(self.research, {"limit": 1}).json()["items"]), 1)
        self.assertEqual(self.related(self.research, {"offset": 50}).json()["items"], [])
        self.assertEqual(self.related(self.research, {"limit": settings.API_PAGE_SIZE_MAX + 1}).status_code, 422)

    def test_the_gate_is_watch_read(self) -> None:
        self.assertEqual(self.client.get(f"{OBLIGATIONS}/{self.research.id}/changes").status_code, 401)
        with stub_session(user_principal(permissions={perms.CASES_READ}, tenant_id=self.inside.id)):
            refused = self.client.get(
                f"{OBLIGATIONS}/{self.research.id}/changes", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}"
            )
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, perms.WATCH_READ))

    def test_the_query_count_is_pinned_and_the_read_stays_inside_the_budget(self) -> None:
        headers = sign_in(self.reader, tenant=self.inside)
        with self.assertNumQueries(RELATED_QUERIES):
            response = self.related(self.research, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.related(self.research, headers=headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)
