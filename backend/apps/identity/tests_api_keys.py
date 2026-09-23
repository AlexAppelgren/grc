"""Rule branches of the API keys (ID-10, AGT-01, ADM-02, AUD-01): the platform's agent keys
and what a bank's own key may hold. ID-S20 walks the happy path of both; this file pins
each refusal and each boundary on its own."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.agents import testing as agents_testing
from apps.identity import api_keys_logic
from apps.identity.models import ApiKey, LoginEvent, LoginEventKind
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"
RUN_BODY = {"agent": "watch-sweeper", "model": "mock-llm", "pipelineVersion": "1"}
CHECK_BODY = {"sourceName": "Finansinspektionen news", "status": "ok", "itemsFound": 3}
RUN = "11111111-1111-4111-8111-111111111111"


class AgentKeyRoutes(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = factories.tenant(slug="agent-keys-bank")
        self.bank_admin = factories.member(self.bank, roles=("admin",)).user
        tenancy.clear_tenant()
        self.sweeper = agents_testing.agent()
        self.platform_admin = factories.platform_user(roles=("platform_admin",))
        self.console = sign_in(self.platform_admin, step_up=True)

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _mint(self, changes: dict[str, Any] | None = None) -> Any:
        body = {"name": "Watch sweeper, nightly", "agentId": str(self.sweeper.id), "scopes": ["library:read"]} | (changes or {})
        return self._post("/agent-keys", body, self.console)

    def test_the_list_holds_every_platform_key_and_no_bank_key(self) -> None:
        bank_key = factories.api_key(self.bank)
        tenancy.clear_tenant()
        older = agents_testing.agent_key(agent_row=self.sweeper)
        ApiKey.objects.filter(pk=older.id).update(created_at=timezone.now() - timedelta(days=1))
        newer = self._mint().json()
        page = self.client.get(f"{V1}/agent-keys", **self.console)
        self.assertEqual(page.status_code, 200, page.content)
        ids = [item["id"] for item in page.json()["items"]]
        self.assertLess(ids.index(newer["id"]), ids.index(str(older.id)), "newest first")
        self.assertNotIn(str(bank_key.id), ids)
        self.assertGreaterEqual(page.json()["total"], 2)
        row = next(item for item in page.json()["items"] if item["id"] == newer["id"])
        self.assertEqual(row["agent"], {"key": self.sweeper.key, "kind": None, "label": f"{self.sweeper.key} v1"})
        self.assertNotIn("plainKey", row)

    def test_each_refusal_of_a_new_key_names_its_reason(self) -> None:
        cases: list[tuple[dict[str, Any], str]] = [
            ({"agentId": str(uuid.uuid4())}, "unknown_key"),
            ({"scopes": ["library:write"]}, "unknown_key"),
            ({"name": "   "}, "name_required"),
            ({"expiresAt": (timezone.now() - timedelta(days=1)).isoformat()}, "expiry_in_past"),
            ({"tone": "negative"}, "validation_error"),
        ]
        for change, code in cases:
            with self.subTest(change=sorted(change)):
                refused = self._mint(change)
                self.assertEqual(refused.status_code, 422, refused.content)
                self.assertEqual(refused.json()["code"], code)
        tenancy.clear_tenant()
        self.assertFalse(ApiKey.objects.filter(tenant__isnull=True).exists(), "a refusal writes nothing")

    def test_only_a_platform_admin_reaches_the_keys(self) -> None:
        editor = sign_in(factories.platform_user(roles=("library_editor",)), step_up=True)
        bank = sign_in(self.bank_admin, tenant=self.bank, step_up=True)
        for headers in (editor, bank):
            for method, path, body in (
                ("get", "/agent-keys", None),
                ("get", "/agent-definitions", None),
                ("post", "/agent-keys", {"name": "x", "agentId": str(self.sweeper.id), "scopes": ["library:read"]}),
                ("post", f"/agent-keys/{uuid.uuid4()}/revoke", {}),
            ):
                with self.subTest(method=method, path=path):
                    if body is None:
                        refused = self.client.get(f"{V1}{path}", **headers)
                    else:
                        refused = self._post(path, body, headers)
                    self.assertEqual(refused.status_code, 403, refused.content)
                    self.assertEqual(refused.json()["requiredPermission"], perms.AGENT_DEFINITIONS_MANAGE)

    def test_revoking_touches_platform_keys_only_and_stays_revoked(self) -> None:
        bank_key = factories.api_key(self.bank)
        missing = self._post(f"/agent-keys/{bank_key.id}/revoke", {}, self.console)
        self.assertEqual(missing.status_code, 404, missing.content)
        self.assertEqual(missing.json()["code"], "not_found")
        self.assertIsNotNone(api_keys_logic.resolve_api_key(bank_key.plain_key), "a bank's key is the bank's to revoke")
        tenancy.clear_tenant()  # a console request starts outside every bank, as in production
        self.assertEqual(self._post(f"/agent-keys/{uuid.uuid4()}/revoke", {}, self.console).status_code, 404)

        key_id = self._mint().json()["id"]
        first = self._post(f"/agent-keys/{key_id}/revoke", {}, self.console)
        again = self._post(f"/agent-keys/{key_id}/revoke", {}, self.console)
        self.assertEqual((first.status_code, again.status_code), (200, 200), again.content)
        self.assertEqual(again.json()["revokedAt"], first.json()["revokedAt"], "a revocation is never moved")
        tenancy.clear_tenant()
        self.assertEqual(LoginEvent.objects.filter(api_key_id=key_id, event=LoginEventKind.KEY_REVOKED.value).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="agent_key.revoked", subject_id=key_id).count(), 2)

    def test_the_definitions_read_names_what_a_key_binds_to(self) -> None:
        page = self.client.get(f"{V1}/agent-definitions?limit=100", **self.console)
        self.assertEqual(page.status_code, 200, page.content)
        row = next(item for item in page.json()["items"] if item["id"] == str(self.sweeper.id))
        self.assertEqual(
            row,
            {
                "id": str(self.sweeper.id),
                "key": self.sweeper.key,
                "description": self.sweeper.description,
                "currentVersion": self.sweeper.current_version,
                "active": self.sweeper.active,
            },
        )
        keys = [item["key"] for item in page.json()["items"]]
        self.assertEqual(keys, sorted(keys))
        tenancy.clear_tenant()
        self.assertEqual(self.client.get(f"{V1}/agent-definitions", HTTP_X_API_KEY=agents_testing.agent_key().plain_key).status_code, 401)


class BankKeyScopes(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = factories.tenant(slug="bank-key-scopes")

    def test_the_two_sets_divide_every_scope_and_a_bank_writes_only_proposals(self) -> None:
        self.assertEqual(perms.TENANT_KEY_SCOPES | perms.PLATFORM_ONLY_SCOPES, perms.ALL_SCOPES)
        self.assertEqual(perms.TENANT_KEY_SCOPES & perms.PLATFORM_ONLY_SCOPES, frozenset())
        self.assertEqual({scope for scope in perms.TENANT_KEY_SCOPES if not scope.endswith(":read")}, {perms.SCOPE_PROPOSALS_WRITE})

    def test_a_bank_key_holding_a_watch_write_is_refused_at_the_route(self) -> None:
        legacy = factories.api_key(self.bank, scopes=sorted(perms.PLATFORM_ONLY_SCOPES))
        agent = {"HTTP_X_API_KEY": legacy.plain_key}
        for path, body, scope in (
            ("/agent-runs", RUN_BODY, perms.SCOPE_AGENT_RUNS_WRITE),
            (f"/agent-runs/{RUN}/source-checks", CHECK_BODY, perms.SCOPE_SOURCES_WRITE),
        ):
            with self.subTest(path=path):
                refused = self.client.post(f"{V1}{path}", data=body, content_type="application/json", **agent)
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertEqual((refused.json()["code"], refused.json()["requiredPermission"]), ("permission_denied", scope))
        self.activate(self.bank)
        withheld = LoginEvent.objects.filter(api_key=legacy.row, event=LoginEventKind.KEY_SCOPES_WITHHELD.value)
        self.assertEqual(withheld.count(), 1, "throttled with key_used: two calls, one row")
        self.assertEqual(withheld.get().failure_reason, ", ".join(sorted(perms.PLATFORM_ONLY_SCOPES)))

    def test_a_platform_key_keeps_its_watch_writes(self) -> None:
        tenancy.clear_tenant()
        key = agents_testing.agent_key()
        principal = api_keys_logic.resolve_api_key(key.plain_key)
        assert principal is not None
        self.assertEqual(principal.scopes, frozenset(agents_testing.WATCH_SCOPES))
        self.assertFalse(LoginEvent.objects.filter(api_key=key.row, event=LoginEventKind.KEY_SCOPES_WITHHELD.value).exists())
