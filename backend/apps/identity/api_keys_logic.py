"""Scoped API keys for agents and integrations (ID-10, AC-PRO1): shown once, stored as a
prefix plus the secret's hash, revocable, with a throttled last-used stamp. Scopes are
the constants in apps/shared/permissions.py and none reaches a library edit.

Two kinds of key. A bank's own key carries its tenant and may hold only
`TENANT_KEY_SCOPES`: reads, and filing a proposal. A platform key carries no tenant, is
bound to one agent definition and is minted from the console under
`agent_definitions.manage` (AGT-01, D-61, D-62): it is what bleqq's own agents run on, so
it alone may hold the watch writes and the review scope.

Two credential kinds share the table (ACC-03, ADR 0056). A service key bound to an agent
access entry reads as that entry and stops the moment the entry is revoked. A personal
access token acts as the member who minted it: it stops the moment the person, their
membership or a permission one of its scopes stands on is gone (`SCOPE_BACKING`), checked
on every request rather than by a sweep. `tenant:read` reaches a bank's register only
through an entry, so a bank's credential bound to none is resolved without it.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.agents import logic as agents_logic
from apps.agents.models import AgentKind
from apps.agents.seeds.definition import DEFINITIONS, read_definition
from apps.identity import tokens
from apps.identity.models import ApiKey, CredentialKind, LoginEventKind, LoginMethod, Membership, User, UserStatus
from apps.identity.security_log import log_event
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import Tenant

# What an agent's kind may hold beyond the reads and `agent-runs:write` every agent needs
# (H43, D-62). A review agent decides what another definition filed, so it holds
# `proposals:review` and none of the filing scopes; every other kind files and never
# decides, so no key of one can approve its own definition's work.
FILING_SCOPES: frozenset[str] = frozenset({perms.SCOPE_SOURCES_WRITE, perms.SCOPE_CHANGES_WRITE, perms.SCOPE_PROPOSALS_WRITE})


def _refused_for_kind(kind: str, scopes: Iterable[str]) -> list[str]:
    barred = FILING_SCOPES if kind == AgentKind.REVIEW.value else frozenset({perms.SCOPE_PROPOSALS_REVIEW})
    return sorted(set(scopes) & barred)


@functools.cache
def _declared_status(key: str, version: int) -> str:
    """The `status` the definition file of this version declares (`draft`, `active` or
    `retired`), or "" when the build ships no such file. The files are part of the image,
    so one read per process is the truth for its life."""
    path = DEFINITIONS / key / f"v{version}" / "definition.yaml"
    return read_definition(path).status if path.is_file() else ""


def _carries_keys(*, active: bool, key: str, version: int) -> bool:
    """Whether a key bound to the definition `key` may be minted and may work (H43, D-93):
    an active definition, or one whose file still declares it a draft, so its runner can be
    evaluated and the journeys run before release. A retired definition, and one switched
    off, carry none. Primitives rather than the row, because this module writes keys and the
    library fence refuses a module naming a library model beside a write."""
    return active or _declared_status(key, version) == "draft"


# The permission a person must hold for their token to hold each scope (ACC-03): a token
# never reads more than its person could read in their own session.
SCOPE_BACKING: dict[str, str] = {
    perms.SCOPE_LIBRARY_READ: perms.LIBRARY_READ,
    perms.SCOPE_SEARCH_READ: perms.SEARCH_USE,
    perms.SCOPE_UPCOMING_READ: perms.ROADMAP_READ,
    perms.SCOPE_TENANT_READ: perms.REGISTER_READ,
}


def _person_permissions(tenant_id: uuid.UUID, user_id: uuid.UUID) -> frozenset[str] | None:
    """What the person holds in their bank now, or None when they are deactivated or no
    longer an active member of it. Read with the bank activated."""
    if not User.objects.filter(pk=user_id, deactivated_at__isnull=True).exclude(status=UserStatus.DEACTIVATED.value).exists():
        return None
    rows = list(
        Membership.objects.filter(tenant_id=tenant_id, user_id=user_id, deactivated_at__isnull=True).values_list(
            "roles__permissions", flat=True
        )
    )
    if not rows:
        return None
    return frozenset(permission for granted in rows for permission in granted or []) & perms.TENANT_PERMISSIONS


def _backed(key: ApiKey) -> bool:
    """A token lives while its person is an active member holding the permission behind
    every scope it carries (ACC-03). Always true for a service key."""
    if key.kind != CredentialKind.PERSONAL.value:
        return True
    if key.tenant_id is None or key.acts_as_user_id is None:  # a CHECK demands both on a token
        return False
    held = _person_permissions(key.tenant_id, key.acts_as_user_id)
    return held is not None and all(SCOPE_BACKING.get(scope) in held for scope in key.scopes)


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
    if key.agent is not None and not _carries_keys(active=key.agent.active, key=key.agent.key, version=key.agent.current_version):
        return None
    if key.tenant_id is not None:
        tenancy.activate(key.tenant_id)
    else:
        # A platform key's own zone is "no tenant", not "whatever the last request left
        # active": a prior tenant-scoped request in the same connection must never leak its
        # context into this one (H15).
        tenancy.clear_tenant()
    # The entry and the person are the bank's rows, read in its zone (forced RLS).
    entry = key.agent_access
    if entry is not None and not entry.active:
        return None
    if not _backed(key):
        return None
    held = frozenset(key.scopes)
    # A bank's key created before the watch writes became platform-only may still list one;
    # it works without it rather than breaking the integration (D-61). `tenant:read` reads a
    # bank's register only as an entry whose reach it carries, so a bank's credential bound
    # to no entry is resolved without it (ACC-04, D-72).
    withheld = held - perms.TENANT_KEY_SCOPES if key.tenant_id is not None else frozenset()
    if key.tenant_id is not None and entry is None:
        withheld |= held & {perms.SCOPE_TENANT_READ}
    personal = key.kind == CredentialKind.PERSONAL.value
    method = LoginMethod.PERSONAL_TOKEN if personal else LoginMethod.API_KEY
    throttle = timedelta(seconds=settings.API_KEY_LAST_USED_THROTTLE_SECONDS)
    if key.last_used_at is None or now - key.last_used_at > throttle:
        key.last_used_at = now
        key.save(update_fields=["last_used_at"])
        log_event(
            event=LoginEventKind.TOKEN_USED if personal else LoginEventKind.KEY_USED,
            method=method,
            success=True,
            request=None,
            tenant_id=key.tenant_id,
            api_key=key,
            user=key.acts_as_user,
        )
        if withheld:
            log_event(
                event=LoginEventKind.KEY_SCOPES_WITHHELD,
                method=method,
                success=False,
                request=None,
                tenant_id=key.tenant_id,
                api_key=key,
                user=key.acts_as_user,
                failure_reason=", ".join(sorted(withheld)),
            )
    return Principal(
        kind=PrincipalKind.AGENT,
        subject_id=key.id,
        tenant_id=key.tenant_id,
        scopes=held - withheld,
        agent_id=key.agent_id,
        agent_label=key.agent.key if key.agent is not None else "",
        agent_access_id=entry.id if entry is not None else None,
        agent_access_label=entry.name if entry is not None else "",
        acting_user_id=key.acts_as_user_id,
        acting_user_label=key.acts_as_user.name if key.acts_as_user is not None else "",
    )


def log_rate_limited(principal: Principal) -> None:
    """The first refusal of a credential's rate window, in the security log (ACC-09). The
    bank is already activated by the credential's own resolution."""
    key = ApiKey.objects.select_related("acts_as_user").filter(pk=principal.subject_id).first()  # ordering: pk lookup, at most one row
    if key is None:  # pragma: no cover - the key resolved on this same request
        return
    log_event(
        event=LoginEventKind.CREDENTIAL_RATE_LIMITED,
        method=LoginMethod.PERSONAL_TOKEN if key.kind == CredentialKind.PERSONAL.value else LoginMethod.API_KEY,
        success=False,
        request=None,
        tenant_id=key.tenant_id,
        api_key=key,
        user=key.acts_as_user,
        failure_reason=f"over {settings.AGENT_ACCESS_RATE_PER_MINUTE} a minute",
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
# The service keys of an agent access entry (ACC-01, ACC-03, acc-entries-and-log). Minted
# under `agent_access.manage` with a step-up by the agents app, which has checked the entry
# is live and the bank's; hold only `AGENT_ACCESS_SCOPES`, expire no later than
# `AGENT_ACCESS_KEY_MAX_DAYS` from now (that far by default), and are shown once. Revoking
# the entry revokes every credential bound to it, its keys and the tokens that name it.
# ---------------------------------------------------------------------------------------
def create_entry_key(
    *,
    tenant: Tenant,
    entry_id: uuid.UUID,
    actor: Actor,
    created_by: User,
    name: str,
    scopes: Iterable[str],
    expires_at: datetime | None,
    step_up_assertion_id: uuid.UUID | None,
) -> tuple[ApiKey, str]:
    latest = timezone.now() + timedelta(days=settings.AGENT_ACCESS_KEY_MAX_DAYS)
    expiry = expires_at if expires_at is not None else latest
    cleaned_name = _checked_name(name, expiry)
    if expiry > latest:
        raise ValidationError(
            f"A key of an agent access entry lives at most {settings.AGENT_ACCESS_KEY_MAX_DAYS} days.", code="expiry_too_late"
        )
    granted = _validate_scopes(scopes, perms.AGENT_ACCESS_SCOPES)
    plain, prefix, key_hash = tokens.new_api_key()
    key = ApiKey.objects.create(
        tenant=tenant,
        agent_access_id=entry_id,
        name=cleaned_name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=granted,
        created_by=created_by,
        expires_at=expiry,
    )
    log_event(event=LoginEventKind.KEY_CREATED, method=LoginMethod.API_KEY, success=True, request=None, tenant_id=tenant.id, user=created_by, api_key=key)
    record(
        action="api_key.created",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"Agent access key {key.key_prefix} created with scopes {', '.join(granted)}.",
        tenant_id=tenant.id,
        after={"keyPrefix": key.key_prefix, "agentAccessId": str(entry_id), "scopes": granted, "expiresAt": expiry.isoformat()},
        step_up_assertion_id=step_up_assertion_id,
    )
    return key, plain


def _revoke(key: ApiKey, *, user: User, now: datetime) -> None:
    key.revoked_at = now
    key.save(update_fields=["revoked_at"])
    personal = key.kind == CredentialKind.PERSONAL.value
    log_event(
        event=LoginEventKind.TOKEN_REVOKED if personal else LoginEventKind.KEY_REVOKED,
        method=LoginMethod.PERSONAL_TOKEN if personal else LoginMethod.API_KEY,
        success=True,
        request=None,
        tenant_id=key.tenant_id,
        user=user,
        api_key=key,
    )


def revoke_entry_key(
    *, tenant: Tenant, entry_id: uuid.UUID, key_id: uuid.UUID, actor: Actor, revoked_by: User, step_up_assertion_id: uuid.UUID | None
) -> ApiKey:
    """One credential bound to the entry, a key or a token naming it. Revoking twice is a
    safe retry: nothing changes, and it is still audited with `before` equal to `after`."""
    key = ApiKey.objects.select_related("acts_as_user").filter(pk=key_id, tenant=tenant, agent_access_id=entry_id).first()  # ordering: pk lookup, at most one row
    if key is None:
        raise ValidationError("That key is not one of this entry's.", code="not_found")
    before = key.revoked_at
    if before is None:
        _revoke(key, user=revoked_by, now=timezone.now())
    record(
        action="api_key.revoked",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"Agent access key {key.key_prefix} revoked." if before is None else f"Agent access key {key.key_prefix} was already revoked; nothing changed.",
        tenant_id=tenant.id,
        before={"revokedAt": before.isoformat() if before else None},
        after={"revokedAt": key.revoked_at.isoformat() if key.revoked_at else None},
        step_up_assertion_id=step_up_assertion_id,
    )
    return key


def revoke_entry_credentials(*, tenant: Tenant, entry_id: uuid.UUID, revoked_by: User) -> list[str]:
    """Every live credential bound to the entry, revoked at once, each with its security log
    row; answers their prefixes for the entry's own audit row."""
    now = timezone.now()
    live = list(ApiKey.objects.filter(tenant=tenant, agent_access_id=entry_id, revoked_at__isnull=True).order_by("created_at", "id"))
    for key in live:
        _revoke(key, user=revoked_by, now=now)
    return [key.key_prefix for key in live]


# ---------------------------------------------------------------------------------------
# Platform agent keys (ID-10, AGT-01). Reached only through `agent_definitions.manage`,
# which no bank session can hold (session_logic.build_principal), so every caller is a
# platform session. The two writes still assert the platform zone rather than inherit one:
# the row belongs to no tenant, and the mixed table accepts it only from that zone (H15,
# D-78). A key holds the scopes its agent's kind takes, `proposals:review` for a review
# agent (D-62, H43); none reaches a library row (AC-PRO1, ID-S21).
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
    if not _carries_keys(active=agent.active, key=agent.key, version=agent.current_version):
        raise ValidationError(
            f"{agent.key} is retired or switched off, so no key can be bound to it.",
            code="agent_inactive",
        )
    barred = _refused_for_kind(agent.kind, granted)
    if barred:
        raise ValidationError(
            f"A {agent.kind} agent may not hold {', '.join(barred)}. A review agent decides and never files; "
            "every other agent files and never decides.",
            code="scope_not_for_kind",
        )
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
    """Revoking twice is a safe retry: the second call changes nothing and, like every 2xx,
    is still audited (AC-AUD1), with a summary that says so and `before` equal to `after`."""
    tenancy.clear_tenant()
    key = ApiKey.objects.select_related("agent").filter(pk=key_id, tenant__isnull=True).first()  # ordering: pk lookup, at most one row
    if key is None:
        raise ValidationError("Not found.", code="not_found")
    before = key.revoked_at
    if before is None:
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        log_event(event=LoginEventKind.KEY_REVOKED, method=LoginMethod.API_KEY, success=True, request=None, user=revoked_by, api_key=key)
    record(
        action="agent_key.revoked",
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"Agent key {key.key_prefix} revoked." if before is None else f"Agent key {key.key_prefix} was already revoked; nothing changed.",
        tenant_id=None,
        before={"revokedAt": before.isoformat() if before else None},
        after={"revokedAt": key.revoked_at.isoformat() if key.revoked_at else None},
    )
    return key
