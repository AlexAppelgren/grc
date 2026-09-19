"""The management commands the entrypoint and the gates call: seed_reference (the loop and
its "what breaks without it" line), migrate_from_zero (the subprocess it spawns and the
scratch database it drops), export_openapi (writes the normalised document)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from apps.shared.management.commands import migrate_from_zero, seed_reference


class SeedReference(TestCase):
    def test_the_registered_seeds_run_and_report(self) -> None:
        from apps.shared import factories

        factories.tenant(slug="seeded")
        out = StringIO()
        call_command("seed_reference", stdout=out)
        self.assertIn("languages: 5 rows", out.getvalue())
        self.assertIn("platform_roles: 2 rows", out.getvalue())
        self.assertIn("tenant_system_roles: 7 rows", out.getvalue())

    def test_each_seed_runs_in_order_and_prints_what_breaks_without_it(self) -> None:
        order: list[str] = []

        def first() -> int:
            order.append("first")
            return 3

        def second() -> int:
            order.append("second")
            return 1

        seeds = (
            ("permissions", first, "every route 403s"),
            ("system_roles", second, "invitations cannot assign a role"),
        )
        out = StringIO()
        with mock.patch.object(seed_reference, "REFERENCE_SEEDS", seeds):
            call_command("seed_reference", stdout=out)
        self.assertEqual(order, ["first", "second"])
        self.assertIn("permissions: 3 rows (without it: every route 403s)", out.getvalue())
        self.assertIn("system_roles: 1 rows", out.getvalue())


class MigrateFromZero(SimpleTestCase):
    @override_settings(IS_DEPLOYED_ENVIRONMENT=True)
    def test_refuses_a_deployed_environment(self) -> None:
        with self.assertRaises(CommandError):
            call_command("migrate_from_zero")

    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch")
    def test_recreates_the_scratch_database_and_migrates_it_in_a_subprocess(self) -> None:
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        completed = mock.Mock(returncode=0)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn) as connect, mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=completed
        ) as run:
            call_command("migrate_from_zero", stdout=StringIO())
        self.assertEqual(connect.call_args_list[0].args[0], "postgres://cw_migrator:pw@db:5432/postgres")
        self.assertTrue(any("DROP DATABASE IF EXISTS" in sql for sql in executed))
        self.assertTrue(any("CREATE DATABASE" in sql and "TEMPLATE template1" in sql for sql in executed))
        self.assertEqual(executed.count('DROP DATABASE IF EXISTS "compliance_watch_scratch" WITH (FORCE)'), 2)
        env = run.call_args.kwargs["env"]
        scratch = "postgres://cw_migrator:pw@db:5432/compliance_watch_scratch"
        self.assertEqual(env["DATABASE_URL"], scratch)
        self.assertEqual(env["MIGRATOR_DATABASE_URL"], scratch)
        self.assertIn("migrate", run.call_args.args[0])

    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch")
    def test_keep_leaves_the_scratch_database_and_a_failed_migrate_raises(self) -> None:
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=0)
        ):
            call_command("migrate_from_zero", "--keep", stdout=StringIO())
        self.assertEqual(executed.count('DROP DATABASE IF EXISTS "compliance_watch_scratch" WITH (FORCE)'), 1)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=1)
        ):
            with self.assertRaises(CommandError):
                call_command("migrate_from_zero", stdout=StringIO())


    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch")
    def test_name_picks_the_database_and_refuses_an_unsafe_one(self) -> None:
        """The E2E boot builds `compliance_watch_e2e` with `--name` and `--keep`
        (frontend/tests/e2e/support/start-backend.sh). Before this option existed the boot
        migrated the scratch database, dropped it, and seeded an unmigrated one:
        'relation "tenant" does not exist' on the first E2E run, 2026-09-19."""
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as run:
            call_command("migrate_from_zero", "--name", "compliance_watch_e2e", "--keep", stdout=StringIO())
        self.assertEqual(executed.count('DROP DATABASE IF EXISTS "compliance_watch_e2e" WITH (FORCE)'), 1)
        self.assertIn('CREATE DATABASE "compliance_watch_e2e" TEMPLATE template1', executed)
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["DATABASE_URL"], "postgres://cw_migrator:pw@db:5432/compliance_watch_e2e")
        self.assertEqual(env["MIGRATOR_DATABASE_URL"], "postgres://cw_migrator:pw@db:5432/compliance_watch_e2e")
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn):
            with self.assertRaises(CommandError):
                call_command("migrate_from_zero", "--name", 'x"; DROP DATABASE postgres; --', stdout=StringIO())


class ScratchNameFollowsTheConfiguredDatabase(SimpleTestCase):
    """Parallel worktrees each get their own database (scripts/worktree.sh). A fixed scratch
    name would let one worktree's `migrate_from_zero` drop another's scratch database in the
    middle of its run, so the default derives from the configured database instead. Added
    2026-09-19 with the worktree workflow."""

    def test_default_scratch_name_is_the_configured_name_plus_scratch(self) -> None:
        self.assertEqual(
            migrate_from_zero.default_scratch_name("postgres://u:p@db:5432/compliance_watch"),
            "compliance_watch_scratch",
        )
        self.assertEqual(
            migrate_from_zero.default_scratch_name("postgres://u:p@db:5432/compliance_watch_wt3"),
            "compliance_watch_wt3_scratch",
        )

    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch_wt3")
    def test_a_worktree_slot_migrates_its_own_scratch_database(self) -> None:
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=0)
        ):
            call_command("migrate_from_zero", stdout=StringIO())
        self.assertIn('CREATE DATABASE "compliance_watch_wt3_scratch" TEMPLATE template1', executed)
        self.assertNotIn('CREATE DATABASE "compliance_watch_scratch" TEMPLATE template1', executed)


class ExportOpenApi(SimpleTestCase):
    def test_writes_a_sorted_normalised_document(self) -> None:
        from django.conf import settings

        out = Path(settings.MEDIA_ROOT) / "openapi-test.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        stdout = StringIO()
        call_command("export_openapi", "--out", str(out), stdout=stdout)
        document = json.loads(out.read_text(encoding="utf-8"))
        self.assertIn("/api/v1/me", document["paths"])
        self.assertIn("/api/v1/reference/product", document["paths"])
        self.assertNotIn("servers", document)
        self.assertEqual(document["paths"]["/api/v1/me"]["get"]["responses"]["200"]["description"], "OK")
        self.assertEqual(list(document), sorted(document))
        from apps.shared.routes import iter_operations
        from config.api import api

        self.assertIn(f"{len(list(iter_operations(api)))} operations", stdout.getvalue())
        out.unlink()
