"""The subject registry (CHUNK10_TASKS ruling 3): which records a notification or a comment
may name, the permission that reads each, how to load one, and the title a person is shown.

"Can this person read this record" is written once, here; a new kind is one row, and
`tests_notify.py` checks each row. A title is always the record's own in the reader's
language order, never typed text (rule 13). Lookups run under row-level security.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError

from apps.agents.models import TenantAgent
from apps.cases.models import Action, ChangeCase
from apps.library.models import Obligation
from apps.library.reading import localized
from apps.register.models import TenantObligation
from apps.shared import permissions as perms


@dataclass(frozen=True)
class Subject:
    read_permission: str
    lookup: Callable[[uuid.UUID], Any | None]
    title: Callable[[Any, list[str]], str]


def _obligation(subject_id: uuid.UUID) -> Obligation | None:
    return Obligation.objects.prefetch_related("titles").filter(pk=subject_id).first()  # ordering: pk lookup, at most one row


def _obligation_title(row: Obligation, order: list[str]) -> str:
    title = localized(row.titles.all(), order)
    return title.text if title is not None else row.stable_key


def _change_case(subject_id: uuid.UUID) -> ChangeCase | None:
    return ChangeCase.objects.select_related("change").filter(pk=subject_id).first()  # ordering: pk lookup, at most one row


def _change_case_title(row: ChangeCase, order: list[str]) -> str:
    # A bank's case is titled by its change's library title, one language for every reader.
    return row.change.title


def _action(subject_id: uuid.UUID) -> Action | None:
    return Action.objects.select_related("case__change").filter(pk=subject_id).first()  # ordering: pk lookup, at most one row


def _action_title(row: Action, order: list[str]) -> str:
    # An action's own title is typed by a person, so it is titled by its case's change.
    return row.case.change.title


def _tenant_obligation(subject_id: uuid.UUID) -> TenantObligation | None:
    return (
        TenantObligation.objects.select_related("obligation")
        .prefetch_related("obligation__titles")
        .filter(pk=subject_id)
        .first()  # ordering: pk lookup, at most one row
    )


def _tenant_obligation_title(row: TenantObligation, order: list[str]) -> str:
    return _obligation_title(row.obligation, order)


# One of the bank's own agents, which the cap paused (AGT-04). Read by those who steer the
# agents, titled by its definition's key.
def _tenant_agent(subject_id: uuid.UUID) -> TenantAgent | None:
    return TenantAgent.objects.select_related("agent").filter(pk=subject_id).first()  # ordering: pk lookup, at most one row


def _tenant_agent_title(row: TenantAgent, order: list[str]) -> str:
    return row.agent.key


SUBJECTS: dict[str, Subject] = {
    "obligation": Subject(read_permission=perms.LIBRARY_READ, lookup=_obligation, title=_obligation_title),
    "change_case": Subject(read_permission=perms.CASES_READ, lookup=_change_case, title=_change_case_title),
    # An action's reminders and escalation, and a register entry's review reminder.
    "action": Subject(read_permission=perms.CASES_READ, lookup=_action, title=_action_title),
    "tenant_obligation": Subject(
        read_permission=perms.REGISTER_READ, lookup=_tenant_obligation, title=_tenant_obligation_title
    ),
    "tenant_agent": Subject(read_permission=perms.AGENTS_MANAGE, lookup=_tenant_agent, title=_tenant_agent_title),
}


def subject(kind: str) -> Subject:
    found = SUBJECTS.get(kind)
    if found is None:
        raise ValidationError("This kind of record cannot be commented on or notified about.", code="unsupported_subject")
    return found
