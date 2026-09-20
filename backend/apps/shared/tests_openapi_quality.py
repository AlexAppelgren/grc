"""The OpenAPI quality gate (scripts/openapi_quality.py): the specification documents
itself, so a bank integrating from outside reads openapi.json and needs nothing else
(CONVENTIONS 1.8). The gate is loaded by path and run over a planted document, never over
the real one, except in the last test, which pins the committed contract green so an
undocumented property cannot reach main through a suite that never ran the gate."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "openapi_quality.py"

GOOD_PROPERTY = "The Swedish authority that issued the instrument, so a bank can tell an FFFS rule from an EU one."


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("openapi_quality_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {spec.name: module}):  # its dataclasses look themselves up
        spec.loader.exec_module(module)
    return module


def document(properties: dict[str, Any], *, operation_description: str = GOOD_PROPERTY) -> dict[str, Any]:
    return {
        "components": {"schemas": {"PlantedRow": {"properties": properties, "type": "object"}}},
        "paths": {
            "/api/v1/planted": {
                "get": {
                    "operationId": "listPlanted",
                    "summary": "List Planted",
                    "description": operation_description,
                    "tags": ["Planted"],
                }
            }
        },
    }


def problems(gate: ModuleType, doc: dict[str, Any], allowlist: list[Any] | None = None) -> dict[str, str]:
    findings, stale, _, _, _ = gate.run(doc, allowlist or [])
    return {finding.target: finding.problem for finding in findings + stale}


class PlantedSchema(SimpleTestCase):
    """The planted bad schema: every rule fires, and says which property to fix."""

    def test_an_undocumented_or_hollow_property_fails(self) -> None:
        gate = load_gate()
        found = problems(
            gate,
            document(
                {
                    "issuer": {"type": "string", "description": GOOD_PROPERTY},
                    "reference": {"type": "string"},
                    "effectiveFrom": {"type": "string", "description": "The date."},
                    "supervisorName": {"type": "string", "description": "The name of the supervisor as a string value."},
                }
            ),
        )
        self.assertNotIn("PlantedRow.issuer", found)
        self.assertIn("no description", found["PlantedRow.reference"])
        self.assertIn("words", found["PlantedRow.effectiveFrom"])
        self.assertIn("repeats the field name", found["PlantedRow.supervisorName"])

    def test_an_enumerated_property_names_its_values(self) -> None:
        gate = load_gate()
        silent = "Where the bank stands on the change, which drives the colour of the pill on the timeline."
        found = problems(
            gate,
            document(
                {
                    "status": {"type": "string", "enum": ["open", "closed"], "description": silent},
                    "phase": {
                        "anyOf": [{"type": "string", "enum": ["draft", "final"]}, {"type": "null"}],
                        "description": f"{silent} Either `draft` while the bank is still working or `final` once signed off.",
                    },
                }
            ),
        )
        self.assertIn("closed, open", found["PlantedRow.status"])
        self.assertNotIn("PlantedRow.phase", found)

    def test_a_keyed_property_says_where_its_values_come_from(self) -> None:
        gate = load_gate()
        silent = "What the bank files this obligation under when it reports to the board every quarter."
        found = problems(
            gate,
            document(
                {
                    "kind": {"type": "string", "description": silent},
                    "urgencyKey": {"type": "string", "description": silent},
                    "roleKeys": {
                        "items": {"type": "string"},
                        "type": "array",
                        "description": f"{silent} A key from the roles list, which an admin manages.",
                    },
                    "plainKey": {"type": "string", "description": silent},
                }
            ),
        )
        self.assertIn("where its values come from", found["PlantedRow.kind"])
        self.assertNotIn("PlantedRow.roleKeys", found)
        # A singular `*Key` is a secret or an identifier, not a list member: no source demanded.
        self.assertNotIn("PlantedRow.urgencyKey", found)
        self.assertNotIn("PlantedRow.plainKey", found)

    def test_an_operation_without_a_description_fails(self) -> None:
        gate = load_gate()
        self.assertIn("no description", problems(gate, document({}, operation_description=""))["listPlanted"])
        self.assertIn("words", problems(gate, document({}, operation_description="Lists them."))["listPlanted"])


class Allowlist(SimpleTestCase):
    """The allowlist covers what genuinely needs nothing, each line with its reason, and
    cannot rot: a line that suppresses nothing is a finding."""

    def parse(self, gate: ModuleType, text: str) -> tuple[list[Any], list[Any]]:
        path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "allowlist.txt"
        path.write_text(text, encoding="utf-8")
        return gate.load_allowlist(path)

    def test_an_entry_without_a_reason_is_refused(self) -> None:
        gate = load_gate()
        entries, findings = self.parse(gate, "PlantedRow.reference\nPlantedRow.other  # the row id, an opaque handle\n")
        self.assertEqual([entry.target for entry in entries], ["PlantedRow.other"])
        self.assertIn("carries no reason", findings[0].problem)

    def test_an_entry_suppresses_its_property_and_a_tag_its_operations(self) -> None:
        gate = load_gate()
        entries, _ = self.parse(
            gate,
            "PlantedRow.reference  # an opaque handle the bank never reads\ntag:Planted  # documented by a later package\n",
        )
        found = problems(gate, document({"reference": {"type": "string"}}, operation_description=""), entries)
        self.assertEqual(found, {})

    def test_a_glob_covers_a_whole_schema_and_goes_stale_when_it_is_documented(self) -> None:
        gate = load_gate()
        entries, _ = self.parse(gate, "Planted*.*  # documented by a later package\n")
        self.assertEqual(problems(gate, document({"reference": {"type": "string"}}), entries), {})
        found = problems(gate, document({"reference": {"type": "string", "description": GOOD_PROPERTY}}), entries)
        self.assertIn("covers nothing any more", found["Planted*.*"])


class CommittedContract(SimpleTestCase):
    """The committed openapi.json passes the gate with the committed allowlist."""

    def test_the_contract_is_documented_or_allowlisted_with_a_reason(self) -> None:
        gate = load_gate()
        entries, findings = gate.load_allowlist(gate.ALLOWLIST)
        kept, stale, properties, operations, _ = gate.run(json.loads(gate.SPEC.read_text(encoding="utf-8")), entries)
        self.assertEqual([f"{finding.target}: {finding.problem}" for finding in findings + kept + stale], [])
        self.assertGreater(properties, 0)
        self.assertGreater(operations, 0)
