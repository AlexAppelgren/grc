"""A child of an instrument or an obligation lives in its parent's zone (INV-07, OWN-04;
library 0012, ADR 0050 tranche 2, hardening H7's private half).

One test per child table, as cw_app (the `app` alias) and in SQL rather than through the ORM,
because the policy is what must refuse here, not the library fence in Python. Each builds the
same world: a shared instrument and obligation with every kind of child, and tenant A's own
pair with the same. Then, per table:

- the reads: tenant B and a platform session read the shared child and never A's; A reads both;
- the refused writes: B inserts under the shared parent and under A's, a platform session under
  A's, A under the shared one, and each is refused; B, the platform and A each update and delete
  nothing of a zone that is not theirs;
- the write the rule allows: A inserts a child under its own parent.

Every statement runs inside the door its table accepts (the seed door, or the watch door for a
change's coverage row), because outside one the trigger of shared 0008 refuses the statement
before the policy is asked; the last test proves that it still does.

A new row is a copy of the shared child with its parent swapped and, where a unique key would
collide under A's parent, one column changed (`CHANGED`), so the probe reaches the policy and
not a constraint. A provision under a parent its writer cannot see is refused by
`provision_not_under_standard` first, which fails closed the same way (tests_library.py).

Proven to fail 2026-09-25 by giving `obligation_title`, in a scratch copy of library 0012, its
read rule as its write rule: tenant B's insert under the shared parent went through, A's under
the shared parent reached the unique key instead of the policy, and B's update and delete
reached the shared title; `obligation_summary`, left as it was, stayed green.
"""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections, transaction
from django.test import TransactionTestCase

from apps.agents import testing as agents_testing
from apps.library import testing as build
from apps.library.models import ObligationVersion, RecurringDuty
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.shared.tenancy import library_write
from apps.watch import testing as watch_testing

APP = "app"
TRANSLATED = {"language_id": "sv", "is_original": False, "is_machine": True}

# The column that differs from the copied shared child when A writes under its own parent,
# because A's parent already holds a child with the shared one's unique value.
CHANGED: dict[str, dict[str, Any]] = {
    "instrument_title": TRANSLATED,
    "obligation_title": TRANSLATED,
    "obligation_summary": TRANSLATED,
    "provision_text": TRANSLATED,
    "obligation_version": {"version_number": 2},
    "provision_version": {"version_number": 2},
    "provision": {"stable_key": "bank-a-act/probe"},
}


def _sql(template: str, *identifiers: str) -> str:
    """`template` with each `{}` filled by a quoted table or column name."""
    return sql.SQL(template).format(*(sql.Identifier(name) for name in identifiers)).as_string()


class ChildrenFollowTheirParentsZone(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        with transaction.atomic():
            watch_testing.seed_watch_reference()
        self.tenant_a = factories.tenant(slug="child-a")
        self.tenant_b = factories.tenant(slug="child-b")
        self.agent = agents_testing.agent(key="child-duty-agent")
        shared = self._records("shared-act", None)
        own = self._records("bank-a-act", self.tenant_a)
        # table: (the column naming its parent, the shared parent, tenant A's parent)
        self.parents = {
            table: (column, shared[parent], own[parent])
            for table, (column, parent) in {
                "instrument_title": ("instrument_id", "instrument"),
                "instrument_relation": ("from_instrument_id", "instrument"),
                "provision": ("instrument_id", "instrument"),
                "provision_version": ("provision_id", "provision"),
                "provision_text": ("version_id", "provision_version"),
                "obligation_title": ("obligation_id", "obligation"),
                "obligation_version": ("obligation_id", "obligation"),
                "obligation_summary": ("version_id", "obligation_version"),
                "obligation_provision": ("obligation_id", "obligation"),
                "obligation_term": ("obligation_id", "obligation"),
                "obligation_tag": ("obligation_id", "obligation"),
                "obligation_relation": ("from_obligation_id", "obligation"),
                "recurring_duty": ("obligation_id", "obligation"),
                "change_obligation": ("obligation_id", "obligation"),
            }.items()
        }

    def _records(self, key: str, owner: Tenant | None) -> dict[str, uuid.UUID]:
        """An instrument and an obligation of `owner`'s zone with one child of every kind,
        written by the builders in that zone. Returns the parents' ids by kind."""
        instrument = build.instrument(key=key, regime="regime:securities", owner_tenant=owner)
        build.relate_instruments(instrument, build.instrument(key=f"{key}-2", regime="regime:securities", owner_tenant=owner), relation="implements")
        provision = build.provision(instrument, key=f"{key}/1")
        provision_version = build.provision_version(provision)
        own = owner is not None
        obligation = build.obligation(
            instrument,
            key=f"{key}/o1",
            owner_tenant=owner,
            terms=("service_type:custody",) if own else ("service_type:advice",),
            tags=("costs",) if own else ("advice",),
            cites=(provision,),
        )
        build.relate(obligation, build.obligation(instrument, key=f"{key}/o2", owner_tenant=owner))
        with transaction.atomic(), library_write("a test builder"), tenancy.platform_zone():
            if owner is not None:
                tenancy.activate(owner.id)
            RecurringDuty.objects.create(
                obligation=obligation,
                title="Quarterly report to the supervisor",
                recurrence_rule="FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=-1",
                lead_days=14,
                created_origin="agent",
                created_by_agent=self.agent,
            )
            obligation_version = ObligationVersion.objects.get(obligation=obligation)
        watch_testing.obligation_link(watch_testing.change(), obligation)
        return {
            "instrument": instrument.id,
            "provision": provision.id,
            "provision_version": provision_version.id,
            "obligation": obligation.id,
            "obligation_version": obligation_version.id,
        }

    # --- the probes, all on the cw_app connection --------------------------------------
    @staticmethod
    def _enter(zone: Tenant | None) -> None:
        if zone is not None:
            tenancy.activate(zone.id, using=APP)

    @staticmethod
    def _door(table: str) -> Any:
        return tenancy.library_door("watch" if table == "change_obligation" else "seed", using=APP)

    def _row(self, table: str, column: str, parent: uuid.UUID, zone: Tenant | None) -> uuid.UUID:
        with transaction.atomic(using=APP), connections[APP].cursor() as cursor:
            self._enter(zone)
            cursor.execute(_sql('SELECT id FROM {} WHERE {} = %s ORDER BY id LIMIT 1', table, column), [parent])
            row = cursor.fetchone()
        self.assertIsNotNone(row, f"{table}: no child under {parent} in its own zone")
        assert row is not None
        return uuid.UUID(str(row[0]))

    def _visible(self, table: str, rows: list[uuid.UUID], zone: Tenant | None) -> set[uuid.UUID]:
        with transaction.atomic(using=APP), connections[APP].cursor() as cursor:
            self._enter(zone)
            cursor.execute(_sql("SELECT id FROM {} WHERE id = ANY(%s)", table), [rows])
            return {uuid.UUID(str(found)) for (found,) in cursor.fetchall()}

    def _insert(self, table: str, template: uuid.UUID, column: str, parent: uuid.UUID) -> int:
        """A copy of `template` under `parent`, in the zone and door the caller opened."""
        changed = CHANGED.get(table, {})
        with connections[APP].cursor() as cursor:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position", [table])
            columns = [name for (name,) in cursor.fetchall()]
            values: list[sql.Composable] = []
            params: list[Any] = []
            for name in columns:
                if name == "id":
                    values.append(sql.SQL("gen_random_uuid()"))
                elif name == column or name in changed:
                    values.append(sql.Placeholder())
                    params.append(parent if name == column else changed[name])
                else:
                    values.append(sql.Identifier(name))
            statement = sql.SQL("INSERT INTO {table} ({names}) SELECT {values} FROM {table} WHERE id = %s").format(
                table=sql.Identifier(table),
                names=sql.SQL(", ").join(sql.Identifier(name) for name in columns),
                values=sql.SQL(", ").join(values),
            )
            cursor.execute(statement.as_string(), [*params, template])
            return cursor.rowcount

    def _refused(self, table: str, zone: Tenant | None, template: uuid.UUID, column: str, parent: uuid.UUID) -> None:
        with self.assertRaises(DatabaseError) as refused, transaction.atomic(using=APP):
            self._enter(zone)
            with self._door(table):
                self._insert(table, template, column, parent)
        expected = "provision_not_under_standard" if table == "provision" and "row-level" not in str(refused.exception) else "row-level security"
        self.assertIn(expected, str(refused.exception))

    def _touched(self, table: str, zone: Tenant | None, rows: list[uuid.UUID]) -> tuple[int, int]:
        """How many of `rows` an update and a delete from `zone` reach."""
        with transaction.atomic(using=APP), connections[APP].cursor() as cursor:
            self._enter(zone)
            with self._door(table):
                cursor.execute(_sql("UPDATE {} SET id = id WHERE id = ANY(%s)", table), [rows])
                updated = cursor.rowcount
                cursor.execute(_sql("DELETE FROM {} WHERE id = ANY(%s)", table), [rows])
                return updated, cursor.rowcount

    def _prove(self, table: str) -> None:
        column, shared_parent, own_parent = self.parents[table]
        shared = self._row(table, column, shared_parent, None)
        own = self._row(table, column, own_parent, self.tenant_a)
        both = [shared, own]

        self.assertEqual(self._visible(table, both, self.tenant_b), {shared}, "another bank reads the shared child only")
        self.assertEqual(self._visible(table, both, None), {shared}, "a platform session reads the shared child only")
        self.assertEqual(self._visible(table, both, self.tenant_a), {shared, own}, "the owner reads both")

        for zone, parent in ((self.tenant_b, shared_parent), (self.tenant_b, own_parent), (None, own_parent), (self.tenant_a, shared_parent)):
            with self.subTest(write="insert", zone=zone.slug if zone else "platform", parent=str(parent)):
                self._refused(table, zone, shared, column, parent)
        for zone, rows in ((self.tenant_b, both), (None, [own]), (self.tenant_a, [shared])):
            with self.subTest(write="update and delete", zone=zone.slug if zone else "platform"):
                self.assertEqual(self._touched(table, zone, rows), (0, 0))
        self.assertEqual(self._visible(table, both, self.tenant_a), {shared, own}, "nothing was changed or deleted")

        with transaction.atomic(using=APP):
            self._enter(self.tenant_a)
            with self._door(table):
                self.assertEqual(self._insert(table, shared, column, own_parent), 1, "the owner writes under its own parent")

    def test_instrument_title(self) -> None:
        self._prove("instrument_title")

    def test_instrument_relation(self) -> None:
        self._prove("instrument_relation")

    def test_provision(self) -> None:
        self._prove("provision")

    def test_provision_version(self) -> None:
        self._prove("provision_version")

    def test_provision_text(self) -> None:
        self._prove("provision_text")

    def test_obligation_title(self) -> None:
        self._prove("obligation_title")

    def test_obligation_version(self) -> None:
        self._prove("obligation_version")

    def test_obligation_summary(self) -> None:
        self._prove("obligation_summary")

    def test_obligation_provision(self) -> None:
        self._prove("obligation_provision")

    def test_obligation_term(self) -> None:
        self._prove("obligation_term")

    def test_obligation_tag(self) -> None:
        self._prove("obligation_tag")

    def test_obligation_relation(self) -> None:
        self._prove("obligation_relation")

    def test_recurring_duty(self) -> None:
        self._prove("recurring_duty")

    def test_change_obligation(self) -> None:
        self._prove("change_obligation")

    def test_the_door_trigger_still_refuses_a_write_outside_a_door(self) -> None:
        """H16, ADR 0058: the owner's own write under its own parent, with no door open, is
        refused by the trigger before any policy is asked."""
        for table, (column, shared_parent, own_parent) in sorted(self.parents.items()):
            template = self._row(table, column, shared_parent, None)
            with self.subTest(table=table), self.assertRaises(DatabaseError) as refused, transaction.atomic(using=APP):
                self._enter(self.tenant_a)
                self._insert(table, template, column, own_parent)
            self.assertIn(f"INSERT on {table} refused: the door open is none", str(refused.exception))

    def test_every_child_table_is_proven_here(self) -> None:
        """The census in apps/shared/tests_rls.py names every child; each has a test above."""
        from apps.shared.tests_rls import CHILD_TABLES

        self.assertEqual(set(self.parents), set(CHILD_TABLES))
        self.assertEqual({name.removeprefix("test_") for name in dir(self) if name.removeprefix("test_") in CHILD_TABLES}, set(CHILD_TABLES))
