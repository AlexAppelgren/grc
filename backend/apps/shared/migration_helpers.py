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
    stands between a bank session and a shared record there is the library fence (PRO-01):
    `library_write()` and its AST guard in Python, and in the database the door trigger below,
    which refuses the app role's write to either table unless an approved proposal, the
    re-verification stamp or a reference seed opened a door (H16, shared 0008, ADR 0058).
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

    `identity_lookup=True` adds the policy needed on the five tables read before a tenant is
    known (apps/shared/tenancy.py, `identity_lookup()`): invitation, membership,
    user_session, api_key and calendar_feed, whose token arrives with no session and no key
    at all (D-52). It reads, and never writes, whatever tenant the row belongs to. The RLS
    guard pins that list.
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


LIBRARY_DOOR_FUNCTION = "cw_library_door_guard"
LIBRARY_DOOR_SETTING = "cw.library_door"

# The doors each library-zone table accepts (H16, ADR 0058), passed to the trigger as its
# arguments. The inventory and the library vocabularies change through an approved proposal
# or a reference seed; the re-verification stamp reaches the obligation and its verification
# rows and nothing else (INV-06); the watch door reaches the seven watch tables only (D-64);
# the index door reaches the search index only (D-65); the evaluation door reaches the
# search evaluation set and its runs only, the platform staff's own test of search that no
# proposal carries (search 0003). The library app's reference rows change through a
# reference seed alone: `language`, which every bank reads and no proposal writes. The
# jurisdiction rows and their labels take the inventory's doors since shared 0010, because a
# jurisdiction is relabelled, retired and restored through a proposal (D-94).
INVENTORY_DOORS = ("proposal", "seed")
STAMPED_DOORS = ("proposal", "reverification", "seed")
WATCH_DOORS = ("watch",)
INDEX_DOORS = ("index",)
EVAL_DOORS = ("eval",)
REFERENCE_DOORS = ("seed",)

# One trigger per library-zone table, per statement and before it, so it fires once however
# many rows the statement touches, and fires for a statement that touches none: a write
# outside a door is refused as a write, not only when it finds a row. TRUNCATE is included
# although cw_app holds no TRUNCATE grant, so the rule does not rest on the grant alone.
#
# The door is a setting the app role sets itself, through `library_door()` in
# apps/shared/tenancy.py, so this refuses a write that never entered a door — an ORM call
# that bypassed the Python fence, raw SQL, a cascade — and not a statement that sets the
# setting first (ADR 0058 says what that leaves to the lint and the AST guards). The schema
# owner passes by `session_user`, as `_MAINTENANCE_CHECK` recognises it, so a migration's
# data step, the E2E seed and tenant exit are not refused; never `current_user`, which a
# SECURITY DEFINER function or a cascade changes (shared 0005).
LIBRARY_DOOR_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {LIBRARY_DOOR_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    door text := current_setting('{LIBRARY_DOOR_SETTING}', true);
BEGIN
    IF session_user = '{MIGRATOR_ROLE}' OR door = ANY (TG_ARGV) THEN
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'library door: % on % refused: the door open is %, and % accepts only %. A library row changes only through a door (PRO-01, ADR 0058).',
        TG_OP, TG_TABLE_NAME, coalesce(nullif(door, ''), 'none'), TG_TABLE_NAME, array_to_string(TG_ARGV, ', ')
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def library_door_function_operations() -> list[migrations.RunSQL]:
    """The trigger function (shared 0008). A later change to its text replaces it in place
    in a migration of its own, which reaches every trigger already attached."""
    return [
        migrations.RunSQL(
            sql=LIBRARY_DOOR_FUNCTION_SQL,
            reverse_sql=f"DROP FUNCTION IF EXISTS {LIBRARY_DOOR_FUNCTION}()",
        )
    ]


def library_door_trigger_operations(table: str, doors: tuple[str, ...]) -> list[migrations.RunSQL]:
    """Attach the door trigger to `table`, accepting `doors`. The migration that creates a
    library-zone table calls this for it; apps/shared/tests_library_db_guard.py fails for a
    library table without it and for one whose doors are not the ones its kind accepts."""
    trigger = f"{table}_library_door"
    arguments = ", ".join(f"'{door}'" for door in doors)
    return [
        migrations.RunSQL(
            sql=(
                f'CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON "{table}" '
                f"FOR EACH STATEMENT EXECUTE FUNCTION {LIBRARY_DOOR_FUNCTION}({arguments})"
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
