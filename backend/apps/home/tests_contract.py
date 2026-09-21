"""Contract guard for the nine home operations: Today, the weekly briefing, the roadmap,
the public list of upcoming dates and the revocable calendar feed (HOM-01 to HOM-04;
chunk 6 `c6-home-api-contract`).

Each route was declared before the logic that serves it and answers 501 `not_built` from the
named function in the module that will build it, until that module lands (`BUILT_OPERATIONS`
below names the ones that have). What stands in front of the route is what this file proves,
whether or not its logic is there: no credential is 401, the wrong permission or scope is 403
naming what was needed, and a value the schema does not accept is 422 — so a client learns
what to send long before there is anything to send it to. Written before the routes existed
(2026-09-21): every case below answered 404 until `home/api.py` landed.

Three separations are pinned here because they are the ones a later change could quietly
lose:

- **A key reaches `GET /upcoming` and nothing else.** That list is library facts only, which
  is what makes an agent's key safe on it. Every other route in this app joins a bank's own
  case, briefing or subscriptions, so a key holding every scope there is still gets no
  session on them.
- **`GET /calendar/{feedToken}` reads no token while it is a stub.** It answers 501 for a
  token that looks real, for one that does not and for an empty-looking one alike, so nothing
  about any token can be learned from it before the feature ships.
- **`GET /home` is not a page-level 403.** It carries `roadmap.read`, which every system role
  holds, rather than an entry in `UNGATED_BY_DESIGN`; the panels a reader may not see are
  answered as null by `c6-home-backend`, not refused here.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase

from apps.shared import permissions as perms
from apps.shared.routes import iter_operations
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from config.api import api

FEED = "11111111-1111-4111-8111-111111111111"
WEEK = "2026-09-14"
# The right length (43 characters, what `secrets.token_urlsafe(32)` produces) built from two
# halves nobody could mistake for a credential. Written out as one literal it would be a
# random-looking string of exactly the shape a real key takes, and the secret scanner cannot
# tell those apart — a test that has to be allowlisted teaches the scanner to ignore the very
# shape it exists to catch. No token exists yet either way: the route reads none.
TOKEN = "feed-token-" + "x" * 32

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

HOME = "/api/v1/home"
CURRENT_BRIEFING = "/api/v1/briefings/current"
BRIEFING = f"/api/v1/briefings/{WEEK}"
ROADMAP = "/api/v1/roadmap"
UPCOMING = "/api/v1/upcoming"
FEEDS = "/api/v1/calendar-feeds"
ONE_FEED = f"/api/v1/calendar-feeds/{FEED}"
ICS = f"/api/v1/calendar/{TOKEN}"

FEED_BODY = {"filter": "regulatory"}

# Every operation this task declares: (operationId, method, url, body, the one permission a
# person needs). The ICS route is not here: it has no permission at all and is proved on its
# own below.
SESSION_ROUTES = [
    ("getHome", "get", HOME, None, perms.ROADMAP_READ),
    ("getCurrentBriefing", "get", CURRENT_BRIEFING, None, perms.WATCH_READ),
    ("getBriefing", "get", BRIEFING, None, perms.WATCH_READ),
    ("getRoadmap", "get", ROADMAP, None, perms.ROADMAP_READ),
    ("listUpcoming", "get", UPCOMING, None, perms.ROADMAP_READ),
    ("listCalendarFeeds", "get", FEEDS, None, perms.ROADMAP_READ),
    ("createCalendarFeed", "post", FEEDS, FEED_BODY, perms.ROADMAP_READ),
    ("revokeCalendarFeed", "delete", ONE_FEED, None, perms.ROADMAP_READ),
]
# Routes that join a bank's own rows, which an agent's key has no business in.
TENANT_ONLY_ROUTES = [
    ("getHome", "get", HOME, None),
    ("getCurrentBriefing", "get", CURRENT_BRIEFING, None),
    ("getBriefing", "get", BRIEFING, None),
    ("getRoadmap", "get", ROADMAP, None),
    ("listCalendarFeeds", "get", FEEDS, None),
    ("createCalendarFeed", "post", FEEDS, FEED_BODY),
    ("revokeCalendarFeed", "delete", ONE_FEED, None),
]
# The operations whose logic has landed, so they no longer answer 501. Their gates are
# proved here like every other route's; what they answer behind the gate is proved by the
# module that built them. One line per task, deleted from nowhere: the list only grows
# until it holds all nine and the stub half of this file goes with the last one.
BUILT_OPERATIONS = frozenset(
    {
        "getRoadmap",  # c6-roadmap-backend; behaviour in tests_roadmap.py
        "getHome",  # c6-home-backend; behaviour in tests_home.py
        "listUpcoming",  # c6-upcoming-calendar-backend; behaviour in tests_calendar.py
        "getCurrentBriefing",  # c6-briefing-backend; behaviour in tests_briefing.py
        "getBriefing",  # c6-briefing-backend; behaviour in tests_briefing.py
    }
)
DECLARED_OPERATIONS = {
    ("GET", "/home"): "getHome",
    ("GET", "/briefings/current"): "getCurrentBriefing",
    ("GET", "/briefings/{week_start}"): "getBriefing",
    ("GET", "/roadmap"): "getRoadmap",
    ("GET", "/upcoming"): "listUpcoming",
    ("GET", "/calendar-feeds"): "listCalendarFeeds",
    ("POST", "/calendar-feeds"): "createCalendarFeed",
    ("DELETE", "/calendar-feeds/{feed_id}"): "revokeCalendarFeed",
    ("GET", "/calendar/{feed_token}"): "getCalendarIcs",
}


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class HomeRouteRegistration(TestCase):
    def test_the_nine_operations_are_registered_with_the_ids_the_screens_call(self) -> None:
        """The operation ids are the contract's own names, which the generated TypeScript
        client and every screen key on; renaming one silently is how a screen loses its
        call."""
        registered = {(op.method, op.path): op.operation_id for op in iter_operations(api)}
        for key, operation_id in DECLARED_OPERATIONS.items():
            with self.subTest(route=key):
                self.assertEqual(registered.get(key), operation_id)


class HomeRouteGates(TestCase):
    def test_no_credential_is_401(self) -> None:
        for name, method, url, body, _ in SESSION_ROUTES:
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_a_session_without_the_permission_is_403_naming_it(self) -> None:
        with stub_session(user_principal(permissions={perms.CASES_READ}, tenant_id=uuid.uuid4())):
            for name, method, url, body, permission in SESSION_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    problem = response.json()
                    self.assertEqual(problem["code"], "permission_denied")
                    self.assertEqual(problem["requiredPermission"], permission)

    def test_home_is_refused_by_permission_and_never_left_ungated(self) -> None:
        """`GET /home` carries `roadmap.read` rather than an entry in the ungated allowlist,
        so the refusal names a permission an admin can grant (chunk 6 defaults)."""
        from apps.shared.permissions import UNGATED_BY_DESIGN

        self.assertNotIn(("GET", "/home"), UNGATED_BY_DESIGN)
        with stub_session(user_principal(permissions=set(), tenant_id=uuid.uuid4())):
            response = self.client.get(HOME, **AS_SESSION)
        self.assertEqual(response.json()["requiredPermission"], perms.ROADMAP_READ)

    def test_a_key_without_upcoming_read_is_403_naming_the_scope(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_LIBRARY_READ})):
            response = self.client.get(UPCOMING, **AS_KEY)
        self.assertEqual(response.status_code, 403)
        problem = response.json()
        self.assertEqual(problem["code"], "permission_denied")
        self.assertEqual(problem["requiredPermission"], perms.SCOPE_UPCOMING_READ)

    def test_a_key_reaches_upcoming_and_nothing_else_in_this_app(self) -> None:
        """Every other route here joins a bank's own case, briefing or subscriptions, so a
        key holding every scope there is still gets no session on them (NFR-01)."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES)):
            for name, method, url, body in TENANT_ONLY_ROUTES:
                with self.subTest(operation=name):
                    self.assertEqual(_call(self.client, method, url, body, AS_KEY).status_code, 401)

    def test_a_console_session_never_reaches_a_banks_home_or_briefing(self) -> None:
        """A library editor holds no tenant permission and belongs to no bank, so these
        answer 403 rather than an empty page of somebody's data."""
        with stub_session(user_principal(permissions={perms.PROPOSALS_REVIEW})):
            for name, method, url, body, permission in SESSION_ROUTES:
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["requiredPermission"], permission)

    def test_a_bad_filter_or_body_is_422_before_the_stub(self) -> None:
        cases = [
            ("getRoadmap", "get", f"{ROADMAP}?kind=ours", None),
            ("getRoadmap", "get", f"{ROADMAP}?from=last-week", None),
            ("getBriefing", "get", "/api/v1/briefings/this-week", None),
            ("listUpcoming", "get", f"{UPCOMING}?limit=101", None),
            ("listUpcoming", "get", f"{UPCOMING}?limit=0", None),
            ("createCalendarFeed", "post", FEEDS, {"filter": "everything"}),
            ("createCalendarFeed", "post", FEEDS, {**FEED_BODY, "tone": "brand"}),
            ("revokeCalendarFeed", "delete", "/api/v1/calendar-feeds/not-a-uuid", None),
        ]
        with stub_session(
            user_principal(permissions={perms.ROADMAP_READ, perms.WATCH_READ}, tenant_id=uuid.uuid4())
        ):
            for name, method, url, body in cases:
                with self.subTest(operation=name, url=url, body=body):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_the_upcoming_page_defaults_to_twenty_and_stops_at_a_hundred(self) -> None:
        from django.conf import settings

        self.assertEqual((settings.API_PAGE_SIZE_DEFAULT, settings.API_PAGE_SIZE_MAX), (20, 100))
        with stub_session(user_principal(permissions={perms.ROADMAP_READ}, tenant_id=uuid.uuid4())):
            at_the_cap = self.client.get(f"{UPCOMING}?limit=100", **AS_SESSION)
        self.assertEqual(at_the_cap.status_code, 200, "the maximum itself is accepted rather than refused")

    def test_current_is_matched_as_itself_and_not_parsed_as_a_week(self) -> None:
        """`/briefings/current` is registered before `/briefings/{weekStart}`, so the word is
        matched as itself. Each reaches a different function, which the two stubs' details
        prove: routing them to one would make the running week unreachable the moment the
        snapshot read starts answering 404 for a week nobody was sent."""
        with stub_session(user_principal(permissions={perms.WATCH_READ}, tenant_id=uuid.uuid4())):
            current = self.client.get(CURRENT_BRIEFING, **AS_SESSION)
            not_a_week = self.client.get("/api/v1/briefings/this-week", **AS_SESSION)
        # A path segment the date parser refuses answers 422; `current` never does, because
        # it is matched by the route registered before the dated one and is never parsed.
        self.assertEqual(not_a_week.status_code, 422)
        self.assertNotEqual(current.status_code, 422)
        # Both stop at the caller's bank here, which is the gate in front of either read;
        # that the two reach different functions is proved in `tests_briefing.py`, where a
        # real bank gets a running week from one and a 404 for an unsent week from the other.
        self.assertEqual(current.status_code, 404)


class HomeRouteStubs(TestCase):
    def assert_not_built(self, response: Any) -> None:
        self.assertEqual(response.status_code, 501)
        problem = response.json()
        self.assertEqual(problem["code"], "not_built")
        self.assertEqual(response.headers["Content-Type"], "application/problem+json")
        self.assertNotIn("traceback", response.content.decode().lower())

    def test_a_session_with_its_permission_reaches_the_stub(self) -> None:
        permissions = {perms.ROADMAP_READ, perms.WATCH_READ}
        with stub_session(user_principal(permissions=permissions, tenant_id=uuid.uuid4())):
            for name, method, url, body, _ in SESSION_ROUTES:
                if name in BUILT_OPERATIONS:
                    continue
                with self.subTest(operation=name):
                    self.assert_not_built(_call(self.client, method, url, body, AS_SESSION))

    def test_a_key_with_upcoming_read_reaches_the_list(self) -> None:
        """The scope is the whole of the gate: a key holding it reads the public list, and
        what it gets back is proved in `tests_calendar.py`."""
        with stub_api_key(agent_principal(scopes={perms.SCOPE_UPCOMING_READ})):
            self.assertEqual(self.client.get(UPCOMING, **AS_KEY).status_code, 200)

    def test_the_ics_route_answers_the_same_501_for_every_token_and_reads_none(self) -> None:
        """The token is the credential, so the route must say nothing about any token while
        it is a stub: a well-formed one, a nonsense one and a repeated call all answer
        identically, with no session and no key anywhere in the request."""
        bodies = set()
        for token in (TOKEN, "not-a-token", "x", TOKEN):
            with self.subTest(token=token[:8]):
                response = self.client.get(f"/api/v1/calendar/{token}")
                self.assert_not_built(response)
                bodies.add(response.content)
        self.assertEqual(len(bodies), 1, "the ICS route answered two different bodies; a token could be probed")

    def test_coming_up_is_the_roadmaps_own_function_and_not_a_second_query(self) -> None:
        """Ruling 5: `c6-home-backend` builds Today's "Coming up" by calling the roadmap
        module, so the panel and the page can never answer different rows.

        While the roadmap was a stub this pinned that `coming_up()` refused the same way.
        Now that `c6-roadmap-backend` has built it, the stronger proof lives where the rows
        are — `tests_roadmap.py` calls both functions on one bank and demands the same first
        items — and what is left here is the structural half: the function is in the roadmap
        module and takes the roadmap's own arguments, so a later task cannot answer Today
        from a query of its own.
        """
        import inspect

        from apps.home import roadmap

        self.assertEqual(
            list(inspect.signature(roadmap.coming_up).parameters), ["tenant", "order", "limit"]
        )

    def test_a_token_longer_than_the_limit_is_422_before_the_stub(self) -> None:
        from apps.home.schemas import FEED_TOKEN_MAX

        response = self.client.get(f"/api/v1/calendar/{'a' * (FEED_TOKEN_MAX + 1)}")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")
