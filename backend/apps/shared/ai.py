"""The one door to a model (AUD-02, playbook 16).

`apps/shared/adapters/llm.py` moves prompts and knows nothing about logging. This module is
the only code allowed to call it (apps/shared/tests_ai_wrapper.py), and every call leaves an
`ai_generation` row: `generate` in the caller's transaction once answered or in a block of
its own when the model failed, `stream` in a transaction of its own however it ends. The
prompt is never stored or logged, only its hash, and the answer ships as `status = draft`
until a person stands behind it. The "So what?" of a change is the agent's own words (D-66),
not a call made here.

**The bank's own switch** (`tenant.ai_enabled`, D-07): read here, before the model, when the
transaction is in a bank's zone, as the database's setting rather than the Python mirror. A
platform run is in no zone, so no bank can stop bleqq's own watch agents. A bank whose row
cannot be read is treated as switched off.

**A bank's own record is never a model input** (INV-07, OWN-04, D-57): a call whose subject is
a library record is made only when that record reads, in the call's zone, as shared; anything
else raises before any model is asked, and no row is written.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.governance import ai_log
from apps.governance.ai_log import log_generation
from apps.governance.models import AiGeneration, AiPurpose
from apps.governance.schemas import AiCitation
from apps.library.models import Instrument, Obligation, Provision, SubjectType
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
FAILED = ai_log.FAILED
# How many characters of a prompt one input token stands for, to estimate what a failed call
# cost when the provider reported no usage (S-9): the usual rule of thumb for the languages the
# library is written in, so a failure counts against a cap rather than as free.
CHARS_PER_TOKEN = 4


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


class PrivateRecordRefused(RuntimeError):
    """A model call named a bank's own library record, or one it could not read as shared,
    as its subject (INV-07, D-57)."""


def refuse_private(subject_type: str, subject_id: uuid.UUID | None) -> None:
    """Refuse a call about a library record unless it reads as a shared one. A subject
    outside the library (a registered change, an answer) is not this rule's to judge."""
    shared = {
        SubjectType.INSTRUMENT.value: Instrument.objects.filter(owner_tenant__isnull=True),
        SubjectType.OBLIGATION.value: Obligation.objects.filter(
            owner_tenant__isnull=True, instrument__owner_tenant__isnull=True
        ),
        SubjectType.PROVISION.value: Provision.objects.filter(instrument__owner_tenant__isnull=True),
    }.get(subject_type)
    if shared is not None and (subject_id is None or not shared.filter(pk=subject_id).exists()):
        raise PrivateRecordRefused(
            f"A model call about {subject_type} {subject_id} was refused: a bank's own record, "
            "and anything not readable as a shared one, never reaches a model (INV-07, D-57)."
        )


def cost_minor(input_tokens: int, output_tokens: int) -> int:
    """What a call cost, in minor units, at `LLM_PRICE_*_MINOR_PER_MTOK`, rounded up so a call
    that spent anything never reads as free."""
    spent = input_tokens * settings.LLM_PRICE_INPUT_MINOR_PER_MTOK + output_tokens * settings.LLM_PRICE_OUTPUT_MINOR_PER_MTOK
    return math.ceil(spent / 1_000_000)


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
    deadline_s: float | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> Generation:
    """Ask the model, then write the row, in the caller's transaction.

    A call that fails with `LlmError` may still have cost tokens, so it is logged all the same
    (review 2026-11-11 S-9): `stop_reason = failed`, no output, the model addressed and the
    input cost estimated (`CHARS_PER_TOKEN`), in a savepoint of its own, then the error is
    raised again. A finished call's row carries the provider's own model and version.

    A bank's own library record as subject is refused first (`refuse_private`). `deadline_s`
    shortens the adapter's deadline; the row carries `cost_minor` and the agent run, if any.
    """
    refuse_private(subject_type, subject_id)
    ensure_enabled()
    engine = llm if llm is not None else get_llm()
    try:
        completion = engine.complete(
            system=system, prompt=prompt, max_tokens=max_tokens or settings.LLM_MAX_TOKENS, deadline_s=deadline_s
        )
    except LlmError:
        model, model_version = engine.asked_model()
        with transaction.atomic():
            log_generation(
                purpose=purpose,
                model=model,
                model_version=model_version,
                output="",
                citations=citations,
                tenant_id=tenant_id,
                agent_run_id=agent_run_id,
                asker_id=asker_id,
                subject_type=subject_type,
                subject_id=subject_id,
                prompt_template=prompt_template,
                prompt_hash=prompt_hash(system, prompt),
                cost_minor=cost_minor(math.ceil(len(system + prompt) / CHARS_PER_TOKEN), 0),
                metadata_reported_by_agent=False,
                stop_reason=FAILED,
            )
        raise
    row = log_generation(
        purpose=purpose,
        model=completion.model,
        model_version=completion.model_version,
        output=completion.text,
        citations=citations,
        tenant_id=tenant_id,
        agent_run_id=agent_run_id,
        asker_id=asker_id,
        subject_type=subject_type,
        subject_id=subject_id,
        prompt_template=prompt_template,
        prompt_hash=prompt_hash(system, prompt),
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        cost_minor=cost_minor(completion.input_tokens, completion.output_tokens),
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

    The switch is checked now, while the request still holds its transaction and tenant, so a
    refusal is a status the caller can send. The row is written later, after the request
    committed, in a transaction of its own with the bank's zone activated.

    `cite` turns the finished text into what it rests on; the row records those, the caller's
    `generation_id` and the provider's stop reason.

    Once asked, the call leaves its row however it ends (AUD-02, D-82): a failure writes
    `stop_reason = failed` and raises `LlmError`; a reader who stops early writes `aborted`.
    Either row holds the words so far as a draft, with no usage. Closing this before the first
    read asks no model and logs nothing.
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
