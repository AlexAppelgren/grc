"""Reading one of the platform's agent definitions, and the version a run pins (AGT-03,
AGT-06).

A published version is append-only: a run points at the version it opened with, the
newest one still published, and retiring one only stops new runs. Publishing and retiring
a version answer 501 until the fence decision in docs/TODO_FOR_alex.md
(c11-definitions-platform); their implementation and tests wait on
`claude/r2w3-c11-definitions-platform-writes`.

Proven to fail 2026-09-25: the read answered 501 `not_built` before `definitions.py` was
written, and the pinning tests found runs with no version.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import DatabaseError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.agents import runs, testing as agent_build
from apps.agents.models import Agent, AgentRun, AgentVersion
from apps.agents.schemas import AgentRunInput
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError
from apps.shared.tenancy import library_write
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, stub_session, user_principal

DEFINITIONS = "/api/v1/agent-definitions"
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}


def platform_agent(key: str, *, versions: int) -> Agent:
    """One of bleqq's agents at version `versions`, with every earlier version published."""
    row = agent_build.agent(key=key, version=versions)
    with library_write("test"):
        for number in range(1, versions + 1):
            AgentVersion.objects.create(agent=row, version_no=number, model="claude-opus-5", prompt_path="prompt.md")
    return row


class ReadingOneDefinition(TestCase):
    """A platform administrator and one of bleqq's agents at v3."""

    def setUp(self) -> None:
        self.agent = platform_agent(f"nordic-watch-{uuid.uuid4().hex[:6]}", versions=3)

    def call(self, method: str, url: str) -> Any:
        with stub_session(user_principal(permissions={perms.AGENT_DEFINITIONS_MANAGE})):
            return getattr(self.client, method)(url, **AS_SESSION)

    def test_it_lists_every_version_newest_first_retired_ones_included(self) -> None:
        with library_write("test"):
            AgentVersion.objects.filter(agent=self.agent, version_no=1).update(retired_at=timezone.now())
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
        self.assertEqual(self.open().version_no, 2)

    def test_a_retired_version_starts_no_run(self) -> None:
        with library_write("test"):
            AgentVersion.objects.filter(agent=self.agent, version_no=2).update(retired_at=timezone.now())
        self.assertEqual(self.open().version_no, 1)

    def test_an_agent_whose_every_version_is_retired_opens_no_run(self) -> None:
        with library_write("test"):
            AgentVersion.objects.filter(agent=self.agent).update(retired_at=timezone.now())
        with self.assertRaises(ProblemError) as caught:
            self.open()
        self.assertEqual((caught.exception.status, caught.exception.code), (409, "no_published_version"))
        self.assertFalse(AgentRun.objects.filter(agent=self.agent).exists())

    def test_the_version_is_written_once(self) -> None:
        run = AgentRun.objects.get(agent_version=self.open())
        first = AgentVersion.objects.get(agent=self.agent, version_no=1)
        with self.assertRaisesMessage(DatabaseError, "agent_version_id is written when the run opens"), transaction.atomic():
            AgentRun.objects.filter(pk=run.pk).update(agent_version=first)
