"""The only writer of `ai_generation` (AUD-02, ruling 1).

Every model call the product makes leaves a row here, and a row is written nowhere else:
`apps/governance/tests_ai_log.py` walks the production tree and fails on any other module
that creates one. One writer is what makes "every model output is logged" a fact rather
than a habit, and it is the place the three rules about the log live:

- **No prompt and no output text ever leaves this row.** The prompt is stored as a hash
  and a template name; the output is stored because AUD-02 asks for it and because a
  confirmation must be a confirmation of something, but nothing here logs, reports or
  puts either in an audit summary (NFR-04, playbook 4.7).
- **A row is written in the caller's own transaction**, so a rolled-back write leaves no
  claim that a model was asked something.
- **A row ships as `draft`.** AI output stays labelled until a person confirms it, and
  nothing in chunk 5 moves that state: a bank's confirmation of a "So what?" lives on its
  own `change_case`, because the library's row has no tenant and the split write policy
  refuses a bank session that reaches for it (ruling I).

Where the model metadata comes from differs by purpose, and the reader is told which:
`apps/shared/ai.py` observes it, because it made the call, while a "So what?" filed by an
agent with the change it read is metadata that agent reported about itself (D-66).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection

from apps.governance.models import AiGeneration, AiPurpose, AiStatus
from apps.governance.schemas import AiCitation, AiGenerationRow


class NotInTransaction(RuntimeError):
    """`log_generation()` was called outside a transaction, so the row could commit alone
    while the write that caused it rolled back."""


def log_generation(
    *,
    purpose: AiPurpose,
    model: str,
    model_version: str,
    output: str,
    citations: Sequence[AiCitation],
    tenant_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
    asker_id: uuid.UUID | None = None,
    subject_type: str = "",
    subject_id: uuid.UUID | None = None,
    prompt_template: str = "",
    prompt_hash: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_minor: int = 0,
    metadata_reported_by_agent: bool = False,
) -> AiGeneration:
    """Write one row for one model call, in the caller's transaction.

    `model` and `model_version` are required in words as well as in the signature: a log
    that cannot say which machine wrote something is not the log AUD-02 asks for, and a
    caller that has no version reports the one it has rather than an empty string.

    The output is stored up to `AI_GENERATION_OUTPUT_MAX_CHARS`. Model output is untrusted
    text off a network, so the cap is at the boundary rather than left to the provider's
    own token limit, and a truncated row is still a true record of what was said first.
    """
    if not connection.in_atomic_block:
        raise NotInTransaction(
            "log_generation() must run inside the transaction of the call it records; "
            "requests run under ATOMIC_REQUESTS, tasks use @tenant_task or transaction.atomic()."
        )
    if not model.strip() or not model_version.strip():
        raise ValidationError(
            "A model call is logged with the model and the model version behind it.",
            code="validation_error",
        )
    return AiGeneration.objects.create(
        tenant_id=tenant_id,
        agent_run_id=agent_run_id,
        asker_id=asker_id,
        purpose=purpose.value,
        subject_type=subject_type,
        subject_id=subject_id,
        model=model,
        model_version=model_version,
        model_metadata_reported_by_agent=metadata_reported_by_agent,
        prompt_template=prompt_template,
        prompt_hash=prompt_hash,
        output=output[: settings.AI_GENERATION_OUTPUT_MAX_CHARS],
        citations=[citation.model_dump(by_alias=True) for citation in citations],
        status=AiStatus.DRAFT.value,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_minor=cost_minor,
    )


def generations_for(
    *, purpose: str | None, status: str | None, limit: int, offset: int
) -> tuple[list[AiGeneration], int]:
    """The reader's own rows and the library's, newest first, with the total.

    Row-level security has already cut the table to the session's own tenant plus the rows
    with no tenant, so this adds the filters and the page and nothing about who may see
    what: the zone is the database's answer, not a `WHERE` clause a later edit could drop.
    """
    rows = AiGeneration.objects.all()
    if purpose:
        rows = rows.filter(purpose=purpose)
    if status:
        rows = rows.filter(status=status)
    rows = rows.order_by("-created_at", "id")
    return list(rows[offset : offset + limit]), rows.count()


def generation_row(row: AiGeneration, tenant_id: uuid.UUID | None) -> AiGenerationRow:
    """One log row as a reader sees it. `tenantScoped` is computed against the reader's own
    tenant rather than stored, because the same library row is shared and is nobody's."""
    return AiGenerationRow(
        id=row.id,
        purpose=row.purpose,
        model=row.model,
        model_version=row.model_version,
        model_metadata_reported_by_agent=row.model_metadata_reported_by_agent,
        prompt_template=row.prompt_template,
        prompt_hash=row.prompt_hash,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        output=row.output,
        citations=[AiCitation(**citation) for citation in row.citations],
        status=row.status,
        reviewed_at=row.reviewed_at,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        tenant_scoped=row.tenant_id is not None and row.tenant_id == tenant_id,
        created_at=row.created_at,
    )
