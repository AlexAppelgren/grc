from django.db import migrations, models

"""cases 0004 (chunk 10, `c10-case-triage-due`; COL-02): `change_case.triage_due_at`, when
triage is due, and its backfill for the cases still waiting for triage.

The backfill gives every open `new` case its opening time plus its own bank's
`triage_target_hours` (shared 0009). `change_case` is under forced row-level security, which
binds the schema owner too, so the update runs once per bank inside that bank's zone; a case
that already left `new` keeps a null, because reminders read the column only while a case is
`new`. It is a derived scheduling column, not a decision, so it writes no audit row."""

BACKFILL_SQL = """
DO $$
DECLARE bank record;
BEGIN
    FOR bank IN SELECT id, triage_target_hours FROM tenant LOOP
        PERFORM set_config('app.tenant_id', bank.id::text, true);
        UPDATE change_case
           SET triage_due_at = created_at + make_interval(hours => bank.triage_target_hours)
         WHERE status = 'new' AND triage_due_at IS NULL;
    END LOOP;
    PERFORM set_config('app.tenant_id', '', true);
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0003_evidence"),
        ("shared", "0009_tenant_workflow_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="changecase",
            name="triage_due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunSQL(sql=BACKFILL_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
