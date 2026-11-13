"""The library baseline through the proposal door (ADR 0065, D-118; PRO-01, INV-01, INV-03).

`proposals.baseline` files the baseline's entries as proposals of the platform agent
`library-baseline`; a second principal approves them. Proved here:

- every entry of the real baseline files and, once a person approves it, applies: the
  instruments on the first call, their duties and summaries on the second, the provisions
  that cite those duties on the third, nothing on the fourth;
- each proposal names the agent and a run of it, carries a source on every field, and is
  open until someone else decides it; the agent can never be that someone;
- runs hold at most `WATCH_RUN_MAX_PROPOSALS` filings and close as succeeded with the count;
- an entry open in the queue under its key is left alone, whoever filed it; a rejected entry
  is not filed again until the baseline changes it; a dry run files nothing;
- an entry the door refuses is reported and files nothing, and the rest still file;
- approving a library instrument queues the filing, so its duties follow within seconds:
  one run for a page of approvals, none when it is switched off or for a bank's own;
- a provision, the law's own words (INV-02), is filed once its instrument and every duty it
  names are held, once, as the door takes it; approving a duty queues the filing; a caller
  whose reviewer is an agent is handed neither provisions nor summaries; and the command's
  summary counts provisions filed, held and waiting.

Operations exercised (the audit-on-write guard reads these names): none; the command files.
"""

from __future__ import annotations

import copy
import io
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.conf import settings
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentRun, RunStatus
from apps.agents.seeds import seed_agent_definitions
from apps.library.models import Instrument, Obligation, ObligationProvision, Provision, ProvisionText
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import baseline, logic
from apps.proposals.models import OriginType, Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent
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


def _provision(instrument: str, *duties: str, path: str = "001", text: str = "A firm shall tell the public what it must.") -> dict[str, Any]:
    """A provision of `instrument` as a provisions file holds it (the baseline's README, "The
    law's own words"): the text of an article of an invented Union regulation, so English is
    its original, cited by `duties`."""
    return {
        "key": f"{instrument}/{path}",
        "instrument": instrument,
        "provisionKind": "article",
        "refLabel": "Art. 1",
        "path": path,
        "heading": None,
        "texts": {"en": text},
        "originalLanguage": "en",
        "obligations": list(duties),
        "source": f"{SOURCE}#art_1",
        "sourceLabel": "EUR-Lex, an invented regulation for this test, Article 1, as published in the Official Journal",
        "readOn": "2026-11-13",
    }


def write_provisions(folder: Path, provisions: list[dict[str, Any]], name: str = "test-tranche") -> None:
    (folder / baseline.PROVISIONS_DIR).mkdir(exist_ok=True)
    body = {"tranche": name, "researchedOn": "2026-11-13", "provisions": provisions}
    (folder / baseline.PROVISIONS_DIR / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")


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


class TheRealBaseline(BaselineCase):
    def test_every_entry_files_and_applies_instruments_first_then_their_duties_then_the_law_they_cite(self) -> None:
        entries = baseline.load()
        instruments = {entry.key for entry in entries if entry.kind == baseline.INSTRUMENT}
        duties = {entry.key for entry in entries if entry.kind == baseline.OBLIGATION}
        summaries = {entry.key for entry in entries if entry.kind == baseline.SUMMARY}
        # None until the law's own words are filed in `provisions/`; every count below holds either way.
        provisions = {entry.key for entry in entries if entry.kind == baseline.PROVISION}
        self.assertTrue(instruments, "the baseline holds instruments")
        self.assertEqual(summaries, instruments, "every instrument of the baseline has its summary (INV-09)")

        first = baseline.file()
        self.assertEqual(first.refused, [])
        self.assertEqual(sum(first.filed.values()), len(instruments), "only instruments are due on the first call")
        self.assertEqual(sum(first.waiting.values()), len(duties) + len(summaries) + len(provisions))
        self.assertEqual(self.approve_open(), len(instruments))

        second = baseline.file()
        self.assertEqual(second.refused, [])
        self.assertEqual(sum(second.filed.values()), len(duties) + len(summaries), "the duties and the summaries follow")
        self.assertEqual(sum(second.waiting.values()), len(provisions), "a provision waits for the duties that cite it")
        self.assertEqual(self.approve_open(), len(duties) + len(summaries))

        third = baseline.file()
        self.assertEqual(third.refused, [])
        self.assertEqual(sum(third.filed.values()), len(provisions), "the law's own words follow the duties that cite them")
        self.assertEqual(self.approve_open(), len(provisions))

        fourth = baseline.file()
        self.assertEqual((sum(fourth.filed.values()), fourth.runs), (0, 0))
        self.assertEqual(sum(fourth.held.values()), len(instruments) + len(duties) + len(summaries) + len(provisions))
        self.assertEqual(set(Instrument.objects.filter(stable_key__in=instruments).values_list("stable_key", flat=True)), instruments)
        self.assertEqual(set(Obligation.objects.filter(stable_key__in=duties).values_list("stable_key", flat=True)), duties)
        self.assertEqual(set(Provision.objects.filter(stable_key__in=provisions).values_list("stable_key", flat=True)), provisions)


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
        self.assertEqual(first.waiting[("test-tranche", baseline.OBLIGATION)], 2)
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


class FilingTheLawsOwnWords(BaselineCase):
    """A tranche's provisions (INV-02; Alex, 2026-11-13): each is filed as a `new_provision`
    once the library holds its instrument and every duty it names, as the door takes it, and
    is held from then on like any other record."""

    TALLY = ("test-tranche", baseline.PROVISION)

    def setUp(self) -> None:
        super().setUp()
        self.folder = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(baseline, "BASELINE_DIR", self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        body = {"tranche": "test-tranche", "researchedOn": "2026-09-30", "instruments": [_instrument("test-a", _duty("obl-test-a-one"), _duty("obl-test-a-two"))]}
        (self.folder / "test-tranche.json").write_text(json.dumps(body), encoding="utf-8")
        self.entry = _provision("test-a", "obl-test-a-one", "obl-test-a-two")
        write_provisions(self.folder, [self.entry])

    def approve(self, key: str) -> None:
        proposal = Proposal.objects.get(payload__key=key, status=ProposalStatus.OPEN.value)
        actor = factories.user_actor(user_id=self.reviewer.id, label=self.reviewer.name)
        logic.approve(proposal=proposal, reviewer=self.reviewer, actor=actor, note="", step_up_assertion_id=None)

    def hold_the_duties(self) -> None:
        """The instrument and its two duties, filed and approved, with nothing else filed."""
        for _pass in range(2):
            baseline.file(only_agent_confirmable=True)
            self.approve_open()

    def test_a_provision_waits_for_its_instrument_and_every_duty_it_names_and_is_filed_once(self) -> None:
        first = baseline.file()
        self.assertEqual((first.filed[self.TALLY], first.waiting[self.TALLY]), (0, 1), "its instrument is not held")
        self.approve("test-a")
        second = baseline.file()
        self.assertEqual((second.filed[self.TALLY], second.waiting[self.TALLY]), (0, 1), "its duties are proposed, not held")
        self.approve("obl-test-a-one")
        third = baseline.file()
        self.assertEqual((third.filed[self.TALLY], third.waiting[self.TALLY]), (0, 1), "one duty it names is still not held")
        self.assertFalse(Proposal.objects.filter(kind=baseline.PROVISION).exists())
        self.approve("obl-test-a-two")

        fourth = baseline.file()

        self.assertEqual((fourth.filed[self.TALLY], fourth.waiting[self.TALLY], fourth.refused), (1, 0, []))
        proposal = Proposal.objects.get(kind=baseline.PROVISION)
        self.assertEqual(
            proposal.payload,
            {
                "key": "test-a/001",
                "instrument": "test-a",
                "provisionKind": "article",
                "refLabel": "Art. 1",
                "heading": "",
                "sortOrder": 0,
                "texts": self.entry["texts"],
                "originalLanguage": "en",
                "isMachine": False,
                "obligations": ["obl-test-a-one", "obl-test-a-two"],
                "effectiveFromPrecision": "day",
            },
            "the entry's own fields as the door takes them, and nothing the file keeps for itself",
        )
        self.assertEqual(proposal.title, "Add the text of Art. 1, Regulation (EU) 2099/test-a, as read on 2026-11-13")
        self.assertEqual((proposal.source_url, proposal.source_label), (self.entry["source"], self.entry["sourceLabel"]))
        self.assertEqual(set(proposal.field_sources), {"instrument", "provisionKind", "refLabel", "texts.en", "obligations"})
        self.assertEqual(set(proposal.field_sources.values()), {self.entry["source"]})
        self.assertEqual((proposal.status, getattr(proposal.proposed_by_agent, "key", None)), ("open", baseline.AGENT_KEY))
        self.assertTrue(proposal.idempotency_key.startswith("baseline:test-a/001:"))  # type: ignore[union-attr]
        fifth = baseline.file()
        self.assertEqual((fifth.filed[self.TALLY], fifth.open[self.TALLY], fifth.runs), (0, 1, 0), "open in the queue, it is left alone")

        self.approve("test-a/001")

        provision = Provision.objects.get(stable_key="test-a/001")
        texts = {row.language_id: (row.is_original, row.is_machine) for row in ProvisionText.objects.filter(version__provision=provision)}
        self.assertEqual(texts, {"en": (True, False)})
        cited_by = set(ObligationProvision.objects.filter(provision=provision).values_list("obligation__stable_key", flat=True))
        self.assertEqual(cited_by, {"obl-test-a-one", "obl-test-a-two"})
        sixth = baseline.file()
        self.assertEqual((sixth.filed[self.TALLY], sixth.held[self.TALLY], sixth.runs), (0, 1, 0), "held, it is never filed again")

    def test_a_rejected_provision_is_filed_again_only_when_its_entry_changes(self) -> None:
        self.hold_the_duties()
        baseline.file()
        logic.reject(
            proposal=Proposal.objects.get(kind=baseline.PROVISION),
            reviewer=self.reviewer,
            actor=factories.user_actor(user_id=self.reviewer.id),
            rejection_code="wrong_fact",
            note="Not the wording of the article.",
        )
        self.assertEqual(baseline.file().decided[self.TALLY], 1)
        write_provisions(self.folder, [_provision("test-a", "obl-test-a-one", "obl-test-a-two", text="A firm shall tell the public at once.")])
        self.assertEqual(baseline.file().filed[self.TALLY], 1)
        self.assertEqual(Proposal.objects.filter(kind=baseline.PROVISION, status=ProposalStatus.OPEN.value).count(), 1)

    def test_a_caller_whose_reviewer_is_an_agent_is_handed_nothing_a_person_must_approve(self) -> None:
        (self.folder / baseline.SUMMARIES_DIR).mkdir()
        summary = {"key": "test-a", "source": SOURCE, "sourceLabel": "EUR-Lex, an invented regulation for this test", "text": {"en": "What the invented regulation asks of a bank."}}
        body = {"tranche": "test-tranche", "researchedOn": "2026-11-09", "summaries": [summary]}
        (self.folder / baseline.SUMMARIES_DIR / "test-tranche.json").write_text(json.dumps(body), encoding="utf-8")
        self.hold_the_duties()

        for_an_agent = baseline.file(only_agent_confirmable=True)

        self.assertEqual((sum(for_an_agent.filed.values()), sum(for_an_agent.waiting.values()), for_an_agent.runs), (0, 0, 0))
        self.assertEqual({proposal.kind for proposal in Proposal.objects.all()}, {baseline.INSTRUMENT, baseline.OBLIGATION})
        for_a_person = baseline.file()
        self.assertEqual((for_a_person.filed[("test-tranche", baseline.SUMMARY)], for_a_person.filed[self.TALLY]), (1, 1))

    def test_a_dry_run_reports_the_provision_and_files_nothing(self) -> None:
        self.hold_the_duties()
        before = Proposal.objects.count()
        self.assertEqual(baseline.file(dry_run=True).filed[self.TALLY], 1)
        self.assertEqual(Proposal.objects.count(), before)

    def test_the_command_counts_provisions_filed_held_and_waiting(self) -> None:
        def run(*arguments: str) -> str:
            out = io.StringIO()
            call_command("file_library_baseline", *arguments, stdout=out)
            return out.getvalue()

        self.assertIn(
            "test-tranche: filed 1 instruments, 0 duties, 0 summaries, 0 provisions; "
            "waiting for an approval: 0 instruments, 2 duties, 0 summaries, 1 provisions;",
            run(),
        )
        self.approve_open()
        baseline.file()
        self.approve_open()
        self.assertIn("test-tranche: would file 0 instruments, 0 duties, 0 summaries, 1 provisions;", run("--dry-run"))
        self.assertIn("test-tranche: filed 0 instruments, 0 duties, 0 summaries, 1 provisions;", run("--tranche", "test-tranche"))
        self.assertIn("open in the queue: 0 instruments, 0 duties, 0 summaries, 1 provisions;", run())
        self.approve_open()
        done = run()
        self.assertIn("already in the library: 1 instruments, 2 duties, 0 summaries, 1 provisions;", done)
        self.assertIn("runs: 0, refused: 0", done)


class RegisteringTheSources(BaselineCase):
    """The pages the baseline's records came from are registered for the watch (WAT-01),
    through the console's own writer, once each."""

    def test_every_source_of_the_real_baseline_registers_once(self) -> None:
        from apps.watch.models import Source

        names = [spec["name"] for spec in json.loads((baseline.BASELINE_DIR / baseline.SOURCES_FILE).read_text(encoding="utf-8"))["sources"]]
        self.assertEqual(baseline.register_sources(), len(names))
        self.assertEqual(sorted(Source.objects.filter(name__in=names).values_list("name", flat=True)), sorted(names))
        self.assertEqual(baseline.register_sources(), 0, "a second call registers nothing")
        self.assertEqual(AuditEvent.objects.filter(action="source.registered").count(), len(names))
        fi = Source.objects.select_related("authority").get(name="Finansinspektionen, nyheter")
        self.assertEqual((getattr(fi.authority, "key", None), fi.check_frequency, fi.active), ("fi", "weekly", True))

    def test_a_source_an_editor_already_registered_by_name_is_left_as_it_is(self) -> None:
        from apps.watch.models import Source

        folder = Path(tempfile.mkdtemp())
        spec = {"name": "ESMA news", "url": "https://www.esma.europa.eu/press-news/esma-news", "kind": "authority_site", "authority": "esma"}
        (folder / baseline.SOURCES_FILE).write_text(json.dumps({"sources": [spec]}), encoding="utf-8")
        self.assertEqual(baseline.register_sources(folder), 1)
        moved = {**spec, "url": "https://www.esma.europa.eu/"}
        (folder / baseline.SOURCES_FILE).write_text(json.dumps({"sources": [moved]}), encoding="utf-8")
        self.assertEqual(baseline.register_sources(folder), 0)
        self.assertEqual(Source.objects.get(name="ESMA news").url, spec["url"])


class TheBaselineOnTheBeat(BaselineCase):
    def test_the_beat_files_the_baseline_and_registers_its_sources(self) -> None:
        from apps.proposals import tasks

        self.assertEqual(settings.CELERY_BEAT_SCHEDULE["library-baseline"]["task"], "apps.proposals.tasks.file_library_baseline")
        folder = Path(tempfile.mkdtemp())
        body = {"tranche": "beat", "researchedOn": "2026-10-01", "instruments": [_instrument("beat-a")]}
        (folder / "beat.json").write_text(json.dumps(body), encoding="utf-8")
        with mock.patch.object(baseline, "BASELINE_DIR", folder):
            tasks.file_library_baseline()
        self.assertEqual(Proposal.objects.get(payload__key="beat-a").proposed_by_agent.key, baseline.AGENT_KEY)  # type: ignore[union-attr]


def _drain_outbox() -> None:
    """Deliver every pending row; the seeds alone write more than one batch."""
    from apps.shared import outbox

    while outbox.deliver_batch().delivered:
        pass


@override_settings(LIBRARY_BASELINE_ON_APPROVAL_S=10)
class DutiesFollowAnApproval(BaselineCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.folder = Path(tempfile.mkdtemp())
        body = {"tranche": "follow", "researchedOn": "2026-11-09", "instruments": [_instrument("follow-a", _duty("follow-a-duty")), _instrument("follow-b")]}
        (self.folder / "follow.json").write_text(json.dumps(body), encoding="utf-8")
        patcher = mock.patch.object(baseline, "BASELINE_DIR", self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_approving_an_instrument_files_its_duties_without_waiting_for_the_beat(self) -> None:
        baseline.file()
        self.approve_open()
        self.assertFalse(Proposal.objects.filter(payload__key="follow-a-duty").exists())
        _drain_outbox()
        duty = Proposal.objects.get(payload__key="follow-a-duty")
        self.assertEqual((duty.status, duty.proposed_by_agent.key), (ProposalStatus.OPEN.value, baseline.AGENT_KEY))  # type: ignore[union-attr]

    def test_approving_a_duty_files_the_provisions_that_cite_it_without_waiting_for_the_beat(self) -> None:
        write_provisions(self.folder, [_provision("follow-a", "follow-a-duty")], name="follow")
        baseline.file()
        self.approve_open()
        _drain_outbox()  # the instruments' approvals queue the run that files the duty
        self.assertFalse(Proposal.objects.filter(kind=baseline.PROVISION).exists(), "the duty it names is only proposed")
        cache.clear()  # the duty is approved in a later window
        self.approve_open()
        _drain_outbox()
        provision = Proposal.objects.get(kind=baseline.PROVISION)
        self.assertEqual((provision.status, provision.payload["obligations"]), (ProposalStatus.OPEN.value, ["follow-a-duty"]))

    def test_a_page_of_approvals_queues_one_run(self) -> None:
        from apps.proposals import tasks

        baseline.file()
        self.assertEqual(self.approve_open(), 2)
        with mock.patch.object(tasks.file_library_baseline, "apply_async") as queued:
            _drain_outbox()
        queued.assert_called_once_with(countdown=10)

    def test_nothing_is_queued_when_switched_off_or_for_a_banks_own_instrument(self) -> None:
        from apps.proposals import tasks
        from apps.shared.models import OutboxEvent

        own = OutboxEvent(topic=tasks.INSTRUMENT_CREATED, tenant_id=uuid.uuid4())
        shared = OutboxEvent(topic=tasks.INSTRUMENT_CREATED, tenant_id=None)
        with mock.patch.object(tasks.file_library_baseline, "apply_async") as queued:
            tasks.queue_after_approval(own)
            with override_settings(LIBRARY_BASELINE_ON_APPROVAL_S=0):
                tasks.queue_after_approval(shared)
        queued.assert_not_called()
