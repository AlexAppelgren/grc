"""A company's own scope as rows (taxonomy 0013; FP-05, D-121, ADR 0066), proved as cw_app
on committed rows: tenant B sees none of tenant A's exclusions or company lines, and the
database refuses a reference to another bank's legal entity or request from an exclusion, a
company line or a history row.

What is written here is written as cw_app with a tenant active, the way the request logic
writes it; that only an approved request writes an exclusion is FP-S21's
(apps/taxonomy/tests_scenarios.py)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from django.db import DEFAULT_DB_ALIAS, IntegrityError, transaction
from django.db.models import Model
from django.test import TransactionTestCase

from apps.library import testing as library_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.models import (
    EntityScopeExclusion,
    FootprintAction,
    FootprintChangeEntityTerm,
    FootprintChangeRequest,
    FootprintHistory,
)
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.models import OrgUnit, OrgUnitKind

APP = "app"


class Bank:
    """One bank's legal entity, a waiting request with one company line and one exclusion, as
    cw_app in its zone."""

    def __init__(self, tenant: Tenant, requester_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.term_id = library_testing.term("regime:insurance").id
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.entity = self.create(OrgUnit, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Example Fonder AB")
            self.request = self.create(FootprintChangeRequest, requested_by_id=requester_id)
            self.line = self.create(
                FootprintChangeEntityTerm,
                request_id=self.request.id,
                org_unit_id=self.entity.id,
                term_id=self.term_id,
                action=FootprintAction.REMOVED.value,
            )
            self.exclusion = self.create(
                EntityScopeExclusion, org_unit_id=self.entity.id, term_id=self.term_id, request_id=self.request.id
            )

    def create(self, model: type[Model], **fields: Any) -> Any:  # compliance: allow-kwargs test helper spreading row fields
        return model._default_manager.using(APP).create(tenant_id=self.tenant.id, **fields)


class EntityScopeTablesUnderRowLevelSecurity(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
        tenant_a = factories.tenant(slug="entity-scope-a")
        tenant_b = factories.tenant(slug="entity-scope-b")
        self.a = Bank(tenant_a, factories.member(tenant_a).user_id)
        self.b = Bank(tenant_b, factories.member(tenant_b).user_id)

    def test_each_tenant_sees_only_its_own_exclusions_and_company_lines(self) -> None:
        for bank in (self.a, self.b):
            with transaction.atomic(using=APP):
                tenancy.activate(bank.tenant.id, using=APP)
                self.assertEqual(list(EntityScopeExclusion.objects.using(APP).values_list("id", flat=True)), [bank.exclusion.id])
                self.assertEqual(list(FootprintChangeEntityTerm.objects.using(APP).values_list("id", flat=True)), [bank.line.id])

    def test_the_database_refuses_a_reference_to_another_tenants_entity_or_request(self) -> None:
        a, b = self.a, self.b
        attempts: dict[str, Callable[[], object]] = {
            "entity_scope_exclusion_org_unit_id_same_tenant": lambda: a.create(
                EntityScopeExclusion, org_unit_id=b.entity.id, term_id=library_testing.term("regime:banking").id, request_id=a.request.id
            ),
            "entity_scope_exclusion_request_id_same_tenant": lambda: a.create(
                EntityScopeExclusion, org_unit_id=a.entity.id, term_id=library_testing.term("regime:banking").id, request_id=b.request.id
            ),
            "footprint_change_entity_term_org_unit_id_same_tenant": lambda: a.create(
                FootprintChangeEntityTerm,
                request_id=a.request.id,
                org_unit_id=b.entity.id,
                term_id=a.term_id,
                action=FootprintAction.REMOVED.value,
            ),
            "footprint_change_entity_term_request_id_same_tenant": lambda: a.create(
                FootprintChangeEntityTerm,
                request_id=b.request.id,
                org_unit_id=a.entity.id,
                term_id=library_testing.term("regime:banking").id,
                action=FootprintAction.REMOVED.value,
            ),
            "footprint_history_org_unit_id_same_tenant": lambda: a.create(
                FootprintHistory, term_id=a.term_id, org_unit_id=b.entity.id, action=FootprintAction.REMOVED.value
            ),
        }
        for constraint, attempt in attempts.items():
            with self.subTest(constraint), transaction.atomic(using=APP):
                tenancy.activate(a.tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    attempt()
