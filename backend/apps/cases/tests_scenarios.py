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

from django.test import TestCase

from apps.cases import creation, testing as case_build
from apps.cases.tests_creation import cases_of, drain, registered
from apps.taxonomy.models import CaseStatusCategory
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

    def test_cas_s4(self) -> None:
        """CAS-S4

        The impact assessment records what applies and what must change (CAS-03).
        """
        from apps.cases.tests_assessment import AssessmentClient, bank_with_a_case, body

        bank = bank_with_a_case(CaseStatusCategory.ASSIGNED)
        calls = AssessmentClient(self, bank)

        started = calls.start()
        self.assertEqual(started.status_code, 200, started.content)
        self.assertEqual(started.json()["status"], CaseStatusCategory.ASSESSING.value)
        self.assertEqual(started.json()["assessment"]["version"], 1)

        saved = calls.save(body())
        self.assertEqual(saved.status_code, 200, saved.content)
        answer = saved.json()
        self.assertEqual(answer["status"], CaseStatusCategory.ASSESSING.value, "saving moves no state")
        stored = answer["assessment"]
        self.assertEqual(
            {name: stored[name] for name in ("applies", "why", "whatMustChange", "internalDeadline")},
            {name: body()[name] for name in ("applies", "why", "whatMustChange", "internalDeadline")},
        )
        self.assertEqual(stored["effort"]["key"], "m", "the effort is a key of the bank's list")

        without_why = calls.save(body(why=""))
        self.assertEqual(without_why.status_code, 422)

        refused = calls.save(body(applies="no"), bank.contributor)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["requiredPermission"], "cases.work")

        closed = calls.save(body(applies="no"))
        self.assertEqual(closed.status_code, 200, closed.content)
        self.assertEqual(closed.json()["status"], CaseStatusCategory.CLOSED.value)
        self.assertEqual(closed.json()["closeReason"]["kind"], "not_applicable")
        self.assertIn(CaseStatusCategory.NEW.value, closed.json()["allowedTransitions"], "restorable to triage")

    def test_cas_s5(self) -> None:
        """CAS-S5

        Two people saving the same assessment: the second receives stale_write (CAS-03, CAS-08, AC-CAS2).
        """
        from apps.cases.tests_assessment import OTHER_WHY, WHY, AssessmentClient, bank_with_a_case, body

        bank = bank_with_a_case(CaseStatusCategory.ASSESSING)
        calls = AssessmentClient(self, bank)
        loaded = calls.version()  # the owner and the contributor both read this version

        first = calls.save(body(), bank.owner, if_match=loaded)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["version"], loaded + 1)

        second = calls.save(body(why=OTHER_WHY), bank.contributor, if_match=loaded)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "stale_write")
        self.assertEqual(second.json()["currentVersion"], loaded + 1, "the screen reloads to this version")
        self.assertEqual(calls.assessment().why, WHY, "never merged")

    def test_cas_s6(self) -> None:
        """CAS-S6

        Actions have an owner and a due date, are locked in sign-off and are removed softly
        (CAS-04, CAS-08). The ticket export is chunk 13's (INT-S3). c9-actions.
        """
        import datetime
        from typing import Any

        from django.utils import timezone

        from apps.cases import logic
        from apps.cases.models import Action, ChangeCase, Evidence, EvidenceKind
        from apps.cases.tests_actions import assessing
        from apps.shared import factories, tenancy
        from apps.shared.audit import Actor, ActorType
        from apps.shared.models import AuditEvent
        from apps.shared.testing import sign_in
        from apps.taxonomy.models import CaseSubStatus

        tenant = factories.tenant()
        owner = factories.member(tenant, roles=("compliance_officer",)).user
        case = assessing(tenant, owner)
        actions_url = f"/api/v1/changes/{case.change_id}/actions"
        due = timezone.localdate() + datetime.timedelta(days=10)

        def add(body: dict[str, object]) -> Any:
            tenancy.activate(tenant.id)
            version = ChangeCase.objects.get(pk=case.pk).version
            return self.client.post(
                actions_url, data=body, content_type="application/json", HTTP_IF_MATCH=str(version), **sign_in(owner, tenant=tenant)
            )

        def open_count() -> int:
            tenancy.activate(tenant.id)
            return logic.case_facts(ChangeCase.objects.get(pk=case.pk), actor=None).open_action_count

        # "Add action" with a title and a due date and no owner.
        first = add({"title": "Document the research quality criteria", "dueDate": due.isoformat()})
        self.assertEqual(first.status_code, 201, first.content)
        listed = self.client.get(actions_url, **sign_in(owner, tenant=tenant)).json()["items"]
        self.assertEqual([(row["id"], row["dueDate"], row["owner"]["id"]) for row in listed], [(first.json()["id"], due.isoformat(), str(owner.id))])
        tenancy.activate(tenant.id)
        self.assertEqual(ChangeCase.objects.get(pk=case.pk).status, CaseStatusCategory.IMPLEMENTING.value)

        # Without a title, or for someone outside the bank.
        self.assertEqual(add({"title": "", "dueDate": due.isoformat()}).status_code, 422)
        stranger = add({"title": "Train the desk", "dueDate": due.isoformat(), "ownerId": str(factories.user().id)})
        self.assertEqual((stranger.status_code, stranger.json()["code"]), (422, "unknown_member"))
        second = add({"title": "Train the desk", "dueDate": due.isoformat()}).json()

        # The case moves to waiting for sign-off, through the real move, under a sub-status.
        tenancy.activate(tenant.id)
        Action.objects.filter(case=case).update(done_at=timezone.now(), done_by=owner)
        Evidence.objects.create(
            tenant=tenant, case=case, kind=EvidenceKind.LINK.value, name="Criteria memo",
            url="https://intranet.example.com/memo/7", uploaded_by=owner, scan_state="clean", scanned_at=timezone.now(),
        )
        moving = logic.load_case(tenant, case.change_id, for_update=True)
        moving.signoff_requested_by, moving.signoff_requested_at = owner, timezone.now()
        who = Actor(kind=ActorType.USER, id=owner.id, label=owner.name)
        logic.transition(moving, CaseStatusCategory.SIGNOFF, actor=who, user=owner)
        ChangeCase.objects.filter(pk=case.pk).update(sub_status=CaseSubStatus.objects.get(tenant=tenant, key="signoff"))
        headers = {**sign_in(owner, tenant=tenant), "HTTP_IF_MATCH": "1"}
        for response in (
            add({"title": "Late", "dueDate": due.isoformat()}),
            self.client.patch(f"/api/v1/actions/{second['id']}", data={"done": False}, content_type="application/json", **headers),
            self.client.delete(f"/api/v1/actions/{second['id']}", **headers),
        ):
            self.assertEqual((response.status_code, response.json()["code"]), (409, "actions_locked"))
        self.assertEqual(self.client.get(actions_url, **sign_in(owner, tenant=tenant)).status_code, 200)

        # Sent back, the owner reopens one action and removes it.
        tenancy.activate(tenant.id)
        back = logic.load_case(tenant, case.change_id, for_update=True)
        logic.transition(back, CaseStatusCategory.IMPLEMENTING, actor=who, user=owner)
        reopened = self.client.patch(f"/api/v1/actions/{second['id']}", data={"done": False}, content_type="application/json", **headers)
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(open_count(), 1)
        removed = self.client.delete(f"/api/v1/actions/{second['id']}", **{**sign_in(owner, tenant=tenant), "HTTP_IF_MATCH": "2"})
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(open_count(), 0)
        listed = self.client.get(actions_url, **sign_in(owner, tenant=tenant)).json()
        self.assertEqual([row["id"] for row in listed["items"]], [first.json()["id"]])
        tenancy.activate(tenant.id)
        row = Action.objects.get(pk=second["id"])
        self.assertEqual((row.removed_by_id, row.removed_at is not None), (owner.id, True), "the row stays for the case file")
        self.assertTrue(AuditEvent.objects.filter(action="case.action_removed", subject_id=row.id, actor_id=owner.id).exists())

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

    def test_cas_s13(self) -> None:
        """CAS-S13

        Sub-statuses inside a category leave the guards untouched (CAS-02, VOC-04).
        """
        from apps.cases.tests_assessment import AssessmentClient, bank_with_a_case, body, sub_status

        bank = bank_with_a_case(CaseStatusCategory.ASSESSING)
        sub_status(bank.tenant, "waiting_for_legal", CaseStatusCategory.ASSESSING, "Waiting for legal")
        calls = AssessmentClient(self, bank)
        plain = calls.save(body())
        self.assertEqual(plain.status_code, 200, plain.content)

        placed = calls.save(body(subStatus="waiting_for_legal"))

        self.assertEqual(placed.status_code, 200, placed.content)
        answer = placed.json()
        self.assertEqual(answer["status"], CaseStatusCategory.ASSESSING.value, "the machine still reads assessing")
        self.assertEqual(answer["allowedTransitions"], plain.json()["allowedTransitions"], "the guards are untouched")
        self.assertNotIn(CaseStatusCategory.SIGNOFF.value, answer["allowedTransitions"])
        self.assertFalse(answer["canRequestSignoff"], "sign-off rules apply unchanged")
        # The pill's tone comes from the kind, the category; its text is the bank's label.
        self.assertEqual(answer["subStatus"], {"key": "waiting_for_legal", "kind": "assessing", "label": "Waiting for legal"})

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
