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
  refuses a bank session that reaches for it (ruling I). The read shows each bank that
  confirmation as the row's review state, computed and never stored (`_reviewed`, D-62).

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
from django.db.models import Case, CharField, DateTimeField, Exists, F, OuterRef, Q, QuerySet, Subquery, UUIDField, Value, When
from django.db.models.functions import Left

from apps.cases.models import ChangeCase
from apps.governance.models import AiGeneration, AiPurpose, AiStatus
from apps.governance.schemas import AiCitation, AiGenerationQuery, AiGenerationReviewer, AiGenerationRow


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
    generation_id: uuid.UUID | None = None,
    stop_reason: str = "",
) -> AiGeneration:
    """Write one row for one model call, in the caller's transaction.

    `model` and `model_version` are required in words as well as in the signature: a log
    that cannot say which machine wrote something is not the log AUD-02 asks for, and a
    caller that has no version reports the one it has rather than an empty string.

    The output is stored up to `AI_GENERATION_OUTPUT_MAX_CHARS`. Model output is untrusted
    text off a network, so the cap is at the boundary rather than left to the provider's
    own token limit, and a truncated row is still a true record of what was said first.

    `generation_id` is for a caller that named its output before the model finished: an
    Ask answer carries its id from the stream's first event, so a reader's verdict on it
    can find this row (`rateAnswer`).

    `stop_reason` is how the call ended, for a call bleqq made and watched end
    (`apps/shared/ai.py`); an agent's filing leaves it empty.
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
        id=generation_id or uuid.uuid4(),
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
        stop_reason=stop_reason,
    )


def answer_of(answer_id: uuid.UUID, tenant_id: uuid.UUID, *, asker_id: uuid.UUID) -> AiGeneration | None:
    """One Ask answer `asker_id` was given in their bank, by the id its stream gave it, or
    nothing. An id of another bank's answer is nothing too: row-level security has already
    hidden it, and the tenant is named here as well so a query written before that policy
    could not reach it. A colleague's answer is nothing as well, so nobody replaces the
    verdict of the person who asked (hardening H48)."""
    return AiGeneration.objects.filter(
        pk=answer_id, tenant_id=tenant_id, asker_id=asker_id, purpose=AiPurpose.ANSWER.value
    ).first()  # ordering: pk lookup, at most one row


def set_feedback(row: AiGeneration, *, feedback: str, note: str) -> None:
    """A reader's verdict on an answer (AUD-02, SRC-05), on its row. The caller writes the
    audit row that goes with it (`apps/search/ask.py::rate_answer`), in the same
    transaction; the note stays here, beside the answer, and never reaches the audit."""
    row.feedback = feedback
    row.feedback_note = note
    row.save(update_fields=["feedback", "feedback_note"])


def logged_for(*, agent_run_id: uuid.UUID, purpose: AiPurpose, subject_type: str, subject_id: uuid.UUID) -> bool:
    """Whether this run has already logged a call of this purpose about this subject, read
    here so the module that writes the log is the one that knows its shape (AUD-02). A
    caller asks it to tell a retry from a new model call (D-80)."""
    return AiGeneration.objects.filter(
        agent_run_id=agent_run_id, purpose=purpose.value, subject_type=subject_type, subject_id=subject_id
    ).exists()


def generations_for(
    *, tenant_id: uuid.UUID | None, filters: AiGenerationQuery, limit: int, offset: int
) -> tuple[list[AiGeneration], int]:
    """The reader's own rows and the library's, newest first, with the total.

    Row-level security has already cut the table to the session's own tenant plus the rows
    with no tenant, so this adds the filters and the page and nothing about who may see
    what: the zone is the database's answer, not a `WHERE` clause a later edit could drop.
    The `status` filter reads the review state as this reader sees it (`_reviewed`).
    """
    rows = _reviewed(AiGeneration.objects.all(), tenant_id)
    if filters.purpose:
        rows = rows.filter(purpose=filters.purpose)
    if filters.status:
        rows = rows.filter(Q(review_status=filters.status))
    if filters.subject_id:
        rows = rows.filter(subject_id=filters.subject_id)
    rows = rows.order_by("-created_at", "id")
    return list(rows[offset : offset + limit]), rows.count()


def _reviewed(rows: QuerySet[AiGeneration], tenant_id: uuid.UUID | None) -> QuerySet[AiGeneration]:
    """Each row annotated with its review state, reviewer and time as the reading bank sees
    them, in the one query that pages it.

    A bank's own row carries its own. A library "So what?" is one row every bank reads, and
    no bank may move it (ruling I), so its review state is the reading bank's own, taken
    from that bank's case for the change (`so_what_confirmed_by`, `so_what_confirmed_at`)
    and never written anywhere shared (D-62). The case settles the newest draft of the
    change logged by the time it was confirmed: that row reads `confirmed` when the bank's
    words are still the draft's and `edited` when the bank rewrote them. Any other draft of
    the change reads `draft`, because nobody at that bank stood behind those words.
    """
    so_what = AiPurpose.SO_WHAT.value
    confirmed_case = ChangeCase.objects.filter(
        Q(tenant_id=tenant_id), change_id=OuterRef("subject_id"), so_what_confirmed=True
    )
    rows = rows.annotate(
        case_confirmed_at=Subquery(confirmed_case.values("so_what_confirmed_at")[:1]),
        case_text=Subquery(confirmed_case.values("so_what_text")[:1]),
        case_reviewer_id=Subquery(confirmed_case.values("so_what_confirmed_by_id")[:1]),
        case_reviewer_name=Subquery(confirmed_case.values("so_what_confirmed_by__name")[:1]),
    )
    superseded = AiGeneration.objects.filter(
        tenant__isnull=True, purpose=so_what, subject_id=OuterRef("subject_id"), created_at__lte=OuterRef("case_confirmed_at")
    ).filter(Q(created_at__gt=OuterRef("created_at")) | Q(created_at=OuterRef("created_at"), id__lt=OuterRef("id")))
    library_so_what = Q(tenant__isnull=True, purpose=so_what)
    settled = library_so_what & Q(case_confirmed_at__gte=F("created_at"), superseded=False)
    # The log keeps an output up to its cap, so the bank's words are compared up to it too.
    cap = settings.AI_GENERATION_OUTPUT_MAX_CHARS
    return rows.annotate(superseded=Exists(superseded), case_text_drafted=Left("case_text", cap)).annotate(
        review_status=Case(
            When(settled & Q(case_text_drafted=F("output")), then=Value(AiStatus.CONFIRMED.value)),
            When(settled, then=Value(AiStatus.EDITED.value)),
            When(library_so_what, then=Value(AiStatus.DRAFT.value)),
            default=F("status"),
            output_field=CharField(),
        ),
        review_by_id=Case(
            When(settled, then=F("case_reviewer_id")),
            When(library_so_what, then=None),
            default=F("reviewed_by_id"),
            output_field=UUIDField(),
        ),
        review_by_name=Case(
            When(settled, then=F("case_reviewer_name")),
            When(library_so_what, then=None),
            default=F("reviewed_by__name"),
            output_field=CharField(),
        ),
        review_at=Case(
            When(settled, then=F("case_confirmed_at")),
            When(library_so_what, then=None),
            default=F("reviewed_at"),
            output_field=DateTimeField(),
        ),
    )


def generation_row(row: AiGeneration, tenant_id: uuid.UUID | None) -> AiGenerationRow:
    """One log row as a reader sees it, from a row `generations_for` annotated.
    `tenantScoped` is computed against the reader's own tenant rather than stored, because
    the same library row is shared and is nobody's; so are the review fields (`_reviewed`)."""
    review = {field: getattr(row, f"review_{field}") for field in ("status", "by_id", "by_name", "at")}
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
        status=review["status"],
        reviewed_by=None if review["by_id"] is None else AiGenerationReviewer(id=review["by_id"], name=review["by_name"]),
        reviewed_at=review["at"],
        feedback=row.feedback,
        feedback_note=row.feedback_note,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        stop_reason=row.stop_reason,
        tenant_scoped=row.tenant_id is not None and row.tenant_id == tenant_id,
        created_at=row.created_at,
    )
