"""The one door to a model (AUD-02, playbook 16).

`apps/shared/adapters/llm.py` moves prompts and knows nothing about logging. This module is
the only code allowed to call it, and every call it makes leaves an `ai_generation` row:
`generate` in the caller's own transaction once the model has answered, and `stream`, whose
words reach somebody as they arrive, in a transaction of its own however the call ends.
`apps/shared/tests_ai_wrapper.py` walks the production tree
and fails on any other module that imports or calls the adapter, so "every model call is
logged" is a fact a test keeps true rather than a habit a new caller can forget.

One door, not one per feature: the rule the wrapper carries for everybody is that the
prompt is never stored, never logged and never put in an audit summary — a hash of it is —
and that what comes back ships labelled, `status = draft`, until a person stands behind it.

Since D-66, what the wrapper does **not** do is draft the "So what?" of a change. The agent
that read the change writes those words and files them with the change, and the write
records the log row from what the agent reported; a second call from a handler of ours over
the same facts is a second moving part and a second cost. So this wrapper serves calls
bleqq itself makes — chunk 7's Ask is the first — and the log says which rows are which
through `modelMetadataReportedByAgent`.

**The bank's own switch.** A bank can switch its own AI features off (`tenant.ai_enabled`,
D-07, owner item 14): Ask, the drafts a model writes for it and, from chunk 11, its own
agents. The switch is read here, before the model is reached, and only when the caller's
transaction is in a bank's zone: a platform (library) run is in none, so bleqq's own watch
agents, which are part of the base package, never consult it and no bank can stop them.
The zone is the database's own setting, the one row-level security reads, and not the
Python-side mirror of it, which outlives the transaction that set it on a thread that
serves one request after another. A bank whose row cannot be read is treated as switched
off, because the switch is what decides whether a bank's own words leave it for a model.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.governance.ai_log import log_generation
from apps.governance.models import AiGeneration, AiPurpose
from apps.governance.schemas import AiCitation
from apps.shared import tenancy
from apps.shared.adapters.llm import Completion, LlmAdapter, get_llm
from apps.shared.adapters.llm import LlmError as LlmError
from apps.shared.adapters.llm import format_context as format_context
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

# How a streamed call ended when the model did not say, on its log row (`stop_reason`,
# D-82): the caller stopped reading first, or the model failed once asked. A call the model
# finished carries the provider's own stop reason instead.
ABORTED = "aborted"
FAILED = "failed"


@dataclass(frozen=True)
class Generation:
    """What a call produced and the log row that records it, so a caller can point at the
    row without reading the table back."""

    text: str
    generation: AiGeneration


def prompt_hash(system: str, prompt: str) -> str:
    """The only thing kept about a prompt. SHA-256 of the whole prompt, so two identical
    calls hash alike and nothing of a bank's own words can be read back out of the log
    (NFR-04, D-07)."""
    return hashlib.sha256(f"{system}\n\n{prompt}".encode()).hexdigest()


def ensure_enabled() -> None:
    """Refuse a model call for a bank that switched its own AI features off, before any
    model is reached. With no bank in the transaction's zone this is a platform call, and
    it passes: no bank's switch reaches bleqq's own agents (owner item 14)."""
    tenant_id = tenancy.database_tenant_id()
    if tenant_id is None:
        return
    enabled = Tenant.objects.filter(pk=tenant_id).values_list("ai_enabled", flat=True).first()  # ordering: pk lookup, at most one row
    if enabled is not True:
        raise ProblemError(
            status=403, code="feature_off", detail="Your organisation has switched its AI features off."
        )


def generate(
    *,
    purpose: AiPurpose,
    system: str,
    prompt: str,
    prompt_template: str,
    citations: Sequence[AiCitation],
    tenant_id: uuid.UUID | None = None,
    asker_id: uuid.UUID | None = None,
    subject_type: str = "",
    subject_id: uuid.UUID | None = None,
    max_tokens: int | None = None,
    llm: LlmAdapter | None = None,
) -> Generation:
    """Ask the model, then write the row, in the caller's transaction.

    The adapter raises `LlmError` when the model cannot answer; nothing is logged then:
    no word of the output reached anybody, and the row would share the caller's
    transaction, which the caller keeps or rolls back as that failure decides for its own
    work. The model and the version on the row are the provider's own, read off the
    response, which is what `modelMetadataReportedByAgent = False` means to a reader.
    """
    ensure_enabled()
    engine = llm if llm is not None else get_llm()
    completion = engine.complete(
        system=system, prompt=prompt, max_tokens=max_tokens or settings.LLM_MAX_TOKENS
    )
    row = log_generation(
        purpose=purpose,
        model=completion.model,
        model_version=completion.model_version,
        output=completion.text,
        citations=citations,
        tenant_id=tenant_id,
        asker_id=asker_id,
        subject_type=subject_type,
        subject_id=subject_id,
        prompt_template=prompt_template,
        prompt_hash=prompt_hash(system, prompt),
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        metadata_reported_by_agent=False,
        stop_reason=completion.stop_reason,
    )
    return Generation(text=completion.text, generation=row)


def stream(
    *,
    purpose: AiPurpose,
    system: str,
    prompt: str,
    prompt_template: str,
    cite: Callable[[str], Sequence[AiCitation]],
    tenant_id: uuid.UUID | None,
    asker_id: uuid.UUID | None,
    generation_id: uuid.UUID,
    max_tokens: int,
) -> Generator[str | Generation]:
    """Ask the model and hand back its words as they arrive, then the logged `Generation`.

    The switch is checked now, while the caller's request still holds its transaction and
    its tenant, and not when the first word is wanted: a refusal must be a status the
    caller can still send. What is returned is read later, as a streamed response is sent,
    which is after the request's own transaction has committed, so the row is written in a
    transaction of its own with the bank's zone activated for it.

    `cite` turns the finished text into what it rests on, because which passages an answer
    cites is only known once it is written; the row records those and nothing else. The
    row carries `generation_id`, the id the caller already gave the answer, so a reader's
    verdict on it finds its row, and the provider's own stop reason.

    Once the model has been asked, the call leaves its row however it ends (AUD-02, D-82),
    because the caller may already have shown its words to somebody. A model that fails
    raises `LlmError` after the row is written with `stop_reason = failed`; a caller that
    stops reading before the answer is finished, a reader closing the tab, closes what this
    returns, and the row is written with `stop_reason = aborted`. Either row holds the words
    written so far, what they cite and the model the call was addressed to, as a draft like
    any other; usage is left at nothing, because the provider reports it only with the last
    word. Closing this before it is first read asks no model and logs nothing.
    """
    ensure_enabled()
    engine = get_llm()

    def log(
        text: str, model: str, model_version: str, input_tokens: int, output_tokens: int, stop_reason: str
    ) -> AiGeneration:
        with transaction.atomic():
            if tenant_id is not None:
                tenancy.activate(tenant_id)
            return log_generation(
                purpose=purpose,
                model=model,
                model_version=model_version,
                output=text,
                citations=cite(text),
                tenant_id=tenant_id,
                asker_id=asker_id,
                prompt_template=prompt_template,
                prompt_hash=prompt_hash(system, prompt),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                generation_id=generation_id,
                stop_reason=stop_reason,
            )

    def streamed() -> Generator[str | Generation]:
        written: list[str] = []
        logged = False

        def cut_short(stop_reason: str) -> None:
            if not logged:
                log("".join(written), *engine.asked_model(), 0, 0, stop_reason)

        try:
            for event in engine.stream(system=system, prompt=prompt, max_tokens=max_tokens):
                if isinstance(event, Completion):
                    row = log(
                        event.text,
                        event.model,
                        event.model_version,
                        event.input_tokens,
                        event.output_tokens,
                        event.stop_reason,
                    )
                    logged = True
                    yield Generation(text=event.text, generation=row)
                else:
                    written.append(event)
                    yield event
        except LlmError:
            cut_short(FAILED)
            raise
        except GeneratorExit:
            cut_short(ABORTED)
            raise

    return streamed()
