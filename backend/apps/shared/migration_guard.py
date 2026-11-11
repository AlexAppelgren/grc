"""Refuse `migrate` on a database where a squashed migration is partly applied (review
2026-11-11 B-13).

Each app builds its schema from squashed migrations whose `replaces` name the migrations they
stand for, and those files are gone. Django runs a squash on a database that applied none of
them and records it on one that applied all of them; on one that applied only some it uses
neither and says nothing, so the rest never runs: a column, a constraint or a row-level
security policy would be missing. A database check runs at the start of `migrate` (and of
`check --database`), so this turns that into an error naming the squash and what the
database lacks. The fix is to deploy the commit before the squash first."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.apps import AppConfig
from django.core import checks
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder


@checks.register(checks.Tags.database)
def squashes_applied_whole(*, app_configs: Sequence[AppConfig] | None, databases: Sequence[str] | None, **kwargs: Any) -> list[checks.CheckMessage]:  # compliance: allow-kwargs Django system check signature
    replacements = MigrationLoader(None, ignore_no_migrations=True).replacements
    errors: list[checks.CheckMessage] = []
    for alias in databases or ():
        recorded = MigrationRecorder(connections[alias]).applied_migrations()
        for (app, name), squash in sorted(replacements.items()):
            missing = [f"{label}.{old}" for label, old in squash.replaces if (label, old) not in recorded]
            if missing and len(missing) < len(squash.replaces):
                errors.append(
                    checks.Error(
                        f"{app}.{name} is partly applied on {alias!r}: missing {', '.join(missing)}.",
                        hint="Deploy the commit before the squash first, so the database applies every migration it replaces.",
                        id="shared.E001",
                    )
                )
    return errors
