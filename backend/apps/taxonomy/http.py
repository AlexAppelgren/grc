"""What the taxonomy and proposals routes share: who is calling, the logic gates, `If-Match`,
and turning a logic `ValidationError` into the one problem shape (playbook 4.2, 4.4).

`answers_problems` is the api.py half of "logic raises ValidationError, api re-raises with
the right status". It adds what the shared handler in config/api.py cannot: the statuses of
this chunk's own codes (`in_use`, `system_row`, `request_pending`, `invalid_transition`,
`idempotency_conflict` are 409, not the default 422) and the `extra` a refusal carries
beside its code (the near match of a duplicate, the usage count of a value in use), so the
screen offers the next step without a second call. It also marks the request's transaction
for rollback, so a refusal raised after a partial write can never commit that write.

The logic gates exist because some routes serve more than one principal or more than one
permission: a library list is proposed with `proposals.create` from a tenant or
`library_vocab.manage` from the console, and read by a person's session or an agent's key
with `library:read`. Each such route is listed in `UNGATED_BY_DESIGN` as `logic-gate`, and
the gate here still answers the structured 403 with `requiredPermission`.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse

from apps.shared import permissions as perms
from apps.shared.audit import Actor, ActorType
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import STATUS_BY_CODE, ProblemError, problem_response

# The codes this chunk introduces that are conflicts with the record's state, not fields
# the caller can fix: 409. Everything else falls through to the shared table, then 422.
CHUNK_STATUS_BY_CODE: dict[str, int] = {
    **STATUS_BY_CODE,
    "in_use": 409,
    "system_row": 409,
    "request_pending": 409,
    "invalid_transition": 409,
    "idempotency_conflict": 409,
    "forbidden": 403,
}

F = TypeVar("F", bound=Callable[..., Any])


def problem_for(exc: ValidationError) -> HttpResponse:
    code = getattr(exc, "code", None) or "validation_error"
    status = CHUNK_STATUS_BY_CODE.get(code, 422)
    error = ProblemError(status=status, code=code, detail=" ".join(exc.messages))
    response = problem_response(error)
    extra = getattr(exc, "extra", None)
    if extra:
        import json

        body = json.loads(response.content)
        body.update(extra)
        response.content = json.dumps(body).encode()
    return response


def answers_problems(view: F) -> F:
    """Innermost decorator of a route: turn a logic refusal into its problem response and
    roll the request's transaction back. `functools.wraps` keeps the gate marks the route
    guard reads."""

    @functools.wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        try:
            return view(request, *args, **kwargs)
        except ValidationError as exc:
            if transaction.get_connection().in_atomic_block:
                transaction.set_rollback(True)
            return problem_for(exc)

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------------------
# Who is calling
# ---------------------------------------------------------------------------------------
def principal(request: HttpRequest) -> Principal:
    value = getattr(request, "auth", None)
    if not isinstance(value, Principal):
        raise ProblemError(status=401, code="unauthenticated", detail="Sign in to continue.")
    return value


def caller_user(request: HttpRequest) -> Any:
    from apps.identity.models import User

    who = principal(request)
    if who.kind is not PrincipalKind.USER:
        raise ProblemError(status=403, code="permission_denied", detail="A person must do this.")
    user = User.objects.filter(pk=who.subject_id).first()  # ordering: pk lookup, at most one row
    if user is None:  # pragma: no cover - a live session always names a user
        raise ProblemError(status=401, code="unauthenticated", detail="Sign in to continue.")
    return user


def caller_tenant(request: HttpRequest) -> Any:
    from apps.shared.models import Tenant

    who = principal(request)
    if who.tenant_id is None:
        raise ProblemError(status=404, code="not_found", detail="Sign in to a company to see this.")
    tenant = Tenant.objects.select_related("default_language").filter(pk=who.tenant_id).first()  # ordering: pk lookup, at most one row
    if tenant is None:  # pragma: no cover - the session's tenant always exists
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return tenant


def actor_for(request: HttpRequest, user: Any = None) -> Actor:
    """The audit actor. A person's name may be in the audit log (playbook 4.7); an agent's
    key names its agent (ID-10), and a key bound to none is still named by its own id."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if who.agent_id is not None:
            return Actor(kind=ActorType.AGENT, id=who.agent_id, label=who.agent_label)
        return Actor(kind=ActorType.AGENT, id=who.subject_id, label=f"api key {who.subject_id}")
    user = user if user is not None else caller_user(request)
    return Actor(kind=ActorType.USER, id=user.id, label=user.name)


def proposer_for(request: HttpRequest) -> Any:
    from apps.proposals.logic import Proposer

    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        return Proposer(actor=actor_for(request), api_key_id=who.subject_id)
    user = caller_user(request)
    return Proposer(actor=actor_for(request, user), user=user)


def if_match(request: HttpRequest) -> int | None:
    """`If-Match` carries the version the caller last read (playbook 4.3). Absent means the
    caller did not ask for a check; present and not a version is a 422."""
    raw = request.headers.get("If-Match")
    if raw is None or raw == "":
        return None
    try:
        return int(raw.strip().strip('"').removeprefix("W/").strip('"'))
    except ValueError:
        raise ProblemError(status=422, code="validation_error", detail="If-Match must be the version you last read.") from None


def idempotency_key(request: HttpRequest) -> str | None:
    value = request.headers.get("Idempotency-Key", "").strip()
    return value or None


# ---------------------------------------------------------------------------------------
# Logic gates (UNGATED_BY_DESIGN reason `logic-gate`)
# ---------------------------------------------------------------------------------------
def deny(permission: str) -> ProblemError:
    return ProblemError(
        status=403, code="permission_denied", detail="You do not have access to this.", required_permission=permission
    )


def require_any(request: HttpRequest, *permissions: str) -> Principal:
    """A person holding any one of `permissions`. The 403 names the first, which is the one a
    tenant member would ask their admin for."""
    who = principal(request)
    if not any(who.has_permission(permission) for permission in permissions):
        raise deny(permissions[0])
    return who


def require_library_reader(request: HttpRequest) -> Principal:
    """Library vocabularies are read by any person's session and by an agent's key with
    `library:read` (AGT-02: agents read vocabularies at run start and submit keys only)."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT and not who.has_scope(perms.SCOPE_LIBRARY_READ):
        raise deny(perms.SCOPE_LIBRARY_READ)
    return who


def require_library_read(request: HttpRequest) -> Principal:
    """Library records (instruments, provisions, obligations) are read by a person holding
    `library.read` in their tenant, or by an agent's key with `library:read` (INV-03,
    AGT-02). Stricter than `require_library_reader`: a record read is filtered by a
    tenant's footprint, so the caller is always in a tenant."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if not who.has_scope(perms.SCOPE_LIBRARY_READ):
            raise deny(perms.SCOPE_LIBRARY_READ)
        return who
    return require_any(request, perms.LIBRARY_READ)


def require_proposer(request: HttpRequest) -> Principal:
    """Who may put a proposal in the queue: a tenant member with `proposals.create`, a
    platform editor with `library_vocab.manage`, or an agent's key with `proposals:write`."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if not who.has_scope(perms.SCOPE_PROPOSALS_WRITE):
            raise deny(perms.SCOPE_PROPOSALS_WRITE)
        return who
    return require_any(request, perms.PROPOSALS_CREATE, perms.LIBRARY_VOCAB_MANAGE)


def uuid_or_404(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ProblemError(status=404, code="not_found", detail="Not found.") from None
