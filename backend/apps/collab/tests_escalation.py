"""Escalation of overdue actions to the head of the owner's department, once (COL-02, D-21,
CHUNK10_TASKS ruling 7; `c10-reminders-escalation-reviews`).

What these pin:

- **Threshold.** An open action overdue by the bank's `escalate_after_days` escalates; one a
  day short does not, and nor does a done or removed action.
- **Who.** The head of the department of the owner's team, every active holder of the
  bank's `escalate_to_role` and the owner, each once. With no department, or a department
  without a head, the role holders and the owner alone, and the audit row says the head was
  missing.
- **Never muted.** A person who switched reminders off still receives the escalation, and
  an away head's escalation reaches their delegate.
- **Once.** A second run, and the days after, escalate nobody.
- **No tenant text.** The mail and the audit row name the change, the owner, the date and the
  days overdue, never the action's own title.

Every date is the bank's local today plus an offset, at the send hour (CHUNK10_TASKS rule 14).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import Action
from apps.collab import tasks
from apps.collab.escalation import ESCALATED
from apps.collab.models import Notification
from apps.collab.tests_reminders import HELSINKI, at, frozen
from apps.identity.models import Membership, TenantRole, User
from apps.library.reading import today_for
from apps.shared import factories, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import AuditEvent, Tenant
from apps.taxonomy.models import Team
from apps.tenants.models import OrgUnit, OrgUnitKind
from apps.watch import testing as watch_build


class EscalationTestCase(TestCase):
    """Anna owns the action and is in "Legal", whose department is headed by Helena; Olof
    and Oskar are compliance officers, the bank's escalation role."""

    tenant: Tenant
    anchor: datetime.date
    anna: User
    helena: User
    olof: User
    oskar: User
    reader: User
    legal: Team
    department: OrgUnit

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="escalation", timezone=HELSINKI)
        Tenant.objects.filter(pk=cls.tenant.pk).update(escalate_after_days=5, escalate_to_role="compliance_officer")
        cls.anchor = today_for(cls.tenant)
        cls.anna = factories.member_user(cls.tenant, roles=("contributor",))
        cls.helena = factories.member_user(cls.tenant, roles=("reader",))
        cls.olof = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.oskar = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        tenancy.activate(cls.tenant.id)
        cls.department = OrgUnit.objects.create(
            tenant=cls.tenant, kind=OrgUnitKind.FUNCTION.value, name="Legal and Compliance", head_user=cls.helena
        )
        cls.legal = Team.objects.create(tenant=cls.tenant, key="legal", org_unit=cls.department)
        factories.team_member(cls.tenant, cls.legal, cls.anna)

    def setUp(self) -> None:
        MockMailer.reset()
        self.addCleanup(MockMailer.reset)
        tenancy.activate(self.tenant.id)

    def day(self, offset: int) -> datetime.date:
        return self.anchor + datetime.timedelta(days=offset)

    def action(self, due_offset: int, *, owner: User | None = None) -> Action:
        case = cases_build.case(self.tenant, watch_build.change(title=f"FI amends rule {Action.objects.count()}"))
        return factories.action(case, owner or self.anna, due_date=self.day(due_offset), title="Rewrite the custody memo")

    def run_on(self, offset: int) -> None:
        with frozen(at(self.day(offset), settings.REMINDER_SEND_HOUR)):
            tasks.send_tenant_escalations(str(self.tenant.id))
        tenancy.activate(self.tenant.id)

    def escalated(self, action: Action) -> list[tuple[Any, Any]]:
        tenancy.activate(self.tenant.id)
        return sorted(
            (row.user_id, row.on_behalf_of_id)
            for row in Notification.objects.filter(subject_id=action.id, kind="escalation")
        )

    def audit(self, action: Action) -> list[AuditEvent]:
        return list(AuditEvent.objects.filter(action=ESCALATED, subject_id=action.id))

    def everyone(self) -> list[tuple[Any, Any]]:
        return sorted((person.id, None) for person in (self.anna, self.helena, self.olof, self.oskar))


class Threshold(EscalationTestCase):
    def test_an_action_five_days_overdue_escalates_to_the_head_the_officers_and_the_owner_once_each(self) -> None:
        action = self.action(-5)
        self.run_on(0)
        self.assertEqual(self.escalated(action), self.everyone())
        self.assertEqual(sorted(mailed.to for mailed in MockMailer.sent), sorted(p.email for p in (self.anna, self.helena, self.olof, self.oskar)))
        self.assertTrue(all(row.emailed_at for row in Notification.objects.filter(subject_id=action.id)))
        [event] = self.audit(action)
        self.assertEqual(event.after["departmentHeadIds"], [str(self.helena.id)])
        self.assertFalse(event.after["departmentHeadMissing"])
        self.assertEqual(event.after["daysOverdue"], 5)

    def test_an_action_a_day_short_of_the_threshold_does_not_escalate(self) -> None:
        action = self.action(-4)
        self.run_on(0)
        self.assertEqual(self.escalated(action), [])
        self.assertEqual(self.audit(action), [])

    def test_the_threshold_is_the_banks_own(self) -> None:
        Tenant.objects.filter(pk=self.tenant.pk).update(escalate_after_days=2)
        action = self.action(-2)
        self.run_on(0)
        self.assertEqual(self.escalated(action), self.everyone())

    def test_a_done_or_removed_action_never_escalates(self) -> None:
        done = self.action(-9)
        removed = self.action(-9)
        Action.objects.filter(pk=done.pk).update(done_at=timezone.now(), done_by=self.anna)
        Action.objects.filter(pk=removed.pk).update(removed_at=timezone.now(), removed_by=self.anna)
        self.run_on(0)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action=ESCALATED).exists())


class Once(EscalationTestCase):
    def test_a_second_run_and_the_three_days_after_escalate_nobody(self) -> None:
        action = self.action(-5)
        for offset in (0, 0, 1, 2, 3):
            self.run_on(offset)
        self.assertEqual(self.escalated(action), self.everyone())
        self.assertEqual(len(MockMailer.sent), 4)
        self.assertEqual(len(self.audit(action)), 1)

    def test_an_escalation_that_found_nobody_to_tell_is_not_retried(self) -> None:
        Membership.objects.filter(tenant=self.tenant).update(deactivated_at=timezone.now())
        action = self.action(-5)
        self.run_on(0)
        Membership.objects.filter(tenant=self.tenant).update(deactivated_at=None)
        self.run_on(1)
        self.assertEqual(self.escalated(action), [])
        self.assertEqual(len(self.audit(action)), 1)
        self.assertEqual(self.audit(action)[0].after["recipientIds"], [])


class MissingHead(EscalationTestCase):
    def assert_role_holders_alone(self, action: Action) -> None:
        self.run_on(0)
        self.assertEqual(self.escalated(action), sorted((p.id, None) for p in (self.anna, self.olof, self.oskar)))
        [event] = self.audit(action)
        self.assertTrue(event.after["departmentHeadMissing"])
        self.assertEqual(event.after["departmentHeadIds"], [])

    def test_a_team_with_no_department_escalates_to_the_role_holders_and_records_the_missing_head(self) -> None:
        Team.objects.filter(pk=self.legal.pk).update(org_unit=None)
        self.assert_role_holders_alone(self.action(-5))

    def test_a_department_with_no_head_does_the_same(self) -> None:
        OrgUnit.objects.filter(pk=self.department.pk).update(head_user=None)
        self.assert_role_holders_alone(self.action(-5))

    def test_an_owner_in_no_team_does_the_same(self) -> None:
        loner = factories.member_user(self.tenant, roles=("contributor",))
        action = self.action(-5, owner=loner)
        self.run_on(0)
        self.assertEqual(self.escalated(action), sorted((p.id, None) for p in (loner, self.olof, self.oskar)))
        [event] = self.audit(action)
        self.assertTrue(event.after["departmentHeadMissing"])

    def test_the_escalation_role_is_the_banks_own_key(self) -> None:
        self.assertTrue(TenantRole.objects.filter(tenant=self.tenant, key="reader").exists())
        Tenant.objects.filter(pk=self.tenant.pk).update(escalate_to_role="reader")
        action = self.action(-5)
        self.run_on(0)
        self.assertEqual(self.escalated(action), sorted((p.id, None) for p in (self.anna, self.helena, self.reader)))


class NeverMuted(EscalationTestCase):
    def test_a_person_who_muted_reminders_still_receives_the_escalation(self) -> None:
        Membership.objects.filter(user=self.anna).update(notification_prefs={"reminders": False})
        action = self.action(-5)
        self.run_on(0)
        self.assertIn((self.anna.id, None), self.escalated(action))
        self.assertIn(self.anna.email, {mailed.to for mailed in MockMailer.sent})

    def test_an_away_heads_escalation_reaches_their_delegate(self) -> None:
        Membership.objects.filter(user=self.helena).update(out_of_office_until=self.day(3), delegate=self.reader)
        action = self.action(-5)
        self.run_on(0)
        self.assertEqual(
            self.escalated(action),
            sorted([(self.anna.id, None), (self.reader.id, self.helena.id), (self.olof.id, None), (self.oskar.id, None)]),
        )


class NoTenantText(EscalationTestCase):
    def test_the_mail_names_the_change_the_owner_and_the_days_and_never_the_actions_own_title(self) -> None:
        action = self.action(-6)
        self.run_on(0)
        change = action.case.change
        for mailed in MockMailer.sent:
            self.assertEqual(mailed.subject, f"Escalated to you: {change.title}")
            self.assertIn(f"owned by {self.anna.name}", mailed.body)
            self.assertIn(f"was due on {self.day(-6).isoformat()}", mailed.body)
            self.assertIn("Days overdue: 6", mailed.body)
            self.assertIn(f"{settings.APP_BASE_URL.rstrip('/')}/watch/{change.id}", mailed.body)
            self.assertNotIn(action.title, mailed.body)
        [event] = self.audit(action)
        self.assertNotIn(action.title, str(event.after))
        self.assertNotIn(action.title, event.summary)
        self.assertEqual({row.title for row in Notification.objects.filter(subject_id=action.id)}, {change.title})
