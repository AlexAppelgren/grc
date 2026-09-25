"""Scenario stubs for the register app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ACC, REG.
"""

from unittest import skip

from django.test import TestCase

from apps.library import testing as library_build
from apps.register.applicability import APPLICABILITY_SET, entities_spanned
from apps.register.models import TenantObligation, TenantObligationScope
from apps.register.tests_applicability import Bank, banks_duty, seed_library
from apps.shared import tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import sign_in
from apps.taxonomy.models import ComplianceStatus, FootprintTerm


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

    @skip("pending: REG-S3")
    def test_reg_s3(self) -> None:
        """REG-S3

        Compliance status and its details are kept per legal entity (REG-02).
        Operations: `updateRegisterEntity`.
        """

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

    @skip("pending: REG-S11")
    def test_reg_s11(self) -> None:
        """REG-S11

        A stale write on a register row is refused (REG-02).
        Operations: `updateRegister`.
        """

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
