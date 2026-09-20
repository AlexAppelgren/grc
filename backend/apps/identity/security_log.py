"""The security log (ID-11): one `login_event` row per sign-in, failure, enrolment,
recovery and key use. Append-only in Python (AppendOnlyModel) and by trigger.

`log_event()` is to this ledger what `record()` is to the audit log: the one door, and it
writes the row in the zone its `tenant_id` names. A row with a tenant needs that tenant
activated and a row without one needs no tenant activated, because since H15 the mixed
policy's WITH CHECK accepts only the session's own zone. A platform row therefore goes in
with the tenant cleared, which is what a sign-in that failed before any tenant was known
records, whatever the caller had activated."""

from __future__ import annotations

import uuid
from contextlib import nullcontext

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest

from apps.identity.models import ApiKey, LoginEvent, LoginEventKind, LoginMethod, User
from apps.shared import tenancy

USER_AGENT_MAX_LENGTH = 500


def client_ip(request: HttpRequest | None) -> str | None:
    """The address the rate limits and the security log key on. `X-Forwarded-For` is
    client-supplied text: a caller can put anything in it, so it is read only when
    TRUSTED_PROXY_HOPS says how many proxies of ours appended to it, and then from the
    right (the hop our edge appended), never the leftmost value. With no trusted proxy
    the socket address is the answer (security review 2026-09-19, finding F1)."""
    if request is None:
        return None
    hops = settings.TRUSTED_PROXY_HOPS
    if hops > 0:
        forwarded = [item.strip() for item in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if item.strip()]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.META.get("REMOTE_ADDR") or None


def user_agent(request: HttpRequest | None) -> str:
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_MAX_LENGTH]


def log_event(
    *,
    event: LoginEventKind,
    method: LoginMethod,
    success: bool,
    request: HttpRequest | None,
    user: User | None = None,
    tenant_id: uuid.UUID | None = None,
    api_key: ApiKey | None = None,
    email: str = "",
    failure_reason: str = "",
) -> LoginEvent:
    crosses_zones = tenant_id is None and tenancy.database_tenant_id() is not None
    # The zone block outside and an atomic block inside, exactly as record() nests them: a
    # failed insert rolls back to its own savepoint before the tenant goes back on, so the
    # caller is handed the error the insert raised and not the one that putting the tenant
    # back on an aborted transaction would raise over the top of it.
    with tenancy.platform_zone() if crosses_zones else nullcontext(), transaction.atomic():
        return LoginEvent.objects.create(
            tenant_id=tenant_id,
            user=user,
            api_key=api_key,
            email=email or (user.email if user else ""),
            method=method.value,
            event=event.value,
            success=success,
            failure_reason=failure_reason,
            ip=client_ip(request),
            user_agent=user_agent(request),
        )


def list_events(tenant_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[LoginEvent], int]:
    queryset = LoginEvent.objects.filter(tenant_id=tenant_id).order_by("-occurred_at", "-id")
    total = queryset.count()
    return list(queryset[offset : offset + limit]), total
