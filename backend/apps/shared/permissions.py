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
import uuid
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
# API key scopes (ID-10), named as schema v0.3 names them (`api_key.scopes` check). Named
# here so `@requires_scope` and the key console share them. No scope allows a library
# edit (AC-PRO1, ID-S21): the agent writes changes and proposals only.
# ---------------------------------------------------------------------------------------
SCOPE_AGENT_RUNS_WRITE = "agent-runs:write"
SCOPE_SOURCES_WRITE = "sources:write"
SCOPE_CHANGES_WRITE = "changes:write"
SCOPE_PROPOSALS_WRITE = "proposals:write"
SCOPE_SEARCH_READ = "search:read"
SCOPE_LIBRARY_READ = "library:read"
SCOPE_UPCOMING_READ = "upcoming:read"
SCOPE_TENANT_READ = "tenant:read"
ALL_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_AGENT_RUNS_WRITE,
        SCOPE_SOURCES_WRITE,
        SCOPE_CHANGES_WRITE,
        SCOPE_PROPOSALS_WRITE,
        SCOPE_SEARCH_READ,
        SCOPE_LIBRARY_READ,
        SCOPE_UPCOMING_READ,
        SCOPE_TENANT_READ,
    }
)

# ---------------------------------------------------------------------------------------
# The permission catalogue for the role editor (`GET /reference/permissions`, ID-09):
# a one-line description per constant. The group is the word before the dot.
# ---------------------------------------------------------------------------------------
PERMISSION_DESCRIPTIONS: dict[str, str] = {
    LIBRARY_READ: "Read the shared library of instruments, provisions and obligations.",
    WATCH_READ: "Read the watch feed of regulatory changes.",
    ROADMAP_READ: "Read the roadmap of dated changes.",
    SEARCH_USE: "Search and ask questions of the library.",
    COMMENTS_WRITE: "Write comments on cases and records.",
    PROBLEMS_REPORT: "Report a problem with a library record.",
    REGISTER_READ: "Read the obligation register and its statuses.",
    CASES_READ: "Read change cases.",
    REPORTS_READ: "Read reports.",
    AUDIT_READ: "Read the audit log.",
    FOOTPRINT_REQUEST: "Request a footprint change.",
    FOOTPRINT_APPROVE: "Approve a footprint change requested by someone else.",
    CASES_TRIAGE: "Triage new cases: urgency and owner.",
    CASES_WORK: "Work a case: so what, assessment, actions, evidence, request sign-off.",
    CASES_CONTRIBUTE: "Contribute to a case: assessment input, actions, evidence.",
    CASES_SIGNOFF: "Sign off a case worked by someone else.",
    REGISTER_EDIT: "Edit register entries.",
    GAPS_EDIT: "Edit gaps.",
    APPLICABILITY_REQUEST: "Request an applicability decision.",
    APPLICABILITY_APPROVE: "Approve an applicability decision requested by someone else.",
    RISK_ACCEPT_APPROVE: "Approve a risk acceptance requested by someone else.",
    PROPOSALS_CREATE: "Propose a change to the shared library.",
    EXPORTS_CREATE: "Create exports.",
    AI_LOG_READ: "Read the AI generation log.",
    MEMBERS_MANAGE: "Invite, change and deactivate members; re-issue enrolment; revoke sessions.",
    ROLES_MANAGE: "Create and change the tenant's roles.",
    SECURITY_MANAGE: "Change the security policy and read the security log.",
    VOCAB_MANAGE: "Manage the tenant's vocabularies.",
    WORKFLOW_MANAGE: "Manage workflow policy.",
    AGENTS_MANAGE: "Switch agents on and off and set their cadence and budget.",
    INTEGRATIONS_MANAGE: "Manage integrations and API keys.",
    PROPOSALS_REVIEW: "Review proposals in the platform console.",
    LIBRARY_VOCAB_MANAGE: "Manage the library vocabularies.",
    SOURCES_MANAGE: "Manage sources.",
    EVAL_MANAGE: "Manage evaluation sets.",
    TENANTS_MANAGE: "Manage tenants and plans.",
    AGENT_DEFINITIONS_MANAGE: "Manage agent definitions.",
    SUPPORT_ACCESS_GRANT: "Enter a tenant under a logged support access grant.",
    SYSTEM_HEALTH: "Read system health.",
}


def permission_group(permission: str) -> str:
    return permission.split(".", 1)[0]


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


_SELF_ME = "Acts only on the caller's own account: the session is the grant (ID-04)."
_SELF_STEP_UP = "A fresh assertion on the caller's own session (ID-06)."
_BOOTSTRAP_AUTH = "An auth ceremony step that runs before any principal exists; rate limited (ID-02, ID-03)."
_CAPABILITY_ENROL = "The enrolment or full session itself is the capability to add a passkey (ID-02, AC-ID2)."
_CAPABILITY_MEMBER = "Any member's session is the grant: pickers and the shell need labels and the profile (TEN-01)."
_CAPABILITY_VOCAB_READ = "Any session reads the list of lists; pickers, filters and pills need every list (VOC-01)."
_LOGIC_LIBRARY_READ = "A person's session, or an agent's key holding library:read; pickers and agents read one endpoint (AGT-02)."
_LOGIC_VOCAB_WRITE = "vocab.manage writes a tenant list; a library list write is a proposal from proposals.create or library_vocab.manage (VOC-07)."
_LOGIC_PROPOSE = "A term change is a proposal from proposals.create (tenant) or library_vocab.manage (console); never a direct write (VOC-07)."
_LOGIC_RUN_LOG = "agents.manage in a tenant reads the library's runs and its own; system.health reads them in the console (AGT-01, item 14). The gate is the `require_any(AGENTS_MANAGE, SYSTEM_HEALTH)` call in apps/agents/api.py:list_agent_runs, which refuses a session holding neither with the structured 403."
_LOGIC_WATCH_READER = "watch.read in the caller's tenant, or an agent's key with library:read, because a run must know which sources to check (WAT-01, AGT-02). The gate is apps/watch/api.py:require_watch_reader, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_CHANGE_FACTS = "An agent's key with changes:write, or a library editor with proposals.review; a change's facts are library facts and no tenant role holds that (WAT-02, WAT-03, PRO-01). The gate is apps/watch/api.py:require_change_writer, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_LIBRARY_RECORDS = "library.read in the caller's tenant, or an agent's key holding library:read; one read serves the inventory and the agents (INV-03, AGT-02)."

# (METHOD, path as Ninja registers it under /api/v1) -> why it needs no permission gate.
UNGATED_BY_DESIGN: dict[tuple[str, str], Ungated] = {
    ("GET", "/me"): Ungated(
        UngatedReason.SELF,
        "Returns the caller's own principal; the enrolment session may call it too (AC-ID2).",
    ),
    ("PATCH", "/me"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("GET", "/me/passkeys"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("PATCH", "/me/passkeys/{passkey_id}"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("DELETE", "/me/passkeys/{passkey_id}"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("GET", "/me/sessions"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("DELETE", "/me/sessions/{session_id}"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("POST", "/auth/step-up/options"): Ungated(UngatedReason.SELF, _SELF_STEP_UP),
    ("POST", "/auth/step-up/verify"): Ungated(UngatedReason.SELF, _SELF_STEP_UP),
    ("GET", "/reference/product"): Ungated(
        UngatedReason.BOOTSTRAP,
        "The sign-in page needs the product name before anyone has signed in.",
    ),
    ("POST", "/auth/invitations/open"): Ungated(
        UngatedReason.PUBLIC_TOKEN, "The single-use invitation token, in the body, is the grant; rate limited (ID-01)."
    ),
    ("POST", "/auth/invitations/verify"): Ungated(
        UngatedReason.PUBLIC_TOKEN,
        "The single-use invitation token and the emailed code, both in the body, are the grant; rate limited (ID-02).",
    ),
    ("POST", "/auth/code/request"): Ungated(UngatedReason.BOOTSTRAP, _BOOTSTRAP_AUTH),
    ("POST", "/auth/code/verify"): Ungated(UngatedReason.BOOTSTRAP, _BOOTSTRAP_AUTH),
    ("POST", "/auth/passkeys/authenticate/options"): Ungated(UngatedReason.BOOTSTRAP, _BOOTSTRAP_AUTH),
    ("POST", "/auth/passkeys/authenticate/verify"): Ungated(UngatedReason.BOOTSTRAP, _BOOTSTRAP_AUTH),
    ("POST", "/auth/refresh"): Ungated(
        UngatedReason.BOOTSTRAP, "The refresh cookie is the credential; no access token exists yet (D-06)."
    ),
    ("POST", "/auth/sign-out"): Ungated(
        UngatedReason.BOOTSTRAP, "Revokes the session named by the refresh cookie, which may already be stale (D-06)."
    ),
    ("POST", "/auth/passkeys/register/options"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_ENROL),
    ("POST", "/auth/passkeys/register/verify"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_ENROL),
    ("GET", "/tenant"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/roles"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/reference/languages"): Ungated(
        UngatedReason.CAPABILITY, "A reference read for pickers; any session may list the language rows (I18N-01)."
    ),
    ("GET", "/reference/permissions"): Ungated(
        UngatedReason.CAPABILITY,
        "The permission constants are public within a session; the role editor lists them (ID-09).",
    ),
    ("GET", "/e2e/mail-outbox"): Ungated(
        UngatedReason.BOOTSTRAP,
        "Exists only under E2E_MODE (404 otherwise) so journeys can prove the mailer sent nothing (AC-ID1).",
    ),
    # Chunk 2 (vocabularies, taxonomy, footprint, proposals). A logic gate here means one
    # route serves more than one principal or permission; apps/taxonomy/http.py decides and
    # still answers the structured 403 with requiredPermission.
    ("GET", "/vocab"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_VOCAB_READ),
    ("GET", "/vocab/{list_name}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_READ),
    ("GET", "/vocab/{list_name}/{key}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_READ),
    ("POST", "/vocab/{list_name}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_VOCAB_WRITE),
    ("PATCH", "/vocab/{list_name}/{key}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_VOCAB_WRITE),
    ("POST", "/vocab/{list_name}/{key}/retire"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_VOCAB_WRITE),
    ("POST", "/vocab/{list_name}/{key}/restore"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_VOCAB_WRITE),
    ("POST", "/vocab/{list_name}/{key}/merge"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_VOCAB_WRITE),
    ("POST", "/vocab/{list_name}/suggest"): Ungated(
        UngatedReason.CAPABILITY,
        "Any member may suggest a value; it lands with vocab.manage holders or in the proposal queue (VOC-03).",
    ),
    ("GET", "/taxonomy/dimensions"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_READ),
    ("GET", "/taxonomy/terms"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_READ),
    ("POST", "/taxonomy/terms"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PROPOSE),
    ("PATCH", "/taxonomy/terms/{term_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PROPOSE),
    ("POST", "/proposals"): Ungated(
        UngatedReason.LOGIC_GATE,
        "proposals.create from a tenant, library_vocab.manage from the console or the proposals:write scope (PRO-01).",
    ),
    ("GET", "/tenant/footprint"): Ungated(
        UngatedReason.CAPABILITY, "Every member reads the footprint that filters every surface they see (FP-03)."
    ),
    ("GET", "/tenant/footprint/requests"): Ungated(
        UngatedReason.CAPABILITY, "Every member may see which footprint changes were asked for and decided (FP-02)."
    ),
    ("GET", "/reference/jurisdictions"): Ungated(
        UngatedReason.CAPABILITY, "A reference read for pickers; any session may list the jurisdiction rows (I18N-01)."
    ),
    # Chunk 3 (library reads). apps/taxonomy/http.py require_library_read decides.
    ("GET", "/obligations"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/obligations/{obligation_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/obligations/{obligation_id}/diff"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    # Chunk 5 (the agent API). Eight routes serve more than one kind of principal, so
    # apps/watch/api.py and apps/agents/api.py decide and still answer the structured 403
    # with requiredPermission. Everything else the chunk declares carries a single gate.
    # The chunk 5 brief's "none is added to UNGATED_BY_DESIGN" is amended for these eight,
    # each naming the dual-principal gate it defers to (CHUNK5_TASKS.md, c5-contract-api-agent).
    ("GET", "/agent-runs"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_RUN_LOG),
    ("GET", "/sources"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_WATCH_READER),
    ("GET", "/sources/coverage"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_WATCH_READER),
    ("POST", "/changes"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("PATCH", "/changes/{change_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("POST", "/changes/{change_id}/events"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("PATCH", "/changes/{change_id}/events/{event_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("PUT", "/changes/{change_id}/obligations"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
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


def enforce_step_up(request: HttpRequest) -> uuid.UUID:
    """Demand a passkey assertion younger than STEP_UP_FRESHNESS_MINUTES on the caller's
    session (ID-06, AC-ID3); put its id on `request.step_up_assertion_id` and return it so
    logic passes it to `record()`. Used by `@requires_step_up` and, for actions whose
    sensitivity depends on the body (a role change inside a member PATCH), by the route."""
    principal = _principal(request)
    if principal.kind is not PrincipalKind.USER:
        raise ProblemError(status=403, code="step_up_required", detail="A person must confirm this with a passkey.")
    freshness = timedelta(minutes=settings.STEP_UP_FRESHNESS_MINUTES)
    if (
        principal.step_up_at is None
        or principal.step_up_assertion_id is None
        or timezone.now() - principal.step_up_at > freshness
    ):
        raise ProblemError(status=403, code="step_up_required", detail="Confirm this action with your passkey.")
    request.step_up_assertion_id = principal.step_up_assertion_id  # type: ignore[attr-defined]
    return principal.step_up_assertion_id


def enforce_recent_sign_in_or_step_up(request: HttpRequest) -> uuid.UUID | None:
    """Adding or removing a passkey from a full session (security review F9, narrowed):
    allowed while the session is younger than STEP_UP_FRESHNESS_MINUTES (its creation,
    which a refresh does not move), or with a fresh assertion. Returns the assertion id
    when there is one. A sign-in never counts as a step-up for `@requires_step_up`."""
    principal = _principal(request)
    try:
        return enforce_step_up(request)
    except ProblemError:
        created = principal.session_created_at
        if principal.kind is PrincipalKind.USER and created is not None and timezone.now() - created <= timedelta(minutes=settings.STEP_UP_FRESHNESS_MINUTES):
            return None
        raise


def requires_step_up(view: F) -> F:
    """A fresh passkey assertion within STEP_UP_FRESHNESS_MINUTES (ID-06, AC-ID3). The
    assertion reference is put on `request.step_up_assertion_id` for the logic to store
    on the audit event; a stale session is refused with 403 `step_up_required`."""

    @functools.wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        enforce_step_up(request)
        return view(request, *args, **kwargs)

    wrapper.__cw_step_up__ = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


def gate_of(view: Callable[..., Any]) -> Gate | None:
    return getattr(view, "__cw_gate__", None)


def step_up_of(view: Callable[..., Any]) -> bool:
    return bool(getattr(view, "__cw_step_up__", False))
