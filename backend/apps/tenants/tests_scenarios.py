"""Scenario tests for the tenants app (playbook 4.1, Appendix B): one method per
`@integration` scenario in app.md, each carrying its ID. Chunk 1 un-skips TEN-S1, ADM-S1
and ADM-S3; chunk 8 un-skips TEN-S6's grant halves (c8-ten-support-grants), and
c8-ten-organisation un-skips TEN-S2 and TEN-S10. Never delete a scenario without
updating app.md.

Operations exercised (the audit-on-write guard reads these names): updateTenant,
setTenantAi (its branches in tests_organisation.py),
consoleReissueEnrolment (proven in identity ID-S13), requestConsoleSupportAccess,
approveSupportAccess, declineSupportAccess, revokeSupportAccess.

Prefixes hosted: ADM, TEN.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest import skip

from apps.identity.models import Membership, TenantRole
from apps.library.models import Obligation
from apps.library.reading import today_for
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy import tenant_lists_logic
from apps.taxonomy.models import FootprintTerm, TaxonomyTerm, TermDimensionKind
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions


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

    def _seed_terms(self) -> None:
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()

    def test_ten_s2(self) -> None:
        """TEN-S2

        Legal entities and products are scoped like obligations (TEN-02).
        Operations: `createOrgUnit`, `createLicence`, `createProduct`, `updateProduct`.

        c8-ten-organisation. The register's line (a compliance status per entity) is the
        register's to prove once it holds one; here the entity is a unit whose id a register
        row points at, carrying its legal-entity term.
        """
        self._seed_terms()
        headers = self._member_with(perms.VOCAB_MANAGE)
        owner = factories.member_user(self.tenant)
        entity = self.client.post(
            "/api/v1/tenant/org-units", data={"kind": "legal_entity", "name": "Bank AB", "entityTerm": "bank"}, content_type="application/json", **headers
        )
        self.assertEqual(entity.status_code, 201, entity.content)
        unit_id = entity.json()["id"]
        today = today_for(self.tenant)
        licence = self.client.post(
            f"/api/v1/tenant/org-units/{unit_id}/licences",
            data={"licenceType": "bank", "reference": "FI 12-3456", "grantedOn": (today - timedelta(days=3650)).isoformat(), "serviceTerms": ["custody"]},
            content_type="application/json",
            **headers,
        )
        self.assertEqual(licence.status_code, 201, licence.content)
        product = self.client.post(
            "/api/v1/tenant/products", data={"name": "Custody", "orgUnitId": unit_id, "terms": ["custody", "retail"]}, content_type="application/json", **headers
        )
        self.assertEqual(product.status_code, 201, product.content)
        # Both carry terms of the dimensions obligations are scoped with: the dimensions are
        # read from the rows the registry serves, by kind, never from a list of keys here.
        scope_dimensions = set(
            REGISTRY["term_dimension"].model.objects.filter(kind__in=[TermDimensionKind.SCOPE.value, TermDimensionKind.OPT_IN.value]).values_list("key", flat=True)
        )
        carried = [entity.json()["entityTerm"]["key"], licence.json()["licenceType"]["key"]]
        carried += [term["key"] for term in licence.json()["serviceTerms"] + product.json()["terms"]]
        dimensions = set(TaxonomyTerm.objects.filter(key__in=carried).values_list("dimension__key", flat=True))
        self.assertLessEqual(dimensions, scope_dimensions)
        # A licence row may also hold a certificate with its validity, next audit and owner;
        # those carry no term.
        certificate = self.client.patch(
            f"/api/v1/tenant/licences/{licence.json()['id']}",
            data={"validUntil": (today + timedelta(days=365)).isoformat(), "nextAuditOn": (today + timedelta(days=90)).isoformat(), "ownerUserId": str(owner.id)},
            content_type="application/json",
            HTTP_IF_MATCH='"1"',
            **headers,
        )
        self.assertEqual(certificate.status_code, 200, certificate.content)
        self.assertEqual(certificate.json()["owner"]["id"], str(owner.id))
        self.assertEqual([term["key"] for term in certificate.json()["serviceTerms"]], ["custody"])
        # Retiring the product is a status; the row stays.
        retired = self.client.patch(
            f"/api/v1/tenant/products/{product.json()['id']}", data={"status": "retired"}, content_type="application/json", HTTP_IF_MATCH='"1"', **headers
        )
        self.assertEqual((retired.status_code, retired.json()["status"]), (200, "retired"))
        self.assertEqual([row["id"] for row in self.client.get("/api/v1/tenant/products", **headers).json()["items"]], [product.json()["id"]])

    @skip("pending: TEN-S3 (TEN-03, chunk 8)")
    def test_ten_s3(self) -> None:
        """TEN-S3

        A team can own work and the ownership survives a member leaving (TEN-03).
        """

    @skip("pending: TEN-S4 (TEN-04, chunk 8)")
    def test_ten_s4(self) -> None:
        """TEN-S4

        An out-of-office delegate receives approvals and reminders (TEN-04).
        """

    @skip("pending: TEN-S5 (TEN-05, chunk 8)")
    def test_ten_s5(self) -> None:
        """TEN-S5

        Removing a member with open work offers bulk reassignment (TEN-05).
        Operations: `removeMember`.
        """

    def test_ten_s6(self) -> None:
        """TEN-S6

        Support access is requested by the platform, approved by the bank and time-boxed (TEN-06).
        Operations: `requestConsoleSupportAccess`, `approveSupportAccess`, `declineSupportAccess`,
        `revokeSupportAccess`. The request, approve, decline and revoke halves are proven here;
        entering (`enterConsoleSupportAccess`), the logged reads, the 403 on a write and the 401
        after a revoke or the end of the window are pending: c8-support-access-mechanism adds
        them to this method.
        """
        MockMailer.reset()
        platform = factories.platform_user()
        console = sign_in(platform, tenant=None)
        bank = sign_in(self.admin, tenant=self.tenant, step_up=True)
        url = f"/api/v1/console/tenants/{self.tenant.id}/support-access"
        body = {"purpose": "The bank reports that its watch feed stopped updating.", "hours": 2}

        # Given a platform admin without any grant, the bank's reads answer 404.
        self.assertEqual(self.client.get("/api/v1/tenant/support-access", **console).status_code, 404)
        # They request two hours with a purpose: nothing is granted and security.manage hears.
        requested = self.client.post(url, data=body, content_type="application/json", **console)
        self.assertEqual(requested.status_code, 201, requested.content)
        self.assertEqual(requested.json()["state"], "pending")
        self.assertEqual(self.client.get("/api/v1/tenant/support-access", **console).status_code, 404)
        self.assertEqual([mail.to for mail in MockMailer.sent], [self.admin.email])
        grant = requested.json()["id"]

        # A tenant admin approves with a fresh step-up; the panel shows purpose, person and end.
        approved = self.client.post(f"/api/v1/tenant/support-access/{grant}/approve", **bank)
        self.assertEqual(approved.status_code, 200, approved.content)
        panel = self.client.get("/api/v1/tenant/support-access", **bank).json()["items"][0]
        self.assertEqual(panel["state"], "active")
        self.assertEqual(panel["purpose"], body["purpose"])
        self.assertEqual(panel["platformPerson"]["id"], str(platform.id))
        self.assertIsNotNone(panel["endsAt"])

        # pending: c8-support-access-mechanism enters here, proves each read lands in the
        # bank's audit log as support_access.read and that a write answers 403.

        # The tenant admin revokes it.
        revoked = self.client.post(f"/api/v1/tenant/support-access/{grant}/revoke", **bank)
        self.assertEqual(revoked.status_code, 200, revoked.content)
        self.assertEqual(revoked.json()["state"], "revoked")
        # pending: c8-support-access-mechanism, the next request 401, the ones after it 404.

        # And a second request the bank does not want is declined, granting nothing.
        second = self.client.post(url, data=body, content_type="application/json", **console).json()["id"]
        declined = self.client.post(f"/api/v1/tenant/support-access/{second}/decline", **bank)
        self.assertEqual(declined.json()["state"], "declined")
        self.assertEqual(self.client.post(f"/api/v1/tenant/support-access/{second}/approve", **bank).status_code, 422)

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

    def test_ten_s10(self) -> None:
        """TEN-S10

        A legal entity records a certificate it holds (TEN-02, AC-TEN1).
        Operations: `createLicence`, `updateLicence`.

        c8-ten-organisation. The entity screen's section is the organisation journey's; here
        the list that screen reads carries the row with its validity and next audit.
        """
        self._seed_terms()
        headers = self._member_with(perms.VOCAB_MANAGE)
        owner = factories.member_user(self.tenant)
        entity = self.client.post(
            "/api/v1/tenant/org-units", data={"kind": "legal_entity", "name": "Example Bank AB", "entityTerm": "bank"}, content_type="application/json", **headers
        ).json()
        self.activate(self.tenant)
        footprint = list(FootprintTerm.objects.filter(tenant=self.tenant).values_list("term_id", flat=True))
        obligations = Obligation.objects.count()
        today = today_for(self.tenant)
        dates = {
            "issuedOn": (today - timedelta(days=200)).isoformat(),
            "validUntil": (today + timedelta(days=895)).isoformat(),
            "nextAuditOn": (today + timedelta(days=165)).isoformat(),
        }
        created = self.client.post(
            f"/api/v1/tenant/org-units/{entity['id']}/licences",
            data={
                "licenceType": "iso_iec_27001",
                "issuer": "Example Certification AB",
                "number": "EC-2026-0142",
                "scopeStatement": "Information security management for payment services.",
                "ownerUserId": str(owner.id),
                **dates,
            },
            content_type="application/json",
            **headers,
        )
        self.assertEqual(created.status_code, 201, created.content)
        listed = self.client.get(f"/api/v1/tenant/org-units/{entity['id']}/licences", **headers).json()
        [row] = [row for row in listed["items"] if row["id"] == created.json()["id"]]
        self.assertEqual({key: row[key] for key in dates}, dates)
        self.assertEqual((row["issuer"], row["number"], row["owner"]["id"], row["withdrawnOn"]), ("Example Certification AB", "EC-2026-0142", str(owner.id), None))
        # The write is audited with before and after values, and nothing else moved.
        self.activate(self.tenant)
        [event] = AuditEvent.objects.filter(tenant=self.tenant, subject_id=row["id"])
        self.assertEqual((event.action, event.before), ("licence.created", {}))
        self.assertEqual({key: event.after[key] for key in dates}, dates)
        self.assertEqual(event.after["ownerUserId"], str(owner.id))
        self.assertEqual(list(FootprintTerm.objects.filter(tenant=self.tenant).values_list("term_id", flat=True)), footprint)
        self.assertEqual(Obligation.objects.count(), obligations)
        # A withdrawal date: the row reads as withdrawn and stays in the history.
        withdrawn_on = today.isoformat()
        withdrawn = self.client.patch(
            f"/api/v1/tenant/licences/{row['id']}", data={"withdrawnOn": withdrawn_on}, content_type="application/json", HTTP_IF_MATCH='"1"', **headers
        )
        self.assertEqual((withdrawn.status_code, withdrawn.json()["withdrawnOn"]), (200, withdrawn_on))
        listed = self.client.get(f"/api/v1/tenant/org-units/{entity['id']}/licences", **headers).json()
        self.assertEqual([(item["id"], item["withdrawnOn"]) for item in listed["items"]], [(row["id"], withdrawn_on)])
        self.activate(self.tenant)
        update = AuditEvent.objects.get(tenant=self.tenant, subject_id=row["id"], action="licence.updated")
        self.assertEqual((update.before, update.after), ({"withdrawnOn": None}, {"withdrawnOn": withdrawn_on, "rewritten": []}))

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
