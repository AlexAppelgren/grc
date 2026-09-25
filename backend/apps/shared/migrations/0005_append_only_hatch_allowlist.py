"""shared 0005 (hardening, from the H-B review; INV-02): the hatch names the one role that
may use it.

shared 0003 refused the application role by name. That left the hatch to every other role
there will ever be, and to anything that arrives as another role: a SECURITY DEFINER
function owned by the migrator, or a cascading foreign key, runs with `current_user` set to
the owner. The check is now an allowlist on `session_user`, the role that authenticated,
which nothing inside a session changes: `cw.maintenance` counts for cw_migrator and for
nobody else.

Replaced in place, so every trigger already attached picks the new text up. Irreversible on
purpose, like 0003: going back would widen who holds the hatch, and the guard only ever
gets stronger.
"""

from django.db import migrations

from apps.shared.migration_helpers import APPEND_ONLY_FUNCTION_SQL, OUTBOX_GUARD_FUNCTION_SQL


class Migration(migrations.Migration):
    dependencies = [("shared", "0004_mixed_tables_write_their_own_zone")]

    operations = [
        migrations.RunSQL(sql=APPEND_ONLY_FUNCTION_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=OUTBOX_GUARD_FUNCTION_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
