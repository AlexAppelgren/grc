"""Agent access entries (ACC-01, ACC-03, ACC-08; AGENT_ACCESS.md sections 3, 8 and 9).

A bank registers each agent it runs on its own infrastructure as an entry: a name, a
purpose, the team that answers for it, and the departments and products it serves, which
narrow what it reads (ACC-02, `apps/taxonomy/entry_scope.py`). Every write is the admin's,
under `agent_access.manage` with a step-up, and goes through `record()`. An entry is revoked,
never deleted, and revoking it revokes every credential bound to it in the same transaction,
so the next call on any of them answers 401.

The service keys themselves are written by `apps/identity/api_keys_logic.py`, the one module
that mints and revokes keys; this module checks the entry is the bank's and still live
first.

`reach_allowed` is the one question a register read asks for a credential: the bank's own
switch (`apps/governance/reach.py`) and the entry's own toggle, both on.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.utils import timezone

from apps.agents.models import AgentAccess, AgentAccessDepartment, AgentAccessProduct
from apps.agents.schemas import AgentAccessKeyOut, AgentAccessOut, AgentAccessTeamRef, AgentAccessUnitRef
from apps.governance.reach import tenant_reach_on
from apps.identity import api_keys_logic
from apps.identity.models import ApiKey
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal
from apps.shared.models import Tenant
from apps.taxonomy.models import Team, TeamLabel
from apps.taxonomy.reading import Labels, label_of
from apps.taxonomy.schemas import PersonRef
from apps.tenants.models import OrgUnit, TenantProduct

SUBJECT_TYPE = "agent_access"


def reach_allowed(principal: Principal) -> bool:
    """Whether this credential may read the bank's register (ACC-04, ACC-08, D-72): tenant
    reach is on for the bank and on for the live entry the credential is bound to. A
    credential bound to no entry never reaches it. Reads under row-level security, so the
    credential's bank must be activated, as its own resolution does."""
    if principal.agent_access_id is None or principal.tenant_id is None:
        return False
    return (
        tenant_reach_on(principal.tenant_id)
        and AgentAccess.objects.filter(pk=principal.agent_access_id, active=True, tenant_reach=True).exists()
    )


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def _entries(tenant_id: uuid.UUID) -> Any:
    return (
        AgentAccess.objects.filter(tenant_id=tenant_id)
        .select_related("owner_team", "created_by", "revoked_by")
        .prefetch_related(
            Prefetch("departments", queryset=AgentAccessDepartment.objects.select_related("department").order_by("department__name", "department_id")),
            Prefetch("products", queryset=AgentAccessProduct.objects.select_related("product").order_by("product__name", "product_id")),
            Prefetch("api_keys", queryset=ApiKey.objects.select_related("acts_as_user").order_by("-created_at", "-id")),
        )
    )


def entry(tenant_id: uuid.UUID, entry_id: uuid.UUID) -> AgentAccess:
    """The bank's entry, or `not_found`: another bank's entry is not there either."""
    found = _entries(tenant_id).filter(pk=entry_id).first()  # ordering: pk lookup, at most one row
    if found is None:
        raise ValidationError("That agent access entry is not here.", code="not_found")
    return found


def list_entries(tenant_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[AgentAccess], int]:
    queryset = _entries(tenant_id)
    return list(queryset[offset : offset + limit]), queryset.count()


def _person(user: Any) -> PersonRef | None:
    return None if user is None else PersonRef(id=user.id, name=user.name)


def key_out(key: ApiKey) -> AgentAccessKeyOut:
    return AgentAccessKeyOut(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        kind=key.kind,  # type: ignore[arg-type]
        scopes=sorted(key.scopes),
        person=_person(key.acts_as_user),
        created_at=key.created_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        last_used_at=key.last_used_at,
    )


def views(rows: list[AgentAccess], order: list[str]) -> list[AgentAccessOut]:
    """The entries as the API answers them, the team labels read in one query."""
    labels = Labels.for_rows(TeamLabel, list({row.owner_team_id: row.owner_team for row in rows}.values()))
    return [
        AgentAccessOut(
            id=row.id,
            name=row.name,
            purpose=row.purpose,
            owner_team=AgentAccessTeamRef(
                key=row.owner_team.key,
                label=label_of(labels.texts(row.owner_team_id), order, original=labels.original(row.owner_team_id), key=row.owner_team.key),
            ),
            departments=[AgentAccessUnitRef(id=link.department_id, name=link.department.name) for link in row.departments.all()],
            products=[AgentAccessUnitRef(id=link.product_id, name=link.product.name) for link in row.products.all()],
            tenant_reach=row.tenant_reach,
            active=row.active,
            revoked_at=row.revoked_at,
            revoked_by=_person(row.revoked_by),
            created_by=PersonRef(id=row.created_by.id, name=row.created_by.name),
            created_at=row.created_at,
            version=row.version,
            keys=[key_out(key) for key in row.api_keys.all()],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------
def _name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("Give the agent a name.", code="name_required")
    return cleaned


def _purpose(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("Say what the agent does.", code="purpose_required")
    return cleaned


def _team(tenant: Tenant, key: str) -> Team:
    team = Team.objects.filter(tenant=tenant, key=key, active=True).first()  # ordering: unique per tenant and key, at most one row
    if team is None:
        raise ValidationError(f"The bank has no team {key}.", code="unknown_key")
    return team


def _known(model: Any, tenant: Tenant, ids: Iterable[uuid.UUID], what: str) -> list[uuid.UUID]:
    wanted = sorted(set(ids))
    found = set(model.objects.filter(tenant=tenant, pk__in=wanted).values_list("pk", flat=True))
    if len(found) != len(wanted):
        raise ValidationError(f"Some of those {what} are not the bank's.", code="unknown_key")
    return wanted


def _set_links(row: AgentAccess, departments: list[uuid.UUID] | None, products: list[uuid.UUID] | None) -> None:
    if departments is not None:
        row.departments.all().delete()
        AgentAccessDepartment.objects.bulk_create(
            [AgentAccessDepartment(tenant_id=row.tenant_id, agent_access=row, department_id=unit) for unit in departments]
        )
    if products is not None:
        row.products.all().delete()
        AgentAccessProduct.objects.bulk_create(
            [AgentAccessProduct(tenant_id=row.tenant_id, agent_access=row, product_id=product) for product in products]
        )


def _state(row: AgentAccess, departments: list[uuid.UUID], products: list[uuid.UUID]) -> dict[str, Any]:
    """What an audit row keeps of an entry: keys and ids, never the purpose the bank wrote."""
    return {
        "name": row.name,
        "ownerTeam": row.owner_team.key,
        "departmentIds": [str(unit) for unit in departments],
        "productIds": [str(product) for product in products],
        "tenantReach": row.tenant_reach,
        "active": row.active,
        "version": row.version,
    }


def _links(row: AgentAccess) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    return (
        sorted(row.departments.values_list("department_id", flat=True)),
        sorted(row.products.values_list("product_id", flat=True)),
    )


def _locked(tenant: Tenant, entry_id: uuid.UUID, expected_version: int | None) -> AgentAccess:
    """The live entry, locked so two writes queue on it, its version checked under the lock."""
    row = AgentAccess.objects.select_for_update().select_related("owner_team").filter(tenant=tenant, pk=entry_id).first()  # ordering: pk lookup, at most one row
    if row is None:
        raise ValidationError("That agent access entry is not here.", code="not_found")
    if not row.active:
        raise ValidationError("This entry is revoked; register a new one instead.", code="invalid_transition")
    if expected_version is not None and expected_version != row.version:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")
    return row


def register(
    *,
    tenant: Tenant,
    user: Any,
    actor: Actor,
    name: str,
    purpose: str,
    owner_team: str,
    department_ids: Iterable[uuid.UUID],
    product_ids: Iterable[uuid.UUID],
    step_up_assertion_id: uuid.UUID,
) -> AgentAccess:
    departments = _known(OrgUnit, tenant, department_ids, "departments")
    products = _known(TenantProduct, tenant, product_ids, "products")
    row = AgentAccess.objects.create(
        tenant=tenant,
        name=_name(name),
        purpose=_purpose(purpose),
        owner_team=_team(tenant, owner_team),
        created_by=user,
    )
    _set_links(row, departments, products)
    record(
        action="agent_access.registered",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=row.name,
        summary=f"Registered the agent access entry {row.name}.",
        tenant_id=tenant.id,
        after=_state(row, departments, products),
        step_up_assertion_id=step_up_assertion_id,
    )
    return row


def update(
    *,
    tenant: Tenant,
    entry_id: uuid.UUID,
    actor: Actor,
    name: str | None,
    purpose: str | None,
    owner_team: str | None,
    department_ids: Iterable[uuid.UUID] | None,
    product_ids: Iterable[uuid.UUID] | None,
    expected_version: int | None,
    step_up_assertion_id: uuid.UUID,
) -> AgentAccess:
    row = _locked(tenant, entry_id, expected_version)
    before = _state(row, *_links(row))
    departments = _known(OrgUnit, tenant, department_ids, "departments") if department_ids is not None else None
    products = _known(TenantProduct, tenant, product_ids, "products") if product_ids is not None else None
    if name is not None:
        row.name = _name(name)
    if purpose is not None:
        row.purpose = _purpose(purpose)
    if owner_team is not None:
        row.owner_team = _team(tenant, owner_team)
    row.version += 1
    row.save(update_fields=["name", "purpose", "owner_team", "version"])
    _set_links(row, departments, products)
    after = _state(row, *_links(row))
    after["purposeChanged"] = purpose is not None
    record(
        action="agent_access.updated",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=row.name,
        summary=f"Changed the agent access entry {row.name}.",
        tenant_id=tenant.id,
        before=before,
        after=after,
        step_up_assertion_id=step_up_assertion_id,
    )
    return row


def set_tenant_reach(
    *, tenant: Tenant, entry_id: uuid.UUID, actor: Actor, enabled: bool, expected_version: int | None, step_up_assertion_id: uuid.UUID
) -> AgentAccess:
    """The entry's own toggle. It counts only while the bank's switch is on too."""
    row = _locked(tenant, entry_id, expected_version)
    before = {"tenantReach": row.tenant_reach, "version": row.version}
    row.tenant_reach = enabled
    row.version += 1
    row.save(update_fields=["tenant_reach", "version"])
    record(
        action="agent_access.reach_set",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=row.name,
        summary=f"Tenant reach {'on' if enabled else 'off'} for the agent access entry {row.name}.",
        tenant_id=tenant.id,
        before=before,
        after={"tenantReach": row.tenant_reach, "version": row.version},
        step_up_assertion_id=step_up_assertion_id,
    )
    return row


def revoke(
    *, tenant: Tenant, entry_id: uuid.UUID, user: Any, actor: Actor, expected_version: int | None, step_up_assertion_id: uuid.UUID
) -> AgentAccess:
    """Deactivate the entry and revoke every credential bound to it, at once."""
    row = _locked(tenant, entry_id, expected_version)
    row.active = False
    row.revoked_by = user
    row.revoked_at = timezone.now()
    row.version += 1
    row.save(update_fields=["active", "revoked_by", "revoked_at", "version"])
    prefixes = api_keys_logic.revoke_entry_credentials(tenant=tenant, entry_id=row.id, revoked_by=user)
    record(
        action="agent_access.revoked",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=row.name,
        summary=f"Revoked the agent access entry {row.name} and {len(prefixes)} credential(s) under it.",
        tenant_id=tenant.id,
        before={"active": True, "version": row.version - 1},
        after={"active": False, "version": row.version, "revokedKeyPrefixes": prefixes},
        step_up_assertion_id=step_up_assertion_id,
    )
    return row


def create_key(
    *,
    tenant: Tenant,
    entry_id: uuid.UUID,
    user: Any,
    actor: Actor,
    name: str,
    scopes: Iterable[str],
    expires_at: datetime | None,
    step_up_assertion_id: uuid.UUID,
) -> tuple[ApiKey, str]:
    """A service key for a live entry of the bank, shown once."""
    row = _locked(tenant, entry_id, None)
    return api_keys_logic.create_entry_key(
        tenant=tenant,
        entry_id=row.id,
        actor=actor,
        created_by=user,
        name=name,
        scopes=scopes,
        expires_at=expires_at,
        step_up_assertion_id=step_up_assertion_id,
    )


def revoke_key(
    *, tenant: Tenant, entry_id: uuid.UUID, key_id: uuid.UUID, user: Any, actor: Actor, step_up_assertion_id: uuid.UUID
) -> ApiKey:
    """One credential of the bank's entry, revoked or already so. A revoked entry's
    credentials are already revoked, so this stays a safe retry there too."""
    entry(tenant.id, entry_id)
    return api_keys_logic.revoke_entry_key(
        tenant=tenant, entry_id=entry_id, key_id=key_id, actor=actor, revoked_by=user, step_up_assertion_id=step_up_assertion_id
    )
