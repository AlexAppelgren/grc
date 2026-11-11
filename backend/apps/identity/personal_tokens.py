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
from apps.identity import api_keys_logic
from apps.identity.models import ApiKey, CredentialKind, User
from apps.shared import permissions as perms
from apps.shared.audit import Actor
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
    return api_keys_logic.mint_key(
        tenant=tenant,
        actor=actor,
        created_by=user,
        name=cleaned_name,
        scopes=granted,
        expires_at=expiry,
        step_up_assertion_id=step_up_assertion_id,
        action="personal_token.created",
        kind=CredentialKind.PERSONAL,
        agent_access_id=entry.id if entry is not None else None,
        acts_as_user=user,
        after={"agentAccessId": str(entry.id) if entry is not None else None},
    )


def revoke_own(*, tenant: Tenant, user: User, actor: Actor, token_id: uuid.UUID) -> ApiKey:
    """One of the member's own tokens."""
    key = _own(tenant.id, user.id).filter(pk=token_id).first()  # ordering: pk lookup, at most one row
    return api_keys_logic.revoke_key(
        key, actor=actor, revoked_by=user, action="personal_token.revoked", missing="You have no personal access token with that id."
    )
