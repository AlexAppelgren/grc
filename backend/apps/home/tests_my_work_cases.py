"""Case work and duties on My work (HOM-05, CAS-04, REG-07, D-23, D-24), proved on Postgres
under row-level security, one class per question:

- **Cases.** An open case reaches its owner and every person or team taking part in it,
  dated by its internal deadline, its live actions and its key date while that is ahead;
  a finished case never does.
- **Actions.** A live action reaches its owner on the case's row, dated by that action
  alone; a done or removed one never does.
- **Duties.** An open duty occurrence dates the register entry it is on for everyone
  involved in the entry, and puts the entry on its own owner's list.
- **Permissions, footprint, isolation, cost.** Case rows and counts need `cases.read`
  alone; the footprint hides nothing (D-24); another bank's cases never appear; a read
  writes nothing; the query count does not grow with the number of cases.

Every date is the bank's own today plus an offset, never a literal (playbook 8.3).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import Action, ChangeCase, ImpactAssessment
from apps.collab.models import Participant
from apps.home.tests_my_work import DAY, Bank, ids, obligation, pick, row, whos
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import Obligation
from apps.register.models import Applicability, DutyOccurrence, DutyStatus, TenantObligation
from apps.shared import factories
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.permissions import CASES_READ, REGISTER_READ
from apps.taxonomy.models import CaseStatusCategory, FootprintTerm, Team
from apps.tenants.models import TeamMember
from apps.watch import testing as watch_build
from apps.watch.models import ChangeObligation
from apps.watch.write import watch_write

_changes = iter(range(1, 10_000))


def open_case(
    bank: Bank,
    *,
    owner: User | None = None,
    category: CaseStatusCategory = CaseStatusCategory.ASSESSING,
    key_date: datetime.date | None = None,
    internal_deadline: datetime.date | None = None,
    **extra: Any,
) -> ChangeCase:
    """A case of the bank's on a fresh change, in `category`, with an assessment when it
    has an internal deadline."""
    change = watch_build.change(title=f"Reform {next(_changes)}", key_date=key_date)
    case = cases_build.case(bank.tenant, change, owner=owner, **extra)
    cases_build.in_category(case, category)
    bank.activate()
    if internal_deadline is not None:
        ImpactAssessment.objects.create(tenant=bank.tenant, case=case, internal_deadline=internal_deadline)
    case.refresh_from_db()
    return case


def action(bank: Bank, case: ChangeCase, owner: User, due: datetime.date, **fields: Any) -> Action:
    bank.activate()
    return Action.objects.create(
        tenant=bank.tenant, case=case, title="Update the procedure", owner=owner, due_date=due, created_by=bank.officer, **fields
    )


def takes_part(bank: Bank, case: ChangeCase, *, user: User | None = None, team: Team | None = None, **fields: Any) -> Participant:
    bank.activate()
    return Participant.objects.create(tenant=bank.tenant, case=case, user=user, team=team, added_by=bank.officer, **fields)


def occurrence(bank: Bank, entry: TenantObligation, due: datetime.date, **fields: Any) -> DutyOccurrence:
    duty = library_build.recurring_duty(Obligation.objects.get(pk=entry.obligation_id))
    bank.activate()
    return DutyOccurrence.objects.create(
        tenant=bank.tenant, recurring_duty=duty, tenant_obligation=entry, due_date=due, **fields
    )


def legal_team(bank: Bank) -> Team:
    """The team "Legal" in the bank's Legal unit, with Johan and Karin."""
    return bank.team("legal", bank.legal, [bank.johan, bank.karin])


class Cases(TestCase):
    """An open case reaches its owner and the people and teams taking part, dated by the
    case's own dates; a finished one reaches nobody."""

    bank: Bank
    owned: ChangeCase
    in_force: ChangeCase
    closed: ChangeCase
    dismissed: ChangeCase
    teamed: ChangeCase
    joined: ChangeCase
    left: ChangeCase
    team: Team

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-cases")
        today = bank.today()
        cls.team = legal_team(bank)
        cls.owned = open_case(bank, owner=bank.anna, key_date=today + 90 * DAY, internal_deadline=today + 20 * DAY)
        # Someone else's action on Anna's case still dates her case: she answers for all of it.
        action(bank, cls.owned, bank.erik, today + 10 * DAY)
        action(bank, cls.owned, bank.erik, today - 5 * DAY, done_at=timezone.now(), done_by=bank.erik)
        action(bank, cls.owned, bank.erik, today - 4 * DAY, removed_at=timezone.now(), removed_by=bank.officer)
        cls.in_force = open_case(bank, owner=bank.anna, key_date=today - 30 * DAY)
        cls.closed = open_case(bank, owner=bank.anna, category=CaseStatusCategory.CLOSED, internal_deadline=today)
        cls.dismissed = open_case(bank, owner=bank.anna, category=CaseStatusCategory.DISMISSED)
        cls.teamed = open_case(bank, owner=bank.officer, internal_deadline=today + 3 * DAY)
        takes_part(bank, cls.teamed, team=cls.team)
        cls.joined = open_case(bank, owner=bank.officer, category=CaseStatusCategory.IMPLEMENTING)
        takes_part(bank, cls.joined, user=bank.erik)
        cls.left = open_case(bank, owner=bank.officer)
        takes_part(bank, cls.left, user=bank.erik, removed_at=timezone.now(), removed_by=bank.erik)

    def test_an_owned_open_case_is_one_row_dated_by_its_nearest_open_date(self) -> None:
        today = self.bank.today()
        page = self.bank.read(self.bank.anna)
        item = row(page, self.owned.change_id)
        self.assertEqual(item.item_kind, "change_case")
        self.assertEqual(pick(item, "bucket", "date", "kind"), ("due_soon", today + 10 * DAY, "action_due"))
        self.assertEqual(whos(item), {("owner", "Anna Berg")})
        self.assertEqual(ids(page).count(self.owned.change_id), 1)

    def test_the_internal_deadline_dates_the_case_when_it_is_nearest(self) -> None:
        teamed = row(self.bank.read(self.bank.johan), self.teamed.change_id)
        self.assertEqual(pick(teamed, "bucket", "kind"), ("due_soon", "internal_deadline"))

    def test_a_key_date_in_the_past_is_not_overdue(self) -> None:
        item = row(self.bank.read(self.bank.anna), self.in_force.change_id)
        self.assertEqual(pick(item, "bucket", "date"), ("open", None))

    def test_a_finished_case_reaches_nobody(self) -> None:
        listed = ids(self.bank.read(self.bank.anna))
        self.assertNotIn(self.closed.change_id, listed)
        self.assertNotIn(self.dismissed.change_id, listed)

    def test_every_member_of_a_team_taking_part_sees_the_case(self) -> None:
        for person in (self.bank.johan, self.bank.karin):
            item = row(self.bank.read(person), self.teamed.change_id)
            self.assertEqual(whos(item), {("participant", "legal")})
        self.assertNotIn(self.teamed.change_id, ids(self.bank.read(self.bank.erik)))

    def test_a_person_taking_part_sees_the_case_until_they_leave(self) -> None:
        page = self.bank.read(self.bank.erik)
        self.assertEqual(whos(row(page, self.joined.change_id)), {("participant", "Erik Holm")})
        self.assertNotIn(self.left.change_id, ids(page))

    def test_a_row_carries_the_case_urgency_and_no_obligation_facts(self) -> None:
        item = row(self.bank.read(self.bank.anna), self.owned.change_id)
        self.assertEqual(pick(item, "urgency", "status"), ("act_now", None))
        self.assertEqual(item.open_change_count, 0)
        self.assertIsNone(item.entity)


class Actions(TestCase):
    """A live action reaches its owner on its case's row, dated by that action alone."""

    bank: Bank
    elsewhere: ChangeCase
    later: ChangeCase
    finished: ChangeCase
    done: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-actions")
        today = bank.today()
        cls.elsewhere = open_case(bank, owner=bank.officer)
        action(bank, cls.elsewhere, bank.anna, today - DAY)
        action(bank, cls.elsewhere, bank.anna, today + 2 * DAY)
        cls.later = open_case(bank, owner=bank.officer, internal_deadline=today + DAY, key_date=today + 3 * DAY)
        action(bank, cls.later, bank.erik, today + 40 * DAY)
        action(bank, cls.later, bank.johan, today + 2 * DAY)
        cls.finished = open_case(bank, owner=bank.officer, category=CaseStatusCategory.CLOSED)
        action(bank, cls.finished, bank.anna, today - DAY)
        cls.done = open_case(bank, owner=bank.officer)
        action(bank, cls.done, bank.anna, today - DAY, done_at=timezone.now(), done_by=bank.anna)
        action(bank, cls.done, bank.anna, today - DAY, removed_at=timezone.now(), removed_by=bank.officer)

    def test_an_overdue_action_puts_its_case_under_overdue(self) -> None:
        item = row(self.bank.read(self.bank.anna), self.elsewhere.change_id)
        self.assertEqual(
            pick(item, "bucket", "date", "kind"), ("overdue", self.bank.today() - DAY, "action_due")
        )
        self.assertEqual(whos(item), {("owner", "Anna Berg")})

    def test_an_action_owner_is_dated_by_their_own_action_alone(self) -> None:
        item = row(self.bank.read(self.bank.erik), self.later.change_id)
        self.assertEqual(
            pick(item, "bucket", "date", "kind"), ("open", self.bank.today() + 40 * DAY, "action_due")
        )

    def test_done_removed_and_finished_actions_reach_nobody(self) -> None:
        listed = ids(self.bank.read(self.bank.anna))
        self.assertNotIn(self.finished.change_id, listed)
        self.assertNotIn(self.done.change_id, listed)

    def test_a_department_with_no_team_lists_no_case(self) -> None:
        page = self.bank.read(self.bank.karin, scope="unit", unit=self.bank.legal.id)
        self.assertEqual((page.items, page.total), ([], 0))

    def test_a_department_names_each_action_owner(self) -> None:
        item = row(self.bank.read(self.bank.karin, scope="unit", unit=self.bank.retail.id), self.later.change_id)
        self.assertEqual(whos(item), {("owner", "Erik Holm"), ("owner", "Johan Ek")})
        self.assertEqual(pick(item, "date", "kind"), (self.bank.today() + 2 * DAY, "action_due"))


class LinkedAndOwned(TestCase):
    """A case reached through a confirmed link and through its owner is one row with both
    reasons; the obligation's open case count is unchanged."""

    def test_one_row_with_every_reason(self) -> None:
        watch_build.seed_watch_reference()
        bank = Bank("mywork-linked-owned")
        duty = obligation("Linked and owned")
        bank.entry(duty, first_line_owner=bank.anna)
        case = open_case(bank, owner=bank.anna, internal_deadline=bank.today() - DAY)
        watch_build.obligation_link(case.change, duty)
        with watch_write("test fixture"):
            ChangeObligation.objects.filter(change=case.change).update(
                confirmed_by=bank.officer, confirmed_at=timezone.now()
            )
        page = bank.read(bank.anna)
        self.assertEqual(ids(page).count(case.change_id), 1)
        item = row(page, case.change_id)
        self.assertEqual(pick(item, "bucket", "kind"), ("overdue", "internal_deadline"))
        self.assertEqual(
            {(reason.reason, reason.via.obligation_id if reason.via else None) for reason in item.reasons},
            {("owner", None), ("owner", duty.id)},
        )
        self.assertEqual(row(page, duty.id).open_change_count, 1)


class Duties(TestCase):
    """An open duty occurrence dates its entry for everyone involved in it, and puts the
    entry on its own owner's list with the entity it is for."""

    bank: Bank
    owned: Obligation
    delegated: Obligation
    finished: Obligation
    not_applying: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-duties")
        today = bank.today()
        cls.owned = obligation("Quarterly report")
        entry = bank.entry(cls.owned, first_line_owner=bank.anna, next_review_date=today + 200 * DAY)
        occurrence(bank, entry, today + 5 * DAY)
        cls.delegated = obligation("Delegated report")
        entry = bank.entry(cls.delegated, first_line_owner=bank.officer)
        occurrence(bank, entry, today - 2 * DAY, owner=bank.erik, org_unit=bank.fund_ab, status=DutyStatus.MISSED.value)
        cls.finished = obligation("Reported already")
        entry = bank.entry(cls.finished, first_line_owner=bank.anna)
        occurrence(bank, entry, today - 2 * DAY, status=DutyStatus.DONE.value)
        cls.not_applying = obligation("Not ours")
        entry = bank.entry(cls.not_applying, owner_team=bank.retail_team, applicability=Applicability.DOES_NOT_APPLY.value)
        occurrence(bank, entry, today, owner_team=bank.retail_team)

    def test_an_open_occurrence_dates_its_entry(self) -> None:
        item = row(self.bank.read(self.bank.anna), self.owned.id)
        self.assertEqual(pick(item, "bucket", "date", "kind"), ("due_soon", self.bank.today() + 5 * DAY, "duty_due"))

    def test_an_occurrence_owner_gets_the_entry_dated_by_it(self) -> None:
        item = row(self.bank.read(self.bank.erik), self.delegated.id)
        self.assertEqual(pick(item, "bucket", "kind", "entity"), ("overdue", "duty_due", "Fund AB"))
        self.assertEqual(whos(item), {("owner", "Erik Holm")})

    def test_a_done_occurrence_and_an_entry_that_does_not_apply_date_nothing(self) -> None:
        page = self.bank.read(self.bank.anna)
        self.assertEqual(pick(row(page, self.finished.id), "bucket", "date"), ("open", None))
        self.assertNotIn(self.not_applying.id, ids(page))


class PermissionsAndFootprint(TestCase):
    """Case rows and counts need `cases.read` alone; without it they are named, never
    counted; the footprint hides no case."""

    bank: Bank
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-case-permissions")
        cls.case = open_case(bank, owner=bank.anna, footprint_match=False, internal_deadline=bank.today() - DAY)
        action(bank, open_case(bank, owner=bank.officer), bank.anna, bank.today())
        bank.activate()
        FootprintTerm.objects.create(tenant=bank.tenant, term=library_build.term("regime:aml"))

    def test_without_cases_read_no_case_row_and_no_case_count(self) -> None:
        page = self.bank.read(self.bank.anna, permissions=frozenset({REGISTER_READ}))
        self.assertEqual((page.items, page.total), ([], 0))
        self.assertEqual(page.counts.model_dump(), {"overdue": 0, "due_soon": 0, "aware": 0, "open": 0})
        self.assertEqual(page.permission_limited, ["change_case"])

    def test_cases_read_alone_lists_the_case_work(self) -> None:
        page = self.bank.read(self.bank.anna, permissions=frozenset({CASES_READ}))
        self.assertEqual(page.permission_limited, ["tenant_obligation", "internal_item"])
        self.assertEqual((page.counts.overdue, page.counts.due_soon, page.total), (1, 1, 2))

    def test_a_case_outside_the_footprint_is_listed(self) -> None:
        self.assertIn(self.case.change_id, ids(self.bank.read(self.bank.anna)))


class IsolationAndReads(TestCase):
    """Another bank's cases, actions, participations and duties never reach a row or a
    count, and a read writes nothing."""

    def test_another_banks_case_work_never_appears_and_a_read_writes_nothing(self) -> None:
        watch_build.seed_watch_reference()
        mine = Bank("mywork-cases-mine")
        theirs = Bank("mywork-cases-theirs")
        # Anna is a member of the second bank too, and owns work there.
        factories.member(theirs.tenant, user_row=mine.anna)
        case = open_case(theirs, owner=mine.anna, internal_deadline=theirs.today())
        action(theirs, open_case(theirs, owner=theirs.officer), mine.anna, theirs.today())
        team = theirs.team("theirs_legal", theirs.legal, [mine.anna])
        takes_part(theirs, open_case(theirs, owner=theirs.officer), team=team)
        duty = obligation("Their duty")
        occurrence(theirs, theirs.entry(duty, first_line_owner=theirs.officer), theirs.today(), owner=mine.anna)

        mine.activate()
        audit, outbox = AuditEvent.objects.count(), OutboxEvent.objects.count()
        with CaptureQueriesContext(connection) as captured:
            page = mine.read(mine.anna)
        self.assertEqual((page.items, page.total), ([], 0))
        self.assertEqual(page.counts.model_dump(), {"overdue": 0, "due_soon": 0, "aware": 0, "open": 0})
        self.assertEqual((AuditEvent.objects.count(), OutboxEvent.objects.count()), (audit, outbox))
        writes = [q["sql"] for q in captured.captured_queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(writes, [])
        self.assertIn(case.change_id, ids(theirs.read(mine.anna)))


def seed_case_work(bank: Bank, team: Team, n: int) -> None:
    """`n` of each case source for Anna and her teams: an owned case with an assessment, an
    action, a person's and a team's participation, and a duty occurrence on an entry."""
    today = bank.today()
    for _ in range(n):
        open_case(bank, owner=bank.anna, internal_deadline=today + DAY)
        action(bank, open_case(bank, owner=bank.officer), bank.anna, today - DAY)
        takes_part(bank, open_case(bank, owner=bank.officer), user=bank.anna)
        takes_part(bank, open_case(bank, owner=bank.officer), team=team)
        entry = bank.entry(obligation(f"Duty {next(_changes)}"), first_line_owner=bank.anna)
        occurrence(bank, entry, today + DAY)


def queries(bank: Bank, user: User, **query: Any) -> int:
    with CaptureQueriesContext(connection) as captured:
        bank.read(user, limit=100, **query)
    return len(captured.captured_queries)


class Cost(TestCase):
    """The case and duty sources add a fixed number of queries, never one per row."""

    def test_the_count_does_not_grow_with_the_case_work(self) -> None:
        watch_build.seed_watch_reference()
        bank = Bank("mywork-cases-cost")
        team = bank.team("anna_legal", bank.retail, [bank.anna])
        seed_case_work(bank, team, 1)
        one, one_unit = queries(bank, bank.anna), queries(bank, bank.karin, scope="unit", unit=bank.retail.id)
        seed_case_work(bank, team, 6)
        self.assertEqual(queries(bank, bank.anna), one)
        self.assertEqual(queries(bank, bank.karin, scope="unit", unit=bank.retail.id), one_unit)
        self.assertEqual(bank.read(bank.anna, limit=100).total, 7 * 5)


def run_hom_s14(test: TestCase) -> None:
    """HOM-S14: Anna's overdue action and her case with no open dates, Erik's item dated
    by his own action, each member of Legal seeing the case their team takes part in, and
    the query count of HOM-S12's department view unmoved by the case sources."""
    watch_build.seed_watch_reference()
    bank = Bank("hom-s14")
    today = bank.today()
    legal = legal_team(bank)

    with_action = open_case(bank, owner=bank.officer)
    action(bank, with_action, bank.anna, today - DAY)
    in_force = open_case(bank, owner=bank.anna, key_date=today - 30 * DAY)
    erik_case = open_case(bank, owner=bank.officer, internal_deadline=today + DAY)
    action(bank, erik_case, bank.erik, today + 40 * DAY)
    teamed = open_case(bank, owner=bank.officer)
    takes_part(bank, teamed, team=legal)

    anna = bank.read(bank.anna)
    test.assertEqual(pick(row(anna, with_action.change_id), "bucket", "kind"), ("overdue", "action_due"))
    test.assertEqual(pick(row(anna, in_force.change_id), "bucket", "date"), ("open", None))

    erik = row(bank.read(bank.erik), erik_case.change_id)
    test.assertEqual(pick(erik, "date", "kind"), (today + 40 * DAY, "action_due"))

    for member in TeamMember.objects.filter(team=legal).select_related("user"):
        item = row(bank.read(member.user), teamed.change_id)
        test.assertEqual(whos(item), {("participant", "legal")})

    view = {"scope": "unit", "unit": bank.retail.id}
    seed_case_work(bank, bank.retail_team, 1)
    before = queries(bank, bank.karin, **view)
    seed_case_work(bank, bank.retail_team, 4)
    test.assertEqual(queries(bank, bank.karin, **view), before)
