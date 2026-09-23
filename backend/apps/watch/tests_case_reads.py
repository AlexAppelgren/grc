"""The person behind this bank's decisions on the watch reads, and the links it removed
(WAT-04, WAT-05, WAT-S6, WAT-S7).

A confirmed 'So what?' and a decided link are one person's decision per bank, so the
change page and the feed name that person: `case.soWhatConfirmedByName` and each
decision's `decidedByName`, read in the same queries as the case rather than one per row,
and null while nobody has decided. A link this bank removed is "not related to us", so the
obligation's related-changes panel leaves that change out of its items, its total and its
open count — for this bank only; another bank and the shared library are untouched.
"""

from __future__ import annotations

from typing import Any

from apps.cases import testing as cases_build
from apps.cases.models import CaseLinkDecision
from apps.shared.testing import sign_in
from apps.watch import testing as build
from apps.watch.tests_change_reads import CHANGE_QUERIES, RELATED_QUERIES, ChangeReadFixture
from apps.watch.tests_reading import confirm_so_what


class CaseReadFixture(ChangeReadFixture):
    """The change reads' fixture, with `reporting` also linked to the second change: this
    bank removed `reporting` from the lead change's case (the parent fixture) and has
    decided nothing about it on the second one."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        build.obligation_link(cls.later_change, cls.reporting, confidence=0.5)

    def case_of_lead(self) -> Any:
        return self.read(self.lead).json()["case"]


class TheReadNamesThePersonTests(CaseReadFixture):
    """`soWhatConfirmedByName` and `decidedByName` on the change page and the feed."""

    def test_an_unconfirmed_so_what_names_nobody(self) -> None:
        case = self.case_of_lead()
        self.assertFalse(case["soWhatConfirmed"])
        self.assertIsNone(case["soWhatConfirmedByName"])

    def test_a_confirmed_so_what_names_the_person_who_confirmed_it(self) -> None:
        confirm_so_what(self.case, self.reader)
        case = self.case_of_lead()
        self.assertTrue(self.reader.name)
        self.assertEqual(case["soWhatConfirmedByName"], self.reader.name)
        row = next(item for item in self.feed().json()["items"] if item["id"] == str(self.lead.id))
        self.assertEqual(row["case"]["soWhatConfirmedByName"], self.reader.name, "the feed row names the same person")

    def test_a_decision_names_the_person_who_decided_and_a_system_decision_names_nobody(self) -> None:
        cases_build.link_decision(self.case, self.research, decision=CaseLinkDecision.ACCEPTED, decided_by=self.reader)
        decisions = {item["obligationId"]: item for item in self.case_of_lead()["obligationDecisions"]}
        self.assertEqual(decisions[str(self.research.id)]["decidedByName"], self.reader.name)
        self.assertEqual(decisions[str(self.research.id)]["decision"], "accepted")
        # The parent fixture's removal names no person: a decision the system made.
        self.assertIsNone(decisions[str(self.reporting.id)]["decidedByName"])

    def test_another_banks_case_never_carries_this_banks_names(self) -> None:
        confirm_so_what(self.case, self.reader)
        theirs = self.read(self.lead, sign_in(self.other_reader, tenant=self.outside)).json()["case"]
        self.assertIsNone(theirs["soWhatConfirmedByName"])
        self.assertEqual(theirs["obligationDecisions"], [])

    def test_the_names_cost_no_query_per_row(self) -> None:
        confirm_so_what(self.case, self.reader)
        cases_build.link_decision(self.case, self.research, decided_by=self.reader)
        headers = sign_in(self.reader, tenant=self.inside)
        with self.assertNumQueries(CHANGE_QUERIES):
            case = self.read(self.lead, headers).json()["case"]
        self.assertEqual(case["soWhatConfirmedByName"], self.reader.name)


class ARemovedLinkLeavesThePanelTests(CaseReadFixture):
    """`GET /obligations/{obligationId}/changes` without the changes this bank removed."""

    def test_a_change_this_bank_removed_is_gone_from_items_total_and_open_count(self) -> None:
        body = self.related(self.reporting).json()
        self.assertEqual([row["stableKey"] for row in body["items"]], ["chg-second"])
        self.assertEqual((body["total"], body["openCount"]), (1, 1))

    def test_an_accepted_link_stays(self) -> None:
        cases_build.link_decision(self.case, self.research, decided_by=self.reader)
        body = self.related(self.research).json()
        self.assertEqual({row["stableKey"] for row in body["items"]}, {"chg-lead", "chg-second"})

    def test_the_removal_is_this_banks_alone(self) -> None:
        theirs = self.related(self.reporting, headers=sign_in(self.other_reader, tenant=self.outside)).json()
        self.assertEqual({row["stableKey"] for row in theirs["items"]}, {"chg-lead", "chg-second"})
        self.assertEqual((theirs["total"], theirs["openCount"]), (2, 1), "their own lead case is still open work")

    def test_a_removal_on_one_obligation_leaves_the_change_on_another(self) -> None:
        body = self.related(self.research).json()
        self.assertIn("chg-lead", [row["stableKey"] for row in body["items"]])
        self.assertEqual((body["total"], body["openCount"]), (2, 2))

    def test_the_query_count_is_unchanged_by_the_removal_filter(self) -> None:
        headers = sign_in(self.reader, tenant=self.inside)
        with self.assertNumQueries(RELATED_QUERIES):
            response = self.related(self.reporting, headers=headers)
        self.assertEqual(response.json()["total"], 1)
