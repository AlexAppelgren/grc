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


def rls_operations(
    table: str, *, mixed: bool = False, identity_lookup: bool = False
) -> list[migrations.RunSQL]:
    """ENABLE and FORCE row-level security and create the tenant policy on `table`.

    `mixed=True` is for tables that hold library rows (tenant_id NULL, visible to every
    tenant) beside tenant rows (visible to their tenant): audit_event, outbox_event,
    ai_generation, problem_report, api_key (playbook 14).

    `identity_lookup=True` adds the clause the auth layer needs on the four tables it
    reads before a tenant is known (apps/shared/tenancy.py, `identity_lookup()`):
    invitation, membership, user_session, api_key. The RLS guard pins that list.
    """
    if mixed:
        using = f"tenant_id IS NULL OR tenant_id = {TENANT_EXPRESSION}"
    else:
        using = f"tenant_id = {TENANT_EXPRESSION}"
    if identity_lookup:
        using = f"({using}) OR {IDENTITY_LOOKUP_EXPRESSION}"
    return [
        migrations.RunSQL(
            sql=f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=(
                f'CREATE POLICY {POLICY_NAME} ON "{table}" FOR ALL '
                f"USING ({using}) WITH CHECK ({using})"
            ),
            reverse_sql=f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"',
        ),
    ]


APPEND_ONLY_FUNCTION = "cw_append_only_guard"
OUTBOX_GUARD_FUNCTION = "cw_outbox_guard"
MAINTENANCE_SETTING = "cw.maintenance"

# The escape hatch: `SET LOCAL cw.maintenance = 'on'` inside the fixing transaction states
# the intent and is itself visible in the session's statement log.
_MAINTENANCE_CHECK = f"current_setting('{MAINTENANCE_SETTING}', true) = 'on'"


def append_only_function_operations() -> list[migrations.RunSQL]:
    """The trigger functions. Created once (shared 0001); later migrations attach them."""
    return [
        migrations.RunSQL(
            sql=f"""
CREATE OR REPLACE FUNCTION {APPEND_ONLY_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF {_MAINTENANCE_CHECK} THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% is append-only: % refused (set cw.maintenance to state a conscious fix)',
        TG_TABLE_NAME, TG_OP USING ERRCODE = 'raise_exception';
END;
$$;
""",
            reverse_sql=f"DROP FUNCTION IF EXISTS {APPEND_ONLY_FUNCTION}()",
        ),
        migrations.RunSQL(
            sql=f"""
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
""",
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
