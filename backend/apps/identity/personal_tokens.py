"""Personal access tokens (ACC-03, ADR 0056, AGENT_ACCESS.md section 8).

A member holding `tokens.create` mints a token for themselves from a session with a fresh
passkey assertion. The token acts as that member: it reads with the scopes it was given,
each one a read the member's own permissions back (`api_keys_logic.SCOPE_BACKING`), and it
may name one live agent access entry of the bank, whose scope then narrows it and whose
reach it then carries. It always expires, no later than `PERSONAL_TOKEN_MAX_DAYS` from now,
and is shown once and stored as a hash. It can never open a session or step up: the agent
access guard refuses it on every step-up route, this one included, so a token cannot mint a
token.

A member lists and revokes their own tokens without `tokens.create`, so a person who lost
the permission can still stop what they minted. An administrator sees and revokes every
credential of the bank through `/tenant/api-keys` (`api_keys_logic`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.utils import timezone

from apps.agents.models import AgentAccess
from apps.identity import api_keys_logic, tokens
from apps.identity.models import ApiKey, CredentialKind, LoginEventKind, LoginMethod, User
from apps.identity.security_log import log_event
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant


def _own(tenant_id: uuid.UUID, user_id: uuid.UUID) -> QuerySet[ApiKey]:
    return (
        ApiKey.objects.select_related("agent_access")
        .filter(tenant_id=tenant_id, kind=CredentialKind.PERSONAL.value, acts_as_user_id=user_id)
        .order_by("-created_at", "-id")
    )


def list_own(tenant_id: uuid.UUID, user_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[ApiKey], int]:
    queryset = _own(tenant_id, user_id)
    return list(queryset[offset : offset + limit]), queryset.count()


def _expiry(expires_at: datetime) -> datetime:
    if expires_at <= timezone.now():
        raise ValidationError("The expiry must be in the future.", code="expiry_in_past")
    if expires_at > timezone.now() + timedelta(days=settings.PERSONAL_TOKEN_MAX_DAYS):
        raise ValidationError(f"A personal access token lives at most {settings.PERSONAL_TOKEN_MAX_DAYS} days.", code="expiry_too_late")
    return expires_at


def _scopes(values: Iterable[str], held: frozenset[str], *, entry_id: uuid.UUID | None) -> list[str]:
    wanted = api_keys_logic.validate_scopes(values, perms.AGENT_ACCESS_SCOPES)
    unbacked = [scope for scope in wanted if api_keys_logic.SCOPE_BACKING[scope] not in held]
    if unbacked:
        raise ValidationError(
            f"You cannot read what {', '.join(unbacked)} reaches yourself, so a token of yours cannot hold it.",
            code="scope_not_held",
        )
    if perms.SCOPE_TENANT_READ in wanted and entry_id is None:
        raise ValidationError(
            f"{perms.SCOPE_TENANT_READ} reads the bank's register only through an agent access entry; name one.",
            code="entry_required",
        )
    return wanted


def mint(
    *,
    tenant: Tenant,
    user: User,
    actor: Actor,
    name: str,
    scopes: Iterable[str],
    expires_at: datetime,
    agent_access_id: uuid.UUID | None,
    step_up_assertion_id: uuid.UUID | None,
) -> tuple[ApiKey, str]:
    """A token acting as `user`, a member of `tenant`, shown once."""
    expiry = _expiry(expires_at)
    cleaned_name = api_keys_logic.checked_name(name, expiry)
    held = api_keys_logic.person_permissions(tenant.id, user.id) or frozenset()
    granted = _scopes(scopes, held, entry_id=agent_access_id)
    entry = None
    if agent_access_id is not None:
        entry = AgentAccess.objects.filter(pk=agent_access_id, tenant=tenant, active=True).first()  # ordering: pk lookup, at most one row
        if entry is None:
            raise ValidationError("Your bank has no live agent access entry with that id.", code="unknown_key")
    plain, prefix, key_hash = tokens.new_api_key()
    key = ApiKey.objects.create(
        tenant=tenant,
        kind=CredentialKind.PERSONAL.value,
        acts_as_user=user,
        agent_access=entry,
        name=cleaned_name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=granted,
        created_by=user,
        expires_at=expiry,
    )
    log_event(
        event=LoginEventKind.TOKEN_CREATED, method=LoginMethod.PERSONAL_TOKEN, success=True, request=None, tenant_id=tenant.id, user=user, api_key=key
    )
    record(
        action="personal_token.created",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"Personal access token {key.key_prefix} created with scopes {', '.join(granted)}.",
        tenant_id=tenant.id,
        after={
            "keyPrefix": key.key_prefix,
            "scopes": granted,
            "agentAccessId": str(entry.id) if entry is not None else None,
            "expiresAt": expiry.isoformat(),
        },
        step_up_assertion_id=step_up_assertion_id,
    )
    return key, plain


def revoke_own(*, tenant: Tenant, user: User, actor: Actor, token_id: uuid.UUID) -> ApiKey:
    """One of the member's own tokens. Revoking twice is a safe retry: nothing changes, and
    it is still audited with `before` equal to `after`."""
    key = _own(tenant.id, user.id).filter(pk=token_id).first()  # ordering: pk lookup, at most one row
    if key is None:
        raise ValidationError("You have no personal access token with that id.", code="not_found")
    before = key.revoked_at
    if before is None:
        api_keys_logic.revoke_credential(key, user=user, now=timezone.now())
    record(
        action="personal_token.revoked",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"Personal access token {key.key_prefix} revoked."
        if before is None
        else f"Personal access token {key.key_prefix} was already revoked; nothing changed.",
        tenant_id=tenant.id,
        before={"revokedAt": before.isoformat() if before else None},
        after={"revokedAt": key.revoked_at.isoformat() if key.revoked_at else None},
    )
    return key
