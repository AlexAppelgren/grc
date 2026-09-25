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


# Tenant-scoped routes register here (chunk 1 onward) so the tenant-isolation guard can
# request a record of tenant A as tenant B for each one and demand a 404. Entries are
# (method, path, model label, factory name); the guard builds the record with the
# factory in apps/shared/factories.py. Phase 0 has none, and the guard enumerates
# an empty registry rather than skipping.
TENANT_SCOPED_ROUTES: list[tuple[str, str, str, str]] = [
    ("PATCH", "/tenant/members/{user_id}", "identity.Membership", "member_user"),
    ("DELETE", "/tenant/members/{user_id}", "identity.Membership", "member_user"),
    ("GET", "/tenant/members/{user_id}/sessions", "identity.Membership", "member_user"),
    ("DELETE", "/tenant/members/{user_id}/sessions", "identity.Membership", "member_user"),
    ("DELETE", "/tenant/invitations/{invitation_id}", "identity.Invitation", "invitation"),
    ("PATCH", "/tenant/roles/{key}", "identity.TenantRole", "tenant_role_key"),
    ("DELETE", "/tenant/api-keys/{key_id}", "identity.ApiKey", "api_key"),
    ("POST", "/tenant/footprint/requests/{request_id}/approve", "taxonomy.FootprintChangeRequest", "footprint_request"),
    ("POST", "/tenant/footprint/requests/{request_id}/reject", "taxonomy.FootprintChangeRequest", "footprint_request"),
    ("POST", "/tenant/footprint/requests/{request_id}/withdraw", "taxonomy.FootprintChangeRequest", "footprint_request"),
    ("POST", "/vocab/{list_name}/suggestions/{suggestion_id}/decline", "taxonomy.VocabularySuggestion", "vocabulary_suggestion"),
    # c8-tenants-contract (TEN-02, TEN-03, TEN-05, TEN-06). The licence create is proved in
    # apps/tenants/tests_api_contract.py: it refuses this guard's empty body before it loads.
    ("PATCH", "/tenant/org-units/{org_unit_id}", "tenants.OrgUnit", "org_unit"),
    ("GET", "/tenant/org-units/{org_unit_id}/licences", "tenants.OrgUnit", "org_unit"),
    ("PATCH", "/tenant/licences/{licence_id}", "tenants.Licence", "licence"),
    ("PATCH", "/tenant/products/{product_id}", "tenants.TenantProduct", "tenant_product"),
    ("GET", "/tenant/teams/{key}/members", "taxonomy.Team", "team_key"),
    ("GET", "/tenant/members/{user_id}/open-work", "identity.Membership", "member_user"),
    ("POST", "/tenant/members/{user_id}/remove", "identity.Membership", "member_user"),
    ("POST", "/tenant/support-access/{grant_id}/approve", "tenants.SupportAccess", "support_access"),
    ("POST", "/tenant/support-access/{grant_id}/decline", "tenants.SupportAccess", "support_access"),
    ("POST", "/tenant/support-access/{grant_id}/revoke", "tenants.SupportAccess", "support_access"),
    # c9-case-contract: the workflow routes whose request an empty body satisfies. Each
    # loads the case under row-level security before its stub answers 501, so another
    # bank's case, action or evidence is a 404 now and stays one when the logic lands. The
    # routes that need a body are proven the same way in apps/cases/tests_contract.py.
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
]


# c8-support-session-guard (TEN-06, D-49, ADR 0042): every route a support session may call,
# as (method, path as Ninja registers it under /api/v1). The reads the seven support
# permissions cover, written out one by one, and nothing else: every other route, a GET
# added later as much as any write, answers 403 `support_read_only` from
# `SupportReadOnlyMiddleware` until someone adds it here, under
# apps/shared/tests_support_routes.py. Deliberately left off: evidence and export downloads,
# search, Ask, the person's own calendar feeds, member, role, team and key lists, the
# tenant's profile, footprint and support-access list, proposals, agent runs and the AI log.
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
        ("GET", "/taxonomy/dimensions"),
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
