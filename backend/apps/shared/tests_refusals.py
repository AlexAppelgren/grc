"""The performance waves left every refusal and every audit row in place (PERF_AUDIT, rules
for every package).

Wave A (perf-request-once, perf-bulk-set-based, perf-frontend-requests) changed how every
request resolves its caller, the two bulk writes and what several reads carry; wave B
(perf-tenant-in-token, perf-audit-writes, perf-obligation-page) signs the session's bank into
the access token, sends a write's audit and outbox rows as one statement and makes the
register read carry every panel. One table of refusals over one table of the routes they
changed proves them on the merged tree: a revoked session, a removed membership and a token
whose bank is not its session's are 401 on the very next request, a revoked key is 401 on
REST and MCP, another bank's id is 404 or never rides along, and an audited write leaves
exactly its audit and outbox row, append-only, while a refused write leaves neither.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from apps.identity import tokens
from apps.identity.models import ApiKey, Membership, UserSession
from apps.library import testing as library_build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

V1 = "/api/v1"
MCP_VERSION = "2025-11-25"


class Refusals(TestCase):
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
        """Every session route the waves changed, as a bank admin who is also its officer calls
        it: the fixed cost of every request, the register read and the bulk write."""
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

    def assert_answered_then_refused(self, refuse: Any) -> None:
        """Each route answers 200, then 401 once `refuse` has turned the caller's headers bad."""
        for method, path, body in self.routes():
            with self.subTest(path=path):
                headers = sign_in(self.user, tenant=self.tenant)
                self.assertEqual(self.call(method, path, body, headers).status_code, 200, path)
                tenancy.activate(self.tenant.id)
                headers = refuse(headers)
                self.assertEqual(self.call(method, path, body, headers).status_code, 401, path)
                tenancy.activate(self.tenant.id)
                UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
                Membership.objects.filter(user=self.user, tenant=self.tenant).update(deactivated_at=None)

    def revoke_session(self, headers: dict[str, Any]) -> dict[str, Any]:
        UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
        return headers

    def remove_membership(self, headers: dict[str, Any]) -> dict[str, Any]:
        Membership.objects.filter(user=self.user, tenant=self.tenant).update(deactivated_at=timezone.now())
        return headers

    def claim_another_bank(self, headers: dict[str, Any]) -> dict[str, Any]:
        claims = tokens.parse_access_token(str(headers["HTTP_AUTHORIZATION"]).removeprefix("Bearer "), timezone.now())
        assert claims is not None
        forged, _ = tokens.issue_access_token(claims.session_id, claims.kind, self.other.id, timezone.now())
        return {**headers, "HTTP_AUTHORIZATION": f"Bearer {forged}"}

    def test_each_refusal_is_401_on_every_changed_route(self) -> None:
        for refusal in (self.revoke_session, self.remove_membership, self.claim_another_bank):
            with self.subTest(refusal=refusal.__name__):
                self.assert_answered_then_refused(refusal)

    def test_a_revoked_session_cannot_refresh(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        tenancy.activate(self.tenant.id)
        UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
        self.assertEqual(self.client.post(f"{V1}/auth/refresh", HTTP_COOKIE=headers["HTTP_COOKIE"]).status_code, 401)

    def test_a_revoked_key_is_refused_on_rest_and_mcp(self) -> None:
        entry = factories.agent_access_entry(self.tenant)
        key = factories.entry_key(self.tenant, entry, scopes=("library:read", "search:read"))

        def mcp(method: str, params: dict[str, Any]) -> Any:
            message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            return self.client.post(
                f"{V1}/mcp", data=json.dumps(message), content_type="application/json",
                HTTP_X_API_KEY=key.plain_key, HTTP_MCP_PROTOCOL_VERSION=MCP_VERSION,
            )

        def calls() -> list[int]:
            rest = self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=key.plain_key)
            listed = mcp("tools/list", {})
            called = mcp("tools/call", {"name": "get_obligation", "arguments": {"obligationId": str(self.duty.id)}})
            return [rest.status_code, listed.status_code, called.status_code]

        self.assertEqual(calls(), [200, 200, 200])
        tenancy.activate(self.tenant.id)
        ApiKey.objects.filter(pk=key.id).update(revoked_at=timezone.now())
        self.assertEqual(calls(), [401, 401, 401])

    def test_another_banks_ids_are_not_found_and_never_ride_along(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/obligations/{self.their_duty.id}/register", **headers).status_code, 404)
        self.assertEqual(self.client.get(f"{V1}/tenant/org-units/{self.their_entity.id}/licences", **headers).status_code, 404)
        answer = {"obligationId": str(self.duty.id), "orgUnitId": str(self.their_entity.id), "applicability": "applies", "reason": "x"}
        self.assertEqual(self.call("post", f"{V1}/applicability", {"rows": [answer]}, headers).status_code, 404)
        units = self.client.get(f"{V1}/tenant/org-units", **headers).json()["items"]
        self.assertIn(str(self.entity.id), {row["id"] for row in units})
        self.assertNotIn(str(self.their_entity.id), {row["id"] for row in units})
        panels = self.client.get(f"{V1}/obligations/{self.duty.id}/register", **headers).content.decode()
        self.assertNotIn(str(self.other.id), panels)
        self.assertNotIn(str(self.their_entity.id), panels)

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


class AuditRows(TestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="refusals-audit")
        self.other = factories.tenant(slug="refusals-audit-theirs")
        self.user = factories.member_user(self.tenant, roles=("admin",))
        self.entity = factories.legal_entity(self.tenant, name="Mine AB")
        self.their_entity = factories.legal_entity(self.other, name="Theirs AB")

    def create(self, parent: uuid.UUID, headers: dict[str, Any] | None = None) -> Any:
        body = {"kind": "business_area", "name": "Retail Banking", "parentId": str(parent)}
        headers = headers or sign_in(self.user, tenant=self.tenant)
        return self.client.post(f"{V1}/tenant/org-units", data=json.dumps(body), content_type="application/json", **headers)

    def test_an_audited_write_leaves_its_audit_and_outbox_row_append_only(self) -> None:
        response = self.create(self.entity.id)
        self.assertEqual(response.status_code, 201, response.content)
        unit = response.json()["id"]
        tenancy.activate(self.tenant.id)
        event = AuditEvent.objects.get(action="org_unit.created", subject_id=unit)
        self.assertEqual((event.tenant_id, event.actor_id, event.subject_type), (self.tenant.id, self.user.id, "org_unit"))
        outbox = OutboxEvent.objects.get(audit_event=event)
        self.assertEqual(outbox.tenant_id, self.tenant.id)
        self.assertEqual(outbox.payload["auditEventId"], str(event.id))
        with connection.cursor() as cursor:
            for statement, row in (
                ("UPDATE audit_event SET summary = 'x' WHERE id = %s", event.id),
                ("DELETE FROM audit_event WHERE id = %s", event.id),
                ("UPDATE outbox_event SET topic = 'x' WHERE id = %s", outbox.id),
                ("DELETE FROM outbox_event WHERE id = %s", outbox.id),
            ):
                with self.subTest(statement=statement), self.assertRaises(DatabaseError) as caught, transaction.atomic():
                    cursor.execute(statement, [str(row)])
                self.assertIn("append-only", str(caught.exception))

    def test_a_refused_write_leaves_no_row(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)  # signing in writes rows of its own
        tenancy.activate(self.tenant.id)
        before = (AuditEvent.objects.count(), OutboxEvent.objects.count())
        self.assertIn(self.create(self.their_entity.id, headers).status_code, (404, 422))
        tenancy.activate(self.tenant.id)
        self.assertEqual((AuditEvent.objects.count(), OutboxEvent.objects.count()), before)
