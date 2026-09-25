"""The bank's organisation tables (tenants 0002; TEN-02, REG-05, ID-07, ID-08), proved as
cw_app on committed rows: tenant B sees none of tenant A's organisation, and the database
itself refuses a reference to another tenant's row, which a plain foreign key would accept
because PostgreSQL checks it without row-level security.

The composite keys were proven to fail 2026-09-25 by leaving the `COMPOSITE_KEYS` operations
out of a scratch copy of the migration: every cross-tenant reference below went through."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, IntegrityError, transaction
from django.db.models import Model
from django.test import TransactionTestCase

from apps.library import testing as library_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.models import LinkKind
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.models import (
    CredentialPolicyKind,
    InternalItem,
    Licence,
    LicenceServiceTerm,
    OrgUnit,
    OrgUnitKind,
    ProductStatusKind,
    SecurityPolicy,
    TenantProduct,
    TenantProductTerm,
)

APP = "app"
ORGANISATION_MODELS: tuple[type[Model], ...] = (
    OrgUnit,
    Licence,
    LicenceServiceTerm,
    TenantProduct,
    TenantProductTerm,
    InternalItem,
    SecurityPolicy,
)


class Organisation:
    """One bank's organisation, every table written once, as cw_app in its own zone."""

    def __init__(self, tenant: Tenant, head_user_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.head_user_id = head_user_id
        entity_term = library_testing.term("legal_entity:bank")
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.link_kind_id = LinkKind.objects.using(APP).get(key="policy").id
            group = self.create(OrgUnit, kind=OrgUnitKind.GROUP.value, name="Example Group")
            self.entity = self.create(
                OrgUnit,
                kind=OrgUnitKind.LEGAL_ENTITY.value,
                name="Example Bank AB",
                parent_id=group.id,
                org_number="556000-0000",
                lei="5493000EXAMPLE000000",
                country_code="SE",
                entity_term_id=entity_term.id,
                head_user_id=head_user_id,
            )
            self.licence = self.create(
                Licence,
                org_unit_id=self.entity.id,
                licence_type_id=entity_term.id,
                reference="FI 12-3456",
                issuer="Example Certification AB",
                number="CERT-1",
                owner_user_id=head_user_id,
            )
            self.create(LicenceServiceTerm, licence_id=self.licence.id, term_id=library_testing.term("service_type:custody").id)
            self.product = self.create(
                TenantProduct, name="Custody", status=ProductStatusKind.LIVE.value, org_unit_id=self.entity.id, owner_user_id=head_user_id
            )
            self.create(TenantProductTerm, product_id=self.product.id, term_id=library_testing.term("service_type:custody").id)
            self.item = self.create(
                InternalItem, kind_id=self.link_kind_id, name="Custody policy", org_unit_id=self.entity.id, owner_user_id=head_user_id
            )
            self.create(SecurityPolicy, credential_policy=CredentialPolicyKind.DEVICE_BOUND.value, updated_by_id=head_user_id)

    def create(self, model: type[Model], **fields: Any) -> Any:
        return model._default_manager.using(APP).create(tenant_id=self.tenant.id, **fields)


class OrganisationTablesUnderRowLevelSecurity(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
        tenant_a = factories.tenant(slug="org-a")
        tenant_b = factories.tenant(slug="org-b")
        self.a = Organisation(tenant_a, factories.member(tenant_a).user_id)
        self.b = Organisation(tenant_b, factories.member(tenant_b).user_id)

    def _visible(self, tenant: Tenant) -> dict[str, set[uuid.UUID]]:
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            return {
                model._meta.db_table: set(model._default_manager.using(APP).values_list("tenant_id", flat=True))
                for model in ORGANISATION_MODELS
            }

    def test_each_tenant_sees_only_its_own_organisation(self) -> None:
        for organisation in (self.a, self.b):
            seen = self._visible(organisation.tenant)
            self.assertEqual(seen, {model._meta.db_table: {organisation.tenant.id} for model in ORGANISATION_MODELS})

    def test_the_database_refuses_a_reference_to_another_tenants_row(self) -> None:
        a, b = self.a, self.b
        attempts: dict[str, Callable[[], object]] = {
            "org_unit_parent_id_same_tenant": lambda: a.create(OrgUnit, kind=OrgUnitKind.BUSINESS_AREA.value, name="Retail", parent_id=b.entity.id),
            "org_unit_head_user_id_same_tenant": lambda: a.create(OrgUnit, kind=OrgUnitKind.FUNCTION.value, name="Legal", head_user_id=b.head_user_id),
            "licence_org_unit_id_same_tenant": lambda: a.create(Licence, org_unit_id=b.entity.id, licence_type_id=a.licence.licence_type_id),
            "licence_owner_user_id_same_tenant": lambda: a.create(
                Licence, org_unit_id=a.entity.id, licence_type_id=a.licence.licence_type_id, owner_user_id=b.head_user_id
            ),
            "licence_service_term_licence_id_same_tenant": lambda: a.create(
                LicenceServiceTerm, licence_id=b.licence.id, term_id=library_testing.term("service_type:advice").id
            ),
            "tenant_product_org_unit_id_same_tenant": lambda: a.create(TenantProduct, name="Cards", org_unit_id=b.entity.id),
            "tenant_product_owner_user_id_same_tenant": lambda: a.create(TenantProduct, name="Loans", owner_user_id=b.head_user_id),
            "tenant_product_term_product_id_same_tenant": lambda: a.create(
                TenantProductTerm, product_id=b.product.id, term_id=library_testing.term("service_type:advice").id
            ),
            "internal_item_kind_id_same_tenant": lambda: a.create(InternalItem, kind_id=b.link_kind_id, name="Their kind"),
            "internal_item_org_unit_id_same_tenant": lambda: a.create(InternalItem, kind_id=a.link_kind_id, name="Their unit", org_unit_id=b.entity.id),
            "internal_item_owner_user_id_same_tenant": lambda: a.create(
                InternalItem, kind_id=a.link_kind_id, name="Their owner", owner_user_id=b.head_user_id
            ),
        }
        for constraint, attempt in attempts.items():
            with self.subTest(constraint), transaction.atomic(using=APP):
                tenancy.activate(a.tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    attempt()

    def test_the_security_policy_names_a_member_of_its_own_tenant_once_per_tenant(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            with self.assertRaisesMessage(IntegrityError, "security_policy_tenant_unique"), transaction.atomic(using=APP):
                self.a.create(SecurityPolicy)
            policy = SecurityPolicy.objects.using(APP).get()
            policy.updated_by_id = self.b.head_user_id
            with self.assertRaisesMessage(IntegrityError, "security_policy_updated_by_id_same_tenant"), transaction.atomic(using=APP):
                policy.save(using=APP)
            with self.assertRaisesMessage(IntegrityError, "security_policy_idle_positive"), transaction.atomic(using=APP):
                SecurityPolicy.objects.using(APP).update(session_idle_minutes=0)

    def test_only_a_legal_entity_carries_a_term_and_only_of_the_legal_entity_dimension(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            with self.assertRaisesMessage(IntegrityError, "legal_entity dimension"), transaction.atomic(using=APP):
                self.a.create(
                    OrgUnit,
                    kind=OrgUnitKind.LEGAL_ENTITY.value,
                    name="Example Fonder AB",
                    entity_term_id=library_testing.term("service_type:custody").id,
                )
            with self.assertRaisesMessage(IntegrityError, "org_unit_entity_term_on_legal_entity"), transaction.atomic(using=APP):
                self.a.create(
                    OrgUnit,
                    kind=OrgUnitKind.BUSINESS_UNIT.value,
                    name="Retail",
                    entity_term_id=library_testing.term("legal_entity:fund_company").id,
                )
            with self.assertRaisesMessage(IntegrityError, "org_unit_not_own_parent"), transaction.atomic(using=APP):
                OrgUnit.objects.using(APP).filter(pk=self.a.entity.pk).update(parent_id=self.a.entity.pk)

    def test_units_licences_products_and_items_are_never_deleted(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            for row in (self.a.entity, self.a.licence, self.a.product, self.a.item):
                with self.subTest(type(row).__name__), self.assertRaises(ValidationError) as refused:
                    row.delete()
                self.assertEqual(refused.exception.code, "deactivate_not_delete")
                self.assertTrue(type(row)._default_manager.using(APP).filter(pk=row.pk).exists())
