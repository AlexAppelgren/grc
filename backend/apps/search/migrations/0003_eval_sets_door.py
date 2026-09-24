"""search 0003 (H16, ADR 0058; SRC-05): the evaluation set's two tables take the library
door trigger, with a door of their own.

`eval_question` and `eval_run` hold no tenant, in an app whose shared rows are library-zone
rows, so the door census of apps/shared/tests_library_db_guard.py counts them. They are not
library records: no proposal carries them and no bank reads them, which search 0002's
`platform_only` policy already holds for a session with a tenant active. What the policy
does not hold is a write in the platform's zone that never entered a door. The trigger
refuses it unless the `eval` door is open, which only `create_question()` and `record_run()`
in apps/search/eval_sets.py open, and the schema owner passes as everywhere else. So the
tables have both layers, and neither the inventory's doors nor the seed door reach them."""

from django.db import migrations

from apps.shared.migration_helpers import EVAL_DOORS, library_door_trigger_operations


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0002_eval_sets"),
        ("shared", "0008_library_write_guard"),
    ]

    operations = [
        *library_door_trigger_operations("eval_question", EVAL_DOORS),
        *library_door_trigger_operations("eval_run", EVAL_DOORS),
    ]
