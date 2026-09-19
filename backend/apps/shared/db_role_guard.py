"""Boot guard for the database role (playbook 11.1 and 14, PRD AC-NFR2).

PostgreSQL lets three kinds of role skip row-level security policies: superusers, roles
with BYPASSRLS, and the owner of a table unless the table has FORCE ROW LEVEL SECURITY
(Verification_Log: PostgreSQL row security policies). The migrations force RLS on every
tenant table, but an app that connects as the owner or a superuser would still be one
`ALTER TABLE` away from reading every tenant. So the app refuses to start on any role
that is not the plain cw_app kind: not a superuser, owning no table in the public
schema, no BYPASSRLS.

`check_role(connection)` is the pure check and raises `RoleGuardError`.
`check_at_boot()` is what SharedConfig.ready() calls; it consults the settings that say
when the check is skipped (the test runner, and the commands that run as the migrator).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.backends.base.base import BaseDatabaseWrapper

logger = logging.getLogger(__name__)


class RoleGuardError(ImproperlyConfigured):
    """The connected database role can bypass row-level security."""


@dataclass(frozen=True)
class RoleFacts:
    role: str
    is_superuser: bool
    bypasses_rls: bool
    owned_tables: tuple[str, ...]

    @property
    def problems(self) -> list[str]:
        problems: list[str] = []
        if self.is_superuser:
            problems.append("is a superuser")
        if self.bypasses_rls:
            problems.append("has BYPASSRLS")
        if self.owned_tables:
            shown = ", ".join(self.owned_tables[:5])
            more = "" if len(self.owned_tables) <= 5 else f" and {len(self.owned_tables) - 5} more"
            problems.append(f"owns tables ({shown}{more})")
        return problems


def inspect_role(connection: BaseDatabaseWrapper) -> RoleFacts:
    """Read the facts about the connection's role from the catalog. Parameterised, ORM-free
    by necessity (playbook 11.2 allows raw SQL for exactly this kind of thing)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        role, is_superuser, bypasses_rls = cursor.fetchone()
        cursor.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tableowner = current_user ORDER BY tablename"
        )
        owned = tuple(row[0] for row in cursor.fetchall())
    return RoleFacts(
        role=role,
        is_superuser=bool(is_superuser),
        bypasses_rls=bool(bypasses_rls),
        owned_tables=owned,
    )


def check_role(connection: BaseDatabaseWrapper) -> RoleFacts:
    """Raise RoleGuardError unless the connection's role is a plain application role."""
    facts = inspect_role(connection)
    if facts.problems:
        raise RoleGuardError(
            f"Refusing to boot: database role {facts.role!r} {'; '.join(facts.problems)}. "
            "Row-level security means nothing for such a role (playbook 14). Point "
            "DATABASE_URL at cw_app; MIGRATOR_DATABASE_URL is for migrations only."
        )
    return facts


def _running_command() -> str | None:
    """The manage.py subcommand, if this process is one."""
    argv = sys.argv
    if len(argv) >= 2 and argv[0].endswith("manage.py"):
        return argv[1]
    return None


def check_at_boot() -> None:
    if not settings.DB_ROLE_GUARD_ENABLED:
        # Only config/test_settings.py sets this (override 2), and the reason is written
        # there. tests_production_guard.py proves the guard stays on everywhere else.
        return
    command = _running_command()
    if command in settings.DB_ROLE_GUARD_EXEMPT_COMMANDS:
        return
    facts = check_role(connections[DEFAULT_DB_ALIAS])
    logger.info("database role guard passed", extra={"role": facts.role})
