"""The case file as an export job (CAS-07; c9-case-file-export).

The exported file is byte for byte what `GET /changes/{changeId}/case-file` answers the
same person. Asking for it takes `exports.create`, a step-up and `cases.read`, and names a
case of the caller's own bank; downloading it checks both permissions again and writes one
audit row. Another bank's case answers 404 before a job is written, and the builder
refuses a job whose case is not its own tenant's as a second check.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.identity.models import User
from apps.reports import exporters, tasks
from apps.reports.exporters import case_file as exporter
from apps.reports.models import ExportJob, ExportKind, JobStatus
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in, stub_session, user_principal

EXPORTS = "/api/v1/exports"


def body(case_id: uuid.UUID) -> dict[str, Any]:
    return {"kind": "case_file", "subjectId": str(case_id), "format": "txt"}


class CaseFileExport(ScenarioTestCase):
    a: Tenant
    b: Tenant
    officer: User
    outsider: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.a = factories.tenant()
        cls.b = factories.tenant()
        cls.officer = factories.member_user(cls.a, roles=("compliance_officer",))
        cls.outsider = factories.member_user(cls.b, roles=("compliance_officer",))

    def ask(self, user: User, tenant: Tenant, case_id: uuid.UUID) -> Any:
        headers = sign_in(user, tenant=tenant, step_up=True)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(EXPORTS, data=body(case_id), content_type="application/json", **headers)

    def test_it_is_registered_as_text_only(self) -> None:
        registered = exporters.lookup(ExportKind.CASE_FILE)
        assert registered is not None
        self.assertEqual(registered.formats, frozenset({"txt"}))
        pdf = self.client.post(
            EXPORTS,
            data={**body(factories.closed_case(self.a).case.id), "format": "pdf"},
            content_type="application/json",
            **sign_in(self.officer, tenant=self.a, step_up=True),
        )
        self.assertEqual(pdf.status_code, 422)
        self.assertEqual(pdf.json()["code"], "format_not_offered")

    def test_the_file_is_byte_identical_to_the_text_on_screen(self) -> None:
        built = factories.closed_case(self.a)
        job = self.ask(self.officer, self.a, built.case.id).json()
        headers = sign_in(self.officer, tenant=self.a)
        self.assertEqual(self.client.get(f"{EXPORTS}/{job['id']}", **headers).json()["status"], "succeeded")
        download = self.client.get(f"{EXPORTS}/{job['id']}/download", **headers)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn(".txt", download["Content-Disposition"])
        on_screen = self.client.get(f"/api/v1/changes/{built.change_id}/case-file", **headers).content
        self.assertEqual(b"".join(download.streaming_content), on_screen)  # type: ignore[attr-defined]

    def test_it_is_asked_for_under_a_step_up_named_in_the_audit_row(self) -> None:
        built = factories.closed_case(self.a)
        job = self.ask(self.officer, self.a, built.case.id).json()
        requested = AuditEvent.objects.get(action="export.requested", subject_id=job["id"])
        self.assertIsNotNone(requested.step_up_assertion_id)
        refused = self.client.post(
            EXPORTS, data=body(built.case.id), content_type="application/json", **sign_in(self.officer, tenant=self.a)
        )
        self.assertEqual(refused.json()["code"], "step_up_required")

    def test_another_banks_case_is_404_and_no_job_is_written(self) -> None:
        theirs = factories.closed_case(self.a)
        exported = AuditEvent.objects.filter(action__startswith="export.")
        before = exported.count()
        for case_id in (theirs.case.id, uuid.uuid4()):
            with self.subTest(case_id=case_id):
                response = self.ask(self.outsider, self.b, case_id)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")
        tenancy.activate(self.b.id)
        self.assertFalse(ExportJob.objects.exists())
        self.assertEqual(exported.count(), before)

    def test_without_cases_read_it_is_neither_asked_for_nor_downloaded(self) -> None:
        built = factories.closed_case(self.a)
        job_id = self.ask(self.officer, self.a, built.case.id).json()["id"]
        tenancy.activate(self.a.id)
        jobs_before, audit_before = ExportJob.objects.count(), AuditEvent.objects.count()
        principal = user_principal(
            subject_id=self.officer.id,
            tenant_id=self.a.id,
            permissions=perms.TENANT_PERMISSIONS - {perms.CASES_READ},
            step_up_at=timezone.now(),
        )
        with stub_session(principal):
            asked = self.client.post(EXPORTS, data=body(built.case.id), content_type="application/json", **self.as_user(principal))
            downloaded = self.client.get(f"{EXPORTS}/{job_id}/download", **self.as_user(principal))
        for response in (asked, downloaded):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["requiredPermission"], perms.CASES_READ)
        tenancy.activate(self.a.id)
        self.assertEqual(ExportJob.objects.count(), jobs_before)
        self.assertEqual(AuditEvent.objects.count(), audit_before, "a refusal writes nothing")

    def test_the_builder_refuses_a_job_whose_case_is_not_its_tenants(self) -> None:
        theirs = factories.closed_case(self.a)
        tenancy.activate(self.b.id)
        job = ExportJob.objects.create(
            tenant=self.b, kind="case_file", subject_id=theirs.case.id, format="txt", requested_by=self.outsider
        )
        tasks.run_export(self.b.id, str(job.id))
        tenancy.activate(self.b.id)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED.value)
        self.assertEqual(job.error, "The case this export names is not in your bank.")
        self.assertIsNone(job.storage_key)


class CaseFileCheck(TestCase):
    def test_a_missing_subject_is_404(self) -> None:
        tenant = factories.tenant()
        with self.assertRaises(ProblemError) as refused:
            exporter.check(tenant=tenant, permissions=frozenset({perms.CASES_READ}), subject_id=None)
        self.assertEqual(refused.exception.status, 404)
