"""tenants, squashed (review 2026-11-11 B-13): the bank's organisation, products, licences,
internal items, security policy, team members, support access and public-register facts,
with their final fields, their keys to the tenant, and the rules that read only tenants'
tables. 0002 adds the links to other apps' tables and the rules that read them.

- Every table is under forced row-level security (TEN-02, TEN-06, TEN-07, ID-07).
- PostgreSQL checks a foreign key without row-level security, so every reference to a
  tenant row is also a composite `(tenant_id, …)` key into `UNIQUE (tenant_id, id)`.
- A support access request (TEN-06, D-49, ADR 0042) is never deleted, and who asked, for
  what, at which level and for how long never change; the decision columns move once. The
  hatch is the schema owner's alone, as on the append-only ledgers, so the retention purge
  and tenant exit can still delete.
- A register entry belongs to a legal entity (TEN-07, TEN-08), which a trigger checks
  because a CHECK cannot read another row."""

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import (
    MAINTENANCE_SETTING,
    MIGRATOR_ROLE,
    rls_operations,
    same_tenant_key,
    tenant_id_unique,
)

TABLES = (
    "org_unit",
    "licence",
    "licence_service_term",
    "tenant_product",
    "tenant_product_term",
    "internal_item",
    "security_policy",
    "team_member",
    "support_access",
    "register_lookup",
    "register_entry",
)
TENANT_ID_UNIQUE = ("org_unit", "licence", "tenant_product", "internal_item", "support_access")
# (table, column, target table, target column)
COMPOSITE_KEYS = (
    ("org_unit", "parent_id", "org_unit", "id"),
    ("licence", "org_unit_id", "org_unit", "id"),
    ("licence_service_term", "licence_id", "licence", "id"),
    ("tenant_product", "org_unit_id", "org_unit", "id"),
    ("tenant_product_term", "product_id", "tenant_product", "id"),
    ("internal_item", "org_unit_id", "org_unit", "id"),
    ("register_entry", "org_unit_id", "org_unit", "id"),
)

GUARD_SQL = f"""
CREATE FUNCTION cw_support_access_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('{MAINTENANCE_SETTING}', true) = 'on' AND session_user = '{MIGRATOR_ROLE}' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'support_access is never deleted' USING ERRCODE = 'raise_exception';
    END IF;
    IF (NEW.id, NEW.tenant_id, NEW.platform_user_id, NEW.reason, NEW.ticket_ref, NEW.access_level,
        NEW.hours, NEW.requested_at, NEW.request_expires_at)
       IS DISTINCT FROM
       (OLD.id, OLD.tenant_id, OLD.platform_user_id, OLD.reason, OLD.ticket_ref, OLD.access_level,
        OLD.hours, OLD.requested_at, OLD.request_expires_at) THEN
        RAISE EXCEPTION 'support_access: who asked, for what, at which level and for how long never change'
            USING ERRCODE = 'raise_exception';
    END IF;
    IF (OLD.started_at IS NOT NULL
        AND (NEW.approved_by_id, NEW.approved_step_up_assertion_id, NEW.started_at, NEW.expires_at)
            IS DISTINCT FROM (OLD.approved_by_id, OLD.approved_step_up_assertion_id, OLD.started_at, OLD.expires_at))
       OR (OLD.ended_at IS NOT NULL
        AND (NEW.ended_at, NEW.ended_by_id) IS DISTINCT FROM (OLD.ended_at, OLD.ended_by_id)) THEN
        RAISE EXCEPTION 'support_access: a decision is made once and never rewritten'
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER support_access_guard BEFORE UPDATE OR DELETE ON support_access
    FOR EACH ROW EXECUTE FUNCTION cw_support_access_guard();
"""

GUARD_REVERSE_SQL = """
DROP TRIGGER IF EXISTS support_access_guard ON support_access;
DROP FUNCTION IF EXISTS cw_support_access_guard();
"""



LEGAL_ENTITY_GUARD_SQL = """
CREATE FUNCTION cw_register_entry_legal_entity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM org_unit u WHERE u.id = NEW.org_unit_id AND u.kind = 'legal_entity'
    ) THEN
        RAISE EXCEPTION 'register_entry.org_unit must be a legal entity'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER register_entry_legal_entity_guard BEFORE INSERT OR UPDATE OF org_unit_id ON register_entry
    FOR EACH ROW EXECUTE FUNCTION cw_register_entry_legal_entity_guard();
"""
LEGAL_ENTITY_GUARD_REVERSE_SQL = """
DROP TRIGGER IF EXISTS register_entry_legal_entity_guard ON register_entry;
DROP FUNCTION IF EXISTS cw_register_entry_legal_entity_guard();
"""


class Migration(migrations.Migration):

    replaces = [
        ('tenants', '0001_initial'),
    ]

    initial = True

    dependencies = [
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrgUnit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('group', 'group'), ('legal_entity', 'legal_entity'), ('business_area', 'business_area'), ('business_unit', 'business_unit'), ('function', 'function')], max_length=16)),
                ('name', models.CharField(max_length=200)),
                ('org_number', models.CharField(blank=True, max_length=40)),
                ('lei', models.CharField(blank=True, max_length=20)),
                ('country_code', models.CharField(blank=True, max_length=2)),
                ('active', models.BooleanField(default=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='tenants.orgunit')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'org_unit',
                'ordering': ['name', 'id'],
                'constraints': [models.CheckConstraint(condition=models.Q(('parent', models.F('id')), _negated=True), name='org_unit_not_own_parent')],
            },
        ),
        migrations.CreateModel(
            name='Licence',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reference', models.CharField(blank=True, max_length=200)),
                ('granted_on', models.DateField(blank=True, null=True)),
                ('withdrawn_on', models.DateField(blank=True, null=True)),
                ('scope_note', models.TextField(blank=True)),
                ('issuer', models.CharField(blank=True, max_length=200)),
                ('number', models.CharField(blank=True, max_length=100)),
                ('scope_statement', models.TextField(blank=True)),
                ('issued_on', models.DateField(blank=True, null=True)),
                ('valid_until', models.DateField(blank=True, null=True)),
                ('next_audit_on', models.DateField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('org_unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='licences', to='tenants.orgunit')),
            ],
            options={
                'db_table': 'licence',
                'ordering': ['org_unit', 'granted_on', 'id'],
            },
        ),
        migrations.CreateModel(
            name='InternalItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('reference', models.CharField(blank=True, max_length=200)),
                ('url', models.URLField(blank=True, max_length=2000)),
                ('external_system', models.CharField(blank=True, max_length=100)),
                ('external_ref', models.CharField(blank=True, max_length=200)),
                ('last_reviewed_on', models.DateField(blank=True, null=True)),
                ('next_review_on', models.DateField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('org_unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='internal_items', to='tenants.orgunit')),
            ],
            options={
                'db_table': 'internal_item',
                'ordering': ['name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='RegisterEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('facts', models.JSONField()),
                ('source_url', models.URLField(max_length=500)),
                ('read_at', models.DateTimeField()),
                ('changed_at', models.DateTimeField()),
                ('version', models.PositiveIntegerField(default=1)),
                ('org_unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='register_entries', to='tenants.orgunit')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'register_entry',
            },
        ),
        migrations.CreateModel(
            name='RegisterLookup',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('query', models.CharField(max_length=40)),
                ('status', models.CharField(choices=[('queued', 'queued'), ('running', 'running'), ('succeeded', 'succeeded'), ('failed', 'failed')], default='queued', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('error', models.CharField(blank=True, max_length=40)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'register_lookup',
                'ordering': ['-created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='SecurityPolicy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('credential_policy', models.CharField(choices=[('any_passkey', 'any_passkey'), ('device_bound', 'device_bound')], default='any_passkey', max_length=16)),
                ('allowed_authenticators', models.JSONField(blank=True, default=list)),
                ('device_bound_from', models.DateField(blank=True, null=True)),
                ('session_idle_minutes', models.PositiveIntegerField(blank=True, null=True)),
                ('session_absolute_hours', models.PositiveIntegerField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'security_policy',
                'ordering': ['tenant'],
                'constraints': [models.UniqueConstraint(fields=('tenant',), name='security_policy_tenant_unique'), models.CheckConstraint(condition=models.Q(('session_idle_minutes__isnull', True), ('session_idle_minutes__gt', 0), _connector='OR'), name='security_policy_idle_positive'), models.CheckConstraint(condition=models.Q(('session_absolute_hours__isnull', True), ('session_absolute_hours__gt', 0), _connector='OR'), name='security_policy_absolute_positive')],
            },
        ),
        migrations.CreateModel(
            name='SupportAccess',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reason', models.TextField()),
                ('ticket_ref', models.CharField(blank=True, max_length=100)),
                ('access_level', models.CharField(choices=[('read', 'read'), ('write', 'write')], default='read', max_length=8)),
                ('status', models.CharField(choices=[('requested', 'requested'), ('approved', 'approved'), ('declined', 'declined'), ('revoked', 'revoked'), ('expired', 'expired')], default='expired', max_length=16)),
                ('hours', models.PositiveSmallIntegerField(default=0)),
                ('requested_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('request_expires_at', models.DateTimeField(blank=True, null=True)),
                ('approved_step_up_assertion_id', models.UUIDField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'support_access',
                'ordering': ['requested_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='TeamMember',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'team_member',
            },
        ),
        migrations.CreateModel(
            name='TenantProduct',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('planned', 'planned'), ('live', 'live'), ('retired', 'retired')], default='live', max_length=8)),
                ('launch_date', models.DateField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('org_unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='products', to='tenants.orgunit')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_product',
                'ordering': ['name', 'id'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'name'), name='tenant_product_name_unique')],
            },
        ),
        migrations.CreateModel(
            name='TenantProductTerm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='terms', to='tenants.tenantproduct')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_product_term',
            },
        ),
        migrations.CreateModel(
            name='LicenceServiceTerm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('licence', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='service_terms', to='tenants.licence')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'licence_service_term',
                'constraints': [],
            },
        ),
        *[operation for table in TABLES for operation in rls_operations(table)],
        *[tenant_id_unique(table) for table in TENANT_ID_UNIQUE],
        *[same_tenant_key(*key) for key in COMPOSITE_KEYS],
        migrations.RunSQL(sql=GUARD_SQL, reverse_sql=GUARD_REVERSE_SQL),
        migrations.RunSQL(sql=LEGAL_ENTITY_GUARD_SQL, reverse_sql=LEGAL_ENTITY_GUARD_REVERSE_SQL),
    ]
