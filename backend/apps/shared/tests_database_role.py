"""Guard: database role (playbook 5, 14, AC-NFR2).

Connects as the application role through the `app` alias (cw_app on the test database)
and demands: not a superuser, not the owner of any table, no BYPASSRLS. Then runs the
same check against the runner's own `default` connection (cw_migrator, the owner) and
demands a refusal, so the guard is proven to bite in the same run that proves it passes.

The boot-time wiring (SharedConfig.ready → check_at_boot) is proven by
tests_production_guard.py in subprocesses.

Proven to fail 2026-09-19 by pointing the `app` alias at the migrator URL: the test
named the role and the tables it owns.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import psycopg
from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase, override_settings
from psycopg import sql

from apps.shared import db_role_guard
from apps.shared.db_role_guard import RoleGuardError, check_role, inspect_role
from apps.shared.tests_production_guard import _with_database


class DatabaseRoleGuard(TestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def test_application_role_cannot_bypass_rls(self) -> None:
        facts = check_role(connections["app"])
        self.assertEqual(facts.role, "cw_app")
        self.assertFalse(facts.is_superuser)
        self.assertFalse(facts.bypasses_rls)
        self.assertFalse(facts.creates_roles)
        self.assertEqual(facts.owned_tables, ())

    def test_a_member_of_the_owner_and_a_role_creator_are_refused(self) -> None:
        """Review 2026-11-11 L-7: `GRANT cw_migrator TO cw_app` passed the guard, because
        it read only the tables the role owns itself, and a CREATEROLE role can grant
        itself more. Two throwaway roles live inside one superuser transaction that is
        rolled back, so no other connection on the cluster ever sees them."""
        test_db = connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]
        migrator = connections[DEFAULT_DB_ALIAS].settings_dict["USER"]
        member, creator = (f"cw_l7_{name}_{uuid.uuid4().hex[:10]}" for name in ("member", "creator"))
        with psycopg.connect(_with_database(settings.TEST_SUPERUSER_DATABASE_URL, test_db)) as admin:
            try:
                admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(member)))
                admin.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(migrator), sql.Identifier(member)))
                admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN CREATEROLE").format(sql.Identifier(creator)))
                for role, problem in ((member, "owns tables"), (creator, "has CREATEROLE")):
                    with self.subTest(role=role):
                        admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
                        with self.assertRaises(RoleGuardError) as caught:
                            check_role(cast(Any, admin))
                        self.assertIn(problem, str(caught.exception))
                        admin.execute("RESET ROLE")
            finally:
                admin.rollback()

    def test_the_migrator_is_refused_because_it_owns_the_tables(self) -> None:
        facts = inspect_role(connections[DEFAULT_DB_ALIAS])
        self.assertIn("audit_event", facts.owned_tables, "the test database was not migrated by the migrator")
        with self.assertRaises(RoleGuardError) as caught:
            check_role(connections[DEFAULT_DB_ALIAS])
        self.assertIn("owns tables", str(caught.exception))
        self.assertIn(facts.role, str(caught.exception))

    def test_check_at_boot_is_skipped_only_by_the_setting_or_an_exempt_command(self) -> None:
        # Under the runner the setting is off (test_settings override 2): nothing raises.
        db_role_guard.check_at_boot()
        # With the setting on and argv naming an exempt command: nothing raises either.
        with override_settings(DB_ROLE_GUARD_ENABLED=True):
            with self.settings(DB_ROLE_GUARD_EXEMPT_COMMANDS=frozenset({"test"})):
                db_role_guard.check_at_boot()
            # With the setting on and no exemption, the default (migrator) connection is refused.
            with self.settings(DB_ROLE_GUARD_EXEMPT_COMMANDS=frozenset()):
                with self.assertRaises(RoleGuardError):
                    db_role_guard.check_at_boot()


class JustInTimeCompilationIsOff(TestCase):
    """r2-perf (NFR-02): the row-level security subqueries lift a hybrid search's estimated
    cost far above PostgreSQL's `jit_above_cost`, and on a slot of 3,000 obligations the
    search spent 5.1 s of 5.9 s compiling a plan whose rows took under 400 ms. Every
    connection the app opens runs with JIT off."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def test_every_connection_runs_without_jit(self) -> None:
        for alias in (DEFAULT_DB_ALIAS, "app"):
            with self.subTest(alias=alias), connections[alias].cursor() as cursor:
                cursor.execute("SHOW jit")
                self.assertEqual(cursor.fetchone(), ("off",))

    def test_the_deployed_settings_ask_for_it(self) -> None:
        from config import settings as deployed

        self.assertEqual(deployed.DATABASES["default"]["OPTIONS"]["options"], "-c jit=off")

