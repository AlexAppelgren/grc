"""Export jobs (REP-02, CAS-07; CHUNK12_TASKS c12-exports-contract-b).

`create` writes the job and hands it to the worker once the request's transaction commits,
so a request never builds a file. A kind nobody registered answers 501 `not_built` and a
format its exporter does not offer answers 422, both before a row is written. `download`
streams the file back through the same permission, writes one audit row per download and
stamps the first one. Every read and write names the caller's own tenant on top of
row-level security, so another bank's job is a plain 404.

Nothing here logs; the audit rows name the export's kind and format and the person, never
anything from the file.
"""

from __future__ import annotations

import uuid
from typing import IO

from django.db import transaction
from django.utils import timezone

from apps.identity.models import User
from apps.reports import exporters, tasks
from apps.reports.models import ExportJob, ExportKind, JobStatus
from apps.reports.schemas import ExportInput
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.storage import get_storage

# Spelled out here as in tasks.py, so the audit guards read it (apps/shared/tests_hardening.py).
SUBJECT_TYPE = "export_job"
EXPORT_REQUESTED = "export.requested"
EXPORT_DOWNLOADED = "export.downloaded"


def create(*, tenant: Tenant, user: User, actor: Actor, body: ExportInput, step_up_assertion_id: uuid.UUID | None) -> ExportJob:
    kind = ExportKind(body.kind)
    exporter = exporters.lookup(kind)
    if exporter is None:
        raise ProblemError(
            status=501,
            code="not_built",
            detail=f"Exports of this kind are not built yet; {exporters.PLANNED_BY[kind]} builds them.",
        )
    if body.format not in exporter.formats:
        raise ProblemError(
            status=422,
            code="format_not_offered",
            detail=f"This export comes as {', '.join(sorted(exporter.formats))}.",
        )
    if (kind is ExportKind.CASE_FILE) != (body.subject_id is not None):
        raise ProblemError(
            status=422,
            code="validation_error",
            detail="A case file names its case in subjectId, and no other export names one.",
        )
    job = ExportJob.objects.create(
        tenant=tenant,
        kind=kind.value,
        subject_id=body.subject_id,
        format=body.format,
        filters=body.filters.model_dump(mode="json", by_alias=True, exclude_none=True) if body.filters else {},
        requested_by=user,
    )
    record(
        action=EXPORT_REQUESTED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=job.id,
        subject_title=job.audit_title,
        summary=f"{actor.label} asked for a {job.audit_title}.",
        tenant_id=tenant.id,
        after={"kind": job.kind, "format": job.format, "subjectId": str(job.subject_id) if job.subject_id else None},
        step_up_assertion_id=step_up_assertion_id,
    )
    tenant_id, job_id = str(tenant.id), str(job.id)
    transaction.on_commit(lambda: tasks.run_export.delay(tenant_id, job_id))
    return job


def get(*, tenant: Tenant, job_id: uuid.UUID) -> ExportJob:
    job = ExportJob.objects.filter(pk=job_id, tenant=tenant).first()  # ordering: pk lookup, at most one row
    if job is None:
        raise ProblemError(status=404, code="not_found", detail="No export with that id.")
    return job


def page(*, tenant: Tenant, limit: int, offset: int) -> tuple[list[ExportJob], int]:
    jobs = ExportJob.objects.filter(tenant=tenant)
    return list(jobs.order_by("-created_at", "id")[offset : offset + limit]), jobs.count()


def download(*, tenant: Tenant, actor: Actor, job_id: uuid.UUID) -> tuple[ExportJob, IO[bytes]]:
    job = ExportJob.objects.select_for_update().filter(pk=job_id, tenant=tenant).first()  # ordering: pk lookup, at most one row
    if job is None:
        raise ProblemError(status=404, code="not_found", detail="No export with that id.")
    if job.status != JobStatus.SUCCEEDED.value or job.storage_key is None:
        raise ProblemError(status=409, code="export_not_ready", detail="This export has no file yet. Check its status and try again.")
    now = timezone.now()
    if job.expires_at is not None and job.expires_at <= now:
        raise ProblemError(status=409, code="export_expired", detail="This export's file has expired. Ask for a new export.")
    first = job.downloaded_at is None
    if first:
        job.downloaded_at = now
        job.save(update_fields=["downloaded_at"])
    record(
        action=EXPORT_DOWNLOADED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=job.id,
        subject_title=job.audit_title,
        summary=f"{actor.label} downloaded a {job.audit_title}.",
        tenant_id=tenant.id,
        after={"kind": job.kind, "format": job.format, "contentHash": job.content_hash, "firstDownload": first},
    )
    return job, get_storage().open(job.storage_key)
