"""Scenario stubs for the register app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ACC, REG.
"""

import uuid
from typing import Any
from unittest import mock, skip

from django.core.cache import cache
from django.db import OperationalError, transaction
from django.test import Client, TestCase
from django.utils import timezone

from apps.governance.models import AiGeneration, AiPurpose
from apps.library import testing as library_build
from apps.library import testing as library_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.library.models import Obligation
from apps.library.seeds.library import seed_authorities
from apps.proposals import logic as proposals_logic
from apps.proposals.models import Proposal
from apps.proposals.tests_apply_private import filing
from apps.proposals.tests_kinds import instrument_body, obligation_body
from apps.proposals.tests_private_controls import control_body
from apps.register import applicability, decide_all
from apps.register import tasks as register_tasks
from apps.register.applicability import APPLICABILITY_SET, entities_spanned
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, ComplianceAssessment, Gap, TenantObligation, TenantObligationScope
from apps.register.tests_applicability import Bank, banks_duty, seed_library
from apps.register.tests_company_view import FI, register_facts
from apps.shared.adapters.llm import MockLlm
from apps.shared.models import AuditEvent
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, sign_in, stub_session, user_principal
from apps.taxonomy.models import ComplianceStatus, FootprintTerm, GapSource, GapStatus, RiskRating
from apps.search.models import SearchChunk
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
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

    def test_reg_s4(self) -> None:
        """REG-S4

        "Applies" and "we comply" are separate facts (REG-01, REG-02).
        Operations: `setApplicability`, `updateRegister`, `getObligation`, `getRegisterEntry`.
        """
        # c8-inventory-overlay: "does not apply" hides the status on the obligation and
        # deletes nothing; "applies" again shows the same status and the same gap.
        seed_library()
        a = Bank("reg-s4")
        duty = banks_duty()
        officer = sign_in(a.officer, tenant=a.tenant)

        def answer(value: str, version: int) -> None:
            response = self.client.put(
                f"/api/v1/obligations/{duty.id}/applicability",
                data={"applicability": value, "reason": f"Reviewed: {value}"},
                content_type="application/json",
                HTTP_IF_MATCH=f'"{version}"',
                **officer,
            )
            self.assertEqual(response.status_code, 200, response.content)

        def card() -> Any:
            response = self.client.get(f"/api/v1/obligations/{duty.id}", **officer)
            self.assertEqual(response.status_code, 200, response.content)
            return response.json()

        def kept() -> tuple[Any, ...]:
            tenancy.activate(a.tenant.id)
            entry = TenantObligation.objects.select_related("compliance_status").get(obligation=duty)
            gaps = list(Gap.objects.filter(tenant_obligation=entry).values_list("id", "title", "status__key", "version"))
            assessments = list(ComplianceAssessment.objects.filter(tenant_obligation=entry).values_list("id", "status__key", "rationale"))
            return entry.compliance_status.key, entry.status_note, gaps, assessments

        answer("applies", 0)
        recorded = self.client.patch(
            f"/api/v1/obligations/{duty.id}/register",
            data={"complianceStatus": "gap", "statusNote": "Reconciliation is weekly", "rationale": "Audit finding"},
            content_type="application/json",
            HTTP_IF_MATCH='"2"',
            **officer,
        )
        self.assertEqual(recorded.status_code, 200, recorded.content)
        tenancy.activate(a.tenant.id)
        Gap.objects.create(
            tenant=a.tenant,
            tenant_obligation=TenantObligation.objects.get(obligation=duty),
            title="Reconciliation is weekly",
            severity=RiskRating.objects.get(key="high"),
            source=GapSource.objects.get(key="audit"),
            status=GapStatus.objects.get(key="open"),
            identified_by=a.officer,
        )
        self.assertEqual((card()["applicability"], card()["complianceStatus"]["key"]), ("applies", "gap"))
        before = kept()
        self.assertEqual(len(before[2]), 1)
        self.assertEqual([row[1:] for row in before[3]], [("gap", "Audit finding")])

        answer("not_applicable", 3)
        self.assertEqual((card()["applicability"], card()["complianceStatus"]), ("not_applicable", None))
        self.assertEqual(kept(), before, "the status, its note, its gap and its history are untouched")
        register = self.client.get(f"/api/v1/obligations/{duty.id}/register", **officer).json()
        self.assertEqual((register["complianceStatus"]["key"], register["statusNote"]), ("gap", "Reconciliation is weekly"))

        answer("applies", 4)
        self.assertEqual((card()["applicability"], card()["complianceStatus"]["key"]), ("applies", "gap"))
        self.assertEqual(kept(), before, "nothing was deleted or rewritten")

    def test_reg_s5(self) -> None:
        """REG-S5

        A gap has an owner, severity, target date and remediation (REG-03).
        Operations: `createGap`, `updateGap`, `getRoadmap`.

        The roadmap line is c8-home-standing-roadmap's: the target date is an `internal`
        item, which the screen marks "Our deadline", naming the gap's owner.
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
        # c8-home-standing-roadmap: the roadmap lists the target date as our own deadline.
        on_roadmap = [item for item in self.client.get("/api/v1/roadmap", {"kind": "internal"}, **owner).json()["items"] if item["id"] == f"gap_target:{gap['id']}"]
        self.assertEqual([(item["kind"], item["itemType"], item["date"]) for item in on_roadmap], [("internal", "gap_target", body["targetDate"])])
        self.assertEqual((on_roadmap[0]["owner"]["person"]["id"], on_roadmap[0]["subject"]["gapId"]), (str(world.owner.id), gap["id"]))
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
        reading = self.client.get(f"{url}/register", **reader).json()["interpretation"]
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

    def test_reg_s10(self) -> None:
        """REG-S10

        Recurring duties appear on the roadmap from recurrence rules (REG-07).
        Operations: `listDuties`, `getRoadmap`, `completeDutyOccurrence`.

        The quarterly duty's occurrence due 2026-12-31 reads back through the duties route and
        on the roadmap for Q4 2026 as "Our deadline" with its owner; completing it generates
        exactly 2027-03-31, which takes its place (x-roadmap-case-deadlines).
        """
        import datetime
        from unittest import mock

        from apps.register import duties
        from apps.register.logic import ensure_register_entry
        from apps.register.models import DutyOccurrence
        from apps.shared import factories

        seed_library()
        a = Bank("reg-s10")
        law = banks_duty()
        library_build.recurring_duty(law, title="Quarterly client asset report", rule="FREQ=MONTHLY;BYMONTH=3,6,9,12;BYMONTHDAY=-1")
        actor = factories.user_actor(label="Sara Lind", user_id=a.officer.id)
        tenancy.activate(a.tenant.id)
        entry = ensure_register_entry(tenant_id=a.tenant.id, obligation_id=law.id, actor=actor)
        TenantObligation.objects.filter(pk=entry.pk).update(first_line_owner=a.officer)
        entry.refresh_from_db()
        # The obligation began to apply at 22:30 UTC on 30 September, 1 October in Stockholm.
        at = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)

        def roadmap(to: str) -> list[Any]:
            """The bank's own deadlines read on 1 October, whatever day the suite runs."""
            with mock.patch("django.utils.timezone.now", return_value=at):
                response = self.client.get(f"/api/v1/roadmap?kind=internal&to={to}", **sign_in(a.officer, tenant=a.tenant))
            self.assertEqual(response.status_code, 200, response.content)
            return [(i["itemType"], i["date"], i["quarter"], i["title"], i["owner"]["person"]["id"], i["subject"]["obligationId"]) for i in response.json()["items"]]

        duties.schedule_first(tenant=a.tenant, actor=actor, targets=[(entry, None)], at=at)

        headers = sign_in(a.officer, tenant=a.tenant)
        [item] = self.client.get(f"/api/v1/obligations/{law.id}/duties", **headers).json()["items"]
        occurrence = item["nextOccurrence"]
        self.assertEqual((item["title"], occurrence["dueDate"], occurrence["status"]), ("Quarterly client asset report", "2026-12-31", "upcoming"))
        # When the roadmap for Q4 2026 is read, then the duty appears with "Our deadline"
        # (an internal item, which the screen marks so) and its owner
        officer, duty = str(a.officer.id), str(law.id)
        self.assertEqual(roadmap("2026-12-31"), [("duty_due", "2026-12-31", "2026-Q4", "Quarterly client asset report", officer, duty)])

        response = self.client.post(
            f"/api/v1/duty-occurrences/{occurrence['id']}/complete", data={}, content_type="application/json", **headers
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["completed"]["status"], response.json()["next"]["dueDate"]), ("done", "2027-03-31"))
        tenancy.activate(a.tenant.id)
        self.assertEqual(
            sorted((row.due_date.isoformat(), row.status) for row in DutyOccurrence.objects.all()),
            [("2026-12-31", "done"), ("2027-03-31", "upcoming")],
        )
        # The completed occurrence leaves the roadmap and the next one takes its place.
        self.assertEqual(roadmap("2027-03-31"), [("duty_due", "2027-03-31", "2027-Q1", "Quarterly client asset report", officer, duty)])

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

    def test_reg_s13(self) -> None:
        """REG-S13

        A tenant lists its clauses and controls as units in its own words (REG-08).
        Operations: `createUnit`, `updateUnit`, `removeUnit`, `pasteUnits`.
        """
        # c8-units-paste-soa
        from apps.register import units as unit_logic
        from apps.register.models import SoaUnit
        from apps.register.tests_units import SoaWorld

        w = SoaWorld(self, "reg-s13")
        # Given Bank AB's conformance row applies, and the officer pastes 12 invented lines
        lines = [{"reference": f"X.{n}", "title": f"Our own words for control {n}"} for n in range(1, 13)]
        # Then a dry run lists the rows it will create and refuses duplicate references and over-long lines
        dry = w.expect(w.paste([*lines, {"reference": "X.1", "title": "Again"}, {"reference": "X.99", "title": "T" * 301}], dry_run=True), 200)
        self.assertEqual([row["outcome"] for row in dry["rows"]], ["will_create"] * 12 + ["refused", "refused"])
        self.assertEqual([row["problem"] for row in dry["rows"][12:]], ["duplicate_reference", "title_too_long"])
        self.assertEqual(w.units(), [])
        # When they commit, then 12 units exist for Bank AB, each with one audit event
        committed = w.expect(w.paste(lines, dry_run=False), 200)
        self.assertEqual(committed["created"], 12)
        created = w.units()
        self.assertEqual({unit.scope.org_unit_id for unit in created}, {w.bank.bank_ab.id})
        self.assertEqual(sorted(e.subject_id for e in w.events(unit_logic.UNIT_CREATED)), sorted(unit.id for unit in created))
        # And the form offers no field for the standard's text and asks for their own words
        path = f"/obligations/{w.standard.id}/units"
        w.expect(w.call("POST", path, {"orgUnitId": str(w.bank.bank_ab.id), "reference": "X.20", "title": "Ours", "standardText": "Theirs"}), 422, "validation_error")
        # When they add a unit for Liv, whose conformance row does not apply: 422
        w.expect(w.call("POST", path, {"orgUnitId": str(w.bank.liv.id), "reference": "X.1", "title": "Ours"}), 422, "scope_not_applicable")
        # When they add a unit under an obligation whose instrument is not a standard: 422
        duty = banks_duty()
        w.expect(
            w.call("POST", f"/obligations/{duty.id}/units", {"orgUnitId": str(w.bank.bank_ab.id), "reference": "X.1", "title": "Ours"}),
            422,
            "units_only_under_standards",
        )
        # When they rename a unit that has an applicability decision: 409, and it is unchanged
        decided, fresh = created[0], created[1]
        w.expect(w.call("PUT", f"/obligations/{w.standard.id}/applicability", {"unitId": str(decided.id), "applicability": "applies", "reason": "Certified"}, version=1), 200)
        w.expect(w.call("PATCH", f"/units/{decided.id}", {"title": "Moved"}, version=2), 409, "unit_has_history")
        self.assertEqual(SoaUnit.objects.get(pk=decided.pk).title, decided.title)
        # And a unit with no history can be renamed with If-Match or removed, each audited
        w.expect(w.call("PATCH", f"/units/{fresh.id}", {"title": "Our better words"}, version=1), 200)
        w.expect(w.call("DELETE", f"/units/{fresh.id}", version=2), 204)
        self.assertEqual([e.subject_id for e in w.events(unit_logic.UNIT_RENAMED)], [fresh.id])
        self.assertEqual([e.subject_id for e in w.events(unit_logic.UNIT_REMOVED)], [fresh.id])

    def test_reg_s14(self) -> None:
        """REG-S14

        Unit decisions are set from the paste in one confirmed call (REG-01, REG-08).
        Operations: `pasteUnits`, `setApplicabilityMany`.
        """
        # c8-units-paste-soa
        from django.test import override_settings

        from apps.register.tests_units import SoaWorld

        w = SoaWorld(self, "reg-s14")
        # Given the officer pastes 93 invented units for Bank AB, each with an answer and a reason
        lines = [
            {"reference": f"A.{n}", "title": f"Our control {n}", "applicability": "applies" if n % 3 else "not_applicable", "reason": f"Reason {n}"}
            for n in range(1, 94)
        ]
        # Then the dry run behind the dialog shows the 93 decisions and stores nothing
        dry = w.expect(w.paste(lines, dry_run=True), 200)
        self.assertEqual((dry["dryRun"], [row["outcome"] for row in dry["rows"]]), (True, ["will_create"] * 93))
        self.assertEqual((w.units(), w.events(APPLICABILITY_SET)), ([], []))
        # When they confirm, then each unit carries its own decision, reason and time
        w.expect(w.paste(lines, dry_run=False), 200)
        stored = {unit.reference: unit for unit in w.units()}
        for line in lines:
            unit = stored[line["reference"]]
            want = "applies" if line["applicability"] == "applies" else "does_not_apply"
            self.assertEqual((unit.applicability, unit.applicability_reason, unit.applicability_decided_by_id), (want, line["reason"], w.officer.id))
            self.assertIsNotNone(unit.applicability_decided_at)
        # And 93 audit events name the officer, each with the value before and after and its reason
        events = w.events(APPLICABILITY_SET)
        self.assertEqual(sorted(e.subject_id for e in events), sorted(unit.id for unit in stored.values()))
        self.assertEqual({e.actor_id for e in events}, {w.officer.id})
        self.assertTrue(all(e.before["applicability"] == "under_assessment" and e.after["reason"] for e in events))
        # And a call with more rows than the configured cap is refused and stores nothing
        more = [{**line, "reference": f"B.{n}"} for n, line in enumerate(lines[:3])]
        with override_settings(REGISTER_BULK_MAX=2):
            w.expect(w.paste(more, dry_run=False), 422, "validation_error")
            rows = [{"obligationId": str(w.standard.id), "unitId": str(unit.id), "applicability": "applies", "reason": "Again"} for unit in list(stored.values())[:3]]
            w.expect(w.call("POST", "/applicability", {"rows": rows}), 422, "validation_error")
        self.assertEqual(len(w.units()), 93)
        self.assertEqual(len(w.events(APPLICABILITY_SET)), 93)

    def test_reg_s15(self) -> None:
        """REG-S15

        The register filtered by standard and entity is the Statement of Applicability (REG-08).
        Operations: `getStatementOfApplicability`, `getHome`.
        """
        # c8-units-paste-soa
        from apps.register.tests_units import SoaWorld

        w = SoaWorld(self, "reg-s15")
        # Given Bank AB's decided units under the standard
        lines = [
            {"reference": "X.2", "title": "Our backups", "applicability": "not_applicable", "reason": "No own data centre"},
            {"reference": "X.1", "title": "Our access rules", "applicability": "applies", "reason": "In the certificate"},
        ]
        w.expect(w.paste(lines, dry_run=False), 200)
        # When the officer filters the register by that standard and by Bank AB
        statement = w.expect(w.call("GET", f"/obligations/{w.standard.id}/statement-of-applicability?entity={w.bank.bank_ab.id}"), 200)
        # Then each unit shows its reference, own title, answer, reason, status, who and when
        self.assertEqual(
            [(u["reference"], u["title"], u["applicability"], u["applicabilityReason"], u["complianceStatus"]["kind"], u["applicabilityDecidedBy"]["name"]) for u in statement["units"]],
            [("X.1", "Our access rules", "applies", "In the certificate", "not_assessed", "Sara Lind"), ("X.2", "Our backups", "not_applicable", "No own data centre", "not_assessed", "Sara Lind")],
        )
        self.assertTrue(all(u["applicabilityDecidedAt"] for u in statement["units"]))
        # And each unit's history lists its applicability decisions with who and when
        self.assertEqual(
            [[(h["applicability"], h["decidedBy"]["id"]) for h in u["history"]] for u in statement["units"]],
            [[("applies", str(w.officer.id))], [("not_applicable", str(w.officer.id))]],
        )
        self.assertTrue(all(h["decidedAt"] for u in statement["units"] for h in u["history"]))
        # And the conformance row shows its own assessed status, and none is computed from the units
        conformance = statement["conformance"]
        self.assertEqual((conformance["orgUnitId"], conformance["applicability"]), (str(w.bank.bank_ab.id), "applies"))
        self.assertEqual(conformance["complianceStatus"]["key"], ComplianceStatus.objects.get(is_default=True).key)
        # And Today's standing counts the standard as one obligation: its one conformance
        # entry, in its own not-assessed category, however many units sit under it
        standing = w.expect(w.call("GET", "/home"), 200)["standing"]
        self.assertEqual((standing["applying"], standing["notAssessed"], standing["compliant"]), (1, 1, 0))
        self.assertEqual(len(w.units()), 2)

    # acc-register-read: the entry's read of the register (apps/register/tests_agent_read.py).
    def test_acc_s4(self) -> None:
        """ACC-S4

        With tenant reach on, an entry reads the register decisions in its scope and nothing else (ACC-04).
        """
        from apps.register.tests_agent_read import ENTRIES, ReadWorld, leaks

        world = ReadWorld(slug="acc-s4")
        # listRegisterEntries: the four decided obligations in scope, each with D-76's fields.
        listed = world.get(self.client, ENTRIES, world.narrow_key)
        self.assertEqual(listed.status_code, 200, listed.content)
        rows = listed.json()["items"]
        self.assertEqual({row["obligationId"] for row in rows}, {str(duty.id) for duty in world.in_scope})
        for row in rows:
            self.assertEqual(row["applicability"], "applies")
            self.assertTrue(row["applicabilityReason"] and row["statusNote"] and row["interpretation"])
            self.assertTrue(row["owner"] and row["process"] and row["system"] and row["nextReviewDate"])
            self.assertEqual({entity["applicability"] for entity in row["entities"]}, {"applies"})
            self.assertTrue(all(entity["applicabilityReason"] and entity["complianceStatus"] for entity in row["entities"]))
            self.assertEqual([item["label"] for item in row["internalItems"]], ["Client asset policy"])
        # No gap, case, assessment, comment, evidence or audit row, and no private record.
        self.assertEqual(leaks(listed.content), [])
        self.assertNotIn(str(world.private.id), listed.content.decode())
        # readRegisterEntry: one in scope reads alone; outside the scope, or private, is 404.
        one = world.get(self.client, f"{ENTRIES}/{world.in_scope[0].id}", world.narrow_key)
        self.assertEqual((one.status_code, leaks(one.content)), (200, []))
        for duty in (world.outside, world.private):
            self.assertEqual(world.get(self.client, f"{ENTRIES}/{duty.id}", world.narrow_key).status_code, 404)

    def test_reg_s17(self) -> None:
        """REG-S17

        The register decides the bank's own obligations as it decides shared ones, and links their controls (OWN-04, OWN-05, REG-01, REG-02, REG-05).

        d89-private-records proves the register half: the obligation the bank's own agent
        found and a second person approved takes applicability and status as a shared one
        does. The controls half is d89-controls' (D-99): the control the agent files beside the
        obligation waits in the bank's own queue and its approval with a passkey links it to
        the obligation's register entry as an internal item of the control kind.
        """
        seed_library()
        seed_term_dimensions()
        seed_authorities()
        bank = Bank("reg-s17")
        approver = factories.member_user(bank.tenant, roles=("approver",))

        @tenancy.tenant_task
        def file_finding(tenant_id: uuid.UUID, body: dict[str, Any]) -> Proposal:
            proposal, _ = proposals_logic.create(
                proposer=proposals_logic.Proposer(actor=factories.agent_actor(label="Scope researcher")), private=True, **filing(body)
            )
            return proposal

        for body in (instrument_body(key="reg-s17-act", officialRef="REG-S17", shortName="REG-S17"), obligation_body(instrument="reg-s17-act", key="reg-s17-duty")):
            tenancy.clear_tenant()
            proposal = file_finding(bank.tenant.id, body)
            approved = self.client.post(
                f"/api/v1/private-proposals/{proposal.id}/approve", data={}, content_type="application/json", **sign_in(approver, tenant=bank.tenant, step_up=True)
            )
            self.assertEqual(approved.status_code, 200, approved.content)
        tenancy.activate(bank.tenant.id)
        duty = Obligation.objects.get(stable_key="reg-s17-duty")
        self.assertEqual(duty.owner_tenant_id, bank.tenant.id)

        # One officer holding applicability.approve sets "Applies" for a legal entity, with a
        # reason and no second approver or step-up; it is stored and audited at once.
        officer = sign_in(bank.officer, tenant=bank.tenant)
        answered = self.client.put(
            f"/api/v1/obligations/{duty.id}/applicability",
            data={"orgUnitId": str(bank.bank_ab.id), "applicability": "applies", "reason": "Our own branch rule"},
            content_type="application/json",
            HTTP_IF_MATCH='"0"',
            **officer,
        )
        self.assertEqual(answered.status_code, 200, answered.content)
        tenancy.activate(bank.tenant.id)
        scope = TenantObligationScope.objects.get(tenant_obligation__obligation=duty, org_unit=bank.bank_ab)
        self.assertEqual((scope.applicability, scope.applicability_reason), (Applicability.APPLIES.value, "Our own branch rule"))
        event = AuditEvent.objects.get(action=APPLICABILITY_SET, subject_id=scope.tenant_obligation_id)
        self.assertEqual((event.tenant_id, event.actor_id, event.step_up_assertion_id), (bank.tenant.id, bank.officer.id, None))

        # Its compliance status is set per legal entity, as a separate fact.
        self.assertEqual(scope.compliance_status.key, "not_assessed")
        stated = self.client.patch(
            f"/api/v1/obligations/{duty.id}/register/entities/{bank.bank_ab.id}",
            data={"complianceStatus": "compliant"},
            content_type="application/json",
            HTTP_IF_MATCH=f'"{scope.version}"',
            **officer,
        )
        self.assertEqual(stated.status_code, 200, stated.content)
        tenancy.activate(bank.tenant.id)
        scope.refresh_from_db()
        self.assertEqual((scope.applicability, scope.compliance_status.key), (Applicability.APPLIES.value, "compliant"))

        # d89-controls: the bank's own agent files the obligation's control, which waits in the
        # bank's own queue until an approver approves it with a passkey.
        tenancy.clear_tenant()
        control = file_finding(bank.tenant.id, control_body(obligation="reg-s17-duty", name="Monthly branch rule check"))
        waiting = self.client.get("/api/v1/private-proposals", **sign_in(approver, tenant=bank.tenant)).json()["items"]
        self.assertIn((str(control.id), "new_control"), [(row["id"], row["kind"]) for row in waiting])
        approved = self.client.post(
            f"/api/v1/private-proposals/{control.id}/approve", data={}, content_type="application/json", **sign_in(approver, tenant=bank.tenant, step_up=True)
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        links = self.client.get(f"/api/v1/obligations/{duty.id}/internal-links", **officer).json()["items"]
        self.assertEqual([(link["label"], link["kind"]["key"]) for link in links], [("Monthly branch rule check", "control")])

        # Nothing of it reaches the search index, and tenant B's fetch answers 404.
        self.assertFalse(SearchChunk.objects.filter(source_id=duty.id).exists())
        other = Bank("reg-s17-b")
        for path in (f"/api/v1/obligations/{duty.id}", f"/api/v1/obligations/{duty.id}/register", f"/api/v1/obligations/{duty.id}/internal-links"):
            refused = self.client.get(path, **sign_in(other.officer, tenant=other.tenant))
            self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"), path)

    def test_reg_s18(self) -> None:
        """REG-S18

        A rule outside a company's licences is not offered for that company (FP-05, REG-01).
        Operations: `createFootprintRequest`, `approveFootprintRequest`.
        """
        seed_library()
        a = Bank("reg-s18")
        approver = factories.member(a.tenant, roles=("approver",)).user
        payments_law = library_build.instrument(key="lob", short_name="LOB", regime="regime:payments")
        aml_law = library_build.instrument(key="pvml", short_name="PVML", regime="regime:aml")
        payments_only = library_build.obligation(payments_law, key="lob-safeguarding", terms=("regime:payments",))
        payments_and_securities = library_build.obligation(payments_law, key="lob-client-money", terms=("regime:payments", "regime:securities"))
        aml = library_build.obligation(aml_law, key="pvml-kyc", terms=("regime:aml",))
        excluded = [{"orgUnitId": str(a.fonder.id), "dimension": "regime", "key": key} for key in ("banking", "insurance", "payments")]
        created = self.client.post(
            "/api/v1/tenant/footprint/requests",
            data={"entityExclusions": excluded},
            content_type="application/json",
            **sign_in(a.officer, tenant=a.tenant),
        )
        self.assertEqual(created.status_code, 201, created.content)
        approved = self.client.post(
            f"/api/v1/tenant/footprint/requests/{created.json()['id']}/approve",
            data={},
            content_type="application/json",
            **sign_in(approver, tenant=a.tenant, step_up=True),
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        tenancy.activate(a.tenant.id)
        spanned = {
            key: {entity.name for entity in entities}
            for key, entities in (
                (row.stable_key, entities_spanned([row.id])[row.id]) for row in (payments_only, payments_and_securities, aml)
            )
        }
        everyone = {"Example Bank AB", "Example Fonder AB", "Example Liv Försäkring AB"}
        self.assertEqual(spanned["lob-safeguarding"], everyone - {"Example Fonder AB"})
        self.assertEqual(spanned["lob-client-money"], everyone, "securities is still in Fonder's scope")
        self.assertEqual(spanned["pvml-kyc"], everyone, "a cross-cutting term is never excluded")
        # The bank's own scope and every other bank are untouched.
        self.assertFalse(FootprintTerm.objects.exists())
        b = Bank("reg-s18-b")
        tenancy.activate(b.tenant.id)
        self.assertEqual({entity.name for entity in entities_spanned([payments_only.id])[payments_only.id]}, everyone)

    def test_reg_s19(self) -> None:
        """REG-S19

        What applies lists, per company, the obligations its licences leave in span, with the
        answer so far (REG-01, FP-05).
        Operations: `listApplicabilityCompanies`, `listApplicabilityRegulations`,
        `listApplicabilityRows`, `getInstrumentApplicability`.
        """
        seed_library()
        a = Bank("reg-s19")
        approver = factories.member(a.tenant, roles=("approver",)).user
        securities_law = library_build.instrument(key="s19-lvm", short_name="LVM", regime="regime:securities")
        payments_law = library_build.instrument(key="s19-lob", short_name="LOB", regime="regime:payments")
        shared = library_build.obligation(securities_law, key="s19-lvm-1", ref_label="1 §", terms=("legal_entity:bank", "legal_entity:fund_company"))
        banks_alone = library_build.obligation(securities_law, key="s19-lvm-2", ref_label="2 §", terms=("legal_entity:bank",))
        library_build.obligation(payments_law, key="s19-lob-1", ref_label="1 §")
        officer = sign_in(a.officer, tenant=a.tenant)
        created = self.client.post(
            "/api/v1/tenant/footprint/requests",
            data={"entityExclusions": [{"orgUnitId": str(a.fonder.id), "dimension": "regime", "key": "payments"}]},
            content_type="application/json",
            **officer,
        )
        self.assertEqual(created.status_code, 201, created.content)
        approved = self.client.post(
            f"/api/v1/tenant/footprint/requests/{created.json()['id']}/approve",
            data={},
            content_type="application/json",
            **sign_in(approver, tenant=a.tenant, step_up=True),
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        bank, fonder = str(a.bank_ab.id), str(a.fonder.id)
        for duty, body in (
            (shared, {"orgUnitId": bank, "applicability": "applies", "reason": "Holds client assets"}),
            (banks_alone, {"applicability": "not_applicable", "reason": "No large exposures"}),
        ):
            answered = self.client.put(f"/api/v1/obligations/{duty.id}/applicability", data=body, content_type="application/json", **officer)
            self.assertEqual(answered.status_code, 200, answered.content)

        def stored() -> tuple[int, int, int]:
            tenancy.activate(a.tenant.id)
            return TenantObligation.objects.count(), TenantObligationScope.objects.count(), AuditEvent.objects.filter(action__startswith="register.").count()

        before = stored()
        member = sign_in(a.owner, tenant=a.tenant)

        def read(path: str, **params: str) -> Any:
            response = self.client.get(f"/api/v1{path}", params, **member)
            self.assertEqual(response.status_code, 200, response.content)
            return response.json()

        # Each company with what the register offers for it and how its answers stand.
        self.assertEqual(
            [(row["orgUnit"]["name"], row["offered"], row["applies"], row["notApplicable"], row["underAssessment"]) for row in read("/applicability/companies")],
            [("Example Bank AB", 3, 1, 1, 1), ("Example Fonder AB", 1, 0, 0, 1), ("Example Liv Försäkring AB", 1, 0, 0, 1)],
        )
        # Payments is outside the fund company's own scope, so its regulation is not listed for it.
        regulations = {entity: [row["instrument"]["key"] for row in read("/applicability/regulations", orgUnitId=entity)["items"]] for entity in (bank, fonder)}
        self.assertEqual(regulations, {bank: ["s19-lob", "s19-lvm"], fonder: ["s19-lvm"]})
        rows = {entity: read("/applicability/rows", orgUnitId=entity, instrument="s19-lvm")["items"] for entity in (bank, fonder)}
        self.assertEqual(
            [(row["obligationId"], row["orgUnitId"], row["applicability"], row["reason"], row["version"]) for row in rows[bank]],
            [(str(shared.id), bank, "applies", "Holds client assets", 1), (str(banks_alone.id), None, "not_applicable", "No large exposures", 2)],
        )
        self.assertEqual(
            [(row["obligationId"], row["orgUnitId"], row["applicability"], row["reason"], row["version"]) for row in rows[fonder]],
            [(str(shared.id), fonder, "under_assessment", None, 0)],
        )
        # Never a suggested answer: a row is the answer so far and what an answer must name.
        self.assertEqual(
            set(rows[bank][0]), {"obligationId", "refLabel", "title", "orgUnitId", "applicability", "reason", "decidedAt", "decidedBy", "version", "matchedTerms"}
        )
        rolled = read(f"/instruments/{securities_law.id}/applicability")
        self.assertEqual((rolled["inScope"], rolled["applies"], rolled["notApplicable"], rolled["underAssessment"]), (2, 1, 1, 0))
        for answer, count in (("applies", "applies"), ("not_applicable", "notApplicable"), ("under_assessment", "underAssessment")):
            self.assertEqual(rolled[count], read("/obligations", instrument="s19-lvm", applicability=answer)["total"], answer)
        self.assertEqual(sum(row["count"] for row in rolled["statuses"]), rolled["applies"])
        self.assertEqual([row["orgUnit"]["name"] for row in rolled["companies"]], ["Example Bank AB", "Example Fonder AB"])
        self.assertEqual(stored(), before, "a read stores nothing and writes no audit event")

    def test_reg_s20(self) -> None:
        """REG-S20

        A whole company's unanswered obligations are decided in one confirmed run (REG-01, AC-REG1).
        Operations: `decideAllApplicability`, `readDecideAllApplicability`.

        The dialog is the screen's. Here the confirmed call lists what nobody has answered and
        answers at once; the worker, eager in tests and held back until a colleague has
        answered one row, then sets the rest through the door of a single answer.
        """
        seed_library()
        cache.clear()
        a = Bank("reg-s20")
        colleague = factories.member(a.tenant, roles=("compliance_officer",), user_row=factories.user(name="Erik Holm")).user
        law = library_build.instrument(key="s20-lvm", short_name="LVM", regime="regime:securities")
        earlier, first, second, third = (library_build.obligation(law, key=f"s20-lvm-{number}", ref_label=f"{number} §") for number in range(1, 5))
        bank, reason = str(a.bank_ab.id), "Covered by the bank's securities licence"
        officer = sign_in(a.officer, tenant=a.tenant)

        def answer(headers: dict[str, Any], duty: Obligation, body: dict[str, Any]) -> dict[str, Any]:
            stored = self.client.put(f"/api/v1/obligations/{duty.id}/applicability", data={"orgUnitId": bank, **body}, content_type="application/json", **headers)
            self.assertEqual(stored.status_code, 200, stored.content)
            row: dict[str, Any] = stored.json()
            return row

        def on_the_page(duty: Obligation) -> tuple[Any, ...]:
            """What the obligation page shows for Example Bank AB."""
            [row] = self.client.get(f"/api/v1/obligations/{duty.id}/register", **officer).json()["entities"]
            return row["orgUnitId"], row["applicability"], row["applicabilityReason"], row["applicabilityDecidedBy"]["name"], row["version"]

        before = answer(officer, earlier, {"applicability": "not_applicable", "reason": "No such business"})
        read = self.client.get("/api/v1/applicability/companies", **officer).json()[0]
        self.assertEqual((read["orgUnit"]["name"], read["offered"], read["toDecide"]), ("Example Bank AB", 4, 3))

        # The confirmed call: the company, the answer and one reason. It lists the three
        # nobody has answered and answers before anything is set.
        with mock.patch.object(register_tasks.decide_listed, "delay") as queued, self.captureOnCommitCallbacks(execute=True):
            started = self.client.post(
                "/api/v1/applicability/decide-all", data={"orgUnitId": bank, "applicability": "applies", "reason": reason}, content_type="application/json", **officer
            )
        self.assertEqual(started.status_code, 202, started.content)
        self.assertEqual((started.json()["status"], started.json()["total"], started.json()["set"]), ("running", 3, 0))

        # A colleague answers one of them after the start and before the worker reaches it.
        theirs = answer(sign_in(colleague, tenant=a.tenant), second, {"applicability": "not_applicable", "reason": "Handled by the group"})
        with self.captureOnCommitCallbacks(execute=True):
            register_tasks.decide_listed(*queued.call_args.args)
        run = self.client.get("/api/v1/applicability/decide-all", **officer).json()
        self.assertEqual((run["status"], run["total"], run["set"], run["skipped"], run["refused"], run["stopped"]), ("finished", 3, 2, 1, 0, None))

        # Each row the run set has its own audit event naming the officer and the reason,
        # beside the one row for the decision, which names the count and never the reason.
        tenancy.activate(a.tenant.id)
        events = list(AuditEvent.objects.filter(action=APPLICABILITY_SET, after__reason=reason))
        self.assertEqual(sorted(event.after["obligationId"] for event in events), sorted(str(duty.id) for duty in (first, third)))
        self.assertEqual({(event.actor_id, event.actor_label, event.before["applicability"]) for event in events}, {(a.officer.id, "Sara Lind", "under_assessment")})
        [decision] = AuditEvent.objects.filter(action=decide_all.STARTED)
        self.assertEqual((decision.actor_id, decision.after["count"], decision.after["applicability"]), (a.officer.id, 3, "applies"))
        self.assertNotIn(reason, str([decision.after, decision.summary]))

        # What was answered before the run, and the colleague's answer, are as they were.
        self.assertEqual(on_the_page(earlier), (bank, "not_applicable", "No such business", "Sara Lind", before["version"]))
        self.assertEqual(on_the_page(second), (bank, "not_applicable", "Handled by the group", "Erik Holm", theirs["version"]))
        # And the obligation page shows the run's answer on the others.
        for duty in (first, third):
            self.assertEqual(on_the_page(duty)[:4], (bank, "applies", reason, "Sara Lind"))
        after = self.client.get("/api/v1/applicability/companies", **officer).json()[0]
        self.assertEqual((after["applies"], after["notApplicable"], after["toDecide"]), (2, 2, 0))
        self.assertFalse(AuditEvent.objects.filter(action=decide_all.STOPPED).exists(), "a run that finished whole says nothing more")

        # A later run whose worker fails part way: the failure hook, as Celery calls it once the
        # chunk's transaction has rolled back, ends it and records that it stopped.
        fifth = library_build.obligation(law, key="s20-lvm-5", ref_label="5 §")
        with mock.patch.object(register_tasks.decide_listed, "delay") as queued, self.captureOnCommitCallbacks(execute=True):
            self.client.post("/api/v1/applicability/decide-all", data={"orgUnitId": bank, "applicability": "applies", "reason": reason}, content_type="application/json", **officer)
        with mock.patch.object(applicability, "_store", side_effect=OperationalError("could not serialize access")), self.assertRaises(OperationalError):
            register_tasks.decide_listed(*queued.call_args.args)
        register_tasks.decide_listed.on_failure(OperationalError("could not serialize access"), "task-id", queued.call_args.args, {}, None)
        run = self.client.get("/api/v1/applicability/decide-all", **officer).json()
        self.assertEqual((run["status"], run["total"], run["set"], run["stopped"]), ("finished", 1, 0, "failed"))
        tenancy.activate(a.tenant.id)
        [stopped] = AuditEvent.objects.filter(action=decide_all.STOPPED)
        self.assertEqual((stopped.actor_id, stopped.subject_id), (a.officer.id, a.bank_ab.id))
        self.assertEqual(stopped.after, {"stopped": "failed", "set": 0, "skipped": 0, "refused": 0, "left": 1})
        self.assertNotIn(reason, str([stopped.after, stopped.summary]))
        self.assertIsNone(TenantObligationScope.objects.filter(tenant_obligation__obligation=fifth, org_unit=a.bank_ab).first())

    def test_reg_s23(self) -> None:
        """REG-S23

        AI drafts the reason from the licence facts alone, and the person stands behind it
        (REG-01, D-143).
        Operations: `draftApplicabilityReason`, `setApplicability`.
        """
        seed_library()
        library_build.authority(key=FI, short_name="FI")
        a = Bank("reg-s23")
        law = library_build.instrument(key="s23-lvm", short_name="LVM", official_ref="SFS 2007:528", regime="regime:securities")
        duty = library_build.obligation(law, key="s23-lvm-1", ref_label="8 kap. 11 §", titles={"en": "Keep client assets apart"})
        register_facts(a.tenant, a.bank_ab, "556000-0001")
        officer = sign_in(a.officer, tenant=a.tenant)

        # Asked for a draft of "Applies" for Example Bank AB on one obligation: the server
        # reads the licence facts and the library's facts, and nothing typed or named.
        original = MockLlm.stream
        with mock.patch.object(MockLlm, "stream", autospec=True, side_effect=original) as model:
            drafted = Client().post(
                "/api/v1/applicability/reason-draft",
                data={"orgUnitId": str(a.bank_ab.id), "obligationIds": [str(duty.id)], "applicability": "applies"},
                content_type="application/json",
                **officer,
            )
        self.assertEqual(drafted.status_code, 200, drafted.content)
        draft = drafted.json()
        self.assertTrue(draft["aiGenerated"])
        prompt = model.call_args.kwargs["prompt"]
        self.assertIn("Tillstånd att driva bankrörelse", prompt)
        self.assertIn("Keep client assets apart", prompt)
        for name in ("Example Bank AB", a.tenant.name, "Sara Lind"):
            self.assertNotIn(name, prompt)
        tenancy.activate(a.tenant.id)
        row = AiGeneration.objects.get(pk=draft["generationId"])
        self.assertEqual((row.purpose, row.asker_id, row.status), (AiPurpose.REASON_DRAFT.value, a.officer.id, "draft"))

        # The officer sets the answer with the draft as it stood: the log row reads confirmed
        # in their name, and the decision's audit event names the draft.
        stored = self.client.put(
            f"/api/v1/obligations/{duty.id}/applicability",
            data={"orgUnitId": str(a.bank_ab.id), "applicability": "applies", "reason": draft["text"], "reasonDraftId": draft["generationId"]},
            content_type="application/json",
            **officer,
        )
        self.assertEqual(stored.status_code, 200, stored.content)
        tenancy.activate(a.tenant.id)
        row.refresh_from_db()
        self.assertEqual((row.status, row.reviewed_by_id), ("confirmed", a.officer.id))
        [event] = AuditEvent.objects.filter(action=APPLICABILITY_SET, after__obligationId=str(duty.id))
        self.assertEqual(event.after["reasonDraft"], {"generationId": draft["generationId"], "review": "confirmed"})
        self.assertEqual(event.after["reason"], draft["text"])
