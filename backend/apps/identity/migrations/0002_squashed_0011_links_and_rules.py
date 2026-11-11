"""identity, squashed (review 2026-11-11 B-13): identity's links to other apps' tables.

PostgreSQL checks a foreign key without row-level security, and `api_key` and
`user_session` are mixed tables, so a key's agent access entry (ACC-03, ADR 0056) and a
support session's grant (TEN-06, D-49, ADR 0042) are also composite `(tenant_id, …)` keys:
neither may be another bank's."""

import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import same_tenant_key


class Migration(migrations.Migration):

    replaces = [
        ('identity', '0002_api_key_agent'),
        ('identity', '0003_mixed_tables_write_their_own_zone'),
        ('identity', '0004_login_event_feed_used'),
        ('identity', '0005_login_event_key_created_and_withheld'),
        ('identity', '0006_retire_applicability_request'),
        ('identity', '0007_credential_kinds'),
        ('identity', '0009_support_session'),
        ('identity', '0010_login_event_access_token_refused'),
        ('identity', '0011_invitation_first_administrator'),
    ]

    dependencies = [
        ('agents', '0001_squashed_0001_tables'),
        ('identity', '0001_squashed_0001_tables'),
        ('library', '0001_squashed_0001_tables'),
        ('tenants', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='api_keys', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='apikey',
            name='agent_access',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='api_keys', to='agents.agentaccess'),
        ),
        migrations.AddField(
            model_name='user',
            name='locale',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.language'),
        ),
        migrations.AddField(
            model_name='usersession',
            name='support_access',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.supportaccess'),
        ),
        migrations.AddConstraint(
            model_name='apikey',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('acts_as_user__isnull', True), ('kind', 'service')), models.Q(('acts_as_user__isnull', False), ('agent__isnull', True), ('expires_at__isnull', False), ('kind', 'personal'), ('tenant__isnull', False)), _connector='OR'), name='api_key_personal_token_fenced'),
        ),
        migrations.AddConstraint(
            model_name='apikey',
            constraint=models.CheckConstraint(condition=models.Q(('agent_access__isnull', True), models.Q(('agent__isnull', True), ('tenant__isnull', False)), _connector='OR'), name='api_key_entry_key_is_a_tenant_key'),
        ),
        migrations.AddConstraint(
            model_name='apikey',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('agent_access__isnull', True), ('kind', 'service')), ('scopes__contained_by', ['library:read', 'search:read', 'tenant:read', 'upcoming:read']), _connector='OR'), name='api_key_agent_access_reads_only'),
        ),
        migrations.AddConstraint(
            model_name='usersession',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('kind', 'support'), ('support_access__isnull', False), ('tenant__isnull', False)), models.Q(models.Q(('kind', 'support'), _negated=True), ('support_access__isnull', True)), _connector='OR'), name='user_session_support_stands_on_a_grant'),
        ),
        same_tenant_key("api_key", "agent_access_id", "agent_access", "id"),
        same_tenant_key(
            "user_session", "support_access_id", "support_access", "id", name="user_session_support_access_same_tenant"
        ),
    ]
