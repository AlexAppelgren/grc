"""The library baseline through the proposal door (ADR 0065, D-118; PRO-01, INV-01, INV-03).

`proposals.baseline` files the baseline's entries as proposals of the platform agent
`library-baseline`; a second principal approves them. Proved here:

- each proposal names the agent and a run of it, carries a source on every field, and is
  open until someone else decides it; the agent can never be that someone;
- runs hold at most `WATCH_RUN_MAX_PROPOSALS` filings and close as succeeded with the count;
- an entry open in the queue under its key is left alone, whoever filed it; a rejected entry
  is not filed again until the baseline changes it; a dry run files nothing;
- an entry the door refuses is reported and files nothing, and the rest still file.

Operations exercised (the audit-on-write guard reads these names): none; the command files.
"""

from __future__ import annotations

import copy
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentRun, RunStatus
from apps.agents.seeds import seed_agent_definitions
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import baseline, logic
from apps.proposals.models import OriginType, Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

SOURCE = "https://eur-lex.europa.eu/eli/reg/2099/1/oj"


def _instrument(key: str, *duties: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": f"Add {key}",
        "source": SOURCE,
        "sourceLabel": "EUR-Lex, an invented regulation for this test",
        "payload": {
            "key": key,
            "titles": {"en": f"Invented regulation {key}"},
            "originalLanguage": "en",
            "shortName": key.upper(),
            "officialRef": f"Regulation (EU) 2099/{key}",
            "level": "eu_regulation",
            "jurisdiction": "eu",
            "authority": "eu-legislator",
            "regime": "regime:securities",
            "inForceFrom": "2099-01-01",
        },
        "obligations": list(duties),
    }


def _duty(key: str, summary: str = "The firm tells the public what it must.") -> dict[str, Any]:
    return {
        "title": f"Add the duty: {key}",
        "source": SOURCE,
        "sourceLabel": "EUR-Lex, an invented regulation for this test, Article 1",
        "payload": {
            "key": key,
            "titles": {"en": "Tell the public"},
            "summaries": {"en": summary},
            "originalLanguage": "en",
            "refLabel": "Art. 1",
            "dutyType": "disclosure",
            "terms": ["legal_entity:bank"],
        },
    }


class BaselineCase(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        seed_authorities()
        tenancy.clear_tenant()  # the command files in no tenant's zone
        seed_agent_definitions()
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")

    def approve_open(self) -> int:
        approved = 0
        for proposal in Proposal.objects.filter(status=ProposalStatus.OPEN.value).order_by("created_at", "id"):
            logic.approve(
                proposal=proposal,
                reviewer=self.reviewer,
                actor=factories.user_actor(user_id=self.reviewer.id, label=self.reviewer.name),
                note="",
                step_up_assertion_id=None,
            )
            approved += 1
        return approved


class FilingTheBaseline(BaselineCase):
    def setUp(self) -> None:
        super().setUp()
        self.folder = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(baseline, "BASELINE_DIR", self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write([_instrument("test-a", _duty("obl-test-a-one"), _duty("obl-test-a-two")), _instrument("test-b")])

    def write(self, instruments: list[dict[str, Any]], name: str = "test-tranche") -> None:
        body = {"tranche": name, "researchedOn": "2026-09-30", "instruments": instruments}
        (self.folder / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")

    def test_a_proposal_names_the_agent_and_its_run_and_sources_every_field(self) -> None:
        baseline.file()
        agent = Agent.objects.get(key=baseline.AGENT_KEY)
        proposal = Proposal.objects.get(payload__key="test-a")
        self.assertEqual((proposal.status, proposal.origin, proposal.proposed_by_agent_id), ("open", OriginType.AGENT.value, agent.id))
        self.assertIsNone(proposal.proposed_by_user_id)
        self.assertIsNone(proposal.proposed_by_api_key_id)
        self.assertEqual(AgentRun.objects.get(pk=proposal.agent_run_id or uuid.uuid4()).agent_id, agent.id)
        self.assertEqual(proposal.source_url, SOURCE)
        self.assertEqual(set(proposal.field_sources), set(logic.sourced_fields(logic.parsed_payload(proposal.kind, proposal.payload))))
        self.assertEqual(set(proposal.field_sources.values()), {SOURCE})

    def test_the_agent_can_never_approve_what_it_filed(self) -> None:
        baseline.file()
        proposal = Proposal.objects.get(payload__key="test-a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Proposal.objects.filter(pk=proposal.pk).update(reviewed_by_agent_id=proposal.proposed_by_agent_id, status="approved")

    @override_settings(WATCH_RUN_MAX_PROPOSALS=1)
    def test_a_run_files_at_most_its_budget_and_closes_with_its_count(self) -> None:
        report = baseline.file()
        runs = AgentRun.objects.filter(agent__key=baseline.AGENT_KEY)
        self.assertEqual((report.runs, runs.count()), (2, 2))
        for run in runs:
            self.assertEqual((run.status, run.stats["proposalsSubmitted"], run.tenant_id), (RunStatus.SUCCEEDED.value, 1, None))
            self.assertEqual(run.external_session_id, "", "no runner was handed the run")

    def test_duties_wait_for_their_instrument_and_file_once_it_is_approved(self) -> None:
        first = baseline.file()
        self.assertEqual(first.waiting["test-tranche"], 2)
        self.approve_open()
        second = baseline.file()
        self.assertEqual(second.filed[("test-tranche", baseline.OBLIGATION)], 2)
        self.assertEqual(sum(second.held.values()), 2)

    def test_a_second_call_files_nothing_while_the_first_is_open(self) -> None:
        baseline.file()
        again = baseline.file()
        self.assertEqual((sum(again.filed.values()), again.runs, sum(again.open.values())), (0, 0, 2))
        self.assertEqual(Proposal.objects.count(), 2)

    def test_an_entry_open_under_its_key_from_anyone_is_left_alone(self) -> None:
        with mock.patch.object(baseline, "BASELINE_DIR", self.folder):
            entry = next(entry for entry in baseline.load() if entry.key == "test-b")
        editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        logic.create(
            kind=entry.kind,
            title="A person's own proposal of the same instrument",
            payload=entry.payload,
            proposer=logic.Proposer(actor=factories.user_actor(user_id=editor.id), user=editor),
            field_sources=entry.field_sources,
            source_url=entry.source_url,
        )
        report = baseline.file()
        self.assertEqual(report.open[("test-tranche", baseline.INSTRUMENT)], 1)
        self.assertEqual(Proposal.objects.filter(payload__key="test-b").count(), 1)

    def test_a_rejected_entry_is_not_filed_again_until_the_baseline_changes_it(self) -> None:
        baseline.file()
        proposal = Proposal.objects.get(payload__key="test-b")
        logic.reject(
            proposal=proposal,
            reviewer=self.reviewer,
            actor=factories.user_actor(user_id=self.reviewer.id),
            rejection_code="duplicate",
            note="The library already says this.",
        )
        self.assertEqual(baseline.file().decided[("test-tranche", baseline.INSTRUMENT)], 1)
        corrected = _instrument("test-b")
        corrected["payload"]["shortName"] = "TEST-B CORRECTED"
        self.write([_instrument("test-a", _duty("obl-test-a-one"), _duty("obl-test-a-two")), corrected])
        self.assertEqual(baseline.file().filed[("test-tranche", baseline.INSTRUMENT)], 1)
        self.assertEqual(Proposal.objects.filter(payload__key="test-b", status="open").count(), 1)

    def test_a_dry_run_files_nothing(self) -> None:
        report = baseline.file(dry_run=True)
        self.assertEqual(sum(report.filed.values()), 2)
        self.assertEqual((Proposal.objects.count(), AgentRun.objects.count()), (0, 0))

    def test_an_entry_the_door_refuses_is_reported_and_the_rest_still_file(self) -> None:
        broken = _instrument("test-c")
        broken["payload"]["authority"] = "no-such-authority"
        self.write([_instrument("test-a"), copy.deepcopy(broken)])
        report = baseline.file()
        self.assertEqual([key for key, _code, _detail in report.refused], ["test-c"])
        self.assertEqual(list(Proposal.objects.values_list("payload__key", flat=True)), ["test-a"])

    def test_an_unknown_tranche_is_refused_by_name(self) -> None:
        with self.assertRaisesMessage(Exception, "No such tranche: nope"):
            baseline.file(only=["nope"])
