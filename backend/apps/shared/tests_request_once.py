"""Resolve once per request (perf-request-once, 2026-09-28, PERF_AUDIT findings 1, 2, 5, 6).

What a request pays before its route runs is pinned: the bank the token signs activated, then
the session with its person, its bank, the membership's grants and the latest step-up in one
read (2, perf-tenant-in-token, ADR 0064). What the credential's read loaded is what
`caller_user`, `caller_tenant` and `language_order` answer with, at no query. A key is
resolved once per request, through MCP included; vocabulary labels are read once per read
request. And every saving still leaves each decision made on every request: a revoked
session, a removed membership, a revoked key and another bank's id are all still refused.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.client import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.identity import session_logic
from apps.identity.models import ApiKey, Membership, UserSession
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared.authentication import PrincipalKind
from apps.shared.middleware import _request_memo
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.http import caller_tenant, caller_user
from apps.taxonomy.models import Urgency, UrgencyLabel
from apps.taxonomy.reading import Labels, language_order
from apps.watch import testing as watch_build
from apps.shared.tests_support_session import grant

V1 = "/api/v1"
# A session request's cost before its route (the savepoint pair of the test's transaction
# aside): the signed bank activated, then the session with its person, its bank, the grants
# and the latest step-up in one read. Eight in all on 2026-09-28, six of them the auth
# layer's; four after wave A; now two (ADR 0064).
AUTH_QUERIES = 2
# GET /reference/languages: the savepoint pair, the auth layer and the route's one read.
LANGUAGES_QUERIES = 2 + AUTH_QUERIES + 1


def _token(headers: dict[str, Any]) -> str:
    return str(headers["HTTP_AUTHORIZATION"]).removeprefix("Bearer ")


class FixedCost(TestCase):
    """The plain client: the scenario client's audit count would add to every request's."""

    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="once-a")
        self.user = factories.member_user(self.tenant, roles=("admin",))

    def test_a_session_request_pays_two_queries_before_its_route(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        with self.assertNumQueries(LANGUAGES_QUERIES):
            response = self.client.get(f"{V1}/reference/languages", **headers)
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_lookup_ends_with_the_flag_off_and_the_session_bank_active(self) -> None:
        token = _token(sign_in(self.user, tenant=self.tenant))
        tenancy.clear_tenant()
        principal = session_logic.resolve_access_token(token, want=PrincipalKind.USER)
        assert principal is not None
        self.assertFalse(tenancy.identity_lookup_active())
        self.assertEqual(tenancy.database_tenant_id(), self.tenant.id)
        self.assertEqual(tenancy.active_tenant_id(), self.tenant.id)
        # What the read loaded rides on the principal.
        self.assertEqual((principal.user.id, principal.tenant.id), (self.user.id, self.tenant.id))

    def test_a_lookup_that_raises_switches_the_flag_off_and_enters_no_bank(self) -> None:
        tenancy.clear_tenant()
        with self.assertRaises(RuntimeError), tenancy.identity_lookup() as lookup:
            lookup.then_activate(self.tenant.id)
            raise RuntimeError("the credential's row was unreadable")
        self.assertFalse(tenancy.identity_lookup_active())
        self.assertIsNone(tenancy.database_tenant_id())

    def test_the_step_up_rides_on_the_grants_read(self) -> None:
        stepped = session_logic.resolve_access_token(_token(sign_in(self.user, tenant=self.tenant, step_up=True)), want=PrincipalKind.USER)
        plain = session_logic.resolve_access_token(_token(sign_in(self.user, tenant=self.tenant)), want=PrincipalKind.USER)
        assert stepped is not None and plain is not None
        self.assertIsNotNone(stepped.step_up_at)
        self.assertIsNotNone(stepped.step_up_assertion_id)
        self.assertIsNone(plain.step_up_at)
        # A step-up route still weighs it: refused without, answered with (createApiKey).
        body = json.dumps({"name": "Nightly sync", "scopes": ["library:read"]})
        refused = self.client.post(f"{V1}/tenant/api-keys", data=body, content_type="application/json", **sign_in(self.user, tenant=self.tenant))
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "step_up_required"))
        created = self.client.post(
            f"{V1}/tenant/api-keys", data=body, content_type="application/json", **sign_in(self.user, tenant=self.tenant, step_up=True)
        )
        self.assertEqual(created.status_code, 201, created.content)

    def test_the_caller_reads_cost_nothing_after_sign_in(self) -> None:
        principal = session_logic.resolve_access_token(_token(sign_in(self.user, tenant=self.tenant)), want=PrincipalKind.USER)
        request = RequestFactory().get("/")
        request.auth = principal  # type: ignore[attr-defined]
        with self.assertNumQueries(0):
            self.assertEqual(caller_user(request).id, self.user.id)
            self.assertEqual(caller_tenant(request).id, self.tenant.id)
            self.assertEqual(language_order(request)[-1], "en")


class StillRefused(ScenarioTestCase):
    """Every saving leaves every decision made on every request."""

    def setUp(self) -> None:
        cache.clear()
        seed_languages()
        self.tenant = factories.tenant(slug="once-refused-a")
        self.other = factories.tenant(slug="once-refused-b")
        self.user = factories.member_user(self.tenant, roles=("admin",))

    def test_a_revoked_session_is_refused_on_its_next_request(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/me", **headers).status_code, 200)
        self.activate(self.tenant)
        UserSession.objects.filter(user=self.user).update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(f"{V1}/me", **headers).status_code, 401)

    def test_a_removed_membership_is_refused_on_its_next_request(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **headers).status_code, 200)
        self.activate(self.tenant)
        Membership.objects.filter(user=self.user, tenant=self.tenant).update(deactivated_at=timezone.now())
        self.assertEqual(self.client.get(f"{V1}/reference/languages", **headers).status_code, 401)

    def test_another_banks_id_is_not_found(self) -> None:
        theirs = factories.org_unit(self.other, name="Their unit")
        headers = sign_in(self.user, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/tenant/org-units/{theirs.id}/licences", **headers).status_code, 404)

    def test_a_revoked_key_is_refused_on_its_next_request(self) -> None:
        key = factories.api_key(self.tenant)
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=key.plain_key).status_code, 200)
        self.activate(self.tenant)
        ApiKey.objects.filter(pk=key.id).update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=key.plain_key).status_code, 401)


class KeyResolvedOnce(TestCase):
    """The plain client: a search through MCP is a read that takes a body and writes no
    audit row, which the scenario client would refuse."""

    def setUp(self) -> None:
        cache.clear()
        seed_languages()
        self.tenant = factories.tenant(slug="once-key")
        entry = factories.agent_access_entry(self.tenant)
        self.key = factories.entry_key(self.tenant, entry, scopes=("library:read", "search:read"))

    def call(self) -> Any:
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "reporting"}}}
        return self.client.post(
            f"{V1}/mcp", data=json.dumps(message), content_type="application/json", HTTP_X_API_KEY=self.key.plain_key, HTTP_MCP_PROTOCOL_VERSION="2025-11-25"
        )

    def test_an_mcp_tool_call_reads_its_key_once_and_a_revoked_one_is_refused(self) -> None:
        with CaptureQueriesContext(connection) as queries:
            response = self.call()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("error", response.json())
        key_reads = [query for query in queries.captured_queries if query["sql"].startswith('SELECT "api_key".')]
        self.assertEqual(len(key_reads), 1, [query["sql"][:80] for query in key_reads])
        tenancy.activate(self.tenant.id)
        ApiKey.objects.filter(pk=self.key.id).update(revoked_at=timezone.now())
        self.assertEqual(self.call().status_code, 401)


class LabelsReadOncePerReadRequest(ScenarioTestCase):
    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        self.rows = list(Urgency.objects.all()[:3])
        self.assertTrue(self.rows, "the reference seeds hold the urgency levels")

    def test_a_read_request_reads_a_rows_labels_once(self) -> None:
        token = _request_memo.set({})
        try:
            with self.assertNumQueries(1):
                first = Labels.for_rows(UrgencyLabel, self.rows)
                again = Labels.for_rows(UrgencyLabel, self.rows)
        finally:
            _request_memo.reset(token)
        self.assertEqual([first.texts(row.id) for row in self.rows], [again.texts(row.id) for row in self.rows])
        self.assertTrue(any(first.texts(row.id) for row in self.rows))

    def test_outside_a_read_request_every_call_reads(self) -> None:
        with self.assertNumQueries(2):
            Labels.for_rows(UrgencyLabel, self.rows)
            Labels.for_rows(UrgencyLabel, self.rows)

    def test_the_memo_never_answers_for_another_bank(self) -> None:
        first, second = factories.tenant(slug="once-memo-a"), factories.tenant(slug="once-memo-b")
        token = _request_memo.set({})
        try:
            tenancy.activate(first.id)
            with self.assertNumQueries(1):
                Labels.for_rows(UrgencyLabel, self.rows)
            tenancy.activate(second.id)
            with self.assertNumQueries(1):
                Labels.for_rows(UrgencyLabel, self.rows)
        finally:
            _request_memo.reset(token)

    def test_a_write_request_keeps_no_memo(self) -> None:
        seen: list[Any] = []

        from apps.shared.middleware import RequestMemoMiddleware, request_memo

        def view(request: Any) -> Any:
            seen.append(request_memo())
            from django.http import HttpResponse

            return HttpResponse()

        middleware = RequestMemoMiddleware(view)
        middleware(RequestFactory().get("/"))
        middleware(RequestFactory().post("/"))
        self.assertEqual(seen, [{}, None])
        self.assertIsNone(request_memo())


class RefreshAnswersMe(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="once-refresh")
        self.user = factories.member_user(self.tenant, roles=("compliance_officer",))

    def test_a_refresh_answers_what_get_me_answers(self) -> None:
        headers = sign_in(self.user, tenant=self.tenant)
        refreshed = self.client.post(f"{V1}/auth/refresh", HTTP_COOKIE=headers["HTTP_COOKIE"])
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        body = refreshed.json()
        me = self.client.get(f"{V1}/me", HTTP_AUTHORIZATION=f"Bearer {body['accessToken']}")
        self.assertEqual(me.status_code, 200, me.content)
        self.assertEqual(body["me"], me.json())
        self.assertEqual(body["me"]["user"]["id"], str(self.user.id))

    def test_a_support_sessions_refresh_answers_no_me(self) -> None:
        platform = factories.platform_user()
        admin = factories.member_user(self.tenant, roles=("admin",))
        row = grant(self.tenant, platform, admin)
        entered = self.client.post(f"{V1}/console/support-access/{row.id}/enter", **sign_in(platform, tenant=None, step_up=True))
        self.assertEqual(entered.status_code, 200, entered.content)
        refreshed = self.client.post(f"{V1}/auth/refresh", HTTP_COOKIE=f"cw_refresh={entered.cookies['cw_refresh'].value}")
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        self.assertIsNone(refreshed.json()["me"])
