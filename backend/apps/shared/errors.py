"""One error shape everywhere (playbook 4.4): RFC 9457 problem details.

`ProblemError` is raised from api.py (re-raising a logic ValidationError with the right
status) or by the permission decorators. config/api.py turns it into a response. The
`code` values are the contract's vocabulary: four_eyes_violation, open_actions,
evidence_missing, invalid_transition, stale_write, unknown_key, step_up_required,
permission_denied, unauthenticated, not_found, validation_error.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from django.http import JsonResponse

PROBLEM_CONTENT_TYPE = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        *,
        title: str | None = None,
        required_permission: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.title = title or HTTPStatus(status).phrase
        self.required_permission = required_permission
        self.errors = errors or []

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }
        if self.required_permission is not None:
            body["requiredPermission"] = self.required_permission
        if self.errors:
            body["errors"] = self.errors
        return body


def problem_response(error: ProblemError) -> JsonResponse:
    return JsonResponse(error.as_dict(), status=error.status, content_type=PROBLEM_CONTENT_TYPE)
