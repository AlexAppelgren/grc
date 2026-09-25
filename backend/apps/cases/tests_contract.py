"""Contract guard for the case routes chunk 5 declares (WAT-04, WAT-05, CAS-01, NFR-01;
`c5-contract-api-screens`).

A bank says what a change means for it and decides which suggested obligation links are
real for it. Both are that bank's own judgement, so both take a person's session with
`cases.work` and neither takes an agent's key: an agent writes the library, never a bank's
case (AGT-01, rule 13).

This file is the gate half and stays the gate half now that `cases/so_what.py` and
`cases/links.py` are built: who is refused, with which code, and on what body — all decided
before a case is ever read. What the routes then do with a case is
`apps/cases/tests_so_what.py`, `tests_links.py` and WAT-S6 and WAT-S7.

Written before the routes existed: every case below failed with 404 until `cases/api.py`
landed and the router was mounted in `config/api.py`. The rows that once asserted 501
`not_built` now assert 404: the caller passes every gate and the bank in the stubbed session
has no case for that change, which is the same answer another bank's case gets.

Chunk 9 (`c9-case-contract`) adds the gate half of the eighteen workflow operations
(CAS-02 to CAS-08) and the shared case logic every one of them uses: who is refused, with
which code, before the 501 `not_built` each answers until its module is built; that no key
reaches any; that another bank's case, action or evidence is a 404; and what
`apps/cases/logic.py` promises — the loader, `If-Match`, the guards' facts in one query, and
`transition()` writing its ledger row and its audit row in one transaction.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cases import logic, state
from apps.cases import testing as case_build
from apps.cases.models import Action, CaseTransition, ChangeCase, Evidence, EvidenceKind, ImpactAssessment
from apps.cases.schemas import SO_WHAT_MAX
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from config.api import api

CHANGE = "11111111-1111-4111-8111-111111111111"
OBLIGATION = "44444444-4444-4444-8444-444444444444"

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

SO_WHAT_BODY = {"text": "Confirm with the desk that the annual research criteria are documented before 1 October."}
LINK_BODY = {"obligationId": OBLIGATION}

# (name, method, url, body). Every one of them is gated by cases.work alone.
CASE_ROUTES = [
    ("saveSoWhat", "put", f"/api/v1/changes/{CHANGE}/so-what", SO_WHAT_BODY),
    ("confirmSoWhat", "post", f"/api/v1/changes/{CHANGE}/so-what/confirm", None),
    ("acceptCaseObligationLink", "post", f"/api/v1/changes/{CHANGE}/case/obligation-links", LINK_BODY),
    ("removeCaseObligationLink", "delete", f"/api/v1/changes/{CHANGE}/case/obligation-links/{OBLIGATION}", None),
]


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class CaseRouteGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        for name, method, url, body in CASE_ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_session_without_cases_work_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.CASES_READ}, tenant_id=uuid.uuid4())):
            for name, method, url, body in CASE_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], perms.CASES_WORK)

    def test_an_agent_key_never_touches_a_banks_case(self) -> None:
        """A case is a bank's judgement. No scope reaches one, whatever the key holds: the
        agent writes library facts and the bank decides what they mean (AGT-01, rule 13)."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body in CASE_ROUTES:
                with self.subTest(operation=name):
                    self.assertEqual(_call(self.client, method, url, body, AS_KEY).status_code, 401)

    def test_a_library_editor_never_writes_a_banks_wording(self) -> None:
        """`proposals.review` is the console's permission and no tenant role holds it; it is
        equally true the other way, so a library editor cannot write a bank's "So what?"."""
        with stub_session(user_principal(permissions={perms.PROPOSALS_REVIEW, perms.SOURCES_MANAGE})):
            for name, method, url, body in CASE_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["requiredPermission"], perms.CASES_WORK)

    def test_bad_input_is_422_before_the_stub(self) -> None:
        so_what_url = f"/api/v1/changes/{CHANGE}/so-what"
        links_url = f"/api/v1/changes/{CHANGE}/case/obligation-links"
        cases = [
            ("saveSoWhat", "put", so_what_url, {}),
            ("saveSoWhat", "put", so_what_url, {"text": ""}),
            ("saveSoWhat", "put", so_what_url, {"text": "x" * (SO_WHAT_MAX + 1)}),
            ("saveSoWhat", "put", so_what_url, {**SO_WHAT_BODY, "tone": "negative"}),
            ("acceptCaseObligationLink", "post", links_url, {}),
            ("acceptCaseObligationLink", "post", links_url, {"obligationId": "not-a-uuid"}),
            ("acceptCaseObligationLink", "post", links_url, {**LINK_BODY, "decision": "accepted"}),
        ]
        with stub_session(user_principal(permissions={perms.CASES_WORK}, tenant_id=uuid.uuid4())):
            for name, method, url, body in cases:
                with self.subTest(operation=name, body=body):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_the_longest_wording_the_library_can_draft_is_accepted(self) -> None:
        """The bank's cap is the library draft's cap, so confirming a draft can never be
        refused for length (`watch/schemas.py:TEXT_MAX`)."""
        from apps.watch.schemas import TEXT_MAX

        self.assertEqual(SO_WHAT_MAX, TEXT_MAX)
        with stub_session(user_principal(permissions={perms.CASES_WORK}, tenant_id=uuid.uuid4())):
            response = _call(
                self.client, "put", f"/api/v1/changes/{CHANGE}/so-what", {"text": "x" * SO_WHAT_MAX}, AS_SESSION
            )
        self.assertEqual(response.status_code, 404, "the cap itself is accepted and reaches the logic")


class CaseRouteLogic(TestCase):
    def test_a_session_with_cases_work_reaches_the_logic(self) -> None:
        """Past every gate, into a bank that has no case for that change: 404, in the one
        problem shape, with nothing of the server in it."""
        with stub_session(user_principal(permissions={perms.CASES_WORK}, tenant_id=uuid.uuid4())):
            for name, method, url, body in CASE_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 404)
                    problem = response.json()
                    self.assertEqual(problem["code"], "not_found")
                    self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                    self.assertNotIn("traceback", response.content.decode().lower())


# =======================================================================================
# The case workflow (c9-case-contract)
# =======================================================================================

C = CaseStatusCategory
V1 = "/api/v1"
TRIAGE_BODY = {"urgency": "within_3_months", "ownerId": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60"}
ASSESSMENT_BODY = {"applies": "yes", "why": "Both advice services pay for external research."}
ACTION_BODY = {"title": "Document the criteria", "ownerId": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "dueDate": "2026-10-10"}
EVIDENCE_FORM = {"kind": "link", "name": "FI decision memo", "url": "https://intranet.example.com/memo/42"}
MULTIPART = "multipart"


class Route:
    """One workflow operation as a caller reaches it: the address is filled from a record
    built for the test, because the child routes carry their own id."""

    def __init__(self, operation_id: str, method: str, path: str, body: Any, permission: str, *, step_up: bool = False) -> None:
        self.operation_id = operation_id
        self.method = method
        self.path = path
        self.body = body
        self.permission = permission
        self.step_up = step_up

    def url(self, change_id: Any, action_id: Any = None, evidence_id: Any = None) -> str:
        return V1 + self.path.format(change=change_id, action=action_id, evidence=evidence_id)


WORKFLOW = [
    Route("triageChange", "post", "/changes/{change}/triage", TRIAGE_BODY, perms.CASES_TRIAGE),
    Route("dismissChange", "post", "/changes/{change}/dismiss", {"reasonKey": "out_of_scope"}, perms.CASES_TRIAGE),
    Route("restoreChange", "post", "/changes/{change}/restore", None, perms.CASES_TRIAGE),
    Route("startAssessment", "post", "/changes/{change}/assessment/start", None, perms.CASES_WORK),
    Route("saveAssessment", "put", "/changes/{change}/assessment", ASSESSMENT_BODY, perms.CASES_CONTRIBUTE),
    Route("closeWithoutAction", "post", "/changes/{change}/close", {"reasonKey": "no_action"}, perms.CASES_WORK),
    Route("listActions", "get", "/changes/{change}/actions", None, perms.CASES_READ),
    Route("addAction", "post", "/changes/{change}/actions", ACTION_BODY, perms.CASES_WORK),
    Route("updateAction", "patch", "/actions/{action}", {"done": True}, perms.CASES_CONTRIBUTE),
    Route("deleteAction", "delete", "/actions/{action}", None, perms.CASES_WORK),
    Route("listEvidence", "get", "/changes/{change}/evidence", None, perms.CASES_READ),
    Route("addEvidence", "post", "/changes/{change}/evidence", MULTIPART, perms.CASES_CONTRIBUTE),
    Route("downloadEvidence", "get", "/evidence/{evidence}/download", None, perms.CASES_READ),
    Route("removeEvidence", "delete", "/evidence/{evidence}", None, perms.CASES_WORK),
    Route("requestSignoff", "post", "/changes/{change}/signoff/request", None, perms.CASES_WORK),
    Route("approveSignoff", "post", "/changes/{change}/signoff/approve", {"note": "Checked."}, perms.CASES_SIGNOFF, step_up=True),
    Route("sendBackSignoff", "post", "/changes/{change}/signoff/send-back", {"note": "One action is missing."}, perms.CASES_SIGNOFF),
    Route("getCaseFile", "get", "/changes/{change}/case-file", None, perms.CASES_READ),
]


# The operations whose module has landed, each proved by its own tests, not by a 501.
BUILT: set[str] = set()
# c9-signoff (apps/cases/tests_signoff.py).
BUILT |= {"requestSignoff", "approveSignoff", "sendBackSignoff"}
# c9-case-file-export (apps/cases/tests_case_file.py).
BUILT |= {"getCaseFile"}


def _send(client: Any, route: Route, url: str, headers: dict[str, Any]) -> Any:
    if route.body is MULTIPART:
        return client.post(url, data=EVIDENCE_FORM, **headers)
    return _call(client, route.method, url, route.body, headers)


def _bank_with_work() -> SimpleNamespace:
    """A bank with a case, a live action and a live piece of evidence (each on a case of the
    bank's), and one of its people holding every tenant permission with a fresh step-up."""
    tenant = factories.tenant()
    action = factories.case_action(tenant)
    evidence = factories.case_evidence(tenant)
    person = factories.member_user(tenant, roles=("admin",))
    return SimpleNamespace(
        tenant=tenant,
        change_id=action.case.change_id,
        action_id=action.id,
        evidence_id=evidence.id,
        principal=user_principal(
            subject_id=person.id, tenant_id=tenant.id, permissions=perms.TENANT_PERMISSIONS, step_up_at=timezone.now()
        ),
    )


class WorkflowContract(TestCase):
    def test_all_eighteen_operations_are_published_with_their_ids(self) -> None:
        schema = api.get_openapi_schema()
        published = {
            operation["operationId"]: (method, path)
            for path, item in schema["paths"].items()
            for method, operation in item.items()
        }
        for route in WORKFLOW:
            with self.subTest(operation=route.operation_id):
                self.assertIn(route.operation_id, published)
                method, path = published[route.operation_id]
                self.assertEqual(method, route.method)
                self.assertEqual(path.replace("{change_id}", "{change}").replace("{action_id}", "{action}").replace("{evidence_id}", "{evidence}"), V1 + route.path)
        self.assertEqual(len(WORKFLOW), 18)
        self.assertNotIn("exportActionsAsTickets", published, "the ticket export is chunk 13's (ruling 3)")
        self.assertNotIn("DownloadLink", schema["components"]["schemas"], "a download streams (ruling 5)")
        self.assertNotIn("uploadUrl", schema["components"]["schemas"]["CasesEvidenceCreated"]["properties"], "ruling 4")
        self.assertIn("multipart/form-data", schema["paths"][V1 + "/changes/{change_id}/evidence"]["post"]["requestBody"]["content"])
        responses = schema["paths"][V1 + "/changes/{change_id}/case-file"]["get"]["responses"]
        self.assertIn("text/plain", responses.get("200", responses.get(200, {}))["content"])

    def test_no_credential_is_401(self) -> None:
        for route in WORKFLOW:
            with self.subTest(operation=route.operation_id):
                response = _send(self.client, route, route.url(CHANGE, uuid.uuid4(), uuid.uuid4()), {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_no_api_key_reaches_any_whatever_its_scopes(self) -> None:
        """A case is a bank's judgement: an agent's key, of a bank or of the platform, with
        every scope there is, is refused by every workflow operation (AGT-01)."""
        for key in (agent_principal(scopes=perms.ALL_SCOPES), agent_principal(scopes=perms.ALL_SCOPES, tenant_id=uuid.uuid4())):
            with stub_api_key(key):
                for route in WORKFLOW:
                    with self.subTest(operation=route.operation_id, tenant=key.tenant_id):
                        response = _send(self.client, route, route.url(CHANGE, uuid.uuid4(), uuid.uuid4()), AS_KEY)
                        self.assertEqual(response.status_code, 401)

    def test_a_session_without_the_permission_is_403_naming_it(self) -> None:
        """Every other tenant permission and a fresh step-up, only the one each operation
        needs taken away: the 403 names exactly that one, before anything is read."""
        for route in WORKFLOW:
            others = perms.TENANT_PERMISSIONS - {route.permission}
            principal = user_principal(permissions=others, tenant_id=uuid.uuid4(), step_up_at=timezone.now())
            with self.subTest(operation=route.operation_id), stub_session(principal):
                response = _send(self.client, route, route.url(CHANGE, uuid.uuid4(), uuid.uuid4()), AS_SESSION)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "permission_denied")
                self.assertEqual(response.json()["requiredPermission"], route.permission)

    def test_only_the_approval_takes_a_step_up(self) -> None:
        """Playbook 4.2: sign-off approval needs a fresh passkey assertion and answers 403
        `step_up_required` before the case is read; nothing else in the workflow asks."""
        bank = _bank_with_work()
        stale = user_principal(
            subject_id=bank.principal.subject_id, tenant_id=bank.tenant.id, permissions=perms.TENANT_PERMISSIONS
        )
        with stub_session(stale):
            for route in WORKFLOW:
                with self.subTest(operation=route.operation_id):
                    response = _send(self.client, route, route.url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4()), AS_SESSION)
                    if route.step_up:
                        self.assertEqual(response.status_code, 403)
                        self.assertEqual(response.json()["code"], "step_up_required")
                    else:
                        self.assertEqual(response.status_code, 404, "past every gate, into a change with no case")

    def test_past_every_gate_each_answers_501_not_built(self) -> None:
        bank = _bank_with_work()
        with stub_session(bank.principal):
            for route in WORKFLOW:
                if route.operation_id in BUILT:
                    continue
                with self.subTest(operation=route.operation_id):
                    response = _send(self.client, route, route.url(bank.change_id, bank.action_id, bank.evidence_id), AS_SESSION)
                    self.assertEqual(response.status_code, 501)
                    self.assertEqual(response.json()["code"], "not_built")
                    self.assertEqual(response.headers["Content-Type"], "application/problem+json")

    def test_another_banks_case_action_and_evidence_are_404_before_the_stub(self) -> None:
        """Every route, the ones that need a body included: the stub loads its record under
        row-level security first, so another bank never learns a 501 (R2_CROSS_CUTTING (e))."""
        owner = _bank_with_work()
        other = _bank_with_work()
        with stub_session(other.principal):
            for route in WORKFLOW:
                with self.subTest(operation=route.operation_id):
                    response = _send(self.client, route, route.url(owner.change_id, owner.action_id, owner.evidence_id), AS_SESSION)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["code"], "not_found")

    def test_a_change_the_bank_has_no_case_for_is_404(self) -> None:
        bank = _bank_with_work()
        with stub_session(bank.principal):
            for route in WORKFLOW:
                if "{change}" not in route.path:
                    continue
                with self.subTest(operation=route.operation_id):
                    response = _send(self.client, route, route.url(uuid.uuid4()), AS_SESSION)
                    self.assertEqual(response.status_code, 404)

    def test_bad_input_is_422_before_the_stub(self) -> None:
        bank = _bank_with_work()
        change = bank.change_id
        cases = [
            ("post", f"{V1}/changes/{change}/triage", {"urgency": "act_now"}),
            ("post", f"{V1}/changes/{change}/triage", {**TRIAGE_BODY, "tone": "negative"}),
            ("post", f"{V1}/changes/{change}/dismiss", {"reasonKey": ""}),
            ("post", f"{V1}/changes/{change}/dismiss", {"reason": "free text is not a reason"}),
            ("post", f"{V1}/changes/{change}/close", {"reasonKey": "no_action", "note": "x" * 2001}),
            ("put", f"{V1}/changes/{change}/assessment", {"applies": "maybe", "why": "x"}),
            ("put", f"{V1}/changes/{change}/assessment", {"applies": "yes", "why": ""}),
            ("put", f"{V1}/changes/{change}/assessment", {**ASSESSMENT_BODY, "contributors": ["Legal"]}),
            ("post", f"{V1}/changes/{change}/actions", {"title": "x"}),
            ("patch", f"{V1}/actions/{bank.action_id}", {"title": ""}),
            ("post", f"{V1}/changes/{change}/signoff/approve", {"note": "x" * 2001}),
        ]
        with stub_session(bank.principal):
            for method, url, body in cases:
                with self.subTest(url=url, body=body):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")
            response = self.client.post(f"{V1}/changes/{change}/evidence", data={"kind": "video", "name": "x"}, **AS_SESSION)
            self.assertEqual(response.status_code, 422, "an evidence kind outside the three is refused")
            response = self.client.get(f"{V1}/changes/{change}/actions?limit=101", **AS_SESSION)
            self.assertEqual(response.status_code, 422, "a page is at most 100")

    def test_a_malformed_if_match_is_422(self) -> None:
        bank = _bank_with_work()
        with stub_session(bank.principal):
            response = self.client.post(f"{V1}/changes/{bank.change_id}/restore", HTTP_IF_MATCH="yesterday", **AS_SESSION)
        self.assertEqual(response.status_code, 422)


# ---------------------------------------------------------------------------------------
# apps/cases/logic.py
# ---------------------------------------------------------------------------------------
class CaseLogic(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.case = case_build.case_on_a_new_change(self.tenant)
        self.person = factories.member_user(self.tenant, roles=("compliance_officer",))
        self.actor = factories.user_actor(label=self.person.name, user_id=self.person.id)

    def _activated(self) -> None:
        tenancy.activate(self.tenant.id)

    def test_the_loader_answers_only_the_callers_own_case(self) -> None:
        with transaction.atomic():
            self._activated()
            self.assertEqual(logic.load_case(self.tenant, self.case.change_id).pk, self.case.pk)
        other = factories.tenant()
        with transaction.atomic():
            tenancy.activate(other.id)
            with self.assertRaises(ProblemError) as refused:
                logic.load_case(other, self.case.change_id)
        self.assertEqual((refused.exception.status, refused.exception.code), (404, "not_found"))

    def test_a_removed_child_is_404(self) -> None:
        action = factories.case_action(self.tenant)
        evidence = factories.case_evidence(self.tenant)
        with transaction.atomic():
            self._activated()
            self.assertEqual(logic.load_action(self.tenant, action.id).pk, action.id)
            self.assertEqual(logic.load_evidence(self.tenant, evidence.id).pk, evidence.id)
            Action.objects.filter(pk=action.id).update(removed_at=timezone.now(), removed_by=self.person)
            Evidence.objects.filter(pk=evidence.id).update(removed_at=timezone.now())
            for load, record_id in ((logic.load_action, action.id), (logic.load_evidence, evidence.id)):
                with self.subTest(load=load.__name__), self.assertRaises(ProblemError):
                    load(self.tenant, record_id)

    def test_if_match_must_name_the_current_version(self) -> None:
        with transaction.atomic():
            self._activated()
            case = logic.load_case(self.tenant, self.case.change_id)
            logic.check_version(case, case.version)
            for sent in (None, case.version - 1, case.version + 1):
                with self.subTest(sent=sent), self.assertRaises(logic.StaleWrite) as refused:
                    logic.check_version(case, sent)
                self.assertEqual(refused.exception.code, "stale_write")
                self.assertEqual(refused.exception.extra, {"currentVersion": case.version})

    def test_facts_read_live_open_actions_and_live_clean_evidence(self) -> None:
        with transaction.atomic():
            self._activated()
            case = logic.load_case(self.tenant, self.case.change_id)
            today = timezone.localdate()
            for title, done, removed in (("open", False, False), ("done", True, False), ("removed", False, True)):
                Action.objects.create(
                    tenant=self.tenant,
                    case=case,
                    title=title,
                    owner=self.person,
                    due_date=today,
                    created_by=self.person,
                    done_at=timezone.now() if done else None,
                    done_by=self.person if done else None,
                    removed_at=timezone.now() if removed else None,
                    removed_by=self.person if removed else None,
                )
            for name, scan, removed in (("clean", "clean", False), ("pending", "pending", False), ("gone", "clean", True)):
                Evidence.objects.create(
                    tenant=self.tenant,
                    case=case,
                    kind=EvidenceKind.LINK.value,
                    name=name,
                    url="https://intranet.example.com/memo",
                    uploaded_by=self.person,
                    scan_state=scan,
                    scanned_at=None if scan == "pending" else timezone.now(),
                    removed_at=timezone.now() if removed else None,
                )
            facts = logic.case_facts(case, actor=self.person.id)
        self.assertEqual(facts.open_action_count, 1, "a done or removed action is not open")
        self.assertEqual(facts.clean_evidence_count, 1, "pending or removed evidence does not count")
        self.assertFalse(facts.why_saved)
        self.assertEqual(facts.actor, self.person.id)

    def test_facts_for_many_cases_cost_one_query(self) -> None:
        cases = [case_build.case_on_a_new_change(self.tenant) for _ in range(3)]
        with transaction.atomic():
            self._activated()
            with CaptureQueriesContext(connection) as one:
                logic.case_facts_for(cases[:1], actor=None)
            with CaptureQueriesContext(connection) as three:
                facts = logic.case_facts_for(cases, actor=None)
        self.assertEqual(len(one), 1)
        self.assertEqual(len(three), len(one), "the same query count however many cases (NFR-02)")
        self.assertEqual(set(facts), {case.id for case in cases})

    def test_a_move_writes_its_ledger_row_and_its_audit_row_and_bumps_the_version(self) -> None:
        with transaction.atomic():
            self._activated()
            case = logic.load_case(self.tenant, self.case.change_id, for_update=True)
            before = case.version
            case.owner = self.person
            moved = logic.transition(case, C.ASSIGNED, actor=self.actor, user=self.person, note="Owned by compliance.")
            case.refresh_from_db()
            self.assertEqual(case.status, C.ASSIGNED.value)
            self.assertEqual(case.version, before + 1)
            self.assertEqual(case.owner_id, self.person.id, "the fields the caller set are saved with the move")
            self.assertEqual(
                (moved.from_status, moved.to_status, moved.by_user_id, moved.note),
                (C.NEW.value, C.ASSIGNED.value, self.person.id, "Owned by compliance."),
            )
            audit = AuditEvent.objects.filter(action=logic.MOVED, subject_id=case.id).get()
        self.assertEqual(audit.before, {"status": "new"})
        self.assertEqual(audit.after, {"status": "assigned", "version": before + 1})
        self.assertNotIn("Owned by compliance.", str(audit.after), "a note is tenant content and never audited")

    def test_a_refused_move_writes_nothing(self) -> None:
        with transaction.atomic():
            self._activated()
            case = logic.load_case(self.tenant, self.case.change_id)
            with self.assertRaises(state.InvalidTransition) as refused:
                logic.transition(case, C.ASSIGNED, actor=self.actor, user=self.person)
            self.assertEqual(refused.exception.code, "owner_required")
            with self.assertRaises(state.InvalidTransition) as refused:
                logic.transition(case, C.SIGNOFF, actor=self.actor, user=self.person)
            self.assertEqual(refused.exception.code, "invalid_transition")
            fresh = ChangeCase.objects.get(pk=case.pk)
            self.assertEqual((fresh.status, fresh.version), (C.NEW.value, 1))
            self.assertFalse(CaseTransition.objects.filter(case_id=case.pk).exists())
            self.assertFalse(AuditEvent.objects.filter(action=logic.MOVED, subject_id=case.pk).exists())

    def test_the_implementing_guard_reads_the_saved_why(self) -> None:
        with transaction.atomic():
            self._activated()
            case = logic.load_case(self.tenant, self.case.change_id)
            case_build.in_category(case, C.ASSESSING)
            case = logic.load_case(self.tenant, self.case.change_id)
            with self.assertRaises(state.InvalidTransition) as refused:
                logic.transition(case, C.IMPLEMENTING, actor=self.actor, user=self.person)
            self.assertEqual(refused.exception.code, "why_required")
            ImpactAssessment.objects.create(
                tenant=self.tenant, case=case, why="It applies.", saved=True, saved_by=self.person, saved_at=timezone.now()
            )
            logic.transition(case, C.IMPLEMENTING, actor=self.actor, user=self.person)
            self.assertEqual(ChangeCase.objects.get(pk=case.pk).status, C.IMPLEMENTING.value)

    def test_saving_or_confirming_the_so_what_bumps_the_version(self) -> None:
        """Neither takes `If-Match`, but a workflow write from a copy read before either is
        stale afterwards (CAS-08)."""
        with transaction.atomic():
            self._activated()
            ChangeCase.objects.filter(pk=self.case.pk).update(so_what_text="The draft.")
        principal = user_principal(subject_id=self.person.id, tenant_id=self.tenant.id, permissions={perms.CASES_WORK})
        with stub_session(principal):
            confirmed = self.client.post(f"{V1}/changes/{self.case.change_id}/so-what/confirm", **AS_SESSION)
            saved = _call(self.client, "put", f"{V1}/changes/{self.case.change_id}/so-what", SO_WHAT_BODY, AS_SESSION)
        self.assertEqual((confirmed.status_code, saved.status_code), (200, 200))
        with transaction.atomic():
            self._activated()
            self.assertEqual(ChangeCase.objects.get(pk=self.case.pk).version, 3)

