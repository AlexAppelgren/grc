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

A provision's text is the law's own words (`TheLawsOwnWords`; Alex, 2026-11-13): its
original is the language its jurisdiction writes law in, a second language the authority
itself published is neither the original nor machine-made, and the obligations it names are
tied to it when it is approved, through the proposal door as the app role.

The standards check (INV-08, D-35, D-36) answers at the same three doors: `licensed_text`
for a provision under a standard or a non-link source on a standard's obligation,
`one_conformance_obligation` for a second obligation under one, `standard_term_required`
for a standard's obligation with no standard term or two, and
`standard_term_only_on_standards` for a standard's term on a law's new obligation.
"""

from __future__ import annotations

import datetime
import importlib
import uuid
from typing import Any
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, connection, migrations, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.agents import testing as agents_testing
from apps.governance.models import AiGeneration
from apps.library import testing as library_build
from apps.library.models import (
    Instrument,
    InstrumentSummary,
    InstrumentTitle,
    Obligation,
    ObligationProvision,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import apply, logic, standards
from apps.proposals.models import OriginType, Proposal, ProposalKind, ProposalStatus
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


def summary_body(instrument: str = PARENT_KEY) -> dict[str, Any]:
    """A summary of `instrument` in plain words, sourced (INV-09, D-124)."""
    fields: dict[str, Any] = {
        "instrument": instrument,
        "summaries": {"en": "Finansinspektionen's rules on how a bank outsources functions and keeps a register of them."},
        "originalLanguage": "en",
    }
    return {
        "kind": "new_instrument_summary",
        "title": "Add a summary of the outsourcing rules",
        "payload": fields,
        "fieldSources": {"instrument": SOURCE, "summaries.en": SOURCE},
        "sourceLabel": "Finansinspektionen, FFFS 2017:2",
        "sourceUrl": SOURCE,
    }


def translations_body(target: str = "instrument", key: str = PARENT_KEY, **payload: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper overriding payload fields
    """Machine translations of the record `target` keyed `key`: its English title into Swedish
    and Danish, as the translator files them (D-129). `payload` overrides fields."""
    fields: dict[str, Any] = {
        "target": target,
        "key": key,
        "titles": {"sv": "Finansinspektionens regler om utkontraktering", "da": "Finanstilsynets regler om outsourcing"},
        "titlesFrom": "en",
        **payload,
    }
    return {
        "kind": "new_translations",
        "title": f"Translate {key} into da, sv",
        "payload": fields,
        "fieldSources": {field: SOURCE for field in _facts(fields)},
        "sourceLabel": "FFFS 2017:2",
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
    unsourced = {"key", "originalLanguage", "isMachine", "officialLanguages", "effectiveFromPrecision", "inForceFromPrecision", "inForceToPrecision", "sortOrder"}
    # Which record a translation is for, its version and the languages it was made from.
    unsourced |= {"target", "version", "titlesFrom", "summariesFrom"}
    facts: list[str] = []
    for name, value in fields.items():
        if name in unsourced:
            continue
        facts += [f"{name}.{language}" for language in value] if isinstance(value, dict) else [name]
    return facts


class TheKindTable(SimpleTestCase):
    """Every proposal kind is one row of `logic.KINDS`, and the sets the rules read are
    derived from it (review 2026-11-11 B-9 item 6)."""

    def test_the_kinds_an_agent_may_approve_are_pinned(self) -> None:
        """INV-05, D-62, D-79: only kinds whose applied record can name its confirming agent.
        Widening this set is a decision, and this pin makes it a visible one."""
        self.assertEqual(
            logic.AGENT_CONFIRMABLE_KINDS,
            {
                "vocabulary_create",
                "vocabulary_relabel",
                "vocabulary_retire",
                "vocabulary_restore",
                "vocabulary_merge",
                "term_create",
                "term_update",
                "new_obligation_version",
                "new_instrument",
                "new_obligation",
                "new_recurring_duty",
            },
        )

    def test_every_kind_has_a_row_and_a_new_row_waits_for_a_person(self) -> None:
        # The re-tag batch is the one kind outside the table: `batch.create_batch()` files it.
        self.assertEqual(set(logic.KINDS), {kind.value for kind in ProposalKind} - {ProposalKind.OBLIGATION_SCOPE.value})
        rule = logic.KindRule(ProposalObligationPayload)
        self.assertFalse(rule.agent_confirmable, "a kind added later is approved by a person")
        self.assertFalse(rule.private or rule.new_record or rule.target, "and names nothing it was not given")


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


class NewInstrumentSummary(KindsTestCase):
    """INV-09, D-124: what an instrument is, in plain words, enters the library through the
    proposal door like every fact, is written once, and never under a bank's own record."""

    def test_a_person_approves_and_the_summary_is_written_once(self) -> None:
        proposal = self._filed(summary_body())
        self.assertEqual((proposal["kind"], proposal["targetId"]), ("new_instrument_summary", None))
        self.assertFalse(InstrumentSummary.objects.filter(instrument=self.parent).exists(), "nothing changes until approval")

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        row = InstrumentSummary.objects.get(instrument=self.parent)
        self.assertEqual((row.language_id, row.is_original, row.is_machine), ("en", True, False))
        event = AuditEvent.objects.get(action="instrument.summary_added", subject_id=self.parent.id)
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertIsNone(event.tenant_id)
        # A second summary of the same instrument is refused when filed, and at approval.
        self._refused(self._file(summary_body()), 409, "duplicate_key")
        stored = self._stored(summary_body())
        self._refused(self._approve(str(stored.id)), 409, "duplicate_key")

    def test_an_unknown_instrument_and_an_agent_reviewer_are_refused(self) -> None:
        self._refused(self._file(summary_body(instrument="no-such-act")), 422, "unknown_key")
        proposal = self._filed(summary_body())
        response, _confirmer = self._approve_as_agent(proposal["id"])
        self._refused(response, 409, "person_review_required")


class NewTranslations(KindsTestCase):
    """INV-05, I18N-01, D-129: a record's machine translations enter the library through the
    proposal door, only as rows it lacks, always labelled machine-made, from the original,
    and approved by a person."""

    def _summarised(self) -> None:
        with library_write("test"):
            InstrumentSummary.objects.create(instrument=self.parent, language_id="en", text="The rules on how a bank outsources.", is_original=True)

    def test_a_person_approves_and_every_row_is_a_machine_translation(self) -> None:
        self._summarised()
        body = translations_body(summaries={"sv": "Reglerna om hur en bank utkontrakterar."}, summariesFrom="en")
        proposal = self._filed(body)
        self.assertEqual((proposal["kind"], proposal["targetId"]), ("new_translations", None))
        self.assertFalse(InstrumentTitle.objects.filter(instrument=self.parent, language_id="sv").exists(), "nothing changes until approval")

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        titles = {row.language_id: (row.is_original, row.is_machine) for row in InstrumentTitle.objects.filter(instrument=self.parent)}
        self.assertEqual(titles, {"en": (True, False), "sv": (False, True), "da": (False, True)}, "a person's approval confirms no translation")
        summary = InstrumentSummary.objects.get(instrument=self.parent, language_id="sv")
        self.assertEqual((summary.text, summary.is_original, summary.is_machine), ("Reglerna om hur en bank utkontrakterar.", False, True))
        event = AuditEvent.objects.get(action="instrument.translations_added", subject_id=self.parent.id)
        self.assertEqual((event.after["titles"], event.after["summaries"], event.tenant_id), (["da", "sv"], ["sv"], None))
        self.assertIsNotNone(event.step_up_assertion_id)
        # A language the record holds now is refused when filed, and at approval of one
        # stored before it was added: never a second row, never skipped.
        self._refused(self._file(translations_body()), 409, "duplicate_key")
        self._refused(self._approve(str(self._stored(translations_body()).id)), 409, "duplicate_key")

    def test_what_the_door_refuses(self) -> None:
        self._refused(self._file(translations_body(key="no-such-act")), 422, "unknown_key")
        self._refused(self._file(translations_body(target="provision")), 422, "unknown_key")
        self._refused(self._file(translations_body(titles={"de": "Regeln"})), 422, "unknown_key")
        self._refused(self._file(translations_body(titles={"en": "FFFS 2017:2"})), 409, "duplicate_key")
        self._refused(self._file(translations_body(titlesFrom="sv")), 422, "validation_error")
        self._refused(self._file(translations_body(titles={"sv": " "})), 422, "validation_error")
        self._refused(self._file(translations_body(titles={})), 422, "validation_error")
        self._refused(self._file(translations_body(summaries={"sv": "Reglerna."}, summariesFrom="en")), 422, "validation_error")
        with override_settings(LIBRARY_TRANSLATION_TEXT_MAX_CHARS=10):
            self._refused(self._file(translations_body()), 422, "validation_error")
        own = library_build.instrument(key="own-act", regime="regime:securities", owner_tenant=factories.tenant(slug="own-bank"))
        tenancy.clear_tenant()
        self._refused(self._file(translations_body(key=own.stable_key)), 422, "unknown_key")

    def test_an_agent_never_approves_one(self) -> None:
        proposal = self._filed(translations_body())
        response, _confirmer = self._approve_as_agent(proposal["id"])
        self._refused(response, 409, "person_review_required")

    def test_an_obligation_s_summaries_translate_its_version_in_force(self) -> None:
        duty = library_build.obligation(
            self.parent,
            key="obl-kinds-translated",
            versions=[(None, {"en": "Keep a register."}), (datetime.date(2099, 1, 1), {"en": "Keep a longer register."})],
        )
        body = translations_body(
            target="obligation", key=duty.stable_key, titles={"sv": "Förteckning"}, summaries={"sv": "För en förteckning."}, summariesFrom="en"
        )
        self._refused(self._file({**body, "payload": {**body["payload"], "version": 2}}), 422, "validation_error")
        self._refused(self._file(body), 422, "validation_error")
        proposal = self._filed({**body, "payload": {**body["payload"], "version": 1}})

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        summaries = {(row.version.version_number, row.language_id) for row in ObligationSummary.objects.filter(version__obligation=duty)}
        self.assertEqual(summaries, {(1, "en"), (1, "sv"), (2, "en")}, "the version in force, never the one to come")
        self.assertTrue(ObligationTitle.objects.get(obligation=duty, language_id="sv").is_machine)
        in_force = ObligationVersion.objects.get(obligation=duty, version_number=1)
        self.assertTrue(SearchChunk.objects.filter(source_id=in_force.id, language_id="sv").exists(), "searchable in Swedish once approved")


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

        approved = self._approve(
            proposal["id"],
            {"payloadOverrides": {"summaries": {"sv": corrected, "en": "The institution keeps a current register."}}, "fieldSources": {"summaries.sv": SOURCE, "summaries.en": SOURCE}},
        )

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

    def test_an_agent_cannot_approve_a_provisions_new_text_through_the_route(self) -> None:
        """A provision's new text is the other kind with nowhere to name its confirming
        agent, so an independent agent approving it through the real route answers 409
        `person_review_required`, applies nothing and logs no model call, and a person
        still approves it (INV-05, D-79; security-review-c4 L15, HARDENING H34)."""
        provision = library_build.provision(self.parent, key=PROVISION_KEY, ref_label="9 kap. 6 §")
        library_build.provision_version(provision, texts={"sv": "Den tidigare lydelsen."})
        proposal = self._filed(provision_version_body(provision))

        refused, _confirmer = self._approve_as_agent(proposal["id"])

        self._refused(refused, 409, "person_review_required")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertEqual(ProvisionVersion.objects.filter(provision=provision).count(), 1)
        self.assertFalse(AiGeneration.objects.filter(subject_id=proposal["id"]).exists(), "a refused decision logs no model call")
        self.assertEqual(self._approve(proposal["id"]).status_code, 200)
        self.assertEqual(ProvisionVersion.objects.filter(provision=provision).count(), 2)


# A provision keyed as the seeded library and the baseline key one: its instrument's key, a
# slash and its place in the instrument.
SLASH_KEY = f"{PARENT_KEY}/009-006"
SWEDISH = "Ett värdepappersinstitut ska inhämta uppgifter om kunden."
ENGLISH = "A securities institution shall obtain information about the client."


class TheLawsOwnWords(KindsTestCase):
    """The law's own words and the duties that cite them (INV-02, INV-05; Alex, 2026-11-13:
    "it says that the original text is in english while its actually swedish").

    A provision's original is the language its jurisdiction writes law in, at every door:
    where it is proposed, over a correction and at apply. A second language the authority
    itself published is neither the original nor machine-made. A provision names the
    obligations that cite it, shared ones in force under its own instrument, and approval
    ties each to it. A payload that sends none of this is stored and applied as before."""

    def setUp(self) -> None:
        super().setUp()
        self.duty = library_build.obligation(self.parent, key="obl-kinds-know-the-client", ref_label="9 kap. 6 §")
        self.second_duty = library_build.obligation(self.parent, key="obl-kinds-keep-the-record", ref_label="9 kap. 6 §")

    def _flags(self, key: str) -> dict[str, tuple[bool, bool]]:
        """Each text of the provision's one version: is it the original, is it machine-made."""
        version = ProvisionVersion.objects.get(provision__stable_key=key)
        return {row.language_id: (row.is_original, row.is_machine) for row in ProvisionText.objects.filter(version=version)}

    def _version_body(self, provision: Provision, **payload: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper overriding payload fields
        """A new text of `provision`, every field it sets sourced."""
        fields = {"texts": {"sv": "Institutet ska inhämta uppgifter om kundens mål."}, "originalLanguage": "sv", "effectiveFrom": "2028-01-01", **payload}
        return {**provision_version_body(provision), "payload": fields, "fieldSources": {field: SOURCE for field in _facts(fields)}}

    # --- the original is the authority's language ---
    def test_english_is_never_the_original_of_swedish_law(self) -> None:
        refused = self._file(provision_body(originalLanguage="en"))
        self._refused(refused, 422, "validation_error")
        self.assertIn(f"{PARENT_KEY!r} is written in 'sv'", refused.json()["detail"])
        self.assertFalse(Proposal.objects.exists(), "nothing is queued")

    def test_the_rule_reads_the_instruments_own_jurisdiction(self) -> None:
        union = library_build.instrument(key="celex-32014r0596", short_name="MAR", jurisdiction="eu", level="eu_regulation", regime="regime:securities")
        article = {"key": "celex-32014r0596/017", "provisionKind": "article", "refLabel": "Art. 17"}
        # Swedish is a translation of a Union act filed here, and English its original.
        self._refused(self._file(provision_body(union.stable_key, **article)), 422, "validation_error")
        english = {"texts": {"en": "An issuer shall inform the public as soon as possible of inside information."}, "originalLanguage": "en", "isMachine": False}
        proposal = self._filed(provision_body(union.stable_key, **article, **english))
        self.assertEqual(self._approve(proposal["id"]).status_code, 200)
        self.assertEqual(self._flags("celex-32014r0596/017"), {"en": (True, False)})

    def test_a_correction_and_a_proposal_stored_before_the_rule_are_refused_the_same(self) -> None:
        proposal = self._filed(provision_body())
        corrected = self._approve(proposal["id"], {"payloadOverrides": {"originalLanguage": "en"}})
        self._refused(corrected, 422, "validation_error")
        row = Proposal.objects.get(pk=proposal["id"])
        self.assertEqual((row.status, row.corrected_payload), (ProposalStatus.OPEN.value, None))
        stored = self._stored(provision_body(key="fffs-2017-2-kinds-filed-before", originalLanguage="en"))
        self._refused(self._approve(str(stored.id)), 422, "validation_error")
        self.assertFalse(Provision.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action__in=("proposal.approved", "provision.created")).exists())

    def test_a_new_text_of_a_provision_obeys_the_same_rule_at_every_door(self) -> None:
        provision = library_build.provision(self.parent, key=PROVISION_KEY, ref_label="9 kap. 6 §", kind="section")
        library_build.provision_version(provision, texts={"sv": "Den tidigare lydelsen."})
        english_first = self._version_body(provision, texts={"sv": SWEDISH, "en": ENGLISH}, originalLanguage="en")
        refused = self._file(english_first)
        self._refused(refused, 422, "validation_error")
        self.assertIn("written in 'sv'", refused.json()["detail"])
        self.assertFalse(Proposal.objects.exists())
        # Over a correction, and at apply for a proposal stored before the rule.
        proposal = self._filed(self._version_body(provision, texts={"sv": SWEDISH, "en": ENGLISH}, isMachine=True))
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"originalLanguage": "en"}}), 422, "validation_error")
        stored = Proposal.objects.create(
            kind="new_provision_version",
            title="Filed before the rule",
            target_type="provision",
            target_id=provision.id,
            payload=english_first["payload"],
            field_sources=english_first["fieldSources"],
            origin="agent",
            proposed_by_api_key_id=self.proposer.id,
            proposed_by_agent=self.proposer.agent,
            agent_run_id=self.agent_run.id,
        )
        self._refused(self._approve(str(stored.id)), 422, "validation_error")
        self.assertEqual(ProvisionVersion.objects.filter(provision=provision).count(), 1)
        # As filed, with Swedish the original, it applies.
        self.assertEqual(self._approve(proposal["id"]).status_code, 200)
        latest = ProvisionVersion.objects.get(provision=provision, version_number=2)
        self.assertEqual({row.language_id: (row.is_original, row.is_machine) for row in ProvisionText.objects.filter(version=latest)}, {"sv": (True, False), "en": (False, True)})

    # --- a second language the authority itself published ---
    def test_an_official_second_language_is_neither_the_original_nor_machine_made(self) -> None:
        act = library_build.instrument(key="fi-sd-2014-610", short_name="Luottolaitoslaki", jurisdiction="fi", regime="regime:banking")
        texts = {"fi": "Tätä lakia sovelletaan luottolaitostoimintaan.", "sv": "Denna lag tillämpas på kreditinstitutsverksamhet.", "en": "This Act applies to credit institution activity."}
        body = provision_body(act.stable_key, key="fi-sd-2014-610/001-001", refLabel="1 luku 1 §", texts=texts, originalLanguage="fi", officialLanguages=["sv", "sv"], isMachine=True)
        proposal = self._filed(body)
        self.assertEqual(proposal["payload"]["officialLanguages"], ["sv"], "each once")
        self.assertNotIn("officialLanguages", proposal["fieldSources"], "it says how the text is written, and needs no source")

        self.assertEqual(self._approve(proposal["id"]).status_code, 200)

        self.assertEqual(self._flags("fi-sd-2014-610/001-001"), {"fi": (True, False), "sv": (False, False), "en": (False, True)})

    def test_the_original_is_never_marked_as_anything_else(self) -> None:
        for case, official in (("the original itself", ["sv"]), ("a language with no text", ["da"])):
            with self.subTest(case=case):
                refused = self._file(provision_body(officialLanguages=official))
                self._refused(refused, 422, "validation_error")
                self.assertIn(official[0], refused.json()["detail"])
        self.assertFalse(Proposal.objects.exists())
        # And `isMachine` speaks for the translations alone: the original stays unlabelled.
        proposal = self._filed(provision_body(isMachine=True, officialLanguages=[]))
        self.assertNotIn("officialLanguages", proposal["payload"], "an empty list says what leaving it out says")
        self.assertEqual(self._approve(proposal["id"]).status_code, 200)
        self.assertEqual(self._flags(PROVISION_KEY), {"sv": (True, False), "en": (False, True)})

    def test_only_a_language_the_authority_publishes_in_sheds_the_machine_mark(self) -> None:
        """Review 2026-11-13: a payload could name the machine English of Swedish law as the
        authority's own and store it unlabelled."""
        act = library_build.instrument(key="fi-sd-2014-610", short_name="Luottolaitoslaki", jurisdiction="fi", regime="regime:banking")
        texts = {"fi": "Tätä lakia sovelletaan luottolaitostoimintaan.", "sv": "Denna lag tillämpas på kreditinstitutsverksamhet.", "en": "This Act applies to credit institution activity."}
        for case, body in (
            ("English beside Swedish law", provision_body(officialLanguages=["en"])),
            ("English beside Finnish law", provision_body(act.stable_key, key="fi-sd-2014-610/001-001", refLabel="1 luku 1 §", texts=texts, originalLanguage="fi", officialLanguages=["sv", "en"])),
        ):
            with self.subTest(case=case):
                refused = self._file(body)
                self._refused(refused, 422, "validation_error")
                self.assertIn("Not one of them: en.", refused.json()["detail"])
        proposal = self._filed(provision_body())
        self._refused(self._approve(proposal["id"], {"payloadOverrides": {"officialLanguages": ["en"]}}), 422, "validation_error")
        self.assertEqual(Proposal.objects.count(), 1)
        self.assertFalse(Provision.objects.exists(), "nothing is written over a correction that names one")

    def test_a_translation_of_law_is_stored_machine_made_whatever_the_payload_says(self) -> None:
        """Review 2026-11-13: a person approving a provision whose payload did not say
        `isMachine` stored its English unmarked, and the regulation page then called it the
        authority's official text (D-142)."""
        proposal = self._filed(provision_body(isMachine=False))
        self.assertEqual(self._approve(proposal["id"]).status_code, 200)
        self.assertEqual(self._flags(PROVISION_KEY), {"sv": (True, False), "en": (False, True)})
        # A new text of the same provision is held to it too.
        provision = Provision.objects.get(stable_key=PROVISION_KEY)
        version = self._filed(self._version_body(provision, texts={"sv": SWEDISH, "en": ENGLISH}, isMachine=False, effectiveFrom="2028-01-01"))
        self.assertEqual(self._approve(version["id"]).status_code, 200)
        latest = ProvisionVersion.objects.get(provision=provision, version_number=2)
        self.assertEqual({row.language_id: (row.is_original, row.is_machine) for row in ProvisionText.objects.filter(version=latest)}, {"sv": (True, False), "en": (False, True)})

    def test_the_lists_are_bounded_at_the_door(self) -> None:
        cases: tuple[tuple[str, dict[str, Any]], ...] = (
            ("an obligation key longer than a key", {"obligations": ["o" * 121]}),
            ("an obligation key that is not one", {"obligations": ["OBL Kinds"]}),
            ("more official languages than languages", {"officialLanguages": ["sv", "en", "da", "nb", "fi"]}),
            ("a language key longer than one", {"officialLanguages": ["s" * 9]}),
            # The cap counts the list as sent, though a repeat would be kept once.
            ("one key sent past the cap", {"obligations": [self.duty.stable_key] * (settings.PROPOSAL_PROVISION_MAX_OBLIGATIONS + 1)}),
        )
        for case, fields in cases:
            with self.subTest(case=case):
                self._refused(self._file(provision_body(**fields)), 422, "validation_error")
        self.assertFalse(Proposal.objects.exists())

    # --- the obligations that cite it ---
    def test_the_obligations_named_are_shared_ones_in_force_under_the_same_instrument(self) -> None:
        elsewhere = library_build.obligation(library_build.instrument(key="fffs-2014-1", regime="regime:securities"), key="obl-kinds-elsewhere")
        retired = library_build.obligation(self.parent, key="obl-kinds-retired")
        with library_write("test"):
            Obligation.objects.filter(pk=retired.pk).update(status="retired")
        for case, named in (
            ("an obligation of another instrument", [self.duty.stable_key, elsewhere.stable_key]),
            ("a key no obligation carries", ["obl-kinds-nobody"]),
            ("a retired obligation", [retired.stable_key]),
        ):
            with self.subTest(case=case):
                refused = self._file(provision_body(obligations=named))
                self._refused(refused, 422, "unknown_key")
                self.assertIn(named[-1], refused.json()["detail"])
                self.assertNotIn(f": {self.duty.stable_key}", refused.json()["detail"], "only the ones that are wrong are named")
        too_many = [f"obl-kinds-{n}" for n in range(settings.PROPOSAL_PROVISION_MAX_OBLIGATIONS + 1)]
        self._refused(self._file(provision_body(obligations=too_many)), 422, "validation_error")
        unsourced = provision_body(obligations=[self.duty.stable_key])
        del unsourced["fieldSources"]["obligations"]
        self._refused(self._file(unsourced), 422, "source_missing")
        self.assertFalse(Proposal.objects.exists())

    def test_approval_adds_the_node_its_first_text_and_the_ties_in_one_write(self) -> None:
        named = [self.duty.stable_key, self.second_duty.stable_key, self.duty.stable_key]
        proposal = self._filed(provision_body(key=SLASH_KEY, obligations=named))
        self.assertEqual(proposal["payload"]["obligations"], [self.duty.stable_key, self.second_duty.stable_key], "each once, in the order given")
        self.assertFalse(ObligationProvision.objects.exists(), "nothing changes until approval")

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        provision = Provision.objects.get(stable_key=SLASH_KEY)
        version = ProvisionVersion.objects.get(provision=provision)
        self.assertEqual((provision.instrument_id, version.version_number, str(version.applied_by_proposal_id)), (self.parent.id, 1, proposal["id"]))
        self.assertEqual(self._flags(SLASH_KEY), {"sv": (True, False), "en": (False, True)})
        self.assertEqual(
            set(ObligationProvision.objects.filter(provision=provision).values_list("obligation__stable_key", flat=True)),
            {self.duty.stable_key, self.second_duty.stable_key},
        )
        self.assertEqual([cited.stable_key for cited in self.duty.provisions.all()], [SLASH_KEY], "the duty cites the section")
        event = AuditEvent.objects.get(action="provision.created", subject_id=provision.id)
        self.assertEqual(event.after["obligations"], [self.duty.stable_key, self.second_duty.stable_key])
        self.assertIsNotNone(event.step_up_assertion_id)

    def test_a_failed_reindex_leaves_no_tie_behind(self) -> None:
        proposal = self._filed(provision_body(obligations=[self.duty.stable_key]))
        with mock.patch.object(apply, "reindex_provision", side_effect=RuntimeError("index unavailable")):
            self.assertEqual(self._approve(proposal["id"]).status_code, 500)
        self.assertFalse(ObligationProvision.objects.exists())
        self.assertFalse(Provision.objects.filter(stable_key=PROVISION_KEY).exists())

    def test_a_reviewer_may_clear_the_obligations_a_proposer_named(self) -> None:
        """Review 2026-11-13: the proposer's source for `obligations` outlived the field and
        refused the correction that cleared it."""
        proposal = self._filed(provision_body(obligations=[self.duty.stable_key]))

        approved = self._approve(proposal["id"], {"payloadOverrides": {"obligations": []}})

        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertFalse(ObligationProvision.objects.exists(), "nothing is tied")
        row = Proposal.objects.get(pk=proposal["id"])
        self.assertNotIn("obligations", row.corrected_payload or {"obligations": "no correction stored"})
        self.assertNotIn("obligations", row.field_sources, "the source went with its field")
        event = AuditEvent.objects.get(action="proposal.approved", subject_id=row.id)
        self.assertEqual(event.before["fieldSources"], {"obligations": SOURCE}, "the dropped source stays on the record")

    def test_a_new_text_ties_what_is_missing_and_leaves_an_existing_tie_alone(self) -> None:
        provision = library_build.provision(self.parent, key=PROVISION_KEY, ref_label="9 kap. 6 §", kind="section")
        library_build.provision_version(provision, texts={"sv": "Den tidigare lydelsen."})
        with library_write("test"):
            held = ObligationProvision.objects.create(obligation=self.duty, provision=provision)
        body = self._version_body(provision, obligations=[self.duty.stable_key, self.second_duty.stable_key])
        unsourced = {**body, "fieldSources": {field: source for field, source in body["fieldSources"].items() if field != "obligations"}}
        self._refused(self._file(unsourced), 422, "source_missing")
        elsewhere = library_build.obligation(library_build.instrument(key="fffs-2014-1", regime="regime:securities"), key="obl-kinds-elsewhere")
        self._refused(self._file(self._version_body(provision, obligations=[elsewhere.stable_key])), 422, "unknown_key")
        proposal = self._filed(body)

        approved = self._approve(proposal["id"])

        self.assertEqual(approved.status_code, 200, approved.content)
        ties = ObligationProvision.objects.filter(provision=provision)
        self.assertEqual({tie.obligation_id for tie in ties}, {self.duty.id, self.second_duty.id})
        self.assertTrue(ties.filter(pk=held.pk).exists(), "the tie the library held is the same row")
        event = AuditEvent.objects.get(action="provision.version_applied", subject_id=provision.id)
        self.assertEqual(event.after["obligations"], [self.second_duty.stable_key], "only what this approval tied")

    def test_the_cost_of_the_ties_does_not_grow_with_their_number(self) -> None:
        """Playbook 10: the duties a provision names are resolved in one query where it is
        proposed and tied in one insert where it is approved, whether it names one or many."""
        many = [library_build.obligation(self.parent, key=f"obl-kinds-duty-{n}").stable_key for n in range(8)]
        costs: list[tuple[int, int]] = []
        # The first request also pays for what the process caches; the last two are compared.
        for path, named in (("001", [self.duty.stable_key]), ("002", [self.duty.stable_key]), ("003", many)):
            with CaptureQueriesContext(connection) as filing:
                proposal = self._filed(provision_body(key=f"{PARENT_KEY}/{path}", obligations=named))
            with CaptureQueriesContext(connection) as approving:
                self.assertEqual(self._approve(proposal["id"]).status_code, 200)
            costs.append((len(filing), len(approving)))
        self.assertEqual(costs[1], costs[2], "naming eight duties costs what naming one does")
        self.assertEqual(ObligationProvision.objects.filter(provision__stable_key=f"{PARENT_KEY}/003").count(), 8)

    def test_an_agent_still_cannot_approve_a_provision_that_names_its_duties(self) -> None:
        proposal = self._filed(provision_body(obligations=[self.duty.stable_key]))
        refused, _confirmer = self._approve_as_agent(proposal["id"])
        self._refused(refused, 409, "person_review_required")
        self.assertFalse(Provision.objects.filter(stable_key=PROVISION_KEY).exists())
        self.assertFalse(ObligationProvision.objects.exists())

    # --- what did not change ---
    def test_a_payload_that_sends_none_of_this_is_stored_and_applied_as_before(self) -> None:
        proposal = self._filed(provision_body())
        self.assertEqual(
            proposal["payload"],
            {
                "key": PROVISION_KEY,
                "instrument": PARENT_KEY,
                "provisionKind": "section",
                "refLabel": "9 kap. 6 §",
                "heading": "",
                "sortOrder": 0,
                "texts": {"sv": SWEDISH, "en": ENGLISH},
                "originalLanguage": "sv",
                "isMachine": True,
                "effectiveFrom": "2027-01-01",
                "effectiveFromPrecision": "day",
            },
        )
        self.assertEqual(self._approve(proposal["id"]).status_code, 200)
        self.assertEqual(self._flags(PROVISION_KEY), {"sv": (True, False), "en": (False, True)})
        self.assertFalse(ObligationProvision.objects.exists())
        self.assertEqual(AuditEvent.objects.get(action="provision.created").after["obligations"], [])

    def test_a_key_may_end_in_a_slash_and_the_provisions_place_and_nothing_looser(self) -> None:
        for key in ("FFFS-2017-2/9", f"{PARENT_KEY}/009/006", f"{PARENT_KEY}/", f"/{PARENT_KEY}", f"{PARENT_KEY}/009_006"):
            with self.subTest(key=key):
                self._refused(self._file(provision_body(key=key)), 422, "validation_error")
        # Before the slash stands the provision's own instrument, never another's.
        library_build.instrument(key="fffs-2014-1", regime="regime:securities")
        refused = self._file(provision_body(key="fffs-2014-1/009-006"))
        self._refused(refused, 422, "validation_error")
        self.assertIn(repr(PARENT_KEY), refused.json()["detail"])
        self.assertEqual(self._filed(provision_body(key=SLASH_KEY))["payload"]["key"], SLASH_KEY)


class TheTiesAreWrittenThroughTheDoorAsTheAppRole(TransactionTestCase):
    """The rest of this module runs as the schema owner, whom the database's door trigger
    lets through (apps/shared/tests_library_db_guard.py). Here a provision that names its
    obligations is filed and approved on the cw_app connection, as a console request does
    it, so `obligation_provision` is proven to be written inside the proposal door and under
    its row-level policies (H16, ADR 0058, AC-PRO1)."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_term_dimensions()
            seed_taxonomy_terms()
            seed_authorities()
        self.parent = library_build.instrument(key=PARENT_KEY, short_name="FFFS 2017:2", regime="regime:securities")
        self.duty = library_build.obligation(self.parent, key="obl-kinds-know-the-client")
        self.proposer = factories.platform_user(roles=("library_editor",), email="tie-proposer@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="tie-reviewer@bleqq.test")

    def test_a_provision_and_its_ties_are_written_as_the_app_role(self) -> None:
        # Imported here: that module imports this one's bodies.
        from apps.shared.tests_library_db_guard import as_the_app_role

        body = provision_body(obligations=[self.duty.stable_key])
        with as_the_app_role():
            with transaction.atomic():
                tenancy.clear_tenant()  # the console's session: no bank's zone
                proposal, _ = logic.create(
                    kind=body["kind"],
                    title=body["title"],
                    payload=body["payload"],
                    proposer=logic.Proposer(actor=factories.user_actor(user_id=self.proposer.id), user=self.proposer),
                    field_sources=body["fieldSources"],
                    source_label=body["sourceLabel"],
                    source_url=body["sourceUrl"],
                )
            with transaction.atomic():
                tenancy.clear_tenant()
                logic.approve(
                    proposal=logic.by_id(proposal.id),
                    reviewer=self.reviewer,
                    actor=factories.user_actor(user_id=self.reviewer.id),
                    note="",
                    step_up_assertion_id=uuid.uuid4(),
                )
        with transaction.atomic():
            tenancy.clear_tenant()
            tied = ObligationProvision.objects.filter(provision__stable_key=PROVISION_KEY).values_list("obligation__stable_key", flat=True)
            self.assertEqual(list(tied), [self.duty.stable_key])


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
        # A standard's source label is its official reference alone (H35).
        return {**obligation_body(STANDARD_KEY, **fields), "sourceLabel": "ISO/IEC 27001:2022"}

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


class TheObligationScopeKind(TestCase):
    """PRO-04's re-tag kind, `obligation_scope`, which chunk 4 cut (parallel-plan ruling 14):
    a member of the code enum `apply()` branches on, never a vocabulary row, so the class
    already allowlisted in apps/shared/kinds.py covers it. Its payload schema and its apply
    branch are the batch tasks' that follow; here it is a kind a proposal row can carry."""

    def test_it_is_a_member_and_a_choice_of_the_kind_column(self) -> None:
        self.assertEqual(ProposalKind.OBLIGATION_SCOPE.value, "obligation_scope")
        self.assertIn("obligation_scope", {value for value, _ in Proposal._meta.get_field("kind").choices or []})

    def test_the_migration_stores_the_choice(self) -> None:
        migration = importlib.import_module("apps.proposals.migrations.0001_squashed_0001_tables").Migration
        proposal = next(op for op in migration.operations if isinstance(op, migrations.CreateModel) and op.name == "Proposal")
        self.assertIn(("obligation_scope", "obligation_scope"), list(dict(proposal.fields)["kind"].choices or []))

    def test_every_kind_round_trips(self) -> None:
        proposer = factories.user()
        for kind in ProposalKind:
            with self.subTest(kind=kind):
                stored = Proposal.objects.create(
                    kind=kind.value, title=f"A {kind.value}", origin=OriginType.USER.value, proposed_by_user=proposer
                )
                self.assertEqual(ProposalKind(Proposal.objects.get(pk=stored.pk).kind), kind)
