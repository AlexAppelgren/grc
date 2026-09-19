"""shared 0001: extensions, tenant, audit_event, outbox_event, the append-only triggers,
the mixed-table policies and the application role's grants (playbook 14, AUD-01).

Hand-written on top of the generated model operations so the RunSQL parts sit beside the
tables they govern and every one has reverse SQL."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import (
    OUTBOX_GUARD_FUNCTION,
    append_only_function_operations,
    append_only_trigger_operations,
    extension_operations,
    grant_operations,
    rls_operations,
)


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        *extension_operations(),
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("timezone", models.CharField(default="Europe/Stockholm", max_length=64)),
                ("created", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "tenant", "ordering": ["slug"]},
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "actor_type",
                    models.CharField(
                        choices=[("user", "user"), ("agent", "agent"), ("system", "system")], max_length=16
                    ),
                ),
                ("actor_id", models.UUIDField(blank=True, null=True)),
                ("actor_label", models.CharField(blank=True, max_length=200)),
                ("action", models.CharField(max_length=100)),
                ("subject_type", models.CharField(max_length=64)),
                ("subject_id", models.UUIDField(blank=True, null=True)),
                ("subject_title", models.CharField(blank=True, max_length=500)),
                ("summary", models.CharField(blank=True, max_length=1000)),
                ("before", models.JSONField(blank=True, default=dict)),
                ("after", models.JSONField(blank=True, default=dict)),
                ("step_up_assertion_id", models.UUIDField(blank=True, null=True)),
                ("request_id", models.CharField(blank=True, max_length=128)),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_events",
                        to="shared.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "audit_event",
                "ordering": ["created", "id"],
                "indexes": [
                    models.Index(fields=["tenant", "created"], name="audit_event_tenant_created"),
                    models.Index(fields=["subject_type", "subject_id"], name="audit_event_subject"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OutboxEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("topic", models.CharField(max_length=100)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                (
                    "audit_event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="outbox_events",
                        to="shared.auditevent",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="outbox_events",
                        to="shared.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "outbox_event",
                "ordering": ["created", "id"],
                "indexes": [models.Index(fields=["published_at", "created"], name="outbox_event_pending")],
            },
        ),
        # Ledgers: the trigger makes AppendOnlyModel's docstring true for every client.
        *append_only_function_operations(),
        *append_only_trigger_operations("audit_event"),
        *append_only_trigger_operations("outbox_event", function=OUTBOX_GUARD_FUNCTION),
        # Mixed tables: library rows (tenant_id NULL) to everyone, tenant rows to their tenant.
        *rls_operations("audit_event", mixed=True),
        *rls_operations("outbox_event", mixed=True),
        # The application role's privileges, now and by default for every later table.
        *grant_operations(),
    ]
