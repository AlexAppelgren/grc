"""The security log (ID-11): one `login_event` row per sign-in, failure, enrolment,
recovery and key use. Append-only in Python (AppendOnlyModel) and by trigger.

`log_event()` is to this ledger what `record()` is to the audit log: the one door. It writes
the row in the zone its `tenant_id` names, because the mixed policy's WITH CHECK accepts
only the session's own zone (H15); a platform row goes in with the tenant cleared."""

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
    client-supplied, so it is read only when TRUSTED_PROXY_HOPS says how many of our proxies
    appended to it, and then from the right, never the leftmost value. With no trusted proxy
    the socket address is the answer (F1)."""
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
    # Zone outside, atomic inside, as record() nests them: a failed insert rolls back to its
    # savepoint first, so the caller sees the insert's own error.
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
