"""register, squashed (review 2026-11-11 B-13): the register entry, its scope rows per legal
entity, the append-only assessment history, gaps, interpretations, links to the bank's
internal items, the Statement of Applicability's units and the dated duty occurrences, every
table under forced row-level security (REG-01..REG-08, TEN-03, D-41, D-75).

PostgreSQL checks a foreign key without row-level security, so every reference to a tenant
row is also a composite `(tenant_id, …)` key: to `UNIQUE (tenant_id, id)` on the tables here
and on the tenant lists they name, and to `membership_tenant_user_unique` for a person, which
makes every person named a member of the same bank. apps/register/tests_models.py and
tests_units.py walk `REGISTER_KEYS` and `UNIT_KEYS` below, so a key added there is proved
without a line of its own.

Risk acceptance is behind four eyes: `gap_four_eyes` keeps the person who accepts apart from
the person who asked. A gap's status is the tenant's own row, whose fixed category a CHECK
cannot read, so a trigger keeps a gap out of a `risk_accepted` status until it has been
accepted."""

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import append_only_trigger_operations, rls_operations, same_tenant_key, tenant_id_unique

TABLES = (
    "tenant_obligation",
    "tenant_obligation_scope",
    "compliance_assessment",
    "gap",
    "interpretation",
    "internal_link",
    "soa_unit",
    "duty_occurrence",
)
TENANT_ID_UNIQUE = ("tenant_obligation", "tenant_obligation_scope", "soa_unit")

# (table, column, target table, target column)
REGISTER_KEYS = (
    ("tenant_obligation", "applicability_decided_by_id", "membership", "user_id"),
    ("tenant_obligation", "compliance_status_id", "compliance_status", "id"),
    ("tenant_obligation", "risk_rating_id", "risk_rating", "id"),
    ("tenant_obligation", "first_line_owner_id", "membership", "user_id"),
    ("tenant_obligation", "compliance_contact_id", "membership", "user_id"),
    ("tenant_obligation", "owner_team_id", "team", "id"),
    ("tenant_obligation_scope", "tenant_obligation_id", "tenant_obligation", "id"),
    ("tenant_obligation_scope", "org_unit_id", "org_unit", "id"),
    ("tenant_obligation_scope", "product_id", "tenant_product", "id"),
    ("tenant_obligation_scope", "applicability_decided_by_id", "membership", "user_id"),
    ("tenant_obligation_scope", "compliance_status_id", "compliance_status", "id"),
    ("tenant_obligation_scope", "risk_rating_id", "risk_rating", "id"),
    ("tenant_obligation_scope", "owner_id", "membership", "user_id"),
    ("tenant_obligation_scope", "owner_team_id", "team", "id"),
    ("compliance_assessment", "tenant_obligation_id", "tenant_obligation", "id"),
    ("compliance_assessment", "scope_id", "tenant_obligation_scope", "id"),
    ("compliance_assessment", "status_id", "compliance_status", "id"),
    ("compliance_assessment", "risk_rating_id", "risk_rating", "id"),
    ("compliance_assessment", "assessed_by_id", "membership", "user_id"),
    ("gap", "tenant_obligation_id", "tenant_obligation", "id"),
    ("gap", "org_unit_id", "org_unit", "id"),
    ("gap", "severity_id", "risk_rating", "id"),
    ("gap", "source_id", "gap_source", "id"),
    ("gap", "status_id", "gap_status", "id"),
    ("gap", "identified_by_id", "membership", "user_id"),
    ("gap", "owner_id", "membership", "user_id"),
    ("gap", "owner_team_id", "team", "id"),
    ("gap", "acceptance_reason_id", "risk_acceptance_reason", "id"),
    ("gap", "acceptance_requested_by_id", "membership", "user_id"),
    ("gap", "accepted_by_id", "membership", "user_id"),
    ("gap", "closed_by_id", "membership", "user_id"),
    ("interpretation", "tenant_obligation_id", "tenant_obligation", "id"),
    ("interpretation", "author_id", "membership", "user_id"),
    ("internal_link", "tenant_obligation_id", "tenant_obligation", "id"),
    ("internal_link", "internal_item_id", "internal_item", "id"),
    ("internal_link", "created_by_id", "membership", "user_id"),
    ("internal_link", "removed_by_id", "membership", "user_id"),
)
UNIT_KEYS = (
    ("soa_unit", "scope_id", "tenant_obligation_scope", "id"),
    ("soa_unit", "applicability_decided_by_id", "membership", "user_id"),
    ("soa_unit", "compliance_status_id", "compliance_status", "id"),
    ("soa_unit", "removed_by_id", "membership", "user_id"),
    ("gap", "unit_id", "soa_unit", "id"),
)
DUTY_KEYS = (
    ("duty_occurrence", "tenant_obligation_id", "tenant_obligation", "id"),
    ("duty_occurrence", "org_unit_id", "org_unit", "id"),
    ("duty_occurrence", "owner_id", "membership", "user_id"),
    ("duty_occurrence", "owner_team_id", "team", "id"),
    ("duty_occurrence", "completed_by_id", "membership", "user_id"),
)
FOUR_EYES_SQL = (
    'ALTER TABLE "gap" ADD CONSTRAINT gap_four_eyes '
    "CHECK (accepted_by_id IS NULL OR accepted_by_id <> acceptance_requested_by_id)"
)

ACCEPTED_GUARD_SQL = """
CREATE FUNCTION cw_gap_accepted_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.accepted_by_id IS NULL AND EXISTS (
        SELECT 1 FROM gap_status s WHERE s.id = NEW.status_id AND s.kind = 'risk_accepted'
    ) THEN
        RAISE EXCEPTION 'gap: a risk_accepted status needs an acceptance by a second person'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER gap_accepted_guard BEFORE INSERT OR UPDATE OF status_id, accepted_by_id ON gap
    FOR EACH ROW EXECUTE FUNCTION cw_gap_accepted_guard();
"""
ACCEPTED_GUARD_REVERSE_SQL = """
DROP TRIGGER IF EXISTS gap_accepted_guard ON gap;
DROP FUNCTION IF EXISTS cw_gap_accepted_guard();
"""


ACCEPTED_GUARD_SQL = """
CREATE FUNCTION cw_gap_accepted_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.accepted_by_id IS NULL AND EXISTS (
        SELECT 1 FROM gap_status s WHERE s.id = NEW.status_id AND s.kind = 'risk_accepted'
    ) THEN
        RAISE EXCEPTION 'gap: a risk_accepted status needs an acceptance by a second person'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER gap_accepted_guard BEFORE INSERT OR UPDATE OF status_id, accepted_by_id ON gap
    FOR EACH ROW EXECUTE FUNCTION cw_gap_accepted_guard();
"""
ACCEPTED_GUARD_REVERSE_SQL = """
DROP TRIGGER IF EXISTS gap_accepted_guard ON gap;
DROP FUNCTION IF EXISTS cw_gap_accepted_guard();
"""


class Migration(migrations.Migration):

    replaces = [
        ('register', '0001_register'),
        ('register', '0002_gaps_history_links'),
        ('register', '0003_soa_unit'),
        ('register', '0004_duty_occurrence'),
    ]

    initial = True

    dependencies = [
        ('identity', '0002_squashed_0011_links_and_rules'),
        ('library', '0002_squashed_0013_links_and_rules'),
        ('shared', '0002_squashed_0010_links_and_rules'),
        ('taxonomy', '0002_squashed_0014_links_and_rules'),
        ('tenants', '0002_squashed_0006_links_and_rules'),
    ]

    operations = [
        migrations.CreateModel(
            name='SoaUnit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reference', models.CharField(max_length=64)),
                ('title', models.CharField(max_length=300)),
                ('applicability', models.CharField(choices=[('applies', 'applies'), ('does_not_apply', 'does_not_apply'), ('not_assessed', 'not_assessed')], default='not_assessed', max_length=16)),
                ('applicability_reason', models.TextField(blank=True)),
                ('applicability_decided_at', models.DateTimeField(blank=True, null=True)),
                ('status_note', models.TextField(blank=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
                ('applicability_decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('compliance_status', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.compliancestatus')),
                ('removed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'soa_unit',
                'ordering': ['reference', 'id'],
            },
        ),
        migrations.CreateModel(
            name='TenantObligation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('applicability', models.CharField(choices=[('applies', 'applies'), ('does_not_apply', 'does_not_apply'), ('not_assessed', 'not_assessed')], default='not_assessed', max_length=16)),
                ('applicability_reason', models.TextField(blank=True)),
                ('applicability_decided_at', models.DateTimeField(blank=True, null=True)),
                ('status_note', models.TextField(blank=True)),
                ('process', models.CharField(blank=True, max_length=200)),
                ('system', models.CharField(blank=True, max_length=200)),
                ('evidence_location', models.CharField(blank=True, max_length=500)),
                ('next_review_date', models.DateField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('applicability_decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('compliance_contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('compliance_status', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.compliancestatus')),
                ('first_line_owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.obligation')),
                ('owner_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team')),
                ('risk_rating', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.riskrating')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_obligation',
                'ordering': ['obligation_id', 'id'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'obligation'), name='tenant_obligation_unique')],
            },
        ),
        migrations.CreateModel(
            name='Interpretation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version_number', models.PositiveIntegerField()),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('superseded_at', models.DateTimeField(blank=True, null=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tenant_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='interpretations', to='register.tenantobligation')),
            ],
            options={
                'db_table': 'interpretation',
                'ordering': ['tenant_obligation_id', 'version_number'],
                'constraints': [models.UniqueConstraint(fields=('tenant_obligation', 'version_number'), name='interpretation_version_unique')],
            },
        ),
        migrations.CreateModel(
            name='InternalLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('label', models.CharField(max_length=200)),
                ('url', models.URLField(blank=True, max_length=2000)),
                ('external_ref', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('internal_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.internalitem')),
                ('removed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tenant_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='links', to='register.tenantobligation')),
            ],
            options={
                'db_table': 'internal_link',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('removed_at__isnull', True)), fields=('tenant_obligation', 'internal_item'), name='internal_link_live_unique')],
            },
        ),
        migrations.CreateModel(
            name='Gap',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('identified_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('target_date', models.DateField(blank=True, null=True)),
                ('remediation', models.TextField(blank=True)),
                ('acceptance_note', models.TextField(blank=True)),
                ('acceptance_requested_at', models.DateTimeField(blank=True, null=True)),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('acceptance_reason', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.riskacceptancereason')),
                ('acceptance_requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('accepted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('identified_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('org_unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.orgunit')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('owner_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team')),
                ('severity', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.riskrating')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.gapsource')),
                ('status', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.gapstatus')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='gaps', to='register.soaunit')),
                ('tenant_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='gaps', to='register.tenantobligation')),
            ],
            options={
                'db_table': 'gap',
                'ordering': ['identified_at', 'id'],
                'constraints': [models.CheckConstraint(condition=models.Q(('accepted_by__isnull', True), models.Q(('acceptance_reason__isnull', False), ('acceptance_requested_by__isnull', False), ('accepted_at__isnull', False)), _connector='OR'), name='gap_acceptance_complete'), models.CheckConstraint(condition=models.Q(('owner__isnull', True), ('owner_team__isnull', True), _connector='OR'), name='gap_one_owner_kind')],
            },
        ),
        migrations.CreateModel(
            name='DutyOccurrence',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('due_date', models.DateField()),
                ('status', models.CharField(choices=[('upcoming', 'upcoming'), ('in_progress', 'in_progress'), ('done', 'done'), ('missed', 'missed'), ('not_applicable', 'not_applicable')], default='upcoming', max_length=16)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('note', models.TextField(blank=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('completed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('org_unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.orgunit')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('owner_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team')),
                ('recurring_duty', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.recurringduty')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tenant_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='duty_occurrences', to='register.tenantobligation')),
            ],
            options={
                'db_table': 'duty_occurrence',
                'ordering': ['due_date', 'id'],
                'constraints': [models.UniqueConstraint(fields=('recurring_duty', 'tenant', 'org_unit', 'due_date'), name='duty_occurrence_unique', nulls_distinct=False), models.CheckConstraint(condition=models.Q(('owner__isnull', True), ('owner_team__isnull', True), _connector='OR'), name='duty_occurrence_one_owner_kind')],
            },
        ),
        migrations.CreateModel(
            name='TenantObligationScope',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('applicability', models.CharField(choices=[('applies', 'applies'), ('does_not_apply', 'does_not_apply'), ('not_assessed', 'not_assessed')], default='not_assessed', max_length=16)),
                ('applicability_reason', models.TextField(blank=True)),
                ('applicability_decided_at', models.DateTimeField(blank=True, null=True)),
                ('status_note', models.TextField(blank=True)),
                ('process', models.CharField(blank=True, max_length=200)),
                ('system', models.CharField(blank=True, max_length=200)),
                ('evidence_location', models.CharField(blank=True, max_length=500)),
                ('next_review_date', models.DateField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('applicability_decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('compliance_status', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.compliancestatus')),
                ('org_unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.orgunit')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('owner_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.tenantproduct')),
                ('risk_rating', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.riskrating')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tenant_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='scopes', to='register.tenantobligation')),
            ],
            options={
                'db_table': 'tenant_obligation_scope',
                'ordering': ['tenant_obligation_id', 'org_unit_id', 'id'],
                'constraints': [models.UniqueConstraint(fields=('tenant_obligation', 'org_unit', 'product'), name='tenant_obligation_scope_unique', nulls_distinct=False), models.CheckConstraint(condition=models.Q(('owner__isnull', True), ('owner_team__isnull', True), _connector='OR'), name='tenant_obligation_scope_one_owner_kind')],
            },
        ),
        migrations.AddField(
            model_name='soaunit',
            name='scope',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='units', to='register.tenantobligationscope'),
        ),
        migrations.CreateModel(
            name='ComplianceAssessment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('method', models.CharField(choices=[('self_assessment', 'self_assessment'), ('second_line_review', 'second_line_review'), ('internal_audit', 'internal_audit'), ('external_audit', 'external_audit'), ('regulator', 'regulator')], default='self_assessment', max_length=24)),
                ('rationale', models.TextField()),
                ('next_review_date', models.DateField(blank=True, null=True)),
                ('assessed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('assessed_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('risk_rating', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.riskrating')),
                ('status', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.compliancestatus')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tenant_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='register.tenantobligation')),
                ('scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='register.tenantobligationscope')),
            ],
            options={
                'db_table': 'compliance_assessment',
                'ordering': ['assessed_at', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='soaunit',
            constraint=models.UniqueConstraint(condition=models.Q(('removed_at__isnull', True)), fields=('scope', 'reference'), name='soa_unit_live_reference_unique'),
        ),
        *[operation for table in TABLES for operation in rls_operations(table)],
        *[tenant_id_unique(table) for table in TENANT_ID_UNIQUE],
        *[same_tenant_key(*key) for key in (*REGISTER_KEYS, *UNIT_KEYS, *DUTY_KEYS)],
        *append_only_trigger_operations("compliance_assessment"),
        migrations.RunSQL(sql=FOUR_EYES_SQL, reverse_sql='ALTER TABLE "gap" DROP CONSTRAINT IF EXISTS gap_four_eyes'),
        migrations.RunSQL(sql=ACCEPTED_GUARD_SQL, reverse_sql=ACCEPTED_GUARD_REVERSE_SQL),
    ]
