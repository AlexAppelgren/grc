"""Proposal apply (PRO-02, VOC-07; playbook 8.1: tests required with every change to proposal
apply, vocabulary retire and merge).

The scenarios in tests_scenarios.py prove the door: a proposal is the only way into the
library and a second person opens it. These prove what walks through it: every chunk 2 kind
applied against the library as it is at approval time, and refused when the library moved
underneath it (a key someone else created meanwhile, a system row, a row already retired),
with the proposal left open and nothing written.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, IntegrityError, transaction
from django.test import Client, TransactionTestCase

from apps.agents import testing as agents_testing

from apps.library import testing as library_build
from apps.library.models import (
    Instrument,
    InstrumentRelation,
    Jurisdiction,
    Obligation,
    ObligationRelation,
    ObligationTag,
    ObligationTerm,
    ObligationVersion,
    Provision,
    SubjectType,
    Verification,
    VerificationOutcome,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import apply, logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.proposals.tests_decide import _actor, _agent_actor, _approval, _race, _seed
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.shared.schemas import AgentDecision
from apps.shared.tenancy import LibraryWriteRefused, library_write
from apps.shared.testing import LANDED, ScenarioTestCase, sign_in
from apps.taxonomy import repoint
from apps.taxonomy.models import (
    DutyType,
    Flag,
    InstrumentLevel,
    LibraryTag,
    ProvisionKind,
    RelationType,
    TaxonomyTerm,
    TermDimension,
    Urgency,
)
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from apps.watch import testing as watch_build
from apps.watch.models import ChangeTerm

V1 = "/api/v1"
# The obligation was last verified here, months before any test runs: a stamp is proven by
# the date moving off this anchor, never by comparing with today (plan rule 8).
WAS_VERIFIED_AT = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


class ProposalApply(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")

    # --- helpers ------------------------------------------------------------------------------
    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _patch(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.patch(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _approve(self, proposal: dict[str, Any]) -> Any:
        return self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.reviewer, step_up=True))

    def _proposed(self, response: Any) -> dict[str, Any]:
        self.assertEqual(response.status_code, 202, response.content)
        proposal: dict[str, Any] = response.json()["proposal"]
        return proposal

    def _new_flag(self, key: str = "client_money", label: str = "Client money") -> Flag:
        proposal = self._proposed(self._post("/vocab/flag", {"key": key, "labels": {"en": label}}, sign_in(self.editor)))
        self.assertEqual(self._approve(proposal).status_code, 200)
        return Flag.objects.get(key=key)

    # --- vocabulary kinds ---------------------------------------------------------------------
    def test_relabel_applies_labels_note_order_and_extra_columns(self) -> None:
        editor = sign_in(self.editor)
        proposal = self._proposed(
            self._patch(
                "/vocab/urgency/act_now",
                {"labels": {"sv": "Agera omedelbart"}, "usageNote": "Days, not weeks.", "sortOrder": 9, "extra": {"slaDays": 7, "ignored": 1}},
                editor,
                HTTP_IF_MATCH="1",
            )
        )
        self.assertEqual(proposal["kind"], "vocabulary_relabel")
        self.assertEqual(proposal["payload"]["extra"], {"slaDays": 7})
        self.assertEqual(self._approve(proposal).status_code, 200)
        row = Urgency.objects.get(key="act_now")
        self.assertEqual((row.usage_note, row.sort_order, row.sla_days, row.version), ("Days, not weeks.", 9, 7, 2))
        self.assertEqual(row.labels.get(language="sv").text, "Agera omedelbart")
        self.assertEqual(row.labels.get(language="en").text, "Act now")
        # The version moved, so a proposal made from the old read is refused before it queues.
        stale = self._patch("/vocab/urgency/act_now", {"labels": {"en": "x"}}, editor, HTTP_IF_MATCH="1")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "stale_write")

    def test_retire_restore_and_merge_of_a_library_value_are_proposals(self) -> None:
        editor = sign_in(self.editor)
        money = self._new_flag()
        funds = self._new_flag("client_funds", "Client funds held")
        retire = self._proposed(self._post("/vocab/flag/client_money/retire", {}, editor))
        self.assertEqual(retire["kind"], "vocabulary_retire")
        self.assertTrue(Flag.objects.get(pk=money.pk).active, "nothing changes until approval")
        self.assertEqual(self._approve(retire).status_code, 200)
        self.assertFalse(Flag.objects.get(pk=money.pk).active)
        self.assertEqual(self._post("/vocab/flag/client_money/retire", {}, editor).json()["code"], "invalid_transition")
        restore = self._proposed(self._post("/vocab/flag/client_money/restore", {}, editor))
        self.assertEqual(restore["kind"], "vocabulary_restore")
        self.assertEqual(self._approve(restore).status_code, 200)
        self.assertTrue(Flag.objects.get(pk=money.pk).active)
        # Merge: the dry run answers what would move and writes nothing; the commit is a proposal.
        before = AuditEvent.objects.count()
        preview = Client().post(f"{V1}/vocab/flag/client_funds/merge?dryRun=true", data={"into": "client_money"}, content_type="application/json", **editor)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json(), {"from": "client_funds", "into": "client_money", "usageCount": 0, "repointed": 0, "dryRun": True})
        self.assertEqual(AuditEvent.objects.count(), before)
        self.assertEqual(self._post("/vocab/flag/client_funds/merge", {"into": "client_funds"}, editor).json()["code"], "validation_error")
        self.assertEqual(self._post("/vocab/flag/ai/merge", {"into": "client_money"}, editor).json()["code"], "system_row")
        merge = self._proposed(self._post("/vocab/flag/client_funds/merge", {"into": "client_money"}, editor))
        self.assertEqual(merge["payload"], {"list": "flag", "key": "client_funds", "into": "client_money"})
        self.assertEqual(self._approve(merge).status_code, 200)
        self.assertFalse(Flag.objects.get(pk=funds.pk).active)
        self.assertEqual(AuditEvent.objects.get(action="vocabulary.merged", subject_id=funds.id).after["into"], "client_money")

    def test_approval_rechecks_the_library_as_it_is_now(self) -> None:
        editor = sign_in(self.editor)
        first = self._proposed(self._post("/vocab/flag", {"key": "custody_risk", "labels": {"en": "Custody risk"}}, editor))
        second = self._proposed(self._post("/vocab/flag", {"key": "custody_risk", "labels": {"en": "Custody risk"}}, sign_in(self.reviewer)))
        self.assertEqual(self._approve(first).status_code, 200)
        # The second proposal named a key that now exists: refused, left open, nothing written.
        clash = self._post(f"/proposals/{second['id']}/approve", {}, sign_in(self.editor, step_up=True))
        self.assertEqual(clash.status_code, 409, clash.content)
        self.assertEqual(clash.json()["code"], "duplicate_key")
        self.assertEqual(Proposal.objects.get(pk=second["id"]).status, ProposalStatus.OPEN.value)
        self.assertEqual(Flag.objects.filter(key="custody_risk").count(), 1)
        # A system row is never retired, even by a proposal that reached the queue directly.
        direct = self._post("/proposals", {"kind": "vocabulary_retire", "title": "Retire ai", "payload": {"list": "flag", "key": "ai"}}, editor)
        self.assertEqual(direct.status_code, 201, direct.content)
        refused = self._approve(direct.json())
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["code"], "system_row")
        self.assertTrue(Flag.objects.get(key="ai").active)
        # A row kind the list does not know is refused when the proposal is made, with the valid ones.
        bad_kind = self._post("/proposals", {"kind": "vocabulary_create", "title": "Odd", "payload": {"list": "change_type", "key": "odd", "labels": {"en": "Odd"}, "kind": "sideways"}}, editor)
        self.assertEqual(bad_kind.status_code, 422)
        self.assertEqual(bad_kind.json()["code"], "unknown_key")
        self.assertIn("in_force", bad_kind.json()["detail"])

    def test_proposals_only_name_library_lists_and_real_dimensions(self) -> None:
        editor = sign_in(self.editor)
        tenant_list = self._post("/proposals", {"kind": "vocabulary_create", "title": "Tag", "payload": {"list": "tenant_tag", "key": "x", "labels": {"en": "X"}}}, editor)
        self.assertEqual(tenant_list.status_code, 422)
        self.assertEqual(tenant_list.json()["code"], "unknown_key")
        self.assertIn("flag", tenant_list.json()["detail"])
        # A jurisdiction's keys are fixed (D-94): relabelled, retired and restored, never added.
        seeded = self._post("/proposals", {"kind": "vocabulary_create", "title": "Land", "payload": {"list": "jurisdiction", "key": "is", "labels": {"en": "Iceland"}}}, editor)
        self.assertEqual(seeded.json()["code"], "validation_error")
        dimension = self._post("/proposals", {"kind": "term_create", "title": "T", "payload": {"dimension": "planet", "key": "x", "labels": {"en": "X"}}}, editor)
        self.assertEqual(dimension.json()["code"], "unknown_key")
        untitled = self._post("/proposals", {"kind": "vocabulary_retire", "title": "  ", "payload": {"list": "flag", "key": "ai"}}, editor)
        self.assertEqual(untitled.json()["code"], "validation_error")
        # And the vocabulary route refuses to queue one.
        self.assertEqual(self._post("/vocab/jurisdiction", {"labels": {"en": "Iceland"}}, editor).json()["code"], "validation_error")

    # --- a proposal made directly is checked like one made through the vocabulary routes ---------
    def _direct(self, kind: str, payload: dict[str, Any], headers: dict[str, Any] | None = None) -> Any:
        body = {"kind": kind, "title": "Direct", "payload": payload}
        return self._post("/proposals", body, headers or sign_in(self.editor))

    def _refused(self, response: Any, code: str) -> None:
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], code, response.content)

    def test_extra_values_are_typed_and_references_resolved_when_the_proposal_is_made(self) -> None:
        before = Proposal.objects.count()
        urgency = {"list": "urgency", "key": "within_a_day", "labels": {"en": "Within a day"}, "kind": "negative"}
        self._refused(self._direct("vocabulary_create", {**urgency, "extra": {"ordinal": "abc"}}), "validation_error")
        self._refused(self._direct("vocabulary_relabel", {"list": "urgency", "key": "act_now", "extra": {"slaDays": "soon"}}), "validation_error")
        provision = {"list": "provision_kind", "key": "stycke", "labels": {"sv": "Stycke"}, "kind": "unit"}
        self._refused(self._direct("vocabulary_create", {**provision, "extra": {"jurisdiction": "atlantis"}}), "unknown_key")
        # The vocabulary routes build the same payload, so they refuse the same values.
        self._refused(self._patch("/vocab/urgency/act_now", {"extra": {"slaDays": "soon"}}, sign_in(self.editor), HTTP_IF_MATCH="1"), "validation_error")
        self.assertEqual(Proposal.objects.count(), before, "nothing reached the queue")
        # A clean value is stored as its column's type, and a reference becomes the row it names.
        typed = self._direct("vocabulary_create", {**urgency, "extra": {"ordinal": "4", "sla_days": "1"}})
        self.assertEqual(typed.status_code, 201, typed.content)
        self.assertEqual(typed.json()["payload"]["extra"], {"ordinal": 4, "slaDays": 1}, "the queue shows what approval writes")
        self.assertEqual(self._approve(typed.json()).status_code, 200)
        self.assertEqual((Urgency.objects.get(key="within_a_day").ordinal, Urgency.objects.get(key="within_a_day").sla_days), (4, 1))
        placed = self._direct("vocabulary_create", {**provision, "extra": {"jurisdiction": "se"}})
        self.assertEqual(placed.status_code, 201, placed.content)
        self.assertEqual(placed.json()["payload"]["extra"], {"jurisdiction": "se"})
        self.assertEqual(self._approve(placed.json()).status_code, 200)
        self.assertEqual(ProvisionKind.objects.filter(key="stycke").values_list("jurisdiction__key", flat=True).get(), "se")

    def test_extra_carries_only_the_lists_own_columns(self) -> None:
        urgency = {"list": "urgency", "key": "within_a_day", "labels": {"en": "Within a day"}, "kind": "negative"}
        for extra in ({"pillTone": "negative", "background": "#f00"}, {"ordinal": 5, "tone": "brand"}):
            self._refused(self._direct("vocabulary_create", {**urgency, "extra": extra}), "validation_error")
            self._refused(self._direct("vocabulary_relabel", {"list": "urgency", "key": "act_now", "extra": extra}), "validation_error")
        self._refused(self._direct("vocabulary_create", {"list": "flag", "key": "x", "labels": {"en": "X"}, "extra": {"rank": 1}}), "validation_error")
        self.assertFalse(Proposal.objects.exists())

    def test_keys_and_labels_are_checked_when_the_proposal_is_made(self) -> None:
        flag = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}
        self._refused(self._direct("vocabulary_create", {**flag, "key": "Bad Key!"}), "validation_error")
        self._refused(self._direct("vocabulary_create", {**flag, "labels": {"zz": "Klientpengar"}}), "unknown_key")
        self._refused(self._direct("vocabulary_create", {**flag, "labels": {"en": "   "}}), "validation_error")
        self._refused(self._direct("vocabulary_relabel", {"list": "flag", "key": "ai", "labels": {"zz": "x"}}), "unknown_key")
        self._refused(self._direct("vocabulary_relabel", {"list": "flag", "key": "AI!", "labels": {"en": "x"}}), "validation_error")
        term = {"dimension": "service_type", "key": "sub_custody", "labels": {"en": "Sub-custody"}}
        self._refused(self._direct("term_create", {**term, "key": "Sub Custody"}), "validation_error")
        self._refused(self._direct("term_create", {**term, "labels": {"zz": "x"}}), "unknown_key")
        self._refused(self._direct("term_update", {"dimension": "service_type", "key": "custody", "labels": {"zz": "x"}}), "unknown_key")
        self._refused(self._direct("term_update", {"dimension": "service_type", "key": "Custody!"}), "validation_error")
        self.assertFalse(Proposal.objects.exists())
        # A good label is stored trimmed, as the vocabulary routes store it.
        made = self._direct("vocabulary_create", {**flag, "labels": {"en": "  Client money  ", "sv": ""}})
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual(made.json()["payload"]["labels"], {"en": "Client money"})

    def test_a_stored_payload_that_no_longer_parses_is_refused_at_approval_and_stays_open(self) -> None:
        stored = Proposal.objects.create(
            kind="vocabulary_create", title="Written before the payload schema closed", payload={"list": "flag", "key": "x"}, origin="user"
        )
        refused = self._approve({"id": str(stored.id)})
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "validation_error")
        self.assertIn("labels", refused.json()["detail"])
        self.assertEqual(Proposal.objects.get(pk=stored.pk).status, ProposalStatus.OPEN.value)

    def test_field_sources_are_links_by_field_and_unknown_top_level_fields_are_refused(self) -> None:
        flag = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}
        body = {"kind": "vocabulary_create", "title": "Add Client money", "payload": flag}
        editor = sign_in(self.editor)
        self._refused(self._post("/proposals", {**body, "fieldSources": {"labels": {"nested": True}}}, editor), "validation_error")
        self._refused(self._post("/proposals", {**body, "tone": "positive"}, editor), "validation_error")
        self.assertFalse(Proposal.objects.exists())
        made = self._post("/proposals", {**body, "fieldSources": {"labels": "https://www.fi.se/"}}, editor)
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual(made.json()["fieldSources"], {"labels": "https://www.fi.se/"})

    # --- term kinds -----------------------------------------------------------------------------
    def test_terms_are_created_under_a_parent_and_updated_through_proposals(self) -> None:
        editor = sign_in(self.editor)
        parent = TaxonomyTerm.objects.get(dimension__key="service_type", key="custody")
        created = self._proposed(self._post("/taxonomy/terms", {"dimension": "service_type", "key": "sub_custody", "labels": {"sv": "Underförvaring"}, "parent": "custody"}, editor))
        self.assertEqual(self._approve(created).status_code, 200)
        term = TaxonomyTerm.objects.get(dimension__key="service_type", key="sub_custody")
        self.assertEqual(term.parent_id, parent.id)
        self.assertTrue(term.labels.get(language="sv").is_original)
        self.assertEqual(self._post("/taxonomy/terms", {"dimension": "service_type", "key": "SUB_CUSTODY", "labels": {"en": "Again"}}, editor).json()["code"], "duplicate_key")
        self.assertEqual(self._post("/taxonomy/terms", {"dimension": "service_type", "labels": {"en": "Orphan"}, "parent": "nowhere"}, editor).json()["code"], "unknown_key")
        update = self._proposed(self._patch(f"/taxonomy/terms/{term.id}", {"usageNote": "Held by a sub-custodian.", "sortOrder": 40}, editor))
        self.assertEqual(self._approve(update).status_code, 200)
        term.refresh_from_db()
        self.assertEqual((term.usage_note, term.sort_order, term.version), ("Held by a sub-custodian.", 40, 2))
        self.assertEqual(self._patch("/taxonomy/terms/00000000-0000-4000-8000-000000000000", {"sortOrder": 1}, editor).status_code, 404)
        self.assertEqual(self._patch("/taxonomy/terms/not-a-uuid", {"sortOrder": 1}, editor).status_code, 404)

    # --- deciding -------------------------------------------------------------------------------
    def test_an_agent_proposal_is_decided_by_any_reviewer_and_nobody_rejects_their_own(self) -> None:
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        agent = self._post("/proposals", {"kind": "vocabulary_create", "title": "Add Greenwashing", "payload": {"list": "flag", "key": "greenwashing", "labels": {"en": "Greenwashing"}}, "model": "mock-1"}, {"HTTP_X_API_KEY": key.plain_key})
        self.assertEqual(agent.status_code, 201, agent.content)
        # A bank's own key is bound to no agent and names no run; a run it named would have to be its own (AGT-01).
        self.assertEqual((agent.json()["agentRunId"], agent.json()["model"], agent.json()["origin"]), (None, "mock-1", "agent"))
        self.assertEqual(self._post(f"/proposals/{agent.json()['id']}/approve", {}, sign_in(self.editor, step_up=True)).status_code, 200)
        own = self._proposed(self._post("/vocab/flag", {"labels": {"en": "Sanctions"}}, sign_in(self.editor)))
        refused = self._post(f"/proposals/{own['id']}/reject", {"rejectionCode": "duplicate", "note": "Mine."}, sign_in(self.editor))
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["code"], "four_eyes_violation")
        self.assertEqual(self.client.get(f"{V1}/proposals/00000000-0000-4000-8000-000000000000", **sign_in(self.editor)).status_code, 404)


class ApprovalCorrectionsAndTheAssertion(ScenarioTestCase):
    """PRO-02, AC-PRO2, AC-ID3: what a reviewer may change on the way through, and what
    every row the approval writes has to carry.

    The scenarios (PRO-S3, PRO-S4) prove an obligation version applied and corrected. These
    prove the two rules that hold for every kind: corrections belong to a sourced fact
    alone, and the passkey assertion the reviewer just made is on every audit row the
    approval's transaction leaves, the library change included, so the log of a library
    change says which passkey opened the door.
    """

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")
        with library_write("test fixture"):
            instrument = Instrument.objects.create(
                stable_key="fffs-2017-2",
                short_name="FFFS 2017:2",
                official_ref="FFFS 2017:2",
                source_url="https://www.fi.se/",
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                regime=TaxonomyTerm.objects.get(dimension__key="regime", key="securities"),
                created_origin="user",
            )
            self.obligation = Obligation.objects.create(
                stable_key="obl-advice-suitability",
                instrument=instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.get(key="conduct"),
                created_origin="user",
                source_url="https://www.fi.se/",
                source_label="FFFS 2017:2, 9 kap. 6 §",
            )

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _flag_proposal(self) -> dict[str, Any]:
        created = self._post(
            "/proposals",
            {"kind": "vocabulary_create", "title": "Add the flag Client money", "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}},
            sign_in(self.editor),
        )
        self.assertEqual(created.status_code, 201, created.content)
        row: dict[str, Any] = created.json()
        return row

    def _version_proposal(self) -> dict[str, Any]:
        created = self._post(
            "/proposals",
            {
                "kind": "new_obligation_version",
                "title": "Version 2 of the advice obligation, in force 1 October 2026",
                "targetType": "obligation",
                "targetId": str(self.obligation.id),
                "payload": {
                    "summaries": {"sv": "Institutet bedömer kunden innan rådgivning."},
                    "originalLanguage": "sv",
                    "effectiveFrom": "2026-10-01",
                    "effectiveFromPrecision": "day",
                },
                "fieldSources": {"summaries.sv": "https://www.fi.se/", "effectiveFrom": "https://www.fi.se/"},
            },
            sign_in(self.editor),
        )
        self.assertEqual(created.status_code, 201, created.content)
        row: dict[str, Any] = created.json()
        return row

    def test_a_correction_belongs_to_a_sourced_fact_and_not_to_a_label(self) -> None:
        # A vocabulary row's label is wording a person writes, not a fact from an
        # authority, so there is nothing to correct it against: a reviewer who disagrees
        # rejects it with a reason instead.
        proposal = self._flag_proposal()

        refused = self._post(
            f"/proposals/{proposal['id']}/approve",
            {"payloadOverrides": {"labels": {"en": "Client funds"}}},
            sign_in(self.reviewer, step_up=True),
        )

        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "validation_error")
        self.assertFalse(Flag.objects.filter(key="client_money").exists())
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)

    def test_every_audit_row_an_approval_writes_carries_the_reviewers_assertion(self) -> None:
        for name, proposal in (("a vocabulary row", self._flag_proposal()), ("an obligation version", self._version_proposal())):
            with self.subTest(kind=name):
                reviewer = sign_in(self.reviewer, step_up=True)  # signing in is its own audited act
                written_before = set(AuditEvent.objects.values_list("id", flat=True))

                approved = self._post(f"/proposals/{proposal['id']}/approve", {}, reviewer)

                self.assertEqual(approved.status_code, 200, approved.content)
                rows = list(AuditEvent.objects.exclude(id__in=written_before))
                # The decision and the library change it made, and nothing without an assertion.
                self.assertGreaterEqual(len(rows), 2)
                self.assertEqual([row.action for row in rows if row.step_up_assertion_id is None], [])


    def test_a_decisions_note_stays_on_the_proposal_and_never_in_its_audit_value(self) -> None:
        """From R2 a proposal can be a bank's own (D-89), and a reviewer's note is their own
        words about it, so it is tenant content an audit value may not carry (CHUNK10 rule
        13): the note is kept on the proposal row, which the proposer reads, and the audit
        row says only what was decided."""
        approved_note = "Checked against the board decision; the wording is the authority's."
        rejected_note = "The flag list already has Client assets for this."
        approving = self._version_proposal()
        rejecting = self._flag_proposal()

        approved = self._post(f"/proposals/{approving['id']}/approve", {"note": approved_note}, sign_in(self.reviewer, step_up=True))
        rejected = self._post(
            f"/proposals/{rejecting['id']}/reject", {"rejectionCode": "duplicate", "note": rejected_note}, sign_in(self.reviewer, step_up=True)
        )

        self.assertEqual((approved.status_code, rejected.status_code), (200, 200), (approved.content, rejected.content))
        for proposal, action, note in ((approving, "proposal.approved", approved_note), (rejecting, "proposal.rejected", rejected_note)):
            with self.subTest(action=action):
                self.assertEqual(Proposal.objects.get(pk=proposal["id"]).review_note, note)
                audit = AuditEvent.objects.get(action=action, subject_id=proposal["id"])
                self.assertNotIn("note", audit.after)
                self.assertNotIn(note, str(audit.before) + str(audit.after) + audit.summary)
        self.assertEqual(AuditEvent.objects.get(action="proposal.rejected", subject_id=rejecting["id"]).after["rejectionCode"], "duplicate")

    def test_a_correction_that_changes_a_sourced_value_names_a_fresh_source(self) -> None:
        """A reviewer who changes what a sourced field says read the new value somewhere, and
        the proposer's source vouches only for the value it was given for (H35, security-review
        c4 L5): the changed field names its fresh source in `fieldSources`, checked as a
        proposal's are, and the proposal then keeps that source for the field."""
        proposal = self._version_proposal()
        reviewer = sign_in(self.reviewer, step_up=True)
        reworded = {"summaries": {"sv": "Institutet bedömer kunden noggrant innan rådgivning."}}
        fresh = "https://www.fi.se/sv/publicerat/nyheter/2026/beslut/"

        for body, code in (
            ({"payloadOverrides": reworded}, "source_missing"),
            ({"payloadOverrides": reworded, "fieldSources": {"summaries.sv": "see above"}}, "validation_error"),
            # A source for a value the correction leaves as proposed is a source for nothing.
            ({"payloadOverrides": reworded, "fieldSources": {"summaries.sv": fresh, "effectiveFrom": fresh}}, "validation_error"),
            ({"fieldSources": {"summaries.sv": fresh}}, "validation_error"),
        ):
            with self.subTest(body=body):
                refused = self._post(f"/proposals/{proposal['id']}/approve", body, reviewer)
                self.assertEqual(refused.status_code, 422, refused.content)
                self.assertEqual(refused.json()["code"], code)
                row = Proposal.objects.get(pk=proposal["id"])
                self.assertEqual((row.status, row.corrected_payload), (ProposalStatus.OPEN.value, None))

        # Correcting a value to what was proposed changes nothing, so it needs no source.
        unchanged = {"summaries": {"sv": "Institutet bedömer kunden innan rådgivning."}, "effectiveFrom": "2026-10-01"}
        as_proposed = self._post(f"/proposals/{proposal['id']}/approve", {"payloadOverrides": unchanged}, reviewer)
        self.assertEqual(as_proposed.status_code, 200, as_proposed.content)
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).field_sources, {"summaries.sv": "https://www.fi.se/", "effectiveFrom": "https://www.fi.se/"})
        self.assertNotIn("fieldSources", AuditEvent.objects.get(action="proposal.approved", subject_id=proposal["id"]).after)

        second = self._version_proposal()
        approved = self._post(f"/proposals/{second['id']}/approve", {"payloadOverrides": reworded, "fieldSources": {"summaries.sv": f" {fresh} "}}, reviewer)
        self.assertEqual(approved.status_code, 200, approved.content)
        row = Proposal.objects.get(pk=second["id"])
        self.assertEqual((row.corrected_payload or {})["summaries"], reworded["summaries"])
        self.assertEqual(row.field_sources, {"summaries.sv": fresh, "effectiveFrom": "https://www.fi.se/"})
        # The proposer's source for the value it no longer vouches for stays in the log.
        audit = AuditEvent.objects.get(action="proposal.approved", subject_id=second["id"])
        self.assertEqual((audit.before["fieldSources"], audit.after["fieldSources"]), ({"summaries.sv": "https://www.fi.se/"}, {"summaries.sv": fresh}))


class MirroredTermsAtApproval(ScenarioTestCase):
    """FP-S12, FP-S9: the terms that mirror the jurisdiction rows are the reference seed's,
    so no approval may add one, rename one or scope an obligation with one.

    Creation refuses all three today, but a proposal filed before that rule existed may
    still wait in the queue. Each proposal below is stored the way such a proposal was
    stored, without today's creation checks, and approving it answers 422
    `jurisdiction_term_mirrored`, leaves it open and writes nothing: no term, no label, no
    version, no scope link, no audit row, not even the decision.
    """

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")
        instrument = library_build.instrument(key="fffs-2017-2", regime="regime:securities")
        self.obligation = library_build.obligation(instrument, key="fffs-2017-2-9-6", terms=("service_type:advice",))

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _filed_before_the_rule(self, kind: str, payload: dict[str, Any], *, versions: bool = False) -> Proposal:
        return Proposal.objects.create(
            kind=kind,
            title="Filed before the mirror rule",
            payload=payload,
            origin="user",
            proposed_by_user=self.editor,
            target_type="obligation" if versions else "",
            target_id=self.obligation.id if versions else None,
        )

    def _refused_at_approval(self, proposal: Proposal) -> None:
        reviewer = sign_in(self.reviewer, step_up=True)  # signing in is its own audited act
        written = AuditEvent.objects.count()
        refused = self._post(f"/proposals/{proposal.id}/approve", {}, reviewer)
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "jurisdiction_term_mirrored")
        self.assertEqual(Proposal.objects.get(pk=proposal.pk).status, ProposalStatus.OPEN.value)
        self.assertEqual(AuditEvent.objects.count(), written, "nothing was written, not even the decision")

    def _scope(self) -> list[str]:
        links = ObligationTerm.objects.filter(obligation=self.obligation).select_related("term__dimension")
        return sorted(f"{link.term.dimension.key}:{link.term.key}" for link in links)

    def test_a_new_term_in_a_mirrored_dimension_is_refused_at_approval(self) -> None:
        proposal = self._filed_before_the_rule("term_create", {"dimension": "jurisdiction", "key": "is", "labels": {"en": "Iceland"}})
        self._refused_at_approval(proposal)
        self.assertFalse(TaxonomyTerm.objects.filter(dimension__key="jurisdiction", key="is").exists())

    def test_renaming_a_mirrored_term_is_refused_at_approval(self) -> None:
        sweden = TaxonomyTerm.objects.get(dimension__key="jurisdiction", key="se")
        proposal = self._filed_before_the_rule(
            "term_update", {"dimension": "jurisdiction", "key": "se", "labels": {"en": "Kingdom of Sweden"}, "sortOrder": 99}
        )
        self._refused_at_approval(proposal)
        kept = TaxonomyTerm.objects.get(pk=sweden.pk)
        self.assertEqual((kept.version, kept.sort_order), (sweden.version, sweden.sort_order))
        self.assertEqual(kept.labels.get(language="en").text, "Sweden")

    def test_an_obligation_version_scoped_to_a_market_is_refused_at_approval(self) -> None:
        proposal = self._filed_before_the_rule(
            "new_obligation_version",
            {
                "summaries": {"en": "The firm assesses suitability before it advises."},
                "originalLanguage": "en",
                "effectiveFromPrecision": "day",
                "terms": ["service_type:custody", "jurisdiction:no"],
            },
            versions=True,
        )
        self._refused_at_approval(proposal)
        self.assertEqual(ObligationVersion.objects.filter(obligation=self.obligation).count(), 1)
        self.assertEqual(self._scope(), ["service_type:advice"])

    def test_an_empty_scope_clears_the_scope_and_links_no_term(self) -> None:
        """The scope is resolved before the version is written, and an empty list is
        never handed to the resolver, whose empty filter matches every term: an approved
        empty scope reads "Not client-specific", never "every term there is"."""
        created = self._post(
            "/proposals",
            {
                "kind": "new_obligation_version",
                "title": "Version 2, no longer client-specific",
                "targetType": "obligation",
                "targetId": str(self.obligation.id),
                "payload": {"summaries": {"en": "Every firm keeps this record."}, "originalLanguage": "en", "terms": []},
                "fieldSources": {"summaries.en": "https://www.fi.se/", "terms": "https://www.fi.se/"},
            },
            sign_in(self.editor),
        )
        self.assertEqual(created.status_code, 201, created.content)
        approved = self._post(f"/proposals/{created.json()['id']}/approve", {}, sign_in(self.reviewer, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(self._scope(), [])
        self.assertEqual(ObligationVersion.objects.filter(obligation=self.obligation).count(), 2)


class ReverificationStamp(ScenarioTestCase):
    """INV-06, INV-S8: re-verifying a record against its source is the one library write
    that is not a proposal, and it stays a stamp. Every outcome files a Verification row —
    the history is append-only (library 0004), so a second stamp is a second row and never
    an edit of the first. Only `no_change` moves `last_verified_at` and `verified_by`: the
    editor saw the source and it still says what the library says. A change found or a
    source that would not load leaves the old date standing, so the record still reads as
    last verified when it truly was.

    The route over this writer is chunk3-rest-T11b.
    """

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.actor = Actor(kind=ActorType.USER, id=self.editor.id, label=self.editor.name)
        self.assertion_id = uuid.uuid4()
        with library_write("test fixture"):
            instrument = Instrument.objects.create(
                stable_key="fffs-2017-2",
                short_name="FFFS 2017:2",
                official_ref="FFFS 2017:2",
                source_url="https://www.fi.se/",
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                regime=TaxonomyTerm.objects.get(dimension__key="regime", key="securities"),
                created_origin="user",
            )
            self.obligation = Obligation.objects.create(
                stable_key="fffs-2017-2/9/6",
                instrument=instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.get(key="conduct"),
                created_origin="user",
                source_url="https://www.fi.se/",
                source_label="FFFS 2017:2, 9 kap. 6 §",
                last_verified_at=WAS_VERIFIED_AT,
            )

    def _reverify(self, outcome: str, note: str = "") -> Any:
        from apps.proposals import apply

        with transaction.atomic():
            return apply.apply_reverification(
                self.obligation,
                actor=self.actor,
                verified_by=self.editor,
                outcome=outcome,
                note=note,
                step_up_assertion_id=self.assertion_id,
            )

    def test_no_change_stamps_the_date_and_the_verifier_and_nothing_else(self) -> None:
        before: dict[str, Any] = dict(Obligation.objects.values().get(id=self.obligation.id))
        verification = self._reverify(VerificationOutcome.NO_CHANGE.value, note="Checked against fi.se.")
        after: dict[str, Any] = dict(Obligation.objects.values().get(id=self.obligation.id))
        changed = {name for name, value in after.items() if before[name] != value}
        self.assertEqual(changed, {"last_verified_at", "verified_by_id"})
        self.assertEqual(after["last_verified_at"], verification.verified_at)
        self.assertEqual(after["verified_by_id"], self.editor.id)
        self.assertEqual(verification.note, "Checked against fi.se.")

    def test_a_change_found_or_an_unreachable_source_files_the_row_and_leaves_the_stamp(self) -> None:
        for outcome in (VerificationOutcome.CHANGE_FOUND.value, VerificationOutcome.SOURCE_UNAVAILABLE.value):
            with self.subTest(outcome=outcome):
                verification = self._reverify(outcome)
                self.obligation.refresh_from_db()
                self.assertEqual(verification.outcome, outcome)
                self.assertEqual(self.obligation.last_verified_at, WAS_VERIFIED_AT)
                self.assertIsNone(self.obligation.verified_by_id)

    def test_every_stamp_is_a_new_verification_row_pointing_at_the_obligation(self) -> None:
        first = self._reverify(VerificationOutcome.CHANGE_FOUND.value)
        second = self._reverify(VerificationOutcome.NO_CHANGE.value)
        rows = Verification.objects.filter(subject_id=self.obligation.id)
        self.assertEqual(rows.count(), 2)
        self.assertNotEqual(first.id, second.id)
        for row in rows:
            self.assertEqual(row.subject_type, SubjectType.OBLIGATION.value)
            self.assertEqual(row.verified_by_id, self.editor.id)

    def test_one_audit_row_carries_the_step_up_assertion_and_no_tenant(self) -> None:
        verification = self._reverify(VerificationOutcome.NO_CHANGE.value, note="Checked against fi.se.")
        event = AuditEvent.objects.get(action="library.reverified")
        self.assertEqual(event.step_up_assertion_id, self.assertion_id)
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.subject_id, self.obligation.id)
        self.assertEqual(event.subject_title, self.obligation.stable_key)
        self.assertEqual(event.after["verificationId"], str(verification.id))
        self.assertEqual(event.after["outcome"], VerificationOutcome.NO_CHANGE.value)
        self.assertEqual(event.before["lastVerifiedAt"], WAS_VERIFIED_AT.isoformat())
        self.assertEqual(event.after["lastVerifiedAt"], verification.verified_at.isoformat())
        for haystack in (event.summary, str(event.after)):
            self.assertNotIn("Checked against fi.se.", haystack)

    def test_the_stamp_happens_inside_the_fence_and_refuses_an_outcome_that_is_not_one(self) -> None:
        from apps.proposals import apply

        with self.assertRaises(ValidationError) as caught, transaction.atomic():
            apply.apply_reverification(
                self.obligation,
                actor=self.actor,
                verified_by=self.editor,
                outcome="looks_fine",
                note="",
                step_up_assertion_id=self.assertion_id,
            )
        self.assertEqual(caught.exception.code, "unknown_key")
        self.assertFalse(Verification.objects.exists())
        # Outside library_write() the same write is refused by the fence itself (PRO-01).
        with self.assertRaises(LibraryWriteRefused):
            self.obligation.save(update_fields=["last_verified_at"])


class LibraryMergeRepoints(ScenarioTestCase):
    """VOC-02, VOC-07, VOC-S5 for a library list: an approved merge moves every current
    library and watch row that carries the merged-away value, in the approval's own
    transaction, and drops a row whose twin already carries the target. The merged-away row
    stays, retired, with its labels, so history still resolves; the number the preview
    promised is the number that moved, and the audit row says so per table."""

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        seed_term_dimensions()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _approved(self, response: Any) -> Any:
        self.assertEqual(response.status_code, 202, response.content)
        return self._post(f"/proposals/{response.json()['proposal']['id']}/approve", {}, sign_in(self.reviewer, step_up=True))

    def _new(self, list_name: str, key: str, label: str, extra: dict[str, Any] | None = None) -> None:
        body: dict[str, Any] = {"key": key, "labels": {"en": label}, **({"extra": extra} if extra else {})}
        approved = self._approved(self._post(f"/vocab/{list_name}", body, sign_in(self.editor)))
        self.assertEqual(approved.status_code, 200, approved.content)

    def _preview(self, list_name: str, key: str, into: str) -> dict[str, Any]:
        response = Client().post(
            f"{V1}/vocab/{list_name}/{key}/merge?dryRun=true", data={"into": into}, content_type="application/json", **sign_in(self.editor)
        )
        self.assertEqual(response.status_code, 200, response.content)
        preview: dict[str, Any] = response.json()
        return preview

    def _merge(self, list_name: str, key: str, into: str) -> Any:
        return self._approved(self._post(f"/vocab/{list_name}/{key}/merge", {"into": into}, sign_in(self.editor)))

    def _merged_audit(self, row: Any) -> AuditEvent:
        return AuditEvent.objects.get(action="vocabulary.merged", subject_id=row.id)

    def test_a_used_flags_merge_moves_its_change_term_rows_and_counts_what_moved(self) -> None:
        self._new("flag", "client_money", "Client money")
        self._new("flag", "client_funds", "Client funds held")
        funds = Flag.objects.get(key="client_funds")
        both = watch_build.change()
        watch_build.term_link(both, flag_key="client_funds")
        watch_build.term_link(both, flag_key="client_money")
        only = watch_build.change()
        watch_build.term_link(only, flag_key="client_funds")
        twin = ChangeTerm.objects.get(change=both, flag=funds)
        moving = ChangeTerm.objects.get(change=only, flag=funds)

        preview = self._preview("flag", "client_funds", "client_money")
        # Two changes carry it; one already carries the target, so one link moves.
        self.assertEqual((preview["usageCount"], preview["repointed"]), (2, 1))
        self.assertEqual(self._merge("flag", "client_funds", "client_money").status_code, 200)

        self.assertFalse(ChangeTerm.objects.filter(flag=funds).exists())
        self.assertEqual(list(ChangeTerm.objects.filter(change=both).values_list("flag__key", flat=True)), ["client_money"])
        self.assertEqual(list(ChangeTerm.objects.filter(change=only).values_list("flag__key", flat=True)), ["client_money"])
        retired = Flag.objects.get(pk=funds.pk)
        self.assertFalse(retired.active)
        self.assertEqual(retired.labels.get(language="en").text, "Client funds held")
        audit = self._merged_audit(funds)
        self.assertEqual((audit.before["from"], audit.after["into"]), ("client_funds", "client_money"))
        self.assertEqual(audit.after["repointed"], preview["repointed"])
        self.assertEqual(audit.after["moved"], {ChangeTerm._meta.db_table: 1})
        # The audit row names the link that moved and the twin that went (H23), so which
        # change carried the merged-away flag can be rebuilt from the log alone.
        self.assertEqual(audit.after["rows"], {ChangeTerm._meta.db_table: {"moved": [str(moving.id)], "dropped": [str(twin.id)]}})
        self.assertEqual(ChangeTerm.objects.get(pk=moving.pk).flag_id, Flag.objects.get(key="client_money").id)
        self.assertFalse(ChangeTerm.objects.filter(pk=twin.pk).exists())

    def test_a_tag_merge_moves_obligation_tags_inside_the_approval(self) -> None:
        self._new("library_tag", "retrocessions", "Retrocessions")
        self._new("library_tag", "inducement_payments", "Inducement payments")
        charges = LibraryTag.objects.get(key="inducement_payments")
        on = library_build.instrument(key="lvfs-2026-1", regime="regime:securities")
        both = library_build.obligation(on, key="obl-both", tags=("retrocessions", "inducement_payments"))
        only = library_build.obligation(on, key="obl-only", tags=("inducement_payments",))
        versions = list(ObligationVersion.objects.filter(obligation__in=(both, only)).values_list("id", "version_number"))

        preview = self._preview("library_tag", "inducement_payments", "retrocessions")
        self.assertEqual(self._merge("library_tag", "inducement_payments", "retrocessions").status_code, 200)

        for obligation in (both, only):
            with self.subTest(obligation=obligation.stable_key):
                self.assertEqual(list(ObligationTag.objects.filter(obligation=obligation).values_list("tag__key", flat=True)), ["retrocessions"])
        self.assertFalse(LibraryTag.objects.get(pk=charges.pk).active)
        # A merge moves link rows and never writes a version.
        self.assertEqual(list(ObligationVersion.objects.filter(obligation__in=(both, only)).values_list("id", "version_number")), versions)
        audit = self._merged_audit(charges)
        self.assertEqual((preview["repointed"], audit.after["repointed"]), (1, 1))
        self.assertEqual(audit.after["moved"], {ObligationTag._meta.db_table: 1})

    def test_a_relation_merge_drops_the_duplicate_of_an_instrument_relation_and_moves_the_rest(self) -> None:
        self._new("relation_type", "amends_in_part", "Amends in part")
        in_part = RelationType.objects.get(key="amends_in_part")
        amended = library_build.instrument(key="fffs-2017-2", regime="regime:securities")
        twice = library_build.instrument(key="fffs-2026-11", regime="regime:securities")
        once = library_build.instrument(key="fffs-2026-12", regime="regime:securities")
        library_build.relate_instruments(twice, amended, relation="amends")
        twin = library_build.relate_instruments(twice, amended, relation="amends_in_part")
        moving = library_build.relate_instruments(once, amended, relation="amends_in_part")
        first = library_build.obligation(amended, key="obl-first")
        second = library_build.obligation(amended, key="obl-second")
        library_build.relate(first, second, relation="amends_in_part")
        between = ObligationRelation.objects.get(relation_type=in_part)

        preview = self._preview("relation_type", "amends_in_part", "amends")
        self.assertEqual((preview["usageCount"], preview["repointed"]), (3, 2))
        self.assertEqual(self._merge("relation_type", "amends_in_part", "amends").status_code, 200)

        relations = InstrumentRelation.objects.filter(to_instrument=amended)
        self.assertEqual(sorted(relations.values_list("from_instrument__stable_key", "relation_type__key")), [("fffs-2026-11", "amends"), ("fffs-2026-12", "amends")])
        audit = self._merged_audit(in_part)
        self.assertEqual(audit.after["moved"], {InstrumentRelation._meta.db_table: 1, ObligationRelation._meta.db_table: 1})
        self.assertEqual(
            audit.after["rows"],
            {
                InstrumentRelation._meta.db_table: {"moved": [str(moving.id)], "dropped": [str(twin.id)]},
                ObligationRelation._meta.db_table: {"moved": [str(between.id)], "dropped": []},
            },
        )

    def test_a_merge_across_kinds_of_level_is_refused_when_proposed_and_when_approved(self) -> None:
        """A level's kind is what the standards rules read (INV-08, D-35, D-36), so merging a
        law's level into `standard`, or a standard's level into a law's, would move records
        from under one rule to another with no check of either. Refused when proposed, and
        at approval for a proposal filed before the rule, with nothing moved."""
        self._new("instrument_level", "national_act", "National act", {"bindingDefault": True, "rank": 41})
        national = InstrumentLevel.objects.get(key="national_act")
        bare = library_build.instrument(key="sfs-2026-1", regime="regime:securities", level="national_act")
        with_text = library_build.instrument(key="sfs-2026-2", regime="regime:securities", level="national_act")
        library_build.provision(with_text, key="sfs-2026-2-1-kap")
        edition = self._approved(self._post("/vocab/instrument_level", {"key": "iso_edition", "labels": {"en": "ISO edition"}, "kind": "standard"}, sign_in(self.editor)))
        self.assertEqual(edition.status_code, 200, edition.content)

        for key, into in (("national_act", "standard"), ("iso_edition", "eu_guidance")):
            with self.subTest(key=key, into=into):
                proposed = self._post(f"/vocab/instrument_level/{key}/merge", {"into": into}, sign_in(self.editor))
                self.assertEqual(proposed.status_code, 409, proposed.content)
                self.assertEqual(proposed.json()["code"], "invalid_transition")
        self.assertFalse(Proposal.objects.filter(kind="vocabulary_merge").exists())

        stored = Proposal.objects.create(
            kind="vocabulary_merge",
            title="Filed before the rule",
            payload={"list": "instrument_level", "key": "national_act", "into": "standard"},
            origin="user",
            proposed_by_user=self.editor,
            target_type="instrument_level",
            target_id=national.id,
        )
        refused = self._post(f"/proposals/{stored.id}/approve", {}, sign_in(self.reviewer, step_up=True))
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(refused.json()["code"], "invalid_transition")

        self.assertEqual(sorted(Instrument.objects.filter(pk__in=(bare.pk, with_text.pk)).values_list("level__key", flat=True)), ["national_act", "national_act"])
        self.assertTrue(InstrumentLevel.objects.get(pk=national.pk).active)
        self.assertEqual(Proposal.objects.get(pk=stored.pk).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(action="vocabulary.merged").exists())
        self.assertFalse(AuditEvent.objects.filter(action="proposal.approved", subject_id=stored.id).exists())

    def test_a_merge_into_itself_or_into_a_retired_value_is_refused_through_every_door(self) -> None:
        """`POST /proposals` takes a merge payload without the vocabulary route, so the rows it
        names are checked there too, and again at approval for the list as it is then."""
        self._new("flag", "client_money", "Client money")
        self._new("flag", "client_assets", "Client assets")
        itself = self._post(
            "/proposals",
            {"kind": "vocabulary_merge", "title": "Merge into itself", "payload": {"list": "flag", "key": "client_money", "into": "client_money"}},
            sign_in(self.editor),
        )
        self.assertEqual(itself.status_code, 422, itself.content)
        self.assertEqual(itself.json()["code"], "validation_error")

        proposed = self._post("/vocab/flag/client_money/merge", {"into": "client_assets"}, sign_in(self.editor))
        self.assertEqual(proposed.status_code, 202, proposed.content)
        with library_write("test"):
            Flag.objects.filter(key="client_assets").update(active=False)
        refused = self._post(f"/proposals/{proposed.json()['proposal']['id']}/approve", {}, sign_in(self.reviewer, step_up=True))
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(refused.json()["code"], "invalid_transition")
        self.assertTrue(Flag.objects.get(key="client_money").active)
        retired = self._post("/vocab/flag/client_money/merge", {"into": "client_assets"}, sign_in(self.editor))
        self.assertEqual(retired.status_code, 409, retired.content)
        self.assertEqual(retired.json()["code"], "invalid_transition")


class JurisdictionsByProposal(ScenarioTestCase):
    """ADM-02, VOC-07, FP-04, D-94: a jurisdiction is relabelled, retired and restored through
    an approved proposal like any library list row, never added and never merged away, and
    its key never changes. The approval moves the term that mirrors it in the same
    transaction, so the footprint's markets read as the jurisdiction list does; the reference
    seed a deploy re-runs undoes none of it. An agent's confirmation names both agents on the
    row and the term and never reads as a person's."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenancy.clear_tenant()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")

    def _send(self, method: str, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        response = getattr(self.client, method)(f"{V1}{path}", data=body, content_type="application/json", **headers)
        tenancy.clear_tenant()
        return response

    def _applied(self, method: str, path: str, body: dict[str, Any], **headers: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper forwarding request headers
        proposed = self._send(method, path, body, {**sign_in(self.editor), **headers})
        self.assertEqual(proposed.status_code, 202, proposed.content)
        proposal: dict[str, Any] = proposed.json()["proposal"]
        approved = self._send("post", f"/proposals/{proposal['id']}/approve", {}, sign_in(self.reviewer, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        return proposal

    def _term(self, key: str) -> TaxonomyTerm:
        return TaxonomyTerm.objects.get(jurisdiction__key=key)

    def test_a_relabel_is_a_proposal_and_the_mirrored_term_follows_in_the_same_approval(self) -> None:
        term = self._term("se")
        proposal = self._applied("patch", "/vocab/jurisdiction/se", {"labels": {"sv": "Konungariket Sverige"}, "sortOrder": 7}, HTTP_IF_MATCH="1")
        self.assertEqual(proposal["kind"], "vocabulary_relabel")
        row = Jurisdiction.objects.get(key="se")
        self.assertEqual((row.version, row.sort_order, row.verified_origin, row.verified_by_agent_id), (2, 7, "user", None))
        self.assertEqual(str(row.applied_by_proposal_id), proposal["id"])
        self.assertEqual((row.labels.get(language="sv").text, row.labels.get(language="en").text), ("Konungariket Sverige", "Sweden"))
        followed = TaxonomyTerm.objects.get(pk=term.pk)
        self.assertEqual((followed.version, followed.sort_order, followed.active, followed.verified_origin), (term.version + 1, 7, True, "user"))
        self.assertEqual(followed.labels.get(language="sv").text, "Konungariket Sverige")
        self.assertFalse(followed.labels.get(language="sv").is_machine)
        audit = AuditEvent.objects.filter(subject_id=term.id, action="taxonomy.term_updated").latest("created")
        self.assertEqual((audit.before["labels"]["sv"], audit.after["labels"]["sv"]), ("Sverige", "Konungariket Sverige"))
        self.assertIsNotNone(audit.step_up_assertion_id)
        # A deploy's reference seeds put back neither the order nor the wording.
        seed_jurisdictions()
        seed_taxonomy_terms()
        self.assertEqual(Jurisdiction.objects.get(key="se").sort_order, 7)
        self.assertEqual((self._term("se").sort_order, self._term("se").labels.get(language="sv").text), (7, "Konungariket Sverige"))
        # The list reads the stamp, and a proposal made from the old read is refused.
        read = self._send("get", "/vocab/jurisdiction/se", {}, sign_in(self.editor)).json()
        self.assertEqual((read["version"], read["verifiedOrigin"]), (2, "user"))
        stale = self._send("patch", "/vocab/jurisdiction/se", {"labels": {"en": "Sweden"}}, {**sign_in(self.editor), "HTTP_IF_MATCH": "1"})
        self.assertEqual((stale.status_code, stale.json()["code"]), (409, "stale_write"))

    def test_retire_and_restore_take_the_mirrored_term_with_them(self) -> None:
        self._applied("post", "/vocab/jurisdiction/dk/retire", {})
        self.assertEqual((Jurisdiction.objects.get(key="dk").active, self._term("dk").active), (False, False))
        # A deploy's reference seeds keep the decision: neither the row nor its term comes back.
        seed_jurisdictions()
        seed_taxonomy_terms()
        self.assertEqual((Jurisdiction.objects.get(key="dk").active, self._term("dk").active), (False, False))
        self._applied("post", "/vocab/jurisdiction/dk/restore", {})
        self.assertEqual((Jurisdiction.objects.get(key="dk").active, self._term("dk").active), (True, True))
        # International mirrors no term, so it retires alone.
        self._applied("post", "/vocab/jurisdiction/intl/retire", {})
        self.assertFalse(Jurisdiction.objects.get(key="intl").active)
        self.assertFalse(TaxonomyTerm.objects.filter(jurisdiction__key="intl").exists())

    def test_a_retirement_of_a_jurisdiction_records_are_filed_under_asks_first(self) -> None:
        library_build.instrument(key="lag-2004-297", regime="regime:securities", jurisdiction="se")
        asked = self._send("post", "/vocab/jurisdiction/se/retire", {}, sign_in(self.editor))
        self.assertEqual((asked.status_code, asked.json()["code"], asked.json()["usageCount"]), (409, "in_use", 1))
        self._applied("post", "/vocab/jurisdiction/se/retire", {"confirm": True})
        self.assertFalse(Jurisdiction.objects.get(key="se").active)

    def test_a_jurisdictions_key_never_changes_and_no_value_is_added_or_merged_away(self) -> None:
        editor = sign_in(self.editor)
        for method, path, body in (
            ("post", "/vocab/jurisdiction", {"key": "is", "labels": {"en": "Iceland"}}),
            ("post", "/vocab/jurisdiction/no/merge", {"into": "dk"}),
            ("post", "/vocab/jurisdiction/no/merge?dryRun=true", {"into": "dk"}),
            ("post", "/proposals", {"kind": "vocabulary_merge", "title": "Merge", "payload": {"list": "jurisdiction", "key": "no", "into": "dk"}}),
        ):
            with self.subTest(path=path):
                refused = self._send(method, path, body, editor)
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"), refused.content)
        # A merge filed before the rule is refused at approval and stays open.
        stored = Proposal.objects.create(
            kind="vocabulary_merge", title="Filed before the rule", payload={"list": "jurisdiction", "key": "no", "into": "dk"},
            origin="user", proposed_by_user=self.editor,
        )
        refused = self._send("post", f"/proposals/{stored.id}/approve", {}, sign_in(self.reviewer, step_up=True))
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"))
        self.assertEqual(Proposal.objects.get(pk=stored.pk).status, ProposalStatus.OPEN.value)
        self.assertTrue(Jurisdiction.objects.get(key="no").active)
        self.assertFalse(Jurisdiction.objects.filter(key="is").exists())
        # The key itself is immutable on the row, whatever door is open.
        row = Jurisdiction.objects.get(key="fi")
        row.key = "suomi"
        with self.assertRaises(ValidationError), library_write("test", door="proposal"):
            row.save()

    def test_an_agents_confirmation_names_both_agents_on_the_row_and_its_term(self) -> None:
        proposing = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        run = agents_testing.platform_run(key=proposing)
        confirming = agents_testing.reviewer_api_key()
        agent = proposing.agent
        proposal, _ = logic.create(
            kind="vocabulary_relabel",
            title="Relabel Finland",
            payload={"list": "jurisdiction", "key": "fi", "labels": {"sv": "Republiken Finland"}},
            proposer=logic.Proposer(actor=Actor(kind=ActorType.AGENT, id=agent.id, label=agent.key), api_key_id=proposing.id, agent_id=agent.id),
            agent_run_id=run.id,
        )
        approved = self.client.post(
            f"{V1}/proposals/{proposal.id}/approve", data=agents_testing.decision(confirming),
            content_type="application/json", HTTP_X_API_KEY=confirming.plain_key,
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        tenancy.clear_tenant()
        row, term = Jurisdiction.objects.get(key="fi"), self._term("fi")
        for stamped in (row, term):
            with self.subTest(stamped=type(stamped).__name__):
                self.assertEqual((stamped.verified_origin, stamped.verified_by_agent_id), ("agent", confirming.agent.id))
                self.assertEqual(Proposal.objects.values_list("proposed_by_agent_id", flat=True).get(pk=proposal.id), agent.id)
                self.assertEqual(stamped.applied_by_proposal_id, proposal.id)
                self.assertTrue(stamped.labels.get(language="sv").is_machine, "an agent's wording is labelled machine-made")
        read = self._send("get", "/vocab/jurisdiction/fi", {}, sign_in(self.editor)).json()
        self.assertEqual(
            (read["verifiedOrigin"], read["confirmedByAgent"]["key"], read["proposedByAgent"]["key"]),
            ("agent", confirming.agent.key, agent.key),
        )


class MirroredDimensionRowAndMergesWithoutLinks(ScenarioTestCase):
    """Hardening H28: the dimension row whose terms mirror the jurisdictions is as closed to
    proposals as its terms, at propose and at apply, so no approval can turn off its footprint
    rule, retire it or merge it; a merge on a list that counts its uses without links (a
    dimension's terms) is refused while the value is in use, because it would retire the
    value and move nothing; and a retired target is refused on either side of a merge (the
    `LibraryMergeRepoints` test on flags proves that one for the route and the apply)."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenancy.clear_tenant()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")

    def _send(self, path: str, body: dict[str, Any], headers: dict[str, Any], method: str = "post") -> Any:
        response = getattr(self.client, method)(f"{V1}{path}", data=body, content_type="application/json", **headers)
        tenancy.clear_tenant()
        return response

    def _stored(self, kind: str, payload: dict[str, Any]) -> Proposal:
        """A proposal stored as one filed before these rules existed was."""
        return Proposal.objects.create(kind=kind, title="Filed before H28", payload=payload, origin="user", proposed_by_user=self.editor)

    def _refused_at_approval(self, proposal: Proposal, status: int, code: str) -> None:
        reviewer = sign_in(self.reviewer, step_up=True)
        written = AuditEvent.objects.count()
        refused = self._send(f"/proposals/{proposal.id}/approve", {}, reviewer)
        self.assertEqual((refused.status_code, refused.json()["code"]), (status, code), refused.content)
        self.assertEqual(Proposal.objects.get(pk=proposal.pk).status, ProposalStatus.OPEN.value)
        self.assertEqual(AuditEvent.objects.count(), written, "nothing was written, not even the decision")

    def test_a_proposal_on_the_mirrored_dimension_row_is_refused_at_propose_and_at_apply(self) -> None:
        dimension = TermDimension.objects.get(terms__jurisdiction__key="se")
        editor = sign_in(self.editor)
        change = {"extra": {"restrictsFootprint": False}}
        refused = self._send(f"/vocab/term_dimension/{dimension.key}", change, {**editor, "HTTP_IF_MATCH": str(dimension.version)}, method="patch")
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "jurisdiction_term_mirrored"), refused.content)
        for kind, payload in (
            ("vocabulary_relabel", {"list": "term_dimension", "key": dimension.key, **change}),
            ("vocabulary_retire", {"list": "term_dimension", "key": dimension.key}),
            ("vocabulary_merge", {"list": "term_dimension", "key": "service_type", "into": dimension.key}),
        ):
            with self.subTest(kind=kind):
                direct = self._send("/proposals", {"kind": kind, "title": "Direct", "payload": payload}, editor)
                self.assertEqual((direct.status_code, direct.json()["code"]), (422, "jurisdiction_term_mirrored"), direct.content)
                self._refused_at_approval(self._stored(kind, payload), 422, "jurisdiction_term_mirrored")
        kept = TermDimension.objects.get(pk=dimension.pk)
        self.assertEqual((kept.restricts_footprint, kept.active, kept.version), (dimension.restricts_footprint, True, dimension.version))

    def test_a_merge_that_would_move_none_of_the_uses_of_a_value_is_refused(self) -> None:
        with library_write("test"):
            desk = TermDimension.objects.create(key="desk", kind="classification")
            TermDimension.objects.create(key="counter", kind="classification")
            TaxonomyTerm.objects.create(dimension=desk, key="fx_desk")
        payload = {"list": "term_dimension", "key": "desk", "into": "counter"}
        proposed = self._send("/vocab/term_dimension/desk/merge", {"into": "counter"}, sign_in(self.editor))
        self.assertEqual((proposed.status_code, proposed.json()["code"]), (409, "invalid_transition"), proposed.content)
        self._refused_at_approval(self._stored("vocabulary_merge", payload), 409, "invalid_transition")
        self.assertTrue(TermDimension.objects.get(key="desk").active)
        self.assertEqual(TaxonomyTerm.objects.get(key="fx_desk").dimension_id, desk.id)
        # With no use left, the same merge is only a retirement and goes through.
        with library_write("test"):
            TaxonomyTerm.objects.filter(key="fx_desk").update(dimension=TermDimension.objects.get(key="counter"))
        merged = self._send("/vocab/term_dimension/desk/merge", {"into": "counter"}, sign_in(self.editor))
        self.assertEqual(merged.status_code, 202, merged.content)


class ApprovalsOnOneRowRace(TransactionTestCase):
    """Two approvals of different proposals on one library row at once (PRO-02, INV-05, H34,
    H25), each session on its own cw_app connection as two requests reach production (the
    helpers in apps/proposals/tests_decide.py). The first applies and holds its transaction
    open until PostgreSQL reports the second waiting on it.

    A relabel reads the row and saves it whole, so without the row lock in `apply._row` a
    person's relabel read the row before an agent's committed and wrote it back over it: one
    version bump lost and the agent's stamp replaced by the person's while the agent's
    machine label stayed. Proven to fail 2026-09-25 without that lock (version 2, not 3, and
    `verified_origin` read `user`).

    A provision's insert reads its instrument's level in `provision_not_under_standard`, and
    a level merge re-points the instrument under a lock the insert's foreign-key check waits
    on only after that trigger has passed, so a provision could land under an instrument the
    merge had just moved onto a standard. `apply._new_provision` locks the instrument and
    reads it again first. Proven to fail 2026-09-25 without that lock: the provision was
    written under the standard."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            _seed()
        with transaction.atomic():
            tenancy.clear_tenant()
            self.proposer = factories.platform_user(roles=("library_editor",), email="proposer@bleqq.test")
            self.person = factories.platform_user(roles=("library_editor",), email="person@bleqq.test")
            confirmer = agents_testing.reviewer_api_key()
            self.review_run = agents_testing.platform_run(key=confirmer)
            self.agent = logic.Reviewer(
                actor=_agent_actor(confirmer), api_key_id=confirmer.id, agent_id=confirmer.agent.id, api_key_prefix=confirmer.row.key_prefix
            )

    def _proposed(self, kind: str, payload: dict[str, Any], **sourced: Any) -> uuid.UUID:  # compliance: allow-kwargs test helper forwarding create() arguments
        with transaction.atomic():
            tenancy.clear_tenant()
            proposal, _ = logic.create(
                kind=kind, title=f"{kind} {uuid.uuid4().hex[:6]}", payload=payload, proposer=logic.Proposer(actor=_actor(self.proposer), user=self.proposer), **sourced
            )
            return proposal.id

    def _by_agent(self, proposal_id: uuid.UUID) -> Callable[[], object]:
        return lambda: logic.approve(
            proposal=logic.by_id(proposal_id),
            reviewer=self.agent,
            actor=self.agent.actor,
            note="",
            step_up_assertion_id=None,
            decision=AgentDecision.model_validate(agents_testing.DECISION),
            agent_run_id=self.review_run.id,
        )

    def test_an_agents_and_a_persons_relabel_of_one_row_at_once_both_land_in_turn(self) -> None:
        created = self._proposed("vocabulary_create", {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}})
        with transaction.atomic():
            tenancy.clear_tenant()
            _approval(created, self.person)()
        by_agent = self._proposed("vocabulary_relabel", {"list": "flag", "key": "client_money", "labels": {"en": "Client funds"}})
        by_person = self._proposed("vocabulary_relabel", {"list": "flag", "key": "client_money", "labels": {"sv": "Kundmedel"}})

        self.assertEqual(_race(self._by_agent(by_agent), _approval(by_person, self.person)), (LANDED, LANDED))

        with transaction.atomic():
            tenancy.clear_tenant()
            flag = Flag.objects.get(key="client_money")
            # Both bumps count, and the agent's machine label keeps the row naming the agent.
            self.assertEqual(flag.version, 3)
            self.assertEqual((flag.verified_origin, flag.verified_by_agent_id, flag.applied_by_proposal_id), ("agent", self.agent.agent_id, by_agent))
            labels = {label.language: (label.text, label.is_machine) for label in flag.labels.all()}
            self.assertEqual(labels, {"en": ("Client funds", True), "sv": ("Kundmedel", False)})

    def _instrument_on_a_new_level(self) -> tuple[Instrument, InstrumentLevel]:
        with transaction.atomic():
            tenancy.clear_tenant()
            with library_write("test fixture"):
                level = InstrumentLevel.objects.create(key="national_act", binding_default=True, rank=41, active=True)
            return library_build.instrument(key="sfs-2026-1", regime="regime:securities", level="national_act"), level

    def _merge_onto_the_standard(self, level: InstrumentLevel) -> Callable[[], object]:
        """What a level merge writes (`apply._vocabulary_merge`): every instrument at `level`
        re-pointed onto the standard level through `repoint.move`, and the database's refusal
        answered by the code the trigger names. The merge route checks the two kinds match
        first; this is the write beneath it, which the trigger has to hold on its own."""

        def merge() -> None:
            try:
                with transaction.atomic(), library_write("test: a level merge"):
                    repoint.move(REGISTRY["instrument_level"].links, level, InstrumentLevel.objects.get(key="standard"), library=apply._repoint_rows)
            except IntegrityError as refused:
                if "provision_not_under_standard" not in str(refused):
                    raise
                raise ValidationError("Refused by the database.", code="provision_not_under_standard") from refused

        return merge

    def _provision_proposal(self, instrument: Instrument) -> uuid.UUID:
        return self._proposed(
            "new_provision",
            {
                "key": "sfs-2026-1-1-kap",
                "instrument": instrument.stable_key,
                "provisionKind": "chapter",
                "refLabel": "1 kap.",
                "texts": {"sv": "Lagen gäller för banker."},
                "originalLanguage": "sv",
            },
            field_sources={field: "https://www.riksdagen.se/" for field in ("instrument", "provisionKind", "refLabel", "texts.sv")},
            source_url="https://www.riksdagen.se/",
        )

    def _no_provision_under_a_standard(self) -> None:
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertFalse(Provision.objects.filter(instrument__level__kind="standard").exists())

    def test_a_level_merge_waiting_on_a_provision_insert_ends_in_provision_not_under_standard(self) -> None:
        instrument, level = self._instrument_on_a_new_level()
        provision = self._provision_proposal(instrument)

        outcomes = _race(_approval(provision, self.person), self._merge_onto_the_standard(level))

        self.assertEqual(outcomes, (LANDED, "provision_not_under_standard"))
        self._no_provision_under_a_standard()
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(Instrument.objects.get(pk=instrument.pk).level_id, level.id)

    def test_a_provision_insert_waiting_on_a_level_merge_is_refused_as_licensed_text(self) -> None:
        instrument, level = self._instrument_on_a_new_level()
        provision = self._provision_proposal(instrument)

        outcomes = _race(self._merge_onto_the_standard(level), _approval(provision, self.person))

        self.assertEqual(outcomes, (LANDED, "licensed_text"))
        self._no_provision_under_a_standard()
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(Proposal.objects.get(pk=provision).status, ProposalStatus.OPEN.value)
