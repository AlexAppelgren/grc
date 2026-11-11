"""What a bank's own agent found, filed as the bank's own proposals (OWN-02, INV-07, PRO-01;
D-57, D-89, D-91, ADR 0059).

Reached only from the worker (`apps.agents.runner_events.apply_finding` has checked the
run); no route or API key reaches it. Each finding becomes one proposal through
`logic.create()`, the shared door's creation check. Before it:

- **Only a new record of the bank's own**: a `new_instrument`, `new_obligation` or
  `new_control` (OWN-05, D-99); anything else is `not_own_record`.
- **Owned by the run's bank**: `private=True`, checked against the run.
- **Never a duplicate**: a record or control the bank holds is 409
  `already_in_our_library`, answered by the database (`library.reading.held_as_own`), so
  the agent never reads the bank's records (D-57).
- **Once per run and event**: the event id is the idempotency key.

The proposal names the agent, the run and the model; its origin is `agent` until a person
decides it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError

from apps.agents.models import AgentRun
from apps.library import reading
from apps.proposals import logic, private_controls
from apps.proposals.models import Proposal
from apps.proposals.schemas import ProposalControlPayload, ProposalInstrumentPayload, ProposalObligationPayload
from apps.shared.audit import Actor, ActorType
from apps.shared.errors import ProblemError

# The longest event id a runner may report; the proposal's retry key is built from it.
EVENT_ID_MAX_CHARS = 80
# The widths of `proposal.title`, `proposal.source_label` and `proposal.model`.
_WIDTHS = {"title": 500, "source_label": 500, "model": 200}


@dataclass(frozen=True)
class Finding:
    """One record a bank's own agent reports, as its runner event carries it. Every field
    came from a model and a network, so none is trusted: `target_type` and `target_id` are
    carried only so a finding that names a shared record is refused by name."""

    event_id: str
    kind: str
    title: str
    payload: dict[str, Any]
    field_sources: dict[str, str]
    source_url: str
    source_label: str = ""
    model: str = ""
    target_type: str = ""
    target_id: uuid.UUID | None = None


def _not_own_record(detail: str) -> ValidationError:
    return ValidationError(detail, code="not_own_record")


def _checked(finding: Finding) -> None:
    if not 1 <= len(finding.event_id) <= EVENT_ID_MAX_CHARS:
        raise ValidationError(f"A runner event's id is 1 to {EVENT_ID_MAX_CHARS} characters.", code="invalid_runner_event")
    for field, width in _WIDTHS.items():
        if len(getattr(finding, field)) > width:
            raise ValidationError(f"A finding's {field} is at most {width} characters.", code="invalid_runner_event")
    if finding.target_type or finding.target_id is not None:
        raise _not_own_record("A bank's own agent never proposes a change to a shared record.")
    if finding.kind not in logic.PRIVATE_RECORD_KINDS:
        raise _not_own_record("A bank's own agent files only a new instrument, a new obligation or a control of the bank's own.")


def _held(run: AgentRun, finding: Finding) -> bool:
    """Whether the bank already holds the record as its own. A payload that does not parse is
    left to `logic.create()`, which names the fields to fix."""
    parsed = logic.parsed_payload(finding.kind, finding.payload)
    bank = run.tenant_id
    if bank is None:
        return False  # never a platform run: apply_finding refused it
    if isinstance(parsed, ProposalInstrumentPayload):
        return reading.held_as_own(bank, instrument=True, key=parsed.key, reference=parsed.official_ref)
    if isinstance(parsed, ProposalObligationPayload):
        return reading.held_as_own(bank, instrument=False, key=parsed.key, reference=parsed.ref_label, instrument_key=parsed.instrument)
    if isinstance(parsed, ProposalControlPayload):
        return private_controls.held(bank, parsed)
    return False


def file_finding(run: AgentRun, finding: Finding) -> Proposal:
    """File `finding` as the run's bank's own proposal, or refuse it and store nothing. The
    caller holds the run's row locked and stands in the run's zone. A finding already filed
    under this run answers its proposal, whatever the bank decided since."""
    _checked(finding)
    retry_key = f"runner:{run.id}:{finding.event_id}"
    filed = Proposal.objects.filter(agent_run_id=run.id, idempotency_key=retry_key).exists()
    if not filed and _held(run, finding):
        raise ProblemError(
            status=409,
            code="already_in_our_library",
            detail="Your organisation already holds this record as its own, so the finding was not filed.",
        )
    proposal, _created = logic.create(
        kind=finding.kind,
        title=finding.title,
        payload=finding.payload,
        proposer=logic.Proposer(actor=Actor(kind=ActorType.AGENT, id=run.agent_id, label=run.agent.key), agent_id=run.agent_id),
        idempotency_key=retry_key,
        agent_run_id=run.id,
        model=finding.model,
        field_sources=finding.field_sources,
        source_label=finding.source_label,
        source_url=finding.source_url,
        private=True,
    )
    return proposal
