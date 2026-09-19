"""Read a versioned agent definition (`backend/agents/<agent>/v<n>/definition.yaml`, AGT-03).

PyYAML is a development dependency and the image installs `--only main`, while
`seed_reference` runs on every deploy, so the seed cannot import it and dependencies are
not this package's to change. The five fields the seed needs are plain top-level scalars,
so this reader takes those and refuses any value it cannot read rather than seeding a
half-read definition. `apps/agents/tests_models.py` parses the same file with PyYAML and
demands the two agree, so the reader cannot drift from real YAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

# `backend/agents/`, which is `/app/agents/` in the API image: the image builds from
# `backend/` alone, so a definition anywhere else never reaches the deploy that seeds it.
DEFINITIONS: Path = settings.BASE_DIR / "agents"

FIELD = re.compile(r"[a-z][a-z0-9_]*")
# YAML ends an unquoted scalar at whitespace followed by `#`.
COMMENT = re.compile(r"\s+#.*$")
# Values this reader does not read: quoted, flow, anchored, aliased or tagged.
UNREADABLE = "\"'[{&*!|"


class DefinitionError(RuntimeError):
    """A definition file this reader cannot read. The deploy stops rather than guess."""


@dataclass(frozen=True)
class Definition:
    """What the seed stores. The rest of the file is the runner's contract, not a column."""

    key: str
    version: int
    kind: str
    status: str
    description: str

    @property
    def active(self) -> bool:
        """Only a published definition is switched on; `draft` and `retired` are not."""
        return self.status == "active"


def read_definition(path: Path) -> Definition:
    scalars = _top_level_scalars(path)
    missing = [name for name in ("id", "version", "kind", "status", "description") if name not in scalars]
    if missing:
        raise DefinitionError(f"{path}: missing {', '.join(missing)}")
    version = scalars["version"]
    if not version.isdigit():
        raise DefinitionError(f"{path}: version must be a whole number, not {version!r}")
    return Definition(
        key=scalars["id"],
        version=int(version),
        kind=scalars["kind"],
        status=scalars["status"],
        description=scalars["description"],
    )


def _top_level_scalars(path: Path) -> dict[str, str]:
    """Every `name: value` at column zero. Nested mappings and lists are skipped; a
    folded or literal block (`>` or `|`) is joined into one line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    scalars: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        name, separator, raw = line.partition(":")
        if not separator or not FIELD.fullmatch(name):
            raise DefinitionError(f"{path} line {index}: expected `name: value` at the start of a line")
        value = COMMENT.sub("", raw).strip()
        if value == ">":
            value, index = _folded_block(lines, index)
        elif not value:
            continue  # a nested mapping or list: not a field the seed reads
        elif value[0] in UNREADABLE:
            raise DefinitionError(f"{path} line {index}: {name} is not a plain scalar this reader can read")
        scalars[name] = value
    return scalars


def _folded_block(lines: list[str], index: int) -> tuple[str, int]:
    """The indented lines under a folded (`>`) marker, joined by a single space, which is
    what YAML folding does to one paragraph, without its trailing newline."""
    parts: list[str] = []
    while index < len(lines) and (not lines[index].strip() or lines[index][0].isspace()):
        if lines[index].strip():
            parts.append(lines[index].strip())
        index += 1
    return " ".join(parts), index
