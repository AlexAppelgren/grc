"""Routes of the library app (playbook 4.1: routes only). Chunk 1 adds the language
reference read for pickers (locale, tenant languages); chunk 3 adds the library reads,
beginning with the obligations list, and the two writes a record accepts.

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

from typing import Any

from django.http import HttpRequest
from ninja import Query, Router

from apps.identity.schemas import RoleRef
from apps.library import reading, reports
from apps.library.models import Language, SubjectType
from apps.library.schemas import (
    ObligationPage,
    ObligationQuery,
    ProblemReportBody,
    ProblemReportCreated,
    ReverificationBody,
    VerificationCreated,
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


@router.post(
    "/obligations/{obligation_id}/problem-reports",
    response={201: ProblemReportCreated},
    auth=SESSION,
    operation_id="reportObligationProblem",
    by_alias=True,
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def report_obligation_problem(request: HttpRequest, obligation_id: str, body: ProblemReportBody) -> Any:
    tenant = caller_tenant(request)
    reporter = caller_user(request)
    obligation = reading.obligation_subject(obligation_id, tenant=tenant)
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
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def report_instrument_problem(request: HttpRequest, instrument_id: str, body: ProblemReportBody) -> Any:
    tenant = caller_tenant(request)
    reporter = caller_user(request)
    instrument = reading.instrument_subject(instrument_id, tenant=tenant)
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
)
@requires_permission(perms.PROPOSALS_REVIEW)
@requires_step_up
@answers_problems
def reverify_obligation(request: HttpRequest, obligation_id: str, body: ReverificationBody) -> Any:
    reviewer = caller_user(request)
    # A library editor works in no bank and checks the shared library, so there is no tenant
    # to scope the subject by; a bank's own private record is nobody else's to re-verify.
    obligation = reading.obligation_subject(obligation_id, tenant=None)
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
