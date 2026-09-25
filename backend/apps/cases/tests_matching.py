"""Recomputing a case's footprint verdict when the scope moves (FP-01 to FP-04, CAS-01, D-30).

`change_case.footprint_match` is a cache written once, at creation. Nothing kept it true
afterwards, which is why FP-S4's journey could not be driven end to end: switching a term
off changed what the feed and the inventory showed, because they re-decide per request, and
left the roadmap and the briefing reading a verdict from the week before. What is proved
here is the two things that move underneath the cache, and the four rules the recomputation
holds to while it follows them.

The events are written the only way an event is ever written — through `record()`, by the
production code that already had to write one — and delivered by the one cursor, so what
runs here is the production path and not a call to the handler.

Proven to fail 2026-09-21: with both handlers unregistered, every verdict below stayed at
the value creation cached, which is exactly the state FP-S4's `test.fixme` note described.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.cases import creation, matching, testing as case_build
from apps.cases.models import ChangeCase
from apps.shared import outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import AuditEvent, OutboxEvent
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange

SECURITIES = "regime:securities"
AML = "regime:aml"


def drain() -> None:
    """Deliver until the backlog is empty, from the library's zone."""
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


def registered(change: RegulatoryChange) -> None:
    with transaction.atomic():
        tenancy.clear_tenant()
        record(
            action=creation.CHANGE_REGISTERED,
            actor=Actor.system("watch"),
            subject_type="regulatory_change",
            subject_id=change.id,
            subject_title=change.title,
            summary=f"Registered {change.title}.",
            tenant_id=None,
        )
    drain()


def facts_updated(change: RegulatoryChange) -> None:
    """The event `apps/watch/curation.py` writes when a change's facts move."""
    with transaction.atomic():
        tenancy.clear_tenant()
        record(
            action=matching.CHANGE_FACTS_UPDATED,
            actor=Actor.system("library-editor"),
            subject_type="regulatory_change",
            subject_id=change.id,
            subject_title=change.title,
            summary="Corrected the facts of a registered change.",
            tenant_id=None,
        )
    drain()


def footprint_approved(tenant: Any) -> None:
    """The event `apps/taxonomy/footprint_logic.py` writes when a second person approves a
    footprint change. It belongs to the bank, so the cursor runs the handler in its zone."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        record(
            action=matching.FOOTPRINT_APPROVED,
            actor=Actor.system("approver"),
            subject_type="footprint_change_request",
            subject_id=uuid.uuid4(),
            subject_title="A regulatory scope change",
            summary="Regulatory scope change approved.",
            tenant_id=tenant.id,
        )
    drain()


def verdicts(tenant: Any) -> dict[uuid.UUID, bool]:
    """This bank's cached verdicts, read inside its own zone."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return {case.change_id: case.footprint_match for case in ChangeCase.objects.all()}


class RecomputeCase(TestCase):
    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        # The app's own `ready()` registered both at boot; a test that emptied the registry
        # to isolate its own may have taken them off again (apps/shared/tests_outbox.py).
        creation.register()
        matching.register()
        self.banks = case_build.two_tenants_with_different_footprints(inside=SECURITIES, outside=AML)
        drain()

    def swap_scope(self, change: RegulatoryChange, *, to: str) -> None:
        """What a library editor's correction does to a change's scope terms: the old links
        go, the new one arrives, every one of them still a suggestion (WAT-03)."""
        with watch_build.watch_write(watch_build.REASON):
            change.term_links.filter(term__isnull=False).delete()
        watch_build.term_link(change, term_ref=to)

    def move_footprint(self, tenant: Any, *, add: str) -> None:
        from apps.taxonomy.models import FootprintTerm

        with transaction.atomic():
            tenancy.activate(tenant.id)
            FootprintTerm.objects.create(tenant=tenant, term=watch_build.term(add))


class AFootprintChangeRedecidesThisBanksCases(RecomputeCase):
    def test_approving_a_footprint_change_flips_only_the_cases_it_should(self) -> None:
        ours = watch_build.change_with_timeline(terms=(SECURITIES,))
        theirs = watch_build.change_with_timeline(terms=(AML,))
        registered(ours)
        registered(theirs)
        self.assertEqual(verdicts(self.banks.inside), {ours.id: True, theirs.id: False})
        self.assertEqual(verdicts(self.banks.outside), {ours.id: False, theirs.id: True})

        self.move_footprint(self.banks.inside, add=AML)
        footprint_approved(self.banks.inside)

        self.assertEqual(
            verdicts(self.banks.inside),
            {ours.id: True, theirs.id: True},
            "the bank now watches both regimes, so both of its cases are in scope",
        )
        self.assertEqual(
            verdicts(self.banks.outside),
            {ours.id: False, theirs.id: True},
            "another bank's footprint change must not touch this bank's cases",
        )

    def test_the_recomputation_is_one_statement_for_this_bank(self) -> None:
        """A footprint change in a bank with ten thousand cases must stay one UPDATE.

        The claim is about `change_case`, not about the whole call: the audit row and the
        outbox row `record()` writes are two more statements whatever the case count is.
        Counting the statements that touch the table is what a loop would break.
        """
        for _ in range(3):
            registered(watch_build.change_with_timeline(terms=(AML,)))
        self.move_footprint(self.banks.inside, add=AML)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            with CaptureQueriesContext(connection) as captured:
                matching._recompute(self.banks.inside.id, change_id=None)
        touched = [query["sql"] for query in captured.captured_queries if '"change_case"' in query["sql"]]
        self.assertEqual(len(touched), 1, f"three cases were re-decided in {len(touched)} statements")
        self.assertTrue(touched[0].startswith("UPDATE"))
        self.assertEqual(verdicts(self.banks.inside), dict.fromkeys(verdicts(self.banks.inside), True))

    def test_a_closed_case_is_left_as_it_was(self) -> None:
        theirs = watch_build.change_with_timeline(terms=(AML,))
        registered(theirs)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            ChangeCase.objects.filter(change=theirs).update(status=CaseStatusCategory.CLOSED.value)
        self.move_footprint(self.banks.inside, add=AML)
        footprint_approved(self.banks.inside)
        self.assertEqual(
            verdicts(self.banks.inside),
            {theirs.id: False},
            "finished work keeps the verdict it was finished under",
        )

    def test_one_audit_row_per_bank_and_nothing_else_moves(self) -> None:
        """D-30: a recomputation sets no urgency, opens no triage and notifies nobody."""
        theirs = watch_build.change_with_timeline(terms=(AML,))
        registered(theirs)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            before = list(ChangeCase.objects.values("id", "status", "urgency_id", "urgency_confirmed", "owner_id"))
        self.move_footprint(self.banks.inside, add=AML)
        footprint_approved(self.banks.inside)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            after = list(ChangeCase.objects.values("id", "status", "urgency_id", "urgency_confirmed", "owner_id"))
            rows = AuditEvent.objects.filter(action=matching.RECOMPUTED, tenant_id=self.banks.inside.id)
            self.assertEqual(rows.count(), 1, "one row per bank, never one per case")
            self.assertEqual(rows.get().after["casesMoved"], 1)
        self.assertEqual(before, after, "only the cached boolean moves")

    def test_a_replayed_event_moves_nothing_and_writes_no_second_audit_row(self) -> None:
        theirs = watch_build.change_with_timeline(terms=(AML,))
        registered(theirs)
        self.move_footprint(self.banks.inside, add=AML)
        footprint_approved(self.banks.inside)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            OutboxEvent.objects.filter(topic=matching.FOOTPRINT_APPROVED).update(published_at=None)
        drain()
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            self.assertEqual(
                AuditEvent.objects.filter(action=matching.RECOMPUTED, tenant_id=self.banks.inside.id).count(),
                1,
                "a second delivery finds nothing to move, so it records nothing",
            )


class AChangesScopeRedecidesEveryBanksCase(RecomputeCase):
    def test_correcting_a_changes_scope_flips_the_verdict_in_every_bank(self) -> None:
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        registered(change)
        self.assertEqual(verdicts(self.banks.inside), {change.id: True})
        self.assertEqual(verdicts(self.banks.outside), {change.id: False})

        self.swap_scope(change, to=AML)
        facts_updated(change)

        self.assertEqual(
            verdicts(self.banks.inside),
            {change.id: False},
            "the change is about money laundering after all, so this bank is out of scope",
        )
        self.assertEqual(
            verdicts(self.banks.outside),
            {change.id: True},
            "and the bank that watches money laundering is now in scope",
        )

    def test_only_the_named_changes_cases_move(self) -> None:
        moved = watch_build.change_with_timeline(terms=(SECURITIES,))
        untouched = watch_build.change_with_timeline(terms=(SECURITIES,))
        registered(moved)
        registered(untouched)
        self.swap_scope(moved, to=AML)
        facts_updated(moved)
        self.assertEqual(verdicts(self.banks.inside), {moved.id: False, untouched.id: True})

    def test_a_case_that_falls_outside_is_still_its_owners(self) -> None:
        """Watching hides nothing (D-30): the feed's filter is what leaves it out."""
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        registered(change)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            case = ChangeCase.objects.get(change=change)
            owner = case.owner_id
        self.swap_scope(change, to=AML)
        facts_updated(change)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            still_there = ChangeCase.objects.get(change=change)
            self.assertFalse(still_there.footprint_match)
            self.assertEqual(still_there.owner_id, owner)
            self.assertEqual(still_there.status, CaseStatusCategory.NEW.value)
