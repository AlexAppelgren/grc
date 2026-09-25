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
    # c8-reg-links-history (REG-05): a link is removed by id.
    ("DELETE", "/internal-links/{link_id}", "register.InternalLink", "internal_link"),
    # c8-participants (COL-04): a participant on a register entry for an obligation private to
    # tenant A, so the obligation itself is invisible to tenant B.
    ("GET", "/obligations/{obligation_id}/participants", "collab.Participant", "obligation_participant"),
    ("DELETE", "/obligations/{obligation_id}/participants/{participant_id}", "collab.Participant", "obligation_participant"),
]
