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
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from django.conf import settings

from apps.governance.ai_log import log_generation
from apps.governance.models import AiGeneration, AiPurpose
from apps.governance.schemas import AiCitation
from apps.shared.adapters.llm import LlmAdapter, get_llm


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
