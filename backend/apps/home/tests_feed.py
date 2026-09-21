"""The calendar subscription (HOM-04, D-52, ADR 0045): an address whose token is the whole
credential, so what is proved here is everything that stands in place of a sign-in.

- **Shown once.** The address comes back from the create call and appears nowhere else —
  not in the list read, not in an audit row, not in a log line. The log half is proved by
  capturing the handler and formatting with the formatter production uses, rather than by
  assuming what a line would hold; D-52 put the token in the query string on exactly that
  claim.
- **One refusal.** Unknown, malformed, revoked, expired and wrong-secret tokens all leave
  by one 404 with one body, so no address ever says whether it existed.
- **A public document.** The events are selected by this bank's roadmap and say only what
  the library holds, pinned by asserting the property names emitted against a set, so a
  field added to a roadmap item later fails here instead of reaching a phone.
- **Stopped by the server.** The four rules that end a subscription are read on the
  request, and each one revokes the row and records a system actor doing it.

`tests_calendar.py` holds the other half of HOM-04, the public list, because
`apps/home/calendar.py` holds the code for it. The clock is frozen at a fixed instant and
every date is written out (playbook 8.3).
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import itertools
import logging
from collections.abc import Iterator
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.test import TestCase, override_settings

from apps.cases import testing as cases_build
from apps.home import feed as feed_logic
from apps.home.models import TOKEN_PREFIX_LENGTH, CalendarFeed
from apps.identity.models import LoginEvent, LoginEventKind, LoginMethod, Membership, TenantRole, User
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.audit import ActorType
from apps.shared.logging import JsonFormatter
from apps.shared.models import AuditEvent, Tenant
from apps.shared.routes import iter_operations
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build
from apps.watch.models import RegulatoryChange
from config.api import api

# Distinct slugs, because each fixture below builds its own bank.
_slugs = itertools.count(1)

# The instant everything here is frozen at, and the dates around it. The server reads in
# UTC, where this instant is still 30 September.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
SOON = datetime.date(2026, 10, 15)
LATER = datetime.date(2027, 1, 20)


def a_change(*, title: str, key_date: datetime.date) -> RegulatoryChange:
    return watch_build.change(title=title, key_date=key_date, key_date_label="In force")


FEEDS = "/api/v1/calendar-feeds"
ICS = "/api/v1/calendar/feed.ics"
# The bank's own judgement, seeded on the case behind every date below. Nothing in this
# file may find it in an address, a list, an audit row, a log line or the document itself.
SO_WHAT = "Three regulations change for us and research budgets move."
# A month after the instant everything here is frozen at: past the 30-day idle expiry.
LONG_AGO = INSTANT - datetime.timedelta(days=40)
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


def a_dated_case(tenant: Tenant, *, title: str, key_date: datetime.date) -> RegulatoryChange:
    """One reform with a date, and this bank's own open case on it carrying a judgement."""
    change = a_change(title=title, key_date=key_date)
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

    def headers(self, user: User | None = None) -> dict[str, Any]:
        """A session minted at the frozen instant, so it is young enough to mint an address
        (D-52: a recent sign-in or a fresh passkey assertion)."""
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            return sign_in(user or self.reader, tenant=self.tenant)

    def subscribe(self, headers: dict[str, Any] | None = None) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            return self.client.post(
                FEEDS, data={}, content_type="application/json", **(headers or self.headers())
            )

    def token_of(self, response: Any) -> str:
        return parse_qs(urlsplit(response.json()["url"]).query)["token"][0]

    def fetch(self, token: str, *, at: datetime.datetime = INSTANT) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=at):
            return self.client.get(ICS, {"token": token})

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
        properties = {
            line.split(":", 1)[0].split(";", 1)[0]
            for line in body.split("\r\n")
            if line and not line.startswith(" ")
        }
        self.assertEqual(
            properties,
            {"BEGIN", "END", "VERSION", "PRODID", "UID", "DTSTAMP", "DTSTART", "SUMMARY", "DESCRIPTION", "URL"},
        )
        for judgement in (SO_WHAT, self.tenant.name, "act_now", "urgency", "owner", "new"):
            with self.subTest(judgement=judgement):
                self.assertNotIn(judgement, body)

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
                self.assertLessEqual(len(line.encode()), 76)

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
                self.assertLessEqual(len(line.encode()), 76)

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

    def test_being_enrolled_again_stops_it(self) -> None:
        """A re-enrolment retires every passkey and revokes every session, so an address
        minted by the person as they were is not one the person as they are now asked for."""
        token = self.token_of(self.subscribe())
        tenancy.activate(self.tenant.id)
        with mock.patch("django.utils.timezone.now", return_value=INSTANT + datetime.timedelta(minutes=1)):
            LoginEvent.objects.create(
                tenant=self.tenant,
                user=self.reader,
                email=self.reader.email,
                method=LoginMethod.EMAIL_CODE.value,
                event=LoginEventKind.REENROLMENT_ISSUED.value,
                success=True,
            )
        self.assert_stopped(token, because="enrolled again")

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
