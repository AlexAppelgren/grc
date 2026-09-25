"""Deciding a batch proposal whole or row by row (PRO-04, PRO-S8; c11-proposal-batches-decide).

A second person holding `proposals.review` approves or rejects a batch's rows with a fresh
passkey. Approved rows rewrite their obligation's scope terms through `apply()`, inside the
proposal door, each with its own audit row holding the terms before and after and its
re-index; a rejected row names a live reason and changes nothing; one more audit row names
every row's outcome. All of it is one transaction. The proposer, and any agent, decides
nothing: the call answers before a single row moves.
"""

from __future__ import annotations

import ast
import inspect
import uuid
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, transaction
from django.test import TransactionTestCase

from apps.agents import testing as agents_testing
from apps.library import testing as library_build
from apps.library.models import ObligationTerm
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import apply, batch
from apps.proposals.logic import Proposer, Reviewer
from apps.proposals.models import Proposal, ProposalBatchRow, ProposalKind, ProposalStatus
from apps.proposals.schemas import ObligationScopePayload, ProposalBatchDecision
from apps.proposals.tests_batch import CUSTODY, RETAIL, V1, BatchTestCase, body, change
from apps.search.logic import reindex
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.shared.tests_library_db_guard import APP, as_the_app_role
from apps.shared.testing import sign_in
from apps.taxonomy.models import RejectionReason
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

ROW_ACTIONS = ("obligation.scope_changed", "proposal.batch_row_rejected")


class DecidingABatch(BatchTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")
        filed = self._file(body(*(change(obligation) for obligation in self.obligations)))
        self.assertEqual(filed.status_code, 201, filed.content)
        self.batch = Proposal.objects.get(pk=filed.json()["id"])
        self.rows = {row.subject_id: row for row in ProposalBatchRow.objects.filter(proposal=self.batch)}

    def _row(self, n: int) -> ProposalBatchRow:
        return self.rows[self.obligations[n].id]

    def _decide(self, data: dict[str, Any], headers: dict[str, Any] | None = None) -> Any:
        return self._post(f"/proposal-batches/{self.batch.id}/decide", data, headers if headers is not None else sign_in(self.reviewer, step_up=True))

    def _custody(self) -> set[uuid.UUID]:
        return set(ObligationTerm.objects.filter(term=library_build.term(CUSTODY)).values_list("obligation_id", flat=True))

    def _nothing_moved(self) -> None:
        self.assertEqual(self._custody(), set())
        self.assertEqual(set(ProposalBatchRow.objects.filter(proposal=self.batch).values_list("decision", flat=True)), {"pending"})
        self.assertEqual(Proposal.objects.get(pk=self.batch.pk).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(action__in=(*ROW_ACTIONS, "proposal.batch_decided")).exists())


class ApprovingAndRejectingRows(DecidingABatch):
    def test_two_rejected_and_the_rest_approved_change_ten_records_in_one_call(self) -> None:
        rejected = [self._row(0), self._row(1)]
        with mock.patch("apps.proposals.apply.reindex", wraps=reindex) as reindexed:
            response = self._decide(
                {
                    "rows": [{"rowId": str(row.id), "decision": "rejected", "rejectionCode": "wrong_scope"} for row in rejected],
                    "rest": "approved",
                    "note": "Two of these are the firm's own assets.",
                }
            )
        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        approved_ids = {obligation.id for obligation in self.obligations[2:]}
        self.assertEqual(answer["status"], "approved")
        self.assertEqual(
            {row["subjectId"]: (row["decision"], row["rejectionCode"]) for row in answer["rows"]},
            {str(o.id): ("rejected", "wrong_scope") if o.id not in approved_ids else ("approved", "") for o in self.obligations},
        )
        self.assertEqual({row["decidedBy"]["id"] for row in answer["rows"]}, {str(self.reviewer.id)})
        self.assertEqual(self._custody(), approved_ids)
        self.assertEqual({call.args[0] for call in reindexed.call_args_list}, approved_ids)
        # A rejected record keeps the scope it had; an approved one keeps its other terms.
        for obligation in self.obligations:
            terms = set(ObligationTerm.objects.filter(obligation=obligation).values_list("term__key", flat=True))
            self.assertEqual(terms, {"retail", "custody"} if obligation.id in approved_ids else {"retail"})
        stored = Proposal.objects.get(pk=self.batch.pk)
        self.assertEqual((stored.reviewed_by_id, stored.review_note), (self.reviewer.id, "Two of these are the firm's own assets."))
        self.assertIsNotNone(stored.applied_at)

        # One audit row per row, before and after, and one naming every row's outcome; every
        # one carries the passkey assertion that opened the door, and none carries the note.
        changed = AuditEvent.objects.filter(action="obligation.scope_changed")
        self.assertEqual({event.subject_id for event in changed}, approved_ids)
        for event in changed:
            self.assertEqual((event.before["terms"], event.after["terms"]), ([RETAIL], sorted([RETAIL, CUSTODY])))
            self.assertEqual(event.after["proposal"], str(self.batch.id))
        refused = AuditEvent.objects.filter(action="proposal.batch_row_rejected")
        self.assertEqual({event.subject_id for event in refused}, {row.subject_id for row in rejected})
        self.assertEqual({event.after["rejectionCode"] for event in refused}, {"wrong_scope"})
        outcome = AuditEvent.objects.get(action="proposal.batch_decided", subject_id=self.batch.id)
        self.assertEqual(
            {row["subjectId"]: row["decision"] for row in outcome.after["rows"]},
            {str(o.id): "approved" if o.id in approved_ids else "rejected" for o in self.obligations},
        )
        self.assertEqual((outcome.before["status"], outcome.after["status"]), ("open", "approved"))
        events = AuditEvent.objects.filter(action__in=(*ROW_ACTIONS, "proposal.batch_decided"))
        self.assertEqual(events.count(), 13)
        self.assertEqual(len({event.step_up_assertion_id for event in events}), 1)
        self.assertIsNotNone(events.first().step_up_assertion_id)  # type: ignore[union-attr]
        self.assertNotIn("firm's own assets", repr([(event.before, event.after) for event in events]))

    def test_a_removed_term_leaves_and_an_added_one_arrives(self) -> None:
        filed = self._file(body(change(self.obligations[0], add=(CUSTODY,), remove=(RETAIL,)), title="Swap the scope")).json()
        response = self._post(f"/proposal-batches/{filed['id']}/decide", {"rest": "approved"}, sign_in(self.reviewer, step_up=True))
        self.assertEqual(response.status_code, 200, response.content)
        terms = set(ObligationTerm.objects.filter(obligation=self.obligations[0]).values_list("term__key", flat=True))
        self.assertEqual(terms, {"custody"})
        event = AuditEvent.objects.get(action="obligation.scope_changed", subject_id=self.obligations[0].id)
        self.assertEqual((event.before["terms"], event.after["terms"]), ([RETAIL], [CUSTODY]))

    def test_the_parent_closes_only_when_no_row_is_pending(self) -> None:
        first = self._decide({"rows": [{"rowId": str(self._row(0).id), "decision": "approved"}]})
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["status"], "open")
        self.assertEqual(self._custody(), {self.obligations[0].id})
        self.assertEqual(AuditEvent.objects.get(action="proposal.batch_decided").after["status"], "open")
        again = self._decide({"rows": [{"rowId": str(self._row(0).id), "decision": "rejected", "rejectionCode": "wrong_scope"}]})
        self._refused(again, 409, "invalid_transition")
        rest = self._decide({"rest": "rejected", "restRejectionCode": "duplicate"})
        self.assertEqual(rest.status_code, 200, rest.content)
        self.assertEqual(rest.json()["status"], "approved", "one approved row makes the batch approved")
        self.assertEqual(self._custody(), {self.obligations[0].id})
        self._refused(self._decide({"rest": "approved"}), 409, "invalid_transition")

    def test_rejecting_every_row_rejects_the_batch_and_changes_nothing(self) -> None:
        response = self._decide({"rest": "rejected", "restRejectionCode": "not_relevant"})
        self.assertEqual(response.status_code, 200, response.content)
        stored = Proposal.objects.get(pk=self.batch.pk)
        self.assertEqual((stored.status, stored.rejection_code, stored.applied_at), ("rejected", "not_relevant", None))
        self.assertEqual(self._custody(), set())
        self.assertEqual(AuditEvent.objects.filter(action="proposal.batch_row_rejected").count(), 12)

    def test_a_failure_part_way_leaves_no_record_changed(self) -> None:
        calls = {"n": 0}

        def failing(obligation_id: uuid.UUID) -> None:
            calls["n"] += 1
            if calls["n"] == 5:
                raise RuntimeError("the index is down")
            reindex(obligation_id)

        tenancy.clear_tenant()
        reviewer = Reviewer(actor=Actor(kind=ActorType.USER, id=self.reviewer.id, label=self.reviewer.name), user=self.reviewer)
        with mock.patch("apps.proposals.apply.reindex", side_effect=failing), self.assertRaises(RuntimeError):
            batch.decide(proposal=self.batch, decision=ProposalBatchDecision(rest="approved"), reviewer=reviewer, step_up_assertion_id=uuid.uuid4())
        self._nothing_moved()


class WhoDecides(DecidingABatch):
    def test_the_proposer_is_refused_before_anything_is_decided(self) -> None:
        self._refused(self._decide({"rest": "approved"}, sign_in(self.editor, step_up=True)), 409, "four_eyes_violation")
        self._nothing_moved()

    def test_a_person_decides_only_with_a_fresh_passkey_and_the_permission(self) -> None:
        self._refused(self._decide({"rest": "approved"}, sign_in(self.reviewer)), 403, "step_up_required")
        admin = factories.platform_user(roles=("platform_admin",))
        self._refused(self._decide({"rest": "approved"}, sign_in(admin, step_up=True)), 403, "permission_denied")
        tenant = factories.tenant(slug="bank")
        officer = factories.member(tenant, roles=("compliance_officer",)).user
        self.assertEqual(self._decide({"rest": "approved"}, sign_in(officer, tenant=tenant, step_up=True)).status_code, 403)
        tenancy.clear_tenant()
        self._refused(
            self._post(f"/proposal-batches/{uuid.uuid4()}/decide", {"rest": "approved"}, sign_in(self.reviewer, step_up=True)), 404, "not_found"
        )
        self._nothing_moved()

    def test_no_agent_key_decides_a_batch(self) -> None:
        """A key never reaches the route (the library's writing routes take a person's
        session alone), and the logic refuses an agent reviewer on its own with 409
        `person_review_required`: who decides a re-tag batch is a person."""
        key = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_REVIEW,))
        self.assertEqual(self._decide({"rest": "approved"}, {"HTTP_X_API_KEY": key.plain_key}).status_code, 401)
        tenancy.clear_tenant()
        agent = Reviewer(actor=Actor(kind=ActorType.AGENT, id=key.agent.id, label="confirmer"), api_key_id=key.id, agent_id=key.agent.id)
        with self.assertRaises(ValidationError) as refused:
            batch.decide(proposal=self.batch, decision=ProposalBatchDecision(rest="approved"), reviewer=agent, step_up_assertion_id=None)
        self.assertEqual(refused.exception.code, "person_review_required")
        self._nothing_moved()


class WhatADecisionMustSay(DecidingABatch):
    def test_a_rejection_needs_a_live_reason_row(self) -> None:
        with library_write("test"):
            RejectionReason.objects.filter(key="duplicate").update(active=False)
        row = str(self._row(0).id)
        for case, data in (
            ("no reason", {"rows": [{"rowId": row, "decision": "rejected"}]}),
            ("a reason the list does not hold", {"rows": [{"rowId": row, "decision": "rejected", "rejectionCode": "because"}]}),
            ("a retired reason", {"rows": [{"rowId": row, "decision": "rejected", "rejectionCode": "duplicate"}]}),
            ("the rest rejected without a reason", {"rest": "rejected"}),
        ):
            with self.subTest(case=case):
                self._refused(self._decide(data), 422, "reason_required")
        self._nothing_moved()

    def test_a_malformed_decision_is_refused_whole(self) -> None:
        row = str(self._row(0).id)
        for case, data, status, code in (
            ("nothing to decide", {}, 422, "validation_error"),
            ("an unknown decision", {"rows": [{"rowId": row, "decision": "maybe"}]}, 422, "validation_error"),
            ("an unknown rest", {"rest": "pending"}, 422, "validation_error"),
            ("a reason on an approval", {"rows": [{"rowId": row, "decision": "approved", "rejectionCode": "wrong_scope"}]}, 422, "validation_error"),
            ("a reason on an approved rest", {"rest": "approved", "restRejectionCode": "wrong_scope"}, 422, "validation_error"),
            ("a row named twice", {"rows": [{"rowId": row, "decision": "approved"}, {"rowId": row, "decision": "approved"}]}, 422, "validation_error"),
            ("a row of no batch", {"rows": [{"rowId": str(uuid.uuid4()), "decision": "approved"}]}, 422, "unknown_key"),
        ):
            with self.subTest(case=case):
                self._refused(self._decide(data), status, code)
        self._nothing_moved()

    def test_a_stale_row_cannot_be_approved_and_does_not_stop_the_rest(self) -> None:
        with library_write("test"):
            ObligationTerm.objects.create(obligation=self.obligations[0], term=library_build.term("client_category:professional"))
        stale = self._row(0)
        named = self._decide({"rows": [{"rowId": str(stale.id), "decision": "approved"}], "rest": "approved"})
        self._refused(named, 409, "stale_write")
        self.assertEqual(self._custody(), set())
        rest = self._decide({"rest": "approved"})
        self.assertEqual(rest.status_code, 200, rest.content)
        self.assertEqual(rest.json()["status"], "open", "the stale row stays pending")
        self.assertEqual(self._custody(), {obligation.id for obligation in self.obligations[1:]})
        self.assertEqual(ProposalBatchRow.objects.get(pk=stale.pk).decision, "pending")
        closed = self._decide({"rows": [{"rowId": str(stale.id), "decision": "rejected", "rejectionCode": "wrong_scope"}]})
        self.assertEqual(closed.json()["status"], "approved")

    def test_a_retired_record_is_stale(self) -> None:
        with library_write("test"):
            type(self.obligations[0]).objects.filter(pk=self.obligations[0].pk).update(status="retired")
        self._refused(self._decide({"rows": [{"rowId": str(self._row(0).id), "decision": "approved"}]}), 409, "stale_write")


class EveryKindIsApplied(DecidingABatch):
    def test_every_proposal_kind_has_an_apply_branch(self) -> None:
        """A kind with no branch in `apply()` would be one the queue takes and no approval can
        write; `obligation_scope` is the re-tag a batch applies."""
        tree = ast.parse(inspect.getsource(apply.apply))
        branched = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "ProposalKind"
        }
        self.assertEqual(branched, {member.name for member in ProposalKind})

    def test_the_batch_answer_reads_as_filed_after_a_decision(self) -> None:
        self._decide({"rest": "approved"})
        read = self.client.get(f"{V1}/proposal-batches/{self.batch.id}", **sign_in(self.reviewer))
        self.assertEqual(read.status_code, 200, read.content)
        self.assertEqual({row["stale"] for row in read.json()["rows"]}, {False})


class ABatchWritesAsTheAppRole(TransactionTestCase):
    """The row writes above run as the schema owner, whom the library's trigger lets
    through; here the decision runs as cw_app, so the database's own door is what lets the
    re-tag in (the proposal door `apply()` opens)."""

    databases = {DEFAULT_DB_ALIAS, APP}

    def test_approved_rows_rewrite_the_scope_through_the_proposal_door(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_term_dimensions()
            seed_taxonomy_terms()
            seed_authorities()
        law = library_build.instrument(key="door-batch-act", regime="regime:securities")
        obligations = [library_build.obligation(law, key=f"door-batch-act/{n}", terms=(RETAIL,)) for n in range(2)]
        editor = factories.platform_user(roles=("library_editor",), email="door-editor@bleqq.test")
        reviewer = factories.platform_user(roles=("library_editor",), email="door-reviewer@bleqq.test")
        filed, _ = batch.create_batch(
            kind=ProposalKind.OBLIGATION_SCOPE.value,
            title="Re-tag through the door",
            payload=ObligationScopePayload.model_validate({"changes": [change(obligation) for obligation in obligations]}),
            proposer=Proposer(actor=Actor(kind=ActorType.USER, id=editor.id, label=editor.name), user=editor),
        )
        with as_the_app_role(), transaction.atomic():
            tenancy.clear_tenant()
            batch.decide(
                proposal=filed,
                decision=ProposalBatchDecision(rest="approved"),
                reviewer=Reviewer(actor=Actor(kind=ActorType.USER, id=reviewer.id, label=reviewer.name), user=reviewer),
                step_up_assertion_id=uuid.uuid4(),
            )
        custody = set(ObligationTerm.objects.filter(term=library_build.term(CUSTODY)).values_list("obligation_id", flat=True))
        self.assertEqual(custody, {obligation.id for obligation in obligations})
