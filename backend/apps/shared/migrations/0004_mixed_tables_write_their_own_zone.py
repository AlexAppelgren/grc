"""shared 0004 (hardening H15, NFR-01): the two ledgers write only their own zone.

`audit_event` and `outbox_event` are mixed: a row without a tenant is the platform's and
every tenant reads it. Their one FOR ALL policy checked writes with that read rule, so a
bank session could insert a row with no tenant and have it read by every other bank. The
write rule is now the session's own zone, and reading the platform's rows is a policy of
its own that can only read.

Both tables are append-only by trigger as well, so what this closes is the insert.
"""

from django.db import migrations

from apps.shared.migration_helpers import split_policy_operations


class Migration(migrations.Migration):
    dependencies = [("shared", "0003_append_only_guard_ignores_the_app_role")]

    operations = [
        *split_policy_operations("audit_event", mixed=True),
        *split_policy_operations("outbox_event", mixed=True),
    ]
