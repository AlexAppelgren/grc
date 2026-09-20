"""Scenario tests for the governance app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

AUD-S1 and AUD-S2 are proven by the structural guards in apps/shared; their scenarios
run those guard proofs, so one source proves each rule. AUD-S7 reads through
GET /audit-events (chunk 4).

Operations exercised (the audit-on-write guard reads these names): createProposal,
approveProposal, createConsoleTenant, createFootprintRequest. ADM-S4 also drives the
console routes other apps register — the source registry and the platform agent keys —
by their gate alone; what each one then does is its own app's scenario.

Prefixes hosted: ACC, ADM, AUD.
"""

from __future__ import annotations

import unittest
import uuid
from typing import Any
from unittest import skip

from django.db import connection
from django.test import override_settings

from apps.identity.models import Invitation, TenantRole
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms
# Modules, not classes: a TestCase imported by name would be collected and run here twice.
from apps.shared import tests_append_only as append_only_guards
from apps.shared import tests_audit_on_write as audit_guards
from apps.shared import tests_rls as rls_guards
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import AuditEvent, Tenant, TenantContentLanguage
from apps.shared.permissions import UNGATED_BY_DESIGN, gate_of
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import ComplianceStatus, Flag
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import TENANT_SYSTEM_ROWS
from config.api import api

V1 = "/api/v1"
# The mixed tables that exist so far (app.md, AC "Mixed tables"); ai_generation joins with AUD-02.
MIXED_TABLES = ("audit_event", "outbox_event", "problem_report", "api_key")

PLATFORM_ROLES = ("library_editor", "platform_admin")
_ANY_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

# ADM-S4 drives every console endpoint that a platform permission gates. Ninja parses the
# body before the gate runs, so each entry carries a request the schema accepts; the id in
# a path never has to exist, because the gate answers first. The first assertion of the
# test fails when a console route is added and not listed here, so the table cannot rot.
PLATFORM_ROUTE_REQUESTS: dict[str, tuple[str, str, dict[str, Any] | None]] = {
    "listProposals": ("GET", "/proposals", None),
    "getProposal": ("GET", f"/proposals/{_ANY_ID}", None),
    "approveProposal": ("POST", f"/proposals/{_ANY_ID}/approve", {}),
    "rejectProposal": ("POST", f"/proposals/{_ANY_ID}/reject", {"rejectionCode": "other"}),
    "listConsoleTenants": ("GET", "/console/tenants", None),
    "createConsoleTenant": (
        "POST",
        "/console/tenants",
        {
            "name": "Console Bank AB",
            "slug": "console-bank",
            "timezone": "Europe/Stockholm",
            "defaultLanguage": "sv",
            "contentLanguages": ["sv", "en"],
            "firstAdminEmail": "first.admin@console-bank.test",
        },
    ),
    "consoleReissueEnrolment": (
        "POST",
        f"/console/tenants/{_ANY_ID}/members/{_ANY_ID}/reissue-enrolment",
        {"reason": "The administrator lost every device.", "outOfBandCheck": "Called the registered number."},
    ),
    # The source registry is the library editor's alone (WAT-01): a platform admin is refused.
    "createSource": (
        "POST",
        "/sources",
        {"name": "Finansinspektionen news", "kind": "authority_site", "checkFrequency": "daily"},
    ),
    "updateSource": ("PATCH", f"/sources/{_ANY_ID}", {"active": False}),
    # A key bound to an agent is the platform admin's alone (ID-10, AGT-01): a library
    # editor is refused. Creating one also needs a passkey, which the owner half proves.
    "listAgentKeys": ("GET", "/agent-keys", None),
    "createAgentKey": (
        "POST",
        "/agent-keys",
        {"name": "Watch sweeper", "agentId": str(_ANY_ID), "scopes": ["changes:write"]},
    ),
    "revokeAgentKey": ("POST", f"/agent-keys/{_ANY_ID}/revoke", {}),
}

# Console routes whose caller a logic gate decides instead of a decorator (they carry a
# `logic-gate` reason in UNGATED_BY_DESIGN). Each still answers 403 with the permission it
# wanted, to the platform role that does not hold it. chunk4-T16b adds GET /problem-reports.
LOGIC_GATED_PLATFORM_ROUTES: dict[str, tuple[str, str, dict[str, Any] | None, str]] = {
    "createProposal": (
        "POST",
        "/proposals",
        {"kind": "vocabulary_create", "title": "Add a flag", "payload": {"list": "flag", "key": "x", "labels": {"en": "X"}}},
        "platform_admin",
    ),
}


class GovernanceScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.governance, one method per @integration scenario."""

    def _prove(self, *guards: type[unittest.TestCase]) -> None:
        """Run every proof of the guard classes that prove a scenario, one test at a time
        inside this test's transaction (a class-level run would close its connection), and
        fail with the guards' own messages."""
        result = unittest.TestResult()
        for guard in guards:
            for name in unittest.defaultTestLoader.getTestCaseNames(guard):
                guard(name)(result)  # __call__: Django wraps each proof in a savepoint
        self.assertGreater(result.testsRun, 0)
        self.assertEqual([f"{test}: {trace}" for test, trace in result.errors + result.failures], [])

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _one(self, action: str, subject_id: Any) -> AuditEvent:
        return AuditEvent.objects.get(action=action, subject_id=subject_id)

    def test_aud_s1(self) -> None:
        """AUD-S1

        Every write leaves an audit row and an outbox row in the same transaction (AUD-01, AC-AUD1).
        """
        # The client proof posts to the guard module's own probe views (its class decorator).
        with override_settings(ROOT_URLCONF=audit_guards.__name__):
            self._prove(
                audit_guards.MutatingRoutesHaveScenarios,
                audit_guards.AuditAssertingClientBites,
                audit_guards.RecordWritesBothRowsInOneTransaction,
            )

    def test_aud_s2(self) -> None:
        """AUD-S2

        The audit table rejects update and delete (AUD-01, AC-AUD1).

        The hatch clause is proven for the application role by
        apps/shared/tests_append_only.py, whose proofs need committed rows on the
        cw_app connection and so cannot run inside this transaction.
        """
        self._prove(audit_guards.AppendOnlyHolds, append_only_guards.EveryAppendOnlyTableRunsAGuard)

    @skip("pending: AUD-S4")
    def test_aud_s4(self) -> None:
        """AUD-S4

        Every model output is logged with its review state (AUD-02).
        """

    @skip("pending: AUD-S5")
    def test_aud_s5(self) -> None:
        """AUD-S5

        A problem report stays inside the bank that filed it (AUD-03).
        """

    @skip("pending: AUD-S6")
    def test_aud_s6(self) -> None:
        """AUD-S6

        The purge deletes ten years after a record's last use and never updates a ledger row (AUD-04).
        """

    def test_aud_s7(self) -> None:
        """AUD-S7

        Mixed tables show library rows to everyone and tenant rows to their tenant (AUD-01).
        """
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenant_a = factories.tenant(slug="audit-a")
        tenant_b = factories.tenant(slug="audit-b")
        officer_a = factories.member(tenant_a, roles=("compliance_officer",)).user
        reader_b = factories.member(tenant_b, roles=("reader",)).user
        editor = factories.platform_user(roles=("library_editor",))
        second_editor = factories.platform_user(roles=("library_editor",))
        # Given a library change: a vocabulary row added by an approved proposal, recorded
        # with no tenant and a library editor as actor.
        body = {
            "kind": "vocabulary_create",
            "title": "Add the flag Client money",
            "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            "sourceLabel": "FFFS 2017:2",
            "sourceUrl": "https://www.fi.se/",
        }
        proposal = self._post("/proposals", body, sign_in(editor))
        self.assertEqual(proposal.status_code, 201, proposal.content)
        approved = self._post(f"/proposals/{proposal.json()['id']}/approve", {}, sign_in(second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        library_event = self._one("vocabulary.created", Flag.objects.get(key="client_money").id)
        # And tenant A's own work (a footprint change request; cases arrive with chunk 9).
        requested = self._post(
            "/tenant/footprint/requests",
            {"adds": [{"dimension": "channel", "key": "digital"}], "removes": []},
            sign_in(officer_a, tenant=tenant_a),
        )
        self.assertEqual(requested.status_code, 201, requested.content)
        tenant_event = self._one("footprint.change_requested", requested.json()["id"])
        self.assertEqual(tenant_event.tenant_id, tenant_a.id)
        # When tenant B reads the audit log, it sees the library event and not tenant A's.
        read = self.client.get(f"{V1}/audit-events?limit=100", **sign_in(reader_b, tenant=tenant_b))
        self.assertEqual(read.status_code, 200, read.content)
        seen = {row["id"] for row in read.json()["items"]}
        self.assertIn(str(library_event.id), seen)
        self.assertNotIn(str(tenant_event.id), seen)
        # Tenant A sees both.
        read_a = self.client.get(f"{V1}/audit-events?limit=100", **sign_in(officer_a, tenant=tenant_a))
        self.assertTrue({str(library_event.id), str(tenant_event.id)} <= {row["id"] for row in read_a.json()["items"]})
        # When the row-level security guard enumerates the mixed tables, each is enabled and
        # forced, reads "shared or mine" and writes only the session's own zone (H15): the
        # tenant policy carries the own-zone rule and a read policy adds the platform's rows.
        self._prove(rls_guards.RowLevelSecurityGuard)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename, policyname, cmd, qual, with_check FROM pg_policies WHERE tablename = ANY(%s)",
                [list(MIXED_TABLES)],
            )
            policies = {(table, policy): (cmd, qual, check) for table, policy, cmd, qual, check in cursor.fetchall()}
        own_zone = rls_guards.own_zone_rule("tenant_id")
        for table in MIXED_TABLES:
            write_rule = policies[(table, "tenant_isolation")]
            self.assertEqual(write_rule[0], "ALL", f"{table}'s tenant policy is not the write rule")
            self.assertIn(own_zone, write_rule[2], f"{table} accepts a write outside the session's zone")
            read_rule = policies[(table, rls_guards.LIBRARY_READ_POLICY)]
            self.assertEqual(
                (read_rule[0], read_rule[1]), ("SELECT", "(tenant_id IS NULL)"), f"{table} is not shared-or-mine"
            )

    def _call(self, method: str, path: str, payload: dict[str, Any] | None, headers: dict[str, Any]) -> Any:
        if payload is None:
            return self.client.get(f"{V1}{path}", **headers)
        send = getattr(self.client, method.lower())  # POST and PATCH both carry a body
        return send(f"{V1}{path}", data=payload, content_type="application/json", **headers)

    def _platform_gated_operations(self) -> dict[str, str]:
        """Every registered operation a platform permission gates, with that permission."""
        gated: dict[str, str] = {}
        for operation in iter_operations(api):
            gate = gate_of(operation.view_func)
            if gate is not None and gate.kind == "permission" and gate.value in perms.PLATFORM_PERMISSIONS:
                gated[operation.operation_id] = gate.value
        return gated

    def test_adm_s4(self) -> None:
        """ADM-S4

        The platform console offers each surface to the platform role that owns it (ADM-02).
        """
        seed_languages()
        holders = {key: factories.platform_user(roles=(key,)) for key in PLATFORM_ROLES}
        gated = self._platform_gated_operations()
        self.assertEqual(
            sorted(gated),
            sorted(PLATFORM_ROUTE_REQUESTS),
            "a console endpoint was added or removed; list it in PLATFORM_ROUTE_REQUESTS so ADM-S4 drives it",
        )
        for operation_id, (method, path, payload) in PLATFORM_ROUTE_REQUESTS.items():
            permission = gated[operation_id]
            owner = next(key for key in PLATFORM_ROLES if permission in perms.SYSTEM_ROLES[key])
            other = next(key for key in PLATFORM_ROLES if key != owner)
            with self.subTest(operation=operation_id):
                refused = self._call(method, path, payload, sign_in(holders[other]))
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertEqual(refused.json()["requiredPermission"], permission)
                # The owning role reaches the operation: it may still be refused for
                # another reason (a missing record, a missing step-up), never for this one.
                answered = self._call(method, path, payload, sign_in(holders[owner]))
                code = answered.json().get("code", "") if answered.status_code >= 400 else ""
                self.assertNotEqual(code, "permission_denied", f"{operation_id} refused {owner}")
        # The console routes a logic gate decides answer the same way.
        for operation_id, (method, path, payload, refused_role) in LOGIC_GATED_PLATFORM_ROUTES.items():
            with self.subTest(operation=operation_id):
                self.assertIn((method, path), UNGATED_BY_DESIGN)
                refused = self._call(method, path, payload, sign_in(holders[refused_role]))
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertTrue(refused.json()["requiredPermission"])

    @skip("pending: ADM-S5")
    def test_adm_s5(self) -> None:
        """ADM-S5

        System health names what is wrong (ADM-02).
        """

    def test_adm_s6(self) -> None:
        """ADM-S6

        A tenant is created from the console with its first administrator invited (ADM-02, ID-01, TEN-01).
        """
        MockMailer.reset()
        seed_languages()
        platform_admin = factories.platform_user(roles=("platform_admin",))
        headers = sign_in(platform_admin)
        created = self._post(
            "/console/tenants",
            {
                "name": "Example Bank AB",
                "slug": "example-bank",
                "timezone": "Europe/Stockholm",
                "defaultLanguage": "sv",
                "contentLanguages": ["sv", "en"],
                "firstAdminEmail": "admin@example-bank.test",
                "firstAdminTitle": "Head of Compliance",
            },
            headers,
        )
        self.assertEqual(created.status_code, 201, created.content)
        tenant = Tenant.objects.get(pk=created.json()["id"])
        # The console lists it by id, never by a count.
        listed = self.client.get(f"{V1}/console/tenants", **headers)
        self.assertIn(str(tenant.id), [row["id"] for row in listed.json()["items"]])
        # The tenant has its system roles, its own lists and its content languages.
        self.activate(tenant)
        self.assertTrue(TenantRole.objects.filter(tenant=tenant, key="admin", is_system=True).exists())
        self.assertTrue(ComplianceStatus.objects.filter(tenant=tenant, is_system=True).exists())
        self.assertEqual(
            [link.language.key for link in TenantContentLanguage.objects.filter(tenant=tenant)], ["sv", "en"]
        )
        # And one pending administrator invitation, whose link was emailed.
        invitation = Invitation.objects.get(tenant=tenant)
        self.assertEqual([link.role.key for link in invitation.role_links.all()], ["admin"])
        self.assertIsNone(invitation.accepted_at)
        self.assertEqual([mail.to for mail in MockMailer.sent], ["admin@example-bank.test"])
        # The creation is audited in the new tenant's own log.
        creation = self._one("tenant.created", tenant.id)
        self.assertEqual(creation.tenant_id, tenant.id)
        # So are the lists it was given, under the same person: the console's rows are
        # nobody's deploy, and the log says who created the bank.
        listed_rows = AuditEvent.objects.filter(tenant=tenant, action="vocabulary.created")
        self.assertEqual(listed_rows.count(), sum(len(rows) for _, rows in TENANT_SYSTEM_ROWS.values()))
        self.assertEqual({(row.actor_type, row.actor_id) for row in listed_rows}, {(creation.actor_type, creation.actor_id)})
        self.assertEqual((creation.actor_type, creation.actor_id), ("user", platform_admin.id))

    @skip("pending: AUD-S8 (AUD-04, chunk 12)")
    def test_aud_s8(self) -> None:
        """AUD-S8

        The ledger purge refuses a cutoff inside the floor and a paused tenant (AUD-04).
        """

    @skip("pending: ADM-S7 (ADM-02, chunk 14)")
    def test_adm_s7(self) -> None:
        """ADM-S7

        The console reads each bank's figures through one audited window (ADM-02).
        """

    @skip("pending: AUD-S9 (D-62, chunk 4 c4-agent-approver)")
    def test_aud_s9(self) -> None:
        """AUD-S9

        An agent's approval is in the audit trail with the agent named (AUD-01, AUD-02).
        """


class GovernanceAgentAccessScenarioTests(ScenarioTestCase):
    """Agent access scenarios for apps.governance (PRD 0.5 module ACC), one method per
    @integration heading in app.md. Skipped until chunk 11 builds them."""

    @skip("pending: ACC-S11")
    def test_acc_s11(self) -> None:
        """ACC-S11

        Tenant reach needs two people, and off means off (ACC-08, AC-ACC2).
        """

    @skip("pending: ACC-S12")
    def test_acc_s12(self) -> None:
        """ACC-S12

        The access log records the call and holds no content (ACC-08).
        """
