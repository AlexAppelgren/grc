"""The drafted "So what?" a run files with the change it read (WAT-05, AUD-02, D-66).

**Where the words come from changed on 2026-09-21.** They used to be ours: a handler of
ours would see a change appear and call a model a second time over the same facts. Alex
decided (D-66) that the agent which read the source writes them, because it has just read
it, and files them with the change through the door it already writes through. So this
module makes no model call at all. It takes what the agent reported, writes the words onto
the shared change, and turns the report into the `ai_generation` row AUD-02 asks for.

What that costs, said out loud rather than left for a reader to discover: the model, the
version and the citations on that row are **the agent's account of itself**, not something
bleqq measured. In R1 every agent is bleqq's own, so it is a reporting boundary; it becomes
a trust boundary the day a bank runs its own agent against `POST /changes`, which is R2's
agent-access work. The boundary is stored on the row
(`ai_generation.model_metadata_reported_by_agent`) and stated in both routes' descriptions,
so nothing downstream has to guess.

What has not changed:

- **One draft per change, from library facts only.** No footprint term, bank name, legal
  entity, product or bank-written text is in the prompt, because none of it is in the
  change: a change is a library row (D-07, D-32). The draft is copied into every bank's
  case unconfirmed, and each bank confirms or rewrites its own copy there.
- **Labelled machine output until a person confirms it.** The log row ships as `draft` and
  every bank's copy arrives with `so_what_confirmed` false.
- **A change with no draft is a change with no draft.** A run that cannot say what a reform
  means files none; registration and case creation carry on without one, which is what
  makes this optional rather than a blocking second call.

The event this writes, `regulatory_change.so_what_drafted`, is what carries the wording to
the banks: `apps/cases/so_what.py` listens for it on the one ordered cursor and brings
every copy that is still the unedited draft up to the new words, leaving alone every copy a
person has already made their bank's own.

This module writes, so it names no library record: `apps/watch/keys.py` resolves and hands
over the row, which is the split the library fence's AST guard demands.
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

# The kind `apps/cases/so_what.py` listens for: a change's drafted wording moved, so every
# bank whose copy is still that draft should be reading the new words.
SO_WHAT_DRAFTED = "regulatory_change.so_what_drafted"


def store(
    change: keys.ChangeRow, report: WatchSoWhatInput, *, actor: Actor, agent_run_id: uuid.UUID | None
) -> None:
    """Put the reported words on the change, record the call that produced them, and say so.

    Runs inside the caller's own transaction, so the draft, its log row, the audit row and
    the event that carries the wording to the banks commit together or not at all.
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
            # The words themselves are on the log row this points at; the audit row carries
            # what a reader checks a draft by — which model said it, and on what.
            after={
                "generationId": str(generation.id),
                "model": report.model,
                "modelVersion": report.model_version,
                "modelMetadataReportedByAgent": True,
                "citations": [citation.url for citation in report.citations],
            },
        )
