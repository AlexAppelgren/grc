"""The kinds that bring a new record into the library: `new_instrument` and `new_obligation`
(PRO-01, PRO-02, INV-01, INV-03, INV-05, INV-08, D-39, D-62).

Each kind's payload is named and checked when the proposal is made and again over a
reviewer's correction, with an https link as the source of every fact it sets. Approval
writes the record (and a new obligation's first version) with its audit row and the search
re-index in one transaction. An instrument's regime is a term of the regime dimension, or
422 `not_a_regime` at every door: creation, correction and apply.

Provenance is proven through `apply.apply` for an agent reviewer, because an agent's
`approve()` of these kinds still waits for a person (D-79) until the vocabulary and term
provenance lands; the record must say an agent confirmed it the moment one may.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError

from apps.agents import testing as agents_testing
from apps.library import testing as library_build
from apps.library.models import Instrument, InstrumentTitle, Obligation, ObligationTerm, ObligationVersion
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import apply, logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.proposals.schemas import ProposalObligationPayload
from apps.search.models import SearchChunk
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
SOURCE = "https://www.fi.se/sv/vara-register/forfattningssamling/fffs-2026-9/"
INSTRUMENT_KEY = "fffs-2026-9"
OBLIGATION_KEY = "obl-fffs-2026-9-outsourcing-register"
# A second new duty under the same instrument, outside a bank that only advises.
EXECUTION_DUTY = "obl-fffs-2026-9-execution"
# The shared instrument a new obligation is broken out of; a scenario builds it with the
# library's own test builder.
PARENT_KEY = "fffs-2017-2-kinds"


def instrument_body(**payload: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper overriding payload fields
    """A new instrument, every fact sourced, as an agent files it. `payload` overrides fields."""
    fields: dict[str, Any] = {
        "key": INSTRUMENT_KEY,
        "titles": {
            "sv": "Finansinspektionens föreskrifter om utkontraktering",
            "en": "The Swedish FSA's regulations on outsourcing",
        },
        "originalLanguage": "sv",
        "isMachine": True,
        "shortName": "FFFS 2026:9",
        "officialRef": "FFFS 2026:9",
        "level": "authority_regulation",
        "jurisdiction": "se",
        "authority": "fi",
        "regime": "regime:securities",
        "inForceFrom": "2027-01-01",
        **payload,
    }
    return {
        "kind": "new_instrument",
        "title": "New instrument: FFFS 2026:9 on outsourcing",
        "payload": fields,
        "fieldSources": {field: SOURCE for field in _facts(fields)},
        "sourceLabel": "Finansinspektionen, FFFS 2026:9",
        "sourceUrl": SOURCE,
    }


def obligation_body(instrument: str = PARENT_KEY, **payload: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper overriding payload fields
    """A new obligation under `instrument`, every fact sourced. `payload` overrides fields."""
    fields: dict[str, Any] = {
        "key": OBLIGATION_KEY,
        "instrument": instrument,
        "titles": {"sv": "Förteckning över utkontrakterade funktioner", "en": "Keep a register of outsourced functions"},
        "summaries": {
            "sv": "Institutet för en förteckning över alla utkontrakterade funktioner.",
            "en": "The institution keeps a register of every outsourced function.",
        },
        "originalLanguage": "sv",
        "isMachine": True,
        "refLabel": "4 kap. 2 §",
        "dutyType": "conduct",
        "effectiveFrom": "2027-01-01",
        "terms": ["legal_entity:bank"],
        **payload,
    }
    return {
        "kind": "new_obligation",
        "title": "New obligation: keep a register of outsourced functions",
        "payload": fields,
        "fieldSources": {field: SOURCE for field in _facts(fields)},
        "sourceLabel": "Finansinspektionen, FFFS 2026:9, 4 kap. 2 §",
        "sourceUrl": SOURCE,
    }


def _facts(fields: dict[str, Any]) -> list[str]:
    """The fields a source is owed for, spelled out here rather than read from the code
    under test, so the test states the rule instead of echoing it."""
    unsourced = {"key", "originalLanguage", "isMachine", "effectiveFromPrecision", "inForceFromPrecision", "inForceToPrecision"}
    facts: list[str] = []
    for name, value in fields.items():
        if name in unsourced:
            continue
        facts += [f"{name}.{language}" for language in value] if isinstance(value, dict) else [name]
    return facts


class KindsTestCase(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        seed_authorities()
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")
        self.proposer = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        self.agent_run = agents_testing.platform_run(key=self.proposer)
        self.parent = library_build.instrument(key=PARENT_KEY, short_name="FFFS 2017:2", regime="regime:securities")

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _file(self, body: dict[str, Any]) -> Any:
        """File `body` as the proposing agent, under its open run."""
        return self._post("/proposals", {**body, "agentRunId": str(self.agent_run.id), "model": "agent pipeline 0.4"}, {"HTTP_X_API_KEY": self.proposer.plain_key})

    def _filed(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self._file(body)
        self.assertEqual(response.status_code, 201, response.content)
        row: dict[str, Any] = response.json()
        return row

    def _approve(self, proposal_id: str, body: dict[str, Any] | None = None) -> Any:
        return self._post(f"/proposals/{proposal_id}/approve", body or {}, sign_in(self.reviewer, step_up=True))

    def _refused(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)

    def _stored(self, body: dict[str, Any]) -> Proposal:
        """A proposal stored as it arrived before a rule existed, bypassing the creation
        check, so the apply's own check is what answers."""
        return Proposal.objects.create(
            kind=body["kind"],
            title=body["title"],
            payload=body["payload"],
            field_sources=body["fieldSources"],
            source_url=body["sourceUrl"],
            source_label=body["sourceLabel"],
            origin="agent",
            proposed_by_api_key_id=self.proposer.id,
            proposed_by_agent=self.proposer.agent,
            agent_run_id=self.agent_run.id,
        )

    def _agent_reviewer(self) -> logic.Reviewer:
        confirmer = agents_testing.reviewer_api_key()
        actor = Actor(kind=ActorType.AGENT, id=confirmer.agent.id, label=confirmer.agent.key)
        return logic.Reviewer(actor=actor, api_key_id=confirmer.id, agent_id=confirmer.agent.id, api_key_prefix=confirmer.row.key_prefix)


class NewInstrument(KindsTestCase):
    def test_a_person_approves_and_the_instrument_names_both_sides(self) -> None:
        proposal = self._filed(instrument_body())
        self.assertEqual(proposal["kind"], "new_instrument")
        self.assertIsNone(proposal["targetId"])
        self.assertFalse(Instrument.objects.filter(stable_key=INSTRUMENT_KEY).exists(), "nothing changes until approval")
        # The reviewer opens it with the source of every fact beside it.
        detail = self.client.get(f"{V1}/proposals/{proposal['id']}", **sign_in(self.reviewer))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual({source["field"]: source["url"] for source in detail.json()["sources"]}, instrument_body()["fieldSources"])

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        instrument = Instrument.objects.get(stable_key=INSTRUMENT_KEY)
        self.assertEqual(
            (instrument.short_name, instrument.official_ref, instrument.level.key, instrument.jurisdiction.key, instrument.authority and instrument.authority.key),
            ("FFFS 2026:9", "FFFS 2026:9", "authority_regulation", "se", "fi"),
        )
        # `binding` was left out, so the level's default decides it.
        self.assertEqual(instrument.binding, instrument.level.binding_default)
        self.assertEqual(f"{instrument.regime.dimension.key}:{instrument.regime.key}", "regime:securities")
        self.assertEqual((instrument.in_force_from, instrument.in_force_from_precision), (datetime.date(2027, 1, 1), "day"))
        self.assertEqual(instrument.source_url, SOURCE)
        # Who proposed it: an agent, under the run that found it. Who confirmed it: a person.
        self.assertEqual((instrument.created_origin, instrument.created_by_agent_run), ("agent", self.agent_run.id))
        self.assertEqual((instrument.verified_origin, instrument.verified_by_agent_id), ("user", None))
        titles = {row.language_id: (row.is_original, row.is_machine) for row in InstrumentTitle.objects.filter(instrument=instrument)}
        self.assertEqual(titles, {"sv": (True, False), "en": (False, True)})
        # One transaction: the record's audit row carries the reviewer's passkey assertion.
        event = AuditEvent.objects.get(action="instrument.created", subject_id=instrument.id)
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.after["proposal"], proposal["id"])

    def test_an_agent_reviewer_stamps_machine_confirmed(self) -> None:
        proposal = Proposal.objects.get(pk=self._filed(instrument_body())["id"])
        reviewer = self._agent_reviewer()

        apply.apply(proposal, actor=reviewer.actor, reviewer=reviewer, step_up=None)

        instrument = Instrument.objects.get(stable_key=INSTRUMENT_KEY)
        self.assertEqual((instrument.verified_origin, instrument.verified_by_agent_id), ("agent", reviewer.agent_id))
        self.assertIsNone(instrument.verified_by_id, "no person is named as its verifier")
        self.assertEqual((instrument.created_origin, instrument.created_by_agent_run), ("agent", self.agent_run.id))

    def test_a_regime_from_another_dimension_is_refused_at_every_door(self) -> None:
        # At creation: nothing is stored.
        self._refused(self._file(instrument_body(regime="service_type:advice")), 422, "not_a_regime")
        self.assertFalse(Proposal.objects.filter(kind="new_instrument").exists())
        # Over a reviewer's correction: nothing is written and the proposal waits.
        proposal = self._filed(instrument_body())
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"regime": "service_type:advice"}}), 422, "not_a_regime")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(Instrument.objects.filter(stable_key=INSTRUMENT_KEY).exists())
        # At apply, for a proposal stored before the rule.
        stored = self._stored(instrument_body(key="fffs-2026-10", regime="service_type:advice"))
        self._refused(self._approve(str(stored.id)), 422, "not_a_regime")
        self.assertFalse(Instrument.objects.filter(stable_key="fffs-2026-10").exists())
        self.assertFalse(AuditEvent.objects.filter(action="instrument.created").exists())

    def test_the_payload_is_checked_when_it_is_made(self) -> None:
        for case, body, status, code in (
            ("unknown level", instrument_body(level="edict"), 422, "unknown_key"),
            ("unknown authority", instrument_body(authority="nobody"), 422, "unknown_key"),
            ("unknown regime", instrument_body(regime="regime:alchemy"), 422, "unknown_key"),
            ("key taken", instrument_body(key=PARENT_KEY), 409, "duplicate_key"),
            ("not a stable key", instrument_body(key="FFFS 2026:9"), 422, "validation_error"),
            ("original not among the titles", instrument_body(originalLanguage="da"), 422, "validation_error"),
            ("ends before it starts", instrument_body(inForceTo="2026-01-01"), 422, "validation_error"),
            ("an unknown field", instrument_body(tone="negative"), 422, "validation_error"),
        ):
            with self.subTest(case=case):
                self._refused(self._file(body), status, code)
        self.assertFalse(Proposal.objects.exists())

    def test_every_fact_carries_a_link_and_no_target_is_named(self) -> None:
        body = instrument_body()
        without = {**body, "fieldSources": {f: u for f, u in body["fieldSources"].items() if f != "regime"}}
        self._refused(self._file(without), 422, "source_missing")
        # A provision's key is a source for a change to a record that exists, never for a
        # record that does not.
        provision = library_build.provision(self.parent, key="fffs-2017-2-9-kap")
        self._refused(self._file({**body, "fieldSources": {**body["fieldSources"], "regime": provision.stable_key}}), 422, "validation_error")
        self._refused(self._file({**body, "sourceUrl": ""}), 422, "source_missing")
        self._refused(self._file({**body, "targetType": "instrument", "targetId": str(self.parent.id)}), 422, "validation_error")
        self.assertFalse(Proposal.objects.exists())

    def test_a_key_taken_while_it_waited_is_refused_at_apply(self) -> None:
        first = self._filed(instrument_body())
        second = self._filed({**instrument_body(), "title": "The same instrument, found twice"})
        self.assertEqual(self._approve(first["id"]).status_code, 200)
        self._refused(self._approve(second["id"]), 409, "duplicate_key")
        self.assertEqual(Proposal.objects.get(pk=second["id"]).status, ProposalStatus.OPEN.value)


class NewObligation(KindsTestCase):
    def test_a_person_approves_and_the_obligation_arrives_with_its_first_version(self) -> None:
        proposal = self._filed(obligation_body())

        approved = self._approve(proposal["id"], {"note": "Matches the regulation."})

        self.assertEqual(approved.status_code, 200, approved.content)
        obligation = Obligation.objects.get(stable_key=OBLIGATION_KEY)
        self.assertEqual((obligation.instrument_id, obligation.ref_label, obligation.duty_type.key), (self.parent.id, "4 kap. 2 §", "conduct"))
        self.assertEqual((obligation.source_url, obligation.source_label), (SOURCE, "Finansinspektionen, FFFS 2026:9, 4 kap. 2 §"))
        self.assertEqual((obligation.created_origin, obligation.created_by_agent_run, obligation.created_model), ("agent", self.agent_run.id, "agent pipeline 0.4"))
        self.assertEqual((obligation.verified_origin, obligation.verified_by_agent_id), ("user", None))
        self.assertEqual({row.language_id: row.is_original for row in obligation.titles.all()}, {"sv": True, "en": False})
        self.assertEqual([f"{link.term.dimension.key}:{link.term.key}" for link in ObligationTerm.objects.filter(obligation=obligation)], ["legal_entity:bank"])
        # The first version names the proposal that filed it, which names the proposing agent.
        version = ObligationVersion.objects.get(obligation=obligation)
        self.assertEqual((version.version_number, version.effective_from, version.effective_from_precision), (1, datetime.date(2027, 1, 1), "day"))
        self.assertEqual(str(version.applied_by_proposal_id), proposal["id"])
        self.assertEqual(Proposal.objects.get(pk=str(version.applied_by_proposal_id)).proposed_by_agent_id, self.proposer.agent.id)
        self.assertEqual((version.approved_by_id, version.verified_origin, version.verified_by_agent_id), (self.reviewer.id, "user", None))
        self.assertEqual(
            {row.language_id: (row.is_original, row.is_machine) for row in version.summaries.all()},
            {"sv": (True, False), "en": (False, True)},
        )
        # Indexed in the same transaction, and audited with the reviewer's assertion.
        self.assertTrue(SearchChunk.objects.filter(source_id=version.id).exists())
        event = AuditEvent.objects.get(action="obligation.created", subject_id=obligation.id)
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertEqual((event.after["versionNumber"], event.after["proposal"]), (1, proposal["id"]))

    def test_an_agent_reviewer_stamps_the_obligation_and_its_version(self) -> None:
        proposal = Proposal.objects.get(pk=self._filed(obligation_body(isMachine=False))["id"])
        reviewer = self._agent_reviewer()

        apply.apply(proposal, actor=reviewer.actor, reviewer=reviewer, step_up=None)

        obligation = Obligation.objects.get(stable_key=OBLIGATION_KEY)
        version = ObligationVersion.objects.get(obligation=obligation)
        for record in (obligation, version):
            with self.subTest(record=type(record).__name__):
                self.assertEqual((record.verified_origin, record.verified_by_agent_id), ("agent", reviewer.agent_id))
        self.assertIsNone(version.approved_by_id, "no person is named as its verifier")
        self.assertEqual(Proposal.objects.get(pk=str(version.applied_by_proposal_id)).proposed_by_agent_id, self.proposer.agent.id)
        # An agent's approval confirms no translation, whatever the payload claimed.
        self.assertEqual({row.language_id: row.is_machine for row in version.summaries.all()}, {"sv": False, "en": True})

    def test_a_failed_reindex_writes_nothing(self) -> None:
        proposal = self._filed(obligation_body())
        with mock.patch.object(apply, "reindex", side_effect=RuntimeError("index unavailable")):
            failed = self._approve(proposal["id"])
        self.assertEqual(failed.status_code, 500, failed.content)
        self.assertFalse(Obligation.objects.filter(stable_key=OBLIGATION_KEY).exists())
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(action="obligation.created").exists())

    def test_the_payload_is_checked_when_it_is_made(self) -> None:
        retired = library_build.instrument(key="fffs-2014-1", regime="regime:securities")
        with library_write("test"):
            Instrument.objects.filter(pk=retired.pk).update(status="retired")
        for case, body, status, code in (
            ("unknown instrument", obligation_body("fffs-1999-1"), 422, "unknown_key"),
            ("retired instrument", obligation_body("fffs-2014-1"), 422, "unknown_key"),
            ("unknown duty type", obligation_body(dutyType="whim"), 422, "unknown_key"),
            ("unknown term", obligation_body(terms=["legal_entity:dragon"]), 422, "unknown_key"),
            ("a mirrored jurisdiction term", obligation_body(terms=["jurisdiction:se"]), 422, "jurisdiction_term_mirrored"),
            ("original not among the summaries", obligation_body(originalLanguage="fi"), 422, "validation_error"),
            ("not a date precision", obligation_body(effectiveFromPrecision="week"), 422, "unknown_key"),
        ):
            with self.subTest(case=case):
                self._refused(self._file(body), status, code)
        library_build.obligation(self.parent, key=OBLIGATION_KEY)
        self._refused(self._file(obligation_body()), 409, "duplicate_key")
        self.assertFalse(Proposal.objects.exists())

    def test_a_reviewer_corrects_the_wording_and_the_correction_is_sourced(self) -> None:
        proposal = self._filed(obligation_body())
        corrected = "Institutet för en aktuell förteckning över alla utkontrakterade funktioner."
        # A field the kind does not have cannot arrive by correction.
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"retention": "Ten years."}}), 422, "validation_error")

        approved = self._approve(proposal["id"], {"payloadOverrides": {"summaries": {"sv": corrected, "en": "The institution keeps a current register."}}})

        self.assertEqual(approved.status_code, 200, approved.content)
        version = ObligationVersion.objects.get(obligation__stable_key=OBLIGATION_KEY)
        self.assertEqual(version.summaries.get(language_id="sv").text, corrected)
        row = Proposal.objects.get(pk=proposal["id"])
        self.assertEqual(row.payload["summaries"]["sv"], obligation_body()["payload"]["summaries"]["sv"])
        self.assertEqual((row.corrected_payload or {})["summaries"]["sv"], corrected)

    def test_a_correction_adding_an_unsourced_fact_is_refused(self) -> None:
        body = obligation_body()
        del body["payload"]["effectiveFrom"]
        del body["fieldSources"]["effectiveFrom"]
        proposal = self._filed(body)
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"effectiveFrom": "2027-02-01"}}), 422, "source_missing")
        self.assertFalse(Obligation.objects.filter(stable_key=OBLIGATION_KEY).exists())

    def test_the_standards_check_can_reach_the_resolved_rows(self) -> None:
        """What the standards check (a later package) reads: the instrument and the scope
        terms, resolved by the one function creation, correction and apply share."""
        instrument, terms = logic.validated_obligation(ProposalObligationPayload.model_validate(obligation_body()["payload"]))
        self.assertEqual(instrument.id, self.parent.id)
        self.assertEqual([f"{term.dimension.key}:{term.key}" for term in terms], ["legal_entity:bank"])
        with self.assertRaises(ValidationError):
            logic.validated_obligation(ProposalObligationPayload.model_validate(obligation_body(uuid.uuid4().hex)["payload"]))


class NewRecordsInLibraryUpdates(KindsTestCase):
    """A bank reads a new obligation in its library updates as it reads a new version: under
    the record's own title and cut to its footprint (PRO-03, FP-03). A new obligation names
    no target on the proposal, so the duty is found through the first version it wrote."""

    def setUp(self) -> None:
        from apps.taxonomy import footprint_logic
        from apps.taxonomy.models import TaxonomyTerm
        from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

        super().setUp()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.member = factories.member(self.tenant, roles=("reader",)).user
        footprint_logic.seed_terms(
            tenant=self.tenant, actor=Actor.system("test"), terms=[TaxonomyTerm.objects.get(dimension__key="service_type", key="advice")]
        )
        tenancy.clear_tenant()

    def _read(self, query: str = "") -> list[dict[str, Any]]:
        answer = self.client.get(f"{V1}/library-updates{query}", **sign_in(self.member, tenant=self.tenant))
        self.assertEqual(answer.status_code, 200, answer.content)
        return [item for day in answer.json()["days"] for item in day["items"]]

    def test_a_new_obligation_is_titled_by_the_record_and_cut_to_the_footprint(self) -> None:
        inside = self._filed(obligation_body(terms=["service_type:advice"]))
        outside = self._filed(obligation_body(key=EXECUTION_DUTY, terms=["service_type:execution_only"]))
        for proposal in (inside, outside):
            self.assertEqual(self._approve(proposal["id"]).status_code, 200)
            tenancy.clear_tenant()
        advice = Obligation.objects.get(stable_key=OBLIGATION_KEY)

        items = self._read()

        self.assertEqual([item["id"] for item in items], [inside["id"]])
        item = items[0]
        self.assertEqual(item["kind"], "new_obligation")
        self.assertEqual(item["target"]["id"], str(advice.id))
        self.assertIn(item["target"]["title"], obligation_body()["payload"]["titles"].values())
        self.assertEqual((item["versionNumber"], item["vocabularyList"], item["inFootprint"]), (1, None, True))
        # Asked for the rest, the other one comes with the facet that hid it.
        everything = {item["id"]: item for item in self._read("?outsideFootprint=true")}
        self.assertFalse(everything[outside["id"]]["inFootprint"])
        self.assertEqual(everything[outside["id"]]["outsideReason"][0]["dimension"]["key"], "service_type")
