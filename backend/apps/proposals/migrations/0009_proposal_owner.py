import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import rls_operations

"""proposals 0009 (INV-07, PRO-03, OWN-03; D-57, D-89, ADR 0050, ADR 0059): a proposal may
belong to one bank, and `proposal` becomes a mixed table under forced row-level security.

`owner_tenant_id` is null for a proposal to the shared library, which is every proposal
before this migration, and names the bank for a proposal of that bank's own record. The
server sets it (`apps/proposals/logic.create`), never a request body.

The policies are the split every mixed table carries (H15, `rls_operations(mixed=True)`):
`tenant_isolation` FOR ALL on the session's own zone, the bank's own rows or, with no tenant,
the shared rows, and `library_rows_visible` FOR SELECT on the shared rows. So the console,
which runs with no tenant, reads and writes no owned row, and a bank reads the shared rows
and its own but changes only its own.

One widening beside them, FOR INSERT only: a bank's member files proposals to the shared
library from inside the bank (PRO-01, PRO-03), and those rows are shared, not the bank's.
`shared_proposal_filed` lets a bank's session insert a shared row and nothing more: one
marked as filed inside a bank, single, open and undecided. It can never update, delete or
read anything, so what a bank filed is decided in the console and nowhere else. The
four-eyes constraint `proposal_four_eyes` is untouched.
"""

SHARED_FILED_POLICY = "shared_proposal_filed"
SHARED_FILED_CHECK = (
    "owner_tenant_id IS NULL AND proposed_in_tenant AND NOT is_batch AND status = 'open' "
    "AND reviewed_at IS NULL AND applied_at IS NULL"
)


class Migration(migrations.Migration):
    dependencies = [
        ("proposals", "0008_proposal_batches"),
        ("shared", "0010_jurisdiction_proposal_door"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposal",
            name="owner_tenant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="shared.tenant",
            ),
        ),
        *rls_operations("proposal", mixed=True, column="owner_tenant_id"),
        migrations.RunSQL(
            sql=f'CREATE POLICY {SHARED_FILED_POLICY} ON "proposal" FOR INSERT WITH CHECK ({SHARED_FILED_CHECK})',
            reverse_sql=f'DROP POLICY IF EXISTS {SHARED_FILED_POLICY} ON "proposal"',
        ),
    ]
