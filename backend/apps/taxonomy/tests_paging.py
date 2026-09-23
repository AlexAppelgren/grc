"""Two lists that only grow are pages (NFR-02, FP-02, VOC-03): the regulatory scope's
request history, `GET /tenant/footprint/requests`, and a tenant list's suggestion inbox,
`GET /vocab/{list}/suggestions`. A decided request is never deleted, so a bank that has
decided scope changes for years has hundreds, and the inbox fills whenever an admin is
away.

Both take `PageQuery` like every other list (playbook 10): `limit` 20 by default and 100
at most, a larger one refused with a 422 rather than quietly trimmed, `offset` to walk on,
and `total` counting every row. Two reads agree on the order because it ends on the id,
so two rows written in the same instant never swap places between pages.

The query counts are pinned so an N+1 shows up as a number (playbook 10): a page of one
and a page of many cost the same. Each read also carries `Server-Timing: app` and stays
inside `API_BUDGET_MS` at a full page (NFR-S6 stays green per route).
"""

from __future__ import annotations

import datetime
import sys
import time
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.shared import factories
from apps.shared.audit import Actor, ActorType
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy import footprint_logic, terms_logic
from apps.taxonomy.models import FootprintChangeRequest, VocabularySuggestion
from apps.taxonomy.tests_scenarios import V1, _seed_library
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

# Queries per read, measured 2026-09-23. Every read starts with the ten the scenario tests
# count (tests_scenarios.py): the scenario client's audit count (1), the savepoint pair (2),
# the auth layer (6) and the caller's tenant (1). Then the read's own, which do not grow
# with the number of rows:
# - the request history: the caller's user for the label order (1); the page (1) and its
#   total (1); the terms every request on the page adds (1) and removes (1), their
#   dimensions (1) and their labels (1); and the waiting request's recount against today's
#   library, one request at most because the partial unique constraint lets only one wait
#   (4 in this fixture: the footprint, the restricting dimensions, the obligations' scopes
#   and their instruments).
FOOTPRINT_REQUESTS_QUERIES = 10 + 1 + 2 + 4 + 4
# - the suggestion inbox: the page with each suggester (1) and its total (1). A suggestion
#   carries its labels as typed, so no label order is read.
SUGGESTIONS_QUERIES = 10 + 2

REQUESTS = f"{V1}/tenant/footprint/requests"
SUGGESTIONS = f"{V1}/vocab/tenant_tag/suggestions"
# More than one default page, so the second page is real.
MORE_THAN_A_PAGE = settings.API_PAGE_SIZE_DEFAULT + 3


def _actor(user: Any) -> Actor:
    return Actor(kind=ActorType.USER, id=user.id, label=user.name)


class PagingFixture(ScenarioTestCase):
    def setUp(self) -> None:
        _seed_library()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.admin = factories.member(self.tenant, roles=("admin",), user_row=factories.user(name="Erik Holm")).user
        self.officer = factories.member(
            self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")
        ).user
        self.reader = factories.member(self.tenant, roles=("reader",), user_row=factories.user(name="Oskar Lund")).user

    def get(self, url: str, query: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.get(url, query, **headers)

    def assert_walks_in_a_stable_order(self, url: str, headers: dict[str, Any], stamp: str, newest_first: bool) -> list[str]:
        """Two pages hold every row once, and each row sits where the order puts it: by its
        timestamp, and by its id where two timestamps are equal."""
        first = self.get(url, {}, headers).json()
        second = self.get(url, {"offset": settings.API_PAGE_SIZE_DEFAULT}, headers).json()
        self.assertEqual((len(first["items"]), first["total"]), (settings.API_PAGE_SIZE_DEFAULT, MORE_THAN_A_PAGE))
        self.assertEqual((len(second["items"]), second["total"]), (MORE_THAN_A_PAGE - settings.API_PAGE_SIZE_DEFAULT, MORE_THAN_A_PAGE))
        rows = [(datetime.datetime.fromisoformat(row[stamp]), row["id"]) for row in first["items"] + second["items"]]
        ids = [row_id for _, row_id in rows]
        self.assertEqual(len(set(ids)), MORE_THAN_A_PAGE, "no row on both pages and none on neither")
        for (stamped, row_id), (next_stamped, next_id) in zip(rows, rows[1:], strict=False):
            if stamped == next_stamped:
                self.assertLess(row_id, next_id, "a tie is broken by the id")
            else:
                self.assertEqual(stamped > next_stamped, newest_first)
        return ids

    def assert_page_bounds(self, url: str, headers: dict[str, Any]) -> None:
        self.assertEqual(self.get(url, {"limit": settings.API_PAGE_SIZE_MAX}, headers).status_code, 200)
        for refused in ({"limit": settings.API_PAGE_SIZE_MAX + 1}, {"limit": 0}, {"offset": -1}):
            with self.subTest(query=refused):
                response = self.get(url, refused, headers)
                self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))
        past = self.get(url, {"offset": settings.API_PAGE_OFFSET_MAX}, headers)
        self.assertEqual(past.status_code, 200, "a page past the end is empty, never an error")
        self.assertEqual(past.json()["items"], [])
        self.assertEqual(past.json()["total"], self.get(url, {}, headers).json()["total"])

    def assert_inside_the_budget(self, url: str, headers: dict[str, Any]) -> None:
        response = self.get(url, {"limit": settings.API_PAGE_SIZE_MAX}, headers)
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        # CPU time on the request thread, the best of five, with coverage's tracer paused.
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.get(url, {"limit": settings.API_PAGE_SIZE_MAX}, headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)


class FootprintRequestHistoryPaging(PagingFixture):
    """`GET /tenant/footprint/requests`: every member reads what was asked and decided."""

    def setUp(self) -> None:
        super().setUp()
        self.advice = terms_logic.term_by_ref("service_type", "advice")
        self.retail = terms_logic.term_by_ref("client_category", "retail")
        footprint_logic.seed_terms(tenant=self.tenant, actor=Actor.system("test"), terms=[self.advice])

    def _requests(self, decided: int, *, waiting: bool = False) -> None:
        """`decided` requests, each withdrawn once sent, then one left waiting if asked: the
        partial unique constraint lets only one wait at a time.

        Then each is stamped by hand, because a clock that ticks every 15.6 ms (Windows) or
        every microsecond (Linux) would decide the order by chance: the decided ones two to a
        minute, a week ago, so every page walks through ties the id has to settle, and the
        waiting one a day later, so it is the newest by construction."""
        self.activate(self.tenant)
        sent: list[FootprintChangeRequest] = []
        for _ in range(decided):
            request = footprint_logic.create_request(
                tenant=self.tenant, requester=self.officer, actor=_actor(self.officer), adds=[self.retail], removes=[self.advice]
            )
            footprint_logic.withdraw(tenant=self.tenant, request=request, requester=self.officer, actor=_actor(self.officer))
            sent.append(request)
        week_ago = timezone.now() - datetime.timedelta(days=7)
        for n, request in enumerate(sent):
            FootprintChangeRequest.objects.filter(pk=request.pk).update(requested_at=week_ago + datetime.timedelta(minutes=n // 2))
        if waiting:
            request = footprint_logic.create_request(
                tenant=self.tenant, requester=self.officer, actor=_actor(self.officer), adds=[self.retail], removes=[self.advice]
            )
            FootprintChangeRequest.objects.filter(pk=request.pk).update(requested_at=week_ago + datetime.timedelta(days=1))

    def test_the_history_pages_newest_first_in_a_stable_order(self) -> None:
        self._requests(MORE_THAN_A_PAGE - 1, waiting=True)
        headers = sign_in(self.reader, tenant=self.tenant)
        self.assert_walks_in_a_stable_order(REQUESTS, headers, "requestedAt", newest_first=True)
        first = self.get(REQUESTS, {"limit": 1}, headers).json()["items"][0]
        self.assertEqual(first["status"], "pending", "the waiting request is the newest")
        self.assertEqual(([t["key"] for t in first["adds"]], [t["key"] for t in first["removes"]]), (["retail"], ["advice"]))
        self.assertEqual(first["preview"]["obligations"]["available"], True, "a waiting request is counted again on every read")

    def test_the_page_size_is_bounded(self) -> None:
        self._requests(1)
        self.assert_page_bounds(REQUESTS, sign_in(self.reader, tenant=self.tenant))

    def test_no_request_is_an_empty_page(self) -> None:
        response = self.get(REQUESTS, {}, sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((response.status_code, response.json()), (200, {"items": [], "total": 0}))

    def test_the_query_count_does_not_grow_with_the_page(self) -> None:
        self._requests(5, waiting=True)
        for limit in (1, 6):
            headers = sign_in(self.reader, tenant=self.tenant)
            with self.subTest(limit=limit), self.assertNumQueries(FOOTPRINT_REQUESTS_QUERIES):
                response = self.get(REQUESTS, {"limit": limit}, headers)
            self.assertEqual(len(response.json()["items"]), limit)
            self.assertTrue(all(row["adds"] and row["removes"] for row in response.json()["items"]))

    def test_a_full_page_stays_inside_the_budget(self) -> None:
        self._requests(MORE_THAN_A_PAGE - 1, waiting=True)
        self.assert_inside_the_budget(REQUESTS, sign_in(self.reader, tenant=self.tenant))


class SuggestionInboxPaging(PagingFixture):
    """`GET /vocab/{list}/suggestions`: the holders of vocab.manage read what members
    suggested for a tenant list, oldest first, because the inbox is worked in the order it
    filled."""

    def _suggestions(self, count: int) -> None:
        """`count` suggestions for the tags, stamped two to a minute over the past week so
        every page walks through ties the id has to settle (see `_requests` above)."""
        self.activate(self.tenant)
        week_ago = timezone.now() - datetime.timedelta(days=7)
        for n in range(count):
            suggestion = VocabularySuggestion.objects.create(
                tenant=self.tenant, list_name="tenant_tag", key=f"suggested-{n:03d}", labels={"en": f"Suggested {n}"}, suggested_by=self.reader
            )
            VocabularySuggestion.objects.filter(pk=suggestion.pk).update(created_at=week_ago + datetime.timedelta(minutes=n // 2))
        # Another list's suggestion is in another inbox.
        VocabularySuggestion.objects.create(tenant=self.tenant, list_name="effort_size", key="huge", labels={"en": "Huge"}, suggested_by=self.reader)

    def test_the_inbox_pages_oldest_first_in_a_stable_order(self) -> None:
        self._suggestions(MORE_THAN_A_PAGE)
        ids = self.assert_walks_in_a_stable_order(SUGGESTIONS, sign_in(self.admin, tenant=self.tenant), "createdAt", newest_first=False)
        self.activate(self.tenant)
        self.assertEqual(set(ids), {str(pk) for pk in VocabularySuggestion.objects.filter(list_name="tenant_tag").values_list("id", flat=True)})

    def test_the_page_size_is_bounded(self) -> None:
        self._suggestions(1)
        self.assert_page_bounds(SUGGESTIONS, sign_in(self.admin, tenant=self.tenant))

    def test_the_query_count_does_not_grow_with_the_page(self) -> None:
        self._suggestions(5)
        for limit in (1, 5):
            headers = sign_in(self.admin, tenant=self.tenant)
            with self.subTest(limit=limit), self.assertNumQueries(SUGGESTIONS_QUERIES):
                response = self.get(SUGGESTIONS, {"limit": limit}, headers)
            self.assertEqual(len(response.json()["items"]), limit)

    def test_a_full_page_stays_inside_the_budget(self) -> None:
        self._suggestions(settings.API_PAGE_SIZE_MAX)
        self.assert_inside_the_budget(SUGGESTIONS, sign_in(self.admin, tenant=self.tenant))

    def test_the_inbox_is_for_the_holders_of_vocab_manage(self) -> None:
        self.assertEqual(self.get(SUGGESTIONS, {}, sign_in(self.reader, tenant=self.tenant)).status_code, 403)
