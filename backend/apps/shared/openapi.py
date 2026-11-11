"""What the published contract adds to and takes from Ninja's generated document
(playbook 14). `config/api.py` runs it on every generation, so the exported openapi.json and
the DEBUG docs page agree."""

from __future__ import annotations

import inspect
import json
import re
from typing import Any

from django.conf import settings

from apps.shared.permissions import gate_of, step_up_of
from apps.shared.routes import RegisteredOperation

_REF = re.compile(r'"#/components/schemas/([^"]+)"')


def without_unreferenced_schemas(document: dict[str, Any]) -> dict[str, Any]:
    """Drop the component schemas no operation reaches. Ninja inlines a `Query[...]` model
    into `parameters` yet still lists the model as a component, which an integrator can
    neither send nor receive (review 2026-11-11 B-2)."""
    schemas: dict[str, Any] = document.get("components", {}).get("schemas", {})
    reached: set[str] = set()
    pending = set(_REF.findall(json.dumps(document.get("paths", {}))))
    while pending:
        name = pending.pop()
        if name in reached or name not in schemas:
            continue
        reached.add(name)
        pending |= set(_REF.findall(json.dumps(schemas[name])))
    for name in set(schemas) - reached:
        del schemas[name]
    return document


# Who `unauthenticated` turns away, by the auth classes a route accepts.
_CREDENTIAL = {"SessionAuth": "a signed-in session", "ApiKeyAuth": "a valid API key", "EnrolmentAuth": "an enrolment session"}


def gate_errors(operation: RegisteredOperation) -> list[str]:
    """The errors a route's auth class and decorators answer before its logic runs, as
    clauses of the published `Errors` paragraph. The decorators are the source of truth, so
    a route cannot describe a gate it does not have or miss one it has (review 2026-11-11
    B-10)."""
    view = operation.view_func
    clauses: list[str] = []
    accepted = [_CREDENTIAL[type(auth).__name__] for auth in operation.auth or [] if type(auth).__name__ in _CREDENTIAL]
    if accepted:
        clauses.append(f"`unauthenticated` (401) without {' or '.join(accepted)}")
    gate = gate_of(view)
    if gate is not None and gate.kind == "permission":
        clauses.append(f"`permission_denied` (403) without `{gate.value}`, named in `requiredPermission`")
    elif gate is not None:
        clauses.append(f"`permission_denied` (403) for a key without the `{gate.value}` scope, named in `requiredPermission`")
    if step_up_of(view):
        clauses.append(
            "`step_up_required` (403) without a passkey assertion younger than the step-up window, "
            "which a screen answers by opening the passkey prompt and retrying"
        )
    return clauses


def other_errors(operation: dict[str, Any], view: Any) -> list[str]:
    """The errors a route's parameters and headers answer: a page past its bounds, and a
    write whose `If-Match` names a version that is no longer current."""
    clauses: list[str] = []
    names = {parameter.get("name") for parameter in operation.get("parameters") or []}
    if {"limit", "offset"} <= names:
        clauses.append(
            f"`validation_error` (422) when `limit` is above {settings.API_PAGE_SIZE_MAX} or `offset` "
            f"above {settings.API_PAGE_OFFSET_MAX}"
        )
    if "if_match(request)" in inspect.getsource(inspect.unwrap(view)):
        clauses.append("`stale_write` (409) when `If-Match` names a version that is no longer the current one")
    return clauses


def with_generated_errors(document: dict[str, Any], operations: list[RegisteredOperation]) -> dict[str, Any]:
    """Append each operation's mechanical errors to its description as one paragraph. The
    hand-written `Errors` paragraph keeps only what the route's own rules answer."""
    by_id = {
        operation["operationId"]: operation
        for item in document.get("paths", {}).values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    for registered in operations:
        operation = by_id.get(registered.operation_id)
        if operation is None:
            continue
        clauses = gate_errors(registered) + other_errors(operation, registered.view_func)
        if clauses:
            paragraph = "Errors every call can meet: " + "; ".join(clauses) + "."
            operation["description"] = f"{operation.get('description', '').rstrip()}\n\n{paragraph}".lstrip()
    return document
