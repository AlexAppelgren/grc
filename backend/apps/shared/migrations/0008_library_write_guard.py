"""shared 0008 (hardening H16, ADR 0058; PRO-01, NFR-01, AC-PRO1): the database refuses a
library-zone write that never entered a door.

Until now the only thing between the app role and a shared library row was Python: the
library fence, its AST guard and the watch and index doors. Most library tables carry no
row-level security at all (they hold no tenant), and instrument and obligation check a
write with their read rule, so at the database level a bank's session could change or
delete a shared record through any path the fence does not see — the base queryset's
update, a collector's fast delete, raw SQL.

This installs `cw_library_door_guard()` and attaches it to every library-zone table as a
statement-level BEFORE INSERT, UPDATE, DELETE and TRUNCATE trigger. It refuses the write
unless the transaction-local `cw.library_door` names a door the table accepts, and lets
the schema owner through by `session_user`. Each table's doors are the trigger's arguments:

- the inventory and the library vocabularies: an approved proposal or a reference seed;
- `obligation` and `verification`: those two and the re-verification stamp (INV-06);
- the seven watch tables: the watch door only (D-64);
- `search_chunk`: the index door only (D-65);
- `language`, `jurisdiction` and `jurisdiction_label`, the library app's reference rows
  that are not `LibraryModel`s and that no proposal writes: a reference seed only.

The tables are listed here explicitly; apps/shared/tests_library_db_guard.py reads the app
registry and fails for any library table this list (or a later table's own migration)
leaves out, and for any shared row of a library-zone app that is neither. Every app whose tables are listed is a dependency, at its latest migration, so
the tables exist when the triggers are attached. A library table created after this
migration attaches the trigger in its own migration with `library_door_trigger_operations()`.
"""

from django.db import migrations

from apps.shared.migration_helpers import (
    INDEX_DOORS,
    INVENTORY_DOORS,
    REFERENCE_DOORS,
    STAMPED_DOORS,
    WATCH_DOORS,
    library_door_function_operations,
    library_door_trigger_operations,
)

INVENTORY_TABLES = (
    # library: the inventory (INV-01..INV-06)
    "authority",
    "instrument",
    "instrument_title",
    "instrument_relation",
    "provision",
    "provision_version",
    "provision_text",
    "obligation_title",
    "obligation_version",
    "obligation_summary",
    "obligation_provision",
    "obligation_term",
    "obligation_tag",
    "obligation_relation",
    # taxonomy: the library vocabularies and the taxonomy (VOC-07)
    "term_dimension",
    "term_dimension_label",
    "instrument_level",
    "instrument_level_label",
    "provision_kind",
    "provision_kind_label",
    "change_type",
    "change_type_label",
    "duty_type",
    "duty_type_label",
    "relation_type",
    "relation_type_label",
    "source_kind",
    "source_kind_label",
    "urgency",
    "urgency_label",
    "library_tag",
    "library_tag_label",
    "flag",
    "flag_label",
    "rejection_reason",
    "rejection_reason_label",
    "taxonomy_term",
    "taxonomy_term_label",
    # agents: the platform's agent definitions (AGT-01)
    "agent",
)
STAMPED_TABLES = ("obligation", "verification")
WATCH_TABLES = (
    "source",
    "source_check",
    "regulatory_change",
    "change_event",
    "change_document",
    "change_term",
    "change_obligation",
)
INDEX_TABLES = ("search_chunk",)
REFERENCE_TABLES = ("language", "jurisdiction", "jurisdiction_label")


class Migration(migrations.Migration):
    dependencies = [
        ("shared", "0007_tenant_ai_enabled"),
        ("library", "0008_standard_level_regime_required"),
        ("taxonomy", "0006_opt_in_footprint"),
        ("agents", "0003_agent_kind_review"),
        ("watch", "0001_watch"),
        ("search", "0001_search_chunk"),
    ]

    operations = [
        *library_door_function_operations(),
        *[operation for table in INVENTORY_TABLES for operation in library_door_trigger_operations(table, INVENTORY_DOORS)],
        *[operation for table in STAMPED_TABLES for operation in library_door_trigger_operations(table, STAMPED_DOORS)],
        *[operation for table in WATCH_TABLES for operation in library_door_trigger_operations(table, WATCH_DOORS)],
        *[operation for table in INDEX_TABLES for operation in library_door_trigger_operations(table, INDEX_DOORS)],
        *[operation for table in REFERENCE_TABLES for operation in library_door_trigger_operations(table, REFERENCE_DOORS)],
    ]
