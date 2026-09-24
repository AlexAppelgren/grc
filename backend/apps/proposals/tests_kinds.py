"""The kinds that bring a new record into the library: `new_instrument`, `new_obligation` and
`new_provision`, with `new_provision_version` beside them (PRO-01, PRO-02, INV-01, INV-02,
INV-03, INV-05, INV-08, D-35, D-39, D-62).

Each kind's payload is named and checked when the proposal is made and again over a
reviewer's correction, with an https link as the source of every fact it sets. Approval
writes the record (and a new obligation's first version) with its audit row and the search
re-index in one transaction. An instrument's regime is a term of the regime dimension, or
422 `not_a_regime` at every door: creation, correction and apply.

An independent agent approves a new instrument and a new obligation through the real
route, and the record says an agent confirmed it (D-79). A provision has no column to say so,
so an agent's approval of one waits for a person.

The standards check (INV-08, D-35, D-36) answers at the same three doors: `licensed_text`
for a provision under a standard or a non-link source on a standard's obligation,
`one_conformance_obligation` for a second obligation under one, `standard_term_required`
for a standard's obligation with no standard term or two, and
`standard_term_only_on_standards` for a standard's term on a law's new obligation.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError

from apps.agents import testing as agents_testing
from apps.library import testing as library_build
from apps.library.models import (
    Instrument,
    InstrumentTitle,
    Obligation,
    ObligationTerm,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import apply, logic, standards
from apps.proposals.models import Proposal, ProposalStatus
from apps.proposals.schemas import ProposalObligationPayload
from apps.search.models import SearchChunk
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.shared.schemas import AgentDecision
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import TaxonomyTerm
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
PROVISION_KEY = "fffs-2017-2-9-kap-6"
# A standard edition, whose text is licensed (INV-08, D-35), and its one standard term.
STANDARD_KEY = "iso-iec-27001-2022"
STANDARD_TERM = "standard:iso_iec_27001"


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


def provision_body(instrument: str = PARENT_KEY, **payload: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper overriding payload fields
    """A new provision of `instrument` with its first text, every fact sourced."""
    fields: dict[str, Any] = {
        "key": PROVISION_KEY,
        "instrument": instrument,
        "provisionKind": "section",
        "refLabel": "9 kap. 6 §",
        "texts": {"sv": "Ett värdepappersinstitut ska inhämta uppgifter om kunden.", "en": "A securities institution shall obtain information about the client."},
        "originalLanguage": "sv",
        "isMachine": True,
        "effectiveFrom": "2027-01-01",
        **payload,
    }
    return {
        "kind": "new_provision",
        "title": "New provision: 9 kap. 6 §",
        "payload": fields,
        "fieldSources": {field: SOURCE for field in _facts(fields)},
        "sourceLabel": "Finansinspektionen, FFFS 2017:2, 9 kap. 6 §",
        "sourceUrl": SOURCE,
    }


def provision_version_body(provision: Provision) -> dict[str, Any]:
    """A new text of `provision`, in force from 1 January 2028, every field sourced."""
    return {
        "kind": "new_provision_version",
        "title": f"New text of {provision.ref_label}",
        "targetType": "provision",
        "targetId": str(provision.id),
        "payload": {"texts": {"sv": "Institutet ska inhämta uppgifter om kundens mål."}, "originalLanguage": "sv", "effectiveFrom": "2028-01-01"},
        "fieldSources": {"texts.sv": SOURCE, "effectiveFrom": SOURCE},
        "sourceLabel": "Finansinspektionen, FFFS 2027:1",
        "sourceUrl": SOURCE,
    }


def _facts(fields: dict[str, Any]) -> list[str]:
    """The fields a source is owed for, spelled out here rather than read from the code
    under test, so the test states the rule instead of echoing it."""
    unsourced = {"key", "originalLanguage", "isMachine", "effectiveFromPrecision", "inForceFromPrecision", "inForceToPrecision", "sortOrder"}
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

    def _approve_as_agent(self, proposal_id: str) -> tuple[Any, Any]:
        """Approve as an independent agent through the real route: a key of another
        definition than the proposer's, with the model call behind its decision and an open
        run of its own (D-62, D-80). Returns the response and the confirming key."""
        confirmer = agents_testing.reviewer_api_key()
        tenancy.clear_tenant()
        response = self._post(f"/proposals/{proposal_id}/approve", agents_testing.decision(confirmer), {"HTTP_X_API_KEY": confirmer.plain_key})
        return response, confirmer

    def _agent_reviewer(self, confirmer: Any = None) -> logic.Reviewer:
        confirmer = confirmer or agents_testing.reviewer_api_key()
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
        approved, confirmer = self._approve_as_agent(self._filed(instrument_body())["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        instrument = Instrument.objects.get(stable_key=INSTRUMENT_KEY)
        self.assertEqual((instrument.verified_origin, instrument.verified_by_agent_id), ("agent", confirmer.agent.id))
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
        approved, confirmer = self._approve_as_agent(self._filed(obligation_body(isMachine=False))["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        obligation = Obligation.objects.get(stable_key=OBLIGATION_KEY)
        version = ObligationVersion.objects.get(obligation=obligation)
        for record in (obligation, version):
            with self.subTest(record=type(record).__name__):
                self.assertEqual((record.verified_origin, record.verified_by_agent_id), ("agent", confirmer.agent.id))
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

    def test_a_laws_new_text_is_a_record_of_the_library_and_never_cut(self) -> None:
        """A provision names no duty, so like a new instrument it reaches every bank uncut."""
        provision = library_build.provision(self.parent, key=PROVISION_KEY)
        proposal = self._filed(provision_version_body(provision))
        self.assertEqual(self._approve(proposal["id"]).status_code, 200)
        tenancy.clear_tenant()

        items = {item["id"]: item for item in self._read()}

        item = items[proposal["id"]]
        self.assertEqual((item["kind"], item["target"], item["vocabularyList"], item["inFootprint"]), ("new_provision_version", None, None, True))


class NewProvision(KindsTestCase):
    """A law's verbatim text enters as a node with its first version, and a later text as a
    new version, each with its audit row and its re-index in the approval's transaction
    (INV-02, PRO-02)."""

    def test_a_person_approves_and_the_provision_arrives_with_its_first_text(self) -> None:
        chapter = library_build.provision(self.parent, key="fffs-2017-2-9-kap")
        proposal = self._filed(provision_body(parent=chapter.stable_key, heading="Kundkännedom"))
        self.assertFalse(Provision.objects.filter(stable_key=PROVISION_KEY).exists(), "nothing changes until approval")

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        provision = Provision.objects.get(stable_key=PROVISION_KEY)
        self.assertEqual(
            (provision.instrument_id, provision.parent_id, provision.kind.key, provision.ref_label, provision.heading),
            (self.parent.id, chapter.id, "section", "9 kap. 6 §", "Kundkännedom"),
        )
        self.assertEqual(provision.path, f"{chapter.path} > 9 kap. 6 §")
        version = ProvisionVersion.objects.get(provision=provision)
        self.assertEqual((version.version_number, version.effective_from), (1, datetime.date(2027, 1, 1)))
        self.assertEqual(str(version.applied_by_proposal_id), proposal["id"])
        texts = {row.language_id: (row.is_original, row.is_machine) for row in ProvisionText.objects.filter(version=version)}
        self.assertEqual(texts, {"sv": (True, False), "en": (False, True)})
        self.assertTrue(SearchChunk.objects.filter(source_id=version.id).exists(), "indexed in the same transaction")
        event = AuditEvent.objects.get(action="provision.created", subject_id=provision.id)
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertEqual((event.after["versionNumber"], event.after["proposal"]), (1, proposal["id"]))

    def test_a_new_text_is_a_new_version_and_the_old_one_stays(self) -> None:
        provision = library_build.provision(self.parent, key=PROVISION_KEY, ref_label="9 kap. 6 §")
        first = library_build.provision_version(provision, texts={"sv": "Den tidigare lydelsen."})
        proposal = self._filed(provision_version_body(provision))

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        versions = list(ProvisionVersion.objects.filter(provision=provision).order_by("version_number"))
        self.assertEqual([(row.id, row.version_number) for row in versions][0], (first.id, 1))
        second = versions[1]
        self.assertEqual((second.version_number, second.effective_from, str(second.applied_by_proposal_id)), (2, datetime.date(2028, 1, 1), proposal["id"]))
        self.assertEqual(ProvisionText.objects.get(version=first).text, "Den tidigare lydelsen.")
        self.assertTrue(SearchChunk.objects.filter(source_id=second.id).exists())
        event = AuditEvent.objects.get(action="provision.version_applied", subject_id=provision.id)
        self.assertEqual((event.before["versionNumber"], event.after["versionNumber"]), (1, 2))

    def test_a_failed_reindex_writes_nothing(self) -> None:
        proposal = self._filed(provision_body())
        with mock.patch.object(apply, "reindex_provision", side_effect=RuntimeError("index unavailable")):
            failed = self._approve(proposal["id"])
        self.assertEqual(failed.status_code, 500, failed.content)
        self.assertFalse(Provision.objects.filter(stable_key=PROVISION_KEY).exists())
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(action="provision.created").exists())

    def test_the_payload_is_checked_when_it_is_made(self) -> None:
        other = library_build.instrument(key="fffs-2014-1", regime="regime:securities")
        elsewhere = library_build.provision(other, key="fffs-2014-1-1-kap")
        taken = library_build.provision(self.parent, key="fffs-2017-2-kinds-1-kap")
        for case, body, status, code in (
            ("unknown instrument", provision_body("fffs-1999-1"), 422, "unknown_key"),
            ("a parent of another instrument", provision_body(parent=elsewhere.stable_key), 422, "unknown_key"),
            ("unknown provision kind", provision_body(provisionKind="verse"), 422, "unknown_key"),
            ("key taken", provision_body(key=taken.stable_key), 409, "duplicate_key"),
            ("original not among the texts", provision_body(originalLanguage="fi"), 422, "validation_error"),
            ("a provision key as a source", {**provision_body(), "fieldSources": {**provision_body()["fieldSources"], "refLabel": taken.stable_key}}, 422, "validation_error"),
            ("a target named", {**provision_body(), "targetType": "provision", "targetId": str(taken.id)}, 422, "validation_error"),
        ):
            with self.subTest(case=case):
                self._refused(self._file(body), status, code)
        without_target = {key: value for key, value in provision_version_body(taken).items() if key not in {"targetType", "targetId"}}
        self._refused(self._file(without_target), 422, "validation_error")
        self._refused(self._file({**provision_version_body(taken), "targetId": str(uuid.uuid4())}), 422, "unknown_key")
        self.assertFalse(Proposal.objects.exists())

    def test_an_agent_cannot_approve_a_provision_yet(self) -> None:
        """A provision version has nowhere to say an agent confirmed it, so it is not in
        `AGENT_CONFIRMABLE_KINDS` and waits for a person (INV-05, D-79)."""
        proposal = Proposal.objects.get(pk=self._filed(provision_body())["id"])
        confirmer = agents_testing.reviewer_api_key()
        reviewer = self._agent_reviewer(confirmer)
        # With the model call behind its decision and an open run of its own key (D-80), so
        # the refusal is D-79's and nothing else's.
        decided = agents_testing.decision(confirmer)
        with self.assertRaises(ValidationError) as caught:
            logic.approve(
                proposal=proposal,
                reviewer=reviewer,
                actor=reviewer.actor,
                note="",
                step_up_assertion_id=None,
                decision=AgentDecision.model_validate(decided["decision"]),
                agent_run_id=uuid.UUID(decided["agentRunId"]),
            )
        self.assertEqual(caught.exception.code, "person_review_required")
        self.assertFalse(Provision.objects.filter(stable_key=PROVISION_KEY).exists())


class StandardsCheck(KindsTestCase):
    """The standards rules at creation, over a reviewer's correction and at apply, for the
    kinds that write a standard's records (INV-08, AC-INV2, D-35, D-36)."""

    def setUp(self) -> None:
        super().setUp()
        # The seeds keep the one standard term switched off until its records exist (D-47).
        with library_write("test"):
            TaxonomyTerm.objects.filter(dimension__key="standard", key="iso_iec_27001").update(active=True)
        self.standard = library_build.instrument(
            key=STANDARD_KEY, short_name="ISO/IEC 27001:2022", official_ref="ISO/IEC 27001:2022", regime="regime:ai_ict", level="standard", binding=False
        )

    def _conformance(self, **payload: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper overriding payload fields
        fields = {"key": "obl-iso-iec-27001-2022-conformance", "refLabel": "ISO/IEC 27001:2022", "terms": [STANDARD_TERM], **payload}
        return obligation_body(STANDARD_KEY, **fields)

    def test_a_standards_conformance_obligation_enters_with_its_one_term(self) -> None:
        proposal = self._filed(self._conformance())
        approved = self._approve(proposal["id"])
        self.assertEqual(approved.status_code, 200, approved.content)
        obligation = Obligation.objects.get(instrument=self.standard)
        self.assertEqual([f"{link.term.dimension.key}:{link.term.key}" for link in ObligationTerm.objects.filter(obligation=obligation)], [STANDARD_TERM])

    def test_a_provision_under_a_standard_is_licensed_text_and_nothing_is_stored(self) -> None:
        self._refused(self._file(provision_body(STANDARD_KEY)), 422, "licensed_text")
        self.assertFalse(Proposal.objects.exists())
        # A version of a standard's provision cannot be proposed either. The database holds
        # no such provision (the trigger `provision_not_under_standard`), so the rule is
        # proven on the check itself.
        with self.assertRaises(ValidationError) as caught:
            standards.check("new_provision_version", self.standard, None, {})
        self.assertEqual(caught.exception.code, "licensed_text")

    def test_a_non_link_source_on_a_standards_obligation_is_licensed_text(self) -> None:
        body = self._conformance()
        pasted = "5.1 Leadership and commitment: top management shall demonstrate"
        self._refused(self._file({**body, "fieldSources": {**body["fieldSources"], "summaries.en": pasted}}), 422, "licensed_text")
        self.assertFalse(Proposal.objects.exists())

    def test_a_standards_obligation_is_labelled_by_the_official_reference_alone(self) -> None:
        """D-35: the conformance obligation's `ref_label` equals the standard's official
        reference, so no clause number or control title reaches the library through it."""
        clause = self._conformance(refLabel="A.5.1 Policies for information security")
        self._refused(self._file(clause), 422, "licensed_text")
        self.assertFalse(Proposal.objects.exists())
        stored = self._stored(clause)
        self._refused(self._approve(str(stored.id)), 422, "licensed_text")
        self.assertFalse(Obligation.objects.filter(instrument=self.standard).exists())

    def test_a_second_obligation_under_a_standard_is_refused_at_creation_and_at_apply(self) -> None:
        library_build.obligation(self.standard, key="obl-iso-conformance", terms=[STANDARD_TERM])
        second = self._conformance(key="obl-iso-second")
        self._refused(self._file(second), 422, "one_conformance_obligation")
        self.assertFalse(Proposal.objects.exists())
        stored = self._stored(second)
        self._refused(self._approve(str(stored.id)), 422, "one_conformance_obligation")
        self.assertFalse(Obligation.objects.filter(stable_key="obl-iso-second").exists())
        self.assertFalse(AuditEvent.objects.filter(action="obligation.created").exists())

    def test_a_standards_obligation_carries_exactly_one_standard_term(self) -> None:
        with library_write("test"):
            TaxonomyTerm.objects.create(dimension=library_build.term(STANDARD_TERM).dimension, key="iso_22301", sort_order=2)
        for case, terms in (("none", ["legal_entity:bank"]), ("no scope at all", None), ("two", [STANDARD_TERM, "standard:iso_22301"])):
            body = self._conformance(terms=terms)
            if terms is None:
                del body["payload"]["terms"]
                del body["fieldSources"]["terms"]
            with self.subTest(case=case):
                self._refused(self._file(body), 422, "standard_term_required")
                stored = self._stored(body)
                self._refused(self._approve(str(stored.id)), 422, "standard_term_required")
                self.assertFalse(Obligation.objects.filter(instrument=self.standard).exists())
        # Over a correction: the one term replaced by none.
        proposal = self._filed(self._conformance())
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"terms": ["legal_entity:bank"]}}), 422, "standard_term_required")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).corrected_payload, None)

    def test_a_standards_term_on_a_laws_new_obligation_is_refused_at_every_door(self) -> None:
        with_standard = obligation_body(terms=["legal_entity:bank", STANDARD_TERM])
        self._refused(self._file(with_standard), 422, "standard_term_only_on_standards")
        self.assertFalse(Proposal.objects.exists())
        proposal = self._filed(obligation_body())
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"terms": ["legal_entity:bank", STANDARD_TERM]}}), 422, "standard_term_only_on_standards")
        stored = self._stored({**with_standard, "title": "Filed before the rule"})
        self._refused(self._approve(str(stored.id)), 422, "standard_term_only_on_standards")
        self.assertFalse(Obligation.objects.filter(stable_key=OBLIGATION_KEY).exists())

    def test_a_correction_moving_a_provision_under_a_standard_writes_nothing(self) -> None:
        proposal = self._filed(provision_body())
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"instrument": STANDARD_KEY}}), 422, "licensed_text")
        row = Proposal.objects.get(pk=proposal["id"])
        self.assertEqual((row.status, row.corrected_payload), (ProposalStatus.OPEN.value, None))
        self.assertFalse(Provision.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action__in=("proposal.approved", "provision.created")).exists())
