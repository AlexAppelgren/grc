"""Scenario tests for the proposals app (playbook 4.1, Appendix B): one method per
`@integration` scenario in app.md, each carrying its ID. Chunk 2 un-skips the scenarios a
vocabulary proposal can prove: PRO-S2 (the library vocabulary half), PRO-S5, PRO-S6 and
PRO-S9. PRO-S1, S3, S4 and S7 need obligation records and land with chunk 4; PRO-S8 is
R2. Never delete a scenario without updating app.md.

Operations exercised (the audit-on-write guard reads these names): createProposal,
approveProposal, rejectProposal.

Prefixes hosted: PRO.
"""

from __future__ import annotations

from typing import Any
from unittest import skip

from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories, permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import Flag
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from config.api import api

V1 = "/api/v1"
# Queries per queue read, measured 2026-09-19 and pinned so an N+1 shows up as a number
# (playbook 10): the scenario client's audit count (1), the request's savepoint pair (2), the
# auth layer for a platform session with no tenant (identity flag on, the session row, flag
# off, platform roles, latest step-up: 5) and the page with its proposer and reviewer (1).
PROPOSAL_QUEUE_QUERIES = 1 + 2 + 5 + 1


class ProposalsScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.proposals, one method per @integration scenario."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant)
        self.officer = factories.member(self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")).user
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")

    def _post(self, path: str, body: dict[str, Any] | None, headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"{V1}{path}", data=body or {}, content_type="application/json", **headers, **extra)

    def _flag_proposal(self) -> dict[str, Any]:
        body = {
            "kind": "vocabulary_create",
            "title": "Add the flag Client money",
            "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money", "sv": "Kundmedel"}, "usageNote": "Safeguarding of client funds."},
            "sourceLabel": "FFFS 2017:2",
            "sourceUrl": "https://www.fi.se/",
        }
        return body

    @skip("pending: PRO-S1 (PRO-01, chunk 4: obligation proposals)")
    def test_pro_s1(self) -> None:
        """PRO-S1

        A proposal carries a source per changed field (PRO-01).
        """

    def test_pro_s2(self) -> None:
        """PRO-S2

        No scope and no tenant role can change a library record directly (PRO-01, AC-PRO1).
        """
        # The library vocabulary half (chunk 2): an API key with every scope and a tenant admin
        # holding every tenant permission. Instruments, provisions and obligations follow in
        # chunk 3 and reuse the same fence.
        key = factories.api_key(self.tenant, scopes=tuple(sorted(perms.ALL_SCOPES)))
        agent = {"HTTP_X_API_KEY": key.plain_key}
        self.assertEqual(self._post("/vocab/flag", {"labels": {"en": "Client money"}}, agent).status_code, 401)
        self.assertEqual(self.client.patch(f"{V1}/vocab/flag/ai", data={"labels": {"en": "x"}}, content_type="application/json", **agent).status_code, 401)
        self.assertEqual(self._post("/taxonomy/terms", {"dimension": "regime", "labels": {"en": "Crypto"}}, agent).status_code, 401)
        # A person with every tenant permission gets a proposal, never a row.
        everything = sign_in(self.admin, tenant=self.tenant, step_up=True)
        # Between them the tenant's system roles hold every tenant permission; none of them is
        # a library write. (cases.signoff is the approver's alone, PRD section 6.)
        tenant_roles = ("admin", "compliance_officer", "owner", "approver", "contributor", "reader", "auditor")
        held = frozenset().union(*(perms.SYSTEM_ROLES[role] for role in tenant_roles))
        self.assertEqual(held, perms.TENANT_PERMISSIONS)
        officer = sign_in(self.officer, tenant=self.tenant, step_up=True)
        proposed = self._post("/vocab/flag", {"labels": {"en": "Client money"}}, officer)
        self.assertEqual(proposed.status_code, 202, proposed.content)
        self.assertFalse(Flag.objects.filter(key="client_money").exists())
        # The admin without proposals.create cannot even propose; the review route is 403 for both.
        self.assertEqual(self._post("/vocab/flag", {"labels": {"en": "Client money"}}, everything).status_code, 403)
        proposal_id = proposed.json()["proposal"]["id"]
        self.assertEqual(self._post(f"/proposals/{proposal_id}/approve", {}, officer).status_code, 403)
        self.assertEqual(self._post(f"/proposals/{proposal_id}/approve", {}, everything).status_code, 403)
        self.assertEqual(self.client.get(f"{V1}/proposals", **officer).status_code, 403)
        # No route writes a library vocabulary or term directly.
        paths = {(op.method, op.path) for op in iter_operations(api)}
        for forbidden in (("PUT", "/vocab/{list}/{key}"), ("DELETE", "/vocab/{list}/{key}"), ("DELETE", "/taxonomy/terms/{term_id}"), ("PUT", "/taxonomy/terms/{term_id}")):
            self.assertNotIn(forbidden, paths)
        # The only path that leaves a library change is an approved proposal.
        approved = self._post(f"/proposals/{proposal_id}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertTrue(Flag.objects.filter(key="client_money").exists())

    @skip("pending: PRO-S3 (PRO-02, chunk 4: obligation versions and re-index)")
    def test_pro_s3(self) -> None:
        """PRO-S3

        Approval applies payload, version, audit row and re-index in one transaction (PRO-02).
        """

    @skip("pending: PRO-S4 (PRO-02, chunk 4: obligation payload overrides)")
    def test_pro_s4(self) -> None:
        """PRO-S4

        The reviewer corrects scope and wording before approving (PRO-02).
        """

    def test_pro_s5(self) -> None:
        """PRO-S5

        Approving your own proposal answers four_eyes_violation (PRO-02, AC-PRO2).
        """
        editor = sign_in(self.editor, step_up=True)
        created = self._post("/proposals", self._flag_proposal(), editor)
        self.assertEqual(created.status_code, 201, created.content)
        proposal = created.json()
        self.assertEqual(proposal["proposedBy"]["id"], str(self.editor.id))
        self.assertEqual(proposal["origin"], "user")
        own = self._post(f"/proposals/{proposal['id']}/approve", {}, editor)
        self.assertEqual(own.status_code, 409, own.content)
        self.assertEqual(own.json()["code"], "four_eyes_violation")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(Flag.objects.filter(key="client_money").exists())
        # The check constraint on the proposal table refuses the row on its own.
        from django.db import connection, transaction

        with self.assertRaises(Exception) as caught:  # compliance: allow-broad-except the driver raises IntegrityError for a CHECK violation
            # A savepoint, so the refused statement does not abort the rest of the scenario.
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("UPDATE proposal SET reviewed_by_id = proposed_by_user_id WHERE id = %s", [proposal["id"]])
        self.assertIn("four_eyes", str(caught.exception))
        # A second editor approves with step-up; the audit event carries the assertion and
        # the applied change is in the same transaction.
        approved = self._post(f"/proposals/{proposal['id']}/approve", {"note": "Agreed."}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(approved.json()["reviewedBy"]["id"], str(self.second_editor.id))
        self.assertIsNotNone(approved.json()["appliedAt"])
        self.assertEqual(Flag.objects.get(key="client_money").labels.get(language="sv").text, "Kundmedel")
        event = AuditEvent.objects.get(action="proposal.approved", subject_id=proposal["id"])
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertIsNone(event.tenant_id)
        self.assertTrue(AuditEvent.objects.filter(action="vocabulary.created", subject_id=Flag.objects.get(key="client_money").id).exists())
        # Approving twice is an invalid transition.
        twice = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(twice.status_code, 409)
        self.assertEqual(twice.json()["code"], "invalid_transition")

    def test_pro_s6(self) -> None:
        """PRO-S6

        A retried submission with the same Idempotency-Key creates one proposal (PRO-01).
        """
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        agent = {"HTTP_X_API_KEY": key.plain_key, "HTTP_IDEMPOTENCY_KEY": "run-42-flag-7"}
        body = self._flag_proposal()
        first = self._post("/proposals", body, agent)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["origin"], "agent")
        self.assertIsNone(first.json()["proposedBy"])
        second = self._post("/proposals", body, agent)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(Proposal.objects.filter(idempotency_key="run-42-flag-7").count(), 1)
        conflict = self._post("/proposals", {**body, "title": "Something else"}, agent)
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(conflict.json()["code"], "idempotency_conflict")
        # Without the scope the key is refused; an unknown kind is refused with the valid keys.
        no_scope = factories.api_key(self.tenant, scopes=("changes:write",))
        self.assertEqual(self._post("/proposals", body, {"HTTP_X_API_KEY": no_scope.plain_key}).status_code, 403)
        unknown = self._post("/proposals", {**body, "kind": "new_planet"}, agent)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(unknown.json()["code"], "unknown_key")
        self.assertIn("vocabulary_create", unknown.json()["detail"])
        bad_payload = self._post("/proposals", {**body, "payload": {"list": "flag"}}, {"HTTP_X_API_KEY": key.plain_key})
        self.assertEqual(bad_payload.status_code, 422)
        self.assertEqual(bad_payload.json()["code"], "validation_error")
        # The queue lists it for the editor, filtered by status and kind.
        editor = sign_in(self.editor)
        listed = self.client.get(f"{V1}/proposals?status=open&kind=vocabulary_create", **editor)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.json()["total"], 1)
        detail = self.client.get(f"{V1}/proposals/{first.json()['id']}", **editor)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["payload"]["key"], "client_money")
        # The vocabulary screen's "Suggested" tab: open proposals that would add to one list.
        suggested = self.client.get(f"{V1}/proposals?status=open&kind=vocabulary_create,term_create&targetList=flag", **editor)
        self.assertEqual(suggested.status_code, 200, suggested.content)
        self.assertEqual([p["payload"]["key"] for p in suggested.json()["items"]], ["client_money"])
        self.assertEqual(self.client.get(f"{V1}/proposals?targetList=urgency", **editor).json()["total"], 0)
        self.assertEqual(self.client.get(f"{V1}/proposals?status=approved,rejected", **editor).json()["total"], 0)
        with self.assertNumQueries(PROPOSAL_QUEUE_QUERIES):
            self.client.get(f"{V1}/proposals", **editor)

    @skip("pending: PRO-S7 (PRO-03, chunk 4: library updates and problem reports)")
    def test_pro_s7(self) -> None:
        """PRO-S7

        The queue is in the console and tenants see updates and report problems (PRO-03).
        """

    @skip("pending: PRO-S8 (PRO-04, R2)")
    def test_pro_s8(self) -> None:
        """PRO-S8

        A batch proposal previews and is approved whole or row by row (PRO-04).
        """

    def test_pro_s9(self) -> None:
        """PRO-S9

        A rejection needs a reason and is audited (PRO-01).
        """
        officer = sign_in(self.officer, tenant=self.tenant)
        proposal = self._post("/vocab/flag", {"labels": {"en": "Client money"}}, officer).json()["proposal"]
        editor = sign_in(self.editor)
        without = self._post(f"/proposals/{proposal['id']}/reject", {"rejectionCode": "duplicate", "note": "  "}, editor)
        self.assertEqual(without.status_code, 422, without.content)
        self.assertEqual(without.json()["code"], "reason_required")
        no_code = self._post(f"/proposals/{proposal['id']}/reject", {"rejectionCode": "", "note": "We have this already."}, editor)
        self.assertEqual(no_code.status_code, 422)
        rejected = self._post(f"/proposals/{proposal['id']}/reject", {"rejectionCode": "duplicate", "note": "We have this already."}, editor)
        self.assertEqual(rejected.status_code, 200, rejected.content)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertEqual(rejected.json()["rejectionCode"], "duplicate")
        self.assertEqual(rejected.json()["reviewNote"], "We have this already.")
        self.assertFalse(Flag.objects.filter(key="client_money").exists())
        event = AuditEvent.objects.get(action="proposal.rejected", subject_id=proposal["id"])
        self.assertEqual(event.after["rejectionCode"], "duplicate")
        self.assertEqual(event.actor_id, self.editor.id)
        # The proposer is told: an outbox event carries the topic the notifier delivers.
        self.assertTrue(event.outbox_events.filter(topic="proposal.rejected").exists())
        # A rejected proposal cannot be approved afterwards.
        again = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "invalid_transition")

    @skip("pending: PRO-S10 (INV-08, chunks 4 and 5)")
    def test_pro_s10(self) -> None:
        """PRO-S10

        Licensed text and extra obligations never enter a standard (INV-08, PRO-01, PRO-02).
        """

    @skip("pending: PRO-S11 (INV-08, chunk 4)")
    def test_pro_s11(self) -> None:
        """PRO-S11

        A standard term never sits on a law's obligation (FP-01, INV-08).
        """

    @skip("pending: PRO-S12 (INV-07, PRO-03, chunk 13)")
    def test_pro_s12(self) -> None:
        """PRO-S12

        A private proposal is approved inside the bank and never reaches the console (INV-07, PRO-03).
        """
