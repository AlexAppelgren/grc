"""What the published contract adds to and takes from Ninja's generated document
(playbook 14). `config/api.py` runs it on every generation, so the exported openapi.json and
the DEBUG docs page agree."""

from __future__ import annotations

import json
import re
from typing import Any

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
