"""Scenario tests for the identity app (playbook 4.1, Appendix B): one method per
`@integration` scenario in app.md, each carrying its ID. Chunk 1 un-skips ID-S1 to S15,
S18 to S22 and S26 (Alex, 2026-09-19: tests first). ID-S16, S17, S23, S24 and S27 to S29
stay skipped (R2/R3). Never delete a scenario without updating app.md.

Operations exercised (the audit-on-write guard reads these names): openInvitation,
verifyInvitationCode, requestCode, verifyCode, passkeyRegisterOptions, passkeyRegisterVerify,
passkeyAuthenticateOptions, passkeyAuthenticateVerify, stepUpOptions, stepUpVerify,
refreshSession, signOut, updateMe, renameMyPasskey, removeMyPasskey, revokeMySession,
inviteMember, updateMember, deactivateMember, revokeMemberSessions, reissueEnrolment,
resendInvitation, revokeInvitation, createRole, updateRole, retireRole, createApiKey,
revokeApiKey, markVisit.

The ceremonies run for real against py_webauthn through the software authenticator in
tests_webauthn_support.py; the emailed link and code are read from the mock mailer.

Prefixes hosted: ID.
"""

from __future__ import annotations

import ast
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock, skip

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.identity import api_keys_logic, roles_logic, tokens
from apps.identity.models import (
    ApiKey,
    Invitation,
    InvitationKind,
    LoginEvent,
    LoginEventKind,
    LoginMethod,
    Membership,
    OtpCode,
    PlatformRole,
    PlatformRoleAssignment,
    TenantRole,
    User,
    UserSession,
    UserStatus,
    WebAuthnCredential,
)
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.library.seeds import seed_languages
from apps.shared import factories, permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.authentication import ApiKeyAuth
from apps.shared.models import AuditEvent
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in
from config.api import api

ANNA = "anna@bank.example"
CHROME_ON_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
LINK = re.compile(r"/invite#(\S+)")
CODE = re.compile(r"Your code is (\d+)")
COOKIE = settings.REFRESH_COOKIE_NAME
# The library bookmark of ID-S31 starts here, months before any test runs: the move is
# proven by the stamp leaving this anchor, never by comparing it with today (CLAUDE.md §11).
SEEN_BEFORE = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)

# Every non-GET route an API key's scope reaches, frozen so that none lands unreviewed
# (ID-10, AC-PRO1). ID-S21 asserts the registered scope-gated set equals this one, so a new
# agent-writable route fails the scenario until someone adds its line and says here why a
# key may make that call. None of them touches a library record: the library's only door is
# a proposal, and what each route does behind its scope is its own app's scenario.
AGENT_WRITABLE_ROUTES: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("POST", "/agent-runs", perms.SCOPE_AGENT_RUNS_WRITE),  # an agent opens its own run (AGT-01)
        ("PATCH", "/agent-runs/{run_id}", perms.SCOPE_AGENT_RUNS_WRITE),  # and closes it (AGT-01)
        ("POST", "/agent-runs/{run_id}/source-checks", perms.SCOPE_SOURCES_WRITE),  # what the run checked (WAT-01)
        ("POST", "/changes/{change_id}/documents", perms.SCOPE_CHANGES_WRITE),  # a page it screened (AGT-07)
        ("POST", "/search/similar", perms.SCOPE_SEARCH_READ),  # a read over POST: what already exists (AGT-02)
    }
)


def _find(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    assert match is not None, f"{pattern.pattern!r} not found in the mail body"
    return match.group(1)


class IdentityScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.identity, one method per @integration scenario."""

    def setUp(self) -> None:
        MockMailer.reset()
        cache.clear()
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.admin = factories.member(
            self.tenant, roles=("admin",), user_row=factories.user(email="erik@bank.example", name="Erik Holm")
        ).user
        self.second_admin = factories.member(
            self.tenant, roles=("admin",), user_row=factories.user(email="maria@bank.example", name="Maria Ek")
        ).user

    # --- helpers --------------------------------------------------------------------------
    def _bearer(self, token: str) -> dict[str, Any]:
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _cookie(self, value: str) -> dict[str, Any]:
        return {"HTTP_COOKIE": f"{COOKIE}={value}"}

    def _post(self, path: str, body: dict[str, Any] | None = None, **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"/api/v1{path}", data=body or {}, content_type="application/json", **extra)

    def _invite(self, email: str = ANNA, roles: tuple[str, ...] = ("compliance_officer", "reader")) -> tuple[Invitation, str]:
        response = self._post("/tenant/members", {"email": email, "roleKeys": list(roles)}, **sign_in(self.admin, tenant=self.tenant))
        self.assertEqual(response.status_code, 201, response.content)
        token = _find(LINK, MockMailer.sent[-1].body)
        self.activate(self.tenant)
        return Invitation.objects.get(pk=response.json()["id"]), token

    def _open_and_get_code(self, token: str) -> str:
        response = self._post("/auth/invitations/open", {"token": token})
        self.assertEqual(response.status_code, 202, response.content)
        return _find(CODE, MockMailer.sent[-1].body)

    def _verify_code(self, email: str, code: str) -> Any:
        return self._post("/auth/code/verify", {"email": email, "code": code})

    def _verify_invitation(self, token: str, code: str) -> Any:
        return self._post("/auth/invitations/verify", {"token": token, "code": code})

    def _register(self, access_token: str, authenticator: SoftwareAuthenticator, nickname: str | None = None) -> Any:
        """The screen sends no nickname (the server names the passkey from the device); a
        nickname is still accepted when given."""
        options = self._post("/auth/passkeys/register/options", **self._bearer(access_token))
        self.assertEqual(options.status_code, 200, options.content)
        body: dict[str, Any] = {"credential": authenticator.register(options.json())}
        if nickname is not None:
            body["nickname"] = nickname
        return self._post("/auth/passkeys/register/verify", body, HTTP_USER_AGENT=CHROME_ON_WINDOWS, **self._bearer(access_token))

    def _enrol(self, email: str = ANNA, nickname: str | None = None) -> tuple[User, SoftwareAuthenticator, dict[str, Any], str]:
        """Invite, open the link, verify the code, register the first passkey. Returns the
        user, the authenticator, the enrolment-complete response body and the refresh cookie."""
        _, token = self._invite(email)
        code = self._open_and_get_code(token)
        verified = self._verify_code(email, code)
        self.assertEqual(verified.status_code, 200, verified.content)
        authenticator = SoftwareAuthenticator()
        registered = self._register(verified.json()["accessToken"], authenticator, nickname)
        self.assertEqual(registered.status_code, 201, registered.content)
        return User.objects.get(email=email), authenticator, registered.json(), registered.cookies[COOKIE].value

    def _sign_in(self, authenticator: SoftwareAuthenticator) -> Any:
        options = self._post("/auth/passkeys/authenticate/options")
        self.assertEqual(options.status_code, 200, options.content)
        return self._post("/auth/passkeys/authenticate/verify", {"credential": authenticator.assert_(options.json())})

    def _step_up(self, access_token: str, authenticator: SoftwareAuthenticator) -> Any:
        options = self._post("/auth/step-up/options", **self._bearer(access_token))
        self.assertEqual(options.status_code, 200, options.content)
        return self._post("/auth/step-up/verify", {"credential": authenticator.assert_(options.json())}, **self._bearer(access_token))

    def _admin_with_passkey(self, user: User) -> SoftwareAuthenticator:
        """A software authenticator whose key is the user's stored passkey, so the real
        step-up ceremony verifies."""
        authenticator = SoftwareAuthenticator()
        authenticator.user_handle = user.id.bytes
        factories.passkey(user, public_key=tokens.b64url(authenticator.cose_public_key()), credential_id=authenticator.credential_id_b64)
        return authenticator

    def _later(self, **delta: int) -> Any:  # compliance: allow-kwargs test helper forwarding timedelta fields
        return mock.patch.object(timezone, "now", return_value=timezone.now() + timedelta(**delta))

    # --- scenarios ------------------------------------------------------------------------
    def test_id_s1(self) -> None:
        """ID-S1

        An invitation carries roles and a single-use token that expires (ID-01).
        """
        invitation, token = self._invite()
        self.assertEqual(invitation.kind, InvitationKind.INVITE.value)
        self.assertEqual(sorted(invitation.role_links.values_list("role__key", flat=True)), ["compliance_officer", "reader"])
        self.assertEqual(invitation.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(invitation.token_hash, token)
        self.assertEqual(len(MockMailer.sent), 1, "the plain token appears only in the emailed link")
        self.assertEqual(MockMailer.sent[0].to, ANNA)
        self.assertNotIn(token, str(AuditEvent.objects.filter(subject_id=invitation.id).values()))
        # Expired: opening after INVITATION_TTL_HOURS (a setting) answers 410.
        with self._later(hours=settings.INVITATION_TTL_HOURS + 1):
            expired = self._post("/auth/invitations/open", {"token": token})
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(expired.json()["code"], "invitation_expired")
        # Consumed: after enrolment the same link answers 410 too.
        user, authenticator, body, _ = self._enrol("bo@bank.example")
        self.activate(self.tenant)
        consumed_token = _find(LINK, next(m.body for m in MockMailer.sent if m.to == "bo@bank.example" and "/invite#" in m.body))
        consumed = self._post("/auth/invitations/open", {"token": consumed_token})
        self.assertEqual(consumed.status_code, 410)
        self.assertEqual(consumed.json()["code"], "invitation_expired")
        # An unknown token is 410 as well: the answer never says which.
        self.assertEqual(self._post("/auth/invitations/open", {"token": "not-a-token"}).status_code, 410)

    def test_id_s2(self) -> None:
        """ID-S2

        Opening the invitation sends a six-digit code within its limits (ID-02).
        """
        _, token = self._invite()
        sent_before = len(MockMailer.sent)
        code = self._open_and_get_code(token)
        self.assertEqual(len(MockMailer.sent), sent_before + 1, "exactly one code mail")
        self.assertEqual(MockMailer.sent[-1].to, ANNA)
        self.assertEqual(len(code), settings.ENROLMENT_CODE_DIGITS)
        self.assertTrue(code.isdigit())
        row = OtpCode.objects.get(email=ANNA, consumed_at__isnull=True)
        self.assertNotEqual(row.code_hash, code)
        self.assertEqual(row.code_hash, tokens.hash_code(code, row.salt))
        self.assertEqual(row.max_attempts, settings.ENROLMENT_CODE_MAX_ATTEMPTS)
        self.assertAlmostEqual(
            row.expires_at, row.created_at + timedelta(minutes=settings.ENROLMENT_CODE_TTL_MINUTES), delta=timedelta(seconds=5)
        )
        # The link's token and the code alone verify; no email address travels. A code
        # issued for another address is refused with this token.
        _, other_token = self._invite("bo@bank.example")
        other_code = self._open_and_get_code(other_token)
        if other_code != code:
            refused = self._verify_invitation(token, other_code)
            self.assertEqual((refused.status_code, refused.json()["code"]), (400, "invalid_code"))
        verified = self._verify_invitation(token, code)
        self.assertEqual(verified.status_code, 200, verified.content)
        self.assertEqual(verified.json()["sessionKind"], "enrolment")
        # The limit per address (a setting) fires on the request after it, with the
        # rate limiter switched on for this one proof (config/test_settings.py override 6).
        with override_settings(RATE_LIMITING_ENABLED=True, E2E_MODE=False):
            cache.clear()
            for _ in range(settings.ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR):
                self.assertEqual(self._post("/auth/code/request", {"email": ANNA}).status_code, 202)
            limited = self._post("/auth/code/request", {"email": ANNA})
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["code"], "rate_limited")

    def test_id_s3(self) -> None:
        """ID-S3

        A wrong code is refused and locks after five attempts (ID-02).
        """
        _, token = self._invite()
        code = self._open_and_get_code(token)
        wrong = "000000" if code != "000000" else "111111"
        with mock.patch.object(tokens.secrets, "compare_digest", wraps=secrets.compare_digest) as compare:
            for attempt in range(settings.ENROLMENT_CODE_MAX_ATTEMPTS):
                response = self._verify_code(ANNA, wrong)
                self.assertEqual(response.status_code, 400, f"attempt {attempt + 1}")
                self.assertEqual(response.json()["code"], "invalid_code")
            self.assertEqual(compare.call_count, settings.ENROLMENT_CODE_MAX_ATTEMPTS, "every attempt compares in constant time")
        locked = self._verify_code(ANNA, code)
        self.assertEqual(locked.status_code, 400)
        self.assertEqual(locked.json()["code"], "code_locked")
        events = LoginEvent.objects.filter(email=ANNA, method=LoginMethod.EMAIL_CODE.value, success=False)
        self.assertGreaterEqual(events.filter(event=LoginEventKind.CODE_FAILED.value).count(), settings.ENROLMENT_CODE_MAX_ATTEMPTS - 1)
        self.assertGreaterEqual(events.filter(event=LoginEventKind.CODE_LOCKED.value).count(), 1)

    def test_id_s4(self) -> None:
        """ID-S4

        The enrolment session reaches only passkey registration and GET /me (ID-02, AC-ID2).
        """
        _, token = self._invite()
        code = self._open_and_get_code(token)
        verified = self._verify_code(ANNA, code)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()["sessionKind"], "enrolment")
        enrolment_token = verified.json()["accessToken"]
        me = self.client.get("/api/v1/me", **self._bearer(enrolment_token))
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json()["enrolmentPending"])
        for path in ("/tenant", "/tenant/roles", "/tenant/members", "/me/passkeys", "/me/sessions"):
            with self.subTest(path=path):
                refused = self.client.get(f"/api/v1{path}", **self._bearer(enrolment_token))
                self.assertEqual(refused.status_code, 403)
                self.assertEqual(refused.json()["code"], "enrolment_only")
        registered = self._register(enrolment_token, SoftwareAuthenticator(), "Laptop")
        self.assertEqual(registered.status_code, 201)

    def test_id_s5(self) -> None:
        """ID-S5

        The first passkey activates the account and asks for a second one (ID-02, ID-03).
        """
        user, authenticator, body, _ = self._enrol(nickname=None)
        row = WebAuthnCredential.objects.get(user=user)
        self.assertEqual(row.credential_id, authenticator.credential_id_b64)
        self.assertEqual(tokens.b64url_decode(row.public_key), authenticator.cose_public_key())
        self.assertEqual(row.sign_count, 0)
        self.assertEqual(row.transports, ["internal", "hybrid"])
        self.assertEqual(row.aaguid, "00000000-0000-0000-0000-000000000000")
        self.assertTrue(row.backup_eligible)
        self.assertTrue(row.backed_up)
        self.assertEqual(row.device_type, "multi_device")
        # No name was sent: the zero AAGUID names no provider, so the registering browser
        # does (apps/identity/passkey_names.py), and the confirmation shows the same name.
        self.assertEqual(row.nickname, "Chrome on Windows")
        self.assertEqual(body["passkey"]["nickname"], "Chrome on Windows")
        self.assertIsNotNone(row.created_at)
        self.assertIsNotNone(row.last_used_at)
        self.assertEqual(user.status, UserStatus.ACTIVE.value)
        sessions = UserSession.objects.filter(user=user).order_by("created_at")
        self.assertEqual([s.kind for s in sessions], ["enrolment", "full"])
        self.assertIsNotNone(sessions[0].revoked_at, "the enrolment session is replaced")
        self.assertIsNone(sessions[1].revoked_at)
        self.assertEqual(body["sessionKind"], "full")
        self.assertTrue(body["accessToken"])
        self.activate(self.tenant)
        membership = Membership.objects.get(user=user, tenant=self.tenant)
        self.assertEqual(sorted(membership.roles.values_list("key", flat=True)), ["compliance_officer", "reader"])
        me = self.client.get("/api/v1/me", **self._bearer(body["accessToken"]))
        self.assertFalse(me.json()["enrolmentPending"])
        self.assertEqual(me.json()["passkeyCount"], 1, "the screen prompts for a second passkey from this count")
        self.assertTrue(LoginEvent.objects.filter(user=user, event=LoginEventKind.ENROLLED.value, success=True).exists())

    def test_id_s6(self) -> None:
        """ID-S6

        A code request for an enrolled account looks normal and sends nothing (ID-03, AC-ID1).
        """
        user, _, _, _ = self._enrol()
        MockMailer.reset()
        with mock.patch("apps.identity.code_logic.tokens.hash_code", wraps=tokens.hash_code) as hashing:
            enrolled = self._post("/auth/code/request", {"email": ANNA})
            unknown = self._post("/auth/code/request", {"email": "nobody@nowhere.example"})
            self.assertEqual(hashing.call_count, 2, "the same hashing work on both paths")
        self.assertEqual(enrolled.status_code, 202)
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(enrolled.json(), unknown.json())
        self.assertEqual(enrolled.content, unknown.content)
        self.assertEqual(MockMailer.sent, [], "the mailer sent nothing")
        self.assertTrue(
            LoginEvent.objects.filter(user=user, event=LoginEventKind.CODE_REFUSED_ENROLLED.value, success=False).exists()
        )
        # And the code path is closed for good: even a code that exists is refused.
        self.assertEqual(self._verify_code(ANNA, "123456").json()["code"], "invalid_code")

    def test_id_s7(self) -> None:
        """ID-S7

        No password exists anywhere (ID-03).
        """
        from django.apps import apps as django_apps

        for model in django_apps.get_models():
            for field in model._meta.get_fields():
                self.assertNotIn("password", field.name.lower(), f"{model._meta.label}.{field.name}")
        self.assertFalse(hasattr(User, "password"))
        self.assertFalse(hasattr(User, "set_password"))
        schema = api.get_openapi_schema(path_prefix="/api/v1")
        for name, component in schema["components"]["schemas"].items():
            self.assertNotIn("password", " ".join(component.get("properties", {})).lower(), name)
        self.assertEqual(settings.AUTHENTICATION_BACKENDS, [])
        self.assertEqual(settings.AUTH_PASSWORD_VALIDATORS, [])

    def test_id_s8(self) -> None:
        """ID-S8

        Passkey sign-in issues a session (ID-03).
        """
        user, authenticator, _, _ = self._enrol()
        response = self._sign_in(authenticator)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["accessToken"])
        self.assertEqual(body["sessionKind"], "full")
        self.assertEqual(body["expiresIn"], settings.ACCESS_TOKEN_TTL_MINUTES * 60)
        cookie = response.cookies[COOKIE]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], settings.REFRESH_COOKIE_PATH)
        session = UserSession.objects.filter(user=user, kind="full", revoked_at__isnull=True).order_by("-created_at").first()
        assert session is not None
        self.assertEqual(session.refresh_token_hash, tokens.hash_token(cookie.value.split(".", 1)[1]))
        self.assertEqual(session.tenant_id, self.tenant.id)
        self.assertTrue(LoginEvent.objects.filter(user=user, event=LoginEventKind.SIGNIN.value, method=LoginMethod.PASSKEY.value, success=True).exists())
        self.assertEqual(WebAuthnCredential.objects.get(user=user).sign_count, 1)
        # A wrong key is refused and logged.
        options = self._post("/auth/passkeys/authenticate/options")
        failed = self._post("/auth/passkeys/authenticate/verify", {"credential": authenticator.assert_(options.json(), wrong_key=True)})
        self.assertEqual(failed.status_code, 401)
        self.assertEqual(failed.json()["code"], "signin_failed")
        self.assertTrue(LoginEvent.objects.filter(user=user, event=LoginEventKind.SIGNIN_FAILED.value).exists())

    def test_id_s9(self) -> None:
        """ID-S9

        Refresh rotates and a replayed refresh is refused after the grace window (ID-03).
        """
        user, _, _, first = self._enrol()
        refreshed = self._post("/auth/refresh", **self._cookie(first))
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        second = refreshed.cookies[COOKIE].value
        self.assertNotEqual(second, first, "a new refresh token is issued and the old one retired")
        session = UserSession.objects.get(user=user, kind="full")
        self.assertEqual(session.refresh_token_hash, tokens.hash_token(second.split(".", 1)[1]))
        self.assertEqual(session.previous_refresh_hash, tokens.hash_token(first.split(".", 1)[1]))
        # Inside the grace window (a setting): the old token still answers, no third token.
        replay = self._post("/auth/refresh", **self._cookie(first))
        self.assertEqual(replay.status_code, 200)
        self.assertNotIn(COOKIE, replay.cookies)
        self.assertTrue(replay.json()["accessToken"])
        # After the grace window: 401 and the whole session is revoked.
        with self._later(seconds=settings.REFRESH_REPLAY_GRACE_SECONDS + 1):
            late = self._post("/auth/refresh", **self._cookie(first))
        self.assertEqual(late.status_code, 401)
        session.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(session.revoked_reason, "refresh_replay")
        self.assertTrue(LoginEvent.objects.filter(user=user, event=LoginEventKind.REFRESH_REPLAY.value).exists())
        self.assertEqual(self._post("/auth/refresh", **self._cookie(second)).status_code, 401, "the current token died with the session")

    def test_id_s10(self) -> None:
        """ID-S10

        A user adds and renames passkeys and can never remove the last one (ID-04).
        """
        user, _, body, _ = self._enrol()
        headers = self._bearer(body["accessToken"])
        # An enrolment mints no step-up assertion (F9 narrowed, ID-S14), but the new
        # session is younger than the window, so the second-passkey prompt needs none.
        self.assertIsNone(self.client.get("/api/v1/me", **headers).json()["stepUpValidUntil"])
        added = self._register(body["accessToken"], SoftwareAuthenticator())
        self.assertEqual(added.status_code, 201, added.content)
        self.assertIsNone(added.json()["accessToken"], "adding a passkey to a full session issues no new session")
        listed = self.client.get("/api/v1/me/passkeys", **headers).json()
        # Named from the same browser, so the second one carries a counter.
        self.assertEqual([p["nickname"] for p in listed], ["Chrome on Windows", "Chrome on Windows (2)"])
        for passkey in listed:
            self.assertIn("createdAt", passkey)
            self.assertIn("lastUsedAt", passkey)
        laptop, phone = listed
        renamed = self.client.patch(f"/api/v1/me/passkeys/{phone['id']}", data={"nickname": "Work phone"}, content_type="application/json", **headers)
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["nickname"], "Work phone")
        self.assertEqual({k: v for k, v in renamed.json().items() if k != "nickname"}, {k: v for k, v in phone.items() if k != "nickname"})
        removed = self.client.delete(f"/api/v1/me/passkeys/{laptop['id']}", **headers)
        self.assertEqual(removed.status_code, 204)
        self.assertEqual([p["id"] for p in self.client.get("/api/v1/me/passkeys", **headers).json()], [phone["id"]])
        last = self.client.delete(f"/api/v1/me/passkeys/{phone['id']}", **headers)
        self.assertEqual(last.status_code, 409)
        self.assertEqual(last.json()["code"], "last_passkey")
        self.assertEqual(WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).count(), 1)
        # Outside the step-up window, adding or removing a passkey asks for a fresh assertion (F9).
        with self._later(minutes=settings.STEP_UP_FRESHNESS_MINUTES + 1):
            stale_add = self._post("/auth/passkeys/register/options", **headers)
            self.assertEqual(stale_add.status_code, 200)
            stale_verify = self._post(
                "/auth/passkeys/register/verify",
                {"credential": SoftwareAuthenticator().register(stale_add.json()), "nickname": "Late"},
                **headers,
            )
            stale_delete = self.client.delete(f"/api/v1/me/passkeys/{phone['id']}", **headers)
        self.assertEqual((stale_verify.status_code, stale_verify.json()["code"]), (403, "step_up_required"))
        self.assertEqual((stale_delete.status_code, stale_delete.json()["code"]), (403, "step_up_required"))

    def test_id_s11(self) -> None:
        """ID-S11

        A user sees and revokes their sessions (ID-04).
        """
        user, authenticator, body, _ = self._enrol()
        other = self._sign_in(authenticator)
        self.assertEqual(other.status_code, 200)
        other_cookie = other.cookies[COOKIE].value
        headers = self._bearer(body["accessToken"])
        listed = self.client.get("/api/v1/me/sessions", **headers).json()
        self.assertEqual(len(listed), 2)
        self.assertEqual(sum(1 for s in listed if s["current"]), 1)
        for session in listed:
            self.assertIn("createdAt", session)
            self.assertIn("lastSeenAt", session)
            self.assertIn("userAgent", session)
        other_id = next(s["id"] for s in listed if not s["current"])
        revoked = self.client.delete(f"/api/v1/me/sessions/{other_id}", **headers)
        self.assertEqual(revoked.status_code, 204)
        self.assertEqual(self._post("/auth/refresh", **self._cookie(other_cookie)).status_code, 401)
        self.assertEqual(len(self.client.get("/api/v1/me/sessions", **headers).json()), 1)

    def test_id_s12(self) -> None:
        """ID-S12

        A tenant admin re-issues enrolment behind step-up (ID-05).
        """
        user, authenticator, body, _ = self._enrol()
        self._sign_in(authenticator)
        MockMailer.reset()
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        response = self._post(f"/tenant/members/{user.id}/reissue-enrolment", **headers)
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json(), {})
        self.assertFalse(UserSession.objects.filter(user=user, revoked_at__isnull=True).exists(), "every session revoked")
        self.assertFalse(WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).exists(), "every passkey retired")
        user.refresh_from_db()
        self.assertEqual(user.status, UserStatus.INVITED.value, "she is awaiting enrolment again")
        self.activate(self.tenant)
        invitation = Invitation.objects.get(email=ANNA, accepted_at__isnull=True, revoked_at__isnull=True)
        self.assertEqual(invitation.kind, InvitationKind.REENROLMENT.value)
        recipients = sorted(m.to for m in MockMailer.sent)
        self.assertEqual(recipients, [ANNA, "maria@bank.example"], "the user and the other admin are notified")
        event = AuditEvent.objects.get(action="member.enrolment_reissued", subject_id=user.id)
        self.assertEqual(event.actor_id, self.admin.id)
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertTrue(LoginEvent.objects.filter(user=user, event=LoginEventKind.REENROLMENT_ISSUED.value).exists())
        # The code path is open again for the address, and the old passkey no longer signs in.
        self.assertEqual(self._post("/auth/code/request", {"email": ANNA}).status_code, 202)
        self.assertEqual(MockMailer.sent[-1].to, ANNA)
        self.assertIn("Your code is", MockMailer.sent[-1].body)
        self.assertEqual(self._sign_in(authenticator).status_code, 401)

    def test_id_s13(self) -> None:
        """ID-S13

        The last admin recovers through platform support (ID-05).
        """
        from apps.tenants.models import SupportAccess

        lonely = factories.tenant(slug="lonely")
        only_admin = factories.member(lonely, roles=("admin",), user_row=factories.user(email="sole@lonely.example")).user
        factories.passkey(only_admin)
        support = factories.platform_user(roles=("platform_admin",), email="support@bleqq.test")
        headers = sign_in(support, tenant=None, step_up=True)
        body = {"reason": "Lost every passkey", "ticketRef": "SUP-42", "outOfBandCheck": "Called back on the registered number"}
        response = self._post(f"/console/tenants/{lonely.id}/members/{only_admin.id}/reissue-enrolment", body, **headers)
        self.assertEqual(response.status_code, 202, response.content)
        self.activate(lonely)
        access = SupportAccess.objects.get(tenant=lonely)
        self.assertEqual(access.platform_user_id, support.id)
        self.assertEqual((access.reason, access.ticket_ref, access.access_level), ("Lost every passkey", "SUP-42", "write"))
        self.assertIsNotNone(access.ended_at, "one-shot: the grant closes with the action")
        recorded = AuditEvent.objects.get(action="support_access.recorded", subject_id=access.id)
        self.assertEqual(recorded.after["outOfBandCheck"], "Called back on the registered number")
        self.assertIsNotNone(recorded.step_up_assertion_id)
        reissued = AuditEvent.objects.get(action="member.enrolment_reissued", subject_id=only_admin.id)
        self.assertEqual(reissued.after["supportAccessId"], str(access.id))
        invitation = Invitation.objects.get(email="sole@lonely.example", accepted_at__isnull=True, revoked_at__isnull=True)
        self.assertEqual(invitation.kind, InvitationKind.REENROLMENT.value)
        self.assertFalse(WebAuthnCredential.objects.filter(user=only_admin, retired_at__isnull=True).exists())
        # The re-issued enrolment runs the same ceremony (which prompts for a second passkey).
        token = _find(LINK, next(m.body for m in MockMailer.sent if m.to == "sole@lonely.example"))
        code = self._open_and_get_code(token)
        self.assertEqual(self._verify_code("sole@lonely.example", code).json()["sessionKind"], "enrolment")
        # Another tenant's id, or one that does not exist, is a 404.
        missing = self._post(f"/console/tenants/00000000-0000-4000-8000-0000000000ff/members/{only_admin.id}/reissue-enrolment", body, **headers)
        self.assertEqual(missing.status_code, 404)

    def test_id_s14(self) -> None:
        """ID-S14

        A sensitive action without a fresh assertion answers step_up_required (ID-06, AC-ID3).
        """
        user, _, _, _ = self._enrol()
        no_step_up = sign_in(self.admin, tenant=self.tenant)
        response = self._post(f"/tenant/members/{user.id}/reissue-enrolment", **no_step_up)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")
        self.assertIn("detail", response.json())
        # An assertion older than the window (a setting) is stale too.
        stale = sign_in(self.admin, tenant=self.tenant, step_up=True)
        with self._later(minutes=settings.STEP_UP_FRESHNESS_MINUTES + 1):
            late = self._post(f"/tenant/members/{user.id}/reissue-enrolment", **stale)
        self.assertEqual(late.status_code, 403)
        self.assertEqual(late.json()["code"], "step_up_required")
        self.assertTrue(WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).exists(), "nothing happened")

    def test_id_s15(self) -> None:
        """ID-S15

        A completed sensitive action references its assertion on the audit event (ID-06, AC-ID3).
        """
        user, _, _, _ = self._enrol()
        authenticator = self._admin_with_passkey(self.admin)
        headers = sign_in(self.admin, tenant=self.tenant)
        stepped = self._step_up(headers["HTTP_AUTHORIZATION"].split(" ", 1)[1], authenticator)
        self.assertEqual(stepped.status_code, 200, stepped.content)
        assertion_id = stepped.json()["assertionId"]
        self.assertIn("expiresAt", stepped.json())
        me = self.client.get("/api/v1/me", **headers).json()
        self.assertIsNotNone(me["stepUpValidUntil"])
        response = self._post(f"/tenant/members/{user.id}/reissue-enrolment", **headers)
        self.assertEqual(response.status_code, 202, response.content)
        self.activate(self.tenant)
        event = AuditEvent.objects.get(action="member.enrolment_reissued", subject_id=user.id)
        self.assertEqual(str(event.step_up_assertion_id), assertion_id)
        self.assertTrue(LoginEvent.objects.filter(user=self.admin, event=LoginEventKind.STEP_UP.value, success=True).exists())
        # A wrong key fails the step-up and is logged.
        options = self._post("/auth/step-up/options", **headers)
        failed = self._post("/auth/step-up/verify", {"credential": authenticator.assert_(options.json(), wrong_key=True)}, **headers)
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(failed.json()["code"], "step_up_failed")

    @skip("pending: ID-S16 (ID-07, R2)")
    def test_id_s16(self) -> None:
        """ID-S16

        A tenant can require attested device-bound authenticators (ID-07).
        """

    @skip("pending: ID-S17 (ID-08, R2)")
    def test_id_s17(self) -> None:
        """ID-S17

        Session limits are tenant policy within platform maximums (ID-08).
        """

    def test_id_s18(self) -> None:
        """ID-S18

        Permissions are code and roles are rows (ID-09).
        """
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        seeded = self.client.get("/api/v1/tenant/roles", **headers).json()
        self.assertEqual([r["key"] for r in seeded], list(k for k in perms.SYSTEM_ROLES if k not in ("library_editor", "platform_admin")))
        self.assertTrue(all(r["isSystem"] for r in seeded))
        body = {
            "key": "legal_reviewer",
            "labels": {"en": "Legal reviewer", "sv": "Juridisk granskare"},
            "usageNote": "Reads cases and adds input; never triages.",
            "permissions": [perms.CASES_READ, perms.CASES_CONTRIBUTE],
        }
        created = self._post("/tenant/roles", body, **headers)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["label"], "Legal reviewer")
        self.activate(self.tenant)
        row = TenantRole.objects.get(tenant=self.tenant, key="legal_reviewer")
        self.assertEqual(sorted(row.permissions), sorted([perms.CASES_CONTRIBUTE, perms.CASES_READ]))
        self.assertFalse(row.is_system)
        reviewer = factories.member(self.tenant, roles=("legal_reviewer",)).user
        me = self.client.get("/api/v1/me", **sign_in(reviewer, tenant=self.tenant)).json()
        self.assertIn(perms.CASES_CONTRIBUTE, me["permissions"])
        self.assertNotIn(perms.CASES_TRIAGE, me["permissions"])
        self.assertEqual([r["label"] for r in me["roles"]], ["Legal reviewer"])
        denied = self.client.get("/api/v1/tenant/members", **sign_in(reviewer, tenant=self.tenant))
        self.assertEqual(denied.status_code, 403)
        # A permission change on a role needs step-up; a relabel does not.
        plain = sign_in(self.admin, tenant=self.tenant)
        relabel = self.client.patch("/api/v1/tenant/roles/legal_reviewer", data={"labels": {"en": "Legal review"}}, content_type="application/json", **plain)
        self.assertEqual(relabel.status_code, 200, relabel.content)
        self.assertEqual(relabel.json()["label"], "Legal review")
        widen = self.client.patch("/api/v1/tenant/roles/legal_reviewer", data={"permissions": [perms.CASES_TRIAGE]}, content_type="application/json", **plain)
        self.assertEqual(widen.status_code, 403)
        self.assertEqual(widen.json()["code"], "step_up_required")
        unknown = self._post("/tenant/roles", {**body, "key": "x", "permissions": ["not.a.permission"]}, **headers)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(unknown.json()["code"], "unknown_key")
        system = self.client.patch("/api/v1/tenant/roles/reader", data={"permissions": [perms.CASES_TRIAGE]}, content_type="application/json", **headers)
        self.assertEqual(system.json()["code"], "system_role")
        in_use = self._post("/tenant/roles/legal_reviewer/retire", **headers)
        self.assertEqual(in_use.status_code, 409)
        self.assertEqual(in_use.json()["code"], "role_in_use")
        # No endpoint or logic compares a role name: the system keys appear as string
        # constants in no api.py or logic module.
        apps_dir = Path(__file__).resolve().parent.parent
        role_keys = {k for k in perms.SYSTEM_ROLES}
        offenders: list[str] = []
        for path in sorted(apps_dir.rglob("*.py")):
            rel = path.relative_to(apps_dir).as_posix()
            if not (rel.endswith("/api.py") or rel.endswith("logic.py")) or rel.endswith("roles_logic.py"):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in role_keys:
                    offenders.append(f"apps/{rel}:{node.lineno} {node.value!r}")
        self.assertEqual(offenders, [], "an endpoint or logic module compares a role name")

    def test_id_s19(self) -> None:
        """ID-S19

        A tenant always keeps one admin (ID-09).
        """
        lonely = factories.tenant(slug="one-admin")
        only_admin = factories.member(lonely, roles=("admin",)).user
        factories.member(lonely, roles=("reader",))
        headers = sign_in(only_admin, tenant=lonely, step_up=True)
        demoted = self.client.patch(f"/api/v1/tenant/members/{only_admin.id}", data={"roleKeys": ["reader"]}, content_type="application/json", **headers)
        self.assertEqual(demoted.status_code, 409)
        self.assertEqual(demoted.json()["code"], "last_admin")
        removed = self.client.delete(f"/api/v1/tenant/members/{only_admin.id}", **headers)
        self.assertEqual(removed.status_code, 409)
        self.assertEqual(removed.json()["code"], "last_admin")
        self.activate(lonely)
        self.assertEqual(sorted(Membership.objects.get(user=only_admin, tenant=lonely).roles.values_list("key", flat=True)), ["admin"])
        # With a second admin the same changes go through, and a title change needs no step-up.
        factories.member(lonely, roles=("admin",))
        plain = sign_in(only_admin, tenant=lonely)
        retitled = self.client.patch(f"/api/v1/tenant/members/{only_admin.id}", data={"title": "Head of compliance"}, content_type="application/json", **plain)
        self.assertEqual(retitled.status_code, 200, retitled.content)
        self.assertEqual(retitled.json()["title"], "Head of compliance")
        demoted = self.client.patch(f"/api/v1/tenant/members/{only_admin.id}", data={"roleKeys": ["reader"]}, content_type="application/json", **headers)
        self.assertEqual(demoted.status_code, 200, demoted.content)
        self.assertEqual([r["key"] for r in demoted.json()["roles"]], ["reader"])

    def test_id_s20(self) -> None:
        """ID-S20

        An API key is shown once, stored hashed and revocable (ID-10).
        Operations: `createApiKey`, `revokeApiKey`, `createAgentKey`, `revokeAgentKey`.
        """
        headers = sign_in(self.admin, tenant=self.tenant, step_up=True)
        created = self._post("/tenant/api-keys", {"name": "Research agent", "scopes": [perms.SCOPE_CHANGES_WRITE, perms.SCOPE_PROPOSALS_WRITE]}, **headers)
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        plain = body["plainKey"]
        self.assertTrue(plain.startswith(f"cw_{body['keyPrefix']}_"))
        self.activate(self.tenant)
        row = ApiKey.objects.get(pk=body["id"])
        self.assertEqual(row.key_hash, tokens.hash_token(plain.split("_", 2)[2]))
        self.assertNotIn(plain, str(ApiKey.objects.filter(pk=row.pk).values()))
        self.assertEqual(sorted(row.scopes), sorted([perms.SCOPE_CHANGES_WRITE, perms.SCOPE_PROPOSALS_WRITE]))
        self.assertIsNotNone(row.created_at)
        self.assertIsNone(row.last_used_at)
        listed = self.client.get("/api/v1/tenant/api-keys", **headers).json()
        self.assertEqual(listed["total"], 1)
        self.assertNotIn("plainKey", listed["items"][0])
        self.assertNotIn(plain, created.content.decode().replace(plain, "", 1), "the plain key appears once")
        # Used: the principal carries the scopes, last used updates, the log records it.
        self.assertIsNone(ApiKeyAuth()(RequestFactory().get("/")), "no header, no principal")
        principal = api_keys_logic.resolve_api_key(plain)
        assert principal is not None
        self.assertEqual(principal.tenant_id, self.tenant.id)
        self.assertEqual(principal.scopes, frozenset({perms.SCOPE_CHANGES_WRITE, perms.SCOPE_PROPOSALS_WRITE}))
        row.refresh_from_db()
        self.assertIsNotNone(row.last_used_at)
        self.assertTrue(LoginEvent.objects.filter(api_key=row, event=LoginEventKind.KEY_USED.value).exists())
        self.assertIsNone(api_keys_logic.resolve_api_key(plain[:-1] + ("a" if plain[-1] != "a" else "b")), "a wrong secret")
        # Revoked: the next call answers nothing (401 at the route).
        revoked = self.client.delete(f"/api/v1/tenant/api-keys/{row.id}", **headers)
        self.assertEqual(revoked.status_code, 204)
        self.assertIsNone(api_keys_logic.resolve_api_key(plain))
        self.assertTrue(LoginEvent.objects.filter(api_key=row, event=LoginEventKind.KEY_REVOKED.value).exists())
        # Creating a key without step-up is refused; an unknown scope is a 422.
        self.assertEqual(self._post("/tenant/api-keys", {"name": "x", "scopes": [perms.SCOPE_CHANGES_WRITE]}, **sign_in(self.admin, tenant=self.tenant)).json()["code"], "step_up_required")
        self.assertEqual(self._post("/tenant/api-keys", {"name": "x", "scopes": ["library:write"]}, **headers).json()["code"], "unknown_key")

    def test_id_s21(self) -> None:
        """ID-S21

        No API key scope allows a library edit (ID-10, AC-PRO1).
        """
        key = factories.api_key(self.tenant, scopes=tuple(sorted(perms.ALL_SCOPES)))
        self.assertFalse(any("write" in scope and scope.startswith("library") for scope in perms.ALL_SCOPES))
        self.assertFalse(any(scope.split(":")[0] in {"instruments", "provisions", "obligations"} for scope in perms.ALL_SCOPES))
        library_paths = ("/instruments", "/provisions", "/obligations")
        session_bound = {perms.UngatedReason.SELF, perms.UngatedReason.CAPABILITY}
        scope_gated: set[tuple[str, str, str]] = set()
        probed = 0
        for operation in iter_operations(api):
            if operation.method == "GET":
                continue
            self.assertFalse(operation.path.startswith(library_paths), f"a library write route exists: {operation.path}")
            gate = perms.gate_of(operation.view_func)
            ungated = perms.UNGATED_BY_DESIGN.get((operation.method, operation.path))
            if gate is not None and gate.kind == "scope":
                # An agent-writable route: AGENT_WRITABLE_ROUTES above is the review hook.
                scope_gated.add((operation.method, operation.path, gate.value))
                continue
            if gate is None and (ungated is None or ungated.reason not in session_bound):
                continue  # a public bootstrap step (code request, sign-in) is no grant to anything
            with self.subTest(route=f"{operation.method} {operation.path}"):
                url = "/api/v1" + re.sub(r"\{[^}]+\}", "00000000-0000-4000-8000-000000000001", operation.path)
                for headers in ({"HTTP_AUTHORIZATION": f"Bearer {key.plain_key}"}, {"HTTP_X_API_KEY": key.plain_key}):
                    response = self.client.generic(operation.method, url, data="{}", content_type="application/json", **headers)
                    self.assertIn(response.status_code, (401, 403), "a key reached a route it must not")
                probed += 1
        self.assertGreater(probed, 10)
        # The routes a key may write are named one by one, never waved through by their
        # decorator: a new one fails here until it is listed and reviewed.
        self.assertEqual(
            scope_gated,
            AGENT_WRITABLE_ROUTES,
            "a route an API key's scope may write was added, removed or regated; list it in "
            "AGENT_WRITABLE_ROUTES with the reason that scope may make that call (ID-10, AC-PRO1)",
        )

    def test_id_s22(self) -> None:
        """ID-S22

        The security log records sign-ins, failures, enrolments, recoveries and key use (ID-11).
        """
        user, authenticator, _, _ = self._enrol()  # enrolled
        _, token = self._invite("nils@bank.example")
        self._open_and_get_code(token)
        self._verify_code("nils@bank.example", "000000")  # code_failed
        self._sign_in(authenticator)  # signin
        key = factories.api_key(self.tenant)
        api_keys_logic.resolve_api_key(key.plain_key)  # key_used
        self._post(f"/tenant/members/{user.id}/reissue-enrolment", **sign_in(self.admin, tenant=self.tenant, step_up=True))  # reenrolment_issued
        listed = self.client.get("/api/v1/tenant/security-log?limit=100", **sign_in(self.admin, tenant=self.tenant))
        self.assertEqual(listed.status_code, 200, listed.content)
        items = listed.json()["items"]
        events = {item["event"] for item in items}
        for expected in ("code_sent", "code_failed", "enrolled", "signin", "key_used", "reenrolment_issued", "session_revoked"):
            self.assertIn(expected, events)
        for item in items:
            for field in ("occurredAt", "method", "success", "ip", "userAgent"):
                self.assertIn(field, item)
        signin = next(item for item in items if item["event"] == "signin")
        self.assertEqual((signin["method"], signin["userId"], signin["success"]), ("passkey", str(user.id), True))
        # Only security.manage reads it; and the table refuses update and delete.
        self.assertEqual(self.client.get("/api/v1/tenant/security-log", **sign_in(user, tenant=self.tenant)).status_code, 403)
        row = LoginEvent.objects.filter(tenant=self.tenant).order_by("id").first()
        assert row is not None
        with connection.cursor() as cursor:
            with self.assertRaises(DatabaseError) as caught:
                with transaction.atomic():
                    cursor.execute("UPDATE login_event SET success = NOT success WHERE id = %s", [row.id])
            self.assertIn("append-only", str(caught.exception))
            with self.assertRaises(DatabaseError):
                with transaction.atomic():
                    cursor.execute("DELETE FROM login_event WHERE id = %s", [row.id])

    @skip("pending: ID-S23 (ID-12, R3)")
    def test_id_s23(self) -> None:
        """ID-S23

        SSO and SCIM never introduce a password (ID-12).
        """

    @skip("pending: ID-S24 (ID-13, R3)")
    def test_id_s24(self) -> None:
        """ID-S24

        A tenant IP allow-list blocks other addresses (ID-13).
        """

    def test_id_s26(self) -> None:
        """ID-S26

        A denied request answers a structured 403 the UI renders as is (ID-09).
        """
        reader = factories.member(self.tenant, roles=("reader",)).user
        # The triage endpoint lands in chunk 9; the members list is the gated route that
        # exists, and the shape is what the Restricted screen renders.
        response = self.client.get("/api/v1/tenant/members", **sign_in(reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        body = response.json()
        self.assertEqual(body["status"], 403)
        self.assertEqual(body["code"], "permission_denied")
        self.assertEqual(body["requiredPermission"], perms.MEMBERS_MANAGE)
        self.assertTrue(body["detail"])
        self.assertTrue(body["title"])

    @skip("pending: ID-S27 (ID-12, R3)")
    def test_id_s27(self) -> None:
        """ID-S27

        SSO proves who a person is and never opens a session on its own (ID-12).
        """

    @skip("pending: ID-S28 (ID-12, R3)")
    def test_id_s28(self) -> None:
        """ID-S28

        A SCIM key carries one scope and its default role holds no admin permission (ID-12).
        """

    @skip("pending: ID-S29 (ID-07, R2)")
    def test_id_s29(self) -> None:
        """ID-S29

        A stricter passkey policy binds new passkeys now and old ones from its notice date (ID-07).
        """

    def test_id_s30(self) -> None:
        """ID-S30

        A bank invitation never reaches platform staff (ID-01, ID-02, ID-03).
        """
        # At invitation: an address that already holds a platform role is turned away and
        # no invitation row is written.
        staff = factories.platform_user(roles=("library_editor",), email="editor@platform.example")
        refused = self.client.post(
            "/api/v1/tenant/members",
            data={"email": staff.email, "roleKeys": ["reader"]},
            content_type="application/json",
            **sign_in(self.admin, tenant=self.tenant),
        )
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "platform_account")
        self.activate(self.tenant)
        self.assertFalse(Invitation.objects.filter(tenant=self.tenant, email=staff.email).exists())

        # At enrolment: the platform role arrived after the invitation went out. The
        # ceremony has to refuse before the credential is stored, because a 422 is built
        # inside the view and the request's transaction still commits: a credential
        # written first would stay behind with no audit row, and the account would hold a
        # live passkey it cannot sign in with and an emailed code that no longer works.
        _, token = self._invite("late@bank.example")
        code = self._open_and_get_code(token)
        late = User.objects.get(email="late@bank.example")
        roles_logic.ensure_platform_roles()
        PlatformRoleAssignment.objects.create(user=late, role=PlatformRole.objects.get(key="library_editor"))
        verified = self._verify_code("late@bank.example", code)
        self.assertEqual(verified.status_code, 200, verified.content)
        registered = self._register(verified.json()["accessToken"], SoftwareAuthenticator())
        self.assertEqual(registered.status_code, 422, registered.content)
        self.assertEqual(registered.json()["code"], "platform_account")
        self.assertEqual(WebAuthnCredential.objects.filter(user=late).count(), 0)
        late.refresh_from_db()
        self.assertNotEqual(late.status, UserStatus.ACTIVE.value)
        self.activate(self.tenant)
        self.assertFalse(Membership.objects.filter(tenant=self.tenant, user=late).exists())

    def test_id_s31(self) -> None:
        """ID-S31

        A member marks the library as seen and only their own bookmark moves (ID-04, AUD-01, AC-AUD1).
        """
        self.activate(self.tenant)
        mine = Membership.objects.get(tenant=self.tenant, user=self.admin)
        mine.last_visit_at = SEEN_BEFORE
        mine.save(update_fields=["last_visit_at"])
        editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")

        seen = self._post("/me/visit", **sign_in(self.admin, tenant=self.tenant))

        self.assertEqual(seen.status_code, 204, seen.content)
        self.activate(self.tenant)
        mine.refresh_from_db()
        assert mine.last_visit_at is not None
        self.assertGreater(mine.last_visit_at, SEEN_BEFORE)
        self.assertIsNone(Membership.objects.get(tenant=self.tenant, user=self.second_admin).last_visit_at)
        visits = list(AuditEvent.objects.filter(action="member.visited"))
        self.assertEqual([(row.tenant_id, row.actor_id) for row in visits], [(self.tenant.id, self.admin.id)])
        self.assertEqual(visits[0].before["lastVisitAt"], SEEN_BEFORE.isoformat())
        self.assertEqual(visits[0].after["lastVisitAt"], mine.last_visit_at.isoformat())

        # Platform staff hold no membership, so there is no bookmark of theirs to move.
        refused = self._post("/me/visit", **sign_in(editor))

        self.assertEqual(refused.status_code, 404, refused.content)
        self.assertEqual(refused.json()["code"], "not_found")
        self.activate(self.tenant)
        self.assertEqual(AuditEvent.objects.filter(action="member.visited").count(), 1)
