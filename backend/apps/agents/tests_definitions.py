"""Publishing and retiring a version of one of the platform's agents, reading one definition,
and the version a run pins (AGT-03, ADM-02, AGT-06).

A version is published from the folder the build ships, read by the seed's own reader and
never from a body pasted into a request, so what runs is what was reviewed into the tree.
A published version is append-only: a run points at the version it opened with, and
retiring one only stops new runs. Every publish and retire needs `agent_definitions.manage`
and a fresh passkey, and leaves one audit row with no tenant, because it changes what runs
for every bank at once.

Proven to fail 2026-09-25 against the declared contract: every route test below answered
501 `not_built` before `definitions.py` was written, and the pinning tests found runs with
no version.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.agents import runs, testing as agent_build
from apps.agents.models import Agent, AgentRun, AgentVersion
from apps.agents.schemas import AgentRunInput
from apps.agents.seeds import definition as reader
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, stub_session, user_principal

DEFINITIONS = "/api/v1/agent-definitions"
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}
JSON = "application/json"
SHIPPED_FOLDER = reader.DEFINITIONS / "watch-sweeper" / "v1"
CHANGED_PROMPT = "Sweep the registered sources and read the new FFFS index page first.\n"


def shipped_folder(root: Path, key: str, version: int, *, prompt: str = CHANGED_PROMPT) -> Path:
    """A version folder as the build would ship it for `key`: the sweeper's own definition
    under that id and number, with a prompt of its own. Written under `root`, which a test
    puts in place of `backend/agents/` for the reader."""
    folder = root / key / f"v{version}"
    folder.mkdir(parents=True)
    text = SHIPPED_FOLDER.joinpath("definition.yaml").read_text(encoding="utf-8")
    text = re.sub(r"(?m)^id: .*$", f"id: {key}", text)
    text = re.sub(r"(?m)^version: .*$", f"version: {version}", text)
    folder.joinpath("definition.yaml").write_text(text, encoding="utf-8")
    folder.joinpath("prompt.md").write_text(prompt, encoding="utf-8")
    return folder


@contextmanager
def definitions_root() -> Iterator[Path]:
    """A throwaway `backend/agents/` the reader reads from for the length of the block."""
    root = Path(tempfile.mkdtemp())
    try:
        with mock.patch.object(reader, "DEFINITIONS", root):
            yield root
    finally:
        shutil.rmtree(root)


def platform_agent(key: str, *, versions: int) -> Agent:
    """One of bleqq's agents at version `versions`, with every earlier version published."""
    row = agent_build.agent(key=key, version=versions)
    with library_write("test"):
        for number in range(1, versions + 1):
            AgentVersion.objects.create(agent=row, version_number=number, model="claude-opus-5", prompt_path="prompt.md")
    return row


class DefinitionCase(TestCase):
    """A platform administrator with a fresh passkey and one of bleqq's agents at v3."""

    def setUp(self) -> None:
        self.admin = factories.platform_user()
        self.agent = platform_agent(f"nordic-watch-{uuid.uuid4().hex[:6]}", versions=3)
        self.assertion = uuid.uuid4()

    def principal(self, *, step_up: bool = True) -> Principal:
        return user_principal(
            permissions={perms.AGENT_DEFINITIONS_MANAGE},
            subject_id=self.admin.id,
            step_up_at=timezone.now() if step_up else None,
            step_up_assertion_id=self.assertion if step_up else None,
        )

    def call(self, method: str, url: str, body: Any = None, principal: Principal | None = None) -> Any:
        with stub_session(principal or self.principal()):
            return getattr(self.client, method)(url, data=body, content_type=JSON, **AS_SESSION)

    def publish(self, version_no: int, principal: Principal | None = None) -> Any:
        body = {"versionNo": version_no, "changeNote": "Reads the new FFFS index page."}
        return self.call("post", f"{DEFINITIONS}/{self.agent.key}/versions", body, principal)

    def events(self, action: str) -> list[AuditEvent]:
        return list(AuditEvent.objects.filter(action=action, subject_title__startswith=self.agent.key))


class PublishingAVersion(DefinitionCase):
    def test_publishing_the_shipped_folder_creates_the_next_version_and_moves_the_agent(self) -> None:
        with definitions_root() as root:
            shipped_folder(root, self.agent.key, 4)
            response = self.publish(4)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["versionNo"], 4)
        self.assertEqual(body["changeNote"], "Reads the new FFFS index page.")
        self.assertEqual(body["publishedBy"], {"id": str(self.admin.id), "name": self.admin.name})
        self.assertIsNone(body["retiredAt"])
        version = AgentVersion.objects.get(agent=self.agent, version_number=4)
        definition = reader.read_definition(SHIPPED_FOLDER / "definition.yaml")
        self.assertEqual((version.model, version.prompt_path, tuple(version.tools)), (definition.model, definition.prompt, definition.tools))
        self.assertEqual(Agent.objects.get(pk=self.agent.pk).current_version, 4)

    def test_every_publish_leaves_one_audit_row_with_no_bank_the_note_and_the_assertion(self) -> None:
        with definitions_root() as root:
            shipped_folder(root, self.agent.key, 4)
            self.publish(4)
        [event] = self.events("agent_version.published")
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.actor_id, self.admin.id)
        self.assertEqual(event.step_up_assertion_id, self.assertion)
        self.assertEqual(event.before, {"currentVersion": 3})
        self.assertEqual(event.after["versionNo"], 4)
        self.assertEqual(event.after["changeNote"], "Reads the new FFFS index page.")

    def test_a_version_that_already_exists_is_409_and_changes_nothing(self) -> None:
        with definitions_root() as root:
            shipped_folder(root, self.agent.key, 3)
            response = self.publish(3)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "version_exists")
        self.assertEqual(self.events("agent_version.published"), [])

    def test_a_version_that_skips_one_is_refused(self) -> None:
        with definitions_root() as root:
            shipped_folder(root, self.agent.key, 5)
            response = self.publish(5)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "version_not_next")
        self.assertFalse(AgentVersion.objects.filter(agent=self.agent, version_number=5).exists())

    def test_a_folder_the_reader_cannot_read_is_422_naming_it_and_creates_nothing(self) -> None:
        with definitions_root() as root:
            folder = shipped_folder(root, self.agent.key, 4)
            definition = folder / "definition.yaml"
            definition.write_text(re.sub(r"(?m)^model: .*$", "model: 'quoted'", definition.read_text(encoding="utf-8")), encoding="utf-8")
            unreadable = self.publish(4)
            shutil.rmtree(folder)
            missing = self.publish(4)
        for response in (unreadable, missing):
            with self.subTest(detail=response.json().get("detail")):
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "definition_unreadable")
                self.assertIn(f"agents/{self.agent.key}/v4/definition.yaml", response.json()["detail"])
                self.assertNotIn(str(root), response.json()["detail"], "the server's own paths stay on the server")
        self.assertFalse(AgentVersion.objects.filter(agent=self.agent, version_number=4).exists())
        self.assertEqual(Agent.objects.get(pk=self.agent.pk).current_version, 3)

    def test_a_folder_of_another_agent_or_that_changes_the_agents_zone_is_refused(self) -> None:
        cases = (
            ("another id", r"(?m)^id: .*$", "id: another-agent"),
            ("another number", r"(?m)^version: .*$", "version: 7"),
            ("a bank's own", r"(?m)^scope: .*$", "scope: tenant"),
            ("writing a bank's zone", r"(?m)^writes_to: .*$", "writes_to: tenant"),
            ("another kind", r"(?m)^kind: .*$", "kind: research"),
        )
        for label, pattern, replacement in cases:
            with self.subTest(folder=label), definitions_root() as root:
                definition = shipped_folder(root, self.agent.key, 4) / "definition.yaml"
                definition.write_text(re.sub(pattern, replacement, definition.read_text(encoding="utf-8")), encoding="utf-8")
                response = self.publish(4)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "definition_unreadable")
        self.assertFalse(AgentVersion.objects.filter(agent=self.agent, version_number=4).exists())

    def test_a_folder_without_its_prompt_is_refused(self) -> None:
        with definitions_root() as root:
            (shipped_folder(root, self.agent.key, 4) / "prompt.md").unlink()
            response = self.publish(4)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "definition_unreadable")

    def test_without_a_fresh_assertion_it_is_403_and_creates_nothing(self) -> None:
        with definitions_root() as root:
            shipped_folder(root, self.agent.key, 4)
            response = self.publish(4, self.principal(step_up=False))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["code"], "step_up_required")
        self.assertFalse(AgentVersion.objects.filter(agent=self.agent, version_number=4).exists())

    def test_an_unknown_definition_is_404(self) -> None:
        body = {"versionNo": 1, "changeNote": "First."}
        response = self.call("post", f"{DEFINITIONS}/no-such-agent/versions", body)
        self.assertEqual(response.status_code, 404, response.content)


class APublishedVersionStaysPublished(TransactionTestCase):
    """A version the console published is append-only on `cw_app`, the role the app runs
    as: not even the door the console writes through changes it afterwards. Committed
    first, so the app's own connection sees the row."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def test_the_app_role_cannot_rewrite_it(self) -> None:
        admin = factories.platform_user()
        agent = platform_agent(f"committed-{uuid.uuid4().hex[:6]}", versions=1)
        principal = user_principal(permissions={perms.AGENT_DEFINITIONS_MANAGE}, subject_id=admin.id, step_up_at=timezone.now())
        body = {"versionNo": 2, "changeNote": "Reads the new FFFS index page."}
        with definitions_root() as root, stub_session(principal):
            shipped_folder(root, agent.key, 2)
            response = self.client.post(f"{DEFINITIONS}/{agent.key}/versions", data=body, content_type=JSON, **AS_SESSION)
        self.assertEqual(response.status_code, 201, response.content)
        version = AgentVersion.objects.get(agent=agent, version_number=2)
        with self.assertRaisesMessage(DatabaseError, "agent_version is append-only"):
            with transaction.atomic(using="app"), tenancy.library_door("seed", using="app"):
                with connections["app"].cursor() as cursor:
                    cursor.execute("UPDATE agent_version SET prompt_path = 'other.md' WHERE id = %s", [version.pk])
        self.assertEqual(AgentVersion.objects.get(pk=version.pk).prompt_path, "prompt.md")


class RetiringAVersion(DefinitionCase):
    def retire(self, version_no: int, principal: Principal | None = None) -> Any:
        return self.call("post", f"{DEFINITIONS}/{self.agent.key}/versions/{version_no}/retire", {}, principal)

    def test_retiring_sets_retired_at_and_nothing_else(self) -> None:
        before = AgentVersion.objects.get(agent=self.agent, version_number=2)
        response = self.retire(2)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.json()["retiredAt"])
        after = AgentVersion.objects.get(pk=before.pk)
        self.assertIsNotNone(after.retired_at)
        self.assertEqual((after.model, after.prompt_path, after.version_number), (before.model, before.prompt_path, 2))
        self.assertEqual(Agent.objects.get(pk=self.agent.pk).current_version, 3)
        [event] = self.events("agent_version.retired")
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.step_up_assertion_id, self.assertion)

    def test_retiring_a_retired_version_answers_it_as_it_is(self) -> None:
        first = self.retire(2).json()["retiredAt"]
        again = self.retire(2)
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["retiredAt"], first)
        self.assertEqual(len(self.events("agent_version.retired")), 1)

    def test_the_last_unretired_version_of_an_active_agent_is_409(self) -> None:
        self.assertEqual(self.retire(1).status_code, 200)
        self.assertEqual(self.retire(2).status_code, 200)
        response = self.retire(3)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "last_version")
        self.assertIsNone(AgentVersion.objects.get(agent=self.agent, version_number=3).retired_at)

    def test_without_a_fresh_assertion_it_is_403(self) -> None:
        response = self.retire(2, self.principal(step_up=False))
        self.assertEqual(response.json()["code"], "step_up_required")
        self.assertIsNone(AgentVersion.objects.get(agent=self.agent, version_number=2).retired_at)

    def test_a_version_that_does_not_exist_is_404(self) -> None:
        self.assertEqual(self.retire(9).status_code, 404)


class ReadingOneDefinition(DefinitionCase):
    def test_it_lists_every_version_newest_first_retired_ones_included(self) -> None:
        self.call("post", f"{DEFINITIONS}/{self.agent.key}/versions/1/retire", {})
        response = self.call("get", f"{DEFINITIONS}/{self.agent.key}")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["key"], body["scope"], body["currentVersion"]), (self.agent.key, "platform", 3))
        self.assertEqual([row["versionNo"] for row in body["versions"]], [3, 2, 1])
        self.assertIsNotNone(body["versions"][2]["retiredAt"])
        self.assertIsNotNone(body["publishedAt"])

    def test_an_unknown_key_is_404(self) -> None:
        self.assertEqual(self.call("get", f"{DEFINITIONS}/no-such-agent").status_code, 404)


class ARunPinsItsVersion(TestCase):
    """AGT-06: `agent_run.agent_version_id` is written once, when the run opens: the newest
    version still published, never one retired."""

    def setUp(self) -> None:
        self.agent = platform_agent(f"pinned-{uuid.uuid4().hex[:6]}", versions=2)
        self.key = agent_build.agent_key(agent_row=self.agent, scopes=(perms.SCOPE_AGENT_RUNS_WRITE,))
        self.who = Principal(
            kind=PrincipalKind.AGENT, subject_id=self.key.id, agent_id=self.agent.id, agent_label=self.agent.key
        )

    def open(self) -> AgentVersion:
        """The version the run it opens pins."""
        opened = runs.open_run(
            who=self.who, body=AgentRunInput(agent=self.agent.key, model="m", pipeline_version="1"), idempotency_key=None
        )
        version = AgentRun.objects.select_related("agent_version").get(pk=opened.id).agent_version
        assert version is not None
        return version

    def test_a_run_names_the_newest_published_version(self) -> None:
        self.assertEqual(self.open().version_number, 2)

    def test_a_retired_version_starts_no_run(self) -> None:
        with library_write("test"):
            AgentVersion.objects.filter(agent=self.agent, version_number=2).update(retired_at=timezone.now())
        self.assertEqual(self.open().version_number, 1)

    def test_an_agent_whose_every_version_is_retired_opens_no_run(self) -> None:
        with library_write("test"):
            AgentVersion.objects.filter(agent=self.agent).update(retired_at=timezone.now())
        with self.assertRaises(ProblemError) as caught:
            self.open()
        self.assertEqual((caught.exception.status, caught.exception.code), (409, "no_published_version"))
        self.assertFalse(AgentRun.objects.filter(agent=self.agent).exists())

    def test_the_version_is_written_once(self) -> None:
        run = AgentRun.objects.get(agent_version=self.open())
        first = AgentVersion.objects.get(agent=self.agent, version_number=1)
        with self.assertRaisesMessage(DatabaseError, "agent_version_id is written when the run opens"), transaction.atomic():
            AgentRun.objects.filter(pk=run.pk).update(agent_version=first)
