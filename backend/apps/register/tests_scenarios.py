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

from apps.shared.testing import sign_in


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

    def test_reg_s7(self) -> None:
        """REG-S7

        Assessment history and "How we read this rule" are kept per obligation (REG-04).
        Operations: `saveInterpretation`.
        """
        from apps.register.tests_history import assessment
        from apps.register.tests_links import build_world

        w = build_world()
        url = f"/api/v1/obligations/{w.obligation.id}"
        officer = sign_in(w.officer, tenant=w.bank)
        # Given an obligation assessed twice over a year
        earlier = assessment(w.bank, w.obligation.id, w.officer, "gap", days_ago=330, rationale="The reconciliation log was manual.")
        later = assessment(w.bank, w.obligation.id, w.reader, "compliant", days_ago=5, rationale="The log is automated.")
        for version, text in enumerate(("We read this as covering client accounts.", "We read this as covering every client account, custody included.")):
            saved = self.client.put(
                f"{url}/interpretation", data={"text": text}, content_type="application/json", HTTP_IF_MATCH=f'"{version}"', **officer
            )
            self.assertEqual(saved.status_code, 200, saved.content)
        # When a user opens the obligation
        reader = sign_in(w.reader, tenant=w.bank)
        reading = self.client.get(f"{url}/interpretation", **reader).json()
        assessments = self.client.get(f"{url}/assessments", **reader).json()
        # Then "How we read this rule" shows the current interpretation with its author and date
        self.assertEqual(reading["current"]["text"], "We read this as covering every client account, custody included.")
        self.assertEqual(reading["current"]["author"], {"id": str(w.officer.id), "name": w.officer.name})
        self.assertTrue(reading["current"]["writtenAt"])
        self.assertEqual([v["text"] for v in reading["earlier"]], ["We read this as covering client accounts."])
        # And the history lists each earlier assessment unchanged, with who and when
        self.assertEqual(
            [(row["id"], row["status"]["key"], row["rationale"], row["assessedBy"]["id"], row["assessedAt"][:19]) for row in assessments["items"]],
            [
                (str(later.id), "compliant", "The log is automated.", str(w.reader.id), later.assessed_at.isoformat()[:19]),
                (str(earlier.id), "gap", "The reconciliation log was manual.", str(w.officer.id), earlier.assessed_at.isoformat()[:19]),
            ],
        )

    def test_reg_s8(self) -> None:
        """REG-S8

        Linked internal items carry external references (REG-05).
        Operations: `addInternalLink`, `removeInternalLink`.
        """
        from apps.register.tests_links import build_world

        w = build_world()
        url = f"/api/v1/obligations/{w.obligation.id}/internal-links"
        officer = sign_in(w.officer, tenant=w.bank)
        # When the owner links the policy "Client asset policy" with the reference "POL-014"
        # and the control "Daily reconciliation" with a link kind from the tenant vocabulary
        policy = self.client.post(
            url, data={"kind": "policy", "label": "Client asset policy", "externalRef": "POL-014"}, content_type="application/json", **officer
        )
        control = self.client.post(
            url, data={"kind": "control", "label": "Daily reconciliation", "externalRef": "CTL-7"}, content_type="application/json", **officer
        )
        self.assertEqual((policy.status_code, control.status_code), (201, 201), (policy.content, control.content))
        # Then "Linked internal items" lists both with their kind label and external reference
        page = self.client.get(url, **sign_in(w.reader, tenant=w.bank)).json()
        self.assertEqual(
            [(row["kind"]["key"], row["kind"]["label"], row["label"], row["externalRef"]) for row in page["items"]],
            [("policy", "Policy", "Client asset policy", "POL-014"), ("control", "Control", "Daily reconciliation", "CTL-7")],
        )
        # And the API exposes them so an external GRC system can read the links: ids and keys
        # that never move beside the label, and a removed link leaves the list but not the item
        self.assertEqual(page["total"], 2)
        self.assertTrue(all(row["id"] and row["internalItemId"] for row in page["items"]))
        removed = self.client.delete(f"/api/v1/internal-links/{policy.json()['id']}", **officer)
        self.assertEqual(removed.status_code, 204)
        after = self.client.get(url, **sign_in(w.reader, tenant=w.bank)).json()
        self.assertEqual([row["label"] for row in after["items"]], ["Daily reconciliation"])

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

    @skip("pending: REG-S17 (OWN-04, OWN-05, REG-01, REG-02, REG-05, chunk 11)")
    def test_reg_s17(self) -> None:
        """REG-S17

        The register decides the bank's own obligations as it decides shared ones, and links their controls (OWN-04, OWN-05, REG-01, REG-02, REG-05).
        """
