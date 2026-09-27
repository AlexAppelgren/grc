"""`/me`: the caller's own account (ID-04, AC-ID2). The enrolment session may read it and
sees `enrolmentPending` true; it may change nothing else.

`counts` and `lastVisitAt` (f03-T48, D-23) are Today's "Decide now" source: `docs/inputs/
openapi.yaml` put a `decideNow` field on `Home` and D-23 moved it here instead, so a queue
count has one source. `_counts()` runs three independent reads, none chained behind
another, and each is filtered by the caller's own permission rather than refused: a member
without `cases.triage` or `proposals.create` reads a true 0, never a 403 that would take
the panel away (chunk 6 default). The session's tenant is already activated by the time
this runs (`session_logic.resolve_access_token`), so every read below is under row-level
security without activating it again."""

from __future__ import annotations

import datetime
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cases.models import ChangeCase
from apps.collab.models import Notification
from apps.identity import passkey_logic, roles_logic, session_logic
from apps.identity.models import Membership, PlatformRoleAssignment, User, UserStatus
from apps.identity.schemas import MembershipNotificationPrefs, MembershipNotificationPrefsPatch
from apps.library.models import Language
from apps.proposals.models import ProposalStatus, ProposalTenant
from apps.shared import permissions as perms
from apps.shared.audit import record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import Tenant
from apps.taxonomy.models import CaseStatusCategory
from apps.tenants.models import OrgUnit, OrgUnitKind

# The two categories a case has finished in (D-13): excluded from "assigned to me" so a
# closed or dismissed case a person once owned does not sit in their queue forever. The
# same pair `apps/home/roadmap.py` excludes from the roadmap; identity does not import
# from home; two lines is not worth a cross-app dependency for.
_FINISHED_CASES = (CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value)

DEPARTMENT_KINDS = (OrgUnitKind.BUSINESS_AREA.value, OrgUnitKind.BUSINESS_UNIT.value, OrgUnitKind.FUNCTION.value)


def _tenant_out(tenant: Tenant | None) -> dict[str, Any] | None:
    if tenant is None:
        return None
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "timezone": tenant.timezone}


def _counts(principal: Principal) -> dict[str, int]:
    """`MeCounts`: four independent reads, none chained behind another (a pinned query
    count proves it in `tests_me_counts.py`). A count behind a permission the caller lacks
    is 0 without the query ever running, exactly as `home.logic.home_today()` skips a panel
    a reader may not see rather than reading it and hiding the answer."""
    triage = 0
    if principal.has_permission(perms.CASES_TRIAGE):
        triage = ChangeCase.objects.filter(status=CaseStatusCategory.NEW.value).count()
    proposals = 0
    if principal.has_permission(perms.PROPOSALS_CREATE):
        # A proposal itself carries no tenant_id (PRO-01: the library is shared). Which
        # bank made it is `ProposalTenant`, a tenant table of its own under row-level
        # security (PRO-03) filed at the same time as the proposal; reading through it
        # rather than the proposer's current membership means a proposal counts here even
        # after its author has since left the bank.
        proposals = ProposalTenant.objects.filter(proposal__status=ProposalStatus.OPEN.value).count()
    assigned_to_me = ChangeCase.objects.filter(owner_id=principal.subject_id).exclude(status__in=_FINISHED_CASES).count()
    # Row-level security keeps this to the session's bank; every member reads their own.
    unread = Notification.objects.filter(user_id=principal.subject_id, read_at__isnull=True).count()
    return {"triage": triage, "proposals": proposals, "assignedToMe": assigned_to_me, "unreadNotifications": unread}


def _head_of(tenant: Tenant, user: User) -> list[dict[str, Any]]:
    """The active departments the member heads, by name (TEN-02, HOM-05, D-21). A department is
    a business area, business unit or function; a legal entity or group never is."""
    units = OrgUnit.objects.filter(tenant=tenant, head_user=user, active=True, kind__in=DEPARTMENT_KINDS).order_by("name", "id")
    return [{"id": unit.id, "name": unit.name} for unit in units]


def notification_prefs(membership: Membership) -> dict[str, bool]:
    """A member's switches as stored (the schema's camelCase keys), with every key they
    never set read as on, so an older row needs no migration (COL-02)."""
    return MembershipNotificationPrefs.model_validate(membership.notification_prefs).model_dump(by_alias=True)


def me(principal: Principal) -> dict[str, Any]:
    user = User.objects.select_related("locale").get(pk=principal.subject_id)
    tenant = Tenant.objects.select_related("default_language").filter(pk=principal.tenant_id).first() if principal.tenant_id else None  # ordering: pk lookup, at most one row
    order = roles_logic.language_order(user, tenant)
    roles: list[dict[str, Any]] = []
    last_visit_at = None
    prefs = None
    head_of: list[dict[str, Any]] = []
    if principal.kind is PrincipalKind.USER and tenant is not None:
        membership = (
            Membership.objects.filter(tenant=tenant, user=user, deactivated_at__isnull=True)
            .prefetch_related("roles__labels")
            .first()
        )  # ordering: unique (tenant, user), at most one row
        if membership is not None:
            roles = [roles_logic.role_ref(role, order) for role in membership.roles.all()]
            last_visit_at = membership.last_visit_at
            prefs = notification_prefs(membership)
            head_of = _head_of(tenant, user)
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
        "counts": _counts(principal) if principal.tenant_id is not None else None,
        "last_visit_at": last_visit_at,
        "notification_prefs": prefs,
        "head_of": head_of,
        "roles": roles,
        "permissions": sorted(principal.permissions),
        "platform_roles": platform_roles,
        "enrolment_pending": principal.kind is PrincipalKind.ENROLMENT or user.status != UserStatus.ACTIVE.value,
        "passkey_count": len(passkey_logic.list_passkeys(user.id)),
        "step_up_valid_until": fresh_until,
    }


def update_me(
    principal: Principal,
    *,
    name: str | None,
    locale: str | None,
    notification_prefs_patch: MembershipNotificationPrefsPatch | None,
) -> dict[str, Any]:
    """The caller's own name, language and notification switches, in one audit event with
    before and after: these are the person's own settings, not tenant content. A switch
    key the schema does not name is refused before anything is written."""
    user = User.objects.select_related("locale").get(pk=principal.subject_id)
    before: dict[str, Any] = {"name": user.name, "locale": user.locale.key if user.locale else None}
    after: dict[str, Any] = {}
    membership = None
    if notification_prefs_patch is not None:
        if notification_prefs_patch.model_extra:
            raise ValidationError("Unknown notification preference.", code="unknown_key")
        if principal.tenant_id is not None:
            membership = Membership.objects.filter(
                tenant_id=principal.tenant_id, user_id=user.id, deactivated_at__isnull=True
            ).first()  # ordering: unique (tenant, user), at most one row
        if membership is None:
            raise ValidationError("Not found.", code="not_found")
        prefs = notification_prefs(membership)
        before["notificationPrefs"] = prefs
        changed = notification_prefs_patch.model_dump(exclude_none=True, by_alias=True)
        membership.notification_prefs = {**prefs, **changed}
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
    after.update({"name": user.name, "locale": user.locale.key if user.locale else None})
    if membership is not None:
        membership.save(update_fields=["notification_prefs"])
        after["notificationPrefs"] = membership.notification_prefs
    record(
        action="user.updated",
        actor=session_logic.actor_of(user),
        subject_type="user",
        subject_id=user.id,
        subject_title=user.name,
        summary="Profile updated.",
        tenant_id=principal.tenant_id,
        before=before,
        after=after,
    )
    return me(principal)


def mark_visit(principal: Principal) -> None:
    """Move the caller's "seen the library" bookmark to now (PRO-03, AUD-01).

    The bookmark is a column of the caller's own membership, so the tenant app writes it
    for the person who is signed in and for nobody else; the library-updates screen reads
    it back to decide which updates are new to them. It is a reading habit, not a
    judgement about a regulation, so it stays inside the bank that owns the membership row
    and never reaches the library zone.

    Platform staff read the library itself rather than a bank's view of it, so a session
    with no tenant has no bookmark to move: 404, like every other tenant route, with
    nothing written.

    Each move writes an audit and an outbox row kept for ten years, so a visit within
    `VISIT_MIN_INTERVAL_SECONDS` of the last one writes nothing at all (hardening H38): the
    bookmark it would have moved is already that recent.
    """
    membership = None
    if principal.tenant_id is not None:
        query = Membership.objects.select_related("user").filter(
            tenant_id=principal.tenant_id, user_id=principal.subject_id, deactivated_at__isnull=True
        )
        membership = query.first()  # ordering: unique (tenant, user), at most one row
    if membership is None:
        raise ValidationError("Not found.", code="not_found")
    seen_before = membership.last_visit_at
    now = timezone.now()
    if seen_before is not None and datetime.timedelta(0) <= now - seen_before < datetime.timedelta(seconds=settings.VISIT_MIN_INTERVAL_SECONDS):
        return
    membership.last_visit_at = now
    membership.save(update_fields=["last_visit_at"])
    record(
        action="member.visited",
        actor=session_logic.actor_of(membership.user),
        subject_type="membership",
        subject_id=membership.id,
        subject_title=membership.user.name,
        summary="Marked the library as seen.",
        tenant_id=principal.tenant_id,
        before={"lastVisitAt": seen_before.isoformat() if seen_before else None},
        after={"lastVisitAt": membership.last_visit_at.isoformat()},
    )
