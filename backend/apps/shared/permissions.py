"""Permissions are code, roles are rows (PRD §6, ID-09, playbook 4.2).

The constants below are the PRD's permission matrix, exactly. A route is gated with
`@requires_permission` (people) or `@requires_scope` (agents), then `@requires_step_up`
where playbook 4.2 lists the action. A route with no gate must be registered in
`UNGATED_BY_DESIGN` with one of five reasons, which the route-permissions guard
(apps/shared/tests_route_permissions.py) reads back.

Decorator order under the Ninja decorator: `@router.get(...)` outermost, then
`@requires_permission(...)`, then `@requires_step_up`, then the view. The decorators mark
the wrapped function (`__cw_gate__`, `__cw_step_up__`) and `functools.wraps` carries the
marks outward, so the guard reads them off the object Ninja registered.

The 403 is structured (playbook 4.2): `detail`, `code`, `requiredPermission`.
"""

from __future__ import annotations

import enum
import functools
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, TypeVar

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone

from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError

# ---------------------------------------------------------------------------------------
# Tenant permissions (PRD §6). The comment after each row names who holds it by default.
# ---------------------------------------------------------------------------------------
LIBRARY_READ = "library.read"  # everyone
WATCH_READ = "watch.read"  # everyone
ROADMAP_READ = "roadmap.read"  # everyone
SEARCH_USE = "search.use"  # everyone
COMMENTS_WRITE = "comments.write"  # everyone
PROBLEMS_REPORT = "problems.report"  # everyone
REGISTER_READ = "register.read"  # everyone
CASES_READ = "cases.read"  # everyone
REPORTS_READ = "reports.read"  # everyone
AUDIT_READ = "audit.read"  # everyone
FOOTPRINT_REQUEST = "footprint.request"  # admin, compliance officer
FOOTPRINT_APPROVE = "footprint.approve"  # admin, compliance officer, approver
CASES_TRIAGE = "cases.triage"  # compliance officer
CASES_WORK = "cases.work"  # compliance officer, owner
CASES_CONTRIBUTE = "cases.contribute"  # compliance officer, owner, contributor
CASES_SIGNOFF = "cases.signoff"  # approver
REGISTER_EDIT = "register.edit"  # compliance officer, owner
GAPS_EDIT = "gaps.edit"  # compliance officer, owner
APPLICABILITY_REQUEST = "applicability.request"  # compliance officer, owner
APPLICABILITY_APPROVE = "applicability.approve"  # compliance officer, approver
RISK_ACCEPT_APPROVE = "risk.accept.approve"  # compliance officer, approver
PROPOSALS_CREATE = "proposals.create"  # compliance officer
EXPORTS_CREATE = "exports.create"  # admin, compliance officer, approver, auditor
AI_LOG_READ = "ai_log.read"  # admin, compliance officer, approver, auditor
MEMBERS_MANAGE = "members.manage"  # admin
ROLES_MANAGE = "roles.manage"  # admin
SECURITY_MANAGE = "security.manage"  # admin
VOCAB_MANAGE = "vocab.manage"  # admin, compliance officer
WORKFLOW_MANAGE = "workflow.manage"  # admin, compliance officer
AGENTS_MANAGE = "agents.manage"  # admin
INTEGRATIONS_MANAGE = "integrations.manage"  # admin

# ---------------------------------------------------------------------------------------
# Platform permissions (PRD §6): library_editor and platform_admin.
# ---------------------------------------------------------------------------------------
PROPOSALS_REVIEW = "proposals.review"  # library_editor
LIBRARY_VOCAB_MANAGE = "library_vocab.manage"  # library_editor
SOURCES_MANAGE = "sources.manage"  # library_editor
EVAL_MANAGE = "eval.manage"  # library_editor
TENANTS_MANAGE = "tenants.manage"  # platform_admin
AGENT_DEFINITIONS_MANAGE = "agent_definitions.manage"  # platform_admin
SUPPORT_ACCESS_GRANT = "support_access.grant"  # platform_admin
SYSTEM_HEALTH = "system.health"  # platform_admin

TENANT_PERMISSIONS: frozenset[str] = frozenset(
    {
        LIBRARY_READ,
        WATCH_READ,
        ROADMAP_READ,
        SEARCH_USE,
        COMMENTS_WRITE,
        PROBLEMS_REPORT,
        REGISTER_READ,
        CASES_READ,
        REPORTS_READ,
        AUDIT_READ,
        FOOTPRINT_REQUEST,
        FOOTPRINT_APPROVE,
        CASES_TRIAGE,
        CASES_WORK,
        CASES_CONTRIBUTE,
        CASES_SIGNOFF,
        REGISTER_EDIT,
        GAPS_EDIT,
        APPLICABILITY_REQUEST,
        APPLICABILITY_APPROVE,
        RISK_ACCEPT_APPROVE,
        PROPOSALS_CREATE,
        EXPORTS_CREATE,
        AI_LOG_READ,
        MEMBERS_MANAGE,
        ROLES_MANAGE,
        SECURITY_MANAGE,
        VOCAB_MANAGE,
        WORKFLOW_MANAGE,
        AGENTS_MANAGE,
        INTEGRATIONS_MANAGE,
    }
)
PLATFORM_PERMISSIONS: frozenset[str] = frozenset(
    {
        PROPOSALS_REVIEW,
        LIBRARY_VOCAB_MANAGE,
        SOURCES_MANAGE,
        EVAL_MANAGE,
        TENANTS_MANAGE,
        AGENT_DEFINITIONS_MANAGE,
        SUPPORT_ACCESS_GRANT,
        SYSTEM_HEALTH,
    }
)
ALL_PERMISSIONS: frozenset[str] = TENANT_PERMISSIONS | PLATFORM_PERMISSIONS

# Four eyes applies to every approve permission: never the requester (PRD §6).
APPROVE_PERMISSIONS: frozenset[str] = frozenset(
    {FOOTPRINT_APPROVE, CASES_SIGNOFF, APPLICABILITY_APPROVE, RISK_ACCEPT_APPROVE, PROPOSALS_REVIEW}
)

# ---------------------------------------------------------------------------------------
# System roles as the PRD's matrix states them. Seeded as rows by chunk 1 (ID-09); kept
# here so the seed and the seed-integrity guard read one source.
# ---------------------------------------------------------------------------------------
_EVERYONE = frozenset(
    {
        LIBRARY_READ,
        WATCH_READ,
        ROADMAP_READ,
        SEARCH_USE,
        COMMENTS_WRITE,
        PROBLEMS_REPORT,
        REGISTER_READ,
        CASES_READ,
        REPORTS_READ,
        AUDIT_READ,
    }
)
SYSTEM_ROLES: dict[str, frozenset[str]] = {
    "admin": _EVERYONE
    | {
        FOOTPRINT_REQUEST,
        FOOTPRINT_APPROVE,
        EXPORTS_CREATE,
        AI_LOG_READ,
        MEMBERS_MANAGE,
        ROLES_MANAGE,
        SECURITY_MANAGE,
        VOCAB_MANAGE,
        WORKFLOW_MANAGE,
        AGENTS_MANAGE,
        INTEGRATIONS_MANAGE,
    },
    "compliance_officer": _EVERYONE
    | {
        FOOTPRINT_REQUEST,
        FOOTPRINT_APPROVE,
        CASES_TRIAGE,
        CASES_WORK,
        CASES_CONTRIBUTE,
        REGISTER_EDIT,
        GAPS_EDIT,
        APPLICABILITY_REQUEST,
        APPLICABILITY_APPROVE,
        RISK_ACCEPT_APPROVE,
        PROPOSALS_CREATE,
        EXPORTS_CREATE,
        AI_LOG_READ,
        VOCAB_MANAGE,
        WORKFLOW_MANAGE,
    },
    "owner": _EVERYONE
    | {CASES_WORK, CASES_CONTRIBUTE, REGISTER_EDIT, GAPS_EDIT, APPLICABILITY_REQUEST},
    "approver": _EVERYONE
    | {
        FOOTPRINT_APPROVE,
        CASES_SIGNOFF,
        APPLICABILITY_APPROVE,
        RISK_ACCEPT_APPROVE,
        EXPORTS_CREATE,
        AI_LOG_READ,
    },
    "contributor": _EVERYONE | {CASES_CONTRIBUTE},
    "reader": _EVERYONE,
    "auditor": _EVERYONE | {EXPORTS_CREATE, AI_LOG_READ},
    "library_editor": frozenset({PROPOSALS_REVIEW, LIBRARY_VOCAB_MANAGE, SOURCES_MANAGE, EVAL_MANAGE}),
    "platform_admin": frozenset(
        {TENANTS_MANAGE, AGENT_DEFINITIONS_MANAGE, SUPPORT_ACCESS_GRANT, SYSTEM_HEALTH}
    ),
}

# ---------------------------------------------------------------------------------------
# API key scopes (ID-10). Named here so `@requires_scope` and the key console share them.
# No scope allows a library edit (AC-PRO1); the agent writes proposals and changes only.
# ---------------------------------------------------------------------------------------
SCOPE_AGENT_RUNS = "agent.runs"
SCOPE_CHANGES_WRITE = "changes.write"
SCOPE_PROPOSALS_WRITE = "proposals.write"
SCOPE_VOCAB_READ = "vocab.read"
SCOPE_SEARCH = "search.use"
SCOPE_UPCOMING_READ = "upcoming.read"
ALL_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_AGENT_RUNS,
        SCOPE_CHANGES_WRITE,
        SCOPE_PROPOSALS_WRITE,
        SCOPE_VOCAB_READ,
        SCOPE_SEARCH,
        SCOPE_UPCOMING_READ,
    }
)


# ---------------------------------------------------------------------------------------
# Ungated by design (playbook 5). Five shapes, each read back and disagreed with in review.
# ---------------------------------------------------------------------------------------
class UngatedReason(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py)."""

    SELF = "self"  # acts only on the caller's own principal (GET /me, own passkeys)
    BOOTSTRAP = "bootstrap"  # needed before any principal exists (product name, health)
    CAPABILITY = "capability"  # the credential itself is the capability (enrolment ceremony)
    LOGIC_GATE = "logic-gate"  # logic.py decides per record; no single permission fits
    PUBLIC_TOKEN = "public-token"  # noqa: S105 an enum value, not a credential  # a revocable token in the URL is the grant (calendar feed)


@dataclass(frozen=True)
class Ungated:
    reason: UngatedReason
    note: str  # one sentence a reviewer can disagree with


# (METHOD, path as Ninja registers it under /api/v1) -> why it needs no permission gate.
UNGATED_BY_DESIGN: dict[tuple[str, str], Ungated] = {
    ("GET", "/me"): Ungated(
        UngatedReason.SELF,
        "Returns the caller's own principal; the enrolment session may call it too (AC-ID2).",
    ),
    ("GET", "/reference/product"): Ungated(
        UngatedReason.BOOTSTRAP,
        "The sign-in page needs the product name before anyone has signed in.",
    ),
}


# ---------------------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Gate:
    kind: str  # "permission" | "scope"
    value: str


F = TypeVar("F", bound=Callable[..., Any])


def _principal(request: HttpRequest) -> Principal:
    principal = getattr(request, "auth", None)
    if not isinstance(principal, Principal):
        raise ProblemError(status=401, code="unauthenticated", detail="Sign in to continue.")
    return principal


def requires_permission(permission: str) -> Callable[[F], F]:
    if permission not in ALL_PERMISSIONS:
        raise ValueError(f"{permission!r} is not a permission constant in apps.shared.permissions")

    def decorate(view: F) -> F:
        @functools.wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            principal = _principal(request)
            if not principal.has_permission(permission):
                raise ProblemError(
                    status=403,
                    code="permission_denied",
                    detail="You do not have access to this.",
                    required_permission=permission,
                )
            return view(request, *args, **kwargs)

        wrapper.__cw_gate__ = Gate("permission", permission)  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate


def requires_scope(scope: str) -> Callable[[F], F]:
    if scope not in ALL_SCOPES:
        raise ValueError(f"{scope!r} is not a scope constant in apps.shared.permissions")

    def decorate(view: F) -> F:
        @functools.wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            principal = _principal(request)
            if not principal.has_scope(scope):
                raise ProblemError(
                    status=403,
                    code="permission_denied",
                    detail="This key does not have the scope for that.",
                    required_permission=scope,
                )
            return view(request, *args, **kwargs)

        wrapper.__cw_gate__ = Gate("scope", scope)  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate


def requires_step_up(view: F) -> F:
    """A fresh passkey assertion within STEP_UP_FRESHNESS_MINUTES (ID-06, AC-ID3). The
    assertion reference is stored on the audit event by the logic that completes the
    action; this decorator only refuses stale sessions with 403 `step_up_required`."""

    @functools.wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        principal = _principal(request)
        if principal.kind is not PrincipalKind.USER:
            raise ProblemError(
                status=403, code="step_up_required", detail="A person must confirm this with a passkey."
            )
        freshness = timedelta(minutes=settings.STEP_UP_FRESHNESS_MINUTES)
        if principal.step_up_at is None or timezone.now() - principal.step_up_at > freshness:
            raise ProblemError(
                status=403,
                code="step_up_required",
                detail="Confirm this action with your passkey.",
            )
        return view(request, *args, **kwargs)

    wrapper.__cw_step_up__ = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


def gate_of(view: Callable[..., Any]) -> Gate | None:
    return getattr(view, "__cw_gate__", None)


def step_up_of(view: Callable[..., Any]) -> bool:
    return bool(getattr(view, "__cw_step_up__", False))
