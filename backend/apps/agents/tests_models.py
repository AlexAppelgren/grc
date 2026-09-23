"""Models, seed and isolation of the agents app (AGT-01, AGT-02, AGT-03, ID-10, D-80).

Proven here: the definition reader reads every shipped definition exactly as PyYAML does,
so the seed's stripped-down reader can never drift from real YAML; the definitions are in
the API image, where the seed reads them on every deploy; the seed creates one agent row
per definition once and leaves it alone on the next deploy, and an agent's key never
changes; the confirming definition is independent of the proposing one by what it may
call, and every vocabulary a definition reads at run start is one the API serves;
`agent_run` is a mixed table whose policies bite for `cw_app`: a tenant reads the
library's runs but never writes them, and a run lives in its key's zone; a key bound to
an agent writes its audit rows as that agent, not as a bare key id; and the decision an
agent reports with its model call is refused without a model, a version or a citation.
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
from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, ProgrammingError, transaction
from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from pydantic import ValidationError as SchemaError

from apps.agents.models import Agent, AgentKind, AgentRun, RunStatus
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
LIBRARY_CONFIRMER = DEFINITIONS / "library-confirmer" / "v1" / "definition.yaml"
# The lists an agent's key reads that are not rows of the vocabulary registry, each behind
# a route of its own that takes `library:read`: `GET /taxonomy/terms`, `GET /authorities`
# and `GET /sources`.
READ_OUTSIDE_THE_REGISTRY = frozenset({"taxonomy_term", "authority", "source"})
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
        self.assertFalse(read_definition(LIBRARY_CONFIRMER).active, "library-confirmer v1 waits for its evals")

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
        confirmer, sweeper = _parsed("library-confirmer", 1), _parsed("watch-sweeper", 1)
        self.assertNotEqual(confirmer["id"], sweeper["id"])
        prompts = {
            (DEFINITIONS / definition["id"] / "v1" / definition["prompt"]).read_text(encoding="utf-8")
            for definition in (confirmer, sweeper)
        }
        self.assertEqual(len(prompts), 2, "the confirmer has a prompt of its own")

    def test_every_vocabulary_read_at_run_start_is_one_the_api_serves(self) -> None:
        """A list named here that no route serves would fail the run at its first read.
        The registry's library lists come from `GET /vocab/{list}`; the rest have routes of
        their own. A tenant list is never one: a platform run reads no bank's rows."""
        served = set(LIBRARY_LISTS) | READ_OUTSIDE_THE_REGISTRY
        for name, version in SHIPPED:
            lists = _parsed(name, version)["vocabularies_read_at_run_start"]
            self.assertEqual(len(lists), len(set(lists)), f"{name} names a list twice")
            self.assertLessEqual(set(lists), served, name)
        self.assertIn("rejection_reason", _parsed("library-confirmer", 1)["vocabularies_read_at_run_start"])


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
        self.plain_key = platform_key(self.agent)[0]

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
        "promptTemplate": "library-confirmer/decide/v1",
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
        ):
            with self.assertRaises(SchemaError, msg=why):
                AgentDecision.model_validate({**self.DECISION, **change})
        body = {name: value for name, value in self.DECISION.items() if name != "model"}
        with self.assertRaises(SchemaError, msg="a missing model"):
            AgentDecision.model_validate(body)
