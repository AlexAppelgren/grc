"""The API documentation gate (scripts/api_docs_gate.py), against the standard in
docs/plans/briefs/API_DOCUMENTATION.md.

DOCUMENTED below is the worked example: a contract that satisfies every rule, so the
standard is executable and a sweep agent can copy a shape that is known to pass without
opening a real app's schemas.py. Each other test breaks exactly one rule in a copy of it
and pins that the gate says so, because a gate that cannot fail is not a gate.

The gate is loaded by path and run over these built documents, never over the repository's
openapi.json, so the tests keep their meaning as the real contract gets documented.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "api_docs_gate.py"

# ---------------------------------------------------------------------------------------
# The worked example. Every description says what the fact is in the bank's language, where
# it comes from, what a reader must not conclude from it, every value it may hold and every
# limit the schema states. Copy this shape; it is the one the gate is known to accept.
# ---------------------------------------------------------------------------------------
DOCUMENTED: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Worked example", "version": "1"},
    "components": {
        "schemas": {
            "VocabularyRef": {
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "The stable key of the vocabulary row, which is what an integration "
                            "stores and compares on. Keys never change once issued, while labels "
                            "are renamed freely, so never match on the label. The values are rows "
                            "in a vocabulary that a tenant's admin may extend or retire, not a "
                            "closed set; read GET /vocabularies for the live list."
                        ),
                    },
                    "kind": {
                        "type": "string",
                        "description": (
                            "Which vocabulary the row belongs to, for example obligation-status "
                            "or evidence-type. The kinds are rows an admin may extend, so treat "
                            "an unfamiliar vocabulary kind as data and not as an error."
                        ),
                    },
                    "label": {
                        "type": "string",
                        "description": (
                            "The row's name in the reader's language, for showing on screen only. "
                            "It is renamed whenever the bank prefers different wording, so storing "
                            "it or matching on it will break; store the key instead."
                        ),
                    },
                },
                "type": "object",
            },
            "ObligationSummary": {
                "description": "One obligation as the inventory holds it today.",
                "properties": {
                    "stableKey": {
                        "type": "string",
                        "maxLength": 120,
                        "description": (
                            "The obligation's permanent identity, issued once and never changed, "
                            "so an integration can follow the same obligation across versions. A "
                            "library fact: it changes only through an approved proposal. At most "
                            "120 characters; a longer key is refused with `validation_error`."
                        ),
                    },
                    "status": {
                        "$ref": "#/components/schemas/VocabularyRef",
                        "description": (
                            "Where the bank's own work on this obligation stands. This is the "
                            "bank's judgement in its own zone, never a library fact and never "
                            "shared with another tenant. The values are rows in the "
                            "obligation-status vocabulary that an admin may extend, so do not "
                            "treat them as a closed set; read GET /vocabularies for the live one."
                        ),
                    },
                    "origin": {
                        "type": "string",
                        "enum": ["agent", "user"],
                        "description": (
                            "Who put this obligation into the inventory: `agent` means a research "
                            "agent proposed it and the row stays labelled as machine output until "
                            "a person confirms it, `user` means a person at the bank entered or "
                            "confirmed it. An `agent` row is not a verified fact."
                        ),
                    },
                    "appliesToUs": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Whether this obligation binds the bank at all, which is a separate "
                            "fact from whether the bank complies with it. Defaults to false until "
                            "somebody decides; false therefore means undecided or out of scope, "
                            "never compliant."
                        ),
                    },
                },
                "type": "object",
            },
        }
    },
    "paths": {
        "/api/v1/obligations": {
            "get": {
                "operationId": "listObligations",
                "tags": ["Library"],
                "summary": "List the obligations in the bank's inventory",
                "description": (
                    "Call this to page through the inventory. It changes nothing and records no "
                    "audit event. Needs the obligation.read permission. An inventory with no "
                    "matches answers 200 with an empty items list, never 404."
                ),
                "parameters": [
                    {
                        "in": "query",
                        "name": "limit",
                        "required": False,
                        "description": (
                            "How many obligations to return in one page. Defaults to 20 and the "
                            "maximum is 100; asking for more is refused with `validation_error` "
                            "rather than quietly reduced, so a caller always knows what it got."
                        ),
                        "schema": {"type": "integer", "default": 20, "maximum": 100, "minimum": 1},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ObligationSummary"},
                                "example": {
                                    "stableKey": "se-fi-2019-23-s4",
                                    "status": {"key": "in-review", "kind": "obligation-status", "label": "In review"},
                                    "origin": "agent",
                                    "appliesToUs": False,
                                },
                            }
                        },
                    },
                    "409": {"description": "`four_eyes_violation`: the requester cannot approve their own proposal."},
                },
            }
        }
    },
}


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("api_docs_gate_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {spec.name: module}):
        spec.loader.exec_module(module)
    return module


def findings_for(document: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(where, rule, what) for every finding the gate makes about a document."""
    gate = load_gate()
    found, _ = gate.collect(document)
    return [(finding.where, finding.rule, finding.what) for finding in found]


def without(*path: str | int) -> dict[str, Any]:
    """A copy of the worked example with one key removed, to break one rule at a time."""
    document = copy.deepcopy(DOCUMENTED)
    node: Any = document
    for step in path[:-1]:
        node = node[step]
    del node[path[-1]]
    return document


def captured(call: Callable[[], int]) -> tuple[int, str]:
    """A gate's exit status and everything it printed: the failure message is the product
    here, so the tests read it the way a later agent will."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        status = call()
    return status, buffer.getvalue()


class TheWorkedExamplePasses(SimpleTestCase):
    def test_a_fully_documented_contract_has_no_findings(self) -> None:
        """If this fails, the worked example no longer is one and the tests below say nothing."""
        self.assertEqual(findings_for(DOCUMENTED), [])


class EveryRuleFires(SimpleTestCase):
    def test_a_property_with_no_description_is_named(self) -> None:
        document = without("components", "schemas", "ObligationSummary", "properties", "stableKey", "description")
        self.assertIn(
            ("ObligationSummary.stableKey", "description", "no description; every property needs one"),
            findings_for(document),
        )

    def test_a_description_that_only_restates_the_property_name_is_refused(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        document["components"]["schemas"]["ObligationSummary"]["properties"]["stableKey"]["description"] = "Stable key"
        found = [(where, rule) for where, rule, _ in findings_for(document)]
        self.assertIn(("ObligationSummary.stableKey", "description"), found)

    def test_an_enum_whose_description_misses_a_member_is_refused(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        document["components"]["schemas"]["ObligationSummary"]["properties"]["origin"]["description"] = (
            "Who put this obligation into the inventory: `agent` means a research agent "
            "proposed it and it stays labelled as machine output until a person confirms it."
        )
        matching = [what for where, rule, what in findings_for(document) if rule == "values"]
        self.assertTrue(matching, "an enum missing a member must be a values finding")
        self.assertIn("'user'", matching[0])

    def test_a_vocabulary_presented_as_a_closed_set_is_refused(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        document["components"]["schemas"]["ObligationSummary"]["properties"]["status"]["description"] = (
            "Where the bank's own work on this obligation stands. One of open, in-review or "
            "closed, and nothing else is ever returned by this endpoint."
        )
        found = [(where, rule) for where, rule, _ in findings_for(document)]
        self.assertIn(("ObligationSummary.status", "values"), found)

    def test_the_key_of_a_vocabulary_row_must_name_its_vocabulary(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        document["components"]["schemas"]["VocabularyRef"]["properties"]["key"]["description"] = (
            "The stable key of the row, which an integration stores and compares on rather "
            "than the label, because a label is renamed whenever the bank prefers other wording."
        )
        found = [(where, rule) for where, rule, _ in findings_for(document)]
        self.assertIn(("VocabularyRef.key", "values"), found)

    def test_a_limit_the_description_never_states_is_refused(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        document["components"]["schemas"]["ObligationSummary"]["properties"]["stableKey"]["description"] = (
            "The obligation's permanent identity, issued once and never changed, so an "
            "integration can follow the same obligation across versions. A library fact, "
            "changed only through an approved proposal."
        )
        matching = [what for where, rule, what in findings_for(document) if where == "ObligationSummary.stableKey"]
        self.assertTrue(matching)
        self.assertIn("maxLength=120", matching[0])

    def test_a_default_the_description_never_states_is_refused(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        document["components"]["schemas"]["ObligationSummary"]["properties"]["appliesToUs"]["description"] = (
            "Whether this obligation binds the bank at all, which is a separate fact from "
            "whether the bank complies with it. Nobody may infer compliance from it."
        )
        found = [(where, rule) for where, rule, _ in findings_for(document)]
        self.assertIn(("ObligationSummary.appliesToUs", "limits"), found)

    def test_an_operation_with_no_summary_is_refused(self) -> None:
        document = without("paths", "/api/v1/obligations", "get", "summary")
        found = [(where, rule, what) for where, rule, what in findings_for(document)]
        self.assertIn(("listObligations", "operations", "no summary; say what the caller achieves"), found)

    def test_a_summary_that_only_re_spaces_the_operation_id_is_refused(self) -> None:
        """Ninja titles an operation from its function name, so an undocumented operation
        arrives looking documented."""
        document = copy.deepcopy(DOCUMENTED)
        document["paths"]["/api/v1/obligations"]["get"]["summary"] = "List Obligations"
        matching = [what for where, rule, what in findings_for(document) if where == "listObligations"]
        self.assertTrue(any("re-spaces the operationId" in what for what in matching), matching)

    def test_an_operation_with_no_description_is_refused(self) -> None:
        document = without("paths", "/api/v1/obligations", "get", "description")
        matching = [what for where, rule, what in findings_for(document) if where == "listObligations"]
        self.assertTrue(any(what.startswith("no description") for what in matching))

    def test_an_operation_with_no_example_is_refused(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        content = document["paths"]["/api/v1/obligations"]["get"]["responses"]["200"]["content"]
        del content["application/json"]["example"]
        matching = [what for where, rule, what in findings_for(document) if where == "listObligations"]
        self.assertTrue(any(what.startswith("no example") for what in matching))

    def test_an_error_code_no_route_can_raise_is_refused(self) -> None:
        document = copy.deepcopy(DOCUMENTED)
        document["paths"]["/api/v1/obligations"]["get"]["responses"]["409"]["description"] = (
            "`obligation_frozen`: the obligation cannot be changed right now."
        )
        matching = [what for where, rule, what in findings_for(document) if where == "listObligations"]
        self.assertTrue(any("`obligation_frozen`" in what for what in matching), matching)

    def test_a_raisable_error_code_is_accepted(self) -> None:
        """The check refuses an invented code, not the act of documenting one."""
        self.assertEqual(findings_for(DOCUMENTED), [])

    def test_a_query_parameter_needs_its_own_description(self) -> None:
        """Ninja inlines a Query model, so the pagination limits only exist here."""
        document = without("paths", "/api/v1/obligations", "get", "parameters", 0, "description")
        found = [(where, rule) for where, rule, _ in findings_for(document)]
        self.assertIn(("listObligations.limit", "description"), found)


class TheRaisableCodesComeFromTheSource(SimpleTestCase):
    """The codes a sweep may document are read from `backend/apps/`, never typed by hand.

    The hand-written list that came before held 26 codes while the API answered far more,
    so the first sweep could not document `invalid_slug`, `in_use` or `idempotency_conflict`
    — codes a caller really has to branch on — and the honest way past the gate was to
    leave them out (2026-09-20)."""

    def test_a_code_a_route_raises_is_accepted(self) -> None:
        codes = load_gate().RAISABLE_CODES
        for code in ("invalid_slug", "in_use", "system_row", "idempotency_conflict"):
            with self.subTest(code=code):
                self.assertIn(code, codes)

    def test_a_code_nothing_raises_is_not(self) -> None:
        self.assertNotIn("obligation_frozen", load_gate().RAISABLE_CODES)

    def test_a_code_only_a_test_names_is_not_raisable(self) -> None:
        """A test module is not a source: `tests_*.py` is skipped by the scan."""
        self.assertNotIn("a_code_no_route_raises", load_gate().RAISABLE_CODES)

    def test_the_scan_fails_closed_when_it_finds_nothing(self) -> None:
        module = load_gate()
        self.assertGreaterEqual(len(module.RAISABLE_CODES), module.CODES_FLOOR)


class TheLedgerOnlyShrinks(SimpleTestCase):
    """The ledger explains what is not documented yet. Anything undocumented that is not in
    it fails, and a line whose subject is now documented fails as stale, so no sweep can
    park new work in it and none can leave a closed line behind."""

    def run_gate(self, document: dict[str, Any], ledger: str) -> tuple[int, str]:
        gate = load_gate()
        with tempfile.TemporaryDirectory() as tmp:
            built = Path(tmp) / "openapi.json"
            pending = Path(tmp) / "api_docs_pending.txt"
            built.write_text(json.dumps(document), encoding="utf-8")
            pending.write_text(ledger, encoding="utf-8")
            with mock.patch.object(gate, "BUILT", built), mock.patch.object(gate, "PENDING", pending):
                return captured(lambda: gate.main([]))

    def test_a_documented_contract_with_an_empty_ledger_passes(self) -> None:
        status, _ = self.run_gate(DOCUMENTED, "# nothing pending\n")
        self.assertEqual(status, 0)

    def test_something_undocumented_and_not_in_the_ledger_fails(self) -> None:
        document = without("components", "schemas", "ObligationSummary", "properties", "origin", "description")
        status, printed = self.run_gate(document, "# nothing pending\n")
        self.assertEqual(status, 1)
        self.assertIn("ObligationSummary.origin", printed)
        self.assertIn("python backend/scripts/api_docs_gate.py", printed)

    def test_something_undocumented_that_the_ledger_carries_passes(self) -> None:
        document = without("components", "schemas", "ObligationSummary", "properties", "origin", "description")
        status, _ = self.run_gate(document, "schema ObligationSummary app library 1 finding (description)\n")
        self.assertEqual(status, 0)

    def test_sweeping_one_app_ignores_only_that_apps_lines(self) -> None:
        """`--app library` is what a sweep agent runs: it reports what library still owes and
        stays quiet about every other app, so ten sweeps never edit the ledger to see their
        own work."""
        gate = load_gate()
        document = without("components", "schemas", "ObligationSummary", "properties", "origin", "description")
        ledger = (
            "schema ObligationSummary app library 1 finding (description)\n"
            "schema VocabularyRef app taxonomy 1 finding (description)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            built = Path(tmp) / "openapi.json"
            pending = Path(tmp) / "api_docs_pending.txt"
            built.write_text(json.dumps(document), encoding="utf-8")
            pending.write_text(ledger, encoding="utf-8")
            with mock.patch.object(gate, "BUILT", built), mock.patch.object(gate, "PENDING", pending):
                status, printed = captured(lambda: gate.main(["--app", "library"]))
                self.assertEqual(status, 1)
                self.assertIn("ObligationSummary.origin", printed)
                # taxonomy keeps its suppression, and the run wrote nothing back.
                self.assertNotIn("VocabularyRef", printed)
                self.assertEqual(pending.read_text(encoding="utf-8"), ledger)
                # An app that owes nothing goes green.
                self.assertEqual(captured(lambda: gate.main(["--app", "taxonomy"]))[0], 0)

    def test_a_ledger_line_that_is_already_documented_fails_as_stale(self) -> None:
        status, printed = self.run_gate(DOCUMENTED, "schema ObligationSummary app library 1 finding (description)\n")
        self.assertEqual(status, 1)
        self.assertIn("stale ledger line", printed)
        self.assertIn("ObligationSummary", printed)


class TheFailureTeaches(SimpleTestCase):
    """A later agent reads the failure and nothing else, so it has to name the property, the
    rule it breaks and one shape that passes."""

    def test_a_finding_names_the_property_the_rule_and_a_compliant_example(self) -> None:
        gate = load_gate()
        document = without("components", "schemas", "ObligationSummary", "properties", "origin", "description")
        found, _ = gate.collect(document)
        status, printed = captured(lambda: gate.report(found, {}))
        self.assertEqual(status, 1)
        self.assertIn("ObligationSummary.origin", printed)
        self.assertIn("What a documented one looks like:", printed)
        self.assertIn("docs/plans/briefs/API_DOCUMENTATION.md", printed)


class TheGateReadsTheContractNotTheSource(SimpleTestCase):
    def test_the_repository_contract_is_accounted_for_by_the_ledger(self) -> None:
        """The committed openapi.json and the committed ledger agree: every undocumented
        schema and operation is listed, and no listed one is already documented. This is the
        gate CI runs, pinned here so a regeneration that documents nothing cannot pass."""
        gate = load_gate()
        self.assertEqual(gate.main([]), 0)
