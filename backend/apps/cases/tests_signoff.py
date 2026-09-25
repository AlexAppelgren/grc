"""Sign-off: the request and its two refusals, the second person's approval with a step-up,
and send-back (CAS-06, CAS-08, AC-CAS1, AC-ID3).

What is proved here beside the scenarios in `tests_scenarios.py`: evidence the scanner has
not passed never satisfies the request; the refusals carry their counts; the approvers and
only they are told, once each; `canRequestSignoff` is the guard's own answer on every
seeded case; the requester's approval is refused before a row is written, and the
database refuses it again on a direct write; the approval's audit row names the step-up
assertion; and a sign-off moves no library or register row.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cases import logic, responses, state
from apps.cases import testing as case_build
from apps.cases.models import Action, CaseTransition, ChangeCase, Evidence, EvidenceKind, ImpactAssessment
from apps.collab.models import Notification, NotificationKind
from apps.identity.models import StepUpAssertion
from apps.shared import factories, tenancy
from apps.shared.e2e_seed import seed_e2e
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent, OutboxEvent, Tenant
from apps.shared.tenancy import LibraryModel
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.watch import testing as watch_build

C = CaseStatusCategory
V1 = "/api/v1"


# ---------------------------------------------------------------------------------------
# Builders shared with tests_scenarios.py
# ---------------------------------------------------------------------------------------
class Bank:
    """One bank with a case in implementing: its owner holds `cases.work` and
    `cases.signoff` (so the self sign-off is reachable), a second person holds
    `cases.signoff`, and a reader holds neither."""

    def __init__(self) -> None:
        watch_build.seed_watch_reference()
        self.tenant = factories.tenant()
        self.owner = factories.member_user(self.tenant, roles=("compliance_officer", "approver"))
        self.approver = factories.member_user(self.tenant, roles=("approver",))
        self.reader = factories.member_user(self.tenant, roles=("reader",))
        self.case = case_build.case(self.tenant, watch_build.change(), owner=self.owner)
        case_build.in_category(self.case, C.IMPLEMENTING)

    def fresh(self) -> ChangeCase:
        tenancy.activate(self.tenant.id)
        return ChangeCase.objects.select_related(*logic.CASE_JOINS).get(pk=self.case.pk)

    def action(self, *, done: bool) -> Action:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            return Action.objects.create(
                tenant=self.tenant,
                case=self.case,
                title="Document the research criteria",
                owner=self.owner,
                due_date=timezone.localdate(),
                created_by=self.owner,
                done_at=timezone.now() if done else None,
                done_by=self.owner if done else None,
            )

    def evidence(self, scan_state: str) -> Evidence:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            return Evidence.objects.create(
                tenant=self.tenant,
                case=self.case,
                kind=EvidenceKind.LINK.value,
                name="FI decision memo",
                url="https://intranet.example.com/memo/42",
                uploaded_by=self.owner,
                scan_state=scan_state,
                scanned_at=None if scan_state == "pending" else timezone.now(),
            )

    def post(self, client: Any, move: str, who: Any, *, body: Any = None, version: int | None = None, step_up: bool = False) -> Any:
        headers = sign_in(who, tenant=self.tenant, step_up=step_up)
        if version is None:
            version = self.fresh().version
        return client.post(
            f"{V1}/changes/{self.case.change_id}/signoff/{move}",
            data=body if body is not None else {},
            content_type="application/json",
            HTTP_IF_MATCH=str(version),
            **headers,
        )

    def ready_for_signoff(self, client: Any) -> None:
        """Every action done, clean evidence, and the owner's request made."""
        self.action(done=True)
        self.evidence("clean")
        response = self.post(client, "request", self.owner)
        assert response.status_code == 200, response.content


def row_counts() -> dict[str, int]:
    """How many rows the case's own tables and the audit trail hold, for a refusal that
    must write nothing."""
    return {
        "change_case": ChangeCase.objects.count(),
        "case_transition": CaseTransition.objects.count(),
        # Signing in writes audit rows of its own; the case's are what a refusal must not.
        "audit_event": AuditEvent.objects.filter(subject_type=logic.SUBJECT_TYPE).count(),
        "outbox_event": OutboxEvent.objects.filter(audit_event__subject_type=logic.SUBJECT_TYPE).count(),
        "notification": Notification.objects.count(),
    }


def inventory_snapshot() -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every library model and every register model, whole, so any insert,
    update or delete during a call shows as a difference."""
    models: list[type[Any]] = [model for model in apps.get_models() if issubclass(model, LibraryModel)]
    models += list(apps.get_app_config("register").get_models())
    return {
        model._meta.label: sorted(tuple(map(str, row)) for row in model.objects.order_by().values_list())
        for model in models
    }


def guard_allows_request(case: ChangeCase) -> bool:
    """What `state.py` says about asking for sign-off on `case`, independently of any
    response."""
    try:
        state.check_transition(C(case.status), C.SIGNOFF, logic.case_facts(case, actor=None))
    except state.InvalidTransition:
        return False
    return True


# ---------------------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------------------
class RequestSignoff(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = Bank()

    def test_an_open_action_is_refused_with_the_count_and_nothing_is_written(self) -> None:
        self.bank.action(done=False)
        self.bank.action(done=False)
        self.bank.action(done=True)
        before = row_counts()
        response = self.bank.post(self.client, "request", self.bank.owner)
        self.assertEqual(response.status_code, 409)
        problem = response.json()
        self.assertEqual(problem["code"], "open_actions")
        self.assertEqual(problem["openActionCount"], 2)
        self.assertEqual(problem["cleanEvidenceCount"], 0)
        self.bank.fresh()
        self.assertEqual(row_counts(), before)
        case = self.bank.fresh()
        self.assertEqual(case.status, C.IMPLEMENTING.value)
        self.assertIsNone(case.signoff_requested_by_id)

    def test_no_evidence_is_refused_with_zero_beside_the_code(self) -> None:
        self.bank.action(done=True)
        response = self.bank.post(self.client, "request", self.bank.owner)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "evidence_missing")
        self.assertEqual(response.json()["cleanEvidenceCount"], 0)
        self.assertEqual(response.json()["openActionCount"], 0)

    def test_evidence_the_scanner_has_not_passed_does_not_count(self) -> None:
        for scan_state in ("pending", "infected", "error"):
            with self.subTest(scan_state=scan_state):
                self.bank.evidence(scan_state)
                response = self.bank.post(self.client, "request", self.bank.owner)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "evidence_missing")

    def test_removed_evidence_does_not_count(self) -> None:
        evidence = self.bank.evidence("clean")
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            Evidence.objects.filter(pk=evidence.pk).update(removed_at=timezone.now())
        response = self.bank.post(self.client, "request", self.bank.owner)
        self.assertEqual(response.json()["code"], "evidence_missing")

    def test_a_request_names_the_requester_moves_the_case_and_writes_its_trail(self) -> None:
        self.bank.evidence("clean")
        version = self.bank.fresh().version
        response = self.bank.post(self.client, "request", self.bank.owner, version=version)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], "signoff")
        self.assertEqual(body["signoffRequestedBy"]["id"], str(self.bank.owner.id))
        self.assertIsNotNone(body["signoffRequestedAt"])
        self.assertEqual(body["version"], version + 1)
        self.assertFalse(body["canRequestSignoff"])
        self.assertNotIn("closed", body["allowedTransitions"], "the requester reads no approval open to them")
        self.assertIn("implementing", body["allowedTransitions"])
        case = self.bank.fresh()
        moved = CaseTransition.objects.get(case=case, to_status="signoff")
        self.assertEqual((moved.from_status, moved.by_user_id), ("implementing", self.bank.owner.id))
        audit = AuditEvent.objects.get(subject_id=case.id, action=logic.MOVED, after__status="signoff")
        self.assertEqual(audit.actor_id, self.bank.owner.id)
        self.assertEqual(audit.after["status"], "signoff")

    def test_requesting_twice_is_an_invalid_transition(self) -> None:
        self.bank.evidence("clean")
        self.assertEqual(self.bank.post(self.client, "request", self.bank.owner).status_code, 200)
        response = self.bank.post(self.client, "request", self.bank.owner)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "invalid_transition")
        self.assertNotIn("openActionCount", response.json())

    def test_an_old_version_is_a_stale_write(self) -> None:
        self.bank.evidence("clean")
        stale = self.bank.fresh().version - 1
        response = self.bank.post(self.client, "request", self.bank.owner, version=stale)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_write")

    def test_the_approvers_are_told_once_each_and_nobody_else(self) -> None:
        second_approver = factories.member_user(self.bank.tenant, roles=("approver", "auditor"))
        departed = factories.member(self.bank.tenant, roles=("approver",))
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            type(departed).objects.filter(pk=departed.pk).update(deactivated_at=timezone.now())
        self.bank.evidence("clean")
        self.assertEqual(self.bank.post(self.client, "request", self.bank.owner).status_code, 200)
        self.bank.fresh()
        told = list(
            Notification.objects.filter(subject_id=self.bank.case.id, kind=NotificationKind.SIGNOFF_REQUESTED.value)
            .order_by("user_id")
            .values_list("user_id", flat=True)
        )
        self.assertEqual(sorted(told), sorted([self.bank.approver.id, second_approver.id]))
        self.assertNotIn(self.bank.owner.id, told, "the requester is never asked to sign off their own case")
        self.assertNotIn(self.bank.reader.id, told)
        self.assertNotIn(departed.user_id, told)

    def test_another_banks_case_is_404(self) -> None:
        other = Bank()
        self.bank.evidence("clean")
        response = self.client.post(
            f"{V1}/changes/{self.bank.case.change_id}/signoff/request",
            data={},
            content_type="application/json",
            HTTP_IF_MATCH="1",
            **sign_in(other.owner, tenant=other.tenant),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.bank.fresh().status, C.IMPLEMENTING.value)


# ---------------------------------------------------------------------------------------
# canRequestSignoff is the guard's answer
# ---------------------------------------------------------------------------------------
class CanRequestSignoffIsTheGuard(TestCase):
    def test_on_a_case_in_every_category_with_and_without_work_left(self) -> None:
        bank = Bank()
        for category in C:
            for actions, evidence in (((), ()), ((False,), ("clean",)), ((True,), ("pending",)), ((True,), ("clean",))):
                row = case_build.case(bank.tenant, watch_build.change(), owner=bank.owner)
                case_build.in_category(row, category)
                for done in actions:
                    Action.objects.create(
                        tenant=bank.tenant, case=row, title="A step", owner=bank.owner, due_date=timezone.localdate(),
                        created_by=bank.owner, done_at=timezone.now() if done else None, done_by=bank.owner if done else None,
                    )
                for scan_state in evidence:
                    Evidence.objects.create(
                        tenant=bank.tenant, case=row, kind=EvidenceKind.LINK.value, name="Memo", url="https://example.com/m",
                        uploaded_by=bank.owner, scan_state=scan_state, scanned_at=None if scan_state == "pending" else timezone.now(),
                    )
                case = ChangeCase.objects.select_related(*logic.CASE_JOINS).get(pk=row.pk)
                with self.subTest(category=category.value, actions=actions, evidence=evidence):
                    answer = responses.case_response(case, reader=bank.owner.id, order=["en"]).can_request_signoff
                    self.assertEqual(answer, guard_allows_request(case))
        self.assertTrue(
            any(guard_allows_request(case) for case in ChangeCase.objects.filter(tenant=bank.tenant)),
            "at least one built case can ask, so the comparison is not all-false",
        )


class TheAnswerCarriesTheAssessment(TestCase):
    def test_a_saved_assessment_is_in_the_case_a_move_answers(self) -> None:
        bank = Bank()
        ImpactAssessment.objects.create(
            tenant=bank.tenant, case=bank.case, why="Both desks pay for research.", saved=True, saved_by=bank.owner, saved_at=timezone.now()
        )
        answer = responses.case_response(bank.fresh(), reader=bank.owner.id, order=["en"])
        assert answer.assessment is not None
        self.assertEqual((answer.assessment.why, answer.assessment.applies, answer.assessment.effort), ("Both desks pay for research.", "yes", None))
        self.assertEqual(answer.assessment.saved_by.id if answer.assessment.saved_by else None, bank.owner.id)


@override_settings(E2E_MODE=True)
class CanRequestSignoffOnTheSeed(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_e2e()

    def test_equals_the_guard_on_every_seeded_case(self) -> None:
        seen = 0
        for tenant in Tenant.objects.order_by("slug"):
            tenancy.activate(tenant.id)
            for case in ChangeCase.objects.select_related(*logic.CASE_JOINS).filter(tenant=tenant):
                with self.subTest(tenant=tenant.slug, case=str(case.id), status=case.status):
                    answer = responses.case_response(case, reader=None, order=["en"]).can_request_signoff
                    self.assertEqual(answer, guard_allows_request(case))
                seen += 1
        self.assertGreater(seen, 0, "the seed carries cases to compare")


# ---------------------------------------------------------------------------------------
# The approval
# ---------------------------------------------------------------------------------------
class ApproveSignoff(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = Bank()
        self.bank.ready_for_signoff(self.client)

    def test_the_requester_is_refused_before_anything_is_written(self) -> None:
        before_counts = row_counts()
        before = self.bank.fresh()
        response = self.bank.post(self.client, "approve", self.bank.owner, body={"note": "Mine."}, step_up=True)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "four_eyes_violation")
        after = self.bank.fresh()
        self.assertEqual(row_counts(), before_counts)
        self.assertEqual(
            (after.status, after.version, after.signed_off_by_id, after.close_reason_id, after.closed_at, after.closed_note),
            (before.status, before.version, None, None, None, ""),
        )

    def test_without_a_fresh_assertion_it_is_403_before_the_case_is_read(self) -> None:
        response = self.bank.post(self.client, "approve", self.bank.approver, body={"note": ""}, step_up=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")
        self.assertEqual(self.bank.fresh().status, C.SIGNOFF.value)

    def test_a_second_person_closes_it_and_the_audit_row_names_the_assertion(self) -> None:
        version = self.bank.fresh().version
        response = self.bank.post(
            self.client, "approve", self.bank.approver, body={"note": "Criteria checked."}, version=version, step_up=True
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], "closed")
        self.assertEqual(body["closeReason"]["key"], "signed_off")
        self.assertEqual(body["closeReason"]["kind"], "signed_off")
        self.assertEqual(body["signedOffBy"]["id"], str(self.bank.approver.id))
        self.assertEqual(body["signoffRequestedBy"]["id"], str(self.bank.owner.id), "both people stay on the case")
        self.assertEqual(body["closedNote"], "Criteria checked.")
        self.assertIsNotNone(body["closedAt"])
        self.assertEqual(body["version"], version + 1)
        self.assertEqual(body["allowedTransitions"], [], "a signed-off close is final")
        case = self.bank.fresh()
        audit = AuditEvent.objects.get(subject_id=case.id, action=logic.MOVED, after__status="closed")
        assertion = StepUpAssertion.objects.filter(session__user=self.bank.approver).order_by("-created_at").first()
        assert assertion is not None
        self.assertEqual(audit.step_up_assertion_id, assertion.id)
        self.assertEqual(audit.actor_id, self.bank.approver.id)
        self.assertNotIn("Criteria checked.", str(audit.before) + str(audit.after) + audit.summary, "a note never reaches the audit values")
        moved = CaseTransition.objects.get(case=case, to_status="closed")
        self.assertEqual((moved.from_status, moved.note, moved.by_user_id), ("signoff", "Criteria checked.", self.bank.approver.id))

    def test_a_sign_off_moves_no_library_or_register_row(self) -> None:
        before = inventory_snapshot()
        self.assertTrue(any(before.values()), "the snapshot holds library rows, so it can show a change")
        response = self.bank.post(self.client, "approve", self.bank.approver, body={"note": ""}, step_up=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(inventory_snapshot(), before)

    def test_approving_twice_is_an_invalid_transition(self) -> None:
        self.assertEqual(self.bank.post(self.client, "approve", self.bank.approver, step_up=True).status_code, 200)
        response = self.bank.post(self.client, "approve", self.bank.approver, step_up=True)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "invalid_transition")


class FourEyesAtTheDatabase(TestCase):
    def test_the_check_refuses_the_requester_as_approver_on_a_direct_write(self) -> None:
        """The second line of defence: with the guard bypassed, PostgreSQL still refuses."""
        bank = Bank()
        case_build.in_category(bank.case, C.SIGNOFF)
        tenancy.activate(bank.tenant.id)
        ChangeCase.objects.filter(pk=bank.case.pk).update(signoff_requested_by=bank.owner, signoff_requested_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChangeCase.objects.filter(pk=bank.case.pk).update(signed_off_by=bank.owner)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChangeCase.objects.filter(pk=bank.case.pk).update(signoff_requested_by=None, signed_off_by=bank.approver)


# ---------------------------------------------------------------------------------------
# Send-back
# ---------------------------------------------------------------------------------------
class SendBack(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = Bank()
        self.bank.ready_for_signoff(self.client)

    def test_it_reopens_the_work_clears_the_request_and_keeps_the_note_on_the_ledger(self) -> None:
        response = self.bank.post(self.client, "send-back", self.bank.approver, body={"note": "Attach the desk's signature."})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], "implementing")
        self.assertIsNone(body["signoffRequestedBy"])
        self.assertIsNone(body["signoffRequestedAt"])
        self.assertTrue(body["canRequestSignoff"], "the work is still done, so it can be asked for again")
        case = self.bank.fresh()
        moved = CaseTransition.objects.get(case=case, from_status="signoff", to_status="implementing")
        self.assertEqual(moved.note, "Attach the desk's signature.")
        audit = AuditEvent.objects.get(subject_id=case.id, action=logic.MOVED, after__status="implementing", before__status="signoff")
        self.assertNotIn("desk", str(audit.after) + str(audit.before) + audit.summary)
        self.assertIsNone(audit.step_up_assertion_id, "send-back takes no step-up")

    def test_the_requester_may_send_back_their_own_request_without_a_step_up(self) -> None:
        """Send-back is the safe direction: it closes nothing, so four eyes is not asked."""
        response = self.bank.post(self.client, "send-back", self.bank.owner, body={"note": ""})
        self.assertEqual(response.status_code, 200)

    def test_a_case_not_waiting_for_sign_off_cannot_be_sent_back(self) -> None:
        self.assertEqual(self.bank.post(self.client, "send-back", self.bank.approver).status_code, 200)
        response = self.bank.post(self.client, "send-back", self.bank.approver)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "invalid_transition")

    def test_a_note_over_the_cap_is_422(self) -> None:
        from apps.cases.schemas import NOTE_MAX

        response = self.bank.post(self.client, "send-back", self.bank.approver, body={"note": "x" * (NOTE_MAX + 1)})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.bank.fresh().status, C.SIGNOFF.value)
