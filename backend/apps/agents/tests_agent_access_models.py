"""The agent access tables (agents 0006; ACC-01, ACC-02, D-70, ADR 0055), proved as cw_app on
committed rows: tenant B sees none of tenant A's entries or their joins, and the database
itself refuses an entry, or a join, that names another bank's team, person, department,
product or entry, which a plain foreign key would accept because PostgreSQL checks it
without row-level security.

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
from django.utils import timezone

from apps.agents.models import AgentAccess, AgentAccessDepartment, AgentAccessProduct
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.models import Team
from apps.tenants.models import OrgUnit, OrgUnitKind, TenantProduct

APP = "app"
ACCESS_MODELS: tuple[type[Model], ...] = (AgentAccess, AgentAccessDepartment, AgentAccessProduct)


class Bank:
    """One bank's entry narrowed to one department and one product, written as cw_app."""

    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant
        self.admin_id = factories.member(tenant, roles=("admin",)).user_id
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.team_id = Team.objects.using(APP).get(key="compliance").id
            self.department = self.create(OrgUnit, kind=OrgUnitKind.BUSINESS_AREA.value, name="Trading")
            self.product = self.create(TenantProduct, name="Equities")
            self.entry = self.create(
                AgentAccess,
                name="Trading platform coding agent",
                purpose="Builds the order-routing service.",
                owner_team_id=self.team_id,
                created_by_id=self.admin_id,
            )
            self.create(AgentAccessDepartment, agent_access_id=self.entry.id, department_id=self.department.id)
            self.create(AgentAccessProduct, agent_access_id=self.entry.id, product_id=self.product.id)

    def create(self, model: type[Model], **fields: Any) -> Any:
        return model._default_manager.using(APP).create(tenant_id=self.tenant.id, **fields)


class AgentAccessUnderRowLevelSecurity(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        self.a = Bank(factories.tenant(slug="access-a"))
        self.b = Bank(factories.tenant(slug="access-b"))

    def _visible(self, tenant: Tenant) -> dict[str, set[uuid.UUID]]:
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            return {
                model._meta.db_table: set(model._default_manager.using(APP).values_list("id", flat=True))
                for model in ACCESS_MODELS
            }

    def _rows_of(self, bank: Bank) -> dict[str, set[uuid.UUID]]:
        return {
            "agent_access": {bank.entry.id},
            "agent_access_department": set(bank.entry.departments.using(APP).values_list("id", flat=True)),
            "agent_access_product": set(bank.entry.products.using(APP).values_list("id", flat=True)),
        }

    def test_tenant_b_sees_no_entry_of_tenant_a(self) -> None:
        for bank in (self.a, self.b):
            with transaction.atomic(using=APP):
                tenancy.activate(bank.tenant.id, using=APP)
                own = self._rows_of(bank)
            self.assertEqual(self._visible(bank.tenant), own)
            self.assertTrue(all(own.values()), "each bank wrote an entry and both joins")

    def test_the_database_refuses_a_reference_to_another_tenants_row(self) -> None:
        a, b = self.a, self.b

        def entry(**fields: Any) -> Any:
            return a.create(AgentAccess, **{"name": "Card agent", "purpose": "Reads card rules.", "owner_team_id": a.team_id, "created_by_id": a.admin_id, **fields})

        now = timezone.now()
        attempts: dict[str, Callable[[], object]] = {
            "agent_access_owner_team_id_same_tenant": lambda: entry(owner_team_id=b.team_id),
            "agent_access_created_by_id_same_tenant": lambda: entry(created_by_id=b.admin_id),
            "agent_access_revoked_by_id_same_tenant": lambda: entry(active=False, revoked_at=now, revoked_by_id=b.admin_id),
            "agent_access_department_department_id_same_tenant": lambda: a.create(
                AgentAccessDepartment, agent_access_id=a.entry.id, department_id=b.department.id
            ),
            "agent_access_department_agent_access_id_same_tenant": lambda: a.create(
                AgentAccessDepartment, agent_access_id=b.entry.id, department_id=a.department.id
            ),
            "agent_access_product_product_id_same_tenant": lambda: a.create(
                AgentAccessProduct, agent_access_id=a.entry.id, product_id=b.product.id
            ),
            "agent_access_product_agent_access_id_same_tenant": lambda: a.create(
                AgentAccessProduct, agent_access_id=b.entry.id, product_id=a.product.id
            ),
        }
        for constraint, attempt in attempts.items():
            with self.subTest(constraint), transaction.atomic(using=APP):
                tenancy.activate(a.tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    attempt()

    def test_an_entry_names_a_department_or_a_product_once(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            with self.assertRaisesMessage(IntegrityError, "agent_access_department_unique"), transaction.atomic(using=APP):
                self.a.create(AgentAccessDepartment, agent_access_id=self.a.entry.id, department_id=self.a.department.id)
            with self.assertRaisesMessage(IntegrityError, "agent_access_product_unique"), transaction.atomic(using=APP):
                self.a.create(AgentAccessProduct, agent_access_id=self.a.entry.id, product_id=self.a.product.id)

    def test_a_new_entry_reads_the_library_only_and_is_revoked_never_deleted(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            entry = AgentAccess.objects.using(APP).get(pk=self.a.entry.pk)
            self.assertEqual((entry.tenant_reach, entry.active, entry.version, entry.revoked_at), (False, True, 1, None))
            rows = AgentAccess.objects.using(APP).filter(pk=entry.pk)
            changes: dict[str, dict[str, Any]] = {
                "an inactive entry carries its revocation": {"active": False},
                "a revoked entry is inactive": {"revoked_at": timezone.now()},
                "only a revoked entry names who revoked it": {"revoked_by_id": self.a.admin_id},
            }
            for constraint, change in changes.items():
                with self.subTest(constraint), self.assertRaisesMessage(IntegrityError, "agent_access_revoked_is_inactive"):
                    with transaction.atomic(using=APP):
                        rows.update(**change)
            rows.update(active=False, revoked_at=timezone.now(), revoked_by_id=self.a.admin_id)
            with self.assertRaises(ValidationError) as refused:
                entry.delete()
            self.assertEqual(refused.exception.code, "revoke_not_delete")
            self.assertTrue(rows.exists())

    def test_entries_list_by_name(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            self.a.create(AgentAccess, name="Card issuing assistant", purpose="Answers staff.", owner_team_id=self.a.team_id, created_by_id=self.a.admin_id)
            names = list(AgentAccess.objects.using(APP).values_list("name", flat=True))
        self.assertEqual(names, sorted(names))
