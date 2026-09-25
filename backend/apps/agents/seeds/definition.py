"""Read a versioned agent definition (`backend/agents/<agent>/v<n>/definition.yaml`, AGT-03).

PyYAML is a development dependency and the image installs `--only main`, while
`seed_reference` runs on every deploy, so the seed cannot import it and dependencies are
not this package's to change. The fields the seed needs are plain top-level scalars and
the tool names, so this reader takes those and refuses any value it cannot read rather than
seeding a half-read definition. `apps/agents/tests_models.py` and
`apps/agents/tests_definition_files.py` parse the same files with PyYAML and demand the two
agree, so the reader cannot drift from real YAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.agents.models import AgentScopeKind, AgentWritesTo

# `backend/agents/`, which is `/app/agents/` in the API image: the image builds from
# `backend/` alone, so a definition anywhere else never reaches the deploy that seeds it.
DEFINITIONS: Path = settings.BASE_DIR / "agents"

FIELD = re.compile(r"[a-z][a-z0-9_]*")
# One entry of the `tools:` list, `  - name: <tool>`, and the names a tool may have.
TOOL_ENTRY = re.compile(r"\s+- name:(.*)$")
TOOL_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
REQUIRED = (
    "id",
    "version",
    "kind",
    "status",
    "description",
    "scope",
    "tenant_configurable",
    "writes_to",
    "model",
    "change_note",
    "prompt",
)
BOOLEANS = {"true": True, "false": False}
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
    scope: str
    tenant_configurable: bool
    writes_to: str
    model: str
    change_note: str
    prompt: str
    tools: tuple[str, ...]

    @property
    def active(self) -> bool:
        """Only a published definition is switched on; `draft` and `retired` are not."""
        return self.status == "active"


def read_definition(path: Path) -> Definition:
    lines = path.read_text(encoding="utf-8").splitlines()
    scalars = _top_level_scalars(path, lines)
    missing = [name for name in REQUIRED if name not in scalars]
    if missing:
        raise DefinitionError(f"{path}: missing {', '.join(missing)}")
    version = scalars["version"]
    if not version.isdigit():
        raise DefinitionError(f"{path}: version must be a whole number, not {version!r}")
    # These land in columns the platform fence reads, so a value outside the kind is refused.
    for name, kind in (("scope", AgentScopeKind), ("writes_to", AgentWritesTo)):
        if scalars[name] not in {member.value for member in kind}:
            raise DefinitionError(f"{path}: {name} must be one of {', '.join(member.value for member in kind)}")
    if scalars["tenant_configurable"] not in BOOLEANS:
        raise DefinitionError(f"{path}: tenant_configurable must be true or false")
    return Definition(
        key=scalars["id"],
        version=int(version),
        kind=scalars["kind"],
        status=scalars["status"],
        description=scalars["description"],
        scope=scalars["scope"],
        tenant_configurable=BOOLEANS[scalars["tenant_configurable"]],
        writes_to=scalars["writes_to"],
        model=scalars["model"],
        change_note=scalars["change_note"],
        prompt=scalars["prompt"],
        tools=_tool_names(path, lines),
    )


def _top_level_scalars(path: Path, lines: list[str]) -> dict[str, str]:
    """Every `name: value` at column zero. Nested mappings and lists are skipped; a
    folded or literal block (`>` or `|`) is joined into one line."""
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


def _tool_names(path: Path, lines: list[str]) -> tuple[str, ...]:
    """The `name` of every entry of the top-level `tools:` list, in order. An entry must
    open with its name, so a tool is never read without one."""
    if "tools:" not in lines:
        raise DefinitionError(f"{path}: missing tools")
    names: list[str] = []
    for number, line in enumerate(lines[lines.index("tools:") + 1 :], start=lines.index("tools:") + 2):
        if line.strip() and not line[0].isspace() and not line.startswith("#"):
            break  # the next top-level field ends the list
        if line.lstrip().startswith("- "):
            entry = TOOL_ENTRY.fullmatch(line)
            name = COMMENT.sub("", entry.group(1)).strip() if entry else ""
            if not TOOL_NAME.fullmatch(name):
                raise DefinitionError(f"{path} line {number}: a tool entry opens with `- name: <tool>`")
            names.append(name)
    if not names:
        raise DefinitionError(f"{path}: tools lists no tool")
    return tuple(names)
