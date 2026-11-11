"""Enumerate the operations Ninja registered: the same objects that produce openapi.json
(playbook 5). The route guards, the audit-on-write guard and the tenant-isolation guard
all read this one function so they can never disagree about what exists."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ninja import NinjaAPI


@dataclass(frozen=True)
class RegisteredOperation:
    method: str
    path: str  # as registered under /api/v1, e.g. "/me"
    operation_id: str
    view_func: Callable[..., Any]
    auth: Any


def _join(prefix: str, path: str) -> str:
    parts = [segment for segment in (prefix.strip("/"), path.strip("/")) if segment]
    return "/" + "/".join(parts)


def iter_operations(api: NinjaAPI) -> Iterator[RegisteredOperation]:
    for bound in api._get_bound_routers():
        for path, path_view in bound.path_operations.items():
            for operation in path_view.operations:
                for method in operation.methods:
                    yield RegisteredOperation(
                        method=method.upper(),
                        path=_join(bound.prefix, path),
                        operation_id=operation.operation_id
                        or api.get_openapi_operation_id(operation),
                        view_func=operation.view_func,
                        auth=operation.auth_callbacks,
                    )


# Tenant-scoped routes, so the tenant-isolation guard requests tenant A's record as tenant B
# and demands a 404. Entries are (method, path with its query where the route reads its
# record from one, model label, factory name in apps/shared/factories.py).
TENANT_SCOPED_ROUTES: list[tuple[str, str, str, str]] = [
    ("PATCH", "/tenant/members/{user_id}", "identity.Membership", "member_user"),
    ("GET", "/tenant/members/{user_id}/sessions", "identity.Membership", "member_user"),
    ("DELETE", "/tenant/members/{user_id}/sessions", "identity.Membership", "member_user"),
    ("DELETE", "/tenant/invitations/{invitation_id}", "identity.Invitation", "invitation"),
    ("PATCH", "/tenant/roles/{key}", "identity.TenantRole", "tenant_role_key"),
    ("DELETE", "/tenant/api-keys/{key_id}", "identity.ApiKey", "api_key"),
    ("DELETE", "/tenant/api-keys/{key_id}", "identity.ApiKey", "member_personal_token"),
    ("DELETE", "/me/tokens/{token_id}", "identity.ApiKey", "member_personal_token"),
    ("POST", "/tenant/footprint/requests/{request_id}/approve", "taxonomy.FootprintChangeRequest", "footprint_request"),
    ("POST", "/tenant/footprint/requests/{request_id}/reject", "taxonomy.FootprintChangeRequest", "footprint_request"),
    ("POST", "/tenant/footprint/requests/{request_id}/withdraw", "taxonomy.FootprintChangeRequest", "footprint_request"),
    ("POST", "/vocab/{list_name}/suggestions/{suggestion_id}/decline", "taxonomy.VocabularySuggestion", "vocabulary_suggestion"),
    # Tenants (TEN-02, TEN-03, TEN-05, TEN-06). The licence create is proved in
    # apps/tenants/tests_api_contract.py.
    ("PATCH", "/tenant/org-units/{org_unit_id}", "tenants.OrgUnit", "org_unit"),
    ("PATCH", "/tenant/licences/{licence_id}", "tenants.Licence", "licence"),
    ("PATCH", "/tenant/products/{product_id}", "tenants.TenantProduct", "tenant_product"),
    ("GET", "/tenant/members/{user_id}/open-work", "identity.Membership", "member_user"),
    ("POST", "/tenant/members/{user_id}/remove", "identity.Membership", "member_user"),
    ("POST", "/tenant/support-access/{grant_id}/approve", "tenants.SupportAccess", "support_access"),
    ("POST", "/tenant/support-access/{grant_id}/decline", "tenants.SupportAccess", "support_access"),
    ("POST", "/tenant/support-access/{grant_id}/revoke", "tenants.SupportAccess", "support_access"),
    # public-registers (TEN-07): a lookup in the public registers. Its apply needs a body the
    # guard's empty one fails before the load, so apps/tenants/tests_scenarios.py (TEN-S13)
    # proves that route's 404.
    ("GET", "/tenant/register-lookups/{lookup_id}", "tenants.RegisterLookup", "register_lookup"),
    # Case workflow routes an empty body satisfies; those needing a body are proven in
    # apps/cases/tests_contract.py.
    ("POST", "/changes/{change_id}/restore", "cases.ChangeCase", "case_change"),
    ("POST", "/changes/{change_id}/assessment/start", "cases.ChangeCase", "case_change"),
    ("GET", "/changes/{change_id}/actions", "cases.ChangeCase", "case_change"),
    ("GET", "/changes/{change_id}/evidence", "cases.ChangeCase", "case_change"),
    ("POST", "/changes/{change_id}/signoff/request", "cases.ChangeCase", "case_change"),
    ("POST", "/changes/{change_id}/signoff/approve", "cases.ChangeCase", "case_change"),
    ("POST", "/changes/{change_id}/signoff/send-back", "cases.ChangeCase", "case_change"),
    ("GET", "/changes/{change_id}/case-file", "cases.ChangeCase", "case_change"),
    ("PATCH", "/actions/{action_id}", "cases.Action", "case_action"),
    ("DELETE", "/actions/{action_id}", "cases.Action", "case_action"),
    ("GET", "/evidence/{evidence_id}/download", "cases.Evidence", "case_evidence"),
    ("DELETE", "/evidence/{evidence_id}", "cases.Evidence", "case_evidence"),
    # A legal entity's register row (REG-02).
    ("PATCH", "/obligations/{obligation_id}/register/entities/{org_unit_id}", "register.TenantObligationScope", "register_entity"),
    # Gaps (REG-03); `POST /gaps/{gap_id}/accept-risk` needs a body, so
    # apps/register/tests_gaps.py proves its 404.
    ("PATCH", "/gaps/{gap_id}", "register.Gap", "gap"),
    ("POST", "/gaps/{gap_id}/accept-risk/approve", "register.Gap", "gap"),
    ("POST", "/gaps/{gap_id}/reopen", "register.Gap", "gap"),
    # A link is removed by id (REG-05).
    ("DELETE", "/internal-links/{link_id}", "register.InternalLink", "internal_link"),
    # A Statement of Applicability unit (REG-08).
    ("PATCH", "/units/{unit_id}", "register.SoaUnit", "soa_unit"),
    ("DELETE", "/units/{unit_id}", "register.SoaUnit", "soa_unit"),
    # A participant on a register entry for an obligation private to tenant A (COL-04); the
    # subject rides in the query, which the guard fills too (B-14).
    ("GET", "/participants?subjectType=obligation&subjectId={obligation_id}", "collab.Participant", "obligation_participant"),
    ("DELETE", "/participants/{participant_id}?subjectType=obligation&subjectId={obligation_id}", "collab.Participant", "obligation_participant"),
    # Tenant agents (AGT-04).
    ("PATCH", "/agents/{tenant_agent_id}", "agents.TenantAgent", "tenant_agent"),
    # ACC-08: deciding a request for tenant reach.
    ("POST", "/tenant/reach/requests/{request_id}/approve", "governance.TenantReachRequest", "tenant_reach_request"),
    ("POST", "/tenant/reach/requests/{request_id}/reject", "governance.TenantReachRequest", "tenant_reach_request"),
    # A dated duty occurrence (REG-07).
    ("POST", "/duty-occurrences/{occurrence_id}/complete", "register.DutyOccurrence", "duty_occurrence"),
    # A participant on a case of tenant A, for a change tenant B has no case for (COL-04).
    ("GET", "/participants?subjectType=change&subjectId={change_id}", "collab.Participant", "case_participant"),
    ("DELETE", "/participants/{participant_id}?subjectType=change&subjectId={change_id}", "collab.Participant", "case_participant"),
    # ACC-01, ACC-03, ACC-08: an agent access entry, its keys and its log.
    ("GET", "/agent-access/{uuidstr:entry_id}", "agents.AgentAccess", "agent_access_entry"),
    ("PATCH", "/agent-access/{uuidstr:entry_id}", "agents.AgentAccess", "agent_access_entry"),
    ("POST", "/agent-access/{uuidstr:entry_id}/revoke", "agents.AgentAccess", "agent_access_entry"),
    ("POST", "/agent-access/{uuidstr:entry_id}/keys/{uuidstr:key_id}/revoke", "identity.ApiKey", "agent_access_key"),
    ("GET", "/agent-access/{uuidstr:entry_id}/calls", "agents.AgentAccess", "agent_access_entry"),
    # A comment of tenant A on its own case, and a notification of one of its members.
    ("DELETE", "/comments/{comment_id}", "collab.Comment", "comment"),
    ("POST", "/notifications/{notification_id}/read", "collab.Notification", "notification"),
]


# Every route a support session may call (TEN-06, D-49, ADR 0042), as (method, path under
# /api/v1): the reads the seven support permissions cover, one by one. Anything else is 403
# `support_read_only` until added here (apps/shared/tests_support_routes.py). Deliberately
# off: downloads, search, Ask, calendar feeds, member, role, team and key lists, the tenant
# profile, footprint, support access, proposals, agent runs and the AI log.
SUPPORT_READ_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        # library.read: the shared library and its reference lists.
        ("GET", "/authorities"),
        ("GET", "/instruments"),
        ("GET", "/instruments/{instrument_id}"),
        ("GET", "/instruments/{instrument_id}/provisions"),
        ("GET", "/obligations"),
        ("GET", "/obligations/{obligation_id}"),
        ("GET", "/obligations/{obligation_id}/diff"),
        ("GET", "/obligations/{obligation_id}/sources"),
        ("GET", "/provisions/{provision_id}/diff"),
        ("GET", "/library-updates"),
        ("GET", "/sources"),
        ("GET", "/sources/coverage"),
        ("GET", "/taxonomy/terms"),
        # watch.read: the feed, a change and the weekly briefing.
        ("GET", "/changes"),
        ("GET", "/changes/{change_id}"),
        ("GET", "/obligations/{obligation_id}/changes"),
        ("GET", "/briefings/current"),
        ("GET", "/briefings/{week_start}"),
        # roadmap.read: the timeline home, the roadmap and what is coming up.
        ("GET", "/home"),
        ("GET", "/roadmap"),
        ("GET", "/upcoming"),
        # cases.read: a case's actions, its evidence list and its case file; never a download.
        ("GET", "/changes/{change_id}/actions"),
        ("GET", "/changes/{change_id}/evidence"),
        ("GET", "/changes/{change_id}/case-file"),
        # audit.read: the bank's audit log, where every one of these reads is written.
        ("GET", "/audit-events"),
    }
)
# The support session's own two calls, which read nothing of the bank: turning its refresh
# cookie into the next access token, never past the grant's window, and signing out. Both
# act on the refresh cookie alone.
SUPPORT_SESSION_ROUTES: frozenset[tuple[str, str]] = frozenset({("POST", "/auth/refresh"), ("POST", "/auth/sign-out")})
