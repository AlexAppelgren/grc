"""library 0008 (INV-01, INV-02, INV-08, AC-INV2; D-35, D-37, D-39): every instrument
carries a regime, and no provision ever sits under a standard.

`instrument.regime_id` becomes NOT NULL, as schema.sql already has it (INPUT_DELTAS §1).
The regime is the sector boundary: an instrument without one would match every bank's
footprint. No default is invented for a row that has none: `SET NOT NULL` fails loudly on
it, naming the column, and the row needs its regime before this runs again. Every
instrument the prototype fixture seeds already carries one.

No provision sits under a standard, because a standard's text is licensed and never held
here (D-35). Three triggers hold that on every path a row can take there, whatever writes
it (a proposal's apply, a seed, the watch pipeline or a tenant's own record), and each
raises `check_violation` naming `provision_not_under_standard`, which Django reads as an
IntegrityError:

- `provision_not_under_standard` refuses a provision inserted under, or moved onto, an
  instrument whose level's kind is `standard`. It runs as the writer (SECURITY INVOKER, as
  apps/shared/tests_append_only.py requires), and row-level security hides another zone's
  instrument from it while foreign-key checks do not, so it fails closed: a provision under
  an instrument the writer cannot see is refused too, since it would cross a zone anyway.
- `instrument_level_not_standard_with_provisions` refuses moving an instrument that holds a
  provision onto a standard level. `provision` and `instrument_level` carry no row-level
  security, so it sees every provision.
- `instrument_level_kind_not_standard_with_provisions` refuses giving an existing level the
  kind `standard` (only the reference seed rewrites a kind) while a provision sits under an
  instrument at that level, or under an instrument the writer cannot see.

`standard` is the tier-one `InstrumentLevelKind` value, frozen here as a migration freezes
every list (playbook 4.5)."""

from django.db import migrations, models
import django.db.models.deletion

REFUSED = "USING ERRCODE = 'check_violation', CONSTRAINT = 'provision_not_under_standard'"

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

CREATE FUNCTION cw_instrument_level_kind_not_standard_with_provisions() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.kind = 'standard' AND OLD.kind IS DISTINCT FROM 'standard' AND EXISTS (
        SELECT 1
        FROM provision
        LEFT JOIN instrument ON instrument.id = provision.instrument_id
        WHERE instrument.id IS NULL OR instrument.level_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'provision_not_under_standard: level % refused the kind standard, because provisions sit under it or under an instrument not visible from this zone', NEW.key
            {REFUSED};
    END IF;
    RETURN NEW;
END;
$$;
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
        migrations.RunSQL(sql=STANDARD_TRIGGERS, reverse_sql=DROP_STANDARD_TRIGGERS),
    ]
