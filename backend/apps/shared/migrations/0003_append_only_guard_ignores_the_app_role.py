"""shared 0003 (hardening H11, INV-02): the append-only guard the application role cannot
switch off. `SET LOCAL cw.maintenance = 'on'` used to work for whoever ran it, so one
stray or injected `SET LOCAL` in request code would have made every ledger writable for
the rest of that transaction, with a source lint the only thing in the way. Both guard
functions now ignore the setting when they run as cw_app; the schema owner keeps the hatch
for the fix a migration states out loud.

Replaced in place, so every trigger already attached picks the new text up. Irreversible on
purpose: going back would hand the hatch to the application role again, and the guard only
ever gets stronger.
"""

from django.db import migrations

from apps.shared.migration_helpers import APPEND_ONLY_FUNCTION_SQL, OUTBOX_GUARD_FUNCTION_SQL


class Migration(migrations.Migration):
    dependencies = [("shared", "0002_tenant_profile")]

    operations = [
        migrations.RunSQL(sql=APPEND_ONLY_FUNCTION_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=OUTBOX_GUARD_FUNCTION_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
