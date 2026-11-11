"""library, squashed (review 2026-11-11 B-13): the library tables with their final fields,
their keys to the tenant, and the rules that read only library tables. 0002 adds the links
to other apps' tables and the rules that read them.

- Zones (INV-07, NFR-01, H15): instrument and obligation are "shared or mine" on
  `owner_tenant_id` behind the library fence (PRO-01); `problem_report` writes its own zone
  and reads the shared one.
- A child of an instrument or an obligation lives in its parent's zone (OWN-04, D-57, D-89,
  ADR 0050): forced row-level security with `parent_visible` for reads (the parent's own
  policy, asked through a subquery, so a grandchild asks its parent, which asks the root) and
  `parent_owned` for writes (the root's `owner_tenant_id` is the session's own zone). A link
  row's owning end decides the write, and its referenced end must be visible for the write
  and the read.
- Versions are append-only (INV-02).
- The library door on every library-zone table (H16, ADR 0058): the inventory, the
  jurisdictions and their labels take a proposal or a seed (D-94), obligation and
  verification also the re-verification stamp (INV-06), `language` the seed alone. The door
  decides whether a write may happen at all; the policies decide which rows it may touch."""

import django.contrib.postgres.indexes
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import (
    INVENTORY_DOORS,
    REFERENCE_DOORS,
    STAMPED_DOORS,
    append_only_trigger_operations,
    library_door_trigger_operations,
    parent_policy_operations,
    rls_operations,
)

INVENTORY_TABLES = (
    "authority",
    "instrument",
    "instrument_title",
    "instrument_summary",
    "instrument_relation",
    "provision",
    "provision_version",
    "provision_text",
    "obligation_title",
    "obligation_version",
    "obligation_summary",
    "obligation_provision",
    "obligation_term",
    "obligation_tag",
    "obligation_relation",
    "recurring_duty",
    "jurisdiction",
    "jurisdiction_label",
)
STAMPED_TABLES = ("obligation", "verification")
REFERENCE_TABLES = ("language",)
APPEND_ONLY_TABLES = ("provision_version", "provision_text", "obligation_version", "obligation_summary", "verification")

# child: (the path from the child to its root, each hop a column and the table it names;
#         the referenced ends that must also be visible, each a column and its table)
CHILDREN: dict[str, tuple[list[tuple[str, str]], list[tuple[str, str]]]] = {
    "instrument_title": ([("instrument_id", "instrument")], []),
    "instrument_relation": ([("from_instrument_id", "instrument")], [("to_instrument_id", "instrument")]),
    "provision": ([("instrument_id", "instrument")], []),
    "provision_version": ([("provision_id", "provision"), ("instrument_id", "instrument")], []),
    "provision_text": (
        [("version_id", "provision_version"), ("provision_id", "provision"), ("instrument_id", "instrument")],
        [],
    ),
    "obligation_title": ([("obligation_id", "obligation")], []),
    "obligation_version": ([("obligation_id", "obligation")], []),
    "obligation_summary": ([("version_id", "obligation_version"), ("obligation_id", "obligation")], []),
    "obligation_provision": ([("obligation_id", "obligation")], [("provision_id", "provision")]),
    "obligation_term": ([("obligation_id", "obligation")], []),
    "obligation_tag": ([("obligation_id", "obligation")], []),
    "obligation_relation": ([("from_obligation_id", "obligation")], [("to_obligation_id", "obligation")]),
    "recurring_duty": ([("obligation_id", "obligation")], []),
    "instrument_summary": ([("instrument_id", "instrument")], []),
}


class Migration(migrations.Migration):

    replaces = [
        ('library', '0001_initial'),
    ]

    initial = True

    dependencies = [
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='Authority',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=80, unique=True)),
                ('short_name', models.CharField(max_length=40)),
                ('name', models.CharField(max_length=200)),
                ('url', models.URLField(max_length=2000)),
            ],
            options={
                'db_table': 'authority',
                'ordering': ['key'],
            },
        ),
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=8, unique=True)),
                ('name', models.CharField(max_length=80)),
                ('text_search_config', models.CharField(max_length=40)),
                ('active', models.BooleanField(default=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'language',
                'ordering': ['key'],
            },
        ),
        migrations.CreateModel(
            name='Verification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('subject_type', models.CharField(choices=[('instrument', 'instrument'), ('provision', 'provision'), ('obligation', 'obligation')], max_length=32)),
                ('subject_id', models.UUIDField()),
                ('verified_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('outcome', models.CharField(choices=[('no_change', 'no_change'), ('change_found', 'change_found'), ('source_unavailable', 'source_unavailable')], max_length=32)),
                ('note', models.TextField(blank=True)),
            ],
            options={
                'db_table': 'verification',
                'ordering': ['-verified_at'],
                'indexes': [models.Index(fields=['subject_type', 'subject_id', '-verified_at'], name='verification_subject_idx')],
            },
        ),
        migrations.CreateModel(
            name='Jurisdiction',
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
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='library.jurisdiction')),
                ('default_language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language')),
            ],
            options={
                'db_table': 'jurisdiction',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='jurisdiction_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='Instrument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stable_key', models.SlugField(max_length=120, unique=True)),
                ('short_name', models.CharField(max_length=120)),
                ('official_ref', models.CharField(max_length=200)),
                ('eli_uri', models.URLField(blank=True, max_length=2000)),
                ('source_url', models.URLField(max_length=2000)),
                ('binding', models.BooleanField()),
                ('in_force_from', models.DateField(blank=True, null=True)),
                ('in_force_from_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('in_force_to', models.DateField(blank=True, null=True)),
                ('in_force_to_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('implements_note', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('active', 'active'), ('retired', 'retired')], default='active', max_length=16)),
                ('created_origin', models.CharField(choices=[('agent', 'agent'), ('user', 'user')], max_length=16)),
                ('created_by_agent_run', models.UUIDField(blank=True, null=True)),
                ('last_verified_at', models.DateTimeField(blank=True, null=True)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('authority', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='instruments', to='library.authority')),
                ('owner_tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('jurisdiction', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.jurisdiction')),
            ],
            options={
                'db_table': 'instrument',
                'ordering': ['stable_key'],
                'indexes': [django.contrib.postgres.indexes.GinIndex(fields=['official_ref'], name='instrument_official_ref_trgm', opclasses=['gin_trgm_ops'])],
                'constraints': [models.CheckConstraint(condition=models.Q(('in_force_to__isnull', True), ('in_force_from__isnull', True), ('in_force_to__gt', models.F('in_force_from')), _connector='OR'), name='instrument_in_force_order')],
            },
        ),
        migrations.AddField(
            model_name='authority',
            name='jurisdiction',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='authorities', to='library.jurisdiction'),
        ),
        migrations.CreateModel(
            name='JurisdictionLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='library.jurisdiction')),
            ],
            options={
                'db_table': 'jurisdiction_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='jurisdiction_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='InstrumentTitle',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('instrument', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='titles', to='library.instrument')),
                ('language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
            ],
            options={
                'db_table': 'instrument_title',
                'ordering': ['language'],
                'indexes': [django.contrib.postgres.indexes.GinIndex(fields=['text'], name='instrument_title_trgm', opclasses=['gin_trgm_ops'])],
                'constraints': [models.UniqueConstraint(fields=('instrument', 'language'), name='instrument_title_language_unique'), models.UniqueConstraint(condition=models.Q(('is_original', True)), fields=('instrument',), name='instrument_title_one_original')],
            },
        ),
        migrations.CreateModel(
            name='InstrumentSummary',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('instrument', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='summaries', to='library.instrument')),
                ('language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
            ],
            options={
                'db_table': 'instrument_summary',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('instrument', 'language'), name='instrument_summary_language_unique'), models.UniqueConstraint(condition=models.Q(('is_original', True)), fields=('instrument',), name='instrument_summary_one_original')],
            },
        ),
        migrations.CreateModel(
            name='Obligation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stable_key', models.SlugField(max_length=120, unique=True)),
                ('ref_label', models.CharField(max_length=200)),
                ('product_scope', models.TextField(blank=True)),
                ('trigger_frequency', models.TextField(blank=True)),
                ('retention', models.TextField(blank=True)),
                ('sanction_exposure', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('active', 'active'), ('retired', 'retired')], default='active', max_length=16)),
                ('created_origin', models.CharField(choices=[('agent', 'agent'), ('user', 'user')], max_length=16)),
                ('created_by_agent_run', models.UUIDField(blank=True, null=True)),
                ('created_model', models.CharField(blank=True, max_length=200)),
                ('source_url', models.URLField(max_length=2000)),
                ('source_label', models.CharField(max_length=500)),
                ('last_verified_at', models.DateTimeField(blank=True, null=True)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('instrument', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='obligations', to='library.instrument')),
                ('owner_tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'obligation',
                'ordering': ['stable_key'],
                'indexes': [models.Index(fields=['last_verified_at'], name='obligation_verified_idx')],
            },
        ),
        migrations.CreateModel(
            name='ObligationRelation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('from_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='relations_out', to='library.obligation')),
                ('to_obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='relations_in', to='library.obligation')),
            ],
            options={
                'db_table': 'obligation_relation',
                'ordering': ['from_obligation__stable_key', 'to_obligation__stable_key'],
                'constraints': [models.UniqueConstraint(fields=('from_obligation', 'to_obligation'), name='obligation_relation_unique'), models.CheckConstraint(condition=models.Q(('from_obligation', models.F('to_obligation')), _negated=True), name='obligation_relation_not_self')],
            },
        ),
        migrations.CreateModel(
            name='ObligationTag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.obligation')),
            ],
            options={
                'db_table': 'obligation_tag',
                'ordering': ['tag__sort_order', 'tag__key'],
            },
        ),
        migrations.CreateModel(
            name='ObligationTerm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.obligation')),
            ],
            options={
                'db_table': 'obligation_term',
                'ordering': ['term__sort_order', 'term__key'],
            },
        ),
        migrations.CreateModel(
            name='ObligationTitle',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='titles', to='library.obligation')),
            ],
            options={
                'db_table': 'obligation_title',
                'ordering': ['language'],
                'indexes': [django.contrib.postgres.indexes.GinIndex(fields=['text'], name='obligation_title_trgm', opclasses=['gin_trgm_ops'])],
                'constraints': [models.UniqueConstraint(fields=('obligation', 'language'), name='obligation_title_language_unique'), models.UniqueConstraint(condition=models.Q(('is_original', True)), fields=('obligation',), name='obligation_title_one_original')],
            },
        ),
        migrations.CreateModel(
            name='ObligationVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version_number', models.PositiveIntegerField()),
                ('effective_from', models.DateField(blank=True, null=True)),
                ('effective_from_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('caused_by_change', models.UUIDField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='versions', to='library.obligation')),
            ],
            options={
                'db_table': 'obligation_version',
                'ordering': ['version_number'],
                'indexes': [models.Index(fields=['obligation', 'effective_from'], name='obligation_version_asof_idx')],
                'constraints': [models.UniqueConstraint(fields=('obligation', 'version_number'), name='obligation_version_unique')],
            },
        ),
        migrations.CreateModel(
            name='ObligationSummary',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='summaries', to='library.obligationversion')),
            ],
            options={
                'db_table': 'obligation_summary',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('version', 'language'), name='obligation_summary_language_unique'), models.UniqueConstraint(condition=models.Q(('is_original', True)), fields=('version',), name='obligation_summary_one_original')],
            },
        ),
        migrations.CreateModel(
            name='ProblemReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('subject_type', models.CharField(choices=[('instrument', 'instrument'), ('provision', 'provision'), ('obligation', 'obligation')], max_length=32)),
                ('subject_id', models.UUIDField()),
                ('text', models.TextField()),
                ('version_number', models.PositiveIntegerField(blank=True, null=True)),
                ('status', models.CharField(choices=[('open', 'open'), ('answered', 'answered'), ('fixed', 'fixed'), ('rejected', 'rejected')], default='open', max_length=16)),
                ('resolution_note', models.TextField(blank=True, default='')),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('language', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'problem_report',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Provision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stable_key', models.CharField(max_length=200, unique=True)),
                ('ref_label', models.CharField(max_length=200)),
                ('heading', models.TextField(blank=True)),
                ('path', models.CharField(max_length=500)),
                ('sort_order', models.IntegerField(default=0)),
                ('status', models.CharField(choices=[('active', 'active'), ('retired', 'retired')], default='active', max_length=16)),
                ('instrument', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='provisions', to='library.instrument')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='library.provision')),
            ],
            options={
                'db_table': 'provision',
                'ordering': ['sort_order', 'stable_key'],
                'indexes': [models.Index(fields=['instrument', 'sort_order'], name='provision_instrument_idx')],
            },
        ),
        migrations.CreateModel(
            name='ObligationProvision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.obligation')),
                ('provision', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.provision')),
            ],
            options={
                'db_table': 'obligation_provision',
                'ordering': ['provision__sort_order', 'provision__stable_key'],
                'constraints': [models.UniqueConstraint(fields=('obligation', 'provision'), name='obligation_provision_unique')],
            },
        ),
        migrations.AddField(
            model_name='obligation',
            name='provisions',
            field=models.ManyToManyField(related_name='obligations', through='library.ObligationProvision', to='library.provision'),
        ),
        migrations.CreateModel(
            name='ProvisionVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version_number', models.PositiveIntegerField()),
                ('effective_from', models.DateField(blank=True, null=True)),
                ('effective_from_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('effective_to', models.DateField(blank=True, null=True)),
                ('effective_to_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('transitional_note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('provision', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='versions', to='library.provision')),
            ],
            options={
                'db_table': 'provision_version',
                'ordering': ['version_number'],
                'indexes': [models.Index(fields=['provision', 'effective_from'], name='provision_version_asof_idx')],
                'constraints': [models.UniqueConstraint(fields=('provision', 'version_number'), name='provision_version_unique'), models.CheckConstraint(condition=models.Q(('effective_to__isnull', True), ('effective_from__isnull', True), ('effective_to__gt', models.F('effective_from')), _connector='OR'), name='provision_version_effective_order')],
            },
        ),
        migrations.CreateModel(
            name='ProvisionText',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='texts', to='library.provisionversion')),
            ],
            options={
                'db_table': 'provision_text',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('version', 'language'), name='provision_text_language_unique'), models.UniqueConstraint(condition=models.Q(('is_original', True)), fields=('version',), name='provision_text_one_original')],
            },
        ),
        migrations.CreateModel(
            name='RecurringDuty',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=300)),
                ('recurrence_rule', models.CharField(max_length=500)),
                ('due_rule_note', models.TextField(blank=True)),
                ('lead_days', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('active', 'active'), ('retired', 'retired')], default='active', max_length=16)),
                ('created_origin', models.CharField(choices=[('agent', 'agent'), ('user', 'user')], max_length=16)),
                ('verified_origin', models.CharField(blank=True, choices=[('agent', 'agent'), ('user', 'user')], default='', max_length=16)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recurring_duties', to='library.obligation')),
                ('recipient_authority', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.authority')),
            ],
            options={
                'db_table': 'recurring_duty',
                'ordering': ['obligation__stable_key', 'title'],
            },
        ),
        migrations.CreateModel(
            name='InstrumentRelation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('from_ref', models.CharField(blank=True, max_length=200)),
                ('to_ref', models.CharField(blank=True, max_length=200)),
                ('note', models.TextField(blank=True)),
                ('from_instrument', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='relations_out', to='library.instrument')),
                ('to_instrument', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='relations_in', to='library.instrument')),
            ],
            options={
                'db_table': 'instrument_relation',
                'ordering': ['from_instrument__stable_key', 'to_instrument__stable_key'],
                'constraints': [models.CheckConstraint(condition=models.Q(('from_instrument', models.F('to_instrument')), _negated=True), name='instrument_relation_not_self')],
            },
        ),
        *rls_operations("instrument", mixed=True, library_fence=True, column="owner_tenant_id"),
        *rls_operations("obligation", mixed=True, library_fence=True, column="owner_tenant_id"),
        *rls_operations("problem_report", mixed=True),
        *(operation for child in CHILDREN for operation in parent_policy_operations(child, *CHILDREN[child])),
        *[operation for table in APPEND_ONLY_TABLES for operation in append_only_trigger_operations(table)],
        *[operation for table in INVENTORY_TABLES for operation in library_door_trigger_operations(table, INVENTORY_DOORS)],
        *[operation for table in STAMPED_TABLES for operation in library_door_trigger_operations(table, STAMPED_DOORS)],
        *[operation for table in REFERENCE_TABLES for operation in library_door_trigger_operations(table, REFERENCE_DOORS)],
    ]
