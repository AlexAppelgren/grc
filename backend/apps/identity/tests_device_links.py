"""Adding a device by its code (ID-04, D-135): the branches the scenario (ID-S40) does not
walk. The ceremony itself is proven there."""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.utils import timezone

from apps.identity import tokens
from apps.identity.models import DeviceLink, UserSession, UserStatus
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.shared import factories, tenancy
from apps.shared.testing import ScenarioTestCase, sign_in


class DeviceLinkTests(ScenarioTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.tenant = factories.tenant(slug="bank")
        self.person = factories.member(self.tenant, roles=("reader",)).user

    def _start(self) -> tuple[str, str]:
        tenancy.clear_tenant()
        started = self.client.post("/api/v1/auth/device-links", content_type="application/json")
        self.assertEqual(started.status_code, 201, started.content)
        return started.json()["secret"], started.json()["code"]

    def _approve(self, code: str) -> None:
        approved = self.client.post(
            "/api/v1/me/device-links/approve", {"code": code}, content_type="application/json", **sign_in(self.person, tenant=self.tenant, step_up=True)
        )
        self.assertEqual(approved.status_code, 200, approved.content)

    def _claim(self, secret: str) -> Any:
        tenancy.clear_tenant()
        return self.client.post("/api/v1/auth/device-links/claim", {"secret": secret}, content_type="application/json")

    def test_signing_the_approving_session_out_cancels_the_link(self) -> None:
        secret, code = self._start()
        self._approve(code)
        UserSession.objects.filter(user=self.person).update(revoked_at=timezone.now(), revoked_reason="signed_out_everywhere")
        refused = self._claim(secret)
        self.assertEqual(refused.status_code, 410, refused.content)
        self.assertIsNone(DeviceLink.objects.get().claimed_at)

    def test_a_person_closed_since_the_approval_gets_no_session(self) -> None:
        secret, code = self._start()
        self._approve(code)
        type(self.person).objects.filter(pk=self.person.pk).update(status=UserStatus.DEACTIVATED.value, deactivated_at=timezone.now())
        refused = self._claim(secret)
        self.assertEqual(refused.status_code, 410, refused.content)
        self.assertEqual(refused.json()["code"], "device_link_expired")
        self.assertIsNone(DeviceLink.objects.get().claimed_at)

    def test_codes_are_read_without_case_spaces_or_dashes(self) -> None:
        self.assertEqual(tokens.hash_device_link_code("k7mp q2-xd"), tokens.hash_device_link_code("K7MPQ2XD"))
        code = tokens.new_device_link_code()
        self.assertEqual(len(code), tokens.DEVICE_LINK_CODE_LENGTH)
        self.assertTrue(set(code) <= set(tokens.DEVICE_LINK_CODE_ALPHABET))

    def test_platform_staff_without_a_bank_land_in_the_console(self) -> None:
        staff = factories.platform_user(roles=("platform_admin",), email="ops@platform.example")
        secret, code = self._start()
        approved = self.client.post(
            "/api/v1/me/device-links/approve", {"code": code}, content_type="application/json", **sign_in(staff, step_up=True)
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        claimed = self._claim(secret)
        self.assertEqual(claimed.status_code, 200, claimed.content)
        bearer: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {claimed.json()['accessToken']}"}
        options = self.client.post("/api/v1/auth/passkeys/register/options", content_type="application/json", **bearer)
        self.assertEqual(options.status_code, 200, options.content)
        credential = SoftwareAuthenticator().register(options.json())
        registered = self.client.post("/api/v1/auth/passkeys/register/verify", {"credential": credential}, content_type="application/json", **bearer)
        self.assertEqual(registered.status_code, 201, registered.content)
        me = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {registered.json()['accessToken']}")
        self.assertEqual(me.status_code, 200, me.content)
        self.assertIsNone(me.json()["tenant"])
