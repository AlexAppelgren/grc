"""Routes of the home app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Nine operations, all nine declared here at once, each calling a named function in the module
that owns it. Declaring the whole contract first was deliberate: the four screens and the
newsletter agent were built against it while the logic was still arriving, and a screen that
calls a stub is better than a screen built against a shape nobody committed to. All nine are
built now, so nothing here answers 501 any more.

The four calendar-feed operations serve the shape D-52 and ADR 0045 decided: the address is
`/api/v1/calendar/feed.ics?token=<prefix>.<secret>`, a person keeps at most
`CALENDAR_FEEDS_PER_USER` subscriptions, creating one takes a recent sign-in or a step-up,
and the server revokes one when the person leaves, loses `roadmap.read`, is enrolled again
or lets it go idle.

Two gates here serve more than one principal or no principal at all, so they are logic
gates listed in `UNGATED_BY_DESIGN` and still answer the structured 403 with
`requiredPermission` (apps/shared/permissions.py, apps/taxonomy/http.py):

- **`GET /upcoming`** serves a person with `roadmap.read` and an agent's key with
  `upcoming:read`. It is the one list in this app that holds no bank's judgement at all,
  which is why a key may read it; no other route here is reachable with a key, whatever
  scopes that key holds.
- **`GET /calendar/feed.ics`** has no session and no key. A calendar client sends no
  header, follows no sign-in and cannot be asked for a passkey, so the revocable token in
  the address is the whole credential — the `public-token` shape the invitation links
  already use. It rides in the query string and not in the path, because our own access log
  prints the route without the query while a hosting edge writes whole request lines
  (D-52, ADR 0045; the one named exception to CONVENTIONS 3.6). Unknown, malformed, revoked
  and expired tokens leave it by one refusal, so nothing about a token can be probed.

`GET /upcoming` is served by `apps/home/calendar.py` and the four subscription
operations by `apps/home/feed.py`: one reads library records and writes nothing, the other
writes a bank's own rows and reads no library record, and the library fence wants those in
different files (`apps/shared/tests_library_fence.py`).

Everything else carries a single permission. `GET /home` takes `roadmap.read`, which every
system role holds, rather than being left ungated: a panel a reader may not see is answered
as null inside a 200, never as a 403 that would take the whole page away.

No route here writes a library row, and no route here approves, signs off, exports or
creates a key, so none takes the passkey step-up those actions need. `POST /calendar-feeds`
asks something narrower of the same mechanism: `enforce_recent_sign_in_or_step_up` accepts a
session made minutes ago or one that has just confirmed a passkey, because the address it
mints keeps working long after the session that asked for it has gone (D-52).
"""

import datetime
import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.home import briefing as briefing_reads
from apps.home import calendar as calendar_reads
from apps.home import feed as feed_logic
from apps.home import logic, roadmap
from apps.home.schemas import (
    FEED_TOKEN_MAX,
    UPCOMING_ITEM_EXAMPLE,
    CALENDAR_FEED_EXAMPLE,
    Home,
    HomeBriefing,
    HomeCalendarFeed,
    HomeCalendarFeedCreated,
    HomeCalendarFeedInput,
    HomeRoadmap,
    HomeRoadmapQuery,
    HomeUpcomingItem,
    HomeUpcomingQuery,
)
from apps.library.reading import reader_of
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, PrincipalKind, SessionAuth
from apps.shared.permissions import requires_permission
from apps.taxonomy.http import (
    actor_for,
    answers_problems,
    caller_tenant,
    caller_user,
    deny,
    principal,
    require_any,
)
from apps.taxonomy.reading import language_order

router = Router(tags=["Home"])

SESSION = SessionAuth()
SESSION_OR_KEY = [SessionAuth(), ApiKeyAuth()]

# What each path parameter means to a caller, hoisted out of the signatures so a route body
# stays one line of gate, schema and call (playbook 4.1).
_WEEK_START = (
    "The Monday of the week to read, as a plain calendar date (`2026-09-14`) in the bank's "
    "own time zone. The week is the ISO week, Monday to Sunday, so any other weekday answers "
    "404 rather than silently rounding to a week the caller did not ask for. A week the bank "
    "was never sent a briefing for answers 404 too."
)
_FEED_ID = (
    "The calendar subscription to revoke, as a uuid from `GET /calendar-feeds`. A "
    "subscription belonging to another person or another bank answers 404, never 403, so no "
    "id can be probed for what somebody else holds."
)
_FEED_TOKEN = (
    "The token from the calendar address, as `<prefix>.<secret>` and at most 128 "  # noqa: S105 a parameter description, never a credential
    "characters: a short lookup prefix, a dot, and 256 random bits. It is the whole "
    "credential, because a calendar client sends no header and cannot be asked for a "
    "passkey, so treat the address as a secret and never put it anywhere it will be read "
    "back. It travels in the query string rather than the path so that request lines a "
    "server writes down carry the route and not the token. A token that is unknown, "
    "revoked, expired or no longer served all answer the same 404 with the same body, so "
    "the address never says whether it ever existed."
)

# A short fixed list is answered as a plain array rather than a page, so its example lives on
# the route; the documentation gate reads it from the 200 response (playbook 4.1, the
# authorities read).
_UPCOMING_EXAMPLE = {"responses": {200: {"content": {"application/json": {"example": [UPCOMING_ITEM_EXAMPLE]}}}}}
_FEEDS_EXAMPLE = {"responses": {200: {"content": {"application/json": {"example": [CALENDAR_FEED_EXAMPLE]}}}}}
# The ICS answer is an iCalendar document served as `text/calendar`, which is what a calendar
# client subscribes to. Declared here because the generated response carries the body's type
# (a string) and not the media type the feed is served under.
_ICS_EXAMPLE = {
    "responses": {
        200: {
            "content": {
                "text/calendar": {
                    "schema": {"type": "string"},
                    "example": (
                        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//bleqq//Compliance Watch//EN\r\n"
                        "BEGIN:VEVENT\r\nUID:chg-fi-2026-research-payments@bleqq.com\r\nDTSTART;VALUE=DATE:20261001\r\n"
                        "SUMMARY:In force: FI adopts amended rules on paying for investment research\r\n"
                        "END:VEVENT\r\nEND:VCALENDAR\r\n"
                    ),
                }
            }
        }
    }
}


def require_upcoming_reader(request: HttpRequest) -> None:
    """`GET /upcoming`: a person with `roadmap.read` in their own bank, or an agent's key
    with `upcoming:read` so a newsletter run can read the dates it writes about (HOM-04,
    AGT-02). The list holds library facts only, which is what makes a key safe here; the 403
    names the scope it wanted to a key and the permission it wanted to a person."""
    who = principal(request)
    if who.kind is PrincipalKind.AGENT:
        if not who.has_scope(perms.SCOPE_UPCOMING_READ):
            raise deny(perms.SCOPE_UPCOMING_READ)
        return
    require_any(request, perms.ROADMAP_READ)


# ---------------------------------------------------------------------------------------
# Today (HOM-01)
# ---------------------------------------------------------------------------------------
@router.get(
    "/home",
    response=Home,
    auth=SESSION,
    operation_id="getHome",
    by_alias=True,
    summary="See what matters today",
)
@requires_permission(perms.ROADMAP_READ)
@answers_problems
def get_home(request: HttpRequest) -> Any:
    """Everything the timeline home shows, in one call: the bank's own date, the next dates
    with the whole roadmap's count beside them, the change that leads the week and how the
    watching of the sources is going. Call it once when a person opens the app; the screen
    fans out its other calls beside this one and chains nothing behind it.

    A read: it changes nothing and writes no audit row. A person's session holding
    `roadmap.read`, which every system role holds. Each panel is filtered by the reader's own
    permissions rather than the page being refused: a reader without `watch.read` gets a 200
    with `lead` and `sources` null and sees the rest. What is dated and what leads are
    filtered by the bank's regulatory scope (FP-03); the library half of every row is the same
    for every bank and the case half never leaves this one.

    Two panels of the design are answered elsewhere on purpose. What needs a decision is the
    `counts` object on `GET /me` (D-23), so one number has one source. The compliance standing
    arrives with the obligation register in a later chunk, because "0 gaps" before a register
    exists is a false statement about the bank.

    `comingUp` is the first rows of `GET /roadmap` with no filter and `roadmapCount` is how
    many that read holds in all, both from the one roadmap query, so the panel can never name
    a date the roadmap page does not. `lead` is the running ISO week's most urgent open,
    in-scope change, the same one the week's briefing leads with. A week with nothing in scope
    answers a null `lead`, and a bank with nothing dated ahead an empty `comingUp`; neither is
    an error.

    Errors: `permission_denied` when the session lacks `roadmap.read`, and `unauthenticated`
    when there is no session.
    """
    tenant = caller_tenant(request)
    who = principal(request)
    return logic.home_today(
        tenant,
        language_order(request, tenant=tenant),
        watch_reader=who.has_permission(perms.WATCH_READ),
    )


# ---------------------------------------------------------------------------------------
# The weekly briefing (HOM-02)
# ---------------------------------------------------------------------------------------
# `/briefings/current` is registered before `/briefings/{weekStart}` so the word `current`
# is matched as itself and never parsed as a date.
@router.get(
    "/briefings/current",
    response=HomeBriefing,
    auth=SESSION,
    operation_id="getCurrentBriefing",
    by_alias=True,
    summary="Read this week in brief",
)
@requires_permission(perms.WATCH_READ)
@answers_problems
def get_current_briefing(request: HttpRequest) -> Any:
    """This week's regulation as it reaches this bank: the week's changes inside the bank's
    regulatory scope, the one that leads, and the dates just ahead. Call it for the briefing
    page and for the "This week in brief" panel on Today.

    A read: it changes nothing, writes no audit row and stores no snapshot. The running week
    is computed live every time it is asked for, so it moves as the week does; the snapshot
    that a person can reopen is written once, by the weekly job, in the transaction that sends
    the mail. `emailSentAt` is therefore null here and stays null while the week is running:
    the mail for a week goes out once the week has ended.

    The week is the ISO week, Monday to Sunday, in the bank's own time zone, and a change
    belongs to it by when it was first sighted. `items` are the week's changes the bank has
    open work on inside its regulatory scope, most urgent first and then by key date, capped
    at the `BRIEFING_MAX_ITEMS` setting; what is left out stays on the watch feed. `lead` is
    the first of them, chosen by the same rule as the lead card on Today, so the two never
    disagree.

    A person's session holding `watch.read` in their own bank. Everything outside the library
    facts is this bank's own and is invisible to bleqq, to every other bank and to every model
    endpoint. A "So what?" that no person has confirmed is still an AI draft, is labelled as
    one on screen and never travels in the mail (WAT-05).

    A quiet week is a 200 with an empty `items` and a null `lead`, never a 404. Errors:
    `permission_denied` without `watch.read`, `unauthenticated` without a session.
    """
    tenant = caller_tenant(request)
    return briefing_reads.current_briefing(tenant, language_order(request, tenant=tenant))


@router.get(
    "/briefings/{week_start}",
    response=HomeBriefing,
    auth=SESSION,
    operation_id="getBriefing",
    by_alias=True,
    summary="Reopen a briefing exactly as it was sent",
)
@requires_permission(perms.WATCH_READ)
@answers_problems
def get_briefing(request: HttpRequest, week_start: datetime.date = Path(..., description=_WEEK_START)) -> Any:
    """One past week, read back from the snapshot the weekly job stored when it sent the
    mail. Call it from the link in that mail and from the previous-week control on the
    briefing page.

    A read: it changes nothing and writes no audit row. A person's session holding
    `watch.read` in their own bank; a week belonging to another bank is not addressable here
    at all. The snapshot is append-only, so a later change to the feed never alters it: what a
    person was told last Monday is what this call answers, which is the whole point of storing
    it rather than recomputing it.

    What the snapshot fixes is which changes that week's mail named and in which order. Each
    one is then resolved as it stands now, so a case somebody has since triaged shows its new
    urgency and its new status — the briefing records what a bank was told about, not a
    photograph of a case file. A change sighted after the mail went out never joins it.

    Errors: `not_found` when no briefing was stored for that week, or when the date is not a
    Monday, or when the caller may not see it — answered the same way on purpose, so no week
    can be probed; `permission_denied` without `watch.read`; `unauthenticated` without a
    session; `validation_error` when the path segment is not a calendar date.
    """
    tenant = caller_tenant(request)
    return briefing_reads.briefing_for_week(tenant, language_order(request, tenant=tenant), week_start)


# ---------------------------------------------------------------------------------------
# The roadmap (HOM-03, FP-03)
# ---------------------------------------------------------------------------------------
@router.get(
    "/roadmap",
    response=HomeRoadmap,
    auth=SESSION,
    operation_id="getRoadmap",
    by_alias=True,
    summary="See every date ahead, quarter by quarter",
)
@requires_permission(perms.ROADMAP_READ)
@answers_problems
def get_roadmap(request: HttpRequest, query: Query[HomeRoadmapQuery]) -> Any:
    """The bank's calendar of regulation: every dated change it has open work on, earliest
    first, with the quarter keys the screen draws its roster from. Call it for the roadmap
    page, and with `from` and `to` to look at one window.

    A read: it changes nothing and writes no audit row. A person's session holding
    `roadmap.read`, which every system role holds. What is listed respects the bank's
    regulatory scope (FP-03) and there is no switch to lift it: the inventory is where a
    person looks outside the scope. Each row carries library facts beside this bank's own case
    status, so two banks reading the same reform see the same date and different work.

    An item is here while all three are true: the bank's case for the change is open (a
    `closed` or `dismissed` case has left), the change is inside the bank's regulatory scope,
    and its date is today or later in the bank's own time zone. A date that has gone leaves
    the roadmap and stays on the change itself, so a `from` earlier than the bank's today
    widens nothing. The quarter key on every item is computed in that same time zone, which
    is why two banks an hour apart can open the same day in two quarters.

    A window with nothing in it is a 200 with an empty `items` and an empty `quarters`, never
    a 404, and `kind=internal` answers the same way in this release because the branches that
    produce the bank's own deadlines have not shipped yet.

    The whole window is answered at once rather than paged, because the screen draws a roster
    of every quarter ahead; narrow it with `from` and `to` rather than by paging.

    Errors: `permission_denied` without `roadmap.read`, `unauthenticated` without a session,
    and `validation_error` for a filter value the schema refuses — a `kind` outside the three
    it names, or a `from` or `to` that is not a calendar date. A query parameter this route
    does not read is ignored rather than refused, so check a filter's spelling against
    `kind`, `from` and `to` when it seems to have no effect.
    """
    tenant = caller_tenant(request)
    return roadmap.roadmap_items(tenant, language_order(request, tenant=tenant), query)


# ---------------------------------------------------------------------------------------
# Upcoming public facts and the calendar feed (HOM-04)
# ---------------------------------------------------------------------------------------
@router.get(
    "/upcoming",
    response=list[HomeUpcomingItem],
    auth=SESSION_OR_KEY,
    operation_id="listUpcoming",
    by_alias=True,
    summary="List the regulatory dates that are coming up",
    openapi_extra=_UPCOMING_EXAMPLE,
)
@answers_problems
def list_upcoming(request: HttpRequest, page: Query[HomeUpcomingQuery]) -> Any:
    """Every change in the shared library with a date still ahead of it, earliest first: what
    is coming, when, who issued it and how soon bleqq thinks it needs work. Call it to fill a
    public calendar, to write a newsletter, and from an agent run that has to know which dates
    are already known.

    A read: it changes nothing and writes no audit row. A person's session holding
    `roadmap.read`, or an agent's key carrying the `upcoming:read` scope — the only route in
    this app a key reaches, because it is the only one with no bank in it. Library facts
    exactly: no case, no footprint verdict, no owner and no "So what?", so two banks calling
    it receive identical answers and nothing here may be read as any bank's judgement or
    compliance position. The one narrower caller is an agent the bank runs itself, whose key
    or token reads only the changes inside the bank's regulatory scope and inside the
    departments and products its agent access entry names; every row it gets is still the
    row everyone gets.

    A change is here while all three are true: the shared library holds it as active (a
    withdrawn or superseded reform has left, whatever its date still says), it carries a key
    date, and that date is today or later. A change registered before anybody published its
    date is absent rather than listed with an empty one. The window's floor is the server's
    own calendar day and not any bank's, so the list really is one list: a newsletter run
    belongs to no bank, and two banks an hour apart must not read two "public" answers.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most; there is no total, so
    a page shorter than `limit` is the end of the list. Nothing dated ahead is a 200 with an
    empty array.

    Errors: `permission_denied` when a session lacks `roadmap.read` or a key lacks
    `upcoming:read`, `unauthenticated` when there is neither, and `validation_error` for a
    `limit` above the maximum or below 1. A query parameter other than `limit` and `offset`
    is ignored rather than refused.
    """
    # Ungated by design: logic-gate (roadmap.read in a tenant, or a key with upcoming:read).
    require_upcoming_reader(request)
    return calendar_reads.list_upcoming(language_order(request), page, reader_of(principal(request)))


@router.get(
    "/calendar-feeds",
    response=list[HomeCalendarFeed],
    auth=SESSION,
    operation_id="listCalendarFeeds",
    by_alias=True,
    summary="See your own calendar subscriptions",
    openapi_extra=_FEEDS_EXAMPLE,
)
@requires_permission(perms.ROADMAP_READ)
@answers_problems
def list_calendar_feeds(request: HttpRequest) -> Any:
    """The calendar subscriptions the caller created, newest first, with when each one was
    last fetched and whether it still works. Call it for the account page where a person
    manages their own subscriptions.

    A read that changes nothing a person asked for. The one write it can make is the server's
    own: a subscription nobody has fetched for `CALENDAR_FEED_IDLE_DAYS` days, or one made
    before the caller was enrolled again, is stopped here, before it is listed, and recorded
    as an audit event with a system actor, once however many reads find it at the same moment
    — exactly what the next fetch of it would have done — so the list never shows as working
    an address that answers 404. A person's session holding `roadmap.read`. The caller's own
    rows only — never another member's and never another bank's — and the address is
    **not** in this answer: it is shown once when the subscription is created and stored
    afterwards only as a lookup prefix and a hash, so a reader must not expect to recover a
    lost address here. Revoking and creating a new one is the way back.

    Every subscription that still works is listed, and beside them the most recently stopped
    `CALENDAR_FEED_REVOKED_SHOWN` (five by default) with the date each stopped, so a person
    can see that an address they pasted somewhere no longer works. The ones the server
    revoked for them — after they lost `roadmap.read`, were enrolled again or let a
    subscription go idle — read the same way as one they revoked themselves. Both halves are
    bounded, so the list is never paged.

    A person with no subscriptions gets a 200 with an empty array, never a 404. Errors:
    `permission_denied` without `roadmap.read`, `unauthenticated` without a session.
    """
    return feed_logic.list_feeds(caller_tenant(request), caller_user(request))


@router.post(
    "/calendar-feeds",
    response={201: HomeCalendarFeedCreated},
    auth=SESSION,
    operation_id="createCalendarFeed",
    by_alias=True,
    summary="Subscribe your calendar to the roadmap",
)
@requires_permission(perms.ROADMAP_READ)
@answers_problems
def create_calendar_feed(request: HttpRequest, body: HomeCalendarFeedInput) -> Any:
    """Mint a calendar address the caller can paste into their own calendar client, so the
    roadmap's dates appear beside their meetings. Call it from the account page when a person
    chooses to subscribe.

    It creates one row in the caller's own bank and writes one audit event through the same
    transaction, recording who subscribed — never the address itself. A person's session
    holding `roadmap.read`, and no API key reaches it. The body carries no fields: every
    subscription carries the same public dates, so there is nothing to choose.

    The session has to be a recent one. A session made within the step-up window, or one that
    has just confirmed a passkey, may subscribe; an older one is refused with
    `step_up_required` and the screen asks for the passkey. The reason is that the address
    outlives the session: a stolen access token expires in minutes, and without this it could
    leave behind a calendar address that keeps answering for months.

    A person keeps at most `CALENDAR_FEEDS_PER_USER` subscriptions at once, which is what a
    phone, a laptop and a work calendar need; asking for one past the cap is refused, and
    revoking one makes room. One nobody has fetched for `CALENDAR_FEED_IDLE_DAYS` days, or
    one made before the caller was enrolled again, is stopped by the server first, with an
    audit event of its own, and never counted, so a person enrolled again after losing their
    devices can subscribe at once. Two calls at once take turns, so they cannot both take
    the last place.

    The address is returned **once**, in `url`, and never again: the server keeps only the
    lookup prefix and a SHA-256 of the secret, exactly as it does for an API key. Treat the
    whole address as a secret. Losing it means revoking the subscription and creating another.

    Errors: `permission_denied` without `roadmap.read`, `unauthenticated` without a session,
    `step_up_required` when the session is neither recent nor freshly confirmed,
    `feed_limit_reached` when the caller already holds `CALENDAR_FEEDS_PER_USER`
    subscriptions that still work — revoke one and ask again — and `validation_error` for a
    field the body does not know, including the `filter` the designed contract once offered,
    which is gone.
    """
    # Not `@requires_step_up`: D-52 asks for a recent sign-in *or* a fresh assertion, which is
    # the same rule the passkey routes use (security review F9). It is a gate and not logic,
    # so it belongs here beside the permission rather than in the module below.
    perms.enforce_recent_sign_in_or_step_up(request)
    user = caller_user(request)
    created = feed_logic.create_feed(
        tenant=caller_tenant(request), user=user, actor=actor_for(request, user), request=request
    )
    return 201, created


@router.delete(
    "/calendar-feeds/{feed_id}",
    response={204: None},
    auth=SESSION,
    operation_id="revokeCalendarFeed",
    by_alias=True,
    summary="Stop a calendar subscription working",
)
@requires_permission(perms.ROADMAP_READ)
@answers_problems
def revoke_calendar_feed(request: HttpRequest, feed_id: uuid.UUID = Path(..., description=_FEED_ID)) -> Any:
    """Switch off one of the caller's own calendar subscriptions. The address stops working
    at once and can never be made to work again; a calendar client that still holds it simply
    stops receiving dates. Call it from the account page's revoke control.

    It stamps the row as revoked rather than deleting it, so the bank can still see that the
    subscription existed and when it stopped, and it writes one audit event in the same
    transaction. A person's session holding `roadmap.read`, acting on their own subscription;
    no passkey step-up and no recent sign-in needed, because revoking is the safe direction
    and a person whose address has leaked must be able to stop it at once.

    The server revokes a subscription by itself on the same terms — when its owner leaves the
    bank, loses `roadmap.read`, is enrolled again, or lets it go idle for
    `CALENDAR_FEED_IDLE_DAYS` days — so a subscription this call finds already revoked may
    never have been revoked by a person at all.

    Answers 204 with no body. Revoking a subscription that is already revoked answers 204 as
    well, so a retry is safe.

    Errors: `not_found` when no subscription of the caller's has that id — including one
    belonging to another person or another bank, answered the same way so no id can be probed;
    `permission_denied` without `roadmap.read`; `unauthenticated` without a session.
    """
    user = caller_user(request)
    feed_logic.revoke_feed(
        tenant=caller_tenant(request), user=user, actor=actor_for(request, user), feed_id=feed_id
    )
    return 204, None


@router.get(
    "/calendar/feed.ics",
    response={200: None},
    auth=None,
    operation_id="getCalendarIcs",
    by_alias=True,
    summary="Fetch a subscribed calendar as iCalendar",
    openapi_extra=_ICS_EXAMPLE,
)
def get_calendar_ics(request: HttpRequest, token: str = Query(..., max_length=FEED_TOKEN_MAX, description=_FEED_TOKEN)) -> Any:
    # Ungated by design: public-token. The revocable token in the address is the whole
    # credential, because a calendar client sends no header and cannot be asked for a passkey.
    """The subscribed roadmap as an iCalendar document, served as `text/calendar` for a
    calendar client to poll. Nobody calls this by hand: the address comes from
    `POST /calendar-feeds` and is pasted into a calendar application.

    A read of public dates: it changes nothing a bank can see and writes no audit row, and the
    response is marked `no-store`. No session and no API key: the token in the query string is
    the credential, which is why the address is shown once, kept only as a lookup prefix and
    the secret's hash, and revocable with immediate effect. It rides in the query string
    rather than the path because our own logs print the route and drop the query, while a
    hosting edge writes whole request lines (D-52).

    The events are the roadmap's regulatory dates — the ones the outside world set, never the
    bank's own deadlines — and only those the source stated to the day, because an all-day
    event on a date published as a month or a quarter would state a day nobody published.
    Each event carries the date, what the date is and the record's title, with the change's
    stable key as its UID, and nothing else. No "So what?", no case note, no owner, no bank
    name: a calendar entry travels to devices and mail clients outside the bank's control, so
    no judgement of the bank's ever goes into one.
    Anyone holding the address can still see which regulatory changes the bank has open work
    on, which is what makes it worth revoking rather than passing on.

    Every fetch checks that the subscription still holds: its owner is still a member of the
    bank, still holds `roadmap.read` and has not been enrolled again since they created it. A
    check that fails revokes the subscription there and then, and one that nobody has fetched
    for `CALENDAR_FEED_IDLE_DAYS` days expires. Fetches are rate limited per token and the
    security log records that a feed was used, never which address was used.

    Errors: `not_found` for a token that is unknown, revoked, expired or no longer served —
    all of them answered identically, so the address never says whether it ever existed;
    `validation_error` when `token` is missing or longer than the limit above; `rate_limited`
    when one address is fetched far more often than a calendar client would.
    """
    return feed_logic.calendar_ics(request, token)
