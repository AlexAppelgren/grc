#!/usr/bin/env python3
"""CodeQL SARIF gate (playbook 9: "CodeQL, own SARIF gate, medium and above").

Reads the SARIF files that `github/codeql-action/analyze` wrote and fails on
any finding at or above the severity floor unless that exact finding is
accepted in `.github/codeql-accepted.json`. Acceptance is per fingerprint
(SARIF `partialFingerprints.primaryLocationLineHash`) plus rule id, with a
reason and a date, never per rule. An acceptance whose fingerprint is no
longer present is *stale* and also fails the gate, so the list cannot rot
into a mute.

Why an own gate rather than GitHub's "fail on alert" setting: the code
scanning UI silently drops findings that were dismissed in the browser, and a
dismissal there has no reason, no date and no reviewer in the repository. This
file and the acceptance list are the record a bank's vendor review can read.

Thresholds are settings with an env override (brief, "Conventions"):

    CODEQL_GATE_MIN_SECURITY_SEVERITY   default 4.0  (CodeQL: medium is 4.0-6.9)
    CODEQL_GATE_FAIL_LEVELS             default "error,warning"  (rules without a
                                        security-severity: SARIF level that fails)

Exit codes: 0 clean, 1 gate failed (unaccepted or stale findings), 2 invalid
input (unreadable SARIF, malformed acceptance list). Stdlib only: it runs on
the runner's python3 before any project environment exists.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

REQUIRED_ACCEPTANCE_FIELDS = (
    "language",
    "ruleId",
    "fingerprint",
    "path",
    "reason",
    "acceptedOn",
    "acceptedBy",
)


class GateError(Exception):
    """Invalid input: the gate cannot answer the question it was asked."""


def _float_setting(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise GateError(f"{name} must be a number, got {raw!r}") from exc


def _levels_setting(name: str, default: str) -> set[str]:
    raw = os.environ.get(name) or default
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def load_acceptances(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"acceptance list not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"acceptance list is not valid JSON: {path}: {exc}") from exc
    accepted = data.get("accepted") if isinstance(data, dict) else None
    if not isinstance(accepted, list):
        raise GateError(f'{path}: expected an object with an "accepted" array')
    seen: set[tuple[str, str, str]] = set()
    for index, entry in enumerate(accepted):
        if not isinstance(entry, dict):
            raise GateError(f"{path}: accepted[{index}] is not an object")
        missing = [f for f in REQUIRED_ACCEPTANCE_FIELDS if not str(entry.get(f, "")).strip()]
        if missing:
            raise GateError(f"{path}: accepted[{index}] is missing {', '.join(missing)}")
        try:
            dt.date.fromisoformat(str(entry["acceptedOn"]))
        except ValueError as exc:
            raise GateError(
                f"{path}: accepted[{index}].acceptedOn must be YYYY-MM-DD, got {entry['acceptedOn']!r}"
            ) from exc
        key = (str(entry["language"]), str(entry["ruleId"]), str(entry["fingerprint"]))
        if key in seen:
            raise GateError(f"{path}: accepted[{index}] duplicates an earlier entry {key}")
        seen.add(key)
    return accepted


def load_sarif_files(sarif_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not sarif_dir.is_dir():
        raise GateError(f"SARIF directory not found: {sarif_dir}")
    files = sorted(sarif_dir.glob("*.sarif")) + sorted(sarif_dir.glob("*.sarif.json"))
    if not files:
        raise GateError(f"no SARIF files in {sarif_dir}; the analysis did not run")
    loaded = []
    for file in files:
        try:
            loaded.append((file, json.loads(file.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as exc:
            raise GateError(f"{file} is not valid SARIF JSON: {exc}") from exc
    return loaded


def rule_index(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map rule id to rule metadata across the driver and any extensions."""
    tool = run.get("tool", {})
    components = [tool.get("driver", {})] + list(tool.get("extensions", []))
    rules: dict[str, dict[str, Any]] = {}
    for component in components:
        for rule in component.get("rules", []) or []:
            rule_id = rule.get("id")
            if rule_id and rule_id not in rules:
                rules[rule_id] = rule
    return rules


def resolve_rule(result: dict[str, Any], run: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    rule_ref = result.get("rule") or {}
    tool = run.get("tool", {})
    component_index = (rule_ref.get("toolComponent") or {}).get("index")
    index = rule_ref.get("index")
    if index is not None:
        components = [tool.get("driver", {})] + list(tool.get("extensions", []))
        component = components[component_index] if component_index is not None else components[0]
        component_rules = component.get("rules", []) or []
        if 0 <= index < len(component_rules):
            return component_rules[index]
    return rules.get(result.get("ruleId", ""), {})


def primary_location(result: dict[str, Any]) -> tuple[str, int]:
    locations = result.get("locations") or []
    if not locations:
        return ("<no location>", 0)
    physical = locations[0].get("physicalLocation", {})
    uri = physical.get("artifactLocation", {}).get("uri", "<no uri>")
    line = int(physical.get("region", {}).get("startLine", 0) or 0)
    return (uri, line)


def fingerprint_of(result: dict[str, Any]) -> str:
    partial = result.get("partialFingerprints") or {}
    value = partial.get("primaryLocationLineHash")
    if value:
        return str(value)
    # CodeQL always emits primaryLocationLineHash; this fallback only keeps a
    # foreign SARIF from silently escaping the gate. It is line-based and will
    # rehash on adjacent edits, which is acceptable for a fallback.
    uri, line = primary_location(result)
    digest = hashlib.sha256(f"{result.get('ruleId')}|{uri}|{line}".encode()).hexdigest()
    return f"fallback:{digest[:16]}"


def severity_label(rule: dict[str, Any], result: dict[str, Any]) -> tuple[str, str]:
    """Return (kind, value): ('security', '7.5') or ('level', 'warning')."""
    props = rule.get("properties") or {}
    security = props.get("security-severity")
    if security not in (None, ""):
        return ("security", str(security))
    level = result.get("level") or (rule.get("defaultConfiguration") or {}).get("level") or "warning"
    return ("level", str(level).lower())


def is_gated(rule: dict[str, Any], result: dict[str, Any], min_security: float, fail_levels: set[str]) -> bool:
    kind, value = severity_label(rule, result)
    if kind == "security":
        try:
            return float(value) >= min_security
        except ValueError:
            # A rule with an unreadable severity gets the strict reading.
            return True
    return value in fail_levels


def annotate(kind: str, uri: str, line: int, message: str) -> None:
    # GitHub workflow command: shows the finding inline on the commit/PR.
    safe = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{kind} file={uri},line={max(line, 1)}::{safe}")


def gate(sarif_dir: Path, accepted_path: Path, language: str) -> int:
    min_security = _float_setting("CODEQL_GATE_MIN_SECURITY_SEVERITY", 4.0)
    fail_levels = _levels_setting("CODEQL_GATE_FAIL_LEVELS", "error,warning")
    acceptances = [a for a in load_acceptances(accepted_path) if a["language"] == language]
    accepted_keys = {(a["ruleId"], a["fingerprint"]): a for a in acceptances}

    present_keys: set[tuple[str, str]] = set()
    unaccepted: list[str] = []
    accepted_hits: list[str] = []
    below_floor = 0

    for file, sarif in load_sarif_files(sarif_dir):
        for run in sarif.get("runs", []):
            rules = rule_index(run)
            for result in run.get("results", []) or []:
                rule_id = str(result.get("ruleId", "<no rule>"))
                fingerprint = fingerprint_of(result)
                present_keys.add((rule_id, fingerprint))
                rule = resolve_rule(result, run, rules)
                uri, line = primary_location(result)
                kind, value = severity_label(rule, result)
                message = (result.get("message") or {}).get("text", "").strip().splitlines()[:1]
                text = message[0] if message else rule_id
                if not is_gated(rule, result, min_security, fail_levels):
                    below_floor += 1
                    continue
                acceptance = accepted_keys.get((rule_id, fingerprint))
                if acceptance is None:
                    unaccepted.append(f"{rule_id} ({kind} {value}) at {uri}:{line} [{fingerprint}] {text}")
                    annotate(
                        "error",
                        uri,
                        line,
                        f"CodeQL {rule_id} ({kind} {value}) is not accepted. "
                        f"Fix it, or accept fingerprint {fingerprint} in {accepted_path} with a reason.",
                    )
                else:
                    accepted_hits.append(
                        f"{rule_id} at {uri}:{line} accepted {acceptance['acceptedOn']} "
                        f"by {acceptance['acceptedBy']}: {acceptance['reason']}"
                    )

    stale = [a for a in acceptances if (a["ruleId"], a["fingerprint"]) not in present_keys]

    summary = [
        f"## CodeQL gate: {language}",
        "",
        f"- Severity floor: security-severity >= {min_security} (or level in {sorted(fail_levels)} when a rule has none)",
        f"- Findings below the floor: {below_floor}",
        f"- Accepted findings still present: {len(accepted_hits)}",
        f"- Unaccepted findings at or above the floor: {len(unaccepted)}",
        f"- Stale acceptances: {len(stale)}",
        "",
    ]
    for item in accepted_hits:
        summary.append(f"- accepted: {item}")
    for item in unaccepted:
        summary.append(f"- FAIL: {item}")
    for a in stale:
        summary.append(
            f"- STALE: {a['ruleId']} [{a['fingerprint']}] at {a['path']} accepted {a['acceptedOn']} "
            f"by {a['acceptedBy']} no longer matches a finding; remove it or re-triage at the new location"
        )
        annotate(
            "error",
            str(a["path"]),
            0,
            f"Stale CodeQL acceptance {a['ruleId']} [{a['fingerprint']}]: remove it from {accepted_path}.",
        )

    report = "\n".join(summary)
    print(report)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")

    return 1 if (unaccepted or stale) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sarif-dir", required=True, type=Path, help="directory holding *.sarif from codeql-action/analyze")
    parser.add_argument("--accepted", required=True, type=Path, help="path to codeql-accepted.json")
    parser.add_argument("--language", required=True, help="CodeQL language of this run (python, javascript-typescript)")
    args = parser.parse_args(argv)
    try:
        return gate(args.sarif_dir, args.accepted, args.language)
    except GateError as exc:
        print(f"::error::codeql_gate: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
