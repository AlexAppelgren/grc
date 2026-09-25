"""Contract guard for the register routes chunk 8 declares (REG-01 to REG-05, REG-07, REG-08;
`c8-register-contract`).

Every register route is published before its logic, behind the gate it will keep: 401 without
a session, 403 naming `requiredPermission` without its one permission, 403
`step_up_required` where a fresh passkey assertion is declared, and only then 501
`not_built` from the named function in the module of the package that will build it. A
logic package that replaces its stub changes the last row of this file for its routes and
nothing above it.

Written before the routes existed: every row failed with 404 until `register/api.py` was
written and its router mounted in `config/api.py`.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.routes import iter_operations
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from config.api import api

OBLIGATION = "44444444-4444-4444-8444-444444444444"
ENTITY = "55555555-5555-4555-8555-555555555555"
RECORD = "66666666-6666-4666-8666-666666666666"

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

STATUS_BODY = {"complianceStatus": "partly_compliant", "statusNote": "Reconciliation runs daily; the evidence log is manual."}
APPLICABILITY_BODY = {"applicability": "applies", "reason": "Certified", "orgUnitId": ENTITY}
MANY_BODY = {"rows": [{"obligationId": OBLIGATION, "unitId": RECORD, "applicability": "not_applicable", "reason": "No cloud services"}]}
GAP_BODY = {"title": "Evidence of reconciliation is manual", "severity": "high", "source": "assessment", "targetDate": "2026-12-31"}
GAP_PATCH = {"remediation": "Automate the daily reconciliation report."}
ACCEPT_BODY = {"reason": "compensating_control"}
INTERPRETATION_BODY = {"text": "We read this as covering every client account the bank holds, custody included."}
LINK_BODY = {"kind": "policy", "label": "Client asset policy", "externalRef": "POL-014"}
UNIT_BODY = {"orgUnitId": ENTITY, "reference": "A.5.1", "title": "Our information security policies"}
UNIT_PATCH = {"title": "Our information security policy set"}
PASTE_BODY = {"orgUnitId": ENTITY, "lines": [{"reference": "A.5.1", "title": "Our policies"}], "dryRun": True}
COMPLETE_BODY = {"note": "Filed with the authority on 20 December."}

# (operationId, method, url, body, permission, step-up). The one table every assertion walks.
REGISTER_ROUTES: list[tuple[str, str, str, Any, str, bool]] = [
    ("getRegisterEntry", "get", f"/api/v1/obligations/{OBLIGATION}/register", None, perms.REGISTER_READ, False),
    ("updateRegister", "patch", f"/api/v1/obligations/{OBLIGATION}/register", STATUS_BODY, perms.REGISTER_EDIT, False),
    ("updateRegisterEntity", "patch", f"/api/v1/obligations/{OBLIGATION}/register/entities/{ENTITY}", STATUS_BODY, perms.REGISTER_EDIT, False),
    ("setApplicability", "put", f"/api/v1/obligations/{OBLIGATION}/applicability", APPLICABILITY_BODY, perms.APPLICABILITY_APPROVE, False),
    ("setApplicabilityMany", "post", "/api/v1/applicability", MANY_BODY, perms.APPLICABILITY_APPROVE, False),
    ("listObligationGaps", "get", f"/api/v1/obligations/{OBLIGATION}/gaps", None, perms.REGISTER_READ, False),
    ("createGap", "post", f"/api/v1/obligations/{OBLIGATION}/gaps", GAP_BODY, perms.GAPS_EDIT, False),
    ("listRegisterGaps", "get", "/api/v1/gaps", None, perms.REGISTER_READ, False),
    ("updateGap", "patch", f"/api/v1/gaps/{RECORD}", GAP_PATCH, perms.GAPS_EDIT, False),
    ("requestRiskAcceptance", "post", f"/api/v1/gaps/{RECORD}/accept-risk", ACCEPT_BODY, perms.GAPS_EDIT, False),
    ("approveRiskAcceptance", "post", f"/api/v1/gaps/{RECORD}/accept-risk/approve", None, perms.RISK_ACCEPT_APPROVE, True),
    ("reopenGap", "post", f"/api/v1/gaps/{RECORD}/reopen", None, perms.GAPS_EDIT, False),
    ("listAssessments", "get", f"/api/v1/obligations/{OBLIGATION}/assessments", None, perms.REGISTER_READ, False),
    ("getInterpretation", "get", f"/api/v1/obligations/{OBLIGATION}/interpretation", None, perms.REGISTER_READ, False),
    ("saveInterpretation", "put", f"/api/v1/obligations/{OBLIGATION}/interpretation", INTERPRETATION_BODY, perms.REGISTER_EDIT, False),
    ("listInternalLinks", "get", f"/api/v1/obligations/{OBLIGATION}/internal-links", None, perms.REGISTER_READ, False),
    ("addInternalLink", "post", f"/api/v1/obligations/{OBLIGATION}/internal-links", LINK_BODY, perms.REGISTER_EDIT, False),
    ("removeInternalLink", "delete", f"/api/v1/internal-links/{RECORD}", None, perms.REGISTER_EDIT, False),
    ("listUnits", "get", f"/api/v1/obligations/{OBLIGATION}/units?entity={ENTITY}", None, perms.REGISTER_READ, False),
    ("createUnit", "post", f"/api/v1/obligations/{OBLIGATION}/units", UNIT_BODY, perms.REGISTER_EDIT, False),
    ("updateUnit", "patch", f"/api/v1/units/{RECORD}", UNIT_PATCH, perms.REGISTER_EDIT, False),
    ("removeUnit", "delete", f"/api/v1/units/{RECORD}", None, perms.REGISTER_EDIT, False),
    ("pasteUnits", "post", f"/api/v1/obligations/{OBLIGATION}/units/paste", PASTE_BODY, perms.REGISTER_EDIT, False),
    ("getStatementOfApplicability", "get", f"/api/v1/obligations/{OBLIGATION}/statement-of-applicability?entity={ENTITY}", None, perms.REGISTER_READ, False),
    ("listDuties", "get", f"/api/v1/obligations/{OBLIGATION}/duties", None, perms.REGISTER_READ, False),
    ("completeDutyOccurrence", "post", f"/api/v1/duty-occurrences/{RECORD}/complete", COMPLETE_BODY, perms.REGISTER_EDIT, False),
]


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class RegisterRouteTable(TestCase):
    def test_the_table_names_every_register_operation_and_nothing_else(self) -> None:
        """A register route added without a row here would be published ungated by this file;
        a row naming no route would prove nothing."""
        registered = {
            op.operation_id
            for op in iter_operations(api)
            if op.view_func.__module__ == "apps.register.api"
        }
        self.assertEqual(registered, {row[0] for row in REGISTER_ROUTES})

    def test_only_the_risk_approval_asks_for_a_step_up(self) -> None:
        """D-75: setting applicability is one person's confirmed answer, with no step-up.
        Accepting a risk keeps its four eyes and its passkey (REG-03)."""
        declared = {
            op.operation_id for op in iter_operations(api) if perms.step_up_of(op.view_func) and op.view_func.__module__ == "apps.register.api"
        }
        self.assertEqual(declared, {"approveRiskAcceptance"})


class RegisterRouteGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        for name, method, url, body, _permission, _step_up in REGISTER_ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_an_agent_key_reaches_no_register_route(self) -> None:
        """The register is a bank's judgement; no key, whatever its scopes, reaches it yet."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES, tenant_id=uuid.uuid4())):
            for name, method, url, body, _permission, _step_up in REGISTER_ROUTES:
                with self.subTest(operation=name):
                    self.assertEqual(_call(self.client, method, url, body, AS_KEY).status_code, 401)

    def test_every_permission_but_its_own_is_403_naming_it(self) -> None:
        """Every other tenant permission and a fresh step-up, so the only thing missing is the
        route's own permission and the 403 can only come from its gate."""
        for name, method, url, body, permission, _step_up in REGISTER_ROUTES:
            everything_else = perms.TENANT_PERMISSIONS - {permission}
            who = user_principal(permissions=everything_else, tenant_id=uuid.uuid4(), step_up_at=timezone.now())
            with self.subTest(operation=name), stub_session(who):
                response = _call(self.client, method, url, body, AS_SESSION)
                self.assertEqual(response.status_code, 403)
                problem = response.json()
                self.assertEqual(problem["code"], "permission_denied")
                self.assertEqual(problem["requiredPermission"], permission)

    def test_the_risk_approval_without_a_fresh_step_up_is_403_step_up_required(self) -> None:
        stale = timezone.now() - timedelta(days=1)
        for step_up_at in (None, stale):
            who = user_principal(permissions=perms.TENANT_PERMISSIONS, tenant_id=uuid.uuid4(), step_up_at=step_up_at)
            with self.subTest(step_up_at=step_up_at), stub_session(who):
                response = self.client.post(f"/api/v1/gaps/{RECORD}/accept-risk/approve", **AS_SESSION)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "step_up_required")

    def test_bad_input_is_422_before_the_stub(self) -> None:
        register = f"/api/v1/obligations/{OBLIGATION}/register"
        applicability = f"/api/v1/obligations/{OBLIGATION}/applicability"
        cases: list[tuple[str, str, str, Any, dict[str, Any]]] = [
            ("updateRegister", "patch", register, {**STATUS_BODY, "tone": "negative"}, {}),
            ("updateRegister", "patch", register, {"statusNote": "x" * 4001}, {}),
            ("setApplicability", "put", applicability, {"applicability": "maybe", "reason": "Certified"}, {}),
            ("setApplicability", "put", applicability, {"applicability": "applies", "reason": ""}, {}),
            ("setApplicability", "put", applicability, {**APPLICABILITY_BODY, "unitId": RECORD}, {}),
            ("setApplicabilityMany", "post", "/api/v1/applicability", {"rows": []}, {}),
            ("createGap", "post", f"/api/v1/obligations/{OBLIGATION}/gaps", {**GAP_BODY, "source": "x" * 65}, {}),
            ("createGap", "post", f"/api/v1/obligations/{OBLIGATION}/gaps", {"severity": "high", "source": "audit"}, {}),
            ("listRegisterGaps", "get", "/api/v1/gaps?limit=101", None, {}),
            ("listRegisterGaps", "get", "/api/v1/gaps?targetFrom=someday", None, {}),
            ("addInternalLink", "post", f"/api/v1/obligations/{OBLIGATION}/internal-links", {"kind": "policy"}, {}),
            ("createUnit", "post", f"/api/v1/obligations/{OBLIGATION}/units", {**UNIT_BODY, "reference": "x" * 65}, {}),
            ("pasteUnits", "post", f"/api/v1/obligations/{OBLIGATION}/units/paste", {**PASTE_BODY, "lines": []}, {}),
            ("getStatementOfApplicability", "get", f"/api/v1/obligations/{OBLIGATION}/statement-of-applicability", None, {}),
            ("saveInterpretation", "put", f"/api/v1/obligations/{OBLIGATION}/interpretation", {"text": ""}, {}),
        ]
        who = user_principal(permissions=perms.TENANT_PERMISSIONS, tenant_id=uuid.uuid4(), step_up_at=timezone.now())
        with stub_session(who):
            for name, method, url, body, extra in cases:
                with self.subTest(operation=name, body=body, headers=extra):
                    response = _call(self.client, method, url, body, {**AS_SESSION, **extra})
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")


# The versioned writes: each reads `If-Match` before its logic runs (INPUT_DELTAS section 4).
IF_MATCH_ROUTES = {
    "updateRegister",
    "updateRegisterEntity",
    "setApplicability",
    "updateGap",
    "saveInterpretation",
    "updateUnit",
    "removeUnit",
}


# The operations whose logic has landed, each proved in its package's own tests.
BUILT = {
    # c8-reg-status (apps/register/tests_status.py)
    "getRegisterEntry",
    "updateRegister",
    "updateRegisterEntity",
    "listObligationGaps",
    "createGap",
    "listRegisterGaps",
    "updateGap",
    "requestRiskAcceptance",
    "approveRiskAcceptance",
    "reopenGap",
    "setApplicability", "setApplicabilityMany",  # c8-reg-applicability, tests_applicability.py
    "listDuties", "completeDutyOccurrence",  # c8-duty-occurrences, tests_duties.py
}


# Operations whose logic has landed, each with the package that built it. Past every gate they
# answer from the logic: for this file's made-up ids, 404 `not_found` in the same problem shape.
BUILT_ROUTES = {
    "listUnits",  # c8-reg-units
    "createUnit",  # c8-reg-units
    "updateUnit",  # c8-reg-units
    "removeUnit",  # c8-reg-units
    "pasteUnits",  # c8-reg-units (the dry run; its commit is c8-units-paste-soa's)
}


class RegisterRouteStubs(TestCase):
    tenant: Any
    person: Any

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant()
        cls.person = factories.member_user(cls.tenant, roles=("compliance_officer",))

    def _everything(self) -> Any:
        return user_principal(
            permissions=perms.TENANT_PERMISSIONS, tenant_id=self.tenant.id, subject_id=self.person.id, step_up_at=timezone.now()
        )

    def test_an_if_match_that_is_not_a_version_is_422_on_every_versioned_write(self) -> None:
        with stub_session(self._everything()):
            for name, method, url, body, _permission, _step_up in REGISTER_ROUTES:
                if name not in IF_MATCH_ROUTES:
                    continue
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, {**AS_SESSION, "HTTP_IF_MATCH": "not-a-version"})
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_a_caller_holding_everything_reaches_the_named_stub(self) -> None:
        """Past every gate, in a real bank as a real member: 501 `not_built`, in the one problem
        shape, with nothing of the server in it. Replaced row by row as each logic lands."""
        with stub_session(self._everything()):
            for name, method, url, body, _permission, _step_up in REGISTER_ROUTES:
                if name in BUILT:
                    continue
                headers = {**AS_SESSION, "HTTP_IF_MATCH": '"3"'} if method in {"patch", "put", "delete"} else AS_SESSION
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, headers)
                    expected = (404, "not_found") if name in BUILT_ROUTES else (501, "not_built")
                    self.assertEqual(response.status_code, expected[0])
                    problem = response.json()
                    self.assertEqual(problem["code"], expected[1])
                    self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                    self.assertNotIn("traceback", response.content.decode().lower())
