"""The calendar subscription: one person's revocable address onto their bank's roadmap
(HOM-04, D-52, ADR 0045).

The token in the address is a credential, because a calendar client sends no header. So:
256-bit secret shown once and kept as a prefix beside its SHA-256; at most
`CALENDAR_FEEDS_PER_USER` working addresses; minting needs a recent sign-in or step-up;
unknown, malformed, revoked and expired tokens share one 404; every fetch re-checks
membership, `roadmap.read` and re-enrolment, and an address idle for
`CALENDAR_FEED_IDLE_DAYS` or older than a re-enrolment is stopped wherever it is next read.
No token, prefix or secret reaches a log, audit row or error body.

Events are selected by the bank's roadmap (`roadmap.calendar_items()`) but say only library
facts: stable key, date, what it is, title, publisher and a signed-in link. Never anything of
the bank's, because the entry travels outside its control (AC-TEN1). Kept apart from
`calendar.py` by the library fence (PRO-01).
"""

from __future__ import annotations

import datetime
import secrets
import uuid
from typing import NoReturn
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.home import roadmap
from apps.home.models import TOKEN_PREFIX_LENGTH, CalendarFeed
from apps.home.schemas import HomeCalendarFeed, HomeCalendarFeedCreated, HomeRoadmapItem
from apps.identity import rate_limit, roles_logic, tokens
from apps.identity.models import LoginEventKind, LoginMethod, Membership, User, WebAuthnCredential
from apps.identity.security_log import log_event
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.errors import not_found
from apps.shared.models import Tenant
from apps.taxonomy.reading import FALLBACK_LANGUAGE

# --- Minting, holding and stopping an address ---
# Pinned against the route Ninja registered (`tests_feed.py`).
ICS_PATH = "/api/v1/calendar/feed.ics"
# 256 random bits, as D-52 says, encoded by `secrets.token_urlsafe`.
FEED_SECRET_BYTES = 32
MINUTE = 60
# What an audit row calls it: never the address or its prefix, since half a credential is
# still half a credential (D-52).
FEED_SUBJECT = "Calendar subscription"
# The octet limit of one content line, the CRLF that ends it excluded (RFC 5545 §3.1).
FOLD_OCTETS = 75


def _mint_token() -> tuple[str, str, str]:
    """`(address token, lookup prefix, SHA-256 of the secret)`. The token is handed back
    once and stored nowhere; only the last two are kept."""
    prefix = secrets.token_hex(TOKEN_PREFIX_LENGTH // 2)
    secret = tokens.new_token(FEED_SECRET_BYTES)
    return f"{prefix}.{secret}", prefix, tokens.hash_token(secret)


def _parse_token(presented: str) -> tuple[str, str] | None:
    """`<prefix>.<secret>` as the prefix and the secret's hash, or None for any other shape;
    a malformed token and an unmatched one end the same way.
    """
    prefix, dot, secret = presented.strip().partition(".")
    if not dot or not secret or len(prefix) != TOKEN_PREFIX_LENGTH:
        return None
    return prefix, tokens.hash_token(secret)


def _no_such_feed() -> NoReturn:
    """The one refusal this address makes, for unknown, malformed, revoked, expired or no
    longer served alike: one body, one status and the same work in front of it, so neither
    the body nor the timing says which (D-52).
    """
    raise not_found()


def _feed_out(feed: CalendarFeed) -> HomeCalendarFeed:
    """The row as a person reads it. No prefix and no hash: the address is shown once, by
    `create_feed()`, and nothing else hands back a piece of it."""
    return HomeCalendarFeed(
        id=feed.id,
        created_at=feed.created_at,
        last_used_at=feed.last_used_at,
        revoked_at=feed.revoked_at,
    )


def list_feeds(tenant: Tenant, user: User) -> list[HomeCalendarFeed]:
    """`GET /calendar-feeds`: the caller's own subscriptions, newest first (HOM-04).

    Own rows by the query itself. Revoked ones stay listed with their stop date, the newest
    `CALENDAR_FEED_REVOKED_SHOWN` of them; working ones are capped, so no paging. Idle or
    pre-re-enrolment ones are stopped first, so none is shown as working that answers 404.
    """
    _live_feeds(tenant, user, timezone.now())
    mine = CalendarFeed.objects.filter(tenant=tenant, user=user)
    stopped = mine.filter(revoked_at__isnull=False).order_by("-revoked_at", "id").values("pk")
    rows = mine.filter(Q(revoked_at__isnull=True) | Q(pk__in=stopped[: settings.CALENDAR_FEED_REVOKED_SHOWN]))
    return [_feed_out(feed) for feed in rows]


def create_feed(*, tenant: Tenant, user: User, actor: Actor) -> HomeCalendarFeedCreated:
    """`POST /calendar-feeds`: mint one address and show it once (HOM-04, D-52).

    The route demanded a recent sign-in or step-up. Here: at most `CALENDAR_FEEDS_PER_USER`
    working subscriptions, so a stolen session cannot leave a drawer of addresses behind.
    Revoked, idle and pre-re-enrolment rows do not count (the latter two are stopped first).
    The membership row is locked before counting, so two concurrent calls cannot both mint
    the fifth. The audit row carries no part of the address.
    """
    # Read for its lock alone; a second call waits here until the first has committed.
    Membership.objects.select_for_update().filter(tenant=tenant, user=user).first()  # ordering: unique (tenant, user), at most one row
    if len(_live_feeds(tenant, user, timezone.now())) >= settings.CALENDAR_FEEDS_PER_USER:
        raise ValidationError(
            f"You already have {settings.CALENDAR_FEEDS_PER_USER} calendar subscriptions. "
            "Stop one you no longer use and then subscribe again.",
            code="feed_limit_reached",
        )
    plain, prefix, token_hash = _mint_token()
    feed = CalendarFeed.objects.create(
        tenant=tenant, user=user, token_prefix=prefix, token_hash=token_hash
    )
    record(
        action="calendar_feed.created",
        actor=actor,
        subject_type="calendar_feed",
        subject_id=feed.id,
        subject_title=FEED_SUBJECT,
        summary="Subscribed a calendar client to the roadmap.",
        tenant_id=tenant.id,
        after={"createdAt": feed.created_at.isoformat()},
    )
    # The app's own public address, never the request's host: a call that came through the web
    # server carries the API's private name there (D-134), which no calendar client can reach.
    address = f"{settings.APP_BASE_URL.rstrip('/')}{ICS_PATH}?{urlencode({'token': plain})}"
    return HomeCalendarFeedCreated(feed=_feed_out(feed), url=address)


def revoke_feed(*, tenant: Tenant, user: User, actor: Actor, feed_id: uuid.UUID) -> None:
    """`DELETE /calendar-feeds/{feedId}`: stop one of the caller's own addresses (HOM-04).

    Another person's and an unknown id both answer `not_found`. Revoking an already revoked
    one succeeds and is audited (retries are safe, AC-AUD1), saying when it was stopped.
    """
    feed = CalendarFeed.objects.filter(
        pk=feed_id,
        tenant=tenant,
        user=user,
    ).first()  # ordering: pk lookup inside one owner, at most one row
    if feed is None:
        raise ValidationError("Not found.", code="not_found")
    stopped = _stop(feed, timezone.now())
    stamp = feed.revoked_at.isoformat() if feed.revoked_at is not None else None
    record(
        action="calendar_feed.revoked",
        actor=actor,
        subject_type="calendar_feed",
        subject_id=feed.id,
        subject_title=FEED_SUBJECT,
        summary="Stopped a calendar subscription.",
        tenant_id=tenant.id,
        before={"revokedAt": None if stopped else stamp},
        after={"revokedAt": stamp},
    )


# --- The fetch: the one route whose whole credential is in a query string ---
def calendar_ics(request: HttpRequest, token: str) -> HttpResponse:
    """`GET /calendar/feed.ics?token=<prefix>.<secret>`: the subscribed roadmap as iCalendar
    (HOM-04, D-52, ADR 0045). The address is the whole credential, so each step stands in
    for a sign-in:

    1. Shape, then prefix lookup through `tenancy.identity_lookup()`, then a constant-time
       compare of the secret's SHA-256, as for an API key (ID-10).
    2. Still granted: a departed owner, lost `roadmap.read`, a re-enrolment or
       `CALENDAR_FEED_IDLE_DAYS` without a fetch revoke the row now, with a system-actor
       audit row, so access dies at the next fetch rather than the next night.
    3. One 404 for all of it (`_no_such_feed()`).

    No audit row for a read; a throttled `feed_used` security-log row with no address or IP.
    """
    parsed = _parse_token(token)
    if parsed is None:
        _no_such_feed()
    prefix, presented_hash = parsed
    # Per token: `rate_limit` hashes the key, so the bucket names no credential, and a flood on
    # one address leaves the others answering.
    rate_limit.enforce("calendar-feed", prefix, settings.CALENDAR_FEED_RATE_PER_MINUTE, MINUTE)
    with tenancy.identity_lookup():
        feed = (
            CalendarFeed.objects.select_related("tenant__default_language", "user__locale")
            .filter(token_prefix=prefix)
            .first()  # ordering: token_prefix is unique across every bank, at most one row
        )
    if feed is None or not tokens.constant_equal(presented_hash, feed.token_hash):
        _no_such_feed()
    if feed.revoked_at is not None:
        _no_such_feed()
    tenancy.activate(feed.tenant_id)
    now = timezone.now()
    ended = _subscription_ended(feed, now)
    if ended is not None:
        _revoke_automatically(feed, now, ended)
        _no_such_feed()
    _stamp_used(feed, now)
    response = HttpResponse(_ics_document(feed, now), content_type="text/calendar; charset=utf-8")
    # The body is one bank's roadmap fetched with a credential: no shared cache may keep it.
    response["Cache-Control"] = "private, no-store"
    return response


def _live_feeds(tenant: Tenant, user: User, now: datetime.datetime) -> list[CalendarFeed]:
    """The caller's working subscriptions, after stopping each idle or pre-re-enrolment one
    as a fetch would (ADR 0045), so none is shown as working or counted against the cap."""
    passkeys = _passkeys(user.id)
    live = []
    for feed in CalendarFeed.objects.filter(tenant=tenant, user=user, revoked_at__isnull=True):
        if _idle(feed, now):
            _revoke_automatically(feed, now, _idle_summary())
        elif _enrolled_again(feed, passkeys):
            _revoke_automatically(feed, now, ENROLLED_AGAIN)
        else:
            live.append(feed)
    return live


def _idle(feed: CalendarFeed, now: datetime.datetime) -> bool:
    """Nobody has fetched it for `CALENDAR_FEED_IDLE_DAYS` days: a calendar that was removed
    or a device that was replaced, never one in use, because every fetch moves the stamp."""
    idle_since = feed.last_used_at or feed.created_at
    return now - idle_since > datetime.timedelta(days=settings.CALENDAR_FEED_IDLE_DAYS)


ENROLLED_AGAIN = "Calendar subscription stopped: the person who made it was enrolled again."


def _idle_summary() -> str:
    return f"Calendar subscription stopped: nobody fetched it for {settings.CALENDAR_FEED_IDLE_DAYS} days."


def _subscription_ended(feed: CalendarFeed, now: datetime.datetime) -> str | None:
    """Why this subscription has to stop, as its audit summary, or None (D-52, ADR 0045).
    Bank rows are read with the feed's tenant activated; re-enrolment from the person's
    passkeys, which belong to no bank.
    """
    if _idle(feed, now):
        return _idle_summary()
    membership = Membership.objects.filter(
        tenant_id=feed.tenant_id,
        user_id=feed.user_id,
        deactivated_at__isnull=True,
    ).first()  # ordering: unique (tenant, user), at most one row
    if membership is None:
        return "Calendar subscription stopped: the person who made it is no longer a member."
    if perms.ROADMAP_READ not in roles_logic.permissions_of(membership.roles.all()):
        return "Calendar subscription stopped: the person who made it lost access to the roadmap."
    if _enrolled_again(feed, _passkeys(feed.user_id)):
        return ENROLLED_AGAIN
    return None


def _passkeys(user_id: uuid.UUID) -> list[tuple[datetime.datetime, datetime.datetime | None]]:
    """When each of a person's passkeys, retired ones included, was made and retired."""
    return list(WebAuthnCredential.objects.filter(user_id=user_id).values_list("created_at", "retired_at"))


def _enrolled_again(
    feed: CalendarFeed, passkeys: list[tuple[datetime.datetime, datetime.datetime | None]]
) -> bool:
    """Whether the owner was enrolled again since subscribing (ID-05).

    Re-enrolment is the only thing that leaves a person with no passkey (removing the last is
    refused, under a lock), so a moment after the subscription with none left is a
    re-enrolment. The security log's `reenrolment_issued` cannot serve: row-level security
    hides it from the person's other banks, whose subscriptions must stop too.
    """
    retirements = {retired for _, retired in passkeys if retired is not None and retired > feed.created_at}
    return any(
        all(created > moment or (retired is not None and retired <= moment) for created, retired in passkeys)
        for moment in retirements
    )


def _stop(feed: CalendarFeed, now: datetime.datetime) -> bool:
    """Stamp the row if it still works, and say whether this call stopped it. Conditional in
    the statement, so of two concurrent stops the second changes nothing and the stop date
    never moves. `feed` then carries the stored stamp."""
    stopped = CalendarFeed.objects.filter(pk=feed.pk, revoked_at__isnull=True).update(revoked_at=now) == 1
    if stopped:
        feed.revoked_at = now
    else:
        feed.refresh_from_db(fields=["revoked_at"])
    return stopped


def _revoke_automatically(feed: CalendarFeed, now: datetime.datetime, summary: str) -> None:
    """Stop the row with a system actor and a summary naming the rule (ADR 0045), in this
    request's transaction. A row someone else just stopped is audited once, by them."""
    if not _stop(feed, now):
        return
    record(
        action="calendar_feed.revoked",
        actor=Actor.system(),
        subject_type="calendar_feed",
        subject_id=feed.id,
        subject_title=FEED_SUBJECT,
        summary=summary,
        tenant_id=feed.tenant_id,
        before={"revokedAt": None},
        after={"revokedAt": now.isoformat()},
    )


def _stamp_used(feed: CalendarFeed, now: datetime.datetime) -> None:
    """Move `last_used_at` and write `feed_used`, at most once every
    `CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS` (ID-11, ADR 0045), so a polling client does
    not turn reads into writes. `request=None` keeps address and IP out of the row. The
    method is `api_key`, this credential's twin; the event names which it was.
    """
    throttle = datetime.timedelta(seconds=settings.CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS)
    if feed.last_used_at is not None and now - feed.last_used_at <= throttle:
        return
    feed.last_used_at = now
    feed.save(update_fields=["last_used_at"])
    log_event(
        event=LoginEventKind.FEED_USED,
        method=LoginMethod.API_KEY,
        success=True,
        request=None,
        user=feed.user,
        tenant_id=feed.tenant_id,
    )


# --- The document (RFC 5545) ---
def _ics_document(feed: CalendarFeed, now: datetime.datetime) -> str:
    """The owner's roadmap as iCalendar, from library columns only (ADR 0045, AC-TEN1).
    Selected by `calendar_items()`, the roadmap's own query; each event says only library
    facts, never a judgement of the bank's. `tests_feed.py` pins the properties emitted.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//bleqq//{settings.PRODUCT_NAME}//EN",
    ]
    for change_key, item in roadmap.calendar_items(feed.tenant, _language_order(feed)):
        lines.extend(_event(change_key, item, now))
    lines.append("END:VCALENDAR")
    return "".join(f"{folded}\r\n" for line in lines for folded in _fold(line))


def _event(change_key: str, item: HomeRoadmapItem, now: datetime.datetime) -> list[str]:
    """One all-day event, five properties. The UID is the change's stable key, so a client
    updates the event when its date moves and nothing of the bank leaves. The key is escaped
    like any text: an agent chose it, and a line break would start a property of its own."""
    summary = f"{item.label}: {item.title}" if item.label else item.title
    link = f"{settings.APP_BASE_URL.rstrip('/')}/watch/{item.change_id}"
    return [
        "BEGIN:VEVENT",
        f"UID:{_escape(change_key)}@{_uid_domain()}",
        f"DTSTAMP:{now.astimezone(datetime.UTC):%Y%m%dT%H%M%SZ}",
        f"DTSTART;VALUE=DATE:{item.date:%Y%m%d}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(item.source_label or '')}",
        f"URL:{_escape(link)}",
        "END:VEVENT",
    ]


def _language_order(feed: CalendarFeed) -> list[str]:
    """The owner's language, then the bank's, then English, built from the row because there
    is no request principal here."""
    spoken = (feed.user.locale, feed.tenant.default_language)
    order = [language.key for language in spoken if language is not None]
    order.append(FALLBACK_LANGUAGE)
    return list(dict.fromkeys(order))


def _uid_domain() -> str:
    """The host half of an event's UID, from the app's own public address. A UID has to be
    globally unique, and this is the only place a domain appears in the document."""
    return urlsplit(settings.APP_BASE_URL).hostname or "bleqq"


def _escape(text: str) -> str:
    """RFC 5545 §3.3.11: a backslash, a semicolon, a comma or a newline inside a text value
    is escaped, or a title with a comma in it splits one property into two."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> list[str]:
    """RFC 5545 §3.1: a content line is at most 75 octets; a longer one continues on the next
    line after one space."""
    raw = line.encode("utf-8")
    if len(raw) <= FOLD_OCTETS:
        return [line]
    pieces: list[str] = []
    while raw:
        cut = FOLD_OCTETS if not pieces else FOLD_OCTETS - 1
        # Never split a character: step back to the start of the one straddling the limit,
        # which its continuation bytes (0b10xxxxxx) name.
        while cut < len(raw) and raw[cut] & 0xC0 == 0x80:
            cut -= 1
        piece = raw[:cut].decode("utf-8")
        pieces.append(piece if not pieces else f" {piece}")
        raw = raw[cut:]
    return pieces
