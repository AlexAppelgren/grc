"""The three auth classes and the /me and /reference/product routes (playbook 4.2, ID-02,
AC-ID2). The contract pinned here: a missing or unknown credential is 401 in the problem
shape, an enrolment token on any other route is 403 enrolment_only, SessionAuth accepts
only user principals, EnrolmentAuth only enrolment principals, ApiKeyAuth only agent
principals (by header or `cw_` bearer), and `request.auth` is a Principal with the
documented shape. The resolvers are the real ones since chunk 1; the stubs remain for
scenarios that need a principal without a ceremony.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase
from django.test.client import RequestFactory

from apps.shared import authentication
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


class Resolvers(TestCase):
    def test_an_unknown_credential_resolves_to_nothing(self) -> None:
        self.assertIsNone(resolve_session_token("anything"))
        self.assertIsNone(resolve_api_key("anything"))
        self.assertIsNone(resolve_enrolment_token("anything"))
        self.assertIsNone(resolve_api_key("cw_deadbeef_nope"))


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
        agent = agent_principal(scopes={"changes:write"})
        with stub_api_key(agent):
            self.assertIs(ApiKeyAuth()(request), agent)
            self.assertIsNone(ApiKeyAuth()(self.factory.get("/")))
        with stub_api_key(user_principal()):
            self.assertIsNone(ApiKeyAuth()(request))

    def test_api_key_auth_also_reads_a_cw_bearer_token(self) -> None:
        """Chunk 1 brief: `Authorization: Bearer cw_<prefix>_<secret>`; a session bearer is
        not offered to the key resolver at all."""
        agent = agent_principal(scopes={"changes:write"})
        with mock.patch.object(authentication, "resolve_api_key", lambda key: agent if key == "cw_abc_def" else None):
            self.assertIs(ApiKeyAuth()(self.factory.get("/", HTTP_AUTHORIZATION="Bearer cw_abc_def")), agent)
            self.assertIsNone(ApiKeyAuth()(self.factory.get("/", HTTP_AUTHORIZATION="Bearer v1.session.token")))

    def test_principal_shape(self) -> None:
        subject = uuid.uuid4()
        tenant = uuid.uuid4()
        person = Principal(
            kind=PrincipalKind.USER, subject_id=subject, tenant_id=tenant, permissions=frozenset({LIBRARY_READ})
        )
        self.assertTrue(person.has_permission(LIBRARY_READ))
        self.assertFalse(person.has_permission("cases.signoff"))
        self.assertFalse(person.has_scope("changes:write"))
        agent = Principal(kind=PrincipalKind.AGENT, subject_id=subject, scopes=frozenset({"changes:write"}))
        self.assertTrue(agent.has_scope("changes:write"))
        self.assertFalse(agent.has_permission(LIBRARY_READ))
        self.assertIsNone(person.step_up_at)
        self.assertFalse(person.is_platform_staff)


class MeRoute(TestCase):
    """`GET /me` in its chunk 1 shape (identity app): user, tenant, roles, permissions,
    platform roles, enrolment state, passkey count, step-up validity."""

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

    def test_200_with_a_real_session_in_camel_case(self) -> None:
        from apps.shared import factories
        from apps.shared.testing import sign_in

        tenant = factories.tenant()
        membership = factories.member(tenant, roles=("reader",))
        response = self.client.get("/api/v1/me", **sign_in(membership.user, tenant=tenant))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user"]["id"], str(membership.user.id))
        self.assertEqual(body["tenant"]["slug"], tenant.slug)
        self.assertEqual([role["key"] for role in body["roles"]], ["reader"])
        self.assertEqual(body["roles"][0]["label"], "Reader")
        self.assertIn(LIBRARY_READ, body["permissions"])
        self.assertEqual(body["platformRoles"], [])
        self.assertFalse(body["enrolmentPending"])
        self.assertEqual(body["passkeyCount"], 0)
        self.assertIsNone(body["stepUpValidUntil"])
        self.assertNotIn("subject_id", body, "the API is camelCase (playbook 4.1)")

    def test_the_enrolment_session_may_call_me_and_nothing_else(self) -> None:
        from apps.shared import factories
        from apps.shared.testing import sign_in

        tenant = factories.tenant()
        person = factories.user(status=__import__("apps.identity.models", fromlist=["UserStatus"]).UserStatus.INVITED)
        headers = sign_in(person, tenant=tenant, kind="enrolment")
        response = self.client.get("/api/v1/me", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enrolmentPending"])
        self.assertEqual(response.json()["permissions"], [])
        refused = self.client.get("/api/v1/tenant/roles", **headers)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["code"], "enrolment_only")

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
