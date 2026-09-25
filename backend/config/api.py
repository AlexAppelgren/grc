"""The one NinjaAPI instance. Every app's router is added here, so the object the
structural guards enumerate is the same object that produces openapi.json (playbook 5).

Errors leave in one shape everywhere (playbook 4.4): RFC 9457 problem details with
`title`, `status`, `detail`, a machine-readable `code`, `errors[]` for field validation
and `requiredPermission` on a 403. The client branches on `code`, never on `detail`.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import BadRequest, SuspiciousOperation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.http.multipartparser import MultiPartParserError
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError
from ninja.errors import ValidationError as NinjaValidationError

from apps.agents.api import router as agents_router
from apps.cases.api import router as cases_router
from apps.governance.api import router as governance_router
from apps.home.api import router as home_router
from apps.identity.api import router as identity_router
from apps.integrations.api import router as integrations_router
from apps.library.api import router as library_router
from apps.proposals.api import router as proposals_router
from apps.search.api import router as search_router
from apps.shared.api import router as shared_router
from apps.shared.errors import STATUS_BY_CODE, ProblemError, problem_response
from apps.shared.middleware import loggable_route
from apps.taxonomy.api import router as taxonomy_router
from apps.tenants.api import router as tenants_router
from apps.watch.api import router as watch_router

logger = logging.getLogger(__name__)

api = NinjaAPI(
    title=f"{settings.PRODUCT_NAME} API",
    version="0.1.0",
    description=(
        "Compliance inventory and regulatory watch. Library records are shared facts that "
        "change only through approved proposals; tenant records belong to one company and "
        "sit under row-level security. Errors follow RFC 9457 and carry a `code`."
    ),
    # The interactive docs page exists only under DEBUG; the exported openapi.json is the
    # contract everywhere else (playbook 14).
    docs_url="/docs" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    urls_namespace="api-v1",
)

api.add_router("", shared_router)
api.add_router("", identity_router)
api.add_router("", tenants_router)
api.add_router("", library_router)
api.add_router("", taxonomy_router)
api.add_router("", proposals_router)
api.add_router("", governance_router)
api.add_router("", search_router)
api.add_router("", agents_router)
api.add_router("", watch_router)
api.add_router("", cases_router)
api.add_router("", home_router)
api.add_router("", integrations_router)  # acc-mcp-transport: POST /mcp


@api.exception_handler(ProblemError)
def handle_problem(request: HttpRequest, exc: ProblemError) -> HttpResponse:
    return problem_response(exc)


@api.exception_handler(AuthenticationError)
def handle_authentication(request: HttpRequest, exc: AuthenticationError) -> HttpResponse:
    # The enrolment session reaches only the passkey registration ceremony and GET /me;
    # everywhere else it is refused with 403 enrolment_only, not 401 (ID-02, AC-ID2).
    from apps.identity.session_logic import enrolment_token_presented

    if enrolment_token_presented(request):
        return problem_response(
            ProblemError(status=403, code="enrolment_only", detail="Finish enrolling a passkey first.")
        )
    return problem_response(
        ProblemError(
            status=401, code="unauthenticated", detail="Sign in to continue."
        )
    )


@api.exception_handler(HttpError)
def handle_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
    return problem_response(
        ProblemError(status=exc.status_code, code="http_error", detail=str(exc.message))
    )


@api.exception_handler(NinjaValidationError)
def handle_ninja_validation(request: HttpRequest, exc: NinjaValidationError) -> HttpResponse:
    errors: list[dict[str, Any]] = [
        {"field": ".".join(str(part) for part in error.get("loc", ())), "message": error.get("msg", "")}
        for error in exc.errors
    ]
    return problem_response(
        ProblemError(
            status=422,
            code="validation_error",
            detail="Some fields need attention.",
            errors=errors,
        )
    )


@api.exception_handler(DjangoValidationError)
def handle_django_validation(request: HttpRequest, exc: DjangoValidationError) -> HttpResponse:
    # logic.py raises ValidationError with user-facing text (playbook 4.4). The message
    # is the detail; the code is the exception's own code or a generic one.
    messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
    code = getattr(exc, "code", None) or "validation_error"
    return problem_response(
        ProblemError(
            status=STATUS_BY_CODE.get(code, 422),
            code=code,
            detail=" ".join(messages),
        )
    )


@api.exception_handler(SuspiciousOperation)
@api.exception_handler(BadRequest)
@api.exception_handler(MultiPartParserError)
def handle_unreadable(request: HttpRequest, exc: Exception) -> HttpResponse:
    # A body over the size limit, too many fields or a broken multipart body: Django's own
    # 400, in the one problem shape. The route and the error's type are logged, never the
    # path or the message (finding F6).
    logger.warning("unreadable request", extra={"route": loggable_route(request), "error": type(exc).__qualname__})
    return problem_response(ProblemError(status=400, code="bad_request", detail="The request could not be read."))


@api.exception_handler(Exception)
def handle_unexpected(request: HttpRequest, exc: Exception) -> HttpResponse:
    # Anything the handlers above do not name. The request's writes roll back (it runs in
    # one transaction, ATOMIC_REQUESTS), the frames go to the log (apps.shared.logging
    # writes them without any exception message) with the route pattern, never the path,
    # and the caller gets the one problem shape with no trace (playbook 4.4, 4.7).
    if transaction.get_connection().in_atomic_block:
        transaction.set_rollback(True)
    logger.exception("unhandled error", extra={"route": loggable_route(request), "method": request.method})
    return problem_response(
        ProblemError(status=500, code="internal_error", detail="Something went wrong on our side. Try again.")
    )


def not_found(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    """Django-level 404 for paths outside the API, in the same problem shape."""
    return problem_response(ProblemError(status=404, code="not_found", detail="Not found."))
