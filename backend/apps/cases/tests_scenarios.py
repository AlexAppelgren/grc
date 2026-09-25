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

from typing import Any
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

    def test_cas_s7(self) -> None:
        """CAS-S7

        Evidence is scanned, hashed and streamed through permission checks (CAS-05).
        """
        # --- c9-evidence: CAS-S7 ---
        import hashlib
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import transaction
        from django.test import override_settings

        from apps.cases import evidence as evidence_logic
        from apps.cases.tests_evidence import AS_SESSION, PDF, bank_with_case
        from apps.shared import permissions as perms
        from apps.shared import tenancy
        from apps.shared.models import AuditEvent
        from apps.shared.testing import AuditAssertingClient, stub_session, user_principal

        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=media.name, STORAGE_BACKEND="local", SCANNER_PROVIDER="mock"))
        client = AuditAssertingClient()
        bank = bank_with_case(CaseStatusCategory.IMPLEMENTING)
        url = f"/api/v1/changes/{bank.change_id}/evidence"

        # The owner attaches a PDF, a link and a reference; the PDF waits for its scan.
        with stub_session(bank.principal), self.captureOnCommitCallbacks(execute=False) as queued:
            pdf = client.post(url, data={"kind": "file", "name": "Research criteria", "file": SimpleUploadedFile("criteria.pdf", PDF, content_type="application/pdf")}, **AS_SESSION)
        with stub_session(bank.principal):
            link = client.post(url, data={"kind": "link", "name": "FI decision memo", "url": "https://intranet.example.com/memo/42"}, **AS_SESSION)
            reference = client.post(url, data={"kind": "reference", "name": "Credit policy, section 4"}, **AS_SESSION)
        self.assertEqual((pdf.status_code, link.status_code, reference.status_code), (201, 201, 201))
        stored = pdf.json()["evidence"]
        self.assertEqual(stored["contentHash"], "sha256:" + hashlib.sha256(PDF).hexdigest())
        self.assertEqual(stored["scanState"], "pending")

        def download(principal: Any) -> Any:
            with stub_session(principal):
                return client.get(f"/api/v1/evidence/{stored['id']}/download", **AS_SESSION)

        self.assertEqual(download(bank.principal).status_code, 409, "invisible until the scan passes")

        # A file outside the size or type allow-list answers 422 and stores nothing.
        with stub_session(bank.principal), override_settings(EVIDENCE_MAX_BYTES=len(PDF) - 1):
            too_large = client.post(url, data={"kind": "file", "name": "Big", "file": SimpleUploadedFile("big.pdf", PDF, content_type="application/pdf")}, **AS_SESSION)
        with stub_session(bank.principal):
            wrong_type = client.post(url, data={"kind": "file", "name": "Page", "file": SimpleUploadedFile("page.html", b"<html></html>", content_type="text/html")}, **AS_SESSION)
        self.assertEqual((too_large.status_code, wrong_type.status_code), (422, 422))

        # The scan passes; a reader downloads through the API, checked and audited.
        for run in queued:
            run()
        reader = user_principal(subject_id=bank.person.id, tenant_id=bank.tenant.id, permissions={perms.CASES_READ})
        downloaded = download(reader)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, PDF)
        with transaction.atomic():
            tenancy.activate(bank.tenant.id)
            self.assertEqual(AuditEvent.objects.filter(action=evidence_logic.DOWNLOADED, subject_id=stored["id"]).count(), 1)
        without_read = user_principal(subject_id=bank.person.id, tenant_id=bank.tenant.id, permissions={perms.CASES_CONTRIBUTE})
        self.assertEqual(download(without_read).status_code, 403, "the permission is checked on every download")
        # --- end c9-evidence: CAS-S7 ---

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

