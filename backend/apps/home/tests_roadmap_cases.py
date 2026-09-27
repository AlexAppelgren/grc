"""The roadmap's last internal branches (HOM-03, CAS-03, CAS-04, REG-07) and H22.

What is proved here, one class per question:

- **A case's own dates.** An open case's internal deadline and the due date of each of its
  actions that is neither done nor removed are "Our deadline" with their owner and the
  change whose case set them. A case that is closed, dismissed or outside the regulatory
  scope takes both with it, and a reader without `cases.read` sees neither.
- **A duty's occurrence.** The open occurrence of a recurring duty is "Our deadline" with
  its owner and its obligation, dropped when it is completed, left out where the answer is
  "does not apply" or the obligation is outside the scope, and only for `register.read`.
- **A period stays while it runs (H22).** A key date stated as a month, a quarter or a year
  is stored on some day of it; the roadmap and Today keep it until the period has ended.
- **Whose rows they are, and what they cost.** Another bank's case and duty never reach this
  bank's roadmap, and the read runs the same queries for one deadline and for thirty.

None of these reaches a calendar subscription; `tests_feed.py` proves that per branch on the
document itself. Dates are the bank's own today plus an offset, or a fixed instant where the
question is the calendar itself (playbook 8.3).
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import Action, ChangeCase, ImpactAssessment
from apps.cases.schemas import ACTION_TITLE_MAX
from apps.home import roadmap
from apps.home.schemas import HomeRoadmapItem, HomeRoadmapQuery
from apps.home.tests_my_work import Bank, obligation
from apps.home.tests_roadmap import a_change
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import DatePrecision
from apps.register.models import Applicability, DutyOccurrence, DutyStatus, TenantObligation
from apps.shared import tenancy
from apps.shared import permissions as perms
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, sign_in, stub_session, user_principal
from apps.taxonomy.models import CaseStatusCategory, FootprintTerm
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange
from apps.watch.write import watch_write

URL = "/api/v1/roadmap"
D = datetime.date

# Twelve queries for a reader holding both `register.read` and `cases.read`, measured
# 2026-09-25 on the cost fixture below and pinned so an N+1 shows up as a number: one per
# branch (the two certificate branches, the entries', entity rows', gaps' and duties' dates,
# the case deadlines and the actions: 8), the reviewed obligations' titles (2), the owning
# teams' labels (1) and the regulatory branch's page of cases (1), whose confirmed links and
# urgencies are not read on a page with no case on it.
CASES_QUERIES = 12


def a_case(bank: Bank, title: str, *, owner: User, footprint_match: bool = True, category: CaseStatusCategory = CaseStatusCategory.IMPLEMENTING) -> ChangeCase:
    """An undated change and this bank's case on it, owned and in `category`: the case's own
    dates are what the test reads, so its change carries none of its own."""
    case = cases_build.case(bank.tenant, a_change(key_date=None, title=title), owner=owner, footprint_match=footprint_match)
    cases_build.in_category(case, category)
    return case


def a_deadline(case: ChangeCase, day: datetime.date) -> ImpactAssessment:
    """The case's saved impact assessment with its internal deadline (CAS-03)."""
    tenancy.activate(case.tenant_id)
    return ImpactAssessment.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        why="Our research budget moves.",
        internal_deadline=day,
        saved=True,
        saved_by_id=case.owner_id,
        saved_at=timezone.now(),
    )


def an_action(case: ChangeCase, title: str, day: datetime.date, *, owner: User, done: bool = False, removed: bool = False) -> Action:
    """An action on the case (CAS-04), open unless it is done or removed."""
    tenancy.activate(case.tenant_id)
    now = timezone.now()
    return Action.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        title=title,
        owner=owner,
        due_date=day,
        created_by=owner,
        done_at=now if done else None,
        done_by=owner if done else None,
        removed_at=now if removed else None,
        removed_by=owner if removed else None,
    )


def an_occurrence(bank: Bank, entry: TenantObligation, day: datetime.date, **fields: Any) -> DutyOccurrence:
    """An occurrence of a fresh quarterly duty on `entry`'s obligation (REG-07)."""
    duty = library_build.recurring_duty(entry.obligation, title=f"Quarterly report {day.isoformat()}")
    bank.activate()
    return DutyOccurrence.objects.create(tenant=bank.tenant, recurring_duty=duty, tenant_obligation=entry, due_date=day, **fields)


def read(bank: Bank, *, register_reader: bool = True, cases_reader: bool = True, **filters: Any) -> list[HomeRoadmapItem]:
    bank.activate()
    return roadmap.roadmap_items(
        bank.tenant, ["en"], HomeRoadmapQuery(**filters), register_reader=register_reader, cases_reader=cases_reader
    ).items


def by_id(bank: Bank, **flags: bool) -> dict[str, HomeRoadmapItem]:
    return {item.id: item for item in read(bank, kind="internal", **flags)}


class CaseDeadlinesOnTheRoadmap(TestCase):
    """CAS-03, CAS-04, HOM-03: an open case's internal deadline and its live actions."""

    bank: Bank
    case: ChangeCase
    deadline: ImpactAssessment
    action: Action
    expected: set[str]

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("roadmap-cases")
        today = bank.today()

        def day(offset: int) -> datetime.date:
            return today + datetime.timedelta(days=offset)

        cls.case = a_case(bank, "Research payments", owner=bank.anna)
        cls.deadline = a_deadline(cls.case, day(20))
        cls.action = an_action(cls.case, "Update the research policy", day(10), owner=bank.erik)
        # Absent each for its own reason: done, removed, and a due date that has gone.
        an_action(cls.case, "Tell the desks", day(12), owner=bank.erik, done=True)
        an_action(cls.case, "Buy a new system", day(14), owner=bank.erik, removed=True)
        an_action(cls.case, "Draft the memo", day(-2), owner=bank.erik)
        # A finished case and one outside the regulatory scope take their dates with them.
        for title, extra in (
            ("Settled", {"category": CaseStatusCategory.CLOSED}),
            ("Not for us", {"category": CaseStatusCategory.DISMISSED}),
            ("Insurance", {"footprint_match": False}),
        ):
            other = a_case(bank, title, owner=bank.anna, **extra)
            a_deadline(other, day(25))
            an_action(other, f"{title} action", day(26), owner=bank.erik)
        cls.expected = {f"internal_deadline:{cls.deadline.id}", f"action_due:{cls.action.id}"}

    def test_each_is_our_deadline_with_its_owner_and_its_case(self) -> None:
        items = by_id(self.bank)
        self.assertEqual(set(items), self.expected)
        deadline = items[f"internal_deadline:{self.deadline.id}"]
        action = items[f"action_due:{self.action.id}"]
        for item, item_type, title, owner in (
            (deadline, "internal_deadline", "Research payments", self.bank.anna),
            (action, "action_due", "Update the research policy", self.bank.erik),
        ):
            with self.subTest(item_type=item_type):
                assert item.owner is not None and item.owner.person is not None
                self.assertEqual((item.kind, item.item_type, item.title), ("internal", item_type, title))
                self.assertEqual((item.owner.person.id, item.owner.person.name, item.owner.team), (owner.id, owner.name, None))
                # The card links to the bank's page for its case; no library judgement rides along.
                self.assertEqual((item.change_id, item.subject), (self.case.change_id, None))
                self.assertEqual((item.status, item.urgency, item.label, item.source_label, item.obligations), (None, None, None, None, []))
                self.assertEqual(item.date_precision, "day")

    def test_an_action_titled_as_long_as_the_case_workflow_allows_is_listed_whole(self) -> None:
        """An action's title may be 500 characters (`ACTION_TITLE_MAX`); the roadmap item
        carries it whole rather than failing the read."""
        long_title = "Renegotiate " + "x" * (ACTION_TITLE_MAX - len("Renegotiate "))
        self.bank.activate()
        Action.objects.filter(pk=self.action.pk).update(title=long_title)
        self.assertEqual(by_id(self.bank)[f"action_due:{self.action.id}"].title, long_title)

    def test_a_done_or_removed_action_and_a_closed_case_leave_the_roadmap(self) -> None:
        self.bank.activate()
        Action.objects.filter(pk=self.action.pk).update(done_at=timezone.now(), done_by=self.bank.erik)
        self.assertEqual(set(by_id(self.bank)), {f"internal_deadline:{self.deadline.id}"})
        cases_build.in_category(self.case, CaseStatusCategory.CLOSED)
        self.assertEqual(by_id(self.bank), {})

    def test_a_case_that_leaves_the_regulatory_scope_takes_its_dates_with_it(self) -> None:
        self.bank.activate()
        ChangeCase.objects.filter(pk=self.case.pk).update(footprint_match=False)
        self.assertEqual(by_id(self.bank), {})

    def test_the_case_workflows_dates_need_cases_read(self) -> None:
        self.assertEqual(by_id(self.bank, cases_reader=False), {})
        self.assertEqual(set(by_id(self.bank, register_reader=False)), self.expected)

    def test_the_route_passes_the_readers_cases_read(self) -> None:
        """A reader, who holds `cases.read`, sees both; a caller holding `roadmap.read` and
        `register.read` alone sees neither."""
        full = self.client.get(f"{URL}?kind=internal", **sign_in(self.bank.anna, tenant=self.bank.tenant))
        self.assertEqual({item["id"] for item in full.json()["items"]}, self.expected)
        self.assertEqual(
            {item["itemType"]: item["changeId"] for item in full.json()["items"]},
            {"internal_deadline": str(self.case.change_id), "action_due": str(self.case.change_id)},
        )
        partial = user_principal(
            permissions={perms.ROADMAP_READ, perms.REGISTER_READ}, tenant_id=self.bank.tenant.id, subject_id=self.bank.anna.id
        )
        with stub_session(partial):
            limited = self.client.get(f"{URL}?kind=internal", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
        self.assertEqual((limited.status_code, limited.json()["items"]), (200, []))

    def test_coming_up_holds_them_too(self) -> None:
        self.bank.activate()
        items, count = roadmap.coming_up(self.bank.tenant, ["en"], 1, register_reader=True, cases_reader=True)
        self.assertEqual(([item.id for item in items], count), ([f"action_due:{self.action.id}"], 2))

    def test_another_banks_case_never_reaches_this_banks_roadmap(self) -> None:
        other = Bank("roadmap-cases-other")
        theirs = a_case(other, "Research payments", owner=other.anna)
        a_deadline(theirs, other.today() + datetime.timedelta(days=5))
        an_action(theirs, "Their action", other.today() + datetime.timedelta(days=5), owner=other.erik)
        self.assertEqual(set(by_id(self.bank)), self.expected)
        self.assertEqual(len(by_id(other)), 2)


class DutyOccurrencesOnTheRoadmap(TestCase):
    """REG-07, HOM-03: a recurring duty's open occurrence is our deadline until completed."""

    bank: Bank
    entry: TenantObligation
    whole: DutyOccurrence
    fund: DutyOccurrence

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("roadmap-duties")
        today = bank.today()

        def day(offset: int) -> datetime.date:
            return today + datetime.timedelta(days=offset)

        cls.entry = bank.entry(obligation("Client asset reporting"), first_line_owner=bank.anna)
        cls.whole = an_occurrence(bank, cls.entry, day(30), owner=bank.anna)
        cls.fund = an_occurrence(bank, cls.entry, day(40), org_unit=bank.fund_ab, owner_team=bank.cards)
        # Absent each for its own reason: done, on an entity that does not apply, gone by,
        # on an entry that does not apply, and outside the regulatory scope (FP-03).
        an_occurrence(bank, cls.entry, day(35), status=DutyStatus.DONE.value)
        bank.scope(cls.entry, bank.bank_ab, applicability=Applicability.DOES_NOT_APPLY.value)
        an_occurrence(bank, cls.entry, day(36), org_unit=bank.bank_ab)
        an_occurrence(bank, cls.entry, day(-1))
        an_occurrence(bank, bank.entry(obligation("Not ours"), applicability=Applicability.DOES_NOT_APPLY.value), day(37))
        an_occurrence(bank, bank.entry(obligation("Advice", terms=["service_type:advice"])), day(38))
        bank.activate()
        FootprintTerm.objects.create(tenant=bank.tenant, term=library_build.term("service_type:custody"))

    def test_each_open_occurrence_is_our_deadline_with_its_owner_and_its_obligation(self) -> None:
        items = by_id(self.bank)
        self.assertEqual(set(items), {f"duty_due:{self.whole.id}", f"duty_due:{self.fund.id}"})
        whole, fund = items[f"duty_due:{self.whole.id}"], items[f"duty_due:{self.fund.id}"]
        assert whole.owner is not None and whole.owner.person is not None and whole.subject is not None
        self.assertEqual((whole.kind, whole.item_type, whole.date), ("internal", "duty_due", self.whole.due_date))
        self.assertEqual((whole.title, whole.owner.person.id, whole.change_id), (f"Quarterly report {self.whole.due_date.isoformat()}", self.bank.anna.id, None))
        self.assertEqual((whole.subject.obligation_id, whole.subject.entity), (self.entry.obligation_id, None))
        assert fund.owner is not None and fund.owner.team is not None and fund.subject is not None and fund.subject.entity is not None
        self.assertEqual((fund.owner.person, fund.owner.team.key, fund.subject.entity.name), (None, "cards", "Fund AB"))

    def test_a_completed_occurrence_is_dropped(self) -> None:
        self.bank.activate()
        DutyOccurrence.objects.filter(pk=self.whole.pk).update(status=DutyStatus.DONE.value, completed_at=timezone.now(), completed_by=self.bank.anna)
        self.assertEqual(set(by_id(self.bank)), {f"duty_due:{self.fund.id}"})

    def test_duties_need_register_read(self) -> None:
        self.assertEqual(by_id(self.bank, register_reader=False), {})


class APeriodStaysWhileItRuns(TestCase):
    """H22: a key date stated as a month, a quarter or a year is stored on a day of it, and
    the roadmap and Today keep it until that period has ended, not until the stored day."""

    bank: Bank

    # Mid-November in Stockholm: October is over, the fourth quarter and the year are not.
    INSTANT = datetime.datetime(2026, 11, 15, 9, 0, tzinfo=datetime.UTC)

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("roadmap-periods")
        dated = (
            ("Q4 reform", D(2026, 10, 1), DatePrecision.QUARTER),
            ("November reform", D(2026, 11, 1), DatePrecision.MONTH),
            ("October reform", D(2026, 10, 1), DatePrecision.MONTH),
            ("This year's reform", D(2026, 1, 1), DatePrecision.YEAR),
            ("Yesterday's reform", D(2026, 11, 14), DatePrecision.DAY),
            ("Q1 reform", D(2027, 1, 1), DatePrecision.QUARTER),
        )
        for title, key_date, precision in dated:
            change = a_change(key_date=key_date, title=title)
            with watch_write("test: a key date stated less exactly than to the day"):
                RegulatoryChange.objects.filter(pk=change.pk).update(key_date_precision=precision.value)
            cases_build.case(bank.tenant, change)

    def titles(self, at: datetime.datetime = INSTANT, **filters: Any) -> list[str]:
        with mock.patch("django.utils.timezone.now", return_value=at):
            return [item.title for item in read(self.bank, kind="regulatory", **filters)]

    def test_a_period_that_has_not_ended_stays_and_one_that_has_leaves(self) -> None:
        self.assertEqual(self.titles(), ["This year's reform", "Q4 reform", "November reform", "Q1 reform"])

    def test_a_quarter_leaves_the_day_after_it_ends(self) -> None:
        last_day = datetime.datetime(2026, 12, 31, 12, 0, tzinfo=datetime.UTC)
        self.assertIn("Q4 reform", self.titles(last_day))
        self.assertNotIn("Q4 reform", self.titles(last_day + datetime.timedelta(days=1)))

    def test_a_window_that_starts_inside_a_period_holds_it(self) -> None:
        self.assertEqual(self.titles(date_from=D(2027, 2, 10)), ["Q1 reform"])
        self.assertEqual(self.titles(date_from=D(2027, 2, 10), date_to=D(2026, 12, 31)), [])

    def test_today_keeps_it_too(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=self.INSTANT):
            self.bank.activate()
            items, count = roadmap.coming_up(self.bank.tenant, ["en"], 1)
        self.assertEqual(([item.title for item in items], count), (["This year's reform"], 4))


class CaseAndDutyDeadlinesCost(TestCase):
    """NFR-02: the case and duty branches cost one query each, whatever the number of rows."""

    bank: Bank

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("roadmap-cases-cost")
        today = bank.today()
        for number in range(10):
            day = today + datetime.timedelta(days=10 + number)
            case = a_case(bank, f"Reform {number}", owner=bank.anna)
            a_deadline(case, day)
            an_action(case, f"Action {number}", day, owner=bank.erik)
            entry: TenantObligation = bank.entry(obligation(f"Duty {number}"), next_review_date=day)
            an_occurrence(bank, entry, day, owner_team=bank.cards)

    def test_the_query_count_does_not_grow_with_the_number_of_deadlines(self) -> None:
        today = self.bank.today()
        for last, expected in ((10, 4), (19, 40)):
            self.bank.activate()
            with self.subTest(items=expected), self.assertNumQueries(CASES_QUERIES):
                items = roadmap.roadmap_items(
                    self.bank.tenant, ["en"], HomeRoadmapQuery(to=today + datetime.timedelta(days=last)), register_reader=True, cases_reader=True
                ).items
            self.assertEqual(len(items), expected)
