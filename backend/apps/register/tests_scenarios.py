"""Scenario stubs for the register app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ACC, REG.
"""

from typing import Any
from unittest import skip

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.library import testing as library_build
from apps.library import testing as library_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.register.applicability import APPLICABILITY_SET, entities_spanned
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.register.tests_applicability import Bank, banks_duty, seed_library
from apps.shared.models import AuditEvent
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, sign_in, stub_session, user_principal
from apps.taxonomy.models import ComplianceStatus, FootprintTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.models import OrgUnit, OrgUnitKind


class StatusWorld:
    """c8-reg-status: one bank, its legal entities and a shared obligation, with an owner
    holding `register.read` and `register.edit`. Applicability is set on the rows directly,
    as c8-reg-applicability's route leaves them; everything else goes through the API."""

    def __init__(self, case: Any, *, entities: tuple[str, ...]) -> None:
        self.case = case
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
        act = library_testing.instrument(key="scenario-act", regime="regime:securities")
        self.obligation = library_testing.obligation(act, key="scenario-duty")
        self.tenant = factories.tenant(slug="scenario-register")
        self.owner = factories.member_user(self.tenant, roles=("compliance_officer",))
        tenancy.activate(self.tenant.id)
        self.entities = [
            OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name=name) for name in entities
        ]
        self.principal = user_principal(
            permissions={perms.REGISTER_READ, perms.REGISTER_EDIT}, tenant_id=self.tenant.id, subject_id=self.owner.id
        )

    def _entry(self) -> Any:
        tenancy.activate(self.tenant.id)
        return ensure_register_entry(
            tenant_id=self.tenant.id, obligation_id=self.obligation.id, actor=factories.user_actor(user_id=self.owner.id)
        )

    def entry_at_version(self, version: int) -> None:
        TenantObligation.objects.filter(pk=self._entry().pk).update(version=version)

    def applies(self, entity: Any, *, reason: str) -> str:
        TenantObligationScope.objects.create(
            tenant=self.tenant,
            tenant_obligation=self._entry(),
            org_unit=entity,
            applicability=Applicability.APPLIES.value,
            applicability_reason=reason,
            applicability_decided_at=timezone.now(),
            applicability_decided_by=self.owner,
            compliance_status=ComplianceStatus.objects.get(is_default=True),
        )
        return reason

    def _patch(self, url: str, body: dict[str, Any], version: int) -> Any:
        with stub_session(self.principal):
            return self.case.client.patch(
                url, data=body, content_type="application/json", HTTP_IF_MATCH=f'"{version}"', HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}"
            )

    def patch_entry(self, body: dict[str, Any], *, version: int) -> Any:
        return self._patch(f"/api/v1/obligations/{self.obligation.id}/register", body, version)

    def patch_entity(self, entity: Any, body: dict[str, Any], *, version: int) -> Any:
        return self._patch(f"/api/v1/obligations/{self.obligation.id}/register/entities/{entity.id}", body, version)

    def read(self) -> Any:
        with stub_session(self.principal):
            response = self.case.client.get(
                f"/api/v1/obligations/{self.obligation.id}/register", HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}"
            )
        self.case.assertEqual(response.status_code, 200, response.content)
        return response.json()



class RegisterScenarioTests(TestCase):
    """Scenario tests for apps.register, one method per @integration scenario."""

    def test_reg_s1(self) -> None:
        """REG-S1

        One compliance person sets applicability after confirming it (REG-01).
        Operations: `setApplicability`.

        The dialog, its confirm and its cancel are the screen's, proved by the journey; here
        the confirmed call stores the answer at once, with no step-up, and one audit event.
        """
        seed_library()
        a = Bank("reg-s1")
        duty = banks_duty()
        before = AuditEvent.objects.filter(action=APPLICABILITY_SET).count()
        response = self.client.put(
            f"/api/v1/obligations/{duty.id}/applicability",
            data={"orgUnitId": str(a.bank_ab.id), "applicability": "not_applicable", "reason": "No client money held"},
            content_type="application/json",
            **sign_in(a.officer, tenant=a.tenant),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["applicability"], response.json()["reason"]), ("not_applicable", "No client money held"))
        tenancy.activate(a.tenant.id)
        scope = TenantObligationScope.objects.get(tenant_obligation__obligation=duty, org_unit=a.bank_ab)
        self.assertEqual((scope.applicability, scope.applicability_reason), ("does_not_apply", "No client money held"))
        [event] = AuditEvent.objects.filter(action=APPLICABILITY_SET)[before:]
        self.assertEqual((event.actor_id, event.actor_label, event.step_up_assertion_id), (a.officer.id, "Sara Lind", None))
        self.assertEqual(event.before["applicability"], "under_assessment")
        self.assertEqual((event.after["applicability"], event.after["reason"]), ("not_applicable", "No client money held"))

    def test_reg_s2(self) -> None:
        """REG-S2

        Only a holder of applicability.approve sets applicability (REG-01).
        """
        seed_library()
        a = Bank("reg-s2")
        duty = banks_duty()
        response = self.client.put(
            f"/api/v1/obligations/{duty.id}/applicability",
            data={"applicability": "applies", "reason": "Client money"},
            content_type="application/json",
            **sign_in(a.owner, tenant=a.tenant),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], "applicability.approve")
        tenancy.activate(a.tenant.id)
        self.assertFalse(TenantObligation.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action=APPLICABILITY_SET).exists())

    def test_reg_s3(self) -> None:
        """REG-S3

        Compliance status and its details are kept per legal entity (REG-02).
        Operations: `updateRegisterEntity`.
        """
        # c8-reg-status: each entity row holds its own status and details, and the
        # obligation's pill is the worse of the two.
        world = StatusWorld(self, entities=("Bank AB", "Bank Finance AB"))
        bank, finance = world.entities
        decided = {entity.id: world.applies(entity, reason=f"{entity.name} holds client assets") for entity in world.entities}
        first = world.patch_entity(
            bank,
            {
                "complianceStatus": "compliant",
                "riskRating": "low",
                "ownerId": str(world.owner.id),
                "process": "Client asset reconciliation",
                "system": "Custody ledger",
                "evidenceLocation": "Compliance share / Bank AB",
                "nextReviewDate": "2027-03-31",
            },
            version=1,
        )
        self.assertEqual(first.status_code, 200, first.content)
        second = world.patch_entity(
            finance,
            {
                "complianceStatus": "partly_compliant",
                "statusNote": "The evidence log is still manual.",
                "riskRating": "high",
                "ownerTeam": "compliance",
                "process": "Fund reconciliation",
                "system": "Fund ledger",
                "evidenceLocation": "Compliance share / Finance AB",
                "nextReviewDate": "2026-12-31",
            },
            version=1,
        )
        self.assertEqual(second.status_code, 200, second.content)

        read = world.read()
        rows = {row["orgUnitId"]: row for row in read["entities"]}
        self.assertEqual(set(rows), {str(bank.id), str(finance.id)})
        expected = {
            bank.id: ("compliant", None, "low", str(world.owner.id), None, "Client asset reconciliation", "Custody ledger", "Compliance share / Bank AB", "2027-03-31"),
            finance.id: ("partly_compliant", "The evidence log is still manual.", "high", None, "compliance", "Fund reconciliation", "Fund ledger", "Compliance share / Finance AB", "2026-12-31"),
        }
        for entity_id, (status, note, risk, owner, team, process, system, evidence, review) in expected.items():
            row = rows[str(entity_id)]
            with self.subTest(entity=row["orgUnitName"]):
                self.assertEqual(row["complianceStatus"]["key"], status)
                self.assertEqual(row["statusNote"], note)
                self.assertEqual(row["riskRating"]["key"], risk)
                self.assertEqual(row["owner"] and row["owner"]["id"], owner)
                self.assertEqual(row["ownerTeam"] and row["ownerTeam"]["key"], team)
                self.assertEqual((row["process"], row["system"], row["evidenceLocation"]), (process, system, evidence))
                self.assertEqual(row["nextReviewDate"], review)
                self.assertEqual(row["applicability"], "applies")
                self.assertEqual(row["applicabilityReason"], decided[entity_id])
                self.assertIsNotNone(row["applicabilityDecidedAt"])
        self.assertEqual(read["complianceStatus"]["key"], "partly_compliant")
        self.assertEqual(read["complianceStatus"]["kind"], "partly")

    @skip("pending: REG-S4")
    def test_reg_s4(self) -> None:
        """REG-S4

        "Applies" and "we comply" are separate facts (REG-01, REG-02).
        """

    @skip("pending: REG-S5")
    def test_reg_s5(self) -> None:
        """REG-S5

        A gap has an owner, severity, target date and remediation (REG-03).
        Operations: `createGap`, `updateGap`.
        """

    @skip("pending: REG-S6")
    def test_reg_s6(self) -> None:
        """REG-S6

        Risk acceptance is behind four eyes with step-up (REG-03).
        Operations: `requestRiskAcceptance`, `approveRiskAcceptance`, `reopenGap`.
        """

    @skip("pending: REG-S7")
    def test_reg_s7(self) -> None:
        """REG-S7

        Assessment history and "How we read this rule" are kept per obligation (REG-04).
        Operations: `saveInterpretation`.
        """

    @skip("pending: REG-S8")
    def test_reg_s8(self) -> None:
        """REG-S8

        Linked internal items carry external references (REG-05).
        Operations: `addInternalLink`, `removeInternalLink`.
        """

    @skip("pending: REG-S9")
    def test_reg_s9(self) -> None:
        """REG-S9

        Yearly attestation and waivers (REG-06).
        """

    @skip("pending: REG-S10")
    def test_reg_s10(self) -> None:
        """REG-S10

        Recurring duties appear on the roadmap from recurrence rules (REG-07).
        Operations: `completeDutyOccurrence`.
        """

    def test_reg_s11(self) -> None:
        """REG-S11

        A stale write on a register row is refused (REG-02).
        Operations: `updateRegister`.
        """
        # c8-reg-status: two owners loaded the entry at version 3; the first save wins and
        # the second is refused with nothing merged.
        world = StatusWorld(self, entities=())
        world.entry_at_version(3)
        first = world.patch_entry({"statusNote": "First owner's note.", "process": "Reconciliation"}, version=3)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["version"], 4)
        second = world.patch_entry({"statusNote": "Second owner's note.", "system": "Ledger"}, version=3)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "stale_write")
        read = world.read()
        self.assertEqual(read["version"], 4)
        self.assertEqual(read["statusNote"], "First owner's note.")
        self.assertIsNone(read["system"])

    def test_reg_s12(self) -> None:
        """REG-S12

        A legal entity follows a standard when its applicability is set to "Applies" (REG-01, REG-02).

        The obligation row's worse-of pill is `c8-reg-status`'s read; here the entity
        statuses it ranks are left as they were.
        """
        seed_library()
        a = Bank("reg-s12")
        standard = library_build.standard()
        tenancy.activate(a.tenant.id)
        FootprintTerm.objects.create(tenant=a.tenant, term=library_build.term("standard:iso_iec_27001"))
        spanned = entities_spanned([standard.id])[standard.id]
        self.assertEqual({row.name for row in spanned}, {"Example Bank AB", "Example Fonder AB", "Example Liv Försäkring AB"})
        self.assertFalse(TenantObligationScope.objects.exists(), "reading the span writes no scope row")
        for entity, value, reason in ((a.bank_ab, "applies", "Certified"), (a.liv, "not_applicable", "Not in the certificate's scope")):
            response = self.client.put(
                f"/api/v1/obligations/{standard.id}/applicability",
                data={"orgUnitId": str(entity.id), "applicability": value, "reason": reason},
                content_type="application/json",
                **sign_in(a.officer, tenant=a.tenant),
            )
            self.assertEqual(response.status_code, 200, response.content)
        tenancy.activate(a.tenant.id)
        rows = {row.org_unit_id: row for row in TenantObligationScope.objects.filter(tenant_obligation__obligation=standard)}
        self.assertEqual(set(rows), {a.bank_ab.id, a.liv.id}, "Fonder was not answered, so it has no row")
        bank, liv = rows[a.bank_ab.id], rows[a.liv.id]
        self.assertEqual((bank.applicability, bank.applicability_reason), ("applies", "Certified"))
        self.assertIsNotNone(bank.applicability_decided_at)
        self.assertEqual(liv.applicability, "does_not_apply")
        default = ComplianceStatus.objects.get(is_default=True)
        self.assertEqual({row.compliance_status_id for row in rows.values()}, {default.id})
        entry = TenantObligation.objects.get(obligation=standard)
        self.assertEqual((entry.applicability, entry.version), ("not_assessed", 1), "the entity answers leave the entry's own answer alone")

    @skip("pending: REG-S13 (REG-08, chunk 8)")
    def test_reg_s13(self) -> None:
        """REG-S13

        A tenant lists its clauses and controls as units in its own words (REG-08).
        Operations: `createUnit`, `updateUnit`, `removeUnit`, `pasteUnits`.
        """

    @skip("pending: REG-S14 (REG-08, chunk 8)")
    def test_reg_s14(self) -> None:
        """REG-S14

        Unit decisions are set from the paste in one confirmed call (REG-01, REG-08).
        Operations: `setApplicabilityMany`.
        """

    @skip("pending: REG-S15 (REG-08, chunk 8)")
    def test_reg_s15(self) -> None:
        """REG-S15

        The register filtered by standard and entity is the Statement of Applicability (REG-08).
        """

    @skip("pending: ACC-S4 (ACC-04, chunk 11)")
    def test_acc_s4(self) -> None:
        """ACC-S4

        With tenant reach on, an entry reads the register decisions in its scope and nothing else (ACC-04).
        """
