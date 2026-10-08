"""Scenario tests for the tenants app (playbook 4.1, Appendix B): one method per
`@integration` scenario in app.md, each carrying its ID. Chunk 1 un-skips TEN-S1, ADM-S1
and ADM-S3; c8-ten-organisation un-skips TEN-S2 and TEN-S10, and c8-ten-support-grants TEN-S6's
grant halves. `c8-ten-reassignment` un-skips TEN-S5 and TEN-S9 and TEN-S3's register half;
their case halves are `c9-owner-team-and-reassign`'s. Never delete a scenario without
updating app.md.

Operations exercised (the audit-on-write guard reads these names): updateTenant,
setTenantAi (its branches in tests_organisation.py),
consoleReissueEnrolment (proven in identity ID-S13), requestConsoleSupportAccess,
approveSupportAccess, declineSupportAccess, revokeSupportAccess, enterConsoleSupportAccess, putMyOutOfOffice (TEN-S4, its
refusals in tests_out_of_office.py), startRegisterLookup and applyRegisterLookup (TEN-S13).

Prefixes hosted: ADM, TEN.
"""

from __future__ import annotations

import dataclasses
import datetime
from datetime import timedelta
from typing import Any
from unittest import mock, skip
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone

from apps.cases import testing as case_build
from apps.cases.models import Action, ChangeCase
from apps.collab.models import Participant
from apps.identity.models import Membership, TenantRole
from apps.library.models import Obligation
from apps.cases import tests_signoff as signoff_build
from apps.collab import reminders
from apps.collab.models import Notification
from apps.library import testing as library_build
from apps.library.reading import today_for
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register.models import TenantObligation
from apps.shared import factories, permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.adapters.registers import MockRegisters, RegisterLicence, RegisterUnavailable
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy import tenant_lists_logic
from apps.taxonomy.models import FootprintChangeRequest, FootprintTerm, TaxonomyTerm, TermDimensionKind
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants import reassignment, tasks
from apps.tenants.models import Licence, OrgUnit, OrgUnitKind, RegisterEntry, SupportAccess, TeamMember
from apps.tenants.tests_reassignment import owned_work
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

    def _erik(self) -> tuple[Any, Any, Any, Any]:
        """TEN-S9's Erik and the work he holds (tests_reassignment.owned_work), Anna who takes
        it over, and the admin's step-up headers."""
        officer = factories.member_user(self.tenant, roles=("compliance_officer",))
        erik = factories.member(self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Erik Dahl")).user
        anna = factories.member_user(self.tenant, roles=("compliance_officer",))
        return erik, anna, owned_work(self.tenant, erik, officer), sign_in(self.admin, tenant=self.tenant, step_up=True)

    def _cases(self, owner: Any, *, team: Any = None, count: int = 2) -> list[Any]:
        """`count` cases in assessment owned by `owner`, with `team` beside, each with an open
        action `owner` owns (c9-owner-team-and-reassign)."""
        cases = [case_build.case_on_a_new_change(self.tenant) for _ in range(count)]
        self.activate(self.tenant)
        ChangeCase.objects.filter(pk__in=[c.pk for c in cases]).update(status=CaseStatusCategory.ASSESSING.value, owner=owner, owner_team=team)
        for case in cases:
            Action.objects.create(tenant=self.tenant, case=case, title="Update the policy", owner=owner, due_date=case.created_at.date(), created_by=owner)
        return cases

    def _remove(self, erik: Any, owners: list[dict[str, Any]], headers: dict[str, Any]) -> Any:
        return self.client.post(
            f"/api/v1/tenant/members/{erik.id}/remove", data={"owners": owners}, content_type="application/json", **headers
        )

    def test_ten_s3(self) -> None:
        """TEN-S3

        A team can own work and the ownership survives a member leaving (TEN-03). The
        register half: the team "Cards" owns an entry and takes part in another, and neither
        moves when Erik, one of its members, is removed. The case half
        (`c9-owner-team-and-reassign`): "Cards" owns a case beside Anna, and the case
        still lists the team, with nothing to reassign on it, after Erik leaves.
        """
        erik, anna, work, headers = self._erik()
        [team_case] = self._cases(anna, team=work.cards, count=1)
        preview = self.client.get(f"/api/v1/tenant/members/{erik.id}/open-work", **headers).json()
        self.assertNotIn(str(work.team_owned.id), str(preview))
        self.assertNotIn("case", {row["kind"] for row in preview["items"]})
        owners = [{"kind": kind, "userId": str(anna.id)} for kind in ("register_entry", "register_entity", "gap", "internal_item")]
        self.assertEqual(self._remove(erik, owners, headers).status_code, 204)
        self.activate(self.tenant)
        entry = TenantObligation.objects.get(pk=work.team_owned.pk)
        self.assertEqual((entry.owner_team_id, entry.first_line_owner_id, entry.version), (work.cards.id, None, 1))
        self.assertIsNone(Participant.objects.get(pk=work.team_part.pk).removed_at)
        self.assertFalse(AuditEvent.objects.filter(subject_id=work.team_owned.id, action="register_entry.reassigned").exists())
        self.assertFalse(AuditEvent.objects.filter(subject_id=team_case.id).exclude(action="session.created").exists())
        page = self.client.get(f"/api/v1/changes/{team_case.change_id}", **sign_in(anna, tenant=self.tenant)).json()
        self.assertEqual((page["case"]["ownerTeam"]["key"], page["case"]["owner"]["id"]), ("cards", str(anna.id)))

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
            reminded = {(row.user_id, row.on_behalf_of_id) for row in reminders.send_reminders(tenant)}
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

    def test_ten_s5(self) -> None:
        """TEN-S5

        Removing a member with open work offers bulk reassignment (TEN-05). Erik owns register
        entries, an entity's row, a gap and an internal item, and two open cases with an
        action each (the case half, `c9-owner-team-and-reassign`).
        Operations: `getMemberOpenWork`, `removeMember`, `deactivateMember`.
        """
        erik, anna, work, headers = self._erik()
        cases = self._cases(erik)
        kinds = ("register_entry", "register_entity", "gap", "internal_item", "case", "action")
        preview = self.client.get(f"/api/v1/tenant/members/{erik.id}/open-work", **headers)
        self.assertEqual(preview.status_code, 200)
        owned = {row["kind"]: row["count"] for row in preview.json()["items"]}
        self.assertEqual({k: owned[k] for k in kinds}, {"register_entry": 3, "register_entity": 1, "gap": 1, "internal_item": 1, "case": 2, "action": 2})
        # Nothing changes until the admin confirms: the plain removal is refused with the counts.
        refused = self.client.delete(f"/api/v1/tenant/members/{erik.id}", **headers)
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "reassignment_required"))
        self.activate(self.tenant)
        self.assertEqual(TenantObligation.objects.filter(first_line_owner=erik).count(), 2)
        self.assertEqual(ChangeCase.objects.filter(owner=erik).count(), 2)
        self.assertIsNone(Membership.objects.get(user=erik).deactivated_at)

        owners = [{"kind": kind, "userId": str(anna.id)} for kind in kinds]
        self.assertEqual(self._remove(erik, owners, headers).status_code, 204)
        self.activate(self.tenant)
        self.assertEqual(reassignment.open_work_counts(self.tenant.id, erik.id), [])
        self.assertEqual(TenantObligation.objects.filter(first_line_owner=anna).count(), 2)
        self.assertEqual(set(ChangeCase.objects.filter(owner=anna).values_list("id", flat=True)), {c.id for c in cases})
        self.assertEqual(Action.objects.filter(case__in=cases, owner=anna).count(), 2)
        self.assertIsNotNone(Membership.objects.get(user=erik).deactivated_at)
        for action, count in (
            ("register_entry.reassigned", 3),
            ("register_entity.reassigned", 1),
            ("gap.reassigned", 1),
            ("internal_item.reassigned", 1),
            ("case.reassigned", 2),
            ("action.reassigned", 2),
            ("member.deactivated", 1),
        ):
            self.assertEqual(AuditEvent.objects.filter(action=action, tenant_id=self.tenant.id).count(), count, action)

    def test_ten_s6(self) -> None:
        """TEN-S6

        Support access is requested by the platform, approved by the bank and time-boxed (TEN-06).
        Operations: `requestConsoleSupportAccess`, `approveSupportAccess`, `declineSupportAccess`,
        `revokeSupportAccess`, `enterConsoleSupportAccess`: the request and the decisions
        (c8-ten-support-grants), then entering, the logged reads, the 403 on a write and the
        401 after a revoke and after the window (c8-support-session-guard).
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

        # The platform person enters with a fresh step-up; every read lands in the bank's audit
        # log as support_access.read, with the route and the platform user.
        support = self._enter(platform, grant)
        self.assertEqual(self.client.get("/api/v1/changes", **support).status_code, 200)
        self.activate(self.tenant)
        read = AuditEvent.objects.filter(action="support_access.read").get()
        self.assertEqual((read.actor_id, read.after["route"], read.after["platformUserId"]), (platform.id, "/changes", str(platform.id)))
        # A write under it answers 403 support_read_only.
        refused = self.client.patch("/api/v1/tenant/workflow", data={"escalateAfterDays": 7}, content_type="application/json", **support)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "support_read_only"))

        # The tenant admin revokes it.
        revoked = self.client.post(f"/api/v1/tenant/support-access/{grant}/revoke", **bank)
        self.assertEqual(revoked.status_code, 200, revoked.content)
        self.assertEqual(revoked.json()["state"], "revoked")
        # The next request answers 401, and the platform person's reads are 404 again.
        ended = self.client.get("/api/v1/changes", **support)
        self.assertEqual((ended.status_code, ended.json()["code"]), (401, "support_access_ended"))
        console = sign_in(platform, tenant=None)
        self.assertEqual(self.client.get("/api/v1/tenant/support-access", **console).status_code, 404)

        # A grant nobody revokes ends the same way when its two hours pass.
        third = self.client.post(url, data=body, content_type="application/json", **console).json()["id"]
        self.assertEqual(self.client.post(f"/api/v1/tenant/support-access/{third}/approve", **bank).status_code, 200)
        with override_settings(ACCESS_TOKEN_TTL_MINUTES=6 * 60):
            support = self._enter(platform, third)
        self.assertEqual(self.client.get("/api/v1/changes", **support).status_code, 200)
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(hours=2, minutes=1)):
            ended = self.client.get("/api/v1/changes", **support)
        self.assertEqual((ended.status_code, ended.json()["code"]), (401, "support_access_ended"))
        console = sign_in(platform, tenant=None)
        self.assertEqual(self.client.get("/api/v1/tenant/support-access", **console).status_code, 404)

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
        Operations: `createOrgUnit`, `updateOrgUnit`, `createVocabularyRow`, `updateVocabularyRow`, `setMemberTeams`.

        The department is added through `createOrgUnit` and the team put in it, moved and taken
        out through the team list's own routes with `extra.orgUnitId` (`ten02-team-department`);
        the database's refusal of another bank's member, department or head is proven as
        `cw_app` in tests_team_models.py and tests_models.py.
        """
        karin = factories.member(self.tenant, user_row=factories.user(name="Karin Holm")).user
        anna = factories.member(self.tenant, user_row=factories.user(name="Anna Berg")).user
        johan = factories.member(self.tenant, user_row=factories.user(name="Johan Ek")).user
        admin = sign_in(self.admin, tenant=self.tenant)

        def write(method: str, url: str, body: dict[str, Any], **headers: str) -> Any:
            call = getattr(self.client, method)
            return call(f"/api/v1{url}", data=body, content_type="application/json", **admin, **headers)

        def department(key: str) -> Any:
            teams = self.client.get("/api/v1/tenant/teams", **admin).json()["items"]
            return next(row["orgUnitId"] for row in teams if row["key"] == key)

        added = write("post", "/tenant/org-units", {"kind": "business_area", "name": "Retail Banking", "headUserId": str(karin.id)})
        self.assertEqual(added.status_code, 201, added.content)
        retail = added.json()["id"]
        cards = write("post", "/tenant/org-units", {"kind": "function", "name": "Cards"}).json()["id"]
        team = write("post", "/vocab/team", {"labels": {"en": "Retail compliance"}, "key": "retail_compliance", "extra": {"orgUnitId": retail}})
        self.assertEqual(team.status_code, 201, team.content)

        me = self.client.get("/api/v1/me", **sign_in(karin, tenant=self.tenant)).json()
        self.assertIn({"id": retail, "name": "Retail Banking"}, me["headOf"])
        self.assertEqual(department("retail_compliance"), retail)
        self.activate(self.tenant)
        created = AuditEvent.objects.get(action="vocabulary.created", subject_title="team:retail_compliance")
        self.assertEqual(created.after["extra"]["orgUnitId"], retail)

        moved = write("patch", "/vocab/team/retail_compliance", {"extra": {"orgUnitId": cards}}, HTTP_IF_MATCH=f'"{team.json()["version"]}"')
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(department("retail_compliance"), cards)
        self.activate(self.tenant)
        [event] = AuditEvent.objects.filter(action="vocabulary.updated", subject_title="team:retail_compliance")
        self.assertEqual((event.before["extra"]["orgUnitId"], event.after["extra"]["orgUnitId"]), (retail, cards))

        stale = write("patch", "/vocab/team/retail_compliance", {"extra": {"orgUnitId": retail}}, HTTP_IF_MATCH=f'"{team.json()["version"]}"')
        self.assertEqual((stale.status_code, stale.json()["code"]), (409, "stale_write"))
        other = factories.tenant(slug="elsewhere")
        theirs = factories.headed_unit(other, name="Their department", head=None)
        foreign = write("patch", "/vocab/team/retail_compliance", {"extra": {"orgUnitId": str(theirs.id)}})
        self.assertEqual((foreign.status_code, foreign.json()["code"]), (404, "not_found"))
        self.assertEqual(department("retail_compliance"), cards)
        entity = write("post", "/tenant/org-units", {"kind": "legal_entity", "name": "Example Bank AB"}).json()["id"]
        closed = write("patch", f"/tenant/org-units/{retail}", {"active": False}, HTTP_IF_MATCH=f'"{added.json()["version"]}"')
        self.assertEqual(closed.status_code, 200, closed.content)
        for unit in (entity, retail):
            refused = write("patch", "/vocab/team/retail_compliance", {"extra": {"orgUnitId": unit}})
            self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"))
        cleared = write("patch", "/vocab/team/retail_compliance", {"extra": {"orgUnitId": None}})
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertIsNone(department("retail_compliance"))

        for person in (anna, johan):
            url = f"/api/v1/tenant/members/{person.id}/teams"
            response = self.client.put(url, data={"teams": ["retail_compliance"]}, content_type="application/json", **admin)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["teams"], ["retail_compliance"])
            self.activate(self.tenant)
            membership = Membership.objects.get(tenant=self.tenant, user=person)
            event = AuditEvent.objects.get(action="member.teams_changed", subject_id=membership.id)
            self.assertEqual((event.before, event.after), ({"teams": []}, {"teams": ["retail_compliance"]}))
        members = self.client.get("/api/v1/tenant/teams/retail_compliance/members", **admin).json()
        self.assertEqual([row["name"] for row in members["items"]], ["Anna Berg", "Johan Ek"])

        stranger = factories.member_user(other)
        refused = self.client.put(
            f"/api/v1/tenant/members/{stranger.id}/teams", data={"teams": ["retail_compliance"]}, content_type="application/json", **admin
        )
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_member"))

        without = self._member_with(perms.CASES_READ)
        denied = self.client.put(
            f"/api/v1/tenant/members/{anna.id}/teams", data={"teams": []}, content_type="application/json", **without
        )
        self.assertEqual(denied.status_code, 403)

    def test_ten_s9(self) -> None:
        """TEN-S9

        Removing a member ends their participations and team memberships (TEN-05, COL-04).
        Erik takes part in three entries and is in "Legal" and "Cards"; the case
        participations are `c9-owner-team-and-reassign`'s.
        """
        erik, anna, work, headers = self._erik()
        preview = self.client.get(f"/api/v1/tenant/members/{erik.id}/open-work", **headers).json()
        held = {row["kind"]: row["count"] for row in preview["items"]}
        self.assertEqual((held["participation"], held["team_membership"]), (3, 2))
        self.assertEqual(sorted(preview["teams"]), ["cards", "legal"])
        self.activate(self.tenant)
        self.assertEqual(Participant.objects.filter(user=erik, removed_at__isnull=True).count(), 3)

        owners = [{"kind": kind, "userId": str(anna.id)} for kind in ("register_entry", "register_entity", "gap", "internal_item")]
        self.assertEqual(self._remove(erik, owners, headers).status_code, 204)
        self.activate(self.tenant)
        self.assertFalse(Participant.objects.filter(user=erik, removed_at__isnull=True).exists())
        self.assertEqual(Participant.objects.filter(user=erik).count(), 3)
        self.assertFalse(TeamMember.objects.filter(user=erik).exists())
        self.assertIsNone(Participant.objects.get(pk=work.team_part.pk).removed_at)
        self.assertEqual(AuditEvent.objects.filter(action="participant.removed", tenant_id=self.tenant.id).count(), 3)
        self.assertEqual(AuditEvent.objects.filter(action="team_member.removed", tenant_id=self.tenant.id).count(), 2)

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

    def _enter(self, platform: Any, grant: str) -> dict[str, Any]:
        """Headers of the support session `platform` opens under `grant`, with a fresh step-up."""
        entered = self.client.post(f"/api/v1/console/support-access/{grant}/enter", **sign_in(platform, tenant=None, step_up=True))
        self.assertEqual(entered.status_code, 200, entered.content)
        self.assertEqual(entered.json()["sessionKind"], "support")
        return {"HTTP_AUTHORIZATION": f"Bearer {entered.json()['accessToken']}"}

    def test_ten_s11(self) -> None:
        """TEN-S11

        A support session reads and never writes, and never approves itself (TEN-06).
        Operations: `enterConsoleSupportAccess`; the refusals are proven over every route in
        apps/shared/tests_support_routes.py.
        """
        platform = factories.platform_user()
        console = sign_in(platform, tenant=None)
        bank = sign_in(self.admin, tenant=self.tenant, step_up=True)
        body = {"purpose": "The bank's briefing did not arrive.", "hours": 1}
        grant = self.client.post(
            f"/api/v1/console/tenants/{self.tenant.id}/support-access", data=body, content_type="application/json", **console
        ).json()["id"]
        self.assertEqual(self.client.post(f"/api/v1/tenant/support-access/{grant}/approve", **bank).status_code, 200)
        support = self._enter(platform, grant)
        self.activate(self.tenant)
        written = AuditEvent.objects.count()

        # Any write, an evidence download or an export: 403 support_read_only, nothing written.
        refusals = [
            ("POST", f"/api/v1/tenant/support-access/{grant}/revoke"),
            ("PATCH", "/api/v1/tenant"),
            ("DELETE", f"/api/v1/tenant/members/{self.admin.id}"),
            ("GET", f"/api/v1/evidence/{grant}/download"),
            # Search and Ask would spend the bank's AI budget.
            ("POST", "/api/v1/search"),
            ("POST", "/api/v1/ask"),
        ]
        for method, path in refusals:
            with self.subTest(route=f"{method} {path}"):
                response = self.client.generic(method, path, data="{}", content_type="application/json", **support)
                self.assertEqual((response.status_code, response.json()["code"]), (403, "support_read_only"))
        self.activate(self.tenant)
        self.assertEqual(AuditEvent.objects.count(), written, "a refused request writes nothing")

        # The platform person who asked can never approve the grant: the database refuses it.
        requested = SupportAccess.objects.create(
            tenant=self.tenant, platform_user=platform, reason="Check the feed.", hours=1, status="requested"
        )
        requested.approved_by = platform
        with self.assertRaises(IntegrityError), transaction.atomic():
            requested.save(update_fields=["approved_by"])

    @skip("pending: TEN-S12 (REP-04, chunk 12)")
    def test_ten_s12(self) -> None:
        """TEN-S12

        A closing tenant refuses writes and still lets people sign in and export (REP-04).
        """

    # --- public-registers (TEN-07, TEN-08) ----------------------------------------------
    LOOKUPS = "/api/v1/tenant/register-lookups"
    BANK_LEI = "549300EXAMPLEBANK001"
    FONDER_LEI = "549300EXAMPLEFOND002"
    LIV_LEI = "549300EXAMPLELIVF003"

    def _register_world(self) -> OrgUnit:
        """The library's jurisdictions, terms and Finansinspektionen, and a bank that already
        has its group and Example Bank AB, with the org number and nothing else, as the E2E
        seed has it."""
        self._seed_terms()
        library_build.authority(key="fi", short_name="Finansinspektionen")
        self.addCleanup(MockRegisters.reset)
        self.activate(self.tenant)
        group = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.GROUP.value, name="Example Group")
        return OrgUnit.objects.create(
            tenant=self.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Example Bank AB", org_number="556000-0001", parent=group
        )

    def _look_up(self, headers: dict[str, Any], query: str) -> dict[str, Any]:
        """Start a lookup, check it answers queued before the worker runs, run the worker's
        hand-off, and read the job back."""
        with self.captureOnCommitCallbacks(execute=False) as queued:
            started = self.client.post(self.LOOKUPS, data={"query": query}, content_type="application/json", **headers)
        self.assertEqual(started.status_code, 202, started.content)
        self.assertEqual((started.json()["status"], started.json()["entities"]), ("queued", []))
        self.assertEqual(len(queued), 1)
        queued[0]()
        read = self.client.get(f"{self.LOOKUPS}/{started.json()['id']}", **headers)
        self.assertEqual(read.status_code, 200, read.content)
        return dict(read.json())

    def _apply(self, headers: dict[str, Any], lookup_id: str, leis: list[str]) -> Any:
        return self.client.post(f"{self.LOOKUPS}/{lookup_id}/apply", data={"leis": leis}, content_type="application/json", **headers)

    def test_ten_s13(self) -> None:
        """TEN-S13

        The legal entities filled in from the public registers (TEN-07, AC-TEN2, J-13).
        Operations: `startRegisterLookup`, `getRegisterLookup`, `applyRegisterLookup`.

        With the mock register, the E2E seed's Example Group: GLEIF lists the bank, its fund
        company, its life insurer, a holding company FI does not list and an Estonian bank.
        """
        bank = self._register_world()
        headers = self._member_with(perms.VOCAB_MANAGE)
        lookup = self._look_up(headers, "556000-0001")
        self.assertEqual((lookup["status"], lookup["error"]), ("succeeded", None))
        self.assertIsNotNone(lookup["completedAt"])
        found = {entity["name"]: entity for entity in lookup["entities"]}
        self.assertEqual(
            [entity["name"] for entity in lookup["entities"]],
            ["Example Bank AB", "Example Fonder AB", "Example Liv Försäkring AB", "Example Holding AB", "Example Pank AS"],
        )
        # The licensed companies ticked, the holding company and the foreign bank not, and the
        # bank the organisation already has marked as already in it.
        self.assertEqual(
            {name: (entity["preselected"], entity["existingOrgUnitId"]) for name, entity in found.items()},
            {
                "Example Bank AB": (True, str(bank.id)),
                "Example Fonder AB": (True, None),
                "Example Liv Försäkring AB": (True, None),
                "Example Holding AB": (False, None),
                "Example Pank AS": (False, None),
            },
        )
        self.assertEqual((found["Example Holding AB"]["authority"], found["Example Holding AB"]["facts"]), ("fi", None))
        self.assertEqual((found["Example Pank AS"]["authority"], found["Example Pank AS"]["country"]), (None, "EE"))
        # Each Swedish company carries its business, licences and branches from FI.
        facts = found["Example Bank AB"]["facts"]
        self.assertEqual(facts["mainBusiness"], "Bankaktiebolag")
        self.assertEqual(len(facts["licences"]), 5)
        self.assertEqual([(branch["countryName"], branch["jurisdiction"]) for branch in facts["branches"]], [("Danmark", "dk"), ("Norge", "no")])
        self.assertEqual(found["Example Bank AB"]["unmapped"], ["IM_MR_SA"])
        self.assertEqual(found["Example Fonder AB"]["entityType"]["key"], "fund_company")
        self.assertEqual(found["Example Liv Försäkring AB"]["entityType"]["key"], "insurer")
        self.assertIsNone(found["Example Holding AB"]["entityType"])

        # Adding the ticked companies.
        self.activate(self.tenant)
        units_before, licences_before = OrgUnit.objects.count(), Licence.objects.count()
        applied = self._apply(headers, lookup["id"], [self.BANK_LEI, self.FONDER_LEI, self.LIV_LEI])
        self.assertEqual(applied.status_code, 200, applied.content)
        self.assertEqual((applied.json()["created"], applied.json()["linked"]), (2, 1))
        self.assertEqual([unit["name"] for unit in applied.json()["orgUnits"]], ["Example Bank AB", "Example Fonder AB", "Example Liv Försäkring AB"])
        self.activate(self.tenant)
        self.assertEqual(OrgUnit.objects.count(), units_before + 2)
        fonder = OrgUnit.objects.select_related("entity_term").get(lei=self.FONDER_LEI)
        liv = OrgUnit.objects.select_related("entity_term").get(lei=self.LIV_LEI)
        self.assertEqual(
            (fonder.kind, fonder.org_number, fonder.country_code, fonder.parent_id, fonder.entity_term.key if fonder.entity_term else None),
            (OrgUnitKind.LEGAL_ENTITY.value, "556000-0003", "SE", bank.id, "fund_company"),
        )
        self.assertEqual((liv.parent_id, liv.entity_term.key if liv.entity_term else None), (bank.id, "insurer"))
        # Linked, not added twice, and left as it was.
        bank.refresh_from_db()
        self.assertEqual((bank.lei, bank.country_code, bank.version), ("", "", 1))
        entries = RegisterEntry.objects.select_related("authority").order_by("org_unit__name")
        self.assertEqual([(entry.org_unit_id, entry.authority.key) for entry in entries], [(bank.id, "fi"), (fonder.id, "fi"), (liv.id, "fi")])
        self.assertEqual(entries[0].facts["licences"][0]["grantedOn"], "1995-03-01")
        # No licence row, and each write has its audit event. The scope follows the companies by
        # itself (D-122, FP-S20 has its terms), with no request: nobody asked for it.
        self.assertEqual(Licence.objects.count(), licences_before)
        self.assertTrue(FootprintTerm.objects.exists())
        self.assertFalse(FootprintChangeRequest.objects.exists())
        actions = list(AuditEvent.objects.filter(tenant_id=self.tenant.id).values_list("action", flat=True))
        for action, count in (
            ("register_lookup.started", 1),
            ("register_lookup.finished", 1),
            ("org_unit.created", 2),
            ("register_entry.created", 3),
            ("register_lookup.applied", 1),
        ):
            self.assertEqual(actions.count(action), count, action)
        # The organisation shows each entity's facts with the date read.
        rows = {row["name"]: row for row in self.client.get("/api/v1/tenant/org-units", **headers).json()["items"]}
        self.assertEqual(rows["Example Bank AB"]["registerEntry"]["authority"], {"key": "fi", "name": "Finansinspektionen"})
        self.assertEqual(rows["Example Bank AB"]["registerEntry"]["readAt"], lookup["completedAt"])
        self.assertEqual(rows["Example Bank AB"]["registerEntry"]["unmapped"], ["IM_MR_SA"])
        self.assertIsNone(rows["Example Group"]["registerEntry"])
        # Applying again links every company and adds nothing.
        again = self._apply(headers, lookup["id"], [self.BANK_LEI, self.FONDER_LEI, self.LIV_LEI])
        self.assertEqual((again.json()["created"], again.json()["linked"]), (0, 3))
        self.activate(self.tenant)
        self.assertEqual((OrgUnit.objects.count(), RegisterEntry.objects.count()), (units_before + 2, 3))
        # An LEI the lookup did not find.
        unknown = self._apply(headers, lookup["id"], ["549300EXAMPLEGONE010"])
        self.assertEqual((unknown.status_code, unknown.json()["code"]), (422, "unknown_lei"))

        # A number no company carries, a number two carry, and a register that cannot be read.
        for query, code in (("556000-0000", "lookup_not_found"), ("556000-9999", "lookup_ambiguous"), ("556000-0666", "register_unavailable")):
            with self.subTest(query=query):
                failed = self._look_up(headers, query)
                self.assertEqual((failed["status"], failed["error"], failed["entities"]), ("failed", code, []))
                refused = self._apply(headers, failed["id"], [self.BANK_LEI])
                self.assertEqual((refused.status_code, refused.json()["code"]), (409, "lookup_not_done"))
        typed = self.client.post(self.LOOKUPS, data={"query": "Example Bank!"}, content_type="application/json", **headers)
        self.assertEqual((typed.status_code, typed.json()["code"]), (422, "invalid_query"))

        # A member without vocab.manage, and another bank.
        reader = sign_in(factories.member(self.tenant, roles=("reader",)).user, tenant=self.tenant)
        for denied in (
            self.client.post(self.LOOKUPS, data={"query": "556000-0001"}, content_type="application/json", **reader),
            self.client.get(f"{self.LOOKUPS}/{lookup['id']}", **reader),
            self._apply(reader, lookup["id"], [self.BANK_LEI]),
        ):
            self.assertEqual((denied.status_code, denied.json()["requiredPermission"]), (403, perms.VOCAB_MANAGE))
        other = factories.tenant(slug="other-bank")
        theirs = sign_in(factories.member(other, roles=("admin",)).user, tenant=other)
        self.assertEqual(self.client.get(f"{self.LOOKUPS}/{lookup['id']}", **theirs).status_code, 404)
        stolen = self._apply(theirs, lookup["id"], [self.BANK_LEI])
        self.assertEqual((stolen.status_code, stolen.json()["code"]), (404, "not_found"))

    def test_ten_s14(self) -> None:
        """TEN-S14

        The nightly re-read refreshes the register facts, and the scope follows them (TEN-08, D-122).
        """
        bank = self._register_world()
        headers = self._member_with(perms.VOCAB_MANAGE)
        lookup = self._look_up(headers, "556000-0001")
        self.assertEqual(self._apply(headers, lookup["id"], [self.BANK_LEI]).status_code, 200)
        self.activate(self.tenant)
        yesterday = timezone.now() - timedelta(days=1)
        RegisterEntry.objects.filter(org_unit=bank).update(read_at=yesterday, changed_at=yesterday)
        units = list(OrgUnit.objects.order_by("id").values_list("id", "version", "name", "lei"))
        # The scope already follows the bank's facts (D-122); a licence that gives no new term moves none.
        scope = set(FootprintTerm.objects.values_list("term_id", flat=True))
        self.assertTrue(scope)

        def entry() -> RegisterEntry:
            self.activate(self.tenant)
            return RegisterEntry.objects.get(org_unit=bank)

        def recheck() -> None:
            tasks.recheck_tenant_registers(str(self.tenant.id))

        # A new licence in FI's register.
        read = MockRegisters().licence_facts("fi", "556000-0001")
        assert read is not None
        granted = RegisterLicence("Tillstånd att ge ut elektroniska pengar, enligt lagen (2011:755) om elektroniska pengar", datetime.date(2026, 10, 1))
        MockRegisters.override("556000-0001", dataclasses.replace(read, licences=(*read.licences, granted)))
        recheck()
        changed = entry()
        self.assertEqual(changed.facts["licences"][-1], {"text": granted.text, "grantedOn": "2026-10-01"})
        self.assertGreater(changed.read_at, yesterday)
        self.assertEqual((changed.changed_at, changed.version), (changed.read_at, 2))
        event = AuditEvent.objects.filter(tenant_id=self.tenant.id, action="register_entry.changed").get()
        self.assertEqual((event.subject_id, event.actor_type, event.after["licencesAdded"]), (changed.id, "system", [granted.text]))
        self.assertEqual((event.after["licencesRemoved"], event.after["branchesAdded"]), ([], []))
        # No organisation row or licence row changes, and a bank's licence already allows every
        # licence-bound term, so the scope the facts give it is the same.
        self.assertEqual(list(OrgUnit.objects.order_by("id").values_list("id", "version", "name", "lei")), units)
        self.assertFalse(Licence.objects.exists())
        self.assertEqual(set(FootprintTerm.objects.values_list("term_id", flat=True)), scope)

        # The next night nothing changed: the read date moves and nothing else.
        recheck()
        unchanged = entry()
        self.assertGreater(unchanged.read_at, changed.read_at)
        self.assertEqual((unchanged.changed_at, unchanged.version, unchanged.facts), (changed.changed_at, 2, changed.facts))
        self.assertEqual(AuditEvent.objects.filter(tenant_id=self.tenant.id, action="register_entry.read").count(), 1)

        # A register that cannot be reached leaves the stored facts as they were.
        MockRegisters.override("556000-0001", RegisterUnavailable("down"))
        events = AuditEvent.objects.count()
        recheck()
        self.assertEqual((entry().read_at, entry().facts, entry().version), (unchanged.read_at, unchanged.facts, 2))
        self.assertEqual(AuditEvent.objects.count(), events)
