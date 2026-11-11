"""`manage.py migrate_from_zero`: drop and recreate a scratch database, then apply the
whole migration graph from nothing (playbook 9, Appendix D), which `makemigrations --check`
cannot prove.

It connects as the migrator (CREATEDB locally and in CI, never in production) to the
`postgres` database, recreates the scratch database and runs `manage.py migrate` in a
subprocess pointed at it, since Django reads connection settings at import.

`--name` picks the database and `--keep` leaves it in place; the E2E boot uses both, so one
command owns "drop, recreate, migrate from zero" everywhere (playbook 8.3).

Refuses to run on a deployed environment: dropping databases is a local and CI act."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SCRATCH_SUFFIX = "_scratch"


def default_scratch_name(migrator_url: str) -> str:
    """The configured database's name plus `_scratch` (`compliance_watch_wt3_scratch` in
    worktree slot 3), so parallel worktrees never drop each other's scratch database."""
    name = urlsplit(migrator_url).path.lstrip("/") or "compliance_watch"
    return f"{name}{SCRATCH_SUFFIX}"


def _with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


class Command(BaseCommand):
    help = "Drop and recreate a scratch database and apply the whole migration graph."

    # System checks open the default connection, which fails before this command can create
    # a missing database; it uses the migrator connection itself.
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--keep", action="store_true", help="Keep the database afterwards.")
        parser.add_argument(
            "--name",
            default=None,
            help="Database to drop, recreate and migrate (default: the configured database's name + _scratch).",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        if settings.IS_DEPLOYED_ENVIRONMENT:
            raise CommandError("migrate_from_zero never runs on a deployed environment.")
        migrator_url = settings.MIGRATOR_DATABASE_URL
        name = str(options["name"] or default_scratch_name(migrator_url))
        if not name.replace("_", "").isalnum():
            raise CommandError(f"database name {name!r} must be letters, digits and underscores")
        maintenance_url = _with_database(migrator_url, "postgres")
        scratch_url = _with_database(migrator_url, name)

        self.stdout.write(f"recreating {name} ...")
        with psycopg.connect(maintenance_url, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            # template1 carries vector, citext and pg_trgm (infra/db/init.sql), so the
            # scratch database has them before the first migration runs.
            conn.execute(f'CREATE DATABASE "{name}" TEMPLATE template1')

        env = dict(os.environ)
        env["DATABASE_URL"] = scratch_url
        env["MIGRATOR_DATABASE_URL"] = scratch_url
        env["DJANGO_SETTINGS_MODULE"] = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings")
        result = subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput", "--settings=config.settings"],
            env=env,
            cwd=str(settings.BASE_DIR),
            check=False,
        )
        if result.returncode != 0:
            raise CommandError(f"migrate from zero failed with exit code {result.returncode}")
        self.stdout.write(self.style.SUCCESS("migration graph applies from zero"))

        if not options["keep"]:
            with psycopg.connect(maintenance_url, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
