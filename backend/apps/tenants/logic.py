"""Tenant profile and onboarding (TEN-01), the platform console's tenant list and
tenant creation with the first administrator's invitation (ADM-02, ID-01), and its
last-admin recovery (ID-05, ID-S13). Every write goes through record(); the timezone is
validated against the IANA database; languages are keys of Language rows."""

from __future__ import annotations

import re
import uuid
import zoneinfo
from collections.abc import Iterable
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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


# Letters slugify would drop because Unicode decomposition has no ASCII for them ("Sør"
# became "sr"): ø, æ, the German sharp s, Faroese and Icelandic ð and þ, the Sami đ, ŋ and
# ŧ, and œ and ł; å is listed beside them for the reader. Names are lower-cased first, so
# this covers the capitals too.
_SPELLED_OUT = str.maketrans(
    {"ø": "o", "æ": "ae", "å": "a", "ß": "ss", "ð": "d", "þ": "th"}
    | {"đ": "d", "ŋ": "ng", "ŧ": "t", "œ": "oe", "ł": "l"}
)
# Slugify keeps underscores; a short name holds letters, digits and single hyphens only.
_SEPARATORS = re.compile(r"[-_]+")
_SLUG_MAX_LENGTH = cast(int, Tenant._meta.get_field("slug").max_length)


def _derive_slug(name: str) -> str:
    """A short name from the organisation's name, never typed by a person (D-68): letters
    without a decomposition spelled out, lower-cased and hyphenated. `_create_with_derived_slug`
    cuts it to fit the column and de-duplicates it."""
    slug = _SEPARATORS.sub("-", slugify(name.lower().translate(_SPELLED_OUT))).strip("-")
    return slug or "tenant"


def _create_with_derived_slug(name: str) -> Tenant:
    """Insert the tenant under the first free short name: the derived one, then with -2, -3
    and so on, each cut so that it and its suffix fit the column without a trailing hyphen.
    The insert runs in a savepoint, so a tenant of the same name committed by a concurrent
    creation after the existence check costs a retry with the next suffix, not the request."""
    base = _derive_slug(name)
    n = 1
    while True:
        suffix = f"-{n}" if n > 1 else ""
        slug = base[: _SLUG_MAX_LENGTH - len(suffix)].rstrip("-") + suffix
        n += 1
        if Tenant.objects.filter(slug=slug).exists():
            continue
        try:
            with transaction.atomic():
                return Tenant.objects.create(name=name, slug=slug)
        except IntegrityError as exc:
            # Only the short name's uniqueness means "taken, try the next"; any other refusal
            # is a fault and surfaces as one.
            if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) != "tenant_slug_key":
                raise


def create_tenant(
    *,
    actor: Actor,
    name: str,
    first_admin_email: str,
    first_admin_title: str,
) -> Tenant:
    """Write the bank and invite its first administrator, in the caller's transaction
    (FIRST_RUN_SETUP steps 6 and 7). The timezone, default language and content languages
    are the bank's own to set, on the Organisation profile screen that already self-services
    them under security.manage (D-68): platform staff no longer guess at them, the tenant
    reads the model's default timezone and no language until its administrator chooses one,
    and the onboarding "profile" step stays open until they do."""
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValidationError("Give the organisation a name.", code="name_required")
    email = invitation_logic.normalise_email(first_admin_email)
    # Platform staff are separate accounts, the same rule bootstrap_platform enforces from
    # the other side: a platform role holder invited into a bank would carry the console's
    # permissions into a bank session.
    if PlatformRoleAssignment.objects.filter(user__email=email).exists():
        raise ValidationError(
            "That address belongs to platform staff. Invite the bank's administrator with an address of their own.",
            code="platform_account",
        )
    tenant = _create_with_derived_slug(cleaned_name)
    # Platform staff have no bypass (playbook 14): the one tenant this call activates is
    # the one it has just written, so no other tenant's rows are readable or writable here.
    tenancy.activate(tenant.id)
    roles_logic.ensure_system_roles(tenant)
    # The lists are this person's work too, not a deploy's: the same actor the creation
    # below is recorded under.
    ensure_tenant_vocabularies(tenant, actor=actor)
    record(
        action="tenant.created",
        actor=actor,
        subject_type="tenant",
        subject_id=tenant.id,
        subject_title=tenant.name,
        summary="Organisation created from the platform console.",
        tenant_id=tenant.id,
        after={"name": tenant.name, "slug": tenant.slug, "timezone": tenant.timezone},
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
