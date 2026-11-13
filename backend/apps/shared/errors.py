"""One error shape everywhere (playbook 4.4): RFC 9457 problem details.

`ProblemError` is raised from api.py or by the permission decorators; config/api.py turns it
into a response. The `code` is the contract's vocabulary (`STATUS_BY_CODE` below), with
`bad_request` for a request Django cannot read and `internal_error` for anything unexpected:
no trace or message leaves the server.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from django.http import JsonResponse

PROBLEM_CONTENT_TYPE = "application/problem+json"

# logic.py raises ValidationError with a `code`; config/api.py and `answers_problems` answer
# with the status named here (playbook 4.4), else 422. One table, so a code never means two
# statuses.
STATUS_BY_CODE: dict[str, int] = {
    "not_found": 404,
    "unauthenticated": 401,
    "signin_failed": 401,
    "invalid_code": 400,
    "code_locked": 400,
    "step_up_failed": 400,
    "invalid_credential": 400,
    "registration_failed": 400,
    "challenge_expired": 400,
    "invitation_expired": 410,
    "device_link_expired": 410,
    "device_link_pending": 409,
    "invitation_closed": 409,
    "last_admin": 409,
    "last_passkey": 409,
    "already_member": 409,
    "duplicate_key": 409,
    "role_in_use": 409,
    "stale_write": 409,
    "four_eyes_violation": 409,
    # A person already holds as many calendar subscriptions as they may (HOM-04, D-52).
    # A conflict with what they hold and not a field they can fix: the screen offers
    # the revoke that makes room, which is why this is not a plain 422.
    "feed_limit_reached": 409,
    # The person or team already takes part in the record (COL-04, D-18): a conflict with
    # what the record holds, and a 409 because a 2xx write must leave an audit row.
    "already_participant": 409,
    # A lookup in the public registers applied before it succeeded (TEN-07): the job's state
    # does not allow the move yet, so a conflict and not a field to fix.
    "lookup_not_done": 409,
    # A bank re-enrols only an account that is in no other bank and not platform staff
    # (review 2026-11-11 S-2): the platform owner re-enrols the others.
    "account_held_elsewhere": 409,
    # Conflicts with the record's state, not fields the caller can fix.
    "in_use": 409,
    "system_row": 409,
    "category_empty": 409,
    # A team still owns open work (TEN-03): a confirm cannot override it.
    "open_work": 409,
    "request_pending": 409,
    "invalid_transition": 409,
    "approval_running": 409,
    # The caller's earlier Decide all run in this bank is still running (REG-01, D-128).
    "decision_running": 409,
    "idempotency_conflict": 409,
    "already_watching": 409,
    "forbidden": 403,
    # An agent approved a kind whose record cannot name its confirming agent (D-79).
    "person_review_required": 409,
    # An agent approved or confirmed what the injection screen flagged (AGT-07, H40).
    "risk_flagged": 409,
    # An agent confirmed a watch fact its own agent suggested (D-74).
    "own_suggestion": 409,
    "same_agent": 409,
    # A sign-off request while an action is open or before evidence passed the scan (CAS-06).
    "open_actions": 409,
    "evidence_missing": 409,
}


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


def not_found(detail: str = "Not found.") -> ProblemError:
    """The one 404: a record that does not exist and one the caller may not see read alike."""
    return ProblemError(status=404, code="not_found", detail=detail)


def problem_response(error: ProblemError) -> JsonResponse:
    return JsonResponse(error.as_dict(), status=error.status, content_type=PROBLEM_CONTENT_TYPE)
