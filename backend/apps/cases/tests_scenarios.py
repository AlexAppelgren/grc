"""Scenario stubs for the cases app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: CAS.

Operations each pending scenario exercises once its logic lands (the audit-on-write guard
reads these names; c9-case-contract declared them): CAS-S2 triageChange, CAS-S3
dismissChange and restoreChange, CAS-S4 startAssessment, saveAssessment and
closeWithoutAction, CAS-S6 addAction, updateAction and deleteAction, CAS-S7 addEvidence and
removeEvidence, CAS-S8 requestSignoff, CAS-S10 approveSignoff, CAS-S18 sendBackSignoff.
"""

from unittest import skip

from django.db import transaction
from django.utils import timezone

from apps.cases import creation, logic, state, testing as case_build
from apps.cases import tests_signoff as signoff_build
from apps.cases.models import Action, CaseTransition
from apps.cases.tests_creation import cases_of, drain, registered
from apps.shared import tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import testing as watch_build


class CasesScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.cases, one method per @integration scenario."""

    def test_cas_s1(self) -> None:
        """CAS-S1

        A change creates one case per tenant in "Needs triage" with its footprint match (CAS-01).
        """
        creation.register()
        watch_build.seed_watch_reference()
        banks = case_build.two_tenants_with_different_footprints(
            inside="regime:securities", outside="regime:aml"
        )
        drain()
        change = watch_build.change_with_timeline(terms=("regime:securities",))
        registered(change.id, title=change.title)
        drain()

        self.assertEqual(
            watch_build.cases_per_tenant(change, [banks.inside, banks.outside]),
            {banks.inside: 1, banks.outside: 1},
            "every bank gets exactly one case for a registered change",
        )
        for bank, matches in ((banks.inside, True), (banks.outside, False)):
            with self.subTest(bank=bank.slug):
                case = cases_of(bank)[0]
                self.assertEqual(case.status, CaseStatusCategory.NEW.value)
                self.assertEqual(case.footprint_match, matches, "each case caches its own bank's verdict")

        registered(change.id, title=change.title)
        drain()
        self.assertEqual(
            watch_build.cases_per_tenant(change, [banks.inside, banks.outside]),
            {banks.inside: 1, banks.outside: 1},
            "registering the same change again leaves each bank with the one case it had",
        )

    @skip("pending: CAS-S2")
    def test_cas_s2(self) -> None:
        """CAS-S2

        Triage needs an urgency and an owner (CAS-02).
        """

    @skip("pending: CAS-S3")
    def test_cas_s3(self) -> None:
        """CAS-S3

        Dismissal needs a reason and can be restored (CAS-02).
        """

    @skip("pending: CAS-S4")
    def test_cas_s4(self) -> None:
        """CAS-S4

        The impact assessment records what applies and what must change (CAS-03).
        """

    @skip("pending: CAS-S5")
    def test_cas_s5(self) -> None:
        """CAS-S5

        Two people saving the same assessment: the second receives stale_write (CAS-03, CAS-08, AC-CAS2).
        """

    @skip("pending: CAS-S6")
    def test_cas_s6(self) -> None:
        """CAS-S6

        Actions have an owner and due date, lock during sign-off and export as tickets (CAS-04).
        """

    @skip("pending: CAS-S7")
    def test_cas_s7(self) -> None:
        """CAS-S7

        Evidence is scanned, hashed and streamed through permission checks (CAS-05).
        """

    def test_cas_s8(self) -> None:
        """CAS-S8

        Sign-off is refused while actions are open or evidence is missing (CAS-06, AC-CAS1).
        """
        bank = signoff_build.Bank()
        action = bank.action(done=False)
        response = bank.post(self.client, "request", bank.owner)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "open_actions"))

        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            Action.objects.filter(pk=action.pk).update(done_at=timezone.now(), done_by=bank.owner)
        response = bank.post(self.client, "request", bank.owner)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "evidence_missing"))

        bank.evidence("clean")
        response = bank.post(self.client, "request", bank.owner)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "signoff", "the category that reads \"Waiting for sign-off\"")

    def test_cas_s9(self) -> None:
        """CAS-S9

        The requester cannot sign off their own case (CAS-06, AC-CAS1).
        """
        bank = signoff_build.Bank()
        bank.ready_for_signoff(self.client)
        response = bank.post(self.client, "approve", bank.owner, body={"note": ""}, step_up=True)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "four_eyes_violation")
        self.assertEqual(response.json()["detail"], "A second person must sign off.")
        self.assertEqual(bank.fresh().status, CaseStatusCategory.SIGNOFF.value)

    def test_cas_s10(self) -> None:
        """CAS-S10

        A second person signs off with step-up and the inventory is untouched (CAS-06).
        """
        bank = signoff_build.Bank()
        bank.ready_for_signoff(self.client)
        response = bank.post(self.client, "approve", bank.approver, body={"note": ""}, step_up=False)
        self.assertEqual((response.status_code, response.json()["code"]), (403, "step_up_required"))

        before = signoff_build.inventory_snapshot()
        response = bank.post(self.client, "approve", bank.approver, body={"note": "Checked."}, step_up=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "closed")
        case = bank.fresh()
        audit = AuditEvent.objects.filter(subject_id=case.id, after__status="closed").get()
        self.assertIsNotNone(audit.step_up_assertion_id, "the audit event carries the assertion")
        self.assertEqual(signoff_build.inventory_snapshot(), before, "no library or register row changed")

    @skip("pending: CAS-S11")
    def test_cas_s11(self) -> None:
        """CAS-S11

        The case file stands alone as text and as an export (CAS-07).
        """

    def test_cas_s12(self) -> None:
        """CAS-S12

        Every response lists allowed transitions and an invalid one is refused (CAS-08).
        """
        bank = signoff_build.Bank()
        case_build.in_category(bank.case, CaseStatusCategory.ASSESSING)
        read = self.client.get(f"/api/v1/changes/{bank.case.change_id}", **sign_in(bank.approver, tenant=bank.tenant))
        self.assertEqual(read.status_code, 200)
        case = bank.fresh()
        machine = state.allowed_transitions(CaseStatusCategory.ASSESSING, logic.case_facts(case, actor=bank.approver.id))
        self.assertEqual(read.json()["case"]["allowedTransitions"], [category.value for category in machine])

        response = bank.post(self.client, "approve", bank.approver, body={"note": ""}, step_up=True)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "invalid_transition"))
        self.assertEqual(bank.fresh().status, CaseStatusCategory.ASSESSING.value)

    @skip("pending: CAS-S13")
    def test_cas_s13(self) -> None:
        """CAS-S13

        Sub-statuses inside a category leave the guards untouched (CAS-02, VOC-04).
        """

    @skip("pending: CAS-S16")
    def test_cas_s16(self) -> None:
        """CAS-S16

        Another tenant's case and evidence answer 404 (CAS-05, CAS-07, NFR-01).
        """

    def test_cas_s18(self) -> None:
        """CAS-S18

        Send-back returns a case to implementing and a fresh request is possible (CAS-06, CAS-08).
        """
        bank = signoff_build.Bank()
        bank.action(done=True)
        bank.ready_for_signoff(self.client)
        response = bank.post(self.client, "send-back", bank.approver, body={"note": "Attach the desk's signature."})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "implementing", "the actions' lock reads this category, so they unlock")
        case = bank.fresh()
        self.assertIsNone(case.signoff_requested_by_id)
        moved = CaseTransition.objects.filter(case=case, to_status="implementing", from_status="signoff").get()
        self.assertEqual(moved.note, "Attach the desk's signature.", "the note is on the case's trail")

        response = bank.post(self.client, "request", bank.owner)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "signoff")

    @skip("pending: CAS-S17 (CAS-03, COL-04, chunk 9)")
    def test_cas_s17(self) -> None:
        """CAS-S17

        Contributor teams are the case's team participants (CAS-03, COL-04).
        """
