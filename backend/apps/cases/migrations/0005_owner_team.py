import django.db.models.deletion
from django.db import migrations, models

"""cases 0005 (chunk 9, `c9-owner-team-and-reassign`; CAS-02, TEN-03): `change_case.owner_team`,
a team of the bank beside the person who owns the case.

PostgreSQL checks a foreign key without row-level security, so the team is also a composite
key `(tenant_id, owner_team_id)` into `team (tenant_id, id)`: the database refuses another
bank's team whatever the code does (INPUT_DELTAS §1). Nullable, with no backfill: no case
has a team until a triage names one."""

NAME = "change_case_owner_team_id_same_tenant"


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0004_triage_due_at"),
        ("taxonomy", "0009_register_lists"),
    ]

    operations = [
        migrations.AddField(
            model_name="changecase",
            name="owner_team",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="taxonomy.team"
            ),
        ),
        migrations.RunSQL(
            sql=f'ALTER TABLE "change_case" ADD CONSTRAINT {NAME} FOREIGN KEY (tenant_id, owner_team_id) REFERENCES "team" (tenant_id, id)',
            reverse_sql=f'ALTER TABLE "change_case" DROP CONSTRAINT IF EXISTS {NAME}',
        ),
    ]
