"""taxonomy 0009 (VOC-04, VOC-06, REG-03, TEN-03; INPUT_DELTAS §1): chunk 8's register
lists as tenant vocabulary rows. `gap_status` (kind `gap_category`), `gap_source`,
`risk_acceptance_reason` and `team` (with `email`), each with its label table, all under
forced row-level security. `team` also gets `UNIQUE (tenant_id, id)` in SQL, the way the
policies are written, so a team membership or a department can point at a team with a
composite key and the database refuses another tenant's team.

`risk_rating` gains its fixed kind (`risk_level`) with no schema change: a vocabulary's
`kind` column carries no database choices, and the tenant hook puts each system row's
level on it on the next `seed_reference`."""

import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import rls_operations

TENANT_TABLES = [
    "gap_status", "gap_status_label",
    "gap_source", "gap_source_label",
    "risk_acceptance_reason", "risk_acceptance_reason_label",
    "team", "team_label",
]


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0008_library_write_guard"),
        ("taxonomy", "0008_set_based_footprint"),
    ]

    operations = [
        migrations.CreateModel(
            name="GapSource",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key", models.SlugField(max_length=80)),
                ("kind", models.CharField(blank=True, max_length=40, null=True)),
                ("usage_note", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
                ("is_system", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "gap_source",
                "ordering": ["sort_order", "key"],
            },
        ),
        migrations.CreateModel(
            name="GapSourceLabel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("language", models.CharField(max_length=8)),
                ("text", models.CharField(max_length=200)),
                ("is_original", models.BooleanField(default=False)),
                ("is_machine", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
                (
                    "vocabulary",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="labels",
                        to="taxonomy.gapsource",
                    ),
                ),
            ],
            options={
                "db_table": "gap_source_label",
                "ordering": ["language"],
            },
        ),
        migrations.CreateModel(
            name="GapStatus",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key", models.SlugField(max_length=80)),
                ("kind", models.CharField(blank=True, max_length=40, null=True)),
                ("usage_note", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
                ("is_system", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "gap_status",
                "ordering": ["sort_order", "key"],
            },
        ),
        migrations.CreateModel(
            name="GapStatusLabel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("language", models.CharField(max_length=8)),
                ("text", models.CharField(max_length=200)),
                ("is_original", models.BooleanField(default=False)),
                ("is_machine", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
                (
                    "vocabulary",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="labels",
                        to="taxonomy.gapstatus",
                    ),
                ),
            ],
            options={
                "db_table": "gap_status_label",
                "ordering": ["language"],
            },
        ),
        migrations.CreateModel(
            name="RiskAcceptanceReason",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key", models.SlugField(max_length=80)),
                ("kind", models.CharField(blank=True, max_length=40, null=True)),
                ("usage_note", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
                ("is_system", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "risk_acceptance_reason",
                "ordering": ["sort_order", "key"],
            },
        ),
        migrations.CreateModel(
            name="RiskAcceptanceReasonLabel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("language", models.CharField(max_length=8)),
                ("text", models.CharField(max_length=200)),
                ("is_original", models.BooleanField(default=False)),
                ("is_machine", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
                (
                    "vocabulary",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="labels",
                        to="taxonomy.riskacceptancereason",
                    ),
                ),
            ],
            options={
                "db_table": "risk_acceptance_reason_label",
                "ordering": ["language"],
            },
        ),
        migrations.CreateModel(
            name="Team",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key", models.SlugField(max_length=80)),
                ("kind", models.CharField(blank=True, max_length=40, null=True)),
                ("usage_note", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("active", models.BooleanField(default=True)),
                ("is_system", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("email", models.EmailField(blank=True, max_length=254)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "team",
                "ordering": ["sort_order", "key"],
            },
        ),
        migrations.CreateModel(
            name="TeamLabel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("language", models.CharField(max_length=8)),
                ("text", models.CharField(max_length=200)),
                ("is_original", models.BooleanField(default=False)),
                ("is_machine", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shared.tenant",
                    ),
                ),
                (
                    "vocabulary",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="labels",
                        to="taxonomy.team",
                    ),
                ),
            ],
            options={
                "db_table": "team_label",
                "ordering": ["language"],
            },
        ),
        migrations.AddConstraint(
            model_name="gapsource",
            constraint=models.UniqueConstraint(
                fields=("tenant", "key"), name="gap_source_key_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="gapsourcelabel",
            constraint=models.UniqueConstraint(
                fields=("vocabulary", "language"), name="gap_source_label_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="gapstatus",
            constraint=models.UniqueConstraint(
                fields=("tenant", "key"), name="gap_status_key_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="gapstatuslabel",
            constraint=models.UniqueConstraint(
                fields=("vocabulary", "language"), name="gap_status_label_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="riskacceptancereason",
            constraint=models.UniqueConstraint(
                fields=("tenant", "key"), name="risk_acceptance_reason_key_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="riskacceptancereasonlabel",
            constraint=models.UniqueConstraint(
                fields=("vocabulary", "language"),
                name="risk_acceptance_reason_label_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                fields=("tenant", "key"), name="team_key_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="teamlabel",
            constraint=models.UniqueConstraint(
                fields=("vocabulary", "language"), name="team_label_unique"
            ),
        ),
        # Tenant tables: RLS enabled and forced, tenant policy (playbook 14).
        *[operation for table in TENANT_TABLES for operation in rls_operations(table)],
        migrations.RunSQL(
            sql='ALTER TABLE "team" ADD CONSTRAINT team_tenant_id_unique UNIQUE (tenant_id, id)',
            reverse_sql='ALTER TABLE "team" DROP CONSTRAINT IF EXISTS team_tenant_id_unique',
        ),
    ]
