"""The support session (TEN-06, D-49, ADR 0042, c8-support-session-guard): entering a bank
under a grant it approved, what the session holds, the 401 once the grant ends, the one audit
row each request writes, the platform person's window onto their own grants, and the AST
guards that keep the mechanism in its two modules.

The sweep over every route is apps/shared/tests_support_routes.py.
"""

from __future__ import annotations

import ast
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from django.utils import timezone

from apps.identity import session_logic
from apps.identity.models import SessionKind, UserSession
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.tenants import support_access
from apps.tenants.models import SupportAccess

APPS = Path(__file__).resolve().parent.parent


def grant(tenant: Any, platform: Any, approver: Any, *, status: str = "approved", hours: int = 2, started: Any = None) -> SupportAccess:
    """A grant of `tenant` to `platform`, decided by `approver` (a member of the bank)."""
    started = started or timezone.now()
    tenancy.activate(tenant.id)
    row = SupportAccess.objects.create(
        tenant=tenant,
        platform_user=platform,
        reason="The bank reports that its watch feed stopped updating.",
        hours=hours,
        status="requested",
        requested_at=started,
        request_expires_at=started + timedelta(hours=24),
    )
    if status == "requested":
        return row
    row.status = status
    if status == "approved":
        row.approved_by, row.started_at, row.expires_at = approver, started, started + timedelta(hours=hours)
        row.save(update_fields=["status", "approved_by", "started_at", "expires_at"])
    else:
        row.ended_by, row.ended_at = approver, started
        row.save(update_fields=["status", "ended_by", "ended_at"])
    return row


def platform_setting() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT coalesce(current_setting('app.platform_user_id', true), '')")
        return str(cursor.fetchone()[0])


class SupportSessionTests(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="bank-a")
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.platform = factories.platform_user()

    def enter(self, row: SupportAccess, *, step_up: bool = True) -> Any:
        return self.client.post(f"/api/v1/console/support-access/{row.id}/enter", **sign_in(self.platform, tenant=None, step_up=step_up))

    def support_headers(self, row: SupportAccess) -> dict[str, Any]:
        entered = self.enter(row)
        self.assertEqual(entered.status_code, 200, entered.content)
        return {"HTTP_AUTHORIZATION": f"Bearer {entered.json()['accessToken']}"}

    # --- Entering --------------------------------------------------------------------------
    def test_entering_replaces_the_console_session_with_one_ending_with_the_window(self) -> None:
        row = grant(self.tenant, self.platform, self.admin)
        console = sign_in(self.platform, tenant=None, step_up=True)
        entered = self.client.post(f"/api/v1/console/support-access/{row.id}/enter", **console)
        self.assertEqual(entered.status_code, 200, entered.content)
        self.assertEqual(entered.json()["sessionKind"], "support")
        self.assertIn("cw_refresh", entered.cookies)
        self.activate(self.tenant)
        session = UserSession.objects.get(user=self.platform, kind=SessionKind.SUPPORT.value)
        self.assertEqual((session.tenant_id, session.support_access_id, session.expires_at), (self.tenant.id, row.id, row.expires_at))
        entered_row = AuditEvent.objects.get(action="support_access.entered")
        self.assertEqual((entered_row.tenant_id, entered_row.subject_id), (self.tenant.id, row.id))
        self.assertIsNotNone(entered_row.step_up_assertion_id)
        # The console session is signed out: its token no longer opens anything.
        self.assertEqual(self.client.get("/api/v1/console/tenants", **console).status_code, 401)

    def test_entering_needs_a_step_up(self) -> None:
        response = self.enter(grant(self.tenant, self.platform, self.admin), step_up=False)
        self.assertEqual((response.status_code, response.json()["code"]), (403, "step_up_required"))

    def test_only_the_callers_own_open_grant_is_entered(self) -> None:
        other = factories.platform_user()
        for label, row in (
            ("another person's grant", grant(self.tenant, other, self.admin)),
            ("a pending request", grant(self.tenant, self.platform, self.admin, status="requested")),
            ("a declined request", grant(self.tenant, self.platform, self.admin, status="declined")),
            ("a revoked grant", grant(self.tenant, self.platform, self.admin, status="revoked")),
            ("a window that has passed", grant(self.tenant, self.platform, self.admin, started=timezone.now() - timedelta(hours=3))),
        ):
            with self.subTest(label):
                self.assertEqual(self.enter(row).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/console/support-access/{uuid.uuid4()}/enter", **sign_in(self.platform, step_up=True)).status_code, 404)

    def test_a_bank_session_cannot_enter(self) -> None:
        row = grant(self.tenant, self.platform, self.admin)
        response = self.client.post(f"/api/v1/console/support-access/{row.id}/enter", **sign_in(self.admin, tenant=self.tenant, step_up=True))
        self.assertEqual((response.status_code, response.json()["code"]), (403, "permission_denied"))

    # --- What the session holds -------------------------------------------------------------
    def test_the_principal_holds_the_seven_reads_and_nothing_else(self) -> None:
        self.assertEqual(
            session_logic.SUPPORT_PERMISSIONS,
            {perms.LIBRARY_READ, perms.WATCH_READ, perms.ROADMAP_READ, perms.REGISTER_READ, perms.CASES_READ, perms.REPORTS_READ, perms.AUDIT_READ},
        )
        row = grant(self.tenant, self.platform, self.admin)
        headers = self.support_headers(row)
        token = headers["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
        principal = session_logic.resolve_access_token(token, want=session_logic.PrincipalKind.USER)
        assert principal is not None
        self.assertEqual(principal.permissions, session_logic.SUPPORT_PERMISSIONS)
        self.assertEqual((principal.tenant_id, principal.support_access_id, principal.is_platform_staff), (self.tenant.id, row.id, False))
        self.assertIsNone(principal.step_up_at, "a support session never steps up")
        # Neither an enrolment route nor any other auth class takes the token as its own.
        self.assertIsNone(session_logic.resolve_access_token(token, want=session_logic.PrincipalKind.ENROLMENT))

    def test_the_database_keeps_a_support_session_on_a_grant_of_its_own_bank(self) -> None:
        other_bank = factories.tenant(slug="bank-b")
        other_admin = factories.member(other_bank, roles=("admin",)).user
        theirs = grant(other_bank, self.platform, other_admin)
        self.activate(self.tenant)
        now = timezone.now()
        for label, fields in (
            ("a support session with no grant", {"kind": SessionKind.SUPPORT.value, "tenant": self.tenant}),
            ("a full session naming a grant", {"kind": SessionKind.FULL.value, "tenant": other_bank, "support_access": theirs}),
            ("another bank's grant", {"kind": SessionKind.SUPPORT.value, "tenant": self.tenant, "support_access": theirs}),
        ):
            with self.subTest(label), self.assertRaises(IntegrityError), transaction.atomic():
                if fields["tenant"] == other_bank:
                    self.activate(other_bank)
                UserSession.objects.create(user=self.platform, refresh_token_hash=uuid.uuid4().hex, last_seen_at=now, expires_at=now, **fields)
            self.activate(self.tenant)

    # --- The grant ends ---------------------------------------------------------------------
    def test_a_revoked_expired_or_declined_grant_answers_401_on_the_next_request(self) -> None:
        row = grant(self.tenant, self.platform, self.admin)
        with override_settings(ACCESS_TOKEN_TTL_MINUTES=6 * 60):
            headers = self.support_headers(row)
        self.assertEqual(self.client.get("/api/v1/changes", **headers).status_code, 200)
        # The window passes: the token itself would still be good, the grant is not.
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(hours=2, seconds=1)):
            ended = self.client.get("/api/v1/changes", **headers)
        self.assertEqual((ended.status_code, ended.json()["code"]), (401, "support_access_ended"))
        # The bank revokes it.
        self.client.post(f"/api/v1/tenant/support-access/{row.id}/revoke", **sign_in(self.admin, tenant=self.tenant))
        ended = self.client.get("/api/v1/changes", **headers)
        self.assertEqual((ended.status_code, ended.json()["code"]), (401, "support_access_ended"))
        # A session standing on a grant that was declined, or that no longer loads, ends too.
        declined = grant(self.tenant, self.platform, self.admin, status="declined")
        self.activate(self.tenant)
        self.assertFalse(session_logic._grant_live(UserSession(tenant_id=self.tenant.id, support_access_id=declined.id)))
        self.assertIsNone(support_access.live_grant(tenant_id=self.tenant.id, grant_id=uuid.uuid4()))
        self.assertIsNone(support_access.live_grant(tenant_id=factories.tenant(slug="bank-c").id, grant_id=row.id))

    def test_a_refused_request_after_the_end_writes_no_read(self) -> None:
        row = grant(self.tenant, self.platform, self.admin)
        headers = self.support_headers(row)
        self.client.post(f"/api/v1/tenant/support-access/{row.id}/revoke", **sign_in(self.admin, tenant=self.tenant))
        self.client.get("/api/v1/changes", **headers)
        self.activate(self.tenant)
        self.assertFalse(AuditEvent.objects.filter(action="support_access.read").exists())

    def test_refreshing_never_extends_the_session_and_an_ended_grant_ends_it(self) -> None:
        row = grant(self.tenant, self.platform, self.admin)
        entered = self.enter(row)
        cookie = entered.cookies["cw_refresh"].value
        refreshed = self.client.post("/api/v1/auth/refresh", HTTP_COOKIE=f"cw_refresh={cookie}")
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        self.activate(self.tenant)
        session = UserSession.objects.get(support_access=row)
        self.assertEqual(session.expires_at, row.expires_at, "a refresh never moves the end past the window")
        self.client.post(f"/api/v1/tenant/support-access/{row.id}/revoke", **sign_in(self.admin, tenant=self.tenant))
        again = self.client.post("/api/v1/auth/refresh", HTTP_COOKIE=f"cw_refresh={refreshed.cookies['cw_refresh'].value}")
        self.assertEqual((again.status_code, again.json()["code"]), (401, "support_access_ended"))
        self.activate(self.tenant)
        session.refresh_from_db()
        self.assertEqual(session.revoked_reason, "support_access_ended")

    def test_the_session_signs_out(self) -> None:
        row = grant(self.tenant, self.platform, self.admin)
        entered = self.enter(row)
        headers: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {entered.json()['accessToken']}"}
        out = self.client.post("/api/v1/auth/sign-out", HTTP_COOKIE=f"cw_refresh={entered.cookies['cw_refresh'].value}", **headers)
        self.assertEqual(out.status_code, 204, out.content)
        self.assertEqual(self.client.get("/api/v1/changes", **headers).status_code, 401)

    # --- The log ----------------------------------------------------------------------------
    READ_KEYS = {"method", "route", "pathIds", "platformUserId"}

    def assert_clean_read(self, after: dict[str, Any]) -> None:
        """A read row holds who, the method, the route template and its path ids: nothing a
        caller typed beyond an id, and nothing the bank wrote."""
        self.assertEqual(set(after), self.READ_KEYS)
        self.assertNotIn("?", after["route"])
        for value in after["pathIds"].values():
            uuid.UUID(value)

    def test_each_request_writes_one_read_row_with_the_route_template_and_path_ids(self) -> None:
        """In the request's own transaction, through record(): a handler that refuses a
        request and rolls its transaction back (a 404 from `answers_problems`) takes the row
        with it, as it takes every other write."""
        row = grant(self.tenant, self.platform, self.admin)
        change_id = factories.case_change(self.tenant).id
        headers = self.support_headers(row)
        actions = self.client.get(f"/api/v1/changes/{change_id}?q=secret-question", **headers)
        self.assertEqual(actions.status_code, 200, actions.content)
        self.assertEqual(self.client.get("/api/v1/changes?q=secret-question", **headers).status_code, 200)
        self.activate(self.tenant)
        reads = list(AuditEvent.objects.filter(action="support_access.read").order_by("created", "id"))
        self.assertEqual(len(reads), 2, "one row per request")
        self.assertEqual([r.after["route"] for r in reads], ["/changes/{change_id}", "/changes"])
        self.assertEqual(reads[0].after["pathIds"], {"change_id": str(change_id)})
        for read in reads:
            self.assert_clean_read(read.after)
            self.assertEqual((read.tenant_id, read.subject_id, read.actor_id), (self.tenant.id, row.id, self.platform.id))
            self.assertNotIn("secret-question", str(read.after) + read.summary)

    def test_the_read_check_fails_on_a_planted_body(self) -> None:
        planted = {"method": "GET", "route": "/changes", "pathIds": {}, "platformUserId": str(self.platform.id), "body": "a note"}
        with self.assertRaises(AssertionError):
            self.assert_clean_read(planted)

    # --- The platform person's own grants ---------------------------------------------------
    def test_a_platform_session_sees_only_the_grants_naming_it_and_the_setting_ends_with_the_block(self) -> None:
        mine = grant(self.tenant, self.platform, self.admin)
        grant(self.tenant, factories.platform_user(), self.admin)
        tenancy.clear_tenant()
        principal = session_logic.Principal(
            kind=session_logic.PrincipalKind.USER, subject_id=self.platform.id, is_platform_staff=True, session_id=uuid.uuid4()
        )
        self.assertEqual(SupportAccess.objects.count(), 0, "outside a grant nothing exists")
        with session_logic.own_grants(principal):
            self.assertEqual(platform_setting(), str(self.platform.id))
            self.assertEqual(list(SupportAccess.objects.values_list("id", flat=True)), [mine.id])
        self.assertEqual(platform_setting(), "")
        with self.assertRaises(RuntimeError), session_logic.own_grants(principal):
            raise RuntimeError("the block fails")
        self.assertEqual(platform_setting(), "", "cleared on an error as well")

    def test_the_setting_is_empty_again_after_the_enter_request(self) -> None:
        self.support_headers(grant(self.tenant, self.platform, self.admin))
        self.assertEqual(platform_setting(), "")

    def test_a_bank_session_never_opens_the_window_and_reads_the_table_as_before(self) -> None:
        grant(self.tenant, self.platform, self.admin)
        grant(self.tenant, factories.platform_user(), self.admin)
        bank = session_logic.Principal(kind=session_logic.PrincipalKind.USER, subject_id=self.admin.id, tenant_id=self.tenant.id)
        with self.assertRaises(session_logic.ProblemError), session_logic.own_grants(bank):
            pass
        self.activate(self.tenant)
        self.assertEqual(SupportAccess.objects.count(), 2)


# --- AST guards -----------------------------------------------------------------------------
def production_sources() -> list[tuple[str, str]]:
    """Every production module as (`apps/<path>`, source); migrations and tests left out."""
    found = []
    for path in sorted(APPS.rglob("*.py")):
        rel = path.relative_to(APPS).as_posix()
        if "/migrations/" in rel or rel.split("/")[-1].startswith("tests_") or rel.endswith("/testing.py"):
            continue
        found.append((f"apps/{rel}", path.read_text(encoding="utf-8")))
    return found


def _scopes(module: str, source: str) -> list[tuple[str, ast.AST]]:
    tree = ast.parse(source)
    return [
        (f"{module}::{top.name}" if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else f"{module}::<module>", node)
        for top in tree.body
        for node in ast.walk(top)
    ]


def platform_setting_writers(sources: list[tuple[str, str]]) -> set[str]:
    """Where the name `app.platform_user_id` is written in production code."""
    return {
        scope
        for module, source in sources
        for scope, node in _scopes(module, source)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "app.platform_user_id" in node.value
    }


def support_session_minters(sources: list[tuple[str, str]]) -> set[str]:
    """Where a support session could be minted: the kind `SessionKind.SUPPORT`, or a call
    naming a grant by keyword (`support_access=` or `support_access_id=`) on a session row."""
    minters = set()
    for module, source in sources:
        for scope, node in _scopes(module, source):
            if isinstance(node, ast.Attribute) and node.attr == "SUPPORT" and isinstance(node.value, ast.Name) and node.value.id == "SessionKind":
                minters.add(scope)
            if isinstance(node, ast.Call) and any(kw.arg in {"support_access", "support_access_id"} for kw in node.keywords):
                minters.add(scope)
    return minters


def grant_loaders(sources: list[tuple[str, str]]) -> set[str]:
    """Where a `support_access` row is queried: `SupportAccess.objects`."""
    return {
        scope
        for module, source in sources
        for scope, node in _scopes(module, source)
        if isinstance(node, ast.Attribute) and node.attr == "objects" and isinstance(node.value, ast.Name) and node.value.id == "SupportAccess"
    }


def outside(found: set[str], allowed: set[str]) -> set[str]:
    return {scope for scope in found if scope not in allowed and scope.split("::")[0] not in allowed}


PLANTED = "apps/watch/planted.py"


class SupportSessionFenceTests(ScenarioTestCase):
    """Only `identity/session_logic.py` sets `app.platform_user_id` or mints a support
    session, and only `tenants/support_access.py` loads a grant, beside the two writers of a
    row that were there before (ADR 0042). Each guard fails on a planted violation."""

    SETTING_ALLOWED = {"apps/identity/session_logic.py::<module>"}
    MINTING_ALLOWED = {
        "apps/identity/session_logic.py",
        # The CHECK that keeps a support session on a grant names the kind.
        "apps/identity/models.py::UserSession",
    }
    LOADING_ALLOWED = {
        "apps/tenants/support_access.py",
        # Chunk 1's one-shot recovery writes its own write-level row (TEN-06, ID-05).
        "apps/tenants/logic.py::console_reissue_enrolment",
        # The test factory (apps/shared/factories.py), which the tenant-isolation guard calls.
        "apps/shared/factories.py::support_access",
    }

    def test_only_session_logic_names_the_platform_user_setting(self) -> None:
        self.assertEqual(outside(platform_setting_writers(production_sources()), self.SETTING_ALLOWED), set())
        planted = [(PLANTED, "def peek(cursor):\n    cursor.execute(\"SELECT set_config('app.platform_user_id', %s, true)\", ['x'])\n")]
        self.assertEqual(outside(platform_setting_writers(planted), self.SETTING_ALLOWED), {f"{PLANTED}::peek"})

    def test_only_session_logic_mints_a_support_session(self) -> None:
        self.assertEqual(outside(support_session_minters(production_sources()), self.MINTING_ALLOWED), set())
        planted = [(PLANTED, "def mint(grant):\n    return UserSession.objects.create(kind='support', support_access=grant)\n")]
        self.assertEqual(outside(support_session_minters(planted), self.MINTING_ALLOWED), {f"{PLANTED}::mint"})
        planted = [(PLANTED, "def kind():\n    return SessionKind.SUPPORT\n")]
        self.assertEqual(outside(support_session_minters(planted), self.MINTING_ALLOWED), {f"{PLANTED}::kind"})

    def test_only_support_access_loads_a_grant(self) -> None:
        self.assertEqual(outside(grant_loaders(production_sources()), self.LOADING_ALLOWED), set())
        planted = [(PLANTED, "def peek(grant_id):\n    return SupportAccess.objects.filter(pk=grant_id).first()\n")]
        self.assertEqual(outside(grant_loaders(planted), self.LOADING_ALLOWED), {f"{PLANTED}::peek"})
