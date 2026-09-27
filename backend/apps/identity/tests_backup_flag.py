"""The backup-eligibility flag of every assertion is held to the stored one (ID-07, ADR 0048
tranche 1, WebAuthn Level 3 section 6.1.3).

Backup eligibility is fixed when a passkey is created, so an assertion whose BE flag differs
from the one stored at registration is not the authenticator that registered: sign-in and
step-up refuse it with a security-log row, for every bank. Backup state (BS) may change over
a passkey's life, so each verified assertion refreshes it. The ceremonies run for real
through the software authenticator; no assertion blob reaches a log line, a security-log row
or the audit trail."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.core.cache import cache

from apps.identity import tokens
from apps.identity.models import LoginEvent, LoginEventKind, StepUpAssertion, TenantRole, User, UserSession, WebAuthnCredential
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.library.seeds import seed_languages
from apps.shared import factories, permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

REFUSED = "backup_eligibility_changed"
INVALID_FLAGS = "invalid_backup_flags"
# Every logger the settings configure: `apps` and `django` do not propagate to the root.
LOGGERS = ("", "apps", "django", "django.request")


@contextmanager
def captured_logs() -> Iterator[list[str]]:
    """Every line any configured logger emits at any level, formatted with its arguments."""
    lines: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(f"{record.getMessage()} {record.__dict__}")

    handler = Collect(level=logging.DEBUG)
    loggers = [logging.getLogger(name) for name in LOGGERS]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    try:
        yield lines
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.removeHandler(handler)
            logger.setLevel(level)


class BackupFlagTests(ScenarioTestCase):
    def setUp(self) -> None:
        cache.clear()
        seed_languages()
        # Two banks: the comparison holds for every bank, whatever its settings.
        self.banks = [factories.tenant(slug="bank-a"), factories.tenant(slug="bank-b")]
        self.members = [
            factories.member(bank, roles=("admin",), user_row=factories.user(email=f"admin@{bank.slug}.example", name=f"Admin {bank.slug}")).user
            for bank in self.banks
        ]

    # --- helpers --------------------------------------------------------------------------
    def _post(self, path: str, body: dict[str, Any] | None = None, headers: dict[str, Any] | None = None) -> Any:
        return self.client.post(f"/api/v1{path}", data=body or {}, content_type="application/json", **(headers or {}))

    def _passkey(self, user: User, *, eligible: bool) -> tuple[SoftwareAuthenticator, WebAuthnCredential]:
        """A stored passkey whose key the software authenticator holds, registered with the
        given backup eligibility and reporting the same flags until a test changes them."""
        authenticator = SoftwareAuthenticator()
        authenticator.user_handle = user.id.bytes
        authenticator.backup_eligible = eligible
        authenticator.backed_up = eligible
        row = factories.passkey(user, public_key=tokens.b64url(authenticator.cose_public_key()), credential_id=authenticator.credential_id_b64)
        row.device_type = "multi_device" if eligible else "single_device"
        row.backup_eligible = eligible
        row.backed_up = eligible
        row.save(update_fields=["device_type", "backup_eligible", "backed_up"])
        return authenticator, row

    def _sign_in(self, authenticator: SoftwareAuthenticator) -> tuple[Any, dict[str, Any]]:
        options = self._post("/auth/passkeys/authenticate/options")
        self.assertEqual(options.status_code, 200, options.content)
        credential = authenticator.assert_(options.json())
        return self._post("/auth/passkeys/authenticate/verify", {"credential": credential}), credential

    def _step_up(self, headers: dict[str, Any], authenticator: SoftwareAuthenticator) -> tuple[Any, dict[str, Any]]:
        options = self._post("/auth/step-up/options", headers=headers)
        self.assertEqual(options.status_code, 200, options.content)
        credential = authenticator.assert_(options.json())
        return self._post("/auth/step-up/verify", {"credential": credential}, headers), credential

    def _assert_no_blob_stored(self, credential: dict[str, Any], log_lines: list[str]) -> None:
        self.assertTrue(log_lines, "the capture saw the request's own log lines")
        blobs = [credential["response"][part] for part in ("authenticatorData", "signature", "clientDataJSON")]
        stored = [
            " ".join(str(value) for value in row)
            for row in LoginEvent.objects.values_list("failure_reason", "user_agent", "email")
        ] + [
            f"{row.summary} {row.subject_title} {row.before} {row.after}"
            for row in AuditEvent.objects.all()
        ]
        for blob in blobs:
            for text in stored + log_lines:
                self.assertNotIn(blob, text)

    # --- sign-in --------------------------------------------------------------------------
    def test_a_sign_in_whose_eligibility_flag_changed_is_refused_with_a_security_log_row_in_every_bank(self) -> None:
        for bank in self.banks:
            for stored_eligible in (True, False):
                with self.subTest(bank=bank.slug, stored_eligible=stored_eligible):
                    user = factories.member(bank, roles=("reader",)).user
                    authenticator, row = self._passkey(user, eligible=stored_eligible)
                    authenticator.backup_eligible = not stored_eligible
                    authenticator.backed_up = False
                    sessions = UserSession.objects.filter(user=user).count()
                    with captured_logs() as lines:
                        response, credential = self._sign_in(authenticator)
                    self.assertEqual(response.status_code, 401, response.content)
                    self.assertEqual(response.json()["code"], "signin_failed")
                    refused = LoginEvent.objects.filter(user=user, event=LoginEventKind.SIGNIN_FAILED.value, success=False).latest("id")
                    self.assertEqual(refused.failure_reason, REFUSED)
                    self.assertEqual(UserSession.objects.filter(user=user).count(), sessions, "no session opened")
                    row.refresh_from_db()
                    self.assertEqual((row.sign_count, row.backup_eligible, row.backed_up), (0, stored_eligible, stored_eligible), "nothing on the passkey moved")
                    self._assert_no_blob_stored(credential, lines)

    def test_backed_up_without_eligibility_is_a_refused_sign_in_not_an_error(self) -> None:
        user = self.members[0]
        authenticator, _ = self._passkey(user, eligible=False)
        authenticator.backed_up = True
        response, _ = self._sign_in(authenticator)
        self.assertEqual(response.status_code, 401, response.content)
        refused = LoginEvent.objects.filter(user=user, event=LoginEventKind.SIGNIN_FAILED.value).latest("id")
        self.assertEqual(refused.failure_reason, INVALID_FLAGS)

    def test_each_sign_in_refreshes_the_backup_state(self) -> None:
        user = self.members[1]
        authenticator, row = self._passkey(user, eligible=True)
        for backed_up in (False, True):
            with self.subTest(backed_up=backed_up):
                authenticator.backed_up = backed_up
                response, _ = self._sign_in(authenticator)
                self.assertEqual(response.status_code, 200, response.content)
                row.refresh_from_db()
                self.assertEqual((row.backup_eligible, row.backed_up), (True, backed_up))

    # --- step-up --------------------------------------------------------------------------
    def test_a_step_up_whose_eligibility_flag_changed_is_refused_and_the_action_stays_undone(self) -> None:
        for bank, user in zip(self.banks, self.members, strict=True):
            with self.subTest(bank=bank.slug):
                authenticator, row = self._passkey(user, eligible=True)
                headers = sign_in(user, tenant=bank)
                authenticator.backup_eligible = False
                authenticator.backed_up = False
                with captured_logs() as lines:
                    response, credential = self._step_up(headers, authenticator)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()["code"], "step_up_failed")
                self.activate(bank)
                refused = LoginEvent.objects.filter(user=user, event=LoginEventKind.STEP_UP_FAILED.value, success=False).latest("id")
                self.assertEqual((refused.failure_reason, refused.tenant_id), (REFUSED, bank.id))
                self.assertFalse(StepUpAssertion.objects.filter(credential=row).exists())
                self._assert_no_blob_stored(credential, lines)

                role = {"key": "backup_probe", "labels": {"en": "Probe", "sv": "Prov"}, "usageNote": "Probe.", "permissions": [perms.CASES_READ]}
                action = self._post("/tenant/roles", role, headers)
                self.assertEqual(action.status_code, 403, action.content)
                self.assertEqual(action.json()["code"], "step_up_required")
                self.activate(bank)
                self.assertFalse(TenantRole.objects.filter(tenant=bank, key="backup_probe").exists())

    def test_each_step_up_refreshes_the_backup_state(self) -> None:
        bank, user = self.banks[0], self.members[0]
        authenticator, row = self._passkey(user, eligible=True)
        headers = sign_in(user, tenant=bank)
        authenticator.backed_up = False
        response, _ = self._step_up(headers, authenticator)
        self.assertEqual(response.status_code, 200, response.content)
        row.refresh_from_db()
        self.assertEqual((row.backup_eligible, row.backed_up), (True, False))
