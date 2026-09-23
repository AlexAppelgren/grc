"""The calendar subscription: one person's revocable address onto their bank's roadmap
(HOM-04, D-52, ADR 0045).

**The token in the address is a credential, and the only one of its kind.** D-52 decided it
that way because a calendar client sends no header, follows no sign-in and subscribes by web
address alone, while a token in the path lands in a hosting edge's request line and our own
logs drop the query. Everything that stands in place of a sign-in is therefore here: the
secret is 256 bits, shown once and kept as a lookup prefix beside its SHA-256; a person
holds at most `CALENDAR_FEEDS_PER_USER` addresses that work; minting one takes a recent
sign-in or a step-up (the route's own gate); an unknown, malformed, revoked or expired token
all answer one 404; and every fetch re-checks that the owner is still a member who still
holds `roadmap.read` and has not been enrolled again, revoking the subscription then and
there when one of those has gone. One nobody has fetched for `CALENDAR_FEED_IDLE_DAYS`, or
one made before its owner was enrolled again, is stopped wherever it is next read — a
fetch, its owner's list or their next subscribe — so it is never shown as working and never
counted against the cap. A row is stopped once: whoever finds it second leaves it as it is.
No token, prefix or secret reaches a log line, an audit row or an error body: the plaintext
exists in `create_feed()` and in its answer, and nowhere else at all.

**What the document says is public.** The events are *selected* by this bank's roadmap —
`roadmap.calendar_items()`, the roadmap's own query narrowed to the regulatory dates stated
to the day, so a calendar never shows a date the roadmap page does not — and what each event
says comes from library columns alone: the change's stable key as its UID, the date, what
the date is, the reform's title, who published it and a link that needs signing in. Never a
"So what?", a case, an owner, an urgency, an internal deadline or the bank's name, because a
calendar entry travels to devices outside the bank's control (AC-TEN1).

**Why this is not in `apps/home/calendar.py`,** where `GET /upcoming` answers the public
half of HOM-04: that module reads library records and writes nothing, this one writes a
bank's own rows and reads no library record, and a module doing both is the shape a library
write outside the fence takes (`apps/shared/tests_library_fence.py`, PRO-01). The fence
decides the file boundary; the two halves meet in `api.py`.
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
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.reading import FALLBACK_LANGUAGE

# ---------------------------------------------------------------------------------------
# Minting, holding and stopping an address
# ---------------------------------------------------------------------------------------
# The address a calendar client polls. Written out once here and pinned against the route
# Ninja registered (`tests_feed.py`), so a minted address can never name a path that
# has moved.
ICS_PATH = "/api/v1/calendar/feed.ics"
# 256 random bits, as D-52 says, encoded by `secrets.token_urlsafe`.
FEED_SECRET_BYTES = 32
MINUTE = 60
# What an audit row calls the thing. Never the address and never its prefix: an audit row
# is read by people who do not hold the subscription, and half a credential is still half
# a credential (D-52).
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
    """`<prefix>.<secret>` as the prefix to look up and the secret's hash to compare, or
    None when the value is not that shape. Nothing about the value reaches the caller: a
    token of the wrong shape and a well-formed one that matches nothing end the same way.
    """
    prefix, dot, secret = presented.strip().partition(".")
    if not dot or not secret or len(prefix) != TOKEN_PREFIX_LENGTH:
        return None
    return prefix, tokens.hash_token(secret)


def _no_such_feed() -> NoReturn:
    """The one refusal this address makes: for a token that is unknown, malformed, revoked,
    expired or no longer served alike.

    One function, so there is one body and one status. A second wording anywhere would tell
    whoever holds an address which of those it is, and saying that it once existed is
    already saying something (D-52). The work in front of it is the same shape every time —
    at most one indexed read and one constant-time compare — so the timing tells no more
    than the body does.
    """
    raise ProblemError(status=404, code="not_found", detail="Not found.")


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

    The caller's own and nobody else's by the query itself, not by a filter afterwards, so
    another member's row cannot appear however this is called. A revoked subscription stays
    in the list with the date it stopped, because a person who pasted an address somewhere
    needs to see that it no longer works — the most recent `CALENDAR_FEED_REVOKED_SHOWN` of
    them, so the list stays short however many addresses a person has replaced over the
    years. What still works is capped already, so the list is bounded by design and needs
    no paging.

    One gone idle, or made before its owner was enrolled again, is stopped here first, so
    the list never shows as working an address that answers 404: the route already demands
    a member holding `roadmap.read`, which are the fetch's other two rules.
    """
    _live_feeds(tenant, user, timezone.now())
    mine = CalendarFeed.objects.filter(tenant=tenant, user=user)
    stopped = mine.filter(revoked_at__isnull=False).order_by("-revoked_at", "id").values("pk")
    rows = mine.filter(Q(revoked_at__isnull=True) | Q(pk__in=stopped[: settings.CALENDAR_FEED_REVOKED_SHOWN]))
    return [_feed_out(feed) for feed in rows]


def create_feed(
    *, tenant: Tenant, user: User, actor: Actor, request: HttpRequest
) -> HomeCalendarFeedCreated:
    """`POST /calendar-feeds`: mint one address and show it once (HOM-04, D-52).

    The route has already demanded a recent sign-in or a fresh passkey assertion, because
    the address outlives the session that asks for it. What is left here is the cap: a
    person holds at most `CALENDAR_FEEDS_PER_USER` subscriptions that still work, so a
    stolen session cannot quietly leave a drawer of addresses behind, and revoking one
    makes room. A revoked subscription is not counted, because it works for nobody — which
    is what makes "revoke one and subscribe again" true rather than nearly true — and nor is
    one gone idle or made before the person was enrolled again, which is stopped here first
    for the same reason: somebody re-enrolled because their devices were lost subscribes
    again straight away.

    Two calls at once take turns. The caller's membership row is locked before anything is
    counted: it exists for every caller, where their live rows may be none, and a count
    over live rows would never see the row a concurrent call is inserting, so both could
    count four and both mint a fifth.

    The audit row says who subscribed and when. It carries no part of the address: the
    plaintext exists in this function and in the answer, and nowhere else at all.
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
    address = f"{request.build_absolute_uri(ICS_PATH)}?{urlencode({'token': plain})}"
    return HomeCalendarFeedCreated(feed=_feed_out(feed), url=address)


def revoke_feed(*, tenant: Tenant, user: User, actor: Actor, feed_id: uuid.UUID) -> None:
    """`DELETE /calendar-feeds/{feedId}`: stop one of the caller's own addresses (HOM-04).

    Another person's subscription and one that never existed both answer `not_found`, so no
    id can be probed for what somebody else holds. Revoking one that is already revoked
    answers the same way and is audited like any other call, because a retry has to be safe
    and an unaudited 2xx is not a thing this product does (AC-AUD1). Its audit row then
    says the row was already stopped, and when, rather than that this call stopped it.
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


# ---------------------------------------------------------------------------------------
# The fetch: the one route in the product whose whole credential is in a query string
# ---------------------------------------------------------------------------------------
def calendar_ics(request: HttpRequest, token: str) -> HttpResponse:
    """`GET /calendar/feed.ics?token=<prefix>.<secret>`: the subscribed roadmap as an
    iCalendar document (HOM-04, D-52, ADR 0045).

    No session and no key reach this route — a calendar client sends no header and cannot
    be asked for a passkey — so the address is the whole credential, and each step below
    stands in place of a sign-in:

    1. **The shape, then the prefix.** The prefix is the lookup and the secret is compared
       in constant time against its stored SHA-256, exactly as an API key is (ID-10). The
       row is found through `tenancy.identity_lookup()`, because no bank is known until it
       is found; `calendar_feed` is the fifth table of that clause.
    2. **Still granted, on this request.** A subscription whose owner has left the bank,
       lost `roadmap.read` or been enrolled again stops working the next time it is
       fetched, and one nobody has fetched for `CALENDAR_FEED_IDLE_DAYS` days expires
       (its owner's list and next subscribe find that one too). It is checked here rather
       than swept nightly, so the gap between losing access and the address going dead is
       one fetch and not one night. Each of those revokes the row and writes an audit
       event with a system actor, in this request's transaction.
    3. **The same 404 for all of it.** Unknown, malformed, revoked, expired and revoked a
       moment ago by step 2 all leave through `_no_such_feed()`.

    A fetch writes no audit row: reading a calendar is not a decision a bank made. It
    writes a throttled `feed_used` row in the security log, with no address and no IP, and
    moves `last_used_at` on the same throttle, which is what the idle expiry then reads.
    """
    parsed = _parse_token(token)
    if parsed is None:
        _no_such_feed()
    prefix, presented_hash = parsed
    # Per token, not per caller: `rate_limit` hashes the key it is handed, so the bucket
    # names no credential even inside the cache, and a flood on one address leaves every
    # other address answering.
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
    # A calendar client may keep its own copy; nothing between it and us may. The body is
    # one bank's roadmap and the address that asked for it is a credential.
    response["Cache-Control"] = "private, no-store"
    return response


def _live_feeds(tenant: Tenant, user: User, now: datetime.datetime) -> list[CalendarFeed]:
    """The caller's subscriptions that still work, after stopping each one gone idle or made
    before the caller was enrolled again, the way a fetch would stop it (ADR 0045). Where a
    person looks — their list, their next subscribe — is where such an address is found, so
    it is ended there rather than shown as working or counted against the cap until some
    calendar client happens to ask. The person's passkeys are read once for all their rows."""
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
    """Why this subscription has to stop working, as the sentence its audit row carries, or
    None while it still holds (D-52, ADR 0045).

    Four reasons, each read on the request rather than swept for. The two that read the
    bank's own rows run with the feed's tenant activated, so they see that bank and no
    other; re-enrolment is read from the person's passkeys, which belong to no bank.
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
    """Whether the owner has been enrolled again since they subscribed (ID-05), read from
    their passkeys, which are the person's and not a bank's.

    Re-enrolment retires every passkey a person holds in one statement, in whichever bank an
    admin issued it, and it is the only thing that can leave them with none: a person is
    refused the removal of their last passkey, and `identity/passkey_logic.remove_passkey`
    locks their passkeys before it counts them, so two removals at once cannot each leave
    the other as the last. So a moment since the subscription at which no passkey was left
    is a re-enrolment, and replacing one phone's passkey while keeping another is not; one
    before the subscription is the person as they are now asking for it, and stops nothing.
    The security log's `reenrolment_issued` row cannot serve: it is written in the issuing
    bank, and row-level security hides it from every other bank the person belongs to,
    whose subscriptions have to stop as well.
    """
    retirements = {retired for _, retired in passkeys if retired is not None and retired > feed.created_at}
    return any(
        all(created > moment or (retired is not None and retired <= moment) for created, retired in passkeys)
        for moment in retirements
    )


def _stop(feed: CalendarFeed, now: datetime.datetime) -> bool:
    """Stamp the row if it still works, and say whether this call is the one that stopped it.

    Conditional in the statement itself, because two requests — two tabs on the account
    page, a list while a client polls, a person's revoke and the server's — can each read
    the row as working before either writes. The second one's update waits for the first,
    finds the row stopped and changes nothing, so the date it stopped never moves (nothing
    overwritten). `feed` then carries the stamp the row holds, whoever wrote it."""
    stopped = CalendarFeed.objects.filter(pk=feed.pk, revoked_at__isnull=True).update(revoked_at=now) == 1
    if stopped:
        feed.revoked_at = now
    else:
        feed.refresh_from_db(fields=["revoked_at"])
    return stopped


def _revoke_automatically(feed: CalendarFeed, now: datetime.datetime, summary: str) -> None:
    """Stop the row and record who did it, in this request's transaction. The actor is the
    system, because nobody asked for it: the bank sees the row a person's revoke would
    leave, with a summary naming the rule that ended it (ADR 0045). A row somebody else
    stopped a moment ago is left as it is and audited once, by whoever stopped it."""
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
    `CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS` (ID-11, ADR 0045).

    Throttled together, as an API key's stamp is: a client polling every minute would
    otherwise turn a read into a write and fill the security log with one bank's polling.
    `request=None` is the point of the call — the row says a subscription was used and
    never which address or from where, because the address is a credential and the IP is
    nobody's business on this route.

    The method is `api_key` because the security log has no fourth method and this
    credential is the API key's twin: minted once, shown once, kept as a prefix beside a
    hash, revocable, used by a machine. The `feed_used` event is what says which of the two
    it was.
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


# ---------------------------------------------------------------------------------------
# The document (RFC 5545)
# ---------------------------------------------------------------------------------------
def _ics_document(feed: CalendarFeed, now: datetime.datetime) -> str:
    """The owner's roadmap as iCalendar, from library columns only (ADR 0045, AC-TEN1).

    What is *selected* is this bank's: `calendar_items()` is the roadmap's own query, so
    the feed shows no date the roadmap page does not and cannot drift from it — only the
    regulatory ones, and only those stated to the day. What each event *says* is the
    library's: the change's stable key, the date, what the date is, the reform's title, who
    published it, and a link that needs a sign-in. No "So what?", no case note, no owner,
    no urgency, no internal deadline and no bank name — a calendar entry travels to phones,
    watches and mail clients outside the bank's control, so no judgement of the bank's ever
    goes into one. `tests_feed.py` pins the properties emitted, so a field added to a
    roadmap item later cannot ride out through here.
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
    """One all-day event: five properties and not a sixth. The UID is the change's stable
    key, which never changes and names no bank, so a client updates the event when its date
    moves rather than showing it twice, and nothing of the bank's own rows — not its case id
    — leaves in it. An agent reading untrusted pages chooses the key, so it is escaped like
    every other text value although the watch door accepts only a slug: a line break in it
    would otherwise end the UID and begin a property of its own on every subscriber's phone."""
    summary = f"{item.label}: {item.title}" if item.label else item.title
    link = f"{settings.APP_BASE_URL.rstrip('/')}/watch/{item.change_id}"
    return [
        "BEGIN:VEVENT",
        f"UID:{_escape(change_key)}@{_uid_domain()}",
        f"DTSTAMP:{now.astimezone(datetime.UTC):%Y%m%dT%H%M%SZ}",
        f"DTSTART;VALUE=DATE:{item.date:%Y%m%d}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(item.source_label)}",
        f"URL:{_escape(link)}",
        "END:VEVENT",
    ]


def _language_order(feed: CalendarFeed) -> list[str]:
    """The owner's language, then the bank's, then English. `language_order()` reads a
    request's principal and there is none here, so the same order is built from the row the
    token found."""
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
    """RFC 5545 §3.1: a content line is at most 75 octets and a longer one continues on the
    next line, which begins with one space. A regulatory title is regularly longer than
    that, and a client that follows the standard reads an unfolded line as a broken one."""
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
