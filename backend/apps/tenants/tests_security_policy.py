"""The bank's session policy routes (ID-08, ADM-01): `GET` and `PUT /tenant/security-policy`.

A holder of `security.manage` reads the bank's idle and absolute session limits beside the
platform defaults and maximums, and changes them with a fresh passkey step-up. A limit above
either platform maximum is refused with `above_platform_maximum`. The write leaves one audit
row with the limits before and after and the step-up assertion, and one outbox event naming
the bank's other `security.manage` holders. The enforcement is `apps/identity/session_logic`'s
(ID-S17); this module proves the read and the write only. The credential policy (ID-07) is
out of R2 (D-100): the routes carry no passkey field.

Operations exercised: getSecurityPolicy, putSecurityPolicy.
"""

from __future__ import annotations

from typing import Any

from django.test import override_settings

from apps.identity.models import StepUpAssertion, TenantRole
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.tenants.models import SecurityPolicy

V1 = "/api/v1"
URL = f"{V1}/tenant/security-policy"


@override_settings(
    SESSION_IDLE_MINUTES_DEFAULT=30,
    SESSION_ABSOLUTE_HOURS_DEFAULT=12,
    SESSION_IDLE_MINUTES_MAX=480,
    SESSION_ABSOLUTE_HOURS_MAX=24,
)
class SecurityPolicyRoutes(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="bank-a")
        self.admin = factories.member(self.tenant, roles=("admin",)).user

    def _put(self, headers: dict[str, Any], body: dict[str, Any]) -> Any:
        return self.client.put(URL, data=body, content_type="application/json", **headers)

    def _events(self, tenant: Any = None) -> list[AuditEvent]:
        tenant = tenant or self.tenant
        self.activate(tenant)
        return list(AuditEvent.objects.filter(tenant=tenant, action="security_policy.updated").order_by("created", "id"))

    def _row(self, tenant: Any = None) -> SecurityPolicy | None:
        tenant = tenant or self.tenant
        self.activate(tenant)
        return SecurityPolicy.objects.filter(tenant=tenant).first()  # ordering: tenant is unique, at most one row

    def test_a_bank_without_a_policy_reads_the_platform_defaults_and_maximums(self) -> None:
        response = self.client.get(URL, **sign_in(self.admin, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            {
                "sessionIdleMinutes": None,
                "sessionAbsoluteHours": None,
                "sessionIdleMinutesDefault": 30,
                "sessionIdleMinutesMax": 480,
                "sessionAbsoluteHoursDefault": 12,
                "sessionAbsoluteHoursMax": 24,
                "updatedAt": None,
                "updatedBy": None,
            },
        )
        self.assertIsNone(self._row(), "a read never creates the row")

    def test_a_write_with_a_step_up_sets_the_limits_audited_with_the_assertion(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        response = self._put(headers, {"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["sessionIdleMinutes"], body["sessionAbsoluteHours"]), (15, 8))
        self.assertEqual(body["updatedBy"], {"id": str(self.admin.id), "name": self.admin.name})
        self.assertIsNotNone(body["updatedAt"])
        self.assertEqual(self.client.get(URL, **headers).json(), body)
        row = self._row()
        assert row is not None
        self.assertEqual((row.session_idle_minutes, row.session_absolute_hours, row.updated_by_id), (15, 8, self.admin.id))
        [event] = self._events()
        assertion = StepUpAssertion.objects.filter(session__user=self.admin).latest("created_at")
        self.assertEqual(
            (event.before, event.after),
            ({"sessionIdleMinutes": None, "sessionAbsoluteHours": None}, {"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8}),
        )
        self.assertEqual(event.step_up_assertion_id, assertion.id)
        self.assertEqual((event.subject_type, event.subject_id, event.actor_id), ("security_policy", self.tenant.id, self.admin.id))

    def test_a_second_write_changes_the_same_row_and_null_returns_to_the_default(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        self._put(headers, {"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8})
        response = self._put(headers, {"sessionIdleMinutes": None, "sessionAbsoluteHours": 10})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["sessionIdleMinutes"], response.json()["sessionAbsoluteHours"]), (None, 10))
        self.activate(self.tenant)
        self.assertEqual(SecurityPolicy.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(
            [(e.before, e.after) for e in self._events()][1],
            ({"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8}, {"sessionIdleMinutes": None, "sessionAbsoluteHours": 10}),
        )

    def test_the_write_tells_the_other_security_manage_holders_through_the_outbox(self) -> None:
        other_admin = factories.member(self.tenant, roles=("admin",)).user
        self.activate(self.tenant)
        TenantRole.objects.get_or_create(tenant=self.tenant, key="security-officer", defaults={"permissions": [perms.SECURITY_MANAGE]})
        officer = factories.member(self.tenant, roles=("security-officer",)).user
        departed = factories.member(self.tenant, roles=("admin",))
        departed.deactivated_at = departed.created_at
        departed.save(update_fields=["deactivated_at"])
        factories.member(self.tenant, roles=("reader",))
        self._put(sign_in(self.admin, tenant=self.tenant, step_up=True), {"sessionIdleMinutes": 20, "sessionAbsoluteHours": 8})
        [event] = self._events()
        [outbox] = OutboxEvent.objects.filter(audit_event=event)
        self.assertEqual(outbox.topic, "security_policy.updated")
        self.assertEqual(outbox.tenant_id, self.tenant.id)
        self.assertEqual(outbox.payload["subjectId"], str(self.tenant.id))
        self.assertEqual(sorted(outbox.payload["notify"]), sorted([str(other_admin.id), str(officer.id)]))

    def test_a_limit_above_either_platform_maximum_is_refused_and_nothing_changes(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        for body, field in (
            ({"sessionIdleMinutes": 481, "sessionAbsoluteHours": 8}, "sessionIdleMinutes"),
            ({"sessionIdleMinutes": 15, "sessionAbsoluteHours": 25}, "sessionAbsoluteHours"),
        ):
            response = self._put(headers, body)
            self.assertEqual((response.status_code, response.json()["code"]), (422, "above_platform_maximum"), body)
            self.assertEqual([e["field"] for e in response.json()["errors"]], [field])
        self.assertIsNone(self._row())
        self.assertEqual(self._events(), [])

    def test_the_maximum_itself_is_accepted_and_follows_the_setting(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        self.assertEqual(self._put(headers, {"sessionIdleMinutes": 480, "sessionAbsoluteHours": 24}).status_code, 200)
        with override_settings(SESSION_ABSOLUTE_HOURS_MAX=12):
            response = self._put(headers, {"sessionIdleMinutes": 480, "sessionAbsoluteHours": 13})
        self.assertEqual(response.json()["code"], "above_platform_maximum")

    def test_the_body_takes_whole_positive_limits_and_nothing_else(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        for body in (
            {"sessionIdleMinutes": 0, "sessionAbsoluteHours": 8},
            {"sessionIdleMinutes": 15, "sessionAbsoluteHours": -1},
            {"sessionIdleMinutes": "15", "sessionAbsoluteHours": 8},
            {"sessionIdleMinutes": 15},
            {"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8, "credentialPolicy": "device_bound"},
        ):
            response = self._put(headers, body)
            self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"), body)
        self.assertIsNone(self._row())

    def test_without_a_step_up_the_write_is_refused_and_nothing_changes(self) -> None:
        response = self._put(sign_in(self.admin, tenant=self.tenant), {"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8})
        self.assertEqual((response.status_code, response.json()["code"]), (403, "step_up_required"))
        self.assertIsNone(self._row())
        self.assertEqual(self._events(), [])

    def test_without_security_manage_both_routes_are_refused_naming_the_permission(self) -> None:
        self.activate(self.tenant)
        TenantRole.objects.get_or_create(tenant=self.tenant, key="members-manage", defaults={"permissions": [perms.MEMBERS_MANAGE]})
        for roles in (("reader",), ("members-manage",)):
            headers = sign_in(factories.member(self.tenant, roles=roles).user, tenant=self.tenant, step_up=True)
            for response in (self.client.get(URL, **headers), self._put(headers, {"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8})):
                self.assertEqual((response.status_code, response.json()["code"]), (403, "permission_denied"), roles)
                self.assertEqual(response.json()["requiredPermission"], perms.SECURITY_MANAGE)
        self.assertIsNone(self._row())

    def test_another_bank_never_reads_or_changes_this_banks_policy(self) -> None:
        """AC-NFR1: the route names no tenant, so bank B's admin can only ever reach B's own
        policy; A's row is invisible under B's session and B's write leaves it untouched."""
        self._put(sign_in(self.admin, tenant=self.tenant, step_up=True), {"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8})
        other = factories.tenant(slug="bank-b")
        other_admin = factories.member(other, roles=("admin",)).user
        headers = sign_in(other_admin, tenant=other, step_up=True)
        self.assertIsNone(self.client.get(URL, **headers).json()["sessionIdleMinutes"])
        self.activate(other)
        self.assertFalse(SecurityPolicy.objects.filter(tenant=self.tenant).exists(), "row-level security hides A's row from B")
        self.assertEqual(self._put(headers, {"sessionIdleMinutes": 60, "sessionAbsoluteHours": 4}).status_code, 200)
        mine = self._row()
        assert mine is not None
        self.assertEqual((mine.session_idle_minutes, mine.session_absolute_hours), (15, 8))
        self.assertEqual(len(self._events()), 1)
        self.assertEqual(len(self._events(other)), 1)
