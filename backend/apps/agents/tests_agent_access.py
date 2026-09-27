"""Agent access entries and their keys (ACC-01, ACC-03, ACC-08; acc-entries-and-log).

An admin holding `agent_access.manage` registers, changes and revokes an entry, sets its
tenant reach toggle and issues and revokes its keys, each with a passkey step-up and an audit
row. A key holds only the reading scopes, expires no later than `AGENT_ACCESS_KEY_MAX_DAYS`,
is shown once and stored hashed. Revoking an entry revokes every credential bound to it, so
the next call on each answers 401. Another bank's entry is 404 on every route.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from apps.agents import agent_access
from apps.agents.models import AgentAccess
from apps.governance.models import TenantReach
from apps.identity.models import ApiKey, LoginEvent
from apps.shared import factories, tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import Team
from apps.tenants.models import OrgUnit, OrgUnitKind, TenantProduct

V1 = "/api/v1"
ACCESS = f"{V1}/agent-access"


class AgentAccessRoutes(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="acc-entries")
        self.admin = factories.member(self.tenant, roles=("admin",), user_row=factories.user(name="Erik Holm")).user
        self.reader = factories.member(self.tenant, roles=("reader",), user_row=factories.user(name="Sara Lindqvist")).user
        tenancy.activate(self.tenant.id)
        self.trading = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.BUSINESS_AREA.value, name="Trading")
        self.product = TenantProduct.objects.create(tenant=self.tenant, name="Equity trading", org_unit=self.trading)

    # -- helpers ---------------------------------------------------------------------------
    def send(self, method: str, path: str, body: Any = None, *, step_up: bool = True, user: Any = None, **headers: Any) -> Any:
        return self.client.generic(
            method,
            path,
            json.dumps(body if body is not None else {}),
            content_type="application/json",
            **sign_in(user or self.admin, tenant=self.tenant, step_up=step_up),
            **headers,
        )

    def register(self, **overrides: Any) -> dict[str, Any]:
        body = {
            "name": "Trading platform coding agent",
            "purpose": "Designs and reviews the order-routing service.",
            "ownerTeam": "compliance",
            "departmentIds": [str(self.trading.id)],
            **overrides,
        }
        response = self.send("POST", ACCESS, body)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def issue(self, entry_id: str, *, step_up: bool = True, **overrides: Any) -> Any:
        body = {"name": "Order router CI", "scopes": ["library:read"], **overrides}
        return self.send("POST", f"{ACCESS}/{entry_id}/keys", body, step_up=step_up)

    def audit(self, action: str) -> AuditEvent:
        tenancy.activate(self.tenant.id)
        return AuditEvent.objects.filter(tenant_id=self.tenant.id, action=action).order_by("-created").first()  # type: ignore[return-value]

    def reads(self, plain_key: str) -> int:
        return int(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=plain_key).status_code)

    # -- entries ---------------------------------------------------------------------------
    def test_an_admin_registers_an_entry_with_a_step_up_and_the_audit_keeps_no_purpose(self) -> None:
        refused = self.send("POST", ACCESS, {"name": "x", "purpose": "y", "ownerTeam": "compliance"}, step_up=False)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "step_up_required"))
        entry = self.register()
        self.assertEqual(entry["ownerTeam"]["key"], "compliance")
        self.assertEqual(entry["departments"], [{"id": str(self.trading.id), "name": "Trading"}])
        self.assertEqual((entry["active"], entry["tenantReach"], entry["version"], entry["keys"]), (True, False, 1, []))
        self.assertEqual(entry["createdBy"]["id"], str(self.admin.id))
        row = self.audit("agent_access.registered")
        self.assertIsNotNone(row.step_up_assertion_id)
        self.assertEqual(row.after["departmentIds"], [str(self.trading.id)])
        self.assertNotIn("order-routing", str(row.after))
        listed = self.send("GET", ACCESS, step_up=False).json()
        self.assertEqual([item["id"] for item in listed["items"]], [entry["id"]])

    def test_a_team_department_or_product_the_bank_has_not_got_is_unknown_key(self) -> None:
        other = factories.tenant(slug="acc-other")
        tenancy.activate(other.id)
        foreign_unit = OrgUnit.objects.create(tenant=other, kind=OrgUnitKind.BUSINESS_AREA.value, name="Cards")
        cases = (
            {"ownerTeam": "no-such-team"},
            {"departmentIds": [str(foreign_unit.id)]},
            {"productIds": [str(foreign_unit.id)]},
        )
        for body in cases:
            with self.subTest(body=body):
                response = self.send("POST", ACCESS, {"name": "Agent", "purpose": "Reads.", "ownerTeam": "compliance", **body})
                self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_key"))
        tenancy.activate(self.tenant.id)
        Team.objects.filter(tenant=self.tenant, key="compliance").update(active=False)
        retired = self.send("POST", ACCESS, {"name": "Agent", "purpose": "Reads.", "ownerTeam": "compliance"})
        self.assertEqual((retired.status_code, retired.json()["code"]), (422, "unknown_key"))
        tenancy.activate(self.tenant.id)
        self.assertFalse(AgentAccess.objects.filter(tenant=self.tenant).exists())

    def test_a_change_replaces_the_lists_it_sends_and_a_stale_version_is_refused(self) -> None:
        entry = self.register()
        path = f"{ACCESS}/{entry['id']}"
        stale = self.send("PATCH", path, {"name": "Renamed"}, HTTP_IF_MATCH="7")
        self.assertEqual((stale.status_code, stale.json()["code"]), (409, "stale_write"))
        changed = self.send("PATCH", path, {"departmentIds": [], "productIds": [str(self.product.id)]}, HTTP_IF_MATCH="1")
        self.assertEqual(changed.status_code, 200, changed.content)
        body = changed.json()
        self.assertEqual((body["departments"], body["products"], body["version"]), ([], [{"id": str(self.product.id), "name": "Equity trading"}], 2))
        self.assertEqual(body["name"], "Trading platform coding agent")
        row = self.audit("agent_access.updated")
        self.assertEqual((row.before["departmentIds"], row.after["productIds"]), ([str(self.trading.id)], [str(self.product.id)]))
        self.assertFalse(row.after["purposeChanged"])

    def test_the_entry_toggle_and_the_bank_switch_together_decide_reach(self) -> None:
        entry = self.register()
        toggled = self.send("PUT", f"{ACCESS}/{entry['id']}/tenant-reach", {"enabled": True})
        self.assertEqual((toggled.status_code, toggled.json()["tenantReach"]), (200, True))
        self.assertEqual(self.audit("agent_access.reach_set").after["tenantReach"], True)
        principal = Principal(kind=PrincipalKind.AGENT, subject_id=self.admin.id, tenant_id=self.tenant.id, agent_access_id=entry["id"])
        tenancy.activate(self.tenant.id)
        self.assertFalse(agent_access.reach_allowed(principal), "the bank's switch is off")
        TenantReach.objects.create(tenant=self.tenant, enabled=True)
        self.assertTrue(agent_access.reach_allowed(principal))
        unbound = Principal(kind=PrincipalKind.AGENT, subject_id=self.admin.id, tenant_id=self.tenant.id)
        self.assertFalse(agent_access.reach_allowed(unbound))
        self.send("PUT", f"{ACCESS}/{entry['id']}/tenant-reach", {"enabled": False})
        tenancy.activate(self.tenant.id)
        self.assertFalse(agent_access.reach_allowed(principal), "the entry's toggle is off")

    # -- keys ------------------------------------------------------------------------------
    def test_a_key_holds_reading_scopes_only_expires_in_time_and_is_shown_once(self) -> None:
        entry = self.register()
        for overrides, code in (
            ({"scopes": ["proposals:write"]}, "unknown_key"),
            ({"expiresAt": (timezone.now() + timedelta(days=settings.AGENT_ACCESS_KEY_MAX_DAYS + 1)).isoformat()}, "expiry_too_late"),
            ({"expiresAt": (timezone.now() - timedelta(days=1)).isoformat()}, "expiry_in_past"),
        ):
            with self.subTest(code=code):
                refused = self.issue(entry["id"], **overrides)
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, code))
        self.assertEqual(self.issue(entry["id"], step_up=False).status_code, 403)
        created = self.issue(entry["id"])
        self.assertEqual(created.status_code, 201, created.content)
        key = created.json()
        self.assertTrue(key["plainKey"].startswith(f"cw_{key['keyPrefix']}_"))
        max_expiry = timezone.now() + timedelta(days=settings.AGENT_ACCESS_KEY_MAX_DAYS)
        self.assertLess(abs((datetime.fromisoformat(key["expiresAt"]) - max_expiry).total_seconds()), 60)
        tenancy.activate(self.tenant.id)
        row = ApiKey.objects.get(pk=key["id"])
        self.assertNotIn(key["plainKey"].rsplit("_", 1)[1], row.key_hash)
        self.assertEqual((str(row.agent_access_id), row.kind), (entry["id"], "service"))
        self.assertNotIn(key["plainKey"], str(self.audit("api_key.created").after))
        listed = self.send("GET", f"{ACCESS}/{entry['id']}", step_up=False).json()["keys"]
        self.assertEqual([(item["id"], item["lastUsedAt"]) for item in listed], [(key["id"], None)])
        self.assertNotIn("plainKey", listed[0])
        self.assertEqual(self.reads(key["plainKey"]), 200)

    @override_settings(AGENT_ACCESS_KEY_MAX_DAYS=7)
    def test_the_longest_life_is_the_setting(self) -> None:
        entry = self.register()
        refused = self.issue(entry["id"], expiresAt=(timezone.now() + timedelta(days=8)).isoformat())
        self.assertEqual(refused.json()["code"], "expiry_too_late")

    def test_revoking_one_key_stops_it_and_a_repeat_is_a_safe_retry(self) -> None:
        entry = self.register()
        key = self.issue(entry["id"]).json()
        path = f"{ACCESS}/{entry['id']}/keys/{key['id']}/revoke"
        self.assertEqual(self.send("POST", path, step_up=False).status_code, 403)
        first = self.send("POST", path)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertIsNotNone(first.json()["revokedAt"])
        self.assertEqual(self.reads(key["plainKey"]), 401)
        self.assertEqual(self.send("POST", path).json()["revokedAt"], first.json()["revokedAt"])
        other = self.register(name="Another")
        self.assertEqual(self.send("POST", f"{ACCESS}/{other['id']}/keys/{key['id']}/revoke").status_code, 404)

    def test_revoking_the_entry_revokes_every_bound_credential_at_once(self) -> None:
        entry = self.register()
        key = self.issue(entry["id"]).json()
        tenancy.activate(self.tenant.id)
        row = AgentAccess.objects.get(pk=entry["id"])
        token = factories.personal_token(self.tenant, self.reader, entry=SimpleNamespace(id=row.id))
        self.assertEqual((self.reads(key["plainKey"]), self.reads(token.plain_key)), (200, 200))
        stale = self.send("POST", f"{ACCESS}/{entry['id']}/revoke", HTTP_IF_MATCH="9")
        self.assertEqual(stale.json()["code"], "stale_write")
        revoked = self.send("POST", f"{ACCESS}/{entry['id']}/revoke")
        self.assertEqual(revoked.status_code, 200, revoked.content)
        body = revoked.json()
        self.assertEqual((body["active"], body["revokedBy"]["id"]), (False, str(self.admin.id)))
        self.assertTrue(all(item["revokedAt"] for item in body["keys"]))
        self.assertEqual((self.reads(key["plainKey"]), self.reads(token.plain_key)), (401, 401))
        tenancy.activate(self.tenant.id)
        self.assertEqual(
            set(LoginEvent.objects.filter(api_key_id__in=[key["id"], token.id], event__in=["key_revoked", "token_revoked"]).values_list("event", flat=True)),
            {"key_revoked", "token_revoked"},
        )
        self.assertEqual(sorted(self.audit("agent_access.revoked").after["revokedKeyPrefixes"]), sorted([key["keyPrefix"], token.row.key_prefix]))
        again = self.send("POST", f"{ACCESS}/{entry['id']}/revoke")
        self.assertEqual((again.status_code, again.json()["code"]), (409, "invalid_transition"))
        for method, path, body in (("PATCH", "", {"name": "x"}), ("PUT", "/tenant-reach", {"enabled": True}), ("POST", "/keys", {"name": "k", "scopes": ["library:read"]})):
            with self.subTest(route=f"{method} {path}"):
                refused = self.send(method, f"{ACCESS}/{entry['id']}{path}", body)
                self.assertEqual((refused.status_code, refused.json()["code"]), (409, "invalid_transition"))

    def test_another_banks_entry_is_not_found_on_every_route(self) -> None:
        entry = self.register()
        key = self.issue(entry["id"]).json()
        other = factories.tenant(slug="acc-elsewhere")
        stranger = factories.member(other, roles=("admin",)).user
        for method, path, body in (
            ("GET", "", None),
            ("PATCH", "", {"name": "x"}),
            ("POST", "/revoke", None),
            ("PUT", "/tenant-reach", {"enabled": True}),
            ("POST", "/keys", {"name": "k", "scopes": ["library:read"]}),
            ("POST", f"/keys/{key['id']}/revoke", None),
            ("GET", "/calls", None),
        ):
            with self.subTest(route=f"{method} {path}"):
                response = self.client.generic(
                    method,
                    f"{ACCESS}/{entry['id']}{path}",
                    json.dumps(body or {}),
                    content_type="application/json",
                    **sign_in(stranger, tenant=other, step_up=True),
                )
                self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_a_member_without_the_permission_and_a_credential_are_refused(self) -> None:
        entry = self.register()
        key = self.issue(entry["id"]).json()
        denied = self.send("GET", ACCESS, user=self.reader)
        self.assertEqual((denied.status_code, denied.json()["code"]), (403, "permission_denied"))
        by_key = self.client.post(f"{ACCESS}/{entry['id']}/revoke", "{}", content_type="application/json", HTTP_X_API_KEY=key["plainKey"])
        self.assertEqual((by_key.status_code, by_key.json()["code"]), (403, "step_up_required"))
        self.assertEqual(self.client.get(ACCESS, HTTP_X_API_KEY=key["plainKey"]).status_code, 401)
