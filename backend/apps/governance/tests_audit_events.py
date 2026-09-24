"""GET /audit-events (AUD-01, AC-AUD1): what a tenant reads, what it never reads, the
filters, the page and the query count. AUD-S7 in tests_scenarios.py proves the headline;
these pin each branch of the row rule.

Row-level security makes the tenant cut. Of the rows without a tenant, a tenant sees a
library record's change made by an agent, the system or platform staff, and nothing else:
never a proposal row (a tenant-made proposal's title, the editor's rejection note, a
tenant member as proposer) and never a platform sign-in or code request.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, get_args
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.governance.schemas import AuditActorKind
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType, record
from apps.shared.models import AuditEvent, Tenant
from apps.shared.permissions import Gate, gate_of
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in, stub_session, user_principal
from apps.taxonomy.seeds import seed_library_vocabularies
from config.api import api

V1 = "/api/v1"


class AuditEventsReadTests(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        self.tenant_a = factories.tenant(slug="audit-read-a")
        self.tenant_b = factories.tenant(slug="audit-read-b")
        self.officer_a = factories.member(
            self.tenant_a, roles=("compliance_officer",), user_row=factories.user(name="Anna Secretname")
        ).user
        self.reader_b = factories.member(self.tenant_b, roles=("reader",)).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")

    # -- helpers -------------------------------------------------------------------------
    def _event(self, *, tenant: Tenant | None, actor: Actor, subject_type: str = "vocabulary", action: str = "vocabulary.updated", **fields: Any) -> AuditEvent:  # compliance: allow-kwargs test helper forwarding record() fields
        if tenant is not None:
            tenancy.activate(tenant.id)
        return record(
            action=action,
            actor=actor,
            subject_type=subject_type,
            subject_id=fields.pop("subject_id", uuid.uuid4()),
            subject_title=fields.pop("subject_title", "flag:ai"),
            summary=fields.pop("summary", "Changed a row."),
            tenant_id=tenant.id if tenant else None,
            **fields,
        )

    def _read(self, headers: dict[str, Any], query: str = "limit=100") -> Any:
        response = self.client.get(f"{V1}/audit-events?{query}", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def _ids(self, headers: dict[str, Any], query: str = "limit=100") -> set[str]:
        return {row["id"] for row in self._read(headers, query).json()["items"]}

    def _as_b(self) -> dict[str, Any]:
        return sign_in(self.reader_b, tenant=self.tenant_b)

    def _person(self, user: Any) -> Actor:
        return Actor(kind=ActorType.USER, id=user.id, label=user.name)

    # -- the gate ------------------------------------------------------------------------
    def test_the_route_is_gated_by_audit_read(self) -> None:
        operation = next(op for op in iter_operations(api) if (op.method, op.path) == ("GET", "/audit-events"))
        self.assertEqual(operation.operation_id, "listAuditEvents")
        self.assertEqual(gate_of(operation.view_func), Gate("permission", perms.AUDIT_READ))
        without = user_principal(permissions=perms.TENANT_PERMISSIONS - {perms.AUDIT_READ}, tenant_id=self.tenant_b.id)
        with stub_session(without):
            refused = self.client.get(f"{V1}/audit-events", **self.as_user(without))
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["requiredPermission"], perms.AUDIT_READ)
        # Platform staff hold no audit.read: there is no console audit view in this chunk.
        self.assertEqual(self.client.get(f"{V1}/audit-events", **sign_in(self.editor)).status_code, 403)
        # An agent's key is not a session.
        key = factories.api_key(self.tenant_b, scopes=tuple(sorted(perms.ALL_SCOPES)))
        self.assertEqual(self.client.get(f"{V1}/audit-events", HTTP_X_API_KEY=key.plain_key).status_code, 401)

    def test_a_platform_session_is_not_found_even_with_the_permission(self) -> None:
        principal = user_principal(permissions={perms.AUDIT_READ}, tenant_id=None)
        with stub_session(principal):
            response = self.client.get(f"{V1}/audit-events", **self.as_user(principal))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    # -- what a row says -----------------------------------------------------------------
    def test_a_row_names_actor_subject_change_and_step_up(self) -> None:
        assertion = uuid.uuid4()
        event = self._event(
            tenant=self.tenant_a,
            actor=self._person(self.officer_a),
            subject_type="footprint_change_request",
            action="footprint.change_approved",
            subject_title="1 added, 0 removed",
            summary="Approved a footprint change.",
            before={"status": "pending"},
            after={"status": "approved"},
            step_up_assertion_id=assertion,
        )
        plain = self._event(tenant=self.tenant_a, actor=Actor.system("seed"), subject_type="footprint", action="footprint.term_added")
        rows = {row["id"]: row for row in self._read(sign_in(self.officer_a, tenant=self.tenant_a)).json()["items"]}
        row = rows[str(event.id)]
        self.assertEqual(
            row,
            {
                "id": str(event.id),
                "createdAt": row["createdAt"],
                "actor": {"type": "user", "id": str(self.officer_a.id), "label": "Anna Secretname"},
                "action": "footprint.change_approved",
                "subjectType": "footprint_change_request",
                "subjectId": str(event.subject_id),
                "subjectTitle": "1 added, 0 removed",
                "summary": "Approved a footprint change.",
                "before": {"status": "pending"},
                "after": {"status": "approved"},
                "steppedUp": True,
            },
        )
        self.assertFalse(rows[str(plain.id)]["steppedUp"])
        self.assertIsNone(rows[str(plain.id)]["actor"]["id"])

    def test_the_contract_closes_the_actor_kind_on_every_kind_the_log_records(self) -> None:
        # A kind added to ActorType but not to the contract would fail every page that holds one.
        self.assertEqual(set(get_args(AuditActorKind)), {kind.value for kind in ActorType})

    def test_newest_first_and_paginated_with_a_total(self) -> None:
        # Three events recorded in a row can share a timestamp, and the page's tiebreak is a
        # random uuid4, so each is given its own creation time at insert. The row is never
        # updated afterwards: `created` is auto_now_add, which reads this clock.
        start = timezone.now()
        events = []
        for minutes in range(3):
            with mock.patch("django.utils.timezone.now", return_value=start + timedelta(minutes=minutes)):
                events.append(self._event(tenant=self.tenant_b, actor=Actor.system("seed"), subject_type="footprint"))
        headers = self._as_b()
        query = "subjectType=footprint"
        page = self._read(headers, query).json()
        self.assertEqual(page["total"], 3)
        self.assertEqual([row["id"] for row in page["items"]], [str(e.id) for e in reversed(events)])
        second = self._read(headers, f"{query}&limit=1&offset=1").json()
        self.assertEqual([row["id"] for row in second["items"]], [str(events[1].id)])
        self.assertEqual(second["total"], 3)

    def test_the_page_defaults_to_20_and_refuses_more_than_100(self) -> None:
        for _ in range(21):
            self._event(tenant=self.tenant_b, actor=Actor.system("seed"), subject_type="footprint")
        headers = self._as_b()
        self.assertEqual(len(self._read(headers, "subjectType=footprint").json()["items"]), 20)
        self.assertEqual(len(self._read(headers, "subjectType=footprint&limit=100").json()["items"]), 21)
        too_many = self.client.get(f"{V1}/audit-events?limit=101", **headers)
        self.assertEqual(too_many.status_code, 422)
        self.assertEqual(too_many.json()["code"], "validation_error")

    def test_the_query_count_does_not_grow_with_the_page(self) -> None:
        for _ in range(30):
            self._event(tenant=self.tenant_b, actor=Actor.system("seed"), subject_type="footprint")
        headers = self._as_b()
        counts = []
        for limit in (1, 30):
            with CaptureQueriesContext(connection) as queries:
                self._read(headers, f"limit={limit}")
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])

    # -- filters -------------------------------------------------------------------------
    def test_filters_by_record_actor_and_time(self) -> None:
        subject = uuid.uuid4()
        mine = self._event(tenant=self.tenant_b, actor=self._person(self.reader_b), subject_type="footprint", subject_id=subject)
        other = self._event(tenant=self.tenant_b, actor=Actor.system("seed"), subject_type="footprint_change_request")
        headers = self._as_b()
        self.assertEqual(self._ids(headers, f"subjectType=footprint&subjectId={subject}"), {str(mine.id)})
        self.assertEqual(self._ids(headers, "subjectType=footprint_change_request"), {str(other.id)})
        self.assertEqual(self._ids(headers, f"subjectId={subject}"), {str(mine.id)})
        by_actor = self._ids(headers, f"actorId={self.reader_b.id}")
        self.assertIn(str(mine.id), by_actor)
        self.assertNotIn(str(other.id), by_actor)
        # `from` is inclusive, `to` exclusive.
        at = other.created.isoformat().replace("+00:00", "Z")
        since = self._ids(headers, f"subjectType=footprint_change_request&from={at}")
        self.assertEqual(since, {str(other.id)})
        self.assertEqual(self._ids(headers, f"subjectType=footprint_change_request&to={at}"), set())
        later = (other.created + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        self.assertEqual(self._ids(headers, f"subjectType=footprint_change_request&to={later}"), {str(other.id)})
        self.assertEqual(self._ids(headers, f"from={later}"), set())
        self.assertEqual(self.client.get(f"{V1}/audit-events?subjectId=not-a-uuid", **headers).status_code, 422)

    # -- rows without a tenant -----------------------------------------------------------
    def test_a_library_change_is_shown_only_when_made_by_an_agent_the_system_or_platform_staff(self) -> None:
        shown = {
            subject_type: self._event(tenant=None, actor=Actor.system("library-seed"), subject_type=subject_type, action="library.seeded")
            for subject_type in ("authority", "instrument", "provision", "obligation", "vocabulary", "taxonomy_term")
        }
        by_agent = self._event(tenant=None, actor=factories.agent_actor(), subject_type="obligation")
        by_editor = self._event(tenant=None, actor=self._person(self.editor), subject_type="vocabulary")
        # A tenant member as the actor of a row without a tenant: never shown elsewhere.
        by_member = self._event(tenant=None, actor=self._person(self.officer_a), subject_type="vocabulary")
        # A row without a tenant whose subject is not a library record: never shown.
        not_library = self._event(tenant=None, actor=Actor.system("worker"), subject_type="outbox_probe", action="probe.ran")
        seen = self._ids(self._as_b())
        for event in (*shown.values(), by_agent, by_editor):
            self.assertIn(str(event.id), seen, event.subject_type)
        self.assertNotIn(str(by_member.id), seen)
        self.assertNotIn(str(not_library.id), seen)

    def test_another_tenant_never_sees_proposal_rows_platform_sign_ins_or_code_requests(self) -> None:
        # Tenant A's officer proposes; the editor rejects with a note.
        officer = sign_in(self.officer_a, tenant=self.tenant_a)
        proposal = self.client.post(
            f"{V1}/vocab/flag", data={"labels": {"en": "Project Nightingale"}}, content_type="application/json", **officer
        ).json()["proposal"]
        rejected = self.client.post(
            f"{V1}/proposals/{proposal['id']}/reject",
            data={"rejectionCode": "duplicate", "note": "Covered by Bank A's own flag."},
            content_type="application/json",
            **sign_in(self.editor),
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)
        # A chunk-2-style creation row: no tenant, a tenant member as actor.
        chunk_two = self._event(
            tenant=None,
            actor=self._person(self.officer_a),
            subject_type="proposal",
            action="proposal.created",
            subject_id=uuid.UUID(proposal["id"]),
            subject_title="Project Nightingale",
        )
        # A platform sign-in, and a code request that names tenant A's officer (she holds a
        # passkey, so no code is sent; the row still carries her name and no tenant).
        sign_in(self.editor)
        factories.passkey(self.officer_a)
        self.assertEqual(
            self.client.post(f"{V1}/auth/code/request", data={"email": self.officer_a.email}, content_type="application/json").status_code,
            202,
        )
        self.assertTrue(AuditEvent.objects.filter(action="auth.code_requested", subject_title="Anna Secretname", tenant__isnull=True).exists())
        hidden = AuditEvent.objects.filter(tenant__isnull=True).filter(
            action__in=("proposal.created", "proposal.rejected", "session.created", "auth.code_requested")
        )
        hidden_ids = {str(pk) for pk in hidden.values_list("id", flat=True)}
        self.assertIn(str(chunk_two.id), hidden_ids)
        self.assertEqual(
            {e.action for e in hidden},
            {"proposal.created", "proposal.rejected", "session.created", "auth.code_requested"},
        )
        response = self._read(self._as_b())
        self.assertEqual({row["id"] for row in response.json()["items"]} & hidden_ids, set())
        body = response.content.decode()
        for secret in ("Anna Secretname", "Project Nightingale", "Covered by Bank A", str(self.officer_a.id), "editor@bleqq.test"):
            self.assertNotIn(secret, body)
