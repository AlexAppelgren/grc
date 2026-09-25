"""The export runner (REP-02, CAS-07).

`run_export` is a `@tenant_task`: the tenant id is its first argument and it runs activated
in its own transaction, so the file's key, its hash and the audit row land together or not
at all. It checks the tenant again: the job is read by its id *and* the tenant it was queued
for, under that tenant's row-level security, so a job id handed to the wrong tenant finds
nothing.

It is idempotent: only a `queued` job is built, under a row lock, so a second delivery of
the same message finds the job finished and changes nothing. A builder's `ValidationError`
fails the job with its user-facing text; anything else propagates, the transaction rolls
back, and the job stays queued for a retry. Nothing here logs the file or its contents.
"""

from __future__ import annotations

import datetime
import hashlib
import uuid

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.reports import exporters
from apps.reports.models import ExportJob, ExportKind, JobStatus
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.storage import get_storage, object_key

SUBJECT_TYPE = "export_job"
EXPORT_SUCCEEDED = "export.succeeded"
EXPORT_FAILED = "export.failed"


@shared_task
@tenancy.tenant_task
def run_export(tenant_id: uuid.UUID, job_id: str) -> None:
    job = ExportJob.objects.select_for_update().filter(pk=job_id, tenant_id=tenant_id).first()  # ordering: pk lookup, at most one row
    if job is None or job.status != JobStatus.QUEUED.value:
        return
    now = timezone.now()
    exporter = exporters.lookup(ExportKind(job.kind))
    try:
        if exporter is None:
            raise ValidationError("Exports of this kind are not built yet.")
        data = exporter.build(job)
    except ValidationError as exc:
        job.status = JobStatus.FAILED.value
        job.error = " ".join(exc.messages)
        job.completed_at = now
        job.save(update_fields=["status", "error", "completed_at"])
        action, summary = EXPORT_FAILED, f"A {job.audit_title} could not be built."
    else:
        key = object_key(tenant_id, job.id, f"export.{job.format}")
        get_storage().write(key, data, exporters.CONTENT_TYPES[job.format])
        job.status = JobStatus.SUCCEEDED.value
        job.storage_key = key
        job.content_hash = hashlib.sha256(data).hexdigest()
        job.completed_at = now
        job.expires_at = now + datetime.timedelta(days=settings.EXPORT_RETENTION_DAYS)
        job.save(update_fields=["status", "storage_key", "content_hash", "completed_at", "expires_at"])
        action, summary = EXPORT_SUCCEEDED, f"A {job.audit_title} was built, {len(data)} bytes."
    record(
        action=action,
        actor=Actor.system("export runner"),
        subject_type=SUBJECT_TYPE,
        subject_id=job.id,
        subject_title=job.audit_title,
        summary=summary,
        tenant_id=tenant_id,
        after={"status": job.status, "contentHash": job.content_hash},
    )
