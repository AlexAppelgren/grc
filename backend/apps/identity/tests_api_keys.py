"""Rule branches of the API keys (ID-10, AGT-01, ADM-02, AUD-01): the platform's agent keys
and what a bank's own key may hold. ID-S20 walks the happy path of both; this file pins
each refusal and each boundary on its own."""

from __future__ import annotations

import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from django.utils import timezone

from apps.agents import testing as agents_testing
from apps.agents.models import Agent, AgentKind
from apps.agents.seeds import seed_agent_definitions
from apps.identity import api_keys_logic
from apps.identity.models import ApiKey, LoginEvent, LoginEventKind
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
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
        # A 2xx is always audited (AC-AUD1), so the retry leaves a row too, and that row says
        # nothing changed rather than reading as a second revocation.
        revoked, repeated = AuditEvent.objects.filter(action="agent_key.revoked", subject_id=key_id).order_by("created", "id")
        self.assertEqual(revoked.before, {"revokedAt": None})
        self.assertEqual(repeated.before, repeated.after)
        self.assertEqual(repeated.after, revoked.after)
        self.assertIn("already revoked", repeated.summary)
        self.assertNotIn("already revoked", revoked.summary)

    def test_the_definitions_read_names_what_a_key_binds_to(self) -> None:
        tenancy.clear_tenant()
        first = agents_testing.agent(key="aaa-first-by-key")
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
                "scope": self.sweeper.scope,
                "tenantConfigurable": self.sweeper.tenant_configurable,
                "publishedAt": None,
            },
        )
        keys = [item["key"] for item in page.json()["items"]]
        self.assertLess(keys.index(first.key), keys.index(self.sweeper.key), "ordered by key")
        self.assertEqual(keys, sorted(keys))
        tenancy.clear_tenant()
        self.assertEqual(self.client.get(f"{V1}/agent-definitions", HTTP_X_API_KEY=agents_testing.agent_key().plain_key).status_code, 401)


def _switch(agent: Agent, *, active: bool) -> None:
    with library_write("test builder"):
        Agent.objects.filter(pk=agent.pk).update(active=active)
    agent.refresh_from_db()


class KeysFollowTheirAgent(ScenarioTestCase):
    """H43: a key follows its agent's kind and life. A retired or switched-off definition is
    minted no key and its keys stop working; a draft keeps both, so its runner can be tried
    before release (D-93); and a key's scopes are the ones its kind takes, so a review
    agent decides and never files, and a filing agent never decides."""

    def setUp(self) -> None:
        tenancy.clear_tenant()
        self.console = sign_in(factories.platform_user(roles=("platform_admin",)), step_up=True)

    def _mint(self, agent: Agent, scopes: list[str]) -> Any:
        body = {"name": f"{agent.key} key", "agentId": str(agent.id), "scopes": scopes}
        return self.client.post(f"{V1}/agent-keys", data=body, content_type="application/json", **self.console)

    def _refused(self, agent: Agent, scopes: list[str], code: str) -> Any:
        tenancy.clear_tenant()
        before = ApiKey.objects.filter(tenant__isnull=True).count()
        response = self._mint(agent, scopes)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], code)
        tenancy.clear_tenant()
        self.assertEqual(ApiKey.objects.filter(tenant__isnull=True).count(), before, "a refusal writes nothing")
        return response

    def test_a_switched_off_definition_is_minted_no_key(self) -> None:
        agent = agents_testing.agent()
        _switch(agent, active=False)
        self._refused(agent, ["library:read"], "agent_inactive")

    def test_a_retired_definition_is_minted_no_key_and_a_draft_is(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for key, status in (("retired-sweeper", "retired"), ("draft-sweeper", "draft")):
                path = Path(folder) / key / "v1" / "definition.yaml"
                path.parent.mkdir(parents=True)
                path.write_text(
                    f"id: {key}\nversion: 1\nkind: watch\nstatus: {status}\ndescription: A test sweeper.\n"
                    "scope: platform\ntenant_configurable: false\nwrites_to: library\nmodel: claude-opus-5\n"
                    "change_note: First version.\nprompt: prompt.md\ntools:\n  - name: startAgentRun\n",
                    encoding="utf-8",
                )
            api_keys_logic._declared_status.cache_clear()
            self.addCleanup(api_keys_logic._declared_status.cache_clear)
            with mock.patch.object(api_keys_logic, "DEFINITIONS", Path(folder)):
                retired = agents_testing.agent(key="retired-sweeper")
                draft = agents_testing.agent(key="draft-sweeper")
                _switch(retired, active=False)
                _switch(draft, active=False)
                self._refused(retired, ["library:read"], "agent_inactive")
                minted = self._mint(draft, ["library:read"])
                self.assertEqual(minted.status_code, 201, minted.content)
                self.assertIsNotNone(api_keys_logic.resolve_api_key(minted.json()["plainKey"]), "a draft's key works")

    def test_the_shipped_drafts_take_keys_for_evaluation(self) -> None:
        """Both shipped definitions are drafts (D-93): J-4 and PRO-S13 mint their keys."""
        seed_agent_definitions()
        tenancy.clear_tenant()
        for key, scopes in (("watch-sweeper", ["agent-runs:write", "changes:write"]), ("library-confirmer", ["agent-runs:write", "proposals:review"])):
            with self.subTest(agent=key):
                agent = Agent.objects.get(key=key)
                self.assertFalse(agent.active, "still a draft")
                minted = self._mint(agent, scopes)
                self.assertEqual(minted.status_code, 201, minted.content)
                self.assertIsNotNone(api_keys_logic.resolve_api_key(minted.json()["plainKey"]))
                tenancy.clear_tenant()

    def test_a_key_stops_working_when_its_agent_is_switched_off(self) -> None:
        key = agents_testing.agent_key()
        self.assertIsNotNone(api_keys_logic.resolve_api_key(key.plain_key))
        tenancy.clear_tenant()
        _switch(key.agent, active=False)
        self.assertIsNone(api_keys_logic.resolve_api_key(key.plain_key))
        refused = self.client.post(f"{V1}/agent-runs", data=RUN_BODY | {"agent": key.agent.key}, content_type="application/json", HTTP_X_API_KEY=key.plain_key)
        self.assertEqual(refused.status_code, 401, refused.content)

    def test_a_review_agent_decides_and_never_files(self) -> None:
        reviewer = agents_testing.agent(key="confirmer-under-test", kind=AgentKind.REVIEW)
        for scope in sorted(api_keys_logic.FILING_SCOPES):
            with self.subTest(scope=scope):
                refused = self._refused(reviewer, ["agent-runs:write", "proposals:review", scope], "scope_not_for_kind")
                self.assertIn(scope, refused.json()["detail"])
        minted = self._mint(reviewer, ["agent-runs:write", "library:read", "proposals:review"])
        self.assertEqual(minted.status_code, 201, minted.content)

    def test_a_filing_agent_never_decides(self) -> None:
        for kind in sorted(set(AgentKind) - {AgentKind.REVIEW}):
            with self.subTest(kind=kind.value):
                filer = agents_testing.agent(key=f"filer-{kind.value}", kind=kind)
                self._refused(filer, ["proposals:write", "proposals:review"], "scope_not_for_kind")
                minted = self._mint(filer, ["agent-runs:write", "sources:write", "changes:write", "proposals:write"])
                self.assertEqual(minted.status_code, 201, minted.content)


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
        # The route names the reason before it reads the scopes, which were withheld (item 14).
        for path, body in (("/agent-runs", RUN_BODY), (f"/agent-runs/{RUN}/source-checks", CHECK_BODY)):
            with self.subTest(path=path):
                refused = self.client.post(f"{V1}{path}", data=body, content_type="application/json", **agent)
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertEqual(refused.json()["code"], "tenant_agents_not_available")
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
