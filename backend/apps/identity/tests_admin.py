"""The tenant admin and profile routes outside the scenarios (playbook 3 step 5): the
members list with its query count pinned, pagination limits, invitations (list, resend,
revoke), a member's sessions (list, revoke all), the roles list, retiring a role, the
permission catalogue, PATCH /me and the security log's paging. Operations exercised:
updateMe, resendInvitation, revokeInvitation, revokeMemberSessions, retireRole."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.test import override_settings

from apps.identity import session_logic
from apps.identity.models import Invitation, LoginEventKind, LoginMethod, SessionKind, TenantRole
from apps.identity.security_log import log_event
from apps.library.seeds import seed_languages
from apps.shared import factories, permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.testing import ScenarioTestCase, sign_in

# Queries per members list, measured 2026-09-19 and pinned so an N+1 shows up as a number
# (playbook 10): the request's savepoint pair (2), the auth layer (identity flag on, the
# session row, flag off, activate, membership permissions, platform roles, latest step-up:
# 7), the caller's user and tenant for the label order (2), the count and the page (2), the
# roles and labels prefetches (2), the test's own activation (1).
MEMBERS_LIST_QUERIES = 16


class MembersAndInvitations(ScenarioTestCase):
    def setUp(self) -> None:
        MockMailer.reset()
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.admin = factories.member(self.tenant, roles=("admin",), title="Administrator").user
        for n in range(5):
            factories.member(self.tenant, roles=("reader", "contributor"), user_row=factories.user(email=f"m{n}@bank.example"))
        self.headers = sign_in(self.admin, tenant=self.tenant)

    def test_the_members_list_is_paginated_and_pinned(self) -> None:
        with self.assertNumQueries(MEMBERS_LIST_QUERIES):
            response = self.client.get("/api/v1/tenant/members?limit=3", **self.headers)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["total"], 6)
        self.assertEqual(len(body["items"]), 3)
        first = body["items"][0]
        self.assertEqual(first["email"], self.admin.email)
        self.assertEqual(first["title"], "Administrator")
        self.assertEqual([r["key"] for r in first["roles"]], ["admin"])
        self.assertEqual(first["roles"][0]["label"], "Administrator")
        self.assertEqual(first["status"], "active")
        self.assertEqual(first["passkeyCount"], 0)
        self.assertEqual(first["activeSessions"], 1)
        second_page = self.client.get("/api/v1/tenant/members?limit=3&offset=3", **self.headers).json()
        self.assertEqual(len(second_page["items"]), 3)
        self.assertNotEqual(second_page["items"][0]["userId"], first["userId"])
        # Limits are settings: above the maximum is a 422, not a clamp.
        too_many = self.client.get(f"/api/v1/tenant/members?limit={settings.API_PAGE_SIZE_MAX + 1}", **self.headers)
        self.assertEqual(too_many.status_code, 422)
        self.assertEqual(too_many.json()["code"], "validation_error")
        default = self.client.get("/api/v1/tenant/members", **self.headers).json()
        self.assertEqual(len(default["items"]), min(6, settings.API_PAGE_SIZE_DEFAULT))

    def test_invitations_are_listed_resent_and_revoked(self) -> None:
        invited = self.client.post(
            "/api/v1/tenant/members",
            data={"email": "new@bank.example", "roleKeys": ["reader"], "title": "Analyst"},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(invited.status_code, 201, invited.content)
        invitation_id = invited.json()["id"]
        self.assertEqual(invited.json()["status"], "pending")
        self.assertEqual(invited.json()["title"], "Analyst")
        listed = self.client.get("/api/v1/tenant/invitations", **self.headers).json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["id"], invitation_id)
        self.assertEqual([r["key"] for r in listed["items"][0]["roles"]], ["reader"])
        self.activate(self.tenant)
        before = Invitation.objects.get(pk=invitation_id).token_hash
        resent = self.client.post(f"/api/v1/tenant/invitations/{invitation_id}/resend", **self.headers)
        self.assertEqual(resent.status_code, 200, resent.content)
        self.activate(self.tenant)
        self.assertNotEqual(Invitation.objects.get(pk=invitation_id).token_hash, before, "a new token")
        self.assertEqual([m.to for m in MockMailer.sent], ["new@bank.example", "new@bank.example"])
        revoked = self.client.delete(f"/api/v1/tenant/invitations/{invitation_id}", **self.headers)
        self.assertEqual(revoked.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/tenant/invitations", **self.headers).json()["items"][0]["status"], "revoked")
        closed = self.client.post(f"/api/v1/tenant/invitations/{invitation_id}/resend", **self.headers)
        self.assertEqual(closed.status_code, 409)
        self.assertEqual(closed.json()["code"], "invitation_closed")
        again = self.client.post("/api/v1/tenant/members", data={"email": self.admin.email, "roleKeys": ["reader"]}, content_type="application/json", **self.headers)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "already_member")
        unknown_role = self.client.post("/api/v1/tenant/members", data={"email": "x@bank.example", "roleKeys": ["nope"]}, content_type="application/json", **self.headers)
        self.assertEqual(unknown_role.json()["code"], "unknown_key")
        self.assertEqual(self.client.delete("/api/v1/tenant/invitations/00000000-0000-4000-8000-000000000001", **self.headers).status_code, 404)

    def test_an_admin_lists_and_revokes_a_members_sessions(self) -> None:
        member = factories.member(self.tenant, roles=("reader",)).user
        sign_in(member, tenant=self.tenant)
        sign_in(member, tenant=self.tenant)
        listed = self.client.get(f"/api/v1/tenant/members/{member.id}/sessions", **self.headers)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.json()), 2)
        self.assertFalse(any(s["current"] for s in listed.json()))
        revoked = self.client.delete(f"/api/v1/tenant/members/{member.id}/sessions", **self.headers)
        self.assertEqual(revoked.status_code, 204)
        self.assertEqual(self.client.get(f"/api/v1/tenant/members/{member.id}/sessions", **self.headers).json(), [])
        self.assertEqual(self.client.get(f"/api/v1/tenant/members/{self.tenant.id}/sessions", **self.headers).status_code, 404)
        gone = self.client.delete(f"/api/v1/tenant/members/{member.id}", **self.headers)
        self.assertEqual(gone.status_code, 204)
        self.assertEqual(self.client.get(f"/api/v1/tenant/members/{member.id}/sessions", **self.headers).status_code, 404)
        listed_members = self.client.get("/api/v1/tenant/members?limit=100", **self.headers).json()
        self.assertEqual(next(m["status"] for m in listed_members["items"] if m["userId"] == str(member.id)), "deactivated")


class RolesAndPermissions(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.headers = sign_in(self.admin, tenant=self.tenant, step_up=True)

    def test_roles_list_carries_labels_in_the_callers_language_and_retire_works(self) -> None:
        listed = self.client.get("/api/v1/tenant/roles", **self.headers)
        self.assertEqual(listed.status_code, 200)
        by_key = {role["key"]: role for role in listed.json()}
        self.assertEqual(by_key["reader"]["label"], "Reader")
        self.assertEqual(by_key["reader"]["labels"], {"en": "Reader", "sv": "Läsare"})
        self.assertTrue(by_key["reader"]["usageNote"])
        self.client.patch("/api/v1/me", data={"locale": "sv"}, content_type="application/json", **self.headers)
        listed = self.client.get("/api/v1/tenant/roles", **self.headers).json()
        self.assertEqual(next(r["label"] for r in listed if r["key"] == "reader"), "Läsare")
        created = self.client.post(
            "/api/v1/tenant/roles",
            data={"key": "Temp Role", "labels": {"en": "Temporary"}, "permissions": [perms.CASES_READ]},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["key"], "temp role")
        retired = self.client.post("/api/v1/tenant/roles/temp role/retire", **self.headers)
        self.assertEqual(retired.status_code, 200, retired.content)
        self.assertFalse(retired.json()["active"])
        self.assertNotIn("temp role", [r["key"] for r in self.client.get("/api/v1/tenant/roles", **self.headers).json()])
        duplicate = self.client.post("/api/v1/tenant/roles", data={"key": "READER", "labels": {"en": "x"}, "permissions": []}, content_type="application/json", **self.headers)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["code"], "duplicate_key")
        no_label = self.client.post("/api/v1/tenant/roles", data={"key": "bare", "labels": {}, "permissions": []}, content_type="application/json", **self.headers)
        self.assertEqual(no_label.json()["code"], "label_required")
        bad_language = self.client.post("/api/v1/tenant/roles", data={"key": "bare", "labels": {"xx": "x"}, "permissions": []}, content_type="application/json", **self.headers)
        self.assertEqual(bad_language.json()["code"], "unknown_key")
        self.assertEqual(self.client.post("/api/v1/tenant/roles/reader/retire", **self.headers).json()["code"], "system_role")
        self.assertEqual(self.client.post("/api/v1/tenant/roles/nope/retire", **self.headers).status_code, 404)
        self.activate(self.tenant)
        self.assertEqual(TenantRole.objects.filter(tenant=self.tenant, active=False).count(), 1)

    def test_the_permission_catalogue_lists_every_tenant_permission(self) -> None:
        response = self.client.get("/api/v1/reference/permissions", **self.headers)
        self.assertEqual(response.status_code, 200)
        keys = {item["key"] for item in response.json()}
        self.assertEqual(keys, set(perms.TENANT_PERMISSIONS))
        for item in response.json():
            self.assertEqual(item["group"], item["key"].split(".")[0])
            self.assertTrue(item["description"])


class MeAndSecurityLog(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.headers = sign_in(self.admin, tenant=self.tenant)

    def test_patch_me_changes_name_and_locale_and_validates(self) -> None:
        updated = self.client.patch("/api/v1/me", data={"name": "Erik H.", "locale": "sv"}, content_type="application/json", **self.headers)
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["user"]["name"], "Erik H.")
        self.assertEqual(updated.json()["user"]["locale"], "sv")
        self.assertEqual(self.client.patch("/api/v1/me", data={"name": " "}, content_type="application/json", **self.headers).json()["code"], "name_required")
        self.assertEqual(self.client.patch("/api/v1/me", data={"locale": "xx"}, content_type="application/json", **self.headers).json()["code"], "unknown_key")

    @override_settings(E2E_MODE=True)
    def test_the_security_log_pages_newest_first(self) -> None:
        member = factories.member(self.tenant, roles=("reader",)).user
        for _ in range(3):
            log_event(event=LoginEventKind.SIGNIN_FAILED, method=LoginMethod.PASSKEY, success=False, request=None, user=member, tenant_id=self.tenant.id, failure_reason="probe")
        page = self.client.get("/api/v1/tenant/security-log?limit=2", **self.headers)
        self.assertEqual(page.status_code, 200, page.content)
        body: dict[str, Any] = page.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertGreaterEqual(body["total"], 3)
        self.assertGreaterEqual(body["items"][0]["id"], body["items"][1]["id"], "newest first")
        self.assertEqual(body["items"][0]["failureReason"], "probe")

    def test_a_platform_session_has_no_tenant_routes(self) -> None:
        staff = factories.platform_user(roles=("library_editor",))
        headers = sign_in(staff, tenant=None)
        self.assertEqual(self.client.get("/api/v1/tenant", **headers).status_code, 404)
        me = self.client.get("/api/v1/me", **headers).json()
        self.assertEqual([r["key"] for r in me["platformRoles"]], ["library_editor"])
        self.assertEqual(me["platformRoles"][0]["label"], "Library editor")
        self.assertIn(perms.PROPOSALS_REVIEW, me["permissions"])
        bundle = session_logic.create_session(user=staff, kind=SessionKind.FULL, tenant_id=None, request=None)
        self.assertIsNone(bundle.session.tenant_id)


class LanguagesReference(ScenarioTestCase):
    def test_any_session_lists_the_language_rows(self) -> None:
        seed_languages()
        tenant = factories.tenant()
        headers = sign_in(factories.member(tenant).user, tenant=tenant)
        response = self.client.get("/api/v1/reference/languages", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["key"] for row in response.json()], ["da", "en", "fi", "nb", "sv"])
        self.assertEqual(response.json()[1], {"key": "en", "kind": None, "label": "English"})
        self.assertEqual(self.client.get("/api/v1/reference/languages").status_code, 401)
        enrolling = sign_in(factories.user(), tenant=tenant, kind="enrolment")
        self.assertEqual(self.client.get("/api/v1/reference/languages", **enrolling).json()["code"], "enrolment_only")
