"""The calendar subscription (HOM-04, D-52, ADR 0045): an address whose token is the whole
credential, so what is proved here is everything that stands in place of a sign-in.

- **Shown once.** The address comes back from the create call and appears nowhere else —
  not in the list read, not in an audit row, not in a log line. The log half is proved by
  capturing the handler and formatting with the formatter production uses, rather than by
  assuming what a line would hold; D-52 put the token in the query string on exactly that
  claim.
- **One refusal.** Unknown, malformed, revoked, expired and wrong-secret tokens all leave
  by one 404 with one body, so no address ever says whether it existed.
- **A public document.** The events are selected by this bank's roadmap — its regulatory
  dates stated to the day, each keyed by the change's stable key — and say only what the
  library holds, pinned by asserting the property names emitted against a set, so a field
  added to a roadmap item later fails here instead of reaching a phone.
- **Stopped by the server.** The four rules that end a subscription are read on the
  fetch, and the idle one on the list and the cap as well; each one revokes the row and
  records a system actor doing it.
- **One person, one cap.** Two subscribe calls at once cannot both mint the last address.

`tests_calendar.py` holds the other half of HOM-04, the public list, because
`apps/home/calendar.py` holds the code for it. The clock is frozen at a fixed instant for
the whole of every test, sessions and calls alike, and every date is written out (playbook
8.3): a session minted at the frozen instant and a call made on the real clock would stop
agreeing the moment the real clock passed it.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import itertools
import logging
import uuid
from collections.abc import Iterator
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, OperationalError, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.home import feed as feed_logic
from apps.home import roadmap
from apps.home.models import TOKEN_PREFIX_LENGTH, CalendarFeed
from apps.home.schemas import HomeRoadmapQuery
from apps.identity import invitation_logic, passkey_logic
from apps.identity.models import LoginEvent, LoginEventKind, Membership, TenantRole, User
from apps.library.models import DatePrecision
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import ActorType
from apps.shared.logging import JsonFormatter
from apps.shared.models import AuditEvent, Tenant
from apps.shared.routes import iter_operations
from apps.shared.testing import sign_in, user_principal
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange
from apps.watch.write import watch_write
from config.api import api

# Distinct slugs, because each fixture below builds its own bank.
_slugs = itertools.count(1)

# The instant everything here is frozen at, and the dates around it. The server reads in
# UTC, where this instant is still 30 September.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
SOON = datetime.date(2026, 10, 15)
LATER = datetime.date(2027, 1, 20)


def a_change(
    *, title: str, key_date: datetime.date, precision: DatePrecision = DatePrecision.DAY
) -> RegulatoryChange:
    change = watch_build.change(title=title, key_date=key_date, key_date_label="In force")
    if precision is not DatePrecision.DAY:
        with watch_write("test: a key date stated less exactly than to the day"):
            RegulatoryChange.objects.filter(pk=change.pk).update(key_date_precision=precision.value)
        change.refresh_from_db()
    return change


def frozen_at(moment: datetime.datetime) -> Any:
    return mock.patch("django.utils.timezone.now", return_value=moment)


# Every property name a calendar document may hold, and no other.
DOCUMENT_PROPERTIES = {"BEGIN", "END", "VERSION", "PRODID", "UID", "DTSTAMP", "DTSTART", "SUMMARY", "DESCRIPTION", "URL"}


def property_names(body: str) -> set[str]:
    """The name of every content line, a folded line's continuation not being one."""
    return {line.split(":", 1)[0].split(";", 1)[0] for line in body.split("\r\n") if line and not line.startswith(" ")}


FEEDS = "/api/v1/calendar-feeds"
ICS = "/api/v1/calendar/feed.ics"
# The bank's own judgement, seeded on the case behind every date below. Nothing in this
# file may find it in an address, a list, an audit row, a log line or the document itself.
SO_WHAT = "Three regulations change for us and research budgets move."
# A month after the instant everything here is frozen at: past the 30-day idle expiry.
LONG_AGO = INSTANT - datetime.timedelta(days=40)
# A re-enrolment a minute after the subscription, and a fetch after that.
AFTER_ENROLMENT = INSTANT + datetime.timedelta(minutes=1)
LATER_THAT_NIGHT = INSTANT + datetime.timedelta(minutes=5)
# The loggers the settings give handlers of their own. A root handler alone would miss
# them, because each one is configured `propagate: False`.
LOGGERS = ("", "django", "django.request", "apps")


@contextlib.contextmanager
def captured_logs() -> Iterator[list[str]]:
    """Every line every logger writes inside the block, formatted by the formatter
    production uses, so what is asserted is what would be written down."""
    written: list[str] = []
    formatter = JsonFormatter()

    class Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            written.append(formatter.format(record))

    sink = Sink(level=logging.NOTSET)
    restore = []
    for name in LOGGERS:
        logger = logging.getLogger(name)
        restore.append((logger, logger.level))
        logger.addHandler(sink)
        logger.setLevel(logging.DEBUG)
    try:
        yield written
    finally:
        for logger, level in restore:
            logger.removeHandler(sink)
            logger.setLevel(level)


def a_dated_case(
    tenant: Tenant, *, title: str, key_date: datetime.date, precision: DatePrecision = DatePrecision.DAY
) -> RegulatoryChange:
    """One reform with a date, and this bank's own open case on it carrying a judgement."""
    change = a_change(title=title, key_date=key_date, precision=precision)
    cases_build.case(tenant, change, so_what_text=SO_WHAT)
    return change


class FeedFixture(TestCase):
    """One bank, one member with `roadmap.read`, one dated reform it has open work on."""

    tenant: Tenant
    member: Membership
    reader: User
    change: RegulatoryChange

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug=f"feed-{next(_slugs)}", timezone="Europe/Stockholm")
        cls.member = factories.member(cls.tenant, roles=("reader",))
        cls.reader = cls.member.user
        cls.change = a_dated_case(cls.tenant, title="Research payments", key_date=SOON)

    def setUp(self) -> None:
        # One frozen clock for the whole test, so a session minted at the instant and every
        # call made with it agree about how old it is whatever day the suite runs on. A call
        # that needs another moment nests its own patch inside this one.
        frozen = frozen_at(INSTANT)
        frozen.start()
        self.addCleanup(frozen.stop)

    def headers(self, user: User | None = None) -> dict[str, Any]:
        """A session minted at the frozen instant, so it is young enough to mint an address
        (D-52: a recent sign-in or a fresh passkey assertion)."""
        return sign_in(user or self.reader, tenant=self.tenant)

    def subscribe(self, headers: dict[str, Any] | None = None) -> Any:
        return self.client.post(FEEDS, data={}, content_type="application/json", **(headers or self.headers()))

    def token_of(self, response: Any) -> str:
        return parse_qs(urlsplit(response.json()["url"]).query)["token"][0]

    def fetch(self, token: str, *, at: datetime.datetime = INSTANT) -> Any:
        with frozen_at(at):
            return self.client.get(ICS, {"token": token})

    def stopped_by_the_server(self) -> dict[uuid.UUID | None, str]:
        """Every revocation the server made itself, as the row it stopped and the sentence
        its audit row carries."""
        return {
            row.subject_id: row.summary
            for row in AuditEvent.objects.filter(action="calendar_feed.revoked", actor_type=ActorType.SYSTEM.value)
        }

    def own_rows(self) -> Any:
        tenancy.activate(self.tenant.id)
        return CalendarFeed.objects.filter(tenant=self.tenant)


class MintingAnAddress(FeedFixture):
    """`POST /calendar-feeds`: shown once, capped, audited, and never echoed again."""

    def test_the_address_is_the_route_that_is_registered_with_the_token_in_its_query(self) -> None:
        """The address is built here and served there; if the route moves and this string
        does not, every subscription a bank made stops working silently. Read off the
        operations Ninja registered rather than off a second copy of the path."""
        registered = {op.path for op in iter_operations(api) if op.operation_id == "getCalendarIcs"}
        self.assertEqual(registered, {"/calendar/feed.ics"})
        created = self.subscribe()
        self.assertEqual(created.status_code, 201)
        address = urlsplit(created.json()["url"])
        self.assertEqual(address.path, feed_logic.ICS_PATH)
        self.assertEqual(list(parse_qs(address.query)), ["token"])

    def test_the_token_is_a_prefix_and_a_secret_and_only_its_hash_is_stored(self) -> None:
        token = self.token_of(self.subscribe())
        prefix, _, secret = token.partition(".")
        feed = self.own_rows().get()
        self.assertEqual(feed.token_prefix, prefix)
        self.assertEqual(len(prefix), TOKEN_PREFIX_LENGTH)
        self.assertEqual(feed.token_hash, hashlib.sha256(secret.encode()).hexdigest())
        self.assertNotIn(secret, feed.token_hash, "the secret itself must not be in the row")
        self.assertGreaterEqual(len(secret), 40, "256 bits, urlsafe-encoded (D-52)")

    def test_the_address_appears_in_the_create_answer_and_in_nothing_else(self) -> None:
        """Shown once. The list read afterwards carries the subscription and no piece of
        the address, so losing it means revoking and subscribing again."""
        created = self.subscribe()
        token = self.token_of(created)
        prefix = token.partition(".")[0]
        listed = self.client.get(FEEDS, **self.headers())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(set(listed.json()[0]), {"id", "createdAt", "lastUsedAt", "revokedAt"})
        for half in (token, prefix):
            with self.subTest(half=half[:6]):
                self.assertNotIn(half, listed.content.decode())

    def test_a_sixth_subscription_is_refused_by_its_own_code_and_revoking_one_makes_room(self) -> None:
        headers = self.headers()
        for _ in range(settings.CALENDAR_FEEDS_PER_USER):
            self.assertEqual(self.subscribe(headers).status_code, 201)
        refused = self.subscribe(headers)
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["code"], "feed_limit_reached")
        self.assertIn(str(settings.CALENDAR_FEEDS_PER_USER), refused.json()["detail"])

        spare = self.own_rows().first()
        assert spare is not None
        self.assertEqual(self.client.delete(f"{FEEDS}/{spare.id}", **headers).status_code, 204)
        self.assertEqual(self.subscribe(headers).status_code, 201)

    def test_creating_and_revoking_each_write_one_audit_row_that_names_no_address(self) -> None:
        headers = self.headers()
        token = self.token_of(self.subscribe(headers))
        feed = self.own_rows().get()
        self.client.delete(f"{FEEDS}/{feed.id}", **headers)
        rows = list(AuditEvent.objects.filter(subject_type="calendar_feed"))
        # As a set: both rows are written in one test and an audit event's id is a random
        # uuid, so their order is not a fact to assert (playbook 4.5).
        self.assertEqual({row.action for row in rows}, {"calendar_feed.created", "calendar_feed.revoked"})
        self.assertEqual(len(rows), 2, "one row each, never two for one call")
        for row in rows:
            with self.subTest(action=row.action):
                self.assertEqual(row.tenant_id, self.tenant.id)
                self.assertEqual(row.subject_id, feed.id)
                self.assertEqual(row.actor_type, ActorType.USER.value)
                written = f"{row.summary} {row.subject_title} {row.before} {row.after}"
                self.assertNotIn(token, written)
                self.assertNotIn(feed.token_prefix, written)
                self.assertNotIn(feed.token_hash, written)

    def test_revoking_stamps_the_row_and_a_second_revoke_answers_the_same(self) -> None:
        headers = self.headers()
        self.subscribe(headers)
        feed = self.own_rows().get()
        self.assertEqual(self.client.delete(f"{FEEDS}/{feed.id}", **headers).status_code, 204)
        feed.refresh_from_db()
        self.assertIsNotNone(feed.revoked_at)
        stopped_at = feed.revoked_at
        self.assertEqual(self.client.delete(f"{FEEDS}/{feed.id}", **headers).status_code, 204)
        feed.refresh_from_db()
        self.assertEqual(feed.revoked_at, stopped_at, "the date it stopped is not moved by a retry")

    def test_another_persons_subscription_is_neither_listed_nor_revocable(self) -> None:
        """Answered 404 and never 403, so no id can be probed for what somebody else holds."""
        self.subscribe()
        mine = self.own_rows().get()
        colleague = factories.member_user(self.tenant, roles=("reader",))
        theirs = self.headers(colleague)
        self.assertEqual(self.client.get(FEEDS, **theirs).json(), [])
        refused = self.client.delete(f"{FEEDS}/{mine.id}", **theirs)
        self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))


class TheIdleRuleOnTheListAndTheCap(FeedFixture):
    """ADR 0045's idle expiry, read where a person looks as well as where a client fetches.
    A subscription nobody fetched for a month works for nobody, so it is stopped the moment
    its owner lists or adds subscriptions — never counted against the cap, never shown as
    live — and stopped the way a fetch stops it: a system actor, audited, in that request's
    transaction."""

    def age(self, feed_ids: list[uuid.UUID]) -> None:
        self.own_rows().filter(pk__in=feed_ids).update(created_at=LONG_AGO, last_used_at=None)

    def test_listing_stops_a_subscription_gone_idle_and_says_which_rule_did(self) -> None:
        headers = self.headers()
        idle = self.subscribe(headers).json()["feed"]["id"]
        in_use = self.subscribe(headers).json()["feed"]["id"]
        self.age([uuid.UUID(idle)])

        listed = {row["id"]: row for row in self.client.get(FEEDS, **headers).json()}

        self.assertIsNotNone(listed[idle]["revokedAt"], "an idle subscription is not listed as working")
        self.assertIsNone(listed[in_use]["revokedAt"])
        self.assertEqual(set(self.stopped_by_the_server()), {uuid.UUID(idle)})
        self.assertIn(f"{settings.CALENDAR_FEED_IDLE_DAYS} days", self.stopped_by_the_server()[uuid.UUID(idle)])

    def test_a_list_with_nothing_gone_idle_writes_nothing(self) -> None:
        headers = self.headers()
        self.subscribe(headers)
        audited = AuditEvent.objects.count()
        self.assertEqual(self.client.get(FEEDS, **headers).status_code, 200)
        self.assertEqual(AuditEvent.objects.count(), audited, "a read that stopped nothing is not a decision")

    def test_idle_subscriptions_are_stopped_rather_than_counted_against_the_cap(self) -> None:
        """A person whose every address went quiet on replaced devices must not be told they
        hold too many: none of them works."""
        headers = self.headers()
        for _ in range(settings.CALENDAR_FEEDS_PER_USER):
            self.assertEqual(self.subscribe(headers).status_code, 201)
        idle = list(self.own_rows().values_list("pk", flat=True))
        self.age(idle)

        created = self.subscribe(headers)

        self.assertEqual(created.status_code, 201)
        self.assertEqual(set(self.stopped_by_the_server()), set(idle))
        self.assertEqual(
            list(self.own_rows().filter(revoked_at__isnull=True).values_list("pk", flat=True)),
            [uuid.UUID(created.json()["feed"]["id"])],
        )

    def test_two_reads_that_find_one_idle_subscription_stop_it_once(self) -> None:
        """Two tabs on the account page, or a list while a calendar client polls, can both read
        the row as working before either of them writes. The one that writes second finds it
        stopped already and leaves it alone: the date it stopped does not move, and the audit
        trail holds one row for one stop, not two claiming the row was working before each."""
        headers = self.headers()
        self.subscribe(headers)
        self.age(list(self.own_rows().values_list("pk", flat=True)))
        as_the_second_read_it = self.own_rows().get()
        self.assertEqual(self.client.get(FEEDS, **headers).status_code, 200)
        stopped_at = self.own_rows().get().revoked_at
        self.assertIsNotNone(stopped_at)

        a_moment_later = INSTANT + datetime.timedelta(seconds=1)
        with frozen_at(a_moment_later):
            feed_logic._revoke_automatically(as_the_second_read_it, a_moment_later, feed_logic._idle_summary())

        self.assertEqual(self.own_rows().get().revoked_at, stopped_at, "the date it stopped moved")
        self.assertEqual(AuditEvent.objects.filter(action="calendar_feed.revoked").count(), 1)

    @override_settings(CALENDAR_FEED_REVOKED_SHOWN=2)
    def test_the_list_holds_what_works_and_only_the_most_recently_stopped(self) -> None:
        """Bounded by design rather than paged: what works is capped, and of what was
        stopped only the most recent `CALENDAR_FEED_REVOKED_SHOWN` are shown, so a person
        who has replaced addresses for years still reads one short list. Same shape and same
        order as ever: newest first."""
        headers = self.headers()
        for _ in range(4):
            self.subscribe(headers)
        live, *stopped = list(self.own_rows())
        for hours_ago, feed in enumerate(stopped, start=1):
            self.own_rows().filter(pk=feed.pk).update(revoked_at=INSTANT - datetime.timedelta(hours=hours_ago))
        oldest_stop = stopped[-1]

        listed = self.client.get(FEEDS, **headers).json()

        shown = [feed.id for feed in self.own_rows() if feed.id != oldest_stop.id]
        self.assertEqual([uuid.UUID(row["id"]) for row in listed], shown)
        self.assertIn(live.id, shown, "a subscription that works is always listed")
        for row in listed:
            with self.subTest(row=row["id"]):
                self.assertEqual(set(row), {"id", "createdAt", "lastUsedAt", "revokedAt"})


class TheCapHoldsUnderConcurrency(TransactionTestCase):
    """Two subscribe calls at once must not both count four and both mint a fifth. The
    lock is the caller's membership row: it exists for every caller, where their live rows
    may be none, and a count over live rows never sees the row a concurrent call is
    inserting. Proved with two connections rather than two threads: the application role
    holds the lock a first call holds, and a second call is shown to wait for it."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        # A TransactionTestCase does not wrap the test in a transaction, and the reference
        # seeds audit every row they write, so record() needs one opened here.
        with transaction.atomic():
            watch_build.seed_watch_reference()
        self.tenant = factories.tenant(slug=f"feed-lock-{uuid.uuid4().hex[:8]}")
        self.member = factories.member(self.tenant, roles=("reader",))

    def subscribe(self) -> None:
        tenancy.activate(self.tenant.id)
        feed_logic.create_feed(
            tenant=self.tenant,
            user=self.member.user,
            actor=factories.user_actor(user_id=self.member.user.id),
            request=RequestFactory().post(FEEDS),
        )

    def test_a_second_subscribe_waits_for_the_first(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant.id, using="app")
            Membership.objects.using("app").select_for_update().get(pk=self.member.pk)
            with self.assertRaisesMessage(OperationalError, "lock timeout"), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '200ms'")
                self.subscribe()
        with transaction.atomic():
            self.subscribe()
            self.assertEqual(CalendarFeed.objects.filter(tenant=self.tenant).count(), 1, "the waiting call wrote nothing")


class FetchingTheCalendar(FeedFixture):
    """`GET /calendar/feed.ics`: what the document says, and what one refusal hides."""

    def live_token(self) -> str:
        return self.token_of(self.subscribe())

    def test_a_live_address_serves_the_roadmap_as_icalendar(self) -> None:
        response = self.fetch(self.live_token())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/calendar; charset=utf-8")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        body = response.content.decode()
        self.assertTrue(body.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(body.endswith("END:VCALENDAR\r\n"))
        self.assertIn("SUMMARY:In force: Research payments\r\n", body)
        self.assertIn("DTSTART;VALUE=DATE:20261015\r\n", body)

    def test_an_event_carries_the_librarys_facts_and_no_judgement_of_the_banks(self) -> None:
        """The guard ADR 0045 asks for. The property names are asserted as a set, so a field
        added to a roadmap item later fails here instead of reaching a phone."""
        body = self.fetch(self.live_token()).content.decode()
        self.assertEqual(property_names(body), DOCUMENT_PROPERTIES)
        for judgement in (SO_WHAT, self.tenant.name, "act_now", "urgency", "owner", "new"):
            with self.subTest(judgement=judgement):
                self.assertNotIn(judgement, body)

    def test_an_events_uid_is_the_changes_stable_key_and_never_the_banks_case(self) -> None:
        """ADR 0045: the stable key is the UID. It never changes, so a client updates the
        event when a date moves instead of showing it twice, and it is the library's, so it
        names nothing of the bank's — a case id is this bank's own row and has no business
        on a phone."""
        body = self.fetch(self.live_token()).content.decode()
        domain = urlsplit(settings.APP_BASE_URL).hostname
        self.assertIn(f"\r\nUID:{self.change.stable_key}@{domain}\r\n", body)
        tenancy.activate(self.tenant.id)
        case = ChangeCase.objects.get(change=self.change)
        self.assertNotIn(str(case.id), body)

    def test_a_stable_key_that_is_not_a_slug_adds_no_line_to_anyones_calendar(self) -> None:
        """An agent that reads untrusted pages chooses the stable key, and the watch door
        refuses one that is not a slug. The calendar does not lean on that alone: a key with
        a line break, a comma and a semicolon in it is escaped like every other text value,
        so it can never end the UID and begin a property of its own on the phone of every
        member of every bank whose roadmap holds the change."""
        crafted = watch_build.change(
            stable_key="chg-x\r\nATTACH:https://evil.example/\r\nX-INJECTED:1,2;3",
            title="Rules on outsourcing",
            key_date=SOON,
        )
        cases_build.case(self.tenant, crafted, so_what_text=SO_WHAT)

        body = self.fetch(self.live_token()).content.decode()

        self.assertEqual(property_names(body), DOCUMENT_PROPERTIES, "the key began a property of its own")
        domain = urlsplit(settings.APP_BASE_URL).hostname
        self.assertIn(
            f"\r\nUID:chg-x\\nATTACH:https://evil.example/\\nX-INJECTED:1\\,2\\;3@{domain}\r\n",
            body.replace("\r\n ", ""),
        )

    def test_a_date_the_source_gave_as_a_quarter_stays_off_the_calendar(self) -> None:
        """ADR 0045: day precision only. An all-day event is one day, and a date published
        as "Q1 2027" pinned to 1 January would state a day nobody published. The roadmap page
        keeps it; the calendar leaves it out."""
        quarter = a_dated_case(
            self.tenant, title="Amended reporting of securities financing", key_date=LATER, precision=DatePrecision.QUARTER
        )
        body = self.fetch(self.live_token()).content.decode()
        self.assertNotIn(quarter.title, body)
        self.assertNotIn(quarter.stable_key, body)
        self.assertIn(f"SUMMARY:In force: {self.change.title}\r\n", body, "a date stated to the day still is")
        on_the_roadmap = [item["title"] for item in self.client.get("/api/v1/roadmap", **self.headers()).json()["items"]]
        self.assertIn(quarter.title, on_the_roadmap)

    def test_the_calendar_is_the_roadmaps_regulatory_items_stated_to_the_day(self) -> None:
        """Only the dates the outside world set reach a calendar, never the bank's own
        (AC-TEN1). The calendar's rows are the roadmap's `kind=regulatory` rows, in the
        roadmap's order, less the ones not stated to the day — so when the bank's own
        deadlines join the roadmap, nothing here can carry one out."""
        a_dated_case(self.tenant, title="Transition ends for research payments", key_date=LATER)
        a_dated_case(self.tenant, title="Guidance on outsourcing", key_date=LATER, precision=DatePrecision.MONTH)
        tenancy.activate(self.tenant.id)
        order = ["en"]

        on_the_calendar = roadmap.calendar_items(self.tenant, order)

        regulatory = roadmap.roadmap_items(self.tenant, order, HomeRoadmapQuery(kind="regulatory")).items
        stated_to_the_day = set(
            RegulatoryChange.objects.filter(key_date_precision=DatePrecision.DAY.value).values_list("pk", flat=True)
        )
        self.assertEqual(
            [item.id for _, item in on_the_calendar],
            [item.id for item in regulatory if item.change_id in stated_to_the_day],
        )
        self.assertEqual(
            [item.title for _, item in on_the_calendar],
            [self.change.title, "Transition ends for research payments"],
            "the month-precision date is the one left out",
        )
        self.assertEqual({(item.kind, item.item_type) for _, item in on_the_calendar}, {("regulatory", "change_date")})
        self.assertEqual(
            [RegulatoryChange.objects.get(stable_key=key).pk for key, _ in on_the_calendar],
            [item.change_id for _, item in on_the_calendar],
            "each item beside its own change's stable key",
        )

    def test_a_long_title_is_folded_rather_than_written_as_one_long_line(self) -> None:
        """RFC 5545 §3.1: a client that follows the standard reads an unfolded line as a
        broken one, and regulatory titles are regularly longer than 75 octets."""
        a_dated_case(
            self.tenant,
            title="FI adopts amended rules on paying for investment research and on reporting it",
            key_date=SOON,
        )
        body = self.fetch(self.live_token()).content.decode()
        self.assertIn("\r\n ", body, "no line was continued")
        for line in body.split("\r\n"):
            with self.subTest(line=line[:30]):
                self.assertLessEqual(len(line.encode()), feed_logic.FOLD_OCTETS)

    def test_a_comma_or_a_semicolon_in_a_title_is_escaped_rather_than_splitting_a_line(self) -> None:
        """RFC 5545 §3.3.11. A regulatory title regularly carries both, and an unescaped one
        would turn the rest of the title into a property nobody wrote."""
        a_dated_case(self.tenant, title="Rules on research, fees; and reporting", key_date=SOON)
        body = self.fetch(self.live_token()).content.decode()
        self.assertIn("SUMMARY:In force: Rules on research\\, fees\\; and reporting\r\n", body)

    def test_folding_never_splits_a_character_in_half(self) -> None:
        """Five content languages, four of them with characters two bytes wide, and a fold
        is counted in octets. The title below is nothing but two-byte characters, so the
        75th octet falls inside one: cutting there would hand a calendar client bytes it
        cannot decode."""
        wide = "\u00e5\u00e4\u00f6" * 20
        a_dated_case(self.tenant, title=wide, key_date=SOON)
        body = self.fetch(self.live_token()).content
        self.assertIn(wide, body.decode("utf-8").replace("\r\n ", ""), "the characters survived the fold")
        for line in body.decode("utf-8").split("\r\n"):
            with self.subTest(line=line[:20]):
                self.assertLessEqual(len(line.encode()), feed_logic.FOLD_OCTETS)

    def test_unknown_revoked_expired_and_malformed_all_answer_one_404(self) -> None:
        """The whole of D-52's indistinguishability: nothing an address answers says whether
        it ever existed, was stopped or simply went quiet."""
        live = self.live_token()
        headers = self.headers()
        revoked = self.token_of(self.subscribe(headers))
        stopped = self.own_rows().exclude(token_prefix=live.partition(".")[0]).get()
        self.client.delete(f"{FEEDS}/{stopped.id}", **headers)

        idle = self.token_of(self.subscribe(headers))
        self.own_rows().filter(token_prefix=idle.partition(".")[0]).update(
            created_at=LONG_AGO, last_used_at=None
        )

        wrong_secret = f"{live.partition('.')[0]}.{'x' * 43}"
        bodies = set()
        for name, token in (
            ("unknown", f"{'0' * TOKEN_PREFIX_LENGTH}.{'y' * 43}"),
            ("wrong secret", wrong_secret),
            ("revoked", revoked),
            ("idle", idle),
            ("malformed", "not-a-token"),
            ("empty secret", f"{'0' * TOKEN_PREFIX_LENGTH}."),
        ):
            with self.subTest(token=name):
                refused = self.fetch(token)
                self.assertEqual(refused.status_code, 404)
                self.assertEqual(refused.json()["code"], "not_found")
                bodies.add(refused.content)
        self.assertEqual(len(bodies), 1, "two refusals differ; an address could be probed")
        self.assertEqual(self.fetch(live).status_code, 200, "the live one still works")

    def test_a_fetch_moves_the_stamp_writes_feed_used_and_writes_no_audit_row(self) -> None:
        token = self.live_token()
        audit_before = AuditEvent.objects.filter(subject_type="calendar_feed").count()
        self.assertEqual(self.fetch(token).status_code, 200)
        feed = self.own_rows().get()
        self.assertEqual(feed.last_used_at, INSTANT)
        used = LoginEvent.objects.filter(event=LoginEventKind.FEED_USED.value)
        self.assertEqual(used.count(), 1)
        row = used.get()
        self.assertEqual((row.tenant_id, row.user_id, row.success), (self.tenant.id, self.reader.id, True))
        self.assertIsNone(row.ip, "a calendar client's address is nobody's business here")
        self.assertEqual(row.user_agent, "")
        self.assertEqual(
            AuditEvent.objects.filter(subject_type="calendar_feed").count(),
            audit_before,
            "reading a calendar is not a decision a bank made",
        )

    def test_the_stamp_and_its_security_log_row_are_throttled(self) -> None:
        """A client polling every minute would otherwise turn a read into a write and fill
        the security log with one bank's polling (ID-10's rule, applied here)."""
        token = self.live_token()
        self.fetch(token)
        soon_after = INSTANT + datetime.timedelta(seconds=settings.CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS)
        self.fetch(token, at=soon_after)
        self.assertEqual(LoginEvent.objects.filter(event=LoginEventKind.FEED_USED.value).count(), 1)
        self.assertEqual(self.own_rows().get().last_used_at, INSTANT)

        later = soon_after + datetime.timedelta(seconds=1)
        self.fetch(token, at=later)
        self.assertEqual(LoginEvent.objects.filter(event=LoginEventKind.FEED_USED.value).count(), 2)
        self.assertEqual(self.own_rows().get().last_used_at, later)

    def test_no_token_prefix_or_secret_reaches_a_log_line(self) -> None:
        """Captured at the handler, formatted by the formatter production uses, over the
        fetch that works and the one that is refused (D-52: the query string is the half our
        own logs drop, and this is the proof rather than the assumption)."""
        token = self.live_token()
        prefix, _, secret = token.partition(".")
        with captured_logs() as written:
            self.assertEqual(self.fetch(token).status_code, 200)
            self.assertEqual(self.fetch(f"{prefix}.{'z' * 43}").status_code, 404)
            self.assertEqual(self.fetch("not-a-token").status_code, 404)
        lines = "\n".join(written)
        for half in (token, prefix, secret):
            with self.subTest(half=half[:6]):
                self.assertNotIn(half, lines)

    def test_a_refusal_never_echoes_the_token_back(self) -> None:
        refused = self.fetch("looks-like-a-token.but-is-not")
        self.assertNotIn("looks-like-a-token", refused.content.decode())

    @override_settings(RATE_LIMITING_ENABLED=True, CALENDAR_FEED_RATE_PER_MINUTE=2)
    def test_a_flood_on_one_address_never_refuses_another(self) -> None:
        headers = self.headers()
        flooded = self.token_of(self.subscribe(headers))
        other = self.token_of(self.subscribe(headers))
        for _ in range(settings.CALENDAR_FEED_RATE_PER_MINUTE):
            self.assertEqual(self.fetch(flooded).status_code, 200)
        refused = self.fetch(flooded)
        self.assertEqual((refused.status_code, refused.json()["code"]), (429, "rate_limited"))
        self.assertEqual(self.fetch(other).status_code, 200)


class TheServerStopsASubscriptionItself(FeedFixture):
    """ADR 0045: checked on the request, not swept for, so the gap between losing access and
    the address going dead is one fetch. Each one revokes the row and records a system
    actor doing it, in the same transaction."""

    def assert_stopped(self, token: str, *, because: str, at: datetime.datetime = INSTANT) -> None:
        self.assertEqual(self.fetch(token, at=at).status_code, 404)
        feed = self.own_rows().get()
        self.assertIsNotNone(feed.revoked_at, "the row was not stopped")
        row = AuditEvent.objects.filter(action="calendar_feed.revoked").get()
        self.assertEqual(row.actor_type, ActorType.SYSTEM.value)
        self.assertEqual((row.tenant_id, row.subject_id), (self.tenant.id, feed.id))
        self.assertIn(because, row.summary)
        self.assertEqual(self.fetch(token, at=at).status_code, 404, "and it stays stopped")

    def test_the_owner_leaving_the_bank_stops_it(self) -> None:
        token = self.token_of(self.subscribe())
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(pk=self.member.pk).update(deactivated_at=INSTANT)
        self.assert_stopped(token, because="no longer a member")

    def test_losing_roadmap_read_stops_it(self) -> None:
        token = self.token_of(self.subscribe())
        tenancy.activate(self.tenant.id)
        for role in TenantRole.objects.filter(tenant=self.tenant):
            TenantRole.objects.filter(pk=role.pk).update(
                permissions=[name for name in role.permissions if name != perms.ROADMAP_READ]
            )
        self.assert_stopped(token, because="lost access to the roadmap")

    def enrol_again(self, bank: Tenant) -> None:
        """An admin of `bank` re-issues the reader's enrolment a minute after they
        subscribed, through the function the members screen and the console both call
        (ID-05)."""
        admin = factories.member_user(bank, roles=("admin",))
        with frozen_at(AFTER_ENROLMENT):
            tenancy.activate(bank.id)
            invitation_logic.reissue_enrolment(
                tenant=bank,
                user=self.reader,
                actor=factories.user_actor(user_id=admin.id),
                actor_user=admin,
                request=None,
                step_up_assertion_id=None,
            )

    def test_being_enrolled_again_stops_it(self) -> None:
        """A re-enrolment retires every passkey and revokes every session, so an address
        minted by the person as they were is not one the person as they are now asked for."""
        factories.passkey(self.reader)
        token = self.token_of(self.subscribe())
        self.enrol_again(self.tenant)
        self.assert_stopped(token, because="enrolled again", at=LATER_THAT_NIGHT)

    def test_being_enrolled_again_by_another_bank_stops_it_too(self) -> None:
        """A person's passkeys are theirs, not a bank's, and re-enrolment retires all of
        them wherever it was issued. The security log's `reenrolment_issued` row is written
        in the issuing bank alone, and row-level security hides it from this one, so it
        cannot be what the rule reads."""
        elsewhere = factories.tenant(slug=f"feed-elsewhere-{next(_slugs)}", timezone="Europe/Stockholm")
        factories.member(elsewhere, roles=("reader",), user_row=self.reader)
        factories.passkey(self.reader)
        token = self.token_of(self.subscribe())
        self.enrol_again(elsewhere)
        self.assert_stopped(token, because="enrolled again", at=LATER_THAT_NIGHT)

    def test_removing_one_passkey_while_keeping_another_is_not_enrolling_again(self) -> None:
        """Replacing a phone retires its passkey and keeps the rest, and a person may never
        remove their last one, so only re-enrolment leaves nobody with a passkey. That
        moment is what the rule looks for, not any retirement at all."""
        old_phone = factories.passkey(self.reader, nickname="Old phone")
        factories.passkey(self.reader, nickname="Laptop")
        token = self.token_of(self.subscribe())
        with frozen_at(AFTER_ENROLMENT):
            passkey_logic.remove_passkey(
                user_principal(subject_id=self.reader.id, tenant_id=self.tenant.id), old_phone.id
            )
        self.assertEqual(self.fetch(token, at=LATER_THAT_NIGHT).status_code, 200)
        self.assertIsNone(self.own_rows().get().revoked_at)

    def test_a_subscription_nobody_fetches_expires(self) -> None:
        token = self.token_of(self.subscribe())
        self.own_rows().update(created_at=LONG_AGO, last_used_at=None)
        self.assert_stopped(token, because=f"{settings.CALENDAR_FEED_IDLE_DAYS} days")

    def test_a_subscription_in_use_is_never_touched_by_the_idle_rule(self) -> None:
        """The stamp is what the rule reads, so a client polling daily keeps it alive for
        years while one nobody pasted anywhere stops after a month."""
        token = self.token_of(self.subscribe())
        self.own_rows().update(created_at=LONG_AGO, last_used_at=INSTANT - datetime.timedelta(days=1))
        self.assertEqual(self.fetch(token).status_code, 200)
        self.assertIsNone(self.own_rows().get().revoked_at)
