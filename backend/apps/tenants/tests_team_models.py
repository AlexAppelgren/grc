"""Team membership, team owners and a team's department (tenants 0003, taxonomy 0010; TEN-02,
TEN-03), proved as cw_app on committed rows: tenant B sees none of tenant A's team members,
and the database itself refuses a team, a member, an owner team or a department of another
tenant, which a plain foreign key would accept because PostgreSQL checks it without
row-level security.

The composite keys were proven to fail 2026-09-25 by leaving the `COMPOSITE_KEYS` operations
out of a scratch copy of both migrations: every cross-tenant reference below went through."""

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
from apps.taxonomy.models import LinkKind, Team
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.models import InternalItem, Licence, OrgUnit, OrgUnitKind, TeamMember

APP = "app"


class Bank:
    """One bank's department, team, member, licence and internal item, as cw_app in its zone."""

    def __init__(self, tenant: Tenant, user_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.user_id = user_id
        self.licence_type_id = library_testing.term("legal_entity:bank").id
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.link_kind_id = LinkKind.objects.using(APP).get(key="policy").id
            self.entity = self.create(OrgUnit, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Example Bank AB")
            self.department = self.create(OrgUnit, kind=OrgUnitKind.FUNCTION.value, name="Compliance", parent_id=self.entity.id)
            self.team = Team.objects.using(APP).get(key="compliance")
            self.team.org_unit_id = self.department.id
            self.team.save(using=APP)
            self.member = self.create(TeamMember, team_id=self.team.id, user_id=user_id)
            self.licence = self.create(Licence, org_unit_id=self.entity.id, licence_type_id=self.licence_type_id, owner_team_id=self.team.id)
            self.item = self.create(InternalItem, kind_id=self.link_kind_id, name="Custody policy", owner_team_id=self.team.id)

    def create(self, model: type[Model], **fields: Any) -> Any:
        return model._default_manager.using(APP).create(tenant_id=self.tenant.id, **fields)


class TeamTablesUnderRowLevelSecurity(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
        tenant_a = factories.tenant(slug="team-a")
        tenant_b = factories.tenant(slug="team-b")
        self.a = Bank(tenant_a, factories.member(tenant_a).user_id)
        self.b = Bank(tenant_b, factories.member(tenant_b).user_id)

    def test_each_tenant_sees_only_its_own_team_members(self) -> None:
        for bank in (self.a, self.b):
            with transaction.atomic(using=APP):
                tenancy.activate(bank.tenant.id, using=APP)
                self.assertEqual(list(TeamMember.objects.using(APP).values_list("id", flat=True)), [bank.member.id])

    def test_the_database_refuses_a_reference_to_another_tenants_row(self) -> None:
        a, b = self.a, self.b
        attempts: dict[str, Callable[[], object]] = {
            "team_member_team_id_same_tenant": lambda: a.create(TeamMember, team_id=b.team.id, user_id=a.user_id),
            "team_member_user_id_same_tenant": lambda: a.create(TeamMember, team_id=a.team.id, user_id=b.user_id),
            "licence_owner_team_id_same_tenant": lambda: a.create(
                Licence, org_unit_id=a.entity.id, licence_type_id=a.licence_type_id, owner_team_id=b.team.id
            ),
            "internal_item_owner_team_id_same_tenant": lambda: a.create(
                InternalItem, kind_id=a.link_kind_id, name="Their team", owner_team_id=b.team.id
            ),
            "team_org_unit_id_same_tenant": lambda: Team.objects.using(APP).filter(pk=a.team.pk).update(org_unit_id=b.department.id),
        }
        for constraint, attempt in attempts.items():
            with self.subTest(constraint), transaction.atomic(using=APP):
                tenancy.activate(a.tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    attempt()

    def test_a_person_is_in_a_team_once(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            with self.assertRaisesMessage(IntegrityError, "team_member_unique"), transaction.atomic(using=APP):
                self.a.create(TeamMember, team_id=self.a.team.id, user_id=self.a.user_id)

    def test_a_licence_or_an_item_has_a_person_or_a_team_as_owner_never_both(self) -> None:
        a = self.a
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            for model, constraint in ((Licence, "licence_one_owner"), (InternalItem, "internal_item_one_owner")):
                with self.subTest(constraint), self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    model._default_manager.using(APP).filter(owner_team_id=a.team.id).update(owner_user_id=a.user_id)
            person_owned = a.create(Licence, org_unit_id=a.entity.id, licence_type_id=a.licence_type_id, owner_user_id=a.user_id)
            self.assertIsNone(person_owned.owner_team_id)
