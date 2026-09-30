"""The library baseline, filed through the proposal door (ADR 0065, D-118; PRO-01, INV-01,
INV-03).

`apps/library/baseline/` holds the shared library's starting inventory as reviewed data: one
entry per instrument and per duty, each already in the shape `POST /proposals` takes. This
module files what the library does not hold as proposals of the platform agent
`library-baseline`, under runs of that agent it opens with no key and hands to no runner:
`manage.py file_library_baseline` is that agent's runner, and it closes each run through the
runner-event path like any runner. It decides nothing. A second, independent principal
approves each proposal in the console queue, and `proposal_four_eyes` refuses this agent as
its own reviewer.

What one call files:

- a `new_instrument` for every instrument whose stable key the library does not hold;
- a `new_obligation` for every duty whose instrument the library holds and whose key it does
  not, so a duty is filed on the first call after its instrument is approved;
- never an entry open in the queue under the same stable key, whoever filed it;
- never an entry this agent filed before unchanged: the retry key carries the entry's
  content hash, so a rejected entry stays rejected until the baseline says something new
  about it, and a corrected one is filed again.

Each entry is filed in a transaction of its own, so an entry the door refuses (its code and
sentence are reported) files nothing and stops nothing else. Filings go in runs of at most
`WATCH_RUN_MAX_PROPOSALS`, the budget every run's proposals are held to.
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
from apps.library.reading import stable_key_taken
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.shared.audit import Actor, ActorType

BASELINE_DIR = Path(__file__).resolve().parents[1] / "library" / "baseline"
AGENT_KEY = "library-baseline"
# Who opens the runs: the command, run by a platform operator in the API's shell.
RUN_ACTOR = Actor.system("file_library_baseline")

INSTRUMENT = ProposalKind.NEW_INSTRUMENT.value
OBLIGATION = ProposalKind.NEW_OBLIGATION.value


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
    """What one call did, per tranche and kind, and every entry the door refused."""

    filed: Counter[tuple[str, str]] = field(default_factory=Counter)
    held: Counter[tuple[str, str]] = field(default_factory=Counter)
    open: Counter[tuple[str, str]] = field(default_factory=Counter)
    decided: Counter[tuple[str, str]] = field(default_factory=Counter)
    waiting: Counter[str] = field(default_factory=Counter)
    refused: list[tuple[str, str, str]] = field(default_factory=list)
    runs: int = 0


def tranches() -> list[str]:
    return sorted(path.stem for path in BASELINE_DIR.glob("*.json"))


def load(only: Collection[str] = ()) -> list[Entry]:
    """Every entry of the named tranches, or of all, instruments before their duties."""
    unknown = sorted(set(only) - set(tranches()))
    if unknown:
        raise ValidationError(f"No such tranche: {', '.join(unknown)}. Tranches: {', '.join(tranches())}.", code="validation_error")
    entries: list[Entry] = []
    for name in tranches():
        if only and name not in only:
            continue
        data = json.loads((BASELINE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        for item in data["instruments"]:
            key = item["payload"]["key"]
            entries.append(_entry(name, INSTRUMENT, item, item["payload"], key))
            for duty in item.get("obligations", []):
                entries.append(_entry(name, OBLIGATION, duty, {**duty["payload"], "instrument": key}, key))
    return entries


def _entry(tranche: str, kind: str, item: dict[str, Any], payload: dict[str, Any], instrument: str) -> Entry:
    """An entry whose every sourced field names a page: its own in `fieldSources`, else the
    entry's `source`, the page the record is read from."""
    given: dict[str, str] = item.get("fieldSources", {})
    sourced = logic.sourced_fields(logic.parsed_payload(kind, payload))
    return Entry(
        tranche=tranche,
        kind=kind,
        key=payload["key"],
        instrument=instrument,
        title=item["title"],
        payload=payload,
        field_sources={**{name: item["source"] for name in sourced}, **given},
        source_url=item["source"],
        source_label=item["sourceLabel"],
    )


def _state(entry: Entry, agent_filed: set[str]) -> str:
    """Where `entry` stands: `held`, `open`, `decided`, `waiting` for its instrument, or `due`."""
    subject = SubjectType.INSTRUMENT.value if entry.kind == INSTRUMENT else SubjectType.OBLIGATION.value
    if stable_key_taken(subject, entry.key):
        return "held"
    if Proposal.objects.filter(kind=entry.kind, status=ProposalStatus.OPEN.value, payload__key=entry.key).exists():
        return "open"
    if entry.retry_key in agent_filed:
        return "decided"
    if entry.kind == OBLIGATION and not stable_key_taken(SubjectType.INSTRUMENT.value, entry.instrument):
        return "waiting"
    return "due"


def file(*, only: Collection[str] = (), dry_run: bool = False) -> Report:
    """File every due entry of the named tranches, or of all. A dry run files nothing and
    reports what a real one would."""
    entries = load(only)
    report = Report()
    agent_filed = {
        key
        for key in Proposal.objects.filter(proposed_by_agent__key=AGENT_KEY, idempotency_key__startswith="baseline:").values_list(
            "idempotency_key", flat=True
        )
        if key
    }
    due: list[Entry] = []
    for entry in entries:
        state = _state(entry, agent_filed)
        tally = (entry.tranche, entry.kind)
        if state == "due":
            due.append(entry)
        elif state == "waiting":
            report.waiting[entry.tranche] += 1
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
