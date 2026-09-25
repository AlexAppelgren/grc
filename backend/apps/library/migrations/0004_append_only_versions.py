"""library 0004 (chunk 3, INV-02, INV-04, INV-05, INV-06): nothing overwritten. Provision
text versions, obligation summary versions, their translation rows and the verification
history refuse UPDATE and DELETE in the database, for every role, through the existing
cw_append_only_guard (shared 0001). A change is a new row; "as of" and the diff read the
history as it was written. Test flush uses TRUNCATE, which a row trigger does not see."""

from django.db import migrations

from apps.shared.migration_helpers import append_only_trigger_operations

TABLES = ("provision_version", "provision_text", "obligation_version", "obligation_summary", "verification")


class Migration(migrations.Migration):
    dependencies = [("library", "0003_library_records")]

    operations = [operation for table in TABLES for operation in append_only_trigger_operations(table)]
