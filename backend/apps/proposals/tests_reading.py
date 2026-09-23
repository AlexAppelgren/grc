"""Reading the queue (chunk 4, PRO-01, PRO-03, VOC-07, INV-04).

What a reviewer is given to decide on: the row that names the library record a proposal
would change, the page that holds what the library says today against what the proposal
would make it say, and the sources behind every changed value. What a reviewer is not
given: the name of a bank member who proposed something, which never reaches the console.

And the other side of the same table: a bank's own list of what it has asked for, cut by
row-level security on `proposal_tenant` rather than by a filter in Python, so tenant B
cannot read tenant A's requests even if this module forgets to ask it not to.

The query counts are pinned (playbook 10): the queue costs the same whether it holds one
row or three, and a bank's list costs the same at two page sizes, so an N+1 shows up here
as a number rather than in production as a slow screen.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.library.models import (
    Instrument,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.shared.tenancy import library_write
from apps.taxonomy.models import DutyType, InstrumentLevel, ProvisionKind, RejectionReason, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

V1 = "/api/v1"
SOURCE = "https://www.fi.se/"
# A source may be the stable key of a provision the library holds instead of a link (PRO-01).
PROVISION_SOURCE = "fffs-2017-2-9-6"
# The whole answer a bank's own list costs, measured 2026-09-21 and pinned so an N+1 shows
# up as a number: the scenario client's audit count (1), the request's savepoint pair (2),
# the auth layer for a tenant session (6: the identity flag on, the session row, the flag
# off, the tenant the session activates, the member's permissions and the latest step-up),
# and the read itself (2: how many proposals match, and the page).
TENANT_LIST_QUERIES = 1 + 2 + 6 + 2
VERSION_ONE_SV = "Institutet bedömer kunden innan rådgivning. Bedömningen dokumenteras."
PROPOSED_SV = "Institutet bedömer kunden innan rådgivning. Bedömningen dokumenteras varje år."


class QueueReads(ScenarioTestCase):
    """GET /proposals and GET /proposals/{id} as the console reads them."""

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
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")
        self.instrument = self._instrument()
        self.obligation = self._obligation("obl-advice-suitability")
        self._provision()

    # --- fixtures ----------------------------------------------------------------------
    def _instrument(self) -> Instrument:
        with library_write("test"):
            return Instrument.objects.create(
                stable_key="fffs-2017-2",
                short_name="FFFS 2017:2",
                official_ref="FFFS 2017:2",
                source_url=SOURCE,
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                created_origin="user",
            )

    def _provision(self) -> Provision:
        """The provision a proposal cites as the source of a changed field, instead of a link."""
        with library_write("test"):
            return Provision.objects.create(
                stable_key=PROVISION_SOURCE,
                instrument=self.instrument,
                kind=ProvisionKind.objects.get(key="section"),
                ref_label="9 kap. 6 §",
                path="9/6",
            )

    def _obligation(self, stable_key: str) -> Obligation:
        """A duty with version 1 in force and one scope term, as the library seeds write it."""
        with library_write("test"):
            obligation = Obligation.objects.create(
                stable_key=stable_key,
                instrument=self.instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.get(key="conduct"),
                created_origin="user",
                source_url=SOURCE,
                source_label="FFFS 2017:2, 9 kap. 6 §",
            )
            ObligationTitle.objects.create(obligation=obligation, language_id="en", text=f"Assess the client: {stable_key}", is_original=True)
            version = ObligationVersion.objects.create(obligation=obligation, version_number=1, effective_from=date(2024, 1, 1))
            ObligationSummary.objects.create(version=version, language_id="sv", text=VERSION_ONE_SV, is_original=True)
            ObligationTerm.objects.create(obligation=obligation, term=self._term("legal_entity", "bank"))
        return obligation

    def _term(self, dimension: str, key: str) -> TaxonomyTerm:
        return TaxonomyTerm.objects.get(dimension__key=dimension, key=key)

    def _version_proposal(self, obligation: Obligation, *, proposer: Any = None) -> Proposal:
        """An agent's proposal of a new version, sourced field by field, waiting in the queue."""
        tenancy.clear_tenant()
        proposal, _ = logic.create(
            kind="new_obligation_version",
            title=f"Version 2 of {obligation.stable_key}",
            payload={
                "summaries": {"sv": PROPOSED_SV},
                "originalLanguage": "sv",
                "isMachine": True,
                "effectiveFrom": "2026-10-01",
                "effectiveFromPrecision": "day",
                "terms": ["legal_entity:bank", "client_category:retail"],
            },
            proposer=proposer or logic.Proposer(actor=factories.user_actor()),
            target_type="obligation",
            target_id=obligation.id,
            field_sources={
                "summaries.sv": SOURCE,
                "effectiveFrom": SOURCE,
                "terms": PROVISION_SOURCE,
            },
            source_label="Finansinspektionen, board decision 15 September 2026",
            source_url=SOURCE,
        )
        return proposal

    def _flag_proposal(self, proposer: Any) -> Proposal:
        tenancy.clear_tenant()
        proposal, _ = logic.create(
            kind="vocabulary_create",
            title="Add the flag Client money",
            payload={"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            proposer=proposer,
        )
        return proposal

    def _editor_proposer(self, user: Any) -> logic.Proposer:
        return logic.Proposer(actor=Actor(kind=ActorType.USER, id=user.id, label=user.name), user=user)

    # --- rows --------------------------------------------------------------------------
    def test_a_row_names_the_record_it_would_change(self) -> None:
        proposal = self._version_proposal(self.obligation)
        listed = self.client.get(f"{V1}/proposals", **sign_in(self.editor))
        self.assertEqual(listed.status_code, 200, listed.content)
        row = next(item for item in listed.json()["items"] if item["id"] == str(proposal.id))
        self.assertEqual(row["target"]["id"], str(self.obligation.id))
        self.assertEqual(row["target"]["title"], "Assess the client: obl-advice-suitability")
        self.assertEqual(row["target"]["referenceLabel"], "9 kap. 6 §")
        self.assertEqual(row["target"]["instrumentShortName"], "FFFS 2017:2")
        self.assertEqual(row["sourceLabel"], "Finansinspektionen, board decision 15 September 2026")
        self.assertFalse(row["isMine"], "an agent's proposal is nobody's own")
        self.assertFalse(row["fromOrganisation"])

    def test_a_vocabulary_proposal_names_no_record(self) -> None:
        proposal = self._flag_proposal(self._editor_proposer(self.editor))
        listed = self.client.get(f"{V1}/proposals", **sign_in(self.editor))
        row = next(item for item in listed.json()["items"] if item["id"] == str(proposal.id))
        self.assertIsNone(row["target"], "a vocabulary list is not a library record with a title")
        self.assertEqual(row["payload"]["key"], "client_money")

    def test_the_reader_is_told_which_proposals_are_their_own(self) -> None:
        mine = self._flag_proposal(self._editor_proposer(self.editor))
        theirs = self._version_proposal(self.obligation)
        rows = {item["id"]: item for item in self.client.get(f"{V1}/proposals", **sign_in(self.editor)).json()["items"]}
        self.assertTrue(rows[str(mine.id)]["isMine"])
        self.assertEqual(rows[str(mine.id)]["proposedBy"]["id"], str(self.editor.id))
        self.assertFalse(rows[str(theirs.id)]["isMine"])
        # The same proposal is not the second editor's own.
        second = {item["id"]: item for item in self.client.get(f"{V1}/proposals", **sign_in(self.second_editor)).json()["items"]}
        self.assertFalse(second[str(mine.id)]["isMine"])

    def test_a_proposal_made_inside_a_bank_reaches_the_console_without_its_proposer(self) -> None:
        """PRO-03: the console learns that a bank asked for it and nothing else — not the
        member's name, not their id, and not which bank they belong to."""
        self.activate(self.tenant)
        made_in_bank = self._post_from_tenant()
        rows = {item["id"]: item for item in self.client.get(f"{V1}/proposals", **sign_in(self.editor)).json()["items"]}
        row = rows[str(made_in_bank.id)]
        self.assertIsNone(row["proposedBy"])
        self.assertTrue(row["fromOrganisation"])
        self.assertFalse(row["isMine"])
        written = repr(row)
        self.assertNotIn(str(self.officer.id), written)
        self.assertNotIn(self.officer.name, written)
        # The detail withholds it too, and so does the row the officer's own call answered.
        detail = self.client.get(f"{V1}/proposals/{made_in_bank.id}", **sign_in(self.editor))
        self.assertIsNone(detail.json()["proposedBy"])
        self.assertTrue(detail.json()["fromOrganisation"])

    def _post_from_tenant(self) -> Proposal:
        """A proposal a bank's own member filed, through the door their screen uses."""
        made = self.client.post(
            f"{V1}/vocab/flag",
            data={"labels": {"en": "Client money"}},
            content_type="application/json",
            **sign_in(self.officer, tenant=self.tenant),
        )
        self.assertEqual(made.status_code, 202, made.content)
        self.activate(self.tenant)
        return Proposal.objects.get(pk=made.json()["proposal"]["id"])

    # --- filters -----------------------------------------------------------------------
    def test_the_queue_filters_by_origin_and_drops_the_readers_own(self) -> None:
        agents = self._version_proposal(self.obligation)
        mine = self._flag_proposal(self._editor_proposer(self.editor))
        editor = sign_in(self.editor)

        by_agent = self.client.get(f"{V1}/proposals?origin=agent", **editor).json()
        self.assertEqual([item["id"] for item in by_agent["items"]], [str(agents.id)])
        by_user = self.client.get(f"{V1}/proposals?origin=user", **editor).json()
        self.assertEqual([item["id"] for item in by_user["items"]], [str(mine.id)])
        not_mine = self.client.get(f"{V1}/proposals?notMine=true", **editor).json()
        self.assertEqual([item["id"] for item in not_mine["items"]], [str(agents.id)])
        self.assertEqual(not_mine["total"], 1, "the total counts the rows the filter left")
        # The second editor filed none of them, so nothing is theirs to drop.
        self.assertEqual(self.client.get(f"{V1}/proposals?notMine=true", **sign_in(self.second_editor)).json()["total"], 2)
        # A value that is not an origin is refused rather than answered with an empty queue.
        unknown = self.client.get(f"{V1}/proposals?origin=nobody", **editor)
        self.assertEqual(unknown.status_code, 422, unknown.content)
        self.assertEqual(unknown.json()["code"], "unknown_key")

    # --- detail ------------------------------------------------------------------------
    def test_the_detail_compares_the_proposed_text_with_what_the_library_says(self) -> None:
        proposal = self._version_proposal(self.obligation)
        answer = self.client.get(f"{V1}/proposals/{proposal.id}", **sign_in(self.editor))
        self.assertEqual(answer.status_code, 200, answer.content)
        body = answer.json()
        self.assertEqual(body["language"], "sv")
        self.assertEqual(body["currentSummary"]["text"], VERSION_ONE_SV)
        self.assertEqual(body["proposedText"], PROPOSED_SV)
        ops = [(segment["op"], segment["text"]) for segment in body["diff"]]
        self.assertEqual(ops[0], ("equal", "Institutet bedömer kunden innan rådgivning."))
        self.assertIn(("delete", "Bedömningen dokumenteras."), ops)
        self.assertIn(("insert", "Bedömningen dokumenteras varje år."), ops)
        # A source per changed field, the link ones carrying the proposal's own sentence and
        # the provision one carrying the key a reader follows into the library.
        sources = {source["field"]: (source["label"], source["url"]) for source in body["sources"]}
        self.assertEqual(sorted(sources), ["effectiveFrom", "summaries.sv", "terms"])
        self.assertEqual(sources["summaries.sv"], ("Finansinspektionen, board decision 15 September 2026", SOURCE))
        self.assertEqual(sources["terms"], (PROVISION_SOURCE, ""))
        self.assertEqual(body["scopeBefore"], ["legal_entity:bank"])
        self.assertEqual(body["scopeAfter"], ["legal_entity:bank", "client_category:retail"])
        self.assertIsNone(body["appliedVersion"])
        self.assertIsNone(body["rejectionReason"])

    def test_the_detail_of_a_vocabulary_proposal_compares_nothing(self) -> None:
        proposal = self._flag_proposal(self._editor_proposer(self.editor))
        body = self.client.get(f"{V1}/proposals/{proposal.id}", **sign_in(self.editor)).json()
        self.assertEqual((body["language"], body["proposedText"]), ("", ""))
        self.assertEqual((body["diff"], body["sources"], body["scopeBefore"]), ([], [], []))
        self.assertIsNone(body["currentSummary"])
        self.assertIsNone(body["scopeAfter"], "a vocabulary proposal leaves no record's scope alone or otherwise")

    def test_the_detail_shows_the_correction_and_then_the_version_it_wrote(self) -> None:
        proposal = self._version_proposal(self.obligation)
        corrected = "Institutet bedömer kunden innan rådgivning. Bedömningen dokumenteras varje kvartal."
        approved = self.client.post(
            f"{V1}/proposals/{proposal.id}/approve",
            data={"payloadOverrides": {"summaries": {"sv": corrected}}},
            content_type="application/json",
            **sign_in(self.editor, step_up=True),
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        body = self.client.get(f"{V1}/proposals/{proposal.id}", **sign_in(self.second_editor)).json()
        self.assertEqual(body["proposedText"], corrected, "the reviewer's own wording is what the diff shows")
        self.assertIn(("insert", "Bedömningen dokumenteras varje kvartal."), [(segment["op"], segment["text"]) for segment in body["diff"]])
        version = ObligationVersion.objects.get(obligation=self.obligation, version_number=2)
        self.assertEqual(body["appliedVersion"], {"id": str(version.id), "versionNumber": 2, "effectiveFrom": "2026-10-01"})

    def test_a_rejection_names_the_reason_row_it_was_refused_under(self) -> None:
        proposal = self._version_proposal(self.obligation)
        rejected = self.client.post(
            f"{V1}/proposals/{proposal.id}/reject",
            data={"rejectionCode": "wrong_scope", "note": "The scope is wider than the decision."},
            content_type="application/json",
            **sign_in(self.editor),
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)
        body = self.client.get(f"{V1}/proposals/{proposal.id}", **sign_in(self.editor)).json()
        self.assertEqual(body["rejectionReason"], {"key": "wrong_scope", "kind": None, "label": "Wrong scope"})

    def test_a_rejection_reason_is_a_row_of_the_list_and_not_a_word_of_its_own(self) -> None:
        """PRO-01, VOC-07: the reason is a key of the `rejection_reason` library list, so a
        code from an older screen, or one whose row has been retired, is refused rather than
        stored as a reason nobody can look up."""
        proposal = self._version_proposal(self.obligation)
        editor = sign_in(self.editor)
        unknown = self.client.post(
            f"{V1}/proposals/{proposal.id}/reject",
            data={"rejectionCode": "just_because", "note": "No."},
            content_type="application/json",
            **editor,
        )
        self.assertEqual(unknown.status_code, 422, unknown.content)
        self.assertEqual(unknown.json()["code"], "reason_required")

        with library_write("test"):
            RejectionReason.objects.filter(key="duplicate").update(active=False)
        retired = self.client.post(
            f"{V1}/proposals/{proposal.id}/reject",
            data={"rejectionCode": "duplicate", "note": "We have this already."},
            content_type="application/json",
            **editor,
        )
        self.assertEqual(retired.status_code, 422, retired.content)
        self.assertEqual(retired.json()["code"], "reason_required")
        self.assertEqual(Proposal.objects.get(pk=proposal.id).status, ProposalStatus.OPEN.value)

    # --- the tenant's own list ---------------------------------------------------------
    def test_a_bank_lists_its_own_proposals_and_never_another_banks(self) -> None:
        self.activate(self.tenant)
        mine = self._post_from_tenant()
        self._version_proposal(self.obligation)  # the console's own, linked to no bank

        answer = self.client.get(f"{V1}/tenant/proposals", **sign_in(self.officer, tenant=self.tenant))
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual([item["id"] for item in answer.json()["items"]], [str(mine.id)])
        self.assertEqual(answer.json()["total"], 1)
        row = answer.json()["items"][0]
        self.assertEqual((row["kind"], row["status"]), ("vocabulary_create", "open"))
        self.assertNotIn("payload", row, "a bank's list carries the request and its status, not the payload")

        other = factories.tenant(slug="second-bank")
        officer_there = factories.member(other, roles=("compliance_officer",)).user
        theirs = self.client.get(f"{V1}/tenant/proposals", **sign_in(officer_there, tenant=other))
        self.assertEqual(theirs.status_code, 200, theirs.content)
        self.assertEqual(theirs.json()["items"], [], "row-level security on proposal_tenant, not a filter in Python")

    def test_a_bank_filters_its_own_list(self) -> None:
        self.activate(self.tenant)
        mine = self._post_from_tenant()
        officer = sign_in(self.officer, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/tenant/proposals?status=open", **officer).json()["total"], 1)
        self.assertEqual(self.client.get(f"{V1}/tenant/proposals?status=approved", **officer).json()["total"], 0)
        self.assertEqual(self.client.get(f"{V1}/tenant/proposals?kind=vocabulary_create", **officer).json()["total"], 1)
        self.assertEqual(self.client.get(f"{V1}/tenant/proposals?targetList=flag", **officer).json()["total"], 1)
        self.assertEqual(self.client.get(f"{V1}/tenant/proposals?targetList=urgency", **officer).json()["total"], 0)
        # Paginated like every list: the total counts every match, the page holds one row.
        page = self.client.get(f"{V1}/tenant/proposals?limit=1", **officer).json()
        self.assertEqual((len(page["items"]), page["total"]), (1, 1))
        self.assertEqual(page["items"][0]["id"], str(mine.id))
        refused = self.client.get(f"{V1}/tenant/proposals?limit=101", **officer)
        self.assertEqual(refused.status_code, 422, refused.content)

    def test_the_review_routes_stay_the_consoles(self) -> None:
        """PRO-S7, PRO-03: no bank role reads the queue, whatever it holds inside its own
        organisation, and the bank's own list is not the console's."""
        proposal = self._version_proposal(self.obligation)
        officer = sign_in(self.officer, tenant=self.tenant)
        self.assertEqual(self.client.get(f"{V1}/proposals", **officer).status_code, 403)
        self.assertEqual(self.client.get(f"{V1}/proposals/{proposal.id}", **officer).status_code, 403)
        self.assertEqual(self.client.get(f"{V1}/tenant/proposals", **sign_in(self.editor)).status_code, 403)

    # --- costs -------------------------------------------------------------------------
    def test_the_queue_costs_the_same_whatever_it_holds(self) -> None:
        """Playbook 10: the record each row names is looked up for the whole page at once, so
        a queue of three costs what a queue of one costs."""
        self._version_proposal(self.obligation)
        editor = sign_in(self.editor)
        with CaptureQueriesContext(connection) as one:
            self.client.get(f"{V1}/proposals", **editor)
        for number in (2, 3):
            self._version_proposal(self._obligation(f"obl-another-{number}"))
        with CaptureQueriesContext(connection) as three:
            answer = self.client.get(f"{V1}/proposals", **editor)
        self.assertEqual(answer.json()["total"], 3)
        self.assertEqual(len(three.captured_queries), len(one.captured_queries))

    def test_a_banks_own_list_costs_the_same_at_two_page_sizes(self) -> None:
        self.activate(self.tenant)
        self._post_from_tenant()
        officer = sign_in(self.officer, tenant=self.tenant)
        with CaptureQueriesContext(connection) as small:
            self.client.get(f"{V1}/tenant/proposals?limit=1", **officer)
        with CaptureQueriesContext(connection) as large:
            self.client.get(f"{V1}/tenant/proposals?limit=20", **officer)
        self.assertEqual(len(large.captured_queries), len(small.captured_queries))
        self.assertEqual(len(small.captured_queries), TENANT_LIST_QUERIES)



class RejectionReasonValidation(ScenarioTestCase):
    """The reason check itself, against the logic rather than a route."""

    def setUp(self) -> None:
        seed_languages()
        seed_library_vocabularies()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.proposer = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")
        tenancy.clear_tenant()
        self.proposal, _ = logic.create(
            kind="vocabulary_create",
            title="Add the flag Client money",
            payload={"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            proposer=logic.Proposer(actor=factories.user_actor(), user=self.proposer),
        )

    def test_a_live_reason_row_is_accepted_and_an_unknown_one_is_not(self) -> None:
        with self.assertRaises(ValidationError) as unknown:
            logic.reject(
                proposal=self.proposal,
                reviewer=self.editor,
                actor=factories.user_actor(),
                rejection_code="not_a_reason",
                note="No.",
            )
        self.assertEqual(unknown.exception.code, "reason_required")
        rejected = logic.reject(
            proposal=self.proposal,
            reviewer=self.editor,
            actor=factories.user_actor(),
            rejection_code="poor_wording",
            note="The label needs tightening before this can be used.",
        )
        self.assertEqual((rejected.status, rejected.rejection_code), (ProposalStatus.REJECTED.value, "poor_wording"))
