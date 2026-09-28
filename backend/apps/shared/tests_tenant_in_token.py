"""The session's bank in its signed access token (perf-tenant-in-token, ADR 0063).

The resolver activates the bank the token signs and reads the session under it, so the
per-request path never opens the identity lookup. Each case of the ADR's threat model is
refused here: a forged claim (another key, or the real key naming another bank), a stale
token (the format before the claim, a bank struck out), a moved or removed membership, a
revoked session, a console session given a bank, a support session given another bank,
and an agent key presented where a session is wanted. A refusal of a claim that does not
match the stored session is logged to the security log and ends the session, and no
request is left in the claimed bank: a request never runs with a tenant other than its
session's.

Proven to fail 2026-09-28 in a scratch copy of the resolver. Without the
`session.tenant_id != claims.tenant_id` comparison, a console session with a bank's claim
resolved as a platform principal with that bank active, and its test named it (in every
other case row-level security hides the row). Without `_refuse_claim`, the eight tests of
a mismatched claim named the missing security-log row, the live session and the claimed
bank left active.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.identity import session_logic, tokens
from apps.identity.models import LoginEvent, LoginEventKind, Membership, SessionKind, UserSession
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared.authentication import PrincipalKind
from apps.shared.testing import sign_in
from apps.shared.tests_support_session import grant

V1 = "/api/v1"
MISMATCH = session_logic.TENANT_CLAIM_MISMATCH


def _session(headers: dict[str, Any]) -> UserSession:
    token = str(headers["HTTP_AUTHORIZATION"]).removeprefix("Bearer ")
    claims = tokens.parse_access_token(token, timezone.now())
    assert claims is not None
    with tenancy.identity_lookup():
        return UserSession.objects.get(pk=claims.session_id)


def _bearer(token: str) -> dict[str, Any]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class TenantInToken(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seed_languages()
        self.bank = factories.tenant(slug="claim-a")
        self.other = factories.tenant(slug="claim-b")
        self.person = factories.member_user(self.bank, roles=("admin",))
        factories.member(self.other, roles=("admin",))

    def forged(self, session: UserSession, tenant_id: Any) -> str:
        """What only a holder of the signing key could mint: the session, another bank."""
        token, _ = tokens.issue_access_token(session.id, session.kind, tenant_id, timezone.now())
        return token

    def refusals(self, session: UserSession) -> list[tuple[str, str, bool]]:
        with tenancy.identity_lookup():
            rows = LoginEvent.objects.filter(user_id=session.user_id, event=LoginEventKind.ACCESS_TOKEN_REFUSED.value)
            return [(row.failure_reason, str(row.tenant_id), row.success) for row in rows]

    def assert_refused_and_logged(self, session: UserSession, token: str, *, want: PrincipalKind = PrincipalKind.USER) -> None:
        self.assertIsNone(session_logic.resolve_access_token(token, want=want))
        # The claimed bank is left for the session's own zone: nothing after the refusal
        # runs in a bank that is not the session's.
        self.assertEqual(tenancy.database_tenant_id(), session.tenant_id)
        self.assertEqual(tenancy.active_tenant_id(), session.tenant_id)
        self.assertFalse(tenancy.identity_lookup_active())
        self.assertEqual(self.refusals(session), [(MISMATCH, str(session.tenant_id), False)])
        with tenancy.identity_lookup():
            ended = UserSession.objects.get(pk=session.id)
        self.assertEqual(ended.revoked_reason, MISMATCH)
        self.assertIsNotNone(ended.revoked_at)

    # --- The request's own path ---------------------------------------------------------------
    def test_a_request_runs_in_the_signed_bank_without_the_identity_lookup(self) -> None:
        headers = sign_in(self.person, tenant=self.bank)
        tenancy.activate(self.other.id)  # whatever the connection last had is not inherited
        with CaptureQueriesContext(connection) as queries:
            principal = session_logic.resolve_access_token(headers["HTTP_AUTHORIZATION"][7:], want=PrincipalKind.USER)
        assert principal is not None
        self.assertEqual((principal.tenant_id, principal.subject_id), (self.bank.id, self.person.id))
        self.assertEqual(tenancy.database_tenant_id(), self.bank.id)
        self.assertEqual(len(queries.captured_queries), 2, [query["sql"][:80] for query in queries.captured_queries])
        self.assertFalse(any(tenancy.IDENTITY_LOOKUP_SETTING in query["sql"] for query in queries.captured_queries))
        self.assertFalse(any("'on'" in query["sql"] for query in queries.captured_queries))

    def test_a_route_answers_in_the_sessions_bank(self) -> None:
        response = self.client.get(f"{V1}/me", **sign_in(self.person, tenant=self.bank))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(str(self.bank.id), response.content.decode())
        self.assertNotIn(str(self.other.id), response.content.decode())

    # --- Forged claims --------------------------------------------------------------------------
    def test_a_token_signed_with_another_key_is_refused(self) -> None:
        session = _session(sign_in(self.person, tenant=self.bank))
        with override_settings(SECRET_KEY="another-signing-key-that-is-not-the-servers"):
            token = self.forged(session, self.bank.id)
        self.assertIsNone(session_logic.resolve_access_token(token, want=PrincipalKind.USER))
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **_bearer(token)).status_code, 401)

    def test_a_signed_claim_of_another_bank_is_refused_logged_and_ends_the_session(self) -> None:
        session = _session(sign_in(self.person, tenant=self.bank))
        self.assert_refused_and_logged(session, self.forged(session, self.other.id))

    def test_the_refusal_answers_401_through_a_route_and_the_session_stays_ended(self) -> None:
        headers = sign_in(self.person, tenant=self.bank)
        session = _session(headers)
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **_bearer(self.forged(session, self.other.id))).status_code, 401)
        # The honest token of the same session no longer opens anything either.
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **headers).status_code, 401)
        self.assertEqual(self.refusals(session), [(MISMATCH, str(self.bank.id), False)])

    # --- Stale claims ---------------------------------------------------------------------------
    def test_a_token_from_before_the_claim_is_refused_and_the_refresh_reissues_one(self) -> None:
        headers = sign_in(self.person, tenant=self.bank)
        session = _session(headers)
        payload = f"v1.{session.id.hex}.full.{int(timezone.now().timestamp()) + 600}"
        stale = f"{payload}.{tokens._sign(payload)}"
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **_bearer(stale)).status_code, 401)
        self.assertEqual(self.refusals(session), [], "a token of the old format is refused, not a forgery")
        refreshed = self.client.post(f"{V1}/auth/refresh", HTTP_COOKIE=headers["HTTP_COOKIE"])
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        claims = tokens.parse_access_token(refreshed.json()["accessToken"], timezone.now())
        assert claims is not None
        self.assertEqual((claims.session_id, claims.tenant_id), (session.id, self.bank.id))

    def test_a_bank_struck_out_of_the_claim_is_refused_and_logged(self) -> None:
        session = _session(sign_in(self.person, tenant=self.bank))
        self.assert_refused_and_logged(session, self.forged(session, None))

    # --- Membership, revocation ---------------------------------------------------------------
    def test_a_removed_membership_is_refused(self) -> None:
        headers = sign_in(self.person, tenant=self.bank)
        tenancy.activate(self.bank.id)
        Membership.objects.filter(user=self.person, tenant=self.bank).update(deactivated_at=timezone.now())
        self.assertIsNone(session_logic.resolve_access_token(headers["HTTP_AUTHORIZATION"][7:], want=PrincipalKind.USER))
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **headers).status_code, 401)

    def test_a_moved_membership_opens_neither_bank_with_the_old_session(self) -> None:
        headers = sign_in(self.person, tenant=self.bank)
        session = _session(headers)
        tenancy.activate(self.bank.id)
        Membership.objects.filter(user=self.person, tenant=self.bank).update(deactivated_at=timezone.now())
        factories.member(self.other, roles=("admin",), user_row=self.person)
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **headers).status_code, 401)
        self.assert_refused_and_logged(session, self.forged(session, self.other.id))

    def test_a_revoked_session_is_refused_whatever_its_claim(self) -> None:
        headers = sign_in(self.person, tenant=self.bank)
        session = _session(headers)
        tenancy.activate(self.bank.id)
        UserSession.objects.filter(pk=session.id).update(revoked_at=timezone.now(), revoked_reason="sign_out")
        self.assertIsNone(session_logic.resolve_access_token(headers["HTTP_AUTHORIZATION"][7:], want=PrincipalKind.USER))
        self.assertIsNone(session_logic.resolve_access_token(self.forged(session, self.other.id), want=PrincipalKind.USER))
        self.assertEqual(tenancy.database_tenant_id(), self.bank.id)
        self.assertEqual(self.refusals(session), [(MISMATCH, str(self.bank.id), False)], "logged, though already ended")

    # --- The console, support and enrolment sessions ------------------------------------------
    def test_a_console_session_runs_in_no_bank_and_refuses_a_banks_claim(self) -> None:
        platform = factories.platform_user()
        headers = sign_in(platform, tenant=None)
        tenancy.activate(self.bank.id)
        principal = session_logic.resolve_access_token(headers["HTTP_AUTHORIZATION"][7:], want=PrincipalKind.USER)
        assert principal is not None
        self.assertEqual((principal.tenant_id, principal.is_platform_staff), (None, True))
        self.assertIsNone(tenancy.database_tenant_id())
        # The console row is readable from a bank (the mixed read), so the comparison refuses it.
        session = _session(headers)
        self.assert_refused_and_logged(session, self.forged(session, self.bank.id))

    def test_a_support_session_runs_in_its_bank_and_refuses_another(self) -> None:
        platform = factories.platform_user()
        row = grant(self.bank, platform, self.person)
        entered = self.client.post(f"{V1}/console/support-access/{row.id}/enter", **sign_in(platform, tenant=None, step_up=True))
        self.assertEqual(entered.status_code, 200, entered.content)
        token = entered.json()["accessToken"]
        principal = session_logic.resolve_access_token(token, want=PrincipalKind.USER)
        assert principal is not None
        self.assertEqual((principal.tenant_id, principal.support_access_id), (self.bank.id, row.id))
        self.assertEqual(tenancy.database_tenant_id(), self.bank.id)
        claims = tokens.parse_access_token(token, timezone.now())
        assert claims is not None
        with tenancy.identity_lookup():
            session = UserSession.objects.get(pk=claims.session_id)
        self.assertEqual(session.kind, SessionKind.SUPPORT.value)
        self.assert_refused_and_logged(session, self.forged(session, self.other.id))

    def test_an_enrolment_session_is_held_to_its_bank_too(self) -> None:
        newcomer = factories.user()
        headers = sign_in(newcomer, tenant=self.bank, kind="enrolment")
        self.assertIsNotNone(session_logic.resolve_access_token(headers["HTTP_AUTHORIZATION"][7:], want=PrincipalKind.ENROLMENT))
        session = _session(headers)
        self.assert_refused_and_logged(session, self.forged(session, self.other.id), want=PrincipalKind.ENROLMENT)

    # --- Agent keys -------------------------------------------------------------------------------
    def test_an_agent_key_is_no_session_and_a_session_token_is_no_key(self) -> None:
        key = factories.api_key(self.bank)
        self.assertIsNone(session_logic.resolve_access_token(key.plain_key, want=PrincipalKind.USER))
        self.assertEqual(self.client.get(f"{V1}/me", **_bearer(key.plain_key)).status_code, 401)
        token = sign_in(self.person, tenant=self.bank)["HTTP_AUTHORIZATION"][7:]
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=token).status_code, 401)
        # The key itself still resolves, through its own path, in its own bank.
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=key.plain_key).status_code, 200)
