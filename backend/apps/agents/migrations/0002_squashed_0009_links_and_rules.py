"""agents, squashed (review 2026-11-11 B-13): the agent tables' links to other apps' tables
and the rules that read them.

- `agent_run` is mixed: a platform run for the shared library (no tenant) is visible to
  every tenant and a tenant's own run only to that tenant. A session writes only rows of
  its own zone, and a run with a key names a key of that same zone: foreign keys ignore
  row-level security, so the key lookup runs under `api_key`'s own policy. A keyless run
  is the worker's and still lands only in the session's zone (AGT-01, AGT-03, H15).
- An entry's owning team, its departments and products, the people who created or revoked
  it (a key into `membership (tenant_id, user_id)`) and a request's scope item are always
  the row's own bank's, through composite `(tenant_id, …)` keys (ACC-01, OWN-02, D-89)."""

import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import LIBRARY_READ_POLICY, POLICY_NAME, TENANT_EXPRESSION, same_tenant_key

OWN_ZONE = f"agent_run.tenant_id IS NOT DISTINCT FROM {TENANT_EXPRESSION}"
KEY_OF_THE_SAME_ZONE = (
    "EXISTS (SELECT 1 FROM api_key k WHERE k.id = agent_run.api_key_id "
    "AND k.tenant_id IS NOT DISTINCT FROM agent_run.tenant_id)"
)
WRITE_RULE = f"({OWN_ZONE} AND (agent_run.api_key_id IS NULL OR {KEY_OF_THE_SAME_ZONE}))"

# (table, column, target table, target column)
COMPOSITE_KEYS = (
    ("agent_access", "owner_team_id", "team", "id"),
    ("agent_access", "created_by_id", "membership", "user_id"),
    ("agent_access", "revoked_by_id", "membership", "user_id"),
    ("agent_access_department", "department_id", "org_unit", "id"),
    ("agent_access_product", "product_id", "tenant_product", "id"),
)


class Migration(migrations.Migration):

    replaces = [
        ('agents', '0002_library_rows_visible'),
        ('agents', '0003_agent_kind_review'),
        ('agents', '0004_agent_versions'),
        ('agents', '0005_tenant_agents'),
        ('agents', '0006_agent_access'),
        ('agents', '0007_run_status_interrupted'),
        ('agents', '0008_research_request_fetched'),
        ('agents', '0009_research_scope_item'),
    ]

    dependencies = [
        ('agents', '0001_squashed_0001_tables'),
        ('identity', '0001_squashed_0001_tables'),
        ('taxonomy', '0001_squashed_0001_tables'),
        ('tenants', '0001_squashed_0001_tables'),
        ('watch', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentaccess',
            name='created_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='agentaccess',
            name='owner_team',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team'),
        ),
        migrations.AddField(
            model_name='agentaccess',
            name='revoked_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='agentaccessdepartment',
            name='department',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.orgunit'),
        ),
        migrations.AddField(
            model_name='agentaccessproduct',
            name='product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.tenantproduct'),
        ),
        migrations.AddField(
            model_name='agentrun',
            name='api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='agent_runs', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='agentrun',
            name='interrupted_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='agentrun',
            name='requested_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='agentversion',
            name='published_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='researchrequest',
            name='requested_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='researchrequest',
            name='scope_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.scopeitem'),
        ),
        migrations.AddField(
            model_name='researchrequest',
            name='source',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='watch.source'),
        ),
        migrations.AddField(
            model_name='tenantagent',
            name='paused_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='tenantagent',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='tenantagentbudget',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddConstraint(
            model_name='agentaccess',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('active', True), ('revoked_at__isnull', True), ('revoked_by__isnull', True)), models.Q(('active', False), ('revoked_at__isnull', False)), _connector='OR'), name='agent_access_revoked_is_inactive'),
        ),
        migrations.AddConstraint(
            model_name='agentaccessdepartment',
            constraint=models.UniqueConstraint(fields=('agent_access', 'department'), name='agent_access_department_unique'),
        ),
        migrations.AddConstraint(
            model_name='agentaccessproduct',
            constraint=models.UniqueConstraint(fields=('agent_access', 'product'), name='agent_access_product_unique'),
        ),
        migrations.AddConstraint(
            model_name='researchrequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('kind', 'scope_item'), ('scope_item__isnull', False)), models.Q(models.Q(('kind', 'scope_item'), _negated=True), ('scope_item__isnull', True)), _connector='OR'), name='research_request_scope_item_kind'),
        ),
        migrations.AddConstraint(
            model_name='researchrequest',
            constraint=models.UniqueConstraint(condition=models.Q(('scope_item__isnull', False)), fields=('scope_item',), name='research_request_one_per_scope_item'),
        ),
        migrations.AddConstraint(
            model_name='agentrun',
            constraint=models.UniqueConstraint(condition=models.Q(('idempotency_key', ''), _negated=True), fields=('api_key', 'idempotency_key'), name='agent_run_idempotency_unique'),
        ),
        migrations.AddConstraint(
            model_name='agentrun',
            constraint=models.CheckConstraint(condition=models.Q(('api_key__isnull', False), models.Q(('trigger', 'api'), _negated=True), _connector='OR'), name='agent_run_api_run_has_a_key'),
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "agent_run" ENABLE ROW LEVEL SECURITY',
            reverse_sql='ALTER TABLE "agent_run" DISABLE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "agent_run" FORCE ROW LEVEL SECURITY',
            reverse_sql='ALTER TABLE "agent_run" NO FORCE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=f'CREATE POLICY {POLICY_NAME} ON "agent_run" FOR ALL USING ({OWN_ZONE}) WITH CHECK {WRITE_RULE}',
            reverse_sql=f'DROP POLICY IF EXISTS {POLICY_NAME} ON "agent_run"',
        ),
        migrations.RunSQL(
            sql=f'CREATE POLICY {LIBRARY_READ_POLICY} ON "agent_run" FOR SELECT USING (tenant_id IS NULL)',
            reverse_sql=f'DROP POLICY IF EXISTS {LIBRARY_READ_POLICY} ON "agent_run"',
        ),
        *[same_tenant_key(*key) for key in COMPOSITE_KEYS],
        same_tenant_key(
            "research_request", "scope_item_id", "scope_item", "id", name="research_request_scope_item_same_tenant"
        ),
    ]
