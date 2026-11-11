"""taxonomy, squashed (review 2026-11-11 B-13): the vocabularies, the taxonomy, the
footprint and its requests and history, the register lists and scope items, with their
final fields, their keys to the tenant, and the rules that read only taxonomy's tables.
0002 adds the links to other apps' tables and the rules that read them.

- Every tenant table is under forced row-level security (playbook 14); the footprint
  history is a ledger, append-only by trigger (FP-02).
- The library vocabularies and the taxonomy take the inventory's doors, a proposal or a
  seed (VOC-07, H16, ADR 0058).
- `UNIQUE (tenant_id, id)` on the tenant lists that other tables point at with a composite
  key, because PostgreSQL checks a foreign key without row-level security: the register's
  statuses, ratings, gap lists and reasons (REG-03), link kinds (TEN-02) and teams (TEN-03).
  A request's scope items, entity exclusions and entity terms and the history's scope item
  point at their own bank's rows the same way (OWN-01, D-89, D-91).
- The footprint rule as SQL, the twin of apps/taxonomy/matching.in_footprint() (FP-01,
  FP-03, D-36, NFR-02): `taxonomy_footprint_guard(tenant)` reads the tables once per query,
  `taxonomy_scope_admits(...)` is the per-row half and reads no table, and
  `taxonomy_in_footprint(tenant, terms)` composes the two. A dimension narrows the footprint
  when it is active and restricts (its flag, or kind `opt_in` whatever the flag says) and,
  unless it is opt-in, the footprint names a term in it. The bodies are frozen here
  (playbook 4.5); apps/taxonomy/tests_matching.py pins them to the Python rule."""

import apps.taxonomy.models
import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import (
    INVENTORY_DOORS,
    append_only_trigger_operations,
    library_door_trigger_operations,
    rls_operations,
    same_tenant_key,
    tenant_id_unique,
)

TENANT_TABLES = (
    "tenant_tag", "tenant_tag_label", "tagging",
    "link_kind", "link_kind_label",
    "effort_size", "effort_size_label",
    "compliance_status", "compliance_status_label",
    "risk_rating", "risk_rating_label",
    "case_sub_status", "case_sub_status_label",
    "dismissal_reason", "dismissal_reason_label",
    "close_reason", "close_reason_label",
    "gap_status", "gap_status_label",
    "gap_source", "gap_source_label",
    "risk_acceptance_reason", "risk_acceptance_reason_label",
    "team", "team_label",
    "vocabulary_suggestion",
    "watched_market",
    "footprint_term", "footprint_change_request", "footprint_change_add", "footprint_change_remove",
    "footprint_history",
    "scope_item", "footprint_change_scope_item",
    "entity_scope_exclusion", "footprint_change_entity_term",
)
LIBRARY_TABLES = (
    "term_dimension", "term_dimension_label",
    "taxonomy_term", "taxonomy_term_label",
    "instrument_level", "instrument_level_label",
    "provision_kind", "provision_kind_label",
    "change_type", "change_type_label",
    "duty_type", "duty_type_label",
    "relation_type", "relation_type_label",
    "source_kind", "source_kind_label",
    "urgency", "urgency_label",
    "library_tag", "library_tag_label",
    "flag", "flag_label",
    "rejection_reason", "rejection_reason_label",
)
TENANT_ID_UNIQUE = ("link_kind", "compliance_status", "risk_rating", "gap_status", "gap_source", "risk_acceptance_reason")
# (table, column, target table, target column)
COMPOSITE_KEYS = (
    ("footprint_change_scope_item", "request_id", "footprint_change_request", "id"),
    ("footprint_change_scope_item", "scope_item_id", "scope_item", "id"),
    ("footprint_history", "scope_item_id", "scope_item", "id"),
    ("entity_scope_exclusion", "request_id", "footprint_change_request", "id"),
    ("footprint_change_entity_term", "request_id", "footprint_change_request", "id"),
)

FOOTPRINT_FUNCTIONS = """
CREATE OR REPLACE FUNCTION taxonomy_footprint_guard(
    p_tenant uuid, OUT terms uuid[], OUT dimensions uuid[], OUT allowed uuid[]
) LANGUAGE sql STABLE AS $$
    SELECT
        coalesce(array_agg(t.id ORDER BY t.id), '{}'),
        coalesce(array_agg(t.dimension_id ORDER BY t.id), '{}'),
        coalesce((SELECT array_agg(f.term_id) FROM footprint_term f WHERE f.tenant_id = p_tenant), '{}')
    FROM term_dimension d
    JOIN taxonomy_term t ON t.dimension_id = d.id
    WHERE d.active AND (d.restricts_footprint OR d.kind = 'opt_in') AND (
        d.kind = 'opt_in' OR EXISTS (
            SELECT 1 FROM footprint_term f
            JOIN taxonomy_term t2 ON t2.id = f.term_id
            WHERE f.tenant_id = p_tenant AND t2.dimension_id = d.id
        )
    )
$$;

-- A loop rather than a grouped subquery: it runs once per row of a list, and measured on
-- 3000 obligations it costs half as much (NFR-02).
CREATE OR REPLACE FUNCTION taxonomy_scope_admits(
    p_terms uuid[], p_guard_terms uuid[], p_guard_dimensions uuid[], p_allowed uuid[]
) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    term uuid;
    slot int;
    wanting uuid[] := '{}';  -- guarded dimensions the record carries terms in
    met uuid[] := '{}';      -- those among them where the footprint names one of its terms
BEGIN
    FOREACH term IN ARRAY coalesce(p_terms, '{}') LOOP
        slot := array_position(p_guard_terms, term);
        CONTINUE WHEN slot IS NULL;
        wanting := wanting || p_guard_dimensions[slot];
        IF term = ANY(p_allowed) THEN
            met := met || p_guard_dimensions[slot];
        END IF;
    END LOOP;
    RETURN wanting <@ met;
END
$$;

CREATE OR REPLACE FUNCTION taxonomy_in_footprint(p_tenant uuid, p_terms uuid[]) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT taxonomy_scope_admits(p_terms, g.terms, g.dimensions, g.allowed)
    FROM taxonomy_footprint_guard(p_tenant) AS g
$$;
"""

DROP_FOOTPRINT_FUNCTIONS = """
DROP FUNCTION IF EXISTS taxonomy_in_footprint(uuid, uuid[]);
DROP FUNCTION IF EXISTS taxonomy_scope_admits(uuid[], uuid[], uuid[], uuid[]);
DROP FUNCTION IF EXISTS taxonomy_footprint_guard(uuid);
"""


class Migration(migrations.Migration):

    replaces = [
        ('taxonomy', '0001_initial'),
    ]

    initial = True

    dependencies = [
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='Flag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'flag',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='flag_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='InstrumentLevel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('binding_default', models.BooleanField(default=True)),
                ('rank', models.PositiveIntegerField(default=0)),
            ],
            options={
                'db_table': 'instrument_level',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='instrument_level_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='LibraryTag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'library_tag',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='library_tag_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='ProvisionKind',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'provision_kind',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='provision_kind_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='RejectionReason',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'rejection_reason',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='rejection_reason_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='RelationType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'relation_type',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='relation_type_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='SourceKind',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'source_kind',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='source_kind_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='TermDimension',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('restricts_footprint', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'term_dimension',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='term_dimension_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='Urgency',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('ordinal', models.PositiveIntegerField(default=0)),
                ('sla_days', models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'urgency',
                'ordering': ['ordinal', 'sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='urgency_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='CaseSubStatus',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'case_sub_status',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='case_sub_status_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='CaseSubStatusLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.casesubstatus')),
            ],
            options={
                'db_table': 'case_sub_status_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='case_sub_status_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='ChangeType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'change_type',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='change_type_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='ChangeTypeLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.changetype')),
            ],
            options={
                'db_table': 'change_type_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='change_type_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='ClosureReason',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'close_reason',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='close_reason_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='ClosureReasonLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.closurereason')),
            ],
            options={
                'db_table': 'close_reason_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='close_reason_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='ComplianceStatus',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('ordinal', models.PositiveIntegerField(default=0)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'compliance_status',
                'ordering': ['ordinal', 'sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='compliance_status_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='ComplianceStatusLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.compliancestatus')),
            ],
            options={
                'db_table': 'compliance_status_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='compliance_status_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='DismissalReason',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'dismissal_reason',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='dismissal_reason_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='DismissalReasonLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.dismissalreason')),
            ],
            options={
                'db_table': 'dismissal_reason_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='dismissal_reason_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='DutyType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
            ],
            options={
                'db_table': 'duty_type',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='duty_type_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='DutyTypeLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.dutytype')),
            ],
            options={
                'db_table': 'duty_type_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='duty_type_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='EffortSize',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'effort_size',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='effort_size_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='EffortSizeLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.effortsize')),
            ],
            options={
                'db_table': 'effort_size_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='effort_size_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='FlagLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.flag')),
            ],
            options={
                'db_table': 'flag_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='flag_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='FootprintChangeRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('preview', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('pending', 'pending'), ('approved', 'approved'), ('rejected', 'rejected'), ('withdrawn', 'withdrawn')], default='pending', max_length=16)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decision_note', models.TextField(blank=True)),
                ('sole_approver', models.BooleanField(default=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'footprint_change_request',
                'ordering': ['requested_at', 'id'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('status', 'pending')), fields=('tenant',), name='footprint_change_request_one_pending'), models.UniqueConstraint(fields=('tenant', 'id'), name='footprint_change_request_tenant_id_unique')],
            },
        ),
        migrations.CreateModel(
            name='FootprintChangeRemove',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='remove_links', to='taxonomy.footprintchangerequest')),
            ],
            options={
                'db_table': 'footprint_change_remove',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='FootprintChangeAdd',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='add_links', to='taxonomy.footprintchangerequest')),
            ],
            options={
                'db_table': 'footprint_change_add',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='GapSource',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'gap_source',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='gap_source_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='GapSourceLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.gapsource')),
            ],
            options={
                'db_table': 'gap_source_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='gap_source_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='GapStatus',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'gap_status',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='gap_status_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='GapStatusLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.gapstatus')),
            ],
            options={
                'db_table': 'gap_status_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='gap_status_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='InstrumentLevelLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.instrumentlevel')),
            ],
            options={
                'db_table': 'instrument_level_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='instrument_level_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='LibraryTagLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.librarytag')),
            ],
            options={
                'db_table': 'library_tag_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='library_tag_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='LinkKind',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'link_kind',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='link_kind_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='LinkKindLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.linkkind')),
            ],
            options={
                'db_table': 'link_kind_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='link_kind_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='ProvisionKindLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.provisionkind')),
            ],
            options={
                'db_table': 'provision_kind_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='provision_kind_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='RejectionReasonLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.rejectionreason')),
            ],
            options={
                'db_table': 'rejection_reason_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='rejection_reason_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='RelationTypeLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.relationtype')),
            ],
            options={
                'db_table': 'relation_type_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='relation_type_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='RiskAcceptanceReason',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'risk_acceptance_reason',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='risk_acceptance_reason_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='RiskAcceptanceReasonLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.riskacceptancereason')),
            ],
            options={
                'db_table': 'risk_acceptance_reason_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='risk_acceptance_reason_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='RiskRating',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('ordinal', models.PositiveIntegerField(default=0)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'risk_rating',
                'ordering': ['ordinal', 'sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='risk_rating_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='RiskRatingLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.riskrating')),
            ],
            options={
                'db_table': 'risk_rating_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='risk_rating_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='ScopeItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, validators=[apps.taxonomy.models.validate_scope_item_description])),
                ('official_reference', models.CharField(blank=True, max_length=200)),
                ('source_url', models.URLField(max_length=2000, validators=[apps.taxonomy.models.validate_public_https_url])),
                ('status', models.CharField(choices=[('requested', 'requested'), ('in_scope', 'in_scope'), ('declined', 'declined'), ('removed', 'removed')], default='requested', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'scope_item',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='scope_item_key_unique'), models.UniqueConstraint(fields=('tenant', 'id'), name='scope_item_tenant_id_unique'), models.CheckConstraint(condition=models.Q(('source_url__startswith', 'https://')), name='scope_item_source_https')],
            },
        ),
        migrations.CreateModel(
            name='FootprintChangeScopeItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('added', 'added'), ('removed', 'removed')], max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scope_item_links', to='taxonomy.footprintchangerequest')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('scope_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='request_links', to='taxonomy.scopeitem')),
            ],
            options={
                'db_table': 'footprint_change_scope_item',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('request', 'scope_item'), name='footprint_change_scope_item_unique')],
            },
        ),
        migrations.CreateModel(
            name='SourceKindLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.sourcekind')),
            ],
            options={
                'db_table': 'source_kind_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='source_kind_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='TaxonomyTerm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='taxonomy.taxonomyterm')),
                ('dimension', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='terms', to='taxonomy.termdimension')),
            ],
            options={
                'db_table': 'taxonomy_term',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('dimension', 'key'), name='taxonomy_term_dimension_key_unique')],
            },
        ),
        migrations.AddField(
            model_name='scopeitem',
            name='regime_term',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.CreateModel(
            name='FootprintTerm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='footprint_terms', to='taxonomy.taxonomyterm')),
            ],
            options={
                'db_table': 'footprint_term',
                'ordering': ['added_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'term'), name='footprint_term_unique')],
            },
        ),
        migrations.CreateModel(
            name='FootprintHistory',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('added', 'added'), ('removed', 'removed')], max_length=16)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('step_up_assertion_id', models.UUIDField(blank=True, null=True)),
                ('reason', models.TextField(blank=True)),
                ('request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='history', to='taxonomy.footprintchangerequest')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('scope_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='history', to='taxonomy.scopeitem')),
                ('term', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm')),
            ],
            options={
                'db_table': 'footprint_history',
                'ordering': ['changed_at', 'id'],
                'indexes': [models.Index(fields=['tenant', 'changed_at'], name='footprint_history_tenant_time')],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('scope_item__isnull', True), ('term__isnull', False)), models.Q(('scope_item__isnull', False), ('term__isnull', True)), _connector='OR'), name='footprint_history_term_or_scope_item')],
            },
        ),
        migrations.AddField(
            model_name='footprintchangerequest',
            name='adds',
            field=models.ManyToManyField(related_name='+', through='taxonomy.FootprintChangeAdd', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='footprintchangerequest',
            name='removes',
            field=models.ManyToManyField(related_name='+', through='taxonomy.FootprintChangeRemove', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='footprintchangeremove',
            name='term',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.CreateModel(
            name='FootprintChangeEntityTerm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('added', 'added'), ('removed', 'removed')], max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entity_links', to='taxonomy.footprintchangerequest')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm')),
            ],
            options={
                'db_table': 'footprint_change_entity_term',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddField(
            model_name='footprintchangeadd',
            name='term',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.CreateModel(
            name='EntityScopeExclusion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.footprintchangerequest')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm')),
            ],
            options={
                'db_table': 'entity_scope_exclusion',
                'ordering': ['org_unit', 'term', 'id'],
            },
        ),
        migrations.CreateModel(
            name='TaxonomyTermLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.taxonomyterm')),
            ],
            options={
                'db_table': 'taxonomy_term_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('term', 'language'), name='taxonomy_term_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'team',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='team_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='TeamLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.team')),
            ],
            options={
                'db_table': 'team_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='team_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='TenantTag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80)),
                ('kind', models.CharField(blank=True, max_length=40, null=True)),
                ('usage_note', models.TextField(blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('is_system', models.BooleanField(default=False)),
                ('is_default', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_tag',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='tenant_tag_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='Tagging',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('subject_type', models.CharField(max_length=64)),
                ('subject_id', models.UUIDField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tag', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='taggings', to='taxonomy.tenanttag')),
            ],
            options={
                'db_table': 'tagging',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('tag', 'subject_type', 'subject_id'), name='tagging_unique')],
            },
        ),
        migrations.CreateModel(
            name='TenantTagLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.tenanttag')),
            ],
            options={
                'db_table': 'tenant_tag_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='tenant_tag_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='TermDimensionLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.termdimension')),
            ],
            options={
                'db_table': 'term_dimension_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='term_dimension_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='UrgencyLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='taxonomy.urgency')),
            ],
            options={
                'db_table': 'urgency_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='urgency_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='VocabularySuggestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('list_name', models.CharField(max_length=40)),
                ('key', models.SlugField(max_length=80)),
                ('labels', models.JSONField(blank=True, default=dict)),
                ('usage_note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'pending'), ('accepted', 'accepted'), ('declined', 'declined')], default='pending', max_length=16)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'vocabulary_suggestion',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='WatchedMarket',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'watched_market',
                'ordering': ['added_at', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='footprintchangeremove',
            constraint=models.UniqueConstraint(fields=('request', 'term'), name='footprint_change_remove_unique'),
        ),
        migrations.AddConstraint(
            model_name='footprintchangeadd',
            constraint=models.UniqueConstraint(fields=('request', 'term'), name='footprint_change_add_unique'),
        ),
        *[operation for table in TENANT_TABLES for operation in rls_operations(table)],
        *append_only_trigger_operations("footprint_history"),
        *[operation for table in LIBRARY_TABLES for operation in library_door_trigger_operations(table, INVENTORY_DOORS)],
        *[tenant_id_unique(table) for table in TENANT_ID_UNIQUE],
        tenant_id_unique("team", name="team_tenant_id_unique"),
        *[same_tenant_key(*key) for key in COMPOSITE_KEYS],
        migrations.RunSQL(sql=FOOTPRINT_FUNCTIONS, reverse_sql=DROP_FOOTPRINT_FUNCTIONS),
    ]
