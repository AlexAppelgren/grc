"""Regression tests for the identity findings of the security review of 2026-11-11
(SECURITY_AND_SIMPLIFICATION_REVIEW_2026-11-11, identity and sessions). Each test names its
finding; the probes the review ran against the test database are written down here as the
proof that the fix holds."""

from __future__ import annotations

import re
import uuid
from typing import Any
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.identity import invitation_logic, passkey_logic, session_logic
from apps.identity.models import (
    Invitation,
    InvitationKind,
    LoginEvent,
    LoginEventKind,
    SessionKind,
    User,
    UserSession,
    UserStatus,
    WebAuthnCredential,
)
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.shared import factories, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.authentication import PrincipalKind
from apps.shared.models import AuditEvent
from apps.tenants.models import SupportAccess
from apps.shared.testing import sign_in

ANNA = "anna@review.example"
LINK = re.compile(r"/invite#(\S+)")
CODE = re.compile(r"Your code is (\d+)")
# A refused enrolment: its session revoked (401, or 403 `enrolment_only` once the enrolment
# token no longer resolves) or the ceremony's own refusal (410 `invitation_expired`).
REFUSED = (401, 403, 410)


def _found(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    assert match is not None, f"{pattern.pattern!r} not in the mail"
    return match.group(1)


class _Ceremonies(TestCase):
    def setUp(self) -> None:
        MockMailer.reset()
        cache.clear()
        self.tenant = factories.tenant(slug="review-bank")
        self.admin = factories.member(self.tenant, roles=("admin",)).user

    def _post(self, path: str, body: dict[str, Any] | None = None, headers: dict[str, Any] | None = None) -> Any:
        return self.client.post(f"/api/v1{path}", data=body or {}, content_type="application/json", **(headers or {}))

    def _bearer(self, token: str) -> dict[str, Any]:
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _invite(self) -> tuple[str, str]:
        """Invite Anna through the route; answers the invitation's id and the link's token."""
        answer = self._post("/tenant/members", {"email": ANNA, "roleKeys": ["reader"]}, sign_in(self.admin, tenant=self.tenant, step_up=True))
        self.assertEqual(answer.status_code, 201, answer.content)
        return answer.json()["id"], _found(LINK, MockMailer.sent[-1].body)

    def _enrolment_session(self, token: str) -> str:
        """Open the link, verify the code it mails: one more enrolment session."""
        self.assertEqual(self._post("/auth/invitations/open", {"token": token}).status_code, 202)
        verified = self._post("/auth/invitations/verify", {"token": token, "code": _found(CODE, MockMailer.sent[-1].body)})
        self.assertEqual(verified.status_code, 200, verified.content)
        return str(verified.json()["accessToken"])

    def _register(self, access_token: str, authenticator: SoftwareAuthenticator) -> Any:
        options = self._post("/auth/passkeys/register/options", headers=self._bearer(access_token))
        if options.status_code != 200:
            return options
        return self._post("/auth/passkeys/register/verify", {"credential": authenticator.register(options.json())}, self._bearer(access_token))

    def _live_passkeys(self) -> int:
        return WebAuthnCredential.objects.filter(user__email=ANNA, retired_at__isnull=True).count()


class AnEnrolmentSessionEndsWithTheFirstPasskeyAndTheInvitation(_Ceremonies):
    def test_a_second_code_session_cannot_add_a_passkey_after_the_first_one(self) -> None:
        """Review 2026-11-11 S-1: two codes verified for one invitation give two enrolment
        sessions; once a passkey is registered through the second, the first registers none."""
        _, token = self._invite()
        first = self._enrolment_session(token)
        second = self._enrolment_session(token)
        # The first session's ceremony is already under way when the second completes.
        early_options = self._post("/auth/passkeys/register/options", headers=self._bearer(first))
        self.assertEqual(early_options.status_code, 200, early_options.content)
        self.assertEqual(self._register(second, SoftwareAuthenticator()).status_code, 201)
        late = self._post(
            "/auth/passkeys/register/verify", {"credential": SoftwareAuthenticator().register(early_options.json())}, self._bearer(first)
        )
        self.assertIn(late.status_code, REFUSED, late.content)
        self.assertIn(self._register(first, SoftwareAuthenticator()).status_code, REFUSED)
        self.assertEqual(self._live_passkeys(), 1)
        tenancy.activate(self.tenant.id)
        self.assertFalse(UserSession.objects.filter(user__email=ANNA, kind=SessionKind.ENROLMENT.value, revoked_at__isnull=True).exists())

    def test_revoking_the_invitation_stops_the_enrolment_in_progress(self) -> None:
        """Review 2026-11-11 S-1: an administrator revokes the invitation while its enrolment
        session is open; the session then registers no passkey."""
        invitation_id, token = self._invite()
        enrolling = self._enrolment_session(token)
        revoked = self.client.delete(f"/api/v1/tenant/invitations/{invitation_id}", **sign_in(self.admin, tenant=self.tenant))
        self.assertEqual(revoked.status_code, 204, revoked.content)
        self.assertIn(self._register(enrolling, SoftwareAuthenticator()).status_code, REFUSED)
        self.assertEqual(self._live_passkeys(), 0)

    def test_the_ceremony_itself_refuses_an_enrolled_account_or_a_closed_invitation(self) -> None:
        """Review 2026-11-11 S-1: the guard holds in the ceremony, not only through the
        revocation, for a session that row-level security kept out of the revocation's reach."""
        invitation = factories.invitation(self.tenant, email=ANNA)
        user = factories.user(email=ANNA, status=UserStatus.INVITED)
        tenancy.activate(self.tenant.id)
        bundle = session_logic.create_session(user=user, kind=SessionKind.ENROLMENT, tenant_id=self.tenant.id, request=None)
        principal = session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.ENROLMENT)
        assert principal is not None
        factories.passkey(user)
        with self.assertRaises(invitation_logic.InvitationExpired):
            passkey_logic.registration_options(principal)
        WebAuthnCredential.objects.filter(user=user).update(retired_at=timezone.now())
        tenancy.activate(self.tenant.id)
        Invitation.objects.filter(pk=invitation.pk).update(revoked_at=timezone.now())
        with self.assertRaises(invitation_logic.InvitationExpired):
            passkey_logic.registration_options(principal)
        with self.assertRaises(invitation_logic.InvitationExpired):
            passkey_logic.verify_registration(principal, {}, None, None)


class ABankReEnrolsOnlyAnAccountThatIsNowhereElse(TestCase):
    def setUp(self) -> None:
        MockMailer.reset()
        cache.clear()
        self.bank_a = factories.tenant(slug="bank-a")
        self.bank_b = factories.tenant(slug="bank-b")
        self.admin_a = factories.member(self.bank_a, roles=("admin",)).user

    def _reissue(self, user: User) -> Any:
        return self.client.post(
            f"/api/v1/tenant/members/{user.id}/reissue-enrolment", **sign_in(self.admin_a, tenant=self.bank_a, step_up=True)
        )

    def _unchanged(self, user: User) -> None:
        user.refresh_from_db()
        self.assertEqual(user.status, UserStatus.ACTIVE.value)
        self.assertEqual(WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).count(), 1)
        tenancy.activate(self.bank_a.id)
        self.assertFalse(Invitation.objects.filter(email=user.email).exists())

    def test_a_member_of_another_bank_is_refused_and_nothing_changes(self) -> None:
        """Review 2026-11-11 S-2: bank A's administrator re-issues enrolment for a reader of
        bank A who administers bank B; 409, and her bank B session still answers."""
        person = factories.member(self.bank_a, roles=("reader",)).user
        factories.member(self.bank_b, roles=("admin",), user_row=person)
        factories.passkey(person)
        in_b = sign_in(person, tenant=self.bank_b)
        answer = self._reissue(person)
        self.assertEqual((answer.status_code, answer.json()["code"]), (409, "account_held_elsewhere"), answer.content)
        self._unchanged(person)
        self.assertEqual(self.client.get("/api/v1/me", **in_b).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/tenant/members", **in_b).status_code, 200)

    def test_platform_staff_with_a_console_session_is_refused_not_a_server_error(self) -> None:
        """Review 2026-11-11 S-2: for a member who is platform staff with an open console
        session, the route answered 500 (`NotUpdated`); it answers 409 and writes nothing."""
        person = factories.platform_user(roles=("library_editor",))
        factories.member(self.bank_a, roles=("reader",), user_row=person)
        factories.passkey(person)
        console = sign_in(person, tenant=None)
        answer = self._reissue(person)
        self.assertEqual((answer.status_code, answer.json()["code"]), (409, "account_held_elsewhere"), answer.content)
        self._unchanged(person)
        self.assertEqual(self.client.get("/api/v1/me", **console).status_code, 200)

    def test_the_console_recovery_refuses_the_same_accounts_and_leaves_no_support_record(self) -> None:
        """Review 2026-11-11 S-2: the console route re-enrols through the same function and
        refuses before it writes the support-access record."""
        person = factories.member(self.bank_a, roles=("admin",)).user
        factories.member(self.bank_b, roles=("reader",), user_row=person)
        support = factories.platform_user(roles=("platform_admin",))
        body = {"reason": "Lost every passkey", "ticketRef": "SUP-1", "outOfBandCheck": "Called back"}
        answer = self.client.post(
            f"/api/v1/console/tenants/{self.bank_a.id}/members/{person.id}/reissue-enrolment",
            data=body,
            content_type="application/json",
            **sign_in(support, tenant=None, step_up=True),
        )
        self.assertEqual((answer.status_code, answer.json()["code"]), (409, "account_held_elsewhere"), answer.content)
        tenancy.activate(self.bank_a.id)
        self.assertFalse(SupportAccess.objects.filter(tenant=self.bank_a).exists())

    def test_a_person_in_this_bank_alone_is_still_re_enrolled(self) -> None:
        """Review 2026-11-11 S-2: the ordinary case keeps working, sessions of this bank end."""
        person = factories.member(self.bank_a, roles=("reader",)).user
        factories.passkey(person)
        own = sign_in(person, tenant=self.bank_a)
        self.assertEqual(self._reissue(person).status_code, 202)
        person.refresh_from_db()
        self.assertEqual(person.status, UserStatus.INVITED.value)
        self.assertEqual(self.client.get("/api/v1/me", **own).status_code, 401)

    def test_a_full_session_of_an_account_that_is_not_active_resolves_to_nothing(self) -> None:
        """Review 2026-11-11 S-2: the resolver refuses a full session once the account is
        `invited` again, wherever the session lives, and the refresh ends it."""
        person = factories.member(self.bank_b, roles=("reader",)).user
        tenancy.activate(self.bank_b.id)
        bundle = session_logic.create_session(user=person, kind=SessionKind.FULL, tenant_id=self.bank_b.id, request=None)
        headers: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {bundle.access_token}"}
        self.assertEqual(self.client.get("/api/v1/me", **headers).status_code, 200)
        User.objects.filter(pk=person.pk).update(status=UserStatus.INVITED.value)
        self.assertEqual(self.client.get("/api/v1/me", **headers).status_code, 401)
        refreshed = self.client.post("/api/v1/auth/refresh", HTTP_COOKIE=f"{session_logic.refresh_cookie_name()}={bundle.refresh_value}")
        self.assertEqual(refreshed.status_code, 401)
        tenancy.activate(self.bank_b.id)
        self.assertIsNotNone(UserSession.objects.get(pk=bundle.session.pk).revoked_at)

    def test_a_console_session_cannot_be_revoked_from_a_bank_session(self) -> None:
        """Review 2026-11-11 S-2: `DELETE /me/sessions/{id}` naming the caller's console
        session from a bank session answers 404, never 500, and the console session lives."""
        person = factories.platform_user(roles=("library_editor",))
        factories.member(self.bank_a, roles=("reader",), user_row=person)
        tenancy.clear_tenant()
        console = session_logic.create_session(user=person, kind=SessionKind.FULL, tenant_id=None, request=None)
        in_bank = sign_in(person, tenant=self.bank_a)
        listed = self.client.get("/api/v1/me/sessions", **in_bank).json()
        self.assertNotIn(str(console.session.id), [row["id"] for row in listed])
        answer = self.client.delete(f"/api/v1/me/sessions/{console.session.id}", **in_bank)
        self.assertEqual((answer.status_code, answer.json()["code"]), (404, "not_found"), answer.content)
        tenancy.clear_tenant()
        self.assertIsNone(UserSession.objects.get(pk=console.session.pk).revoked_at)


class AnInvitationNamesNoAccountToTheBankThatSentIt(TestCase):
    def test_the_inviting_banks_trail_names_the_mailbox_and_the_refusal_goes_to_the_platform(self) -> None:
        """Review 2026-11-11 L-2: inviting an address that already has an account (here a
        member of another bank, with a passkey) shows the inviting bank the mailbox name and
        no account id, and the code refused to the enrolled address is logged outside it."""
        MockMailer.reset()
        cache.clear()
        bank_a, bank_b = factories.tenant(slug="inviting"), factories.tenant(slug="home")
        admin = factories.member(bank_a, roles=("admin",)).user
        person = factories.member(bank_b, user_row=factories.user(email="eva.holm@home.example", name="Eva Holm")).user
        factories.passkey(person)
        answer = self.client.post(
            "/api/v1/tenant/members",
            data={"email": "eva.holm@home.example", "roleKeys": ["reader"]},
            content_type="application/json",
            **sign_in(admin, tenant=bank_a, step_up=True),
        )
        self.assertEqual(answer.status_code, 201, answer.content)
        self.assertEqual(self.client.post("/api/v1/auth/invitations/open", data={"token": _found(LINK, MockMailer.sent[-1].body)}, content_type="application/json").status_code, 202)
        tenancy.activate(bank_a.id)
        rows = list(AuditEvent.objects.filter(tenant=bank_a, subject_type="invitation"))
        self.assertEqual({row.action for row in rows}, {"invitation.created", "invitation.opened"})
        for row in rows:
            self.assertEqual(row.subject_title, "eva.holm")
            self.assertNotIn(str(person.id), str(row.after))
            self.assertNotIn("Eva Holm", f"{row.summary} {row.after}")
        self.assertFalse(LoginEvent.objects.filter(tenant=bank_a, user=person).exists())
        tenancy.clear_tenant()
        refused = LoginEvent.objects.get(user=person, event=LoginEventKind.CODE_REFUSED_ENROLLED.value)
        self.assertIsNone(refused.tenant_id)


class TheAddressPathChoosesItsInvitationByAFixedRule(TestCase):
    def test_a_re_enrolment_or_platform_invitation_first_then_the_oldest_bank_invitation(self) -> None:
        """Review 2026-11-11 L-3: "First time here?" never enrols into whichever bank invited
        the address last."""
        email = "two-invites@review.example"
        older, newer = factories.tenant(slug="older"), factories.tenant(slug="newer")
        first = factories.invitation(older, email=email)
        factories.invitation(newer, email=email)
        tenancy.clear_tenant()
        chosen = invitation_logic.find_open_for_email(email)
        self.assertEqual(chosen.pk if chosen else None, first.pk)
        reenrolment = factories.invitation(newer, email=email, kind=InvitationKind.REENROLMENT)
        tenancy.clear_tenant()
        chosen = invitation_logic.find_open_for_email(email)
        self.assertEqual(chosen.pk if chosen else None, reenrolment.pk)


class TheCookieRoutesAreBoundedAndOwnTheirOrigin(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.tenant = factories.tenant()
        self.person = factories.member(self.tenant).user

    def _bundle(self) -> session_logic.SessionBundle:
        tenancy.activate(self.tenant.id)
        return session_logic.create_session(user=self.person, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None)

    def _refresh(self, value: str, **headers: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post("/api/v1/auth/refresh", HTTP_COOKIE=f"{session_logic.refresh_cookie_name()}={value}", **headers)

    def test_the_refresh_cookie_carries_the_secure_prefix_and_its_flags(self) -> None:
        """Review 2026-11-11 L-5: `__Secure-` wherever the cookie is Secure, path and
        SameSite unchanged; the plain name only where the cookie cannot be Secure."""
        answer = self._refresh(self._bundle().refresh_value)
        self.assertEqual(answer.status_code, 200, answer.content)
        cookie = answer.cookies["__Secure-cw_refresh"]
        self.assertEqual((cookie["path"], cookie["samesite"], bool(cookie["secure"]), bool(cookie["httponly"])), ("/api/v1/auth", "Strict", True, True))
        with self.settings(REFRESH_COOKIE_SECURE=False):
            self.assertEqual(session_logic.refresh_cookie_name(), "cw_refresh")

    def test_a_foreign_origin_is_refused_on_refresh_and_sign_out(self) -> None:
        """Review 2026-11-11 L-5: an `Origin` the API does not serve answers 403
        `origin_refused` and changes nothing; the app's own origin, or none, goes through."""
        bundle = self._bundle()
        foreign: dict[str, Any] = {"HTTP_ORIGIN": "https://evil.example"}
        refused = self._refresh(bundle.refresh_value, **foreign)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "origin_refused"))
        out = self.client.post("/api/v1/auth/sign-out", HTTP_COOKIE=f"{session_logic.refresh_cookie_name()}={bundle.refresh_value}", **foreign)
        self.assertEqual((out.status_code, out.json()["code"]), (403, "origin_refused"))
        tenancy.activate(self.tenant.id)
        self.assertIsNone(UserSession.objects.get(pk=bundle.session.pk).revoked_at)
        own = self._refresh(bundle.refresh_value, HTTP_ORIGIN=settings.CORS_ALLOWED_ORIGINS[0])
        self.assertEqual(own.status_code, 200, own.content)

    def test_a_sign_out_with_no_cookie_writes_nothing(self) -> None:
        """Review 2026-11-11 L-4: a sign-out presenting no cookie at all is a no-op, so it
        cannot fill the audit trail; a stale cookie is still recorded."""
        before = AuditEvent.objects.count()
        self.assertEqual(self.client.post("/api/v1/auth/sign-out").status_code, 204)
        self.assertEqual(AuditEvent.objects.count(), before)
        stale = self.client.post("/api/v1/auth/sign-out", HTTP_COOKIE=f"{session_logic.refresh_cookie_name()}=not-a-token")
        self.assertEqual(stale.status_code, 204)
        self.assertTrue(AuditEvent.objects.filter(action="session.sign_out_without_session").exists())

    def test_refresh_and_sign_out_are_rate_limited_per_address(self) -> None:
        """Review 2026-11-11 L-4: the per-address auth limit applies to both cookie routes."""
        with self.settings(RATE_LIMITING_ENABLED=True, E2E_MODE=False, AUTH_RATE_PER_IP_PER_MINUTE=2):
            cache.clear()
            for _ in range(2):
                self.assertEqual(self.client.post("/api/v1/auth/sign-out").status_code, 204)
            limited = self.client.post("/api/v1/auth/refresh")
            self.assertEqual((limited.status_code, limited.json()["code"]), (429, "rate_limited"))


class ReadThenWriteSequencesHappenOnce(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.person = factories.member(self.tenant).user
        tenancy.activate(self.tenant.id)
        self.bundle = session_logic.create_session(user=self.person, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None)

    def test_two_requests_ending_one_session_revoke_it_once(self) -> None:
        """Review 2026-11-11 L-6: the revocation is a conditional UPDATE, so a second copy of
        the row read before the first revocation writes nothing."""
        first, second = (UserSession.objects.select_related("user").get(pk=self.bundle.session.pk) for _ in range(2))
        actor = session_logic.actor_of(self.person)
        self.assertTrue(session_logic.revoke_session(first, reason="test", actor=actor))
        self.assertFalse(session_logic.revoke_session(second, reason="test", actor=actor))
        self.assertEqual(AuditEvent.objects.filter(action="session.revoked", subject_id=self.bundle.session.pk).count(), 1)

    def test_a_refresh_that_loses_the_race_is_the_replay_and_rotates_nothing(self) -> None:
        """Review 2026-11-11 L-6: two refreshes presenting one token give one rotation; the
        one whose conditional UPDATE finds the token already rotated is answered as the
        replay inside the grace window, with no refresh token of its own."""
        real_limits = session_logic.limits
        inner: list[tuple[str, int, str | None]] = []
        raced: list[bool] = []

        def racing_limits(tenant_id: Any) -> Any:
            if not raced:
                raced.append(True)
                inner.append(session_logic.refresh(self.bundle.refresh_value, None))  # the other tab, first to land
            return real_limits(tenant_id)

        with mock.patch.object(session_logic, "limits", side_effect=racing_limits):
            _, _, rotated = session_logic.refresh(self.bundle.refresh_value, None)
        self.assertIsNotNone(inner[0][2], "the first refresh rotated")
        self.assertIsNone(rotated, "the second is the replay")
        tenancy.activate(self.tenant.id)
        self.assertEqual(AuditEvent.objects.filter(action="session.refreshed", summary="Refresh token rotated.").count(), 1)
        self.assertIsNone(UserSession.objects.get(pk=self.bundle.session.pk).revoked_at)

    def test_one_step_up_serves_one_context_switch(self) -> None:
        """Review 2026-11-11 L-6: the switch ends the session its step-up was made on with a
        conditional UPDATE, so the same assertion cannot start a second session."""
        factories.platform_user(roles=("library_editor",), email="dual@review.example")
        dual = User.objects.get(email="dual@review.example")
        factories.member(self.tenant, user_row=dual)
        tenancy.activate(self.tenant.id)
        bundle = session_logic.create_session(user=dual, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None)
        principal = session_logic.resolve_access_token(bundle.access_token, want=PrincipalKind.USER)
        assert principal is not None
        request = RequestFactory().post("/api/v1/me/context")
        assertion = uuid.uuid4()
        session_logic.switch_context(principal=principal, tenant_id=None, step_up_assertion_id=assertion, request=request)
        tenancy.activate(self.tenant.id)
        with self.assertRaises(ValidationError) as refused:
            session_logic.switch_context(principal=principal, tenant_id=None, step_up_assertion_id=assertion, request=request)
        self.assertEqual(refused.exception.code, "unauthenticated")
        tenancy.clear_tenant()
        self.assertEqual(UserSession.objects.filter(user=dual, tenant__isnull=True).count(), 1)
