"""The shipped definition folders, their reader and the seed that loads them (AGT-03, AGT-04,
c11-runner-and-definitions).

The reader is checked against PyYAML on every field the seed stores, including the platform
fence's columns and the tool names; the seed is checked to write an agent row and its first
version row per shipped folder with an audit event each, and a second run to change nothing;
and the bank-addable definition is checked to carry no tool whose key scope reaches the
shared library.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import yaml
from django.test import SimpleTestCase, TestCase

from apps.agents import seeds
from apps.agents.models import Agent, AgentScopeKind, AgentVersion, AgentWritesTo
from apps.agents.seeds import SHIPPED, definitions, seed_agent_definitions
from apps.agents.seeds.definition import DEFINITIONS, DefinitionError, read_definition
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write

TENANT_DEFINITION = "tenant-source-watch"
# Every key scope that writes, or decides what is written to, the shared library or the
# watch feed every bank reads: the proposal door, the review queue behind it, and the
# platform's own run, source and change writes (PLATFORM_ONLY_SCOPES). A bank's agent holds
# none of them, whatever else a key may carry.
LIBRARY_REACHING_SCOPES = perms.PLATFORM_ONLY_SCOPES | {perms.SCOPE_PROPOSALS_WRITE}


def _path(name: str, version: int) -> Path:
    return DEFINITIONS / name / f"v{version}" / "definition.yaml"


def _parsed(name: str, version: int) -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(_path(name, version).read_text(encoding="utf-8"))
    return parsed


class TheReaderAgreesWithPyYaml(SimpleTestCase):
    def test_every_field_the_seed_stores_reads_as_pyyaml_reads_it(self) -> None:
        for name, version in SHIPPED:
            parsed, read = _parsed(name, version), read_definition(_path(name, version))
            with self.subTest(name):
                self.assertEqual(
                    (read.key, read.version, read.kind, read.status, read.scope, read.writes_to, read.model, read.prompt),
                    (
                        parsed["id"],
                        parsed["version"],
                        parsed["kind"],
                        parsed["status"],
                        parsed["scope"],
                        parsed["writes_to"],
                        parsed["model"],
                        parsed["prompt"],
                    ),
                )
                self.assertIs(read.tenant_configurable, parsed["tenant_configurable"])
                # A folded block keeps a trailing newline in YAML; the column does not.
                self.assertEqual(read.description, parsed["description"].strip())
                self.assertEqual(read.change_note, parsed["change_note"].strip())
                self.assertEqual(read.tools, tuple(tool["name"] for tool in parsed["tools"]))

    def test_the_fence_is_set_by_each_file(self) -> None:
        fence = {read.key: (read.scope, read.tenant_configurable, read.writes_to) for read in definitions()}
        self.assertEqual(fence["watch-sweeper"], (AgentScopeKind.PLATFORM.value, False, AgentWritesTo.LIBRARY.value))
        self.assertEqual(fence["library-confirmer"], (AgentScopeKind.PLATFORM.value, False, AgentWritesTo.LIBRARY.value))
        self.assertEqual(fence[TENANT_DEFINITION], (AgentScopeKind.TENANT.value, True, AgentWritesTo.TENANT.value))

    def test_every_prompt_a_definition_names_ships_beside_it(self) -> None:
        for read in definitions():
            self.assertTrue((DEFINITIONS / read.key / f"v{read.version}" / read.prompt).is_file(), read.key)
        self.assertTrue((DEFINITIONS / TENANT_DEFINITION / "v1" / "evals" / "README.md").is_file())

    def test_a_definition_it_cannot_read_raises_naming_its_file(self) -> None:
        good = _path(TENANT_DEFINITION, 1).read_text(encoding="utf-8")
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "definition.yaml"
        for body, why in (
            (good.replace("scope: tenant ", "scope: bank "), "a scope that is not a kind"),
            (good.replace("writes_to: tenant ", "writes_to: shared_library "), "a zone that is not a kind"),
            (good.replace("tenant_configurable: true", "tenant_configurable: yes"), "a flag that is not true or false"),
            (good.replace("model: claude-opus-5", "model: \"claude\""), "a quoted model"),
            (good.replace("change_note: >", "change_notes: >"), "a missing change note"),
            (good.replace("  - name: findSimilar", "  - operation: x"), "a tool entry without its name first"),
            (good.replace("tools:\n", "tool_list:\n"), "no tool list"),
        ):
            self.assertNotEqual(body, good, why)
            path.write_text(body, encoding="utf-8")
            with self.subTest(why), self.assertRaises(DefinitionError) as refused:
                read_definition(path)
            self.assertIn(str(path), str(refused.exception))


class TheBankAddableDefinition(SimpleTestCase):
    """A bank's own agent never carries a tool that writes the shared library (AGT-04,
    D-57, D-61): proved from its file, against the key scopes that reach the library."""

    def test_its_tools_reach_no_scope_that_writes_the_library(self) -> None:
        definition = _parsed(TENANT_DEFINITION, 1)
        scopes = {scope for tool in definition["tools"] for scope in tool.get("scopes", ())}
        self.assertTrue(scopes, "it reads through key scopes like any agent")
        self.assertLessEqual(scopes, perms.ALL_SCOPES)
        self.assertEqual(scopes & LIBRARY_REACHING_SCOPES, set())
        self.assertLessEqual(scopes, perms.TENANT_KEY_SCOPES, "nothing a bank's own key may not hold")

    def test_every_tool_without_an_operation_is_the_runners_own(self) -> None:
        for tool in _parsed(TENANT_DEFINITION, 1)["tools"]:
            if "operation" not in tool:
                self.assertEqual(tool.get("kind"), "runtime", tool["name"])
                self.assertNotIn("scopes", tool, tool["name"])

    def test_every_shipped_platform_definition_still_reaches_the_library_through_a_door(self) -> None:
        """The other side of the comparison: the scope set is the one the platform agents
        do use, so an empty intersection above means something."""
        for read in definitions():
            if read.scope == AgentScopeKind.PLATFORM.value:
                scopes = {scope for tool in _parsed(read.key, read.version)["tools"] for scope in tool.get("scopes", ())}
                self.assertTrue(scopes & LIBRARY_REACHING_SCOPES, read.key)


class TheSeed(TestCase):
    def test_it_creates_an_agent_and_its_first_version_per_folder_with_an_audit_event_each(self) -> None:
        self.assertEqual(seed_agent_definitions(), len(SHIPPED))
        for read in definitions():
            agent = Agent.objects.get(key=read.key)
            self.assertEqual(
                (agent.scope, agent.tenant_configurable, agent.writes_to, agent.current_version),
                (read.scope, read.tenant_configurable, read.writes_to, read.version),
            )
            version = AgentVersion.objects.get(agent=agent)
            self.assertEqual(
                (version.version_number, version.model, version.prompt_path, version.tools, version.change_note),
                (read.version, read.model, read.prompt, list(read.tools), read.change_note),
            )
            self.assertIsNone(version.published_by_id, "loaded by the deploy, not published by a person")
            seeded = AuditEvent.objects.get(action="agent.seeded", subject_id=agent.id)
            self.assertEqual(
                (seeded.after["scope"], seeded.after["tenantConfigurable"], seeded.after["writesTo"]),
                (read.scope, read.tenant_configurable, read.writes_to),
            )
            loaded = AuditEvent.objects.get(action="agent_version.seeded", subject_id=version.id)
            self.assertIsNone(loaded.tenant_id, "a version is a library row, so its audit row is a library row")

    def test_a_second_run_creates_nothing_and_changes_nothing(self) -> None:
        seed_agent_definitions()
        agents = list(Agent.objects.values())
        versions = list(AgentVersion.objects.values())
        audits = AuditEvent.objects.count()
        self.assertEqual(seed_agent_definitions(), 0)
        self.assertEqual(list(Agent.objects.values()), agents)
        self.assertEqual(list(AgentVersion.objects.values()), versions)
        self.assertEqual(AuditEvent.objects.count(), audits)

    def test_an_agent_seeded_before_versions_existed_gets_the_version_it_is_on_and_no_other(self) -> None:
        with library_write("test"):
            before_versions = Agent.objects.create(key="watch-sweeper", kind="watch", current_version=1)
            on_an_older_folder = Agent.objects.create(key="library-confirmer", kind="review", current_version=1)
        self.assertEqual(seed_agent_definitions(), 1, "only the bank-addable definition is new")
        self.assertEqual(list(before_versions.versions.values_list("version_number", flat=True)), [1])
        self.assertFalse(on_an_older_folder.versions.exists(), "a later folder arrives through publish, never a deploy")
        on_an_older_folder.refresh_from_db()
        self.assertEqual(on_an_older_folder.current_version, 1, "a deploy never moves an agent to another version")

    def test_a_definition_it_cannot_read_stops_the_seed_before_anything_is_written(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        for name, version in SHIPPED:
            shutil.copytree(DEFINITIONS / name / f"v{version}", directory / name / f"v{version}")
        broken = directory / TENANT_DEFINITION / "v1" / "definition.yaml"
        broken.write_text(broken.read_text(encoding="utf-8").replace("scope: tenant ", "scope: bank "), encoding="utf-8")
        with mock.patch.object(seeds, "DEFINITIONS", directory), self.assertRaises(DefinitionError) as refused:
            seed_agent_definitions()
        self.assertIn(str(broken), str(refused.exception))
        self.assertFalse(Agent.objects.exists(), "the platform's own agents are not half-seeded either")
