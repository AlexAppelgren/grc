"""`manage.py e2e_scope_findings <scope item key> [--part N]`: the mock runner reports what
tenant A's own agent found for a scope item of the E2E dataset, for J-12 and PRO-S15
(d89-e2e-journey): the bank's own instrument of part N, or its duties once a person approved
it, filed through the one door a bank's run files through. Prints the proposals as JSON
(id, kind, the record's stable key, title).
Refuses to run on a deployed environment, like `seed_e2e`."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.shared.e2e_seed import report_scope_findings


class Command(BaseCommand):
    help = "Report the mock runner's findings for one of tenant A's scope items. Never deployed."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("scope_item")
        parser.add_argument("--part", type=int, default=1, choices=range(1, 10**9), metavar="N")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        try:
            filed = report_scope_findings(options["scope_item"], options["part"])
        except ValueError as refused:
            raise CommandError(str(refused)) from None
        self.stdout.write(json.dumps([{"id": str(p.id), "kind": p.kind, "key": p.payload["key"], "title": p.title} for p in filed]))
