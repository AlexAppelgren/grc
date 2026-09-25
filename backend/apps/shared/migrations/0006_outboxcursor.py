"""shared 0006 (chunk 5, ruling 9): `outbox_cursor`, the one ordered cursor over
`outbox_event` (apps/shared/outbox.py), and the index its scan reads.

One cursor row, created by the worker on its first pass. No row-level security and no
append-only trigger, deliberately: the table holds a position and a clock and no tenant
content, and the worker rewrites all three columns on every pass. The rows it points at
keep their own zone and their own trigger. cw_app reaches it through the default
privileges shared 0001 granted to cw_migrator's later tables.

`outbox_event_zone_pending` is the index behind the batch's per-zone scan: one read per
zone, oldest first, of the rows still pending. Partial on `published_at IS NULL`, so it
holds the backlog rather than the whole delivered history and shrinks again as rows are
marked; leading on `tenant_id`, because row-level security puts one zone's rows in front
of the scan at a time.

It sits behind 0005 rather than beside 0004: the hardening that split every mixed table's
write rule (0004, 0005) reached main first, and one leaf is the only shape the migration
graph is allowed to have.
"""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shared", "0005_append_only_hatch_allowlist")]

    operations = [
        migrations.CreateModel(
            name="OutboxCursor",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=50, unique=True)),
                ("last_created", models.DateTimeField(blank=True, null=True)),
                ("last_id", models.UUIDField(blank=True, null=True)),
                ("retry_not_before", models.DateTimeField(blank=True, null=True)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "outbox_cursor",
                "ordering": ["name"],
            },
        ),
        migrations.AddIndex(
            model_name="outboxevent",
            index=models.Index(
                condition=models.Q(("published_at__isnull", True)),
                fields=["tenant", "created", "id"],
                name="outbox_event_zone_pending",
            ),
        ),
    ]
