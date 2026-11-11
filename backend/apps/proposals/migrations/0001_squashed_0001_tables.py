"""proposals, squashed (review 2026-11-11 B-13): proposals, their tenant rows and batch
rows, with their final fields, their keys to the tenant, and the rules that read only
proposals' tables. 0002 adds the links to other apps' tables and the four-eyes check.

- `proposal` is mixed on `owner_tenant_id` (INV-07, PRO-03, OWN-03; D-57, D-89, ADR 0050,
  ADR 0059): a session writes its own zone and a bank reads the shared rows too (H15). One
  widening, FOR INSERT only: a bank's member files a shared, single, open and undecided
  proposal from inside the bank, which is then decided in the console and nowhere else.
- A batch row is written once and decided once (PRO-04): the decision columns change only
  while the row is pending, only to a decision, and never to the batch's own proposer; every
  other UPDATE and any DELETE is refused, except the schema owner's stated fix."""

import django.contrib.postgres.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models

from apps.shared.migration_helpers import MAINTENANCE_SETTING, MIGRATOR_ROLE, rls_operations

SHARED_FILED_POLICY = "shared_proposal_filed"
SHARED_FILED_CHECK = (
    "owner_tenant_id IS NULL AND proposed_in_tenant AND NOT is_batch AND status = 'open' "
    "AND reviewed_at IS NULL AND applied_at IS NULL"
)

DECISION_GUARD = "cw_proposal_batch_row_guard"

DECISION_GUARD_SQL = f"""
CREATE FUNCTION {DECISION_GUARD}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('{MAINTENANCE_SETTING}', true) = 'on' AND session_user = '{MIGRATOR_ROLE}' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'proposal_batch_row is append-only: DELETE refused' USING ERRCODE = 'raise_exception';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.proposal_id IS DISTINCT FROM OLD.proposal_id
       OR NEW.subject_type IS DISTINCT FROM OLD.subject_type
       OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
       OR NEW.before IS DISTINCT FROM OLD.before
       OR NEW.after IS DISTINCT FROM OLD.after
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'proposal_batch_row is written once: only its decision may change'
            USING ERRCODE = 'raise_exception';
    END IF;
    IF OLD.decision <> 'pending' OR NEW.decision = 'pending' THEN
        RAISE EXCEPTION 'proposal_batch_row % is already decided or not being decided: a decision is made once', OLD.id
            USING ERRCODE = 'raise_exception';
    END IF;
    IF NEW.decided_by_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM proposal p WHERE p.id = NEW.proposal_id AND p.proposed_by_user_id = NEW.decided_by_id
    ) THEN
        RAISE EXCEPTION 'proposal_batch_row %: four eyes: the batch''s proposer cannot decide its rows', OLD.id
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER proposal_batch_row_decision_guard BEFORE UPDATE OR DELETE ON "proposal_batch_row"
    FOR EACH ROW EXECUTE FUNCTION {DECISION_GUARD}();
"""

DROP_DECISION_GUARD_SQL = (
    'DROP TRIGGER IF EXISTS proposal_batch_row_decision_guard ON "proposal_batch_row"; '
    f"DROP FUNCTION IF EXISTS {DECISION_GUARD}();"
)


class Migration(migrations.Migration):

    replaces = [
        ('proposals', '0001_initial'),
    ]

    initial = True

    dependencies = [
        ('shared', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='Proposal',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('vocabulary_create', 'vocabulary_create'), ('vocabulary_relabel', 'vocabulary_relabel'), ('vocabulary_retire', 'vocabulary_retire'), ('vocabulary_merge', 'vocabulary_merge'), ('vocabulary_restore', 'vocabulary_restore'), ('term_create', 'term_create'), ('term_update', 'term_update'), ('new_obligation_version', 'new_obligation_version'), ('new_instrument', 'new_instrument'), ('new_obligation', 'new_obligation'), ('new_provision', 'new_provision'), ('new_provision_version', 'new_provision_version'), ('obligation_scope', 'obligation_scope'), ('new_recurring_duty', 'new_recurring_duty'), ('new_control', 'new_control'), ('new_instrument_summary', 'new_instrument_summary'), ('new_translations', 'new_translations')], max_length=40)),
                ('target_type', models.CharField(blank=True, max_length=64)),
                ('target_id', models.UUIDField(blank=True, null=True)),
                ('change_id', models.UUIDField(blank=True, null=True)),
                ('title', models.CharField(max_length=500)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('field_sources', models.JSONField(blank=True, default=dict)),
                ('source_label', models.CharField(blank=True, max_length=500)),
                ('source_url', models.URLField(blank=True, max_length=2000)),
                ('risk_flags', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=40), blank=True, default=list)),
                ('effective_from', models.DateField(blank=True, null=True)),
                ('origin', models.CharField(choices=[('agent', 'agent'), ('user', 'user')], max_length=16)),
                ('agent_run_id', models.UUIDField(blank=True, null=True)),
                ('model', models.CharField(blank=True, max_length=200)),
                ('idempotency_key', models.CharField(blank=True, max_length=200, null=True)),
                ('proposed_in_tenant', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('open', 'open'), ('approved', 'approved'), ('rejected', 'rejected'), ('superseded', 'superseded')], default='open', max_length=16)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_code', models.CharField(blank=True, max_length=64)),
                ('review_note', models.TextField(blank=True)),
                ('corrected_payload', models.JSONField(blank=True, null=True)),
                ('corrected_at', models.DateTimeField(blank=True, null=True)),
                ('applied_at', models.DateTimeField(blank=True, null=True)),
                ('is_batch', models.BooleanField(default=False)),
                ('row_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner_tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'proposal',
                'ordering': ['created_at', 'id'],
                'indexes': [models.Index(fields=['status', 'created_at'], name='proposal_queue_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('is_batch', True), ('row_count__gt', 0)), models.Q(('is_batch', False), ('row_count', 0)), _connector='OR'), name='proposal_batch_row_count')],
            },
        ),
        migrations.CreateModel(
            name='ProposalBatchRow',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('subject_type', models.CharField(max_length=64)),
                ('subject_id', models.UUIDField()),
                ('before', models.JSONField(blank=True, default=dict)),
                ('after', models.JSONField(blank=True, default=dict)),
                ('decision', models.CharField(choices=[('pending', 'pending'), ('approved', 'approved'), ('rejected', 'rejected')], default='pending', max_length=16)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('proposal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='batch_rows', to='proposals.proposal')),
            ],
            options={
                'db_table': 'proposal_batch_row',
                'ordering': ['proposal', 'subject_type', 'subject_id'],
                'constraints': [models.UniqueConstraint(fields=('proposal', 'subject_type', 'subject_id'), name='proposal_batch_row_unique')],
            },
        ),
        migrations.CreateModel(
            name='ProposalTenant',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('proposal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tenant_links', to='proposals.proposal')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='shared.tenant')),
            ],
            options={
                'db_table': 'proposal_tenant',
                'ordering': ['created_at', 'id'],
                'constraints': [models.UniqueConstraint(fields=('proposal', 'tenant'), name='proposal_tenant_unique')],
            },
        ),
        *rls_operations("proposal", mixed=True, column="owner_tenant_id"),
        migrations.RunSQL(
            sql=f'CREATE POLICY {SHARED_FILED_POLICY} ON "proposal" FOR INSERT WITH CHECK ({SHARED_FILED_CHECK})',
            reverse_sql=f'DROP POLICY IF EXISTS {SHARED_FILED_POLICY} ON "proposal"',
        ),
        *rls_operations("proposal_tenant"),
        migrations.RunSQL(sql=DECISION_GUARD_SQL, reverse_sql=DROP_DECISION_GUARD_SQL),
    ]
