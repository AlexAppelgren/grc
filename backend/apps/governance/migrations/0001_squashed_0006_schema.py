"""governance, squashed (review 2026-11-11 B-13): the AI generation log, tenant reach and
the access log of the agents a bank runs itself.

- `ai_generation` is mixed (AUD-02): a row without a tenant is the platform's. Every bank
  reads those, except an `agent_review`, a confirming agent's decision on another agent's
  work, which is about the queue, where a bank sees only what it filed itself (PRO-02,
  D-80). The platform still reads it through `tenant_isolation`.
- Tenant reach and its requests (ACC-08, D-72, ADR 0057): the person deciding a request is
  never the one who made it, in the words the four-eyes guard reads back.
- `agent_access_call` (ACC-08) is append-only; only the D-53 purge deletes a row, whole, as
  the schema owner.
- PostgreSQL checks a foreign key without row-level security, so every reference to a
  person is a composite key into `membership (tenant_id, user_id)`, and a reach row's
  request and a call's entry are their own bank's."""

import django.contrib.postgres.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import (
    LIBRARY_READ_POLICY,
    append_only_trigger_operations,
    rls_operations,
    same_tenant_key,
    tenant_id_unique,
)

# (table, column, target table, target column)
COMPOSITE_KEYS = (
    ("tenant_reach_request", "requested_by_id", "membership", "user_id"),
    ("tenant_reach_request", "decided_by_id", "membership", "user_id"),
    ("tenant_reach", "changed_by_id", "membership", "user_id"),
    ("tenant_reach", "request_id", "tenant_reach_request", "id"),
    ("agent_access_call", "agent_access_id", "agent_access", "id"),
    ("agent_access_call", "acting_user_id", "membership", "user_id"),
)


class Migration(migrations.Migration):

    replaces = [
        ('governance', '0001_ai_generation'),
        ('governance', '0002_ai_purpose_agent_review'),
        ('governance', '0003_ai_generation_stop_reason'),
        ('governance', '0004_tenant_reach'),
        ('governance', '0005_agent_access_call'),
        ('governance', '0006_ai_purpose_what_applies'),
    ]

    initial = True

    dependencies = [
        ('agents', '0002_squashed_0009_links_and_rules'),
        ('identity', '0002_squashed_0011_links_and_rules'),
        ('shared', '0002_squashed_0010_links_and_rules'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantReachRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('pending', 'pending'), ('approved', 'approved'), ('rejected', 'rejected'), ('withdrawn', 'withdrawn')], default='pending', max_length=16)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_reach_request',
                'ordering': ['-requested_at', 'id'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('status', 'pending')), fields=('tenant',), name='tenant_reach_request_one_pending'), models.CheckConstraint(condition=models.Q(models.Q(('decided_at__isnull', True), ('decided_by__isnull', True)), models.Q(('decided_at__isnull', False), ('decided_by__isnull', False)), _connector='OR'), name='tenant_reach_request_decision_names_a_person')],
            },
        ),
        migrations.CreateModel(
            name='TenantReach',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('enabled', models.BooleanField(default=False)),
                ('changed_at', models.DateTimeField(blank=True, null=True)),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='governance.tenantreachrequest')),
            ],
            options={
                'db_table': 'tenant_reach',
                'ordering': ['tenant'],
                'constraints': [models.UniqueConstraint(fields=('tenant',), name='tenant_reach_one_row')],
            },
        ),
        migrations.CreateModel(
            name='AgentAccessCall',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tool', models.CharField(max_length=120)),
                ('filters', models.JSONField(blank=True, default=dict)),
                ('record_count', models.PositiveIntegerField(blank=True, null=True)),
                ('scopes', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=32), blank=True, default=list)),
                ('scope_narrowed', models.BooleanField(default=False)),
                ('scope_terms', models.JSONField(blank=True, default=dict)),
                ('duration_ms', models.PositiveIntegerField()),
                ('status', models.PositiveSmallIntegerField()),
                ('at', models.DateTimeField(auto_now_add=True)),
                ('acting_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('agent_access', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agentaccess')),
                ('api_key', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'agent_access_call',
                'ordering': ['-at', '-id'],
                'indexes': [models.Index(fields=['tenant', 'agent_access', '-at'], name='agent_access_call_entry_idx')],
            },
        ),
        migrations.CreateModel(
            name='AiGeneration',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('purpose', models.CharField(choices=[('so_what', 'so_what'), ('change_summary', 'change_summary'), ('scope_suggestion', 'scope_suggestion'), ('link_suggestion', 'link_suggestion'), ('translation', 'translation'), ('answer', 'answer'), ('agent_review', 'agent_review'), ('what_applies', 'what_applies')], max_length=32)),
                ('subject_type', models.CharField(blank=True, max_length=32)),
                ('subject_id', models.UUIDField(blank=True, null=True)),
                ('model', models.CharField(max_length=200)),
                ('model_version', models.CharField(blank=True, max_length=120)),
                ('model_metadata_reported_by_agent', models.BooleanField(default=False)),
                ('prompt_template', models.CharField(blank=True, max_length=200)),
                ('prompt_hash', models.CharField(blank=True, max_length=128)),
                ('output', models.TextField(blank=True)),
                ('citations', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('draft', 'draft'), ('confirmed', 'confirmed'), ('edited', 'edited'), ('rejected', 'rejected')], default='draft', max_length=16)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('input_tokens', models.PositiveIntegerField(default=0)),
                ('output_tokens', models.PositiveIntegerField(default=0)),
                ('stop_reason', models.CharField(blank=True, max_length=64)),
                ('cost_minor', models.PositiveIntegerField(default=0)),
                ('feedback', models.CharField(blank=True, max_length=16)),
                ('feedback_note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('agent_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='generations', to='agents.agentrun')),
                ('asker', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'ai_generation',
                'ordering': ['-created_at', 'id'],
                'indexes': [models.Index(fields=['subject_type', 'subject_id'], name='ai_generation_subject_idx'), models.Index(fields=['tenant', '-created_at'], name='ai_generation_tenant_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('reviewed_at__isnull', True), ('reviewed_by__isnull', True)), models.Q(('reviewed_at__isnull', False), ('reviewed_by__isnull', False)), _connector='OR'), name='ai_generation_review_names_a_person'), models.CheckConstraint(condition=models.Q(models.Q(('purpose', 'agent_review'), _negated=True), models.Q(('agent_run__isnull', False), ('model_metadata_reported_by_agent', True), ('subject_id__isnull', False), models.Q(('subject_type', ''), _negated=True)), _connector='OR'), name='ai_generation_agent_review_names_its_run')],
            },
        ),
        *rls_operations("ai_generation", mixed=True),
        migrations.RunSQL(
            sql=f"ALTER POLICY {LIBRARY_READ_POLICY} ON \"ai_generation\" USING (tenant_id IS NULL AND purpose <> 'agent_review')",
            reverse_sql=f'ALTER POLICY {LIBRARY_READ_POLICY} ON "ai_generation" USING (tenant_id IS NULL)',
        ),
        *rls_operations("tenant_reach_request"),
        *rls_operations("tenant_reach"),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE tenant_reach_request ADD CONSTRAINT tenant_reach_request_four_eyes "
                "CHECK (decided_by_id IS NULL OR decided_by_id <> requested_by_id)"
            ),
            reverse_sql="ALTER TABLE tenant_reach_request DROP CONSTRAINT IF EXISTS tenant_reach_request_four_eyes",
        ),
        tenant_id_unique("tenant_reach_request"),
        *rls_operations("agent_access_call"),
        *append_only_trigger_operations("agent_access_call"),
        *[same_tenant_key(*key) for key in COMPOSITE_KEYS],
    ]
