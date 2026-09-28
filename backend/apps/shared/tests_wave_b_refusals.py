"""Wave B's saved queries left every refusal and every audit row in place (PERF_AUDIT, rules
for every package).

perf-tenant-in-token signs the session's bank into the access token and resolves a request
in two queries, perf-audit-writes sends a write's audit and outbox rows as one statement, and
perf-obligation-page makes the register read carry every panel. Each package proved its own
cases against its own base; this proves them once more on the merged tree, over the routes
the three changed: a revoked session, a removed membership and a token whose bank is not its
session's are 401 on the very next request, a revoked key is 401 on REST and MCP, another
bank's id is 404, and an audited write through a route leaves exactly its audit row and its
outbox row, append-only, while a refused write leaves neither.
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


class WaveBRefusals(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="wave-b-mine")
        self.other = factories.tenant(slug="wave-b-theirs")
        self.user = factories.member_user(self.tenant, roles=("admin", "compliance_officer"))
        law = library_build.instrument(key="wave-b-law", short_name="WBL", regime="regime:securities")
        self.duty = library_build.obligation(law, key="wave-b-duty", ref_label="1 §", terms=("legal_entity:bank",))
        theirs = library_build.instrument(key="wave-b-theirs", regime="regime:securities", owner_tenant=self.other)
        self.their_duty = library_build.obligation(theirs, key="wave-b-their-duty", ref_label="1 §")
        self.entity = factories.legal_entity(self.tenant, name="Mine AB")
        self.their_entity = factories.legal_entity(self.other, name="Theirs AB")

    def routes(self) -> list[str]:
        """The session reads wave B changed: the fixed cost of every request, and the register read."""
        return [
            f"{V1}/reference/languages",
            f"{V1}/me",
            f"{V1}/home",
            f"{V1}/obligations/{self.duty.id}/register",
        ]

    def assert_answered_then_refused(self, refuse: Any) -> None:
        for path in self.routes():
            with self.subTest(path=path):
                headers = sign_in(self.user, tenant=self.tenant)
                self.assertEqual(self.client.get(path, **headers).status_code, 200, path)
                tenancy.activate(self.tenant.id)
                headers = refuse(headers)
                self.assertEqual(self.client.get(path, **headers).status_code, 401, path)
                tenancy.activate(self.tenant.id)
                UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
                Membership.objects.filter(user=self.user, tenant=self.tenant).update(deactivated_at=None)

    def test_a_revoked_session_is_refused(self) -> None:
        def revoke(headers: dict[str, Any]) -> dict[str, Any]:
            UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
            return headers

        self.assert_answered_then_refused(revoke)

    def test_a_removed_membership_is_refused(self) -> None:
        def remove(headers: dict[str, Any]) -> dict[str, Any]:
            Membership.objects.filter(user=self.user, tenant=self.tenant).update(deactivated_at=timezone.now())
            return headers

        self.assert_answered_then_refused(remove)

    def test_a_token_whose_bank_is_not_its_sessions_is_refused(self) -> None:
        def claim_another_bank(headers: dict[str, Any]) -> dict[str, Any]:
            claims = tokens.parse_access_token(str(headers["HTTP_AUTHORIZATION"]).removeprefix("Bearer "), timezone.now())
            assert claims is not None
            forged, _ = tokens.issue_access_token(claims.session_id, claims.kind, self.other.id, timezone.now())
            return {**headers, "HTTP_AUTHORIZATION": f"Bearer {forged}"}

        self.assert_answered_then_refused(claim_another_bank)

    def test_a_revoked_key_is_refused_on_rest_and_mcp(self) -> None:
        entry = factories.agent_access_entry(self.tenant)
        key = factories.entry_key(self.tenant, entry, scopes=("library:read", "search:read"))
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_obligation", "arguments": {"obligationId": str(self.duty.id)}}}

        def calls() -> list[int]:
            rest = self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=key.plain_key)
            mcp = self.client.post(
                f"{V1}/mcp", data=json.dumps(message), content_type="application/json",
                HTTP_X_API_KEY=key.plain_key, HTTP_MCP_PROTOCOL_VERSION=MCP_VERSION,
            )
            return [rest.status_code, mcp.status_code]

        self.assertEqual(calls(), [200, 200])
        tenancy.activate(self.tenant.id)
        ApiKey.objects.filter(pk=key.id).update(revoked_at=timezone.now())
        self.assertEqual(calls(), [401, 401])

    def test_another_banks_id_is_not_found(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/obligations/{self.their_duty.id}/register", **headers).status_code, 404)
        self.assertEqual(self.client.get(f"{V1}/tenant/org-units/{self.their_entity.id}/licences", **headers).status_code, 404)
        panels = self.client.get(f"{V1}/obligations/{self.duty.id}/register", **headers).content.decode()
        self.assertNotIn(str(self.other.id), panels)
        self.assertNotIn(str(self.their_entity.id), panels)


class WaveBAuditRows(TestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="wave-b-audit")
        self.other = factories.tenant(slug="wave-b-audit-theirs")
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
