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
approveProposal, createFootprintRequest.

Prefixes hosted: ADM, AUD.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest import skip

from django.db import connection
from django.test import override_settings

from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories
# Modules, not classes: a TestCase imported by name would be collected and run here twice.
from apps.shared import tests_append_only as append_only_guards
from apps.shared import tests_audit_on_write as audit_guards
from apps.shared import tests_rls as rls_guards
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import Flag
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
# The mixed tables that exist so far (app.md, AC "Mixed tables"); ai_generation joins with AUD-02.
MIXED_TABLES = ("audit_event", "outbox_event", "problem_report", "api_key")


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

        A problem report is resolved by a proposal (AUD-03).
        """

    @skip("pending: AUD-S6")
    def test_aud_s6(self) -> None:
        """AUD-S6

        Retention per tenant purges what it may and keeps append-only rows (AUD-04).
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
        # forced with a tenant policy, and that policy is "shared or mine".
        self._prove(rls_guards.RowLevelSecurityGuard)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename, qual FROM pg_policies WHERE policyname = 'tenant_isolation' AND tablename = ANY(%s)",
                [list(MIXED_TABLES)],
            )
            policies = dict(cursor.fetchall())
        self.assertEqual(set(policies), set(MIXED_TABLES))
        for table, qual in policies.items():
            self.assertIn("tenant_id IS NULL", qual, f"{table} is not shared-or-mine")

    @skip("pending: ADM-S4")
    def test_adm_s4(self) -> None:
        """ADM-S4

        The platform console offers each surface to the platform role that owns it (ADM-02).
        """

    @skip("pending: ADM-S5")
    def test_adm_s5(self) -> None:
        """ADM-S5

        System health names what is wrong (ADM-02).
        """

    @skip("pending: ADM-S6")
    def test_adm_s6(self) -> None:
        """ADM-S6

        Tenants, plans and support access are managed from the console (ADM-02).
        """
