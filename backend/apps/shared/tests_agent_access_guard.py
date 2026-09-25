"""Guard: an agent access credential reads and nothing else (ACC-03, ACC-05, ACC-09, ADR 0055).

Walks every operation Ninja registered (apps/shared/routes.py, the objects behind
openapi.json) and calls each with a key of an agent access entry and with a personal
access token, both holding every scope such a credential may hold:

- every route carrying `@requires_step_up` answers 403 `step_up_required`;
- every other write answers 403 `read_only_credential`, except the reads with a body in
  `READ_ONLY_ALLOWED`;
- every auth class a route takes is one of the three that hand a credential to the guard,
  so a new class that reads a key its own way fails here until it does too.

Then the rate: at most `AGENT_ACCESS_RATE_PER_MINUTE` a minute per credential, 429 beyond
it with one security-log row per window, and no limit on a key that is not agent access.

Proven to fail 2026-09-25: with `agent_access_guard.check` returning at once, the walk
listed 289 answers that were not the refusal (every write, both credentials, both
headers), and the rate test's third request went through.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.identity.models import LoginEvent, LoginEventKind, LoginMethod
from apps.shared import agent_access_guard, factories, permissions as perms
from apps.shared.agent_access_guard import READ_ONLY_ALLOWED
from apps.shared.authentication import ApiKeyAuth, EnrolmentAuth, SessionAuth
from apps.shared.permissions import step_up_of
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase
from config.api import api

V1 = "/api/v1"
READS = sorted(perms.AGENT_ACCESS_SCOPES)
GUARDED_AUTH = (SessionAuth, ApiKeyAuth, EnrolmentAuth)


def _url(path: str) -> str:
    return V1 + re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


class EveryRouteIsFenced(SimpleTestCase):
    def test_every_route_takes_only_auth_classes_that_hand_a_credential_to_the_guard(self) -> None:
        strays = [
            f"{op.method} {op.path}: {type(auth).__name__}"
            for op in iter_operations(api)
            for auth in op.auth
            if not isinstance(auth, GUARDED_AUTH)
        ]
        self.assertEqual(strays, [], "an auth class that reads a key must run agent_access_guard.check")

    def test_the_allow_list_is_reads_with_a_body(self) -> None:
        self.assertEqual(READ_ONLY_ALLOWED, {("POST", "/search"), ("POST", "/agent-access/what-applies"), ("POST", "/mcp")})


class EveryWriteRefusesAnAgentAccessCredential(ScenarioTestCase):
    def setUp(self) -> None:
        self.bank = factories.tenant(slug="guard-bank")
        entry = factories.agent_access_entry(self.bank)
        person = factories.member(self.bank, roles=("compliance_officer",)).user
        self.credentials = {
            "entry key": factories.entry_key(self.bank, entry, scopes=READS).plain_key,
            "personal token": factories.personal_token(self.bank, person, scopes=READS, entry=entry).plain_key,
        }

    def _call(self, method: str, path: str, headers: dict[str, Any]) -> Any:
        return self.client.generic(method, _url(path), data="{}", content_type="application/json", **headers)

    def test_the_walk_over_every_operation(self) -> None:
        operations = [op for op in iter_operations(api) if op.auth]
        self.assertGreater(len(operations), 100, "the enumeration is broken")
        wrong: list[str] = []
        for name, plain in self.credentials.items():
            for header in ({"HTTP_X_API_KEY": plain}, {"HTTP_AUTHORIZATION": f"Bearer {plain}"}):
                for op in operations:
                    if step_up_of(op.view_func):
                        wanted = "step_up_required"
                    elif op.method not in agent_access_guard.READ_METHODS and (op.method, op.path) not in READ_ONLY_ALLOWED:
                        wanted = "read_only_credential"
                    else:
                        continue
                    response = self._call(op.method, op.path, header)
                    answer = response.json().get("code") if response.status_code == 403 else response.status_code
                    if answer != wanted:
                        wrong.append(f"{name} {sorted(header)[0]}: {op.method} {op.path} answered {answer}, wanted 403 {wanted}")
        self.assertEqual(wrong, [], "\n".join(wrong))

    def test_an_allow_listed_read_is_not_refused_as_a_write(self) -> None:
        response = self._call("POST", "/search", {"HTTP_X_API_KEY": self.credentials["personal token"]})
        self.assertNotEqual(response.json().get("code"), "read_only_credential")

    def test_a_read_passes_the_guard(self) -> None:
        for name, plain in self.credentials.items():
            with self.subTest(name):
                self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=plain).status_code, 200)

    def test_no_credential_reaches_a_proposal_route(self) -> None:
        for name, plain in self.credentials.items():
            for path in ("/proposals", "/proposals/{proposal_id}"):
                with self.subTest(name=name, path=path):
                    self.assertEqual(self._call("GET", path, {"HTTP_X_API_KEY": plain}).status_code, 403)

    def test_a_key_that_is_not_agent_access_keeps_its_writes(self) -> None:
        bank_key = factories.api_key(self.bank, scopes=[perms.SCOPE_PROPOSALS_WRITE])
        response = self._call("POST", "/proposals", {"HTTP_X_API_KEY": bank_key.plain_key})
        self.assertNotEqual(response.json().get("code"), "read_only_credential")


@override_settings(RATE_LIMITING_ENABLED=True, AGENT_ACCESS_RATE_PER_MINUTE=2)
class ThePerCredentialRate(ScenarioTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.bank = factories.tenant(slug="rate-bank")
        self.entry = factories.agent_access_entry(self.bank)
        self.person = factories.member(self.bank, roles=("reader",)).user

    def _read(self, plain: str) -> Any:
        return self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=plain)

    def test_a_credential_over_its_rate_is_refused_and_logged_once_a_window(self) -> None:
        token = factories.personal_token(self.bank, self.person, entry=self.entry)
        key = factories.entry_key(self.bank, self.entry)
        self.assertEqual([self._read(token.plain_key).status_code for _ in range(2)], [200, 200])
        for _ in range(2):
            refused = self._read(token.plain_key)
            self.assertEqual((refused.status_code, refused.json()["code"]), (429, "rate_limited"))
        self.assertEqual(self._read(key.plain_key).status_code, 200, "the rate is per credential")
        self.activate(self.bank)
        rows = list(LoginEvent.objects.filter(event=LoginEventKind.CREDENTIAL_RATE_LIMITED.value))
        self.assertEqual([(row.api_key_id, row.method, row.user_id, row.success) for row in rows], [(token.id, LoginMethod.PERSONAL_TOKEN.value, self.person.id, False)])

    def test_the_rate_counts_a_refused_write_too(self) -> None:
        key = factories.entry_key(self.bank, self.entry)
        for _ in range(2):
            self.assertEqual(self.client.post(f"{V1}/proposals", data="{}", content_type="application/json", HTTP_X_API_KEY=key.plain_key).status_code, 403)
        self.assertEqual(self._read(key.plain_key).status_code, 429)

    def test_a_key_that_is_not_agent_access_has_no_such_rate(self) -> None:
        bank_key = factories.api_key(self.bank)
        self.assertEqual({self._read(bank_key.plain_key).status_code for _ in range(4)}, {200})
