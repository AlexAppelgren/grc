"""Machine-confirmed provenance on library lists and taxonomy terms (INV-05, PRO-02, VOC-07,
AUD-02, D-62, D-79).

A list row or a term records who confirmed the approval that wrote its current wording, the
same three facts an obligation version records: `verified_origin`, the confirming agent,
and the proposal that wrote it, through which the proposing agent is read. Under a
person's approval the row says `user` and its labels are the person's, exactly as before.
Under an independent agent's approval the row says `agent`, names both agents, and every
translation the agent writes is labelled machine-made, because "AI output is labelled until
a person confirms it" and D-62's "never reads as verified by a person".

An agent still cannot reach this through `approve()`: D-79's refusal (409
`person_review_required`, apps/proposals/tests_decide.py) stands until Alex confirms the
provenance design lifts it. The agent's half is therefore driven through `apply.apply()`
with the `Reviewer` the API's gate would build for a reviewing key, which is exactly what
`approve()` hands it; the person's half runs through the real routes. The reads are the
routes every surface calls.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.agents import testing as agents_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import apply, logic
from apps.proposals.models import Proposal
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import Flag, FlagLabel, TaxonomyTerm, TaxonomyTermLabel
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
FLAG = {"list": "flag", "key": "client_money", "labels": {"en": "Client money", "sv": "Kundmedel"}}
TERM = {"dimension": "regime", "key": "crypto_assets", "labels": {"en": "Crypto-assets", "sv": "Kryptotillgångar"}}


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
        """What `approve()` hands `apply()` for a reviewing key bound to another definition
        (proposals/api.require_reviewer): no person and no step-up."""
        agent = self.confirming.agent
        reviewer = logic.Reviewer(
            actor=Actor(kind=ActorType.AGENT, id=agent.id, label=f"{agent.key} v{agent.current_version}"),
            api_key_id=self.confirming.id,
            agent_id=agent.id,
            api_key_prefix=self.confirming.row.key_prefix,
        )
        apply.apply(proposal, actor=reviewer.actor, reviewer=reviewer, step_up=None)

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

    def _read(self, path: str) -> Any:
        response = self.client.get(f"{V1}{path}", **sign_in(self.editor))
        self.assertEqual(response.status_code, 200, response.content)
        tenancy.clear_tenant()
        return response.json()

    def _agents(self) -> dict[str, Any]:
        return {
            "confirmedByAgent": {"id": str(self.confirming.agent.id), "key": self.confirming.agent.key},
            "proposedByAgent": {"id": str(self.proposing.agent.id), "key": self.proposing.agent.key},
        }

    @staticmethod
    def _provenance(item: dict[str, Any]) -> dict[str, Any]:
        return {name: item[name] for name in ("verifiedOrigin", "confirmedByAgent", "proposedByAgent")}

    @staticmethod
    def _labels(model: Any, **owner: Any) -> dict[str, tuple[str, bool, bool]]:
        return {label.language: (label.text, label.is_original, label.is_machine) for label in model.objects.filter(**owner)}

    # --- vocabulary rows --------------------------------------------------------------------
    def test_a_row_an_agent_confirmed_names_both_agents_and_its_translations_are_machine_made(self) -> None:
        proposal = self._agent_proposes("vocabulary_create", FLAG)
        self._agent_confirms(proposal)

        row = Flag.objects.get(key=FLAG["key"])
        self.assertEqual((row.verified_origin, row.verified_by_agent_id, row.applied_by_proposal_id), ("agent", self.confirming.agent.id, proposal.id))
        # The original is the row's own wording, labelled by the row; the translation the
        # agent wrote is machine-made, whatever the payload says, because no person saw it.
        self.assertEqual(
            self._labels(FlagLabel, vocabulary=row),
            {"en": ("Client money", True, False), "sv": ("Kundmedel", False, True)},
        )

        detail = self._read(f"/vocab/flag/{FLAG['key']}")
        self.assertEqual(self._provenance(detail), {"verifiedOrigin": "agent", **self._agents()})
        self.assertEqual((detail["originalLanguage"], detail["machineLanguages"]), ("en", ["sv"]))
        listed = next(item for item in self._read("/vocab/flag")["items"] if item["key"] == FLAG["key"])
        self.assertEqual(self._provenance(listed), {"verifiedOrigin": "agent", **self._agents()})

    def test_an_agent_relabel_never_clears_the_machine_label_and_a_person_relabel_confirms_it(self) -> None:
        self._person_approves(self._person_proposes("vocabulary_create", FLAG))
        row = Flag.objects.get(key=FLAG["key"])
        self.assertEqual((row.verified_origin, row.verified_by_agent_id), ("user", None))
        self.assertEqual(self._labels(FlagLabel, vocabulary=row)["sv"], ("Kundmedel", False, False))

        # The agent rewrites the person's Swedish label, rewords the original and adds a
        # Finnish one: both translations are machine-made now, the original stays the row's.
        relabel = self._agent_proposes(
            "vocabulary_relabel",
            {"list": "flag", "key": FLAG["key"], "labels": {"en": "Client monies", "sv": "Klientmedel", "fi": "Asiakasvarat"}},
        )
        self._agent_confirms(relabel)
        row.refresh_from_db()
        self.assertEqual((row.verified_origin, row.verified_by_agent_id, row.applied_by_proposal_id), ("agent", self.confirming.agent.id, relabel.id))
        self.assertEqual(
            self._labels(FlagLabel, vocabulary=row),
            {"en": ("Client monies", True, False), "sv": ("Klientmedel", False, True), "fi": ("Asiakasvarat", False, True)},
        )

        # A second agent relabel of a label already machine-made leaves it machine-made.
        again = self._agent_proposes("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "labels": {"sv": "Kundmedel"}})
        self._agent_confirms(again)
        self.assertEqual(self._labels(FlagLabel, vocabulary=row)["sv"], ("Kundmedel", False, True))

        # The agent proposes and a person confirms: the person's approval is what the row
        # says, the label is the person's, and the proposing agent is still named.
        confirmed = self._agent_proposes("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "labels": {"sv": "Klientmedel"}})
        self._person_approves(confirmed.id)
        row.refresh_from_db()
        self.assertEqual((row.verified_origin, row.verified_by_agent_id, row.applied_by_proposal_id), ("user", None, confirmed.id))
        self.assertEqual(self._labels(FlagLabel, vocabulary=row)["sv"], ("Klientmedel", False, False))
        self.assertEqual(self._labels(FlagLabel, vocabulary=row)["fi"], ("Asiakasvarat", False, True))
        detail = self._read(f"/vocab/flag/{FLAG['key']}")
        self.assertEqual(
            self._provenance(detail),
            {"verifiedOrigin": "user", "confirmedByAgent": None, "proposedByAgent": self._agents()["proposedByAgent"]},
        )
        self.assertEqual(detail["machineLanguages"], ["fi"])

    def test_retire_restore_and_merge_write_no_wording_and_leave_the_provenance_as_it_was(self) -> None:
        create = self._agent_proposes("vocabulary_create", FLAG)
        self._agent_confirms(create)
        into = {"list": "flag", "key": "client_assets", "labels": {"en": "Client assets"}}
        self._person_approves(self._person_proposes("vocabulary_create", into))
        stamped = ("agent", self.confirming.agent.id, create.id)

        for kind in ("vocabulary_retire", "vocabulary_restore"):
            with self.subTest(kind=kind):
                self._person_approves(self._person_proposes(kind, {"list": "flag", "key": FLAG["key"]}))
                row = Flag.objects.get(key=FLAG["key"])
                self.assertEqual((row.verified_origin, row.verified_by_agent_id, row.applied_by_proposal_id), stamped)
        self._person_approves(self._person_proposes("vocabulary_merge", {"list": "flag", "key": FLAG["key"], "into": into["key"]}))
        merged = Flag.objects.get(key=FLAG["key"])
        self.assertFalse(merged.active)
        self.assertEqual((merged.verified_origin, merged.verified_by_agent_id, merged.applied_by_proposal_id), stamped)
        target = Flag.objects.get(key=into["key"])
        self.assertEqual((target.verified_origin, target.verified_by_agent_id), ("user", None))

    def test_a_seeded_row_and_a_banks_own_list_carry_no_confirmation(self) -> None:
        seeded = self._read("/vocab/flag")["items"]
        self.assertTrue(seeded)
        for item in seeded:
            self.assertEqual(self._provenance(item), {"verifiedOrigin": "", "confirmedByAgent": None, "proposedByAgent": None})

        tenant = factories.tenant()
        member = factories.member_user(tenant, roles=("reader",))
        own = self.client.get(f"{V1}/vocab/compliance_status", **sign_in(member, tenant=tenant))
        self.assertEqual(own.status_code, 200, own.content)
        self.assertTrue(own.json()["items"])
        for item in own.json()["items"]:
            self.assertEqual(self._provenance(item), {"verifiedOrigin": "", "confirmedByAgent": None, "proposedByAgent": None})

    # --- taxonomy terms ---------------------------------------------------------------------
    def test_a_term_an_agent_created_and_updated_names_both_agents_and_its_translations_are_machine_made(self) -> None:
        create = self._agent_proposes("term_create", TERM)
        self._agent_confirms(create)
        term = TaxonomyTerm.objects.get(dimension__key=TERM["dimension"], key=TERM["key"])
        self.assertEqual((term.verified_origin, term.verified_by_agent_id, term.applied_by_proposal_id), ("agent", self.confirming.agent.id, create.id))
        self.assertEqual(
            self._labels(TaxonomyTermLabel, term=term),
            {"en": ("Crypto-assets", True, False), "sv": ("Kryptotillgångar", False, True)},
        )

        update = self._agent_proposes(
            "term_update", {"dimension": TERM["dimension"], "key": TERM["key"], "labels": {"en": "Crypto-assets (MiCA)", "da": "Kryptoaktiver"}}
        )
        self._agent_confirms(update)
        term.refresh_from_db()
        self.assertEqual((term.verified_origin, term.verified_by_agent_id, term.applied_by_proposal_id), ("agent", self.confirming.agent.id, update.id))
        self.assertEqual(
            self._labels(TaxonomyTermLabel, term=term),
            {"en": ("Crypto-assets (MiCA)", True, False), "sv": ("Kryptotillgångar", False, True), "da": ("Kryptoaktiver", False, True)},
        )

        listed = next(item for item in self._read(f"/taxonomy/terms?dimension={TERM['dimension']}")["items"] if item["key"] == TERM["key"])
        self.assertEqual(self._provenance(listed), {"verifiedOrigin": "agent", **self._agents()})

    def test_a_term_a_person_approved_says_a_person_confirmed_it(self) -> None:
        self._person_approves(self._person_proposes("term_create", TERM))
        term = TaxonomyTerm.objects.get(dimension__key=TERM["dimension"], key=TERM["key"])
        self.assertEqual((term.verified_origin, term.verified_by_agent_id), ("user", None))
        self.assertEqual(self._labels(TaxonomyTermLabel, term=term)["sv"], ("Kryptotillgångar", False, False))

        update = self._agent_proposes("term_update", {"dimension": TERM["dimension"], "key": TERM["key"], "labels": {"sv": "Kryptotillgångar (MiCA)"}})
        self._person_approves(update.id)
        term.refresh_from_db()
        self.assertEqual((term.verified_origin, term.verified_by_agent_id, term.applied_by_proposal_id), ("user", None, update.id))
        self.assertEqual(self._labels(TaxonomyTermLabel, term=term)["sv"], ("Kryptotillgångar (MiCA)", False, False))
        listed = next(item for item in self._read(f"/taxonomy/terms?dimension={TERM['dimension']}")["items"] if item["key"] == TERM["key"])
        self.assertEqual(
            self._provenance(listed),
            {"verifiedOrigin": "user", "confirmedByAgent": None, "proposedByAgent": self._agents()["proposedByAgent"]},
        )
