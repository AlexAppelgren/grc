"""A bank reads and closes its own problem reports (AUD-03, PRO-03, INV-06, D-50).

A report is filed on a library record by any member (`apps/library/reports.py`) and stays
inside that bank: row-level security on `problem_report` has already cut every query here
to the caller's tenant, so another bank's report is simply not found, and no platform role
holds `problems.report` to get this far (Alex, 2026-09-19, item 3).

Inside the bank, `proposals.create` decides reach, as docs/TODO_FOR_alex.md's default for
item 3 says: its holder (the compliance officer) lists and closes every report of the
bank; every other member lists and closes the reports they filed. No permission is added.

A close sets `answered`, `fixed` or `rejected` with a required note, once. It is not a
library change: the correction of a wrong record reaches the library through the watch
agents' re-check and a proposal, which carries no bank's words. The report's text and the
closing note are tenant content (playbook 4.7): they stay in the row, and the audit row and
the outbox event carry the report's id and its states only.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.governance.schemas import (
    ProblemReportClose,
    ProblemReportPerson,
    ProblemReportQuery,
    ProblemReportRow,
    ProblemReportStatusKind,
    ProblemReportSubjectKind,
)
from apps.identity.models import User
from apps.identity.rate_limit import enforce
from apps.library.models import ProblemReport, ReportStatus, SubjectType
from apps.library.reading import instrument_headings, obligation_headings
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError

ACTION = "problem_report.closed"
BUCKET = "problem-report-close"
HOUR = 3600


def _visible(principal: Principal) -> Any:
    """The reports this caller may read: the bank's for a `proposals.create` holder, their
    own otherwise. Row-level security has already cut the table to the caller's bank."""
    if principal.tenant_id is None:
        raise ValidationError("Not found.", code="not_found")
    reports = ProblemReport.objects.filter(tenant_id=principal.tenant_id)
    if not principal.has_permission(perms.PROPOSALS_CREATE):
        reports = reports.filter(reporter_id=principal.subject_id)
    return reports


def reports_for(
    principal: Principal, filters: ProblemReportQuery, order: list[str], *, limit: int, offset: int
) -> tuple[list[ProblemReportRow], int]:
    """One page of the reports the caller may read, newest first, with the total."""
    reports = _visible(principal)
    if filters.status:
        reports = reports.filter(status=filters.status)
    if filters.subject_type:
        reports = reports.filter(subject_type=filters.subject_type)
    if filters.subject_id:
        reports = reports.filter(subject_id=filters.subject_id)
    reports = reports.select_related("reporter", "closed_by").order_by("-created_at", "-id")
    page = list(reports[offset : offset + limit])
    return _rows(page, order), reports.count()


def close(
    principal: Principal, report_id: uuid.UUID, body: ProblemReportClose, *, closer: User, actor: Actor, order: list[str]
) -> ProblemReportRow:
    """Close one report with its note, in the request's transaction with its audit row."""
    report = _visible_to_close(principal, report_id)
    if report.reporter_id != closer.id and not principal.has_permission(perms.PROPOSALS_CREATE):
        raise ProblemError(
            status=403,
            code="permission_denied",
            detail="Only the person who filed this report, or a colleague who may propose library changes, can close it.",
            required_permission=perms.PROPOSALS_CREATE,
        )
    if report.status != ReportStatus.OPEN.value:
        raise ProblemError(status=409, code="already_closed", detail="This report is already closed.")
    note = body.resolution_note.strip()
    if not note:
        raise ValidationError("Say why you are closing it, so the reporter knows.", code="note_required")
    # A close is a row change and an audit row kept for ten years: one person's closes
    # are bounded per hour, apart from their filing (ACC-09, hardening H39).
    enforce(BUCKET, str(closer.id), settings.PROBLEM_REPORTS_PER_USER_PER_HOUR, HOUR)
    report.status = body.status
    report.resolution_note = note
    report.closed_by = closer
    report.closed_at = timezone.now()
    report.save(update_fields=["status", "resolution_note", "closed_by", "closed_at"])
    row = _rows([report], order)[0]
    record(
        action=ACTION,
        actor=actor,
        subject_type="problem_report",
        subject_id=report.id,
        subject_title=f"Problem report on {row.subject_reference or report.subject_type}",
        summary=f"Closed a problem report as {body.status}.",
        tenant_id=report.tenant_id,
        before={"status": ReportStatus.OPEN.value},
        after={"status": body.status},
    )
    return row


def _visible_to_close(principal: Principal, report_id: uuid.UUID) -> ProblemReport:
    """The bank's report by id, locked so two closes cannot both pass the open check. A
    colleague's report is found here even without `proposals.create`, so the refusal can
    name the permission; another bank's is not, and answers 404."""
    if principal.tenant_id is None:
        raise ValidationError("Not found.", code="not_found")
    report = (
        ProblemReport.objects.select_for_update()
        .filter(id=report_id, tenant_id=principal.tenant_id)
        .select_related("reporter")
        .first()  # ordering: pk lookup, at most one row
    )
    if report is None:
        raise ValidationError("Not found.", code="not_found")
    return report


def _rows(reports: list[ProblemReport], order: list[str]) -> list[ProblemReportRow]:
    """Each report with its record named, in two queries however many rows there are."""
    obligations = obligation_headings(
        [report.subject_id for report in reports if report.subject_type == SubjectType.OBLIGATION.value], order
    )
    instruments = instrument_headings(
        [report.subject_id for report in reports if report.subject_type == SubjectType.INSTRUMENT.value]
    )
    rows = []
    for report in reports:
        title = reference = ""
        if report.subject_id in obligations:
            heading = obligations[report.subject_id]
            title, reference = heading.title, f"{heading.instrument_short_name}, {heading.reference_label}"
        elif report.subject_id in instruments:
            heading = instruments[report.subject_id]
            title, reference = heading.title, heading.reference_label
        closed = report.status != ReportStatus.OPEN.value
        rows.append(
            ProblemReportRow(
                id=report.id,
                subject_type=cast(ProblemReportSubjectKind, report.subject_type),
                subject_id=report.subject_id,
                subject_title=title,
                subject_reference=reference,
                description=report.text,
                version_number=report.version_number,
                language=report.language_id,
                reporter=_person(report.reporter),
                status=cast(ProblemReportStatusKind, report.status),
                created_at=report.created_at,
                closed_by=_person(report.closed_by) if closed else None,
                closed_at=report.closed_at,
                resolution_note=report.resolution_note if closed else None,
            )
        )
    return rows


def _person(user: Any) -> ProblemReportPerson:
    return ProblemReportPerson(id=user.id, name=user.name)
