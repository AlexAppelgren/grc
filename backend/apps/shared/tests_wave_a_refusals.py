"""Wave A's saved queries left every refusal in place (PERF_AUDIT, rules for every package).

perf-request-once changed how every request resolves its caller, perf-bulk-set-based the two
bulk writes, and perf-frontend-requests what several reads carry. Each package proved the
refusals against its own base; this proves them once more on the merged tree, over every
route the three changed: a revoked session and a removed membership are 401 on the very next
request, a revoked key is 401 on MCP, and another bank's id is 404 or never rides along.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.identity.models import ApiKey, Membership, UserSession
from apps.library import testing as library_build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.testing import sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

V1 = "/api/v1"
MCP_VERSION = "2025-11-25"


class WaveARefusals(TestCase):
    """The plain client: the checks below are refusals, which write no audit row."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="wave-a-mine")
        self.other = factories.tenant(slug="wave-a-theirs")
        self.user = factories.member_user(self.tenant, roles=("admin", "compliance_officer"))
        law = library_build.instrument(key="wave-a-law", short_name="WAL", regime="regime:securities")
        self.duty = library_build.obligation(law, key="wave-a-duty", ref_label="1 §", terms=("legal_entity:bank",))
        theirs = library_build.instrument(key="wave-a-theirs", regime="regime:securities", owner_tenant=self.other)
        self.their_duty = library_build.obligation(theirs, key="wave-a-their-duty", ref_label="1 §")
        self.entity = factories.legal_entity(self.tenant, name="Mine AB")
        self.their_entity = factories.legal_entity(self.other, name="Theirs AB")

    def routes(self) -> list[tuple[str, str, dict[str, Any] | None]]:
        """Every session route wave A changed, as a bank admin who is also its officer calls it."""
        answer = {"obligationId": str(self.duty.id), "applicability": "applies", "reason": "Certified"}
        return [
            ("get", f"{V1}/me", None),
            ("get", f"{V1}/reference/languages", None),
            ("get", f"{V1}/home", None),
            ("get", f"{V1}/agents", None),
            ("get", f"{V1}/research-requests", None),
            ("get", f"{V1}/tenant/org-units", None),
            ("get", f"{V1}/obligations/{self.duty.id}/register", None),
            ("post", f"{V1}/applicability", {"rows": [answer]}),
        ]

    def call(self, method: str, path: str, body: dict[str, Any] | None, headers: dict[str, Any]) -> Any:
        if method == "get":
            return self.client.get(path, **headers)
        return self.client.post(path, data=json.dumps(body), content_type="application/json", **headers)

    def assert_answered_then_refused(self, revoke: Any) -> None:
        for method, path, body in self.routes():
            with self.subTest(path=path):
                headers = sign_in(self.user, tenant=self.tenant)
                self.assertEqual(self.call(method, path, body, headers).status_code, 200, path)
                tenancy.activate(self.tenant.id)
                revoke()
                self.assertEqual(self.call(method, path, body, headers).status_code, 401, path)
                tenancy.activate(self.tenant.id)
                UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
                Membership.objects.filter(user=self.user, tenant=self.tenant).update(deactivated_at=None)

    def test_a_revoked_session_is_refused_on_every_changed_route(self) -> None:
        self.assert_answered_then_refused(lambda: UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now()))

    def test_a_removed_membership_is_refused_on_every_changed_route(self) -> None:
        self.assert_answered_then_refused(
            lambda: Membership.objects.filter(user=self.user, tenant=self.tenant).update(deactivated_at=timezone.now())
        )

    def test_a_revoked_session_cannot_refresh(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        tenancy.activate(self.tenant.id)
        UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
        self.assertEqual(self.client.post(f"{V1}/auth/refresh", HTTP_COOKIE=headers["HTTP_COOKIE"]).status_code, 401)

    def test_a_revoked_key_is_refused_on_mcp(self) -> None:
        entry = factories.agent_access_entry(self.tenant)
        key = factories.entry_key(self.tenant, entry, scopes=("library:read", "search:read"))

        def mcp(method: str, params: dict[str, Any]) -> Any:
            message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            return self.client.post(
                f"{V1}/mcp", data=json.dumps(message), content_type="application/json",
                HTTP_X_API_KEY=key.plain_key, HTTP_MCP_PROTOCOL_VERSION=MCP_VERSION,
            )

        calls: tuple[tuple[str, dict[str, Any]], ...] = (("tools/list", {}), ("tools/call", {"name": "get_obligation", "arguments": {"obligationId": str(self.duty.id)}}))
        for method, params in calls:
            self.assertEqual(mcp(method, params).status_code, 200, method)
        tenancy.activate(self.tenant.id)
        ApiKey.objects.filter(pk=key.id).update(revoked_at=timezone.now())
        for method, params in calls:
            self.assertEqual(mcp(method, params).status_code, 401, method)

    def test_another_banks_ids_are_not_found_and_never_ride_along(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/obligations/{self.their_duty.id}/register", **headers).status_code, 404)
        self.assertEqual(self.client.get(f"{V1}/tenant/org-units/{self.their_entity.id}/licences", **headers).status_code, 404)
        answer = {"obligationId": str(self.duty.id), "orgUnitId": str(self.their_entity.id), "applicability": "applies", "reason": "x"}
        self.assertEqual(self.call("post", f"{V1}/applicability", {"rows": [answer]}, headers).status_code, 404)
        units = self.client.get(f"{V1}/tenant/org-units", **headers).json()["items"]
        self.assertIn(str(self.entity.id), {row["id"] for row in units})
        self.assertNotIn(str(self.their_entity.id), {row["id"] for row in units})

    def test_the_batch_decision_refuses_a_revoked_session_and_a_bank_member(self) -> None:
        batch = f"{V1}/proposal-batches/{uuid.uuid4()}/decide"
        body = {"rows": [], "rest": "approved"}
        reviewer = factories.platform_user(roles=("library_editor",), email="wave-a-reviewer@bleqq.test")
        headers = sign_in(reviewer, step_up=True)
        self.assertEqual(self.call("post", batch, body, headers).status_code, 404)
        tenancy.clear_tenant()
        UserSession.objects.filter(user=reviewer).update(revoked_at=timezone.now())
        self.assertEqual(self.call("post", batch, body, headers).status_code, 401)
        self.assertEqual(self.call("post", batch, body, sign_in(self.user, tenant=self.tenant, step_up=True)).status_code, 403)
