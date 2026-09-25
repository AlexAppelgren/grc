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
from django.test import TestCase

from apps.cases import creation, state, testing as case_build
from apps.cases.models import ChangeCase
from apps.cases.tests_creation import cases_of, drain, registered
from apps.cases.tests_triage import CaseMoves, triage_bank
from apps.shared import tenancy
from apps.shared.testing import ScenarioTestCase
from apps.taxonomy.models import CaseStatusCategory, Urgency
from apps.watch import testing as watch_build


class CasesScenarioTests(TestCase):
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

    @skip("pending: CAS-S8")
    def test_cas_s8(self) -> None:
        """CAS-S8

        Sign-off is refused while actions are open or evidence is missing (CAS-06, AC-CAS1).
        """

    @skip("pending: CAS-S9")
    def test_cas_s9(self) -> None:
        """CAS-S9

        The requester cannot sign off their own case (CAS-06, AC-CAS1).
        """

    @skip("pending: CAS-S10")
    def test_cas_s10(self) -> None:
        """CAS-S10

        A second person signs off with step-up and the inventory is untouched (CAS-06).
        """

    @skip("pending: CAS-S11")
    def test_cas_s11(self) -> None:
        """CAS-S11

        The case file stands alone as text and as an export (CAS-07).
        """

    @skip("pending: CAS-S12")
    def test_cas_s12(self) -> None:
        """CAS-S12

        Every response lists allowed transitions and an invalid one is refused (CAS-08).
        """

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

    @skip("pending: CAS-S17 (CAS-03, COL-04, chunk 9)")
    def test_cas_s17(self) -> None:
        """CAS-S17

        Contributor teams are the case's team participants (CAS-03, COL-04).
        """


class TriageScenarioTests(CaseMoves, ScenarioTestCase):
    """Triage, dismissal, restore and the one-person close (c9-triage), through the
    scenario client, which fails any write that leaves no audit row."""

    def test_cas_s2(self) -> None:
        """CAS-S2

        Triage needs an urgency and an owner (CAS-02).
        """
        bank = triage_bank()
        no_owner = self.move(bank, "triage", {"urgency": "within_3_months"})
        self.assertEqual(no_owner.status_code, 422, no_owner.content)
        self.assertTrue(any(error["field"].endswith("ownerId") for error in no_owner.json()["errors"]))

        triaged = self.move(bank, "triage", {"urgency": "within_3_months", "ownerId": str(bank.owner.id)})
        self.assertEqual(triaged.status_code, 200, triaged.content)
        self.assertEqual(triaged.json()["status"], "assigned")
        self.assertEqual(triaged.json()["owner"]["id"], str(bank.owner.id))
        self.assertEqual(self.told(bank), [bank.owner.id], "the owner is notified, once")
        # The pill's tone follows the key's fixed severity ordinal, never the response.
        urgency = triaged.json()["urgency"]
        self.assertIsNone(urgency["kind"])
        self.assertEqual(Urgency.objects.get(key=urgency["key"]).kind, "warning")

    def test_cas_s3(self) -> None:
        """CAS-S3

        Dismissal needs a reason and can be restored (CAS-02).
        """
        bank = triage_bank()
        self.assertEqual(self.move(bank, "dismiss", {}).status_code, 422)

        dismissed = self.move(bank, "dismiss", {"reasonKey": "out_of_scope"})
        self.assertEqual(dismissed.status_code, 200, dismissed.content)
        self.assertEqual(dismissed.json()["status"], "dismissed")
        self.assertEqual(dismissed.json()["dismissedReason"]["label"], "Out of scope")
        self.assertFalse(state.is_open(CaseStatusCategory(dismissed.json()["status"])), "absent from the open list")

        restored = self.move(bank, "restore", None)
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual(restored.json()["status"], "new")
        trail = self.moves_audited(bank)
        self.assertEqual([(row.before["status"], row.after["status"]) for row in trail], [("new", "dismissed"), ("dismissed", "new")])
        self.assertEqual({row.actor_id for row in trail}, {bank.officer.id})

    def test_cas_s19(self) -> None:
        """CAS-S19

        One person closes a case that needs no work, audited, and can restore it (CAS-02; D-92).
        """
        bank = triage_bank()
        case_build.in_category(bank.case, CaseStatusCategory.ASSIGNED)
        note = "Covered by the 2025 research policy review."

        refused = self.move(bank, "close", {"reasonKey": "signed_off"}, who=bank.owner)
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(refused.json()["code"], "four_eyes_violation")

        closed = self.move(bank, "close", {"reasonKey": "no_action", "note": note}, who=bank.owner)
        self.assertEqual(closed.status_code, 200, closed.content)
        self.assertEqual(closed.json()["status"], "closed")
        self.assertEqual(closed.json()["closeReason"]["key"], "no_action")
        self.assertEqual(closed.json()["closedNote"], note)
        [audited] = self.moves_audited(bank)
        self.assertEqual((audited.actor_id, audited.after["reasonKey"]), (bank.owner.id, "no_action"))
        self.assertNotIn(note, str(audited.after), "the note never reaches the audit values")

        restored = self.move(bank, "restore", None)
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual(restored.json()["status"], "new")
        self.assertEqual(self.ledger(bank), [("assigned", "closed", bank.owner.id), ("closed", "new", bank.officer.id)])

        waiting = triage_bank()
        case_build.in_category(waiting.case, CaseStatusCategory.SIGNOFF)
        with transaction.atomic():
            tenancy.activate(waiting.tenant.id)
            ChangeCase.objects.filter(pk=waiting.case.id).update(signoff_requested_by=waiting.owner)
        door = self.move(waiting, "close", {"reasonKey": "no_action"})
        self.assertEqual(door.status_code, 409, door.content)
        self.assertEqual(door.json()["code"], "invalid_transition")
