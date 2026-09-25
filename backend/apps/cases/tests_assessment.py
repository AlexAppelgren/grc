"""The impact assessment (CAS-03, CAS-08, AC-CAS2; c9-assessment).

Starting the assessment is a move, `assigned` to `assessing`, and opens the assessment at
version 1. Saving it replaces the bank's answer under the case's `If-Match` and moves the
case nowhere, with one exception: `applies = no` closes the case on one person's word with
a reason of the `not_applicable` kind, which only a holder of `cases.work` may do (D-92).
What is proved here is that each refusal writes nothing, that the second of two saves from
the same version is refused and never merged, that a sub-status of another category is
refused, and that no text a person typed reaches an audit value or an outbox payload
(R2_CROSS_CUTTING (m)).

Proven to fail 2026-09-25: with the `may_close` check removed a contributor closed the
case, and with `check_version` dropped the second save overwrote the first.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from typing import Any

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.cases import logic, state
from apps.cases import testing as case_build
from apps.cases.models import CaseTransition, ChangeCase, ImpactAssessment
from apps.shared import factories, tenancy
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import CaseSubStatus, CaseSubStatusLabel
from apps.watch import testing as watch_build

V1 = "/api/v1"
C = CaseStatusCategory

WHY = "Self-directed trading and Guided investing both pay for external research."
WHAT = "Document the annual research quality criteria and have the desk sign them."
OTHER_WHY = "Only the corporate desk buys research; retail does not."


def body(**overrides: Any) -> dict[str, Any]:
    """A full assessment as the panel sends it, the deadline a month past today."""
    deadline = timezone.localdate() + datetime.timedelta(days=30)
    return {"applies": "yes", "why": WHY, "whatMustChange": WHAT, "internalDeadline": deadline.isoformat(), "effort": "m", **overrides}


def bank_with_a_case(category: CaseStatusCategory = C.ASSIGNED) -> SimpleNamespace:
    """A bank with an owner (`cases.work`), a contributor (`cases.contribute` only), a
    reader and one case in `category`, owned by the owner."""
    watch_build.seed_watch_reference()
    tenant = factories.tenant()
    owner = factories.member(tenant, roles=("owner",), user_row=factories.user(name="Erik Holm")).user
    contributor = factories.member(tenant, roles=("contributor",)).user
    reader = factories.member(tenant, roles=("reader",)).user
    row = case_build.case(tenant, watch_build.change(), owner=owner)
    case_build.in_category(row, category)
    if category in (C.ASSESSING, C.IMPLEMENTING):
        with transaction.atomic():
            tenancy.activate(tenant.id)
            ImpactAssessment.objects.create(tenant=tenant, case=row)
    return SimpleNamespace(tenant=tenant, owner=owner, contributor=contributor, reader=reader, change_id=row.change_id, case_id=row.id)


def sub_status(tenant: Any, key: str, kind: CaseStatusCategory, label: str) -> CaseSubStatus:
    """A sub-status the bank's admin added inside `kind`, labelled in English."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        row = CaseSubStatus.objects.create(tenant=tenant, key=key, kind=kind.value, sort_order=50)
        CaseSubStatusLabel.objects.create(tenant=tenant, vocabulary=row, language="en", text=label, is_original=True)
    return row


class AssessmentClient:
    """The two assessment routes as a person in the bank calls them."""

    def __init__(self, test: TestCase, bank: SimpleNamespace) -> None:
        self.test = test
        self.bank = bank

    def case(self) -> ChangeCase:
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            return ChangeCase.objects.select_related("close_reason", "sub_status").get(pk=self.bank.case_id)

    def assessment(self) -> ImpactAssessment:
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            return ImpactAssessment.objects.select_related("effort").get(case_id=self.bank.case_id)

    def version(self) -> int:
        return self.case().version

    def start(self, who: Any = None, *, if_match: int | None = None) -> Any:
        return self.test.client.post(
            f"{V1}/changes/{self.bank.change_id}/assessment/start",
            content_type="application/json",
            **self._headers(who, self.version() if if_match is None else if_match),
        )

    def save(self, payload: dict[str, Any], who: Any = None, *, if_match: int | None = None, send_if_match: bool = True) -> Any:
        version = self.version() if if_match is None else if_match
        return self.test.client.put(
            f"{V1}/changes/{self.bank.change_id}/assessment",
            data=payload,
            content_type="application/json",
            **self._headers(who, version if send_if_match else None),
        )

    def _headers(self, who: Any, version: int | None) -> dict[str, Any]:
        headers = sign_in(who or self.bank.owner, tenant=self.bank.tenant)
        if version is not None:
            headers["HTTP_IF_MATCH"] = str(version)
        return headers


class StartAssessmentTests(ScenarioTestCase):
    def test_start_moves_an_assigned_case_to_assessing_with_an_empty_assessment_at_version_1(self) -> None:
        bank = bank_with_a_case(C.ASSIGNED)
        calls = AssessmentClient(self, bank)
        before = calls.version()

        response = calls.start()

        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual(answer["status"], C.ASSESSING.value)
        self.assertEqual(answer["version"], before + 1)
        self.assertEqual(answer["assessment"]["version"], 1)
        self.assertFalse(answer["assessment"]["saved"])
        self.assertIsNone(answer["assessment"]["why"])
        self.assertEqual(answer["owner"]["name"], "Erik Holm")
        self.assertEqual(set(answer["allowedTransitions"]), {C.CLOSED.value}, "implementing waits for a saved why")
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            moved = CaseTransition.objects.get(case_id=bank.case_id)
            self.assertEqual((moved.from_status, moved.to_status, moved.by_user_id), (C.ASSIGNED.value, C.ASSESSING.value, bank.owner.id))
            self.assertTrue(AuditEvent.objects.filter(action=logic.MOVED, subject_id=bank.case_id).exists())

    def test_start_from_anywhere_but_assigned_is_invalid_and_writes_nothing(self) -> None:
        bank = bank_with_a_case(C.NEW)
        calls = AssessmentClient(self, bank)
        before = calls.version()

        response = calls.start(self._officer(bank))

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "invalid_transition")
        self.assertEqual(calls.version(), before)
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            self.assertFalse(ImpactAssessment.objects.filter(case_id=bank.case_id).exists())

    def test_start_without_or_with_an_old_if_match_is_stale(self) -> None:
        bank = bank_with_a_case(C.ASSIGNED)
        calls = AssessmentClient(self, bank)
        current = calls.version()
        for version in (None, current - 1):
            with self.subTest(if_match=version):
                response = self.client.post(
                    f"{V1}/changes/{bank.change_id}/assessment/start",
                    content_type="application/json",
                    **calls._headers(bank.owner, version),
                )
                self.assertEqual(response.status_code, 409, response.content)
                self.assertEqual(response.json()["code"], "stale_write")
                self.assertEqual(response.json()["currentVersion"], current)
        self.assertEqual(calls.case().status, C.ASSIGNED.value)

    def test_a_case_restored_and_started_again_keeps_its_earlier_assessment(self) -> None:
        """Nothing overwritten: a case closed as not applicable, restored and triaged again
        opens the assessment it already had rather than an empty one."""
        bank = bank_with_a_case(C.ASSIGNED)
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            ImpactAssessment.objects.create(
                tenant=bank.tenant, case_id=bank.case_id, why=WHY, saved=True, saved_by=bank.owner, saved_at=timezone.now(), version=3
            )

        response = AssessmentClient(self, bank).start()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["assessment"]["why"], WHY)
        self.assertEqual(response.json()["assessment"]["version"], 3)

    def _officer(self, bank: SimpleNamespace) -> Any:
        return factories.member(bank.tenant, roles=("compliance_officer",)).user


class SaveAssessmentTests(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = bank_with_a_case(C.ASSESSING)
        self.calls = AssessmentClient(self, self.bank)

    def test_save_stores_every_field_with_a_key_for_effort_and_moves_no_state(self) -> None:
        before = self.calls.version()

        response = self.calls.save(body())

        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual(answer["status"], C.ASSESSING.value, "saving moves no state; adding an action does")
        self.assertEqual(answer["version"], before + 1)
        saved = answer["assessment"]
        self.assertEqual((saved["applies"], saved["why"], saved["whatMustChange"]), ("yes", WHY, WHAT))
        self.assertEqual(saved["internalDeadline"], body()["internalDeadline"])
        self.assertEqual((saved["effort"]["key"], saved["effort"]["label"]), ("m", "M"))
        self.assertTrue(saved["saved"])
        self.assertEqual(saved["savedBy"]["name"], "Erik Holm")
        self.assertEqual(saved["version"], 2)
        self.assertIn(C.IMPLEMENTING.value, answer["allowedTransitions"], "a saved why opens the way to the first action")
        row = self.calls.assessment()
        self.assertEqual(row.effort.key if row.effort else None, "m", "the effort is stored as the bank's row, read by key")
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            self.assertFalse(CaseTransition.objects.filter(case_id=self.bank.case_id).exists())

    def test_a_contributor_may_save_input(self) -> None:
        response = self.calls.save(body(applies="partly"), self.bank.contributor)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["assessment"]["applies"], "partly")

    def test_a_reader_may_not_save(self) -> None:
        response = self.calls.save(body(), self.bank.reader)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], "cases.contribute")

    def test_a_save_without_a_why_is_422_and_the_database_refuses_one_too(self) -> None:
        for payload in (body(why=""), {key: value for key, value in body().items() if key != "why"}):
            with self.subTest(payload=payload):
                response = self.calls.save(payload)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "validation_error")
        self.assertFalse(self.calls.assessment().saved)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            ImpactAssessment.objects.filter(case_id=self.bank.case_id).update(
                saved=True, saved_by=self.bank.owner, saved_at=timezone.now(), why=""
            )

    def test_the_second_save_from_the_same_version_is_stale_and_nothing_merges(self) -> None:
        loaded = self.calls.version()
        first = self.calls.save(body(), self.bank.owner, if_match=loaded)
        self.assertEqual(first.status_code, 200, first.content)

        second = self.calls.save(body(why=OTHER_WHY, whatMustChange=""), self.bank.contributor, if_match=loaded)

        self.assertEqual(second.status_code, 409, second.content)
        self.assertEqual(second.json()["code"], "stale_write")
        self.assertEqual(second.json()["currentVersion"], loaded + 1)
        row = self.calls.assessment()
        self.assertEqual((row.why, row.what_must_change, row.version), (WHY, WHAT, 2), "the first save stands whole")

    def test_a_save_without_if_match_is_stale(self) -> None:
        response = self.calls.save(body(), send_if_match=False)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_write")
        self.assertFalse(self.calls.assessment().saved)

    def test_an_unknown_effort_key_is_422_listing_the_valid_ones(self) -> None:
        response = self.calls.save(body(effort="xl"))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "unknown_key")
        self.assertEqual(response.json()["validKeys"], ["s", "m", "l"])
        self.assertFalse(self.calls.assessment().saved)

    def test_a_sub_status_of_the_cases_category_is_set_and_one_of_another_is_422(self) -> None:
        sub_status(self.bank.tenant, "waiting_for_legal", C.ASSESSING, "Waiting for legal")
        sub_status(self.bank.tenant, "tickets_raised", C.IMPLEMENTING, "Tickets raised")

        refused = self.calls.save(body(subStatus="tickets_raised"))
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "unknown_key")
        self.assertIn("waiting_for_legal", refused.json()["validKeys"])
        self.assertNotIn("tickets_raised", refused.json()["validKeys"])
        self.assertIsNone(self.calls.case().sub_status)

        accepted = self.calls.save(body(subStatus="waiting_for_legal"))
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(accepted.json()["subStatus"], {"key": "waiting_for_legal", "kind": "assessing", "label": "Waiting for legal"})

        cleared = self.calls.save(body())
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertIsNone(cleared.json()["subStatus"], "the save replaces the whole answer, the sub-status with it")

    def test_a_case_not_being_assessed_or_implemented_is_invalid(self) -> None:
        for category in (C.ASSIGNED, C.SIGNOFF):
            with self.subTest(category=category):
                bank = bank_with_a_case(category)
                response = AssessmentClient(self, bank).save(body())
                self.assertEqual(response.status_code, 409, response.content)
                self.assertEqual(response.json()["code"], "invalid_transition")

    def test_an_implementing_case_saves_and_stays_implementing(self) -> None:
        bank = bank_with_a_case(C.IMPLEMENTING)
        response = AssessmentClient(self, bank).save(body())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], C.IMPLEMENTING.value)

    def test_no_text_a_person_typed_reaches_an_audit_value_or_an_outbox_payload(self) -> None:
        response = self.calls.save(body())
        self.assertEqual(response.status_code, 200, response.content)
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            event = AuditEvent.objects.get(action="case.assessment_saved", subject_id=self.bank.case_id)
            self.assertEqual(event.after["effort"], "m")
            self.assertEqual(event.after["applies"], "yes")
            written = json.dumps([event.before, event.after, event.summary]) + json.dumps(
                list(OutboxEvent.objects.filter(topic="case.assessment_saved").values_list("payload", flat=True))
            )
        for text in (WHY, WHAT):
            self.assertNotIn(text, written)


class AppliesNoTests(ScenarioTestCase):
    """`applies = no` closes the case on one person's word (D-92)."""

    def setUp(self) -> None:
        self.bank = bank_with_a_case(C.ASSESSING)
        self.calls = AssessmentClient(self, self.bank)

    def test_applies_no_closes_with_a_not_applicable_reason_and_can_be_restored(self) -> None:
        response = self.calls.save(body(applies="no", whatMustChange=""))

        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual(answer["status"], C.CLOSED.value)
        self.assertEqual(answer["closeReason"]["kind"], "not_applicable")
        self.assertIsNotNone(answer["closedAt"])
        self.assertEqual(answer["assessment"]["applies"], "no")
        self.assertIn(C.NEW.value, answer["allowedTransitions"], "a one-person close can be restored to triage")
        case = self.calls.case()
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            moved = CaseTransition.objects.get(case_id=self.bank.case_id)
            self.assertEqual((moved.from_status, moved.to_status, moved.by_user_id), (C.ASSESSING.value, C.CLOSED.value, self.bank.owner.id))
            self.assertTrue(AuditEvent.objects.filter(action=logic.MOVED, subject_id=self.bank.case_id).exists())
            saved = AuditEvent.objects.get(action="case.assessment_saved", subject_id=self.bank.case_id)
            self.assertEqual((saved.actor_id, saved.after["closeReason"]), (self.bank.owner.id, "not_applicable"))
        self.assertEqual(state.allowed_transitions(C.CLOSED, logic.case_facts(case, actor=None)), [C.NEW])

    def test_applies_no_without_cases_work_is_403_naming_it_and_changes_nothing(self) -> None:
        before = self.calls.version()

        response = self.calls.save(body(applies="no"), self.bank.contributor)

        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["code"], "permission_denied")
        self.assertEqual(response.json()["requiredPermission"], "cases.work")
        self.assertEqual((self.calls.case().status, self.calls.version()), (C.ASSESSING.value, before))
        self.assertFalse(self.calls.assessment().saved)

    def test_applies_no_on_an_implementing_case_is_invalid_and_saves_nothing(self) -> None:
        bank = bank_with_a_case(C.IMPLEMENTING)
        calls = AssessmentClient(self, bank)

        response = calls.save(body(applies="no"))

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "invalid_transition")
        self.assertEqual(calls.case().status, C.IMPLEMENTING.value)
        self.assertFalse(calls.assessment().saved, "a refused close rolls the save back with it")

    def test_a_closed_sub_status_goes_with_the_close_and_an_assessing_one_is_422(self) -> None:
        sub_status(self.bank.tenant, "waiting_for_legal", C.ASSESSING, "Waiting for legal")
        refused = self.calls.save(body(applies="no", subStatus="waiting_for_legal"))
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "unknown_key")

        response = self.calls.save(body(applies="no", subStatus="closed"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["subStatus"]["kind"], C.CLOSED.value)
