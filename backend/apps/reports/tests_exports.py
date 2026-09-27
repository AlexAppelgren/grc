"""The export routes, the runner and the download (REP-02, CAS-07; CHUNK12_TASKS
c12-exports-contract-b).

A builder is registered for the test through `registered()`; no real builder exists yet,
and each one's own module proves what its file holds. What is proved here is the mechanism
every kind shares: the gates, that the request never builds the file, that the runner is
idempotent and fails cleanly, and that the download is permission-checked, streamed,
audited and confined to the caller's own bank.
"""

from __future__ import annotations

import datetime
import hashlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.test import TestCase
from django.utils import timezone

from apps.reports import exporters, tasks
from apps.reports.models import ExportJob, ExportKind, JobStatus
from apps.shared import factories, permissions as perms, tenancy
from apps.identity.models import User
from apps.shared.models import AuditEvent, Tenant
from apps.shared.tenancy import is_tenant_task
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    ScenarioTestCase,
    agent_principal,
    sign_in,
    stub_api_key,
    stub_session,
    user_principal,
)
from config.celery import app as celery_app

EXPORTS = "/api/v1/exports"
FILE = b'{"cases": [{"title": "FI adopts amended rules on paying for investment research"}]}'
BODY = {"kind": "cases", "format": "json"}


@contextmanager
def registered(build: exporters.Builder | None = None, *, formats: frozenset[str] = frozenset({"json", "csv"})) -> Iterator[mock.Mock]:
    """A `cases` builder for the length of the block; the mock records every call."""
    builder = mock.Mock(side_effect=build or (lambda job: FILE))
    with mock.patch.dict(exporters._REGISTRY, {ExportKind.CASES: exporters.Exporter(formats, builder)}):
        yield builder


class ExportGates(TestCase):
    ROUTES = [
        ("post", EXPORTS, BODY),
        ("get", EXPORTS, None),
        ("get", f"{EXPORTS}/{uuid.uuid4()}", None),
        ("get", f"{EXPORTS}/{uuid.uuid4()}/download", None),
    ]

    def _call(self, method: str, url: str, body: Any, **headers: Any) -> Any:
        if body is None:
            return getattr(self.client, method)(url, **headers)
        return getattr(self.client, method)(url, data=body, content_type="application/json", **headers)

    def test_no_credential_is_401(self) -> None:
        for method, url, body in self.ROUTES:
            with self.subTest(url=url, method=method):
                self.assertEqual(self._call(method, url, body).status_code, 401)

    def test_a_session_without_exports_create_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.REPORTS_READ}, tenant_id=uuid.uuid4())):
            for method, url, body in self.ROUTES:
                with self.subTest(url=url, method=method):
                    response = self._call(method, url, body, HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["requiredPermission"], perms.EXPORTS_CREATE)

    def test_an_agent_key_never_exports(self) -> None:
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES, tenant_id=uuid.uuid4())):
            for method, url, body in self.ROUTES:
                with self.subTest(url=url, method=method):
                    response = self._call(method, url, body, HTTP_X_API_KEY=API_KEY_FOR_TESTS)
                    self.assertEqual(response.status_code, 401)

    def test_the_runner_is_a_registered_tenant_task(self) -> None:
        self.assertIn(tasks.run_export.name, celery_app.tasks)
        self.assertTrue(is_tenant_task(tasks.run_export.run))


class ExportJobs(ScenarioTestCase):
    a: Tenant
    b: Tenant
    officer: User
    outsider: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.a = factories.tenant()
        cls.b = factories.tenant()
        cls.officer = factories.member(cls.a, roles=("compliance_officer",)).user
        cls.outsider = factories.member(cls.b, roles=("admin",)).user

    def _create(self, body: dict[str, Any] | None = None, *, run: bool = True) -> Any:
        headers = sign_in(self.officer, tenant=self.a, step_up=True)
        with self.captureOnCommitCallbacks(execute=run):
            return self.client.post(EXPORTS, data=body or BODY, content_type="application/json", **headers)

    def _job(self, job_id: str) -> ExportJob:
        tenancy.activate(self.a.id)
        return ExportJob.objects.get(pk=job_id)

    # --- asking -------------------------------------------------------------------------
    def test_without_a_fresh_step_up_it_is_refused_and_nothing_is_written(self) -> None:
        with registered():
            response = self.client.post(EXPORTS, data=BODY, content_type="application/json", **sign_in(self.officer, tenant=self.a))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")
        tenancy.activate(self.a.id)
        self.assertFalse(ExportJob.objects.exists())

    def test_the_request_answers_202_before_the_builder_runs(self) -> None:
        with registered() as builder:
            headers = sign_in(self.officer, tenant=self.a, step_up=True)
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                response = self.client.post(EXPORTS, data=BODY, content_type="application/json", **headers)
            self.assertEqual(response.status_code, 202)
            job = response.json()
            self.assertEqual((job["status"], job["contentHash"], job["downloadedAt"]), ("queued", None, None))
            builder.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
            builder.assert_called_once()
        row = self._job(job["id"])
        self.assertEqual(row.requested_by_id, self.officer.id)
        self.assertEqual(row.status, JobStatus.SUCCEEDED.value)
        requested = AuditEvent.objects.get(action="export.requested", subject_id=row.id)
        self.assertIsNotNone(requested.step_up_assertion_id)

    def test_a_built_job_reports_its_hash_and_expiry(self) -> None:
        with registered():
            job_id = self._create().json()["id"]
        got = self.client.get(f"{EXPORTS}/{job_id}", **sign_in(self.officer, tenant=self.a)).json()
        self.assertEqual(got["status"], "succeeded")
        self.assertEqual(got["contentHash"], hashlib.sha256(FILE).hexdigest())
        self.assertIsNone(got["downloadedAt"])
        self.assertIsNone(got["error"])
        completed = datetime.datetime.fromisoformat(got["completedAt"])
        self.assertEqual(datetime.datetime.fromisoformat(got["expiresAt"]) - completed, datetime.timedelta(days=7))

    def test_an_unregistered_kind_is_501_and_writes_no_row(self) -> None:
        for kind in ExportKind:
            if exporters.lookup(kind) is not None:
                continue  # built; its own module proves what it answers
            with self.subTest(kind=kind):
                body = {"kind": kind.value, "format": "json"}
                response = self._create(body)
                self.assertEqual(response.status_code, 501)
                self.assertEqual(response.json()["code"], "not_built")
        tenancy.activate(self.a.id)
        self.assertFalse(ExportJob.objects.exists())

    def test_a_format_the_kind_does_not_offer_is_422_and_writes_no_row(self) -> None:
        with registered(formats=frozenset({"csv"})):
            response = self._create({"kind": "cases", "format": "pdf"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "format_not_offered")
        tenancy.activate(self.a.id)
        self.assertFalse(ExportJob.objects.exists())

    def test_only_a_case_file_names_a_subject(self) -> None:
        with registered():
            response = self._create({"kind": "cases", "format": "json", "subjectId": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 422)

    def test_filters_are_typed_and_kept(self) -> None:
        with registered():
            body = {"kind": "cases", "format": "csv", "filters": {"statusKeys": ["gap"], "from": "2026-01-01"}}
            job_id = self._create(body).json()["id"]
            self.assertEqual(self._job(job_id).filters, {"statusKeys": ["gap"], "from": "2026-01-01"})
            refused = self._create({"kind": "cases", "format": "csv", "filters": {"tone": "negative"}})
        self.assertEqual(refused.status_code, 422)

    # --- the runner ---------------------------------------------------------------------
    def test_a_builder_refusal_fails_the_job_with_its_text(self) -> None:
        def refuse(job: ExportJob) -> bytes:
            raise ValidationError("This bank has no cases to export yet.")

        with registered(refuse):
            job_id = self._create().json()["id"]
        row = self._job(job_id)
        self.assertEqual((row.status, row.error, row.storage_key), ("failed", "This bank has no cases to export yet.", None))
        self.assertTrue(AuditEvent.objects.filter(action="export.failed", subject_id=row.id).exists())
        got = self.client.get(f"{EXPORTS}/{job_id}", **sign_in(self.officer, tenant=self.a)).json()
        self.assertEqual(got["error"], "This bank has no cases to export yet.")

    def test_a_second_run_of_a_finished_job_changes_nothing(self) -> None:
        with registered() as builder:
            job_id = self._create().json()["id"]
            before = self._job(job_id)
            audit = AuditEvent.objects.count()
            tasks.run_export(self.a.id, job_id)
            builder.assert_called_once()
        after = self._job(job_id)
        self.assertEqual((after.completed_at, after.content_hash), (before.completed_at, before.content_hash))
        self.assertEqual(AuditEvent.objects.count(), audit)

    def test_the_runner_finds_nothing_under_another_tenant(self) -> None:
        with registered() as builder:
            job_id = self._create(run=False).json()["id"]
            tasks.run_export(self.b.id, job_id)
            builder.assert_not_called()
        self.assertEqual(self._job(job_id).status, JobStatus.QUEUED.value)

    # --- the download -------------------------------------------------------------------
    def test_the_download_streams_the_file_with_one_audit_row(self) -> None:
        with registered():
            job_id = self._create().json()["id"]
        headers = sign_in(self.officer, tenant=self.a)
        before = AuditEvent.objects.filter(action="export.downloaded").count()
        response = self.client.get(f"{EXPORTS}/{job_id}/download", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, FileResponse)
        self.assertTrue(response.streaming)
        self.assertEqual(b"".join(response.streaming_content), FILE)  # type: ignore[attr-defined]
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        self.assertIn(".json", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(AuditEvent.objects.filter(action="export.downloaded").count(), before + 1)
        first = self._job(job_id).downloaded_at
        assert first is not None

        again = self.client.get(f"{EXPORTS}/{job_id}/download", **headers)
        b"".join(again.streaming_content)  # type: ignore[attr-defined]
        self.assertEqual(self._job(job_id).downloaded_at, first)
        self.assertEqual(AuditEvent.objects.filter(action="export.downloaded").count(), before + 2)
        got = self.client.get(f"{EXPORTS}/{job_id}", **headers).json()
        self.assertEqual(datetime.datetime.fromisoformat(got["downloadedAt"]), first.replace(microsecond=first.microsecond // 1000 * 1000))

    def test_an_expired_export_is_409(self) -> None:
        with registered():
            job_id = self._create().json()["id"]
        ExportJob.objects.filter(pk=job_id).update(expires_at=timezone.now() - datetime.timedelta(seconds=1))
        response = self.client.get(f"{EXPORTS}/{job_id}/download", **sign_in(self.officer, tenant=self.a))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "export_expired")

    def test_a_job_without_a_file_is_409(self) -> None:
        with registered():
            job_id = self._create(run=False).json()["id"]
        response = self.client.get(f"{EXPORTS}/{job_id}/download", **sign_in(self.officer, tenant=self.a))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "export_not_ready")

    # --- another bank -------------------------------------------------------------------
    def test_another_bank_gets_404_for_the_job_its_status_and_its_download(self) -> None:
        with registered():
            job_id = self._create().json()["id"]
        headers = sign_in(self.outsider, tenant=self.b)
        for url in (f"{EXPORTS}/{job_id}", f"{EXPORTS}/{job_id}/download"):
            with self.subTest(url=url):
                response = self.client.get(url, **headers)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")
        listed = self.client.get(EXPORTS, **headers).json()
        self.assertEqual(listed, {"items": [], "total": 0})
        tenancy.activate(self.a.id)
        self.assertIsNone(ExportJob.objects.get(pk=job_id).downloaded_at)

    def test_the_list_is_the_banks_own_newest_first_and_paged(self) -> None:
        with registered():
            first = self._create().json()["id"]
            second = self._create().json()["id"]
        headers = sign_in(self.officer, tenant=self.a)
        page = self.client.get(f"{EXPORTS}?limit=1", **headers).json()
        self.assertEqual(page["total"], 2)
        self.assertEqual([item["id"] for item in page["items"]], [second])
        rest = self.client.get(f"{EXPORTS}?limit=1&offset=1", **headers).json()
        self.assertEqual([item["id"] for item in rest["items"]], [first])
        self.assertEqual(self.client.get(f"{EXPORTS}?limit=101", **headers).status_code, 422)
