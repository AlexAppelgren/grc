"""The delegation hop in `notify()` (TEN-04, COL-02; CHUNK10_TASKS `c10-delegation`).

What these pin, each on its own:

- **Work follows an away person to their delegate.** A reminder, an escalation, an
  assignment or a sign-off request for someone away through the bank's local today goes to
  their delegate, with `on_behalf_of` naming them, and the absent person gets no row.
- **Everything else stays.** A mention, and every other kind, reaches the absent person.
- **The delegate passes the same check.** A delegate who is deactivated, cannot read the
  subject or is not a member of the bank is skipped, and the absent person keeps the
  notice, so nothing is dropped silently.
- **One hop.** A chain writes one row, for the first delegate; a cycle ends.
- **Nothing is granted.** A delegate told about a case still gets 403 on a write their
  own roles lack.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db import transaction
from django.test import TestCase

from apps.cases import testing as cases_build
from apps.collab import logic
from apps.collab.models import Notification, NotificationKind
from apps.identity.models import Membership, TenantRole, User
from apps.library.reading import today_for
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build

V1 = "/api/v1"


class DelegationTestCase(TestCase):
    tenant: Tenant
    other: Tenant
    anna: User
    erik: User
    karin: User
    case: Any

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="delegation", timezone="Europe/Helsinki")
        cls.other = factories.tenant(slug="delegation-other")
        cls.anna = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.erik = factories.member_user(cls.tenant, roles=("reader",))
        cls.karin = factories.member_user(cls.tenant, roles=("reader",))
        cls.case = cases_build.case(cls.tenant, watch_build.change(title="FI amends the custody rules"))

    def setUp(self) -> None:
        tenancy.activate(self.tenant.id)

    @property
    def today(self) -> datetime.date:
        return today_for(self.tenant)

    def away(self, person: User, delegate: User | None, *, until: datetime.date | None = None) -> None:
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(tenant=self.tenant, user=person).update(
            out_of_office_until=self.today if until is None else until, delegate=delegate
        )

    def notify(self, kind: NotificationKind, *people: User) -> list[tuple[Any, Any]]:
        tenancy.activate(self.tenant.id)
        rows = logic.notify(
            tenant_id=self.tenant.id,
            kind=kind,
            subject_type="change_case",
            subject_id=self.case.id,
            candidates=[(person.id, "owner") for person in people],
        )
        return sorted((row.user_id, row.on_behalf_of_id) for row in rows)


class WorkFollowsTheAwayPerson(DelegationTestCase):
    def test_each_delegated_kind_reaches_the_delegate_on_behalf_of_the_absent_person(self) -> None:
        self.away(self.anna, self.erik)
        for kind in logic.DELEGATED_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self.notify(kind, self.anna), [(self.erik.id, self.anna.id)])
        self.assertFalse(Notification.objects.filter(user=self.anna).exists())

    def test_the_hop_covers_reminders_escalation_assignment_and_signoff_and_nothing_else(self) -> None:
        self.assertEqual(
            logic.DELEGATED_KINDS,
            {"due_soon", "overdue", "review_due", "escalation", "assigned", "signoff_requested"},
        )

    def test_every_other_kind_stays_with_the_absent_person(self) -> None:
        """A mention is addressed to a human being; a digest is that person's own list."""
        self.away(self.anna, self.erik)
        for kind in set(NotificationKind) - logic.DELEGATED_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self.notify(kind, self.anna), [(self.anna.id, None)])
        self.assertFalse(Notification.objects.filter(user=self.erik).exists())

    def test_the_window_is_the_banks_local_today_inclusive(self) -> None:
        self.away(self.anna, self.erik, until=self.today - datetime.timedelta(days=1))
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.anna.id, None)])
        self.away(self.anna, self.erik, until=self.today)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.erik.id, self.anna.id)])

    def test_away_with_no_delegate_keeps_the_notice(self) -> None:
        self.away(self.anna, None)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.anna.id, None)])

    def test_the_absent_persons_muted_reminders_send_nothing_to_anybody(self) -> None:
        self.away(self.anna, self.erik)
        Membership.objects.filter(tenant=self.tenant, user=self.anna).update(notification_prefs={"reminders": False})
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [])

    def test_a_delegate_told_on_their_own_account_gets_one_row_without_the_stamp(self) -> None:
        self.away(self.anna, self.erik)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna, self.erik), [(self.erik.id, None)])

    def test_the_delegates_title_is_in_the_delegates_language(self) -> None:
        self.away(self.anna, self.erik)
        tenancy.activate(self.tenant.id)
        (row,) = logic.notify(
            tenant_id=self.tenant.id,
            kind=NotificationKind.DUE_SOON,
            subject_type="change_case",
            subject_id=self.case.id,
            candidates=[(self.anna.id, "owner")],
        )
        self.assertEqual((row.user_id, row.title), (self.erik.id, "FI amends the custody rules"))


class TheDelegatePassesTheSameCheck(DelegationTestCase):
    def test_a_delegate_who_cannot_read_the_subject_is_skipped(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            TenantRole.objects.create(tenant=self.tenant, key="roadmap-only", permissions=[perms.ROADMAP_READ])
        limited = factories.member(self.tenant, roles=("roadmap-only",)).user
        self.away(self.anna, limited)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.anna.id, None)])

    def test_a_deactivated_delegate_is_skipped(self) -> None:
        from django.utils import timezone

        Membership.objects.filter(tenant=self.tenant, user=self.erik).update(deactivated_at=timezone.now())
        self.away(self.anna, self.erik)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.anna.id, None)])

    def test_a_delegate_who_is_not_a_member_of_the_bank_is_skipped(self) -> None:
        stranger = factories.member_user(self.other, roles=("compliance_officer",))
        self.away(self.anna, stranger)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.anna.id, None)])
        tenancy.activate(self.other.id)
        self.assertFalse(Notification.objects.filter(user=stranger).exists())


class OneHop(DelegationTestCase):
    def test_a_chain_writes_one_row_for_the_first_delegate(self) -> None:
        self.away(self.anna, self.erik)
        self.away(self.erik, self.karin)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.erik.id, self.anna.id)])
        self.assertFalse(Notification.objects.filter(user=self.karin).exists())

    def test_a_cycle_terminates_with_one_row_each(self) -> None:
        self.away(self.anna, self.erik)
        self.away(self.erik, self.anna)
        self.assertEqual(
            self.notify(NotificationKind.DUE_SOON, self.anna, self.erik),
            sorted([(self.erik.id, self.anna.id), (self.anna.id, self.erik.id)]),
        )

    def test_a_person_named_as_their_own_delegate_keeps_the_notice(self) -> None:
        self.away(self.anna, self.anna)
        self.assertEqual(self.notify(NotificationKind.DUE_SOON, self.anna), [(self.anna.id, None)])

    def test_two_absent_people_with_one_delegate_give_the_delegate_one_row(self) -> None:
        self.away(self.anna, self.erik)
        self.away(self.karin, self.erik)
        rows = self.notify(NotificationKind.DUE_SOON, self.anna, self.karin)
        self.assertEqual([user for user, _absent in rows], [self.erik.id])


class NothingIsGranted(DelegationTestCase):
    def test_a_delegate_still_gets_403_on_a_write_their_own_roles_lack(self) -> None:
        """Erik, a Reader, is told about Anna's case in her place; saving what the change
        means for the bank still needs cases.work, which delegation does not give him."""
        self.away(self.anna, self.erik)
        self.assertEqual(self.notify(NotificationKind.ASSIGNED, self.anna), [(self.erik.id, self.anna.id)])
        response = self.client.put(
            f"{V1}/changes/{self.case.change_id}/so-what",
            data={"text": "Our reading"},
            content_type="application/json",
            **sign_in(self.erik, tenant=self.tenant),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], perms.CASES_WORK)
