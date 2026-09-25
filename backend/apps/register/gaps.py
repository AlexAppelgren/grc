"""Gaps and risk acceptance (REG-03).

A gap is a fact about how the bank complies, never about whether a rule applies: it is
recorded on a register entry, optionally for one legal entity, and it stays readable whatever
the entry's applicability later becomes. Only recording one on an obligation that does not
apply is refused. Its status, severity, source and acceptance reason are rows of the bank's
own lists, stored and compared by key.

The status moves between the `open` and `remediating` categories and on to `closed` through
`PATCH`; the `risk_accepted` category is reached only through the acceptance, and a closed or
accepted gap goes back to `open` only through the reopen. Accepting a gap's risk keeps its
four eyes: a second person holding `risk.accept.approve`, with a fresh passkey step-up, who is
not the person who asked (`gap_four_eyes` backs the check below). Every write locks the gap's
row first, so two decisions at once land one.

A gap on a Statement of Applicability unit is `c8-units-paste-soa`'s and answers 501 until
it lands. Audit rows carry ids, keys and dates, never a title, note or plan a person typed
(R2_CROSS_CUTTING (m)).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.identity.models import Membership, UserStatus
from apps.library.reading import obligation_headings
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, Gap, TenantObligation, TenantObligationScope
from apps.register.schemas import RegisterGapBody, RegisterGapPatch, RegisterGapQuery, RegisterRiskAcceptanceBody
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.vocabulary import TenantListVocabulary, label_for
from apps.taxonomy.models import GapCategory, GapSource, GapStatus, RiskAcceptanceReason, RiskRating, Team
from apps.tenants.models import OrgUnit, OrgUnitKind

GAP_RECORDED = "register.gap_recorded"
GAP_AMENDED = "register.gap_amended"
RISK_ACCEPTANCE_REQUESTED = "register.gap_risk_acceptance_requested"
RISK_ACCEPTED = "register.gap_risk_accepted"
GAP_REOPENED = "register.gap_reopened"

# The categories `PATCH` moves a gap between. A gap in any other category moves only through
# its own route: accepted by the approval, and back to open by the reopen.
MOVABLE = {GapCategory.OPEN.value, GapCategory.REMEDIATING.value}
PATCH_TARGETS = MOVABLE | {GapCategory.CLOSED.value}
REOPENABLE = {GapCategory.CLOSED.value, GapCategory.RISK_ACCEPTED.value}
# The fields a person types. An audit row names which of them changed, never their text.
TYPED_FIELDS = ("title", "description", "remediation")

_RELATED = (
    "tenant_obligation",
    "severity",
    "source",
    "status",
    "owner",
    "owner_team",
    "identified_by",
    "acceptance_reason",
    "acceptance_requested_by",
    "accepted_by",
)
_LABELS = ("severity__labels", "source__labels", "status__labels", "owner_team__labels", "acceptance_reason__labels")


# ---------------------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------------------
def _gaps() -> QuerySet[Gap]:
    """Every gap with what its answer shows, in a fixed number of queries per page."""
    return Gap.objects.select_related(*_RELATED).prefetch_related(*_LABELS)


def _by_target_date(gaps: QuerySet[Gap]) -> QuerySet[Gap]:
    return gaps.order_by(F("target_date").asc(nulls_last=True), "id")


def _ref(row: TenantListVocabulary | None, order: list[str]) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"key": row.key, "kind": row.kind, "label": label_for(row, order)}


def _person(user: Any) -> dict[str, Any] | None:
    return None if user is None else {"id": user.id, "name": user.name}


def _out(gap: Gap, order: list[str]) -> dict[str, Any]:
    acceptance = None
    if gap.acceptance_requested_by_id is not None:
        acceptance = {
            "reason": _ref(gap.acceptance_reason, order),
            "note": gap.acceptance_note or None,
            "requested_by": _person(gap.acceptance_requested_by),
            "requested_at": gap.acceptance_requested_at,
            "approved_by": _person(gap.accepted_by),
            "approved_at": gap.accepted_at,
        }
    return {
        "id": gap.id,
        "obligation_id": gap.tenant_obligation.obligation_id,
        "org_unit_id": gap.org_unit_id,
        "unit_id": None,
        "title": gap.title,
        "description": gap.description or None,
        "severity": _ref(gap.severity, order),
        "source": _ref(gap.source, order),
        "status": _ref(gap.status, order),
        "owner": _person(gap.owner),
        "owner_team": _ref(gap.owner_team, order),
        "target_date": gap.target_date,
        "remediation": gap.remediation or None,
        "identified_at": gap.identified_at,
        "identified_by": _person(gap.identified_by),
        "risk_acceptance": acceptance,
        "version": gap.version,
    }


def _page(gaps: QuerySet[Gap], order: list[str], limit: int, offset: int) -> dict[str, Any]:
    rows = list(_by_target_date(gaps)[offset : offset + limit])
    return {"items": [_out(gap, order) for gap in rows], "total": gaps.count()}


def _answer(gap_id: uuid.UUID, order: list[str]) -> dict[str, Any]:
    return _out(_gaps().get(pk=gap_id), order)


def list_obligation_gaps(
    *, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int
) -> dict[str, Any]:
    """`GET /obligations/{obligationId}/gaps`: the bank's gaps on one obligation. An
    obligation nobody has worked on has no entry and so no gaps: an empty page."""
    if not obligation_headings([obligation_id], []):
        raise ValidationError("That obligation is not here.", code="not_found")
    return _page(_gaps().filter(tenant_obligation__obligation_id=obligation_id), order, limit, offset)


def list_gaps(*, tenant: Tenant, order: list[str], filters: RegisterGapQuery, limit: int, offset: int) -> dict[str, Any]:
    """`GET /gaps`: every gap of the bank, filtered with AND, by target date then id."""
    gaps = _gaps()
    if filters.status is not None:
        gaps = gaps.filter(status__key=filters.status)
    if filters.severity is not None:
        gaps = gaps.filter(severity__key=filters.severity)
    if filters.owner is not None:
        gaps = gaps.filter(owner_id=filters.owner)
    if filters.entity is not None:
        gaps = gaps.filter(org_unit_id=filters.entity)
    if filters.target_from is not None:
        gaps = gaps.filter(target_date__gte=filters.target_from)
    if filters.target_to is not None:
        gaps = gaps.filter(target_date__lte=filters.target_to)
    return _page(gaps, order, limit, offset)


# ---------------------------------------------------------------------------------------
# What a write names
# ---------------------------------------------------------------------------------------
def _row(model: type[TenantListVocabulary], key: str, list_name: str) -> Any:
    """An active row of one of the bank's lists by key, or 422 `unknown_key` naming the keys
    the list holds."""
    row = model._default_manager.filter(key=key, active=True).first()  # ordering: key is unique per bank, at most one row
    if row is None:
        keys = ", ".join(model._default_manager.filter(active=True).values_list("key", flat=True))
        raise ValidationError(f"{key!r} is not in the bank's {list_name} list. Use one of: {keys}.", code="unknown_key")
    return row


def _category_row(category: GapCategory) -> GapStatus:
    """The bank's system gap status of a category: one per category, relabelled but never
    retired, so a move the server makes always has its row."""
    return GapStatus.objects.get(kind=category.value, is_system=True)


def _member(user_id: uuid.UUID) -> uuid.UUID:
    active = Membership.objects.filter(user_id=user_id, deactivated_at__isnull=True, user__status=UserStatus.ACTIVE.value)
    if not active.exists():
        raise ValidationError("That person is not an active member of the bank.", code="unknown_member")
    return user_id


def _owner(owner_id: uuid.UUID | None, owner_team: str | None) -> dict[str, Any]:
    """The owner columns a write sets: a person or a team, never both. Empty when the body
    names neither."""
    if owner_id is not None and owner_team is not None:
        raise ValidationError("A gap is owned by a person or a team, not both.", code="validation_error")
    if owner_id is not None:
        return {"owner_id": _member(owner_id), "owner_team_id": None}
    if owner_team is not None:
        return {"owner_id": None, "owner_team_id": _row(Team, owner_team, "team").id}
    return {}


def _refuse_does_not_apply(applicability: str) -> None:
    if applicability == Applicability.DOES_NOT_APPLY.value:
        raise ProblemError(
            status=409,
            code="does_not_apply",
            detail="This obligation does not apply here, so it has no gap. Set it to apply first.",
        )


def _entity(entry: TenantObligation | None, org_unit_id: uuid.UUID) -> None:
    """The bank's own legal entity, whose answer on the obligation is not "does not apply"."""
    if not OrgUnit.objects.filter(pk=org_unit_id, kind=OrgUnitKind.LEGAL_ENTITY.value).exists():
        raise ValidationError("That legal entity is not here.", code="not_found")
    if entry is not None:
        scope = TenantObligationScope.objects.filter(
            tenant_obligation=entry, org_unit_id=org_unit_id, product__isnull=True
        ).first()  # ordering: unique per entry and entity, at most one row
        if scope is not None:
            _refuse_does_not_apply(scope.applicability)


def _locked(gap_id: uuid.UUID) -> Gap:
    """The gap's row, locked until the request commits, so two writes at once serialize."""
    gap = Gap.objects.select_for_update().filter(pk=gap_id).first()  # ordering: pk lookup, at most one row
    if gap is None:
        raise ValidationError("That gap is not here.", code="not_found")
    return gap


def _category(gap: Gap) -> str:
    return str(GapStatus.objects.values_list("kind", flat=True).get(pk=gap.status_id))


def _who(actor: Actor) -> uuid.UUID:
    """The person acting: every gap route takes a person's session and nothing else."""
    if actor.id is None:
        raise ValidationError("Only a person works on gaps.", code="forbidden")
    return actor.id


def _invalid(detail: str) -> ValidationError:
    return ValidationError(detail, code="invalid_transition")


def _facts(gap: Gap) -> dict[str, Any]:
    """What an audit row may say about a gap: ids, keys and dates."""
    values = Gap.objects.filter(pk=gap.pk).values(
        "severity__key", "source__key", "status__key", "owner_id", "owner_team__key", "target_date", "org_unit_id"
    )[0]
    return {
        "severity": values["severity__key"],
        "source": values["source__key"],
        "status": values["status__key"],
        "ownerId": str(values["owner_id"]) if values["owner_id"] else None,
        "ownerTeam": values["owner_team__key"],
        "targetDate": values["target_date"].isoformat() if values["target_date"] else None,
        "orgUnitId": str(values["org_unit_id"]) if values["org_unit_id"] else None,
    }


# ---------------------------------------------------------------------------------------
# Record and amend
# ---------------------------------------------------------------------------------------
def create_gap(
    *, tenant: Tenant, actor: Actor, order: list[str], obligation_id: uuid.UUID, body: RegisterGapBody
) -> dict[str, Any]:
    """`POST /obligations/{obligationId}/gaps`: record a gap in the open category, creating
    the register entry on the first write that needs it."""
    if body.unit_id is not None:
        raise ProblemError(status=501, code="not_built", detail="Recording a gap on a unit is not built yet.")
    existing = TenantObligation.objects.filter(obligation_id=obligation_id).first()  # ordering: unique per bank, at most one row
    if existing is not None:
        _refuse_does_not_apply(existing.applicability)
    if body.org_unit_id is not None:
        _entity(existing, body.org_unit_id)
    fields = {
        "severity_id": _row(RiskRating, body.severity, "risk_rating").id,
        "source_id": _row(GapSource, body.source, "gap_source").id,
        **_owner(body.owner_id, body.owner_team),
    }
    with transaction.atomic():
        entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=obligation_id, actor=actor)
        gap = Gap.objects.create(
            tenant_id=tenant.id,
            tenant_obligation=entry,
            org_unit_id=body.org_unit_id,
            title=body.title,
            description=body.description or "",
            status=_category_row(GapCategory.OPEN),
            identified_by_id=_who(actor),
            target_date=body.target_date,
            remediation=body.remediation or "",
            **fields,
        )
        record(
            action=GAP_RECORDED,
            actor=actor,
            subject_type="gap",
            subject_id=gap.id,
            subject_title=gap.title,
            summary="Gap recorded.",
            tenant_id=tenant.id,
            after={"obligationId": str(obligation_id), **_facts(gap)},
        )
    return _answer(gap.id, order)


def update_gap(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    gap_id: uuid.UUID,
    body: RegisterGapPatch,
    expected_version: int | None,
) -> dict[str, Any]:
    """`PATCH /gaps/{gapId}`: change the fields sent, or move the status between open and
    remediating and on to closed. A write without the current version is refused."""
    gap = _locked(gap_id)
    if expected_version != gap.version:
        raise ValidationError("Someone changed this gap since you read it. Reload it and try again.", code="stale_write")
    sent = body.model_dump(exclude_none=True)
    changes: dict[str, Any] = {name: sent[name] for name in (*TYPED_FIELDS, "target_date") if name in sent}
    if "severity" in sent:
        changes["severity_id"] = _row(RiskRating, sent["severity"], "risk_rating").id
    changes.update(_owner(sent.get("owner_id"), sent.get("owner_team")))
    if "status" in sent:
        target = _row(GapStatus, sent["status"], "gap_status")
        if _category(gap) not in MOVABLE or target.kind not in PATCH_TARGETS:
            raise _invalid("A gap moves between open and remediating and on to closed here; accept a risk or reopen a gap with its own action.")
        changes["status_id"] = target.id
        if target.kind == GapCategory.CLOSED.value:
            # A waiting acceptance is moot once the gap is closed; the audit keeps the request.
            changes.update(closed_by_id=_who(actor), closed_at=timezone.now(), **_no_acceptance())
    before = _facts(gap)
    for name, value in changes.items():
        setattr(gap, name, value)
    gap.version += 1
    gap.save()
    record(
        action=GAP_AMENDED,
        actor=actor,
        subject_type="gap",
        subject_id=gap.id,
        subject_title=gap.title,
        summary="Gap amended.",
        tenant_id=tenant.id,
        before=before,
        after={**_facts(gap), "edited": [name for name in TYPED_FIELDS if name in changes]},
    )
    return _answer(gap.id, order)


# ---------------------------------------------------------------------------------------
# Risk acceptance behind four eyes
# ---------------------------------------------------------------------------------------
def _no_acceptance() -> dict[str, Any]:
    return {
        "acceptance_reason_id": None,
        "acceptance_note": "",
        "acceptance_requested_by_id": None,
        "acceptance_requested_at": None,
        "accepted_by_id": None,
        "accepted_at": None,
    }


def request_risk_acceptance(
    *, tenant: Tenant, actor: Actor, order: list[str], gap_id: uuid.UUID, body: RegisterRiskAcceptanceBody
) -> dict[str, Any]:
    """`POST /gaps/{gapId}/accept-risk`: ask for the risk to be accepted. The status does not
    move; the gap reads "Waiting for approval" until a second person approves."""
    gap = _locked(gap_id)
    if _category(gap) not in MOVABLE:
        raise _invalid("Only an open or remediating gap can have its risk accepted.")
    if gap.acceptance_requested_by_id is not None:
        raise ValidationError("A risk acceptance is already waiting for approval on this gap.", code="request_pending")
    reason = _row(RiskAcceptanceReason, body.reason, "risk_acceptance_reason")
    gap.acceptance_reason = reason
    gap.acceptance_note = body.note or ""
    gap.acceptance_requested_by_id = _who(actor)
    gap.acceptance_requested_at = timezone.now()
    gap.version += 1
    gap.save()
    record(
        action=RISK_ACCEPTANCE_REQUESTED,
        actor=actor,
        subject_type="gap",
        subject_id=gap.id,
        subject_title=gap.title,
        summary="Risk acceptance requested.",
        tenant_id=tenant.id,
        after={"reason": reason.key, "requestedBy": str(actor.id)},
    )
    return _answer(gap.id, order)


def approve_risk_acceptance(
    *, tenant: Tenant, actor: Actor, order: list[str], gap_id: uuid.UUID, step_up_assertion_id: uuid.UUID
) -> dict[str, Any]:
    """`POST /gaps/{gapId}/accept-risk/approve`: the second person accepts the risk, which
    moves the gap to the risk-accepted category. The person who asked is refused before
    anything is written; `gap_four_eyes` refuses them again at the database."""
    gap = _locked(gap_id)
    if gap.acceptance_requested_by_id is None or gap.accepted_by_id is not None or _category(gap) not in MOVABLE:
        raise _invalid("No risk acceptance is waiting for approval on this gap.")
    approver = _who(actor)
    if gap.acceptance_requested_by_id == approver:
        raise ValidationError("You asked for this risk to be accepted, so someone else approves it.", code="four_eyes_violation")
    before = _facts(gap)
    gap.status = _category_row(GapCategory.RISK_ACCEPTED)
    gap.accepted_by_id = approver
    gap.accepted_at = timezone.now()
    gap.version += 1
    gap.save()
    record(
        action=RISK_ACCEPTED,
        actor=actor,
        subject_type="gap",
        subject_id=gap.id,
        subject_title=gap.title,
        summary="Risk accepted.",
        tenant_id=tenant.id,
        before=before,
        after={
            **_facts(gap),
            "reason": gap.acceptance_reason.key if gap.acceptance_reason else None,
            "requestedBy": str(gap.acceptance_requested_by_id),
            "approvedBy": str(approver),
        },
        step_up_assertion_id=step_up_assertion_id,
    )
    return _answer(gap.id, order)


def reopen_gap(*, tenant: Tenant, actor: Actor, order: list[str], gap_id: uuid.UUID) -> dict[str, Any]:
    """`POST /gaps/{gapId}/reopen`: a closed or risk-accepted gap goes back to open and its
    acceptance is cleared; the earlier acceptance stays in the audit log."""
    gap = _locked(gap_id)
    if _category(gap) not in REOPENABLE:
        raise _invalid("Only a closed or risk-accepted gap can be reopened.")
    before = _facts(gap)
    for name, value in {**_no_acceptance(), "closed_by_id": None, "closed_at": None}.items():
        setattr(gap, name, value)
    gap.status = _category_row(GapCategory.OPEN)
    gap.version += 1
    gap.save()
    record(
        action=GAP_REOPENED,
        actor=actor,
        subject_type="gap",
        subject_id=gap.id,
        subject_title=gap.title,
        summary="Gap reopened.",
        tenant_id=tenant.id,
        before=before,
        after=_facts(gap),
    )
    return _answer(gap.id, order)
