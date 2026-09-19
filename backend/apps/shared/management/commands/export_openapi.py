"""`manage.py export_openapi --out <path>`: write the normalised OpenAPI document that is
the truth of what is built (playbook 14). generate-types.sh and CI both call this, so the
normalisation lives here and nowhere else (playbook 9: identical locally and in CI).

Normalisation: keys sorted; every response `description` replaced by the status code's
standard reason phrase, so rewording a route's docstring never churns the generated
TypeScript; `servers` dropped because the host is an environment variable."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from config.api import api


def normalise(schema: dict[str, Any]) -> dict[str, Any]:
    document = json.loads(json.dumps(schema))  # a plain, detached copy
    document.pop("servers", None)
    for path_item in document.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for code, response in operation.get("responses", {}).items():
                try:
                    response["description"] = HTTPStatus(int(code)).phrase
                except ValueError:
                    response["description"] = "Response"
    return document


class Command(BaseCommand):
    help = "Export the normalised OpenAPI document."
    # CI runs this with no database service (generate-types.sh): no system checks that
    # could open a connection, and the role guard exempts the command by name.
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--out", required=True, help="Where to write openapi.json")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        schema = api.get_openapi_schema(path_prefix="/api/v1")
        document = normalise(dict(schema))
        out = Path(options["out"])
        out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        operations = sum(
            1 for item in document["paths"].values() for method in item if method in {"get", "post", "put", "patch", "delete"}
        )
        self.stdout.write(f"wrote {out} ({len(document['paths'])} paths, {operations} operations)")
