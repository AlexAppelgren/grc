from django.db import migrations, models

"""identity 0011 (D-123, ADM-S19): `invitation.first_administrator`, the invitation the console
sent a bank's first administrator when it created the bank, which the console's tenant list
shows.

The backfill marks, in each bank, its earliest invitation when nobody in the bank sent it and
it is an invitation to join: before a bank has a member, only the platform can invite anyone,
so that one is its first administrator's. `invitation` is under forced row-level security,
which binds the schema owner too, so the update runs once per bank inside that bank's zone. It
is a derived mark on the platform's own act, not a decision, so it writes no audit row."""

BACKFILL_SQL = """
DO $$
DECLARE bank record;
BEGIN
    FOR bank IN SELECT id FROM tenant LOOP
        PERFORM set_config('app.tenant_id', bank.id::text, true);
        UPDATE invitation
           SET first_administrator = true
         WHERE id = (
               SELECT first.id FROM invitation AS first
                WHERE first.tenant_id = bank.id
                ORDER BY first.created_at, first.id
                LIMIT 1
         )
           AND invited_by_id IS NULL
           AND kind = 'invite';
    END LOOP;
    PERFORM set_config('app.tenant_id', '', true);
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0010_login_event_access_token_refused"),
    ]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="first_administrator",
            field=models.BooleanField(default=False),
        ),
        migrations.RunSQL(sql=BACKFILL_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
