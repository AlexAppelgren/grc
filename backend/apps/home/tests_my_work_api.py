"""`GET /me/work` (HOM-05, COL-01, COL-04, D-23, D-24, D-25, D-97): My work through its
route, and the two sources that arrive with it, one class per question:

- **The route.** What a member gets and in which shape; the query's refusals; who is
  turned away; the read writes nothing.
- **Participations.** A person or a team taking part in a register entry reaches My work
  with the reason `participant`, dated like the entry's own people; an ended participation
  and an entry that does not apply never do.
- **Comments.** Someone else's comment on a record on the list, mentions included, marks
  it under "Changes on your items" for `MY_WORK_AWARE_DAYS`; the caller's own, a deleted
  one, an older one and one the reader may not read never do.
- **Cost.** The query count stays flat with participants and comments on every row.

The scenarios HOM-S7 to HOM-S12 and COL-S12 are the `run_*` functions at the end, called
from `tests_scenarios.py` in both apps. Every date is the bank's own today plus an offset,
never a literal (playbook 8.3).
"""

from __future__ import annotations

import datetime
import logging
import sys
import time
import uuid
from typing import Any
from unittest import mock

from django.conf import settings
from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.agents.models import AgentKind
from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.collab.logic import notify
from apps.collab.models import Comment, CommentMention, Notification, NotificationKind, Participant
from apps.home.tests_my_work import DAY, Bank, obligation
from apps.identity.models import Membership, MembershipRole, TenantRole, User, UserStatus
from apps.identity.roles_logic import roles_by_keys
from apps.library.models import Obligation, ObligationVersion
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import sign_in
from apps.taxonomy.models import FootprintTerm, Team
from apps.tenants.models import TeamMember
from apps.library import testing as library_build
from apps.watch import testing as watch_build
from apps.watch.models import ChangeObligation, RegulatoryChange
from apps.watch.write import watch_write

URL = "/api/v1/me/work"
SECRET = "the custody angle nobody outside the bank may read"


# ---------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------
def read(test: TestCase, bank: Bank, user: User, query: str = "", *, status: int = 200) -> dict[str, Any]:
    """My work as `user` reads it through the route, signed in to `bank`."""
    response = test.client.get(f"{URL}?{query}", **sign_in(user, tenant=bank.tenant))
    test.assertEqual(response.status_code, status, response.content)
    body: dict[str, Any] = response.json()
    return body


def subject_of(item: dict[str, Any]) -> str:
    subject = item["subject"]
    return str(subject["obligationId"] or subject["changeId"] or subject["internalItemId"])


def ids(page: dict[str, Any]) -> set[str]:
    return {subject_of(item) for item in page["items"]}


def item_for(page: dict[str, Any], subject: uuid.UUID) -> dict[str, Any]:
    return next(item for item in page["items"] if subject_of(item) == str(subject))


def date_of(item: dict[str, Any]) -> tuple[str, str | None, str | None]:
    date = item["date"] or {}
    return item["bucket"], date.get("kind"), date.get("value")


def whos(item: dict[str, Any]) -> set[tuple[str, str]]:
    """Each reason as (reason, the person's name or the team's key)."""
    return {
        (reason["reason"], (reason["who"]["person"] or {}).get("name") or reason["who"]["team"]["key"])
        for reason in item["reasons"]
    }


def take_part(bank: Bank, entry_of: Obligation, *, user: User | None = None, team: Team | None = None) -> Participant:
    """A participation as `POST /obligations/{id}/participants` leaves it, written directly:
    these tests read it. The entry is the bank's own and must exist."""
    bank.activate()
    entry = TenantObligation.objects.get(obligation=entry_of)
    return Participant.objects.create(
        tenant=bank.tenant, tenant_obligation=entry, user=user, team=team, added_by=bank.officer
    )


def comment(
    bank: Bank,
    author: User,
    subject_type: str,
    subject_id: uuid.UUID,
    *,
    ago: datetime.timedelta = datetime.timedelta(minutes=5),
    mentions: tuple[User, ...] = (),
    deleted: bool = False,
) -> Comment:
    """A comment as `POST /comments` leaves it, written directly: these tests only read."""
    bank.activate()
    row = Comment.objects.create(
        tenant=bank.tenant, subject_type=subject_type, subject_id=subject_id, author=author, body=SECRET
    )
    Comment.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - ago, deleted_at=timezone.now() if deleted else None
    )
    for person in mentions:
        CommentMention.objects.create(tenant=bank.tenant, comment=row, user=person)
    return row


def give_role(bank: Bank, user: User, *, key: str | None = None, permissions: set[str] | None = None) -> TenantRole:
    """Replace `user`'s roles in `bank` with the system role `key`, or with a custom role
    holding exactly `permissions`."""
    bank.activate()
    membership = Membership.objects.get(user=user)
    MembershipRole.objects.filter(membership=membership).delete()
    if key is not None:
        role = roles_by_keys(bank.tenant.id, [key])[0]
    else:
        role = TenantRole.objects.create(
            tenant=bank.tenant, key=f"custom-{uuid.uuid4().hex[:8]}", permissions=sorted(permissions or ())
        )
    MembershipRole.objects.create(tenant=bank.tenant, membership=membership, role=role)
    return role


def confirm(change: RegulatoryChange, **confirmer: Any) -> None:
    with watch_write("test fixture"):
        ChangeObligation.objects.filter(change=change).update(confirmed_at=timezone.now(), **confirmer)


# ---------------------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------------------
class Route(TestCase):
    """What a member gets from `GET /me/work`, and who is turned away."""

    bank: Bank
    other: Bank
    overdue: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-route")
        cls.other = Bank("mywork-route-other")
        cls.overdue = obligation("Keep records of advice")
        bank.entry(cls.overdue, first_line_owner=bank.anna, next_review_date=bank.today() - 12 * DAY)

    def test_a_member_reads_their_own_work_in_the_declared_shape(self) -> None:
        page = read(self, self.bank, self.bank.anna)
        self.assertEqual(
            set(page), {"scope", "unit", "counts", "permissionLimited", "items", "total"}
        )
        self.assertEqual(
            (page["scope"], page["unit"], page["counts"], page["permissionLimited"], page["total"]),
            ("mine", None, {"overdue": 1, "dueSoon": 0, "aware": 0, "open": 0}, [], 1),
        )
        item = page["items"][0]
        self.assertEqual(
            item,
            {
                "bucket": "overdue",
                "itemKind": "tenant_obligation",
                "subject": {
                    "obligationId": str(self.overdue.id),
                    "changeId": None,
                    "internalItemId": None,
                    "title": "Keep records of advice",
                },
                "entity": None,
                "date": {
                    "value": (self.bank.today() - 12 * DAY).isoformat(),
                    "kind": "review",
                    "precision": "day",
                },
                "reasons": [
                    {
                        "reason": "owner",
                        "who": {"person": {"id": str(self.bank.anna.id), "name": "Anna Berg"}, "team": None},
                        "via": None,
                    }
                ],
                "status": item["status"],
                "urgency": None,
                "openChangeCount": 0,
            },
        )
        self.assertEqual(set(item["status"]), {"key", "kind", "label"})

    def test_the_department_view_names_its_unit_and_a_bucket_keeps_one_section(self) -> None:
        page = read(self, self.bank, self.bank.johan, f"scope=unit&unit={self.bank.retail.id}&bucket=open")
        self.assertEqual((page["scope"], page["unit"]), ("unit", str(self.bank.retail.id)))
        self.assertEqual((page["items"], page["total"]), ([], 0))
        self.assertEqual(page["counts"]["overdue"], 1, "the counts cover every section")

    def test_a_query_that_makes_no_sense_is_refused(self) -> None:
        for query in (
            "scope=unit",
            f"scope=mine&unit={self.bank.retail.id}",
            "bucket=someday",
            "scope=everyone",
            "limit=101",
            "limit=0",
            "offset=-1",
        ):
            with self.subTest(query=query):
                problem = read(self, self.bank, self.bank.anna, query, status=422)
                self.assertEqual(problem["code"], "validation_error")

    def test_a_unit_of_another_bank_or_of_none_is_not_found(self) -> None:
        for unit in (self.other.retail.id, uuid.uuid4()):
            with self.subTest(unit=unit):
                problem = read(self, self.bank, self.bank.anna, f"scope=unit&unit={unit}", status=404)
                self.assertEqual(problem["code"], "not_found")

    def test_without_a_member_session_it_is_refused(self) -> None:
        self.assertEqual(self.client.get(URL).json()["code"], "unauthenticated")
        enrolling = factories.user(status=UserStatus.INVITED)
        response = self.client.get(URL, **sign_in(enrolling, tenant=self.bank.tenant, kind="enrolment"))
        self.assertEqual((response.status_code, response.json()["code"]), (403, "enrolment_only"))
        response = self.client.get(URL, **sign_in(factories.platform_user()))
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_a_role_that_reads_nothing_gets_the_page_with_the_kinds_named(self) -> None:
        give_role(self.bank, self.bank.anna, permissions={perms.LIBRARY_READ})
        page = read(self, self.bank, self.bank.anna)
        self.assertEqual(
            (page["items"], page["total"], page["counts"]),
            ([], 0, {"overdue": 0, "dueSoon": 0, "aware": 0, "open": 0}),
        )
        self.assertEqual(page["permissionLimited"], ["tenant_obligation", "internal_item", "change_case"])

    def test_another_bank_never_answers_for_this_one(self) -> None:
        factories.member(self.other.tenant, user_row=self.bank.anna)
        self.assertEqual(read(self, self.other, self.bank.anna)["items"], [])

    def test_the_read_writes_nothing(self) -> None:
        headers = sign_in(self.bank.anna, tenant=self.bank.tenant)
        audits, outbox = AuditEvent.objects.count(), OutboxEvent.objects.count()
        self.assertEqual(self.client.get(URL, **headers).status_code, 200)
        self.assertEqual((AuditEvent.objects.count(), OutboxEvent.objects.count()), (audits, outbox))


# ---------------------------------------------------------------------------------------
# Participations (COL-04)
# ---------------------------------------------------------------------------------------
class Participations(TestCase):
    """Taking part in a register entry reaches My work; an ended participation does not."""

    bank: Bank
    joined: Obligation
    teamed: Obligation
    left: Obligation
    not_applying: Obligation
    owned_and_joined: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-participants")
        today = bank.today()
        cls.joined = obligation("Joined by Erik")
        cls.teamed = obligation("Joined by Cards")
        cls.left = obligation("Left by Erik")
        cls.not_applying = obligation("Joined, does not apply")
        cls.owned_and_joined = obligation("Owned by Erik, joined by Cards")
        entry = bank.entry(cls.joined, first_line_owner=bank.anna, next_review_date=today + 50 * DAY)
        # Someone else's gap on the entry dates everyone on the entry itself, a participant too.
        bank.gap(entry, owner=bank.johan, target_date=today + 4 * DAY, org_unit=bank.fund_ab)
        bank.entry(cls.teamed)
        bank.entry(cls.left)
        bank.entry(cls.not_applying, applicability=Applicability.DOES_NOT_APPLY.value)
        bank.entry(cls.owned_and_joined, first_line_owner=bank.erik)
        take_part(bank, cls.joined, user=bank.erik)
        take_part(bank, cls.teamed, team=bank.cards)
        ended = take_part(bank, cls.left, user=bank.erik)
        Participant.objects.filter(pk=ended.pk).update(removed_at=timezone.now(), removed_by=bank.erik)
        take_part(bank, cls.not_applying, user=bank.erik)
        take_part(bank, cls.owned_and_joined, team=bank.cards)

    def test_a_person_and_a_team_taking_part_are_listed_with_the_reason(self) -> None:
        page = read(self, self.bank, self.bank.erik)
        self.assertEqual(
            ids(page), {str(self.joined.id), str(self.teamed.id), str(self.owned_and_joined.id)}
        )
        self.assertEqual(whos(item_for(page, self.joined.id)), {("participant", "Erik Holm")})
        self.assertEqual(whos(item_for(page, self.teamed.id)), {("participant", "cards")})
        self.assertEqual(
            whos(item_for(page, self.owned_and_joined.id)),
            {("owner", "Erik Holm"), ("participant", "cards")},
            "one row, every reason",
        )

    def test_a_participant_is_dated_like_the_entry_own_people(self) -> None:
        item = item_for(read(self, self.bank, self.bank.erik), self.joined.id)
        self.assertEqual(date_of(item), ("due_soon", "gap_target", (self.bank.today() + 4 * DAY).isoformat()))
        self.assertEqual(item["entity"]["name"], "Fund AB")

    def test_a_participation_does_not_touch_the_owner_row(self) -> None:
        item = item_for(read(self, self.bank, self.bank.anna), self.joined.id)
        self.assertEqual(whos(item), {("owner", "Anna Berg")})

    def test_the_department_view_names_the_participant(self) -> None:
        page = read(self, self.bank, self.bank.karin, f"scope=unit&unit={self.bank.retail.id}")
        self.assertEqual(
            whos(item_for(page, self.joined.id)), {("owner", "Anna Berg"), ("owner", "Johan Ek"), ("participant", "Erik Holm")}
        )
        self.assertEqual(whos(item_for(page, self.teamed.id)), {("participant", "cards")})

    def test_a_deactivated_participant_leaves_the_department_view(self) -> None:
        self.bank.activate()
        Membership.objects.filter(user=self.bank.erik).update(deactivated_at=timezone.now())
        page = read(self, self.bank, self.bank.karin, f"scope=unit&unit={self.bank.retail.id}")
        self.assertEqual(whos(item_for(page, self.teamed.id)), {("participant", "cards")})
        self.assertEqual(
            whos(item_for(page, self.joined.id)), {("owner", "Anna Berg"), ("owner", "Johan Ek")}
        )


# ---------------------------------------------------------------------------------------
# Comments and mentions (COL-01, D-25)
# ---------------------------------------------------------------------------------------
class Comments(TestCase):
    """A colleague's comment on a record on the list is a change on it, for the window."""

    bank: Bank
    duty: Obligation
    quiet: Obligation
    elsewhere: Obligation
    change: RegulatoryChange
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-comments")
        cls.duty = obligation("Commented duty")
        cls.quiet = obligation("Quiet duty")
        cls.elsewhere = obligation("Not Anna's")
        bank.entry(cls.duty, first_line_owner=bank.anna)
        bank.entry(cls.quiet, first_line_owner=bank.anna)
        bank.entry(cls.elsewhere, first_line_owner=bank.karin)
        cls.change = watch_build.change(title="A reform", key_date=None)
        watch_build.obligation_link(cls.change, cls.quiet)
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() - 3 * DAY):
            confirm(cls.change, confirmed_by=bank.officer)
        cls.case = cases_build.case(bank.tenant, cls.change)

    def aware(self, user: User | None = None) -> dict[str, dict[str, Any]]:
        page = read(self, self.bank, user or self.bank.anna, "bucket=aware")
        return {subject_of(item): item for item in page["items"]}

    def test_a_colleague_comment_marks_the_record_with_the_day_it_was_written(self) -> None:
        comment(self.bank, self.bank.johan, "obligation", self.duty.id)
        item = self.aware()[str(self.duty.id)]
        self.assertEqual(date_of(item), ("aware", "commented", self.bank.today().isoformat()))
        self.assertNotIn(SECRET, str(item))

    def test_a_mention_on_the_record_marks_it_too(self) -> None:
        comment(self.bank, self.bank.johan, "obligation", self.duty.id, mentions=(self.bank.anna,))
        self.assertIn(str(self.duty.id), self.aware())

    def test_a_comment_on_a_case_on_the_list_moves_its_date(self) -> None:
        self.assertEqual(date_of(self.aware()[str(self.change.id)])[1], "linked")
        comment(self.bank, self.bank.johan, "change_case", self.case.id)
        self.assertEqual(
            date_of(self.aware()[str(self.change.id)]), ("aware", "commented", self.bank.today().isoformat())
        )

    def test_the_caller_own_a_deleted_and_an_old_comment_never_count(self) -> None:
        comment(self.bank, self.bank.anna, "obligation", self.duty.id)
        comment(self.bank, self.bank.johan, "obligation", self.duty.id, deleted=True)
        comment(self.bank, self.bank.johan, "obligation", self.duty.id, ago=datetime.timedelta(days=15))
        self.assertNotIn(str(self.duty.id), self.aware())

    def test_a_comment_off_the_list_adds_nothing(self) -> None:
        comment(self.bank, self.bank.johan, "obligation", self.elsewhere.id)
        self.assertNotIn(str(self.elsewhere.id), ids(read(self, self.bank, self.bank.anna)))

    @override_settings(MY_WORK_AWARE_DAYS=30)
    def test_the_window_is_the_setting(self) -> None:
        comment(self.bank, self.bank.johan, "obligation", self.duty.id, ago=datetime.timedelta(days=20))
        self.assertIn(str(self.duty.id), self.aware())

    def test_a_kind_the_reader_may_not_read_comments_on_counts_for_nothing(self) -> None:
        """Comments on an obligation are read with `library.read` (the subject registry): a
        role holding the register but not the library sees the row and not the comment."""
        comment(self.bank, self.bank.johan, "obligation", self.duty.id)
        give_role(self.bank, self.bank.anna, permissions={perms.REGISTER_READ, perms.CASES_READ})
        page = read(self, self.bank, self.bank.anna)
        self.assertEqual(item_for(page, self.duty.id)["bucket"], "open")


# ---------------------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------------------
def seed_department(bank: Bank, first: int, count: int) -> None:
    """`count` rows of every source, each owned or joined by one of the department's people
    and each carrying a colleague's comment: obligations a team owns with an entity row, a
    gap and a participant, an internal item, and a confirmed link to an open case."""
    today = bank.today()
    bank.activate()
    people = sorted(
        set(TeamMember.objects.filter(team__in=[bank.retail_team, bank.cards]).values_list("user_id", flat=True)),
        key=str,
    )
    for n in range(first, first + count):
        member = User.objects.get(pk=people[n % len(people)])
        duty = obligation(f"Duty {n}", versions=[(None, {"en": "One."}), (None, {"en": "Two."})])
        entry = bank.entry(duty, owner_team=bank.retail_team, next_review_date=today + n * DAY)
        bank.scope(entry, bank.fund_ab, owner=member, next_review_date=today - n * DAY)
        bank.gap(entry, owner=member, target_date=today, org_unit=bank.bank_ab)
        take_part(bank, duty, team=bank.cards)
        bank.internal_item(f"Policy {n}", owner_user=member, next_review_on=today)
        change = watch_build.change(title=f"Reform {n}", key_date=today + DAY)
        watch_build.obligation_link(change, duty)
        confirm(change, confirmed_by=bank.officer)
        case = cases_build.case(bank.tenant, change)
        comment(bank, bank.officer, "obligation", duty.id)
        comment(bank, bank.officer, "change_case", case.id)


def department_of(bank: Bank, size: int) -> None:
    """Grow the bank's Retail Banking to `size` active members across its two teams."""
    bank.activate()
    in_teams = {bank.anna.id, bank.johan.id, bank.erik.id}
    for n in range(size - len(in_teams)):
        person = bank.person(f"Member {n}")
        team = bank.retail_team if n % 2 else bank.cards
        TeamMember.objects.create(tenant=bank.tenant, team=team, user=person)


def queries(test: TestCase, bank: Bank, user: User, query: str) -> int:
    headers = sign_in(user, tenant=bank.tenant)
    with CaptureQueriesContext(connection) as captured:
        response = test.client.get(f"{URL}?{query}", **headers)
    test.assertEqual(response.status_code, 200, response.content)
    return len(captured.captured_queries)


class Cost(TestCase):
    """Participants and comments add a fixed number of queries, never one per row."""

    bank: Bank

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = Bank("mywork-cost")

    def test_the_count_does_not_grow_with_the_rows(self) -> None:
        bank = self.bank
        unit = f"scope=unit&unit={bank.retail.id}&limit=100"
        # Three rows first, so each of the three people owns one of every kind and every
        # lookup already runs; more rows can then only show a query that repeats.
        seed_department(bank, 0, 3)
        mine, department = queries(self, bank, bank.anna, "limit=100"), queries(self, bank, bank.karin, unit)
        seed_department(bank, 3, 6)
        self.assertEqual(queries(self, bank, bank.anna, "limit=100"), mine)
        self.assertEqual(queries(self, bank, bank.karin, unit), department)


# ---------------------------------------------------------------------------------------
# The scenarios, called from tests_scenarios.py
# ---------------------------------------------------------------------------------------
def run_hom_s7(test: TestCase) -> None:
    """HOM-S7: what Anna is responsible for or takes part in, each once, most urgent first."""
    watch_build.seed_watch_reference()
    bank = Bank("hom-s7")
    today = bank.today()
    reviewed = obligation("Review the suitability assessment")
    gapped = obligation("Reconcile client assets")
    teamed = obligation("Report large exposures")
    not_applying = obligation("Offer crowdfunding")
    bank.entry(reviewed, first_line_owner=bank.anna, next_review_date=today - 12 * DAY)
    bank.gap(bank.entry(gapped, first_line_owner=bank.karin), owner=bank.anna, target_date=today + 9 * DAY)
    policy = bank.internal_item("Complaints procedure", owner_user=bank.anna, next_review_on=today + 40 * DAY)
    bank.entry(teamed)
    take_part(bank, teamed, team=bank.retail_team)
    bank.entry(not_applying, first_line_owner=bank.anna, applicability=Applicability.DOES_NOT_APPLY.value)

    page = read(test, bank, bank.anna)

    test.assertEqual(
        [(subject_of(item), item["bucket"]) for item in page["items"]],
        [
            (str(reviewed.id), "overdue"),
            (str(gapped.id), "due_soon"),
            (str(policy.id), "open"),
            (str(teamed.id), "open"),
        ],
        "each once, in its most urgent section, dated rows before undated ones",
    )
    test.assertEqual(date_of(page["items"][0]), ("overdue", "review", (today - 12 * DAY).isoformat()))
    test.assertEqual(date_of(page["items"][1]), ("due_soon", "gap_target", (today + 9 * DAY).isoformat()))
    teamed_item = item_for(page, teamed.id)
    test.assertEqual(teamed_item["date"], None)
    test.assertEqual(whos(teamed_item), {("participant", "retail_compliance")}, "your team takes part")
    test.assertEqual(page["counts"], {"overdue": 1, "dueSoon": 1, "aware": 0, "open": 2})
    # Keys, kinds, dates and record names: every value the screen phrases is a key.
    for item in page["items"]:
        test.assertIn(item["itemKind"], ("tenant_obligation", "internal_item"))
        for reason in item["reasons"]:
            test.assertIn(reason["reason"], ("owner", "participant"))
    test.assertEqual(item_for(page, policy.id)["subject"]["title"], "Complaints procedure")


def run_hom_s8(test: TestCase) -> None:
    """HOM-S8: a compliant obligation and a per-entity review reach My work."""
    watch_build.seed_watch_reference()
    bank = Bank("hom-s8")
    today = bank.today()
    compliant = obligation("Assess costs and charges")
    split = obligation("Assess the quality of investment research paid for")
    entry = bank.entry(compliant, first_line_owner=bank.anna, compliance_status=bank.compliant)
    entity_row = bank.scope(entry, bank.bank_ab, next_review_date=today + 20 * DAY)
    TenantObligationScope.objects.filter(pk=entity_row.pk).update(compliance_status=bank.compliant)
    second = bank.entry(split, first_line_owner=bank.johan)
    bank.scope(second, bank.fund_ab, owner=bank.erik, next_review_date=today - 3 * DAY)

    anna = item_for(read(test, bank, bank.anna), compliant.id)
    test.assertEqual(date_of(anna), ("due_soon", "review", (today + 20 * DAY).isoformat()))
    test.assertEqual(anna["status"]["kind"], "compliant")

    erik = item_for(read(test, bank, bank.erik), split.id)
    test.assertEqual(date_of(erik), ("overdue", "review", (today - 3 * DAY).isoformat()))
    test.assertEqual(erik["entity"]["name"], "Fund AB")
    test.assertEqual(whos(erik), {("owner", "Erik Holm")})

    johan = item_for(read(test, bank, bank.johan), split.id)
    test.assertEqual(date_of(johan), ("overdue", "review", (today - 3 * DAY).isoformat()))


def run_hom_s9(test: TestCase) -> None:
    """HOM-S9: Karin's department view names who is responsible; it grants nothing."""
    watch_build.seed_watch_reference()
    bank = Bank("hom-s9")
    team_owned = obligation("Monitor transactions")
    anna_owned = obligation("Keep the insider list")
    erik_joined = obligation("Report card fraud")
    bank.entry(team_owned, owner_team=bank.retail_team)
    bank.entry(anna_owned, first_line_owner=bank.anna)
    bank.entry(erik_joined)
    take_part(bank, erik_joined, user=bank.erik)
    view = f"scope=unit&unit={bank.retail.id}"

    karin = read(test, bank, bank.karin, view)
    test.assertEqual(ids(karin), {str(team_owned.id), str(anna_owned.id), str(erik_joined.id)})
    test.assertEqual(whos(item_for(karin, team_owned.id)), {("owner", "retail_compliance")})
    test.assertEqual(whos(item_for(karin, anna_owned.id)), {("owner", "Anna Berg")})
    test.assertEqual(whos(item_for(karin, erik_joined.id)), {("participant", "Erik Holm")})

    johan = read(test, bank, bank.johan, view)
    test.assertEqual(johan["items"], karin["items"], "a filter, the same for every reader")

    bank.activate()
    Membership.objects.filter(user=bank.erik).update(deactivated_at=timezone.now())
    test.assertNotIn(str(erik_joined.id), ids(read(test, bank, bank.karin, view)))


def run_hom_s10(test: TestCase) -> None:
    """HOM-S10: a participant whose role lost register.read sees no row and no count, the
    page says the kind is limited, the participation stays; the footprint hides nothing."""
    watch_build.seed_watch_reference()
    bank = Bank("hom-s10")
    joined = obligation("Safeguard client funds")
    bank.entry(joined, next_review_date=bank.today() - DAY)
    give_role(bank, bank.officer, key="compliance_officer")
    role = give_role(bank, bank.erik, permissions={perms.LIBRARY_READ, perms.REGISTER_READ, perms.CASES_READ})
    added = test.client.post(
        f"/api/v1/obligations/{joined.id}/participants",
        {"userId": str(bank.erik.id)},
        content_type="application/json",
        **sign_in(bank.officer, tenant=bank.tenant),
    )
    test.assertEqual(added.status_code, 201, added.content)
    test.assertEqual(ids(read(test, bank, bank.erik)), {str(joined.id)})

    bank.activate()
    TenantRole.objects.filter(pk=role.pk).update(permissions=[perms.LIBRARY_READ, perms.CASES_READ])
    page = read(test, bank, bank.erik)
    test.assertEqual((page["items"], page["total"]), ([], 0))
    test.assertEqual(page["counts"], {"overdue": 0, "dueSoon": 0, "aware": 0, "open": 0})
    test.assertEqual(page["permissionLimited"], ["tenant_obligation", "internal_item"])
    bank.activate()
    test.assertTrue(Participant.objects.filter(user=bank.erik, removed_at__isnull=True).exists())

    advice = obligation("Assess suitability before advice", terms=["service_type:advice"])
    bank.entry(advice, first_line_owner=bank.anna)
    bank.activate()
    FootprintTerm.objects.create(tenant=bank.tenant, term=library_build.term("service_type:custody"))
    test.assertIn(str(advice.id), ids(read(test, bank, bank.anna)))


def run_hom_s11(test: TestCase) -> None:
    """HOM-S11: confirmed links, new versions and colleagues' comments, for the window;
    never a suggestion, never Anna's own acts."""
    watch_build.seed_watch_reference()
    confirmer = agent_build.agent_key(agent_row=agent_build.agent(kind=AgentKind.REVIEW))
    bank = Bank("hom-s11")
    duty = obligation("Linked duty")
    amended = obligation("Amended duty", versions=[(None, {"en": "Before."}), (None, {"en": "After."})])
    discussed = obligation("Discussed duty")
    own = obligation("Anna's own acts")
    for row in (duty, amended, discussed, own):
        bank.entry(row, first_line_owner=bank.anna)
    change = watch_build.change(title="A reform", key_date=None)
    watch_build.obligation_link(change, duty)
    case = cases_build.case(bank.tenant, change)

    def aware(at: datetime.datetime | None = None) -> dict[str, dict[str, Any]]:
        with mock.patch("django.utils.timezone.now", return_value=at or timezone.now()):
            page = read(test, bank, bank.anna, "bucket=aware")
        return {subject_of(item): item for item in page["items"]}

    test.assertNotIn(str(change.id), aware(), "a suggestion nobody confirmed")

    confirm(change, confirmed_by_api_key_id=confirmer.id, confirmed_by_agent_id=confirmer.agent.id)
    listed = aware()[str(change.id)]
    test.assertEqual(listed["itemKind"], "change_case")
    test.assertEqual(
        [(r["reason"], r["via"]["obligationId"]) for r in listed["reasons"]], [("owner", str(duty.id))]
    )
    test.assertEqual(listed["urgency"]["key"], case.urgency.key)

    comment(bank, bank.johan, "obligation", discussed.id)
    comment(bank, bank.anna, "obligation", own.id)
    with library_write("test fixture"):
        ObligationVersion.objects.create(obligation=own, version_number=2, approved_by=bank.anna)
    now = aware()
    test.assertEqual(date_of(now[str(amended.id)])[:2], ("aware", "version_applied"))
    test.assertEqual(date_of(now[str(discussed.id)])[:2], ("aware", "commented"))
    test.assertNotIn(str(own.id), now, "nothing Anna did herself")

    later = aware(timezone.now() + 15 * DAY)
    test.assertNotIn(str(amended.id), later)
    test.assertNotIn(str(discussed.id), later)


def run_hom_s12(test: TestCase) -> None:
    """HOM-S12: a department of fifty members, the same queries whatever its size, inside
    the budget. Duties have no rows until REG-07 lands, so they add nothing here."""
    watch_build.seed_watch_reference()
    bank = Bank("hom-s12")
    department_of(bank, 50)
    bank.activate()
    test.assertEqual(
        TeamMember.objects.filter(team__in=[bank.retail_team, bank.cards]).values("user").distinct().count(), 50
    )
    view = f"scope=unit&unit={bank.retail.id}&limit=100"
    seed_department(bank, 0, 2)
    small = queries(test, bank, bank.karin, view)
    seed_department(bank, 2, 10)
    test.assertEqual(queries(test, bank, bank.karin, view), small)

    headers = sign_in(bank.karin, tenant=bank.tenant)
    # CPU time on the request thread, the best of five, with coverage's tracer paused, as
    # every budget test here measures it.
    spent = []
    tracer = sys.gettrace()
    sys.settrace(None)
    try:
        for _ in range(5):
            started = time.thread_time()
            response = test.client.get(f"{URL}?{view}", **headers)
            spent.append((time.thread_time() - started) * 1000)
    finally:
        sys.settrace(tracer)
    test.assertEqual(response.status_code, 200)
    test.assertEqual(response.json()["total"], 12 * 3)
    test.assertLess(min(spent), settings.API_BUDGET_MS)


class _Captured(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.getMessage()} {record.__dict__}")


def run_col_s12(test: TestCase) -> None:
    """COL-S12: my comments and mentions, limited to what I can read, and Johan's comment on
    Anna's obligation on her My work; ids in the log, the audit and the outbox, never text."""
    watch_build.seed_watch_reference()
    bank = Bank("col-s12")
    first, second = obligation("Assess costs"), obligation("Keep records")
    owned = obligation("Anna's duty")
    bank.entry(owned, first_line_owner=bank.anna)
    case = cases_build.case(bank.tenant, watch_build.change(title="FI amends research payments"))
    give_role(bank, bank.johan, permissions={perms.LIBRARY_READ, perms.REGISTER_READ, perms.COMMENTS_WRITE})

    handler = _Captured()
    logging.getLogger().addHandler(handler)
    try:
        older = comment(bank, bank.anna, "obligation", first.id, ago=datetime.timedelta(minutes=30))
        newer = comment(bank, bank.anna, "obligation", second.id, ago=datetime.timedelta(minutes=10))
        mention = comment(bank, bank.erik, "change_case", case.id, mentions=(bank.anna,))
        comment(bank, bank.erik, "change_case", case.id, mentions=(bank.johan,))

        def mine(user: User, query: str) -> dict[str, Any]:
            response = test.client.get(f"/api/v1/me/comments?{query}", **sign_in(user, tenant=bank.tenant))
            test.assertEqual(response.status_code, 200, response.content)
            body: dict[str, Any] = response.json()
            return body

        mentions = mine(bank.anna, "about=mentioned")
        test.assertEqual([row["id"] for row in mentions["items"]], [str(mention.id)])
        test.assertEqual(
            (mentions["items"][0]["subjectType"], mentions["items"][0]["subjectId"]), ("change_case", str(case.id))
        )
        pages = [mine(bank.anna, f"about=written&limit=1&offset={n}") for n in (0, 1)]
        test.assertEqual([page["items"][0]["id"] for page in pages], [str(newer.id), str(older.id)])
        test.assertEqual(pages[0]["total"], 2)

        johan = mine(bank.johan, "about=mentioned")
        test.assertEqual((johan["items"], johan["permissionLimitedKinds"]), ([], ["change_case"]))
        bank.activate()
        with transaction.atomic():
            sent = notify(
                tenant_id=bank.tenant.id,
                kind=NotificationKind.MENTION,
                subject_type="change_case",
                subject_id=case.id,
                candidates=[(bank.johan.id, "mention")],
            )
        test.assertEqual(sent, [])
        test.assertFalse(Notification.objects.filter(user=bank.johan).exists())

        comment(bank, bank.johan, "obligation", owned.id)
        item = item_for(read(test, bank, bank.anna, "bucket=aware"), owned.id)
        test.assertEqual(date_of(item)[:2], ("aware", "commented"))
    finally:
        logging.getLogger().removeHandler(handler)
    test.assertFalse([line for line in handler.lines if SECRET in line])
    bank.activate()
    for model in (AuditEvent, OutboxEvent):
        test.assertFalse([row for row in model.objects.values() if SECRET in str(row)], model.__name__)
