"""Unit tests for the policy branches of the identity app (playbook 3 step 5): token
hashing, constant-time comparison, the refresh replay grace, idle and absolute limits,
the last admin, the last passkey, the step-up window, rate limiting, the E2E code leg,
the API key auth class, the E2E outbox and the bootstrap command."""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from datetime import timedelta
from io import StringIO
from typing import Any
from unittest import mock
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import CommandError, call_command
from django.db import DataError, transaction
from django.db.models import F
from django.http import HttpRequest
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.identity import (
    api_keys_logic,
    code_logic,
    invitation_logic,
    mail,
    members_logic,
    passkey_logic,
    rate_limit,
    security_log,
    session_logic,
    tokens,
)
from apps.identity.models import (
    AuthChallenge,
    ChallengeKind,
    Invitation,
    InvitationKind,
    LoginEvent,
    LoginEventKind,
    LoginMethod,
    Membership,
    OtpCode,
    PlatformRoleAssignment,
    SessionKind,
    User,
    UserSession,
    UserStatus,
    WebAuthnCredential,
)
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.adapters.mailer import MockMailer, OutgoingMail
from apps.shared.authentication import ApiKeyAuth, Principal, PrincipalKind
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent, Tenant
from config.api import api
from apps.shared.permissions import enforce_step_up
from apps.shared.testing import sign_in, user_principal


class TokenHashing(TestCase):
    def test_random_tokens_are_stored_as_sha256(self) -> None:
        token = tokens.new_token()
        self.assertEqual(len(tokens.hash_token(token)), 64)
        self.assertNotEqual(tokens.hash_token(token), token)
        self.assertNotEqual(tokens.new_token(), token)

    def test_codes_are_salted_and_compared_in_constant_time(self) -> None:
        code = tokens.new_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        one, two = tokens.new_salt(), tokens.new_salt()
        self.assertNotEqual(tokens.hash_code(code, one), tokens.hash_code(code, two))
        with mock.patch.object(tokens.secrets, "compare_digest", wraps=secrets.compare_digest) as compare:
            self.assertTrue(tokens.constant_equal("a" * 64, "a" * 64))
            self.assertFalse(tokens.constant_equal("a" * 64, "b" * 64))
        self.assertEqual(compare.call_count, 2)

    def test_the_code_hash_cannot_be_reproduced_without_the_key(self) -> None:
        """F30: a salted SHA-256 over six digits falls to a million guesses offline, so a
        reader of `otp_code` alone could recover a live code. The hash is keyed by a key
        derived from SECRET_KEY, so the table and its salt are not enough."""
        code, salt = "042917", tokens.new_salt()
        stored = tokens.hash_code(code, salt)
        self.assertEqual(len(stored), 64)
        self.assertEqual(tokens.hash_code(code, salt), stored, "deterministic under one key")
        self.assertNotEqual(stored, hashlib.sha256(f"{salt}:{code}".encode()).hexdigest(), "not the unkeyed hash")
        with override_settings(SECRET_KEY="a-different-secret-key-for-this-test-only"):
            self.assertNotEqual(tokens.hash_code(code, salt), stored, "another key gives another hash")

    @override_settings(E2E_MODE=True)
    def test_the_e2e_code_is_fixed_locally_and_refused_when_deployed(self) -> None:
        self.assertEqual(tokens.new_code(), "123456")
        with override_settings(IS_DEPLOYED_ENVIRONMENT=True):
            with self.assertRaises(ImproperlyConfigured):
                tokens.new_code()

    def test_access_tokens_round_trip_and_reject_tampering_and_expiry(self) -> None:
        now = timezone.now()
        session_id = uuid.uuid4()
        token, expires_in = tokens.issue_access_token(session_id, "full", now)
        self.assertEqual(expires_in, 600)
        claims = tokens.parse_access_token(token, now)
        assert claims is not None
        self.assertEqual((claims.session_id, claims.kind), (session_id, "full"))
        head, _, signature = token.rpartition(".")
        self.assertIsNone(tokens.parse_access_token(f"{head}.{signature[:-2]}xx", now), "tampered signature")
        self.assertIsNone(tokens.parse_access_token(token.replace(".full.", ".enrolment."), now), "tampered claims")
        self.assertIsNone(tokens.parse_access_token(token, now + timedelta(seconds=601)), "expired")
        self.assertIsNone(tokens.parse_access_token("v0.x.y.z.w", now))
        self.assertIsNone(tokens.parse_access_token("nonsense", now))

    def test_refresh_and_api_key_formats(self) -> None:
        session_id = uuid.uuid4()
        value, digest = tokens.new_refresh_token(session_id)
        parsed = tokens.parse_refresh_token(value)
        self.assertEqual(parsed, (session_id, digest))
        self.assertIsNone(tokens.parse_refresh_token("no-dot"))
        self.assertIsNone(tokens.parse_refresh_token("nothex.secret"))
        plain, prefix, key_hash = tokens.new_api_key()
        self.assertEqual(tokens.parse_api_key(plain), (prefix, key_hash))
        self.assertIsNone(tokens.parse_api_key("cw_short_x"))
        self.assertIsNone(tokens.parse_api_key("xx_deadbeef_secret"))


class RateLimiting(TestCase):
    def setUp(self) -> None:
        cache.clear()

    @override_settings(RATE_LIMITING_ENABLED=True, E2E_MODE=False)
    def test_the_limit_fires_after_the_allowed_count(self) -> None:
        """The one test that proves a limit fires sets E2E_MODE off explicitly, so it
        stands on its own settings and not on the suite's default (playbook 11.2)."""
        for _ in range(3):
            rate_limit.enforce("probe", "someone", 3, 60)
        with self.assertRaises(ProblemError) as caught:
            rate_limit.enforce("probe", "someone", 3, 60)
        self.assertEqual((caught.exception.status, caught.exception.code), (429, "rate_limited"))
        rate_limit.enforce("probe", "someone-else", 3, 60)

    @override_settings(RATE_LIMITING_ENABLED=True)
    def test_a_window_that_vanished_restarts(self) -> None:
        with mock.patch.object(rate_limit.cache, "incr", side_effect=ValueError):
            rate_limit.enforce("probe", "someone", 1, 60)

    def test_off_in_tests_by_default(self) -> None:
        for _ in range(50):
            rate_limit.enforce("probe", "someone", 1, 60)


class SessionLimits(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.user = factories.member(self.tenant).user

    def _session(self) -> session_logic.SessionBundle:
        return session_logic.create_session(user=self.user, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None)

    def test_idle_limit_is_enforced_on_refresh(self) -> None:
        bundle = self._session()
        later = timezone.now() + timedelta(minutes=31)
        with mock.patch.object(timezone, "now", return_value=later):
            with self.assertRaises(ValidationError):
                session_logic.refresh(bundle.refresh_value, None)
        bundle.session.refresh_from_db()
        self.assertEqual(bundle.session.revoked_reason, "idle")

    def test_absolute_limit_ends_the_session_and_the_access_token(self) -> None:
        bundle = self._session()
        later = timezone.now() + timedelta(hours=12, minutes=1)
        with mock.patch.object(timezone, "now", return_value=later):
            with self.assertRaises(ValidationError):
                session_logic.refresh(bundle.refresh_value, None)
            self.assertIsNone(session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.USER))

    def test_replay_grace_and_revocation(self) -> None:
        bundle = self._session()
        _, _, second = session_logic.refresh(bundle.refresh_value, None)
        self.assertIsNotNone(second)
        access, _, third = session_logic.refresh(bundle.refresh_value, None)
        self.assertIsNone(third, "inside the grace window: no third token")
        self.assertTrue(access)
        later = timezone.now() + timedelta(seconds=31)
        with mock.patch.object(timezone, "now", return_value=later):
            with self.assertRaises(ValidationError):
                session_logic.refresh(bundle.refresh_value, None)
        bundle.session.refresh_from_db()
        self.assertEqual(bundle.session.revoked_reason, "refresh_replay")
        with self.assertRaises(ValidationError):
            session_logic.refresh(second, None)

    def test_unknown_and_malformed_refresh_values(self) -> None:
        with self.assertRaises(ValidationError):
            session_logic.refresh(None, None)
        with self.assertRaises(ValidationError):
            session_logic.refresh(f"{uuid.uuid4().hex}.nope", None)
        session_logic.sign_out(None, None)
        session_logic.sign_out(f"{uuid.uuid4().hex}.nope", None)

    def test_a_deactivated_user_and_a_wrong_kind_resolve_to_nothing(self) -> None:
        bundle = self._session()
        self.assertIsNone(session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.ENROLMENT))
        self.user.status = "deactivated"
        self.user.save(update_fields=["status"])
        self.assertIsNone(session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.USER))

    def test_sign_out_revokes_once(self) -> None:
        bundle = self._session()
        session_logic.sign_out(bundle.refresh_value, None)
        session_logic.sign_out(bundle.refresh_value, None)
        self.assertEqual(UserSession.objects.get(pk=bundle.session.pk).revoked_reason, "sign_out")
        with self.assertRaises(ValidationError):
            session_logic.revoke_own_session(user_principal(subject_id=uuid.uuid4()), bundle.session.id, None)

    def test_a_cookie_naming_a_session_without_its_secret_signs_nobody_out(self) -> None:
        """Sign-out takes no bearer token, so the cookie is the only proof. Session ids are
        not secret (every `session.created` audit row names one), so a cookie of
        `<someone's session id>.<anything>` must not end their session or write
        `session.revoked` in their name."""
        bundle = self._session()
        session_logic.sign_out(f"{bundle.session.id.hex}.forged", None)
        self.assertIsNone(UserSession.objects.get(pk=bundle.session.pk).revoked_at)
        self.assertFalse(AuditEvent.objects.filter(action="session.revoked", subject_id=bundle.session.id).exists())
        self.assertTrue(AuditEvent.objects.filter(action="session.sign_out_without_session").exists())
        session_logic.refresh(bundle.refresh_value, None)  # the owner's cookie still works

    def test_the_cookie_just_rotated_away_still_signs_out_inside_the_grace_window(self) -> None:
        """A tab signing out while another tab refreshes presents the previous secret; inside
        the replay grace window that is still the owner's cookie."""
        bundle = self._session()
        session_logic.refresh(bundle.refresh_value, None)
        session_logic.sign_out(bundle.refresh_value, None)
        self.assertEqual(UserSession.objects.get(pk=bundle.session.pk).revoked_reason, "sign_out")

    def test_a_platform_user_gets_a_platform_session(self) -> None:
        staff = factories.platform_user()
        self.assertIsNone(session_logic.choose_tenant(staff))
        # With no tenant activated, as the sign-in has it when choose_tenant finds none:
        # user_session accepts a row of the session's own zone only (H15).
        with tenancy.platform_zone():
            bundle = session_logic.create_session(user=staff, kind=SessionKind.FULL, tenant_id=None, request=None)
        principal = session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.USER)
        assert principal is not None
        self.assertTrue(principal.is_platform_staff)
        self.assertIn(perms.SUPPORT_ACCESS_GRANT, principal.permissions)
        self.assertIsNone(principal.tenant_id)
        self.assertEqual(session_logic.choose_tenant(self.user), self.tenant.id)


class StepUpWindow(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _request(self, principal: Principal) -> HttpRequest:
        request = self.factory.post("/")
        request.auth = principal  # type: ignore[attr-defined]
        return request

    def test_fresh_assertion_passes_and_is_put_on_the_request(self) -> None:
        assertion = uuid.uuid4()
        principal = Principal(kind=PrincipalKind.USER, subject_id=uuid.uuid4(), step_up_at=timezone.now(), step_up_assertion_id=assertion)
        request = self._request(principal)
        self.assertEqual(enforce_step_up(request), assertion)
        self.assertEqual(request.step_up_assertion_id, assertion)  # type: ignore[attr-defined]

    def test_stale_missing_or_non_person_is_refused(self) -> None:
        stale = Principal(kind=PrincipalKind.USER, subject_id=uuid.uuid4(), step_up_at=timezone.now() - timedelta(minutes=6), step_up_assertion_id=uuid.uuid4())
        missing = Principal(kind=PrincipalKind.USER, subject_id=uuid.uuid4())
        agent = Principal(kind=PrincipalKind.AGENT, subject_id=uuid.uuid4())
        for principal in (stale, missing, agent):
            with self.assertRaises(ProblemError) as caught:
                enforce_step_up(self._request(principal))
            self.assertEqual((caught.exception.status, caught.exception.code), (403, "step_up_required"))
        with self.assertRaises(ProblemError) as caught:
            enforce_step_up(self.factory.post("/"))
        self.assertEqual(caught.exception.status, 401)


class LastAdminAndLastPasskey(TestCase):
    def test_the_last_admin_cannot_lose_members_manage(self) -> None:
        tenant = factories.tenant()
        admin = factories.member(tenant, roles=("admin",))
        with self.assertRaises(ValidationError) as caught:
            members_logic.assert_not_last_admin(tenant.id, admin, keeps_members_manage=False)
        self.assertEqual(caught.exception.code, "last_admin")
        members_logic.assert_not_last_admin(tenant.id, admin, keeps_members_manage=True)
        factories.member(tenant, roles=("admin",))
        members_logic.assert_not_last_admin(tenant.id, admin, keeps_members_manage=False)
        self.assertEqual(members_logic.admins_besides(tenant.id, admin.user_id), 1)

    def test_the_last_passkey_cannot_be_removed(self) -> None:
        person = factories.user()
        only = factories.passkey(person)
        principal = user_principal(subject_id=person.id)
        with self.assertRaises(ValidationError) as caught:
            passkey_logic.remove_passkey(principal, only.id)
        self.assertEqual(caught.exception.code, "last_passkey")
        second = factories.passkey(person, nickname="Phone")
        passkey_logic.remove_passkey(principal, only.id)
        self.assertEqual([p.id for p in passkey_logic.list_passkeys(person.id)], [second.id])
        with self.assertRaises(ValidationError):
            passkey_logic.rename_passkey(principal, only.id, "gone")
        with self.assertRaises(ValidationError):
            passkey_logic.remove_passkey(user_principal(subject_id=uuid.uuid4()), second.id)


class ApiKeyAuthClass(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.tenant = factories.tenant()
        issued = factories.api_key(self.tenant, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.key = issued.row
        self.plain = issued.plain_key

    def test_header_and_bearer_both_resolve_the_key(self) -> None:
        by_header = ApiKeyAuth()(self.factory.get("/", HTTP_X_API_KEY=self.plain))
        by_bearer = ApiKeyAuth()(self.factory.get("/", HTTP_AUTHORIZATION=f"Bearer {self.plain}"))
        for principal in (by_header, by_bearer):
            assert principal is not None
            self.assertEqual(principal.kind, PrincipalKind.AGENT)
            self.assertEqual(principal.tenant_id, self.tenant.id)
            self.assertTrue(principal.has_scope(perms.SCOPE_LIBRARY_READ))
        self.assertIsNone(ApiKeyAuth()(self.factory.get("/", HTTP_AUTHORIZATION="Bearer v1.not.a.key.x")))

    def test_last_used_is_throttled_and_expiry_and_revocation_bite(self) -> None:
        api_keys_logic.resolve_api_key(self.plain)
        self.key.refresh_from_db()
        first = self.key.last_used_at
        api_keys_logic.resolve_api_key(self.plain)
        self.key.refresh_from_db()
        self.assertEqual(self.key.last_used_at, first, "written at most once a minute")
        self.key.expires_at = timezone.now() - timedelta(seconds=1)
        self.key.save(update_fields=["expires_at"])
        self.assertIsNone(api_keys_logic.resolve_api_key(self.plain))
        with self.assertRaises(ValidationError):
            api_keys_logic.create_api_key(
                tenant=self.tenant, actor=factories.user_actor(), created_by=factories.user(), name=" ", scopes=[perms.SCOPE_LIBRARY_READ], expires_at=None, step_up_assertion_id=None
            )
        with self.assertRaises(ValidationError):
            api_keys_logic.create_api_key(
                tenant=self.tenant, actor=factories.user_actor(), created_by=factories.user(), name="x", scopes=[perms.SCOPE_LIBRARY_READ], expires_at=timezone.now() - timedelta(days=1), step_up_assertion_id=None
            )
        with self.assertRaises(ValidationError):
            api_keys_logic.revoke_api_key(tenant=self.tenant, actor=factories.user_actor(), revoked_by=factories.user(), key_id=uuid.uuid4())


class E2EOutbox(TestCase):
    def test_hidden_unless_e2e_mode(self) -> None:
        self.assertEqual(self.client.get("/api/v1/e2e/mail-outbox").status_code, 404)
        MockMailer.reset()
        MockMailer().send(OutgoingMail(to="a@b.test", subject="s", body="b"))
        with override_settings(E2E_MODE=True):
            response = self.client.get("/api/v1/e2e/mail-outbox")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"to": "a@b.test", "subject": "s", "body": "b"}])


class BootstrapPlatform(TestCase):
    def test_creates_the_admin_with_a_platform_invitation_once(self) -> None:
        MockMailer.reset()
        out = StringIO()
        call_command("bootstrap_platform", "--admin-email", "Root@Bleqq.test", stdout=out)
        user = User.objects.get(email="root@bleqq.test")
        self.assertEqual(PlatformRoleAssignment.objects.filter(user=user, role__key="platform_admin").count(), 1)
        invitation = Invitation.objects.get(email="root@bleqq.test", tenant__isnull=True)
        self.assertIsNone(invitation.tenant_id)
        self.assertIn("/invite#", out.getvalue())
        self.assertEqual(MockMailer.sent[-1].to, "root@bleqq.test")
        call_command("bootstrap_platform", "--admin-email", "root@bleqq.test", stdout=StringIO())
        self.assertEqual(PlatformRoleAssignment.objects.filter(user=user).count(), 1)
        factories.passkey(user)
        with self.assertRaises(CommandError):
            call_command("bootstrap_platform", "--admin-email", "root@bleqq.test", stdout=StringIO())
        # The platform session that follows carries the platform grants and no tenant.
        headers = sign_in(user, tenant=None)
        me = self.client.get("/api/v1/me", **headers).json()
        self.assertIsNone(me["tenant"])
        self.assertEqual([r["key"] for r in me["platformRoles"]], ["platform_admin"])
        self.assertEqual(self.client.get("/api/v1/tenant", **headers).status_code, 404)
        self.assertFalse(WebAuthnCredential.objects.filter(user=user).count() == 0)


class ThePlatformRowIsWrittenInASavepointOfItsOwn(TestCase):
    """`log_event()` leaves the tenant zone to write a platform row (H15), and puts the
    tenant back on the way out whether the insert worked or not. A failed insert aborts the
    transaction, so without a savepoint inside that block the way out runs its SET on an
    aborted transaction and raises there instead — and what the caller sees is that, not
    the error the insert raised. `record()` nests the two the same way.

    A value too long for its column stands in for every database error an insert can raise:
    a constraint, a policy, a connection that went away.

    Proven to fail 2026-09-20 by taking the inner transaction back out: the error was
    TransactionManagementError from the way out, and the DataError was lost.
    """

    def test_a_failed_insert_surfaces_its_own_error_and_gives_the_tenant_back(self) -> None:
        tenant = factories.tenant(slug="security-log-savepoint")
        with transaction.atomic():
            tenancy.activate(tenant.id)

            with self.assertRaises(DataError):
                security_log.log_event(
                    event=LoginEventKind.SIGNIN_FAILED,
                    method=LoginMethod.PASSKEY,
                    success=False,
                    request=None,
                    tenant_id=None,
                    failure_reason="x" * 200,  # the column holds 100
                )

            self.assertEqual(tenancy.database_tenant_id(), tenant.id, "the tenant is back on")
            self.assertEqual(LoginEvent.objects.filter(tenant__isnull=True).count(), 0)


# ---------------------------------------------------------------------------------------
# Regressions from the chunk 1 security review (docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md).
# Each test names its finding.
# ---------------------------------------------------------------------------------------
class ClientAddress(TestCase):
    """F1: X-Forwarded-For is caller-supplied text; only the hops we own are trusted."""

    def _request(self, forwarded: str | None, remote: str = "10.0.0.9") -> HttpRequest:
        request = RequestFactory().post("/api/v1/auth/code/request")
        request.META["REMOTE_ADDR"] = remote
        if forwarded is not None:
            request.META["HTTP_X_FORWARDED_FOR"] = forwarded
        return request

    @override_settings(TRUSTED_PROXY_HOPS=0)
    def test_without_a_trusted_proxy_the_header_is_ignored(self) -> None:
        self.assertEqual(security_log.client_ip(self._request("1.1.1.1, 2.2.2.2")), "10.0.0.9")
        self.assertEqual(security_log.client_ip(self._request(None)), "10.0.0.9")

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_behind_one_proxy_the_rightmost_hop_wins_never_a_spoofed_leftmost_value(self) -> None:
        self.assertEqual(security_log.client_ip(self._request("spoofed, 203.0.113.7")), "203.0.113.7")
        self.assertEqual(security_log.client_ip(self._request("203.0.113.7")), "203.0.113.7")
        self.assertEqual(security_log.client_ip(self._request(None)), "10.0.0.9", "no header: the socket address")

    @override_settings(TRUSTED_PROXY_HOPS=2)
    def test_behind_two_proxies_the_second_from_the_right_is_the_client(self) -> None:
        self.assertEqual(security_log.client_ip(self._request("spoofed, 203.0.113.7, 10.1.1.1")), "203.0.113.7")
        self.assertEqual(security_log.client_ip(self._request("203.0.113.7")), "10.0.0.9", "fewer hops than trusted: fall back")

    @override_settings(RATE_LIMITING_ENABLED=True, E2E_MODE=False, AUTH_RATE_PER_IP_PER_MINUTE=2, TRUSTED_PROXY_HOPS=0)
    def test_a_spoofed_header_cannot_reset_the_per_ip_limit(self) -> None:
        cache.clear()
        for n in range(2):
            passkey_logic.authentication_options(self._request(f"{n}.{n}.{n}.{n}"))
        with self.assertRaises(ProblemError) as caught:
            passkey_logic.authentication_options(self._request("9.9.9.9"))
        self.assertEqual(caught.exception.status, 429)


class UnauthenticatedCeremonySteps(TestCase):
    """F5: every unauthenticated ceremony step is bounded per IP, including the sign-in
    options (a challenge row and an audit row per call) and an unknown invitation token."""

    def setUp(self) -> None:
        cache.clear()

    @override_settings(RATE_LIMITING_ENABLED=True, E2E_MODE=False, AUTH_RATE_PER_IP_PER_MINUTE=2)
    def test_sign_in_options_and_unknown_invitation_tokens_are_rate_limited(self) -> None:
        request = RequestFactory().post("/api/v1/auth", REMOTE_ADDR="198.51.100.4")
        for _ in range(2):
            passkey_logic.authentication_options(request)
        with self.assertRaises(ProblemError) as caught:
            passkey_logic.authentication_options(request)
        self.assertEqual((caught.exception.status, caught.exception.code), (429, "rate_limited"))
        cache.clear()
        for _ in range(2):
            with self.assertRaises(invitation_logic.InvitationExpired):
                invitation_logic.open_invitation("not-a-token", request)
        with self.assertRaises(ProblemError) as caught:
            invitation_logic.open_invitation("not-a-token", request)
        self.assertEqual(caught.exception.status, 429)


class CodeAttemptsUnderConcurrency(TestCase):
    """F2: the attempt counter is spent with one conditional UPDATE, so parallel guesses
    at the same code can never exceed max_attempts between them."""

    def setUp(self) -> None:
        MockMailer.reset()
        self.user = factories.user(email="race@bank.example", status=UserStatus.INVITED)

    def _issue(self) -> tuple[OtpCode, str]:
        row = code_logic.issue_code(user=self.user, tenant_id=None, request=None)
        code = re.search(r"Your code is (\d+)", MockMailer.sent[-1].body)
        assert code is not None
        return row, code.group(1)

    def test_a_right_code_is_refused_when_concurrent_requests_already_spent_the_attempts(self) -> None:
        row, code = self._issue()
        original = code_logic._open_code

        def read_then_lose_the_race(email: str, now: Any) -> OtpCode | None:
            found = original(email, now)
            # Between this read and the claim, other requests spend every attempt.
            OtpCode.objects.filter(pk=row.pk).update(attempts=F("max_attempts"))
            return found

        with mock.patch.object(code_logic, "_open_code", side_effect=read_then_lose_the_race):
            with self.assertRaises(ValidationError) as caught:
                code_logic.verify_code(self.user.email, code, None)
        self.assertEqual(caught.exception.code, "code_locked")
        row.refresh_from_db()
        self.assertEqual(row.attempts, row.max_attempts, "the losing request spent nothing beyond the cap")
        self.assertIsNone(row.consumed_at)

    def test_a_code_is_consumed_once_even_when_two_right_answers_are_in_flight(self) -> None:
        row, code = self._issue()
        original = code_logic._open_code

        def read_then_someone_consumes(email: str, now: Any) -> OtpCode | None:
            found = original(email, now)
            OtpCode.objects.filter(pk=row.pk).update(consumed_at=timezone.now())
            return found

        with mock.patch.object(code_logic, "_open_code", side_effect=read_then_someone_consumes):
            with self.assertRaises(ValidationError) as caught:
                code_logic.verify_code(self.user.email, code, None)
        self.assertEqual(caught.exception.code, "code_locked", "a consumed row claims no attempt either")


class ChallengeSingleUse(TestCase):
    """F3: a WebAuthn challenge is claimed with one conditional UPDATE, so the same
    assertion presented twice at once passes once."""

    def test_a_challenge_consumed_between_read_and_claim_is_refused(self) -> None:
        challenge = secrets.token_bytes(32)
        row = passkey_logic._store_challenge(ChallengeKind.AUTHENTICATION, challenge, user=None, session=None)
        original = passkey_logic._open_challenge

        def read_then_lose_the_race(*args: Any, **kwargs: Any) -> AuthChallenge | None:  # compliance: allow-kwargs test double forwarding the real signature
            found = original(*args, **kwargs)
            AuthChallenge.objects.filter(pk=row.pk).update(consumed_at=timezone.now())
            return found

        with mock.patch.object(passkey_logic, "_open_challenge", side_effect=read_then_lose_the_race):
            with self.assertRaises(ValidationError) as caught:
                passkey_logic._consume_challenge(ChallengeKind.AUTHENTICATION, challenge)
        self.assertEqual(caught.exception.code, "challenge_expired")

    def test_a_challenge_is_consumed_once(self) -> None:
        challenge = secrets.token_bytes(32)
        passkey_logic._store_challenge(ChallengeKind.AUTHENTICATION, challenge, user=None, session=None)
        passkey_logic._consume_challenge(ChallengeKind.AUTHENTICATION, challenge)
        with self.assertRaises(ValidationError):
            passkey_logic._consume_challenge(ChallengeKind.AUTHENTICATION, challenge)


class UserHandleBinding(TestCase):
    """F4 (WebAuthn §7.2 step 6): a discoverable sign-in names its account through the
    assertion's userHandle, which must be the owner of the credential."""

    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.user = factories.member(self.tenant).user
        self.authenticator = SoftwareAuthenticator()
        factories.passkey(self.user, public_key=tokens.b64url(self.authenticator.cose_public_key()), credential_id=self.authenticator.credential_id_b64)

    def _assert(self) -> dict[str, Any]:
        return self.authenticator.assert_(passkey_logic.authentication_options(None))

    def test_a_missing_or_foreign_user_handle_fails_sign_in_and_the_right_one_passes(self) -> None:
        self.authenticator.user_handle = None
        with self.assertRaises(passkey_logic.SignInFailed):
            passkey_logic.verify_authentication(self._assert(), None)
        self.authenticator.user_handle = uuid.uuid4().bytes
        with self.assertRaises(passkey_logic.SignInFailed):
            passkey_logic.verify_authentication(self._assert(), None)
        self.assertEqual(
            list(LoginEvent.objects.filter(user=self.user, event=LoginEventKind.SIGNIN_FAILED.value).values_list("failure_reason", flat=True)),
            ["user_handle_mismatch", "user_handle_mismatch"],
        )
        self.authenticator.user_handle = self.user.id.bytes
        bundle = passkey_logic.verify_authentication(self._assert(), None)
        self.assertEqual(bundle.session.user_id, self.user.id)

    def test_a_step_up_with_a_foreign_user_handle_is_refused(self) -> None:
        headers_session = session_logic.create_session(user=self.user, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None)
        principal = session_logic.resolve_access_token(headers_session.access_token, want=PrincipalKind.USER)
        assert principal is not None
        self.authenticator.user_handle = uuid.uuid4().bytes
        credential = self.authenticator.assert_(passkey_logic.step_up_options(principal))
        with self.assertRaises(passkey_logic.StepUpFailed):
            passkey_logic.verify_step_up(principal, credential, None)


class FullSessionsStandOnMemberships(TestCase):
    """F7: a full session in a tenant resolves only while the person holds an active
    membership there; deactivation also closes the address's open invitations, so nobody
    enrols back into a tenant that removed them."""

    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.membership = factories.member(self.tenant)
        self.user = self.membership.user

    def test_a_session_whose_membership_was_deactivated_resolves_to_nothing(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self.client.get("/api/v1/tenant", **headers).status_code, 200)
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(pk=self.membership.pk).update(deactivated_at=timezone.now())
        self.assertEqual(self.client.get("/api/v1/tenant", **headers).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/me", **headers).status_code, 401)

    def test_deactivation_closes_open_invitations_for_the_address(self) -> None:
        admin = factories.member(self.tenant, roles=("admin",)).user
        pending = factories.invitation(self.tenant, email=self.user.email, kind=InvitationKind.REENROLMENT)
        tenancy.activate(self.tenant.id)
        members_logic.deactivate_member(tenant=self.tenant, actor=session_logic.actor_of(admin), user_id=self.user.id, request=None)
        pending.refresh_from_db()
        self.assertIsNotNone(pending.revoked_at)
        self.assertIsNone(invitation_logic.find_open_for_tenant(self.user.email, self.tenant.id))

    def test_a_re_invited_member_comes_back_with_the_new_roles(self) -> None:
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(pk=self.membership.pk).update(deactivated_at=timezone.now())
        invitation = factories.invitation(self.tenant, email=self.user.email, roles=("auditor",))
        tenancy.activate(self.tenant.id)
        membership = invitation_logic.accept_invitation(invitation, self.user, timezone.now())
        assert membership is not None
        self.assertIsNone(membership.deactivated_at)
        self.assertEqual(sorted(membership.roles.values_list("key", flat=True)), ["auditor"])


class EnrolmentBoundToItsInvitation(TestCase):
    """F8: the first passkey accepts the invitation the enrolment session came from (the
    session's tenant), not whichever tenant invited the address most recently."""

    def test_the_session_tenants_invitation_is_accepted_and_the_other_stays_open(self) -> None:
        email = "two-banks@test.example"
        first, second = factories.tenant(slug="first"), factories.tenant(slug="second")
        invitation_first = factories.invitation(first, email=email, roles=("reader",))
        invitation_second = factories.invitation(second, email=email, roles=("admin",))
        user = factories.user(email=email, status=UserStatus.INVITED)
        tenancy.activate(first.id)
        bundle = session_logic.create_session(user=user, kind=SessionKind.ENROLMENT, tenant_id=first.id, request=None)
        principal = session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.ENROLMENT)
        assert principal is not None
        authenticator = SoftwareAuthenticator()
        credential = authenticator.register(passkey_logic.registration_options(principal))
        result = passkey_logic.verify_registration(principal, credential, "Laptop", None)
        assert result.bundle is not None
        self.assertEqual(result.bundle.session.tenant_id, first.id)
        tenancy.activate(first.id)
        self.assertTrue(Membership.objects.filter(tenant=first, user=user, deactivated_at__isnull=True).exists())
        invitation_first.refresh_from_db()
        self.assertIsNotNone(invitation_first.accepted_at)
        tenancy.activate(second.id)
        invitation_second.refresh_from_db()
        self.assertIsNone(invitation_second.accepted_at, "the other tenant's invitation is untouched")
        self.assertFalse(Membership.objects.filter(tenant=second, user=user).exists())


class CredentialIdUniqueness(TestCase):
    """F15 (WebAuthn §7.1 step 22): a credential id already registered to another account
    is refused with 400 registration_failed, not a broken transaction."""

    def test_a_duplicate_credential_id_is_refused_cleanly(self) -> None:
        authenticator = SoftwareAuthenticator()
        factories.passkey(factories.user(), public_key=tokens.b64url(authenticator.cose_public_key()), credential_id=authenticator.credential_id_b64)
        other = factories.user()
        bundle = session_logic.create_session(user=other, kind=SessionKind.FULL, tenant_id=None, request=None)
        principal = session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.USER)
        assert principal is not None
        credential = authenticator.register(passkey_logic.registration_options(principal))
        with self.assertRaises(ValidationError) as caught:
            passkey_logic.verify_registration(principal, credential, "Dup", None)
        self.assertEqual(caught.exception.code, "registration_failed")
        self.assertEqual(WebAuthnCredential.objects.filter(user=other).count(), 0)
        # The request transaction is still usable after the refused insert.
        self.assertTrue(User.objects.filter(pk=other.pk).exists())


class E2ESignCountLeniency(TestCase):
    """Playwright's virtual authenticator restarts its counter per browser context, so a
    seeded login's second sign-in in a run presents a count at or below the stored one.
    Under E2E_MODE only, the regression is accepted and logged; outside it py_webauthn
    refuses it (a cloned authenticator), and a deployed environment refuses the leniency."""

    def setUp(self) -> None:
        from apps.identity.tests_webauthn_support import SoftwareAuthenticator

        self.user = factories.user()
        self.authenticator = SoftwareAuthenticator()
        self.authenticator.user_handle = self.user.id.bytes
        self.row = factories.passkey(
            self.user, public_key=tokens.b64url(self.authenticator.cose_public_key()), credential_id=self.authenticator.credential_id_b64
        )
        self.row.sign_count = 5
        self.row.save(update_fields=["sign_count"])

    def _regressed_assertion(self) -> dict[str, Any]:
        options = passkey_logic.authentication_options(None)
        return self.authenticator.assert_(options)  # the authenticator's count restarts at 1

    def test_outside_e2e_a_non_increasing_counter_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            passkey_logic.verify_authentication(self._regressed_assertion(), None)
        self.assertEqual(caught.exception.code, "signin_failed")
        self.assertTrue(LoginEvent.objects.filter(user=self.user, event=LoginEventKind.SIGNIN_FAILED.value).exists())

    @override_settings(E2E_MODE=True)
    def test_under_e2e_the_regression_is_accepted_and_logged(self) -> None:
        bundle = passkey_logic.verify_authentication(self._regressed_assertion(), None)
        self.assertEqual(bundle.session.user_id, self.user.id)
        self.row.refresh_from_db()
        self.assertEqual(self.row.sign_count, 5, "the stored counter never goes down")
        signins = LoginEvent.objects.filter(user=self.user, event=LoginEventKind.SIGNIN.value, success=True).order_by("id")
        self.assertEqual([row.failure_reason for row in signins], ["", passkey_logic.SIGN_COUNT_REGRESSION_IGNORED_E2E])

    @override_settings(E2E_MODE=True, IS_DEPLOYED_ENVIRONMENT=True)
    def test_the_leniency_is_refused_when_deployed(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            passkey_logic.verify_authentication(self._regressed_assertion(), None)


class E2ERateLimitsOff(TestCase):
    """The three bootstrap steps a journey repeats from one address are unlimited under
    E2E_MODE; every other limit, and every limit outside E2E, still fires."""

    def setUp(self) -> None:
        cache.clear()

    @override_settings(
        RATE_LIMITING_ENABLED=True,
        E2E_MODE=True,
        ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR=1,
        ENROLMENT_CODE_RATE_PER_IP_PER_HOUR=1,
        AUTH_RATE_PER_IP_PER_MINUTE=1,
    )
    def test_exempt_buckets_do_not_fire_under_e2e_but_the_verify_limit_does(self) -> None:
        from apps.identity import code_logic

        request = RequestFactory().post("/")
        for _ in range(3):
            code_logic.enforce_code_limits("anna@bank.example", request)
            rate_limit.enforce("auth:ip", "127.0.0.1", 1, 60, e2e_exempt=True)
        rate_limit.enforce("auth:ip", "127.0.0.1", 1, 60)
        with self.assertRaises(ProblemError):
            rate_limit.enforce("auth:ip", "127.0.0.1", 1, 60)

    @override_settings(RATE_LIMITING_ENABLED=True, E2E_MODE=False)
    def test_the_same_buckets_fire_outside_e2e(self) -> None:
        rate_limit.enforce("code-request:address", "anna@bank.example", 1, 60, e2e_exempt=True)
        with self.assertRaises(ProblemError):
            rate_limit.enforce("code-request:address", "anna@bank.example", 1, 60, e2e_exempt=True)


class StepUpOnPasskeyChanges(TestCase):
    """Security review F9, narrowed (2026-09-19): a sign-in or an enrolment never mints a
    step-up assertion, so every `@requires_step_up` action needs an explicit ceremony
    (ID-S14). Adding or removing a passkey from a full session is allowed while the
    session itself is younger than the step-up window, or with a fresh assertion."""

    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.user = factories.member(self.tenant, roles=("admin",)).user
        self.authenticator = SoftwareAuthenticator()
        self.authenticator.user_handle = self.user.id.bytes
        self.row = factories.passkey(
            self.user, public_key=tokens.b64url(self.authenticator.cose_public_key()), credential_id=self.authenticator.credential_id_b64
        )

    def _later(self, minutes: int) -> Any:
        return mock.patch.object(timezone, "now", return_value=timezone.now() + timedelta(minutes=minutes))

    def _add(self, headers: dict[str, Any]) -> Any:
        options = self.client.post("/api/v1/auth/passkeys/register/options", **headers)
        self.assertEqual(options.status_code, 200)
        return self.client.post(
            "/api/v1/auth/passkeys/register/verify",
            data={"credential": SoftwareAuthenticator().register(options.json()), "nickname": "Phone"},
            content_type="application/json",
            **headers,
        )

    def test_a_passkey_sign_in_mints_no_assertion_and_does_not_satisfy_step_up(self) -> None:
        from apps.identity.models import StepUpAssertion

        options = passkey_logic.authentication_options(None)
        bundle = passkey_logic.verify_authentication(self.authenticator.assert_(options), None)
        self.assertFalse(StepUpAssertion.objects.filter(session=bundle.session).exists())
        headers: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {bundle.access_token}"}
        self.assertIsNone(self.client.get("/api/v1/me", **headers).json()["stepUpValidUntil"])
        other = factories.member(self.tenant).user
        refused = self.client.post(f"/api/v1/tenant/members/{other.id}/reissue-enrolment", **headers)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "step_up_required"))

    def test_passkey_changes_pass_inside_the_window_after_sign_in_and_not_after(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self._add(headers).status_code, 201)
        second = factories.passkey(self.user, nickname="Other")
        self.assertEqual(self.client.delete(f"/api/v1/me/passkeys/{second.id}", **headers).status_code, 204)
        third = factories.passkey(self.user, nickname="Third")
        with self._later(settings.STEP_UP_FRESHNESS_MINUTES + 1):
            added = self._add(headers)
            removed = self.client.delete(f"/api/v1/me/passkeys/{third.id}", **headers)
        self.assertEqual((added.status_code, added.json()["code"]), (403, "step_up_required"))
        self.assertEqual((removed.status_code, removed.json()["code"]), (403, "step_up_required"))

    def test_a_refresh_does_not_reset_the_window_but_a_step_up_opens_it(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        third = factories.passkey(self.user, nickname="Third")
        with self._later(settings.STEP_UP_FRESHNESS_MINUTES + 1):
            refreshed = self.client.post("/api/v1/auth/refresh", HTTP_COOKIE=headers["HTTP_COOKIE"])
            self.assertEqual(refreshed.status_code, 200, refreshed.content)
            renewed: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {refreshed.json()['accessToken']}"}
            refused = self.client.delete(f"/api/v1/me/passkeys/{third.id}", **renewed)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "step_up_required"))
        fresh = sign_in(self.user, tenant=self.tenant, step_up=True)
        with self._later(settings.STEP_UP_FRESHNESS_MINUTES - 1):
            self.assertEqual(self.client.delete(f"/api/v1/me/passkeys/{third.id}", **fresh).status_code, 204)


class MailLeavesThroughTheWorker(TestCase):
    """Security review F12, fixed: mails are composed in the request and delivered by the
    Celery task after commit; the mock outbox lives in the cache so another process can
    read it."""

    # Celery's import hook runs Django's model checks, which read the server version of
    # every connection, the row-level-security alias `app` included. Whether that read hit
    # the database depended on whether an earlier test had already opened `app`, so the
    # first test here passed or failed by suite order.
    databases = {"default", "app"}

    def setUp(self) -> None:
        MockMailer.reset()

    def test_the_task_is_registered_and_the_outbox_is_in_the_cache(self) -> None:
        from apps.shared.adapters.mailer import MOCK_OUTBOX_CACHE_KEY
        from config.celery import app as celery_app

        celery_app.loader.import_default_modules()
        self.assertIn("apps.identity.tasks.deliver_mail", celery_app.tasks)
        mail.send_code("anna@bank.example", "123456")
        self.assertEqual(len(MockMailer.sent), 1)
        self.assertEqual(cache.get(MOCK_OUTBOX_CACHE_KEY)[0][0], "anna@bank.example")
        MockMailer.reset()
        self.assertEqual(MockMailer.sent, [])

    def test_the_code_mail_names_enrolment_and_never_sign_in(self) -> None:
        """The emailed code works once, for enrolment only, and stops working once the
        first passkey exists (CLAUDE.md section 5), so the subject never calls it a sign-in
        code: a person who read that would expect it to let them sign in again."""
        mail.send_code("anna@bank.example", "123456")
        subject = MockMailer.sent[0].subject
        self.assertIn("enrolment code", subject)
        self.assertNotIn("sign-in", subject.lower())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_outside_tests_the_mail_waits_for_the_commit(self) -> None:
        from apps.identity import tasks

        with mock.patch.object(tasks.deliver_mail, "delay", side_effect=lambda *args: tasks.deliver_mail.apply(args=args)) as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                mail.send_code("anna@bank.example", "123456")
                self.assertEqual(MockMailer.sent, [], "nothing leaves inside the transaction")
            self.assertEqual(len(callbacks), 1)
            delay.assert_not_called()
            callbacks[0]()
            delay.assert_called_once()
        self.assertEqual([m.to for m in MockMailer.sent], ["anna@bank.example"])


class InvitationCodeByToken(TestCase):
    """The invitation path verifies the emailed code against the invitation the link
    names (POST /auth/invitations/verify {token, code}): no email address travels, and a
    code issued for any other address never verifies. The token is in the body, never
    the path, so no access log holds it (finding F6)."""

    def setUp(self) -> None:
        MockMailer.reset()
        cache.clear()
        self.tenant = factories.tenant(slug="token-bank")
        self.invitation = factories.invitation(self.tenant, email="anna@token.example")
        self.token: str = self.invitation.plain_token  # type: ignore[attr-defined]

    def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.client.post(f"/api/v1{path}", data=body or {}, content_type="application/json", REMOTE_ADDR="198.51.100.7")

    def _open(self, token: str) -> str:
        """Open the link and return the code the mail carried."""
        self.assertEqual(self._post("/auth/invitations/open", {"token": token}).status_code, 202)
        found = re.search(r"Your code is (\d+)", MockMailer.sent[-1].body)
        assert found is not None
        return found.group(1)

    def _verify(self, token: str, code: str) -> Any:
        return self._post("/auth/invitations/verify", {"token": token, "code": code})

    def test_the_right_token_and_code_open_an_enrolment_session_in_the_invitations_tenant(self) -> None:
        code = self._open(self.token)
        response = self._verify(self.token, code)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["sessionKind"], "enrolment")
        self.assertIn(settings.REFRESH_COOKIE_NAME, response.cookies)
        tenancy.activate(self.tenant.id)
        session = UserSession.objects.get(user__email="anna@token.example")
        self.assertEqual((session.kind, session.tenant_id), (SessionKind.ENROLMENT.value, self.tenant.id))
        self.assertIsNotNone(OtpCode.objects.get(email="anna@token.example").consumed_at, "the code works once")
        self.assertEqual(self._verify(self.token, code).json()["code"], "invalid_code")

    def test_a_code_issued_for_another_address_never_verifies(self) -> None:
        other = factories.invitation(self.tenant, email="bo@token.example")
        with mock.patch.object(tokens, "new_code", side_effect=["111111", "222222"]):
            self._open(self.token)
            bo_code = self._open(other.plain_token)  # type: ignore[attr-defined]
        self.assertEqual(bo_code, "222222")
        refused = self._verify(self.token, bo_code)
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["code"], "invalid_code")
        anna_row = OtpCode.objects.get(email="anna@token.example", consumed_at__isnull=True)
        self.assertEqual(anna_row.attempts, 1, "the wrong guess is counted against the link's own code")
        self.assertEqual(OtpCode.objects.get(email="bo@token.example").attempts, 0, "the other address's code is untouched")
        self.assertFalse(UserSession.objects.exists())

    def test_an_expired_revoked_consumed_or_unknown_invitation_answers_410(self) -> None:
        code = self._open(self.token)
        with mock.patch.object(timezone, "now", return_value=timezone.now() + timedelta(hours=settings.INVITATION_TTL_HOURS + 1)):
            expired = self._verify(self.token, code)
        self.assertEqual((expired.status_code, expired.json()["code"]), (410, "invitation_expired"))
        for field in ("revoked_at", "accepted_at"):
            with self.subTest(closed_by=field):
                row = factories.invitation(self.tenant, email=f"{field}@token.example")
                row_code = self._open(row.plain_token)  # type: ignore[attr-defined]
                tenancy.activate(self.tenant.id)
                Invitation.objects.filter(pk=row.pk).update(**{field: timezone.now()})
                closed = self._verify(row.plain_token, row_code)  # type: ignore[attr-defined]
                self.assertEqual((closed.status_code, closed.json()["code"]), (410, "invitation_expired"))
        unknown = self._verify("not-a-token", code)
        self.assertEqual((unknown.status_code, unknown.json()["code"]), (410, "invitation_expired"))
        self.assertFalse(UserSession.objects.exists())

    def test_wrong_codes_are_counted_and_the_sixth_attempt_is_locked(self) -> None:
        code = self._open(self.token)
        wrong = "000000" if code != "000000" else "111111"
        with mock.patch.object(tokens.secrets, "compare_digest", wraps=secrets.compare_digest) as compare:
            for attempt in range(settings.ENROLMENT_CODE_MAX_ATTEMPTS):
                response = self._verify(self.token, wrong)
                self.assertEqual((response.status_code, response.json()["code"]), (400, "invalid_code"), f"attempt {attempt + 1}")
            self.assertEqual(compare.call_count, settings.ENROLMENT_CODE_MAX_ATTEMPTS, "every attempt compares in constant time")
        locked = self._verify(self.token, code)
        self.assertEqual((locked.status_code, locked.json()["code"]), (400, "code_locked"))
        tenancy.activate(self.tenant.id)
        events = LoginEvent.objects.filter(tenant_id=self.tenant.id, email="anna@token.example", success=False)
        self.assertEqual(events.filter(event=LoginEventKind.CODE_FAILED.value).count(), settings.ENROLMENT_CODE_MAX_ATTEMPTS - 1)
        self.assertEqual(events.filter(event=LoginEventKind.CODE_LOCKED.value).count(), 2, "the fifth wrong code and the sixth attempt")

    @override_settings(RATE_LIMITING_ENABLED=True, E2E_MODE=False, AUTH_RATE_PER_IP_PER_MINUTE=2)
    def test_guesses_are_rate_limited_per_ip_before_the_lookup(self) -> None:
        for _ in range(2):
            self.assertEqual(self._verify("not-a-token", "123456").status_code, 410)
        limited = self._verify("not-a-token", "123456")
        self.assertEqual((limited.status_code, limited.json()["code"]), (429, "rate_limited"))

    @override_settings(API_BUDGET_MS=-1)
    def test_the_token_is_never_logged(self) -> None:
        records: list[logging.LogRecord] = []

        class Keep(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = Keep(level=logging.DEBUG)
        root = logging.getLogger()
        previous_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            code = self._open(self.token)
            self.assertEqual(self._verify(self.token, "000000" if code != "000000" else "111111").status_code, 400)
            self.assertEqual(self._verify(self.token, code).status_code, 200)
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)
        self.assertTrue(records, "the over-budget warning fired, so the log path was exercised")
        for record in records:
            self.assertNotIn(self.token, f"{record.getMessage()} {record.__dict__}")
        tenancy.activate(self.tenant.id)
        self.assertNotIn(self.token, str(list(LoginEvent.objects.values())))
        self.assertNotIn(self.token, str(list(AuditEvent.objects.values())))


class InvitationTokenNeverInAPath(TestCase):
    """Security review 2026-09-19, finding F29: every server that logs request lines
    (Django's request logger on a 4xx, runserver, gunicorn's access log, the hosting edge,
    the web server) writes the path down, so the invitation token must never be in one.
    The emailed link carries it in the fragment, which no browser sends, and the API
    takes it in the body."""

    def setUp(self) -> None:
        MockMailer.reset()
        cache.clear()

    def test_no_invitation_route_has_a_path_parameter(self) -> None:
        paths = api.get_openapi_schema()["paths"]
        invitation_auth = sorted(path for path in paths if path.startswith("/api/v1/auth/invitations"))
        self.assertEqual(invitation_auth, ["/api/v1/auth/invitations/open", "/api/v1/auth/invitations/verify"])
        for path in invitation_auth:
            self.assertNotIn("{", path)
            self.assertEqual(set(paths[path]), {"post"})

    def test_the_emailed_link_holds_the_token_in_the_fragment_alone(self) -> None:
        token = "secret-invitation-token-29"  # noqa: S105 a test value, not a credential
        parts = urlsplit(mail.invitation_link(token))
        self.assertEqual((parts.path, parts.query, parts.fragment), ("/invite", "", token))

    def test_opening_takes_the_token_in_the_body_and_no_request_line_or_log_carries_it(self) -> None:
        tenant = factories.tenant(slug="f29-bank")
        invitation = factories.invitation(tenant, email="anna@f29.example")
        token: str = invitation.plain_token  # type: ignore[attr-defined]
        opened = self.client.post("/api/v1/auth/invitations/open", data={"token": token}, content_type="application/json")
        self.assertEqual(opened.status_code, 202, opened.content)
        self.assertIn("Your code is", MockMailer.sent[-1].body)
        self.assertNotIn(token, opened.wsgi_request.get_full_path())
        # A 4xx is where Django's request logger writes the request line down.
        unknown = "unknown-token-29"
        with self.assertLogs("django.request", level="WARNING") as logs:
            gone = self.client.post("/api/v1/auth/invitations/open", data={"token": unknown}, content_type="application/json")
        self.assertEqual((gone.status_code, gone.json()["code"]), (410, "invitation_expired"))
        self.assertNotIn(unknown, "\n".join(logs.output))
        self.assertNotIn(unknown, gone.wsgi_request.get_full_path())
        # The path form is gone: a token in a path reaches no handler.
        self.assertEqual(self.client.post(f"/api/v1/auth/invitations/{token}/open").status_code, 404)

    def test_a_token_longer_than_any_issued_is_refused_before_any_lookup(self) -> None:
        response = self.client.post("/api/v1/auth/invitations/open", data={"token": "x" * 129}, content_type="application/json")
        self.assertEqual(response.status_code, 422)


class NotificationPreferences(TestCase):
    """COL-02 (c10-notify-and-prefs): each person's own switches on `GET /me` and
    `PATCH /me`, every one on until they turn it off, stored on their membership of the
    bank the session is in and audited once with before and after."""

    ALL_ON = {"weeklyDigest": True, "reminders": True, "mentions": True, "assignments": True, "weeklyBriefing": True}
    tenant: Tenant
    person: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="prefs-bank")
        cls.person = factories.member_user(cls.tenant, roles=("reader",))

    def setUp(self) -> None:
        # Signed in before any test counts audit rows: signing in writes rows of its own.
        self.headers = sign_in(self.person, tenant=self.tenant)

    def patch(self, body: dict[str, Any]) -> Any:
        return self.client.patch("/api/v1/me", data=body, content_type="application/json", **self.headers)

    def stored(self) -> dict[str, Any]:
        tenancy.activate(self.tenant.id)
        return Membership.objects.get(tenant=self.tenant, user=self.person).notification_prefs

    def test_a_member_who_never_chose_reads_every_switch_on(self) -> None:
        body = self.client.get("/api/v1/me", **self.headers).json()
        self.assertEqual(body["notificationPrefs"], self.ALL_ON)

    def test_a_platform_session_has_no_switches(self) -> None:
        editor = factories.platform_user(roles=("library_editor",), email="editor-prefs@bleqq.test")
        self.assertIsNone(self.client.get("/api/v1/me", **sign_in(editor)).json()["notificationPrefs"])
        refused = self.client.patch(
            "/api/v1/me", data={"notificationPrefs": {"mentions": False}}, content_type="application/json", **sign_in(editor)
        )
        self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))

    def test_a_partial_patch_changes_its_switch_and_leaves_the_others_with_one_audit_event(self) -> None:
        self.patch({"notificationPrefs": {"reminders": False}})
        audit = AuditEvent.objects.count()

        response = self.patch({"notificationPrefs": {"mentions": False}})

        self.assertEqual(response.status_code, 200, response.content)
        expected = {**self.ALL_ON, "reminders": False, "mentions": False}
        self.assertEqual(response.json()["notificationPrefs"], expected)
        self.assertEqual(self.stored(), expected)
        self.assertEqual(AuditEvent.objects.count(), audit + 1)
        event = AuditEvent.objects.filter(action="user.updated").order_by("-created").first()
        assert event is not None
        self.assertEqual(event.before["notificationPrefs"], {**self.ALL_ON, "reminders": False})
        self.assertEqual(event.after["notificationPrefs"], expected)

    def test_a_name_and_the_switches_together_are_one_audit_event(self) -> None:
        audit = AuditEvent.objects.count()
        response = self.patch({"name": "Anna Berg", "notificationPrefs": {"weeklyBriefing": False}})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(AuditEvent.objects.count(), audit + 1)
        self.assertEqual(response.json()["user"]["name"], "Anna Berg")
        self.assertFalse(response.json()["notificationPrefs"]["weeklyBriefing"])

    def test_an_unknown_switch_answers_422_and_writes_nothing(self) -> None:
        audit = AuditEvent.objects.count()
        name = User.objects.get(pk=self.person.pk).name

        response = self.patch({"name": "Somebody Else", "notificationPrefs": {"mentions": False, "snooze": True}})

        self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_key"))
        self.assertEqual(self.stored(), {})
        self.assertEqual(User.objects.get(pk=self.person.pk).name, name)
        self.assertEqual(AuditEvent.objects.count(), audit)

    def test_a_switch_that_is_not_a_boolean_is_refused(self) -> None:
        response = self.patch({"notificationPrefs": {"mentions": "sometimes"}})
        self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))
        self.assertEqual(self.stored(), {})

    def test_a_patch_without_switches_leaves_them_alone(self) -> None:
        self.patch({"notificationPrefs": {"assignments": False}})
        self.patch({"name": "Anna Berg"})
        self.assertEqual(self.stored(), {**self.ALL_ON, "assignments": False})
