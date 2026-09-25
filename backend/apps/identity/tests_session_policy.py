"""A bank's session limits apply to its sessions (ID-08, ID-S17).

The idle and absolute limits come from the tenant's `SecurityPolicy` row, the platform
defaults stand in for a missing row or a blank field, and neither ever exceeds the
SESSION_*_MAX settings, even for a row written around the policy route's check. A limit
lowered while a session is live applies at its next refresh."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.identity import session_logic
from apps.identity.models import SessionKind
from apps.shared import factories, tenancy
from apps.tenants.models import SecurityPolicy


@override_settings(
    SESSION_IDLE_MINUTES_DEFAULT=30,
    SESSION_ABSOLUTE_HOURS_DEFAULT=12,
    SESSION_IDLE_MINUTES_MAX=480,
    SESSION_ABSOLUTE_HOURS_MAX=24,
)
class SessionPolicy(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.user = factories.member(self.tenant).user

    def _policy(self, *, idle: int | None = None, absolute: int | None = None) -> None:
        tenancy.activate(self.tenant.id)
        SecurityPolicy.objects.update_or_create(
            tenant=self.tenant, defaults={"session_idle_minutes": idle, "session_absolute_hours": absolute}
        )

    def _session(self) -> session_logic.SessionBundle:
        tenancy.activate(self.tenant.id)
        return session_logic.create_session(user=self.user, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None)

    def _refresh_at(self, bundle: session_logic.SessionBundle, after: timedelta, value: str | None = None) -> str | None:
        with mock.patch.object(timezone, "now", return_value=bundle.session.created_at + after):
            return session_logic.refresh(value or bundle.refresh_value, None)[2]

    def _cookie_max_age(self, value: str) -> int:
        response = HttpResponse()
        session_logic.set_refresh_cookie(response, value)
        return int(response.cookies[settings.REFRESH_COOKIE_NAME]["max-age"])

    def _assert_ends(self, bundle: session_logic.SessionBundle, after: timedelta, reason: str, value: str | None = None) -> None:
        with self.assertRaises(ValidationError) as caught:
            self._refresh_at(bundle, after, value)
        self.assertEqual(caught.exception.code, "unauthenticated")
        bundle.session.refresh_from_db()
        self.assertEqual(bundle.session.revoked_reason, reason)

    def test_without_a_policy_row_the_platform_defaults_apply(self) -> None:
        bundle = self._session()
        self.assertEqual(bundle.session.expires_at - bundle.session.last_seen_at, timedelta(hours=12))
        self.assertAlmostEqual(self._cookie_max_age(bundle.refresh_value), 12 * 3600, delta=5)
        self.assertIsNotNone(self._refresh_at(bundle, timedelta(minutes=29)))

    def test_a_blank_field_falls_back_to_its_default(self) -> None:
        self._policy(idle=None, absolute=6)
        bundle = self._session()
        self.assertEqual(bundle.session.expires_at - bundle.session.last_seen_at, timedelta(hours=6))
        self._assert_ends(bundle, timedelta(minutes=31), "idle")

    def test_the_policy_sets_the_absolute_limit_and_the_cookie_lifetime(self) -> None:
        self._policy(idle=15, absolute=8)
        bundle = self._session()
        self.assertEqual(bundle.session.expires_at - bundle.session.last_seen_at, timedelta(hours=8))
        self.assertAlmostEqual(self._cookie_max_age(bundle.refresh_value), 8 * 3600, delta=5)

    def test_the_policy_sets_the_idle_limit(self) -> None:
        self._policy(idle=15, absolute=8)
        bundle = self._session()
        rotated = self._refresh_at(bundle, timedelta(minutes=14))
        assert rotated is not None
        self._assert_ends(bundle, timedelta(minutes=14 + 16), "idle", rotated)

    def test_a_row_above_the_platform_maximum_is_capped(self) -> None:
        self._policy(idle=24 * 60, absolute=72)
        bundle = self._session()
        self.assertEqual(bundle.session.expires_at - bundle.session.last_seen_at, timedelta(hours=24))
        self._assert_ends(bundle, timedelta(minutes=481), "idle")

    def test_a_lowered_absolute_limit_applies_at_the_next_refresh(self) -> None:
        bundle = self._session()
        self._policy(absolute=2)
        new_value = self._refresh_at(bundle, timedelta(minutes=20))
        assert new_value is not None
        bundle.session.refresh_from_db()
        self.assertEqual(bundle.session.expires_at, bundle.session.created_at + timedelta(hours=2))
        with mock.patch.object(timezone, "now", return_value=bundle.session.created_at + timedelta(minutes=20)):
            self.assertAlmostEqual(self._cookie_max_age(new_value), 100 * 60, delta=5)
        self._policy(idle=120, absolute=1)
        with self.assertRaises(ValidationError):
            with mock.patch.object(timezone, "now", return_value=bundle.session.created_at + timedelta(minutes=70)):
                session_logic.refresh(new_value, None)
        bundle.session.refresh_from_db()
        self.assertEqual(bundle.session.revoked_reason, "absolute")

    def test_a_lowered_idle_limit_applies_at_the_next_refresh(self) -> None:
        bundle = self._session()
        self._policy(idle=10)
        self._assert_ends(bundle, timedelta(minutes=11), "idle")

    def test_a_raised_limit_never_extends_a_live_session(self) -> None:
        self._policy(absolute=2)
        bundle = self._session()
        signed_in_until = bundle.session.expires_at
        self._policy(absolute=20)
        self.assertIsNotNone(self._refresh_at(bundle, timedelta(minutes=20)))
        bundle.session.refresh_from_db()
        self.assertEqual(bundle.session.expires_at, signed_in_until)

    def test_another_banks_policy_does_not_reach_this_session(self) -> None:
        other = factories.tenant()
        tenancy.activate(other.id)
        SecurityPolicy.objects.create(tenant=other, session_idle_minutes=5, session_absolute_hours=1)
        bundle = self._session()
        self.assertEqual(bundle.session.expires_at - bundle.session.last_seen_at, timedelta(hours=12))
        self.assertIsNotNone(self._refresh_at(bundle, timedelta(minutes=20)))

    def test_a_platform_session_keeps_the_platform_defaults(self) -> None:
        self._policy(idle=5, absolute=1)
        staff = factories.user()
        tenancy.clear_tenant()
        bundle = session_logic.create_session(user=staff, kind=SessionKind.FULL, tenant_id=None, request=None)
        self.assertEqual(bundle.session.expires_at - bundle.session.last_seen_at, timedelta(hours=12))
