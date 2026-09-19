"""Guard: row-level security (playbook 5, 14, NFR-01).

Enumerates every model with a foreign key to `shared.Tenant` (TenantModel subclasses and
the mixed tables) and demands, from `pg_class` and `pg_policies` on the real database,
that RLS is enabled and forced and a `tenant_isolation` policy exists whose expression
reads `app.tenant_id`. A new tenant table without a policy fails here, not in production.

The second class proves the policy on the `app` alias (cw_app, no ownership): rows of
tenant A are invisible and unwritable unless tenant A is activated, and library rows
(tenant_id NULL) are visible to everyone. It is a TransactionTestCase because the proof
needs committed rows visible across two connections.

Proven to fail 2026-09-19 by dropping the FORCE clause for audit_event in a scratch
copy of the migration: the first test named the table and the missing clause.
"""

from __future__ import annotations

import uuid

from django.db import DEFAULT_DB_ALIAS, ProgrammingError, connections, transaction
from django.db.models import ForeignKey, Model
from apps.shared.testing import production_models
from django.test import TestCase, TransactionTestCase

from apps.shared import factories, tenancy
from apps.shared.audit import ActorType
from apps.shared.migration_helpers import IDENTITY_LOOKUP_SETTING, POLICY_NAME, TENANT_SETTING
from apps.shared.models import AuditEvent, Tenant

# The only tables whose policy carries the identity-lookup clause (apps/shared/tenancy.py):
# the auth layer reads them before a tenant is known. Adding one here is a review question.
IDENTITY_LOOKUP_TABLES = frozenset({"invitation", "membership", "user_session", "api_key"})


def tenant_scoped_models() -> list[type[Model]]:
    """Every concrete model with a foreign key to shared.Tenant."""
    found = []
    for model in production_models():
        if model is Tenant or model._meta.abstract:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, ForeignKey) and field.related_model is Tenant:
                found.append(model)
                break
    return found


class RowLevelSecurityGuard(TestCase):
    databases = {DEFAULT_DB_ALIAS}

    def test_enumeration_finds_the_mixed_tables(self) -> None:
        tables = sorted(model._meta.db_table for model in tenant_scoped_models())
        self.assertIn("audit_event", tables)
        self.assertIn("outbox_event", tables)
        # instrument and obligation: "shared or mine" on owner_tenant_id (INPUT_DELTAS §5).
        for table in ("membership", "tenant_role", "invitation", "user_session", "api_key", "login_event", "support_access", "instrument", "obligation", "problem_report"):
            self.assertIn(table, tables)

    def test_only_the_named_tables_carry_the_identity_lookup_clause(self) -> None:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT tablename, qual FROM pg_policies WHERE policyname = %s", [POLICY_NAME])
            with_clause = {table for table, qual in cursor.fetchall() if IDENTITY_LOOKUP_SETTING in (qual or "")}
        self.assertEqual(
            with_clause,
            IDENTITY_LOOKUP_TABLES,
            "the identity-lookup clause is for the tables the auth layer reads before a tenant is known; "
            "update IDENTITY_LOOKUP_TABLES and say why",
        )

    def test_every_tenant_table_has_forced_rls_and_a_tenant_policy(self) -> None:
        problems: list[str] = []
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            for model in tenant_scoped_models():
                table = model._meta.db_table
                cursor.execute(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", [table]
                )
                row = cursor.fetchone()
                if row is None:
                    problems.append(f"{table}: table not found")
                    continue
                enabled, forced = row
                if not enabled:
                    problems.append(f"{table}: ROW LEVEL SECURITY is not enabled")
                if not forced:
                    problems.append(f"{table}: ROW LEVEL SECURITY is not forced (the owner would bypass it)")
                cursor.execute(
                    "SELECT qual, with_check FROM pg_policies WHERE tablename = %s AND policyname = %s",
                    [table, POLICY_NAME],
                )
                policy = cursor.fetchone()
                if policy is None:
                    problems.append(f"{table}: no policy named {POLICY_NAME}")
                    continue
                qual, with_check = policy
                if TENANT_SETTING not in (qual or ""):
                    problems.append(f"{table}: policy USING does not read {TENANT_SETTING}: {qual}")
                if TENANT_SETTING not in (with_check or ""):
                    problems.append(f"{table}: policy WITH CHECK does not read {TENANT_SETTING}: {with_check}")
        self.assertEqual(
            problems,
            [],
            "Tenant tables without forced RLS and a tenant policy:\n  "
            + "\n  ".join(problems)
            + "\nAppend rls_operations(<table>) from apps.shared.migration_helpers to the migration.",
        )


class RowLevelSecurityEnforcement(TransactionTestCase):
    """Proves the policy bites for cw_app (the `app` alias), not just that it exists."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        self.tenant_a = factories.tenant(slug="rls-a")
        self.tenant_b = factories.tenant(slug="rls-b")

    def _insert(self, tenant_id: uuid.UUID | None, *, using: str) -> AuditEvent:
        return AuditEvent.objects.using(using).create(
            tenant_id=tenant_id,
            actor_type=ActorType.SYSTEM.value,
            action="rls.probe",
            subject_type="probe",
            subject_id=uuid.uuid4(),
        )

    def test_activated_tenant_sees_only_its_rows_and_library_rows(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self._insert(self.tenant_a.id, using="app")
            self._insert(None, using="app")
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            self._insert(self.tenant_b.id, using="app")

        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            visible = set(AuditEvent.objects.using("app").values_list("tenant_id", flat=True))
        self.assertEqual(visible, {self.tenant_a.id, None})

        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            visible = set(AuditEvent.objects.using("app").values_list("tenant_id", flat=True))
        self.assertEqual(visible, {self.tenant_b.id, None})

    def test_no_activation_sees_only_library_rows_and_cannot_write_tenant_rows(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self._insert(self.tenant_a.id, using="app")
            self._insert(None, using="app")
        with transaction.atomic(using="app"):
            self.assertIsNone(tenancy.database_tenant_id(using="app"))
            visible = set(AuditEvent.objects.using("app").values_list("tenant_id", flat=True))
            self.assertEqual(visible, {None}, "an unset tenant must match no tenant rows (fail closed)")
        with self.assertRaises(ProgrammingError):
            with transaction.atomic(using="app"):
                self._insert(self.tenant_a.id, using="app")

    def test_activated_tenant_cannot_write_another_tenants_rows(self) -> None:
        with self.assertRaises(ProgrammingError):
            with transaction.atomic(using="app"):
                tenancy.activate(self.tenant_a.id, using="app")
                self._insert(self.tenant_b.id, using="app")
