"""`/me`: the caller's own account (ID-04, AC-ID2). The enrolment session may read it and
sees `enrolmentPending` true; it may change nothing else.

`counts` and `lastVisitAt` (f03-T48, D-23) are Today's "Decide now" source: `docs/inputs/
openapi.yaml` put a `decideNow` field on `Home` and D-23 moved it here instead, so a queue
count has one source. `_figures()` reads every count as a subquery of one statement, and
each is filtered by the caller's own permission rather than refused: a member
without `cases.triage` or `proposals.create` reads a true 0, never a 403 that would take
the panel away (chunk 6 default). The session's tenant is already activated by the time
this runs (`session_logic.resolve_access_token`), so every read below is under row-level
security without activating it again.

R2's four decision counts (x-decide-now-counts: CAS-06, REG-03, TEN-06, ACC-08) count what
the caller may decide and never a request they made themselves, which four eyes would
refuse them. D-75 removed applicability requests, so there is no applicability count."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import F, Func, QuerySet, Subquery
from django.utils import timezone

from apps.cases.models import ChangeCase
from apps.collab.models import Notification
from apps.governance.models import TenantReachRequest
from apps.identity import passkey_logic, roles_logic, session_logic
from apps.identity.models import Membership, PlatformRoleAssignment, User, UserStatus, WebAuthnCredential
from apps.identity.schemas import MembershipNotificationPrefs, MembershipNotificationPrefsPatch
from apps.library.models import Language
from apps.proposals.models import ProposalStatus, ProposalTenant
from apps.register.models import Gap
from apps.shared import permissions as perms
from apps.shared.audit import record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import Tenant
from apps.taxonomy.models import ApprovalStatus, CaseStatusCategory, GapCategory
from apps.tenants.models import DEPARTMENT_KINDS, OrgUnit

# The two categories a case has finished in (D-13): excluded from "assigned to me" so a
# closed or dismissed case a person once owned does not sit in their queue forever. The
# same pair `apps/home/roadmap.py` excludes from the roadmap; identity does not import
# from home; two lines is not worth a cross-app dependency for.
_FINISHED_CASES = (CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value)

def _tenant_out(tenant: Tenant | None) -> dict[str, Any] | None:
    if tenant is None:
        return None
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "timezone": tenant.timezone}


# `MeCounts`, in the order the schema names them.
COUNT_NAMES = (
    "triage",
    "proposals",
    "assignedToMe",
    "unreadNotifications",
    "signoffs",
    "riskAcceptances",
    "supportAccessRequests",
    "tenantReachRequests",
)


def _count(queryset: QuerySet[Any]) -> Subquery:
    """`queryset`'s row count as a scalar subquery, so every count of `/me` is one read."""
    return Subquery(queryset.order_by().annotate(n=Func(F("pk"), function="COUNT")).values("n"))


def _count_subqueries(principal: Principal) -> dict[str, Any]:
    """`MeCounts`, as the subqueries of `_figures()`'s one read. A count behind a permission
    the caller lacks is 0 without its subquery ever running, exactly as
    `home.logic.home_today()` skips a panel a reader may not see rather than reading it and
    hiding the answer."""
    me = principal.subject_id
    counts: dict[str, Any] = {}
    if principal.has_permission(perms.CASES_TRIAGE):
        counts["triage"] = _count(ChangeCase.objects.filter(status=CaseStatusCategory.NEW.value))
    if principal.has_permission(perms.PROPOSALS_CREATE):
        # A proposal itself carries no tenant_id (PRO-01: the library is shared). Which
        # bank made it is `ProposalTenant`, a tenant table of its own under row-level
        # security (PRO-03) filed at the same time as the proposal; reading through it
        # rather than the proposer's current membership means a proposal counts here even
        # after its author has since left the bank.
        counts["proposals"] = _count(ProposalTenant.objects.filter(proposal__status=ProposalStatus.OPEN.value))
    counts["assignedToMe"] = _count(ChangeCase.objects.filter(owner_id=me).exclude(status__in=_FINISHED_CASES))
    # Row-level security keeps this to the session's bank; every member reads their own.
    counts["unreadNotifications"] = _count(Notification.objects.filter(user_id=me, read_at__isnull=True))
    if principal.has_permission(perms.CASES_SIGNOFF):
        counts["signoffs"] = _count(ChangeCase.objects.filter(status=CaseStatusCategory.SIGNOFF.value).exclude(signoff_requested_by_id=me))
    if principal.has_permission(perms.RISK_ACCEPT_APPROVE):
        # What `register.gaps.approve_risk_acceptance` would take: asked, not yet accepted,
        # and in a category the approval moves from.
        counts["riskAcceptances"] = _count(
            Gap.objects.filter(
                acceptance_requested_by__isnull=False,
                accepted_by__isnull=True,
                status__kind__in=(GapCategory.OPEN.value, GapCategory.REMEDIATING.value),
            ).exclude(acceptance_requested_by_id=me)
        )
    if principal.has_permission(perms.SECURITY_MANAGE):
        # Pending as `tenants.support_access.state_of` reads it, counted where grants are read.
        from apps.tenants import support_access

        counts["supportAccessRequests"] = _count(support_access.pending_requests(excluding_user_id=me))
        counts["tenantReachRequests"] = _count(
            TenantReachRequest.objects.filter(status=ApprovalStatus.PENDING.value).exclude(requested_by_id=me)
        )
    return counts


def _figures(principal: Principal, user_id: uuid.UUID) -> tuple[dict[str, int] | None, int]:
    """The "Decide now" counts (None outside a bank) and the person's live passkeys, in one
    read however many there are (a pinned query count proves it in `tests_me_counts.py`)."""
    counts = _count_subqueries(principal) if principal.tenant_id is not None else {}
    row = (
        User.objects.filter(pk=user_id)
        .annotate(passkeys=_count(WebAuthnCredential.objects.filter(user_id=user_id, retired_at__isnull=True)), **counts)
        .values("passkeys", *counts)
        .get()
    )
    figures = {name: row.get(name) or 0 for name in COUNT_NAMES} if principal.tenant_id is not None else None
    return figures, row["passkeys"] or 0


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
    """The session's own read already loaded the person and the bank, and the step-up; the
    passkeys and the "Decide now" counts are one read of figures. A bank's session never
    reads platform roles: platform staff are separate accounts (hardening H13)."""
    user = principal.user or User.objects.select_related("locale").get(pk=principal.subject_id)
    tenant = principal.tenant
    if tenant is None and principal.tenant_id is not None:
        tenant = Tenant.objects.select_related("default_language").filter(pk=principal.tenant_id).first()  # ordering: pk lookup, at most one row
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
    platform_roles = (
        []
        if principal.tenant_id is not None
        else [
            roles_logic.role_ref(assignment.role, order)
            for assignment in PlatformRoleAssignment.objects.filter(user=user, role__active=True).select_related("role").prefetch_related("role__labels")
        ]
    )
    counts, passkeys = _figures(principal, user.id)
    fresh_until = passkey_logic.step_up_valid_until(principal.step_up_at) if principal.step_up_at else None
    if fresh_until is not None and fresh_until <= timezone.now():
        fresh_until = None
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name, "locale": user.locale.key if user.locale else None},
        "tenant": _tenant_out(tenant),
        "counts": counts,
        "last_visit_at": last_visit_at,
        "notification_prefs": prefs,
        "head_of": head_of,
        "roles": roles,
        "permissions": sorted(principal.permissions),
        "platform_roles": platform_roles,
        "enrolment_pending": principal.kind is PrincipalKind.ENROLMENT or user.status != UserStatus.ACTIVE.value,
        "passkey_count": passkeys,
        "step_up_valid_until": fresh_until,
    }


def me_after_refresh(access_token: str) -> dict[str, Any] | None:
    """`/me` for the session a refresh just renewed, so a screen opening from a cold start
    makes one call, not two. None where `session_logic.resolve_refreshed` resolves nothing."""
    principal = session_logic.resolve_refreshed(access_token)
    return None if principal is None else me(principal)


def update_me(
    principal: Principal,
    *,
    name: str | None,
    locale: str | None,
    notification_prefs_patch: MembershipNotificationPrefsPatch | None,
) -> dict[str, Any]:
    """The caller's own name, language and notification switches, in one audit event with
    before and after: these are the person's own settings, not tenant content. A switch
    key the schema does not name is refused before anything is written. The person is the
    one the session loaded, so `me()` answers with what was just saved."""
    user = principal.user or User.objects.select_related("locale").get(pk=principal.subject_id)
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
