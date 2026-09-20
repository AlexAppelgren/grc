"""Tenant profile and onboarding (TEN-01), the platform console's tenant list and
tenant creation with the first administrator's invitation (ADM-02, ID-01), and its
last-admin recovery (ID-05, ID-S13). Every write goes through record(); the timezone is
validated against the IANA database; languages are keys of Language rows."""

from __future__ import annotations

import uuid
import zoneinfo
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils import timezone
from django.utils.text import slugify

from apps.identity import invitation_logic, roles_logic
from apps.identity.models import Invitation, Membership, PlatformRoleAssignment, User, WebAuthnCredential
from apps.library.models import Language
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant, TenantContentLanguage
from apps.taxonomy.models import FootprintTerm
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from apps.tenants.models import SupportAccess, SupportAccessLevel

ONBOARDING_STEPS = ("profile", "members", "footprint", "vocabularies", "passkey")


def language_ref(language: Language | None) -> dict[str, Any] | None:
    if language is None:
        return None
    return {"key": language.key, "kind": None, "label": language.name}


def content_languages(tenant: Tenant) -> list[Language]:
    return [link.language for link in TenantContentLanguage.objects.filter(tenant=tenant).select_related("language").order_by("sort_order", "id")]


def onboarding(tenant: Tenant) -> dict[str, Any]:
    profile_done = bool(tenant.name.strip()) and tenant.default_language_id is not None and TenantContentLanguage.objects.filter(tenant=tenant).exists()
    members_done = Invitation.objects.filter(tenant=tenant).exists() or Membership.objects.filter(tenant=tenant).count() > 1
    admin_user_ids = [
        m.user_id
        for m in Membership.objects.filter(tenant=tenant, deactivated_at__isnull=True).prefetch_related("roles")
        if perms.MEMBERS_MANAGE in roles_logic.permissions_of(m.roles.all())
    ]
    passkey_done = WebAuthnCredential.objects.filter(user_id__in=admin_user_ids, retired_at__isnull=True).exists()
    done = {
        "profile": profile_done,
        "members": members_done,
        "footprint": FootprintTerm.objects.filter(tenant=tenant).exists(),
        "vocabularies": False,  # chunk 2
        "passkey": passkey_done,
    }
    steps = [{"key": key, "done": done[key]} for key in ONBOARDING_STEPS]
    return {"steps_done": sum(1 for step in steps if step["done"]), "steps": steps}


def tenant_out(tenant: Tenant) -> dict[str, Any]:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "timezone": tenant.timezone,
        "status": tenant.status,
        "default_language": language_ref(tenant.default_language),
        "content_languages": [language_ref(language) for language in content_languages(tenant)],
        "onboarding": onboarding(tenant),
    }


def get_tenant(tenant_id: uuid.UUID | None) -> Tenant:
    tenant = Tenant.objects.select_related("default_language").filter(pk=tenant_id).first() if tenant_id else None  # ordering: pk lookup, at most one row
    if tenant is None:
        raise ValidationError("Not found.", code="not_found")
    return tenant


def _validate_timezone(name: str) -> str:
    cleaned = name.strip()
    try:
        zoneinfo.ZoneInfo(cleaned)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError("Unknown timezone.", code="unknown_key") from exc
    return cleaned


def _languages_by_keys(keys: Iterable[str]) -> list[Language]:
    wanted = list(dict.fromkeys(keys))
    if not wanted:
        raise ValidationError("Pick at least one content language.", code="languages_required")
    found = {language.key: language for language in Language.objects.filter(key__in=wanted, active=True)}
    unknown = [key for key in wanted if key not in found]
    if unknown:
        raise ValidationError(f"Unknown language: {', '.join(unknown)}.", code="unknown_key")
    return [found[key] for key in wanted]


def set_content_languages(tenant: Tenant, languages: list[Language]) -> None:
    TenantContentLanguage.objects.filter(tenant=tenant).delete()
    for sort_order, language in enumerate(languages):
        TenantContentLanguage.objects.create(tenant=tenant, language=language, sort_order=sort_order)


def update_tenant(
    *,
    tenant: Tenant,
    actor: Actor,
    name: str | None,
    timezone_name: str | None,
    default_language: str | None,
    content_language_keys: list[str] | None,
) -> Tenant:
    before = {
        "name": tenant.name,
        "timezone": tenant.timezone,
        "defaultLanguage": tenant.default_language.key if tenant.default_language else None,
        "contentLanguages": [language.key for language in content_languages(tenant)],
    }
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Give the organisation a name.", code="name_required")
        tenant.name = cleaned
    if timezone_name is not None:
        tenant.timezone = _validate_timezone(timezone_name)
    if default_language is not None:
        tenant.default_language = _languages_by_keys([default_language])[0]
    tenant.save(update_fields=["name", "timezone", "default_language"])
    if content_language_keys is not None:
        set_content_languages(tenant, _languages_by_keys(content_language_keys))
    tenant = Tenant.objects.select_related("default_language").get(pk=tenant.pk)
    after = {
        "name": tenant.name,
        "timezone": tenant.timezone,
        "defaultLanguage": tenant.default_language.key if tenant.default_language else None,
        "contentLanguages": [language.key for language in content_languages(tenant)],
    }
    record(
        action="tenant.updated",
        actor=actor,
        subject_type="tenant",
        subject_id=tenant.id,
        subject_title=tenant.name,
        summary="Organisation profile updated.",
        tenant_id=tenant.id,
        before=before,
        after=after,
    )
    return tenant


# ---------------------------------------------------------------------------------------
# Console: the last admin recovers through platform support (ID-05, ID-S13)
# ---------------------------------------------------------------------------------------
def console_reissue_enrolment(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    platform_user: User,
    actor: Actor,
    reason: str,
    ticket_ref: str,
    out_of_band_check: str,
    request: HttpRequest | None,
    step_up_assertion_id: uuid.UUID | None,
) -> SupportAccess:
    if not reason.strip() or not out_of_band_check.strip():
        raise ValidationError("State the reason and how the person was verified out of band.", code="check_required")
    tenant = Tenant.objects.filter(pk=tenant_id).first()  # ordering: pk lookup, at most one row
    if tenant is None:
        raise ValidationError("Not found.", code="not_found")
    # Platform staff have no bypass (playbook 14): the support access row is the door,
    # written first, then the tenant is activated for the one action it covers.
    tenancy.activate(tenant.id)
    now = timezone.now()
    access = SupportAccess.objects.create(
        tenant=tenant,
        platform_user=platform_user,
        reason=reason.strip(),
        ticket_ref=ticket_ref.strip(),
        access_level=SupportAccessLevel.WRITE.value,
        started_at=now,
        ended_at=now,
    )
    record(
        action="support_access.recorded",
        actor=actor,
        subject_type="support_access",
        subject_id=access.id,
        subject_title=platform_user.name,
        summary="Platform support entered the tenant to re-issue an administrator's enrolment.",
        tenant_id=tenant.id,
        after={"reason": access.reason, "ticketRef": access.ticket_ref, "outOfBandCheck": out_of_band_check.strip()},
        step_up_assertion_id=step_up_assertion_id,
    )
    membership = Membership.objects.filter(tenant=tenant, user_id=user_id, deactivated_at__isnull=True).select_related("user").first()  # ordering: unique (tenant, user), at most one row
    if membership is None:
        raise ValidationError("Not found.", code="not_found")
    invitation_logic.reissue_enrolment(
        tenant=tenant,
        user=membership.user,
        actor=actor,
        actor_user=platform_user,
        request=request,
        step_up_assertion_id=step_up_assertion_id,
        extra_after={"supportAccessId": str(access.id), "outOfBandCheck": out_of_band_check.strip()},
    )
    return access


# ---------------------------------------------------------------------------------------
# Console: create a bank and invite its first administrator (ADM-02, ADM-S6)
# ---------------------------------------------------------------------------------------
def console_tenant_row(tenant: Tenant) -> dict[str, Any]:
    """What the console list shows: the tenant row itself, never anything under it."""
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "default_language": language_ref(tenant.default_language),
        "created_at": tenant.created,
    }


def console_tenants(*, limit: int, offset: int) -> tuple[list[Tenant], int]:
    tenants = Tenant.objects.select_related("default_language").order_by("slug")
    return list(tenants[offset : offset + limit]), tenants.count()


def _validate_slug(slug: str) -> str:
    cleaned = slug.strip().lower()
    if not cleaned or slugify(cleaned) != cleaned:
        raise ValidationError("A short name is lower-case letters, digits and hyphens.", code="invalid_slug")
    return cleaned


def create_tenant(
    *,
    actor: Actor,
    name: str,
    slug: str,
    timezone_name: str,
    default_language: str,
    content_language_keys: list[str],
    first_admin_email: str,
    first_admin_title: str,
) -> Tenant:
    """Write the bank, give it its roles, lists and languages, and invite its first
    administrator, in the caller's transaction (FIRST_RUN_SETUP steps 6 and 7)."""
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValidationError("Give the organisation a name.", code="name_required")
    cleaned_slug = _validate_slug(slug)
    if Tenant.objects.filter(slug=cleaned_slug).exists():
        raise ValidationError("An organisation already uses that short name.", code="duplicate_key")
    zone = _validate_timezone(timezone_name)
    languages = _languages_by_keys(content_language_keys)
    default = _languages_by_keys([default_language])[0]
    email = invitation_logic.normalise_email(first_admin_email)
    # Platform staff are separate accounts, the same rule bootstrap_platform enforces from
    # the other side: a platform role holder invited into a bank would carry the console's
    # permissions into a bank session.
    if PlatformRoleAssignment.objects.filter(user__email=email).exists():
        raise ValidationError(
            "That address belongs to platform staff. Invite the bank's administrator with an address of their own.",
            code="platform_account",
        )
    tenant = Tenant.objects.create(name=cleaned_name, slug=cleaned_slug, timezone=zone, default_language=default)
    # Platform staff have no bypass (playbook 14): the one tenant this call activates is
    # the one it has just written, so no other tenant's rows are readable or writable here.
    tenancy.activate(tenant.id)
    set_content_languages(tenant, languages)
    roles_logic.ensure_system_roles(tenant)
    ensure_tenant_vocabularies(tenant)
    record(
        action="tenant.created",
        actor=actor,
        subject_type="tenant",
        subject_id=tenant.id,
        subject_title=tenant.name,
        summary="Organisation created from the platform console.",
        tenant_id=tenant.id,
        after={
            "name": tenant.name,
            "slug": tenant.slug,
            "timezone": tenant.timezone,
            "defaultLanguage": default.key,
            "contentLanguages": [language.key for language in languages],
        },
    )
    # The first administrator gets the system role that can invite the rest of the bank,
    # chosen by its permission and never by a role name (playbook 4.2). roles_by_keys
    # refuses an empty list, so the invitation can never go out without that role.
    admin_keys = [key for key, granted in perms.SYSTEM_ROLES.items() if perms.MEMBERS_MANAGE in granted]
    invitation_logic.create_invitation(
        tenant=tenant,
        email=email,
        roles=roles_logic.roles_by_keys(tenant.id, admin_keys),
        title=first_admin_title.strip(),
        # No `invited_by`: the invitation comes from the platform, whose staff are never
        # members of the bank they open.
        invited_by=None,
        actor=actor,
    )
    return tenant
