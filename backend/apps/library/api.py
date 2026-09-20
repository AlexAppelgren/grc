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
the caller may not read is a 404 and never a 403 that would confirm it exists.

Chunk 5 adds the two library reads it needs, under that same read gate: the authority
list, which chunk 3 cut and which the change header and the console's authority filter
both need (ruling E), and a live record's citations, which is how an agent key re-checks
the record against its source without holding any write scope (AGT-01, item 3). Neither
writes; a correction the re-check finds is a proposal (PRO-01)."""

import uuid
from typing import Annotated, Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.identity.schemas import RoleRef
from apps.library import reading, reports
from apps.library.models import Language, SubjectType
from apps.library.schemas import (
    LibraryAuthority,
    LibraryRecordSources,
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

# ---------------------------------------------------------------------------------------
# What the published contract says about the two chunk 5 reads
# ---------------------------------------------------------------------------------------
_OBLIGATION_ID = (
    "The library obligation whose citations to read, as a UUID. A record the caller cannot "
    "see answers 404, never 403, so no id can be probed for."
)

# The authority list is a short fixed reference read, so its example lives on the route
# rather than on a page schema; the gate reads it from the 200 response.
_AUTHORITIES_EXAMPLE = {
    "responses": {
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
                            "key": "fi",
                            "shortName": "FI",
                            "name": "Finansinspektionen",
                            "jurisdiction": {"key": "se", "kind": "country", "label": "Sweden"},
                            "url": "https://www.fi.se/",
                        },
                        {
                            "id": "8e40b6d1-25af-4c73-9d08-b1f4e7a3c592",
                            "key": "esma",
                            "shortName": "ESMA",
                            "name": "European Securities and Markets Authority",
                            "jurisdiction": {"key": "eu", "kind": "union", "label": "European Union"},
                            "url": "https://www.esma.europa.eu/",
                        },
                    ]
                }
            }
        }
    }
}


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


@router.get(
    "/authorities",
    response=list[LibraryAuthority],
    auth=SESSION_OR_KEY,
    operation_id="listAuthorities",
    by_alias=True,
    summary="List the authorities that issue the rules we watch",
    openapi_extra=_AUTHORITIES_EXAMPLE,
)
@answers_problems
def list_authorities(request: HttpRequest) -> Any:
    """Every issuing authority the shared library knows, with its jurisdiction: the Swedish,
    Danish, Norwegian and Finnish supervisors, the EU bodies and the international standards
    publishers. Call it to fill an authority filter on the watch feed or the console's change
    queue, to label a change's issuer, and from an agent run that has to recognise the
    authority behind a page it fetched.

    A read: it changes nothing and writes no audit row. A person's session holding
    `library.read`, or an agent's key carrying the `library:read` scope. A short fixed
    reference list, answered as a plain array rather than a page, like the other reference
    reads. Library facts, the same for every bank, changed only through an approved proposal;
    an authority's `key` never changes, so store the key and never the name.

    Errors: `permission_denied` without `library.read` or `library:read`; `unauthenticated`
    without a credential.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; FP-04, AGT-02).
    # A short fixed reference list, answered as a plain array like the other reference reads.
    require_library_read(request)
    return reading.list_authorities()


@router.get(
    "/obligations/{obligation_id}/sources",
    response=LibraryRecordSources,
    auth=SESSION_OR_KEY,
    operation_id="getRecordSources",
    by_alias=True,
    summary="See which public pages an obligation was taken from",
)
@answers_problems
def get_record_sources(
    request: HttpRequest, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """The citations behind the version of an obligation in force today: which field each one
    backs, the public page it came from, the hash of that page as we last read it and when.
    Call it to show a reader where a fact came from, and from a watch run that re-checks a
    library record against its source.

    A read: it changes nothing and writes no audit row. A person's session holding
    `library.read`, or an agent's key carrying the `library:read` scope alone — which is the
    point of the route, because a run must be able to compare a record with its source
    without holding any write scope. Nothing an agent finds here may be written back: a
    record that has drifted becomes a proposal, approved by a second and independent
    principal, and never a direct edit (PRO-01). A page whose hash has changed means the page
    moved, never that the record is wrong.

    A record with no field-level citation yet is a 200 with an empty `items`, not a 404; the
    record's own `provenance` on `GET /obligations/{obligationId}` still names where it came
    from. Errors: `not_found` when no obligation has that id or the caller may not see it;
    `permission_denied` without `library.read` or `library:read`; `unauthenticated` without a
    credential.

    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-06, AGT-01).
    require_library_read(request)
    return reading.get_record_sources()


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
