"""cases, squashed (review 2026-11-11 B-13): the change case, its obligation links, impact
assessment, actions, append-only transition ledger and evidence, each a tenant table under
enabled and forced row-level security (CAS-02..CAS-08).

Four eyes on the sign-off (CAS-06): the person signing off is never the one who asked for
it. Stated in SQL because Django spells "not equal" as NOT (a = b AND a IS NOT NULL), and
the four-eyes guard reads the definition back from pg_constraint.

PostgreSQL checks a foreign key with row-level security bypassed, so every reference to a
person is also a composite key on `(tenant_id, user)` into `membership`, every child's case a
composite key into `change_case (tenant_id, id)` and a case's owning team one into `team`
(INPUT_DELTAS §1, D-18). Not deferrable, so the refusal comes at the statement that tried."""

import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import append_only_trigger_operations, rls_operations, same_tenant_key

TABLES = ("change_case", "case_obligation_link", "impact_assessment", "action", "case_transition", "evidence")
# (table, column, target table, target column)
COMPOSITE_KEYS = (
    *[
        ("change_case", column, "membership", "user_id")
        for column in (
            "owner_id",
            "so_what_confirmed_by_id",
            "triaged_by_id",
            "dismissed_by_id",
            "signoff_requested_by_id",
            "signed_off_by_id",
        )
    ],
    ("change_case", "owner_team_id", "team", "id"),
    ("case_obligation_link", "case_id", "change_case", "id"),
    ("case_obligation_link", "decided_by_id", "membership", "user_id"),
    ("impact_assessment", "case_id", "change_case", "id"),
    ("impact_assessment", "saved_by_id", "membership", "user_id"),
    ("action", "case_id", "change_case", "id"),
    *[("action", column, "membership", "user_id") for column in ("owner_id", "done_by_id", "created_by_id", "removed_by_id")],
    ("case_transition", "case_id", "change_case", "id"),
    ("case_transition", "by_user_id", "membership", "user_id"),
    ("evidence", "case_id", "change_case", "id"),
    ("evidence", "uploaded_by_id", "membership", "user_id"),
)


class Migration(migrations.Migration):

    replaces = [
        ('cases', '0001_cases'),
        ('cases', '0002_case_workflow'),
        ('cases', '0003_evidence'),
        ('cases', '0004_triage_due_at'),
        ('cases', '0005_owner_team'),
    ]

    initial = True

    dependencies = [
        ('identity', '0002_squashed_0011_links_and_rules'),
        ('library', '0002_squashed_0013_links_and_rules'),
        ('shared', '0002_squashed_0010_links_and_rules'),
        ('taxonomy', '0002_squashed_0014_links_and_rules'),
        ('watch', '0002_squashed_0002_links_and_rules'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChangeCase',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('new', 'new'), ('assigned', 'assigned'), ('assessing', 'assessing'), ('implementing', 'implementing'), ('signoff', 'signoff'), ('closed', 'closed'), ('dismissed', 'dismissed')], default='new', max_length=16)),
                ('urgency_confirmed', models.BooleanField(default=False)),
                ('footprint_match', models.BooleanField()),
                ('so_what_text', models.TextField(blank=True)),
                ('so_what_confirmed', models.BooleanField(default=False)),
                ('so_what_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('briefing_week', models.DateField(blank=True, null=True)),
                ('triaged_at', models.DateTimeField(blank=True, null=True)),
                ('dismissed_at', models.DateTimeField(blank=True, null=True)),
                ('signoff_requested_at', models.DateTimeField(blank=True, null=True)),
                ('closed_note', models.TextField(blank=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('triage_due_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('change', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cases', to='watch.regulatorychange')),
                ('close_reason', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.closurereason')),
                ('dismissed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('dismissed_reason', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.dismissalreason')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('owner_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team')),
                ('signed_off_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('signoff_requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('so_what_confirmed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('sub_status', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.casesubstatus')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('triaged_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('urgency', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.urgency')),
            ],
            options={
                'db_table': 'change_case',
                'ordering': ['-created_at', 'id'],
                'indexes': [models.Index(fields=['tenant', 'status', 'urgency'], name='change_case_queue_idx'), models.Index(condition=models.Q(('status__in', ['closed', 'dismissed']), _negated=True), fields=['tenant', 'owner'], name='change_case_owner_idx')],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'change'), name='change_case_one_per_tenant'), models.CheckConstraint(condition=models.Q(models.Q(('so_what_confirmed', False), ('so_what_confirmed_at__isnull', True), ('so_what_confirmed_by__isnull', True)), models.Q(('so_what_confirmed', True), ('so_what_confirmed_at__isnull', False), ('so_what_confirmed_by__isnull', False)), _connector='OR'), name='change_case_so_what_confirmation_names_a_person'), models.UniqueConstraint(fields=('tenant', 'id'), name='change_case_tenant_id_unique'), models.CheckConstraint(condition=models.Q(models.Q(('status', 'dismissed'), _negated=True), ('dismissed_reason__isnull', False), _connector='OR'), name='change_case_dismissal_needs_a_reason'), models.CheckConstraint(condition=models.Q(models.Q(('status__in', ['assigned', 'assessing', 'implementing', 'signoff']), _negated=True), ('owner__isnull', False), _connector='OR'), name='change_case_worked_case_has_an_owner')],
            },
        ),
        migrations.CreateModel(
            name='CaseTransition',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('from_status', models.CharField(blank=True, choices=[('new', 'new'), ('assigned', 'assigned'), ('assessing', 'assessing'), ('implementing', 'implementing'), ('signoff', 'signoff'), ('closed', 'closed'), ('dismissed', 'dismissed')], max_length=16)),
                ('to_status', models.CharField(choices=[('new', 'new'), ('assigned', 'assigned'), ('assessing', 'assessing'), ('implementing', 'implementing'), ('signoff', 'signoff'), ('closed', 'closed'), ('dismissed', 'dismissed')], max_length=16)),
                ('at', models.DateTimeField(auto_now_add=True)),
                ('note', models.TextField(blank=True)),
                ('by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='cases.changecase')),
            ],
            options={
                'db_table': 'case_transition',
                'ordering': ['at', 'id'],
                'indexes': [models.Index(fields=['case', 'at'], name='case_transition_idx')],
            },
        ),
        migrations.CreateModel(
            name='CaseObligationLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('decision', models.CharField(choices=[('accepted', 'accepted'), ('removed', 'removed')], max_length=16)),
                ('decided_at', models.DateTimeField(auto_now_add=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('obligation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.obligation')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='obligation_links', to='cases.changecase')),
            ],
            options={
                'db_table': 'case_obligation_link',
                'ordering': ['-decided_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'case', 'obligation'), name='case_obligation_link_one_decision')],
            },
        ),
        migrations.CreateModel(
            name='Action',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.TextField()),
                ('due_date', models.DateField()),
                ('done_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('done_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('removed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='actions', to='cases.changecase')),
            ],
            options={
                'db_table': 'action',
                'ordering': ['due_date', 'created_at', 'id'],
                'indexes': [models.Index(condition=models.Q(('done_at__isnull', True), ('removed_at__isnull', True)), fields=['tenant', 'due_date'], name='action_open_due_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('title', ''), _negated=True), name='action_has_a_title'), models.CheckConstraint(condition=models.Q(models.Q(('done_at__isnull', True), ('done_by__isnull', True)), models.Q(('done_at__isnull', False), ('done_by__isnull', False)), _connector='OR'), name='action_done_names_a_person'), models.CheckConstraint(condition=models.Q(models.Q(('removed_at__isnull', True), ('removed_by__isnull', True)), models.Q(('removed_at__isnull', False), ('removed_by__isnull', False)), _connector='OR'), name='action_removal_names_a_person')],
            },
        ),
        migrations.CreateModel(
            name='Evidence',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('file', 'file'), ('link', 'link'), ('reference', 'reference')], max_length=16)),
                ('name', models.TextField()),
                ('storage_key', models.TextField(blank=True)),
                ('url', models.TextField(blank=True)),
                ('content_hash', models.CharField(blank=True, max_length=128)),
                ('size_bytes', models.BigIntegerField(blank=True, null=True)),
                ('mime_type', models.CharField(blank=True, max_length=255)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('removed_at', models.DateTimeField(blank=True, null=True)),
                ('scan_state', models.CharField(choices=[('pending', 'pending'), ('clean', 'clean'), ('infected', 'infected'), ('error', 'error')], default='pending', max_length=16)),
                ('scanned_at', models.DateTimeField(blank=True, null=True)),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='evidence', to='cases.changecase')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
            ],
            options={
                'db_table': 'evidence',
                'ordering': ['-uploaded_at', 'id'],
                'constraints': [models.CheckConstraint(condition=models.Q(('name', ''), _negated=True), name='evidence_has_a_name'), models.CheckConstraint(condition=models.Q(models.Q(('kind', 'file'), _negated=True), models.Q(models.Q(('storage_key', ''), _negated=True), models.Q(('content_hash', ''), _negated=True), ('size_bytes__isnull', False), models.Q(('mime_type', ''), _negated=True)), _connector='OR'), name='evidence_file_is_stored_and_hashed'), models.CheckConstraint(condition=models.Q(models.Q(('kind', 'link'), _negated=True), models.Q(models.Q(('url', ''), _negated=True), ('storage_key', '')), _connector='OR'), name='evidence_link_has_a_url'), models.CheckConstraint(condition=models.Q(models.Q(('kind', 'reference'), _negated=True), ('storage_key', ''), _connector='OR'), name='evidence_reference_has_no_file'), models.CheckConstraint(condition=models.Q(('scan_state', 'pending'), ('scanned_at__isnull', False), _connector='OR'), name='evidence_scan_names_a_time')],
            },
        ),
        migrations.CreateModel(
            name='ImpactAssessment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('applies', models.CharField(choices=[('yes', 'yes'), ('partly', 'partly'), ('no', 'no')], default='yes', max_length=16)),
                ('why', models.TextField(blank=True)),
                ('what_must_change', models.TextField(blank=True)),
                ('internal_deadline', models.DateField(blank=True, null=True)),
                ('saved', models.BooleanField(default=False)),
                ('saved_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('case', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='assessment', to='cases.changecase')),
                ('effort', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.effortsize')),
                ('saved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'impact_assessment',
                'ordering': ['case', 'id'],
                'constraints': [models.CheckConstraint(condition=models.Q(('saved', False), models.Q(('why', ''), _negated=True), _connector='OR'), name='impact_assessment_saved_says_why'), models.CheckConstraint(condition=models.Q(models.Q(('saved', False), ('saved_at__isnull', True), ('saved_by__isnull', True)), models.Q(('saved', True), ('saved_at__isnull', False), ('saved_by__isnull', False)), _connector='OR'), name='impact_assessment_saved_names_a_person')],
            },
        ),
        *[operation for table in TABLES for operation in rls_operations(table)],
        *append_only_trigger_operations("case_transition"),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE change_case ADD CONSTRAINT change_case_four_eyes CHECK (signed_off_by_id IS NULL "
                "OR (signoff_requested_by_id IS NOT NULL AND signed_off_by_id <> signoff_requested_by_id))"
            ),
            reverse_sql="ALTER TABLE change_case DROP CONSTRAINT change_case_four_eyes",
        ),
        *[same_tenant_key(*key) for key in COMPOSITE_KEYS],
    ]
