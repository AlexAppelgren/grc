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

Every other key passes untouched: a bank's unbound key and bleqq's own agent keys keep
the scopes and routes they had.
"""

from __future__ import annotations

import functools

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest

from apps.shared.authentication import ApiKeyAuth, Principal
from apps.shared.errors import ProblemError
from apps.shared.permissions import step_up_of
from apps.shared.routes import RegisteredOperation, iter_operations

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
    _limit_rate(principal)
    operation = operation_of(request)
    if operation is not None and step_up_of(operation.view_func):
        raise ProblemError(
            status=403, code="step_up_required", detail="A person must confirm this with a passkey; a key or token cannot."
        )
    if request.method in READ_METHODS:
        return
    if operation is None or (operation.method, operation.path) not in READ_ONLY_ALLOWED:
        raise ProblemError(status=403, code="read_only_credential", detail="This key or token reads and cannot change anything.")
