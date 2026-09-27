"""Scenario tests for the tenants app (playbook 4.1, Appendix B): one method per
`@integration` scenario in app.md, each carrying its ID. Chunk 1 un-skips TEN-S1, ADM-S1
and ADM-S3; TEN-S2 to S6 stay skipped (R2, chunk 8). Never delete a scenario without
updating app.md.

Operations exercised (the audit-on-write guard reads these names): updateTenant,
setTenantAi (its branches in tests_organisation.py), putMyOutOfOffice (TEN-S4, its
refusals in tests_out_of_office.py),
consoleReissueEnrolment (proven in identity ID-S13).

Prefixes hosted: ADM, TEN.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest import mock, skip
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.cases import testing as case_build
from apps.cases import tests_signoff as signoff_build
from apps.cases.models import ChangeCase
from apps.collab import reminders
from apps.collab.models import Notification

from apps.identity.models import Membership, TenantRole
from apps.library.reading import today_for
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy import tenant_lists_logic
from apps.taxonomy.models import FootprintTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.watch import testing as watch_build


class TenantsScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.tenants, one method per @integration scenario."""

    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.admin = factories.member(self.tenant, roles=("admin",)).user

    def _member_with(self, *permissions: str) -> dict[str, Any]:
        """A member holding exactly `permissions`, through a custom role row (ID-09)."""
        self.activate(self.tenant)
        key = "-".join(p.replace(".", "-") for p in permissions)
        TenantRole.objects.get_or_create(tenant=self.tenant, key=key, defaults={"permissions": list(permissions)})
        return sign_in(factories.member(self.tenant, roles=(key,)).user, tenant=self.tenant)

    def test_ten_s1(self) -> None:
        """TEN-S1

        A tenant profile holds timezone, languages and the onboarding checklist (TEN-01).
        """
        headers = sign_in(self.admin, tenant=self.tenant)
        body = {"name": "Example Bank Oyj", "timezone": "Europe/Helsinki", "defaultLanguage": "fi", "contentLanguages": ["fi", "sv", "en"]}
        response = self.client.patch("/api/v1/tenant", data=body, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        read = self.client.get("/api/v1/tenant", **headers)
        self.assertEqual(read.status_code, 200)
        profile = read.json()
        self.assertEqual(profile["name"], "Example Bank Oyj")
        self.assertEqual(profile["timezone"], "Europe/Helsinki")
        self.assertEqual(profile["defaultLanguage"], {"key": "fi", "kind": None, "label": "Suomi"})
        self.assertEqual([lang["key"] for lang in profile["contentLanguages"]], ["fi", "sv", "en"])
        self.assertEqual(profile["status"], "active")
        steps = {step["key"]: step["done"] for step in profile["onboarding"]["steps"]}
        self.assertTrue(steps["profile"])
        for not_done in ("footprint", "members", "vocabularies", "passkey"):
            self.assertFalse(steps[not_done], not_done)
        self.assertEqual(profile["onboarding"]["stepsDone"], 1)
        # The keys are validated against the rows and the IANA database.
        bad_zone = self.client.patch("/api/v1/tenant", data={"timezone": "Mars/Olympus"}, content_type="application/json", **headers)
        self.assertEqual(bad_zone.status_code, 422)
        self.assertEqual(bad_zone.json()["code"], "unknown_key")
        bad_lang = self.client.patch("/api/v1/tenant", data={"contentLanguages": ["xx"]}, content_type="application/json", **headers)
        self.assertEqual(bad_lang.json()["code"], "unknown_key")
        # Any member reads the profile; only security.manage changes it.
        reader = sign_in(factories.member(self.tenant, roles=("reader",)).user, tenant=self.tenant)
        self.assertEqual(self.client.get("/api/v1/tenant", **reader).status_code, 200)
        denied = self.client.patch("/api/v1/tenant", data={"name": "x"}, content_type="application/json", **reader)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["requiredPermission"], perms.SECURITY_MANAGE)
        # Inviting a member and an admin enrolling a passkey tick their steps.
        self.client.post("/api/v1/tenant/members", data={"email": "new@bank.example", "roleKeys": ["reader"]}, content_type="application/json", **headers)
        factories.passkey(self.admin)
        steps = {step["key"]: step["done"] for step in self.client.get("/api/v1/tenant", **headers).json()["onboarding"]["steps"]}
        self.assertTrue(steps["members"])
        self.assertTrue(steps["passkey"])
        # A footprint term (chunk 2, FP-01) ticks the footprint step.
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.activate(self.tenant)
        FootprintTerm.objects.create(tenant=self.tenant, term=tenant_lists_logic.term_by_ref("service_type", "custody"))
        steps = {step["key"]: step["done"] for step in self.client.get("/api/v1/tenant", **headers).json()["onboarding"]["steps"]}
        self.assertTrue(steps["footprint"])
        self.assertFalse(steps["vocabularies"])

    @skip("pending: TEN-S2 (TEN-02, chunk 8)")
    def test_ten_s2(self) -> None:
        """TEN-S2

        Legal entities and products are scoped like obligations (TEN-02).
        Operations: `createOrgUnit`, `createLicence`, `createProduct`, `updateProduct`.
        """

    @skip("pending: TEN-S3 (TEN-03, chunk 8)")
    def test_ten_s3(self) -> None:
        """TEN-S3

        A team can own work and the ownership survives a member leaving (TEN-03).
        """

    def test_ten_s4(self) -> None:
        """TEN-S4

        An out-of-office delegate receives approvals and reminders (TEN-04, COL-02).
        Reworded to a sign-off request and a triage reminder (app.md).
        Operations: `putMyOutOfOffice`, `requestSignoff`, `approveSignoff`.
        """
        bank = signoff_build.Bank()
        tenant = bank.tenant
        absent = factories.member_user(tenant, roles=("compliance_officer", "approver"))
        delegate = factories.member_user(tenant, roles=("approver",))
        today = today_for(tenant)
        next_friday = today + datetime.timedelta(days=(4 - today.weekday()) % 7 or 7)
        # Given an approver who set out-of-office until next Friday with a delegate
        response = self.client.put(
            "/api/v1/me/out-of-office",
            data={"untilDate": next_friday.isoformat(), "delegateId": str(delegate.id)},
            content_type="application/json",
            **sign_in(absent, tenant=tenant),
        )
        self.assertEqual(response.status_code, 200, response.content)

        # When a sign-off request names that approver
        bank.ready_for_signoff(self.client)
        # Then the delegate is notified and the approver is not. The delegate holds
        # `cases.signoff` themself, so they are told once, on their own account (collab).
        self.activate(tenant)
        told = set(Notification.objects.filter(kind="signoff_requested").values_list("user_id", flat=True))
        self.assertIn(delegate.id, told)
        self.assertNotIn(absent.id, told)
        # And the approver's reminders reach the delegate too
        waiting = case_build.case(tenant, watch_build.change())
        with transaction.atomic():
            self.activate(tenant)
            ChangeCase.objects.filter(pk=waiting.pk).update(
                triage_due_at=datetime.datetime.combine(
                    today + datetime.timedelta(days=3), datetime.time(12), tzinfo=ZoneInfo(tenant.timezone)
                )
            )
            reminded = {(row.user_id, row.on_behalf_of_id) for row in reminders.send_triage_reminders(tenant)}
        self.assertIn((delegate.id, absent.id), reminded)
        self.assertNotIn(absent.id, {user_id for user_id, _ in reminded})
        # And may sign off, the audit event naming the delegate as actor and the approver as delegated
        response = bank.post(self.client, "approve", delegate, step_up=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.activate(tenant)
        approval = AuditEvent.objects.get(subject_id=bank.case.id, after__status="closed")
        self.assertEqual(approval.actor_id, delegate.id)
        self.assertEqual(approval.after["onBehalfOf"], [str(absent.id)])

        # When the window closes
        bank.case = case_build.case(tenant, watch_build.change(), owner=bank.owner)
        case_build.in_category(bank.case, CaseStatusCategory.IMPLEMENTING)
        the_day_after = datetime.datetime.combine(
            next_friday + datetime.timedelta(days=1), datetime.time(9), tzinfo=ZoneInfo(tenant.timezone)
        )
        with mock.patch("django.utils.timezone.now", return_value=the_day_after.astimezone(datetime.UTC)):
            bank.ready_for_signoff(self.client)
        # Then the approver receives requests again
        self.activate(tenant)
        told = set(Notification.objects.filter(kind="signoff_requested", subject_id=bank.case.id).values_list("user_id", flat=True))
        self.assertIn(absent.id, told)
        self.assertIn(delegate.id, told)

    @skip("pending: TEN-S5 (TEN-05, chunk 8)")
    def test_ten_s5(self) -> None:
        """TEN-S5

        Removing a member with open work offers bulk reassignment (TEN-05).
        Operations: `removeMember`.
        """

    @skip("pending: TEN-S6 (TEN-06, chunk 8)")
    def test_ten_s6(self) -> None:
        """TEN-S6

        Support access is requested by the platform, approved by the bank and time-boxed (TEN-06).
        Operations: `requestConsoleSupportAccess`, `approveSupportAccess`, `declineSupportAccess`,
        `revokeSupportAccess`, `enterConsoleSupportAccess`.
        """

    def test_adm_s1(self) -> None:
        """ADM-S1

        Tenant admin surfaces are gated by their own permissions (ADM-01, ADM-03).
        """
        members_only = self._member_with(perms.MEMBERS_MANAGE)
        self.assertEqual(self.client.get("/api/v1/tenant/members", **members_only).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/tenant/invitations", **members_only).status_code, 200)
        # The vocabulary write endpoint lands in chunk 2; every other admin surface of
        # chunk 1 names its own permission in the 403.
        expected = {
            ("POST", "/api/v1/tenant/roles"): perms.ROLES_MANAGE,
            ("GET", "/api/v1/tenant/api-keys"): perms.INTEGRATIONS_MANAGE,
            ("GET", "/api/v1/tenant/security-log"): perms.SECURITY_MANAGE,
            ("PATCH", "/api/v1/tenant"): perms.SECURITY_MANAGE,
        }
        # A well-formed body: Ninja validates the body before the view's permission gate
        # runs, so a malformed one would answer 422 and prove nothing about the gate.
        role_body = '{"key": "probe", "labels": {"en": "Probe"}, "permissions": ["cases.read"]}'
        for (method, url), permission in expected.items():
            with self.subTest(route=f"{method} {url}"):
                body = role_body if url.endswith("/roles") else "{}"
                response = self.client.generic(method, url, data=body, content_type="application/json", **members_only)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "permission_denied")
                self.assertEqual(response.json()["requiredPermission"], permission)
        me = self.client.get("/api/v1/me", **members_only).json()
        self.assertEqual(me["permissions"], [perms.MEMBERS_MANAGE], "the navigation derives from exactly these grants")

    def test_adm_s3(self) -> None:
        """ADM-S3

        User administration and business configuration can sit with different people (ADM-03).
        """
        people_admin = self._member_with(perms.MEMBERS_MANAGE, perms.ROLES_MANAGE)
        config_admin = self._member_with(perms.VOCAB_MANAGE, perms.WORKFLOW_MANAGE)
        self.assertEqual(sorted(self.client.get("/api/v1/me", **people_admin).json()["permissions"]), [perms.MEMBERS_MANAGE, perms.ROLES_MANAGE])
        self.assertEqual(sorted(self.client.get("/api/v1/me", **config_admin).json()["permissions"]), [perms.VOCAB_MANAGE, perms.WORKFLOW_MANAGE])
        self.assertEqual(self.client.get("/api/v1/tenant/members", **people_admin).status_code, 200)
        denied = self.client.get("/api/v1/tenant/members", **config_admin)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["requiredPermission"], perms.MEMBERS_MANAGE)
        denied = self.client.post(
            "/api/v1/tenant/roles",
            data={"key": "probe", "labels": {"en": "Probe"}, "permissions": ["cases.read"]},
            content_type="application/json",
            **config_admin,
        )
        self.assertEqual(denied.json()["requiredPermission"], perms.ROLES_MANAGE)
        # The business-configuration surfaces land with chunk 2; until then the people
        # admin holds neither grant, which is what keeps them off those screens.
        self.assertNotIn(perms.VOCAB_MANAGE, self.client.get("/api/v1/me", **people_admin).json()["permissions"])
        self.assertNotIn(perms.WORKFLOW_MANAGE, self.client.get("/api/v1/me", **people_admin).json()["permissions"])
        # The workflow policy (COL-02, updateTenantWorkflow) is the configuration admin's alone.
        denied = self.client.patch("/api/v1/tenant/workflow", data={"escalateAfterDays": 7}, content_type="application/json", **people_admin)
        self.assertEqual((denied.status_code, denied.json()["requiredPermission"]), (403, perms.WORKFLOW_MANAGE))
        allowed = self.client.patch("/api/v1/tenant/workflow", data={"escalateAfterDays": 7}, content_type="application/json", **config_admin)
        self.assertEqual((allowed.status_code, allowed.json()["workflow"]["escalateAfterDays"]), (200, 7))

    def test_ten_s8(self) -> None:
        """TEN-S8

        A department has a head and teams, and team membership is set on the member row (TEN-02, TEN-03).
        Operations: `createOrgUnit`, `updateOrgUnit`, `setMemberTeams`.

        c8-ten-teams-people: the department and its team are rows here, because adding them
        through `createOrgUnit` and `/vocab/team` is TEN-S2's and VOC-02's to prove; the
        database's refusal of another bank's member, department or head is proven as `cw_app`
        in tests_team_models.py and tests_models.py.
        """
        karin = factories.member(self.tenant, user_row=factories.user(name="Karin Holm")).user
        anna = factories.member(self.tenant, user_row=factories.user(name="Anna Berg")).user
        johan = factories.member(self.tenant, user_row=factories.user(name="Johan Ek")).user
        retail = factories.department(self.tenant, name="Retail Banking", head=karin)
        factories.team(self.tenant, key="retail-compliance", label="Retail compliance", org_unit=retail)

        me = self.client.get("/api/v1/me", **sign_in(karin, tenant=self.tenant)).json()
        self.assertIn({"id": str(retail.id), "name": "Retail Banking"}, me["headOf"])

        admin = sign_in(self.admin, tenant=self.tenant)
        for person in (anna, johan):
            url = f"/api/v1/tenant/members/{person.id}/teams"
            response = self.client.put(url, data={"teams": ["retail-compliance"]}, content_type="application/json", **admin)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["teams"], ["retail-compliance"])
            self.activate(self.tenant)
            membership = Membership.objects.get(tenant=self.tenant, user=person)
            event = AuditEvent.objects.get(action="member.teams_changed", subject_id=membership.id)
            self.assertEqual((event.before, event.after), ({"teams": []}, {"teams": ["retail-compliance"]}))
        members = self.client.get("/api/v1/tenant/teams/retail-compliance/members", **admin).json()
        self.assertEqual([row["name"] for row in members["items"]], ["Anna Berg", "Johan Ek"])

        other = factories.tenant(slug="elsewhere")
        stranger = factories.member_user(other)
        refused = self.client.put(
            f"/api/v1/tenant/members/{stranger.id}/teams", data={"teams": ["retail-compliance"]}, content_type="application/json", **admin
        )
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_member"))

        without = self._member_with(perms.CASES_READ)
        denied = self.client.put(
            f"/api/v1/tenant/members/{anna.id}/teams", data={"teams": []}, content_type="application/json", **without
        )
        self.assertEqual(denied.status_code, 403)

    @skip("pending: TEN-S9 (TEN-05, COL-04, chunk 8)")
    def test_ten_s9(self) -> None:
        """TEN-S9

        Removing a member ends their participations and team memberships (TEN-05, COL-04).
        """

    @skip("pending: TEN-S10 (TEN-02, chunk 8)")
    def test_ten_s10(self) -> None:
        """TEN-S10

        A legal entity records a certificate it holds (TEN-02, AC-TEN1).
        Operations: `createLicence`, `updateLicence`.
        """

    @skip("pending: TEN-S11 (TEN-06, chunk 8)")
    def test_ten_s11(self) -> None:
        """TEN-S11

        A support session reads and never writes, and never approves itself (TEN-06).
        """

    @skip("pending: TEN-S12 (REP-04, chunk 12)")
    def test_ten_s12(self) -> None:
        """TEN-S12

        A closing tenant refuses writes and still lets people sign in and export (REP-04).
        """
