"""Request ID, Server-Timing and CSP middleware (playbook 2.2, 10, 11.2).

- `RequestIdMiddleware` takes `X-Request-ID` from the caller or mints one, stores it in a
  contextvar so every log line in the request carries it, and echoes it on the response.
- `ServerTimingMiddleware` stamps `Server-Timing: app;dur=<ms>` on every response, which
  is how the API budget is measured (playbook 10), and logs a WARNING with the request
  ID when the request exceeds `API_BUDGET_MS`.
- `ContentSecurityPolicyMiddleware` sets the strict policy on every response that has
  none, relaxing it only for the DEBUG docs page.
- `SupportReadOnlyMiddleware` answers 403 `support_read_only` to a support session's
  request for any route off `SUPPORT_READ_ROUTES`, before any view runs (TEN-06, ADR 0042).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
# Bounded so a hostile header cannot become a log-injection vector or a 64 KB line.
REQUEST_ID_MAX_LENGTH = 128

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    return _request_id.get()


def _acceptable_request_id(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) > REQUEST_ID_MAX_LENGTH:
        return None
    if not all(ch.isalnum() or ch in "-_." for ch in value):
        return None
    return value


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        supplied = _acceptable_request_id(request.headers.get(REQUEST_ID_HEADER))
        request_id = supplied or uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestIdLogFilter(logging.Filter):
    """Attaches the current request ID to every log record (settings.LOGGING) and changes
    nothing else: a record passes every handler's filters in turn, so a change here would
    reach every handler after it. What a line says of a request (the route, never the path
    or the query) is apps.shared.logging.JsonFormatter's alone (playbook 4.7)."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Django logs a refused request after RequestIdMiddleware has reset the context, so the
        # id then comes from the request Django attaches to the record.
        request = getattr(record, "request", None)
        record.request_id = getattr(record, "request_id", None) or _request_id.get() or getattr(request, "request_id", None)
        return True


def loggable_route(request: HttpRequest) -> str:
    """The URL pattern that matched (`api/v1/vocab/<list>/<key>`), which holds
    no value a caller supplied. When nothing matched (a 404) the path is reduced to its
    first two segments, which is enough to see what was hit and never a token."""
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", "") if match is not None else ""
    if route:
        return route
    return "/".join(request.path.split("/")[:3])


class ServerTimingMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
        if elapsed_ms > settings.API_BUDGET_MS:
            # The route pattern is logged, never the concrete path, the body or the query
            # (playbook 4.7): a path can carry a value a caller chose (finding F6). No
            # credential travels in a path any more (F29); this keeps it that way in logs.
            logger.warning(
                "request over budget",
                extra={
                    "route": loggable_route(request),
                    "method": request.method,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "budget_ms": settings.API_BUDGET_MS,
                    "status": response.status_code,
                },
            )
        return response


class ContentSecurityPolicyMiddleware:
    """The strict CSP, plus the two headers the API must carry on every response even
    where Django's SecurityMiddleware is not in the stack: `Referrer-Policy: no-referrer`
    (the invitation token is a URL segment on the web app; nothing the API answers may
    carry a referrer anywhere) and `X-Content-Type-Options: nosniff` (security review
    2026-09-19, F28)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Referrer-Policy", "no-referrer")
        response.setdefault("X-Content-Type-Options", "nosniff")
        if response.has_header("Content-Security-Policy"):
            return response
        relaxed = any(
            request.path.startswith(prefix)
            for prefix in settings.CONTENT_SECURITY_POLICY_DOCS_PREFIXES
        )
        response["Content-Security-Policy"] = (
            settings.CONTENT_SECURITY_POLICY_DOCS if relaxed else settings.CONTENT_SECURITY_POLICY
        )
        return response


class SupportReadOnlyMiddleware:
    """The read-only guard of a support session (TEN-06, D-49, ADR 0042). A request whose
    token is a support session's reaches only the `(method, route template)` pairs written
    out in `SUPPORT_READ_ROUTES` (apps/shared/routes.py), and its own refresh and sign-out
    (`SUPPORT_SESSION_ROUTES`); everything else, a new GET as much
    as any write, the evidence and export downloads, search and Ask, answers 403
    `support_read_only` before its view, its auth class or its body parser runs. It matches
    the template Django resolved, never the raw path, so a path id cannot smuggle a request
    onto the list; a path that resolves to no API route is refused as well, and one that
    resolves to nothing at all reaches no view and is Django's 404. Whether the
    grant is still open is the auth layer's, per request (apps/identity/session_logic.py)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self, request: HttpRequest, view_func: Callable[..., Any], view_args: tuple[Any, ...], view_kwargs: dict[str, Any]
    ) -> HttpResponse | None:
        from apps.identity.session_logic import support_token_presented
        from apps.shared.agent_access_guard import operation_of
        from apps.shared.errors import ProblemError, problem_response
        from apps.shared.routes import SUPPORT_READ_ROUTES, SUPPORT_SESSION_ROUTES

        if not support_token_presented(request):
            return None
        operation = operation_of(request)
        if operation is not None and (operation.method, operation.path) in SUPPORT_READ_ROUTES | SUPPORT_SESSION_ROUTES:
            return None
        return problem_response(
            ProblemError(status=403, code="support_read_only", detail="Support access reads the bank and changes nothing.")
        )
