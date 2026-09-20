"""library 0006 (hardening H15, NFR-01): a problem report writes only its own zone.

`problem_report` is mixed: a member's report carries their tenant, a platform reader's
none. Its one FOR ALL policy checked writes with the read rule, so a bank session could
insert a report with no tenant, and change or delete the platform's. Alex decided on
2026-09-19 that a report stays inside the bank with no platform read window, so this is the
plain split every other mixed table gets: writes are the session's own zone, and the
platform's rows stay readable by everyone.

`instrument` and `obligation` are mixed on `owner_tenant_id` and keep their policy for now:
the library fence (PRO-01) is what stands between a tenant session and a shared record, and
splitting their write rule refuses every library write made with a tenant activated, which
the reference seed, the E2E seed and most tests do. HARDENING.md H16 carries it.
"""

from django.db import migrations

from apps.shared.migration_helpers import split_policy_operations


class Migration(migrations.Migration):
    dependencies = [("library", "0005_problem_report_context")]

    operations = [*split_policy_operations("problem_report", mixed=True)]
