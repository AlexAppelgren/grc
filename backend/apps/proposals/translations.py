"""The library's machine translations, filed through the proposal door (INV-05, I18N-01,
D-129).

A model is asked, once per record, for a shared instrument's or obligation's title and
summary in every live content language it lacks; the answer is filed as one
`new_translations` proposal of the platform agent `library-translator`. A person approves
it, and the rows stay machine-made, the original authoritative.

The answer is untrusted: one JSON object, exactly the languages asked, no blank text, at most
`LIBRARY_TRANSLATION_TEXT_MAX_CHARS`, or nothing is filed; then the proposal door checks it,
the injection screen included.

A record is asked once in the same words: skipped while a proposal is open or a call with the
same prompt hash (also the retry key) was made. A failed call is retried until
`LIBRARY_TRANSLATION_MAX_FAILURES` (review 2026-11-11 S-9). The beat queues at most
`LIBRARY_TRANSLATION_RUN_MAX` records; a per-record advisory lock keeps two tasks apart.
"""

from __future__ import annotations

import functools
import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.agents import runner_events, tasks as agent_tasks
from apps.agents.models import AgentRun, RunStatus
from apps.agents.seeds import SHIPPED
from apps.agents.seeds.definition import DEFINITIONS
from apps.governance import ai_log
from apps.governance.models import AiPurpose
from apps.library.models import SubjectType
from apps.library.reading import RecordTexts, record_texts, translatable_records
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.shared import ai
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.shared.audit import Actor, ActorType
from apps.shared.schemas import AiCitation
from apps.taxonomy.tenant_lists_logic import known_languages

logger = logging.getLogger(__name__)

AGENT_KEY = "library-translator"
VERSION = dict(SHIPPED)[AGENT_KEY]
PROMPT_TEMPLATE = f"{AGENT_KEY}/v{VERSION}"
KIND = ProposalKind.NEW_TRANSLATIONS.value
# Who opens the runs: the beat, or an approval's queued task.
RUN_ACTOR = Actor.system("library_translator")


@functools.cache
def system_prompt() -> str:
    """The agent's system prompt, its definition's own file."""
    return (DEFINITIONS / AGENT_KEY / f"v{VERSION}" / "prompt.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Ask:
    """What one model call asks about a record: the languages its title and its summary lack."""

    record: RecordTexts
    titles: tuple[str, ...]
    summaries: tuple[str, ...]

    @property
    def prompt(self) -> str:
        """The originals and the languages wanted, as one JSON document, so no text can pose as
        an instruction outside its own string."""
        record = self.record
        asked: dict[str, Any] = {}
        if self.titles:
            asked["title"] = {"language": record.title_original, "text": record.titles[record.title_original], "translateInto": list(self.titles)}
        if self.summaries:
            asked["summary"] = {"language": record.summary_original, "text": record.summaries[record.summary_original], "translateInto": list(self.summaries)}
        return json.dumps(asked, ensure_ascii=False, indent=1)

    @property
    def hash(self) -> str:
        """The call's content hash, as the AI output log stores it (`ai.prompt_hash`)."""
        return ai.prompt_hash(system_prompt(), self.prompt)


def asked(record: RecordTexts, live: set[str]) -> Ask | None:
    """What `record` lacks among the `live` content languages, or None when nothing: a text
    with no original has nothing to be translated from."""
    titles = tuple(sorted(live - set(record.titles))) if record.title_original else ()
    summaries = tuple(sorted(live - set(record.summaries))) if record.summary_original else ()
    return Ask(record, titles, summaries) if titles or summaries else None


def _settled() -> tuple[set[tuple[str, str]], set[str]]:
    """The records a translation proposal is open for, and the content hash of every call
    this agent's prompt has made."""
    open_rows = Proposal.objects.filter(kind=KIND, status=ProposalStatus.OPEN.value).values_list("payload__target", "payload__key")
    return set(open_rows), ai_log.prompt_hashes(
        purpose=AiPurpose.TRANSLATION, prompt_template=PROMPT_TEMPLATE, failures_allowed=settings.LIBRARY_TRANSLATION_MAX_FAILURES
    )


def _due(ask: Ask | None, open_records: set[tuple[str, str]], made: set[str]) -> bool:
    return ask is not None and (ask.record.target, ask.record.key) not in open_records and ask.hash not in made


def due(limit: int) -> list[tuple[str, uuid.UUID]]:
    """The records, at most `limit`, that lack a live content language and that have no
    translation proposal open and were never asked about in the same words, instruments first."""
    live = known_languages()
    open_records, made = _settled()
    found: list[tuple[str, uuid.UUID]] = []
    for record in translatable_records(timezone.localdate()):
        if len(found) == limit:
            break
        if _due(asked(record, live), open_records, made):
            found.append((record.target, record.id))
    return found


@contextmanager
def _held(target: str, record_id: uuid.UUID) -> Iterator[bool]:
    """Whether this task holds the record, for as long as it runs: a second task for it,
    from an overlapping beat or an approval, answers False and asks nothing."""
    name = f"library-translation:{target}:{record_id}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [name])
        held = bool(cursor.fetchone()[0])
    try:
        yield held
    finally:
        if held:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [name])


def _exact(answer: Any, languages: tuple[str, ...], what: str) -> dict[str, str]:
    """One part of the answer: exactly the languages asked, each a text that is not blank and
    not longer than the cap, or a refusal naming what is wrong."""
    if not isinstance(answer, dict) or set(answer) != set(languages) or not all(isinstance(text, str) for text in answer.values()):
        raise ValidationError(f"The answer's {what} are not exactly the languages asked for.", code="invalid_answer")
    cleaned = {language: text.strip() for language, text in answer.items()}
    if not all(cleaned.values()) or any(len(text) > settings.LIBRARY_TRANSLATION_TEXT_MAX_CHARS for text in cleaned.values()):
        raise ValidationError(f"An answer's {what} is blank or too long.", code="invalid_answer")
    return cleaned


def parsed(text: str, ask: Ask) -> tuple[dict[str, str], dict[str, str]]:
    """The model's answer as the translated titles and summaries, read strictly: one JSON
    object holding `titles` and `summaries` and nothing else, or 422 `invalid_answer`."""
    try:
        answer = json.loads(text)
    except ValueError:
        raise ValidationError("The answer is not one JSON object.", code="invalid_answer") from None
    if not isinstance(answer, dict) or set(answer) != {"titles", "summaries"}:
        raise ValidationError("The answer holds something other than titles and summaries.", code="invalid_answer")
    return _exact(answer["titles"], ask.titles, "titles"), _exact(answer["summaries"], ask.summaries, "summaries")


def _file(ask: Ask, titles: dict[str, str], summaries: dict[str, str], run: AgentRun, model: str) -> Proposal:
    record = ask.record
    payload: dict[str, Any] = {"target": record.target, "key": record.key, "titles": titles, "summaries": summaries}
    if titles:
        payload["titlesFrom"] = record.title_original
    if summaries:
        payload["summariesFrom"] = record.summary_original
        payload["version"] = record.version
    named = record.short_name if record.target == SubjectType.INSTRUMENT.value else f"{record.key} ({record.short_name})"
    proposal, _created = logic.create(
        kind=KIND,
        title=f"Translate {named} into {', '.join(sorted({*titles, *summaries}))}",
        payload={name: value for name, value in payload.items() if value is not None},
        proposer=logic.Proposer(actor=Actor(kind=ActorType.AGENT, id=run.agent_id, label=AGENT_KEY), agent_id=run.agent_id),
        idempotency_key=f"translation:{record.target}:{record.key}:{ask.hash[:32]}",
        agent_run_id=run.id,
        model=model,
        field_sources={**{f"titles.{language}": record.source_url for language in titles}, **{f"summaries.{language}": record.source_url for language in summaries}},
        source_label=record.short_name,
        source_url=record.source_url,
    )
    return proposal


def _close(run: AgentRun, status: RunStatus, *, filed: int, generated: ai.Generation | None = None, error: str = "") -> None:
    logged = None if generated is None else generated.generation
    runner_events.apply_event(
        RunnerEvent(
            run_id=run.id,
            status=status,
            stats={"modelCalls": 0 if logged is None else 1, "proposalsSubmitted": filed},
            tokens_in=None if logged is None else logged.input_tokens,
            tokens_out=None if logged is None else logged.output_tokens,
            error=error,
        )
    )


def translate(target: str, record_id: uuid.UUID) -> str:
    """Ask for one record's missing translations and file them, and say what happened:
    `filed`, `refused` (the answer was not usable, or the door refused it), `failed` (the
    model did not answer), or `skipped` (another task holds the record, it is not a shared
    record in force, or it is not due)."""
    with _held(target, record_id) as held:
        if not held:
            return "skipped"
        try:
            record = record_texts(target, timezone.localdate(), record_id=record_id)
        except ValidationError:
            return "skipped"
        ask = asked(record, known_languages())
        if ask is None or not _due(ask, *_settled()):
            return "skipped"
        with transaction.atomic():
            run = agent_tasks.open_baseline_run(AGENT_KEY, actor=RUN_ACTOR)
        # The failed call's row is written in a block of its own and kept, so the error is caught
        # inside the transaction rather than rolling it back (`ai.generate`).
        generated: ai.Generation | None
        with transaction.atomic():
            try:
                generated = ai.generate(
                    purpose=AiPurpose.TRANSLATION,
                    system=system_prompt(),
                    prompt=ask.prompt,
                    prompt_template=PROMPT_TEMPLATE,
                    citations=[AiCitation(label=record.short_name, url=record.source_url)],
                    subject_type=record.target,
                    subject_id=record.id,
                    agent_run_id=run.id,
                )
            except ai.LlmError:
                generated = None
        if generated is None:
            _close(run, RunStatus.FAILED, filed=0, error="The model did not answer; the record is asked again on a later run, up to the failure limit.")
            logger.warning("library translation not answered", extra={"record_id": str(record.id), "agent_run_id": str(run.id)})
            return "failed"
        try:
            titles, summaries = parsed(generated.text, ask)
            with transaction.atomic():
                _file(ask, titles, summaries, run, generated.generation.model)
        except ValidationError as refused:
            code = getattr(refused, "code", "") or "validation_error"
            _close(run, RunStatus.SUCCEEDED, filed=0, generated=generated, error=f"The model's answer was not filed: {code}.")
            logger.info("library translation refused", extra={"record_id": str(record.id), "agent_run_id": str(run.id), "code": code})
            return "refused"
        _close(run, RunStatus.SUCCEEDED, filed=1, generated=generated)
        return "filed"
