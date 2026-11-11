"""proposals, squashed (review 2026-11-11 B-13): proposals' links to other apps' tables and
four eyes (PRO-02, AC-PRO2, D-62, ADR 0054).

`proposal_four_eyes` refuses a row whose user, key or agent repeats on both sides, and a
reviewing key that names no agent (two unbound platform keys would otherwise both carry a
NULL agent, and NULL <> NULL is unknown in SQL, so the agent clause would pass on a missing
value rather than on independence). An agent's proposal has no proposing user, so any
reviewer may decide it. Stated in SQL because Django spells "not equal" as
NOT (a = b AND a IS NOT NULL), and the four-eyes guard reads the definition back from
pg_constraint (apps/shared/tests_four_eyes.py)."""

import django.db.models.deletion
from django.db import migrations, models

FOUR_EYES_SQL = (
    'ALTER TABLE "proposal" ADD CONSTRAINT proposal_four_eyes CHECK ('
    "(reviewed_by_id IS NULL OR proposed_by_user_id IS NULL OR reviewed_by_id <> proposed_by_user_id) "
    "AND (reviewed_by_api_key_id IS NULL OR proposed_by_api_key_id IS NULL OR reviewed_by_api_key_id <> proposed_by_api_key_id) "
    "AND (reviewed_by_agent_id IS NULL OR proposed_by_agent_id IS NULL OR reviewed_by_agent_id <> proposed_by_agent_id) "
    "AND (reviewed_by_api_key_id IS NULL OR reviewed_by_agent_id IS NOT NULL))"
)


class Migration(migrations.Migration):

    replaces = [
        ('proposals', '0002_obligation_proposals'),
        ('proposals', '0003_agent_reviewer'),
        ('proposals', '0004_instrument_obligation_kinds'),
        ('proposals', '0005_provision_kinds'),
        ('proposals', '0006_idempotency_key_per_proposer'),
        ('proposals', '0007_proposal_risk_flags'),
        ('proposals', '0008_proposal_batches'),
        ('proposals', '0009_proposal_owner'),
        ('proposals', '0010_recurring_duty_kind'),
        ('proposals', '0011_control_kind'),
        ('proposals', '0012_instrument_summary_kind'),
        ('proposals', '0013_translations_kind'),
    ]

    dependencies = [
        ('agents', '0001_squashed_0001_tables'),
        ('identity', '0001_squashed_0001_tables'),
        ('proposals', '0001_squashed_0001_tables'),
        ('taxonomy', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='proposal',
            name='corrected_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='proposal',
            name='proposed_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='proposal',
            name='proposed_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='proposal',
            name='proposed_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='proposal',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='proposal',
            name='reviewed_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='proposal',
            name='reviewed_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='proposalbatchrow',
            name='decided_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='proposalbatchrow',
            name='rejection_reason',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.rejectionreason'),
        ),
        migrations.AddConstraint(
            model_name='proposal',
            constraint=models.UniqueConstraint(condition=models.Q(('idempotency_key__isnull', False), ('proposed_by_user__isnull', False)), fields=('proposed_by_user', 'idempotency_key'), name='proposal_idempotency_per_user'),
        ),
        migrations.AddConstraint(
            model_name='proposal',
            constraint=models.UniqueConstraint(condition=models.Q(('idempotency_key__isnull', False), ('proposed_by_api_key__isnull', False)), fields=('proposed_by_api_key', 'idempotency_key'), name='proposal_idempotency_per_key'),
        ),
        migrations.AddConstraint(
            model_name='proposalbatchrow',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('decided_at__isnull', True), ('decided_by__isnull', True), ('decision', 'pending'), ('rejection_reason__isnull', True)), models.Q(('decided_at__isnull', False), ('decision', 'approved'), ('rejection_reason__isnull', True)), models.Q(('decided_at__isnull', False), ('decision', 'rejected'), ('rejection_reason__isnull', False)), _connector='OR'), name='proposal_batch_row_decided'),
        ),
        migrations.RunSQL(
            sql=FOUR_EYES_SQL,
            reverse_sql='ALTER TABLE "proposal" DROP CONSTRAINT IF EXISTS proposal_four_eyes',
        ),
    ]
