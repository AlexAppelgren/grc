"""Contract guard for the watch routes an agent or a library editor writes through
(WAT-01 to WAT-04, AGT-01, AGT-02, NFR-01, chunk 5 `c5-contract-api-agent`).

Each route is declared before the logic that serves it and answers 501 `not_built` from
the named function in the module that will build it. What stands in front of that stub is
what this file proves, per route: no credential is 401, the wrong scope or permission is
403 naming what was needed, and a body the schema does not accept is 422 — a term, a tone
or a colour never rides along unseen. Written before the routes existed (2026-09-20):
every case below failed with 404 until `watch/api.py` landed.

The library fence is not weakened here: none of these routes writes an inventory row, and
the modules they name (`watch/sources.py`, `registration.py`, `curation.py`) hold nothing
but their stubs until their own tasks land.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase

from apps.shared import permissions as perms
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from apps.watch.schemas import LINKS_MAX

CHANGE = "11111111-1111-4111-8111-111111111111"
EVENT = "22222222-2222-4222-8222-222222222222"
SOURCE = "33333333-3333-4333-8333-333333333333"
OBLIGATION = "44444444-4444-4444-8444-444444444444"

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

SOURCE_BODY = {"name": "Finansinspektionen news", "kind": "authority_site", "checkFrequency": "daily"}
SOURCE_PATCH = {"active": False}
CHANGE_BODY = {
    "stableKey": "fi-2026-14",
    "title": "New reporting rules",
    "changeType": "adopted",
    "authorityLabel": "Finansinspektionen",
    "summary": "Reporting moves to a quarterly cycle.",
    "sourceLabel": "FI news",
    "sourceUrl": "https://www.fi.se/en/published/news/2026/",
}
CHANGE_PATCH = {"keyDateLabel": "Transition ends"}
EVENT_BODY = {"label": "Consultation closes", "eventDate": "2026-11-01", "datePrecision": "day"}
DOCUMENT_BODY = {"url": "https://www.fi.se/en/published/news/2026/reporting/"}
LINKS_BODY = [{"obligationId": OBLIGATION, "confidence": 0.8}]

# Routes an agent key writes and a library editor's session may also write (the change
# facts of WAT-02 and WAT-03): (name, method, url, body, scope, permission).
BOTH_ROUTES = [
    ("createChange", "post", "/api/v1/changes", CHANGE_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("updateChange", "patch", f"/api/v1/changes/{CHANGE}", CHANGE_PATCH, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("addChangeEvent", "post", f"/api/v1/changes/{CHANGE}/events", EVENT_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("updateChangeEvent", "patch", f"/api/v1/changes/{CHANGE}/events/{EVENT}", EVENT_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("replaceChangeObligations", "put", f"/api/v1/changes/{CHANGE}/obligations", LINKS_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
]
# Routes only an agent key writes: (name, method, url, body, scope).
KEY_ROUTES = [
    ("addChangeDocument", "post", f"/api/v1/changes/{CHANGE}/documents", DOCUMENT_BODY, perms.SCOPE_CHANGES_WRITE),
]
# Reads a person's session or a key with library:read may make: (name, url, scope, permission).
READ_ROUTES = [
    ("listSources", "/api/v1/sources", perms.SCOPE_LIBRARY_READ, perms.WATCH_READ),
    ("getSourceCoverage", "/api/v1/sources/coverage", perms.SCOPE_LIBRARY_READ, perms.WATCH_READ),
]
# Routes only a library editor's session writes: (name, method, url, body, permission).
SESSION_ROUTES = [
    ("createSource", "post", "/api/v1/sources", SOURCE_BODY, perms.SOURCES_MANAGE),
    ("updateSource", "patch", f"/api/v1/sources/{SOURCE}", SOURCE_PATCH, perms.SOURCES_MANAGE),
]


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class WatchRouteGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        cases = (
            [(n, m, u, b) for n, m, u, b, _, _ in BOTH_ROUTES]
            + [(n, m, u, b) for n, m, u, b, _ in KEY_ROUTES]
            + [(n, "get", u, None) for n, u, _, _ in READ_ROUTES]
            + [(n, m, u, b) for n, m, u, b, _ in SESSION_ROUTES]
        )
        for name, method, url, body in cases:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_key_without_the_scope_is_403_naming_it(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_UPCOMING_READ})):
            cases = (
                [(n, m, u, b, s) for n, m, u, b, s, _ in BOTH_ROUTES]
                + [(n, m, u, b, s) for n, m, u, b, s in KEY_ROUTES]
                + [(n, "get", u, None, s) for n, u, s, _ in READ_ROUTES]
            )
            for name, method, url, body, scope in cases:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], scope)

    def test_a_session_without_the_permission_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.CASES_READ}, tenant_id=uuid.uuid4())):
            cases = (
                [(n, m, u, b, p) for n, m, u, b, _, p in BOTH_ROUTES]
                + [(n, "get", u, None, p) for n, u, _, p in READ_ROUTES]
                + [(n, m, u, b, p) for n, m, u, b, p in SESSION_ROUTES]
            )
            for name, method, url, body, permission in cases:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], permission)

    def test_a_key_never_registers_a_source(self) -> None:
        """The registry is a library editor's (WAT-01): no scope adds or deactivates a source."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body, _ in SESSION_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 401)

    def test_a_person_never_attaches_a_document(self) -> None:
        """Fetched pages arrive from the agent that screened them (AGT-07), not from a screen."""
        with stub_session(user_principal(permissions=perms.ALL_PERMISSIONS, tenant_id=uuid.uuid4())):
            for name, method, url, body, _ in KEY_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 401)

    def test_bad_input_is_422_before_the_stub(self) -> None:
        cases = [
            ("createChange", "post", "/api/v1/changes", {k: v for k, v in CHANGE_BODY.items() if k != "title"}),
            ("createChange", "post", "/api/v1/changes", {**CHANGE_BODY, "sourceUrl": "not a url"}),
            ("createChange", "post", "/api/v1/changes", {**CHANGE_BODY, "tone": "negative"}),
            ("updateChange", "patch", f"/api/v1/changes/{CHANGE}", {"status": "retired"}),
            ("addChangeEvent", "post", f"/api/v1/changes/{CHANGE}/events", {"eventDate": "2026-11-01"}),
            ("addChangeEvent", "post", f"/api/v1/changes/{CHANGE}/events", {**EVENT_BODY, "datePrecision": "decade"}),
            ("addChangeDocument", "post", f"/api/v1/changes/{CHANGE}/documents", {"url": ""}),
            ("replaceChangeObligations", "put", f"/api/v1/changes/{CHANGE}/obligations", [{"confidence": 0.5}]),
        ]
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body in cases:
                with self.subTest(operation=name, body=body):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_the_obligation_links_a_call_may_carry_are_capped(self) -> None:
        """This route takes its list as the whole body, so the cap sits on the route rather
        than on a schema field, and is the `LINKS_MAX` the same list carries inside
        `WatchChangeInput` (WAT-04). A key sends it, and an uncapped array would be an
        unbounded body to parse. The body is built here, not in the table above, so a
        failure names the case instead of printing two hundred links."""
        url = f"/api/v1/changes/{CHANGE}/obligations"
        link = {"obligationId": OBLIGATION, "confidence": 0.5}
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            refused = _call(self.client, "put", url, [link] * (LINKS_MAX + 1), AS_KEY)
            at_the_cap = _call(self.client, "put", url, [link] * LINKS_MAX, AS_KEY)
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["code"], "validation_error")
        self.assertEqual(at_the_cap.status_code, 501, "the cap itself is accepted and reaches the stub")

    def test_a_source_write_refuses_an_unknown_field(self) -> None:
        with stub_session(user_principal(permissions={perms.SOURCES_MANAGE})):
            response = _call(self.client, "post", "/api/v1/sources", {**SOURCE_BODY, "colour": "red"}, AS_SESSION)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")


class WatchRouteStubs(TestCase):
    def assert_not_built(self, response: Any) -> None:
        self.assertEqual(response.status_code, 501)
        problem = response.json()
        self.assertEqual(problem["code"], "not_built")
        self.assertEqual(response.headers["Content-Type"], "application/problem+json")
        self.assertNotIn("traceback", response.content.decode().lower())

    def test_a_key_with_its_scope_reaches_the_stub(self) -> None:
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            cases = (
                [(n, m, u, b) for n, m, u, b, _, _ in BOTH_ROUTES]
                + [(n, m, u, b) for n, m, u, b, _ in KEY_ROUTES]
                + [(n, "get", u, None) for n, u, _, _ in READ_ROUTES]
            )
            for name, method, url, body in cases:
                with self.subTest(operation=name):
                    self.assert_not_built(_call(self.client, method, url, body, AS_KEY))

    def test_a_session_with_its_permission_reaches_the_stub(self) -> None:
        permissions = {perms.PROPOSALS_REVIEW, perms.SOURCES_MANAGE, perms.WATCH_READ}
        with stub_session(user_principal(permissions=permissions, tenant_id=uuid.uuid4())):
            cases = (
                [(n, m, u, b) for n, m, u, b, _, _ in BOTH_ROUTES]
                + [(n, "get", u, None) for n, u, _, _ in READ_ROUTES]
                + [(n, m, u, b) for n, m, u, b, _ in SESSION_ROUTES]
            )
            for name, method, url, body in cases:
                with self.subTest(operation=name):
                    self.assert_not_built(_call(self.client, method, url, body, AS_SESSION))
