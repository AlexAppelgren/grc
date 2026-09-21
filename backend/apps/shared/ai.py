"""The one door to a model (AUD-02, playbook 16).

`apps/shared/adapters/llm.py` moves prompts and knows nothing about logging. This module is
the only code allowed to call it, and every call it makes leaves an `ai_generation` row in
the caller's own transaction. `apps/shared/tests_ai_wrapper.py` walks the production tree
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
agents. The switch is read here, before the model is reached, and only when a tenant is
active: a platform (library) run has none, so bleqq's own watch agents, which are part of
the base package, never consult it and no bank can stop them. A bank whose row cannot be
read is treated as switched off, because the switch is what decides whether a bank's own
words leave it for a model.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Iterator, Sequence
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

FEATURE_OFF = "feature_off"


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
    model is reached. With no tenant active this is a platform call, and it passes: no
    bank's switch reaches bleqq's own agents (owner item 14)."""
    tenant_id = tenancy.active_tenant_id()
    if tenant_id is None:
        return
    enabled = Tenant.objects.filter(pk=tenant_id).values_list("ai_enabled", flat=True).first()  # ordering: pk lookup, at most one row
    if enabled is not True:
        raise ProblemError(
            status=403, code=FEATURE_OFF, detail="Your organisation has switched its AI features off."
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

    The adapter raises `LlmError` when the model cannot answer; nothing is logged then,
    because no output exists to label, and the caller decides whether that failure blocks
    its own work. The model and the version on the row are the provider's own, read off the
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
) -> Iterator[str | Generation]:
    """Ask the model and hand back its words as they arrive, then the logged `Generation`.

    The switch is checked now, while the caller's request still holds its transaction and
    its tenant, and not when the first word is wanted: a refusal must be a status the
    caller can still send. What is returned is read later, as a streamed response is sent,
    which is after the request's own transaction has committed, so the row is written in a
    transaction of its own with the bank's zone activated for it.

    `cite` turns the finished text into what it rests on, because which passages an answer
    cites is only known once it is written; the row records those and nothing else. The
    row carries `generation_id`, the id the caller already gave the answer, so a reader's
    verdict on it finds its row. A model that fails raises `LlmError` and logs nothing.
    """
    ensure_enabled()
    return _streamed(
        purpose=purpose,
        system=system,
        prompt=prompt,
        prompt_template=prompt_template,
        cite=cite,
        tenant_id=tenant_id,
        asker_id=asker_id,
        generation_id=generation_id,
        max_tokens=max_tokens,
    )


def _streamed(
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
) -> Iterator[str | Generation]:
    for event in get_llm().stream(system=system, prompt=prompt, max_tokens=max_tokens):
        if not isinstance(event, Completion):
            yield event
            continue
        with transaction.atomic():
            if tenant_id is not None:
                tenancy.activate(tenant_id)
            row = log_generation(
                purpose=purpose,
                model=event.model,
                model_version=event.model_version,
                output=event.text,
                citations=cite(event.text),
                tenant_id=tenant_id,
                asker_id=asker_id,
                prompt_template=prompt_template,
                prompt_hash=prompt_hash(system, prompt),
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                generation_id=generation_id,
            )
        yield Generation(text=event.text, generation=row)
