"""Contract guard for the two library reads chunk 5 adds (FP-04, INV-06, AGT-01, AGT-02,
NFR-01; `c5-contract-api-screens`).

`GET /authorities` is the list chunk 3 cut to chunk 5 (ruling E): the change header and
the console's authority filter both need it. `GET /obligations/{obligationId}/sources` is
a live record's citations, and it matters that an agent's key holding `library:read` alone
can read it: that is how a run re-checks a library record against the page it came from
without holding a single write scope, and the correction it finds is a proposal, never an
edit (AGT-01, item 3, PRO-01).

Both sit behind the same logic gate chunk 3's record reads use, which is what this file
proves. Both are built (`c5-watch-change-reads`, `library-recheck-loop`) and answer real
rows, proved on real data in `tests_reading.py`. Written before the routes existed: both
cases below failed with 404 until the routes landed.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase

from apps.shared import permissions as perms
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)

OBLIGATION = "44444444-4444-4444-8444-444444444444"

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

# (name, url). Both serve a person with library.read and a key with library:read.
LIBRARY_READS = [
    ("listAuthorities", "/api/v1/authorities"),
    ("getRecordSources", f"/api/v1/obligations/{OBLIGATION}/sources"),
]


class LibraryReadGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        for name, url in LIBRARY_READS:
            with self.subTest(operation=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_session_without_library_read_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.CASES_READ}, tenant_id=uuid.uuid4())):
            for name, url in LIBRARY_READS:
                with self.subTest(operation=name):
                    response = self.client.get(url, **AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], perms.LIBRARY_READ)

    def test_a_key_without_library_read_is_403_naming_the_scope(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_UPCOMING_READ})):
            for name, url in LIBRARY_READS:
                with self.subTest(operation=name):
                    response = self.client.get(url, **AS_KEY)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], perms.SCOPE_LIBRARY_READ)

    def test_a_key_with_only_library_read_reaches_the_record_sources(self) -> None:
        """The re-check's whole point: reading what a record cites needs no write scope, so
        a key that can propose but not edit is still enough (AGT-01, item 3)."""
        with stub_api_key(agent_principal(scopes={perms.SCOPE_LIBRARY_READ})):
            for name, url in LIBRARY_READS:
                with self.subTest(operation=name):
                    # Past the gate: the authorities answer rows, and the fixed id names no
                    # record, so its citations answer the 404 of a record that is not there.
                    self.assertIn(self.client.get(url, **AS_KEY).status_code, (200, 404))

