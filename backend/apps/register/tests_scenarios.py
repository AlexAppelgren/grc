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


class RegisterScenarioTests(TestCase):
    """Scenario tests for apps.register, one method per @integration scenario."""

    @skip("pending: REG-S1")
    def test_reg_s1(self) -> None:
        """REG-S1

        One compliance person sets applicability after confirming it (REG-01).
        Operations: `setApplicability`.
        """

    @skip("pending: REG-S2")
    def test_reg_s2(self) -> None:
        """REG-S2

        Only a holder of applicability.approve sets applicability (REG-01).
        """

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

    def test_reg_s5(self) -> None:
        """REG-S5

        A gap has an owner, severity, target date and remediation (REG-03).
        Operations: `createGap`, `updateGap`.

        Up to the roadmap line: "Our deadline" on the roadmap is c8-home-standing-roadmap's.
        """
        from apps.register.tests_gaps import GapWorld, gap_body, seed_library
        from apps.shared.testing import sign_in

        seed_library()
        world = GapWorld("reg-s5")
        world.set_entry(applicability="applies", compliance_status=world.status("gap"))
        owner = sign_in(world.owner, tenant=world.tenant)
        body = gap_body(severity="high", ownerId=str(world.owner.id))
        recorded = self.client.post(world.url(), data=body, content_type="application/json", **owner)
        self.assertEqual(recorded.status_code, 201, recorded.content)
        gap = recorded.json()
        self.assertEqual((gap["status"]["key"], gap["status"]["kind"], gap["status"]["label"]), ("open", "open", "Open"))
        self.assertEqual((gap["severity"]["key"], gap["severity"]["label"]), ("high", "High"))
        self.assertEqual(gap["source"]["label"], "Assessment")
        self.assertEqual((gap["owner"]["id"], gap["targetDate"], gap["remediation"]), (str(world.owner.id), body["targetDate"], body["remediation"]))
        started = self.client.patch(
            f"/api/v1/gaps/{gap['id']}", data={"status": "remediating"}, content_type="application/json", HTTP_IF_MATCH=str(gap["version"]), **owner
        )
        self.assertEqual(started.status_code, 200, started.content)
        self.assertEqual((started.json()["status"]["kind"], started.json()["status"]["label"]), ("remediating", "Remediating"))

    def test_reg_s6(self) -> None:
        """REG-S6

        Risk acceptance is behind four eyes with step-up (REG-03).
        Operations: `requestRiskAcceptance`, `approveRiskAcceptance`, `reopenGap`.
        """
        from apps.register.gaps import RISK_ACCEPTED
        from apps.register.tests_gaps import GapWorld, gap_body, seed_library
        from apps.shared.models import AuditEvent
        from apps.shared.testing import sign_in

        seed_library()
        world = GapWorld("reg-s6")
        officer = sign_in(world.officer, tenant=world.tenant, step_up=True)
        gap = self.client.post(world.url(), data=gap_body(), content_type="application/json", **officer).json()
        asked = self.client.post(f"/api/v1/gaps/{gap['id']}/accept-risk", data={"reason": "compensating_control"}, content_type="application/json", **officer)
        self.assertEqual(asked.status_code, 200, asked.content)
        self.assertIsNone(asked.json()["riskAcceptance"]["approvedBy"], "Waiting for approval")
        self.assertEqual(asked.json()["status"]["key"], "open")
        own = self.client.post(f"/api/v1/gaps/{gap['id']}/accept-risk/approve", **officer)
        self.assertEqual((own.status_code, own.json()["code"]), (409, "four_eyes_violation"))
        approved = self.client.post(f"/api/v1/gaps/{gap['id']}/accept-risk/approve", **sign_in(world.second_officer, tenant=world.tenant, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual((approved.json()["status"]["kind"], approved.json()["status"]["label"]), ("risk_accepted", "Risk accepted"))
        [event] = AuditEvent.objects.filter(action=RISK_ACCEPTED, subject_id=gap["id"])
        self.assertEqual(event.actor_id, world.second_officer.id)
        self.assertEqual(event.after["requestedBy"], str(world.officer.id))
        self.assertIsNotNone(event.step_up_assertion_id)

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

    @skip("pending: REG-S12 (REG-01, chunk 8)")
    def test_reg_s12(self) -> None:
        """REG-S12

        A legal entity follows a standard when its applicability is set to "Applies" (REG-01, REG-02).
        """

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
