"""shared, squashed (review 2026-11-11 B-13): the tenant's links to the library's languages."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [
        ('shared', '0002_tenant_profile'),
        ('shared', '0003_append_only_guard_ignores_the_app_role'),
        ('shared', '0004_mixed_tables_write_their_own_zone'),
        ('shared', '0005_append_only_hatch_allowlist'),
        ('shared', '0006_outboxcursor'),
        ('shared', '0007_tenant_ai_enabled'),
        ('shared', '0008_library_write_guard'),
        ('shared', '0009_tenant_workflow_policy'),
        ('shared', '0010_jurisdiction_proposal_door'),
    ]

    dependencies = [
        ('library', '0001_squashed_0001_tables'),
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='default_language',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language'),
        ),
        migrations.AddField(
            model_name='tenantcontentlanguage',
            name='language',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language'),
        ),
        migrations.AddField(
            model_name='tenant',
            name='content_languages',
            field=models.ManyToManyField(blank=True, related_name='+', through='shared.TenantContentLanguage', to='library.language'),
        ),
        migrations.AddConstraint(
            model_name='tenantcontentlanguage',
            constraint=models.UniqueConstraint(fields=('tenant', 'language'), name='tenant_content_language_unique'),
        ),
    ]
