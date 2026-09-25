"""Guard: four eyes (playbook 5, 4.2, PRD §6, AC-PRO2, AC-CAS1).

Enumerates every table in `FOUR_EYES_TABLES` and demands that the requester-is-not-
approver check constraint exists in `pg_constraint` with the expected definition. The
list is empty in Phase 0: no approval table exists yet. That is allowed, with this note,
and the list must grow in the same commit as each of: case sign-off (CAS-06), footprint
change requests (FP-02), proposals (PRO-02), risk acceptance (REG-03). Applicability
(REG-01) is not on it: one person sets it after a confirmation dialog, with an audit
event and no second approver (D-75). The permissions module's APPROVE_PERMISSIONS is
checked against the PRD so the set of approve permissions cannot drift silently either.

Proven to fail 2026-09-19 by adding ("audit_event", "audit_event_four_eyes") to the list:
the test named the table and the missing constraint.
"""

from __future__ import annotations

from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase

from apps.shared.permissions import (
    APPLICABILITY_APPROVE,
    APPROVE_PERMISSIONS,
    CASES_SIGNOFF,
    FOOTPRINT_APPROVE,
    PROPOSALS_REVIEW,
    RISK_ACCEPT_APPROVE,
)

# (table, constraint name). The constraint must compare the requester and approver
# columns: CHECK (approved_by_id IS NULL OR approved_by_id <> requested_by_id).
# Chunk 2 adds the footprint change request (FP-02) and the proposal (PRO-02).
FOUR_EYES_TABLES: list[tuple[str, str]] = [
    ("footprint_change_request", "footprint_change_request_four_eyes"),
    ("proposal", "proposal_four_eyes"),
    # Chunk 9 (c9-case-models): the case sign-off (CAS-06, AC-CAS1). The approver is
    # `signed_off_by`, the requester `signoff_requested_by`.
    ("change_case", "change_case_four_eyes"),
]

# PRO-04 (proposals 0008): a batch's parent is a `proposal` row, so `proposal_four_eyes`
# above already refuses its proposer as its reviewer. Its rows are decided one by one, and a
# check constraint cannot read the parent, so the row's trigger compares the decider with
# the batch's proposer. (table, trigger, the clause its function must hold.)
FOUR_EYES_TRIGGERS: list[tuple[str, str, str]] = [
    ("proposal_batch_row", "proposal_batch_row_decision_guard", "proposed_by_user_id = NEW.decided_by_id"),
    # c8-register-models (register 0002, REG-03): risk acceptance. The person who accepts a
    # gap's risk is never the person who asked for it.
    ("gap", "gap_four_eyes"),
]


class FourEyesGuard(TestCase):
    def test_every_four_eyes_table_has_its_check_constraint(self) -> None:
        self.assertGreaterEqual(len(FOUR_EYES_TABLES), 2, "chunk 2 registered the footprint request and the proposal")
        missing: list[str] = []
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            for table, constraint in FOUR_EYES_TABLES:
                cursor.execute(
                    "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE t.relname = %s AND c.conname = %s AND c.contype = 'c'",
                    [table, constraint],
                )
                row = cursor.fetchone()
                if row is None:
                    missing.append(f"{table}: constraint {constraint} not found")
                elif "<>" not in row[0] and "!=" not in row[0]:
                    missing.append(f"{table}: {constraint} does not compare requester and approver: {row[0]}")
        self.assertEqual(missing, [], "Four-eyes constraints missing:\n  " + "\n  ".join(missing))

    def test_the_approve_permissions_are_exactly_the_prd_list(self) -> None:
        self.assertEqual(
            APPROVE_PERMISSIONS,
            {FOOTPRINT_APPROVE, CASES_SIGNOFF, RISK_ACCEPT_APPROVE, PROPOSALS_REVIEW},
        )
        # One person sets applicability after a confirmation dialog, no second approver (D-75).
        self.assertNotIn(APPLICABILITY_APPROVE, APPROVE_PERMISSIONS)


class FourEyesTriggerGuard(TestCase):
    def test_every_four_eyes_trigger_exists_and_compares_the_decider_with_the_proposer(self) -> None:
        missing: list[str] = []
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            for table, trigger, clause in FOUR_EYES_TRIGGERS:
                cursor.execute(
                    "SELECT p.prosrc FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                    "JOIN pg_proc p ON p.oid = t.tgfoid WHERE c.relname = %s AND t.tgname = %s",
                    [table, trigger],
                )
                row = cursor.fetchone()
                if row is None:
                    missing.append(f"{table}: trigger {trigger} not found")
                elif clause not in row[0]:
                    missing.append(f"{table}: {trigger} does not compare the decider with the proposer")
        self.assertEqual(missing, [], "Four-eyes triggers missing:\n  " + "\n  ".join(missing))
