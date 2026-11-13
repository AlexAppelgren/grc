"""The library baseline, filed through the proposal door (ADR 0065, D-118; PRO-01, INV-01,
INV-03).

`apps/library/baseline/` holds the shared library's starting inventory as reviewed data,
each entry in the shape `POST /proposals` takes. This module files what the library does not
hold as proposals of the platform agent `library-baseline`; `manage.py file_library_baseline`
is that agent's runner. It decides nothing: a second, independent principal approves each
proposal, and `proposal_four_eyes` refuses this agent as its own reviewer.

One call files a `new_instrument` per instrument not held, a `new_obligation` per duty whose
instrument is held, a `new_instrument_summary` per held instrument without one (INV-09,
D-124), and a `new_provision`, the law's own words, per provision whose instrument and every
duty it names are held (INV-02). Never an entry open in the queue, and never one filed
before unchanged: the retry key carries the entry's content hash.

Each entry is filed in its own transaction, so a refused entry stops nothing else. Runs hold
at most `WATCH_RUN_MAX_PROPOSALS`.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.agents import runner_events, tasks
from apps.agents.models import AgentRun, RunStatus
from apps.library.models import SubjectType
from apps.library.reading import held_stable_keys, summarised_stable_keys, unknown_provision_keys
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.shared.audit import Actor, ActorType
from apps.watch import keys as watch_keys, sources as watch_sources
from apps.watch.schemas import WatchSourceInput

BASELINE_DIR = Path(__file__).resolve().parents[1] / "library" / "baseline"
AGENT_KEY = "library-baseline"
# Who opens the runs and registers the sources: the command, or the beat.
RUN_ACTOR = Actor.system("file_library_baseline")
# The pages the watch should check for the baseline's records, beside its tranches.
SOURCES_FILE = "sources.json"
# The language order a registered source is read back in; nobody reads the answer here.
SOURCE_ORDER = ["en"]

INSTRUMENT = ProposalKind.NEW_INSTRUMENT.value
OBLIGATION = ProposalKind.NEW_OBLIGATION.value
SUMMARY = ProposalKind.NEW_INSTRUMENT_SUMMARY.value
PROVISION = ProposalKind.NEW_PROVISION.value
# The folder beside the tranches that holds each tranche's instrument summaries, by its name.
SUMMARIES_DIR = "summaries"
# The language the baseline's summaries are written in.
SUMMARY_LANGUAGE = "en"
# The folder that holds each tranche's provisions, the law's own words, by its name.
PROVISIONS_DIR = "provisions"
# The fields of a provision's file entry the door takes as they stand; the rest of the
# entry says where and when its text was read.
PROVISION_FIELDS = ("key", "instrument", "provisionKind", "refLabel", "heading", "texts", "originalLanguage", "isMachine", "officialLanguages", "obligations")


@dataclass(frozen=True)
class Entry:
    """One proposal the baseline asks for, as its file holds it. `instrument` is the stable
    key of the instrument it is or sits under."""

    tranche: str
    kind: str
    key: str
    instrument: str
    title: str
    payload: dict[str, Any]
    field_sources: dict[str, str]
    source_url: str
    source_label: str

    @property
    def retry_key(self) -> str:
        """The key this agent files the entry under: its stable key and a hash of all it says."""
        body = [self.kind, self.title, self.payload, self.field_sources, self.source_url, self.source_label]
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
        return f"baseline:{self.key}:{digest}"


@dataclass
class Report:
    """What one call did, per tranche and kind, and every entry the door refused. `waiting`
    counts the entries whose instrument, or for a provision whose duties, the library does
    not hold yet."""

    filed: Counter[tuple[str, str]] = field(default_factory=Counter)
    held: Counter[tuple[str, str]] = field(default_factory=Counter)
    open: Counter[tuple[str, str]] = field(default_factory=Counter)
    decided: Counter[tuple[str, str]] = field(default_factory=Counter)
    waiting: Counter[tuple[str, str]] = field(default_factory=Counter)
    refused: list[tuple[str, str, str]] = field(default_factory=list)
    runs: int = 0


def tranches(folder: Path | None = None) -> list[str]:
    return sorted(path.stem for path in (folder or BASELINE_DIR).glob("*.json") if path.name != SOURCES_FILE)


def load(only: Collection[str] = (), folder: Path | None = None) -> list[Entry]:
    """Every entry of the named tranches of `folder` (the baseline's own by default), or of
    all: each instrument, then its duties, its summary and its provisions."""
    folder = folder or BASELINE_DIR
    names = tranches(folder)
    unknown = sorted(set(only) - set(names))
    if unknown:
        raise ValidationError(f"No such tranche: {', '.join(unknown)}. Tranches: {', '.join(names)}.", code="validation_error")
    entries: list[Entry] = []
    for name in names:
        if only and name not in only:
            continue
        data = json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
        summaries = _summaries(folder, name)
        provisions = _provisions(folder, name)
        for item in data["instruments"]:
            payload = item["payload"]
            key = payload["key"]
            entries.append(_entry(name, INSTRUMENT, item, payload, key))
            for duty in item.get("obligations", []):
                entries.append(_entry(name, OBLIGATION, duty, {**duty["payload"], "instrument": key}, key))
            if key in summaries:
                summary = summaries[key]
                written = {
                    "title": f"Add a summary of {payload['shortName']}, {payload['officialRef']}",
                    "source": summary["source"],
                    "sourceLabel": summary["sourceLabel"],
                }
                body = {"instrument": key, "summaries": summary["text"], "originalLanguage": SUMMARY_LANGUAGE}
                entries.append(_entry(name, SUMMARY, written, body, key, key=key))
            for provision in provisions.get(key, []):
                written = {
                    "title": f"Add the text of {provision['refLabel']}, {payload['officialRef']}, as read on {provision['readOn']}",
                    "source": provision["source"],
                    "sourceLabel": provision["sourceLabel"],
                }
                # Copied, never reworded: a field left out or null (a heading) is the door's default.
                body = {wanted: provision[wanted] for wanted in PROVISION_FIELDS if provision.get(wanted) is not None}
                entries.append(_entry(name, PROVISION, written, body, key))
    return entries


def _summaries(folder: Path, tranche: str) -> dict[str, dict[str, Any]]:
    """The tranche's instrument summaries by instrument key, or none when it has no file."""
    path = folder / SUMMARIES_DIR / f"{tranche}.json"
    if not path.exists():
        return {}
    return {item["key"]: item for item in json.loads(path.read_text(encoding="utf-8"))["summaries"]}


def _provisions(folder: Path, tranche: str) -> dict[str, list[dict[str, Any]]]:
    """The tranche's provisions by the instrument each belongs to, in the file's order, or
    none when it has no file. One that names an instrument outside its tranche is the
    checker's to refuse and is never filed."""
    path = folder / PROVISIONS_DIR / f"{tranche}.json"
    found: dict[str, list[dict[str, Any]]] = {}
    if path.exists():
        for item in json.loads(path.read_text(encoding="utf-8"))["provisions"]:
            found.setdefault(item["instrument"], []).append(item)
    return found


def _entry(tranche: str, kind: str, item: dict[str, Any], payload: dict[str, Any], instrument: str, *, key: str = "") -> Entry:
    """An entry whose every sourced field names a page: its own in `fieldSources`, else the
    entry's `source`, the page the record is read from."""
    given: dict[str, str] = item.get("fieldSources", {})
    sourced = logic.sourced_fields(logic.parsed_payload(kind, payload))
    return Entry(
        tranche=tranche,
        kind=kind,
        key=key or payload["key"],
        instrument=instrument,
        title=item["title"],
        payload=payload,
        field_sources={**{name: item["source"] for name in sourced}, **given},
        source_url=item["source"],
        source_label=item["sourceLabel"],
    )


@dataclass(frozen=True)
class _Library:
    """What the library and the queue hold for the entries in hand, read in five queries
    (four while no entry is a provision): the stable keys held (lowercased), the keys open
    in the queue per kind, and the retry keys this agent ever filed."""

    instruments: set[str]
    obligations: set[str]
    summarised: set[str]
    provisions: set[str]
    open: set[tuple[str, str]]
    filed: set[str]


def _cited(entry: Entry) -> set[str]:
    """The duties a provision names as citing it, lowercased as the held keys are; none for
    every other kind."""
    return {key.lower() for key in entry.payload.get("obligations", [])} if entry.kind == PROVISION else set()


def _library(entries: list[Entry]) -> _Library:
    keys = {kind: {entry.key for entry in entries if entry.kind == kind} for kind in (INSTRUMENT, OBLIGATION, PROVISION)}
    parents = {entry.instrument for entry in entries if entry.kind != INSTRUMENT}
    cited = {key for entry in entries for key in _cited(entry)}
    open_rows = Proposal.objects.filter(status=ProposalStatus.OPEN.value, kind__in=(INSTRUMENT, OBLIGATION, SUMMARY, PROVISION))
    return _Library(
        instruments=held_stable_keys(SubjectType.INSTRUMENT.value, keys[INSTRUMENT] | parents),
        obligations=held_stable_keys(SubjectType.OBLIGATION.value, keys[OBLIGATION] | cited),
        summarised=summarised_stable_keys(),
        # A provision's key is lowercase wherever it came from: the door and the checker both hold it to that.
        provisions=keys[PROVISION] - unknown_provision_keys(keys[PROVISION]),
        # A summary is open under the instrument it is for; every other kind under its own key.
        open={
            (kind, summary_for if kind == SUMMARY else key)
            for kind, key, summary_for in open_rows.values_list("kind", "payload__key", "payload__instrument")
        },
        filed={
            key
            for key in Proposal.objects.filter(proposed_by_agent__key=AGENT_KEY, idempotency_key__startswith="baseline:").values_list(
                "idempotency_key", flat=True
            )
            if key
        },
    )


def _state(entry: Entry, library: _Library) -> str:
    """Where `entry` stands: `held`, `open`, `decided`, `waiting` for its instrument or, a
    provision, for a duty it names, or `due`."""
    held = {INSTRUMENT: library.instruments, OBLIGATION: library.obligations, SUMMARY: library.summarised, PROVISION: library.provisions}[entry.kind]
    if entry.key.lower() in held:
        return "held"
    if (entry.kind, entry.key) in library.open:
        return "open"
    if entry.retry_key in library.filed:
        return "decided"
    if entry.kind != INSTRUMENT and entry.instrument.lower() not in library.instruments:
        return "waiting"
    if not _cited(entry) <= library.obligations:
        return "waiting"
    return "due"


def file(*, only: Collection[str] = (), dry_run: bool = False, folder: Path | None = None, only_agent_confirmable: bool = False) -> Report:
    """File every due entry of the named tranches, or of all. A dry run files nothing and
    reports what a real one would. `folder` names another folder of tranches, as the E2E
    seed's fixture is. `only_agent_confirmable` leaves out the kinds only a person may
    approve, an instrument's summary (INV-09) and a provision (D-79), for a caller whose
    reviewer is an agent."""
    entries = [entry for entry in load(only, folder) if not only_agent_confirmable or entry.kind in logic.AGENT_CONFIRMABLE_KINDS]
    report = Report()
    library = _library(entries)
    due: list[Entry] = []
    for entry in entries:
        state = _state(entry, library)
        tally = (entry.tranche, entry.kind)
        if state == "due":
            due.append(entry)
        else:
            getattr(report, state)[tally] += 1
    if dry_run:
        report.filed.update((entry.tranche, entry.kind) for entry in due)
        return report
    for batch in _batches(due, settings.WATCH_RUN_MAX_PROPOSALS):
        _file_run(batch, report)
    return report


def _batches(entries: list[Entry], size: int) -> Iterator[list[Entry]]:
    for start in range(0, len(entries), size):
        yield entries[start : start + size]


def _file_run(batch: list[Entry], report: Report) -> None:
    """One run of the agent: opened, a transaction per entry, closed with what it filed."""
    with transaction.atomic():
        run = tasks.open_baseline_run(AGENT_KEY, actor=RUN_ACTOR)
    report.runs += 1
    filed = 0
    for entry in batch:
        try:
            with transaction.atomic():
                _file_one(entry, run)
        except ValidationError as refused:
            report.refused.append((entry.key, getattr(refused, "code", "") or "validation_error", " ".join(refused.messages)))
            continue
        report.filed[(entry.tranche, entry.kind)] += 1
        filed += 1
    runner_events.apply_event(RunnerEvent(run_id=run.id, status=RunStatus.SUCCEEDED, stats={"proposalsSubmitted": filed}))


def _file_one(entry: Entry, run: AgentRun) -> None:
    logic.create(
        kind=entry.kind,
        title=entry.title,
        payload=entry.payload,
        proposer=logic.Proposer(actor=Actor(kind=ActorType.AGENT, id=run.agent_id, label=AGENT_KEY), agent_id=run.agent_id),
        idempotency_key=entry.retry_key,
        agent_run_id=run.id,
        field_sources=entry.field_sources,
        source_label=entry.source_label,
        source_url=entry.source_url,
    )


def register_sources(folder: Path | None = None) -> int:
    """Register every source the baseline names that the registry does not hold by name,
    through the console's own writer (`apps.watch.sources.create_source`), so the watch
    agents check the pages the baseline's records came from (WAT-01). Returns how many it
    registered. A name already registered is left exactly as an editor may have changed it."""
    path = (folder or BASELINE_DIR) / SOURCES_FILE
    if not path.exists():
        return 0
    registered = 0
    for spec in json.loads(path.read_text(encoding="utf-8"))["sources"]:
        if watch_keys.source_with_name(spec["name"]) is not None:
            continue
        body = WatchSourceInput(
            name=spec["name"],
            url=spec["url"],
            kind=spec["kind"],
            authority_id=watch_keys.authority_named(spec["authority"] or ""),
            check_frequency="weekly",
        )
        watch_sources.create_source(actor=RUN_ACTOR, order=SOURCE_ORDER, body=body)
        registered += 1
    return registered
