"""`/me`: the caller's own account (ID-04, AC-ID2). The enrolment session may read it and
sees `enrolmentPending` true; it may change nothing else."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.identity import passkey_logic, roles_logic, session_logic
from apps.identity.models import Membership, PlatformRoleAssignment, User, UserStatus
from apps.library.models import Language
from apps.shared.audit import record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import Tenant


def _tenant_out(tenant: Tenant | None) -> dict[str, Any] | None:
    if tenant is None:
        return None
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "timezone": tenant.timezone}


def me(principal: Principal) -> dict[str, Any]:
    user = User.objects.select_related("locale").get(pk=principal.subject_id)
    tenant = Tenant.objects.select_related("default_language").filter(pk=principal.tenant_id).first() if principal.tenant_id else None  # ordering: pk lookup, at most one row
    order = roles_logic.language_order(user, tenant)
    roles: list[dict[str, Any]] = []
    if principal.kind is PrincipalKind.USER and tenant is not None:
        membership = (
            Membership.objects.filter(tenant=tenant, user=user, deactivated_at__isnull=True)
            .prefetch_related("roles__labels")
            .first()
        )  # ordering: unique (tenant, user), at most one row
        if membership is not None:
            roles = [roles_logic.role_ref(role, order) for role in membership.roles.all()]
    platform_roles = [
        roles_logic.role_ref(assignment.role, order)
        for assignment in PlatformRoleAssignment.objects.filter(user=user, role__active=True).select_related("role").prefetch_related("role__labels")
    ]
    assertion = session_logic.latest_step_up(principal.session_id) if principal.session_id else None
    fresh_until = passkey_logic.step_up_valid_until(assertion) if assertion else None
    if fresh_until is not None and fresh_until <= timezone.now():
        fresh_until = None
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name, "locale": user.locale.key if user.locale else None},
        "tenant": _tenant_out(tenant),
        "roles": roles,
        "permissions": sorted(principal.permissions),
        "platform_roles": platform_roles,
        "enrolment_pending": principal.kind is PrincipalKind.ENROLMENT or user.status != UserStatus.ACTIVE.value,
        "passkey_count": len(passkey_logic.list_passkeys(user.id)),
        "step_up_valid_until": fresh_until,
    }


def update_me(principal: Principal, *, name: str | None, locale: str | None) -> dict[str, Any]:
    user = User.objects.select_related("locale").get(pk=principal.subject_id)
    before = {"name": user.name, "locale": user.locale.key if user.locale else None}
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Enter your name.", code="name_required")
        user.name = cleaned
    if locale is not None:
        language = Language.objects.filter(key=locale, active=True).first()  # ordering: key is unique, at most one row
        if language is None:
            raise ValidationError("Unknown language.", code="unknown_key")
        user.locale = language
    user.save(update_fields=["name", "locale"])
    record(
        action="user.updated",
        actor=session_logic.actor_of(user),
        subject_type="user",
        subject_id=user.id,
        subject_title=user.name,
        summary="Profile updated.",
        tenant_id=principal.tenant_id,
        before=before,
        after={"name": user.name, "locale": user.locale.key if user.locale else None},
    )
    return me(principal)
