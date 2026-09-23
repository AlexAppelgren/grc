"""Scoped API keys for agents and integrations (ID-10, AC-PRO1): shown once, stored as a
prefix plus the secret's hash, revocable, with a throttled last-used stamp. Scopes are
the constants in apps/shared/permissions.py and none reaches a library edit.

Two kinds of key. A bank's own key carries its tenant and may hold only
`TENANT_KEY_SCOPES`: reads, and filing a proposal. A platform key carries no tenant, is
bound to one agent definition and is minted from the console under
`agent_definitions.manage` (AGT-01, D-61, D-62): it is what bleqq's own agents run on, so
it alone may hold the watch writes and the review scope.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.agents import logic as agents_logic
from apps.identity import tokens
from apps.identity.models import ApiKey, LoginEventKind, LoginMethod, User
from apps.identity.security_log import log_event
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import Tenant


def resolve_api_key(plain: str) -> Principal | None:
    parsed = tokens.parse_api_key(plain)
    if parsed is None:
        return None
    prefix, presented_hash = parsed
    now = timezone.now()
    with tenancy.identity_lookup():
        key = ApiKey.objects.select_related("agent").filter(key_prefix=prefix).first()  # ordering: key_prefix is unique, at most one row
    if key is None or not tokens.constant_equal(presented_hash, key.key_hash):
        return None
    if key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= now):
        return None
    if key.tenant_id is not None:
        tenancy.activate(key.tenant_id)
    else:
        # A platform key's own zone is "no tenant", not "whatever the last request left
        # active": a prior tenant-scoped request in the same connection must never leak its
        # context into this one (H15).
        tenancy.clear_tenant()
    held = frozenset(key.scopes)
    # A bank's key created before the watch writes became platform-only may still list one;
    # it works without it rather than breaking the integration (D-61).
    withheld = held - perms.TENANT_KEY_SCOPES if key.tenant_id is not None else frozenset()
    throttle = timedelta(seconds=settings.API_KEY_LAST_USED_THROTTLE_SECONDS)
    if key.last_used_at is None or now - key.last_used_at > throttle:
        key.last_used_at = now
        key.save(update_fields=["last_used_at"])
        log_event(event=LoginEventKind.KEY_USED, method=LoginMethod.API_KEY, success=True, request=None, tenant_id=key.tenant_id, api_key=key)
        if withheld:
            log_event(
                event=LoginEventKind.KEY_SCOPES_WITHHELD,
                method=LoginMethod.API_KEY,
                success=False,
                request=None,
                tenant_id=key.tenant_id,
                api_key=key,
                failure_reason=", ".join(sorted(withheld)),
            )
    return Principal(
        kind=PrincipalKind.AGENT,
        subject_id=key.id,
        tenant_id=key.tenant_id,
        scopes=held - withheld,
        agent_id=key.agent_id,
        agent_label=key.agent.key if key.agent is not None else "",
    )


def _checked_name(name: str, expires_at: datetime | None) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Give the key a name.", code="name_required")
    if expires_at is not None and expires_at <= timezone.now():
        raise ValidationError("The expiry must be in the future.", code="expiry_in_past")
    return cleaned


def _validate_scopes(values: Iterable[str], allowed: frozenset[str]) -> list[str]:
    wanted = sorted(dict.fromkeys(values))
    if not wanted:
        raise ValidationError("Pick at least one scope.", code="scopes_required")
    refused = [value for value in wanted if value not in allowed]
    if refused:
        raise ValidationError(
            f"This key may not hold {', '.join(refused)}. Valid scopes: {', '.join(sorted(allowed))}.",
            code="unknown_key",
        )
    return wanted


# ---------------------------------------------------------------------------------------
# A bank's own keys
# ---------------------------------------------------------------------------------------
def list_api_keys(tenant_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[ApiKey], int]:
    queryset = ApiKey.objects.filter(tenant_id=tenant_id).order_by("-created_at", "-id")
    return list(queryset[offset : offset + limit]), queryset.count()


def create_api_key(
    *,
    tenant: Tenant,
    actor: Actor,
    created_by: User,
    name: str,
    scopes: Iterable[str],
    expires_at: datetime | None,
    step_up_assertion_id: uuid.UUID | None,
) -> tuple[ApiKey, str]:
    cleaned_name = _checked_name(name, expires_at)
    granted = _validate_scopes(scopes, perms.TENANT_KEY_SCOPES)
    plain, prefix, key_hash = tokens.new_api_key()
    key = ApiKey.objects.create(
        tenant=tenant, name=cleaned_name, key_prefix=prefix, key_hash=key_hash, scopes=granted, created_by=created_by, expires_at=expires_at
    )
    record(
        action="api_key.created",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"API key {key.key_prefix} created with scopes {', '.join(granted)}.",
        tenant_id=tenant.id,
        after={"keyPrefix": key.key_prefix, "scopes": granted, "expiresAt": expires_at.isoformat() if expires_at else None},
        step_up_assertion_id=step_up_assertion_id,
    )
    return key, plain


def revoke_api_key(*, tenant: Tenant, actor: Actor, key_id: uuid.UUID) -> ApiKey:
    key = ApiKey.objects.filter(pk=key_id, tenant=tenant).first()  # ordering: pk lookup, at most one row
    if key is None:
        raise ValidationError("Not found.", code="not_found")
    if key.revoked_at is None:
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        log_event(event=LoginEventKind.KEY_REVOKED, method=LoginMethod.API_KEY, success=True, request=None, tenant_id=tenant.id, api_key=key)
    record(
        action="api_key.revoked",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"API key {key.key_prefix} revoked.",
        tenant_id=tenant.id,
    )
    return key


# ---------------------------------------------------------------------------------------
# Platform agent keys (ID-10, AGT-01). Reached only through `agent_definitions.manage`,
# which no bank session can hold (session_logic.build_principal), so every caller is a
# platform session. The two writes still assert the platform zone rather than inherit one:
# the row belongs to no tenant, and the mixed table accepts it only from that zone (H15,
# D-78). A key may hold any scope, `proposals:review` included (D-62); none reaches a
# library row (AC-PRO1, ID-S21).
# ---------------------------------------------------------------------------------------
def list_agent_keys(*, limit: int, offset: int) -> tuple[list[ApiKey], int]:
    """Every platform key, newest first, bound or not: an unbound one is listed so that it
    can be seen and revoked, never hidden."""
    queryset = ApiKey.objects.select_related("agent").filter(tenant__isnull=True).order_by("-created_at", "-id")
    return list(queryset[offset : offset + limit]), queryset.count()


def create_agent_key(
    *,
    actor: Actor,
    created_by: User,
    agent_id: uuid.UUID,
    name: str,
    scopes: Iterable[str],
    expires_at: datetime | None,
    step_up_assertion_id: uuid.UUID | None,
) -> tuple[ApiKey, str]:
    tenancy.clear_tenant()
    cleaned_name = _checked_name(name, expires_at)
    granted = _validate_scopes(scopes, perms.ALL_SCOPES)
    # Read through the agents app: this module writes keys, and the library fence refuses a
    # module that names a library model beside a write (apps/shared/tests_library_fence.py).
    agent = agents_logic.definition(agent_id)
    if agent is None:
        raise ValidationError("No agent definition has that id.", code="unknown_key")
    plain, prefix, key_hash = tokens.new_api_key()
    key = ApiKey.objects.create(
        tenant=None, agent=agent, name=cleaned_name, key_prefix=prefix, key_hash=key_hash, scopes=granted, created_by=created_by, expires_at=expires_at
    )
    log_event(event=LoginEventKind.KEY_CREATED, method=LoginMethod.API_KEY, success=True, request=None, user=created_by, api_key=key)
    record(
        action="agent_key.created",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"Agent key {key.key_prefix} for {agent.key} created with scopes {', '.join(granted)}.",
        tenant_id=None,
        after={
            "keyPrefix": key.key_prefix,
            "agent": agent.key,
            "scopes": granted,
            "expiresAt": expires_at.isoformat() if expires_at else None,
        },
        step_up_assertion_id=step_up_assertion_id,
    )
    return key, plain


def revoke_agent_key(*, actor: Actor, revoked_by: User, key_id: uuid.UUID) -> ApiKey:
    tenancy.clear_tenant()
    key = ApiKey.objects.select_related("agent").filter(pk=key_id, tenant__isnull=True).first()  # ordering: pk lookup, at most one row
    if key is None:
        raise ValidationError("Not found.", code="not_found")
    if key.revoked_at is None:
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        log_event(event=LoginEventKind.KEY_REVOKED, method=LoginMethod.API_KEY, success=True, request=None, user=revoked_by, api_key=key)
    record(
        action="agent_key.revoked",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"Agent key {key.key_prefix} revoked.",
        tenant_id=None,
        after={"revokedAt": key.revoked_at.isoformat() if key.revoked_at else None},
    )
    return key
