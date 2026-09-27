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

from apps.library import testing as library_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, sign_in, stub_session, user_principal
from apps.taxonomy.models import ComplianceStatus
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
