"""Chunk 11's security review (docs/reviews/CHUNK11_REVIEW.md), finding F10, written before
its fix: a session is refreshed only when its access token has run out, so an idle limit no
longer than the access token's life signs out a person who is working, and a bank's limit
set that low is refused at the route and raised to the floor where it is read."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.identity import session_logic
from apps.identity.models import SessionKind
from apps.shared import factories, tenancy
from apps.shared.testing import sign_in
from apps.tenants.models import SecurityPolicy

URL = "/api/v1/tenant/security-policy"


@override_settings(ACCESS_TOKEN_TTL_MINUTES=10, SESSION_IDLE_MINUTES_MIN=15, SESSION_IDLE_MINUTES_DEFAULT=30)
class TheIdleLimitOutlivesTheAccessToken(TestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.admin = factories.member(self.tenant, roles=("admin",)).user

    def test_the_floor_is_above_the_access_tokens_life(self) -> None:
        self.assertGreater(settings.SESSION_IDLE_MINUTES_MIN, settings.ACCESS_TOKEN_TTL_MINUTES)

    def test_a_limit_below_the_floor_is_refused_and_nothing_changes(self) -> None:
        answer = self.client.put(
            URL,
            data={"sessionIdleMinutes": 5, "sessionAbsoluteHours": 8},
            content_type="application/json",
            **sign_in(self.admin, tenant=self.tenant, step_up=True),
        )
        self.assertEqual((answer.status_code, answer.json()["code"]), (422, "validation_error"), answer.content)
        self.assertEqual([error["field"] for error in answer.json()["errors"]], ["sessionIdleMinutes"])
        tenancy.activate(self.tenant.id)
        self.assertFalse(SecurityPolicy.objects.filter(tenant=self.tenant).exists())

    def test_the_floor_itself_is_accepted(self) -> None:
        answer = self.client.put(
            URL,
            data={"sessionIdleMinutes": 15, "sessionAbsoluteHours": 8},
            content_type="application/json",
            **sign_in(self.admin, tenant=self.tenant, step_up=True),
        )
        self.assertEqual(answer.status_code, 200, answer.content)

    def test_a_row_below_the_floor_is_read_as_the_floor_so_working_people_stay_signed_in(self) -> None:
        tenancy.activate(self.tenant.id)
        SecurityPolicy.objects.create(tenant=self.tenant, session_idle_minutes=5)
        self.assertEqual(session_logic.limits(self.tenant.id)[0], timedelta(minutes=15))
        bundle = session_logic.create_session(
            user=factories.member(self.tenant).user, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None
        )
        # A person working all along refreshes each time the access token runs out.
        value: str | None = bundle.refresh_value
        for minutes in (11, 22, 33):
            with mock.patch.object(timezone, "now", return_value=bundle.session.created_at + timedelta(minutes=minutes)):
                value = session_logic.refresh(value, None)[2]
            self.assertIsNotNone(value)
