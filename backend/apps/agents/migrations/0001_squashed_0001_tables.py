"""agents, squashed (review 2026-11-11 B-13): the agent tables with their final fields,
their keys to the tenant, and the rules that read only agents' and shared's tables. 0002
adds the links to other apps' tables and the rules that read them.

- `agent` is a library table behind the inventory's doors (ADR 0058); its key and its scope
  never change (playbook 4.3, ADR 0053), so a bank's agent never becomes one of bleqq's.
- `agent_version` is behind the same doors and append-only: a run points at the version it
  opened with, so nothing of a published version changes except `retired_at`, once (AGT-03,
  D-54). The schema owner's maintenance hatch is the ledgers' one.
- A run's `agent_version_id` is written when the run opens and never changes.
- `tenant_agent` and `tenant_agent_budget` hold one bank's rows (AGT-04, AGT-05, ADR 0053).
  A trigger refuses a `tenant_agent` on a definition that is one of bleqq's or not
  tenant-configurable, whoever writes it, and refuses a delete: an agent a bank stops is
  paused, never deleted.
- `research_request` is mixed like `agent_run`: a bank's request lives in its zone, the
  console's `retag` in the library's, and each zone writes only its own rows.
- The agent access entries a bank registers for agents on its own infrastructure, with
  their departments and products (ACC-01, ACC-02, D-70, ADR 0055), hold one bank's rows.
- PostgreSQL checks a foreign key without row-level security, so a request, a run and an
  entry's departments and products reach `tenant_agent` and `agent_access` through
  composite `(tenant_id, …)` keys as well."""

import django.contrib.postgres.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import (
    INVENTORY_DOORS,
    MAINTENANCE_SETTING,
    MIGRATOR_ROLE,
    append_only_trigger_operations,
    library_door_trigger_operations,
    rls_operations,
    same_tenant_key,
    tenant_id_unique,
)

MAINTENANCE = f"current_setting('{MAINTENANCE_SETTING}', true) = 'on' AND session_user = '{MIGRATOR_ROLE}'"

AGENT_GUARD_SQL = """
CREATE FUNCTION cw_agent_key_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.key IS DISTINCT FROM OLD.key THEN
        RAISE EXCEPTION 'agent.key never changes: % refused', NEW.key USING ERRCODE = 'raise_exception';
    END IF;
    IF NEW.scope IS DISTINCT FROM OLD.scope THEN
        RAISE EXCEPTION 'agent.scope never changes: % refused', NEW.key USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER agent_key_immutable BEFORE UPDATE ON "agent" FOR EACH ROW EXECUTE FUNCTION cw_agent_key_guard();
"""

VERSION_GUARD_SQL = f"""
CREATE FUNCTION cw_agent_version_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF {MAINTENANCE} THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'agent_version is append-only: DELETE refused' USING ERRCODE = 'raise_exception';
    END IF;
    IF OLD.retired_at IS NOT NULL OR to_jsonb(NEW) - 'retired_at' IS DISTINCT FROM to_jsonb(OLD) - 'retired_at' THEN
        RAISE EXCEPTION 'agent_version is append-only: only retiring a version, once, is allowed'
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$;
"""

RUN_VERSION_GUARD_SQL = """
CREATE FUNCTION cw_agent_run_version_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.agent_version_id IS DISTINCT FROM OLD.agent_version_id THEN
        RAISE EXCEPTION 'agent_run.agent_version_id is written when the run opens and never changes'
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER agent_run_version_written_once BEFORE UPDATE ON "agent_run"
    FOR EACH ROW EXECUTE FUNCTION cw_agent_run_version_guard();
"""


TENANT_AGENT_FENCE_SQL = f"""
CREATE FUNCTION cw_tenant_agent_fence() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF {MAINTENANCE} THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'tenant_agent is paused, never deleted: DELETE refused' USING ERRCODE = 'raise_exception';
    END IF;
    IF (TG_OP = 'INSERT' OR NEW.agent_id IS DISTINCT FROM OLD.agent_id) AND NOT EXISTS (
        SELECT 1 FROM agent a WHERE a.id = NEW.agent_id AND a.scope = 'tenant' AND a.tenant_configurable
    ) THEN
        RAISE EXCEPTION 'tenant_agent refused: agent % is one of bleqq''s agents or not tenant-configurable (ADR 0053)',
            NEW.agent_id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tenant_agent_fence BEFORE INSERT OR UPDATE OR DELETE ON "tenant_agent"
    FOR EACH ROW EXECUTE FUNCTION cw_tenant_agent_fence();
"""


TENANT_TABLES = ("tenant_agent", "tenant_agent_budget", "agent_access", "agent_access_department", "agent_access_product")


class Migration(migrations.Migration):

    replaces = [
        ('agents', '0001_initial'),
    ]

    initial = True

    dependencies = [
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='Agent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80, unique=True)),
                ('kind', models.CharField(choices=[('research', 'research'), ('backfill', 'backfill'), ('reverify', 'reverify'), ('watch', 'watch'), ('review', 'review')], max_length=16)),
                ('description', models.TextField(blank=True)),
                ('active', models.BooleanField(default=False)),
                ('current_version', models.PositiveIntegerField()),
                ('scope', models.CharField(choices=[('platform', 'platform'), ('tenant', 'tenant')], default='platform', max_length=16)),
                ('tenant_configurable', models.BooleanField(default=False)),
                ('runtime', models.CharField(choices=[('agent_sdk', 'agent_sdk'), ('managed_agents', 'managed_agents'), ('routine', 'routine')], default='agent_sdk', max_length=16)),
                ('default_cadence', models.CharField(choices=[('daily', 'daily'), ('weekly', 'weekly'), ('monthly', 'monthly'), ('manual', 'manual')], default='weekly', max_length=16)),
                ('writes_to', models.CharField(choices=[('library', 'library'), ('tenant', 'tenant')], default='library', max_length=16)),
                ('platform_scope', models.JSONField(blank=True, null=True)),
                ('platform_monthly_budget', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
            ],
            options={
                'db_table': 'agent',
                'ordering': ['key'],
                'constraints': [models.CheckConstraint(condition=models.Q(('scope', 'platform'), ('tenant_configurable', True), _negated=True), name='agent_platform_not_tenant_configurable'), models.CheckConstraint(condition=models.Q(models.Q(('scope', 'tenant'), _negated=True), models.Q(('platform_monthly_budget__isnull', True), ('platform_scope__isnull', True), ('writes_to', 'tenant')), _connector='OR'), name='agent_tenant_carries_no_platform_settings')],
            },
        ),
        migrations.CreateModel(
            name='AgentAccess',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('purpose', models.TextField()),
                ('tenant_reach', models.BooleanField(default=False)),
                ('active', models.BooleanField(default=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'agent_access',
                'ordering': ['name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='AgentAccessDepartment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('agent_access', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='departments', to='agents.agentaccess')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'agent_access_department',
                'ordering': ['agent_access', 'department'],
            },
        ),
        migrations.CreateModel(
            name='AgentAccessProduct',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('agent_access', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='agents.agentaccess')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'agent_access_product',
                'ordering': ['agent_access', 'product'],
            },
        ),
        migrations.CreateModel(
            name='AgentVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version_number', models.PositiveIntegerField()),
                ('model', models.CharField(max_length=120)),
                ('prompt_path', models.CharField(max_length=300)),
                ('tools', models.JSONField(blank=True, default=list)),
                ('change_note', models.TextField(blank=True)),
                ('published_at', models.DateTimeField(auto_now_add=True)),
                ('retired_at', models.DateTimeField(blank=True, null=True)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='versions', to='agents.agent')),
            ],
            options={
                'db_table': 'agent_version',
                'ordering': ['agent', '-version_number'],
                'constraints': [models.UniqueConstraint(fields=('agent', 'version_number'), name='agent_version_unique')],
            },
        ),
        migrations.CreateModel(
            name='TenantAgent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('enabled', models.BooleanField(default=False)),
                ('cadence', models.CharField(choices=[('daily', 'daily'), ('weekly', 'weekly'), ('monthly', 'monthly'), ('manual', 'manual')], default='weekly', max_length=16)),
                ('run_weekday', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('run_hour', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('next_run_at', models.DateTimeField(blank=True, null=True)),
                ('scope', models.JSONField(blank=True, default=dict)),
                ('paused_at', models.DateTimeField(blank=True, null=True)),
                ('pause_reason', models.TextField(blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tenant_agents', to='agents.agent')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_agent',
                'ordering': ['tenant', 'agent'],
                'indexes': [models.Index(condition=models.Q(('enabled', True), ('paused_at__isnull', True)), fields=['next_run_at'], name='tenant_agent_due_idx')],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'agent'), name='tenant_agent_unique'), models.CheckConstraint(condition=models.Q(('run_weekday__isnull', True), models.Q(('run_weekday__gte', 1), ('run_weekday__lte', 7)), _connector='OR'), name='tenant_agent_run_weekday_range'), models.CheckConstraint(condition=models.Q(('run_hour__isnull', True), ('run_hour__lte', 23), _connector='OR'), name='tenant_agent_run_hour_range')],
            },
        ),
        migrations.CreateModel(
            name='ResearchRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('run_now', 'run_now'), ('check_source', 'check_source'), ('check_url', 'check_url'), ('research_topic', 'research_topic'), ('retag', 'retag'), ('scope_item', 'scope_item')], max_length=16)),
                ('topic', models.TextField(blank=True)),
                ('url', models.URLField(blank=True, max_length=2000)),
                ('status', models.CharField(choices=[('queued', 'queued'), ('running', 'running'), ('done', 'done'), ('failed', 'failed'), ('rejected', 'rejected'), ('cancelled', 'cancelled')], default='queued', max_length=16)),
                ('result_summary', models.TextField(blank=True)),
                ('fetched_text', models.TextField(blank=True)),
                ('risk_flags', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=40), blank=True, default=list)),
                ('batch_proposal_id', models.UUIDField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tenant_agent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='research_requests', to='agents.tenantagent')),
            ],
            options={
                'db_table': 'research_request',
                'ordering': ['-created_at', 'id'],
                'indexes': [models.Index(fields=['tenant', '-created_at'], name='research_request_tenant_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('kind', 'retag'), ('tenant__isnull', True), ('tenant_agent__isnull', True)), models.Q(models.Q(('kind', 'retag'), _negated=True), ('tenant__isnull', False), ('tenant_agent__isnull', False)), _connector='OR'), name='research_request_zone')],
            },
        ),
        migrations.CreateModel(
            name='AgentRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('trigger', models.CharField(choices=[('schedule', 'schedule'), ('manual', 'manual'), ('request', 'request'), ('api', 'api')], default='api', max_length=16)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('running', 'running'), ('succeeded', 'succeeded'), ('failed', 'failed'), ('interrupted', 'interrupted')], default='running', max_length=16)),
                ('model', models.CharField(max_length=120)),
                ('pipeline_version', models.CharField(max_length=40)),
                ('stats', models.JSONField(blank=True, default=dict)),
                ('output_ref', models.CharField(blank=True, max_length=500)),
                ('error', models.TextField(blank=True)),
                ('idempotency_key', models.CharField(blank=True, max_length=200)),
                ('external_session_id', models.CharField(blank=True, max_length=200)),
                ('budget_limit', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('scope', models.JSONField(blank=True, default=dict)),
                ('interrupted_at', models.DateTimeField(blank=True, null=True)),
                ('cost', models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                ('tokens_in', models.BigIntegerField(blank=True, null=True)),
                ('tokens_out', models.BigIntegerField(blank=True, null=True)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='agents.agent')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('agent_version', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='agents.agentversion')),
                ('research_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='agents.researchrequest')),
                ('tenant_agent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='agents.tenantagent')),
            ],
            options={
                'db_table': 'agent_run',
                'ordering': ['started_at', 'id'],
                'indexes': [models.Index(fields=['tenant', '-started_at'], name='agent_run_tenant_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('tenant_agent__isnull', True), ('tenant__isnull', False), _connector='OR'), name='agent_run_tenant_agent_run_is_a_tenant_run')],
            },
        ),
        migrations.CreateModel(
            name='TenantAgentBudget',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('monthly_cap', models.DecimalField(decimal_places=2, max_digits=10)),
                ('currency', models.CharField(default='EUR', max_length=3)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_agent_budget',
                'ordering': ['tenant'],
                'constraints': [models.UniqueConstraint(fields=('tenant',), name='tenant_agent_budget_one_per_tenant'), models.CheckConstraint(condition=models.Q(('monthly_cap__gte', 0)), name='tenant_agent_budget_not_negative')],
            },
        ),
        *library_door_trigger_operations("agent", INVENTORY_DOORS),
        migrations.RunSQL(
            sql=AGENT_GUARD_SQL,
            reverse_sql='DROP TRIGGER IF EXISTS agent_key_immutable ON "agent"; DROP FUNCTION IF EXISTS cw_agent_key_guard();',
        ),
        *library_door_trigger_operations("agent_version", INVENTORY_DOORS),
        migrations.RunSQL(sql=VERSION_GUARD_SQL, reverse_sql="DROP FUNCTION IF EXISTS cw_agent_version_guard();"),
        *append_only_trigger_operations("agent_version", function="cw_agent_version_guard"),
        migrations.RunSQL(
            sql=RUN_VERSION_GUARD_SQL,
            reverse_sql=(
                'DROP TRIGGER IF EXISTS agent_run_version_written_once ON "agent_run"; '
                "DROP FUNCTION IF EXISTS cw_agent_run_version_guard();"
            ),
        ),
        *[operation for table in TENANT_TABLES for operation in rls_operations(table)],
        *rls_operations("research_request", mixed=True),
        tenant_id_unique("tenant_agent"),
        tenant_id_unique("agent_access"),
        same_tenant_key("research_request", "tenant_agent_id", "tenant_agent", "id", name="research_request_tenant_agent_same_tenant"),
        same_tenant_key("agent_run", "tenant_agent_id", "tenant_agent", "id", name="agent_run_tenant_agent_same_tenant"),
        same_tenant_key("agent_access_department", "agent_access_id", "agent_access", "id"),
        same_tenant_key("agent_access_product", "agent_access_id", "agent_access", "id"),
        migrations.RunSQL(
            sql=TENANT_AGENT_FENCE_SQL,
            reverse_sql=(
                'DROP TRIGGER IF EXISTS tenant_agent_fence ON "tenant_agent"; '
                "DROP FUNCTION IF EXISTS cw_tenant_agent_fence();"
            ),
        ),
    ]
