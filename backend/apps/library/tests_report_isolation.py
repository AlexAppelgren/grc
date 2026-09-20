"""A problem report stays inside the bank that filed it (INV-06, INV-S7).

Alex decided on 2026-09-19 (OWNER_RECOMMENDATIONS item 3) that a report is the bank's
own: no bleqq editor, no other bank, no agent and no model reads it, and the console has
no read window on one. The loop back to the library is closed instead by the watch
agents' re-check, which finds the deviation itself and proposes the correction (chunk 5).

That decision rests on the mixed row-level security policy on `problem_report`, which is
what these tests hold to it, on the cw_app connection where the policy is forced. The
route half of INV-S7 is in tests_scenarios.py; the writer's own proofs are in
tests_reports.py.
"""

from __future__ import annotations

import uuid

from django.db import DEFAULT_DB_ALIAS, transaction
from django.test import TransactionTestCase

from apps.library.models import ProblemReport
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy

# One sentence a reader typed, in the row and nowhere else.
SENTINEL = "Yttrandet om kundkannedom saknar det femte aret, sallsynt nog."


class ProblemReportStaysInTheBank(TransactionTestCase):
    """INV-S7: a report is the bank's own (Alex, 2026-09-19, OWNER_RECOMMENDATIONS item 3).

    Proven on the cw_app connection, where row-level security is forced and the mixed
    policy on problem_report decides: the bank that filed it reads it, another bank does
    not, and neither does a bleqq reader, who works in no tenant. Committed rows, so the
    proof runs on the application role's own connection rather than the migrator's.
    """

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.other = factories.tenant(slug="other-bank")
        self.reader = factories.member(self.tenant, roles=("reader",)).user
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant.id, using="app")
            self.report = ProblemReport.objects.using("app").create(
                tenant_id=self.tenant.id,
                reporter=self.reader,
                subject_type="obligation",
                subject_id=uuid.uuid4(),
                text=SENTINEL,
            )

    def _visible(self, tenant_id: uuid.UUID | None) -> int:
        with transaction.atomic(using="app"):
            if tenant_id is not None:
                tenancy.activate(tenant_id, using="app")
            return ProblemReport.objects.using("app").filter(id=self.report.id).count()

    def test_the_bank_that_filed_it_reads_it(self) -> None:
        self.assertEqual(self._visible(self.tenant.id), 1)

    def test_another_bank_never_sees_it(self) -> None:
        self.assertEqual(self._visible(self.other.id), 0)

    def test_no_bleqq_reader_sees_it(self) -> None:
        """The console has no read window on a report: the loop back to the library is
        closed by the watch agents' re-check, which proposes the correction (chunk 5)."""
        self.assertEqual(self._visible(None), 0)

    def tearDown(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant.id, using="app")
            ProblemReport.objects.using("app").filter(id=self.report.id).delete()

