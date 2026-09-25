"""A proposal owned by a bank, and the bank's own queue declared (INV-07, PRO-03, OWN-03;
D-57, D-89, ADR 0050, ADR 0059; d89-proposal-owner).

The owner is the server's to set: `logic.create` takes it from the target, from the bank
the database is scoped to when the server files the bank's own new record (the filing
session's, or in the worker the run's), and never from a request body. Row-level security
on `proposal` then keeps an owned row out of the console, which runs with no tenant, and
out of every other bank; the policy's own proofs as cw_app are apps/shared/tests_rls.py. The
bank's own queue is declared behind its real gate, `private_records.approve` with a step-up
on approval, and answers 501 once it has loaded the proposal under row-level security.

A test client's requests share one transaction here, so a console request after a bank's
starts with `tenancy.clear_tenant()`, the zone a console request has in production.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase

from apps.identity import api_keys_logic
from apps.library import testing as library_build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalTenant
from apps.proposals.tests_kinds import instrument_body
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.tenancy import tenant_task
from apps.shared.testing import sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
SOURCE = "https://www.fi.se/"

# `proposal_four_eyes` as proposals 0001 and 0003 left it, which this package does not touch.
FOUR_EYES_CHECK = (
    "CHECK ((((reviewed_by_id IS NULL) OR (proposed_by_user_id IS NULL) OR (reviewed_by_id <> proposed_by_user_id)) "
    "AND ((reviewed_by_api_key_id IS NULL) OR (proposed_by_api_key_id IS NULL) OR (reviewed_by_api_key_id <> proposed_by_api_key_id)) "
    "AND ((reviewed_by_agent_id IS NULL) OR (proposed_by_agent_id IS NULL) OR (reviewed_by_agent_id <> proposed_by_agent_id)) "
    "AND ((reviewed_by_api_key_id IS NULL) OR (reviewed_by_agent_id IS NOT NULL))))"
)


def _instrument(key: str) -> dict[str, Any]:
    """A new instrument as `logic.create` takes it, every fact sourced."""
    body = instrument_body(key=key, officialRef=key.upper(), shortName=key.upper())
    return {
        "kind": body["kind"],
        "title": body["title"],
        "payload": body["payload"],
        "field_sources": body["fieldSources"],
        "source_label": body["sourceLabel"],
        "source_url": body["sourceUrl"],
    }


class OwnedProposalTestCase(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        seed_authorities()
        tenancy.clear_tenant()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.bank = factories.tenant(slug="own-a")
        self.officer = factories.member_user(self.bank, roles=("compliance_officer",))
        self.approver = factories.member_user(self.bank, roles=("approver",))
        self.reader = factories.member_user(self.bank, roles=("reader",))
        self.other_bank = factories.tenant(slug="own-b")
        self.other_approver = factories.member_user(self.other_bank, roles=("approver",))

    def _person(self, user: Any) -> logic.Proposer:
        return logic.Proposer(actor=factories.user_actor(user_id=user.id), user=user)

    def _owned(self, tenant: Any, user: Any, key: str = "own-instrument-1") -> Proposal:
        """The bank's own new instrument, filed by `user` inside `tenant`."""
        tenancy.activate(tenant.id)
        proposal, _ = logic.create(proposer=self._person(user), private=True, **_instrument(key))
        return proposal

    def _get(self, path: str, headers: dict[str, Any]) -> Any:
        return self.client.get(f"{V1}{path}", **headers)

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _refused(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)


class TheServerSetsTheOwner(OwnedProposalTestCase):
    def test_the_bank_s_own_new_record_belongs_to_the_filing_session_s_bank(self) -> None:
        proposal = self._owned(self.bank, self.officer)
        self.assertEqual(proposal.owner_tenant_id, self.bank.id)
        self.assertTrue(proposal.proposed_in_tenant)
        self.assertEqual(list(ProposalTenant.objects.filter(proposal=proposal).values_list("tenant_id", flat=True)), [self.bank.id])
        self.assertEqual(AuditEvent.objects.get(action="proposal.created", subject_id=proposal.id).tenant_id, self.bank.id)

    def test_in_the_worker_it_belongs_to_the_run_s_bank(self) -> None:
        @tenant_task
        def file_finding(tenant_id: uuid.UUID) -> Proposal:
            proposal, _ = logic.create(proposer=logic.Proposer(actor=factories.agent_actor()), private=True, **_instrument("own-found-1"))
            return proposal

        tenancy.clear_tenant()
        proposal = file_finding(self.other_bank.id)
        self.assertEqual(proposal.owner_tenant_id, self.other_bank.id)

    def test_a_private_filing_needs_a_bank_and_a_new_record(self) -> None:
        tenancy.clear_tenant()
        with self.assertRaises(ValidationError) as no_bank:
            logic.create(proposer=self._person(self.editor), private=True, **_instrument("own-console-1"))
        self.assertEqual(no_bank.exception.code, "validation_error")
        tenancy.activate(self.bank.id)
        with self.assertRaises(ValidationError) as a_list_row:
            logic.create(
                kind="vocabulary_create",
                title="Add the flag Client money",
                payload={"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
                proposer=self._person(self.officer),
                private=True,
            )
        self.assertEqual(a_list_row.exception.code, "validation_error")
        self.assertFalse(Proposal.objects.exists())

    def test_a_body_naming_an_owner_changes_nothing(self) -> None:
        officer = sign_in(self.officer, tenant=self.bank)
        body = instrument_body(key="own-body-1", officialRef="OWN-BODY-1", shortName="OWN-BODY-1")
        self._refused(self._post("/proposals", {**body, "ownerTenantId": str(self.bank.id)}, officer), 422, "validation_error")
        self.assertFalse(Proposal.objects.exists())
        # Without it, the bank's member files to the shared library, as before.
        filed = self._post("/proposals", body, officer)
        self.assertEqual(filed.status_code, 201, filed.content)
        self.assertIsNone(Proposal.objects.get(pk=filed.json()["id"]).owner_tenant_id)

    def test_a_proposal_against_a_shared_record_stays_shared_and_the_console_lists_it(self) -> None:
        obligation = library_build.obligation(library_build.instrument(key="shared-law-1", regime="regime:securities"), key="obl-shared-1")
        tenancy.activate(self.bank.id)
        proposal, _ = logic.create(
            kind="new_obligation_version",
            title="Version 2 of the shared duty",
            payload={"summaries": {"en": "The institution assesses the client."}, "originalLanguage": "en", "effectiveFrom": "2027-01-01"},
            field_sources={"summaries.en": SOURCE, "effectiveFrom": SOURCE},
            target_type="obligation",
            target_id=obligation.id,
            proposer=self._person(self.officer),
        )
        self.assertIsNone(proposal.owner_tenant_id)
        owned = self._owned(self.bank, self.officer)
        editor = sign_in(self.editor)
        listed = [row["id"] for row in self._get("/proposals", editor).json()["items"]]
        self.assertIn(str(proposal.id), listed)
        self.assertNotIn(str(owned.id), listed)

    def test_a_retry_key_reused_where_its_proposal_cannot_be_read_is_a_conflict(self) -> None:
        both = factories.member(self.other_bank, roles=("compliance_officer",), user_row=self.officer).user
        tenancy.activate(self.bank.id)
        logic.create(proposer=self._person(both), private=True, idempotency_key="retry-1", **_instrument("own-retry-1"))
        tenancy.activate(self.other_bank.id)
        with self.assertRaises(ValidationError) as caught:
            logic.create(proposer=self._person(both), private=True, idempotency_key="retry-1", **_instrument("own-retry-1"))
        self.assertEqual(caught.exception.code, "idempotency_conflict")


class TheConsoleNeverSeesAnOwnedProposal(OwnedProposalTestCase):
    def test_the_queue_leaves_it_out_and_its_fetch_answers_404(self) -> None:
        owned = self._owned(self.bank, self.officer)
        tenancy.clear_tenant()
        editor = sign_in(self.editor)
        self.assertNotIn(str(owned.id), [row["id"] for row in self._get("/proposals", editor).json()["items"]])
        self._refused(self._get(f"/proposals/{owned.id}", editor), 404, "not_found")
        self._refused(self._post(f"/proposals/{owned.id}/approve", {}, sign_in(self.editor, step_up=True)), 404, "not_found")
        self.assertFalse(Proposal.objects.filter(pk=owned.id).exists(), "the console's own connection reads no owned row")


class TheBanksOwnQueueIsDeclared(OwnedProposalTestCase):
    def test_the_list_answers_behind_its_gate_and_then_not_built(self) -> None:
        self._refused(self.client.get(f"{V1}/private-proposals"), 401, "unauthenticated")
        self._refused(self._get("/private-proposals", sign_in(self.reader, tenant=self.bank)), 403, "permission_denied")
        self._refused(self._get("/private-proposals", sign_in(self.editor)), 403, "permission_denied")
        self._refused(self._get("/private-proposals", sign_in(self.approver, tenant=self.bank)), 501, "not_built")

    def test_approve_answers_behind_its_gate_under_row_level_security_and_then_not_built(self) -> None:
        owned = self._owned(self.bank, self.officer)
        body = {"note": "Checked against the regulation."}
        path = f"/private-proposals/{owned.id}/approve"
        self._refused(self._post(path, body, sign_in(self.reader, tenant=self.bank, step_up=True)), 403, "permission_denied")
        self._refused(self._post(path, body, sign_in(self.editor, step_up=True)), 403, "permission_denied")
        self._refused(self._post(path, body, sign_in(self.approver, tenant=self.bank)), 403, "step_up_required")
        self._refused(self._post(path, body, sign_in(self.other_approver, tenant=self.other_bank, step_up=True)), 404, "not_found")
        approver = sign_in(self.approver, tenant=self.bank, step_up=True)
        self._refused(self._post(f"/private-proposals/{uuid.uuid4()}/approve", body, approver), 404, "not_found")
        self._refused(self._post("/private-proposals/not-a-uuid/approve", body, approver), 404, "not_found")
        self._refused(self._post(path, {**body, "payloadOverrides": {}}, approver), 422, "validation_error")
        self._refused(self._post(path, body, approver), 501, "not_built")

    def test_a_shared_proposal_is_not_the_bank_s_own(self) -> None:
        tenancy.activate(self.bank.id)
        shared, _ = logic.create(proposer=self._person(self.officer), **_instrument("shared-filed-1"))
        self.assertIsNone(shared.owner_tenant_id)
        approver = sign_in(self.approver, tenant=self.bank, step_up=True)
        self._refused(self._post(f"/private-proposals/{shared.id}/approve", {}, approver), 404, "not_found")
        self._refused(self._post(f"/private-proposals/{shared.id}/reject", {"rejectionCode": "duplicate", "note": "Held."}, approver), 404, "not_found")

    def test_reject_answers_behind_its_gate_under_row_level_security_and_then_not_built(self) -> None:
        owned = self._owned(self.bank, self.officer)
        body = {"rejectionCode": "duplicate", "note": "We already hold this as our own."}
        path = f"/private-proposals/{owned.id}/reject"
        self._refused(self._post(path, body, sign_in(self.reader, tenant=self.bank)), 403, "permission_denied")
        self._refused(self._post(path, body, sign_in(self.other_approver, tenant=self.other_bank)), 404, "not_found")
        self._refused(self._post(path, body, sign_in(self.approver, tenant=self.bank)), 501, "not_built")


class ThePermissionIsTheBanksAlone(TestCase):
    def test_compliance_officer_and_approver_hold_it_and_nothing_of_the_platform(self) -> None:
        holders = sorted(role for role, granted in perms.SYSTEM_ROLES.items() if perms.PRIVATE_RECORDS_APPROVE in granted)
        self.assertEqual(holders, ["approver", "compliance_officer"])
        self.assertIn(perms.PRIVATE_RECORDS_APPROVE, perms.TENANT_PERMISSIONS)
        self.assertIn(perms.PRIVATE_RECORDS_APPROVE, perms.APPROVE_PERMISSIONS)
        self.assertNotIn(perms.PRIVATE_RECORDS_APPROVE, perms.PLATFORM_PERMISSIONS)

    def test_no_api_key_is_given_it_as_a_scope(self) -> None:
        self.assertNotIn(perms.PRIVATE_RECORDS_APPROVE, perms.ALL_SCOPES)
        bank = factories.tenant(slug="own-keys")
        admin = factories.member_user(bank, roles=("admin",))
        with self.assertRaises(ValidationError) as caught:
            api_keys_logic.create_api_key(
                tenant=bank,
                actor=factories.user_actor(user_id=admin.id),
                created_by=admin,
                name="Private approver",
                scopes=[perms.PRIVATE_RECORDS_APPROVE],
                expires_at=None,
                step_up_assertion_id=None,
            )
        self.assertEqual(caught.exception.code, "unknown_key")

    def test_the_four_eyes_constraint_is_unchanged(self) -> None:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'proposal_four_eyes'")
            self.assertEqual(cursor.fetchone(), (FOUR_EYES_CHECK,))
