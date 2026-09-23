"""The organisation's own Ask switch outside the scenarios (D-07, SRC-03, TEN-01). A bank
switches its AI features off and on through `PUT /tenant/ai`, a security change: it needs
`security.manage` and a fresh passkey step-up, and its audit row carries the state before and
after and the step-up assertion. The profile edit, `PATCH /tenant`, never touches the switch,
so renaming the bank still needs no passkey. SRC-S6 (search) proves the switch's effect.

Operations exercised: getTenant, setTenantAi, updateTenant.
"""

from __future__ import annotations

from typing import Any

from apps.identity.models import StepUpAssertion, TenantRole
from apps.library.seeds import seed_languages
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"


class TenantAiSwitch(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.admin = factories.member(self.tenant, roles=("admin",)).user

    def _put(self, headers: dict[str, Any], enabled: Any) -> Any:
        return self.client.put(f"{V1}/tenant/ai", data={"enabled": enabled}, content_type="application/json", **headers)

    def _ai_enabled(self) -> bool:
        return bool(Tenant.objects.values_list("ai_enabled", flat=True).get(pk=self.tenant.id))

    def _switch_events(self) -> list[AuditEvent]:
        self.activate(self.tenant)
        return list(AuditEvent.objects.filter(tenant=self.tenant, action="tenant.ai_switched").order_by("created", "id"))

    def test_the_profile_says_whether_ai_is_on_and_it_starts_on(self) -> None:
        profile = self.client.get(f"{V1}/tenant", **sign_in(self.admin, tenant=self.tenant)).json()
        self.assertIs(profile["aiEnabled"], True)

    def test_switching_off_with_a_step_up_is_audited_with_before_after_and_the_assertion(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        response = self._put(headers, False)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["aiEnabled"], False)
        self.assertEqual(response.json()["id"], str(self.tenant.id))
        self.assertFalse(self._ai_enabled())
        self.assertIs(self.client.get(f"{V1}/tenant", **headers).json()["aiEnabled"], False)
        [event] = self._switch_events()
        assertion = StepUpAssertion.objects.filter(session__user=self.admin).latest("created_at")
        self.assertEqual((event.before, event.after), ({"aiEnabled": True}, {"aiEnabled": False}))
        self.assertEqual(event.step_up_assertion_id, assertion.id)
        self.assertEqual((event.subject_type, event.subject_id, event.actor_id), ("tenant", self.tenant.id, self.admin.id))

    def test_switching_back_on_is_its_own_audited_change(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        self._put(headers, False)
        response = self._put(headers, True)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["aiEnabled"], True)
        self.assertTrue(self._ai_enabled())
        self.assertEqual([(e.before, e.after) for e in self._switch_events()], [({"aiEnabled": True}, {"aiEnabled": False}), ({"aiEnabled": False}, {"aiEnabled": True})])

    def test_without_a_step_up_the_switch_is_refused_and_nothing_changes(self) -> None:
        response = self._put(sign_in(self.admin, tenant=self.tenant), False)
        self.assertEqual((response.status_code, response.json()["code"]), (403, "step_up_required"))
        self.assertTrue(self._ai_enabled())
        self.assertEqual(self._switch_events(), [])

    def test_without_security_manage_the_switch_is_refused_naming_the_permission(self) -> None:
        self.activate(self.tenant)
        TenantRole.objects.get_or_create(tenant=self.tenant, key="members-manage", defaults={"permissions": [perms.MEMBERS_MANAGE]})
        for roles in (("reader",), ("members-manage",)):
            user = factories.member(self.tenant, roles=roles).user
            response = self._put(sign_in(user, tenant=self.tenant, step_up=True), False)
            self.assertEqual((response.status_code, response.json()["code"]), (403, "permission_denied"), roles)
            self.assertEqual(response.json()["requiredPermission"], perms.SECURITY_MANAGE)
        self.assertTrue(self._ai_enabled())
        self.assertEqual(self._switch_events(), [])

    def test_the_body_takes_a_boolean_and_nothing_else(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        for body in ({"enabled": "off"}, {}, {"enabled": False, "name": "Other"}):
            response = self.client.put(f"{V1}/tenant/ai", data=body, content_type="application/json", **headers)
            self.assertEqual(response.status_code, 422, body)
        self.assertTrue(self._ai_enabled())

    def test_the_profile_edit_never_touches_the_switch_and_needs_no_step_up(self) -> None:
        headers = sign_in(self.admin, tenant=self.tenant)
        response = self.client.patch(f"{V1}/tenant", data={"name": "Renamed Bank AB", "aiEnabled": False}, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["aiEnabled"], True)
        self.assertTrue(self._ai_enabled())
        self.assertEqual(self._switch_events(), [])
