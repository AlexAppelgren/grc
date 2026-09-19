"""The three auth classes and the /me and /reference/product routes (playbook 4.2, ID-02,
AC-ID2). The token resolvers are stubbed (chunk 1 fills them); what is pinned here is the
contract: a missing or unknown credential is 401 in the problem shape, SessionAuth
accepts only user principals, EnrolmentAuth only enrolment principals, ApiKeyAuth only
agent principals, and `request.auth` is a Principal with the documented shape.
"""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.test.client import RequestFactory

from apps.shared.authentication import (
    ApiKeyAuth,
    EnrolmentAuth,
    Principal,
    PrincipalKind,
    SessionAuth,
    resolve_api_key,
    resolve_enrolment_token,
    resolve_session_token,
)
from apps.shared.errors import PROBLEM_CONTENT_TYPE
from apps.shared.permissions import LIBRARY_READ
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    enrolment_principal,
    stub_api_key,
    stub_enrolment,
    stub_session,
    user_principal,
)


class ResolversInPhaseZero(TestCase):
    def test_nothing_authenticates_until_chunk_one(self) -> None:
        self.assertIsNone(resolve_session_token("anything"))
        self.assertIsNone(resolve_api_key("anything"))
        self.assertIsNone(resolve_enrolment_token("anything"))


class AuthClasses(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_session_auth_accepts_only_user_principals(self) -> None:
        request = self.factory.get("/", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
        person = user_principal(permissions={LIBRARY_READ})
        with stub_session(person):
            self.assertIs(SessionAuth()(request), person)
        with stub_session(enrolment_principal()):
            self.assertIsNone(SessionAuth()(request))
        with stub_session(person):
            self.assertIsNone(SessionAuth()(self.factory.get("/", HTTP_AUTHORIZATION="Bearer other")))
            self.assertIsNone(SessionAuth()(self.factory.get("/")))

    def test_enrolment_auth_accepts_only_enrolment_principals(self) -> None:
        request = self.factory.get("/", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
        enrolling = enrolment_principal()
        with stub_enrolment(enrolling):
            self.assertIs(EnrolmentAuth()(request), enrolling)
        with stub_enrolment(user_principal()):
            self.assertIsNone(EnrolmentAuth()(request))

    def test_api_key_auth_accepts_only_agent_principals(self) -> None:
        request = self.factory.get("/", HTTP_X_API_KEY=API_KEY_FOR_TESTS)
        agent = agent_principal(scopes={"changes.write"})
        with stub_api_key(agent):
            self.assertIs(ApiKeyAuth()(request), agent)
            self.assertIsNone(ApiKeyAuth()(self.factory.get("/")))
        with stub_api_key(user_principal()):
            self.assertIsNone(ApiKeyAuth()(request))

    def test_principal_shape(self) -> None:
        subject = uuid.uuid4()
        tenant = uuid.uuid4()
        person = Principal(
            kind=PrincipalKind.USER, subject_id=subject, tenant_id=tenant, permissions=frozenset({LIBRARY_READ})
        )
        self.assertTrue(person.has_permission(LIBRARY_READ))
        self.assertFalse(person.has_permission("cases.signoff"))
        self.assertFalse(person.has_scope("changes.write"))
        agent = Principal(kind=PrincipalKind.AGENT, subject_id=subject, scopes=frozenset({"changes.write"}))
        self.assertTrue(agent.has_scope("changes.write"))
        self.assertFalse(agent.has_permission(LIBRARY_READ))
        self.assertIsNone(person.step_up_at)
        self.assertFalse(person.is_platform_staff)


class MeRoute(TestCase):
    def test_401_without_a_session_in_the_problem_shape(self) -> None:
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"], PROBLEM_CONTENT_TYPE)
        body = response.json()
        self.assertEqual(body["code"], "unauthenticated")
        self.assertEqual(body["status"], 401)
        self.assertIn("detail", body)
        self.assertIn("title", body)

    def test_401_with_an_unknown_token(self) -> None:
        response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(response.status_code, 401)

    def test_200_with_a_stubbed_session_in_camel_case(self) -> None:
        person = user_principal(permissions={LIBRARY_READ}, tenant_id=uuid.uuid4())
        with stub_session(person):
            response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kind"], "user")
        self.assertEqual(body["subjectId"], str(person.subject_id))
        self.assertEqual(body["tenantId"], str(person.tenant_id))
        self.assertEqual(body["permissions"], [LIBRARY_READ])
        self.assertEqual(body["scopes"], [])
        self.assertNotIn("subject_id", body, "the API is camelCase (playbook 4.1)")

    def test_the_enrolment_session_may_call_me(self) -> None:
        enrolling = enrolment_principal()
        with stub_enrolment(enrolling):
            response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kind"], "enrolment")
        self.assertEqual(response.json()["permissions"], [])

    def test_an_api_key_cannot_call_me(self) -> None:
        with stub_api_key(agent_principal()):
            response = self.client.get("/api/v1/me", HTTP_X_API_KEY=API_KEY_FOR_TESTS)
        self.assertEqual(response.status_code, 401)


class ProductRoute(TestCase):
    def test_product_name_is_public_and_comes_from_settings(self) -> None:
        with self.settings(PRODUCT_NAME="bleqq compliance"):
            response = self.client.get("/api/v1/reference/product")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"productName": "bleqq compliance"})
        self.assertIn("Server-Timing", response)
        self.assertIn("X-Request-ID", response)
