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

Suppression: append `# compliance: <id> <reason>` to the offending line, or the line that
opens the offending statement; the reason must be non-empty. A suppression with no reason
is itself a finding.

Proven to fail 2026-09-19 by adding `models.JSONField()` without a schema comment to
apps/home/models.py (exit 1, one finding named), then restored.
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
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "api_operation"}
SUPPRESSION = re.compile(r"#\s*compliance:\s*(?P<id>[a-z-]+)(?P<reason>.*)$")


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
        return self.findings

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
        if self.is_api and name in HTTP_METHODS and base in {"router", "api"}:
            if not any(k.arg == "response" for k in node.keywords):
                self.report(node.lineno, "typed-response", f"@{base}.{name}(...) without response=")

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
