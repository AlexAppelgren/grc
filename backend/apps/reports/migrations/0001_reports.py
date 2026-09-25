"""Export jobs (REP-02, CAS-07): one tenant table under enabled and forced row-level
security. Import jobs are chunk 12's (REP-03) and not here."""

import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import rls_operations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("identity", "0005_login_event_key_created_and_withheld"),
        ("shared", "0008_library_write_guard"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExportJob",
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
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("case_file", "case_file"),
                            ("cases", "cases"),
                            ("committee_pack", "committee_pack"),
                            ("inventory", "inventory"),
                            ("changes", "changes"),
                            ("audit_log", "audit_log"),
                            ("configuration", "configuration"),
                            ("tenant_export", "tenant_export"),
                        ],
                        max_length=32,
                    ),
                ),
                ("subject_id", models.UUIDField(blank=True, null=True)),
                (
                    "format",
                    models.CharField(
                        choices=[
                            ("pdf", "pdf"),
                            ("txt", "txt"),
                            ("json", "json"),
                            ("xlsx", "xlsx"),
                            ("csv", "csv"),
                        ],
                        max_length=8,
                    ),
                ),
                ("filters", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "queued"),
                            ("running", "running"),
                            ("succeeded", "succeeded"),
                            ("failed", "failed"),
                        ],
                        default="queued",
                        max_length=16,
                    ),
                ),
                (
                    "storage_key",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "content_hash",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("downloaded_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="identity.user",
                    ),
                ),
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
                "db_table": "export_job",
                "ordering": ["-created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "-created_at"],
                        name="export_job_tenant_newest_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("status", "succeeded"), _negated=True),
                            models.Q(
                                ("completed_at__isnull", False),
                                ("content_hash__isnull", False),
                                ("expires_at__isnull", False),
                                ("storage_key__isnull", False),
                            ),
                            _connector="OR",
                        ),
                        name="export_job_succeeded_has_a_file",
                    )
                ],
            },
        ),
        *rls_operations("export_job"),
    ]
