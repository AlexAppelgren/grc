"""Routes of the library app (playbook 4.1: routes only). Chunk 1 adds the language
reference read for pickers (locale, tenant languages); chunk 3 adds the library reads: the
obligations list, one obligation as of a date and what changed between two of its versions,
and the two writes a record accepts.

A library record read serves a person with `library.read` and an agent's key with
`library:read`, so it is a logic gate (apps/taxonomy/http.py `require_library_read`) and
listed in `UNGATED_BY_DESIGN`; `answers_problems` is always innermost.

The writes are gated in the ordinary way. "This looks wrong" needs `problems.report`,
which every member of a bank holds and nobody at bleqq does, so a report is filed inside
one bank and stays there (Alex, 2026-09-19). Re-verifying a record needs
`proposals.review` and a fresh passkey: it is the single exception to "a proposal is the
only door into the library", and the one function it may reach lives behind the fence in
apps/proposals/apply.py. Every route resolves its subject through `reading`, so a record
the caller may not read is a 404 and never a 403 that would confirm it exists."""

import uuid
from typing import Annotated, Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.identity.schemas import RoleRef
from apps.library import reading, reports
from apps.library.models import Language, SubjectType
from apps.library.schemas import (
    ObligationAsOfQuery,
    ObligationDetail,
    ObligationDiffQuery,
    ObligationPage,
    ObligationQuery,
    ProblemReportBody,
    ProblemReportCreated,
    ReverificationBody,
    VerificationCreated,
    VersionDiff,
)
from apps.proposals.apply import apply_reverification
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, require_library_read
from apps.taxonomy.reading import language_order
from apps.taxonomy.schemas import PersonRef

router = Router(tags=["Library"])

SESSION = SessionAuth()
SESSION_OR_KEY = [SessionAuth(), ApiKeyAuth()]

# ---------------------------------------------------------------------------------------
# What the published contract says about the writes (docs/plans/briefs/API_DOCUMENTATION.md)
# ---------------------------------------------------------------------------------------
# Long prose belongs beside the route, not inside the decorator's argument list, and the two
# report routes say the same thing about the same record. A backticked snake_case word in an
# operation description is read as an RFC 9457 code by the documentation gate, so the three
# verification outcomes appear here unquoted on purpose.
_SUBJECT_ID = (
    "The {record} the report is about, by its identifier (a UUID). It has to be one the caller "
    "can already read, so another bank's private record and an identifier that names nothing "
    "both answer 404 rather than telling you which of the two it was."
)
OBLIGATION_ID_DESCRIPTION = _SUBJECT_ID.format(record="obligation")
INSTRUMENT_ID_DESCRIPTION = _SUBJECT_ID.format(record="instrument")
REVERIFY_ID_DESCRIPTION = (
    "The obligation that was checked, by its identifier (a UUID). A library editor works in no "
    "bank and so addresses the shared library alone: a record a bank owns privately answers 404 "
    "here, exactly as an identifier that names nothing does."
)

REPORT_DESCRIPTION = (
    "Files a reader's \"this looks wrong\" report against one {record} of the shared library. "
    "Call it when someone reading a record believes a public fact is wrong. Nothing in the "
    "library changes here: a proposal is the only door into it.\n\n"
    "{extra}"
    "The report is created inside the bank the caller is signed in to and stays there. No bleqq "
    "editor, no other bank, no agent and no model ever reads it, and no console surface lists it "
    "(Alex, 2026-09-19). The loop back to the library is closed the other way round: bleqq's "
    "watch agents re-check library records against their sources on every run, find the "
    "deviation themselves, and propose the correction for a second, independent principal to "
    "approve.\n\n"
    "The reporter and the bank are taken from the caller's session and never from the body, so "
    "do not send them; versionNumber and language record which words were on screen.\n\n"
    "Needs the `problems.report` permission, which every member of a bank holds and no platform "
    "role does. Answers 201 with the report's id, its status and when it was filed, and never "
    "reads the reader's own words back. Writes one audit event, library.problem_reported, "
    "carrying the record, the report's id and the version and language on screen, and never the "
    "text itself.\n\n"
    "Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403) "
    "without the permission, including for every platform role; `not_found` (404) when the "
    "{record} is not one this caller may read; `validation_error` (422) when the body is "
    "malformed, the text is longer than 4000 characters or the path segment is not a UUID; "
    "`description_required` (422) when the description is only whitespace; `unknown_key` (422) "
    "when the language is not an active content language."
)

REVERIFY_DESCRIPTION = (
    "Records that a library editor has read this obligation against its source, and moves the "
    "record's re-verification stamp when the source still says the same thing. This is the "
    "single sanctioned exception to \"a proposal is the only door into the library\": it writes "
    "lastVerifiedAt and verifiedBy and nothing else. It creates no record, and changes no text, "
    "date, scope or facet.\n\n"
    "What it does not mean: nobody re-approved the record's content here and no new version was "
    "written. A no_change outcome says one person looked at the source on this date and found it "
    "unchanged; a correction still has to arrive as a proposal that a second, independent "
    "principal approves.\n\n"
    "Only no_change moves the stamp. change_found and source_unavailable file the check and "
    "leave the earlier stamp standing, so a reader is never told a record was confirmed when it "
    "was not. Every check is kept, not only the most recent one.\n\n"
    "Needs the `proposals.review` permission and a fresh passkey assertion (a step-up). No "
    "tenant role holds `proposals.review`, and the route takes a person's session only, so no "
    "API key scope reaches it and an agent can never stamp a record. Writes one audit event, "
    "library.reverified, carrying the assertion the passkey produced.\n\n"
    "Errors to branch on: `unauthenticated` (401) without a session; `permission_denied` (403) "
    "without the permission; `step_up_required` (403) when the session carries no fresh passkey "
    "assertion; `not_found` (404) when the obligation is not one this caller may read; "
    "`validation_error` (422) when the body is malformed, the note is longer than 4000 "
    "characters or the path segment is not a UUID; `unknown_key` (422) when the outcome is not "
    "one of the three."
)


@router.get("/reference/languages", response=list[RoleRef], auth=SessionAuth(), operation_id="listLanguages", by_alias=True)
def list_languages(request: HttpRequest) -> list[RoleRef]:
    # Ungated by design: capability (any session; a reference read for pickers, I18N-01).
    return [
        RoleRef(key=language.key, kind=None, label=language.name)
        for language in Language.objects.filter(active=True).order_by("key")
    ]


@router.get("/obligations", response=ObligationPage, auth=SESSION_OR_KEY, operation_id="listObligations", by_alias=True)
@answers_problems
def list_obligations(request: HttpRequest, query: Query[ObligationQuery], page: Query[PageQuery]) -> ObligationPage:
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-03, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    order = language_order(request, tenant=tenant)
    items, total = reading.obligation_page(tenant, order, query, limit=page.limit, offset=page.offset)
    return ObligationPage(items=items, total=total)


@router.get("/obligations/{obligation_id}", response=ObligationDetail, auth=SESSION_OR_KEY, operation_id="getObligation", by_alias=True)
@answers_problems
def get_obligation(request: HttpRequest, obligation_id: uuid.UUID, query: Query[ObligationAsOfQuery]) -> ObligationDetail:
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-03, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    return reading.obligation_detail(tenant, language_order(request, tenant=tenant), obligation_id, query)


@router.get(
    "/obligations/{obligation_id}/diff", response=VersionDiff, auth=SESSION_OR_KEY, operation_id="getObligationDiff", by_alias=True
)
@answers_problems
def get_obligation_diff(request: HttpRequest, obligation_id: uuid.UUID, query: Query[ObligationDiffQuery]) -> VersionDiff:
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-04, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    return reading.obligation_diff(language_order(request, tenant=tenant), obligation_id, query)


@router.post(
    "/obligations/{obligation_id}/problem-reports",
    response={201: ProblemReportCreated},
    auth=SESSION,
    operation_id="reportObligationProblem",
    by_alias=True,
    summary="Tell us an obligation looks wrong",
    description=REPORT_DESCRIPTION.format(
        record="obligation",
        extra=(
            "The obligation has to be one this caller can already read: a shared record, or one "
            "their own bank owns privately.\n\n"
        ),
    ),
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def report_obligation_problem(
    request: HttpRequest,
    obligation_id: Annotated[uuid.UUID, Path(description=OBLIGATION_ID_DESCRIPTION)],
    body: ProblemReportBody,
) -> Any:
    tenant = caller_tenant(request)
    reporter = caller_user(request)
    obligation = reading.obligation_subject(obligation_id)
    report = reports.create_report(
        subject_type=SubjectType.OBLIGATION,
        subject_id=obligation.id,
        subject_title=obligation.stable_key,
        tenant_id=tenant.id,
        reporter=reporter,
        actor=actor_for(request, reporter),
        description=body.description,
        version_number=body.version_number,
        language=body.language,
    )
    return 201, ProblemReportCreated(id=report.id, status=report.status, created_at=report.created_at)


@router.post(
    "/instruments/{instrument_id}/problem-reports",
    response={201: ProblemReportCreated},
    auth=SESSION,
    operation_id="reportInstrumentProblem",
    by_alias=True,
    summary="Tell us an instrument or one of its provisions looks wrong",
    description=REPORT_DESCRIPTION.format(
        record="instrument",
        extra=(
            "A provision is reported through the instrument whose card shows it, so there is no "
            "separate provision route; say which provision in the text. The instrument has to be "
            "one this caller can already read: a shared record, or one their own bank owns "
            "privately.\n\n"
        ),
    ),
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def report_instrument_problem(
    request: HttpRequest,
    instrument_id: Annotated[uuid.UUID, Path(description=INSTRUMENT_ID_DESCRIPTION)],
    body: ProblemReportBody,
) -> Any:
    tenant = caller_tenant(request)
    reporter = caller_user(request)
    instrument = reading.instrument_subject(instrument_id)
    report = reports.create_report(
        subject_type=SubjectType.INSTRUMENT,
        subject_id=instrument.id,
        subject_title=instrument.stable_key,
        tenant_id=tenant.id,
        reporter=reporter,
        actor=actor_for(request, reporter),
        description=body.description,
        version_number=body.version_number,
        language=body.language,
    )
    return 201, ProblemReportCreated(id=report.id, status=report.status, created_at=report.created_at)


@router.post(
    "/obligations/{obligation_id}/verifications",
    response={201: VerificationCreated},
    auth=SESSION,
    operation_id="reverifyObligation",
    by_alias=True,
    summary="Record that you checked an obligation against its source",
    description=REVERIFY_DESCRIPTION,
)
@requires_permission(perms.PROPOSALS_REVIEW)
@requires_step_up
@answers_problems
def reverify_obligation(
    request: HttpRequest,
    obligation_id: Annotated[uuid.UUID, Path(description=REVERIFY_ID_DESCRIPTION)],
    body: ReverificationBody,
) -> Any:
    reviewer = caller_user(request)
    # A library editor works in no bank, so row-level security shows this lookup the shared
    # library alone: a bank's own private record is nobody else's to re-verify, and asking
    # for one answers the same 404 as an id that names nothing.
    obligation = reading.obligation_subject(obligation_id)
    verification = apply_reverification(
        obligation,
        actor=actor_for(request, reviewer),
        verified_by=reviewer,
        outcome=body.outcome,
        note=body.note,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    stamped_by = obligation.verified_by
    return 201, VerificationCreated(
        id=verification.id,
        outcome=verification.outcome,
        verified_at=verification.verified_at,
        last_verified_at=obligation.last_verified_at,
        verified_by=None if stamped_by is None else PersonRef(id=stamped_by.id, name=stamped_by.name),
    )
