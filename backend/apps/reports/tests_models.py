"""The export job table and the exporter registry (REP-02, CAS-07).

What is proved here is what the database and the registry refuse on their own, whatever a
route does: another bank's job is invisible under forced row-level security, a `succeeded`
job without its file cannot exist, and the registry takes one builder per kind in the
designed formats only.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.reports import exporters
from apps.reports.models import ExportJob, ExportKind, JobStatus
from apps.identity.models import User
from apps.shared import factories, tenancy
from apps.shared.models import Tenant


def _job(tenant: Tenant, user: User, **fields: Any) -> ExportJob:  # compliance: allow-kwargs test builder
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return ExportJob.objects.create(tenant=tenant, kind="cases", format="json", requested_by=user, **fields)


class ExportJobTable(TestCase):
    a: Tenant
    b: Tenant
    person: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.a = factories.tenant()
        cls.b = factories.tenant()
        cls.person = factories.member(cls.a, roles=("admin",)).user

    def test_another_banks_job_is_invisible(self) -> None:
        job = _job(self.a, self.person)
        tenancy.activate(self.b.id)
        self.assertFalse(ExportJob.objects.filter(pk=job.pk).exists())
        tenancy.activate(self.a.id)
        self.assertTrue(ExportJob.objects.filter(pk=job.pk).exists())

    def test_a_new_job_is_queued_with_no_file(self) -> None:
        job = _job(self.a, self.person)
        self.assertEqual(job.status, JobStatus.QUEUED.value)
        self.assertIsNone(job.storage_key)
        self.assertIsNone(job.content_hash)
        self.assertIsNone(job.downloaded_at)

    def test_a_succeeded_job_without_its_file_is_refused(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            _job(self.a, self.person, status=JobStatus.SUCCEEDED.value)

    def test_the_audit_title_carries_kind_and_format_only(self) -> None:
        job = _job(self.a, self.person)
        self.assertEqual(job.audit_title, "cases export (json)")


class ExporterRegistry(TestCase):
    def test_no_builder_is_registered_by_this_package(self) -> None:
        # c9-case-file-export registers the case file; every other kind waits for its task.
        for kind in set(ExportKind) - {ExportKind.CASE_FILE}:
            with self.subTest(kind=kind):
                self.assertIsNone(exporters.lookup(kind))

    def test_every_kind_names_the_task_that_builds_it(self) -> None:
        self.assertEqual(set(exporters.PLANNED_BY), set(ExportKind))

    def test_a_kind_registers_once_in_designed_formats(self) -> None:
        def build(job: ExportJob) -> bytes:
            return b""

        saved = dict(exporters._REGISTRY)
        try:
            exporters.register(ExportKind.CASES, formats=frozenset({"csv"}), build=build)
            self.assertEqual(exporters.lookup(ExportKind.CASES), exporters.Exporter(frozenset({"csv"}), build))
            with self.assertRaises(ValueError):
                exporters.register(ExportKind.CASES, formats=frozenset({"json"}), build=build)
            with self.assertRaises(ValueError):
                exporters.register(ExportKind.CHANGES, formats=frozenset({"docx"}), build=build)
            with self.assertRaises(ValueError):
                exporters.register(ExportKind.CHANGES, formats=frozenset(), build=build)
        finally:
            exporters._REGISTRY.clear()
            exporters._REGISTRY.update(saved)
