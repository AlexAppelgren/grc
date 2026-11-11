"""home, squashed (review 2026-11-11 B-13): the briefing, its items and the calendar feed,
each a tenant table under forced row-level security (HOME-01, playbook 14). A briefing's
items are append-only. The calendar feed is read before a tenant is known, by its address,
through `identity_lookup_visible` (D-52)."""

import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import append_only_trigger_operations, rls_operations


class Migration(migrations.Migration):

    replaces = [
        ('home', '0001_home'),
        ('home', '0002_calendar_feed_address'),
    ]

    initial = True

    dependencies = [
        ('cases', '0001_squashed_0005_schema'),
        ('identity', '0002_squashed_0011_links_and_rules'),
        ('shared', '0002_squashed_0010_links_and_rules'),
    ]

    operations = [
        migrations.CreateModel(
            name='Briefing',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('week_start', models.DateField()),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('email_sent_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'briefing',
                'ordering': ['-week_start'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'week_start'), name='briefing_one_per_week')],
            },
        ),
        migrations.CreateModel(
            name='BriefingItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rank', models.PositiveIntegerField()),
                ('briefing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='home.briefing')),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='cases.changecase')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'briefing_item',
                'ordering': ['rank', 'id'],
                'constraints': [models.UniqueConstraint(fields=('briefing', 'case'), name='briefing_item_one_per_case')],
            },
        ),
        migrations.CreateModel(
            name='CalendarFeed',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('token_prefix', models.CharField(max_length=16, unique=True)),
                ('token_hash', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
            ],
            options={
                'db_table': 'calendar_feed',
                'ordering': ['-created_at', 'id'],
                'indexes': [models.Index(fields=['tenant', 'user'], name='calendar_feed_owner_idx')],
            },
        ),
        *rls_operations("briefing"),
        *rls_operations("briefing_item"),
        *rls_operations("calendar_feed", identity_lookup=True),
        *append_only_trigger_operations("briefing_item"),
    ]
