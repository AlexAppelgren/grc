#!/usr/bin/env python
"""Contract drift (playbook 9, 14): docs/inputs/openapi.yaml is the designed target, the
exported openapi.json the truth of what is built. Every designed operation that is
missing, renamed or reshaped must be explained, either in docs/inputs/INPUT_DELTAS.md
(a row naming the backticked `METHOD /path` or the operationId) or in scripts/contract_drift_pending.txt
(one line per operation naming the build-plan chunk that delivers it). Anything
unexplained fails.

Matching: designed paths are relative to the designed server's `/v1`; built paths carry
`/api/v1`. Path parameters are compared by position, not name (`{userId}` and
`{user_id}` are the same slot). "Reshaped" means the set of top-level property names of
the request body or of the 2xx response differs.

`--write-pending` regenerates contract_drift_pending.txt for every currently missing
operation, keeping any existing chunk annotations; a human then reviews the chunks.

Proven to fail 2026-09-19 by deleting the `GET /me` line from the pending file while
its shape still differs from the designed `Me` (exit 1, operation named), then restored.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
DESIGNED = ROOT / "docs" / "inputs" / "openapi.yaml"
BUILT = ROOT / "openapi.json"
DELTAS = ROOT / "docs" / "inputs" / "INPUT_DELTAS.md"
PENDING = BACKEND / "scripts" / "contract_drift_pending.txt"
BUILT_PREFIX = "/api/v1"
METHODS = ("get", "post", "put", "patch", "delete")

# First-cut mapping of designed tags and paths to build-plan chunks, used only by
# --write-pending to propose a chunk. Reviewed by a person in the pending file.
TAG_CHUNK = {
    "System": 0,
    "Identity and access": 1,
    "Taxonomy and footprint": 2,
    "Inventory": 3,
    "Proposals": 4,
    "Watch": 5,
    "Case workflow": 9,
    "Search and ask": 7,
    "Home and roadmap": 6,
    "Register": 8,
    "Reports and exports": 12,
    "Audit and AI governance": 4,
    "Collaboration": 10,
    "Integration": 13,
}
PATH_CHUNK_OVERRIDES = (
    ("/tenant/api-keys", 5),
    ("/agent-runs", 5),
    ("/saved-searches", 13),
    ("/eval/", 7),
    ("/audit-events", 1),
    ("/ai-generations", 7),
    ("/problem-reports", 4),
    ("/changes/{}/so-what", 5),
    ("/changes/{}/events", 5),
    ("/changes/{}/documents", 5),
    ("/changes/{}/obligations", 5),
    ("/changes", 5),
    ("/exports", 12),
    ("/imports", 12),
    ("/calendar", 6),
    ("/upcoming", 6),
    ("/attestations", 13),
    ("/waivers", 13),
)


def slot(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


@dataclass(frozen=True)
class Shape:
    request: frozenset[str]
    response: frozenset[str]


def _props(schema: dict | None, components: dict) -> frozenset[str]:
    if not schema:
        return frozenset()
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return _props(components.get("schemas", {}).get(name), components)
    props = set(schema.get("properties", {}))
    for part in schema.get("allOf", []):
        props |= _props(part, components)
    return frozenset(props)


def operations(document: dict, prefix: str) -> dict[tuple[str, str], tuple[str, Shape, str]]:
    """(METHOD, slotted path) -> (operationId, shape, tag)."""
    found: dict[tuple[str, str], tuple[str, Shape, str]] = {}
    components = document.get("components", {})
    for path, item in document.get("paths", {}).items():
        if prefix and path.startswith(prefix):
            path = path[len(prefix) :] or "/"
        for method in METHODS:
            op = item.get(method)
            if not op:
                continue
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            response_schema = None
            for code, response in op.get("responses", {}).items():
                if str(code).startswith("2"):
                    response_schema = response.get("content", {}).get("application/json", {}).get("schema")
                    break
            tag = (op.get("tags") or [""])[0]
            found[(method.upper(), slot(path))] = (
                op.get("operationId", ""),
                Shape(_props(body, components), _props(response_schema, components)),
                tag,
            )
    return found


def explained_in_deltas(method: str, path: str, operation_id: str) -> bool:
    """A delta explains an operation only by naming it: its operationId, or the backticked
    `METHOD /path` with the designed parameter names. A bare path would match too much
    (`/me` appears in a sentence about `/me/passkeys`), which is how `GET /me` once slipped
    through as explained while its shape still differed."""
    text = DELTAS.read_text(encoding="utf-8")
    if operation_id and re.search(rf"`{re.escape(operation_id)}`", text):
        return True
    pattern = re.escape(f"`{method} ") + re.escape(path).replace(r"\{\}", r"\{[^}]+\}") + "`"
    return re.search(pattern, text) is not None


def pending_entries() -> dict[tuple[str, str], str]:
    entries: dict[tuple[str, str], str] = {}
    if not PENDING.exists():
        return entries
    for line in PENDING.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+chunk\s+(?P<chunk>\d+)(?:\s+(?P<note>.*))?$", line)
        if not match:
            print(f"contract_drift: unparseable pending line: {line}")
            continue
        entries[(match.group("method"), slot(match.group("path")))] = match.group("chunk")
    return entries


def proposed_chunk(path: str, tag: str) -> int:
    for needle, chunk in PATH_CHUNK_OVERRIDES:
        if path.startswith(needle):
            return chunk
    return TAG_CHUNK.get(tag, 14)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-pending", action="store_true")
    args = parser.parse_args(argv)
    if not BUILT.exists():
        print(f"contract_drift: {BUILT} missing; run `manage.py export_openapi --out ../openapi.json` first")
        return 1
    designed = operations(yaml.safe_load(DESIGNED.read_text(encoding="utf-8")), "")
    built = operations(json.loads(BUILT.read_text(encoding="utf-8")), BUILT_PREFIX)
    pending = pending_entries()

    missing: list[tuple[str, str, str, str]] = []
    reshaped: list[tuple[str, str, str, str]] = []
    for key, (operation_id, shape, tag) in sorted(designed.items()):
        method, path = key
        if key not in built:
            missing.append((method, path, operation_id, tag))
            continue
        _, built_shape, _ = built[key]
        differences = []
        if shape.request != built_shape.request:
            differences.append(f"request {sorted(shape.request)} -> {sorted(built_shape.request)}")
        if shape.response != built_shape.response:
            differences.append(f"response {sorted(shape.response)} -> {sorted(built_shape.response)}")
        if differences:
            reshaped.append((method, path, operation_id, "; ".join(differences)))

    if args.write_pending:
        lines = [
            "# Designed operations (docs/inputs/openapi.yaml) not yet delivered or not yet in their",
            "# designed shape, each with the build-plan chunk that delivers it (docs/plans/Build_Plan.md).",
            "# One line per operation: <METHOD> <path> chunk <n> [note]. Generated by",
            "# scripts/contract_drift.py --write-pending; chunks are a first cut for a person to review.",
            "# A line is deleted when its operation ships in the designed shape, or moved to",
            "# docs/inputs/INPUT_DELTAS.md when the build departs from the design on purpose.",
            "",
        ]
        reshaped_with_tag = [(m, p, o, designed[(m, p)][2]) for m, p, o, _ in reshaped]
        for method, path, operation_id, tag in missing + reshaped_with_tag:
            if explained_in_deltas(method, path, operation_id):
                continue
            chunk = pending.get((method, path)) or str(proposed_chunk(path, tag))
            note = "reshaped: Phase 0 shape differs from the design" if (method, path, operation_id) in {
                (m, p, o) for m, p, o, _ in reshaped
            } else ""
            lines.append(f"{method} {path} chunk {chunk} {note}".rstrip())
        PENDING.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"contract_drift: wrote {PENDING.relative_to(ROOT).as_posix()} ({len(lines) - 7} operations)")
        return 0

    unexplained: list[str] = []
    for method, path, operation_id, _ in missing:
        if (method, path) in pending or explained_in_deltas(method, path, operation_id):
            continue
        unexplained.append(f"missing  {method} {path} ({operation_id})")
    for method, path, operation_id, why in reshaped:
        if (method, path) in pending or explained_in_deltas(method, path, operation_id):
            continue
        unexplained.append(f"reshaped {method} {path} ({operation_id}): {why}")
    stale = [f"{m} {p}" for (m, p) in pending if (m, p) in built and (m, p) not in {(a, b) for a, b, _, _ in reshaped}]

    print(
        f"contract_drift: {len(designed)} designed, {len(built)} built, {len(missing)} missing, "
        f"{len(reshaped)} reshaped, {len(pending)} pending, {len(unexplained)} unexplained"
    )
    for line in unexplained:
        print("  " + line)
    for line in stale:
        print(f"  stale pending entry (delivered in the designed shape): {line}")
    if unexplained or stale:
        print("Explain each in docs/inputs/INPUT_DELTAS.md or scripts/contract_drift_pending.txt with its chunk.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
