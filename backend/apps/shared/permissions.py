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

# Four eyes applies to every approve permission: never the requester (PRD §6). Not to
# `applicability.approve`: one person sets applicability after a confirmation (D-75).
APPROVE_PERMISSIONS: frozenset[str] = frozenset(
    {FOOTPRINT_APPROVE, CASES_SIGNOFF, RISK_ACCEPT_APPROVE, PROPOSALS_REVIEW}
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
        APPLICABILITY_APPROVE,
        RISK_ACCEPT_APPROVE,
        PROPOSALS_CREATE,
        EXPORTS_CREATE,
        AI_LOG_READ,
        VOCAB_MANAGE,
        WORKFLOW_MANAGE,
    },
    "owner": _EVERYONE
    | {CASES_WORK, CASES_CONTRIBUTE, REGISTER_EDIT, GAPS_EDIT},
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
# The second, independent principal an agent may be (PRO-S13, D-62, ADR 0054): reads the
# same review queue a person reads and may approve, correct or reject through the same
# logic, which still writes the library only through an approved proposal. Platform-only
# (PLATFORM_ONLY_SCOPES below): a key carrying a tenant is refused it at creation (422,
# apps/identity/api_keys_logic.py) and at the review gate (403,
# apps/proposals/api.py:require_reviewer).
SCOPE_PROPOSALS_REVIEW = "proposals:review"
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
        SCOPE_PROPOSALS_REVIEW,
    }
)
# A scope a tenant's own key may never hold, however it is granted (ID-10, D-61, D-62): the
# review queue is the platform's, never a bank's, and so is the watch feed. Opening a run,
# logging a source check and writing a change's facts are what bleqq's own agents do for
# every bank at once, and D-61 says a bank's agent never writes the facts every other bank
# reads; a bank's own agents are R2 and write only in its zone, through routes that do not
# exist yet. A bank's key is refused these at creation (422,
# apps/identity/api_keys_logic.py), and a key that already holds one works without it, with
# a `key_scopes_withheld` row in the security log. This is the one place the rule is a set
# membership test rather than a sentence.
PLATFORM_ONLY_SCOPES: frozenset[str] = frozenset(
    {SCOPE_PROPOSALS_REVIEW, SCOPE_AGENT_RUNS_WRITE, SCOPE_SOURCES_WRITE, SCOPE_CHANGES_WRITE}
)
# What a bank's own key may be given: reads, and filing a proposal, which changes nothing
# until someone independent approves it (AC-PRO1).
TENANT_KEY_SCOPES: frozenset[str] = ALL_SCOPES - PLATFORM_ONLY_SCOPES

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
    FOOTPRINT_REQUEST: "Request a change to the regulatory scope.",
    FOOTPRINT_APPROVE: "Approve a change to the regulatory scope requested by someone else.",
    CASES_TRIAGE: "Triage new cases: urgency and owner.",
    CASES_WORK: "Work a case: so what, assessment, actions, evidence, request sign-off.",
    CASES_CONTRIBUTE: "Contribute to a case: assessment input, actions, evidence.",
    CASES_SIGNOFF: "Sign off a case worked by someone else.",
    REGISTER_EDIT: "Edit register entries.",
    GAPS_EDIT: "Edit gaps.",
    APPLICABILITY_APPROVE: "Set whether an obligation applies, after confirming it.",
    RISK_ACCEPT_APPROVE: "Approve a risk acceptance requested by someone else.",
    PROPOSALS_CREATE: "Propose a change to the shared library.",
    EXPORTS_CREATE: "Create exports.",
    AI_LOG_READ: "Read the AI generation log.",
    MEMBERS_MANAGE: "Invite, change and deactivate members; re-issue enrolment; revoke sessions.",
    ROLES_MANAGE: "Create and change the tenant's roles.",
    SECURITY_MANAGE: (
        "Change the security policy and read the security log; includes approving, declining and "
        "revoking support access, and requesting or approving tenant exit, never both by the same person."
    ),
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
    SUPPORT_ACCESS_GRANT: "Request support access to a bank and enter it read-only once a tenant admin approves.",
    SYSTEM_HEALTH: "Read system health.",
    SCOPE_PROPOSALS_REVIEW: "Read the proposal queue and approve, correct or reject a proposal, as an independent agent (platform-only).",
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
_LOGIC_WATCH_READER = "watch.read in the caller's tenant, an agent's key with library:read, because a run must know which sources to check, or sources.manage in the console, which has no tenant and so no watch.read, for the read-only Sources page (WAT-01, AGT-02, ruling 3). The gate is apps/watch/api.py:require_watch_reader, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_CHANGE_FACTS = "An agent's key with changes:write, or a library editor with proposals.review; a change's facts are library facts and no tenant role holds that (WAT-02, WAT-03, PRO-01). The gate is apps/watch/api.py:require_change_writer, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_CURATION_CONFIRM = "A platform key bound to an agent definition and holding the scope `proposals:review`, or a person holding `proposals.review` with a fresh passkey assertion, confirms a change's curated facts for the shared library, because one decorator cannot express 'a session or a key' (WAT-03, WAT-04, D-74). The gate is apps/watch/api.py:require_curation_confirmer, which refuses a tenant-carrying key and a key bound to no agent (`agent_not_bound`), names the scope it wanted to a key and the permission it wanted to a person, and calls `enforce_step_up` for the person; the write refuses an agent confirming what it or another key of its agent suggested."
_LOGIC_LIBRARY_RECORDS = "library.read in the caller's tenant, or an agent's key holding library:read; one read serves the inventory and the agents (INV-03, AGT-02)."
_LOGIC_UPCOMING_READER = "roadmap.read in the caller's tenant, or an agent's key with upcoming:read, because the newsletter run has to know which dates are already public (HOM-04, AGT-02). The list holds library facts only — no case, no footprint verdict, no owner, no 'So what?' — which is what makes a key safe on it, and it is the one route of the home app a key reaches. The gate is apps/home/api.py:require_upcoming_reader, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_PROPOSALS_REVIEW = "The queue read, the detail read, approve and reject accept a session holding `proposals.review` or a platform key bound to an agent and holding the scope `proposals:review`, because `Principal.has_permission`/`has_scope` are kind-exclusive and one decorator cannot express 'a session or a key' (PRO-01, PRO-S13, PRO-S14, D-62, ADR 0054). The gate is apps/proposals/api.py:require_reviewer, which branches on the principal kind, refuses a tenant-carrying key even if its scopes list somehow names the scope, refuses a key bound to no agent definition (`agent_not_bound`), and never applies a step-up to a key, which holds no passkey assertion; approve calls `enforce_step_up` for a person in its body."
_PUBLIC_CALENDAR_TOKEN = "The revocable token in the calendar address is the whole grant: a calendar client sends no header, follows no sign-in and cannot be asked for a passkey, so the URL is the only credential it can carry (HOM-04, D-52, ADR 0045). The mitigations are the ones that decision weighed. The token is `<prefix>.<secret>` with 256 bits of secret, kept as a lookup prefix beside the secret's SHA-256, shown once and never again. It rides in the query string, not the path, because our own access log prints the route and drops the query while a hosting edge writes whole request lines, which makes this the one named exception to CONVENTIONS 3.6 and is pinned by a guard test that no other route reads a token from the query string. A person may hold only CALENDAR_FEEDS_PER_USER addresses and mints one only from a recent sign-in or a step-up, so a stolen access token cannot leave a lasting one behind. Every fetch re-checks that the owner is still a member holding roadmap.read and has not been enrolled again, revoking the subscription when a check fails; an idle one expires after CALENDAR_FEED_IDLE_DAYS; unknown, revoked and expired answer one 404. What is left is the residual risk the decision accepted and the dialog states: whoever holds the address can see which public regulatory dates, stated to the day, the bank has open work on, and nothing else - no internal deadline, owner, urgency or 'So what?' reaches a calendar. The behaviour is apps/home/feed.py's and apps/home/tests_feed.py proves each of these mitigations."  # noqa: S105 a reviewer's note, not a credential

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
    ("GET", "/proposals"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PROPOSALS_REVIEW),
    ("GET", "/proposals/{proposal_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PROPOSALS_REVIEW),
    ("POST", "/proposals/{proposal_id}/approve"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PROPOSALS_REVIEW),
    ("POST", "/proposals/{proposal_id}/reject"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PROPOSALS_REVIEW),
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
    ("GET", "/instruments"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/instruments/{instrument_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/instruments/{instrument_id}/provisions"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/provisions/{provision_id}/diff"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
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
    ("POST", "/changes/{change_id}/confirmation"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CURATION_CONFIRM),
    # Chunk 4 (proposals and the platform console). New entries are appended here, so two
    # sessions adding one at the same time do not land on the same line.
    ("POST", "/me/visit"): Ungated(UngatedReason.SELF, _SELF_ME),

    # The two library reads chunk 5 adds (c5-contract-api-screens). Both serve a person's
    # session and an agent's key, which one decorator cannot express, so they take the same
    # logic gate as chunk 3's record reads: apps/taxonomy/http.py:require_library_read.
    # `GET /obligations/{obligation_id}/sources` is deliberately readable by a key holding
    # library:read alone, because that is how a run re-checks a record against its source
    # without any write scope; the correction it finds is a proposal (AGT-01, PRO-01).
    ("GET", "/authorities"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/obligations/{obligation_id}/sources"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),

    # Chunk 6 (home, the briefing, the roadmap and the calendar feed). Seven of the nine
    # operations carry a single permission and are not here; `GET /home` carries
    # `roadmap.read`, which every system role holds, rather than being left ungated. These
    # two cannot: one decorator expresses a permission or a scope and never "either", and a
    # calendar client presents no principal at all.
    #
    # `c6-home-api-contract`'s brief said no chunk 6 route would join this list, on the
    # reading that `getHome` would be the one tempted to. That reading does not survive the
    # two routes below, exactly as the chunk 5 brief's identical sentence was amended for
    # its eight dual-principal routes. `UngatedReason.PUBLIC_TOKEN` was written in chunk 1
    # naming this calendar feed, so the shape was expected; what changed is only where it is
    # written down. A reviewer disagreeing with either note should say so before the merge.
    #
    # The ICS route's path is `feed.ics` and its token is a query parameter, which D-52 and
    # ADR 0045 decided after the contract first declared `/calendar/{feedToken}`: the token
    # in a path reaches a hosting edge's request log, and the query string does not reach
    # ours. `apps/home/tests_contract.py` pins that no other operation takes a token in its
    # query string, so the exception stays one route wide.
    ("GET", "/upcoming"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_UPCOMING_READER),
    ("GET", "/calendar/feed.ics"): Ungated(UngatedReason.PUBLIC_TOKEN, _PUBLIC_CALENDAR_TOKEN),

    # c8-tenants-contract (TEN-02, TEN-03, TEN-06, COL-04). The bank's organisation, its teams
    # and who from the platform may look in are read by every member: the pickers, the
    # department view and the Support access panel need them. Writes keep their permission.
    ("GET", "/tenant/org-units"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/org-units/{org_unit_id}/licences"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/products"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/teams"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/teams/{key}/members"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/support-access"): Ungated(
        UngatedReason.CAPABILITY,
        "Every member may see who from the platform asked to look in, and who was let in (TEN-06, D-49).",
    ),
    ("GET", "/reference/people"): Ungated(
        UngatedReason.CAPABILITY,
        "A member's session is the grant, never an enrolment session: the owner and participant "
        "pickers need the bank's active members, as ids and names only; `GET /tenant/members` "
        "stays under members.manage (COL-04, TEN-03).",
    ),
    # c10-out-of-office (TEN-04): the caller's own absence on their own membership. The
    # delegate check inside is the gate on what it may name (delegate_cannot_approve).
    ("GET", "/me/out-of-office"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("PUT", "/me/out-of-office"): Ungated(UngatedReason.SELF, _SELF_ME),
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
