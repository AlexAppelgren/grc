"""`manage.py migrate_from_zero`: drop and recreate a scratch database, then apply the
whole migration graph from nothing (playbook 9, Appendix D). This is what proves the
graph still applies, which `makemigrations --check` cannot see.

It connects as the migrator (MIGRATOR_DATABASE_URL, which has CREATEDB locally and in
CI, never in production) to the `postgres` maintenance database, drops and creates the
scratch database, and runs `manage.py migrate` in a subprocess whose DATABASE_URL and
MIGRATOR_DATABASE_URL both point at the scratch database. A subprocess because Django's
connection settings are read at import; changing them in-process is fragile.

`--name` picks the database (default: the scratch name) and `--keep` leaves it in place.
The E2E boot (frontend/tests/e2e/support/start-backend.sh) uses both to build the
throwaway E2E database that seed_e2e then fills and the server then serves, so one
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

SCRATCH_DB_NAME = "compliance_watch_scratch"


def _with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


class Command(BaseCommand):
    help = "Drop and recreate a scratch database and apply the whole migration graph."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--keep", action="store_true", help="Keep the database afterwards.")
        parser.add_argument(
            "--name",
            default=SCRATCH_DB_NAME,
            help=f"Database to drop, recreate and migrate (default {SCRATCH_DB_NAME}).",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        if settings.IS_DEPLOYED_ENVIRONMENT:
            raise CommandError("migrate_from_zero never runs on a deployed environment.")
        migrator_url = settings.MIGRATOR_DATABASE_URL
        name = str(options["name"])
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
