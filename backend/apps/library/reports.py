""""This looks wrong": filing a problem report (INV-06, AUD-03, INV-S7).

A reader who spots a mistake in a public fact never edits the library; they say what
looks wrong. The report stays inside the bank: its own members with the right permission
read and close it (Alex, 2026-09-19, OWNER_RECOMMENDATIONS item 3), and bleqq's watch
agents find the deviation themselves by re-checking the record against its source and
proposing a correction (chunk 5). This module writes that one row.

The subject arrives already resolved — its kind, its id and the public title a colleague
will read — so nothing here names an `Instrument` or an `Obligation`, and the library
fence has nothing to catch. The tenant and the reporter come from the caller's principal,
never from the request body, so a report can only ever be filed for the bank the reader
is signed in to. A tenant is required: `problem_report` is a mixed table, so a row with
no tenant would be the library's own and readable by every bank, which is the opposite of
what the report is for. The route cannot produce one either, because `caller_tenant()`
answers 404 to a principal in no bank.

What the reader wrote is tenant content (playbook 4.7). It lives in `problem_report.text`
and reaches nothing else: not the audit summary, not the audit before and after, not the
outbox payload the worker delivers, and not a log line. The audit row carries the subject,
the report's id and the version and language the reader had on screen, which is what a
colleague needs to open the same words.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError

from apps.library.models import Language, ProblemReport, SubjectType
from apps.shared.audit import Actor, record

ACTION = "library.problem_reported"


def create_report(
    *,
    subject_type: SubjectType,
    subject_id: uuid.UUID,
    subject_title: str,
    tenant_id: uuid.UUID,
    reporter: Any,
    actor: Actor,
    description: str,
    version_number: int | None = None,
    language: str | None = None,
) -> ProblemReport:
    """File one report and its audit row in the caller's transaction.

    `subject_title` is the record's public reference (a stable key or an official
    reference), which a colleague reads in the audit log; it is never the reader's words.
    """
    text = description.strip()
    if not text:
        raise ValidationError("Say what looks wrong, so a colleague can check it.", code="description_required")
    if version_number is not None and version_number < 1:
        raise ValidationError("A version number starts at 1.", code="invalid_value")
    if language is not None and not Language.objects.filter(key=language, active=True).exists():
        raise ValidationError(f"{language!r} is not a content language.", code="unknown_key")

    report = ProblemReport.objects.create(
        tenant_id=tenant_id,
        reporter=reporter,
        subject_type=subject_type.value,
        subject_id=subject_id,
        text=text,
        version_number=version_number,
        language_id=language,
    )
    record(
        action=ACTION,
        actor=actor,
        subject_type=subject_type.value,
        subject_id=subject_id,
        subject_title=subject_title,
        summary=f"Reported a problem with {subject_title}.",
        tenant_id=tenant_id,
        after={"reportId": str(report.id), "versionNumber": version_number, "language": language},
    )
    return report
