"""Contract guard for the case routes chunk 5 declares (WAT-04, WAT-05, CAS-01, NFR-01;
`c5-contract-api-screens`).

A bank says what a change means for it and decides which suggested obligation links are
real for it. Both are that bank's own judgement, so both take a person's session with
`cases.work` and neither takes an agent's key: an agent writes the library, never a bank's
case (AGT-01, rule 13). Each route answers 501 `not_built` from the named function in
`cases/so_what.py` or `cases/links.py`, behind its real gate.

Written before the routes existed: every case below failed with 404 until `cases/api.py`
landed and the router was mounted in `config/api.py`.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase

from apps.cases.schemas import SO_WHAT_MAX
from apps.shared import permissions as perms
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)

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
        self.assertEqual(response.status_code, 501, "the cap itself is accepted and reaches the stub")


class CaseRouteStubs(TestCase):
    def test_a_session_with_cases_work_reaches_the_stub(self) -> None:
        with stub_session(user_principal(permissions={perms.CASES_WORK}, tenant_id=uuid.uuid4())):
            for name, method, url, body in CASE_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 501)
                    problem = response.json()
                    self.assertEqual(problem["code"], "not_built")
                    self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                    self.assertNotIn("traceback", response.content.decode().lower())
