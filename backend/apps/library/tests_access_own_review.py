"""Findings of the security review of agent access and the bank's own records
(security-review-c11-access-d89, docs/reviews/CHUNK11_ACCESS_OWN_REVIEW.md) on the
library reads of a bank's own agent. Each test was written first and failed before its fix.

M3: the bank's overlay and its own tags (applicability, compliance status, owner, team,
tenant tags) were answered to an agent access credential whenever tenant reach was on for
the bank and the entry, whether or not the credential held `tenant:read`. The register
itself refuses such a credential (403 `permission_denied`), and a person without
`register.read` could mint a `library:read` token that read the register's summary through
the library. The bank's layer now needs `tenant:read` as well as reach (AGENT_ACCESS.md
section 5), and its filters are refused without it.
"""

from __future__ import annotations

from types import SimpleNamespace

from apps.library.tests_agent_access_reads import NOT_ASSESSED, OBLIGATIONS, OVERLAY, AgentReadCase
from apps.shared import factories


class TheBanksLayerNeedsTenantRead(AgentReadCase):
    def test_a_library_only_credential_reads_no_overlay_even_with_reach_on(self) -> None:
        w = self.world
        w.reach(True, w.trading)
        library_only = factories.entry_key(w.tenant, SimpleNamespace(id=w.trading.id), scopes=("library:read",)).plain_key
        row = {r["stableKey"]: r for r in self.get(library_only, OBLIGATIONS).json()["items"]}[w.futures.stable_key]
        self.assertEqual({field: row[field] for field in OVERLAY}, NOT_ASSESSED)
        self.assertEqual(row["tenantTags"], [])
        card = self.get(library_only, f"{OBLIGATIONS}/{w.futures.stable_key}").json()
        self.assertEqual({field: card[field] for field in OVERLAY}, NOT_ASSESSED)
        for params in ({"applicability": "applies"}, {"tenantTag": "desk-watch"}):
            with self.subTest(params=params):
                refused = self.get(library_only, OBLIGATIONS, params)
                self.assertEqual((refused.status_code, refused.json()["code"]), (403, "tenant_reach_off"))


class TheBanksOwnListsFollowTheSameGate(AgentReadCase):
    """M4: `GET /vocab/{list}` handed an agent access credential the bank's own lists (its
    tags with their usage counts, its teams, its reasons and sub-statuses) with tenant reach
    off, which the inventory withholds. A library list stays readable."""

    def test_the_banks_own_lists_need_the_registers_gate(self) -> None:
        w = self.world
        library_only = factories.entry_key(w.tenant, SimpleNamespace(id=w.trading.id), scopes=("library:read",)).plain_key
        for on, key, allowed in ((False, w.trading_key, False), (True, library_only, False), (True, w.trading_key, True)):
            w.reach(on, w.trading)
            for url in ("/api/v1/vocab/tenant_tag", "/api/v1/vocab/tenant_tag/desk-watch", "/api/v1/vocab/team"):
                with self.subTest(reach=on, url=url, allowed=allowed):
                    answer = self.get(key, url)
                    if allowed:
                        self.assertEqual(answer.status_code, 200, answer.content)
                    else:
                        self.assertEqual((answer.status_code, answer.json()["code"]), (403, "tenant_reach_off"))
            self.assertEqual(self.get(key, "/api/v1/vocab/duty_type").status_code, 200, "a library list stays readable")


class TheSourceRegistryIsNotAnAgentAccessRead(AgentReadCase):
    """M5: the source registry and its coverage log (`GET /sources`, `/sources/coverage`) are
    for the platform's own runs and the bank's people with `watch.read` (WAT-01, AGT-02). A
    bank's own agent reads the library, search, the upcoming list and the register
    (AGENT_ACCESS.md section 5), yet any agent access credential with `library:read` read
    them, so a personal token read what its person's own session was refused."""

    def test_an_agent_access_credential_is_refused_the_registry(self) -> None:
        w = self.world
        reader = factories.member(w.tenant, roles=("reader",)).user
        token = factories.personal_token(w.tenant, reader, scopes=("library:read",)).plain_key
        for key in (w.trading_key, token):
            for url in ("/api/v1/sources", "/api/v1/sources/coverage"):
                with self.subTest(url=url):
                    answer = self.get(key, url)
                    self.assertEqual((answer.status_code, answer.json()["code"]), (403, "permission_denied"))
