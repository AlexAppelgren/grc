"""Models of the tenants app. Chunk 1 adds `SupportAccess` (ID-05, TEN-06): every time
platform staff act inside a tenant, a row the tenant can see. The full grant workflow
(time-boxed reads) is chunk 8; chunk 1 writes one-shot rows for the last-admin recovery
(ID-S13).

Chunk 8 adds the bank's organisation (TEN-02, REG-05, tenants 0002): org units with a head,
the licences and certificates a legal entity holds (D-43), products scoped in the terms
obligations use, and the internal items a register entry links to. Chunk 11's
`SecurityPolicy` (ID-07, ID-08) sits in the same migration to keep the tenants migrations in
order. Every table is under forced row-level security, and every reference to another tenant
row is also a composite `(tenant_id, …)` foreign key written as SQL in the migration, because
PostgreSQL checks a foreign key without row-level security: a plain key would let one bank
point at another's row. A unit, licence, product or item is deactivated or withdrawn, never
deleted; teams (`owner_team`) arrive with tenants 0003."""

from __future__ import annotations

import enum
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from apps.shared.tenancy import TenantModel


class SupportAccessLevel(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py)."""

    READ = "read"
    WRITE = "write"


class SupportAccess(TenantModel):
    platform_user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="support_accesses")
    reason = models.TextField()
    ticket_ref = models.CharField(max_length=100, blank=True)
    access_level = models.CharField(
        max_length=8,
        choices=[(kind.value, kind.value) for kind in SupportAccessLevel],
        default=SupportAccessLevel.READ.value,
    )
    approved_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "support_access"
        ordering = ["started_at", "id"]

    def __str__(self) -> str:
        return f"{self.platform_user_id}@{self.tenant_id}"


class OrgUnitKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what an org unit is. A legal entity holds
    licences and carries the legal-entity scope term; a business area, unit or function with
    a head is a department (D-21)."""

    GROUP = "group"
    LEGAL_ENTITY = "legal_entity"
    BUSINESS_AREA = "business_area"
    BUSINESS_UNIT = "business_unit"
    FUNCTION = "function"


class ProductStatusKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): retired is how a product is withdrawn, never
    deleted, and what leaves it out of scope."""

    PLANNED = "planned"
    LIVE = "live"
    RETIRED = "retired"


class CredentialPolicyKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): which passkeys a tenant accepts (ID-07)."""

    ANY_PASSKEY = "any_passkey"
    DEVICE_BOUND = "device_bound"


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(value.value, value.value) for value in kind]


class NeverDeleted(TenantModel):
    """Deactivated or withdrawn, never deleted (CLAUDE.md section 5). Only the retention
    purge and tenant exit remove a row, as the schema owner (D-53, D-56)."""

    class Meta:
        abstract = True

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise ValidationError(
            "Organisation rows are deactivated or withdrawn, never deleted.", code="deactivate_not_delete"
        )


class OrgUnit(NeverDeleted):
    """A group, legal entity, business area, business unit or function (TEN-02, D-21).
    `parent` and `head_user` are composite keys; a membership's entity scope (D-69) is not
    here and needs nothing of this table beyond `UNIQUE (tenant_id, id)`."""

    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    kind = models.CharField(max_length=16, choices=_choices(OrgUnitKind))
    name = models.CharField(max_length=200)
    org_number = models.CharField(max_length=40, blank=True)
    lei = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    entity_term = models.ForeignKey(
        "taxonomy.TaxonomyTerm", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    head_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "org_unit"
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(entity_term__isnull=True) | models.Q(kind=OrgUnitKind.LEGAL_ENTITY.value),
                name="org_unit_entity_term_on_legal_entity",
            ),
            models.CheckConstraint(condition=~models.Q(parent=models.F("id")), name="org_unit_not_own_parent"),
        ]

    def __str__(self) -> str:
        return self.name


class Licence(NeverDeleted):
    """A licence or certificate a legal entity holds (TEN-02, D-43, ADR 0037). The licence
    type is a term, never a phrase; the services it covers are `LicenceServiceTerm` rows.
    A certificate's validity and next audit are the bank's own deadlines and decide no span."""

    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="licences")
    authority = models.ForeignKey("library.Authority", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    licence_type = models.ForeignKey("taxonomy.TaxonomyTerm", on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=200, blank=True)
    granted_on = models.DateField(null=True, blank=True)
    withdrawn_on = models.DateField(null=True, blank=True)
    scope_note = models.TextField(blank=True)
    issuer = models.CharField(max_length=200, blank=True)
    number = models.CharField(max_length=100, blank=True)
    scope_statement = models.TextField(blank=True)
    issued_on = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    next_audit_on = models.DateField(null=True, blank=True)
    owner_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "licence"
        ordering = ["org_unit", "granted_on", "id"]

    def __str__(self) -> str:
        return f"{self.licence_type_id}@{self.org_unit_id}"


class LicenceServiceTerm(TenantModel):
    """A service a licence covers, in the terms obligations are scoped with."""

    licence = models.ForeignKey(Licence, on_delete=models.PROTECT, related_name="service_terms")
    term = models.ForeignKey("taxonomy.TaxonomyTerm", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "licence_service_term"
        ordering = ["licence", "term"]
        constraints = [models.UniqueConstraint(fields=["licence", "term"], name="licence_service_term_unique")]


class TenantProduct(NeverDeleted):
    """A product described the way obligations are scoped (TEN-02); retired, never deleted."""

    org_unit = models.ForeignKey(OrgUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=_choices(ProductStatusKind), default=ProductStatusKind.LIVE.value)
    launch_date = models.DateField(null=True, blank=True)
    owner_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "tenant_product"
        ordering = ["name", "id"]
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="tenant_product_name_unique")]

    def __str__(self) -> str:
        return self.name


class TenantProductTerm(TenantModel):
    """A product's scope in the same terms as obligations (TEN-02)."""

    product = models.ForeignKey(TenantProduct, on_delete=models.PROTECT, related_name="terms")
    term = models.ForeignKey("taxonomy.TaxonomyTerm", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "tenant_product_term"
        ordering = ["product", "term"]
        constraints = [models.UniqueConstraint(fields=["product", "term"], name="tenant_product_term_unique")]


class InternalItem(NeverDeleted):
    """A policy, procedure, control, process or system of the bank (REG-05), one row a
    register entry links to. `kind` is a `link_kind` row of the same tenant."""

    kind = models.ForeignKey("taxonomy.LinkKind", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=200)
    reference = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=2000, blank=True)
    owner_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    org_unit = models.ForeignKey(OrgUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="internal_items")
    external_system = models.CharField(max_length=100, blank=True)
    external_ref = models.CharField(max_length=200, blank=True)
    last_reviewed_on = models.DateField(null=True, blank=True)
    next_review_on = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "internal_item"
        ordering = ["name", "id"]
        constraints = [models.UniqueConstraint(fields=["tenant", "kind", "name"], name="internal_item_kind_name_unique")]

    def __str__(self) -> str:
        return self.name


class SecurityPolicy(TenantModel):
    """A tenant's credential and session policy (ID-07, ID-08, ADR 0048). No row means the
    platform defaults; the limits never exceed the SESSION_*_MAX settings, which the write
    checks. `allowed_authenticators` is a list of AAGUIDs."""

    credential_policy = models.CharField(
        max_length=16, choices=_choices(CredentialPolicyKind), default=CredentialPolicyKind.ANY_PASSKEY.value
    )
    allowed_authenticators = models.JSONField(default=list, blank=True)  # schema: AllowedAuthenticators
    device_bound_from = models.DateField(null=True, blank=True)
    session_idle_minutes = models.PositiveIntegerField(null=True, blank=True)
    session_absolute_hours = models.PositiveIntegerField(null=True, blank=True)
    updated_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "security_policy"
        ordering = ["tenant"]
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="security_policy_tenant_unique"),
            models.CheckConstraint(
                condition=models.Q(session_idle_minutes__isnull=True) | models.Q(session_idle_minutes__gt=0),
                name="security_policy_idle_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(session_absolute_hours__isnull=True) | models.Q(session_absolute_hours__gt=0),
                name="security_policy_absolute_positive",
            ),
        ]
