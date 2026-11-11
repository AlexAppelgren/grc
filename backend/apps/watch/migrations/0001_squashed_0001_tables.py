"""watch, squashed (review 2026-11-11 B-13): the watch tables with their final fields,
their keys to the tenant, the "shared or mine" rule on `source` (WAT-01, INV-07) and the
watch door on every watch table (D-64, ADR 0058). 0002 adds the links to other apps' tables;
`change_obligation`'s parent policies are library's (library 0002)."""

import django.contrib.postgres.fields
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import WATCH_DOORS, library_door_trigger_operations, rls_operations

WATCH_TABLES = (
    "source",
    "source_check",
    "regulatory_change",
    "change_event",
    "change_document",
    "change_term",
    "change_obligation",
)


class Migration(migrations.Migration):

    replaces = [
        ('watch', '0001_watch'),
    ]

    initial = True

    dependencies = [
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegulatoryChange',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stable_key', models.SlugField(max_length=120, unique=True)),
                ('title', models.CharField(max_length=500)),
                ('change_type_suggested', models.BooleanField(default=True)),
                ('change_type_confidence', models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True)),
                ('change_type_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('authority_label', models.CharField(max_length=200)),
                ('published_on', models.DateField(blank=True, null=True)),
                ('published_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('summary', models.TextField(blank=True)),
                ('so_what_draft', models.TextField(blank=True)),
                ('key_date', models.DateField(blank=True, null=True)),
                ('key_date_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('key_date_label', models.CharField(blank=True, max_length=200)),
                ('recurrence_rule', models.CharField(blank=True, max_length=500)),
                ('source_label', models.CharField(max_length=500)),
                ('source_url', models.URLField(max_length=2000)),
                ('status', models.CharField(choices=[('active', 'active'), ('superseded', 'superseded'), ('withdrawn', 'withdrawn')], default='active', max_length=16)),
                ('origin', models.CharField(choices=[('agent', 'agent'), ('user', 'user')], max_length=16)),
                ('model', models.CharField(blank=True, max_length=200)),
                ('first_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('superseded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='supersedes', to='watch.regulatorychange')),
            ],
            options={
                'db_table': 'regulatory_change',
                'ordering': [models.OrderBy(models.F('key_date'), descending=True, nulls_last=True), '-first_seen_at', 'id'],
                'indexes': [models.Index(condition=models.Q(('status', 'active')), fields=['key_date'], name='regulatory_change_key_date_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('superseded_by', models.F('id')), _negated=True), name='regulatory_change_not_self_superseded'), models.CheckConstraint(condition=models.Q(('change_type_confidence__isnull', True), models.Q(('change_type_confidence__gte', 0), ('change_type_confidence__lte', 1)), _connector='OR'), name='regulatory_change_type_confidence_range')],
            },
        ),
        migrations.CreateModel(
            name='ChangeTerm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('confidence', models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True)),
                ('suggested', models.BooleanField(default=True)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('change', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='term_links', to='watch.regulatorychange')),
            ],
            options={
                'db_table': 'change_term',
                'constraints': [models.CheckConstraint(condition=models.Q(('confidence__isnull', True), models.Q(('confidence__gte', 0), ('confidence__lte', 1)), _connector='OR'), name='change_term_confidence_range')],
            },
        ),
        migrations.CreateModel(
            name='ChangeObligation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('origin', models.CharField(choices=[('agent', 'agent'), ('user', 'user')], max_length=16)),
                ('confidence', models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('change', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='obligation_links', to='watch.regulatorychange')),
            ],
            options={
                'db_table': 'change_obligation',
                'constraints': [models.CheckConstraint(condition=models.Q(('confidence__isnull', True), models.Q(('confidence__gte', 0), ('confidence__lte', 1)), _connector='OR'), name='change_obligation_confidence_range')],
            },
        ),
        migrations.CreateModel(
            name='ChangeEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('label', models.CharField(max_length=200)),
                ('event_date', models.DateField(blank=True, null=True)),
                ('date_precision', models.CharField(choices=[('day', 'day'), ('month', 'month'), ('quarter', 'quarter'), ('year', 'year')], default='day', max_length=8)),
                ('occurred', models.BooleanField(default=False)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('source_url', models.URLField(blank=True, max_length=2000)),
                ('change', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='watch.regulatorychange')),
            ],
            options={
                'db_table': 'change_event',
                'ordering': ['sort_order', 'id'],
                'indexes': [models.Index(fields=['change', 'sort_order'], name='change_event_change_idx')],
            },
        ),
        migrations.CreateModel(
            name='ChangeDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('url', models.URLField(max_length=2000)),
                ('title', models.CharField(blank=True, max_length=500)),
                ('publisher', models.CharField(blank=True, max_length=200)),
                ('fetched_at', models.DateTimeField(blank=True, null=True)),
                ('content_hash', models.CharField(blank=True, max_length=128)),
                ('is_primary', models.BooleanField(default=False)),
                ('is_duplicate', models.BooleanField(default=False)),
                ('risk_flags', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=40), blank=True, default=list)),
                ('change', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='watch.regulatorychange')),
            ],
            options={
                'db_table': 'change_document',
                'ordering': ['-is_primary', 'url'],
                'constraints': [models.UniqueConstraint(fields=('change', 'url'), name='change_document_url_unique')],
            },
        ),
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200, unique=True)),
                ('url', models.URLField(blank=True, max_length=2000)),
                ('check_frequency', models.CharField(choices=[('daily', 'daily'), ('weekly', 'weekly'), ('monthly', 'monthly')], default='weekly', max_length=16)),
                ('active', models.BooleanField(default=True)),
                ('owner_tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'source',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='SourceCheck',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('checked_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(choices=[('ok', 'ok'), ('failed', 'failed')], max_length=16)),
                ('items_found', models.PositiveIntegerField(default=0)),
                ('error', models.TextField(blank=True)),
                ('kind', models.CharField(choices=[('sweep', 'sweep'), ('recheck', 'recheck')], default='sweep', max_length=16)),
                ('subject_type', models.CharField(blank=True, choices=[('instrument', 'instrument'), ('provision', 'provision'), ('obligation', 'obligation')], max_length=16)),
                ('subject_id', models.UUIDField(blank=True, null=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='checks', to='watch.source')),
            ],
            options={
                'db_table': 'source_check',
                'ordering': ['-checked_at', 'id'],
                'indexes': [models.Index(fields=['source', '-checked_at'], name='source_check_latest_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('kind', 'recheck'), models.Q(('subject_type', ''), _negated=True), ('subject_id__isnull', False)), models.Q(models.Q(('kind', 'recheck'), _negated=True), ('subject_type', ''), ('subject_id__isnull', True)), _connector='OR'), name='source_check_recheck_names_a_subject')],
            },
        ),
        *rls_operations("source", mixed=True, column="owner_tenant_id"),
        *[operation for table in WATCH_TABLES for operation in library_door_trigger_operations(table, WATCH_DOORS)],
    ]
