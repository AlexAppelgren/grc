"""The subject registry (CHUNK10_TASKS ruling 3): which records a notification or a comment
may name, the permission that reads each, how to load one, and the title a person is shown.

"Can this person read this record" is written once, here, and `notify()`, the comments and
the mention check all read it. A later chunk adds a kind by adding one row; the registry
test in `tests_notify.py` fails on a row whose permission is not a bank permission, whose
lookup does not find its record or whose title is not a record title.

A title is always the record's own title in the reader's language order (a library title,
or the change's library title for a bank's case), never text a person typed (rule 13).
Lookups run under the caller's row-level security, so another bank's record is not found.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError

from apps.cases.models import ChangeCase
from apps.library.models import Obligation
from apps.library.reading import localized
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


SUBJECTS: dict[str, Subject] = {
    "obligation": Subject(read_permission=perms.LIBRARY_READ, lookup=_obligation, title=_obligation_title),
    "change_case": Subject(read_permission=perms.CASES_READ, lookup=_change_case, title=_change_case_title),
}


def subject(kind: str) -> Subject:
    found = SUBJECTS.get(kind)
    if found is None:
        raise ValidationError("This kind of record cannot be commented on or notified about.", code="unsupported_subject")
    return found
