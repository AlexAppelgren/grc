"""Routes of the reports app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

The export half (REP-02, CAS-07): ask for an export, follow it, list them and download the
file. Every route takes a person's session holding `exports.create`; no API key reaches
them. Asking for an export also takes a passkey step-up, because playbook 4.2 lists the
export. The download repeats the permission check and writes its own audit row, but asks
for no fresh step-up: the file was authorised when it was asked for, and playbook 4.2 lists
the export, not the download (CHUNK12_TASKS defaults). The logic is `apps/reports/jobs.py`,
the runner `apps/reports/tasks.py`.
"""

import uuid
from typing import Any

from django.http import FileResponse, HttpRequest
from ninja import Path, Query, Router

from apps.reports import jobs
from apps.reports.exporters import CONTENT_TYPES
from apps.reports.schemas import EXPORT_JOB_EXAMPLE, ExportInput, ExportJobOut, ExportJobPage
from apps.shared import permissions as perms
from apps.shared.authentication import SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, caller_tenant, caller_user, principal

router = Router(tags=["Reports"])

SESSION = SessionAuth()

_EXPORT_ID = (
    "The export job's identifier, as a UUID, from `POST /exports` or `GET /exports`. Another "
    "bank's job is never reachable and answers 404."
)

_DOWNLOAD_EXAMPLE = {
    "responses": {
        200: {
            "description": "The file, as an attachment, in the export's format.",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"},
                    "example": '{"case": {"title": "FI adopts amended rules on paying for investment research"}}',
                }
            },
        }
    }
}


def _out(job: Any) -> ExportJobOut:
    return ExportJobOut(
        id=job.id,
        kind=job.kind,
        subject_id=job.subject_id,
        format=job.format,
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        content_hash=job.content_hash,
        downloaded_at=job.downloaded_at,
        error=job.error or None,
    )


@router.post(
    "/exports",
    response={202: ExportJobOut},
    auth=SESSION,
    operation_id="createExport",
    by_alias=True,
    summary="Ask for an export, built in the background",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {"kind": "case_file", "subjectId": "0c9a4a57-8a55-4c43-9c8e-6f1a2b3c4d5e", "format": "json"}}}}},
)
@requires_permission(perms.EXPORTS_CREATE)
@requires_step_up
def create_export(request: HttpRequest, body: ExportInput) -> Any:
    """Starts an export of one kind in one format and answers 202 at once with the queued
    job; the file is built by the worker, never inside this request. Poll
    `GET /exports/{exportId}` until the status is `succeeded`, then fetch the file from
    `GET /exports/{exportId}/download`.

    A person's session holding `exports.create` in their own bank, with a passkey step-up
    confirmed within the last few minutes, because an export takes the bank's records out
    of the screens that check who may see them. No API key reaches it. The request is
    recorded in the audit log with the person, the kind, the format and the step-up; the
    worker records the file's SHA-256 when it is built. The file is kept for a limited
    number of days (`expiresAt`).

    Errors: `step_up_required` without a fresh passkey confirmation; `permission_denied`
    without `exports.create`; `unauthenticated` without a session; `not_built` (501) for a
    kind whose file is not built yet, before any job is written; `format_not_offered` for a
    format the kind does not come in; `validation_error` for a body that is not the shape
    above, or a case file that names no case in `subjectId` or another kind that names one;
    for a case file, `not_found` when `subjectId` is not a case of the caller's bank, and
    `permission_denied` without `cases.read`, both before any job is written.
    """
    user = caller_user(request)
    job = jobs.create(
        tenant=caller_tenant(request),
        user=user,
        actor=actor_for(request, user),
        permissions=principal(request).permissions,
        body=body,
        step_up_assertion_id=getattr(request, "step_up_assertion_id", None),
    )
    return 202, _out(job)


@router.get(
    "/exports",
    response=ExportJobPage,
    auth=SESSION,
    operation_id="listExports",
    by_alias=True,
    summary="See the bank's exports, newest first",
)
@requires_permission(perms.EXPORTS_CREATE)
def list_exports(request: HttpRequest, page: Query[PageQuery]) -> Any:
    """Returns the bank's export jobs one page at a time, newest first, each with its status,
    its checksum once built and when it was first downloaded. Use it to show the exports
    screen or to find an earlier export again.

    A person's session holding `exports.create` in their own bank; only that bank's jobs are
    ever listed. It only reads and writes nothing to the audit log. An empty list is a 200
    with `total` 0.

    Errors: `validation_error` when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` without `exports.create`; `unauthenticated` without a session.
    """
    rows, total = jobs.page(tenant=caller_tenant(request), limit=page.limit, offset=page.offset)
    return ExportJobPage(items=[_out(row) for row in rows], total=total)


@router.get(
    "/exports/{export_id}",
    response=ExportJobOut,
    auth=SESSION,
    operation_id="getExport",
    by_alias=True,
    summary="Check whether an export is ready",
    openapi_extra={"responses": {200: {"content": {"application/json": {"example": EXPORT_JOB_EXAMPLE}}}}},
)
@requires_permission(perms.EXPORTS_CREATE)
def get_export(request: HttpRequest, export_id: uuid.UUID = Path(..., description=_EXPORT_ID)) -> Any:
    """Returns one export job as it stands: `queued` or `running` while the worker builds it,
    `succeeded` with its checksum and expiry once the file is ready, `failed` with the
    reason when it could not be built. Poll it after `POST /exports`.

    A person's session holding `exports.create` in their own bank. It only reads and writes
    nothing to the audit log.

    Errors: `not_found` when no job of this bank has that id, which is also what another
    bank's job answers; `permission_denied` without `exports.create`; `unauthenticated`
    without a session.
    """
    return _out(jobs.get(tenant=caller_tenant(request), job_id=export_id))


@router.get(
    "/exports/{export_id}/download",
    response={200: None},
    auth=SESSION,
    operation_id="downloadExport",
    by_alias=True,
    summary="Download an export's file",
    openapi_extra=_DOWNLOAD_EXAMPLE,
)
@requires_permission(perms.EXPORTS_CREATE)
def download_export(request: HttpRequest, export_id: uuid.UUID = Path(..., description=_EXPORT_ID)) -> Any:
    """Streams the built file as an attachment, in the export's format, marked `no-store`
    so no cache keeps it. There is no link to share: the file only ever leaves through this
    call. Its SHA-256 is the job's `contentHash`.

    A person's session holding `exports.create` in their own bank, checked again on every
    download. No fresh step-up: the export was confirmed with a passkey when it was asked
    for. Every download is recorded in the audit log with the person, the kind and the
    format, and the first one is stamped as the job's `downloadedAt`.

    Errors: `not_found` when no job of this bank has that id, which is also what another
    bank's job answers; `export_not_ready` (409) while the job is queued, running or failed;
    `export_expired` (409) once `expiresAt` has passed, when a new export is needed;
    `permission_denied` without `exports.create`, or for a case file without `cases.read`;
    `unauthenticated` without a session.
    """
    user = caller_user(request)
    job, stream = jobs.download(
        tenant=caller_tenant(request), actor=actor_for(request, user), permissions=principal(request).permissions, job_id=export_id
    )
    response = FileResponse(
        stream,
        as_attachment=True,
        filename=f"{job.kind}-{job.completed_at:%Y-%m-%d}.{job.format}",
        content_type=CONTENT_TYPES[job.format],
    )
    response["Cache-Control"] = "no-store"
    return response
