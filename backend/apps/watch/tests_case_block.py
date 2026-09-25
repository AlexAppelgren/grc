"""The case's workflow block on the change page, and the sub-status on a feed row
(CAS-02 to CAS-08, WAT-02; `c9-case-contract`).

`GET /changes/{changeId}` answers the bank's case with everything the change page works it
from: who owns, triaged, dismissed, asked for and gave sign-off and when, why it was
closed, how many actions are open, whether sign-off can be asked for, the moves open to
this reader and the `version` every workflow write sends back. The moves are the state
machine's own answer, from the same facts every guard reads (`apps/cases/logic.py`); this
file pins that they are, that the read costs the same queries whatever the case holds, and
that no transition table exists anywhere but `apps/cases/state.py`.

A feed row gains only the sub-status, and its query count does not grow with the page.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from django.db import transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.cases import logic, state
from apps.cases import testing as cases_build
from apps.cases.models import Action, ChangeCase, Evidence, EvidenceKind, ImpactAssessment
from apps.identity.models import User
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import CaseStatusCategory, CaseSubStatus, ClosureReason, DismissalReason, EffortSize
from apps.watch import testing as build

C = CaseStatusCategory
CHANGES = "/api/v1/changes"
APPS = Path(__file__).resolve().parent.parent
CATEGORY_NAMES = {member.name for member in C}
CATEGORY_VALUES = {member.value for member in C}


class CaseBlockFixture(TestCase):
    tenant: Tenant
    officer: User
    approver: User
    case: ChangeCase

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="block-bank")
        cls.officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.approver = factories.member_user(cls.tenant, roles=("approver",))
        cls.case = cases_build.case_on_a_new_change(cls.tenant)

    def set_case(self, **fields: Any) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            ChangeCase.objects.filter(pk=self.case.pk).update(**fields)

    def block(self, reader: User | None = None) -> dict[str, Any]:
        response = self.client.get(f"{CHANGES}/{self.case.change_id}", **sign_in(reader or self.officer, tenant=self.tenant))
        self.assertEqual(response.status_code, 200)
        return response.json()["case"]

    def add_action(self, *, done: bool) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            Action.objects.create(
                tenant=self.tenant,
                case=self.case,
                title="Document the criteria",
                owner=self.officer,
                due_date=timezone.localdate(),
                created_by=self.officer,
                done_at=timezone.now() if done else None,
                done_by=self.officer if done else None,
            )

    def add_clean_evidence(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            Evidence.objects.create(
                tenant=self.tenant,
                case=self.case,
                kind=EvidenceKind.LINK.value,
                name="FI decision memo",
                url="https://intranet.example.com/memo/42",
                uploaded_by=self.officer,
                scan_state="clean",
                scanned_at=timezone.now(),
            )

    def moves_by_the_machine(self, reader: User) -> list[str]:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            case = ChangeCase.objects.select_related(*logic.CASE_JOINS).get(pk=self.case.pk)
            facts = logic.case_facts(case, actor=reader.id)
            return [category.value for category in state.allowed_transitions(C(case.status), facts)]


class WorkflowBlockTests(CaseBlockFixture):
    def test_a_new_case_offers_triage_and_dismissal(self) -> None:
        case = self.block()
        self.assertEqual(case["category"], "new")
        self.assertEqual(case["allowedTransitions"], ["assigned", "dismissed"])
        self.assertEqual(case["version"], 1)
        self.assertFalse(case["canRequestSignoff"])
        self.assertEqual(case["openActionCount"], 0)
        for field in ("owner", "triagedBy", "triagedAt", "dismissedReason", "signoffRequestedBy", "signedOffBy", "closeReason", "closedAt", "subStatus"):
            self.assertIsNone(case[field], field)

    def test_every_category_answers_what_the_state_machine_answers(self) -> None:
        """No screen guesses a move: the block is the machine's answer for this reader."""
        for category in C:
            with self.subTest(category=category.value):
                cases_build.in_category(self.case, category)
                self.assertEqual(self.block()["allowedTransitions"], self.moves_by_the_machine(self.officer))

    def test_sign_off_is_offered_only_with_no_open_action_and_clean_evidence(self) -> None:
        cases_build.in_category(self.case, C.IMPLEMENTING)
        self.assertFalse(self.block()["canRequestSignoff"], "no evidence yet")
        self.add_clean_evidence()
        self.add_action(done=False)
        case = self.block()
        self.assertEqual(case["openActionCount"], 1)
        self.assertFalse(case["canRequestSignoff"])
        self.assertNotIn("signoff", case["allowedTransitions"])
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            Action.objects.filter(case=self.case).update(done_at=timezone.now(), done_by=self.officer)
        case = self.block()
        self.assertEqual(case["openActionCount"], 0)
        self.assertTrue(case["canRequestSignoff"])
        self.assertEqual(case["allowedTransitions"], ["signoff"])

    def test_the_requester_is_never_offered_their_own_sign_off(self) -> None:
        cases_build.in_category(self.case, C.SIGNOFF)
        self.set_case(signoff_requested_by=self.officer, signoff_requested_at=timezone.now())
        self.assertEqual(self.block(self.officer)["allowedTransitions"], ["implementing"])
        second = self.block(self.approver)
        self.assertEqual(second["allowedTransitions"], ["implementing", "closed"])
        self.assertEqual(second["signoffRequestedBy"], {"id": str(self.officer.id), "name": self.officer.name})

    def test_people_and_reasons_are_named_and_reasons_are_keys(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            reason = DismissalReason.objects.get(tenant=self.tenant, key="out_of_scope")
            sub_status = CaseSubStatus.objects.get(tenant=self.tenant, key="dismissed")
        self.set_case(
            status=C.DISMISSED.value,
            dismissed_reason=reason,
            dismissed_by=self.officer,
            dismissed_at=timezone.now(),
            sub_status=sub_status,
        )
        case = self.block()
        self.assertEqual(case["dismissedReason"], {"key": "out_of_scope", "kind": None, "label": "Out of scope"})
        self.assertEqual(case["dismissedBy"], {"id": str(self.officer.id), "name": self.officer.name})
        self.assertEqual(case["subStatus"], {"key": "dismissed", "kind": "dismissed", "label": "Dismissed"})
        self.assertEqual(case["allowedTransitions"], ["new"])

    def test_a_one_person_close_is_restorable_and_a_signed_off_one_is_not(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            reasons = {row.key: row for row in ClosureReason.objects.filter(tenant=self.tenant)}
        cases_build.in_category(self.case, C.CLOSED)
        self.set_case(close_reason=reasons["no_action"], closed_at=timezone.now())
        case = self.block()
        self.assertEqual(case["closeReason"]["key"], "no_action")
        self.assertEqual(case["closeReason"]["kind"], "no_action")
        self.assertEqual(case["allowedTransitions"], ["new"])
        self.set_case(close_reason=reasons["signed_off"])
        self.assertEqual(self.block()["allowedTransitions"], [], "a signed-off close stays final")

    def test_the_read_costs_the_same_queries_whatever_the_case_holds(self) -> None:
        cases_build.in_category(self.case, C.IMPLEMENTING)
        headers = sign_in(self.officer, tenant=self.tenant)
        url = f"{CHANGES}/{self.case.change_id}"
        with CaptureQueriesContext(connection) as bare:
            self.client.get(url, **headers)
        for _ in range(3):
            self.add_action(done=False)
            self.add_clean_evidence()
        with CaptureQueriesContext(connection) as busy:
            response = self.client.get(url, **headers)
        self.assertEqual(response.json()["case"]["openActionCount"], 3)
        self.assertEqual(len(busy), len(bare), "actions and evidence are counted, never read one by one (NFR-02)")


class AssessmentOnTheBlockTests(CaseBlockFixture):
    """c9-fe-triage-assessment: the assessment panel and the closed panel read the saved
    assessment and the close note from the change page, as every case panel reads its case
    (design/screens/tenant-change.html), rather than from a write's answer only."""

    def save_assessment(self, *, effort: str | None) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            ImpactAssessment.objects.create(
                tenant=self.tenant,
                case=self.case,
                applies="partly",
                why="We pay two research providers from our own account.",
                what_must_change="Written criteria for the annual assessment.",
                internal_deadline=timezone.localdate(),
                effort=None if effort is None else EffortSize.objects.get(tenant=self.tenant, key=effort),
                saved=True,
                saved_by=self.officer,
                saved_at=timezone.now(),
                version=2,
            )

    def test_no_assessment_and_no_note_before_there_is_one(self) -> None:
        case = self.block()
        self.assertIsNone(case["assessment"])
        self.assertIsNone(case["closedNote"])

    def test_the_saved_assessment_is_on_the_block(self) -> None:
        cases_build.in_category(self.case, C.ASSESSING)
        self.save_assessment(effort="m")
        assessment = self.block()["assessment"]
        self.assertEqual(assessment["applies"], "partly")
        self.assertEqual(assessment["why"], "We pay two research providers from our own account.")
        self.assertEqual(assessment["whatMustChange"], "Written criteria for the annual assessment.")
        self.assertEqual(assessment["internalDeadline"], timezone.localdate().isoformat())
        self.assertEqual(assessment["effort"]["key"], "m")
        self.assertTrue(assessment["saved"])
        self.assertEqual(assessment["savedBy"], {"id": str(self.officer.id), "name": self.officer.name})
        self.assertEqual(assessment["version"], 2)

    def test_the_close_note_is_on_the_block(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            reason = ClosureReason.objects.get(tenant=self.tenant, key="no_action")
        cases_build.in_category(self.case, C.CLOSED)
        self.set_case(close_reason=reason, closed_at=timezone.now(), closed_note="Paid from client charges already.")
        self.assertEqual(self.block()["closedNote"], "Paid from client charges already.")

    def test_an_assessment_costs_no_query_beyond_its_effort_label(self) -> None:
        cases_build.in_category(self.case, C.ASSESSING)
        headers = sign_in(self.officer, tenant=self.tenant)
        url = f"{CHANGES}/{self.case.change_id}"
        with CaptureQueriesContext(connection) as without:
            self.client.get(url, **headers)
        self.save_assessment(effort=None)
        with CaptureQueriesContext(connection) as saved:
            self.client.get(url, **headers)
        self.assertEqual(len(saved), len(without), "the assessment is joined to the case, never read on its own")


class FeedRowTests(CaseBlockFixture):
    def test_a_feed_row_gains_only_the_sub_status(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            sub_status = CaseSubStatus.objects.get(tenant=self.tenant, key="new")
        self.set_case(sub_status=sub_status)
        rows = self.client.get(CHANGES, {"footprint": "all"}, **sign_in(self.officer, tenant=self.tenant)).json()["items"]
        case = next(row["case"] for row in rows if row["id"] == str(self.case.change_id))
        self.assertEqual(case["subStatus"], {"key": "new", "kind": "new", "label": "Needs triage"})
        for field in ("allowedTransitions", "version", "openActionCount", "canRequestSignoff", "owner", "triagedBy"):
            self.assertNotIn(field, case, "the workflow block is the change page's, not the feed's")

    def test_sub_statuses_do_not_grow_the_feeds_query_count(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            sub_status = CaseSubStatus.objects.get(tenant=self.tenant, key="new")
        self.set_case(sub_status=sub_status)
        headers = sign_in(self.officer, tenant=self.tenant)
        with CaptureQueriesContext(connection) as one:
            self.client.get(CHANGES, {"footprint": "all"}, **headers)
        build.seed_watch_reference()
        for _ in range(3):
            other = cases_build.case_on_a_new_change(self.tenant)
            with transaction.atomic():
                tenancy.activate(self.tenant.id)
                ChangeCase.objects.filter(pk=other.pk).update(sub_status=sub_status)
        with CaptureQueriesContext(connection) as four:
            response = self.client.get(CHANGES, {"footprint": "all"}, **headers)
        self.assertEqual(sum(1 for row in response.json()["items"] if row["case"] and row["case"]["subStatus"]), 4)
        self.assertEqual(len(four), len(one))


class OneTransitionTable(TestCase):
    def test_no_transition_table_exists_outside_state_py(self) -> None:
        """CHUNK9 rule 11: `apps/cases/state.py` alone maps a case category to the
        categories it may move to. A dict literal anywhere else under `apps/` whose keys are
        categories and whose values are collections of categories is a second table, and a
        second table is how a screen and a guard come to disagree."""
        offenders = []
        for path in sorted(APPS.rglob("*.py")):
            rel = path.relative_to(APPS).as_posix()
            if rel == "cases/state.py" or "/migrations/" in rel:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Dict) and _is_transition_table(node):
                    offenders.append(f"apps/{rel}:{node.lineno}")
        self.assertEqual(offenders, [], "a transition table outside apps/cases/state.py")

    def test_the_detector_finds_the_real_table(self) -> None:
        """The guard above is only worth something if it recognises the one table there is."""
        tree = ast.parse((APPS / "cases" / "state.py").read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(node, ast.Dict) and _is_transition_table(node) for node in ast.walk(tree)))


def _is_category(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr in CATEGORY_NAMES
    return isinstance(node, ast.Constant) and node.value in CATEGORY_VALUES


def _is_transition_table(node: ast.Dict) -> bool:
    categories_to_many = 0
    for key, value in zip(node.keys, node.values, strict=True):
        if _is_category(key) and isinstance(value, ast.Tuple | ast.List | ast.Set) and any(_is_category(e) for e in value.elts):
            categories_to_many += 1
    return categories_to_many >= 2
