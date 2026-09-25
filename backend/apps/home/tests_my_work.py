"""My work's service (HOM-05, TEN-03, D-23, D-24, D-25, D-97), proved on Postgres under
row-level security, one class per question:

- **Sources.** Each source reaches the person or the team it names, and each record is
  one row however many reasons it has. Entries and entity rows that do not apply, closed
  gaps and inactive internal items never do.
- **Dates and buckets.** A person on the record itself is dated by its earliest open date,
  one on a child by that child's own; the buckets' edges sit on the bank's own today and
  the `MY_WORK_DUE_SOON_DAYS` setting; each section has its order; the counts cover every
  section whatever the filter and the paging.
- **Permissions and the footprint.** Rows and counts come from the permission-filtered
  set, unreadable kinds are named, and the footprint hides nothing (D-24).
- **Departments.** A unit's view expands to its teams and the units below, with active
  members only, names who is responsible, and grants nothing.
- **Changes on your items.** Confirmed links only, a person's or an independent agent's
  (D-97); new versions for `MY_WORK_AWARE_DAYS`; never the caller's own acts.
- **Isolation and cost.** Another bank's rows never appear, and the query count does not
  grow with the number of rows.

Every date is the bank's own today plus an offset, never a literal (playbook 8.3).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError

from apps.agents import testing as agent_build
from apps.agents.models import AgentKind
from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.home import my_work
from apps.home.schemas import HomeWorkItem, HomeWorkPage, HomeWorkQuery
from apps.identity.models import Membership, User
from apps.library import testing as library_build
from apps.library.models import Obligation, ObligationVersion
from apps.library.reading import today_for
from apps.register import logic as register_logic
from apps.register.models import Applicability, Gap, TenantObligation, TenantObligationScope
from apps.shared import factories, tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.permissions import CASES_READ, REGISTER_READ
from apps.shared.tenancy import library_write
from apps.taxonomy.models import (
    CaseStatusCategory,
    ComplianceStatus,
    FootprintTerm,
    GapSource,
    GapStatus,
    LinkKind,
    RiskRating,
    Team,
)
from apps.tenants.models import InternalItem, OrgUnit, OrgUnitKind, TeamMember
from apps.watch import testing as watch_build
from apps.watch.models import ChangeObligation, RegulatoryChange
from apps.watch.write import watch_write

EVERYTHING = frozenset({REGISTER_READ, CASES_READ})
DAY = datetime.timedelta(days=1)


class Bank:
    """One bank's people and organisation, as HOM-S9 draws it: Karin heads Retail Banking,
    whose team Retail compliance holds Anna and Johan; Cards and payments sits under it,
    and its team Cards holds Erik. Legal is a unit with no team."""

    def __init__(self, slug: str) -> None:
        self.tenant = factories.tenant(slug=slug)
        self.anna = self.person("Anna Berg")
        self.johan = self.person("Johan Ek")
        self.erik = self.person("Erik Holm")
        self.karin = self.person("Karin Sund")
        self.officer = self.person("Olle Nyström")
        self.activate()
        self.bank_ab = self.unit(OrgUnitKind.LEGAL_ENTITY, "Bank AB")
        self.fund_ab = self.unit(OrgUnitKind.LEGAL_ENTITY, "Fund AB")
        self.retail = self.unit(OrgUnitKind.BUSINESS_AREA, "Retail Banking", head=self.karin)
        self.cards_unit = self.unit(
            OrgUnitKind.BUSINESS_UNIT, "Cards and payments", parent=self.retail
        )
        self.legal = self.unit(OrgUnitKind.FUNCTION, "Legal")
        self.retail_team = self.team("retail_compliance", self.retail, [self.anna, self.johan])
        self.cards = self.team("cards", self.cards_unit, [self.erik])
        self.default_status = ComplianceStatus.objects.get(is_default=True)
        self.compliant = ComplianceStatus.objects.get(key="compliant")

    def activate(self) -> None:
        tenancy.activate(self.tenant.id)

    def person(self, name: str) -> User:
        return factories.member(self.tenant, user_row=factories.user(name=name)).user

    def unit(
        self,
        kind: OrgUnitKind,
        name: str,
        *,
        parent: OrgUnit | None = None,
        head: User | None = None,
    ) -> OrgUnit:
        return OrgUnit.objects.create(
            tenant=self.tenant, kind=kind.value, name=name, parent=parent, head_user=head
        )

    def team(self, key: str, unit: OrgUnit, people: list[User]) -> Team:
        row = Team.objects.create(tenant=self.tenant, key=key, org_unit=unit)
        for person in people:
            TeamMember.objects.create(tenant=self.tenant, team=row, user=person)
        return row

    def entry(self, obligation: Obligation, **fields: Any) -> TenantObligation:
        """The register entry, made the one way an entry is made, then given its owners."""
        self.activate()
        row = register_logic.ensure_register_entry(
            tenant_id=self.tenant.id, obligation_id=obligation.id, actor=factories.user_actor()
        )
        fields.setdefault("applicability", Applicability.APPLIES.value)
        TenantObligation.objects.filter(pk=row.pk).update(**fields)
        return row

    def scope(self, entry: TenantObligation, unit: OrgUnit, **fields: Any) -> TenantObligationScope:
        self.activate()
        return TenantObligationScope.objects.create(
            tenant=self.tenant,
            tenant_obligation=entry,
            org_unit=unit,
            compliance_status=self.default_status,
            **fields,
        )

    def gap(self, entry: TenantObligation, *, status: str = "open", **fields: Any) -> Gap:
        self.activate()
        return Gap.objects.create(
            tenant=self.tenant,
            tenant_obligation=entry,
            title="Reconciliation is weekly",
            severity=RiskRating.objects.get(key="high"),
            source=GapSource.objects.get(key="audit"),
            status=GapStatus.objects.get(key=status),
            identified_by=self.officer,
            **fields,
        )

    def internal_item(self, name: str, **fields: Any) -> InternalItem:
        self.activate()
        return InternalItem.objects.create(
            tenant=self.tenant, kind=LinkKind.objects.get(key="policy"), name=name, **fields
        )

    def today(self) -> datetime.date:
        return today_for(self.tenant)

    def read(
        self,
        user: User,
        *,
        permissions: frozenset[str] = EVERYTHING,
        at: datetime.datetime | None = None,
        **query: Any,
    ) -> HomeWorkPage:
        """My work as `user` reads it, now or at `at`."""
        self.activate()
        principal = Principal(
            kind=PrincipalKind.USER,
            subject_id=user.id,
            tenant_id=self.tenant.id,
            permissions=permissions,
        )
        with mock.patch("django.utils.timezone.now", return_value=at or timezone.now()):
            return my_work.page(self.tenant, principal, ["en"], HomeWorkQuery(**query))


_keys = iter(range(1, 10_000))


def obligation(title: str, **extra: Any) -> Obligation:
    instrument = library_build.instrument(key=f"mw-{next(_keys)}", regime="regime:securities")
    return library_build.obligation(
        instrument, key=f"mw-obl-{next(_keys)}", titles={"en": title}, **extra
    )


def ids(page: HomeWorkPage) -> list[uuid.UUID]:
    return [_subject_id(item) for item in page.items]


def _subject_id(item: HomeWorkItem) -> uuid.UUID:
    subject = item.subject
    return next(
        value
        for value in (subject.obligation_id, subject.change_id, subject.internal_item_id)
        if value
    )


def row(page: HomeWorkPage, subject: uuid.UUID) -> HomeWorkItem:
    return next(item for item in page.items if _subject_id(item) == subject)


def facts(item: HomeWorkItem) -> dict[str, Any]:
    """A row's bucket, date, date kind, entity, status and urgency as plain values."""
    out = item.model_dump()
    return {
        "bucket": item.bucket,
        "date": (out["date"] or {}).get("value"),
        "kind": (out["date"] or {}).get("kind"),
        "entity": (out["entity"] or {}).get("name"),
        "status": (out["status"] or {}).get("key"),
        "status_kind": (out["status"] or {}).get("kind"),
        "urgency": (out["urgency"] or {}).get("key"),
    }


def pick(item: HomeWorkItem, *names: str) -> tuple[Any, ...]:
    found = facts(item)
    return tuple(found[name] for name in names)


def whos(item: HomeWorkItem) -> set[tuple[str, str]]:
    """Each reason as (reason, the person's name or the team's key)."""
    return {
        (
            reason["reason"],
            (reason["who"]["person"] or {}).get("name") or reason["who"]["team"]["key"],
        )
        for reason in item.model_dump()["reasons"]
    }


class Sources(TestCase):
    """Every source reaches whom it names, once per record; the hidden ones never do."""

    bank: Bank
    first: Obligation
    contact: Obligation
    teamed: Obligation
    split: Obligation
    gapped: Obligation
    closed_gap_only: Obligation
    not_applying: Obligation
    entity_not_applying: Obligation
    policy: InternalItem
    team_policy: InternalItem
    retired: InternalItem

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-sources")
        today = bank.today()
        cls.first = obligation("First-line owned")
        cls.contact = obligation("Contact")
        cls.teamed = obligation("Team owned")
        cls.split = obligation("Split by entity")
        cls.gapped = obligation("Gap owned")
        cls.closed_gap_only = obligation("Only a closed gap")
        cls.not_applying = obligation("Does not apply")
        cls.entity_not_applying = obligation("Entity row does not apply")
        bank.entry(
            cls.first,
            first_line_owner=bank.anna,
            next_review_date=today + 60 * DAY,
            compliance_status=bank.compliant,
        )
        bank.entry(cls.contact, compliance_contact=bank.anna)
        bank.entry(cls.teamed, owner_team=bank.retail_team, next_review_date=today + 10 * DAY)
        split = bank.entry(cls.split, first_line_owner=bank.johan)
        bank.scope(split, bank.fund_ab, owner=bank.anna, next_review_date=today + 5 * DAY)
        bank.scope(split, bank.bank_ab, next_review_date=today - DAY)
        gapped = bank.entry(
            cls.gapped, first_line_owner=bank.karin, next_review_date=today + 90 * DAY
        )
        bank.gap(gapped, owner=bank.anna, target_date=today + 3 * DAY, org_unit=bank.fund_ab)
        bank.gap(gapped, status="closed", owner=bank.anna, target_date=today - 10 * DAY)
        bank.gap(
            bank.entry(cls.closed_gap_only), status="closed", owner=bank.anna, target_date=today
        )
        bank.entry(
            cls.not_applying,
            first_line_owner=bank.anna,
            applicability=Applicability.DOES_NOT_APPLY.value,
        )
        entity_na = bank.entry(cls.entity_not_applying, first_line_owner=bank.karin)
        bank.scope(
            entity_na,
            bank.fund_ab,
            owner=bank.anna,
            applicability=Applicability.DOES_NOT_APPLY.value,
        )
        cls.policy = bank.internal_item(
            "Custody policy", owner_user=bank.anna, next_review_on=today + 2 * DAY
        )
        cls.team_policy = bank.internal_item("Retail procedure", owner_team=bank.retail_team)
        cls.retired = bank.internal_item("Retired policy", owner_user=bank.anna, active=False)

    def test_each_source_reaches_the_person_it_names_once(self) -> None:
        page = self.bank.read(self.bank.anna)
        expected = {
            self.first.id,
            self.contact.id,
            self.teamed.id,
            self.split.id,
            self.gapped.id,
            self.policy.id,
            self.team_policy.id,
        }
        self.assertEqual(
            sorted(ids(page), key=str),
            sorted(expected, key=str),
            "each record once, and only these",
        )
        kinds = {_subject_id(item): item.item_kind for item in page.items}
        self.assertEqual(kinds[self.policy.id], "internal_item")
        self.assertEqual(kinds[self.first.id], "tenant_obligation")

    def test_each_reason_names_the_person_or_the_team(self) -> None:
        page = self.bank.read(self.bank.anna)
        self.assertEqual(whos(row(page, self.first.id)), {("owner", "Anna Berg")})
        self.assertEqual(whos(row(page, self.contact.id)), {("owner", "Anna Berg")})
        self.assertEqual(whos(row(page, self.teamed.id)), {("owner", "retail_compliance")})
        self.assertEqual(whos(row(page, self.team_policy.id)), {("owner", "retail_compliance")})
        self.assertIsNone(row(page, self.first.id).reasons[0].via)

    def test_the_hidden_sources_never_reach_anyone(self) -> None:
        listed = set(ids(self.bank.read(self.bank.anna)))
        for hidden in (
            self.not_applying.id,
            self.closed_gap_only.id,
            self.entity_not_applying.id,
            self.retired.id,
        ):
            self.assertNotIn(hidden, listed)

    def test_a_child_dates_its_owner_and_the_record_dates_the_entry_people(self) -> None:
        """HOM-S8's second half: Anna owns the Fund AB row, Johan the entry itself."""
        today = self.bank.today()
        anna = row(self.bank.read(self.bank.anna), self.split.id)
        self.assertEqual(
            pick(anna, "bucket", "date", "kind", "entity"),
            ("due_soon", today + 5 * DAY, "review", "Fund AB"),
        )
        johan = row(self.bank.read(self.bank.johan), self.split.id)
        self.assertEqual(
            pick(johan, "bucket", "date", "entity"), ("overdue", today - DAY, "Bank AB")
        )
        self.assertEqual(whos(johan), {("owner", "Johan Ek")})

    def test_an_open_gap_dates_its_owner_and_a_closed_one_dates_nobody(self) -> None:
        today = self.bank.today()
        anna = row(self.bank.read(self.bank.anna), self.gapped.id)
        self.assertEqual(pick(anna, "date", "kind"), (today + 3 * DAY, "gap_target"))
        karin = row(self.bank.read(self.bank.karin), self.gapped.id)
        self.assertEqual(
            facts(karin)["date"],
            today + 3 * DAY,
            "the entry's owner sees the earliest open date on it",
        )

    def test_a_row_carries_the_entry_status_and_record_names(self) -> None:
        item = row(self.bank.read(self.bank.anna), self.first.id)
        self.assertEqual(pick(item, "status", "status_kind"), ("compliant", "compliant"))
        self.assertEqual(item.subject.title, "First-line owned")
        self.assertEqual(
            row(self.bank.read(self.bank.anna), self.policy.id).subject.title, "Custody policy"
        )


class Buckets(TestCase):
    """Edges on the bank's own today and the due-soon setting; order; counts; paging."""

    bank: Bank
    by_offset: dict[int | None, uuid.UUID]
    shared: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-buckets")
        today = bank.today()
        cls.by_offset = {}
        for offset in (-5, -1, 0, 20, 30, 31, None):
            duty = obligation(f"Review at {offset}")
            review = None if offset is None else today + offset * DAY
            bank.entry(duty, first_line_owner=bank.anna, next_review_date=review)
            cls.by_offset[offset] = duty.id
        cls.shared = obligation("Everyone on it")
        bank.entry(
            cls.shared,
            first_line_owner=bank.anna,
            compliance_contact=bank.anna,
            owner_team=bank.retail_team,
        )

    def test_each_row_sits_in_the_first_bucket_it_qualifies_for_in_order(self) -> None:
        page = self.bank.read(self.bank.anna)
        by = self.by_offset
        self.assertEqual(
            [(item.bucket, _subject_id(item)) for item in page.items[:7]],
            [
                ("overdue", by[-5]),
                ("overdue", by[-1]),
                ("due_soon", by[0]),
                ("due_soon", by[20]),
                ("due_soon", by[30]),
                ("open", by[31]),
                ("open", min(by[None], self.shared.id, key=str)),
            ],
        )
        self.assertEqual(page.items[-1].bucket, "open")
        self.assertIsNone(page.items[-1].date, "undated rows sort last")

    @override_settings(MY_WORK_DUE_SOON_DAYS=10)
    def test_due_soon_reaches_as_far_as_the_setting(self) -> None:
        page = self.bank.read(self.bank.anna)
        self.assertEqual(row(page, self.by_offset[20]).bucket, "open")

    def test_counts_cover_every_bucket_whatever_the_filter_and_the_paging(self) -> None:
        everything = self.bank.read(self.bank.anna)
        self.assertEqual(
            everything.counts.model_dump(), {"overdue": 2, "due_soon": 3, "aware": 0, "open": 3}
        )
        self.assertEqual(everything.total, 8)
        only_open = self.bank.read(self.bank.anna, bucket="open", limit=1, offset=1)
        self.assertEqual(only_open.counts, everything.counts)
        self.assertEqual(only_open.total, 3)
        self.assertEqual([item.bucket for item in only_open.items], ["open"])
        self.assertEqual(
            only_open.items[0], [item for item in everything.items if item.bucket == "open"][1]
        )

    def test_a_record_reached_several_ways_is_one_row_with_every_reason(self) -> None:
        item = row(self.bank.read(self.bank.anna), self.shared.id)
        self.assertEqual(whos(item), {("owner", "Anna Berg"), ("owner", "retail_compliance")})
        self.assertEqual(ids(self.bank.read(self.bank.anna)).count(self.shared.id), 1)

    def test_the_bank_own_today_decides(self) -> None:
        """Just before midnight UTC it is already tomorrow in Stockholm, so yesterday's review
        there is overdue by the bank's clock."""
        moment = datetime.datetime.combine(
            self.bank.today(), datetime.time(23, 30), tzinfo=datetime.UTC
        )
        page = self.bank.read(self.bank.anna, at=moment)
        self.assertEqual(row(page, self.by_offset[0]).bucket, "overdue")

    def test_the_query_names_its_scope_once(self) -> None:
        for bad in ({"scope": "unit"}, {"scope": "mine", "unit": uuid.uuid4()}):
            with self.subTest(bad), self.assertRaises(PydanticValidationError):
                HomeWorkQuery(**bad)


class PermissionsAndFootprint(TestCase):
    """HOM-S10's rule, on the service: rows and counts from the filtered set (D-23), and the
    footprint never hides a person's own items (D-24)."""

    bank: Bank
    advice: Obligation
    policy: InternalItem
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-permissions")
        today = bank.today()
        cls.advice = obligation("Advice duty", terms=["service_type:advice"])
        bank.entry(cls.advice, first_line_owner=bank.anna, next_review_date=today - DAY)
        cls.policy = bank.internal_item("Custody policy", owner_user=bank.anna)
        change = watch_build.change(title="A linked reform", key_date=None)
        watch_build.obligation_link(change, cls.advice)
        with watch_write("test fixture"):
            ChangeObligation.objects.filter(change=change).update(
                confirmed_by=bank.officer, confirmed_at=timezone.now()
            )
        cls.case = cases_build.case(bank.tenant, change)
        bank.activate()
        FootprintTerm.objects.create(
            tenant=bank.tenant, term=library_build.term("service_type:custody")
        )

    def test_without_register_read_no_row_and_no_count(self) -> None:
        page = self.bank.read(self.bank.anna, permissions=frozenset({CASES_READ}))
        self.assertEqual(page.items, [])
        self.assertEqual(
            (page.total, page.counts.model_dump()),
            (0, {"overdue": 0, "due_soon": 0, "aware": 0, "open": 0}),
        )
        self.assertEqual(page.permission_limited, ["tenant_obligation", "internal_item"])

    def test_without_cases_read_no_case_and_no_case_count(self) -> None:
        page = self.bank.read(self.bank.anna, permissions=frozenset({REGISTER_READ}))
        self.assertEqual(page.permission_limited, ["change_case"])
        self.assertNotIn(self.case.change_id, ids(page))
        self.assertEqual(row(page, self.advice.id).open_change_count, 0)
        self.assertEqual(page.total, 2)

    def test_with_both_everything_is_listed_and_nothing_limited(self) -> None:
        page = self.bank.read(self.bank.anna)
        self.assertEqual(page.permission_limited, [])
        self.assertEqual(set(ids(page)), {self.advice.id, self.policy.id, self.case.change_id})

    def test_the_footprint_hides_nothing(self) -> None:
        """The footprint holds custody alone; the advice duty is outside it and still listed."""
        item = row(self.bank.read(self.bank.anna), self.advice.id)
        self.assertEqual(item.bucket, "overdue")


class Departments(TestCase):
    """HOM-S9 on the service: a unit expands to its teams and the units below, with their
    active members, names who is responsible, and is the same for every reader."""

    bank: Bank
    team_owned: Obligation
    anna_owned: Obligation
    erik_owned: Obligation
    elsewhere: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = bank = Bank("mywork-departments")
        cls.team_owned = obligation("Retail compliance's")
        cls.anna_owned = obligation("Anna's")
        cls.erik_owned = obligation("Erik's")
        cls.elsewhere = obligation("Someone else's")
        bank.entry(cls.team_owned, owner_team=bank.retail_team)
        bank.entry(cls.anna_owned, first_line_owner=bank.anna)
        bank.entry(cls.erik_owned, first_line_owner=bank.erik)
        bank.entry(cls.elsewhere, first_line_owner=bank.officer)

    def test_a_department_lists_its_teams_and_their_people_and_the_units_below(self) -> None:
        page = self.bank.read(self.bank.karin, scope="unit", unit=self.bank.retail.id)
        self.assertEqual(page.scope, "unit")
        self.assertEqual(
            set(ids(page)), {self.team_owned.id, self.anna_owned.id, self.erik_owned.id}
        )
        self.assertEqual(whos(row(page, self.team_owned.id)), {("owner", "retail_compliance")})
        self.assertEqual(whos(row(page, self.anna_owned.id)), {("owner", "Anna Berg")})
        self.assertEqual(whos(row(page, self.erik_owned.id)), {("owner", "Erik Holm")})

    def test_the_view_is_a_filter_and_the_same_for_every_reader(self) -> None:
        karin = self.bank.read(self.bank.karin, scope="unit", unit=self.bank.retail.id)
        johan = self.bank.read(self.bank.johan, scope="unit", unit=self.bank.retail.id)
        self.assertEqual(karin.items, johan.items)
        self.assertEqual(
            self.bank.read(self.bank.karin).items, [], "heading a department owns nothing"
        )

    def test_a_deactivated_member_is_not_expanded_to(self) -> None:
        self.bank.activate()
        Membership.objects.filter(user=self.bank.erik).update(deactivated_at=timezone.now())
        page = self.bank.read(self.bank.karin, scope="unit", unit=self.bank.retail.id)
        self.assertNotIn(self.erik_owned.id, ids(page))

    def test_a_sub_unit_covers_only_itself_and_a_unit_with_no_team_nothing(self) -> None:
        cards = self.bank.read(self.bank.karin, scope="unit", unit=self.bank.cards_unit.id)
        self.assertEqual(ids(cards), [self.erik_owned.id])
        self.assertEqual(
            self.bank.read(self.bank.karin, scope="unit", unit=self.bank.legal.id).items, []
        )

    def test_a_unit_the_bank_does_not_have_is_not_found(self) -> None:
        other = Bank("mywork-departments-other")
        for unit in (uuid.uuid4(), other.retail.id):
            with self.subTest(unit=unit), self.assertRaises(ValidationError) as caught:
                self.bank.read(self.bank.karin, scope="unit", unit=unit)
            self.assertEqual(caught.exception.code, "not_found")


class ChangesOnYourItems(TestCase):
    """HOM-S11 on the service, with D-97: confirmed links, a person's or an independent
    agent's, and new versions within the window; never a suggestion, never one's own act."""

    bank: Bank
    confirmer: Any
    duty: Obligation
    versioned: Obligation
    self_approved: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.confirmer = agent_build.agent_key(agent_row=agent_build.agent(kind=AgentKind.REVIEW))
        cls.bank = bank = Bank("mywork-aware")
        cls.duty = obligation("Linked duty")
        bank.entry(cls.duty, first_line_owner=bank.anna)
        cls.versioned = obligation(
            "Amended duty", versions=[(None, {"en": "Before."}), (None, {"en": "After."})]
        )
        bank.entry(cls.versioned, first_line_owner=bank.anna)
        cls.self_approved = obligation("Amended by Anna")
        bank.entry(cls.self_approved, first_line_owner=bank.anna)
        with library_write("test fixture"):
            ObligationVersion.objects.create(
                obligation=cls.self_approved, version_number=2, approved_by=bank.anna
            )

    def linked_case(
        self, *, key_date: datetime.date | None = None
    ) -> tuple[RegulatoryChange, ChangeCase]:
        change = watch_build.change(title="A reform", key_date=key_date)
        watch_build.obligation_link(change, self.duty)
        return change, cases_build.case(self.bank.tenant, change)

    def confirm(self, change: RegulatoryChange, **confirmer: Any) -> None:
        with watch_write("test fixture"):
            ChangeObligation.objects.filter(change=change).update(
                confirmed_at=timezone.now(), **confirmer
            )

    def aware(self, user: User | None = None, **read: Any) -> list[uuid.UUID]:
        return ids(self.bank.read(user or self.bank.anna, bucket="aware", **read))

    def test_a_suggestion_nobody_confirmed_never_counts(self) -> None:
        change, _case = self.linked_case()
        self.assertNotIn(change.id, self.aware())
        self.assertEqual(row(self.bank.read(self.bank.anna), self.duty.id).open_change_count, 0)

    def test_a_person_confirmed_link_lists_the_case_naming_the_obligation(self) -> None:
        change, case = self.linked_case()
        self.confirm(change, confirmed_by=self.bank.officer)
        page = self.bank.read(self.bank.anna)
        item = row(page, change.id)
        self.assertEqual(item.item_kind, "change_case")
        self.assertEqual(
            pick(item, "bucket", "kind", "date"), ("aware", "linked", self.bank.today())
        )
        self.assertEqual(
            [
                (
                    r["reason"],
                    r["who"]["person"]["name"],
                    r["via"]["obligation_id"],
                    r["via"]["title"],
                )
                for r in item.model_dump()["reasons"]
            ],
            [("owner", "Anna Berg", self.duty.id, "Linked duty")],
        )
        self.assertEqual(facts(item)["urgency"], case.urgency.key)
        self.assertEqual(row(page, self.duty.id).open_change_count, 1)

    def test_an_independent_agent_confirmation_counts(self) -> None:
        change, _case = self.linked_case()
        self.confirm(
            change,
            confirmed_by_api_key_id=self.confirmer.id,
            confirmed_by_agent_id=self.confirmer.agent.id,
        )
        self.assertIn(change.id, self.aware())

    def test_the_caller_own_confirmation_is_left_out_but_still_counted(self) -> None:
        change, _case = self.linked_case()
        self.confirm(change, confirmed_by=self.bank.anna)
        self.assertNotIn(change.id, self.aware())
        self.assertEqual(row(self.bank.read(self.bank.anna), self.duty.id).open_change_count, 1)

    def test_a_finished_case_is_not_a_change_on_your_items(self) -> None:
        change, case = self.linked_case()
        self.confirm(change, confirmed_by=self.bank.officer)
        # With the reason the database's CHECK demands of a dismissed case (c9-case-models).
        cases_build.in_category(case, CaseStatusCategory.DISMISSED)
        self.assertNotIn(change.id, ids(self.bank.read(self.bank.anna)))
        self.assertEqual(row(self.bank.read(self.bank.anna), self.duty.id).open_change_count, 0)

    def test_a_key_date_ahead_makes_the_case_due_soon_and_one_behind_does_not_make_it_overdue(
        self,
    ) -> None:
        today = self.bank.today()
        ahead, _case = self.linked_case(key_date=today + 10 * DAY)
        self.confirm(ahead, confirmed_by=self.bank.officer)
        item = row(self.bank.read(self.bank.anna), ahead.id)
        self.assertEqual(
            pick(item, "bucket", "kind", "date"),
            ("due_soon", "key_date", today + 10 * DAY),
        )
        passed, _case = self.linked_case(key_date=today - 10 * DAY)
        self.confirm(passed, confirmed_by=self.bank.officer)
        self.assertEqual(row(self.bank.read(self.bank.anna), passed.id).bucket, "aware")

    def test_a_new_version_stays_for_the_window_and_the_caller_own_never_does(self) -> None:
        self.assertIn(self.versioned.id, self.aware())
        item = row(self.bank.read(self.bank.anna), self.versioned.id)
        self.assertEqual(pick(item, "kind", "date"), ("version_applied", self.bank.today()))
        self.assertNotIn(self.self_approved.id, self.aware(), "Anna approved it herself")
        self.assertNotIn(self.duty.id, self.aware(), "a first version is not a change")
        later = timezone.now() + 15 * DAY
        self.assertNotIn(self.versioned.id, self.aware(at=later))
        self.assertEqual(
            row(self.bank.read(self.bank.anna, at=later), self.versioned.id).bucket, "open"
        )

    @override_settings(MY_WORK_AWARE_DAYS=30)
    def test_the_window_is_the_setting(self) -> None:
        self.assertIn(self.versioned.id, self.aware(at=timezone.now() + 15 * DAY))


class Isolation(TestCase):
    """Another bank's register never reaches this one's My work, even for a person who is a
    member of both: row-level security, not a filter in Python."""

    a: Bank
    b: Bank
    mine: Obligation
    theirs: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.a = Bank("mywork-iso-a")
        cls.b = Bank("mywork-iso-b")
        factories.member(cls.b.tenant, user_row=cls.a.anna)
        cls.mine = obligation("In bank A")
        cls.theirs = obligation("In bank B")
        cls.a.entry(cls.mine, first_line_owner=cls.a.anna)
        cls.b.entry(cls.theirs, first_line_owner=cls.a.anna)

    def test_each_bank_lists_only_its_own_rows(self) -> None:
        self.assertEqual(ids(self.a.read(self.a.anna)), [self.mine.id])
        self.assertEqual(ids(self.b.read(self.a.anna)), [self.theirs.id])


class QueryCount(TestCase):
    """The service asks the same number of questions for one row and for many (HOM-S12)."""

    bank: Bank

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.bank = Bank("mywork-queries")

    def add(self, count: int) -> None:
        bank, today = self.bank, self.bank.today()
        for n in range(count):
            duty = obligation(
                f"Duty {n}", versions=[(None, {"en": "One."}), (None, {"en": "Two."})]
            )
            entry = bank.entry(
                duty,
                owner_team=bank.retail_team,
                next_review_date=today + n * DAY,
                compliance_status=bank.compliant,
            )
            bank.scope(entry, bank.fund_ab, owner=bank.anna, next_review_date=today - n * DAY)
            bank.gap(entry, owner=bank.anna, target_date=today, org_unit=bank.bank_ab)
            bank.internal_item(f"Policy {next(_keys)}", owner_user=bank.anna, next_review_on=today)
            change = watch_build.change(
                title=f"Reform {n}", key_date=today + DAY, urgency="monitor" if n % 2 else "act_now"
            )
            watch_build.obligation_link(change, duty)
            with watch_write("test fixture"):
                ChangeObligation.objects.filter(change=change).update(
                    confirmed_by=bank.officer, confirmed_at=timezone.now()
                )
            cases_build.case(bank.tenant, change)

    def queries(self, **query: Any) -> int:
        """Every row on one page, so each kind's name lookups run; a page without a kind
        skips its lookups, which only ever lowers the count."""
        with CaptureQueriesContext(connection) as captured:
            self.bank.read(self.bank.anna, limit=100, **query)
        return len(captured.captured_queries)

    def test_the_count_does_not_grow_with_the_rows(self) -> None:
        self.add(1)
        one, one_unit = self.queries(), self.queries(scope="unit", unit=self.bank.retail.id)
        self.add(12)
        self.assertEqual(self.queries(), one)
        self.assertEqual(self.queries(scope="unit", unit=self.bank.retail.id), one_unit)
        self.assertEqual(self.bank.read(self.bank.anna).total, 13 * 3)
