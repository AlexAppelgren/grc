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

from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase, override_settings

from apps.shared import db_role_guard
from apps.shared.db_role_guard import RoleGuardError, check_role, inspect_role


class DatabaseRoleGuard(TestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def test_application_role_cannot_bypass_rls(self) -> None:
        facts = check_role(connections["app"])
        self.assertEqual(facts.role, "cw_app")
        self.assertFalse(facts.is_superuser)
        self.assertFalse(facts.bypasses_rls)
        self.assertEqual(facts.owned_tables, ())

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
