"""The bank's own queue, decided (INV-07, OWN-03, PRO-03; D-57, ADR 0050, ADR 0059;
d89-private-records).

`GET /private-proposals`, `POST /private-proposals/{id}/approve` and `/reject` under
`private_records.approve`: the list holds the bank's own open proposals and nothing else, the
approval takes a fresh passkey and never the proposer, a rejection takes a reason, and each
decision's audit and outbox rows are written in the bank's zone with the passkey assertion
and without the note. The console, another bank, a support session and every API key are
kept out. The gates and the 404 under row-level security were declared by d89-proposal-owner
(tests_private_contract.py); this module proves what the routes now do.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.identity.models import StepUpAssertion
from apps.library.models import Instrument
from apps.proposals.models import Proposal, ProposalStatus
from apps.proposals.tests_apply_private import PrivateRecordsCase
from apps.proposals.tests_kinds import instrument_body
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import sign_in
from apps.shared.tests_support_session import grant

V1 = "/api/v1"
NOTE = "Checked against the authority's page on outsourcing, section four."


class QueueRoutesCase(PrivateRecordsCase):
    def get(self, path: str, headers: dict[str, Any]) -> Any:
        return self.client.get(f"{V1}{path}", **headers)

    def post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def problem(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)

    def approver_session(self, step_up: bool = True) -> dict[str, Any]:
        return sign_in(self.approver, tenant=self.bank, step_up=step_up)

    def in_bank(self) -> None:
        tenancy.activate(self.bank.id)


class TheList(QueueRoutesCase):
    def test_it_holds_the_bank_s_own_open_proposals_oldest_first(self) -> None:
        first = self.own_instrument("own-list-1")
        mine = self.file(_instrument_body("own-list-2"), by=self.person(self.approver))
        decided = self.own_instrument("own-list-3")
        self.approve(decided, by=self.officer)
        shared = self.file(_instrument_body("shared-list-1"), by=self.person(self.officer), private=False)
        elsewhere = self.own_instrument_in(self.other_bank, "other-list-1")

        response = self.get("/private-proposals", self.approver_session(step_up=False))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([row["id"] for row in body["items"]], [str(first.id), str(mine.id)])
        self.assertEqual(body["total"], 2)
        rows = {row["id"]: row for row in body["items"]}
        self.assertEqual((rows[str(first.id)]["origin"], rows[str(first.id)]["isMine"]), ("agent", False))
        self.assertEqual((rows[str(mine.id)]["origin"], rows[str(mine.id)]["isMine"]), ("user", True))
        self.assertEqual(rows[str(first.id)]["status"], "open")
        self.assertNotIn(str(shared.id), rows)
        self.assertNotIn(str(elsewhere.id), rows)

    def test_it_pages(self) -> None:
        for n in range(3):
            self.own_instrument(f"own-page-{n}")
        page = self.get("/private-proposals?limit=2&offset=2", self.approver_session(step_up=False)).json()
        self.assertEqual((len(page["items"]), page["total"]), (1, 3))

    def own_instrument_in(self, tenant: Any, key: str) -> Proposal:
        return self.file(_instrument_body(key), tenant=tenant)


class Approving(QueueRoutesCase):
    def test_the_proposer_is_refused_by_four_eyes(self) -> None:
        proposal = self.file(_instrument_body("own-4e-1"), by=self.person(self.officer))
        officer = sign_in(self.officer, tenant=self.bank, step_up=True)
        self.problem(self.post(f"/private-proposals/{proposal.id}/approve", {}, officer), 409, "four_eyes_violation")
        self.in_bank()
        self.assertEqual(Proposal.objects.get(pk=proposal.id).status, ProposalStatus.OPEN.value)
        self.assertFalse(Instrument.objects.filter(stable_key="own-4e-1").exists())

    def test_a_second_person_approves_with_a_passkey_and_the_bank_zone_holds_the_trail(self) -> None:
        proposal = self.own_instrument("own-ok-1")
        response = self.post(f"/private-proposals/{proposal.id}/approve", {"note": NOTE}, self.approver_session())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["id"], response.json()["status"]), (str(proposal.id), "approved"))

        self.in_bank()
        instrument = Instrument.objects.get(stable_key="own-ok-1")
        self.assertEqual(instrument.owner_tenant_id, self.bank.id)
        stored = Proposal.objects.get(pk=proposal.id)
        self.assertEqual((stored.reviewed_by_id, stored.review_note), (self.approver.id, NOTE))
        assertion = StepUpAssertion.objects.filter(session__user=self.approver).order_by("created_at").last()
        assert assertion is not None
        for action, subject in (("proposal.approved", proposal.id), ("instrument.created", instrument.id)):
            event = AuditEvent.objects.get(action=action, subject_id=subject)
            self.assertEqual(event.tenant_id, self.bank.id, action)
            self.assertEqual(event.step_up_assertion_id, assertion.id, action)
            self.assertEqual(event.actor_id, self.approver.id, action)
            self.assertNotIn(NOTE, json.dumps([event.before, event.after]), action)
        outbox = OutboxEvent.objects.filter(topic="proposal.approved")
        self.assertEqual([row.tenant_id for row in outbox], [self.bank.id])
        self.assertNotIn(NOTE, json.dumps([row.payload for row in outbox]))

    def test_a_decided_proposal_is_not_decided_again(self) -> None:
        proposal = self.own_instrument("own-twice-1")
        self.assertEqual(self.post(f"/private-proposals/{proposal.id}/approve", {}, self.approver_session()).status_code, 200)
        officer = sign_in(self.officer, tenant=self.bank, step_up=True)
        self.problem(self.post(f"/private-proposals/{proposal.id}/approve", {}, officer), 409, "invalid_transition")
        self.problem(
            self.post(f"/private-proposals/{proposal.id}/reject", {"rejectionCode": "duplicate", "note": NOTE}, officer),
            409,
            "invalid_transition",
        )


class Rejecting(QueueRoutesCase):
    def test_a_rejection_without_a_reason_changes_nothing(self) -> None:
        proposal = self.own_instrument("own-no-1")
        session = self.approver_session(step_up=False)
        for body in ({}, {"note": NOTE}, {"rejectionCode": "duplicate"}, {"rejectionCode": "not-a-reason", "note": NOTE}):
            with self.subTest(body=body):
                self.problem(self.post(f"/private-proposals/{proposal.id}/reject", body, session), 422, "reason_required")
        self.in_bank()
        self.assertEqual(Proposal.objects.get(pk=proposal.id).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(action="proposal.rejected").exists())

    def test_a_rejection_with_a_reason_applies_nothing_and_is_audited_in_the_bank(self) -> None:
        proposal = self.own_instrument("own-no-2")
        response = self.post(
            f"/private-proposals/{proposal.id}/reject", {"rejectionCode": "duplicate", "note": NOTE}, self.approver_session(step_up=False)
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "rejected")
        self.in_bank()
        self.assertFalse(Instrument.objects.filter(stable_key="own-no-2").exists())
        event = AuditEvent.objects.get(action="proposal.rejected", subject_id=proposal.id)
        self.assertEqual((event.tenant_id, event.after["rejectionCode"]), (self.bank.id, "duplicate"))
        self.assertNotIn(NOTE, json.dumps([event.before, event.after]))
        outbox = OutboxEvent.objects.get(topic="proposal.rejected")
        self.assertEqual(outbox.tenant_id, self.bank.id)
        self.assertNotIn(NOTE, json.dumps(outbox.payload))

    def test_the_proposer_cannot_reject_their_own(self) -> None:
        proposal = self.file(_instrument_body("own-no-3"), by=self.person(self.officer))
        self.problem(
            self.post(f"/private-proposals/{proposal.id}/reject", {"rejectionCode": "duplicate", "note": NOTE}, sign_in(self.officer, tenant=self.bank)),
            409,
            "four_eyes_violation",
        )


class NobodyElseReachesIt(QueueRoutesCase):
    def test_another_bank_the_console_a_support_session_and_every_key_are_kept_out(self) -> None:
        proposal = self.own_instrument("own-out-1")
        approve, reject = f"/private-proposals/{proposal.id}/approve", f"/private-proposals/{proposal.id}/reject"
        reason = {"rejectionCode": "duplicate", "note": NOTE}

        other = sign_in(self.other_approver, tenant=self.other_bank, step_up=True)
        self.problem(self.post(approve, {}, other), 404, "not_found")
        self.problem(self.post(reject, reason, other), 404, "not_found")
        self.assertEqual(self.get("/private-proposals", other).json()["items"], [])

        console = sign_in(self.editor, step_up=True)
        self.problem(self.get(f"/proposals/{proposal.id}", console), 404, "not_found")
        self.problem(self.post(approve, {}, console), 403, "permission_denied")

        platform = factories.platform_user()
        row = grant(self.bank, platform, factories.member_user(self.bank, roles=("admin",)))
        entered = self.client.post(f"{V1}/console/support-access/{row.id}/enter", **sign_in(platform, tenant=None, step_up=True))
        support = {"HTTP_AUTHORIZATION": f"Bearer {entered.json()['accessToken']}"}
        for path in ("/private-proposals", f"/proposals/{proposal.id}"):
            self.problem(self.get(path, support), 403, "support_read_only")
        self.problem(self.post(approve, {}, support), 403, "support_read_only")

        key = factories.api_key(self.bank, scopes=tuple(sorted(perms.TENANT_KEY_SCOPES)))
        for path, body in ((approve, {}), (reject, reason)):
            self.assertEqual(self.post(path, body, {"HTTP_X_API_KEY": key.plain_key}).status_code, 401)
        self.assertEqual(self.get("/private-proposals", {"HTTP_X_API_KEY": key.plain_key}).status_code, 401)

        self.in_bank()
        self.assertEqual(Proposal.objects.get(pk=proposal.id).status, ProposalStatus.OPEN.value)

    def test_an_unknown_id_is_404(self) -> None:
        self.problem(self.post(f"/private-proposals/{uuid.uuid4()}/approve", {}, self.approver_session()), 404, "not_found")


def _instrument_body(key: str) -> dict[str, Any]:
    return instrument_body(key=key, officialRef=key.upper(), shortName=key.upper())
