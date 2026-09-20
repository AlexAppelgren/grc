"""One case per bank per change (CAS-01, WAT-05, FP-01, FP-03, AUD-01).

This is where a library fact becomes a bank's work, so what is proved here is that it
becomes exactly one piece of work in each bank and nothing in anyone else's:

- every active bank gets exactly one case in the `new` category, each caching its own
  footprint verdict, and a replayed event adds none;
- the verdict comes from the one scope rule in `apps/library/reading.py`. The proof is
  that moving the rule's own fixture — switching a dimension's `restricts_footprint` off —
  moves the verdict, which a second rule copied into this app could not do;
- a bank with no footprint terms still gets a case, because an empty restriction list
  means "no restriction" and nothing is hidden at creation;
- the agent's suggestion is carried and labelled: the urgency is a suggestion until a
  person triages, and the library's drafted "So what?" is copied unconfirmed;
- a case is written inside its own bank, with its audit row and its outbox row in the same
  transaction, and a deactivated bank gets nothing at all.

The events are written the only way an event is ever written, through `record()`, and
delivered by the one cursor, so what runs here is the production path and not a call to
the handler.

Proven to fail 2026-09-21: with the handler unregistered every test below found no case at
all, and with the footprint verdict hardcoded to true the rule tests named the bank that
should have been outside.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.test import TestCase, override_settings

from apps.cases import creation, testing as case_build
from apps.cases.models import ChangeCase
from apps.shared import factories, outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import AuditEvent, OutboxEvent, TenantStatus
from apps.shared.tenancy import library_write
from apps.taxonomy.models import CaseStatusCategory, TermDimension, Urgency
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange

SECURITIES = "regime:securities"
AML = "regime:aml"


def registered(change_id: uuid.UUID, *, title: str = "A registered change") -> OutboxEvent:
    """A `change.registered` event, written exactly as the registration writes it: through
    `record()`, in the library's zone, in the transaction of the change it describes."""
    with transaction.atomic():
        tenancy.clear_tenant()
        event = record(
            action=creation.CHANGE_REGISTERED,
            actor=Actor.system("watch"),
            subject_type="regulatory_change",
            subject_id=change_id,
            subject_title=title,
            summary=f"Registered {title}.",
            tenant_id=None,
        )
        return OutboxEvent.objects.get(audit_event=event)


def cases_of(tenant: Any) -> list[ChangeCase]:
    """This bank's cases, read inside its own zone: forced row-level security applies to the
    test runner's connection too, so an unactivated read answers for whoever came last."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return list(ChangeCase.objects.select_related("urgency").all())


def drain() -> None:
    """Deliver until the backlog is empty, from the library's zone.

    Not one batch: the reference seed and the tenant factories write hundreds of rows and
    `OUTBOX_BATCH_SIZE` is 100, so a single pass leaves a fixture's own event behind the
    seed's and the test reads a case that has not been created yet.
    """
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


class CaseCreationCase(TestCase):
    """Two banks whose footprints do not overlap, and the handler on the one cursor."""

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        # The app's own `ready()` registered the handler at boot; a test that emptied the
        # registry to isolate its own may have taken it off again (apps/shared/tests_outbox.py).
        creation.register()
        self.banks = case_build.two_tenants_with_different_footprints(inside=SECURITIES, outside=AML)
        drain()

    def deliver(self, change: RegulatoryChange) -> None:
        registered(change.id, title=change.title)
        drain()

    def counts(self, change: RegulatoryChange, *tenants: Any) -> dict[Any, int]:
        return watch_build.cases_per_tenant(change, tenants or (self.banks.inside, self.banks.outside))


class OneCasePerBankPerChange(CaseCreationCase):
    def test_each_bank_gets_exactly_one_case_in_needs_triage(self) -> None:
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        self.assertEqual(self.counts(change), {self.banks.inside: 1, self.banks.outside: 1})
        for bank in (self.banks.inside, self.banks.outside):
            with self.subTest(bank=bank.slug):
                self.assertEqual(cases_of(bank)[0].status, CaseStatusCategory.NEW.value)

    def test_each_case_caches_its_own_banks_footprint_verdict(self) -> None:
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        self.assertTrue(cases_of(self.banks.inside)[0].footprint_match)
        self.assertFalse(
            cases_of(self.banks.outside)[0].footprint_match,
            "a change outside a bank's footprint still gets a case; the verdict is cached, not the hiding",
        )

    def test_a_replayed_outbox_row_writes_nothing_new_and_raises_nothing(self) -> None:
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        with transaction.atomic():
            tenancy.clear_tenant()
            OutboxEvent.objects.filter(topic=creation.CHANGE_REGISTERED).update(published_at=None)
        self.assertEqual(outbox.deliver_batch().failed, 0, "a replay is not a failure")
        self.assertEqual(self.counts(change), {self.banks.inside: 1, self.banks.outside: 1})

    def test_registering_the_same_change_again_adds_no_second_case(self) -> None:
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        self.deliver(change)
        self.assertEqual(self.counts(change), {self.banks.inside: 1, self.banks.outside: 1})

    def test_each_case_is_written_inside_its_bank_with_its_audit_and_outbox_rows(self) -> None:
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        for bank in (self.banks.inside, self.banks.outside):
            with self.subTest(bank=bank.slug):
                case = cases_of(bank)[0]
                self.assertEqual(case.tenant_id, bank.id)
                with transaction.atomic():
                    tenancy.activate(bank.id)
                    event = AuditEvent.objects.get(action=creation.CASE_CREATED, subject_id=case.id)
                    self.assertEqual(event.tenant_id, bank.id, "a bank's case is audited in that bank's own zone")
                    self.assertEqual(event.actor_type, "system")
                    self.assertTrue(
                        OutboxEvent.objects.filter(audit_event=event, topic=creation.CASE_CREATED).exists()
                    )

    def test_a_deactivated_bank_gets_no_case(self) -> None:
        self.banks.outside.status = TenantStatus.DEACTIVATED.value
        self.banks.outside.save(update_fields=["status"])
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        self.assertEqual(self.counts(change), {self.banks.inside: 1, self.banks.outside: 0})


class TheFootprintVerdictComesFromTheOneRule(CaseCreationCase):
    """FP-01, FP-03: `apps/library/reading.py` owns the scope rule and this app applies it.
    Moving the rule's own fixture has to move the verdict; a rule copied in here could not
    follow it."""

    def test_a_dimension_that_stops_restricting_moves_the_verdict(self) -> None:
        # A dimension is a library vocabulary row, so moving the rule's fixture opens the
        # fence the way a proposal's apply step does. The product path for this is a
        # proposal; here it is the shortest way to move the rule and watch the case follow.
        with library_write("test: move the scope rule's own fixture"):
            TermDimension.objects.filter(key="regime").update(restricts_footprint=False)
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        self.assertTrue(
            cases_of(self.banks.outside)[0].footprint_match,
            "a dimension that no longer restricts cannot put a change outside a footprint",
        )

    def test_a_bank_with_no_footprint_terms_still_gets_a_case(self) -> None:
        """An empty restriction list means no restriction (playbook 4.5), and creation hides
        nothing: the bank gets its case and the verdict says what the rule says."""
        bare = factories.tenant(slug="bare-footprint")
        drain()
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        cases = cases_of(bare)
        self.assertEqual(len(cases), 1)
        self.assertTrue(cases[0].footprint_match)

    def test_a_change_with_no_scope_terms_reaches_every_bank(self) -> None:
        change = watch_build.change_with_timeline(terms=())
        self.deliver(change)
        self.assertTrue(cases_of(self.banks.inside)[0].footprint_match)
        self.assertTrue(cases_of(self.banks.outside)[0].footprint_match)

    def test_a_flag_is_not_a_scope_term(self) -> None:
        """`change_term` holds both, and only a taxonomy term narrows a footprint (WAT-03)."""
        change = watch_build.change_with_timeline(terms=(), flags=("advice_perimeter",))
        self.deliver(change)
        self.assertTrue(cases_of(self.banks.outside)[0].footprint_match)


class WhatTheAgentSuggestedStaysASuggestion(CaseCreationCase):
    """AI output is labelled until a person at the bank confirms it (WAT-05, AUD-02)."""

    def test_the_urgency_is_the_changes_suggestion_and_is_unconfirmed(self) -> None:
        change = watch_build.change_with_timeline(terms=(SECURITIES,), urgency="act_now")
        self.deliver(change)
        case = cases_of(self.banks.inside)[0]
        self.assertEqual(case.urgency.key, "act_now")
        self.assertFalse(case.urgency_confirmed, "an urgency is a suggestion until someone triages")

    def test_a_change_with_no_suggestion_falls_back_to_the_lists_default(self) -> None:
        """`change_case.urgency` is NOT NULL and the case exists from the moment the change
        does, so the urgency list's own default row is what a bank triages from."""
        change = watch_build.change_with_timeline(terms=(SECURITIES,), urgency=None)
        self.deliver(change)
        case = cases_of(self.banks.inside)[0]
        self.assertEqual(case.urgency, Urgency.objects.get(is_default=True))
        self.assertFalse(case.urgency_confirmed)

    def test_the_drafted_so_what_is_copied_unconfirmed_for_every_bank(self) -> None:
        draft = "Research payments have to be unbundled from execution from 1 October."
        change = watch_build.change_with_timeline(terms=(SECURITIES,), so_what_draft=draft)
        self.deliver(change)
        for bank in (self.banks.inside, self.banks.outside):
            with self.subTest(bank=bank.slug):
                case = cases_of(bank)[0]
                self.assertEqual(case.so_what_text, draft)
                self.assertFalse(case.so_what_confirmed)
                self.assertIsNone(case.so_what_confirmed_by_id)
                self.assertIsNone(case.so_what_confirmed_at)


class TheHandlerOnTheCursor(CaseCreationCase):
    def test_it_is_the_only_handler_for_the_change_registered_kind(self) -> None:
        self.assertEqual(outbox.handlers_for(creation.CHANGE_REGISTERED), (creation.create_cases,))

    def test_registering_twice_leaves_one_handler(self) -> None:
        creation.register()
        creation.register()
        self.assertEqual(outbox.handlers_for(creation.CHANGE_REGISTERED), (creation.create_cases,))

    def test_an_event_naming_no_change_is_delivered_without_a_case(self) -> None:
        """The handler reads the change the event names. A row that is not there leaves
        nothing to fan out, and must not wedge the cursor behind it."""
        registered(uuid.uuid4())
        self.assertEqual(outbox.deliver_batch().failed, 0)
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            self.assertEqual(ChangeCase.objects.count(), 0)


@override_settings(CASE_CREATION_BATCH=2)
class TheBatchIsBounded(CaseCreationCase):
    def test_a_change_reaching_more_banks_than_one_page_still_gives_each_exactly_one(self) -> None:
        extra = [factories.tenant(slug=f"batched-{n}") for n in range(3)]
        drain()
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.deliver(change)
        counts = self.counts(change, self.banks.inside, self.banks.outside, *extra)
        self.assertEqual(set(counts.values()), {1}, "every bank gets one case, however the read is paged")
