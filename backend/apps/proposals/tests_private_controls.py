"""A control of the bank's own obligation (OWN-05, REG-05, INV-07; D-89, D-99, ADR 0059;
d89-controls).

A `new_control` names one of the bank's own obligations in force and is only ever a record of
the bank's own: filed by its own agent through the runner beside the obligation, decided in
its own queue by a second person with a passkey, and applied as a REG-05 internal item of the
`control` link kind linked to that obligation's register entry, in the bank's zone, with the
audit rows beside it. What is proved here, each refusal storing nothing:

- filing: the bank's own, open, naming no target, sourced by https links; a shared
  obligation, another bank's, an unknown one, a target, a missing or unlinked source and the
  shared door are refused;
- the runner's channel files it beside the obligation, and a control the bank already links
  to that obligation is 409 `already_in_our_library`;
- approval: through `POST /private-proposals/{id}/approve`, only with a fresh passkey, never
  the proposer and never an agent; an existing control of that name is linked rather than
  duplicated, a live link is 409 `already_linked`, a retired control kind is 422; another bank
  reaches none of it.

Operations exercised (the audit-on-write guard reads these names): approvePrivateProposal.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import ValidationError

from apps.identity.models import StepUpAssertion
from apps.library import testing as library_build
from apps.library.models import Obligation
from apps.proposals import logic
from apps.proposals.models import OriginType, Proposal, ProposalStatus
from apps.proposals.tests_apply_private import PrivateRecordsCase
from apps.proposals.tests_kinds import SOURCE, obligation_body
from apps.proposals.tests_private_approval import NOTE, QueueRoutesCase
from apps.proposals.tests_tenant_agent import OwnFindingCase, finding
from apps.register.models import InternalLink, TenantObligation
from apps.shared import factories, tenancy
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent
from apps.shared.testing import sign_in
from apps.taxonomy.models import ComplianceStatus, LinkKind
from apps.tenants.models import InternalItem

DUTY = "own-outsourcing-register"
CONTROL = "Quarterly review of the outsourcing register"


def control_body(obligation: str = DUTY, **payload: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper overriding payload fields
    """A control of `obligation`, its facts sourced, as the bank's own agent files it."""
    fields = {"obligation": obligation, "name": CONTROL, "reference": "4 kap. 2 § p. 3", **payload}
    return {
        "kind": "new_control",
        "title": f"New control: {fields['name']}",
        "payload": fields,
        "fieldSources": {field: SOURCE for field in ("name", "reference") if fields.get(field)},
        "sourceLabel": "Finansinspektionen, FFFS 2026:9, 4 kap. 2 §",
        "sourceUrl": SOURCE,
    }


def own_duty(bank: Any, key: str = DUTY) -> Obligation:
    """An obligation of `bank`'s own in force, under an instrument of its own."""
    tenancy.activate(bank.id)
    act = library_build.instrument(key=f"{key}-act", official_ref=f"{key.upper()} ACT", regime="regime:securities", owner_tenant=bank)
    return library_build.obligation(act, key=key, owner_tenant=bank)


class ControlCase(PrivateRecordsCase):
    def setUp(self) -> None:
        super().setUp()
        self.duty = own_duty(self.bank)
        tenancy.clear_tenant()

    def refused_filing(self, body: dict[str, Any], code: str, *, private: bool = True) -> None:
        tenancy.activate(self.bank.id)
        before = (Proposal.objects.count(), AuditEvent.objects.count())
        with self.assertRaises(ValidationError) as caught:
            self.file(body, private=private)
        self.assertEqual(caught.exception.code, code)
        tenancy.activate(self.bank.id)
        self.assertEqual((Proposal.objects.count(), AuditEvent.objects.count()), before, "a refused filing stores nothing")

    def written(self) -> tuple[int, int, int]:
        tenancy.activate(self.bank.id)
        return (InternalItem.objects.count(), InternalLink.objects.count(), TenantObligation.objects.count())


class FilingAControl(ControlCase):
    def test_a_control_of_the_banks_own_obligation_is_its_own_open_proposal_naming_no_target(self) -> None:
        proposal = self.file(control_body())
        self.assertEqual((proposal.kind, proposal.status, proposal.origin), ("new_control", ProposalStatus.OPEN.value, OriginType.AGENT.value))
        self.assertEqual(proposal.owner_tenant_id, self.bank.id)
        self.assertEqual((proposal.target_type, proposal.target_id), ("", None))
        self.assertEqual(proposal.payload, {"obligation": DUTY, "name": CONTROL, "reference": "4 kap. 2 § p. 3"})
        self.assertEqual(self.written(), (0, 0, 0), "filing writes nothing of the register")

    def test_an_obligation_that_is_not_the_banks_own_in_force_is_unknown(self) -> None:
        shared_act = library_build.instrument(key="shared-act-for-controls", regime="regime:securities")
        library_build.obligation(shared_act, key="shared-duty-for-controls")
        theirs = own_duty(self.other_bank, key="their-own-duty")
        tenancy.clear_tenant()
        for key in ("shared-duty-for-controls", theirs.stable_key, "no-such-duty"):
            with self.subTest(obligation=key):
                self.refused_filing(control_body(obligation=key), "unknown_key")

    def test_a_control_is_never_filed_to_the_shared_library(self) -> None:
        self.refused_filing(control_body(), "validation_error", private=False)

    def test_a_control_names_no_target(self) -> None:
        body = {**control_body(), "targetType": "obligation", "targetId": self.duty.id}
        self.refused_filing(body, "validation_error")

    def test_its_facts_need_https_sources_and_the_record_a_source_url(self) -> None:
        self.refused_filing({**control_body(), "fieldSources": {}}, "source_missing")
        self.refused_filing({**control_body(), "fieldSources": {"name": SOURCE}}, "source_missing")
        self.refused_filing({**control_body(), "fieldSources": {"name": "4 kap. 2 §", "reference": SOURCE}}, "validation_error")
        self.refused_filing({**control_body(), "sourceUrl": ""}, "source_missing")

    def test_a_blank_name_is_refused(self) -> None:
        self.refused_filing(control_body(name="   "), "validation_error")


class TheRunnerFilesAControlBesideTheObligation(OwnFindingCase):
    def setUp(self) -> None:
        super().setUp()
        self.duty = own_duty(self.bank)

    def test_a_control_finding_is_filed_as_the_banks_own(self) -> None:
        obligation = self.file(finding(obligation_body(instrument=f"{DUTY}-act"), event_id="event-duty"))
        control = self.file(finding(control_body(), event_id="event-control"))
        self.assertEqual((obligation.kind, control.kind), ("new_obligation", "new_control"))
        self.assertEqual(control.owner_tenant_id, self.bank.id)
        self.assertEqual((control.agent_run_id, control.proposed_by_agent_id), (self.research_run.id, self.research_run.agent_id))
        self.assertFalse(self.visible(self.other, control), "another bank never reads it")
        self.assertFalse(self.visible(None, control), "the console never reads it")

    def test_a_control_the_bank_already_links_to_that_obligation_is_already_in_our_library(self) -> None:
        tenancy.activate(self.bank.id)
        person = factories.member_user(self.bank, roles=("compliance_officer",))
        tenancy.activate(self.bank.id)
        entry = TenantObligation.objects.create(
            tenant=self.bank, obligation=self.duty, compliance_status=ComplianceStatus.objects.get(is_default=True, active=True)
        )
        item = InternalItem.objects.create(tenant=self.bank, kind=LinkKind.objects.get(key="control"), name=CONTROL.upper())
        InternalLink.objects.create(tenant=self.bank, tenant_obligation=entry, internal_item=item, label=item.name, created_by=person)
        self.refused(finding(control_body()), "already_in_our_library")

    def test_a_control_naming_a_target_is_not_the_banks_own_record(self) -> None:
        body = {**control_body(), "targetType": "obligation", "targetId": str(self.duty.id)}
        self.refused(finding(body), "not_own_record")


class ApprovingAControl(ControlCase, QueueRoutesCase):
    def approve_route(self, proposal: Proposal, session: dict[str, Any]) -> Any:
        return self.post(f"/private-proposals/{proposal.id}/approve", {"note": NOTE}, session)

    def test_a_second_person_with_a_passkey_links_a_new_control_to_the_obligation_in_the_bank_zone(self) -> None:
        proposal = self.file(control_body())
        response = self.approve_route(proposal, self.approver_session())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "approved")

        self.in_bank()
        item = InternalItem.objects.get(name=CONTROL)
        self.assertEqual((item.tenant_id, item.kind.key, item.reference, item.active), (self.bank.id, "control", "4 kap. 2 § p. 3", True))
        link = InternalLink.objects.get(internal_item=item)
        self.assertEqual((link.tenant_obligation.obligation_id, link.label, link.created_by_id), (self.duty.id, CONTROL, self.approver.id))
        self.assertIsNone(link.removed_at)
        assertion = StepUpAssertion.objects.filter(session__user=self.approver).order_by("created_at").last()
        assert assertion is not None
        for action, subject in (
            ("register.internal_item_created", item.id),
            ("register.internal_link_added", link.id),
            ("proposal.approved", proposal.id),
        ):
            event = AuditEvent.objects.get(action=action, subject_id=subject)
            self.assertEqual((event.tenant_id, event.actor_id, event.step_up_assertion_id), (self.bank.id, self.approver.id, assertion.id), action)
            self.assertNotIn(NOTE, json.dumps([event.before, event.after]), action)
        self.assertEqual(AuditEvent.objects.get(action="register.internal_link_added").after["proposal"], str(proposal.id))

        other = sign_in(self.other_approver, tenant=self.other_bank)
        tenancy.activate(self.other_bank.id)
        self.assertFalse(InternalItem.objects.filter(pk=item.id).exists(), "another bank never reads the control")
        self.assertEqual(self.get(f"/obligations/{self.duty.id}/internal-links", other).status_code, 404)

    def test_without_a_fresh_passkey_nothing_is_written(self) -> None:
        proposal = self.file(control_body())
        self.problem(self.approve_route(proposal, self.approver_session(step_up=False)), 403, "step_up_required")
        self.assertEqual(self.written(), (0, 0, 0))
        self.assertEqual(Proposal.objects.get(pk=proposal.id).status, ProposalStatus.OPEN.value)

    def test_the_proposer_is_refused_by_four_eyes(self) -> None:
        proposal = self.file(control_body(), by=self.person(self.officer))
        self.problem(self.approve_route(proposal, sign_in(self.officer, tenant=self.bank, step_up=True)), 409, "four_eyes_violation")
        self.assertEqual(self.written(), (0, 0, 0))

    def test_an_agent_never_approves_it(self) -> None:
        proposal = self.file(control_body(), by=self.person(self.officer))
        self.in_bank()
        agent = factories.agent_actor(label="Another agent")
        with self.assertRaises(ValidationError) as caught:
            logic.approve(proposal=proposal, reviewer=logic.Reviewer(actor=agent), actor=agent, note="", step_up_assertion_id=None)
        self.assertEqual(caught.exception.code, "person_review_required")
        self.assertEqual(self.written(), (0, 0, 0))

    def test_an_existing_control_of_that_name_is_linked_not_duplicated(self) -> None:
        second_duty = own_duty(self.bank, key="own-second-duty")
        self.approve(self.file(control_body()))
        response = self.approve_route(self.file(control_body(obligation=second_duty.stable_key)), self.approver_session())
        self.assertEqual(response.status_code, 200, response.content)
        self.in_bank()
        [item] = InternalItem.objects.filter(name=CONTROL)
        self.assertEqual(
            set(InternalLink.objects.filter(internal_item=item).values_list("tenant_obligation__obligation_id", flat=True)),
            {self.duty.id, second_duty.id},
        )
        self.assertEqual(AuditEvent.objects.filter(action="register.internal_item_created").count(), 1)

    def test_a_control_already_linked_to_the_obligation_is_409_and_the_proposal_stays_open(self) -> None:
        first, second = self.file(control_body()), self.file({**control_body(), "title": "The same control again"})
        self.approve(first)
        before = self.written()
        self.problem(self.approve_route(second, self.approver_session()), 409, "already_linked")
        self.assertEqual(self.written(), before)
        self.assertEqual(Proposal.objects.get(pk=second.id).status, ProposalStatus.OPEN.value)

    def test_a_retired_control_kind_is_refused_and_nothing_is_written(self) -> None:
        proposal = self.file(control_body())
        self.in_bank()
        LinkKind.objects.filter(key="control").update(active=False)
        self.problem(self.approve_route(proposal, self.approver_session()), 422, "unknown_key")
        self.assertEqual(self.written(), (0, 0, 0))
        self.assertEqual(Proposal.objects.get(pk=proposal.id).status, ProposalStatus.OPEN.value)

    def test_an_already_decided_control_is_not_applied_twice(self) -> None:
        proposal = self.file(control_body())
        self.assertEqual(self.approve_route(proposal, self.approver_session()).status_code, 200)
        before = self.written()
        with self.assertRaises((ValidationError, ProblemError)):
            self.approve(proposal, by=self.officer)
        self.assertEqual(self.written(), before)
