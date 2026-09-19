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
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError
from ninja.errors import ValidationError as NinjaValidationError

from apps.identity.api import router as identity_router
from apps.library.api import router as library_router
from apps.proposals.api import router as proposals_router
from apps.shared.api import router as shared_router
from apps.shared.errors import STATUS_BY_CODE, ProblemError, problem_response
from apps.taxonomy.api import router as taxonomy_router
from apps.tenants.api import router as tenants_router

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


def not_found(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    """Django-level 404 for paths outside the API, in the same problem shape."""
    return problem_response(ProblemError(status=404, code="not_found", detail="Not found."))
