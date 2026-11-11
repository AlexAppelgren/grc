"""collab, squashed (review 2026-11-11 B-13): comments, the people they mention, the text an
edit replaced, notifications, the proof that a mail went out, and the people and teams
taking part in a register entry or a case (COL-01, COL-02, COL-04). Every table is a tenant
table under forced row-level security with the one `tenant_isolation` policy (NFR-01, ADR
0022); `comment_revision` is append-only, so the text an edit replaced cannot be rewritten
or deleted away.

A foreign-key check does not pass through row-level security, so every reference is also a
composite `(tenant_id, …)` key, written in SQL because Django declares a key on one column
only: a person must be a member of the row's bank, a comment, a register entry, a case and
a team the row's own bank's (D-18). Not deferrable, so the refusal comes at the insert that
makes it; a nullable column is checked when it is set. apps/collab/tests_participants.py
walks `PARTICIPANT_KEYS`.

`participant_one_subject` and `participant_one_member` are the design's `num_nonnulls`
CHECKs: exactly one of the register entry and the case, exactly one of the person and the
team."""

import apps.shared.fields
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import append_only_trigger_operations, rls_operations, same_tenant_key

TABLES = ("comment", "comment_mention", "comment_revision", "notification", "email_message", "participant")

# (table, constraint, columns, referenced table, referenced columns)
MEMBER_KEYS = (
    ("comment", "comment_author_is_member", "tenant_id, author_id", "membership", "tenant_id, user_id"),
    ("comment_mention", "comment_mention_same_bank_comment", "tenant_id, comment_id", "comment", "tenant_id, id"),
    ("comment_mention", "comment_mention_user_is_member", "tenant_id, user_id", "membership", "tenant_id, user_id"),
    ("comment_revision", "comment_revision_same_bank_comment", "tenant_id, comment_id", "comment", "tenant_id, id"),
    ("comment_revision", "comment_revision_editor_is_member", "tenant_id, edited_by_id", "membership", "tenant_id, user_id"),
    ("notification", "notification_user_is_member", "tenant_id, user_id", "membership", "tenant_id, user_id"),
    ("notification", "notification_on_behalf_of_member", "tenant_id, on_behalf_of_id", "membership", "tenant_id, user_id"),
    ("email_message", "email_message_user_is_member", "tenant_id, user_id", "membership", "tenant_id, user_id"),
)


# (column, referenced table, referenced column)
PARTICIPANT_KEYS = (
    ("tenant_obligation_id", "tenant_obligation", "id"),
    ("case_id", "change_case", "id"),
    ("team_id", "team", "id"),
    ("user_id", "membership", "user_id"),
    ("added_by_id", "membership", "user_id"),
    ("removed_by_id", "membership", "user_id"),
)

# (constraint, condition)
CHECKS = (
    ("participant_one_subject", "num_nonnulls(tenant_obligation_id, case_id) = 1"),
    ("participant_one_member", "num_nonnulls(user_id, team_id) = 1"),
)


class Migration(migrations.Migration):

    replaces = [
        ('collab', '0001_comments_notifications'),
        ('collab', '0002_participant'),
    ]

    initial = True

    dependencies = [
        ('cases', '0001_squashed_0005_schema'),
        ('identity', '0002_squashed_0011_links_and_rules'),
        ('register', '0001_squashed_0004_schema'),
        ('shared', '0002_squashed_0010_links_and_rules'),
        ('taxonomy', '0002_squashed_0014_links_and_rules'),
    ]

    operations = [
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('subject_type', models.CharField(max_length=64)),
                ('subject_id', models.UUIDField()),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('edited_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'comment',
                'ordering': ['created_at', 'id'],
                'indexes': [models.Index(fields=['tenant', 'subject_type', 'subject_id', 'created_at'], name='comment_subject_idx')],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'id'), name='comment_tenant_id_unique')],
            },
        ),
        migrations.CreateModel(
            name='CommentMention',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('comment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='collab.comment')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
            ],
            options={
                'db_table': 'comment_mention',
                'ordering': ['comment', 'user'],
                'constraints': [models.UniqueConstraint(fields=('comment', 'user'), name='comment_mention_unique')],
            },
        ),
        migrations.CreateModel(
            name='CommentRevision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('comment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='collab.comment')),
                ('edited_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'comment_revision',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='EmailMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('to_email', apps.shared.fields.CIEmailField(max_length=254)),
                ('template', models.CharField(max_length=64)),
                ('subject', models.TextField()),
                ('subject_type', models.CharField(blank=True, max_length=64, null=True)),
                ('subject_id', models.UUIDField(blank=True, null=True)),
                ('status', models.CharField(choices=[('queued', 'queued'), ('sent', 'sent'), ('delivered', 'delivered'), ('bounced', 'bounced'), ('failed', 'failed')], default='queued', max_length=16)),
                ('provider_message_id', models.CharField(blank=True, max_length=255)),
                ('queued_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('sent_on', models.DateField()),
                ('error', models.TextField(blank=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
            ],
            options={
                'db_table': 'email_message',
                'ordering': ['-queued_at', '-id'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'user', 'template', 'subject_type', 'subject_id', 'sent_on'), name='email_message_once_a_day', nulls_distinct=False)],
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('assigned', 'assigned'), ('mention', 'mention'), ('signoff_requested', 'signoff_requested'), ('approval_requested', 'approval_requested'), ('due_soon', 'due_soon'), ('overdue', 'overdue'), ('escalation', 'escalation'), ('proposal_waiting', 'proposal_waiting'), ('saved_search_hit', 'saved_search_hit'), ('participant_added', 'participant_added'), ('involved_item_changed', 'involved_item_changed'), ('review_due', 'review_due')], max_length=32)),
                ('subject_type', models.CharField(max_length=64)),
                ('subject_id', models.UUIDField()),
                ('title', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('emailed_at', models.DateTimeField(blank=True, null=True)),
                ('on_behalf_of', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
            ],
            options={
                'db_table': 'notification',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(condition=models.Q(('read_at__isnull', True)), fields=['tenant', 'user', '-created_at'], name='notification_inbox_idx')],
            },
        ),
        migrations.CreateModel(
            name='Participant',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('added_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
                ('added_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('case', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='cases.changecase')),
                ('removed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('tenant_obligation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='register.tenantobligation')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
            ],
            options={
                'db_table': 'participant',
                'ordering': ['added_at', 'id'],
                'indexes': [models.Index(condition=models.Q(('removed_at__isnull', True)), fields=['tenant', 'user'], name='participant_live_user_idx'), models.Index(condition=models.Q(('removed_at__isnull', True)), fields=['tenant', 'team'], name='participant_live_team_idx'), models.Index(condition=models.Q(('removed_at__isnull', True)), fields=['tenant', 'case'], name='participant_live_case_idx'), models.Index(condition=models.Q(('removed_at__isnull', True)), fields=['tenant', 'tenant_obligation'], name='participant_live_entry_idx')],
                'constraints': [models.UniqueConstraint(condition=models.Q(('removed_at__isnull', True)), fields=('tenant_obligation', 'case', 'user', 'team'), name='participant_live_unique', nulls_distinct=False)],
            },
        ),
        *[operation for table in TABLES for operation in rls_operations(table)],
        *append_only_trigger_operations("comment_revision"),
        *[
            migrations.RunSQL(
                sql=f'ALTER TABLE "{table}" ADD CONSTRAINT {name} FOREIGN KEY ({columns}) REFERENCES "{target}" ({target_columns})',
                reverse_sql=f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS {name}',
            )
            for table, name, columns, target, target_columns in MEMBER_KEYS
        ],
        *[same_tenant_key("participant", *key) for key in PARTICIPANT_KEYS],
        *[
            migrations.RunSQL(
                sql=f'ALTER TABLE "participant" ADD CONSTRAINT {name} CHECK ({condition})',
                reverse_sql=f'ALTER TABLE "participant" DROP CONSTRAINT IF EXISTS {name}',
            )
            for name, condition in CHECKS
        ],
    ]
