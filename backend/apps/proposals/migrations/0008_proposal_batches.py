import uuid

import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import MAINTENANCE_SETTING, MIGRATOR_ROLE

"""proposals 0008 (PRO-04, AGT-05): a batch proposal and its rows, and the `obligation_scope`
kind chunk 4 cut.

A batch is one `proposal` with `is_batch` set and `row_count` rows in `proposal_batch_row`,
each holding the preview of one library record. A row is written once and decided once:
the trigger below lets the four decision columns change only while the row is pending,
only to a decision, and never to the batch's own proposer (four eyes on every row, beside
`proposal_four_eyes` on the parent), and refuses every other UPDATE and any DELETE. The
schema owner's stated fix (`cw.maintenance`, apps/shared/migration_helpers.py) passes, as it
does on every ledger, for `session_user` = the migrator alone. Existing proposals are single:
`is_batch` false and a count of none.
"""

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

    dependencies = [
        ("proposals", "0007_proposal_risk_flags"),
        ("taxonomy", "0002_rejection_reason"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalBatchRow",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("subject_type", models.CharField(max_length=64)),
                ("subject_id", models.UUIDField()),
                ("before", models.JSONField(blank=True, default=dict)),
                ("after", models.JSONField(blank=True, default=dict)),
                (
                    "decision",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("approved", "approved"),
                            ("rejected", "rejected"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "proposal_batch_row",
                "ordering": ["proposal", "subject_type", "subject_id"],
            },
        ),
        migrations.AddField(
            model_name="proposal",
            name="is_batch",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="proposal",
            name="row_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="proposal",
            name="kind",
            field=models.CharField(
                choices=[
                    ("vocabulary_create", "vocabulary_create"),
                    ("vocabulary_relabel", "vocabulary_relabel"),
                    ("vocabulary_retire", "vocabulary_retire"),
                    ("vocabulary_merge", "vocabulary_merge"),
                    ("vocabulary_restore", "vocabulary_restore"),
                    ("term_create", "term_create"),
                    ("term_update", "term_update"),
                    ("new_obligation_version", "new_obligation_version"),
                    ("new_instrument", "new_instrument"),
                    ("new_obligation", "new_obligation"),
                    ("new_provision", "new_provision"),
                    ("new_provision_version", "new_provision_version"),
                    ("obligation_scope", "obligation_scope"),
                ],
                max_length=40,
            ),
        ),
        migrations.AddConstraint(
            model_name="proposal",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("is_batch", True), ("row_count__gt", 0)),
                    models.Q(("is_batch", False), ("row_count", 0)),
                    _connector="OR",
                ),
                name="proposal_batch_row_count",
            ),
        ),
        migrations.AddField(
            model_name="proposalbatchrow",
            name="decided_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="identity.user",
            ),
        ),
        migrations.AddField(
            model_name="proposalbatchrow",
            name="proposal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="batch_rows",
                to="proposals.proposal",
            ),
        ),
        migrations.AddField(
            model_name="proposalbatchrow",
            name="rejection_reason",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="taxonomy.rejectionreason",
            ),
        ),
        migrations.AddConstraint(
            model_name="proposalbatchrow",
            constraint=models.UniqueConstraint(
                fields=("proposal", "subject_type", "subject_id"),
                name="proposal_batch_row_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="proposalbatchrow",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("decided_at__isnull", True),
                        ("decided_by__isnull", True),
                        ("decision", "pending"),
                        ("rejection_reason__isnull", True),
                    ),
                    models.Q(
                        ("decided_at__isnull", False),
                        ("decision", "approved"),
                        ("rejection_reason__isnull", True),
                    ),
                    models.Q(
                        ("decided_at__isnull", False),
                        ("decision", "rejected"),
                        ("rejection_reason__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="proposal_batch_row_decided",
            ),
        ),
        migrations.RunSQL(sql=DECISION_GUARD_SQL, reverse_sql=DROP_DECISION_GUARD_SQL),
    ]
