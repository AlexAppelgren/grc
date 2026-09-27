"""Roles are rows composed of permission constants (ID-09, PRD §6). System rows are seeded
per tenant from `SYSTEM_ROLES` (apps/shared/permissions.py) and relabelled but never
removed; a tenant adds its own. Platform roles are one shared list. Nothing here or
anywhere compares a role's key to decide anything: the flattened permission set is what
the auth layer hands the decorators."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import QuerySet

from apps.identity.models import PlatformRole, PlatformRoleLabel, TenantRole, TenantRoleLabel, User
from apps.library.models import Language
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.shared.vocabulary import label_for

DEFAULT_LANGUAGE = "en"
# The picker's default rows: the least privileged role of each list (vocabulary guard).
DEFAULT_TENANT_ROLE = "reader"
DEFAULT_PLATFORM_ROLE = "library_editor"

# Labels for the seeded rows, in the two UI languages of R1 (I18N-02). Tenants relabel.
TENANT_ROLE_LABELS: dict[str, dict[str, str]] = {
    "admin": {"en": "Administrator", "sv": "Administratör"},
    "compliance_officer": {"en": "Compliance officer", "sv": "Compliance officer"},
    "owner": {"en": "Obligation owner", "sv": "Ägare"},
    "approver": {"en": "Approver", "sv": "Godkännare"},
    "contributor": {"en": "Contributor", "sv": "Bidragsgivare"},
    "reader": {"en": "Reader", "sv": "Läsare"},
    "auditor": {"en": "Auditor", "sv": "Revisor"},
}
PLATFORM_ROLE_LABELS: dict[str, dict[str, str]] = {
    "library_editor": {"en": "Library editor", "sv": "Biblioteksredaktör"},
    "platform_admin": {"en": "Platform administrator", "sv": "Plattformsadministratör"},
}
TENANT_ROLE_USAGE: dict[str, str] = {
    "admin": "Runs the organisation: members, roles, security, integrations. Not a case worker.",
    "compliance_officer": "Triages changes, assesses, proposes to the library, manages vocabularies.",
    "owner": "Owns obligations and works the cases that touch them.",
    "approver": "Signs off cases and approves regulatory scope and applicability decisions. Never the requester.",
    "contributor": "Adds assessment input, actions and evidence on cases they are asked to help with.",
    "reader": "Reads everything, changes nothing.",
    "auditor": "Reads everything, exports and the AI log included.",
}
PLATFORM_ROLE_USAGE: dict[str, str] = {
    "library_editor": "Reviews proposals and curates the shared library in the console.",
    "platform_admin": "Manages tenants, agent definitions, support access and system health.",
}


def language_order(user: User | None, tenant: Tenant | None) -> list[str]:
    order: list[str] = []
    if user is not None and user.locale_id is not None and user.locale is not None:
        order.append(user.locale.key)
    if tenant is not None and tenant.default_language_id is not None and tenant.default_language is not None:
        order.append(tenant.default_language.key)
    order.append(DEFAULT_LANGUAGE)
    return order


def role_ref(role: TenantRole | PlatformRole, order: list[str]) -> dict[str, Any]:
    return {"key": role.key, "kind": role.kind, "label": label_for(role, order)}


def _labels_dict(role: TenantRole | PlatformRole) -> dict[str, str]:
    return {label.language: label.text for label in role.labels.all()}


# ---------------------------------------------------------------------------------------
# Seeds (idempotent, keyed on the immutable key)
# ---------------------------------------------------------------------------------------
def ensure_system_roles(tenant: Tenant) -> int:
    """Create or refresh the system roles of one tenant. Permissions follow the code (a
    PRD bump changes the matrix); labels and usage notes are written once and left to
    the tenant afterwards. Must run with the tenant activated."""
    count = 0
    for sort_order, key in enumerate(perms.SYSTEM_ROLES):
        if key in perms.PLATFORM_PERMISSIONS or key in PLATFORM_ROLE_LABELS:
            continue
        role, created = TenantRole.objects.update_or_create(
            tenant=tenant,
            key=key,
            defaults={
                "permissions": sorted(perms.SYSTEM_ROLES[key]),
                "is_system": True,
                "active": True,
                "sort_order": sort_order,
                "is_default": key == DEFAULT_TENANT_ROLE,
            },
        )
        if created:
            role.usage_note = TENANT_ROLE_USAGE.get(key, "")
            role.save(update_fields=["usage_note"])
            for language, text in TENANT_ROLE_LABELS[key].items():
                TenantRoleLabel.objects.create(
                    tenant=tenant, vocabulary=role, language=language, text=text, is_original=language == "en"
                )
        count += 1
    return count


def ensure_platform_roles() -> int:
    count = 0
    for sort_order, key in enumerate(PLATFORM_ROLE_LABELS):
        role, created = PlatformRole.objects.update_or_create(
            key=key,
            defaults={
                "permissions": sorted(perms.SYSTEM_ROLES[key]),
                "is_system": True,
                "active": True,
                "sort_order": sort_order,
                "is_default": key == DEFAULT_PLATFORM_ROLE,
            },
        )
        if created:
            role.usage_note = PLATFORM_ROLE_USAGE[key]
            role.save(update_fields=["usage_note"])
            for language, text in PLATFORM_ROLE_LABELS[key].items():
                PlatformRoleLabel.objects.create(vocabulary=role, language=language, text=text, is_original=language == "en")
        count += 1
    return count


# ---------------------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------------------
def tenant_roles(tenant_id: uuid.UUID, *, include_retired: bool = False) -> QuerySet[TenantRole]:
    queryset = TenantRole.objects.filter(tenant_id=tenant_id).prefetch_related("labels")
    if not include_retired:
        queryset = queryset.filter(active=True)
    return queryset.order_by("sort_order", "key")


def tenant_role_by_key(tenant_id: uuid.UUID, key: str) -> TenantRole:
    role = tenant_roles(tenant_id, include_retired=True).filter(key=key.strip().lower()).first()  # ordering: unique (tenant, key), at most one row
    if role is None:
        raise ValidationError("Not found.", code="not_found")
    return role


def roles_by_keys(tenant_id: uuid.UUID, keys: Iterable[str]) -> list[TenantRole]:
    wanted = [key for key in dict.fromkeys(keys)]
    if not wanted:
        raise ValidationError("Pick at least one role.", code="roles_required")
    found = {role.key: role for role in tenant_roles(tenant_id).filter(key__in=wanted)}
    unknown = [key for key in wanted if key not in found]
    if unknown:
        raise ValidationError(f"Unknown role: {', '.join(unknown)}.", code="unknown_key")
    return [found[key] for key in wanted]


def permissions_of(roles: Iterable[TenantRole | PlatformRole]) -> frozenset[str]:
    granted: set[str] = set()
    for role in roles:
        granted.update(role.permissions)
    return frozenset(granted)


def role_out(role: TenantRole, order: list[str]) -> dict[str, Any]:
    return {
        **role_ref(role, order),
        "labels": _labels_dict(role),
        "usage_note": role.usage_note,
        "permissions": sorted(role.permissions),
        "is_system": role.is_system,
        "active": role.active,
    }


# ---------------------------------------------------------------------------------------
# Writes (roles.manage; step-up on permission changes, playbook 4.2)
# ---------------------------------------------------------------------------------------
def _validate_permissions(values: Iterable[str]) -> list[str]:
    wanted = sorted(dict.fromkeys(values))
    unknown = [value for value in wanted if value not in perms.TENANT_PERMISSIONS]
    if unknown:
        raise ValidationError(f"Unknown permission: {', '.join(unknown)}.", code="unknown_key")
    return wanted


def _validate_labels(labels: dict[str, str]) -> dict[str, str]:
    cleaned = {language: text.strip() for language, text in labels.items() if text and text.strip()}
    if not cleaned:
        raise ValidationError("Give the role a label in at least one language.", code="label_required")
    known = set(Language.objects.filter(key__in=cleaned, active=True).values_list("key", flat=True))
    unknown = sorted(set(cleaned) - known)
    if unknown:
        raise ValidationError(f"Unknown language: {', '.join(unknown)}.", code="unknown_key")
    return cleaned


def _write_labels(tenant: Tenant, role: TenantRole, labels: dict[str, str]) -> None:
    for language, text in labels.items():
        TenantRoleLabel.objects.update_or_create(
            vocabulary=role, language=language, defaults={"tenant": tenant, "text": text}
        )


def create_role(
    *,
    tenant: Tenant,
    actor: Actor,
    key: str,
    labels: dict[str, str],
    usage_note: str,
    permissions: Iterable[str],
    step_up_assertion_id: uuid.UUID | None,
) -> TenantRole:
    normalised = key.strip().lower()
    if not normalised:
        raise ValidationError("A role needs a key.", code="key_required")
    if TenantRole.objects.filter(tenant=tenant, key__iexact=normalised).exists():
        raise ValidationError("A role with that key already exists.", code="duplicate_key")
    cleaned_labels = _validate_labels(labels)
    granted = _validate_permissions(permissions)
    next_order = TenantRole.objects.filter(tenant=tenant).count()
    role = TenantRole.objects.create(
        tenant=tenant, key=normalised, permissions=granted, usage_note=usage_note.strip(), sort_order=next_order
    )
    _write_labels(tenant, role, cleaned_labels)
    record(
        action="role.created",
        actor=actor,
        subject_type="tenant_role",
        subject_id=role.id,
        subject_title=cleaned_labels.get(DEFAULT_LANGUAGE) or next(iter(cleaned_labels.values())),
        summary=f"Role {role.key} created with {len(granted)} permissions.",
        tenant_id=tenant.id,
        after={"key": role.key, "permissions": granted, "labels": cleaned_labels},
        step_up_assertion_id=step_up_assertion_id,
    )
    return role


def update_role(
    *,
    tenant: Tenant,
    actor: Actor,
    role: TenantRole,
    labels: dict[str, str] | None,
    usage_note: str | None,
    permissions: Iterable[str] | None,
    step_up_assertion_id: uuid.UUID | None,
) -> TenantRole:
    before = {"permissions": sorted(role.permissions), "usage_note": role.usage_note, "labels": _labels_dict(role)}  # compliance: record-content a role's own label and usage note are the values its audit row records (AUD-01)
    if permissions is not None and role.is_system:
        raise ValidationError("A system role's permissions follow the product; relabel it instead.", code="system_role")
    if permissions is not None:
        role.permissions = _validate_permissions(permissions)
    if usage_note is not None:
        role.usage_note = usage_note.strip()
    role.save()
    if labels:
        _write_labels(tenant, role, _validate_labels(labels))
    role = TenantRole.objects.prefetch_related("labels").get(pk=role.pk)
    after = {"permissions": sorted(role.permissions), "usage_note": role.usage_note, "labels": _labels_dict(role)}  # compliance: record-content a role's own label and usage note are the values its audit row records (AUD-01)
    record(
        action="role.updated",
        actor=actor,
        subject_type="tenant_role",
        subject_id=role.id,
        subject_title=role.key,
        summary=f"Role {role.key} updated.",
        tenant_id=tenant.id,
        before=before,
        after=after,
        step_up_assertion_id=step_up_assertion_id,
    )
    return role


def retire_role(*, tenant: Tenant, actor: Actor, role: TenantRole) -> TenantRole:
    if role.is_system:
        raise ValidationError("System roles can be relabelled, not retired.", code="system_role")
    in_use = role.membership_links.filter(membership__deactivated_at__isnull=True).count()
    if in_use:
        raise ValidationError(f"{in_use} member(s) hold this role. Reassign them first.", code="role_in_use")
    role.active = False
    role.save(update_fields=["active"])
    record(
        action="role.retired",
        actor=actor,
        subject_type="tenant_role",
        subject_id=role.id,
        subject_title=role.key,
        summary=f"Role {role.key} retired.",
        tenant_id=tenant.id,
        before={"active": True},
        after={"active": False},
    )
    return role
