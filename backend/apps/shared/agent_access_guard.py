"""The fence around an agent access credential (ACC-03, ACC-09, ADR 0055, ADR 0056).

A service key bound to an agent access entry, and every personal access token, read and
nothing else. `check` runs once per request, from the auth class that resolved the
credential (apps/shared/authentication.py), before any route sees it:

1. Rate. At most `AGENT_ACCESS_RATE_PER_MINUTE` requests a minute per credential, refused
   with 429 `rate_limited`, and the first refusal of each window leaves a
   `credential_rate_limited` row in the security log.
2. Step-up. A route carrying `@requires_step_up` answers 403 `step_up_required`: nothing
   behind the credential can present a passkey, so there is no path to an assertion.
3. Writes. Every other method than a read answers 403 `read_only_credential`, except the
   reads that take a body, in `READ_ONLY_ALLOWED`.

Once past its rate, the call is begun in the access log (ACC-08,
apps/governance/access_log.py), so a refused write or step-up is logged with its 403 and the
row is written after the response.

Every other key passes untouched: a bank's unbound key and bleqq's own agent keys keep
the scopes and routes they had.

The scope statement (ACC-07). A narrowed agent must never read silence as "nothing
applies", so every answer to an agent access credential, an error included, states the
scope it was answered in, through this one mechanism: once past its rate, `check` marks the
request, and `ScopeStatementMiddleware` adds `Agent-Access-Scope` to the response, a JSON
object in ASCII (`scope_statement`): the entry by id and name, the departments and products
it serves, whether they narrow what it reads, and the "as of" date, today where the bank is.
A personal token naming no entry states no entry and no narrowing. `POST
/agent-access/what-applies` carries the same statement in its body as `scope`.
"""

from __future__ import annotations

import functools
import json
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest, HttpResponse

from apps.shared.authentication import ApiKeyAuth, Principal
from apps.shared.errors import ProblemError
from apps.shared.permissions import step_up_of
from apps.shared.routes import RegisteredOperation, iter_operations

if TYPE_CHECKING:
    from apps.agents.schemas import AgentAccessScopeStatement
    from apps.shared.models import Tenant

READ_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
# A read that takes a body (ACC-05): search, what applies and the MCP server's one endpoint.
# `(METHOD, path as Ninja registers it under /api/v1)`, like UNGATED_BY_DESIGN; an entry
# may name a route a later package adds.
READ_ONLY_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {("POST", "/search"), ("POST", "/agent-access/what-applies"), ("POST", "/mcp")}
)
# config/urls.py mounts the API here; Django's resolver reports the route with it.
API_ROUTE_PREFIX = "api/v1/"
RATE_WINDOW_SECONDS = 60
SCOPE_HEADER = "Agent-Access-Scope"
# Set by the MCP server on the request it makes to the route behind a tool
# (apps/integrations/mcp_tools.py): the fence runs on it again, but the MCP request already
# spent the credential's rate. An attribute, never a header, so no caller can set it.
TOOL_CALL = "agent_access_tool_call"
_STATED = "agent_access_scope_principal"


@functools.cache
def _operations() -> dict[tuple[str, str], RegisteredOperation]:
    from config.api import api

    return {(op.method, op.path.replace("{", "<").replace("}", ">")): op for op in iter_operations(api)}


def operation_of(request: HttpRequest) -> RegisteredOperation | None:
    """The operation Django resolved this request to, or None when it resolved to none."""
    match = getattr(request, "resolver_match", None)
    if match is None or not match.route.startswith(API_ROUTE_PREFIX):
        return None
    return _operations().get((request.method or "", "/" + match.route.removeprefix(API_ROUTE_PREFIX)))


def route_takes_keys(request: HttpRequest) -> bool:
    """Whether the resolved operation also accepts `ApiKeyAuth`, which then resolves and
    checks the credential itself."""
    operation = operation_of(request)
    return operation is not None and any(isinstance(auth, ApiKeyAuth) for auth in operation.auth)


def _limit_rate(principal: Principal) -> None:
    from apps.identity import api_keys_logic, rate_limit

    try:
        rate_limit.enforce("agent-access", str(principal.subject_id), settings.AGENT_ACCESS_RATE_PER_MINUTE, RATE_WINDOW_SECONDS)
    except ProblemError:
        if cache.add(f"rl-logged:agent-access:{principal.subject_id}", 1, timeout=RATE_WINDOW_SECONDS):
            api_keys_logic.log_rate_limited(principal)
        raise


def check(request: HttpRequest, principal: Principal) -> None:
    if not principal.is_agent_access:
        return
    if not getattr(request, TOOL_CALL, False):
        _limit_rate(principal)
    setattr(request, _STATED, principal)
    operation = operation_of(request)
    from apps.governance import access_log

    access_log.begin(request, principal, operation.operation_id if operation is not None else "unmatched")
    if operation is not None and step_up_of(operation.view_func):
        raise ProblemError(
            status=403, code="step_up_required", detail="A person must confirm this with a passkey; a key or token cannot."
        )
    if request.method in READ_METHODS:
        return
    if operation is None or (operation.method, operation.path) not in READ_ONLY_ALLOWED:
        raise ProblemError(status=403, code="read_only_credential", detail="This key or token reads and cannot change anything.")


def scope_statement(principal: Principal, tenant: Tenant) -> AgentAccessScopeStatement:
    """The scope an agent access credential is answered in (ACC-07), read under the bank's
    row-level security: the tenant must be activated."""
    from apps.agents.models import AgentAccess
    from apps.agents.schemas import AgentAccessScopeStatement, AgentAccessUnitRef
    from apps.library.reading import today_for

    entry = (
        None
        if principal.agent_access_id is None
        else AgentAccess.objects.filter(pk=principal.agent_access_id).prefetch_related("departments__department", "products__product").first()  # ordering: pk lookup, at most one row
    )
    departments = [] if entry is None else sorted((row.department for row in entry.departments.all()), key=lambda unit: (unit.name, unit.id))
    products = [] if entry is None else sorted((row.product for row in entry.products.all()), key=lambda product: (product.name, product.id))
    return AgentAccessScopeStatement(
        entry=None if entry is None else AgentAccessUnitRef(id=entry.id, name=entry.name),
        departments=[AgentAccessUnitRef(id=unit.id, name=unit.name) for unit in departments],
        products=[AgentAccessUnitRef(id=product.id, name=product.name) for product in products],
        narrowed=bool(departments or products),
        as_of=today_for(tenant),
    )


def _header(tenant_id: uuid.UUID, principal: Principal) -> str | None:
    from apps.shared import tenancy
    from apps.shared.models import Tenant

    with transaction.atomic():
        tenancy.activate(tenant_id)
        tenant = Tenant.objects.filter(pk=tenant_id).first()  # ordering: pk lookup, at most one row
        if tenant is None:  # pragma: no cover - a live credential's bank exists
            return None
        statement = scope_statement(principal, tenant)
    return json.dumps(statement.model_dump(mode="json", by_alias=True), ensure_ascii=True, separators=(",", ":"))


class ScopeStatementMiddleware:
    """Adds `Agent-Access-Scope` to every answer to an agent access credential that passed
    its rate (ACC-07), after the response, in a transaction of its own."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        principal: Principal | None = getattr(request, _STATED, None)
        if principal is not None and principal.tenant_id is not None:
            value = _header(principal.tenant_id, principal)
            if value is not None:
                response[SCOPE_HEADER] = value
        return response
