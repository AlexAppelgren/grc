"""The bank's own records applied (INV-07, OWN-03, OWN-04; D-57, D-89, ADR 0050, ADR 0059;
d89-private-records).

A bank's own new instrument or obligation is approved inside the bank and applied through the
same door as a shared one: `apply` writes it with its owner taken from the proposal, never
from the payload, in the bank's own zone, with the audit rows beside it. A record of one
zone never sits under, or versions, a record of the other, and a bank's own instrument holds
no provisions. Who proposed it and who confirmed it are both named: the bank's own agent
proposes, and only a person of the bank confirms.

`PrivateRecordsCase` is the world the other d89-private-records modules share.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import Instrument, Obligation, ObligationVersion
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import apply, logic
from apps.proposals.models import Proposal, ProposalKind
from apps.proposals.tests_kinds import instrument_body, obligation_body, provision_body
from apps.search.models import SearchChunk
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent, Tenant
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

AGENT_LABEL = "Scope researcher"


def filing(body: dict[str, Any]) -> dict[str, Any]:
    """A request body as `logic.create` takes it."""
    fields = {
        "kind": body["kind"],
        "title": body["title"],
        "payload": body["payload"],
        "field_sources": body["fieldSources"],
        "source_label": body["sourceLabel"],
        "source_url": body["sourceUrl"],
    }
    if "targetId" in body:
        fields |= {"target_type": body["targetType"], "target_id": body["targetId"]}
    return fields


class PrivateRecordsCase(TestCase):
    """Bank A with an officer who files, an approver who decides and a reader who does
    neither; bank B with an approver of its own; and a platform library editor."""

    editor: User
    bank: Tenant
    officer: User
    approver: User
    reader: User
    other_bank: Tenant
    other_approver: User

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        seed_authorities()
        cls.editor = factories.platform_user(roles=("library_editor",), email="private-editor@bleqq.test")
        cls.bank = factories.tenant(slug="private-a")
        cls.officer = factories.member_user(cls.bank, roles=("compliance_officer",))
        cls.approver = factories.member_user(cls.bank, roles=("approver",))
        cls.reader = factories.member_user(cls.bank, roles=("reader",))
        cls.other_bank = factories.tenant(slug="private-b")
        cls.other_approver = factories.member_user(cls.other_bank, roles=("approver",))
        tenancy.clear_tenant()

    def setUp(self) -> None:
        tenancy.clear_tenant()

    # --- filing ----------------------------------------------------------------------------
    def agent(self) -> logic.Proposer:
        """The bank's own research agent, which files through the worker with no key."""
        return logic.Proposer(actor=factories.agent_actor(label=AGENT_LABEL))

    def person(self, user: Any) -> logic.Proposer:
        return logic.Proposer(actor=factories.user_actor(user_id=user.id), user=user)

    def file(self, body: dict[str, Any], *, by: logic.Proposer | None = None, tenant: Any = None, private: bool = True) -> Proposal:
        """`body` filed inside `tenant` (bank A by default) by `by` (its agent by default)."""
        tenancy.activate((tenant or self.bank).id)
        proposal, _ = logic.create(proposer=by or self.agent(), private=private, **filing(body))
        return proposal

    def own_instrument(self, key: str = "own-act-1") -> Proposal:
        return self.file(instrument_body(key=key, officialRef=key.upper(), shortName=key.upper()))

    def own_obligation(self, instrument: str, key: str = "own-duty-1") -> Proposal:
        return self.file(obligation_body(instrument=instrument, key=key))

    # --- deciding --------------------------------------------------------------------------
    def approve(self, proposal: Proposal, by: Any = None) -> Proposal:
        """`proposal` approved by `by` (bank A's approver by default) with a passkey, as the
        bank's own approval route does it."""
        by = by or self.approver
        tenancy.activate(proposal.owner_tenant_id or self.bank.id)
        actor = factories.user_actor(user_id=by.id)
        return logic.approve(
            proposal=proposal, reviewer=logic.Reviewer(actor=actor, user=by), actor=actor, note="", step_up_assertion_id=None
        )

    def approved_instrument(self, key: str = "own-act-1") -> Instrument:
        self.approve(self.own_instrument(key))
        return Instrument.objects.get(stable_key=key)

    def refused(self, code: str) -> Any:
        return RefusedWith(self, code)


class RefusedWith:
    """`with case.refused("code"):` passes when the block raises a ValidationError of that code."""

    def __init__(self, case: TestCase, code: str) -> None:
        self.case, self.code = case, code

    def __enter__(self) -> None:
        return None

    def __exit__(self, kind: Any, error: Any, traceback: Any) -> bool:
        self.case.assertIsInstance(error, ValidationError, f"expected a refusal with {self.code}")
        self.case.assertEqual(error.code, self.code, error)
        return True


class OwnedKindsApplyIntoTheBank(PrivateRecordsCase):
    def test_an_instrument_takes_its_owner_from_the_proposal_and_is_audited_in_the_bank(self) -> None:
        proposal = self.own_instrument()
        self.approve(proposal)
        instrument = Instrument.objects.get(stable_key="own-act-1")
        self.assertEqual(instrument.owner_tenant_id, self.bank.id)
        self.assertEqual((instrument.created_origin, instrument.verified_origin, instrument.verified_by_agent_id), ("agent", "user", None))
        created = AuditEvent.objects.get(action="instrument.created", subject_id=instrument.id)
        self.assertEqual(created.tenant_id, self.bank.id)
        self.assertEqual(AuditEvent.objects.get(action="proposal.approved", subject_id=proposal.id).tenant_id, self.bank.id)

    def test_an_obligation_under_the_bank_s_own_instrument_is_the_bank_s_and_is_never_indexed(self) -> None:
        self.approved_instrument()
        proposal = self.own_obligation("own-act-1")
        self.approve(proposal)
        obligation = Obligation.objects.get(stable_key="own-duty-1")
        self.assertEqual(obligation.owner_tenant_id, self.bank.id)
        self.assertEqual((obligation.created_origin, obligation.verified_origin), ("agent", "user"))
        version = ObligationVersion.objects.get(obligation=obligation)
        self.assertEqual((version.approved_by_id, version.applied_by_proposal_id, version.verified_origin), (self.approver.id, proposal.id, "user"))
        self.assertFalse(SearchChunk.objects.filter(source_id__in=[obligation.id, version.id]).exists(), "a bank's own record is never indexed")
        self.assertEqual(AuditEvent.objects.get(action="obligation.created", subject_id=obligation.id).tenant_id, self.bank.id)

    def test_the_other_bank_and_the_console_never_see_what_was_applied(self) -> None:
        instrument = self.approved_instrument()
        tenancy.activate(self.other_bank.id)
        self.assertFalse(Instrument.objects.filter(pk=instrument.pk).exists())
        tenancy.clear_tenant()
        self.assertFalse(Instrument.objects.filter(pk=instrument.pk).exists())
        self.assertFalse(AuditEvent.objects.filter(action="instrument.created", subject_id=instrument.id).exists())

    def test_an_agent_never_confirms_a_bank_s_own_record(self) -> None:
        proposal = self.own_instrument()
        reviewer = logic.Reviewer(actor=factories.agent_actor(), api_key_id=None, agent_id=None)
        tenancy.activate(self.bank.id)
        with self.refused("person_review_required"):
            logic.approve(proposal=proposal, reviewer=reviewer, actor=reviewer.actor, note="", step_up_assertion_id=None)
        self.assertFalse(Instrument.objects.filter(stable_key="own-act-1").exists())

    def test_apply_refuses_an_owned_row_of_any_other_kind(self) -> None:
        tenancy.activate(self.bank.id)
        forged = Proposal.objects.create(
            kind=ProposalKind.VOCABULARY_CREATE.value,
            title="Add the flag Client money",
            payload={"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            origin="user",
            proposed_in_tenant=True,
            owner_tenant=self.bank,
        )
        actor = factories.user_actor(user_id=self.approver.id)
        with self.refused("validation_error"):
            apply.apply(forged, actor=actor, reviewer=self.approver, step_up=None)


class NothingCrossesTheZones(PrivateRecordsCase):
    def test_a_bank_s_own_obligation_never_sits_under_a_shared_instrument(self) -> None:
        library_build.instrument(key="shared-act-1", regime="regime:securities")
        with self.refused("validation_error"):
            self.own_obligation("shared-act-1")
        self.assertFalse(Proposal.objects.exists())

    def test_a_shared_obligation_never_sits_under_the_bank_s_own_instrument(self) -> None:
        self.approved_instrument()
        with self.refused("validation_error"):
            self.file(obligation_body(instrument="own-act-1", key="shared-duty-1"), by=self.person(self.officer), private=False)

    def test_the_rule_is_checked_again_at_approval(self) -> None:
        """A correction that moves a bank's own obligation under a shared instrument is
        refused when it is approved, and nothing is written."""
        self.approved_instrument()
        library_build.instrument(key="shared-act-2", regime="regime:securities")
        proposal = self.own_obligation("own-act-1")
        tenancy.activate(self.bank.id)
        actor = factories.user_actor(user_id=self.approver.id)
        with self.refused("validation_error"):
            logic.approve(
                proposal=proposal,
                reviewer=logic.Reviewer(actor=actor, user=self.approver),
                actor=actor,
                note="",
                payload_overrides={"instrument": "shared-act-2"},
                step_up_assertion_id=None,
            )

    def test_a_version_of_the_bank_s_own_obligation_is_never_a_library_proposal(self) -> None:
        self.approved_instrument()
        self.approve(self.own_obligation("own-act-1"))
        own = Obligation.objects.get(stable_key="own-duty-1")
        with self.refused("unknown_key"):
            self.file(
                {
                    "kind": "new_obligation_version",
                    "title": "Version 2 of our own duty",
                    "payload": {"summaries": {"en": "The bank reports yearly."}, "originalLanguage": "en", "effectiveFrom": "2027-01-01"},
                    "fieldSources": {"summaries.en": "https://www.fi.se/", "effectiveFrom": "https://www.fi.se/"},
                    "sourceLabel": "",
                    "sourceUrl": "",
                    "targetType": "obligation",
                    "targetId": own.id,
                },
                by=self.person(self.officer),
                private=False,
            )


class ABanksOwnInstrumentHoldsNoProvisions(PrivateRecordsCase):
    def test_a_provision_under_it_is_refused_by_name(self) -> None:
        self.approved_instrument()
        with self.refused("private_provisions_not_supported"):
            self.file(provision_body(instrument="own-act-1"), by=self.person(self.officer), private=False)

    def test_a_provision_filed_as_the_bank_s_own_is_refused_by_name(self) -> None:
        library_build.instrument(key="shared-act-3", regime="regime:securities")
        with self.refused("private_provisions_not_supported"):
            self.file(provision_body(instrument="shared-act-3"))
        self.assertFalse(Proposal.objects.exists())
