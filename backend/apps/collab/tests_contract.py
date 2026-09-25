"""Contract guard for the eight collab operations: the notification inbox, the comments on a
record and a person's own comments and mentions on My work (COL-01, COL-02, HOM-05;
`c10-collab-contract`).

Every route is declared before its logic and answers 501 `not_built` until the module that
owns it lands. What stands in front of a route is what this file proves: no credential is
401, an agent's key is 401 whatever it holds, an enrolment session is 403 `enrolment_only`,
a session without `comments.write` is 403 naming it on the three writes, a platform session
is 404 because it belongs to no bank, and a value the schema does not accept is 422 — all
before the 501. Written before the routes existed: every case below answered 404 until
`collab/api.py` was mounted.

When a module lands, its rows here move from 501 to what the logic answers for a session
that passes every gate; the gates themselves stay.
"""

from __future__ import annotations

from typing import Any, get_args

from django.test import TestCase

from apps.collab.models import NotificationKind
from apps.collab.schemas import CollabNotificationKind
from apps.identity.models import UserStatus
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.routes import iter_operations
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    sign_in,
    stub_api_key,
    stub_session,
    user_principal,
)
from config.api import api

SUBJECT = "11111111-1111-4111-8111-111111111111"
THING = "22222222-2222-4222-8222-222222222222"

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

COMMENT_BODY = {"subjectType": "change_case", "subjectId": SUBJECT, "body": "Can you check the custody angle?"}
PATCH_BODY = {"body": "Can you check the custody angle before Friday?"}

# (operationId, method, url, body)
READS = [
    ("listNotifications", "get", "/api/v1/notifications", None),
    ("listComments", "get", f"/api/v1/comments?subjectType=change_case&subjectId={SUBJECT}", None),
    ("listMyComments", "get", "/api/v1/me/comments?about=mentioned", None),
]
OWN_WRITES = [
    ("markNotificationRead", "post", f"/api/v1/notifications/{THING}/read", None),
    ("markAllNotificationsRead", "post", "/api/v1/notifications/read-all", None),
]
COMMENT_WRITES = [
    ("addComment", "post", "/api/v1/comments", COMMENT_BODY),
    ("editComment", "patch", f"/api/v1/comments/{THING}", PATCH_BODY),
    ("deleteComment", "delete", f"/api/v1/comments/{THING}", None),
]
ROUTES = READS + OWN_WRITES + COMMENT_WRITES


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class CollabRouteGates(TestCase):
    tenant: Any
    person: Any

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant()
        cls.person = factories.member(cls.tenant, roles=("reader",)).user

    def _member(self, permissions: set[str]) -> Any:
        return stub_session(
            user_principal(permissions=permissions, tenant_id=self.tenant.id, subject_id=self.person.id)
        )

    def test_no_credential_is_401(self) -> None:
        for name, method, url, body in ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_an_agent_key_never_reaches_a_notification_or_a_comment(self) -> None:
        """A notification is one person's and a comment is one bank's own text: no scope
        reaches either, whatever the key holds."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES, tenant_id=self.tenant.id)):
            for name, method, url, body in ROUTES:
                with self.subTest(operation=name):
                    self.assertEqual(_call(self.client, method, url, body, AS_KEY).status_code, 401)

    def test_an_enrolment_session_is_403_on_every_route(self) -> None:
        enrolling = factories.user(status=UserStatus.INVITED)
        headers = sign_in(enrolling, tenant=self.tenant, kind="enrolment")
        for name, method, url, body in ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "enrolment_only")

    def test_the_three_comment_writes_need_comments_write_before_the_stub(self) -> None:
        with self._member({perms.CASES_READ, perms.REGISTER_READ}):
            for name, method, url, body in COMMENT_WRITES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], perms.COMMENTS_WRITE)

    def test_the_reads_and_the_own_writes_need_no_permission(self) -> None:
        """The inbox and My work are the caller's own; a comment read is gated per record by
        the logic, so the route asks for nothing a member could lack."""
        with self._member(set()):
            for name, method, url, body in READS + OWN_WRITES:
                with self.subTest(operation=name):
                    self.assertEqual(_call(self.client, method, url, body, AS_SESSION).status_code, 501)

    def test_a_platform_session_belongs_to_no_bank_and_gets_404(self) -> None:
        with stub_session(user_principal(permissions={perms.COMMENTS_WRITE}, subject_id=self.person.id)):
            for name, method, url, body in ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["code"], "not_found")

    def test_bad_input_is_422_before_the_stub(self) -> None:
        cases = [
            ("listMyComments", "get", "/api/v1/me/comments?about=everything", None),
            ("listMyComments", "get", "/api/v1/me/comments", None),
            ("listMyComments", "get", "/api/v1/me/comments?about=written&limit=101", None),
            ("listNotifications", "get", "/api/v1/notifications?limit=0", None),
            ("listComments", "get", "/api/v1/comments?subjectType=change_case", None),
            ("listComments", "get", "/api/v1/comments?subjectType=change_case&subjectId=not-a-uuid", None),
            ("listComments", "get", f"/api/v1/comments?subjectType={'x' * 65}&subjectId={SUBJECT}", None),
            ("addComment", "post", "/api/v1/comments", {**COMMENT_BODY, "body": ""}),
            ("addComment", "post", "/api/v1/comments", {**COMMENT_BODY, "tone": "negative"}),
            ("addComment", "post", "/api/v1/comments", {**COMMENT_BODY, "mentionUserIds": ["not-a-uuid"]}),
            ("addComment", "post", "/api/v1/comments", {"subjectType": "change_case", "body": "No subject."}),
            ("editComment", "patch", f"/api/v1/comments/{THING}", {"body": ""}),
            ("editComment", "patch", f"/api/v1/comments/{THING}", {**PATCH_BODY, "mentionUserIds": []}),
        ]
        with self._member({perms.COMMENTS_WRITE}):
            for name, method, url, body in cases:
                with self.subTest(operation=name, url=url, body=body):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_a_member_past_every_gate_reaches_the_stub(self) -> None:
        """Past every gate: 501 `not_built`, in the one problem shape, with nothing of the
        server in it. Each row moves to what its logic answers when its module lands."""
        with self._member({perms.COMMENTS_WRITE}):
            for name, method, url, body in ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 501)
                    self.assertEqual(response.json()["code"], "not_built")
                    self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                    self.assertNotIn("traceback", response.content.decode().lower())


class CollabContractShape(TestCase):
    def test_the_eight_operations_are_published_with_their_ids_and_gates(self) -> None:
        # The participant routes (c8-participants) are gated and pinned in tests_participants.py.
        collab = {
            op.operation_id: op
            for op in iter_operations(api)
            if op.view_func.__module__ == "apps.collab.api" and "/participants" not in op.path
        }
        self.assertEqual(set(collab), {name for name, _, _, _ in ROUTES})
        gated = {name for name, op in collab.items() if perms.gate_of(op.view_func) is not None}
        self.assertEqual(gated, {"editComment", "deleteComment"})
        for name in ("editComment", "deleteComment"):
            gate = perms.gate_of(collab[name].view_func)
            assert gate is not None
            self.assertEqual((gate.kind, gate.value), ("permission", perms.COMMENTS_WRITE))
        for name, op in collab.items():
            with self.subTest(operation=name):
                self.assertFalse(getattr(op.view_func, "__cw_step_up__", False), "no collab write asks for a step-up")

    def test_the_published_notification_kinds_are_the_models_kinds(self) -> None:
        self.assertEqual(set(get_args(CollabNotificationKind)), {kind.value for kind in NotificationKind})

    def test_no_comment_text_rides_in_a_path_or_a_query_string(self) -> None:
        """Kinds and ids may; a body never does (CHUNK10_TASKS ruling 9)."""
        schema = api.get_openapi_schema()
        for path, item in schema["paths"].items():
            if "comment" not in path and "notification" not in path:
                continue
            for method, operation in item.items():
                names = {parameter["name"] for parameter in operation.get("parameters", [])}
                with self.subTest(route=f"{method.upper()} {path}"):
                    self.assertNotIn("body", names)
                    self.assertTrue(names <= {"subjectType", "subjectId", "limit", "offset", "unread", "about", "notification_id", "comment_id"}, names)
