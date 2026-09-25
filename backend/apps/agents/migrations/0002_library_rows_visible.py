"""agents 0002 (hardening H15): agent_run's read policy takes the shared name.

agent_run has written only its own zone since the E5 fix, with `library_runs_visible`
beside the write rule. Every mixed table now has that split, from
`apps.shared.migration_helpers`, under the name `library_rows_visible`; renaming this one
means the RLS guard can demand one shape for all of them instead of an exception for the
table that got there first.
"""

from django.db import migrations

from apps.shared.migration_helpers import LIBRARY_READ_POLICY


class Migration(migrations.Migration):
    dependencies = [("agents", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=f'ALTER POLICY library_runs_visible ON "agent_run" RENAME TO {LIBRARY_READ_POLICY}',
            reverse_sql=f'ALTER POLICY {LIBRARY_READ_POLICY} ON "agent_run" RENAME TO library_runs_visible',
        )
    ]
