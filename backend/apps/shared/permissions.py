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

# --- Tenant permissions (PRD §6); the comment after each row names who holds it by default ---
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
# The bank's own queue (INV-07, OWN-03; D-57, ADR 0050): approve or reject a proposal of the
# bank's own record. A tenant permission and never a platform grant or an API key scope.
PRIVATE_RECORDS_APPROVE = "private_records.approve"  # compliance officer, approver
EXPORTS_CREATE = "exports.create"  # admin, compliance officer, approver, auditor
AI_LOG_READ = "ai_log.read"  # admin, compliance officer, approver, auditor
MEMBERS_MANAGE = "members.manage"  # admin
ROLES_MANAGE = "roles.manage"  # admin
SECURITY_MANAGE = "security.manage"  # admin
VOCAB_MANAGE = "vocab.manage"  # admin, compliance officer
WORKFLOW_MANAGE = "workflow.manage"  # admin, compliance officer
AGENTS_MANAGE = "agents.manage"  # admin
INTEGRATIONS_MANAGE = "integrations.manage"  # admin
# A bank's own agents and personal tokens (ACC-01, ACC-03, D-77).
AGENT_ACCESS_MANAGE = "agent_access.manage"  # admin
TOKENS_CREATE = "tokens.create"  # admin, compliance officer, owner

# --- Platform permissions (PRD §6): library_editor and platform_admin ---
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
        PRIVATE_RECORDS_APPROVE,
        EXPORTS_CREATE,
        AI_LOG_READ,
        MEMBERS_MANAGE,
        ROLES_MANAGE,
        SECURITY_MANAGE,
        VOCAB_MANAGE,
        WORKFLOW_MANAGE,
        AGENTS_MANAGE,
        INTEGRATIONS_MANAGE,
        AGENT_ACCESS_MANAGE,
        TOKENS_CREATE,
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
    {FOOTPRINT_APPROVE, CASES_SIGNOFF, RISK_ACCEPT_APPROVE, PROPOSALS_REVIEW, PRIVATE_RECORDS_APPROVE}
)

# --- System roles as the PRD's matrix states them (ID-09) ---
# Kept here so the seed and the seed-integrity guard read one source.
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
        AGENT_ACCESS_MANAGE,
        TOKENS_CREATE,
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
        PRIVATE_RECORDS_APPROVE,
        EXPORTS_CREATE,
        AI_LOG_READ,
        VOCAB_MANAGE,
        WORKFLOW_MANAGE,
        TOKENS_CREATE,
    },
    "owner": _EVERYONE
    | {CASES_WORK, CASES_CONTRIBUTE, REGISTER_EDIT, GAPS_EDIT, TOKENS_CREATE},
    "approver": _EVERYONE
    | {
        FOOTPRINT_APPROVE,
        CASES_SIGNOFF,
        APPLICABILITY_APPROVE,
        RISK_ACCEPT_APPROVE,
        PRIVATE_RECORDS_APPROVE,
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

# --- API key scopes (ID-10) ---
# Shared by `@requires_scope` and the key console. No scope allows a library edit (AC-PRO1,
# ID-S21).
SCOPE_AGENT_RUNS_WRITE = "agent-runs:write"
SCOPE_SOURCES_WRITE = "sources:write"
SCOPE_CHANGES_WRITE = "changes:write"
SCOPE_PROPOSALS_WRITE = "proposals:write"
SCOPE_SEARCH_READ = "search:read"
SCOPE_LIBRARY_READ = "library:read"
SCOPE_UPCOMING_READ = "upcoming:read"
SCOPE_TENANT_READ = "tenant:read"
# The second, independent principal an agent may be (PRO-S13, D-62, ADR 0054): it works the
# review queue through the same logic, which writes the library only through an approved
# proposal. Platform-only: refused to a tenant key at creation and at the review gate.
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
# Scopes a tenant's own key may never hold (ID-10, D-61, D-62): the review queue and the watch
# feed are the platform's, and a bank's agent never writes the facts every bank reads. Refused
# at creation (422); an old key holding one works without it, with `key_scopes_withheld` in
# the security log.
PLATFORM_ONLY_SCOPES: frozenset[str] = frozenset(
    {SCOPE_PROPOSALS_REVIEW, SCOPE_AGENT_RUNS_WRITE, SCOPE_SOURCES_WRITE, SCOPE_CHANGES_WRITE}
)
# What a bank's own key may be given: reads, and filing a proposal, which changes nothing
# until someone independent approves it (AC-PRO1).
TENANT_KEY_SCOPES: frozenset[str] = ALL_SCOPES - PLATFORM_ONLY_SCOPES
# What a credential of an agent access entry, and every personal token, may hold (ACC-03, ADR
# 0055): reads only. `tenant:read` reaches the register only with tenant reach on (D-72,
# D-76). A CHECK on api_key holds the same set.
AGENT_ACCESS_SCOPES: frozenset[str] = frozenset(
    {SCOPE_LIBRARY_READ, SCOPE_SEARCH_READ, SCOPE_UPCOMING_READ, SCOPE_TENANT_READ}
)

# --- The permission catalogue for the role editor (`GET /reference/permissions`, ID-09) ---
# A one-line description per constant; the group is the word before the dot.
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
    PRIVATE_RECORDS_APPROVE: "Approve or reject a proposal of the organisation's own records, filed by someone else.",
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
    AGENT_ACCESS_MANAGE: "Register, change and revoke the agents the bank runs itself, issue their keys and set their tenant reach.",
    TOKENS_CREATE: "Mint a personal access token for yourself, which acts as you and never exceeds your own permissions.",
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


# --- Ungated by design (playbook 5): five shapes ---
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
_LOGIC_WATCH_READER = "watch.read in the caller's tenant, an agent's key with library:read, because a run must know which sources to check, or sources.manage in the console, which has no tenant and so no watch.read, for the read-only Sources page (WAT-01, AGT-02, ruling 3). The gate is apps/watch/api.py:require_watch_reader, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_CHANGE_FACTS = "An agent's key with changes:write, or a library editor with proposals.review; a change's facts are library facts and no tenant role holds that (WAT-02, WAT-03, PRO-01). The gate is apps/watch/api.py:require_change_writer, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_CURATION_CONFIRM = "A platform key bound to an agent definition and holding the scope `proposals:review`, or a person holding `proposals.review` with a fresh passkey assertion, confirms a change's curated facts for the shared library, because one decorator cannot express 'a session or a key' (WAT-03, WAT-04, D-74). The gate is apps/watch/api.py:require_curation_confirmer, which refuses a tenant-carrying key and a key bound to no agent (`agent_not_bound`), names the scope it wanted to a key and the permission it wanted to a person, and calls `enforce_step_up` for the person; the write refuses an agent confirming what it or another key of its agent suggested."
_LOGIC_LIBRARY_RECORDS = "library.read in the caller's tenant, or an agent's key holding library:read; one read serves the inventory and the agents (INV-03, AGT-02)."
_LOGIC_UPCOMING_READER = "roadmap.read in the caller's tenant, or an agent's key with upcoming:read, because the newsletter run has to know which dates are already public (HOM-04, AGT-02). The list holds library facts only — no case, no footprint verdict, no owner, no 'So what?' — which is what makes a key safe on it, and it is the one route of the home app a key reaches. The gate is apps/home/api.py:require_upcoming_reader, which branches on the principal kind and names the scope it wanted to a key and the permission it wanted to a person."
_LOGIC_PROPOSALS_REVIEW = "The queue read, the detail read, approve and reject accept a session holding `proposals.review` or a platform key bound to an agent and holding the scope `proposals:review`, because `Principal.has_permission`/`has_scope` are kind-exclusive and one decorator cannot express 'a session or a key' (PRO-01, PRO-S13, PRO-S14, D-62, ADR 0054). The gate is apps/proposals/api.py:require_reviewer, which branches on the principal kind, refuses a tenant-carrying key even if its scopes list somehow names the scope, refuses a key bound to no agent definition (`agent_not_bound`), and never applies a step-up to a key, which holds no passkey assertion; approve calls `enforce_step_up` for a person in its body."
_PUBLIC_CALENDAR_TOKEN = "The revocable token in the calendar address is the whole grant: a calendar client sends no header, follows no sign-in and cannot be asked for a passkey, so the URL is the only credential it can carry (HOM-04, D-52, ADR 0045). The mitigations are the ones that decision weighed. The token is `<prefix>.<secret>` with 256 bits of secret, kept as a lookup prefix beside the secret's SHA-256, shown once and never again. It rides in the query string, not the path, because our own access log prints the route and drops the query while a hosting edge writes whole request lines, which makes this the one named exception to CONVENTIONS 3.6 and is pinned by a guard test that no other route reads a token from the query string. A person may hold only CALENDAR_FEEDS_PER_USER addresses and mints one only from a recent sign-in or a step-up, so a stolen access token cannot leave a lasting one behind. Every fetch re-checks that the owner is still a member holding roadmap.read and has not been enrolled again, revoking the subscription when a check fails; an idle one expires after CALENDAR_FEED_IDLE_DAYS; unknown, revoked and expired answer one 404. What is left is the residual risk the decision accepted and the dialog states: whoever holds the address can see which public regulatory dates, stated to the day, the bank has open work on, and nothing else - no internal deadline, owner, urgency or 'So what?' reaches a calendar. The behaviour is apps/home/feed.py's and apps/home/tests_feed.py proves each of these mitigations."  # noqa: S105 a reviewer's note, not a credential

# Collaboration.
_SELF_NOTIFICATIONS = "Acts only on the caller's own notification rows; no parameter reaches another person's (COL-02)."
_SELF_MY_COMMENTS = "Returns the caller's own comments and mentions, filtered afterwards by each subject's read permission (COL-01)."
_LOGIC_MY_WORK = "Any member's session opens My work, their own or any department's; the service applies register.read to register entries and internal items and cases.read to cases, row by row and count by count, and names a kind it left out in permissionLimited rather than refusing the page (HOM-05, D-23). The department view is a filter and never a grant."
_LOGIC_CASE_PARTICIPANT_REMOVAL = "A person may always leave their own participation; on an obligation that needs register.read, which apps/collab/api.py:remove_participant checks first, and removing anyone else's needs register.edit on an obligation or cases.contribute on a case, which the logic checks on the row (D-19, COL-04)."
_LOGIC_PARTICIPANTS_READ = "register.read for an obligation's participants, cases.read for a case's: apps/collab/api.py:list_participants checks participants.READ_PERMISSION[subjectType] with require_any before any lookup, naming it in the 403 (COL-04)."
_LOGIC_PARTICIPANTS_ADD = "register.edit to add to an obligation, cases.contribute to add to a case: apps/collab/api.py:add_participant checks participants.EDIT_PERMISSION[subjectType] with require_any before any lookup, naming it in the 403 (COL-04, D-20)."
_LOGIC_COMMENT_SUBJECT = "The gate is the read permission of the subject's kind, which `collab/subjects.py` decides per record; the write also needs `comments.write` (COL-01)."

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
    # ACC-03: a member lists and revokes their own tokens even after
    # losing `tokens.create`; minting stays behind the permission and a step-up.
    ("GET", "/me/tokens"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("DELETE", "/me/tokens/{token_id}"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("POST", "/auth/step-up/options"): Ungated(UngatedReason.SELF, _SELF_STEP_UP),
    ("POST", "/auth/step-up/verify"): Ungated(UngatedReason.SELF, _SELF_STEP_UP),
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
    # A logic gate means one route serves more than one principal or permission;
    # apps/taxonomy/http.py decides and still answers the structured 403.
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
    # Batch proposals (PRO-04, AGT-05).
    ("POST", "/proposal-batches"): Ungated(
        UngatedReason.LOGIC_GATE,
        "proposals.review from a platform person, or the proposals:write scope from a platform key naming an open run of its own; no bank's session or key re-tags the library (PRO-04, AGT-05). The gate is apps/proposals/api.py:require_batch_proposer, which refuses a tenant-carrying principal and names the permission or scope it wanted.",
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
    # Library reads: apps/taxonomy/http.py require_library_read decides.
    ("GET", "/obligations"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/obligations/{obligation_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/obligations/{obligation_id}/diff"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/instruments"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/instruments/{instrument_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/instruments/{instrument_id}/provisions"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/provisions/{provision_id}/diff"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    # The agent API: these routes serve more than one kind of principal, so apps/watch/api.py
    # and apps/agents/api.py decide and still answer the structured 403.
    ("GET", "/sources"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_WATCH_READER),
    ("GET", "/sources/coverage"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_WATCH_READER),
    ("POST", "/changes"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("PATCH", "/changes/{change_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("POST", "/changes/{change_id}/events"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("PATCH", "/changes/{change_id}/events/{event_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("PUT", "/changes/{change_id}/obligations"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CHANGE_FACTS),
    ("POST", "/changes/{change_id}/confirmation"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CURATION_CONFIRM),
    # Proposals and the platform console. New entries are appended here, so two changes do
    # not land on the same line.
    ("POST", "/me/visit"): Ungated(UngatedReason.SELF, _SELF_ME),
    # D-122: a person moves their own session to a bank or the console they already hold.
    ("POST", "/me/context"): Ungated(UngatedReason.SELF, _SELF_ME),
    # D-122: an enrolled person joins a bank through an invitation to their own address,
    # behind a step-up on their own session.
    ("POST", "/me/invitations/accept"): Ungated(UngatedReason.SELF, _SELF_ME),
    # Adding a device (ID-04, D-135): nothing names an account until a passkey approves it.
    ("POST", "/auth/device-links"): Ungated(
        UngatedReason.BOOTSTRAP, "A device with no passkey asks for a code; it names no account and is rate limited (D-135)."
    ),
    ("GET", "/auth/device-links/status"): Ungated(
        UngatedReason.PUBLIC_TOKEN, "The device's 256-bit secret, in a header, is the grant, and the answer is one yes or no (D-135)."
    ),
    ("POST", "/auth/device-links/claim"): Ungated(
        UngatedReason.PUBLIC_TOKEN, "The device's single-use secret is the grant, and only a passkey step-up on another device opens it (D-135)."
    ),
    ("POST", "/me/device-links/approve"): Ungated(UngatedReason.SELF, "A person lets a device in as themselves only, behind a passkey step-up (D-135)."),

    # Library reads served to a session and a key alike: require_library_read decides.
    # `GET /obligations/{obligation_id}/sources` is readable with library:read alone, so a
    # run re-checks a record without a write scope (AGT-01, PRO-01).
    ("GET", "/authorities"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),
    ("GET", "/obligations/{obligation_id}/sources"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_LIBRARY_RECORDS),

    # Home: one decorator cannot say "a permission or a scope", and a calendar client presents
    # no principal at all. The ICS token is a query parameter (D-52, ADR 0045): a path reaches
    # a hosting edge's request log; apps/home/tests_contract.py keeps it the only one.
    ("GET", "/upcoming"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_UPCOMING_READER),
    ("GET", "/calendar/feed.ics"): Ungated(UngatedReason.PUBLIC_TOKEN, _PUBLIC_CALENDAR_TOKEN),

    # The organisation, teams and support access panel are read by every member (TEN-02,
    # TEN-03, TEN-06, COL-04); writes keep their permission.
    ("GET", "/tenant/org-units"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/products"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
    ("GET", "/tenant/teams"): Ungated(UngatedReason.CAPABILITY, _CAPABILITY_MEMBER),
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
    # The inbox routes and GET /me/comments act on the caller's own rows; comment reads and
    # writes are gated per record by collab/subjects.py (COL-01, COL-02, HOM-05).
    ("GET", "/notifications"): Ungated(UngatedReason.SELF, _SELF_NOTIFICATIONS),
    ("POST", "/notifications/{notification_id}/read"): Ungated(UngatedReason.SELF, _SELF_NOTIFICATIONS),
    ("POST", "/notifications/read-all"): Ungated(UngatedReason.SELF, _SELF_NOTIFICATIONS),
    ("GET", "/me/comments"): Ungated(UngatedReason.SELF, _SELF_MY_COMMENTS),
    ("GET", "/comments"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_COMMENT_SUBJECT),
    ("POST", "/comments"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_COMMENT_SUBJECT),

    # My work (HOM-05).
    ("GET", "/me/work"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_MY_WORK),
    # Participants (COL-04, CAS-03, B-14): one route per verb for both subjects, each subject
    # keeping its own permissions (participants.READ_PERMISSION, EDIT_PERMISSION); removal is
    # gated in logic, because leaving needs no permission.
    ("GET", "/participants"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PARTICIPANTS_READ),
    ("POST", "/participants"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_PARTICIPANTS_ADD),
    ("DELETE", "/participants/{participant_id}"): Ungated(UngatedReason.LOGIC_GATE, _LOGIC_CASE_PARTICIPANT_REMOVAL),
    # The caller's own absence (TEN-04); `delegate_cannot_approve` gates what it may name.
    ("GET", "/me/out-of-office"): Ungated(UngatedReason.SELF, _SELF_ME),
    ("PUT", "/me/out-of-office"): Ungated(UngatedReason.SELF, _SELF_ME),
    # ACC-05: one endpoint for every tool, so no single scope fits it.
    ("POST", "/mcp"): Ungated(
        UngatedReason.LOGIC_GATE,
        "Only the key of an agent access entry or a personal access token, through ApiKeyAuth; any other key "
        "answers 403 agent_access_only. The gate is apps/integrations/mcp.py:handle, and the tool list offers a "
        "tool only when the credential holds the scope its route needs, the register tool only with reach too.",
    ),
    # SRC-01, ACC-04, ACC-05: a bank's own agent searches the library in its scope.
    ("POST", "/search"): Ungated(
        UngatedReason.LOGIC_GATE,
        "search.use in the caller's tenant, or a key holding search:read, which is how an agent a bank runs "
        "itself searches; an agent access credential's search is narrowed to its entry's scope (SRC-01, ACC-04). "
        "The gate is apps/search/api.py:require_searcher, which branches on the principal kind and names the "
        "scope it wanted to a key and the permission it wanted to a person.",
    ),
}


# --- Decorators ---
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
    """Adding or removing a passkey from a full session (F9): allowed while the session is
    younger than STEP_UP_FRESHNESS_MINUTES (from its creation), or with a fresh assertion,
    whose id is returned. A sign-in never counts as a step-up for `@requires_step_up`."""
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
