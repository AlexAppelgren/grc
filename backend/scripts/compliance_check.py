#!/usr/bin/env python
"""Compliance lint (playbook 9): the rules a diff review cannot see because the bad line
looks like the twenty good ones above it. Always `--all`, never `--since HEAD~1`.

Rules (each has a suppression id for the inline form `# compliance: <id> <reason>`):

  json-schema     `models.JSONField(` must carry `# schema: <PydanticName>` on its line.
  kinds-only      Every enum class (Enum, StrEnum, IntEnum, TextChoices, IntegerChoices)
                  under apps/ must be in apps/shared/kinds.py TIER_ONE_KINDS.
  log-content     A logger call whose arguments mention a personal-data or tenant-content
                  name (email, phone, token, ..., summary, note, comment, question, body,
                  text, assessment) is refused: log the record id instead (playbook 4.7).
  broad-except    `except Exception:` / `except BaseException:` / bare `except:` need a
                  reason (`allow-broad-except <why>`).
  typed-response  Every `@router.<method>(...)` in api.py declares `response=`.
  secure-random   `import random` / `from random import` in a security module
                  (authentication, identity, anything named token, otp, passkey, session,
                  key, secret): use `secrets`.
  no-kwargs       `*args` / `**kwargs` in a function defined in api.py, logic.py or
                  *_logic.py (`allow-kwargs <why>` for framework signatures).
  maintenance-hatch  The setting that switches the append-only triggers off
                  (`cw.maintenance`, or MAINTENANCE_SETTING which holds it) is named only in
                  apps/shared/migration_helpers.py, under migrations/ and in tests_*.py, so
                  request code cannot reach it. Read case-insensitively and across white
                  space and through quotes, because PostgreSQL folds a setting name and
                  `CW.MAINTENANCE` and `"CW"."MAINTENANCE"` are the same hatch. Any line
                  counts, comments included. This rule takes no suppression.
  library-door    The door the library-zone trigger reads (`cw.library_door`, the constant
                  LIBRARY_DOOR_SETTING that holds it, and `library_door()` that sets it; one
                  token names all three) is named only in apps/shared/tenancy.py, the index
                  door apps/search/indexing.py, the watch door apps/watch/write.py, the
                  evaluation door apps/search/eval_sets.py, apps/shared/migration_helpers.py, under
                  migrations/ and in tests_*.py (H16, ADR 0058). The app role can set the
                  setting itself, so a write that names a door is a write the database lets
                  through; this keeps opening one to the doors. Case-insensitive, through
                  quotes, comments included; no suppression.
  record-content  A `record(...)` whose `before`, `after` or `payload` carries a key whose
                  head noun is body, text, comment, note, summary, assessment or question
                  (`body`, `decisionNote`, `change_summary`; not `commentId` or `noteCount`):
                  an audit value and an outbox payload hold ids, keys and dates, never the
                  text a person typed (COL-01, CHUNK10_TASKS rule 13, R2_CROSS_CUTTING rule
                  m). Read through a dict written in the call, a name bound to a dict in the
                  same function (subscript stores included), `dict(...)`, nested values, and
                  a helper of the same module whose return is a dict. `record()`'s own
                  `summary=` is the row's sentence about the actor and the record, and is
                  exempt. Suppress on the key's line.

Suppression: append `# compliance: <id> <reason>` to the offending line, or the line that
opens the offending statement; the reason must be non-empty. A suppression with no reason
is itself a finding.

Proven to fail 2026-09-19 by adding `models.JSONField()` without a schema comment to
apps/home/models.py (exit 1, one finding named), then restored. maintenance-hatch proven
to fail 2026-09-19 by adding `SET LOCAL cw.maintenance = 'on'` to apps/library/logic.py
(exit 1, one finding named), then restored. library-door proven to fail 2026-09-23 by adding
`with tenancy.library_door("proposal"):` to apps/watch/curation.py (exit 1, one finding
named), then restored. record-content proven to fail 2026-09-25 by adding
`after={"body": "x"}` to the record() of apps/taxonomy/tenant_lists_logic.py's restore()
(exit 1, one finding named), then restored.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SCAN_DIRS = (BACKEND / "apps", BACKEND / "config")
sys.path.insert(0, str(BACKEND))

from apps.shared.kinds import TIER_ONE_KINDS  # noqa: E402  plain Python, no Django

ENUM_BASES = {"Enum", "StrEnum", "IntEnum", "TextChoices", "IntegerChoices", "Choices"}
SECURITY_MODULE = re.compile(r"(authentication|identity|token|otp|passkey|session|api_key|secret|webauthn)")
LOG_SENSITIVE = re.compile(
    r"\b(email|phone|token|secret|password|api_key|apikey|cookie|authorization|"
    r"content|text|body|summary|note|comment|question|answer|assessment|evidence|payload)\b",
    re.IGNORECASE,
)
RECORD_VALUES = {"before", "after", "payload"}
RECORD_CONTENT = {"body", "text", "comment", "note", "summary", "assessment", "question"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "api_operation"}
SUPPRESSION = re.compile(r"#\s*compliance:\s*(?P<id>[a-z-]+)(?P<reason>.*)$")
# Case-insensitive, across white space and through quotes: PostgreSQL folds a setting name
# and accepts the quoted spelling, so `SET LOCAL CW.MAINTENANCE`, `cw . maintenance` and
# `"CW"."MAINTENANCE"` are all the same hatch (H12, then the H-B review).
MAINTENANCE_HATCH = re.compile(r'"?cw"?\s*\.\s*"?maintenance"?|maintenance_setting', re.IGNORECASE)
HATCH_HOME = "apps/shared/migration_helpers.py"
# The library door (H16, ADR 0058): the setting, its constant and the context manager that
# sets it share the token `library_door`, so one pattern finds all three in any letter case,
# around a dot and through quotes (`"CW"."LIBRARY_DOOR"`).
LIBRARY_DOOR = re.compile(r"library_door", re.IGNORECASE)
LIBRARY_DOOR_HOMES = frozenset(
    {
        "apps/shared/tenancy.py",  # the setting, library_door() and library_write()
        "apps/search/indexing.py",  # index_write(), the index door
        "apps/watch/write.py",  # the watch door's re-point inside a merge approval
        "apps/search/eval_sets.py",  # the evaluation door (search 0003)
        "apps/shared/migration_helpers.py",  # the trigger that reads it
    }
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path.relative_to(BACKEND).as_posix()}:{self.line}: [{self.rule}] {self.message}"


class Checker:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.source = path.read_text(encoding="utf-8")
        self.lines = self.source.splitlines()
        self.tree = ast.parse(self.source)
        self.findings: list[Finding] = []
        rel = path.relative_to(BACKEND).as_posix()
        self.is_api = rel.endswith("/api.py")
        self.is_logic = rel.endswith("/logic.py") or rel.endswith("_logic.py")
        self.is_security = bool(SECURITY_MODULE.search(rel))
        self.is_test = path.name.startswith("tests_") or path.name == "testing.py"
        self.may_name_hatch = rel == HATCH_HOME or "/migrations/" in rel or path.name.startswith("tests_")
        self.may_name_door = rel in LIBRARY_DOOR_HOMES or "/migrations/" in rel or path.name.startswith("tests_")
        self.functions = {
            node.name: node for node in self.tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.record_keys: set[tuple[int, int]] = set()
        self.parents = {child: parent for parent in ast.walk(self.tree) for child in ast.iter_child_nodes(parent)}

    def suppressed(self, line: int, rule: str) -> bool:
        for candidate in (line, line - 1):
            if 1 <= candidate <= len(self.lines):
                match = SUPPRESSION.search(self.lines[candidate - 1])
                if match and match.group("id") == rule:
                    if not match.group("reason").strip():
                        self.findings.append(
                            Finding(self.path, candidate, rule, "suppression without a reason")
                        )
                    return True
        return False

    def report(self, line: int, rule: str, message: str, suppression_id: str | None = None) -> None:
        if self.suppressed(line, suppression_id or rule):
            return
        self.findings.append(Finding(self.path, line, rule, message))

    def run(self) -> list[Finding]:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                self.check_call(node)
            elif isinstance(node, ast.ClassDef):
                self.check_class(node)
            elif isinstance(node, ast.ExceptHandler):
                self.check_except(node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self.check_import(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.check_function(node)
        if not self.may_name_hatch:
            self.check_maintenance_hatch()
        if not self.may_name_door:
            self.check_library_door()
        return self.findings

    def check_maintenance_hatch(self) -> None:
        for number, line in enumerate(self.lines, start=1):
            if MAINTENANCE_HATCH.search(line):  # appended directly: no suppression
                self.findings.append(
                    Finding(self.path, number, "maintenance-hatch", f"the append-only escape hatch is named outside {HATCH_HOME}, migrations and tests")
                )

    def check_library_door(self) -> None:
        for number, line in enumerate(self.lines, start=1):
            if LIBRARY_DOOR.search(line):  # appended directly: no suppression
                self.findings.append(
                    Finding(self.path, number, "library-door", "the library door is named outside the doors, the migration helpers, migrations and tests")
                )

    @staticmethod
    def _callee(node: ast.Call) -> tuple[str | None, str | None]:
        func = node.func
        if isinstance(func, ast.Attribute):
            base = func.value.id if isinstance(func.value, ast.Name) else None
            return base, func.attr
        if isinstance(func, ast.Name):
            return None, func.id
        return None, None

    def check_call(self, node: ast.Call) -> None:
        base, name = self._callee(node)
        if name == "JSONField":
            window = " ".join(self.lines[node.lineno - 1 : (node.end_lineno or node.lineno)])
            if not re.search(r"#\s*schema:\s*[A-Z]\w+", window):
                self.report(node.lineno, "json-schema", "JSONField without `# schema: <PydanticName>`")
        if name in LOG_METHODS and base and (base == "logger" or base.endswith("logger") or base == "logging"):
            if self.is_test:
                return
            text = ast.get_source_segment(self.source, node) or ""
            # The message literal itself may name the concept; what must not appear is a
            # value: an f-string field, a %-format argument or an `extra` key of that name.
            values: list[str] = []
            for arg in node.args[1:]:
                values.append(ast.get_source_segment(self.source, arg) or "")
            for arg in node.args[:1]:
                if isinstance(arg, ast.JoinedStr):
                    values.extend(
                        ast.get_source_segment(self.source, v.value) or ""
                        for v in arg.values
                        if isinstance(v, ast.FormattedValue)
                    )
            for keyword in node.keywords:
                if keyword.arg == "extra" and isinstance(keyword.value, ast.Dict):
                    for key in keyword.value.keys:
                        if isinstance(key, ast.Constant):
                            values.append(str(key.value))
            hit = next((v for v in values if LOG_SENSITIVE.search(v)), None)
            if hit is not None:
                self.report(
                    node.lineno,
                    "log-content",
                    f"logger call carries a value named like personal data or tenant content: {hit!r} "
                    f"(log the record id instead; playbook 4.7)",
                )
            del text
        if name == "record" and not self.is_test:
            self.check_record(node)
        if self.is_api and name in HTTP_METHODS and base in {"router", "api"}:
            if not any(k.arg == "response" for k in node.keywords):
                self.report(node.lineno, "typed-response", f"@{base}.{name}(...) without response=")

    def check_record(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            if keyword.arg in RECORD_VALUES:
                for key in self._value_keys(keyword.value, self._scope(node), set()):
                    head = re.split(r"_|(?<=[a-z0-9])(?=[A-Z])", str(key.value))[-1].lower()
                    if head in RECORD_CONTENT and (key.lineno, key.col_offset) not in self.record_keys:
                        self.record_keys.add((key.lineno, key.col_offset))
                        self.report(
                            key.lineno,
                            "record-content",
                            f"record({keyword.arg}=...) carries {key.value!r}, named like tenant content "
                            f"(carry the id or key instead; CHUNK10_TASKS rule 13)",
                        )

    def _scope(self, node: ast.AST) -> ast.AST:
        while node in self.parents and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node = self.parents[node]
        return node

    def _value_keys(self, value: ast.expr | None, scope: ast.AST, seen: set[str]) -> list[ast.Constant]:
        """The constant string keys a before, after or payload value can carry. Only what the
        value itself holds: a dict's keys and values, the items of a list, a name's dict, a
        helper's returned dict. An argument passed to some other call, an attribute's base
        and a subscripted name are not carried whole, so they are not read."""
        if isinstance(value, ast.Dict):
            keys = [k for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            for item in value.values:
                keys.extend(self._value_keys(item, scope, seen))
            return keys
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            return [key for item in value.elts for key in self._value_keys(item, scope, seen)]
        if isinstance(value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self._value_keys(value.elt, scope, seen)
        if isinstance(value, ast.DictComp):
            return self._value_keys(ast.Dict(keys=[value.key], values=[value.value]), scope, seen)
        if isinstance(value, ast.IfExp):
            return self._value_keys(value.body, scope, seen) + self._value_keys(value.orelse, scope, seen)
        if isinstance(value, ast.BoolOp):
            return [key for item in value.values for key in self._value_keys(item, scope, seen)]
        if isinstance(value, ast.Name) and value.id not in seen:
            return self._bound_keys(value.id, scope, seen | {value.id})
        if isinstance(value, ast.Call):
            _, callee = self._callee(value)
            if callee == "dict":
                keys = [ast.Constant(value=k.arg, lineno=k.lineno, col_offset=k.col_offset) for k in value.keywords if k.arg]
                for item in [*value.args, *(k.value for k in value.keywords)]:
                    keys.extend(self._value_keys(item, scope, seen))
                return keys
            if callee in self.functions and callee not in seen:
                helper = self.functions[callee]
                return [
                    key
                    for ret in ast.walk(helper)
                    if isinstance(ret, ast.Return)
                    for key in self._value_keys(ret.value, helper, seen | {callee})
                ]
        return []

    def _bound_keys(self, name: str, scope: ast.AST, seen: set[str]) -> list[ast.Constant]:
        """Keys a name picks up in its function: `name = {...}` and `name["key"] = ...`."""
        keys: list[ast.Constant] = []
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign):
                targets, bound = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, bound = [node.target], node.value
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    keys.extend(self._value_keys(bound, scope, seen))
                elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == name:
                    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                        keys.append(target.slice)
                    keys.extend(self._value_keys(bound, scope, seen))
        return keys

    def check_class(self, node: ast.ClassDef) -> None:
        bases = set()
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.add(base.id)
            elif isinstance(base, ast.Attribute):
                bases.add(base.attr)
        if bases & ENUM_BASES and not self.is_test and node.name not in TIER_ONE_KINDS:
            self.report(
                node.lineno,
                "kinds-only",
                f"enum {node.name} is not in apps/shared/kinds.py TIER_ONE_KINDS (playbook 15)",
            )

    def check_except(self, node: ast.ExceptHandler) -> None:
        broad = node.type is None or (
            isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
        )
        if broad:
            self.report(node.lineno, "broad-except", "bare or broad except; name the exception", "allow-broad-except")

    def check_import(self, node: ast.Import | ast.ImportFrom) -> None:
        if not self.is_security or self.is_test:
            return
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
        if any(n == "random" or n.startswith("random.") for n in names):
            self.report(node.lineno, "secure-random", "`random` in a security module; use `secrets`")

    def check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not (self.is_api or self.is_logic) or self.is_test:
            return
        if node.args.vararg is not None or node.args.kwarg is not None:
            self.report(node.lineno, "no-kwargs", f"{node.name}() takes *args/**kwargs", "allow-kwargs")


def scan(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        findings.extend(Checker(path).run())
    return findings


def python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_DIRS:
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(BACKEND).as_posix()
            if "/migrations/" in rel:
                continue
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="scan the whole tree (the only mode)")
    args = parser.parse_args(argv)
    if not args.all:
        parser.error("run with --all; a partial scan is not a gate (playbook 9)")
    files = python_files()
    findings = scan(files)
    for finding in findings:
        print(finding)
    print(f"compliance_check: {len(files)} files, {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
