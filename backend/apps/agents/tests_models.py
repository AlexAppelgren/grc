"""Models, seed and isolation of the agents app (AGT-01, AGT-02, AGT-03, ID-10, D-80).

Proven here: the definition reader reads every shipped definition exactly as PyYAML does,
so the seed's stripped-down reader can never drift from real YAML; the definitions are in
the API image, where the seed reads them on every deploy; the seed creates one agent row
per definition once and leaves it alone on the next deploy, and an agent's key never
changes; the confirming definition is independent of the proposing one by what it may
call, and every vocabulary a definition reads at run start is one the API serves through
a tool the definition declares with `library:read`;
`agent_run` is a mixed table whose policies bite for `cw_app`: a tenant reads the
library's runs but never writes them, and a run lives in its key's zone; a key bound to
an agent writes its audit rows as that agent, not as a bare key id; and the decision an
agent reports with its model call is refused without a model, a version or a citation.

Chunk 11's tables (AGT-03 to AGT-06, agents 0004 and 0005), in the database and on the
`app` alias where a policy or a trigger is what decides: a platform definition is never
tenant-configurable and a tenant one borrows no platform setting; a definition's scope never
changes; a published version changes only by being retired, once; a run's version is
written once; a run without a key is the worker's and lives in its tenant agent's zone; a
bank's agent is refused on any definition but a configurable tenant one and is paused,
never deleted; a research request without a tenant is the console's retag and nothing else;
and a bank's agents, requests and cap are invisible to another bank.
"""

from __future__ import annotations

import posixpath
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from decimal import Decimal
from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, ProgrammingError, connections, transaction
from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from pydantic import ValidationError as SchemaError

from apps.agents.models import (
    Agent,
    AgentKind,
    AgentRun,
    AgentScopeKind,
    AgentVersion,
    AgentWritesTo,
    ResearchRequest,
    ResearchRequestKind,
    RunStatus,
    RunTrigger,
    TenantAgent,
    TenantAgentBudget,
)
from apps.agents.seeds import SHIPPED, definitions, seed_agent_definitions
from apps.agents.seeds.definition import DEFINITIONS, DefinitionError, read_definition
from apps.identity import tokens
from apps.identity.api_keys_logic import resolve_api_key
from apps.identity.models import ApiKey
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import Actor
from apps.shared.authentication import PrincipalKind
from apps.shared.models import AuditEvent
from apps.shared.schemas import AgentDecision
from apps.shared.tenancy import LibraryWriteRefused, library_write
from apps.shared.testing import ScenarioTestCase
from apps.shared.vocabulary import KeyIsImmutable
from apps.taxonomy.registry import LIBRARY_LISTS
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

V1 = "/api/v1"
WATCH_SWEEPER = DEFINITIONS / "watch-sweeper" / "v1" / "definition.yaml"
CONFIRMER_VERSION = dict(SHIPPED)["library-confirmer"]
LIBRARY_CONFIRMER = DEFINITIONS / "library-confirmer" / f"v{CONFIRMER_VERSION}" / "definition.yaml"
# Where a run reads each list it names at run start, every route taking `library:read`: the
# registry's library lists through one route, the three that are not registry rows through
# routes of their own.
READ_FROM_THE_REGISTRY = "GET /vocab/{list}"
READ_OUTSIDE_THE_REGISTRY = {
    "taxonomy_term": "GET /taxonomy/terms",
    "authority": "GET /authorities",
    "source": "GET /sources",
}
# A .dockerignore wildcard as Docker compiles it (moby/patternmatcher), keyed by its
# re.escape spelling: `**` spans directories, `*` and `?` stay inside one.
DOCKER_WILDCARDS = {r"\*\*/": "(.*/)?", r"\*\*": ".*", r"\*": "[^/]*", r"\?": "[^/]"}
DOCKER_WILDCARD = re.compile("|".join(re.escape(escaped) for escaped in DOCKER_WILDCARDS))


def dockerignore_rules(text: str) -> list[tuple[re.Pattern[str], bool]]:
    """Each rule of a .dockerignore as (pattern, re-includes), relative to the build context."""
    rules = []
    for line in (raw.strip() for raw in text.splitlines()):
        if line and not line.startswith("#"):
            pattern = posixpath.normpath(line.removeprefix("!").strip().lstrip("/"))
            regex = DOCKER_WILDCARD.sub(lambda wildcard: DOCKER_WILDCARDS[wildcard.group()], re.escape(pattern))
            rules.append((re.compile(regex), line.startswith("!")))
    return rules


def ignored(relative: str, rules: list[tuple[re.Pattern[str], bool]]) -> bool:
    """Docker's verdict on one path: the last rule that matches it or a directory above it."""
    parts = relative.split("/")
    candidates = ["/".join(parts[: depth + 1]) for depth in range(len(parts))]
    verdict = False
    for pattern, reincludes in rules:
        if any(pattern.fullmatch(candidate) for candidate in candidates):
            verdict = not reincludes
    return verdict


def platform_key(agent: Agent | None = None) -> tuple[str, ApiKey]:
    """A platform key (no tenant), as the watch agent's key is: the plain key and the row.
    Called with no tenant activated, as the console has it: api_key accepts a row of the
    session's own zone only (H15)."""
    plain, prefix, key_hash = tokens.new_api_key()
    row = ApiKey.objects.create(
        tenant=None, agent=agent, name="Watch sweeper", key_prefix=prefix, key_hash=key_hash, scopes=["proposals:write"]
    )
    return plain, row


class DefinitionReaderTests(TestCase):
    """The reader exists because PyYAML is a dev dependency and `seed_reference` runs on
    every deploy (apps/agents/seeds/definition.py). These tests are the proof it agrees
    with the real thing."""

    def test_the_reader_reads_the_shipped_definition_as_pyyaml_does(self) -> None:
        for name, version in SHIPPED:
            path = DEFINITIONS / name / f"v{version}" / "definition.yaml"
            parsed: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
            read = read_definition(path)
            self.assertEqual(read.key, parsed["id"], path)
            self.assertEqual(read.version, parsed["version"], path)
            self.assertEqual(read.kind, parsed["kind"], path)
            self.assertEqual(read.status, parsed["status"], path)
            # A folded block keeps a trailing newline in YAML; the column does not.
            self.assertEqual(read.description, parsed["description"].strip(), path)

    def test_the_version_folder_matches_the_version_in_the_definition(self) -> None:
        for name, version in SHIPPED:
            self.assertEqual(read_definition(DEFINITIONS / name / f"v{version}" / "definition.yaml").version, version)

    def test_only_a_published_definition_is_active(self) -> None:
        self.assertFalse(read_definition(WATCH_SWEEPER).active, "watch-sweeper v1 is still a draft")
        self.assertFalse(read_definition(LIBRARY_CONFIRMER).active, f"library-confirmer v{CONFIRMER_VERSION} waits for its evals")

    def test_a_definition_it_cannot_read_raises_instead_of_guessing(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        for body, why in (
            ('id: a\nversion: 1\nkind: watch\nstatus: draft\ndescription: "quoted"\n', "a quoted scalar"),
            ('id: a\nversion: one\nkind: watch\nstatus: draft\ndescription: x\n', "a version that is not a number"),
            ('id: a\nkind: watch\nstatus: draft\ndescription: x\n', "a missing field"),
            ('id a\n', "a line that is not `name: value`"),
        ):
            path = directory / "definition.yaml"
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(DefinitionError, msg=why):
                read_definition(path)


def _parsed(name: str, version: int) -> dict[str, Any]:
    """The whole definition as PyYAML reads it: the runner's contract, beyond the five
    scalars the seed stores."""
    path = DEFINITIONS / name / f"v{version}" / "definition.yaml"
    parsed: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parsed


def _scopes(definition: dict[str, Any]) -> set[str]:
    return {scope for tool in definition["tools"] for scope in tool.get("scopes", ())}


class DefinitionContractTests(SimpleTestCase):
    """What a definition may call and read, from its own file (AGT-02, D-62, D-80)."""

    def test_every_kind_is_an_agent_kind(self) -> None:
        kinds = {kind.value for kind in AgentKind}
        for name, version in SHIPPED:
            self.assertIn(_parsed(name, version)["kind"], kinds, name)

    def test_every_scope_a_tool_names_is_one_a_key_can_hold(self) -> None:
        for name, version in SHIPPED:
            self.assertLessEqual(_scopes(_parsed(name, version)), perms.ALL_SCOPES, name)

    def test_the_confirming_definition_cannot_file_what_it_decides(self) -> None:
        """Independence by construction: a `review` definition decides and never proposes,
        and a definition that proposes never decides, so no one definition's key needs
        both scopes. The four-eyes constraint refuses the pair anyway (D-62)."""
        for name, version in SHIPPED:
            definition = _parsed(name, version)
            scopes = _scopes(definition)
            if definition["kind"] == AgentKind.REVIEW.value:
                self.assertIn(perms.SCOPE_PROPOSALS_REVIEW, scopes, name)
                self.assertNotIn(perms.SCOPE_PROPOSALS_WRITE, scopes, name)
            else:
                self.assertNotIn(perms.SCOPE_PROPOSALS_REVIEW, scopes, name)
        confirmer, sweeper = _parsed("library-confirmer", CONFIRMER_VERSION), _parsed("watch-sweeper", 1)
        self.assertNotEqual(confirmer["id"], sweeper["id"])
        prompts = {
            (DEFINITIONS / definition["id"] / f"v{definition['version']}" / definition["prompt"]).read_text(encoding="utf-8")
            for definition in (confirmer, sweeper)
        }
        self.assertEqual(len(prompts), 2, "the confirmer has a prompt of its own")

    def test_every_vocabulary_read_at_run_start_is_one_the_definition_may_read(self) -> None:
        """A list named here that no route serves, or whose route the definition declares
        no tool for with `library:read`, would fail the run at its first read: the key the
        platform issues carries the scopes of the definition's tools and no others. A tenant
        list is never one: a platform run reads no bank's rows."""
        for name, version in SHIPPED:
            definition = _parsed(name, version)
            lists = definition["vocabularies_read_at_run_start"]
            self.assertEqual(len(lists), len(set(lists)), f"{name} names a list twice")
            tools = {tool["operation"]: tool for tool in definition["tools"] if "operation" in tool}
            for listed in lists:
                route = READ_FROM_THE_REGISTRY if listed in LIBRARY_LISTS else READ_OUTSIDE_THE_REGISTRY.get(listed)
                self.assertIsNotNone(route, f"{name}: no route serves {listed}")
                self.assertIn(route, sorted(tools), f"{name} reads {listed} at run start and declares no tool for {route}")
                self.assertIn(perms.SCOPE_LIBRARY_READ, tools[route]["scopes"], f"{name}: {route} needs library:read")
        self.assertIn("rejection_reason", _parsed("library-confirmer", CONFIRMER_VERSION)["vocabularies_read_at_run_start"])


class DefinitionsShipInTheImageTests(SimpleTestCase):
    """`seed_reference` reads the definitions on every deploy, inside the API image. The
    image builds from `backend/` alone (`COPY . .` into /app, `backend/.dockerignore`
    applied), so a definition outside that directory or caught by an ignore rule stops
    every deploy at the seed. The first version read them from the repository root."""

    def test_every_file_of_a_shipped_definition_is_in_the_api_image(self) -> None:
        backend = Path(settings.BASE_DIR)
        self.assertIn("COPY . .", (backend / "Dockerfile").read_text(encoding="utf-8"), "the image copies its context")
        ignore = (backend / ".dockerignore").read_text(encoding="utf-8")
        self.assertNotRegex(ignore, r"[\[\\]", "a character class or an escape: teach dockerignore_rules() it first")
        rules = dockerignore_rules(ignore)
        self.assertTrue(ignored("var/media/a.pdf", rules) and ignored("apps/agents/__pycache__/m.pyc", rules), "rules read")
        for name, version in SHIPPED:
            folder = DEFINITIONS / name / f"v{version}"
            self.assertTrue(folder.is_relative_to(backend), f"{folder} is outside backend/, the API image's build context")
            self.assertTrue((folder / "definition.yaml").is_file(), folder)
            for path in sorted(item for item in folder.rglob("*") if item.is_file()):
                relative = path.relative_to(backend).as_posix()
                self.assertFalse(ignored(relative, rules), f"backend/.dockerignore keeps {relative} out of the image")


class AgentSeedTests(TestCase):
    def test_the_seed_creates_every_shipped_agent_from_its_definition(self) -> None:
        created = seed_agent_definitions()
        self.assertEqual(created, len(SHIPPED))
        for definition in definitions():
            agent = Agent.objects.get(key=definition.key)
            self.assertEqual(agent.kind, definition.kind)
            self.assertEqual(agent.current_version, definition.version)
            self.assertEqual(agent.description, definition.description)
            self.assertFalse(agent.active)
            event = AuditEvent.objects.get(action="agent.seeded", subject_id=agent.id)
            self.assertIsNone(event.tenant_id, "an agent is a library row, so its audit row is a library row")
        kinds = dict(Agent.objects.values_list("key", "kind"))
        self.assertEqual(kinds["watch-sweeper"], AgentKind.WATCH.value)
        self.assertEqual(kinds["library-confirmer"], AgentKind.REVIEW.value, "the second pair of eyes (D-62, D-80)")

    def test_a_second_deploy_changes_nothing(self) -> None:
        seed_agent_definitions()
        before = AuditEvent.objects.count()
        self.assertEqual(seed_agent_definitions(), 0)
        self.assertEqual(Agent.objects.count(), len(SHIPPED))
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_the_seed_is_the_only_door_into_the_agent_table(self) -> None:
        with self.assertRaises(LibraryWriteRefused):
            Agent.objects.create(key="rogue", kind=AgentKind.WATCH.value, current_version=1)


class AgentKeyTests(TestCase):
    """`key` is the definition's id, and keys, runs and audit rows name the agent by it."""

    def setUp(self) -> None:
        with library_write("test"):
            self.agent = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)

    def test_saving_a_changed_key_is_refused(self) -> None:
        self.agent.key = "renamed"
        with library_write("test"), self.assertRaises(KeyIsImmutable) as caught:
            self.agent.save()
        self.assertEqual(caught.exception.code, "key_immutable")

    def test_the_database_refuses_a_key_change_that_skips_the_model(self) -> None:
        with library_write("test"), self.assertRaises(DatabaseError) as caught, transaction.atomic():
            Agent.objects.filter(pk=self.agent.pk).update(key="renamed")
        self.assertIn("never changes", str(caught.exception))

    def test_everything_but_the_key_still_changes(self) -> None:
        with library_write("test"):
            Agent.objects.filter(pk=self.agent.pk).update(active=True)
            self.agent.refresh_from_db()
            self.agent.current_version = 2
            self.agent.save()
        self.agent.refresh_from_db()
        self.assertEqual((self.agent.key, self.agent.active, self.agent.current_version), ("watch-sweeper", True, 2))


class AgentRunModelTests(TestCase):
    def setUp(self) -> None:
        seed_languages()
        with library_write("test"):
            self.agent = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)
        self.tenant = factories.tenant(slug="run-tenant")
        self.key = factories.api_key(self.tenant, scopes=("agent-runs:write",)).row

    def _run(self, **fields: Any) -> AgentRun:  # compliance: allow-kwargs test helper forwarding model fields
        defaults = {"agent": self.agent, "api_key": self.key, "model": "test-model", "pipeline_version": "0.4"}
        return AgentRun.objects.create(**{**defaults, **fields})

    def test_a_run_starts_running_in_its_keys_tenant(self) -> None:
        run = self._run()
        self.assertEqual(run.status, RunStatus.RUNNING.value)
        self.assertEqual(run.tenant_id, self.tenant.id)
        self.assertIsNotNone(run.started_at)
        self.assertIsNone(run.finished_at)
        self.assertEqual(run.stats, {})

    def test_the_tenant_comes_from_the_key_never_from_the_caller(self) -> None:
        other = factories.tenant(slug="run-other")
        tenancy.activate(self.tenant.id)
        self.assertEqual(self._run(tenant=None).tenant_id, self.tenant.id, "a tenant's key never opens a library run")
        self.assertEqual(self._run(tenant=other).tenant_id, self.tenant.id)

    def test_one_run_per_idempotency_key_and_api_key(self) -> None:
        self._run(idempotency_key="run-42")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._run(idempotency_key="run-42")

    def test_the_same_idempotency_key_on_another_key_is_another_run(self) -> None:
        self._run(idempotency_key="run-42")
        other = factories.api_key(self.tenant, name="Second key", scopes=("agent-runs:write",)).row
        self._run(api_key=other, idempotency_key="run-42")
        self.assertEqual(AgentRun.objects.filter(idempotency_key="run-42").count(), 2)

    def test_runs_without_an_idempotency_key_do_not_collide(self) -> None:
        self._run()
        self._run()
        self.assertEqual(AgentRun.objects.filter(idempotency_key="").count(), 2)


class AgentRunIsolationTests(TransactionTestCase):
    """agent_run on the `app` alias (cw_app, no ownership). A tenant reads its own runs and
    the library's and writes only its own; a session with no tenant writes only library
    runs; every run names a key of its own zone. Bulk inserts and queryset updates skip
    AgentRun.save, so there the policies alone decide."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        seed_languages()
        with library_write("test"):
            self.agent = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)
        self.tenant_a = factories.tenant(slug="agent-rls-a")
        self.tenant_b = factories.tenant(slug="agent-rls-b")
        self.key_a = factories.api_key(self.tenant_a, scopes=("agent-runs:write",)).row
        self.key_b = factories.api_key(self.tenant_b, scopes=("agent-runs:write",)).row
        self.platform_key = platform_key(self.agent)[1]

    def _run(self, key: ApiKey) -> AgentRun:
        return AgentRun.objects.using("app").create(agent=self.agent, api_key=key, model="test-model", pipeline_version="0.4")

    def _bulk_insert(self, key: ApiKey, tenant_id: uuid.UUID | None) -> None:
        run = AgentRun(agent=self.agent, api_key=key, tenant_id=tenant_id, model="test-model", pipeline_version="0.4")
        AgentRun.objects.using("app").bulk_create([run])

    def _runs(self, run: AgentRun) -> QuerySet[AgentRun]:
        return AgentRun.objects.using("app").filter(pk=run.pk)

    def _tenant_a(self) -> None:
        tenancy.activate(self.tenant_a.id, using="app")

    def test_a_tenant_sees_its_own_runs_and_the_library_runs(self) -> None:
        with transaction.atomic(using="app"):
            self._run(self.platform_key)
        with transaction.atomic(using="app"):
            self._tenant_a()
            self._run(self.key_a)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            self._run(self.key_b)

        with transaction.atomic(using="app"):
            self._tenant_a()
            visible = set(AgentRun.objects.using("app").values_list("tenant_id", flat=True))
        self.assertEqual(visible, {self.tenant_a.id, None})

    def test_a_tenant_writes_only_its_own_runs(self) -> None:
        with transaction.atomic(using="app"):
            library_run = self._run(self.platform_key)
        with transaction.atomic(using="app"):
            self._tenant_a()
            run = self._run(self.key_a)
            self.assertTrue(self._runs(library_run).exists(), "a library run is visible to every tenant")
            self.assertEqual(self._runs(library_run).update(error="overwritten"), 0)
            self.assertEqual(self._runs(library_run).update(tenant_id=self.tenant_a.id), 0, "pulled into a tenant")
            self.assertEqual(self._runs(library_run).delete()[0], 0)
        self.assertEqual(AgentRun.objects.get(pk=library_run.pk).error, "")
        for write, why in (
            (lambda: self._run(self.key_b), "opened in another tenant"),
            (lambda: self._bulk_insert(self.platform_key, None), "opened in the library"),
            (lambda: self._runs(run).update(tenant_id=None), "moved into the library"),
        ):
            with self.assertRaises(ProgrammingError, msg=why):
                with transaction.atomic(using="app"):
                    self._tenant_a()
                    write()

    def test_a_session_with_no_tenant_writes_only_library_runs(self) -> None:
        with transaction.atomic(using="app"):
            self._tenant_a()
            tenant_run = self._run(self.key_a)
        with transaction.atomic(using="app"):
            library_run = self._run(self.platform_key)
            self.assertEqual(self._runs(library_run).update(status=RunStatus.SUCCEEDED.value), 1)
            self.assertEqual(self._runs(tenant_run).update(error="overwritten"), 0)
            self.assertEqual(self._runs(tenant_run).delete()[0], 0)
            self.assertEqual(self._runs(library_run).delete()[0], 1)
        with self.assertRaises(ProgrammingError):
            with transaction.atomic(using="app"):
                self._bulk_insert(self.key_a, self.tenant_a.id)

    def test_a_run_names_a_key_of_its_own_zone(self) -> None:
        with transaction.atomic(using="app"):
            self._tenant_a()
            run = self._run(self.key_a)
        tenant_a = self.tenant_a.id
        for tenant_id, write, why in (
            (tenant_a, lambda: self._bulk_insert(self.key_b, tenant_a), "a tenant's run on another tenant's key"),
            (tenant_a, lambda: self._bulk_insert(self.platform_key, tenant_a), "a tenant's run on a platform key"),
            (None, lambda: self._bulk_insert(self.key_a, None), "a library run on a tenant's key"),
            (tenant_a, lambda: self._runs(run).update(api_key=self.key_b), "a run moved onto another tenant's key"),
        ):
            with self.assertRaises(ProgrammingError, msg=why):
                with transaction.atomic(using="app"):
                    if tenant_id is not None:
                        tenancy.activate(tenant_id, using="app")
                    write()


class AgentKeyActorTests(ScenarioTestCase):
    """ID-10, the chunk 5 half: the agent behind the key is who the audit log names."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        seed_agent_definitions()
        self.agent = Agent.objects.get(key="watch-sweeper")
        self.tenant = factories.tenant(slug="agent-actor")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        # The key and everything the agent does with it belong to the platform's zone, and a
        # request of its own would carry no tenant: what the factory activated goes off again,
        # or the platform rows below are outside this session's zone (H15).
        tenancy.clear_tenant()
        self.plain_key, key = platform_key(self.agent)
        # What an agent files names an open run of its own key (AGT-01).
        self.open_run = AgentRun.objects.create(agent=self.agent, api_key=key, model="agent pipeline 0.4", pipeline_version="0.4")

    def test_the_principal_carries_the_agent_the_key_is_bound_to(self) -> None:
        with transaction.atomic():
            principal = resolve_api_key(self.plain_key)
        assert principal is not None
        self.assertEqual(principal.kind, PrincipalKind.AGENT)
        self.assertEqual(principal.agent_id, self.agent.id)
        self.assertEqual(principal.agent_label, "watch-sweeper")

    def test_a_key_bound_to_no_agent_carries_none(self) -> None:
        plain = platform_key()[0]
        with transaction.atomic():
            principal = resolve_api_key(plain)
        assert principal is not None
        self.assertIsNone(principal.agent_id)
        self.assertEqual(principal.agent_label, "")

    def test_what_an_agent_key_writes_is_audited_as_its_agent(self) -> None:
        body = {
            "kind": "vocabulary_create",
            "title": "Add the flag Client money",
            "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            "sourceLabel": "FFFS 2017:2",
            "sourceUrl": "https://www.fi.se/",
            "agentRunId": str(self.open_run.id),
        }
        response = self.client.post(
            f"{V1}/proposals", data=body, content_type="application/json", HTTP_X_API_KEY=self.plain_key
        )
        self.assertEqual(response.status_code, 201, response.content)
        event = AuditEvent.objects.filter(action__startswith="proposal.").order_by("-created").first()
        assert event is not None
        self.assertEqual(event.actor_type, "agent")
        self.assertEqual(event.actor_id, self.agent.id, "the agent, not the key")
        self.assertEqual(event.actor_label, "watch-sweeper")


class AgentDecisionTests(SimpleTestCase):
    """The model call a confirming agent reports with its decision (AUD-02, D-80). A body
    from an agent is a trust boundary: what the log cannot attribute or check is refused
    at the shape, before any route reads it."""

    DECISION: dict[str, Any] = {
        "model": "claude-opus-5",
        "modelVersion": "2026-05-01",
        "promptTemplate": "library-confirmer/decide/v2",
        "output": "Approve. The proposed wording matches the amended regulation as published.",
        "citations": [{"label": "Finansinspektionen", "url": "https://www.fi.se/"}],
    }

    def test_a_decision_with_its_model_and_a_citation_is_accepted(self) -> None:
        decision = AgentDecision.model_validate(self.DECISION)
        self.assertEqual((decision.model, decision.model_version), ("claude-opus-5", "2026-05-01"))
        self.assertIsNone(decision.prompt_hash, "the prompt's hash is optional, as D-66's is")
        self.assertEqual(decision.citations[0].url, "https://www.fi.se/")

    def test_what_the_log_could_not_attribute_or_check_is_refused(self) -> None:
        over = settings.AI_GENERATION_OUTPUT_MAX_CHARS + 1
        for change, why in (
            ({"citations": []}, "no citation"),
            ({"model": ""}, "no model"),
            ({"modelVersion": ""}, "no model version"),
            ({"output": ""}, "no conclusion"),
            ({"output": "x" * over}, "an output over the cap, refused rather than cut short"),
            ({"citations": [{"label": "x", "url": "https://www.fi.se/"}] * (settings.AI_GENERATION_CITATIONS_MAX + 1)}, "too many citations"),
            ({"prompt": "the whole prompt"}, "a field the shape does not name, such as the prompt itself"),
            ({"citations": [{"label": "x", "url": "javascript:alert(1)"}]}, "a citation that is not a web page"),
            ({"citations": [{"label": "x", "url": "file:///etc/passwd"}]}, "a citation that is not a web page"),
        ):
            with self.assertRaises(SchemaError, msg=why):
                AgentDecision.model_validate({**self.DECISION, **change})
        body = {name: value for name, value in self.DECISION.items() if name != "model"}
        with self.assertRaises(SchemaError, msg="a missing model"):
            AgentDecision.model_validate(body)


def tenant_definition(key: str = "bank-watch", *, configurable: bool = True) -> Agent:
    """A definition a bank may add for itself (ruling 1): bleqq's, tenant-scoped."""
    with library_write("test"):
        return Agent.objects.create(
            key=key,
            kind=AgentKind.RESEARCH.value,
            current_version=1,
            scope=AgentScopeKind.TENANT.value,
            tenant_configurable=configurable,
            writes_to=AgentWritesTo.TENANT.value,
        )


class AgentDefinitionColumnTests(TestCase):
    """The platform fence's first columns (AGT-03, ruling 1): refused by the database, so
    a queryset update or a seed that skips every form is refused too."""

    def setUp(self) -> None:
        with library_write("test"):
            self.platform = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)

    def _refused(self, **fields: Any) -> None:  # compliance: allow-kwargs test helper forwarding model fields
        with library_write("test"), self.assertRaises(IntegrityError), transaction.atomic():
            Agent.objects.filter(pk=self.platform.pk).update(**fields)

    def test_a_definition_is_one_of_bleqqs_agents_unless_it_says_otherwise(self) -> None:
        self.assertEqual(
            (self.platform.scope, self.platform.tenant_configurable, self.platform.writes_to),
            (AgentScopeKind.PLATFORM.value, False, AgentWritesTo.LIBRARY.value),
        )
        self.assertEqual((self.platform.runtime, self.platform.default_cadence), ("agent_sdk", "weekly"))

    def test_a_platform_definition_is_never_tenant_configurable(self) -> None:
        self._refused(tenant_configurable=True)

    def test_a_platform_definition_carries_its_platform_settings(self) -> None:
        with library_write("test"):
            Agent.objects.filter(pk=self.platform.pk).update(
                platform_scope={"jurisdictions": ["se", "fi"]}, platform_monthly_budget=Decimal("250.00")
            )
        self.platform.refresh_from_db()
        self.assertEqual(self.platform.platform_monthly_budget, Decimal("250.00"))

    def test_a_tenant_definition_borrows_no_platform_setting_and_never_writes_the_library(self) -> None:
        definition = tenant_definition()
        for fields, why in (
            ({"platform_scope": {"jurisdictions": ["se"]}}, "a platform scope"),
            ({"platform_monthly_budget": Decimal("10.00")}, "a platform budget"),
            ({"writes_to": AgentWritesTo.LIBRARY.value}, "writes to the library"),
        ):
            with self.subTest(why), library_write("test"), self.assertRaises(IntegrityError), transaction.atomic():
                Agent.objects.filter(pk=definition.pk).update(**fields)

    def test_a_definitions_scope_never_changes(self) -> None:
        definition = tenant_definition()
        for agent, scope in ((self.platform, AgentScopeKind.TENANT), (definition, AgentScopeKind.PLATFORM)):
            with self.subTest(agent.key), library_write("test"), self.assertRaises(DatabaseError) as caught:
                with transaction.atomic():
                    Agent.objects.filter(pk=agent.pk).update(
                        scope=scope.value, tenant_configurable=False, writes_to=AgentWritesTo.TENANT.value
                    )
            self.assertIn("scope never changes", str(caught.exception))


class AgentVersionTests(TransactionTestCase):
    """A published version as cw_app (AGT-03): inserted inside a door, then only retired,
    once. The door itself is proven for every library table in
    apps/shared/tests_library_db_guard.py."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with library_write("test"):
            self.agent = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)
        with library_write("test"), tenancy.library_door("seed", using="app"):
            self.version = AgentVersion.objects.using("app").create(
                agent=self.agent, version_number=1, model="test-model", prompt_path="prompt.md", tools=[{"operation": "GET /sources"}]
            )

    def _sql(self, statement: str) -> None:
        with transaction.atomic(using="app"), tenancy.library_door("seed", using="app"):
            with connections["app"].cursor() as cursor:
                cursor.execute(statement, [self.version.pk])

    def test_a_published_version_is_never_rewritten_or_deleted(self) -> None:
        for statement in (
            "UPDATE agent_version SET prompt_path = 'other.md' WHERE id = %s",
            "UPDATE agent_version SET model = 'other', retired_at = now() WHERE id = %s",
            "DELETE FROM agent_version WHERE id = %s",
        ):
            with self.subTest(statement), self.assertRaisesMessage(DatabaseError, "agent_version is append-only"):
                self._sql(statement)
        self.assertEqual(AgentVersion.objects.get(pk=self.version.pk).prompt_path, "prompt.md")

    def test_retiring_is_the_one_change_and_happens_once(self) -> None:
        self._sql("UPDATE agent_version SET retired_at = now() WHERE id = %s")
        self.assertIsNotNone(AgentVersion.objects.get(pk=self.version.pk).retired_at)
        with self.assertRaisesMessage(DatabaseError, "only retiring a version, once"):
            self._sql("UPDATE agent_version SET retired_at = now() + interval '1 day' WHERE id = %s")

    def test_the_app_role_cannot_open_the_maintenance_hatch(self) -> None:
        for hatch in ("SET LOCAL cw.maintenance = 'on'", "SET LOCAL CW.MAINTENANCE = 'on'"):
            with self.subTest(hatch), self.assertRaisesMessage(DatabaseError, "agent_version is append-only"):
                with transaction.atomic(using="app"), tenancy.library_door("seed", using="app"):
                    with connections["app"].cursor() as cursor:
                        cursor.execute(hatch)
                        cursor.execute("DELETE FROM agent_version WHERE id = %s", [self.version.pk])

    def test_one_row_per_version_number(self) -> None:
        with self.assertRaises(IntegrityError):
            with library_write("test"), tenancy.library_door("seed", using="app"):
                AgentVersion.objects.using("app").create(agent=self.agent, version_number=1, model="m", prompt_path="p.md")


class WorkerRunTests(TestCase):
    """A run the worker opens has no key (AGT-06): it is refused as an API run, lands in its
    tenant agent's zone or the library's, and keeps the version it opened with."""

    def setUp(self) -> None:
        with library_write("test"):
            self.agent = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)
            self.v1 = AgentVersion.objects.create(agent=self.agent, version_number=1, model="m", prompt_path="prompt.md")
            self.v2 = AgentVersion.objects.create(agent=self.agent, version_number=2, model="m", prompt_path="prompt.md")
        self.definition = tenant_definition()
        self.tenant = factories.tenant(slug="worker-run")
        tenancy.activate(self.tenant.id)
        self.tenant_agent = TenantAgent.objects.create(tenant=self.tenant, agent=self.definition)
        tenancy.clear_tenant()

    def _run(self, **fields: Any) -> AgentRun:  # compliance: allow-kwargs test helper forwarding model fields
        defaults = {"agent": self.agent, "model": "m", "pipeline_version": "0.4", "trigger": RunTrigger.SCHEDULE.value}
        return AgentRun.objects.create(**{**defaults, **fields})

    def test_an_api_run_without_a_key_is_refused(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._run(trigger=RunTrigger.API.value)

    def test_an_api_run_is_what_a_run_is_unless_the_worker_says_otherwise(self) -> None:
        key = platform_key(self.agent)[1]
        run = AgentRun.objects.create(agent=self.agent, api_key=key, model="m", pipeline_version="0.4")
        self.assertEqual(run.trigger, RunTrigger.API.value)

    def test_a_platform_run_without_a_key_is_a_library_run(self) -> None:
        run = self._run(agent_version=self.v1, scope={"jurisdictions": ["se"]})
        self.assertIsNone(run.tenant_id)
        self.assertIsNone(run.api_key_id)

    def test_a_tenant_agents_run_lands_in_its_tenant_whatever_the_caller_says(self) -> None:
        tenancy.activate(self.tenant.id)
        run = self._run(agent=self.definition, tenant_agent=self.tenant_agent, tenant=None, trigger=RunTrigger.MANUAL.value)
        self.assertEqual(run.tenant_id, self.tenant.id)

    def test_a_library_run_never_names_a_tenant_agent(self) -> None:
        run = AgentRun(agent=self.definition, tenant_agent=self.tenant_agent, tenant=None, model="m", pipeline_version="0.4")
        run.trigger = RunTrigger.SCHEDULE.value
        with self.assertRaises(IntegrityError), transaction.atomic():
            AgentRun.objects.bulk_create([run])

    def test_the_version_is_written_when_the_run_opens_and_never_changes(self) -> None:
        run = self._run(agent_version=self.v1)
        self.assertEqual(AgentRun.objects.filter(pk=run.pk).update(status=RunStatus.SUCCEEDED.value, cost=Decimal("0.12")), 1)
        for version in (self.v2, None):
            with self.subTest(version=version), self.assertRaisesMessage(DatabaseError, "never changes"):
                with transaction.atomic():
                    AgentRun.objects.filter(pk=run.pk).update(agent_version=version)
        unversioned = self._run()
        with self.assertRaisesMessage(DatabaseError, "never changes"), transaction.atomic():
            AgentRun.objects.filter(pk=unversioned.pk).update(agent_version=self.v1)


class TenantAgentTableTests(TransactionTestCase):
    """The bank's own agents, research requests and cap on the `app` alias (cw_app, no
    ownership). Written straight to the table, never through a route, so what refuses is
    the database: the fence trigger, a CHECK or the policy."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with library_write("test"):
            self.platform = Agent.objects.create(key="watch-sweeper", kind=AgentKind.WATCH.value, current_version=1)
        self.definition = tenant_definition()
        self.closed = tenant_definition("bank-closed", configurable=False)
        self.tenant_a = factories.tenant(slug="tenant-agent-a")
        self.tenant_b = factories.tenant(slug="tenant-agent-b")
        self.user = factories.user(email="agents-admin@example.test")

    def _tenant_agent(self, tenant: Any, agent: Agent) -> TenantAgent:
        with transaction.atomic(using="app"):
            tenancy.activate(tenant.id, using="app")
            return TenantAgent.objects.using("app").create(tenant=tenant, agent=agent)

    def _request(self, tenant_id: uuid.UUID | None, **fields: Any) -> ResearchRequest:  # compliance: allow-kwargs test helper forwarding model fields
        with transaction.atomic(using="app"):
            if tenant_id is not None:
                tenancy.activate(tenant_id, using="app")
            return ResearchRequest.objects.using("app").create(tenant_id=tenant_id, requested_by_id=self.user.id, **fields)

    def test_a_bank_adds_an_agent_only_on_a_configurable_tenant_definition(self) -> None:
        added = self._tenant_agent(self.tenant_a, self.definition)
        self.assertEqual((added.enabled, added.cadence, added.scope), (False, "weekly", {}))
        for agent, why in ((self.platform, "one of bleqq's agents"), (self.closed, "not tenant-configurable")):
            with self.subTest(why), self.assertRaisesMessage(IntegrityError, "tenant_agent refused"):
                self._tenant_agent(self.tenant_b, agent)
        with self.assertRaisesMessage(IntegrityError, "tenant_agent refused"), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            TenantAgent.objects.using("app").filter(pk=added.pk).update(agent=self.platform)

    def test_a_bank_has_one_row_per_agent_and_times_it_within_a_week_and_a_day(self) -> None:
        self._tenant_agent(self.tenant_a, self.definition)
        with self.assertRaises(IntegrityError):
            self._tenant_agent(self.tenant_a, self.definition)
        second = tenant_definition("bank-second")
        for fields in ({"run_weekday": 0}, {"run_weekday": 8}, {"run_hour": 24}):
            with self.subTest(fields), self.assertRaises(IntegrityError), transaction.atomic(using="app"):
                tenancy.activate(self.tenant_a.id, using="app")
                TenantAgent.objects.using("app").create(tenant=self.tenant_a, agent=second, **fields)

    def test_an_agent_is_paused_never_deleted(self) -> None:
        added = self._tenant_agent(self.tenant_a, self.definition)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            paused = TenantAgent.objects.using("app").filter(pk=added.pk).update(
                paused_at=added.updated_at, paused_by_id=self.user.id, pause_reason="Quarter close"
            )
        self.assertEqual(paused, 1)
        with self.assertRaisesMessage(DatabaseError, "paused, never deleted"), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            TenantAgent.objects.using("app").filter(pk=added.pk).delete()

    def test_a_request_without_a_tenant_is_the_consoles_retag_and_nothing_else(self) -> None:
        retag = self._request(None, kind=ResearchRequestKind.RETAG.value, topic="Custody records: Client money")
        self.assertEqual(retag.status, "queued")
        agent_a = self._tenant_agent(self.tenant_a, self.definition)
        asked = self._request(self.tenant_a.id, tenant_agent_id=agent_a.id, kind=ResearchRequestKind.RESEARCH_TOPIC.value, topic="DORA")
        self.assertEqual(asked.tenant_id, self.tenant_a.id)
        for tenant_id, fields, why in (
            (None, {"kind": ResearchRequestKind.RESEARCH_TOPIC.value, "topic": "x"}, "a platform request that is not a retag"),
            (self.tenant_a.id, {"kind": ResearchRequestKind.RETAG.value, "tenant_agent_id": agent_a.id}, "a bank's retag"),
            (self.tenant_a.id, {"kind": ResearchRequestKind.RUN_NOW.value}, "a bank's request to no agent of its own"),
        ):
            with self.subTest(why), self.assertRaises(IntegrityError):
                self._request(tenant_id, **fields)

    def test_research_requests_follow_agent_runs_split_policy(self) -> None:
        agent_a = self._tenant_agent(self.tenant_a, self.definition)
        retag = self._request(None, kind=ResearchRequestKind.RETAG.value, topic="Client money")
        own = self._request(self.tenant_a.id, tenant_agent_id=agent_a.id, kind=ResearchRequestKind.RUN_NOW.value)
        for tenant_id, expected in ((self.tenant_a.id, {retag.pk, own.pk}), (self.tenant_b.id, {retag.pk}), (None, {retag.pk})):
            with self.subTest(tenant=tenant_id), transaction.atomic(using="app"):
                if tenant_id is not None:
                    tenancy.activate(tenant_id, using="app")
                self.assertEqual(set(ResearchRequest.objects.using("app").values_list("pk", flat=True)), expected)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self.assertEqual(ResearchRequest.objects.using("app").filter(pk=retag.pk).update(status="cancelled"), 0)
        with self.assertRaises(ProgrammingError), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            ResearchRequest.objects.using("app").create(requested_by_id=self.user.id, kind=ResearchRequestKind.RETAG.value, topic="x")

    def test_a_bank_has_one_cap_and_never_a_negative_one(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            TenantAgentBudget.objects.using("app").create(tenant=self.tenant_a, monthly_cap=Decimal("500.00"))
        for tenant, cap, why in ((self.tenant_a, Decimal("100.00"), "a second cap"), (self.tenant_b, Decimal("-1.00"), "a negative cap")):
            with self.subTest(why), self.assertRaises(IntegrityError), transaction.atomic(using="app"):
                tenancy.activate(tenant.id, using="app")
                TenantAgentBudget.objects.using("app").create(tenant=tenant, monthly_cap=cap)

    def test_another_bank_reads_and_writes_none_of_it(self) -> None:
        agent_a = self._tenant_agent(self.tenant_a, self.definition)
        self._request(self.tenant_a.id, tenant_agent_id=agent_a.id, kind=ResearchRequestKind.RUN_NOW.value)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            TenantAgentBudget.objects.using("app").create(tenant=self.tenant_a, monthly_cap=Decimal("500.00"))
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            for model in (TenantAgent, TenantAgentBudget, ResearchRequest):
                self.assertFalse(model.objects.using("app").exists(), model.__name__)
            self.assertEqual(TenantAgent.objects.using("app").filter(pk=agent_a.pk).update(enabled=True), 0)
        with self.assertRaises(ProgrammingError), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            TenantAgent.objects.using("app").create(tenant=self.tenant_a, agent=tenant_definition("bank-other"))

    def test_a_banks_request_or_run_never_names_another_banks_agent(self) -> None:
        """Foreign keys ignore row-level security, so the id of tenant A's agent is enough to
        reach it from tenant B's own row; the same-tenant foreign keys refuse it."""
        agent_a = self._tenant_agent(self.tenant_a, self.definition)
        for write, why in (
            (
                lambda: ResearchRequest.objects.using("app").create(
                    tenant_id=self.tenant_b.id,
                    tenant_agent_id=agent_a.id,
                    requested_by_id=self.user.id,
                    kind=ResearchRequestKind.RUN_NOW.value,
                ),
                "a request",
            ),
            (
                lambda: AgentRun.objects.using("app").bulk_create(
                    [
                        AgentRun(
                            agent_id=self.definition.id,
                            tenant_id=self.tenant_b.id,
                            tenant_agent_id=agent_a.id,
                            trigger=RunTrigger.SCHEDULE.value,
                            model="m",
                            pipeline_version="0.4",
                        )
                    ]
                ),
                "a run",
            ),
        ):
            with self.subTest(why), self.assertRaisesMessage(IntegrityError, "same_tenant"):
                with transaction.atomic(using="app"):
                    tenancy.activate(self.tenant_b.id, using="app")
                    write()

    def test_a_keyless_run_writes_only_the_sessions_zone(self) -> None:
        agent_a = self._tenant_agent(self.tenant_a, self.definition)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            run = AgentRun.objects.using("app").create(
                agent_id=self.definition.id, tenant_agent=agent_a, trigger=RunTrigger.SCHEDULE.value, model="m", pipeline_version="0.4"
            )
        self.assertEqual(run.tenant_id, self.tenant_a.id)
        with transaction.atomic(using="app"):
            AgentRun.objects.using("app").create(agent_id=self.platform.id, trigger=RunTrigger.SCHEDULE.value, model="m", pipeline_version="0.4")
        for tenant_id, fields, why in (
            (self.tenant_a.id, {"agent_id": self.platform.id}, "a library run from a bank's session"),
            (None, {"agent_id": self.definition.id, "tenant_agent": agent_a}, "a bank's run from the platform's session"),
            (self.tenant_b.id, {"agent_id": self.definition.id, "tenant_agent": agent_a}, "a bank's run from another bank's session"),
        ):
            with self.subTest(why), self.assertRaises(ProgrammingError), transaction.atomic(using="app"):
                if tenant_id is not None:
                    tenancy.activate(tenant_id, using="app")
                AgentRun.objects.using("app").create(trigger=RunTrigger.SCHEDULE.value, model="m", pipeline_version="0.4", **fields)
