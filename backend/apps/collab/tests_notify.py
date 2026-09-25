"""`notify()`, the one writer of a notification, and the subject registry it reads (COL-02,
COL-04, D-34, CHUNK10_TASKS rulings 1 and 3).

Each part of the recipient check is its own test: one row per person per event, only for
an active member of the bank whose roles read the subject, only when the person has not
switched the kind off, and never muting an escalation. The title is the record's own title
in each recipient's language, and the log line carries ids only.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.test import TestCase
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.collab import logic, subjects
from apps.collab.models import EmailMessage, Notification, NotificationKind
from apps.identity.models import Membership, TenantRole, User, UserStatus
from apps.library import testing as library_build
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import NotInTransaction
from apps.shared.models import Tenant
from apps.watch import testing as watch_build

CHANGE_TITLE = "FI amends the rules on research payments"


def _obligation(tenant: Tenant) -> Any:
    on = library_build.instrument(key=f"inst-notify-{uuid.uuid4().hex[:8]}", regime="regime:securities")
    return library_build.obligation(
        on,
        key=f"obl-notify-{uuid.uuid4().hex[:8]}",
        titles={"en": "Assess suitability before advice", "sv": "Bedöm lämplighet före rådgivning"},
    )


def _change_case(tenant: Tenant) -> Any:
    return cases_build.case(tenant, watch_build.change(title=CHANGE_TITLE))


def _action(tenant: Tenant) -> Any:
    owner = factories.member_user(tenant, roles=("contributor",))
    return factories.action(_change_case(tenant), owner, due_date=timezone.localdate())


def _tenant_obligation(tenant: Tenant) -> Any:
    return factories.register_entry(tenant, _obligation(tenant).id)


# One builder per registered subject kind: a registry row without one fails the registry
# test, so a kind cannot be added without proving its lookup and its title.
BUILDERS: dict[str, Callable[[Tenant], Any]] = {
    "obligation": _obligation,
    "change_case": _change_case,
    "action": _action,
    "tenant_obligation": _tenant_obligation,
}


class NotifyTestCase(TestCase):
    tenant: Tenant
    other: Tenant
    anna: User
    erik: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="notify")
        cls.other = factories.tenant(slug="notify-other")
        cls.anna = factories.member_user(cls.tenant, roles=("contributor",))
        cls.erik = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        tenancy.activate(self.tenant.id)

    def notify(self, kind: NotificationKind, subject_type: str, subject_id: uuid.UUID, *people: tuple[User, str]) -> list[Notification]:
        tenancy.activate(self.tenant.id)
        return logic.notify(
            tenant_id=self.tenant.id,
            kind=kind,
            subject_type=subject_type,
            subject_id=subject_id,
            candidates=[(person.id, reason) for person, reason in people],
        )

    def set_prefs(self, user: User, prefs: dict[str, bool]) -> None:
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(tenant=self.tenant, user=user).update(notification_prefs=prefs)

    def rows_for(self, user: User) -> list[Notification]:
        tenancy.activate(self.tenant.id)
        return list(Notification.objects.filter(user=user))


class TheRecipientCheck(NotifyTestCase):
    def test_a_person_named_for_two_reasons_gets_one_row(self) -> None:
        case = _change_case(self.tenant)
        rows = self.notify(NotificationKind.ASSIGNED, "change_case", case.id, (self.anna, "owner"), (self.anna, "participant"))
        self.assertEqual([row.user_id for row in rows], [self.anna.id])
        self.assertEqual(len(self.rows_for(self.anna)), 1)

    def test_every_candidate_who_passes_gets_a_row_of_their_own(self) -> None:
        case = _change_case(self.tenant)
        rows = self.notify(NotificationKind.MENTION, "change_case", case.id, (self.anna, "mention"), (self.erik, "mention"))
        self.assertEqual({row.user_id for row in rows}, {self.anna.id, self.erik.id})
        row = self.rows_for(self.anna)[0]
        self.assertEqual((row.kind, row.subject_type, row.subject_id, row.tenant_id), ("mention", "change_case", case.id, self.tenant.id))
        self.assertIsNone(row.read_at)

    def test_a_deactivated_member_gets_nothing(self) -> None:
        case = _change_case(self.tenant)
        leaver = factories.member(self.tenant, roles=("reader",))
        Membership.objects.filter(pk=leaver.pk).update(deactivated_at=timezone.now())
        self.assertEqual(self.notify(NotificationKind.MENTION, "change_case", case.id, (leaver.user, "mention")), [])
        self.assertEqual(self.rows_for(leaver.user), [])

    def test_a_member_whose_account_is_not_active_gets_nothing(self) -> None:
        case = _change_case(self.tenant)
        person = factories.member_user(self.tenant, roles=("reader",))
        User.objects.filter(pk=person.pk).update(status=UserStatus.DEACTIVATED.value)
        self.assertEqual(self.notify(NotificationKind.MENTION, "change_case", case.id, (person, "mention")), [])

    def test_a_member_of_another_bank_gets_nothing(self) -> None:
        case = _change_case(self.tenant)
        stranger = factories.member_user(self.other, roles=("compliance_officer",))
        self.assertEqual(self.notify(NotificationKind.MENTION, "change_case", case.id, (stranger, "mention")), [])
        tenancy.activate(self.other.id)
        self.assertFalse(Notification.objects.filter(user=stranger).exists())

    def test_a_member_whose_roles_cannot_read_the_subject_gets_nothing(self) -> None:
        """Permissions, never role names: a bank's own role without `cases.read`."""
        case = _change_case(self.tenant)
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            TenantRole.objects.create(tenant=self.tenant, key="roadmap-only", permissions=[perms.ROADMAP_READ])
        limited = factories.member(self.tenant, roles=("roadmap-only",)).user
        rows = self.notify(NotificationKind.MENTION, "change_case", case.id, (limited, "mention"), (self.erik, "mention"))
        self.assertEqual([row.user_id for row in rows], [self.erik.id])

    def test_another_banks_record_is_not_found_so_nobody_is_told(self) -> None:
        """The lookup runs under row-level security: a case of the other bank names nothing."""
        foreign = _change_case(self.other)
        self.assertEqual(self.notify(NotificationKind.MENTION, "change_case", foreign.id, (self.anna, "mention")), [])

    def test_a_kind_the_registry_does_not_hold_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            self.notify(NotificationKind.MENTION, "change", uuid.uuid4(), (self.anna, "mention"))
        self.assertEqual(raised.exception.code, "unsupported_subject")

    def test_it_refuses_to_run_outside_a_transaction(self) -> None:
        # TestCase wraps each test in a transaction; check the guard's own condition.
        case = _change_case(self.tenant)
        connection = connections[DEFAULT_DB_ALIAS]
        connection.in_atomic_block = False
        try:
            with self.assertRaises(NotInTransaction):
                logic.notify(
                    tenant_id=self.tenant.id,
                    kind=NotificationKind.MENTION,
                    subject_type="change_case",
                    subject_id=case.id,
                    candidates=[(self.anna.id, "mention")],
                )
        finally:
            connection.in_atomic_block = True
        self.assertEqual(self.rows_for(self.anna), [])


class TitlesAndLogs(NotifyTestCase):
    def test_each_recipient_reads_the_record_title_in_their_own_language(self) -> None:
        obligation = _obligation(self.tenant)
        User.objects.filter(pk=self.erik.pk).update(locale=factories.language("sv"))
        self.notify(NotificationKind.MENTION, "obligation", obligation.id, (self.anna, "mention"), (self.erik, "mention"))
        self.assertEqual(self.rows_for(self.anna)[0].title, "Assess suitability before advice")
        self.assertEqual(self.rows_for(self.erik)[0].title, "Bedöm lämplighet före rådgivning")

    def test_a_case_is_titled_by_its_changes_library_title(self) -> None:
        case = _change_case(self.tenant)
        self.notify(NotificationKind.MENTION, "change_case", case.id, (self.anna, "mention"))
        self.assertEqual(self.rows_for(self.anna)[0].title, CHANGE_TITLE)

    def test_the_log_line_carries_ids_and_no_title(self) -> None:
        case = _change_case(self.tenant)
        with self.assertLogs("apps.collab.logic", level="INFO") as captured:
            self.notify(NotificationKind.MENTION, "change_case", case.id, (self.anna, "mention"))
        (entry,) = captured.records
        logged = f"{entry.getMessage()} {entry.__dict__}"
        self.assertNotIn(CHANGE_TITLE, logged)
        self.assertNotIn(self.anna.name, logged)
        self.assertEqual(entry.__dict__["recipients"], [str(self.anna.id)])
        self.assertEqual(entry.__dict__["subject_id"], str(case.id))


class Preferences(NotifyTestCase):
    def test_a_muted_kind_writes_no_row_and_queues_no_mail_for_that_person_only(self) -> None:
        case = _change_case(self.tenant)
        self.set_prefs(self.anna, {"mentions": False})
        rows = self.notify(NotificationKind.MENTION, "change_case", case.id, (self.anna, "mention"), (self.erik, "mention"))
        self.assertEqual([row.user_id for row in rows], [self.erik.id])
        self.assertEqual(self.rows_for(self.anna), [])
        self.assertFalse(EmailMessage.objects.filter(user=self.anna).exists())

    def test_each_switch_mutes_its_own_kinds_and_no_other(self) -> None:
        case = _change_case(self.tenant)
        for kind, switch in logic.MUTABLE_KINDS.items():
            with self.subTest(kind=kind):
                self.set_prefs(self.anna, {switch: False})
                self.assertEqual(self.notify(kind, "change_case", case.id, (self.anna, "owner")), [])
                self.set_prefs(self.anna, {})
                self.assertEqual(len(self.notify(kind, "change_case", case.id, (self.anna, "owner"))), 1)

    def test_an_escalation_is_never_muted(self) -> None:
        case = _change_case(self.tenant)
        self.set_prefs(
            self.anna,
            {"weeklyDigest": False, "reminders": False, "mentions": False, "assignments": False, "weeklyBriefing": False},
        )
        rows = self.notify(NotificationKind.ESCALATION, "change_case", case.id, (self.anna, "owner"))
        self.assertEqual([(row.user_id, row.kind) for row in rows], [(self.anna.id, "escalation")])

    def test_the_preference_is_read_afresh_on_every_send(self) -> None:
        case = _change_case(self.tenant)
        self.set_prefs(self.anna, {"mentions": False})
        self.assertEqual(self.notify(NotificationKind.MENTION, "change_case", case.id, (self.anna, "mention")), [])
        self.set_prefs(self.anna, {"mentions": True})
        self.assertEqual(len(self.notify(NotificationKind.MENTION, "change_case", case.id, (self.anna, "mention"))), 1)
        self.assertEqual(len(self.rows_for(self.anna)), 1, "the muted mention is not replayed")


class TheSubjectRegistry(NotifyTestCase):
    def test_every_row_has_a_bank_read_permission_a_lookup_and_a_record_title(self) -> None:
        self.assertEqual(set(subjects.SUBJECTS), set(BUILDERS), "a registry row needs a builder here that proves it")
        for kind, row in subjects.SUBJECTS.items():
            with self.subTest(kind=kind):
                self.assertIn(row.read_permission, perms.TENANT_PERMISSIONS)
                record = BUILDERS[kind](self.tenant)
                tenancy.activate(self.tenant.id)
                found = row.lookup(record.id)
                self.assertIsNotNone(found)
                self.assertIsNone(row.lookup(uuid.uuid4()))
                title = row.title(found, ["en"])
                self.assertIsInstance(title, str)
                self.assertTrue(title.strip())

    def test_a_row_missing_a_permission_lookup_or_title_cannot_be_declared(self) -> None:
        with self.assertRaises(TypeError):
            subjects.Subject(read_permission=perms.CASES_READ, lookup=lambda _id: None)  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            subjects.Subject(lookup=lambda _id: None, title=lambda _row, _order: "")  # type: ignore[call-arg]
