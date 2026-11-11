"""Scoped API keys for agents and integrations (ID-10, AC-PRO1): shown once, stored as a
prefix plus the secret's hash, revocable, with a throttled last-used stamp. Scopes are
the constants in apps/shared/permissions.py and none reaches a library edit.

A bank's own key carries its tenant and holds only `TENANT_KEY_SCOPES`. A platform key
carries no tenant, is bound to one agent definition and is minted under
`agent_definitions.manage` (AGT-01, D-61, D-62); it alone may hold the watch writes and the
review scope. A service key bound to an agent access entry reads as that entry (ACC-03, ADR
0056). A personal access token acts as the member who minted it and stops the moment a
permission one of its scopes stands on is gone (`SCOPE_BACKING`), checked on every request.
`tenant:read` reaches a bank's register only through an entry.
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

# What an agent's kind may hold beyond the reads and `agent-runs:write` (H43, D-62): a review
# agent holds `proposals:review` and no filing scope, every other kind files and never
# decides, so no key can approve its own definition's work.
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


def person_permissions(tenant_id: uuid.UUID, user_id: uuid.UUID) -> frozenset[str] | None:
    """What the person holds in their bank now, or None when they are not active (deactivated,
    or awaiting enrolment again after ID-05's re-enrolment) or no longer an active member of
    it. Read with the bank activated."""
    if not User.objects.filter(pk=user_id, deactivated_at__isnull=True, status=UserStatus.ACTIVE.value).exists():
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
    held = person_permissions(key.tenant_id, key.acts_as_user_id)
    return held is not None and all(SCOPE_BACKING.get(scope) in held for scope in key.scopes)


def resolve_api_key(plain: str) -> Principal | None:
    parsed = tokens.parse_api_key(plain)
    if parsed is None:
        return None
    prefix, presented_hash = parsed
    now = timezone.now()
    # The key with its agent and its bank in one read. A platform key's zone is "no tenant",
    # never whatever an earlier request on the connection left active (H15).
    with tenancy.identity_lookup() as lookup:
        key = ApiKey.objects.select_related("agent", "tenant__default_language").filter(key_prefix=prefix).first()  # ordering: key_prefix is unique, at most one row
        usable = (
            key is not None
            and tokens.constant_equal(presented_hash, key.key_hash)
            and key.revoked_at is None
            and (key.expires_at is None or key.expires_at > now)
            and (key.agent is None or _carries_keys(active=key.agent.active, key=key.agent.key, version=key.agent.current_version))
        )
        if usable and key is not None:
            lookup.then_activate(key.tenant_id)
    if not usable or key is None:
        return None
    # The entry and the person are the bank's rows, read in its zone (forced RLS).
    entry = key.agent_access
    if entry is not None and not entry.active:
        return None
    if not _backed(key):
        return None
    held = frozenset(key.scopes)
    # An old bank key may still list a watch write; it works without it (D-61). `tenant:read`
    # needs an entry's reach, so a bank credential bound to no entry goes without it (ACC-04,
    # D-72).
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
        tenant=key.tenant,
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


def checked_name(name: str, expires_at: datetime | None) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Give the key a name.", code="name_required")
    if expires_at is not None and expires_at <= timezone.now():
        raise ValidationError("The expiry must be in the future.", code="expiry_in_past")
    return cleaned


def validate_scopes(values: Iterable[str], allowed: frozenset[str]) -> list[str]:
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


# --- One mint and one revoke for every credential (review 2026-11-11 L-17, B-9) ---
# Each kind's own checks stay with its caller; the row, its security log row and its audit
# row are written here, the same way for all four.
def _label(key: ApiKey) -> str:
    if key.kind == CredentialKind.PERSONAL.value:
        return "Personal access token"
    if key.agent_id is not None:
        return "Agent key"
    if key.agent_access_id is not None:
        return "Agent access key"
    return "API key"


def mint_key(
    *,
    tenant: Tenant | None,
    actor: Actor,
    created_by: User,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
    step_up_assertion_id: uuid.UUID | None,
    action: str,
    kind: CredentialKind = CredentialKind.SERVICE,
    agent_id: uuid.UUID | None = None,
    agent_access_id: uuid.UUID | None = None,
    acts_as_user: User | None = None,
    after: dict[str, object] | None = None,
) -> tuple[ApiKey, str]:
    """Store a credential the caller has checked, shown once: the `key_created` (or, for a
    personal token, `token_created`) security log row and the `action` audit row with what
    it holds and the step-up, in the zone of `tenant` (no tenant: a platform key)."""
    plain, prefix, key_hash = tokens.new_api_key()
    key = ApiKey.objects.create(
        tenant=tenant,
        kind=kind.value,
        agent_id=agent_id,
        agent_access_id=agent_access_id,
        acts_as_user=acts_as_user,
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        created_by=created_by,
        expires_at=expires_at,
    )
    personal = kind is CredentialKind.PERSONAL
    log_event(
        event=LoginEventKind.TOKEN_CREATED if personal else LoginEventKind.KEY_CREATED,
        method=LoginMethod.PERSONAL_TOKEN if personal else LoginMethod.API_KEY,
        success=True,
        request=None,
        tenant_id=tenant.id if tenant is not None else None,
        user=created_by,
        api_key=key,
    )
    record(
        action=action,
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"{_label(key)} {prefix} created with scopes {', '.join(scopes)}.",
        tenant_id=tenant.id if tenant is not None else None,
        after={"keyPrefix": prefix, "scopes": scopes, "expiresAt": expires_at.isoformat() if expires_at else None, **(after or {})},
        step_up_assertion_id=step_up_assertion_id,
    )
    return key, plain


def revoke_key(
    key: ApiKey | None,
    *,
    actor: Actor,
    revoked_by: User,
    action: str,
    step_up_assertion_id: uuid.UUID | None = None,
    missing: str = "Not found.",
) -> ApiKey:
    """Revoke a credential the caller found in its own scope (None: `not_found` with
    `missing`). Revoking twice is a safe retry: nothing changes, and like every 2xx it is
    still audited (AC-AUD1), with a summary that says so and `before` equal to `after`."""
    if key is None:
        raise ValidationError(missing, code="not_found")
    before = key.revoked_at
    if before is None:
        revoke_credential(key, user=revoked_by, now=timezone.now())
    label = _label(key)
    record(
        action=action,
        actor=actor,
        subject_type="api_key",
        subject_id=key.id,
        subject_title=key.name,
        summary=f"{label} {key.key_prefix} revoked." if before is None else f"{label} {key.key_prefix} was already revoked; nothing changed.",
        tenant_id=key.tenant_id,
        before={"revokedAt": before.isoformat() if before else None},
        after={"revokedAt": key.revoked_at.isoformat() if key.revoked_at else None},
        step_up_assertion_id=step_up_assertion_id,
    )
    return key


def revoke_credential(key: ApiKey, *, user: User, now: datetime) -> None:
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


# --- A bank's own keys ---
def list_api_keys(tenant_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[ApiKey], int]:
    """Every credential of the bank, newest first (ACC-03): its unbound keys, the service keys
    of its agent access entries and every member's personal token, each with the entry or
    person behind it."""
    queryset = ApiKey.objects.select_related("agent_access", "acts_as_user").filter(tenant_id=tenant_id).order_by("-created_at", "-id")
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
    return mint_key(
        tenant=tenant,
        actor=actor,
        created_by=created_by,
        name=checked_name(name, expires_at),
        scopes=validate_scopes(scopes, perms.TENANT_KEY_SCOPES),
        expires_at=expires_at,
        step_up_assertion_id=step_up_assertion_id,
        action="api_key.created",
    )


def revoke_api_key(*, tenant: Tenant, actor: Actor, revoked_by: User, key_id: uuid.UUID) -> ApiKey:
    """Any credential of the bank, a key or a member's token (ACC-03), with the security log
    row of its own kind the first time."""
    key = ApiKey.objects.filter(pk=key_id, tenant=tenant).first()  # ordering: pk lookup, at most one row
    return revoke_key(key, actor=actor, revoked_by=revoked_by, action="api_key.revoked")


# --- The service keys of an agent access entry (ACC-01, ACC-03) ---
# Minted under `agent_access.manage` with a step-up by the agents app, which has checked the
# entry; hold only `AGENT_ACCESS_SCOPES`, expire within `AGENT_ACCESS_KEY_MAX_DAYS`, shown
# once. Revoking the entry revokes every credential bound to it.
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
    cleaned_name = checked_name(name, expiry)
    if expiry > latest:
        raise ValidationError(
            f"A key of an agent access entry lives at most {settings.AGENT_ACCESS_KEY_MAX_DAYS} days.", code="expiry_too_late"
        )
    return mint_key(
        tenant=tenant,
        actor=actor,
        created_by=created_by,
        name=cleaned_name,
        scopes=validate_scopes(scopes, perms.AGENT_ACCESS_SCOPES),
        expires_at=expiry,
        step_up_assertion_id=step_up_assertion_id,
        action="api_key.created",
        agent_access_id=entry_id,
        after={"agentAccessId": str(entry_id)},
    )


def revoke_person_tokens(*, tenant_id: uuid.UUID, person: User, revoked_by: User, now: datetime) -> int:
    """Revoke every live personal token `person` minted in the bank, each with its security
    log row: a token dies with its person (ACC-03), so removal and re-enrolment end it for
    good rather than refusing it until the person is back. Answers how many."""
    live = ApiKey.objects.filter(
        tenant_id=tenant_id, kind=CredentialKind.PERSONAL.value, acts_as_user=person, revoked_at__isnull=True
    ).order_by("id")
    count = 0
    for key in live:
        revoke_credential(key, user=revoked_by, now=now)
        count += 1
    return count


def revoke_entry_key(
    *, tenant: Tenant, entry_id: uuid.UUID, key_id: uuid.UUID, actor: Actor, revoked_by: User, step_up_assertion_id: uuid.UUID | None
) -> ApiKey:
    """One credential bound to the entry, a key or a token naming it."""
    key = ApiKey.objects.select_related("acts_as_user").filter(pk=key_id, tenant=tenant, agent_access_id=entry_id).first()  # ordering: pk lookup, at most one row
    return revoke_key(
        key,
        actor=actor,
        revoked_by=revoked_by,
        action="api_key.revoked",
        step_up_assertion_id=step_up_assertion_id,
        missing="That key is not one of this entry's.",
    )


def revoke_entry_credentials(*, tenant: Tenant, entry_id: uuid.UUID, revoked_by: User) -> list[str]:
    """Every live credential bound to the entry, revoked at once, each with its security log
    row; answers their prefixes for the entry's own audit row."""
    now = timezone.now()
    live = list(ApiKey.objects.filter(tenant=tenant, agent_access_id=entry_id, revoked_at__isnull=True).order_by("created_at", "id"))
    for key in live:
        revoke_credential(key, user=revoked_by, now=now)
    return [key.key_prefix for key in live]


# --- Platform agent keys (ID-10, AGT-01) ---
# Reached only through `agent_definitions.manage`, which no bank session holds. The writes
# still assert the platform zone: the mixed table accepts the row only from there (H15,
# D-78). A key holds its agent kind's scopes (D-62, H43); none reaches a library row
# (AC-PRO1, ID-S21).
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
    cleaned_name = checked_name(name, expires_at)
    granted = validate_scopes(scopes, perms.ALL_SCOPES)
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
    return mint_key(
        tenant=None,
        actor=actor,
        created_by=created_by,
        name=cleaned_name,
        scopes=granted,
        expires_at=expires_at,
        step_up_assertion_id=step_up_assertion_id,
        action="agent_key.created",
        agent_id=agent.id,
        after={"agent": agent.key},
    )


def revoke_agent_key(*, actor: Actor, revoked_by: User, key_id: uuid.UUID) -> ApiKey:
    tenancy.clear_tenant()
    key = ApiKey.objects.select_related("agent").filter(pk=key_id, tenant__isnull=True).first()  # ordering: pk lookup, at most one row
    return revoke_key(key, actor=actor, revoked_by=revoked_by, action="agent_key.revoked")
