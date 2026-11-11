"""A person on a record: id and name, the only personal data a screen, a log or an answer
may carry about them (playbook 4.7)."""

from __future__ import annotations

from typing import Any, overload

from apps.shared.schemas import CamelSchema
from apps.taxonomy.schemas import PersonRef


@overload
def person_ref(user: Any) -> PersonRef | None: ...


@overload
def person_ref[S: CamelSchema](user: Any, schema: type[S]) -> S | None: ...


def person_ref(user: Any, schema: type[CamelSchema] = PersonRef) -> CamelSchema | None:
    """`{id, name}` of `user` in `schema`, or None when the record names nobody."""
    return None if user is None else schema.model_validate(user)
