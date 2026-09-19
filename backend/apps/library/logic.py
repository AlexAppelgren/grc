"""Business logic of the library app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3)."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import Protocol, TypeVar


class Versioned(Protocol):
    @property
    def version_number(self) -> int: ...

    @property
    def effective_from(self) -> datetime.date | None: ...


V = TypeVar("V", bound=Versioned)


def in_force(versions: Iterable[V], on: datetime.date) -> V | None:
    """The version in force on `on` (AC-INV1, data-model §4): the one with the latest
    `effective_from` on or before the date, a null meaning since always. Two versions
    effective the same day: the later version number is the correction and wins. None
    when every version starts after the date."""
    candidates = [v for v in versions if v.effective_from is None or v.effective_from <= on]
    return max(candidates, key=lambda v: (v.effective_from or datetime.date.min, v.version_number), default=None)
