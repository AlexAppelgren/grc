"""Support access grants (TEN-06, D-49, ADR 0042): requested by the platform, decided by the
bank, time-boxed, and guarded in the database. Entering a bank under a grant is
`c8-support-access-mechanism`'s and proven there.

Operations exercised (the audit-on-write guard reads these names): requestConsoleSupportAccess,
approveSupportAccess, declineSupportAccess, revokeSupportAccess.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.identity.models import Membership, TenantRole, User
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.tenants import logic
from apps.tenants.models import SupportAccess, SupportAccessLevel, SupportAccessStatus

PURPOSE = "The bank reports that its watch feed stopped updating on Monday."


class SupportGrantCase(ScenarioTestCase):
    def setUp(self) -> None:
        MockMailer.reset()
        self.tenant = factories.tenant(slug="bank")
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.reader = factories.member(self.tenant, roles=("reader",)).user
        self.platform = factories.platform_user()

    def request_grant(self, hours: int = 2, headers: dict[str, Any] | None = None, **extra: Any) -> Any:
        headers = headers or sign_in(self.platform, tenant=None)
        return self.client.post(
            f"/api/v1/console/tenants/{self.tenant.id}/support-access",
            data={"purpose": PURPOSE, "ticketRef": "SUP-2511", "hours": hours, **extra},
            content_type="application/json",
            **headers,
        )

    def pending(self) -> uuid.UUID:
        response = self.request_grant()
        self.assertEqual(response.status_code, 201, response.content)
        return uuid.UUID(response.json()["id"])

    def decide(self, grant_id: uuid.UUID, verb: str, user: User | None = None, *, step_up: bool = False) -> Any:
        headers = sign_in(user or self.admin, tenant=self.tenant, step_up=step_up)
        return self.client.post(f"/api/v1/tenant/support-access/{grant_id}/{verb}", **headers)

    def grant(self, grant_id: uuid.UUID) -> SupportAccess:
        self.activate(self.tenant)
        return SupportAccess.objects.get(pk=grant_id)

    def age(self, grant_id: uuid.UUID, **columns: Any) -> None:
        """Move a row's clock columns into the past, as the schema owner's hatch would: the
        guard trigger freezes them for everyone else."""
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SET LOCAL cw.maintenance = 'on'")
            self.activate(self.tenant)
            SupportAccess.objects.filter(pk=grant_id).update(**columns)
            cursor.execute("SET LOCAL cw.maintenance = 'off'")


class Request(SupportGrantCase):
    def test_the_request_writes_the_grant_and_one_audit_row_and_nothing_else(self) -> None:
        headers = sign_in(self.platform, tenant=None)
        self.activate(self.tenant)
        before = (SupportAccess.objects.count(), AuditEvent.objects.count(), OutboxEvent.objects.count(), Membership.objects.count())
        response = self.request_grant(headers=headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.activate(self.tenant)
        after = (SupportAccess.objects.count(), AuditEvent.objects.count(), OutboxEvent.objects.count(), Membership.objects.count())
        # record() writes the audit row and its outbox row as one; nothing else moves.
        self.assertEqual([b - a for a, b in zip(before, after, strict=True)], [1, 1, 1, 0])
        body = response.json()
        self.assertEqual((body["state"], body["hours"], body["purpose"], body["ticketRef"]), ("pending", 2, PURPOSE, "SUP-2511"))
        self.assertEqual((body["tenantId"], body["tenantName"]), (str(self.tenant.id), self.tenant.name))
        self.assertIsNone(body["endsAt"])
        grant = self.grant(uuid.UUID(body["id"]))
        self.assertEqual(grant.access_level, SupportAccessLevel.READ.value)
        self.assertEqual(grant.status, SupportAccessStatus.REQUESTED.value)
        self.assertIsNone(grant.started_at)
        assert grant.request_expires_at is not None
        self.assertEqual(grant.request_expires_at - grant.requested_at, datetime.timedelta(hours=settings.SUPPORT_ACCESS_REQUEST_TTL_HOURS))
        event = AuditEvent.objects.get(action="support_access.requested", subject_id=grant.id)
        self.assertEqual((event.tenant_id, event.actor_id), (self.tenant.id, self.platform.id))

    def test_only_the_banks_security_manage_holders_are_mailed(self) -> None:
        self.activate(self.tenant)
        TenantRole.objects.create(tenant=self.tenant, key="security-only", permissions=[perms.SECURITY_MANAGE])
        security = factories.member(self.tenant, roles=("security-only",)).user
        gone = factories.member(self.tenant, roles=("admin",))
        Membership.objects.filter(pk=gone.pk).update(deactivated_at=timezone.now())
        elsewhere = factories.member(factories.tenant(slug="other-bank"), roles=("admin",)).user
        self.request_grant()
        recipients = sorted(mail.to for mail in MockMailer.sent)
        self.assertEqual(recipients, sorted([self.admin.email, security.email]))
        self.assertNotIn(elsewhere.email, recipients)
        self.assertIn(PURPOSE, MockMailer.sent[0].body)

    def test_the_window_is_at_most_the_maximum(self) -> None:
        self.assertEqual(self.request_grant(hours=settings.SUPPORT_ACCESS_MAX_HOURS).status_code, 201)
        over = self.request_grant(hours=settings.SUPPORT_ACCESS_MAX_HOURS + 1)
        self.assertEqual(over.status_code, 422)
        self.assertEqual(over.json()["code"], "validation_error")

    def test_a_purpose_of_only_spaces_is_refused(self) -> None:
        response = self.request_grant(purpose="   ")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    @override_settings(SUPPORT_ACCESS_MAX_HOURS=1)
    def test_the_maximum_is_the_setting(self) -> None:
        self.assertEqual(self.request_grant(hours=2).status_code, 422)

    def test_a_write_level_request_is_refused_and_writes_nothing(self) -> None:
        response = self.request_grant(accessLevel="write")
        self.assertEqual(response.status_code, 422)
        self.activate(self.tenant)
        self.assertFalse(SupportAccess.objects.exists())

    def test_a_request_grants_nothing(self) -> None:
        """Until the bank approves, the platform person's reads of the bank answer 404."""
        self.pending()
        headers = sign_in(self.platform, tenant=None)
        for url in ("/api/v1/tenant", "/api/v1/tenant/support-access"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, **headers).status_code, 404)


class Decide(SupportGrantCase):
    def test_approval_opens_the_window_now_and_records_both_people_and_the_step_up(self) -> None:
        grant_id = self.pending()
        response = self.decide(grant_id, "approve", step_up=True)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["state"], "active")
        self.assertEqual(body["decidedBy"], {"id": str(self.admin.id), "name": self.admin.name})
        self.assertEqual(body["platformPerson"], {"id": str(self.platform.id), "name": self.platform.name})
        grant = self.grant(grant_id)
        assert grant.expires_at is not None and grant.started_at is not None
        self.assertEqual(grant.expires_at - grant.started_at, datetime.timedelta(hours=2))
        self.assertEqual(grant.approved_by_id, self.admin.id)
        event = AuditEvent.objects.get(action="support_access.approved", subject_id=grant_id)
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertEqual(event.step_up_assertion_id, grant.approved_step_up_assertion_id)
        self.assertEqual(event.actor_id, self.admin.id)
        self.assertEqual(event.after["platformUserId"], str(self.platform.id))

    def test_approval_without_a_fresh_step_up_is_refused(self) -> None:
        grant_id = self.pending()
        response = self.decide(grant_id, "approve")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")
        self.assertEqual(self.grant(grant_id).status, SupportAccessStatus.REQUESTED.value)

    def test_the_person_who_asked_never_approves(self) -> None:
        """A platform person who is also an admin of the bank still cannot let themself in."""
        factories.member(self.tenant, roles=("admin",), user_row=self.platform)
        grant_id = self.pending()
        response = self.decide(grant_id, "approve", self.platform, step_up=True)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "four_eyes_violation")
        self.assertIsNone(self.grant(grant_id).approved_by_id)

    def test_decline_and_revoke_need_no_step_up(self) -> None:
        declined = self.pending()
        response = self.decide(declined, "decline")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["state"], "declined")
        self.assertEqual(response.json()["decidedBy"]["id"], str(self.admin.id))
        revoked = self.pending()
        self.assertEqual(self.decide(revoked, "approve", step_up=True).status_code, 200)
        response = self.decide(revoked, "revoke")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["state"], "revoked")
        grant = self.grant(revoked)
        assert grant.ended_at is not None
        self.assertLess(abs(datetime.datetime.fromisoformat(response.json()["endsAt"]) - grant.ended_at), datetime.timedelta(milliseconds=1))
        self.assertTrue(AuditEvent.objects.filter(action="support_access.revoked", subject_id=revoked).exists())
        self.assertTrue(AuditEvent.objects.filter(action="support_access.declined", subject_id=declined).exists())

    def test_each_decision_needs_security_manage(self) -> None:
        grant_id = self.pending()
        for verb, step_up in (("approve", True), ("decline", False), ("revoke", False)):
            with self.subTest(verb=verb):
                response = self.decide(grant_id, verb, self.reader, step_up=step_up)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["requiredPermission"], perms.SECURITY_MANAGE)

    def test_a_decision_is_taken_once_and_in_order(self) -> None:
        grant_id = self.pending()
        self.assertEqual(self.decide(grant_id, "revoke").json()["code"], "invalid_transition")
        self.assertEqual(self.decide(grant_id, "decline").status_code, 200)
        for verb in ("approve", "decline", "revoke"):
            with self.subTest(verb=verb):
                response = self.decide(grant_id, verb, step_up=True)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "invalid_transition")

    def test_a_request_nobody_decides_lapses_and_cannot_be_approved(self) -> None:
        grant_id = self.pending()
        self.age(grant_id, request_expires_at=timezone.now() - datetime.timedelta(seconds=1))
        response = self.decide(grant_id, "approve", step_up=True)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "invalid_transition")
        self.assertEqual(self.decide(grant_id, "decline").status_code, 422)
        listed = self.client.get("/api/v1/tenant/support-access", **sign_in(self.reader, tenant=self.tenant)).json()
        self.assertEqual([item["state"] for item in listed["items"]], ["lapsed"])

    def test_a_window_that_passed_reads_as_ended_and_cannot_be_revoked(self) -> None:
        grant_id = self.pending()
        self.decide(grant_id, "approve", step_up=True)
        self.age(grant_id, expires_at=timezone.now() - datetime.timedelta(seconds=1))
        self.assertEqual(self.decide(grant_id, "revoke").json()["code"], "invalid_transition")
        listed = self.client.get("/api/v1/tenant/support-access", **sign_in(self.reader, tenant=self.tenant)).json()
        self.assertEqual(listed["items"][0]["state"], "ended")

    def test_another_banks_admin_cannot_decide(self) -> None:
        grant_id = self.pending()
        other = factories.tenant(slug="other-bank")
        stranger = factories.member(other, roles=("admin",)).user
        headers = sign_in(stranger, tenant=other, step_up=True)
        for verb in ("approve", "decline", "revoke"):
            with self.subTest(verb=verb):
                self.assertEqual(self.client.post(f"/api/v1/tenant/support-access/{grant_id}/{verb}", **headers).status_code, 404)


class TenantList(SupportGrantCase):
    def test_any_member_reads_every_request_newest_first_and_only_their_banks(self) -> None:
        older = self.pending()
        self.decide(older, "decline")
        newer = self.pending()
        other = factories.tenant(slug="other-bank")
        factories.support_access(other)
        response = self.client.get("/api/v1/tenant/support-access", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual([item["id"] for item in body["items"]], [str(newer), str(older)])
        self.assertEqual([item["state"] for item in body["items"]], ["pending", "declined"])
        self.assertEqual(body["items"][0]["purpose"], PURPOSE)
        self.assertIsNone(body["items"][0]["decidedBy"])

    def test_the_page_is_bounded(self) -> None:
        self.pending()
        self.pending()
        headers = sign_in(self.reader, tenant=self.tenant)
        page = self.client.get("/api/v1/tenant/support-access?limit=1&offset=1", **headers).json()
        self.assertEqual((len(page["items"]), page["total"]), (1, 2))


class RecoveryRowsKeepWorking(SupportGrantCase):
    """Chunk 1's one-shot last-admin recovery (ID-05, ID-S13) writes a write-level row the new
    columns must not break, and it stays the only write-level row there is."""

    def test_a_recovery_is_listed_as_one_and_can_never_be_approved(self) -> None:
        lonely = factories.member(self.tenant, roles=("reader",)).user
        with transaction.atomic():
            access = logic.console_reissue_enrolment(
                tenant_id=self.tenant.id,
                user_id=lonely.id,
                platform_user=self.platform,
                actor=Actor(kind=ActorType.USER, id=self.platform.id, label=self.platform.name),
                reason="The only administrator lost her passkey.",
                ticket_ref="SUP-1",
                out_of_band_check="Called the bank's switchboard.",
                request=None,
                step_up_assertion_id=None,
            )
        grant = self.grant(access.id)
        self.assertEqual((grant.access_level, grant.status, grant.hours), (SupportAccessLevel.WRITE.value, SupportAccessStatus.EXPIRED.value, 0))
        self.assertEqual(grant.started_at, grant.ended_at)
        listed = self.client.get("/api/v1/tenant/support-access", **sign_in(self.reader, tenant=self.tenant)).json()
        self.assertEqual([item["state"] for item in listed["items"]], ["recovery"])
        self.assertEqual(self.decide(access.id, "approve", step_up=True).json()["code"], "invalid_transition")
        self.activate(self.tenant)
        self.assertFalse(SupportAccess.objects.filter(access_level=SupportAccessLevel.WRITE.value, approved_by__isnull=False).exists())

    def test_the_database_refuses_an_approved_write_level_row(self) -> None:
        self.activate(self.tenant)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SupportAccess.objects.create(
                tenant=self.tenant, platform_user=self.platform, reason="x", access_level=SupportAccessLevel.WRITE.value, approved_by=self.admin
            )


class TheDatabaseGuardsTheGrant(TransactionTestCase):
    """At the database, as the app role production runs as (cw_app), on committed rows."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="guarded")
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.platform = factories.platform_user()
        factories.member(self.tenant, roles=("reader",), user_row=self.platform)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant.id, using="app")
            self.grant = SupportAccess.objects.using("app").create(
                tenant=self.tenant,
                platform_user=self.platform,
                reason=PURPOSE,
                status=SupportAccessStatus.REQUESTED.value,
                hours=2,
                request_expires_at=timezone.now() + datetime.timedelta(hours=1),
            )

    def _as_app(self, statement: str, params: list[Any], *, hatch: bool = False) -> None:
        with connections["app"].cursor() as cursor, transaction.atomic(using="app"):
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone(), ("cw_app",))
            tenancy.activate(self.tenant.id, using="app")
            if hatch:
                cursor.execute("SET LOCAL cw.maintenance = 'on'")
            cursor.execute(statement, params)

    def test_the_approver_is_never_the_platform_person(self) -> None:
        with self.assertRaisesMessage(IntegrityError, "support_access_approver_is_not_the_requester"):
            self._as_app("UPDATE support_access SET approved_by_id = platform_user_id WHERE id = %s", [str(self.grant.id)])

    def test_the_approver_is_a_member_of_the_same_bank(self) -> None:
        stranger = factories.member(factories.tenant(slug="stranger"), roles=("admin",)).user
        with self.assertRaisesMessage(IntegrityError, "support_access_approved_by_id_same_tenant"):
            self._as_app("UPDATE support_access SET approved_by_id = %s WHERE id = %s", [str(stranger.id), str(self.grant.id)])

    def test_a_delete_and_every_frozen_column_are_refused_even_with_the_hatch(self) -> None:
        other = factories.platform_user()
        statements = [
            ("DELETE FROM support_access WHERE id = %s", []),
            ("UPDATE support_access SET tenant_id = %s WHERE id = %s", [str(factories.tenant(slug="elsewhere").id)]),
            ("UPDATE support_access SET platform_user_id = %s WHERE id = %s", [str(other.id)]),
            ("UPDATE support_access SET reason = 'rewritten' WHERE id = %s", []),
            ("UPDATE support_access SET ticket_ref = 'SUP-0' WHERE id = %s", []),
            ("UPDATE support_access SET access_level = 'write' WHERE id = %s", []),
            ("UPDATE support_access SET hours = 4 WHERE id = %s", []),
            ("UPDATE support_access SET requested_at = now() - interval '1 day' WHERE id = %s", []),
            ("UPDATE support_access SET request_expires_at = now() + interval '1 day' WHERE id = %s", []),
        ]
        for statement, params in statements:
            refusal = "never deleted" if statement.startswith("DELETE") else "never change"
            for hatch in (False, True):
                with self.subTest(statement=statement, hatch=hatch), self.assertRaisesMessage(DatabaseError, refusal):
                    self._as_app(statement, [*params, str(self.grant.id)], hatch=hatch)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant.id, using="app")
            self.assertEqual(SupportAccess.objects.using("app").get(pk=self.grant.id).reason, PURPOSE)

    def test_a_decision_moves_once(self) -> None:
        self._as_app(
            "UPDATE support_access SET status = 'approved', approved_by_id = %s, started_at = now(), expires_at = now() + interval '2 hours' WHERE id = %s",
            [str(self.admin.id), str(self.grant.id)],
        )
        with self.assertRaisesMessage(DatabaseError, "never rewritten"):
            self._as_app("UPDATE support_access SET expires_at = now() + interval '9 hours' WHERE id = %s", [str(self.grant.id)])
        self._as_app(
            "UPDATE support_access SET status = 'revoked', ended_at = now(), ended_by_id = %s WHERE id = %s",
            [str(self.admin.id), str(self.grant.id)],
        )
        with self.assertRaisesMessage(DatabaseError, "never rewritten"):
            self._as_app("UPDATE support_access SET ended_at = now() + interval '1 hour' WHERE id = %s", [str(self.grant.id)])

    def test_the_own_grants_policy_reads_nothing_while_its_setting_is_unset(self) -> None:
        with connections["app"].cursor() as cursor, transaction.atomic(using="app"):
            cursor.execute("SELECT count(*) FROM support_access")
            self.assertEqual(cursor.fetchone(), (0,))
            cursor.execute("SELECT set_config('app.platform_user_id', '', true)")
            cursor.execute("SELECT count(*) FROM support_access")
            self.assertEqual(cursor.fetchone(), (0,))

    def test_the_own_grants_policy_reads_the_persons_own_rows_and_writes_nothing(self) -> None:
        elsewhere = factories.tenant(slug="elsewhere")
        with transaction.atomic(using="app"):
            tenancy.activate(elsewhere.id, using="app")
            SupportAccess.objects.using("app").create(tenant=elsewhere, platform_user=factories.platform_user(), reason="Another person's.")
        with connections["app"].cursor() as cursor, transaction.atomic(using="app"):
            cursor.execute("SELECT set_config('app.platform_user_id', %s, true)", [str(self.platform.id)])
            cursor.execute("SELECT id FROM support_access")
            self.assertEqual(cursor.fetchall(), [(self.grant.id,)])
            cursor.execute("UPDATE support_access SET status = 'declined' WHERE id = %s", [str(self.grant.id)])
            self.assertEqual(cursor.rowcount, 0)
