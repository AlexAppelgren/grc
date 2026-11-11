"""identity, squashed (review 2026-11-11 B-13): the identity tables with their final fields,
their keys to the tenant, and the rules that read only identity's tables. 0002 adds the
links to other apps' tables and the rules that read them.

Every table with a tenant is under forced row-level security (playbook 14). The mixed tables
(invitation, invitation_role, user_session, api_key, login_event) write only their own zone
and read the platform's rows through a policy of their own (H15). Four tables are read
before a tenant is known, through `identity_lookup_visible` (D-52). `login_event` is
append-only (AUD-01).

A personal access token acts as a member of its own bank: PostgreSQL checks a foreign key
without row-level security and `api_key` is mixed, so the person is also a composite
`(tenant_id, acts_as_user_id)` key into `membership` (ACC-03, D-77, ADR 0056)."""

import apps.shared.fields
import django.contrib.postgres.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import append_only_trigger_operations, rls_operations, same_tenant_key


class Migration(migrations.Migration):

    replaces = [
        ('identity', '0001_initial'),
    ]

    initial = True

    dependencies = [
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', apps.shared.fields.CIEmailField(max_length=254, unique=True)),
                ('name', models.CharField(max_length=200)),
                ('status', models.CharField(choices=[('invited', 'invited'), ('active', 'active'), ('deactivated', 'deactivated')], default='invited', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('deactivated_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'app_user',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ApiKey',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('service', 'service'), ('personal', 'personal')], default='service', max_length=16)),
                ('name', models.CharField(max_length=200)),
                ('key_prefix', models.CharField(max_length=8, unique=True)),
                ('key_hash', models.CharField(max_length=64)),
                ('scopes', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=32), blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('acts_as_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user')),
            ],
            options={
                'db_table': 'api_key',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Invitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', apps.shared.fields.CIEmailField(max_length=254)),
                ('title', models.CharField(blank=True, max_length=200)),
                ('token_hash', models.CharField(max_length=64, unique=True)),
                ('kind', models.CharField(choices=[('invite', 'invite'), ('reenrolment', 'reenrolment')], default='invite', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('first_administrator', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'invitation',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Membership',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(blank=True, max_length=200)),
                ('notification_prefs', models.JSONField(blank=True, default=dict)),
                ('last_visit_at', models.DateTimeField(blank=True, null=True)),
                ('deactivated_at', models.DateTimeField(blank=True, null=True)),
                ('out_of_office_until', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'membership',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='PlatformRole',
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
                ('permissions', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=64), blank=True, default=list)),
            ],
            options={
                'db_table': 'platform_role',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('key',), name='platform_role_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='TenantRole',
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
                ('permissions', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=64), blank=True, default=list)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'tenant_role',
                'ordering': ['sort_order', 'key'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'key'), name='tenant_role_key_unique')],
            },
        ),
        migrations.CreateModel(
            name='MembershipRole',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('membership', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='role_links', to='identity.membership')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='membership_links', to='identity.tenantrole')),
            ],
            options={
                'db_table': 'membership_role',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('membership', 'role'), name='membership_role_unique')],
            },
        ),
        migrations.AddField(
            model_name='membership',
            name='roles',
            field=models.ManyToManyField(related_name='memberships', through='identity.MembershipRole', to='identity.tenantrole'),
        ),
        migrations.CreateModel(
            name='InvitationRole',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('invitation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='role_links', to='identity.invitation')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.tenantrole')),
            ],
            options={
                'db_table': 'invitation_role',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('invitation', 'role'), name='invitation_role_unique')],
            },
        ),
        migrations.AddField(
            model_name='invitation',
            name='roles',
            field=models.ManyToManyField(related_name='+', through='identity.InvitationRole', to='identity.tenantrole'),
        ),
        migrations.CreateModel(
            name='TenantRoleLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='identity.tenantrole')),
            ],
            options={
                'db_table': 'tenant_role_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='tenant_role_label_unique')],
            },
        ),
        migrations.CreateModel(
            name='PlatformRoleAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assignments', to='identity.platformrole')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='platform_role_assignments', to='identity.user')),
            ],
            options={
                'db_table': 'platform_role_assignment',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('user', 'role'), name='platform_role_assignment_unique')],
            },
        ),
        migrations.CreateModel(
            name='OtpCode',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', apps.shared.fields.CIEmailField(max_length=254)),
                ('code_hash', models.CharField(max_length=64)),
                ('salt', models.CharField(max_length=64)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('max_attempts', models.PositiveIntegerField()),
                ('expires_at', models.DateTimeField()),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='otp_codes', to='identity.user')),
            ],
            options={
                'db_table': 'otp_code',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddField(
            model_name='membership',
            name='delegate',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='membership',
            name='invited_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='membership',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='memberships', to='identity.user'),
        ),
        migrations.CreateModel(
            name='LoginEvent',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('email', apps.shared.fields.CIEmailField(blank=True, max_length=254)),
                ('method', models.CharField(choices=[('email_code', 'email_code'), ('passkey', 'passkey'), ('api_key', 'api_key'), ('personal_token', 'personal_token')], max_length=16)),
                ('event', models.CharField(choices=[('code_sent', 'code_sent'), ('code_refused_enrolled', 'code_refused_enrolled'), ('code_failed', 'code_failed'), ('code_locked', 'code_locked'), ('enrolled', 'enrolled'), ('signin', 'signin'), ('signin_failed', 'signin_failed'), ('step_up', 'step_up'), ('step_up_failed', 'step_up_failed'), ('refresh_replay', 'refresh_replay'), ('session_revoked', 'session_revoked'), ('reenrolment_issued', 'reenrolment_issued'), ('key_used', 'key_used'), ('key_revoked', 'key_revoked'), ('key_created', 'key_created'), ('key_scopes_withheld', 'key_scopes_withheld'), ('feed_used', 'feed_used'), ('token_created', 'token_created'), ('token_used', 'token_used'), ('token_revoked', 'token_revoked'), ('credential_rate_limited', 'credential_rate_limited'), ('access_token_refused', 'access_token_refused')], max_length=32)),
                ('success', models.BooleanField()),
                ('failure_reason', models.CharField(blank=True, max_length=100)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('api_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.apikey')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='login_events', to='identity.user')),
            ],
            options={
                'db_table': 'login_event',
                'ordering': ['occurred_at', 'id'],
                'indexes': [models.Index(fields=['tenant', 'occurred_at'], name='login_event_tenant_time')],
            },
        ),
        migrations.AddField(
            model_name='invitation',
            name='accepted_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='invitation',
            name='invited_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.CreateModel(
            name='UserSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('enrolment', 'enrolment'), ('full', 'full'), ('support', 'support')], max_length=16)),
                ('refresh_token_hash', models.CharField(max_length=64, unique=True)),
                ('previous_refresh_hash', models.CharField(blank=True, max_length=64, null=True)),
                ('rotated_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField()),
                ('expires_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_reason', models.CharField(blank=True, max_length=64)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='identity.user')),
            ],
            options={
                'db_table': 'user_session',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='AuthChallenge',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('registration', 'registration'), ('authentication', 'authentication'), ('step_up', 'step_up')], max_length=16)),
                ('challenge', models.CharField(max_length=128, unique=True)),
                ('expires_at', models.DateTimeField()),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='challenges', to='identity.user')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='challenges', to='identity.usersession')),
            ],
            options={
                'db_table': 'auth_challenge',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='WebAuthnCredential',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('credential_id', models.CharField(max_length=1024, unique=True)),
                ('public_key', models.TextField()),
                ('sign_count', models.PositiveBigIntegerField(default=0)),
                ('transports', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=32), blank=True, default=list)),
                ('aaguid', models.CharField(blank=True, max_length=36)),
                ('backup_eligible', models.BooleanField(default=False)),
                ('backed_up', models.BooleanField(default=False)),
                ('device_type', models.CharField(choices=[('single_device', 'single_device'), ('multi_device', 'multi_device')], max_length=16)),
                ('nickname', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('retired_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credentials', to='identity.user')),
            ],
            options={
                'db_table': 'webauthn_credential',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='StepUpAssertion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('challenge', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.authchallenge')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='step_up_assertions', to='identity.usersession')),
                ('credential', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.webauthncredential')),
            ],
            options={
                'db_table': 'step_up_assertion',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='PlatformRoleLabel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(max_length=8)),
                ('text', models.CharField(max_length=200)),
                ('is_original', models.BooleanField(default=False)),
                ('is_machine', models.BooleanField(default=False)),
                ('vocabulary', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', to='identity.platformrole')),
            ],
            options={
                'db_table': 'platform_role_label',
                'ordering': ['language'],
                'constraints': [models.UniqueConstraint(fields=('vocabulary', 'language'), name='platform_role_label_unique')],
            },
        ),
        migrations.AddConstraint(
            model_name='membership',
            constraint=models.UniqueConstraint(fields=('tenant', 'user'), name='membership_tenant_user_unique'),
        ),
        *rls_operations("tenant_role"),
        *rls_operations("tenant_role_label"),
        *rls_operations("membership_role"),
        *rls_operations("membership", identity_lookup=True),
        *rls_operations("invitation", mixed=True, identity_lookup=True),
        *rls_operations("invitation_role", mixed=True),
        *rls_operations("user_session", mixed=True, identity_lookup=True),
        *rls_operations("api_key", mixed=True, identity_lookup=True),
        *rls_operations("login_event", mixed=True),
        *append_only_trigger_operations("login_event"),
        same_tenant_key("api_key", "acts_as_user_id", "membership", "user_id"),
    ]
