"""The drafted "So what?" a run files with the change it read (WAT-05, AUD-02, D-66).

The agent that read the source writes the words (D-66); this module makes no model call. It
puts the reported words on the shared change and turns the report into the `ai_generation`
row AUD-02 asks for. That row's model, version and citations are the agent's account of
itself, stored as `model_metadata_reported_by_agent`.

- One draft per change, from library facts only: nothing of any bank is in a change (D-07,
  D-32). Each bank's case gets it unconfirmed and confirms or rewrites its own copy.
- Labelled machine output until a person confirms it.
- Optional: a run that cannot say what a reform means files none.

The `regulatory_change.so_what_drafted` event carries the words to the banks
(`apps/cases/so_what.py`), updating only copies still unedited. `keys.py` hands over the row
(library fence).
"""

from __future__ import annotations

import uuid

from django.db import transaction

from apps.governance.ai_log import log_generation
from apps.governance.models import AiPurpose
from apps.shared.audit import Actor, record
from apps.watch import keys
from apps.watch.schemas import WatchSoWhatInput
from apps.watch.write import watch_write

SUBJECT_TYPE = "regulatory_change"

# The kind `apps/cases/so_what.py` listens for: a change's drafted wording moved.
SO_WHAT_DRAFTED = "regulatory_change.so_what_drafted"


def store(
    change: keys.ChangeRow, report: WatchSoWhatInput, *, actor: Actor, agent_run_id: uuid.UUID | None
) -> None:
    """Put the reported words on the change and record the call, in the caller's
    transaction, so draft, log row, audit row and event commit together.
    """
    change.so_what_draft = report.text
    with watch_write("the So what a run filed with a change"), transaction.atomic():
        change.save(update_fields=["so_what_draft"])
        generation = log_generation(
            purpose=AiPurpose.SO_WHAT,
            model=report.model,
            model_version=report.model_version,
            output=report.text,
            citations=report.citations,
            agent_run_id=agent_run_id,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            prompt_template=report.prompt_template or "",
            prompt_hash=report.prompt_hash or "",
            # D-66: the agent's own account of the model behind these words.
            metadata_reported_by_agent=True,
        )
        record(
            action=SO_WHAT_DRAFTED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary=f"{actor.label} filed a drafted “So what?” for a change.",
            tenant_id=None,
            # The words are on the log row; the audit row carries which model said it, on what.
            after={
                "generationId": str(generation.id),
                "model": report.model,
                "modelVersion": report.model_version,
                "modelMetadataReportedByAgent": True,
                "citations": [citation.url for citation in report.citations],
            },
        )
