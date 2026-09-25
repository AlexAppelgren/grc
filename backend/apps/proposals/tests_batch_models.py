"""The batch proposal's rows (PRO-04, AGT-05, AC-PRO2; proposals 0008).

A batch is one `proposal` with `is_batch` set and `row_count` rows in `proposal_batch_row`,
one per library record it would change, each carrying the preview (`before` and `after`)
the reviewer decides on. A row is written once. Its decision is the only thing that may
change afterwards, once, from `pending` to `approved` or `rejected`, and never by the
person who proposed the batch: the trigger `proposal_batch_row_decision_guard` says so for
every client and `ProposalBatchRow.save()` says so first for the ORM. The batch parent is a
proposal row, so `proposal_four_eyes` refuses its proposer as its reviewer as it does for
any other proposal.

The database proofs run on the `app` alias, as cw_app, on committed rows, the way
production writes: the row triggers would refuse the migrator the same way, but the
application role is the one that must not get past them.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.identity.models import User
from apps.library.seeds import seed_languages
from apps.proposals.models import (
    DECISION_FIELDS,
    BatchRowDecision,
    BatchRowRefused,
    OriginType,
    Proposal,
    ProposalBatchRow,
    ProposalKind,
)
from apps.shared import factories
from apps.taxonomy.models import RejectionReason
from apps.taxonomy.seeds import seed_library_vocabularies

OBLIGATION = "obligation"


def batch(proposer: User, *, rows: int = 1, using: str = DEFAULT_DB_ALIAS) -> Proposal:
    """A re-tag batch as the console files it: one proposal, flagged, counting its rows."""
    return Proposal.objects.using(using).create(
        kind=ProposalKind.OBLIGATION_SCOPE.value,
        title="Re-tag outsourcing duties",
        origin=OriginType.USER.value,
        proposed_by_user=proposer,
        is_batch=True,
        row_count=rows,
    )


def row(proposal: Proposal, *, using: str = DEFAULT_DB_ALIAS) -> ProposalBatchRow:
    return ProposalBatchRow.objects.using(using).create(
        proposal=proposal,
        subject_type=OBLIGATION,
        subject_id=uuid.uuid4(),
        before={"terms": ["activity:lending"]},
        after={"terms": ["activity:lending", "activity:outsourcing"]},
    )


class TheBatchRowInTheDatabase(TransactionTestCase):
    """As cw_app on committed rows: INSERT works, one decision lands, and every other
    UPDATE, a second decision and any DELETE are refused."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        seed_languages()
        seed_library_vocabularies()
        self.reason = RejectionReason.objects.get(key="other")
        self.proposer = factories.user()
        self.reviewer = factories.user()
        with transaction.atomic(using="app"):
            self.batch = batch(self.proposer, using="app")
            self.row = row(self.batch, using="app")

    def _execute(self, statement: str, params: Sequence[Any]) -> int:
        with transaction.atomic(using="app"), connections["app"].cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone(), ("cw_app",))
            cursor.execute(statement, params)
            return cursor.rowcount

    def _decide(self, decision: BatchRowDecision, *, by: User, reason: RejectionReason | None = None) -> int:
        return self._execute(
            "UPDATE proposal_batch_row SET decision = %s, rejection_reason_id = %s, decided_by_id = %s, "
            "decided_at = now() WHERE id = %s",
            [decision.value, reason.id if reason else None, str(by.id), str(self.row.id)],
        )

    def test_the_app_role_inserts_a_row(self) -> None:
        stored = ProposalBatchRow.objects.using("app").get(id=self.row.id)
        self.assertEqual(stored.decision, BatchRowDecision.PENDING.value)
        self.assertEqual(stored.after, {"terms": ["activity:lending", "activity:outsourcing"]})

    def test_anything_but_the_decision_columns_is_refused(self) -> None:
        for statement, value in (
            ("UPDATE proposal_batch_row SET subject_id = %s WHERE id = %s", str(uuid.uuid4())),
            ("UPDATE proposal_batch_row SET subject_type = %s WHERE id = %s", "instrument"),
            ("UPDATE proposal_batch_row SET before = %s WHERE id = %s", '{"terms": []}'),
            ("UPDATE proposal_batch_row SET after = %s WHERE id = %s", '{"terms": []}'),
            ("UPDATE proposal_batch_row SET proposal_id = %s WHERE id = %s", str(batch(self.proposer).id)),
            ("UPDATE proposal_batch_row SET created_at = %s WHERE id = %s", timezone.now()),
        ):
            with self.subTest(statement=statement), self.assertRaisesMessage(DatabaseError, "only its decision may change"):
                self._execute(statement, [value, str(self.row.id)])
        self.assertEqual(ProposalBatchRow.objects.get(id=self.row.id).after, self.row.after)

    def test_a_decision_changing_the_preview_with_it_is_refused(self) -> None:
        with self.assertRaisesMessage(DatabaseError, "only its decision may change"):
            self._execute(
                "UPDATE proposal_batch_row SET decision = 'approved', decided_by_id = %s, decided_at = now(), "
                "after = '{}' WHERE id = %s",
                [str(self.reviewer.id), str(self.row.id)],
            )

    def test_delete_is_refused(self) -> None:
        with self.assertRaisesMessage(DatabaseError, "DELETE refused"):
            self._execute("DELETE FROM proposal_batch_row WHERE id = %s", [str(self.row.id)])
        self.assertTrue(ProposalBatchRow.objects.filter(id=self.row.id).exists())

    def test_one_decision_lands_and_a_second_is_refused(self) -> None:
        self.assertEqual(self._decide(BatchRowDecision.APPROVED, by=self.reviewer), 1)
        for decision, reason in (
            (BatchRowDecision.REJECTED, self.reason),
            (BatchRowDecision.APPROVED, None),
            (BatchRowDecision.PENDING, None),
        ):
            with self.subTest(decision=decision), self.assertRaisesMessage(DatabaseError, "already decided"):
                self._decide(decision, by=self.reviewer, reason=reason)
        stored = ProposalBatchRow.objects.get(id=self.row.id)
        self.assertEqual(stored.decision, BatchRowDecision.APPROVED.value)
        self.assertEqual(stored.decided_by_id, self.reviewer.id)

    def test_a_rejection_lands_with_its_reason(self) -> None:
        self.assertEqual(self._decide(BatchRowDecision.REJECTED, by=self.reviewer, reason=self.reason), 1)
        stored = ProposalBatchRow.objects.get(id=self.row.id)
        self.assertEqual((stored.decision, stored.rejection_reason_id), (BatchRowDecision.REJECTED.value, self.reason.id))

    def test_the_proposer_cannot_decide_a_row_of_their_own_batch(self) -> None:
        with self.assertRaisesMessage(DatabaseError, "four eyes"):
            self._decide(BatchRowDecision.APPROVED, by=self.proposer)
        self.assertEqual(ProposalBatchRow.objects.get(id=self.row.id).decision, BatchRowDecision.PENDING.value)

    def test_a_decision_without_its_facts_is_refused(self) -> None:
        """Decided means dated; rejected means a reason, and only then (the playbook's
        "rejection needs a reason")."""
        for statement, params in (
            ("UPDATE proposal_batch_row SET decision = 'approved' WHERE id = %s", [str(self.row.id)]),
            ("UPDATE proposal_batch_row SET decision = 'rejected', decided_at = now() WHERE id = %s", [str(self.row.id)]),
            (
                "UPDATE proposal_batch_row SET decision = 'approved', decided_at = now(), rejection_reason_id = %s "
                "WHERE id = %s",
                [str(self.reason.id), str(self.row.id)],
            ),
        ):
            with self.subTest(statement=statement), self.assertRaisesMessage(IntegrityError, "proposal_batch_row_decided"):
                self._execute(statement, params)


class TheBatchRowInPython(TestCase):
    """The ORM refuses first, with the same rule, so a caller learns it before the
    database does."""

    proposer: User
    reviewer: User
    batch: Proposal
    row: ProposalBatchRow

    @classmethod
    def setUpTestData(cls) -> None:
        cls.proposer = factories.user()
        cls.reviewer = factories.user()
        cls.batch = batch(cls.proposer)
        cls.row = row(cls.batch)

    def _decide(self, target: ProposalBatchRow) -> None:
        target.decision = BatchRowDecision.APPROVED.value
        target.decided_by = self.reviewer
        target.decided_at = timezone.now()
        target.save(update_fields=list(DECISION_FIELDS))

    def test_a_row_is_decided_once_through_save(self) -> None:
        self._decide(self.row)
        stored = ProposalBatchRow.objects.get(id=self.row.id)
        self.assertEqual((stored.decision, stored.decided_by_id), (BatchRowDecision.APPROVED.value, self.reviewer.id))
        with self.assertRaisesMessage(BatchRowRefused, "already decided"):
            self._decide(stored)

    def test_saving_anything_else_is_refused(self) -> None:
        self.row.after = {"terms": []}
        with self.assertRaisesMessage(BatchRowRefused, "only its decision may change"):
            self.row.save()
        with self.assertRaisesMessage(BatchRowRefused, "only its decision may change"):
            self.row.save(update_fields=["after", "decision"])

    def test_delete_is_refused(self) -> None:
        with self.assertRaisesMessage(BatchRowRefused, "never deleted"):
            self.row.delete()
        with self.assertRaisesMessage(BatchRowRefused, "never deleted"):
            ProposalBatchRow.objects.filter(id=self.row.id).delete()
        with self.assertRaisesMessage(BatchRowRefused, "only its decision may change"):
            ProposalBatchRow.objects.filter(id=self.row.id).update(after={})

    def test_one_row_per_record_in_a_batch(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProposalBatchRow.objects.create(
                proposal=self.batch, subject_type=OBLIGATION, subject_id=self.row.subject_id, before={}, after={}
            )

    def test_rows_read_in_a_stable_order(self) -> None:
        self.assertEqual(ProposalBatchRow._meta.ordering, ["proposal", "subject_type", "subject_id"])


class TheBatchParent(TestCase):
    """The parent is an ordinary proposal: four eyes and the counts hold on it."""

    proposer: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.proposer = factories.user()

    def test_a_proposal_is_not_a_batch_by_default(self) -> None:
        single = Proposal.objects.create(
            kind=ProposalKind.TERM_CREATE.value, title="A term", origin=OriginType.USER.value, proposed_by_user=self.proposer
        )
        self.assertEqual((single.is_batch, single.row_count), (False, 0))

    def test_a_batch_approved_by_its_proposer_is_refused(self) -> None:
        parent = batch(self.proposer, rows=2)
        parent.reviewed_by = self.proposer
        parent.reviewed_at = timezone.now()
        with self.assertRaisesMessage(IntegrityError, "proposal_four_eyes"), transaction.atomic():
            parent.save()

    def test_the_row_count_says_whether_it_is_a_batch(self) -> None:
        for is_batch, rows in ((True, 0), (False, 3)):
            with self.subTest(is_batch=is_batch), self.assertRaisesMessage(IntegrityError, "proposal_batch_row_count"):
                with transaction.atomic():
                    Proposal.objects.create(
                        kind=ProposalKind.OBLIGATION_SCOPE.value,
                        title="Counted",
                        origin=OriginType.USER.value,
                        proposed_by_user=self.proposer,
                        is_batch=is_batch,
                        row_count=rows,
                    )
