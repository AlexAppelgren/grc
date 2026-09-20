"""Scoped API keys for agents and integrations (ID-10, AC-PRO1): shown once, stored as a
prefix plus the secret's hash, revocable, with a throttled last-used stamp. Scopes are
the constants in apps/shared/permissions.py and none reaches a library edit."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import NoReturn

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.identity import tokens
from apps.identity.models import ApiKey, LoginEventKind, LoginMethod, User
from apps.identity.security_log import log_event
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError
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
    throttle = timedelta(seconds=settings.API_KEY_LAST_USED_THROTTLE_SECONDS)
    if key.last_used_at is None or now - key.last_used_at > throttle:
        key.last_used_at = now
        key.save(update_fields=["last_used_at"])
        log_event(event=LoginEventKind.KEY_USED, method=LoginMethod.API_KEY, success=True, request=None, tenant_id=key.tenant_id, api_key=key)
    return Principal(
        kind=PrincipalKind.AGENT,
        subject_id=key.id,
        tenant_id=key.tenant_id,
        scopes=frozenset(key.scopes),
        agent_id=key.agent_id,
        agent_label=key.agent.key if key.agent is not None else "",
    )


def _validate_scopes(values: Iterable[str]) -> list[str]:
    wanted = sorted(dict.fromkeys(values))
    if not wanted:
        raise ValidationError("Pick at least one scope.", code="scopes_required")
    unknown = [value for value in wanted if value not in perms.ALL_SCOPES]
    if unknown:
        raise ValidationError(f"Unknown scope: {', '.join(unknown)}.", code="unknown_key")
    return wanted


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
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValidationError("Give the key a name.", code="name_required")
    if expires_at is not None and expires_at <= timezone.now():
        raise ValidationError("The expiry must be in the future.", code="expiry_in_past")
    granted = _validate_scopes(scopes)
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
# Platform agent keys (ID-10, AGT-01, chunk 5). Declared ahead of the logic (chunk 5 plan
# rule 1): each answers 501 `not_built` behind its real gate until `c5-platform-agent-keys`
# builds them. A key bound to an agent is the platform's alone (rule 13), so these three
# sit under `agent_definitions.manage` and no tenant route reaches them.
# ---------------------------------------------------------------------------------------
def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def list_agent_keys() -> NoReturn:
    """`GET /agent-keys`. Built by `c5-platform-agent-keys`."""
    _not_built("The agent key list is not built yet.")


def create_agent_key() -> NoReturn:
    """`POST /agent-keys`. Built by `c5-platform-agent-keys`."""
    _not_built("Creating an agent key is not built yet.")


def revoke_agent_key() -> NoReturn:
    """`POST /agent-keys/{keyId}/revoke`. Built by `c5-platform-agent-keys`."""
    _not_built("Revoking an agent key is not built yet.")
