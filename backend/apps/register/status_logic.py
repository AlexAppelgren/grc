"""Compliance status on the register entry and per legal entity (REG-02, TEN-03, D-42).

A read never writes: an obligation nobody has worked on reads as the defaults at version 0,
and an entity row appears with the first write that needs it. A write takes `If-Match`, goes
through `ensure_register_entry()` and `record()`, and never touches applicability, which is
its own route (D-75). "Applies" and "we comply" stay two facts, but a status other than the
`not_assessed` category needs "applies" first: the database cannot say so once the status
is a list row (INPUT_DELTAS, c8-register-models), so this module does. Every status change
leaves one assessment row, so the history has the first write.

The obligation's pill is the worst of the entities it applies to, ranked by the fixed
category in `worst_of()`, never by the label or the bank's editable ordinal.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.identity.models import Membership
from apps.library.reading import obligation_headings
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, ComplianceAssessment, TenantObligation, TenantObligationScope
from apps.register.schemas import Applicability as ApplicabilityAnswer
from apps.register.schemas import (
    RegisterEntityPatch,
    RegisterEntityStatus,
    RegisterEntry,
    RegisterPatch,
    RegisterPersonRef,
    RegisterStatusFields,
    RegisterVocabRef,
)
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy.models import (
    ComplianceCategory,
    ComplianceStatus,
    ComplianceStatusLabel,
    RiskRating,
    RiskRatingLabel,
    Team,
    TeamLabel,
)
from apps.taxonomy.reading import Labels, label_of
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.tenants.models import OrgUnit, OrgUnitKind

ENTRY_UPDATED = "register.status_updated"
ENTITY_UPDATED = "register.entity_status_updated"

# Worst first. The rank is the category's, fixed in code, because the bank may relabel and
# reorder its own rows: not assessed ranks below partly, since nobody has shown compliance.
_WORST_FIRST = (ComplianceCategory.GAP, ComplianceCategory.PARTLY, ComplianceCategory.NOT_ASSESSED, ComplianceCategory.COMPLIANT)
_RANK = {category.value: index for index, category in enumerate(_WORST_FIRST)}

# The model's kind in the contract's words (INPUT_DELTAS, c8-register-models).
_APPLICABILITY_OUT: dict[str, ApplicabilityAnswer] = {
    Applicability.APPLIES.value: "applies",
    Applicability.DOES_NOT_APPLY.value: "not_applicable",
    Applicability.NOT_ASSESSED.value: "under_assessment",
}

_ROW_RELATED = ("compliance_status", "risk_rating", "owner_team", "applicability_decided_by")
_ENTRY_RELATED = (*_ROW_RELATED, "first_line_owner", "compliance_contact")
# The scope row's person column, named from the model: the bare word is also a system role's
# key, which no logic module spells out (ID-S18).
_SCOPE_OWNER = TenantObligationScope.owner.field.name
_SCOPE_RELATED = (*_ROW_RELATED, _SCOPE_OWNER, "org_unit")
# The free-text fields a write may change. Their words never reach the audit row (R2 rule m);
# the row names which of them changed.
_TEXT_FIELDS = ("status_note", "process", "system", "evidence_location")
_LIST_FIELDS = ("compliance_status", "risk_rating", "owner_team")


def worst_of(statuses: Iterable[ComplianceStatus]) -> ComplianceStatus | None:
    """The worst of these statuses by category; the first of equals. None for none."""
    ranked = list(statuses)
    return min(ranked, key=lambda status: _RANK[status.kind or ""]) if ranked else None


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def read_register(*, tenant: Tenant, order: list[str], obligation_id: uuid.UUID) -> RegisterEntry:
    """`GET /obligations/{obligationId}/register`: a fixed handful of queries however many
    entities the obligation has, and not one write."""
    _heading(obligation_id)
    entry = TenantObligation.objects.select_related(*_ENTRY_RELATED).filter(obligation_id=obligation_id).first()  # ordering: unique per bank, at most one row
    if entry is None:
        return _defaults(obligation_id, order)
    scopes = list(
        TenantObligationScope.objects.select_related(*_SCOPE_RELATED)
        .filter(tenant_obligation=entry, product__isnull=True)
        .order_by("org_unit__name", "id")
    )
    refs = _Refs([entry, *scopes], order)
    applying = [scope.compliance_status for scope in scopes if scope.applicability == Applicability.APPLIES.value]
    shown = worst_of(applying) or entry.compliance_status
    return RegisterEntry(
        obligation_id=obligation_id,
        **_decision(entry),
        compliance_status=refs.of(shown),
        status_note=entry.status_note or None,
        risk_rating=refs.maybe(entry.risk_rating),
        first_line_owner=_person(entry.first_line_owner),
        compliance_contact=_person(entry.compliance_contact),
        owner_team=refs.maybe(entry.owner_team),
        process=entry.process or None,
        system=entry.system or None,
        evidence_location=entry.evidence_location or None,
        next_review_date=entry.next_review_date,
        entities=[_entity(scope, refs) for scope in scopes],
        version=entry.version,
        updated_at=entry.updated_at,
    )


def _defaults(obligation_id: uuid.UUID, order: list[str]) -> RegisterEntry:
    status = ComplianceStatus.objects.get(is_default=True, active=True)
    return RegisterEntry(
        obligation_id=obligation_id,
        applicability=_APPLICABILITY_OUT[Applicability.NOT_ASSESSED.value],
        applicability_reason=None,
        applicability_decided_at=None,
        applicability_decided_by=None,
        compliance_status=_Refs([], order, [status]).of(status),
        status_note=None,
        risk_rating=None,
        first_line_owner=None,
        compliance_contact=None,
        owner_team=None,
        process=None,
        system=None,
        evidence_location=None,
        next_review_date=None,
        entities=[],
        version=0,
        updated_at=None,
    )


def _entity(scope: TenantObligationScope, refs: _Refs) -> RegisterEntityStatus:
    return RegisterEntityStatus(
        org_unit_id=scope.org_unit_id,
        org_unit_name=scope.org_unit.name,
        **_decision(scope),
        compliance_status=refs.of(scope.compliance_status),
        status_note=scope.status_note or None,
        risk_rating=refs.maybe(scope.risk_rating),
        owner=_person(scope.owner),
        owner_team=refs.maybe(scope.owner_team),
        process=scope.process or None,
        system=scope.system or None,
        evidence_location=scope.evidence_location or None,
        next_review_date=scope.next_review_date,
        version=scope.version,
    )


def _decision(row: TenantObligation | TenantObligationScope) -> dict[str, Any]:
    return {
        "applicability": _APPLICABILITY_OUT[row.applicability],
        "applicability_reason": row.applicability_reason or None,
        "applicability_decided_at": row.applicability_decided_at,
        "applicability_decided_by": _person(row.applicability_decided_by),
    }


def _person(user: Any) -> RegisterPersonRef | None:
    return None if user is None else RegisterPersonRef(id=user.id, name=user.name)


_LABEL_MODELS: dict[type[Any], type[Any]] = {
    ComplianceStatus: ComplianceStatusLabel,
    RiskRating: RiskRatingLabel,
    Team: TeamLabel,
}


class _Refs:
    """The `{key, kind, label}` of every status, risk and team the rows name, labelled in one
    query per list."""

    def __init__(
        self, rows: Iterable[TenantObligation | TenantObligationScope], order: list[str], extra: Iterable[Any] = ()
    ) -> None:
        self.order = order
        named: dict[type[Any], dict[uuid.UUID, Any]] = {model: {} for model in _LABEL_MODELS}
        for value in (*extra, *(getattr(row, field) for row in rows for field in ("compliance_status", "risk_rating", "owner_team"))):
            if value is not None:
                named[type(value)][value.id] = value
        self.labels = {model: Labels.for_rows(_LABEL_MODELS[model], list(values.values())) for model, values in named.items()}

    def maybe(self, row: Any) -> RegisterVocabRef | None:
        return None if row is None else self.of(row)

    def of(self, row: Any) -> RegisterVocabRef:
        labels = self.labels[type(row)]
        label = label_of(labels.texts(row.id), self.order, original=labels.original(row.id), key=row.key)
        return RegisterVocabRef(key=row.key, kind=row.kind, label=label)


# ---------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------
def update_register(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    obligation_id: uuid.UUID,
    body: RegisterPatch,
    expected_version: int | None,
) -> RegisterEntry:
    """`PATCH /obligations/{obligationId}/register`."""
    heading = _heading(obligation_id)
    expected = _required(expected_version)
    entry = _locked(TenantObligation.objects.filter(obligation_id=obligation_id))
    _check_version(expected, entry.version if entry is not None else 0)
    changes = _resolve(
        body, people={"first_line_owner": body.first_line_owner_id, "compliance_contact": body.compliance_contact_id}
    )
    _refuse_status_unless_applies(changes, entry.applicability if entry is not None else Applicability.NOT_ASSESSED.value)
    if entry is None:
        created = ensure_register_entry(tenant_id=tenant.id, obligation_id=obligation_id, actor=actor)
        entry = _locked(TenantObligation.objects.filter(pk=created.pk))
        assert entry is not None  # created in this transaction, so it is there
        # A first write that met another on the unique key: that one's changes stand.
        _check_version(1, entry.version)
    before = _snapshot(entry, ("first_line_owner_id", "compliance_contact_id"))
    changed = _apply(entry, changes)
    entry.version += 1
    entry.save()
    _assess(entry, None, changed, body.rationale, actor)
    record(
        action=ENTRY_UPDATED,
        actor=actor,
        subject_type="tenant_obligation",
        subject_id=entry.id,
        subject_title=heading,
        summary="Compliance status and details updated.",
        tenant_id=tenant.id,
        before=before,
        after={**_snapshot(entry, ("first_line_owner_id", "compliance_contact_id")), "changed": changed},
    )
    return read_register(tenant=tenant, order=order, obligation_id=obligation_id)


def update_entity_status(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    obligation_id: uuid.UUID,
    org_unit_id: uuid.UUID,
    body: RegisterEntityPatch,
    expected_version: int | None,
) -> RegisterEntityStatus:
    """`PATCH /obligations/{obligationId}/register/entities/{orgUnitId}`. The entity is read
    under row-level security first, so another bank's entity is `not_found` before anything
    else is said about it."""
    entity = OrgUnit.objects.filter(pk=org_unit_id, kind=OrgUnitKind.LEGAL_ENTITY.value, active=True).first()  # ordering: pk lookup, at most one row
    if entity is None:
        raise ValidationError("That legal entity is not here.", code="not_found")
    heading = f"{_heading(obligation_id)}, {entity.name}"
    expected = _required(expected_version)
    # The entry's lock serializes every write under the obligation, a first entity row included.
    entry = _locked(TenantObligation.objects.filter(obligation_id=obligation_id))
    scope = None if entry is None else _locked(TenantObligationScope.objects.filter(tenant_obligation=entry, org_unit=entity, product__isnull=True))
    _check_version(expected, scope.version if scope is not None else 0)
    changes = _resolve(body, people={_SCOPE_OWNER: body.owner_id})
    _refuse_status_unless_applies(changes, scope.applicability if scope is not None else Applicability.NOT_ASSESSED.value)
    if entry is None:
        entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=obligation_id, actor=actor)
    if scope is None:
        scope = TenantObligationScope(
            tenant_id=tenant.id,
            tenant_obligation=entry,
            org_unit=entity,
            compliance_status=ComplianceStatus.objects.get(is_default=True, active=True),
            version=0,
        )
    before = _snapshot(scope, ("owner_id",)) if scope.version else {}
    # A person or a team owns an entity's row, never both (`tenant_obligation_scope_one_owner_kind`).
    if "owner_id" in changes:
        changes["owner_team"] = None
    elif "owner_team" in changes:
        changes["owner_id"] = None
    changed = _apply(scope, changes)
    scope.version += 1
    try:
        with transaction.atomic():
            scope.save()
    except IntegrityError:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write") from None
    _assess(entry, scope, changed, body.rationale, actor)
    record(
        action=ENTITY_UPDATED,
        actor=actor,
        subject_type="tenant_obligation_scope",
        subject_id=scope.id,
        subject_title=heading,
        summary="Compliance status and details updated for one legal entity.",
        tenant_id=tenant.id,
        before=before,
        after={**_snapshot(scope, ("owner_id",)), "orgUnitId": str(entity.id), "changed": changed},
    )
    written = TenantObligationScope.objects.select_related(*_SCOPE_RELATED).get(pk=scope.pk)
    return _entity(written, _Refs([written], order))


def _heading(obligation_id: uuid.UUID) -> str:
    heading = obligation_headings([obligation_id], []).get(obligation_id)
    if heading is None:
        raise ValidationError("That obligation is not here.", code="not_found")
    return f"{heading.instrument_short_name}, {heading.reference_label}"


def _required(expected_version: int | None) -> int:
    if expected_version is None:
        raise ValidationError("Send If-Match with the version you last read.", code="validation_error")
    return expected_version


def _check_version(expected: int, current: int) -> None:
    if expected != current:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")


def _locked(queryset: Any) -> Any:
    return queryset.select_for_update().first()  # ordering: unique key, at most one row


def _resolve(body: RegisterStatusFields, *, people: dict[str, uuid.UUID | None]) -> dict[str, Any]:
    """The fields the body sends, by model field: its keys as the bank's active list rows and
    its people as active members' ids, refused with `unknown_key` naming the valid keys, or
    with `unknown_member`."""
    fields: dict[str, Any] = {name: getattr(body, name) for name in (*_TEXT_FIELDS, "next_review_date") if getattr(body, name) is not None}
    for field, model in zip(_LIST_FIELDS, _LABEL_MODELS, strict=True):
        key = getattr(body, field)
        if key is None:
            continue
        rows = {row.key: row for row in model.objects.filter(active=True)}
        if key not in rows:
            raise VocabularyProblem(
                f"{key!r} is not one of this bank's values. Valid keys: {', '.join(sorted(rows))}.",
                code="unknown_key",
                extra={"validKeys": sorted(rows)},
            )
        fields[field] = rows[key]
    wanted = {name: user_id for name, user_id in people.items() if user_id is not None}
    members = set(Membership.objects.filter(user_id__in=wanted.values(), deactivated_at__isnull=True).values_list("user_id", flat=True))
    for name, user_id in wanted.items():
        if user_id not in members:
            raise ValidationError("That person is not an active member of this bank.", code="unknown_member")
        fields[f"{name}_id"] = user_id
    return fields


def _refuse_status_unless_applies(changes: dict[str, Any], applicability: str) -> None:
    status = changes.get("compliance_status")
    if status is not None and status.kind != ComplianceCategory.NOT_ASSESSED.value and applicability != Applicability.APPLIES.value:
        raise ValidationError(
            "Set the obligation to Applies before recording how you comply.", code="invalid_transition"
        )


def _apply(row: TenantObligation | TenantObligationScope, changes: dict[str, Any]) -> list[str]:
    """Set the resolved fields; the names of those whose value moved, as the API spells them.
    A list field is set as its row and a person as an id, so each compares by its key."""
    changed = []
    for name, value in changes.items():
        current = getattr(row, f"{name}_id") if name in _LIST_FIELDS else getattr(row, name)
        if current != (value.pk if name in _LIST_FIELDS and value is not None else value):
            changed.append(_camel(name))
        setattr(row, name, value)
    return sorted(changed)


def _assess(
    entry: TenantObligation, scope: TenantObligationScope | None, changed: list[str], rationale: str | None, actor: Actor
) -> None:
    """One assessment row per status change (REG-04), on the entity's row where there is one."""
    if "complianceStatus" not in changed:
        return
    assert actor.id is not None  # every register write is a person's session
    row = scope if scope is not None else entry
    ComplianceAssessment.objects.create(
        tenant_id=entry.tenant_id,
        tenant_obligation=entry,
        scope=scope,
        status_id=row.compliance_status_id,
        risk_rating_id=row.risk_rating_id,
        rationale=rationale or "",
        next_review_date=row.next_review_date,
        assessed_by_id=actor.id,
    )


def _snapshot(row: TenantObligation | TenantObligationScope, people: tuple[str, ...]) -> dict[str, Any]:
    """Keys, ids and dates only: a status note, a process or a system name is tenant text and
    never enters the audit row (R2 rule m)."""
    snapshot: dict[str, Any] = {
        "complianceStatus": row.compliance_status.key,
        "riskRating": row.risk_rating.key if row.risk_rating is not None else None,
        "ownerTeam": row.owner_team.key if row.owner_team is not None else None,
        "nextReviewDate": row.next_review_date.isoformat() if row.next_review_date else None,
        "version": row.version,
    }
    for name in people:
        value = getattr(row, name)
        snapshot[_camel(name)] = str(value) if value else None
    return snapshot


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)
