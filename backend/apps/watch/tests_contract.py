"""Contract guard for the watch routes an agent or a library editor writes through, and
for the two lists of changes a person reads (WAT-01 to WAT-04, AGT-01, AGT-02, FP-03,
FP-04, NFR-01; chunk 5 `c5-contract-api-agent` and `c5-contract-api-screens`).

Every route here was declared before the logic that serves it, and the writes still answer
501 `not_built` from the named function in the module that will build them. What stands in
front of the logic is what this file proves, per route, whether or not that logic exists
yet: no credential is 401, the wrong scope or permission is 403 naming what was needed, and
a body the schema does not accept is 422 — a term, a tone or a colour never rides along
unseen. Written before the routes existed (2026-09-20): every case below failed with 404
until `watch/api.py` landed.

The two lists are separate on purpose and the tests below pin that. `GET /changes` is a
bank's feed under `watch.read` and joins that bank's own case; `GET /console/changes` is
the library editor's queue under `proposals.review`, which no tenant role holds, and joins
no case at all, because a console session has no tenant (`c5-contract-api-screens`). A
tenant member reaching the console list, or an editor reaching the feed, is a leak between
the zones, so each is proved refused.

The four curation routes are no longer stubs — `c5-watch-curation` built them, and what
they do behind these gates is proved in `tests_curation.py`. The two registry reads and the
two registry writes followed them on 2026-09-21 (`c5-watch-sources-coverage`, proved in
`tests_sources.py`), and the two registration routes the same day
(`c5-watch-registration`, proved in `tests_registration.py`). Nothing of this app is
declared ahead of its logic any more, and every one of them kept the gate assertions it had
on its way out of the stub lists, so nothing is left unproved by their leaving.

The library fence is not weakened here: none of these routes writes an inventory row, and
each of the write modules they name (`watch/sources.py`, `registration.py`, `curation.py`)
opens `watch_write()`, which reaches the seven watch tables and refuses every other library
table at runtime. Which gate each of them may carry is `WATCH_ROUTE_GATES` in
`apps/shared/tests_library_fence.py`, and the registry writes are the ones held to a
person's `sources.manage` rather than to a key's scope. `watch/reading.py` is built and
writes nothing at all.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase

from apps.shared import factories, permissions as perms
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from apps.watch.schemas import LINKS_MAX

CHANGE = "11111111-1111-4111-8111-111111111111"
EVENT = "22222222-2222-4222-8222-222222222222"
SOURCE = "33333333-3333-4333-8333-333333333333"
OBLIGATION = "44444444-4444-4444-8444-444444444444"

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

SOURCE_BODY = {"name": "Finansinspektionen news", "kind": "authority_site", "checkFrequency": "daily"}
SOURCE_PATCH = {"active": False}
CHANGE_BODY = {
    "stableKey": "fi-2026-14",
    "title": "New reporting rules",
    "changeType": "adopted",
    "authorityLabel": "Finansinspektionen",
    "summary": "Reporting moves to a quarterly cycle.",
    "sourceLabel": "FI news",
    "sourceUrl": "https://www.fi.se/en/published/news/2026/",
}
CHANGE_PATCH = {"keyDateLabel": "Transition ends"}
EVENT_BODY = {"label": "Consultation closes", "eventDate": "2026-11-01", "datePrecision": "day"}
DOCUMENT_BODY = {"url": "https://www.fi.se/en/published/news/2026/reporting/"}
LINKS_BODY = [{"obligationId": OBLIGATION, "confidence": 0.8}]

# Routes an agent key writes and a library editor's session may also write (the change
# facts of WAT-02 and WAT-03): (name, method, url, body, scope, permission).
BOTH_ROUTES = [
    ("createChange", "post", "/api/v1/changes", CHANGE_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("updateChange", "patch", f"/api/v1/changes/{CHANGE}", CHANGE_PATCH, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("addChangeEvent", "post", f"/api/v1/changes/{CHANGE}/events", EVENT_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("updateChangeEvent", "patch", f"/api/v1/changes/{CHANGE}/events/{EVENT}", EVENT_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
    ("replaceChangeObligations", "put", f"/api/v1/changes/{CHANGE}/obligations", LINKS_BODY, perms.SCOPE_CHANGES_WRITE, perms.PROPOSALS_REVIEW),
]
# Routes only an agent key writes: (name, method, url, body, scope).
KEY_ROUTES = [
    ("addChangeDocument", "post", f"/api/v1/changes/{CHANGE}/documents", DOCUMENT_BODY, perms.SCOPE_CHANGES_WRITE),
]
# Reads a person's session or a key with library:read may make: (name, url, scope, permission).
READ_ROUTES = [
    ("listSources", "/api/v1/sources", perms.SCOPE_LIBRARY_READ, perms.WATCH_READ),
    ("getSourceCoverage", "/api/v1/sources/coverage", perms.SCOPE_LIBRARY_READ, perms.WATCH_READ),
]
# Routes only a library editor's session writes: (name, method, url, body, permission).
SESSION_ROUTES = [
    ("createSource", "post", "/api/v1/sources", SOURCE_BODY, perms.SOURCES_MANAGE),
    ("updateSource", "patch", f"/api/v1/sources/{SOURCE}", SOURCE_PATCH, perms.SOURCES_MANAGE),
]
# Every write route of this app is built: the four curation routes left this list when
# `c5-watch-curation` built them, the two registry writes when `c5-watch-sources-coverage`
# did, and the two registration routes when `c5-watch-registration` did. The gates above
# still cover all of them, and the ids below are the ones that reach a real change or a
# real source, which none of these constants names.
BUILT = frozenset(
    {
        "createChange",
        "addChangeDocument",
        "updateChange",
        "addChangeEvent",
        "updateChangeEvent",
        "replaceChangeObligations",
        "createSource",
        "updateSource",
    }
)
STUBBED_BOTH_ROUTES = [route for route in BOTH_ROUTES if route[0] not in BUILT]


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class WatchRouteGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        cases = (
            [(n, m, u, b) for n, m, u, b, _, _ in BOTH_ROUTES]
            + [(n, m, u, b) for n, m, u, b, _ in KEY_ROUTES]
            + [(n, "get", u, None) for n, u, _, _ in READ_ROUTES]
            + [(n, m, u, b) for n, m, u, b, _ in SESSION_ROUTES]
        )
        for name, method, url, body in cases:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_key_without_the_scope_is_403_naming_it(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_UPCOMING_READ})):
            cases = (
                [(n, m, u, b, s) for n, m, u, b, s, _ in BOTH_ROUTES]
                + [(n, m, u, b, s) for n, m, u, b, s in KEY_ROUTES]
                + [(n, "get", u, None, s) for n, u, s, _ in READ_ROUTES]
            )
            for name, method, url, body, scope in cases:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], scope)

    def test_a_session_without_the_permission_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.CASES_READ}, tenant_id=uuid.uuid4())):
            cases = (
                [(n, m, u, b, p) for n, m, u, b, _, p in BOTH_ROUTES]
                + [(n, "get", u, None, p) for n, u, _, p in READ_ROUTES]
                + [(n, m, u, b, p) for n, m, u, b, p in SESSION_ROUTES]
            )
            for name, method, url, body, permission in cases:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], permission)

    def test_a_key_never_registers_a_source(self) -> None:
        """The registry is a library editor's (WAT-01): no scope adds or deactivates a source."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body, _ in SESSION_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 401)

    def test_a_person_never_attaches_a_document(self) -> None:
        """Fetched pages arrive from the agent that screened them (AGT-07), not from a screen."""
        with stub_session(user_principal(permissions=perms.ALL_PERMISSIONS, tenant_id=uuid.uuid4())):
            for name, method, url, body, _ in KEY_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 401)

    def test_bad_input_is_422_before_the_stub(self) -> None:
        cases = [
            ("createChange", "post", "/api/v1/changes", {k: v for k, v in CHANGE_BODY.items() if k != "title"}),
            ("createChange", "post", "/api/v1/changes", {**CHANGE_BODY, "sourceUrl": "not a url"}),
            ("createChange", "post", "/api/v1/changes", {**CHANGE_BODY, "tone": "negative"}),
            ("updateChange", "patch", f"/api/v1/changes/{CHANGE}", {"status": "retired"}),
            ("addChangeEvent", "post", f"/api/v1/changes/{CHANGE}/events", {"eventDate": "2026-11-01"}),
            ("addChangeEvent", "post", f"/api/v1/changes/{CHANGE}/events", {**EVENT_BODY, "datePrecision": "decade"}),
            ("addChangeDocument", "post", f"/api/v1/changes/{CHANGE}/documents", {"url": ""}),
            ("replaceChangeObligations", "put", f"/api/v1/changes/{CHANGE}/obligations", [{"confidence": 0.5}]),
        ]
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body in cases:
                with self.subTest(operation=name, body=body):
                    response = _call(self.client, method, url, body, AS_KEY)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_the_obligation_links_a_call_may_carry_are_capped(self) -> None:
        """This route takes its list as the whole body, so the cap sits on the route rather
        than on a schema field, and is the `LINKS_MAX` the same list carries inside
        `WatchChangeInput` (WAT-04). A key sends it, and an uncapped array would be an
        unbounded body to parse. The body is built here, not in the table above, so a
        failure names the case instead of printing two hundred links."""
        url = f"/api/v1/changes/{CHANGE}/obligations"
        link = {"obligationId": OBLIGATION, "confidence": 0.5}
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            refused = _call(self.client, "put", url, [link] * (LINKS_MAX + 1), AS_KEY)
            at_the_cap = _call(self.client, "put", url, [link] * LINKS_MAX, AS_KEY)
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["code"], "validation_error")
        self.assertEqual(at_the_cap.status_code, 404, "the cap itself is accepted and reaches the logic")

    def test_a_source_write_refuses_an_unknown_field(self) -> None:
        with stub_session(user_principal(permissions={perms.SOURCES_MANAGE})):
            response = _call(self.client, "post", "/api/v1/sources", {**SOURCE_BODY, "colour": "red"}, AS_SESSION)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")


class WatchRouteStubs(TestCase):
    def test_nothing_in_this_app_is_still_a_stub(self) -> None:
        self.assertEqual(STUBBED_BOTH_ROUTES, [], "every write route of this app is built")

    # What each built write answers once its gate has passed and these constants have
    # reached its logic: 404 for an id nothing holds, 422 `unknown_key` for a body naming a
    # vocabulary row this bare TestCase never seeded. Either way the gate ran first.
    REACHED_THE_LOGIC = {
        "createChange": (422, "unknown_key"),
        "addChangeDocument": (404, "not_found"),
        "updateChange": (404, "not_found"),
        "addChangeEvent": (404, "not_found"),
        "updateChangeEvent": (404, "not_found"),
        "replaceChangeObligations": (404, "not_found"),
        "createSource": (422, "unknown_key"),
        "updateSource": (404, "not_found"),
    }

    def test_every_built_route_is_accounted_for(self) -> None:
        self.assertEqual(sorted(BUILT), sorted(self.REACHED_THE_LOGIC))

    def test_the_built_change_routes_answer_from_their_logic(self) -> None:
        """A route its task has built no longer answers `not_built`. The change these
        constants name does not exist and no vocabulary is seeded here, so the honest
        answers are 404 and `unknown_key` — which is also the proof that the gate ran first
        and the lookup second."""
        cases = (
            [(n, m, u, b) for n, m, u, b, _, _ in BOTH_ROUTES]
            + [(n, m, u, b) for n, m, u, b, _ in KEY_ROUTES]
        )
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body in cases:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_KEY)
                    status, code = self.REACHED_THE_LOGIC[name]
                    self.assertEqual(response.status_code, status, response.content)
                    self.assertEqual(response.json()["code"], code)

    def test_the_built_registry_writes_answer_from_their_logic(self) -> None:
        # A real person behind the console session: a registry write names who made it in
        # the audit row, so a principal with no user row behind it is refused before the
        # lookup and would prove nothing about the logic.
        editor = factories.platform_user(email="library.editor@bleqq.example")
        with stub_session(user_principal(permissions={perms.SOURCES_MANAGE}, subject_id=editor.id)):
            for name, method, url, body, _ in SESSION_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    status, code = self.REACHED_THE_LOGIC[name]
                    self.assertEqual(response.status_code, status, response.content)
                    self.assertEqual(response.json()["code"], code)

    def test_the_registry_reads_answer_an_empty_registry_with_200(self) -> None:
        """An empty answer is a 200 (playbook 4.4): a registry nobody has filled yet is not
        a missing resource."""
        with stub_session(user_principal(permissions={perms.WATCH_READ}, tenant_id=uuid.uuid4())):
            for name, url, _, _ in READ_ROUTES:
                with self.subTest(operation=name):
                    response = self.client.get(url, **AS_SESSION)
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual(response.json(), [])


# ---------------------------------------------------------------------------------------
# The tenant-facing and console reads (c5-contract-api-screens)
# ---------------------------------------------------------------------------------------
FEED = "/api/v1/changes"
CONSOLE_FEED = "/api/v1/console/changes"
CHANGE_READ = f"/api/v1/changes/{CHANGE}"
OBLIGATION_CHANGES = f"/api/v1/obligations/{OBLIGATION}/changes"

# (name, url, the one permission that opens it).
READ_ONLY_ROUTES = [
    ("listChanges", FEED, perms.WATCH_READ),
    ("getChange", CHANGE_READ, perms.WATCH_READ),
    ("listObligationChanges", OBLIGATION_CHANGES, perms.WATCH_READ),
    ("listConsoleChanges", CONSOLE_FEED, perms.PROPOSALS_REVIEW),
]
# All four are built (`c5-watch-feed-read`, `c5-watch-change-reads`) and answer real rows;
# what this file still guards is the gate in front of each, which is the same whatever the
# logic behind it does. What they answer is proved on real data in `tests_reading.py` and
# `tests_change_reads.py`.


class WatchReadGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        for name, url, _ in READ_ONLY_ROUTES:
            with self.subTest(operation=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_session_without_the_permission_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.CASES_READ}, tenant_id=uuid.uuid4())):
            for name, url, permission in READ_ONLY_ROUTES:
                with self.subTest(operation=name):
                    response = self.client.get(url, **AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], permission)

    def test_a_key_never_reads_a_banks_feed_or_the_console_queue(self) -> None:
        """Every one of these joins or serves a tenant's own case, which an agent's key has
        no business in: a key holding every scope there is still gets no session (NFR-01)."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, url, _ in READ_ONLY_ROUTES:
                with self.subTest(operation=name):
                    self.assertEqual(self.client.get(url, **AS_KEY).status_code, 401)

    def test_a_tenant_member_never_reaches_the_console_queue(self) -> None:
        """No tenant role holds proposals.review (PRO-01), so the console's list of changes
        is refused for a member holding every tenant permission there is."""
        with stub_session(user_principal(permissions=perms.TENANT_PERMISSIONS, tenant_id=uuid.uuid4())):
            response = self.client.get(CONSOLE_FEED, **AS_SESSION)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], perms.PROPOSALS_REVIEW)

    def test_the_console_session_never_reaches_a_banks_feed(self) -> None:
        """A library editor holds no tenant permission, so the feed — which is one bank's
        own cases — answers 403 rather than an empty list."""
        with stub_session(user_principal(permissions={perms.PROPOSALS_REVIEW})):
            response = self.client.get(FEED, **AS_SESSION)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], perms.WATCH_READ)

    def test_the_console_sources_page_reads_the_registry_with_sources_manage(self) -> None:
        """Ruling 3: the read-only console Sources page calls the registry reads, and a
        console session has no tenant and therefore no watch.read."""
        with stub_session(user_principal(permissions={perms.SOURCES_MANAGE})):
            for name, url, _, _ in READ_ROUTES:
                with self.subTest(operation=name):
                    self.assertEqual(self.client.get(url, **AS_SESSION).status_code, 200)

    def test_a_bad_filter_is_422_before_the_stub(self) -> None:
        cases = [
            ("listChanges", f"{FEED}?footprint=inside"),
            ("listChanges", f"{FEED}?tab=triage"),
            ("listChanges", f"{FEED}?status=retired"),
            ("listChanges", f"{FEED}?limit=101"),
            ("listChanges", f"{FEED}?limit=0"),
            ("listConsoleChanges", f"{CONSOLE_FEED}?confirmed=true"),
        ]
        with stub_session(user_principal(permissions={perms.WATCH_READ, perms.PROPOSALS_REVIEW}, tenant_id=uuid.uuid4())):
            for name, url in cases:
                with self.subTest(operation=name, url=url):
                    response = self.client.get(url, **AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_the_designed_in_footprint_pair_is_refused(self) -> None:
        """INPUT_DELTAS §7: `footprint` is one value (`in`, `all`, `watched`), so a client
        written against the designed `inFootprint` pair learns it at once instead of being
        silently given the default."""
        with stub_session(user_principal(permissions={perms.WATCH_READ}, tenant_id=uuid.uuid4())):
            response = self.client.get(f"{FEED}?inFootprint=true", **AS_SESSION)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_the_page_defaults_to_twenty_and_stops_at_a_hundred(self) -> None:
        from django.conf import settings

        self.assertEqual((settings.API_PAGE_SIZE_DEFAULT, settings.API_PAGE_SIZE_MAX), (20, 100))
        with stub_session(user_principal(permissions={perms.WATCH_READ}, tenant_id=uuid.uuid4())):
            at_the_cap = self.client.get(f"{FEED}?limit=100", **AS_SESSION)
        # The maximum itself is accepted: what refuses this stubbed session is its tenant,
        # which is an id no bank has. The page sizes themselves are proved on real rows in
        # `tests_reading.py`.
        self.assertNotEqual(at_the_cap.status_code, 422, "the maximum itself is accepted")
