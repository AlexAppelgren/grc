"""search, squashed (review 2026-11-11 B-13): the search index and the evaluation set.

- `search_chunk` is mixed on `owner_tenant_id`, "shared or mine" (SRC-01, INV-07), and takes
  the index door alone (D-65, ADR 0058).
- `eval_question` and `eval_run` are the platform staff's own test of search (SRC-05,
  ADM-02, INPUT_DELTAS §14), neither a tenant table nor a library one: forced row-level
  security with one policy, `platform_only`, whose USING and WITH CHECK both demand that no
  tenant is active, so a bank's session sees and writes nothing. They take the evaluation
  door alone. The RLS guard pins the shape (`PLATFORM_ONLY_TABLES` in
  apps/shared/tests_rls.py)."""

import django.contrib.postgres.fields
import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
import django.utils.timezone
import pgvector.django.indexes
import pgvector.django.vector
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import (
    EVAL_DOORS,
    INDEX_DOORS,
    TENANT_EXPRESSION,
    library_door_trigger_operations,
    rls_operations,
)

PLATFORM_ONLY_POLICY = "platform_only"
NO_TENANT = f"{TENANT_EXPRESSION} IS NULL"


def platform_only(table: str) -> list[migrations.RunSQL]:
    return [
        migrations.RunSQL(
            sql=f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=f'CREATE POLICY {PLATFORM_ONLY_POLICY} ON "{table}" FOR ALL USING ({NO_TENANT}) WITH CHECK ({NO_TENANT})',
            reverse_sql=f'DROP POLICY IF EXISTS {PLATFORM_ONLY_POLICY} ON "{table}"',
        ),
    ]


class Migration(migrations.Migration):

    replaces = [
        ('search', '0001_search_chunk'),
        ('search', '0002_eval_sets'),
        ('search', '0003_eval_sets_door'),
        ('search', '0004_evalquestion_via'),
    ]

    initial = True

    dependencies = [
        ('library', '0002_squashed_0013_links_and_rules'),
        ('shared', '0002_squashed_0010_links_and_rules'),
    ]

    operations = [
        migrations.CreateModel(
            name='EvalRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('run_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('config', models.JSONField()),
                ('metrics', models.JSONField()),
                ('results', models.JSONField()),
            ],
            options={
                'db_table': 'eval_run',
                'ordering': ['-run_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='EvalQuestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.SlugField(max_length=40, unique=True)),
                ('question', models.TextField()),
                ('expected', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=200), blank=True, default=list)),
                ('match_kind', models.CharField(choices=[('keyword', 'keyword'), ('concept', 'concept'), ('both', 'both')], max_length=10)),
                ('as_of', models.DateField(blank=True, null=True)),
                ('via', models.CharField(choices=[('search', 'search'), ('ask', 'ask')], default='search', max_length=6)),
                ('notes', models.TextField(blank=True, default='')),
                ('active', models.BooleanField(default=True)),
                ('language', models.ForeignKey(db_column='lang', on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
            ],
            options={
                'db_table': 'eval_question',
                'ordering': ['key'],
            },
        ),
        migrations.CreateModel(
            name='SearchChunk',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('source_type', models.CharField(choices=[('provision_version', 'Provision version'), ('obligation_version', 'Obligation version'), ('change', 'Regulatory change')], max_length=20)),
                ('source_id', models.UUIDField()),
                ('title', models.TextField()),
                ('body', models.TextField()),
                ('hierarchy_path', models.TextField(blank=True, default='')),
                ('valid_from', models.DateField(blank=True, null=True)),
                ('valid_to', models.DateField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('tsv', models.GeneratedField(db_persist=True, expression=models.Case(models.When(language='en', then=django.contrib.postgres.search.CombinedSearchVector(django.contrib.postgres.search.SearchVector('title', config=models.Value('english'), weight='A'), '||', django.contrib.postgres.search.SearchVector('body', config=models.Value('english'), weight='B'), django.contrib.postgres.search.SearchConfig(models.Value('english')))), models.When(language='sv', then=django.contrib.postgres.search.CombinedSearchVector(django.contrib.postgres.search.SearchVector('title', config=models.Value('swedish'), weight='A'), '||', django.contrib.postgres.search.SearchVector('body', config=models.Value('swedish'), weight='B'), django.contrib.postgres.search.SearchConfig(models.Value('swedish')))), models.When(language='da', then=django.contrib.postgres.search.CombinedSearchVector(django.contrib.postgres.search.SearchVector('title', config=models.Value('danish'), weight='A'), '||', django.contrib.postgres.search.SearchVector('body', config=models.Value('danish'), weight='B'), django.contrib.postgres.search.SearchConfig(models.Value('danish')))), models.When(language='nb', then=django.contrib.postgres.search.CombinedSearchVector(django.contrib.postgres.search.SearchVector('title', config=models.Value('norwegian'), weight='A'), '||', django.contrib.postgres.search.SearchVector('body', config=models.Value('norwegian'), weight='B'), django.contrib.postgres.search.SearchConfig(models.Value('norwegian')))), models.When(language='fi', then=django.contrib.postgres.search.CombinedSearchVector(django.contrib.postgres.search.SearchVector('title', config=models.Value('finnish'), weight='A'), '||', django.contrib.postgres.search.SearchVector('body', config=models.Value('finnish'), weight='B'), django.contrib.postgres.search.SearchConfig(models.Value('finnish')))), default=django.contrib.postgres.search.CombinedSearchVector(django.contrib.postgres.search.SearchVector('title', config=models.Value('english'), weight='A'), '||', django.contrib.postgres.search.SearchVector('body', config=models.Value('english'), weight='B'), django.contrib.postgres.search.SearchConfig(models.Value('english')))), output_field=django.contrib.postgres.search.SearchVectorField())),
                ('embedding', pgvector.django.vector.VectorField(blank=True, dimensions=1024, null=True)),
                ('embedding_model', models.CharField(blank=True, default='', max_length=120)),
                ('embedding_version', models.CharField(blank=True, default='', max_length=40)),
                ('embedded_at', models.DateTimeField(blank=True, null=True)),
                ('language', models.ForeignKey(db_column='lang', on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language', to_field='key')),
                ('owner_tenant', models.ForeignKey(blank=True, db_column='owner_tenant_id', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'search_chunk',
                'ordering': ['source_type', 'source_id', 'language_id'],
                'indexes': [django.contrib.postgres.indexes.GinIndex(fields=['tsv'], name='search_chunk_tsv_idx'), pgvector.django.indexes.HnswIndex(ef_construction=64, fields=['embedding'], m=16, name='search_chunk_embedding_idx', opclasses=['vector_cosine_ops']), models.Index(fields=['valid_from', 'valid_to'], name='search_chunk_validity_idx')],
                'constraints': [models.UniqueConstraint(fields=('source_type', 'source_id', 'language'), name='search_chunk_source_unique')],
            },
        ),
        *rls_operations("search_chunk", mixed=True, column="owner_tenant_id"),
        *library_door_trigger_operations("search_chunk", INDEX_DOORS),
        *platform_only("eval_question"),
        *platform_only("eval_run"),
        *library_door_trigger_operations("eval_question", EVAL_DOORS),
        *library_door_trigger_operations("eval_run", EVAL_DOORS),
    ]
