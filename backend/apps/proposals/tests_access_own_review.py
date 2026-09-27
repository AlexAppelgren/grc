"""Findings of the security review of agent access and the bank's own records
(security-review-c11-access-d89, docs/reviews/CHUNK11_ACCESS_OWN_REVIEW.md) on applying a
proposal. Each test was written first and failed before its fix.

M6: a stable key is unique across the whole library, both zones, but the check that a key
is free reads under row-level security and so sees only the caller's zone. A bank's own
record holding a key made the console's approval of a shared record with the same key,
or another bank's approval, fail on the database's unique index as an unhandled error
(500). It is now the same 409 `duplicate_key` a visible key answers, and nothing is written.
"""

from __future__ import annotations

from apps.library import testing as library_build
from apps.library.models import Instrument, Obligation
from apps.proposals.models import Proposal, ProposalStatus
from apps.proposals.tests_kinds import INSTRUMENT_KEY, OBLIGATION_KEY, KindsTestCase, instrument_body, obligation_body
from apps.shared import factories, tenancy


class AKeyHeldInAnotherZoneIsADuplicate(KindsTestCase):
    def test_a_banks_own_record_holding_the_key_answers_duplicate_key(self) -> None:
        instrument = self._filed(instrument_body())
        obligation = self._filed(obligation_body())
        bank = factories.tenant(slug="key-squat")
        tenancy.activate(bank.id)
        own = library_build.instrument(key=INSTRUMENT_KEY, regime="regime:securities", owner_tenant=bank)
        library_build.obligation(own, key=OBLIGATION_KEY, owner_tenant=bank)
        tenancy.clear_tenant()
        for filed in (instrument, obligation):
            with self.subTest(kind=filed["kind"]):
                self._refused(self._approve(filed["id"]), 409, "duplicate_key")
                self.assertEqual(Proposal.objects.get(pk=filed["id"]).status, ProposalStatus.OPEN.value)
        tenancy.clear_tenant()
        self.assertFalse(Instrument.objects.filter(stable_key=INSTRUMENT_KEY, owner_tenant__isnull=True).exists())
        self.assertFalse(Obligation.objects.filter(stable_key=OBLIGATION_KEY, owner_tenant__isnull=True).exists())
