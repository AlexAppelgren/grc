"""The one-person close and its way back (CAS-02, CAS-08; D-92, ADR 0060).

Alex's answer to q-case-close, "One person, audited" (2026-09-20): a case that needs no
work is closed on one person's word under `cases.work`, with a reason key of the
`no_action` or `not_applicable` kind, an audit row naming the person and the reason's key,
and a transition row carrying the note. The note stays on the case and its ledger and never
in an audit value. The case can be restored to triage; a case a second person signed off
cannot, and the sign-off route stays the only door a `signed_off` reason goes through.

The security half is `EveryDoorIntoClosed`: over the state machine's own tables, the only
edges into `closed` are the two one-person edges, which refuse a `signed_off` reason, and
the sign-off edge, which refuses the person who asked for it.

Proven to fail 2026-09-25 before `close_without_action` was built (501 `not_built`), and
with `ONE_PERSON_CLOSE` widened to `signed_off` (the four-eyes refusal answered 200).
"""

from __future__ import annotations

import uuid

from django.db import transaction

from apps.cases import state
from apps.cases import testing as case_build
from apps.cases.models import CaseTransition, ChangeCase
from apps.cases.tests_triage import CaseRoutes, triage_bank
from apps.shared import tenancy
from apps.shared.kinds import CaseStatusCategory, CloseReason
from apps.taxonomy.models import ClosureReason

C = CaseStatusCategory
NOTE = "Covered by the 2025 research policy review."


class CloseWithoutAction(CaseRoutes):
    def setUp(self) -> None:
        self.bank = triage_bank()
        case_build.in_category(self.bank.case, C.ASSIGNED)

    def test_one_person_closes_an_assigned_case_with_a_reason_and_a_note(self) -> None:
        response = self.move(self.bank, "close", {"reasonKey": "no_action", "note": NOTE})
        self.assertEqual(response.status_code, 200, response.content)
        case = response.json()
        self.assertEqual(case["status"], "closed")
        self.assertEqual(case["closeReason"]["key"], "no_action")
        self.assertEqual(case["closeReason"]["kind"], "no_action")
        self.assertEqual(case["closedNote"], NOTE)
        self.assertIsNotNone(case["closedAt"])
        self.assertIsNone(case["signedOffBy"], "nobody signed it off, and it never reads as if someone had")
        self.assertEqual(case["allowedTransitions"], ["new"])

        self.assertEqual(self.ledger(self.bank), [("assigned", "closed", self.bank.officer.id)])
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            self.assertEqual(CaseTransition.objects.get(case_id=self.bank.case.id).note, NOTE)
        audited = self.moves_audited(self.bank)
        self.assertEqual(len(audited), 1)
        self.assertEqual(audited[0].actor_id, self.bank.officer.id)
        self.assertEqual(audited[0].after["reasonKey"], "no_action")
        self.assertNotIn(NOTE, str(audited[0].before) + str(audited[0].after) + audited[0].summary, "tenant text stays out of the audit")

    def test_an_assessing_case_closes_as_not_applicable(self) -> None:
        case_build.in_category(self.bank.case, C.ASSESSING)
        response = self.move(self.bank, "close", {"reasonKey": "not_applicable"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["closeReason"]["kind"], "not_applicable")
        self.assertIsNone(response.json()["closedNote"], "no note written reads as none")

    def test_a_signed_off_reason_needs_a_second_person(self) -> None:
        response = self.move(self.bank, "close", {"reasonKey": "signed_off"})
        self.assertProblem(response, 409, "four_eyes_violation")
        case = self.case(self.bank)
        self.assertEqual(case.status, "assigned")
        self.assertIsNone(case.close_reason_id)
        self.assertEqual(self.ledger(self.bank), [])

    def test_a_bank_reason_of_the_no_action_kind_closes_too(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            ClosureReason.objects.create(tenant=self.bank.tenant, key="covered_elsewhere", kind=CloseReason.NO_ACTION.value)
        response = self.move(self.bank, "close", {"reasonKey": "covered_elsewhere"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["closeReason"]["kind"], "no_action")

    def test_an_unknown_or_missing_reason_is_422(self) -> None:
        body = self.assertProblem(self.move(self.bank, "close", {"reasonKey": "done"}), 422, "unknown_key")
        self.assertIn("no_action", body["validKeys"])
        self.assertProblem(self.move(self.bank, "close", {"note": NOTE}), 422, "validation_error")
        self.assertEqual(self.case(self.bank).status, "assigned")

    def test_only_an_assigned_or_assessing_case_closes_this_way(self) -> None:
        for category in (C.NEW, C.IMPLEMENTING, C.SIGNOFF, C.CLOSED, C.DISMISSED):
            with self.subTest(category=category.value):
                case_build.in_category(self.bank.case, category)
                self.assertProblem(self.move(self.bank, "close", {"reasonKey": "no_action"}), 409, "invalid_transition")

    def test_a_case_waiting_for_sign_off_is_never_closed_by_one_person(self) -> None:
        """The sign-off edge's guard reads who asked, not the reason: someone else closing
        it here without action would be a third door into `closed` (D-92)."""
        case_build.in_category(self.bank.case, C.SIGNOFF)
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            ChangeCase.objects.filter(pk=self.bank.case.id).update(signoff_requested_by=self.bank.owner)
        for reason in ("no_action", "not_applicable", "signed_off"):
            with self.subTest(reason=reason):
                self.assertProblem(self.move(self.bank, "close", {"reasonKey": reason}), 409, "invalid_transition")
        self.assertEqual(self.case(self.bank).status, "signoff")
        self.assertEqual(self.ledger(self.bank), [])

    def test_a_stale_close_is_409(self) -> None:
        self.assertProblem(self.move(self.bank, "close", {"reasonKey": "no_action"}, version=None), 409, "stale_write")
        self.assertEqual(self.case(self.bank).status, "assigned")


class RestoreAClose(CaseRoutes):
    def setUp(self) -> None:
        self.bank = triage_bank()
        case_build.in_category(self.bank.case, C.ASSIGNED)

    def test_a_one_person_close_is_restored_to_triage(self) -> None:
        self.assertEqual(self.move(self.bank, "close", {"reasonKey": "no_action", "note": NOTE}).status_code, 200)
        response = self.move(self.bank, "restore", None, who=self.bank.owner)
        self.assertEqual(response.status_code, 200, response.content)
        case = response.json()
        self.assertEqual(case["status"], "new")
        self.assertIsNone(case["closeReason"])
        self.assertIsNone(case["closedNote"])
        self.assertIsNone(case["closedAt"])
        self.assertEqual(
            self.ledger(self.bank),
            [("assigned", "closed", self.bank.officer.id), ("closed", "new", self.bank.owner.id)],
            "the close stays in the case's history",
        )

    def test_a_signed_off_close_stays_final(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            ChangeCase.objects.filter(pk=self.bank.case.id).update(
                status=C.CLOSED.value, close_reason=ClosureReason.objects.get(key="signed_off")
            )
        self.assertProblem(self.move(self.bank, "restore", None), 409, "invalid_transition")
        self.assertEqual(self.case(self.bank).status, "closed")


class EveryDoorIntoClosed(CaseRoutes):
    """No third door reaches `closed` (CHUNK9 q-case-close): proved over the machine's own
    tables, which every route's move goes through."""

    def facts(self, *, reason: CloseReason | None, requester: uuid.UUID | None = None, actor: uuid.UUID | None = None) -> state.CaseFacts:
        return state.CaseFacts(
            owner_set=True,
            reason_given=True,
            why_saved=True,
            open_action_count=0,
            clean_evidence_count=1,
            signoff_requester=requester,
            actor=actor,
            close_reason_kind=reason,
        )

    def test_the_only_edges_into_closed_are_the_one_person_close_and_sign_off(self) -> None:
        into_closed = {origin for origin, targets in state.TRANSITIONS.items() if C.CLOSED in targets}
        self.assertEqual(into_closed, {C.ASSIGNED, C.ASSESSING, C.SIGNOFF})

    def test_one_person_edges_refuse_a_signed_off_reason_and_no_reason(self) -> None:
        for origin in (C.ASSIGNED, C.ASSESSING):
            with self.subTest(origin=origin.value):
                for reason, code in ((CloseReason.SIGNED_OFF, "four_eyes_violation"), (None, "reason_required")):
                    with self.assertRaises(state.InvalidTransition) as refused:
                        state.check_transition(origin, C.CLOSED, self.facts(reason=reason))
                    self.assertEqual(refused.exception.code, code)
                for reason in (CloseReason.NO_ACTION, CloseReason.NOT_APPLICABLE):
                    state.check_transition(origin, C.CLOSED, self.facts(reason=reason))

    def test_the_sign_off_edge_refuses_the_person_who_asked(self) -> None:
        asker = uuid.uuid4()
        with self.assertRaises(state.InvalidTransition) as refused:
            state.check_transition(C.SIGNOFF, C.CLOSED, self.facts(reason=CloseReason.SIGNED_OFF, requester=asker, actor=asker))
        self.assertEqual(refused.exception.code, "four_eyes_violation")
        state.check_transition(C.SIGNOFF, C.CLOSED, self.facts(reason=CloseReason.SIGNED_OFF, requester=asker, actor=uuid.uuid4()))

    def test_only_a_one_person_close_is_restorable(self) -> None:
        for reason in CloseReason:
            with self.subTest(reason=reason.value):
                allowed = state.allowed_transitions(C.CLOSED, self.facts(reason=reason))
                self.assertEqual(allowed, [C.NEW] if reason in state.ONE_PERSON_CLOSE else [])
