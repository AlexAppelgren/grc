"""library 0008 (INV-01, INV-02, INV-08, AC-INV2; D-35, D-37, D-39): every instrument
carries a regime, and no provision ever sits under a standard.

`instrument.regime_id` becomes NOT NULL, as schema.sql already has it (INPUT_DELTAS §1).
The regime is the sector boundary: an instrument without one would match every bank's
footprint. No default is invented for a row that has none: `SET NOT NULL` fails loudly on
it, naming the column, and the row needs its regime before this runs again. Every
instrument the prototype fixture seeds already carries one.

`provision_not_under_standard` refuses an insert of a provision, or a move of its
`instrument_id`, onto an instrument whose level's kind is `standard`, whatever the write
path (a proposal's apply, a seed, the watch pipeline or a tenant's own record): a
standard's text is licensed and never held here (D-35). It raises `check_violation`, which
Django reads as an IntegrityError. `standard` is the tier-one `InstrumentLevelKind` value,
frozen here as a migration freezes every list (playbook 4.5)."""

from django.db import migrations, models
import django.db.models.deletion

PROVISION_TRIGGER = """
CREATE FUNCTION cw_provision_not_under_standard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM instrument
        JOIN instrument_level ON instrument_level.id = instrument.level_id
        WHERE instrument.id = NEW.instrument_id AND instrument_level.kind = 'standard'
    ) THEN
        RAISE EXCEPTION 'provision_not_under_standard: % refused, because the text of a standard is licensed and never held here', NEW.stable_key
            USING ERRCODE = 'check_violation', CONSTRAINT = 'provision_not_under_standard';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER provision_not_under_standard BEFORE INSERT OR UPDATE OF instrument_id ON "provision"
    FOR EACH ROW EXECUTE FUNCTION cw_provision_not_under_standard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0007_agent_confirmed_provenance"),
        ("taxonomy", "0005_term_jurisdiction"),
    ]

    operations = [
        migrations.AlterField(
            model_name="instrument",
            name="regime",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="taxonomy.taxonomyterm"),
        ),
        migrations.RunSQL(
            sql=PROVISION_TRIGGER,
            reverse_sql='DROP TRIGGER IF EXISTS provision_not_under_standard ON "provision"; DROP FUNCTION IF EXISTS cw_provision_not_under_standard();',
        ),
    ]
