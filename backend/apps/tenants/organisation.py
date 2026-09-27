"""The bank's organisation (TEN-02, D-21, D-43, ADM-01): its groups, legal entities and
departments with a head, and the licences and certificates a legal entity holds. Every row
is the bank's own, written under `vocab.manage`, audited with the fields it changed before
and after, and deactivated or withdrawn, never deleted.

A legal entity's term is a term of the library's `legal_entity` dimension; a licence's type
and services, and a product's scope (apps/tenants/products.py), are terms of the dimensions
an obligation's scope is written with (apps/tenants/terms.py).

Free text a person typed (a scope note or statement) never enters the audit row: its before
and after carry ids, keys, names and dates, and `rewritten` names the text fields that
changed (R2_CROSS_CUTTING.md (m)).
"""

from __future__ import annotations

import re
import uuid
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from apps.identity.models import Membership, User
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.schemas import PersonRef
from apps.taxonomy.terms_logic import term_by_ref
from apps.tenants.models import Licence, LicenceServiceTerm, OrgUnit, OrgUnitKind
from apps.tenants.terms import Term, scope_terms, term_refs
from apps.tenants.schemas import (
    OrgUnitKindValue,
    TenantLicence,
    TenantLicenceBody,
    TenantLicencePage,
    TenantLicencePatch,
    TenantOrgUnit,
    TenantOrgUnitBody,
    TenantOrgUnitPage,
    TenantOrgUnitPatch,
)

ENTITY_DIMENSION = "legal_entity"
LEI = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
COUNTRY = re.compile(r"[A-Z]{2}")
ENTITY_ONLY = ("org_number", "lei", "country_code", "entity_term")
STALE = "Someone changed this first. Reload and try again."


# ---------------------------------------------------------------------------------------
# What the organisation and product writes share.
# ---------------------------------------------------------------------------------------
def _not_found() -> ProblemError:
    return ProblemError(status=404, code="not_found", detail="Not found.")


def locked(model: type[Any], tenant: Tenant, pk: uuid.UUID, expected_version: int | None) -> Any:
    """The row, locked for the write, in the caller's bank, or 404; 409 `stale_write` when
    `If-Match` named another version (playbook 4.3)."""
    row = model._default_manager.select_for_update().filter(tenant=tenant, pk=pk).order_by("pk").first()  # ordering: pk lookup, at most one row
    if row is None:
        raise _not_found()
    if expected_version is not None and expected_version != row.version:
        raise ValidationError(STALE, code="stale_write")
    return row


def active_member(tenant: Tenant, user_id: uuid.UUID) -> User:
    """An active member of the caller's bank, or 422 `unknown_member`."""
    membership = (
        Membership.objects.select_related("user")
        .filter(tenant=tenant, user_id=user_id, deactivated_at__isnull=True)
        .first()
    )  # ordering: unique (tenant, user), at most one row
    if membership is None:
        raise ValidationError("That person is not an active member of your organisation.", code="unknown_member")
    return membership.user


def person(user: User | None) -> PersonRef | None:
    return None if user is None else PersonRef(id=user.id, name=user.name)


def changed(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The fields whose value moved, before and after."""
    keys = [key for key in after if before.get(key) != after[key]]
    return {key: before.get(key) for key in keys}, {key: after[key] for key in keys}


def iso(value: Any) -> str | None:
    return None if value is None else value.isoformat()


def ref(value: Any) -> str | None:
    return None if value is None else str(value)


# ---------------------------------------------------------------------------------------
# Units.
# ---------------------------------------------------------------------------------------
def org_unit_of(tenant: Tenant, org_unit_id: uuid.UUID) -> OrgUnit:
    """The unit, in the caller's bank and under its row-level security, or 404."""
    unit = OrgUnit.objects.filter(tenant=tenant, pk=org_unit_id).first()  # ordering: pk lookup, at most one row
    if unit is None:
        raise _not_found()
    return unit


def _unit_snapshot(unit: OrgUnit) -> dict[str, Any]:
    return {
        "kind": unit.kind,
        "name": unit.name,
        "parentId": ref(unit.parent_id),
        "orgNumber": unit.org_number,
        "lei": unit.lei,
        "countryCode": unit.country_code,
        "entityTerm": unit.entity_term.key if unit.entity_term is not None else None,
        "headUserId": ref(unit.head_user_id),
        "active": unit.active,
    }


def _units_out(units: list[OrgUnit], order: list[str]) -> list[TenantOrgUnit]:
    refs = term_refs([unit.entity_term for unit in units if unit.entity_term is not None], order)
    return [
        TenantOrgUnit(
            id=unit.id,
            kind=cast(OrgUnitKindValue, unit.kind),
            name=unit.name,
            parent_id=unit.parent_id,
            org_number=unit.org_number,
            lei=unit.lei,
            country_code=unit.country_code,
            entity_term=refs.get(unit.entity_term_id) if unit.entity_term_id else None,
            head=person(unit.head_user),
            active=unit.active,
            version=unit.version,
        )
        for unit in units
    ]


def _unit_out(tenant: Tenant, unit_id: uuid.UUID, order: list[str]) -> TenantOrgUnit:
    unit = OrgUnit.objects.select_related("entity_term", "head_user").get(tenant=tenant, pk=unit_id)
    return _units_out([unit], order)[0]


def _parent(tenant: Tenant, parent_id: uuid.UUID, unit: OrgUnit | None) -> OrgUnit:
    """The bank's own unit to sit under, or 404; 422 when it is `unit` or sits under it."""
    parent = org_unit_of(tenant, parent_id)
    if unit is not None:
        # Walk up from the new parent: meeting the unit itself would close a loop.
        ancestor: OrgUnit | None = parent
        while ancestor is not None:
            if ancestor.pk == unit.pk:
                raise ValidationError("A unit cannot sit under itself or under a unit below it.", code="validation_error")
            ancestor = ancestor.parent
    return parent


def _apply_unit_fields(tenant: Tenant, unit: OrgUnit, fields: dict[str, Any]) -> None:
    """Set the fields a create or change sends, each validated against the bank's rows."""
    if unit.kind != OrgUnitKind.LEGAL_ENTITY.value and any(fields.get(name) for name in ENTITY_ONLY):
        raise ValidationError(
            "Only a legal entity carries a registration number, an LEI, a country or a legal-entity term.",
            code="validation_error",
        )
    if fields.get("lei") and not LEI.fullmatch(fields["lei"].upper()):
        raise ValidationError("An LEI is 20 letters and digits, ending in two digits.", code="validation_error")
    if fields.get("country_code") and not COUNTRY.fullmatch(fields["country_code"].upper()):
        raise ValidationError("A country is its two-letter ISO 3166 code, such as SE.", code="validation_error")
    if fields.get("name") is not None:
        unit.name = fields["name"]
    for name in ("org_number", "lei", "country_code"):
        if fields.get(name) is not None:
            value = fields[name].strip()
            setattr(unit, name, value.upper() if name != "org_number" else value)
    if fields.get("entity_term") is not None:
        unit.entity_term = term_by_ref(ENTITY_DIMENSION, fields["entity_term"])
    if fields.get("parent_id") is not None:
        unit.parent = _parent(tenant, fields["parent_id"], None if unit._state.adding else unit)
    if fields.get("head_user_id") is not None:
        unit.head_user = active_member(tenant, fields["head_user_id"])
    if fields.get("active") is not None:
        unit.active = fields["active"]


def list_org_units(*, tenant: Tenant, order: list[str], limit: int, offset: int) -> TenantOrgUnitPage:
    """`GET /tenant/org-units`: a page of the bank's units by name, deactivated ones included."""
    queryset = OrgUnit.objects.filter(tenant=tenant)
    units = list(queryset.select_related("entity_term", "head_user").order_by("name", "id")[offset : offset + limit])
    return TenantOrgUnitPage(items=_units_out(units, order), total=queryset.count())


def create_org_unit(*, tenant: Tenant, actor: Actor, order: list[str], body: TenantOrgUnitBody) -> TenantOrgUnit:
    """`POST /tenant/org-units`."""
    unit = OrgUnit(tenant=tenant, kind=body.kind)
    _apply_unit_fields(tenant, unit, body.model_dump())
    unit.save()
    record(
        action="org_unit.created",
        actor=actor,
        subject_type="org_unit",
        subject_id=unit.id,
        subject_title=unit.name,
        summary="Added a unit to the organisation.",
        tenant_id=tenant.id,
        after=_unit_snapshot(unit),
    )
    return _unit_out(tenant, unit.id, order)


def update_org_unit(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    org_unit_id: uuid.UUID,
    body: TenantOrgUnitPatch,
    expected_version: int | None,
) -> TenantOrgUnit:
    """`PATCH /tenant/org-units/{orgUnitId}`: the kind never changes; `active: false`
    deactivates, and nothing deletes."""
    unit: OrgUnit = locked(OrgUnit, tenant, org_unit_id, expected_version)
    before = _unit_snapshot(unit)
    _apply_unit_fields(tenant, unit, body.model_dump())
    before_changed, after_changed = changed(before, _unit_snapshot(unit))
    unit.version += 1
    unit.save()
    record(
        action="org_unit.updated",
        actor=actor,
        subject_type="org_unit",
        subject_id=unit.id,
        subject_title=unit.name,
        summary="Changed a unit of the organisation.",
        tenant_id=tenant.id,
        before=before_changed,
        after=after_changed,
    )
    return _unit_out(tenant, unit.id, order)


# ---------------------------------------------------------------------------------------
# Licences and certificates (D-43, ADR 0037).
# ---------------------------------------------------------------------------------------
LICENCE_DATES = ("granted_on", "withdrawn_on", "issued_on", "valid_until", "next_audit_on")
LICENCE_STRINGS = ("reference", "issuer", "number")
LICENCE_TEXTS = {"scope_note": "scopeNote", "scope_statement": "scopeStatement"}


def licence_of(tenant: Tenant, licence_id: uuid.UUID) -> Licence:
    """The licence, in the caller's bank and under its row-level security, or 404."""
    licence = Licence.objects.filter(tenant=tenant, pk=licence_id).first()  # ordering: pk lookup, at most one row
    if licence is None:
        raise _not_found()
    return licence


def _licence_snapshot(licence: Licence, services: list[Term]) -> dict[str, Any]:
    return {
        "orgUnitId": ref(licence.org_unit_id),
        "licenceType": licence.licence_type.key,
        "reference": licence.reference,
        "issuer": licence.issuer,
        "number": licence.number,
        "grantedOn": iso(licence.granted_on),
        "withdrawnOn": iso(licence.withdrawn_on),
        "issuedOn": iso(licence.issued_on),
        "validUntil": iso(licence.valid_until),
        "nextAuditOn": iso(licence.next_audit_on),
        "ownerUserId": ref(licence.owner_user_id),
        "serviceTerms": [term.key for term in services],
    }


def _licences_out(licences: list[Licence], order: list[str]) -> list[TenantLicence]:
    terms = {licence.licence_type_id: licence.licence_type for licence in licences}
    for licence in licences:
        terms.update({row.term_id: row.term for row in licence.service_terms.all()})
    refs = term_refs(list(terms.values()), order)
    return [
        TenantLicence(
            id=licence.id,
            org_unit_id=licence.org_unit_id,
            licence_type=refs[licence.licence_type_id],
            reference=licence.reference,
            granted_on=licence.granted_on,
            withdrawn_on=licence.withdrawn_on,
            scope_note=licence.scope_note,
            issuer=licence.issuer,
            number=licence.number,
            scope_statement=licence.scope_statement,
            issued_on=licence.issued_on,
            valid_until=licence.valid_until,
            next_audit_on=licence.next_audit_on,
            owner=person(licence.owner_user),
            service_terms=[refs[row.term_id] for row in licence.service_terms.all()],
            version=licence.version,
        )
        for licence in licences
    ]


def _licences(tenant: Tenant) -> Any:
    services = LicenceServiceTerm.objects.select_related("term").order_by("term__sort_order", "term__key")
    return Licence.objects.filter(tenant=tenant).select_related("licence_type", "owner_user").prefetch_related(
        Prefetch("service_terms", queryset=services)
    )


def _licence_out(tenant: Tenant, licence_id: uuid.UUID, order: list[str]) -> TenantLicence:
    return _licences_out([_licences(tenant).get(pk=licence_id)], order)[0]


def _apply_licence_fields(tenant: Tenant, licence: Licence, fields: dict[str, Any]) -> list[str]:
    """Set the fields a create or change sends; the text fields that changed, by name."""
    if fields.get("licence_type") is not None:
        [licence.licence_type] = scope_terms([fields["licence_type"]])
    for name in (*LICENCE_DATES, *LICENCE_STRINGS):
        if fields.get(name) is not None:
            setattr(licence, name, fields[name])
    rewritten = []
    for name, label in LICENCE_TEXTS.items():
        if fields.get(name) is not None and fields[name] != getattr(licence, name):
            setattr(licence, name, fields[name])
            rewritten.append(label)
    if fields.get("owner_user_id") is not None:
        licence.owner_user = active_member(tenant, fields["owner_user_id"])
    for start, end in (("granted_on", "withdrawn_on"), ("issued_on", "valid_until")):
        if getattr(licence, start) and getattr(licence, end) and getattr(licence, end) < getattr(licence, start):
            raise ValidationError("An end date cannot come before the date it starts from.", code="validation_error")
    return rewritten


def _set_services(tenant: Tenant, licence: Licence, terms: list[Term]) -> None:
    LicenceServiceTerm.objects.filter(tenant=tenant, licence=licence).exclude(term__in=terms).delete()
    held = set(LicenceServiceTerm.objects.filter(tenant=tenant, licence=licence).values_list("term_id", flat=True))
    LicenceServiceTerm.objects.bulk_create(
        [LicenceServiceTerm(tenant=tenant, licence=licence, term=term) for term in terms if term.id not in held]
    )


def _services_of(licence: Licence) -> list[Term]:
    return [row.term for row in LicenceServiceTerm.objects.filter(licence=licence).select_related("term").order_by("term__key")]


def list_licences(*, tenant: Tenant, order: list[str], org_unit_id: uuid.UUID, limit: int, offset: int) -> TenantLicencePage:
    """`GET /tenant/org-units/{orgUnitId}/licences`: withdrawn ones included."""
    unit = org_unit_of(tenant, org_unit_id)
    queryset = _licences(tenant).filter(org_unit=unit)
    licences = list(queryset.order_by("granted_on", "id")[offset : offset + limit])
    return TenantLicencePage(items=_licences_out(licences, order), total=queryset.count())


def create_licence(
    *, tenant: Tenant, actor: Actor, order: list[str], org_unit_id: uuid.UUID, body: TenantLicenceBody
) -> TenantLicence:
    """`POST /tenant/org-units/{orgUnitId}/licences`: nothing about the bank's scope, its
    obligations or their applicability changes."""
    unit = org_unit_of(tenant, org_unit_id)
    if unit.kind != OrgUnitKind.LEGAL_ENTITY.value:
        raise ValidationError("Only a legal entity holds licences and certificates.", code="validation_error")
    licence = Licence(tenant=tenant, org_unit=unit)
    rewritten = _apply_licence_fields(tenant, licence, body.model_dump())
    services = scope_terms(body.service_terms)
    licence.save()
    _set_services(tenant, licence, services)
    record(
        action="licence.created",
        actor=actor,
        subject_type="licence",
        subject_id=licence.id,
        subject_title=licence.licence_type.key,
        summary="Recorded a licence or certificate.",
        tenant_id=tenant.id,
        after={**_licence_snapshot(licence, _services_of(licence)), "rewritten": rewritten},
    )
    return _licence_out(tenant, licence.id, order)


def update_licence(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    licence_id: uuid.UUID,
    body: TenantLicencePatch,
    expected_version: int | None,
) -> TenantLicence:
    """`PATCH /tenant/licences/{licenceId}`: withdrawn with `withdrawnOn`, never deleted."""
    licence: Licence = locked(Licence, tenant, licence_id, expected_version)
    before = _licence_snapshot(licence, _services_of(licence))
    rewritten = _apply_licence_fields(tenant, licence, body.model_dump())
    if body.service_terms is not None:
        _set_services(tenant, licence, scope_terms(body.service_terms))
    before_changed, after_changed = changed(before, _licence_snapshot(licence, _services_of(licence)))
    licence.version += 1
    licence.save()
    record(
        action="licence.updated",
        actor=actor,
        subject_type="licence",
        subject_id=licence.id,
        subject_title=licence.licence_type.key,
        summary="Changed a licence or certificate.",
        tenant_id=tenant.id,
        before=before_changed,
        after={**after_changed, "rewritten": rewritten},
    )
    return _licence_out(tenant, licence.id, order)
