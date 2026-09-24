"""Machine-confirmed provenance on library lists and taxonomy terms (INV-05, PRO-02, VOC-07,
AUD-02, D-62, D-79).

A list row or a term records who confirmed the approval that wrote its wording, the same
three facts an obligation version records: `verified_origin`, the confirming agent, and the
proposal, through which the proposing agent is read. A row is relabelled in place, where a
version never is, so each label also carries its own mark: every label an independent
agent's approval writes, the original included, is stored machine-made, and a person's
approval clears the mark only on the labels it writes. The row keeps naming the agents until
a person has confirmed every piece of wording they made, so nothing an agent confirmed ever
reads as a person's check ("AI output is labelled until a person confirms it"; D-62's "never
reads as verified by a person"). An approval that writes no wording leaves the row's stamp
exactly as it was.

Both halves run through the real routes, since Alex lifted D-79's interim refusal on
2026-09-23: an independent agent's key approves through the route a person calls, with the
model call behind its decision in an open run of its own (D-80). The reads are the routes
every surface calls.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.agents import testing as agents_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import logic
from apps.proposals.models import Proposal
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import Flag, FlagLabel, InstrumentLevel, TaxonomyTerm, TaxonomyTermLabel
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
FLAG: dict[str, Any] = {"list": "flag", "key": "client_money", "labels": {"en": "Client money", "sv": "Kundmedel"}}
TERM: dict[str, Any] = {"dimension": "regime", "key": "crypto_assets", "labels": {"en": "Crypto-assets", "sv": "Kryptotillgångar"}}
NOBODY = {"verifiedOrigin": "", "confirmedByAgent": None, "proposedByAgent": None}


class ListAndTermProvenance(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")
        self.proposing = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        self.proposing_run = agents_testing.platform_run(key=self.proposing)
        self.confirming = agents_testing.reviewer_api_key()

    # --- helpers --------------------------------------------------------------------------
    def _agent_proposes(self, kind: str, payload: dict[str, Any]) -> Proposal:
        """A proposal the proposing agent files under its own open run (AGT-01)."""
        agent = self.proposing.agent
        proposal, _ = logic.create(
            kind=kind,
            title=f"{kind} {payload['key']}",
            payload=payload,
            proposer=logic.Proposer(
                actor=Actor(kind=ActorType.AGENT, id=agent.id, label=agent.key), api_key_id=self.proposing.id, agent_id=agent.id
            ),
            agent_run_id=self.proposing_run.id,
        )
        return proposal

    def _agent_confirms(self, proposal: Proposal) -> None:
        """A reviewing key bound to another definition approves through the route a person
        calls (proposals/api.approveProposal): no person and no step-up."""
        approved = self.client.post(
            f"{V1}/proposals/{proposal.id}/approve", data=agents_testing.decision(self.confirming),
            content_type="application/json", HTTP_X_API_KEY=self.confirming.plain_key,
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        tenancy.clear_tenant()

    def _agents_apply(self, kind: str, payload: dict[str, Any]) -> Proposal:
        proposal = self._agent_proposes(kind, payload)
        self._agent_confirms(proposal)
        return proposal

    def _person_proposes(self, kind: str, payload: dict[str, Any]) -> str:
        created = self.client.post(
            f"{V1}/proposals", data={"kind": kind, "title": f"{kind} {payload['key']}", "payload": payload},
            content_type="application/json", **sign_in(self.editor),
        )
        self.assertEqual(created.status_code, 201, created.content)
        proposal_id: str = created.json()["id"]
        return proposal_id

    def _person_approves(self, proposal_id: uuid.UUID | str) -> None:
        approved = self.client.post(
            f"{V1}/proposals/{proposal_id}/approve", data={}, content_type="application/json",
            **sign_in(self.second_editor, step_up=True),
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        tenancy.clear_tenant()

    def _person_applies(self, kind: str, payload: dict[str, Any]) -> str:
        proposal_id = self._person_proposes(kind, payload)
        self._person_approves(proposal_id)
        return proposal_id

    def _read(self, path: str) -> Any:
        response = self.client.get(f"{V1}{path}", **sign_in(self.editor))
        self.assertEqual(response.status_code, 200, response.content)
        tenancy.clear_tenant()
        return response.json()

    def _queries_of(self, path: str) -> int:
        headers = sign_in(self.editor)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(f"{V1}{path}", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        tenancy.clear_tenant()
        return len(queries.captured_queries)

    def _listed(self, key: str) -> dict[str, Any]:
        return dict(next(item for item in self._read("/vocab/flag")["items"] if item["key"] == key))

    def _term_listed(self, key: str) -> dict[str, Any]:
        items = self._read(f"/taxonomy/terms?dimension={TERM['dimension']}")["items"]
        return dict(next(item for item in items if item["key"] == key))

    def _agents(self) -> dict[str, Any]:
        return {
            "verifiedOrigin": "agent",
            "confirmedByAgent": {"id": str(self.confirming.agent.id), "key": self.confirming.agent.key},
            "proposedByAgent": {"id": str(self.proposing.agent.id), "key": self.proposing.agent.key},
        }

    def _a_person_confirmed_the_agents_proposal(self) -> dict[str, Any]:
        return {"verifiedOrigin": "user", "confirmedByAgent": None, "proposedByAgent": self._agents()["proposedByAgent"]}

    @staticmethod
    def _provenance(item: dict[str, Any]) -> dict[str, Any]:
        return {name: item[name] for name in ("verifiedOrigin", "confirmedByAgent", "proposedByAgent")}

    @staticmethod
    def _stamp(row: Any) -> tuple[str, Any, Any]:
        row.refresh_from_db()
        return (row.verified_origin, row.verified_by_agent_id, row.applied_by_proposal_id)

    @staticmethod
    def _labels(model: Any, **owner: Any) -> dict[str, tuple[str, bool, bool]]:
        return {label.language: (label.text, label.is_original, label.is_machine) for label in model.objects.filter(**owner)}

    # --- vocabulary rows --------------------------------------------------------------------
    def test_a_row_an_agent_confirmed_names_both_agents_and_every_label_it_wrote_is_machine_made(self) -> None:
        proposal = self._agents_apply("vocabulary_create", FLAG)

        row = Flag.objects.get(key=FLAG["key"])
        self.assertEqual(self._stamp(row), ("agent", self.confirming.agent.id, proposal.id))
        # No person saw any of it, the original included: each label says so on its own, so
        # a later partial relabel by a person can never make the rest read as theirs.
        self.assertEqual(
            self._labels(FlagLabel, vocabulary=row),
            {"en": ("Client money", True, True), "sv": ("Kundmedel", False, True)},
        )

        detail = self._read(f"/vocab/flag/{FLAG['key']}")
        self.assertEqual(self._provenance(detail), self._agents())
        self.assertEqual((detail["originalLanguage"], detail["machineLanguages"]), ("en", ["en", "sv"]))
        self.assertEqual(self._provenance(self._listed(FLAG["key"])), self._agents())

    def test_a_persons_partial_relabel_leaves_the_agents_named_until_a_person_confirmed_every_label(self) -> None:
        created = self._person_applies("vocabulary_create", FLAG)
        row = Flag.objects.get(key=FLAG["key"])
        self.assertEqual(self._stamp(row), ("user", None, uuid.UUID(created)))
        self.assertEqual(self._labels(FlagLabel, vocabulary=row)["sv"], ("Kundmedel", False, False))

        # The agent rewords the original and the person's Swedish label and adds a Finnish
        # one: all three are machine-made now, and the row names the agents.
        self._agents_apply(
            "vocabulary_relabel",
            {"list": "flag", "key": FLAG["key"], "labels": {"en": "Client monies", "sv": "Klientmedel", "fi": "Asiakasvarat"}},
        )
        self.assertEqual(
            self._labels(FlagLabel, vocabulary=row),
            {"en": ("Client monies", True, True), "sv": ("Klientmedel", False, True), "fi": ("Asiakasvarat", False, True)},
        )
        # An agent never clears the mark: a second agent relabel keeps it.
        again = self._agents_apply("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "labels": {"sv": "Kundmedel"}})
        self.assertEqual(self._stamp(row), ("agent", self.confirming.agent.id, again.id))
        self.assertEqual(self._labels(FlagLabel, vocabulary=row)["sv"], ("Kundmedel", False, True))

        # A person confirms the Swedish label only. That label is the person's now, but the
        # original and the Finnish label are still the agents' wording: the row keeps naming
        # them, and the stamp still points at the agents' approval.
        swedish = self._agent_proposes("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "labels": {"sv": "Klientmedel"}})
        self._person_approves(swedish.id)
        self.assertEqual(self._stamp(row), ("agent", self.confirming.agent.id, again.id))
        self.assertEqual(self._labels(FlagLabel, vocabulary=row)["sv"], ("Klientmedel", False, False))
        detail = self._read(f"/vocab/flag/{FLAG['key']}")
        self.assertEqual(self._provenance(detail), self._agents())
        self.assertEqual(detail["machineLanguages"], ["en", "fi"])

        # Once a person has confirmed every label an agent made, the row is the person's.
        rest = self._person_applies("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "labels": {"en": "Client monies", "fi": "Asiakasvarat"}})
        self.assertEqual(self._stamp(row), ("user", None, uuid.UUID(rest)))
        detail = self._read(f"/vocab/flag/{FLAG['key']}")
        self.assertEqual(self._provenance(detail), {"verifiedOrigin": "user", "confirmedByAgent": None, "proposedByAgent": None})
        self.assertEqual(detail["machineLanguages"], [])

    def test_a_usage_note_an_agent_confirmed_keeps_the_agents_named_until_a_person_rewrites_it(self) -> None:
        create = self._agents_apply("vocabulary_create", {**FLAG, "usageNote": "Money a firm holds for its clients."})
        row = Flag.objects.get(key=FLAG["key"])

        # Every label is the person's now, but the usage note is still the agents' wording.
        self._person_applies("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "labels": {"en": "Client money", "sv": "Kundmedel"}})
        self.assertEqual(self._stamp(row), ("agent", self.confirming.agent.id, create.id))
        self.assertEqual(self._labels(FlagLabel, vocabulary=row), {"en": ("Client money", True, False), "sv": ("Kundmedel", False, False)})

        # The person rewrites the usage note an agent proposed: nothing the agents confirmed
        # is left, and the row names the proposing agent beside the person's approval.
        note = self._agent_proposes("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "usageNote": "Money held for clients."})
        self._person_approves(note.id)
        self.assertEqual(self._stamp(row), ("user", None, note.id))
        self.assertEqual(self._provenance(self._listed(FLAG["key"])), self._a_person_confirmed_the_agents_proposal())

    def test_an_approval_that_writes_no_wording_leaves_the_provenance_as_it_was(self) -> None:
        create = self._agents_apply("vocabulary_create", FLAG)
        into = {"list": "flag", "key": "client_assets", "labels": {"en": "Client assets"}}
        into_created = uuid.UUID(self._person_applies("vocabulary_create", into))
        agents_stamp = ("agent", self.confirming.agent.id, create.id)
        row, target = Flag.objects.get(key=FLAG["key"]), Flag.objects.get(key=into["key"])

        # A person moving the agents' row, and an agent moving the person's: a sort order is
        # no wording, so neither changes who confirmed the words the row carries.
        self._person_applies("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "sortOrder": 90})
        self.assertEqual(self._stamp(row), agents_stamp)
        self._agents_apply("vocabulary_relabel", {"list": "flag", "key": into["key"], "sortOrder": 91})
        self.assertEqual(self._stamp(target), ("user", None, into_created))
        self.assertEqual(target.sort_order, 91)

        for kind in ("vocabulary_retire", "vocabulary_restore"):
            with self.subTest(kind=kind):
                self._person_applies(kind, {"list": "flag", "key": FLAG["key"]})
                self.assertEqual(self._stamp(row), agents_stamp)
        self._person_applies("vocabulary_merge", {"list": "flag", "key": FLAG["key"], "into": into["key"]})
        self.assertEqual(self._stamp(row), agents_stamp)
        self.assertFalse(row.active)
        self.assertEqual(self._stamp(target), ("user", None, into_created))

    def test_a_column_an_agent_changed_names_the_agents_and_its_audit_row_holds_the_values(self) -> None:
        """A list row's own columns (`extra`: a level's binding default and rank, a
        dimension's footprint rule) are facts the rules read, not a sort order, so an
        approval that changes one stamps the row as a wording change does, and the audit row
        holds the values before and after (INV-05, D-62, AUD-01)."""
        level = InstrumentLevel.objects.get(key="eu_guidance")
        before = level.rank
        proposal = self._agents_apply("vocabulary_relabel", {"list": "instrument_level", "key": "eu_guidance", "extra": {"rank": before + 7}})
        self.assertEqual(self._stamp(level), ("agent", self.confirming.agent.id, proposal.id))
        self.assertEqual(level.rank, before + 7)
        event = AuditEvent.objects.get(action="vocabulary.updated", subject_id=level.id)
        self.assertEqual(event.before["extra"], {"rank": before})
        self.assertEqual(event.after["extra"], {"rank": before + 7})

    def test_a_seeded_row_and_a_banks_own_list_carry_no_confirmation(self) -> None:
        seeded = self._read("/vocab/flag")["items"]
        self.assertTrue(seeded)
        for item in seeded:
            self.assertEqual(self._provenance(item), NOBODY)
        # The jurisdiction list is a library list with no provenance columns at all, since
        # nothing proposes it (D-38): it reads as a seeded row does rather than failing.
        jurisdictions = self._read("/vocab/jurisdiction")["items"]
        self.assertTrue(jurisdictions)
        for item in jurisdictions:
            self.assertEqual(self._provenance(item), NOBODY)

        tenant = factories.tenant()
        member = factories.member_user(tenant, roles=("reader",))
        own = self.client.get(f"{V1}/vocab/compliance_status", **sign_in(member, tenant=tenant))
        self.assertEqual(own.status_code, 200, own.content)
        self.assertTrue(own.json()["items"])
        for item in own.json()["items"]:
            self.assertEqual(self._provenance(item), NOBODY)

    # --- taxonomy terms ---------------------------------------------------------------------
    def test_a_term_the_agents_created_and_updated_stays_theirs_until_a_person_confirmed_all_of_it(self) -> None:
        create = self._agents_apply("term_create", TERM)
        term = TaxonomyTerm.objects.get(dimension__key=TERM["dimension"], key=TERM["key"])
        self.assertEqual(self._stamp(term), ("agent", self.confirming.agent.id, create.id))
        self.assertEqual(
            self._labels(TaxonomyTermLabel, term=term),
            {"en": ("Crypto-assets", True, True), "sv": ("Kryptotillgångar", False, True)},
        )

        update = self._agents_apply(
            "term_update", {"dimension": TERM["dimension"], "key": TERM["key"], "labels": {"en": "Crypto-assets (MiCA)", "da": "Kryptoaktiver"}}
        )
        self.assertEqual(self._stamp(term), ("agent", self.confirming.agent.id, update.id))
        self.assertEqual(
            self._labels(TaxonomyTermLabel, term=term),
            {"en": ("Crypto-assets (MiCA)", True, True), "sv": ("Kryptotillgångar", False, True), "da": ("Kryptoaktiver", False, True)},
        )
        self.assertEqual(self._provenance(self._term_listed(TERM["key"])), self._agents())

        # A person confirms the Swedish label and moves the term: the rest is still the
        # agents' wording, so the term keeps naming them.
        self._person_applies("term_update", {"dimension": TERM["dimension"], "key": TERM["key"], "labels": {"sv": "Kryptotillgångar"}, "sortOrder": 90})
        self.assertEqual(self._stamp(term), ("agent", self.confirming.agent.id, update.id))
        self.assertEqual(self._labels(TaxonomyTermLabel, term=term)["sv"], ("Kryptotillgångar", False, False))
        self.assertEqual(self._provenance(self._term_listed(TERM["key"])), self._agents())

    def test_a_term_a_person_approved_says_a_person_confirmed_it(self) -> None:
        self._person_applies("term_create", TERM)
        term = TaxonomyTerm.objects.get(dimension__key=TERM["dimension"], key=TERM["key"])
        self.assertEqual(self._stamp(term)[:2], ("user", None))
        self.assertEqual(self._labels(TaxonomyTermLabel, term=term)["sv"], ("Kryptotillgångar", False, False))

        update = self._agent_proposes("term_update", {"dimension": TERM["dimension"], "key": TERM["key"], "labels": {"sv": "Kryptotillgångar (MiCA)"}})
        self._person_approves(update.id)
        self.assertEqual(self._stamp(term), ("user", None, update.id))
        self.assertEqual(self._labels(TaxonomyTermLabel, term=term)["sv"], ("Kryptotillgångar (MiCA)", False, False))
        self.assertEqual(self._provenance(self._term_listed(TERM["key"])), self._a_person_confirmed_the_agents_proposal())

        # An agent that only moves the term writes no wording: it stays the person's.
        self._agents_apply("term_update", {"dimension": TERM["dimension"], "key": TERM["key"], "sortOrder": 90})
        self.assertEqual(self._stamp(term), ("user", None, update.id))

    # --- what every bank reads ----------------------------------------------------------------
    def test_a_proposal_made_in_a_bank_names_no_proposing_agent(self) -> None:
        """PRO-03: the queue withholds who proposed on a bank's behalf, and so does every
        read of what that proposal wrote. A key bound to an agent is the platform's in R1;
        R2's bank agents are the case this pins."""
        for kind, payload in (("vocabulary_create", FLAG), ("term_create", TERM)):
            proposal = self._agent_proposes(kind, payload)
            Proposal.objects.filter(pk=proposal.pk).update(proposed_in_tenant=True)
            proposal.refresh_from_db()
            self._agent_confirms(proposal)
        withheld = {**self._agents(), "proposedByAgent": None}
        self.assertEqual(self._provenance(self._read(f"/vocab/flag/{FLAG['key']}")), withheld)
        self.assertEqual(self._provenance(self._listed(FLAG["key"])), withheld)
        self.assertEqual(self._provenance(self._term_listed(TERM["key"])), withheld)

    def test_naming_the_agents_costs_no_query_per_row(self) -> None:
        pages = ("/vocab/flag", f"/taxonomy/terms?dimension={TERM['dimension']}")
        self._agents_apply("vocabulary_create", FLAG)
        self._agents_apply("term_create", TERM)
        before = [self._queries_of(page) for page in pages]
        self._agents_apply("vocabulary_create", {"list": "flag", "key": "client_assets", "labels": {"en": "Client assets"}})
        self._agents_apply("term_create", {"dimension": TERM["dimension"], "key": "stablecoins", "labels": {"en": "Stablecoins"}})
        self.assertEqual([self._queries_of(page) for page in pages], before)
