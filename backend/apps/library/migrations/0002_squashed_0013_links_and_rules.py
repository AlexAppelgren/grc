"""library, squashed (review 2026-11-11 B-13): the library's links to other apps' tables
and the rules that read them.

- `change_obligation`, watch's coverage row of a change and an obligation, lives in its
  obligation's zone, the way 0001 puts every child of an obligation (D-57, ADR 0050). Only
  its obligation parent is written; `regulatory_change` holds no zone.
- No provision ever sits under a standard, because a standard's text is licensed and never
  held here (D-35). Three triggers hold that on every path a row can take, each raising
  `check_violation` naming `provision_not_under_standard`: on a provision inserted under or
  moved onto an instrument at a standard level (fail closed: an instrument the writer
  cannot see refuses too), on an instrument with provisions moved onto a standard level,
  and on a level given the kind `standard` while provisions sit under it. The last asks
  every zone in turn, the shared library's and each bank's, and puts the session's own zone
  back before it answers, because a bank's own provisions are hidden from every other zone.
  `standard` is the tier-one `InstrumentLevelKind` value, frozen here (playbook 4.5)."""

import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import TENANT_SETTING, parent_policy_operations

LEVEL_KIND_FUNCTION = "cw_instrument_level_kind_not_standard_with_provisions"
REFUSED = "USING ERRCODE = 'check_violation', CONSTRAINT = 'provision_not_under_standard'"

LEVEL_KIND_EVERY_ZONE = f"""
CREATE OR REPLACE FUNCTION {LEVEL_KIND_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    own_zone text := coalesce(current_setting('{TENANT_SETTING}', true), '');
    zone uuid;
    held boolean := false;
BEGIN
    IF NEW.kind = 'standard' AND OLD.kind IS DISTINCT FROM 'standard' THEN
        FOR zone IN SELECT NULL::uuid UNION ALL SELECT id FROM tenant LOOP
            PERFORM set_config('{TENANT_SETTING}', coalesce(zone::text, ''), true);
            held := EXISTS (
                SELECT 1 FROM provision JOIN instrument ON instrument.id = provision.instrument_id
                WHERE instrument.level_id = NEW.id
            );
            EXIT WHEN held;
        END LOOP;
        PERFORM set_config('{TENANT_SETTING}', own_zone, true);
        IF held THEN
            RAISE EXCEPTION 'provision_not_under_standard: level % refused the kind standard, because provisions sit under it', NEW.key
                {REFUSED};
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""

STANDARD_TRIGGERS = f"""
CREATE FUNCTION cw_provision_not_under_standard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    level_kind text;
BEGIN
    SELECT instrument_level.kind INTO level_kind
    FROM instrument
    JOIN instrument_level ON instrument_level.id = instrument.level_id
    WHERE instrument.id = NEW.instrument_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'provision_not_under_standard: % refused, because its instrument is not visible from this zone', NEW.stable_key
            {REFUSED};
    END IF;
    IF level_kind = 'standard' THEN
        RAISE EXCEPTION 'provision_not_under_standard: % refused, because the text of a standard is licensed and never held here', NEW.stable_key
            {REFUSED};
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER provision_not_under_standard BEFORE INSERT OR UPDATE OF instrument_id ON "provision"
    FOR EACH ROW EXECUTE FUNCTION cw_provision_not_under_standard();

CREATE FUNCTION cw_instrument_level_not_standard_with_provisions() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.level_id IS DISTINCT FROM OLD.level_id
        AND EXISTS (SELECT 1 FROM instrument_level WHERE id = NEW.level_id AND kind = 'standard')
        AND EXISTS (SELECT 1 FROM provision WHERE instrument_id = NEW.id) THEN
        RAISE EXCEPTION 'provision_not_under_standard: % refused the standard level, because it holds provisions', NEW.stable_key
            {REFUSED};
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER instrument_level_not_standard_with_provisions BEFORE UPDATE OF level_id ON "instrument"
    FOR EACH ROW EXECUTE FUNCTION cw_instrument_level_not_standard_with_provisions();

CREATE TRIGGER instrument_level_kind_not_standard_with_provisions BEFORE UPDATE OF kind ON "instrument_level"
    FOR EACH ROW EXECUTE FUNCTION cw_instrument_level_kind_not_standard_with_provisions();
"""

DROP_STANDARD_TRIGGERS = """
DROP TRIGGER IF EXISTS instrument_level_kind_not_standard_with_provisions ON "instrument_level";
DROP FUNCTION IF EXISTS cw_instrument_level_kind_not_standard_with_provisions();
DROP TRIGGER IF EXISTS instrument_level_not_standard_with_provisions ON "instrument";
DROP FUNCTION IF EXISTS cw_instrument_level_not_standard_with_provisions();
DROP TRIGGER IF EXISTS provision_not_under_standard ON "provision";
DROP FUNCTION IF EXISTS cw_provision_not_under_standard();
"""


class Migration(migrations.Migration):

    replaces = [
        ('library', '0002_jurisdiction'),
        ('library', '0003_library_records'),
        ('library', '0004_append_only_versions'),
        ('library', '0005_problem_report_context'),
        ('library', '0006_problem_report_writes_its_own_zone'),
        ('library', '0007_agent_confirmed_provenance'),
        ('library', '0008_standard_level_regime_required'),
        ('library', '0009_problem_report_closure'),
        ('library', '0010_recurring_duty'),
        ('library', '0011_jurisdiction_provenance'),
        ('library', '0012_private_child_rls'),
        ('library', '0013_instrument_summary'),
    ]

    dependencies = [
        ('agents', '0001_squashed_0001_tables'),
        ('identity', '0001_squashed_0001_tables'),
        ('library', '0001_squashed_0001_tables'),
        ('proposals', '0001_squashed_0001_tables'),
        ('taxonomy', '0001_squashed_0001_tables'),
        ('watch', '0002_squashed_0002_links_and_rules'),
    ]

    operations = [
        migrations.AddField(
            model_name='instrument',
            name='level',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.instrumentlevel'),
        ),
        migrations.AddField(
            model_name='instrument',
            name='regime',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='instrument',
            name='verified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='instrument',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='instrumentrelation',
            name='relation_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.relationtype'),
        ),
        migrations.AddField(
            model_name='jurisdiction',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='jurisdiction',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='obligation',
            name='duty_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.dutytype'),
        ),
        migrations.AddField(
            model_name='obligation',
            name='verified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='obligation',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='obligationrelation',
            name='relation_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.relationtype'),
        ),
        migrations.AddField(
            model_name='obligationtag',
            name='tag',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.librarytag'),
        ),
        migrations.AddField(
            model_name='obligation',
            name='tags',
            field=models.ManyToManyField(related_name='+', through='library.ObligationTag', to='taxonomy.librarytag'),
        ),
        migrations.AddField(
            model_name='obligationterm',
            name='term',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='obligation',
            name='terms',
            field=models.ManyToManyField(related_name='+', through='library.ObligationTerm', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='obligationversion',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='obligationversion',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='obligationversion',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='problemreport',
            name='closed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='problemreport',
            name='reporter',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='provision',
            name='kind',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.provisionkind'),
        ),
        migrations.AddField(
            model_name='provisionversion',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='recurringduty',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='recurringduty',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='recurringduty',
            name='created_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='recurringduty',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='verification',
            name='verified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddConstraint(
            model_name='instrumentrelation',
            constraint=models.UniqueConstraint(fields=('from_instrument', 'to_instrument', 'relation_type'), name='instrument_relation_unique'),
        ),
        migrations.AddConstraint(
            model_name='obligationtag',
            constraint=models.UniqueConstraint(fields=('obligation', 'tag'), name='obligation_tag_unique'),
        ),
        migrations.AddConstraint(
            model_name='obligationterm',
            constraint=models.UniqueConstraint(fields=('obligation', 'term'), name='obligation_term_unique'),
        ),
        migrations.AddConstraint(
            model_name='problemreport',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('closed_at__isnull', True), ('closed_by__isnull', True), ('resolution_note', ''), ('status', 'open')), models.Q(models.Q(('status', 'open'), _negated=True), models.Q(('resolution_note', ''), _negated=True), ('closed_at__isnull', False), ('closed_by__isnull', False)), _connector='OR'), name='problem_report_closed_with_note'),
        ),
        migrations.AddConstraint(
            model_name='recurringduty',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('created_origin', 'agent'), _negated=True), ('created_by_agent__isnull', False), _connector='OR'), name='recurring_duty_agent_proposal_named'),
        ),
        migrations.AddConstraint(
            model_name='recurringduty',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('verified_origin', 'agent'), _negated=True), ('verified_by_agent__isnull', False), _connector='OR'), name='recurring_duty_agent_confirmation_named'),
        ),
        migrations.AddConstraint(
            model_name='recurringduty',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('verified_origin', 'user'), _negated=True), ('approved_by__isnull', False), _connector='OR'), name='recurring_duty_person_confirmation_named'),
        ),
        migrations.AddConstraint(
            model_name='recurringduty',
            constraint=models.CheckConstraint(condition=models.Q(('verified_by_agent__isnull', True), ('created_by_agent__isnull', True), models.Q(('verified_by_agent', models.F('created_by_agent')), _negated=True), _connector='OR'), name='recurring_duty_confirmer_independent'),
        ),
        *parent_policy_operations("change_obligation", [("obligation_id", "obligation")]),
        migrations.RunSQL(sql=LEVEL_KIND_EVERY_ZONE, reverse_sql=f"DROP FUNCTION IF EXISTS {LEVEL_KIND_FUNCTION}()"),
        migrations.RunSQL(sql=STANDARD_TRIGGERS, reverse_sql=DROP_STANDARD_TRIGGERS),
    ]
