"""shared, squashed (review 2026-11-11 B-13): the extensions, the tenant, the audit and
outbox ledgers with their append-only triggers and two-zone policies, the trigger
functions every app attaches (append-only, outbox, library door) and the application
role's grants (playbook 14, AUD-01, INV-02, ADR 0058).

Every other app's first migration depends on this one, so the extensions exist before a
`citext` or `vector` column and the default privileges exist before any other table."""

import apps.shared.models
import django.contrib.postgres.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import (
    OUTBOX_GUARD_FUNCTION,
    append_only_function_operations,
    append_only_trigger_operations,
    extension_operations,
    grant_operations,
    library_door_function_operations,
    rls_operations,
)


class Migration(migrations.Migration):

    replaces = [
        ('shared', '0001_initial'),
    ]

    initial = True

    dependencies = [
    ]

    operations = [
        *extension_operations(),
        migrations.CreateModel(
            name='OutboxCursor',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50, unique=True)),
                ('last_created', models.DateTimeField(blank=True, null=True)),
                ('last_id', models.UUIDField(blank=True, null=True)),
                ('retry_not_before', models.DateTimeField(blank=True, null=True)),
                ('updated', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'outbox_cursor',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Tenant',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('slug', models.SlugField(max_length=80, unique=True)),
                ('timezone', models.CharField(default='Europe/Stockholm', max_length=64)),
                ('status', models.CharField(choices=[('active', 'active'), ('deactivated', 'deactivated')], default='active', max_length=16)),
                ('ai_enabled', models.BooleanField(default=True)),
                ('reminder_days_before', django.contrib.postgres.fields.ArrayField(base_field=models.PositiveSmallIntegerField(), default=apps.shared.models.default_reminder_days_before)),
                ('review_reminder_days_before', django.contrib.postgres.fields.ArrayField(base_field=models.PositiveSmallIntegerField(), default=apps.shared.models.default_review_reminder_days_before)),
                ('escalate_after_days', models.PositiveSmallIntegerField(default=apps.shared.models.default_escalate_after_days)),
                ('escalate_to_role', models.CharField(default=apps.shared.models.default_escalate_to_role, max_length=80)),
                ('digest_weekday', models.CharField(choices=[('monday', 'monday'), ('tuesday', 'tuesday'), ('wednesday', 'wednesday'), ('thursday', 'thursday'), ('friday', 'friday'), ('saturday', 'saturday'), ('sunday', 'sunday')], default=apps.shared.models.default_digest_weekday, max_length=16)),
                ('triage_target_hours', models.PositiveSmallIntegerField(default=apps.shared.models.default_triage_target_hours)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'tenant',
                'ordering': ['slug'],
                'constraints': [models.CheckConstraint(condition=models.Q(('reminder_days_before__contained_by', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90]), ('reminder_days_before__len__gte', 1), ('reminder_days_before__len__lte', 5)), name='tenant_reminder_days_before_valid'), models.CheckConstraint(condition=models.Q(('review_reminder_days_before__contained_by', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90]), ('review_reminder_days_before__len__gte', 1), ('review_reminder_days_before__len__lte', 5)), name='tenant_review_reminder_days_before_valid'), models.CheckConstraint(condition=models.Q(('escalate_after_days__gte', 1), ('escalate_after_days__lte', 90)), name='tenant_escalate_after_days_valid'), models.CheckConstraint(condition=models.Q(('triage_target_hours__gte', 1), ('triage_target_hours__lte', 720)), name='tenant_triage_target_hours_valid'), models.CheckConstraint(condition=models.Q(('digest_weekday__in', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])), name='tenant_digest_weekday_valid')],
            },
        ),
        migrations.CreateModel(
            name='AuditEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('actor_type', models.CharField(choices=[('user', 'user'), ('agent', 'agent'), ('system', 'system')], max_length=16)),
                ('actor_id', models.UUIDField(blank=True, null=True)),
                ('actor_label', models.CharField(blank=True, max_length=200)),
                ('action', models.CharField(max_length=100)),
                ('subject_type', models.CharField(max_length=64)),
                ('subject_id', models.UUIDField(blank=True, null=True)),
                ('subject_title', models.CharField(blank=True, max_length=500)),
                ('summary', models.CharField(blank=True, max_length=1000)),
                ('before', models.JSONField(blank=True, default=dict)),
                ('after', models.JSONField(blank=True, default=dict)),
                ('step_up_assertion_id', models.UUIDField(blank=True, null=True)),
                ('request_id', models.CharField(blank=True, max_length=128)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='audit_events', to='shared.tenant')),
            ],
            options={
                'db_table': 'audit_event',
                'ordering': ['created', 'id'],
                'indexes': [models.Index(fields=['tenant', 'created'], name='audit_event_tenant_created'), models.Index(fields=['subject_type', 'subject_id'], name='audit_event_subject')],
            },
        ),
        migrations.CreateModel(
            name='TenantContentLanguage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_language_links', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_content_language',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='OutboxEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('topic', models.CharField(max_length=100)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('last_error', models.CharField(blank=True, max_length=500)),
                ('audit_event', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='outbox_events', to='shared.auditevent')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='outbox_events', to='shared.tenant')),
            ],
            options={
                'db_table': 'outbox_event',
                'ordering': ['created', 'id'],
                'indexes': [models.Index(fields=['published_at', 'created'], name='outbox_event_pending'), models.Index(condition=models.Q(('published_at__isnull', True)), fields=['tenant', 'created', 'id'], name='outbox_event_zone_pending')],
            },
        ),
        *append_only_function_operations(),
        *library_door_function_operations(),
        *append_only_trigger_operations("audit_event"),
        *append_only_trigger_operations("outbox_event", function=OUTBOX_GUARD_FUNCTION),
        *rls_operations("audit_event", mixed=True),
        *rls_operations("outbox_event", mixed=True),
        *rls_operations("tenant_content_language"),
        *grant_operations(),
    ]
