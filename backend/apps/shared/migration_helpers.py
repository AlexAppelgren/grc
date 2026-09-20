"""Reusable migration operations for row-level security, append-only ledgers and the
application role's grants (playbook 14, INPUT_DELTAS §5). Every migration that creates a
tenant table appends `rls_operations(table)` from apps.shared.migration_helpers; the RLS guard checks the result in
`pg_class` and `pg_policies`.

This module reads no setting: a migration declares everything its operations need
inline (playbook 4.5). The role names are the ones infra/db/init.sql and
docs/runbooks/RAILWAY_DEPLOY.md create.
"""

from __future__ import annotations

from django.db import migrations

APP_ROLE = "cw_app"
MIGRATOR_ROLE = "cw_migrator"
POLICY_NAME = "tenant_isolation"
TENANT_SETTING = "app.tenant_id"

# NULLIF(...) because after a `SET LOCAL` the placeholder survives the transaction as an
# empty string on that session, and ''::uuid raises instead of matching nothing.
TENANT_EXPRESSION = f"NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"


IDENTITY_LOOKUP_SETTING = "app.identity_lookup"
IDENTITY_LOOKUP_EXPRESSION = f"current_setting('{IDENTITY_LOOKUP_SETTING}', true) = 'on'"

# Two zones in the database, not only in code (H15, NFR-01). `tenant_isolation` is the write
# rule: FOR ALL, matching the session's own zone and nothing else. Anything a table shows
# beyond that zone is a policy of its own and FOR SELECT, so permissive policies OR together
# into a mixed read and leave the write rule alone.
LIBRARY_READ_POLICY = "library_rows_visible"
IDENTITY_LOOKUP_POLICY = "identity_lookup_visible"
# Every policy name this module writes, which is what a replacement drops first.
POLICY_NAMES = (POLICY_NAME, LIBRARY_READ_POLICY, IDENTITY_LOOKUP_POLICY)


def _create_policy(table: str, name: str, command: str, using: str, *, with_check: str | None = None) -> migrations.RunSQL:
    check = f" WITH CHECK ({with_check})" if with_check else ""
    return migrations.RunSQL(
        sql=f'CREATE POLICY {name} ON "{table}" FOR {command} USING ({using}){check}',
        reverse_sql=_drop_policy_sql(table, name),
    )


def _drop_policy_sql(table: str, name: str) -> str:
    return f'DROP POLICY IF EXISTS {name} ON "{table}"'


def policy_operations(
    table: str,
    *,
    mixed: bool = False,
    identity_lookup: bool = False,
    library_fence: bool = False,
    column: str = "tenant_id",
) -> list[migrations.RunSQL]:
    """The policies of one tenant table: the write rule, then a read policy per widening.

    A mixed table's own zone is `IS NOT DISTINCT FROM`, because there the column is nullable
    and the library's rows are the zone of a session with no tenant; everywhere else the
    column is NOT NULL and `=` says the same thing.

    `library_fence=True` keeps the old shape, one FOR ALL policy whose write check is the read
    rule, on the two library tables mixed on `owner_tenant_id` (instrument, obligation). What
    stands between a bank session and a shared record there is the library fence itself
    (PRO-01): `library_write()` and its AST guard, with proposals the only door. Narrowing
    their write rule refuses every library write made with a tenant activated, which the
    reference seed, the E2E seed and most tests do, so it waits for the fence to name the zone
    of the row it is writing (HARDENING.md H16).
    """
    if library_fence:
        mixed_read = f"{column} IS NULL OR {column} = {TENANT_EXPRESSION}"
        return [_create_policy(table, POLICY_NAME, "ALL", mixed_read, with_check=mixed_read)]
    own_zone = f"{column} IS NOT DISTINCT FROM {TENANT_EXPRESSION}" if mixed else f"{column} = {TENANT_EXPRESSION}"
    operations = [_create_policy(table, POLICY_NAME, "ALL", own_zone, with_check=own_zone)]
    if mixed:
        operations.append(_create_policy(table, LIBRARY_READ_POLICY, "SELECT", f"{column} IS NULL"))
    if identity_lookup:
        operations.append(_create_policy(table, IDENTITY_LOOKUP_POLICY, "SELECT", IDENTITY_LOOKUP_EXPRESSION))
    return operations


def split_policy_operations(
    table: str, *, mixed: bool = False, identity_lookup: bool = False, column: str = "tenant_id"
) -> list[migrations.RunSQL]:
    """Replace whatever policies `table` carries with the split above (H15).

    The database an earlier migration left has one FOR ALL policy whose write check was the
    read rule: a bank session could insert, change or delete the platform's rows, and a
    lookup block could write anything. A database migrated from zero already has the split,
    because `rls_operations()` writes it now. So every policy is dropped IF EXISTS and
    written again from the same helper, which leaves both cases in one state.

    The drops do not come back on a reverse. Reversing then leaves a table with forced
    row-level security and no policy, which shows and accepts nothing; handing the other
    zone's rows back would be the one outcome worse than that.
    """
    drops = [
        migrations.RunSQL(sql=_drop_policy_sql(table, name), reverse_sql=migrations.RunSQL.noop)
        for name in POLICY_NAMES
    ]
    return [*drops, *policy_operations(table, mixed=mixed, identity_lookup=identity_lookup, column=column)]


def rls_operations(
    table: str,
    *,
    mixed: bool = False,
    identity_lookup: bool = False,
    library_fence: bool = False,
    column: str = "tenant_id",
) -> list[migrations.RunSQL]:
    """ENABLE and FORCE row-level security and create the policies on `table`.

    `mixed=True` is for tables that hold library rows (tenant_id NULL, readable by every
    tenant) beside tenant rows (readable by their tenant): audit_event, outbox_event,
    ai_generation, problem_report, api_key (playbook 14). Reading both zones is
    `library_rows_visible`; writing is the session's own zone either way. With
    `column="owner_tenant_id"` it is the "shared or mine" rule of the library tables that
    may hold a tenant-private record (instrument, obligation; INPUT_DELTAS §5, INV-07), where
    `library_fence=True` leaves the write rule as the read rule for now.

    `identity_lookup=True` adds the policy the auth layer needs on the four tables it reads
    before a tenant is known (apps/shared/tenancy.py, `identity_lookup()`): invitation,
    membership, user_session, api_key. It reads, and never writes, whatever tenant the row
    belongs to. The RLS guard pins that list.
    """
    return [
        migrations.RunSQL(
            sql=f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY',
        ),
        *policy_operations(
            table, mixed=mixed, identity_lookup=identity_lookup, library_fence=library_fence, column=column
        ),
    ]


APPEND_ONLY_FUNCTION = "cw_append_only_guard"
OUTBOX_GUARD_FUNCTION = "cw_outbox_guard"
MAINTENANCE_SETTING = "cw.maintenance"

# The escape hatch: `SET LOCAL cw.maintenance = 'on'` inside the fixing transaction states
# the intent and is itself visible in the session's statement log. It is the schema owner's
# alone. The application role may set the setting (nothing but a superuser could forbid
# that), so the guards ask who is running instead: the setting counts only for the migrator,
# and the ledger stays append-only for everyone else, which means one stray or injected
# `SET LOCAL` in request code switches nothing off.
#
# An allowlist, and on `session_user`, not a role to refuse and not `current_user` (H-B
# review): `current_user <> APP_ROLE` handed the hatch to every other role there will ever
# be, and to anything that changes `current_user` on the way in. `session_user` is the role
# that authenticated and no SET ROLE, SECURITY DEFINER function or cascading foreign key
# changes it (only SET SESSION AUTHORIZATION does, and that is a superuser's alone, which
# cw_app is not), so a request can only ever run under it as cw_app (Verification_Log:
# PostgreSQL 16, session information functions). Written from the role constants the grants
# below already use, so a renamed role cannot drift apart from a literal repeated here.
_MAINTENANCE_CHECK = (
    f"current_setting('{MAINTENANCE_SETTING}', true) = 'on' AND session_user = '{MIGRATOR_ROLE}'"
)

APPEND_ONLY_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {APPEND_ONLY_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF {_MAINTENANCE_CHECK} THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% is append-only: % refused (only a migration may set cw.maintenance to state a conscious fix)',
        TG_TABLE_NAME, TG_OP USING ERRCODE = 'raise_exception';
END;
$$;
"""

OUTBOX_GUARD_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {OUTBOX_GUARD_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF {_MAINTENANCE_CHECK} THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'outbox_event is append-only: DELETE refused' USING ERRCODE = 'raise_exception';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.audit_event_id IS DISTINCT FROM OLD.audit_event_id
       OR NEW.topic IS DISTINCT FROM OLD.topic
       OR NEW.payload IS DISTINCT FROM OLD.payload
       OR NEW.created IS DISTINCT FROM OLD.created THEN
        RAISE EXCEPTION 'outbox_event payload is append-only: only delivery state may change'
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$;
"""


def append_only_function_operations() -> list[migrations.RunSQL]:
    """The trigger functions. Created once (shared 0001) and replaced in place whenever their
    text changes (shared 0003, then shared 0005); the migrations in between attach them to
    tables, and a replacement reaches every trigger already attached."""
    return [
        migrations.RunSQL(
            sql=APPEND_ONLY_FUNCTION_SQL,
            reverse_sql=f"DROP FUNCTION IF EXISTS {APPEND_ONLY_FUNCTION}()",
        ),
        migrations.RunSQL(
            sql=OUTBOX_GUARD_FUNCTION_SQL,
            reverse_sql=f"DROP FUNCTION IF EXISTS {OUTBOX_GUARD_FUNCTION}()",
        ),
    ]


def append_only_trigger_operations(table: str, *, function: str = APPEND_ONLY_FUNCTION) -> list[migrations.RunSQL]:
    trigger = f"{table}_append_only"
    return [
        migrations.RunSQL(
            sql=(
                f'CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON "{table}" '
                f"FOR EACH ROW EXECUTE FUNCTION {function}()"
            ),
            reverse_sql=f'DROP TRIGGER IF EXISTS {trigger} ON "{table}"',
        )
    ]


def grant_operations() -> list[migrations.RunSQL]:
    """Give cw_app the table privileges it needs, now and for every later table. Never
    ownership, never TRUNCATE (which would bypass the row triggers)."""
    return [
        migrations.RunSQL(
            sql=f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
            reverse_sql=f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}",
        ),
        migrations.RunSQL(
            sql=f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
            reverse_sql=f"REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}",
        ),
        migrations.RunSQL(
            sql=f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
            reverse_sql=f"REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}",
        ),
        migrations.RunSQL(
            sql=(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR_ROLE} IN SCHEMA public "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
            ),
            reverse_sql=(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR_ROLE} IN SCHEMA public "
                f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
            ),
        ),
        migrations.RunSQL(
            sql=(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR_ROLE} IN SCHEMA public "
                f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
            ),
            reverse_sql=(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR_ROLE} IN SCHEMA public "
                f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
            ),
        ),
    ]


def extension_operations() -> list[migrations.RunSQL]:
    """vector, citext, pg_trgm. Already present locally (init.sql on template1) and on
    Railway (runbook); IF NOT EXISTS makes this a no-op there and a guarantee elsewhere."""
    return [
        migrations.RunSQL(
            sql=f"CREATE EXTENSION IF NOT EXISTS {name}",
            reverse_sql=migrations.RunSQL.noop,
        )
        for name in ("vector", "citext", "pg_trgm")
    ]
