"""Request and response schemas of the home app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Plain Pydantic, never `ModelSchema`: most of what these shapes carry is computed rather than
stored, and the three home tables (`briefing`, `briefing_item`, `calendar_feed`) never appear
in a response as themselves.

Nothing here is restated from chunk 5. The lead change and a briefing's items are
`WatchChangeRow`, an urgency is the `LibraryRef` every surface reads a vocabulary row
through, a failed source is `WatchSourceCoverage` and an obligation link is
`WatchObligationLink`. One shape has one owner (API_DOCUMENTATION §4b), and the home screens
read the same rows the watch screens do.

Every property below carries a description saying what the fact means to a bank, which zone
it comes from and what a reader must not conclude from it (Alex's API rule, 2026-09-20).
Three zones appear and they never mix:

- **Library.** Sourced public facts shared by every bank: a change, its key date, its type,
  its authority and its suggested urgency. `GET /upcoming` is nothing but these, which is why
  an agent's key may read it.
- **The bank's own zone.** The case behind a roadmap item, its status and its confirmed
  urgency, the briefing and its snapshot, and the calendar subscriptions of the bank's
  people. Every one of those rows carries a `tenant_id` under row-level security and is
  invisible to bleqq, to every other bank and to every model endpoint (NFR-01, NFR-04, D-07).
- **Computed by the server.** The tenant-local date, a quarter key, the roadmap count and the
  week's lead. None of it is stored, and a caller never sends it.

Limits, in words as well as in the keywords: `GET /upcoming` pages at 20 by default and 100
at most through the shared `limit` and `offset`, and a larger `limit` answers 422 rather than
being clamped (`apps/shared/schemas.py:PageQuery`). No record in this app is versioned, so no
write here takes `If-Match` and none can answer `stale_write`. Nothing here approves, signs
off or exports, so no route takes the passkey step-up those actions need; creating a calendar
subscription is the one write that asks how the caller's session was made, because the
address it mints outlives the session (D-52). A person keeps at most
`CALENDAR_FEEDS_PER_USER` subscriptions, and revoking one is the safe direction. A briefing
snapshot is append-only: once a week's briefing has been sent it is never rewritten, so what
a bank was told is what a bank can reopen.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from ninja import Field
from pydantic import ConfigDict
from pydantic.json_schema import JsonDict

from apps.library.schemas import LibraryRef
from apps.shared.schemas import CamelSchema, PageQuery, WriteBody
from apps.watch.schemas import (
    CHANGE_ROW_EXAMPLE,
    SOURCE_EXAMPLE,
    CaseCategory,
    DatePrecision,
    WatchChangeRow,
    WatchObligationLink,
    WatchSourceCoverage,
)

__all__ = ["CamelSchema"]

# What a roadmap item is about, and what produced its date. Both are tier-one kinds
# (apps/shared/kinds.py): the screen picks its pill from the first and the ICS builder picks
# its summary line from the second, so neither is a list an admin curates. Declared in full
# although R1 fills only `regulatory` / `change_date`, so a client written now does not have
# to change when chunks 8 and 9 add the branches that fill the rest.
RoadmapItemKind = Literal["regulatory", "internal"]
RoadmapItemType = Literal["change_date", "internal_deadline", "action_due", "review_due"]
# Which kinds of dated item the roadmap read includes (`feed_filter`). A calendar
# subscription used to share this choice; D-52 took it away, because a feed carries the
# dates the outside world set and never the bank's own, leaving it nothing to choose.
FeedFilter = Literal["all", "regulatory", "internal"]

# Lengths, not thresholds: they bound a column or a request body, not a decision. The
# "Coming up" length is a decision and lives in settings as `HOME_COMING_UP_ITEMS`.
LABEL_MAX = 300
# A quarter key is `YYYY-Qn`: seven characters, and the longest a caller could send is the
# same seven.
QUARTER_MAX = 7
# The token in a calendar address is `<prefix>.<secret>`: a 16-character lookup prefix, a
# dot, and 256 random bits encoded with `secrets.token_urlsafe` (43 characters), so 60 in
# all. The bound is generous enough for a longer encoding and small enough that no
# unbounded query value is ever parsed (D-52).
FEED_TOKEN_MAX = 128

# ---------------------------------------------------------------------------------------
# The examples more than one schema shows, named once so a screen and its row cannot drift
# apart. Every value is the prototype's own data (a Swedish supervisor, an FI reform, an
# FFFS instrument), never a real customer's. The change row and the source come from chunk
# 5's own examples, so the lead card on Today and the row on the feed show one reform.
# ---------------------------------------------------------------------------------------
ROADMAP_ITEM_EXAMPLE: JsonDict = {
    "id": "change_date:9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46",
    "kind": "regulatory",
    "itemType": "change_date",
    "date": "2026-10-01",
    "datePrecision": "day",
    "quarter": "2026-Q4",
    "label": "In force",
    "title": "FI adopts amended rules on paying for investment research",
    "status": "new",
    "urgency": {"key": "act_now", "kind": None, "label": "Act now"},
    "sourceLabel": "Finansinspektionen",
    "changeId": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
    "obligations": [
        {
            "obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
            "title": "Assess the quality of investment research paid for",
            "instrumentShortName": "FFFS 2017:2",
            "refLabel": "11 kap. 4 §",
            "origin": "agent",
            "confidence": 0.82,
            "confirmed": True,
        }
    ],
}
SOURCE_HEALTH_EXAMPLE: JsonDict = {
    "checked": 11,
    "total": 12,
    "failed": [
        {
            "source": SOURCE_EXAMPLE,
            "lastCheckedAt": "2026-09-16T06:02:00Z",
            "lastStatus": "failed",
            "lastError": "502 from the publisher after three retries",
            "overdue": True,
        }
    ],
}
HOME_EXAMPLE: JsonDict = {
    "date": "2026-09-21",
    "comingUp": [ROADMAP_ITEM_EXAMPLE],
    "roadmapCount": 7,
    "lead": CHANGE_ROW_EXAMPLE,
    "sources": SOURCE_HEALTH_EXAMPLE,
}
BRIEFING_EXAMPLE: JsonDict = {
    "weekStart": "2026-09-14",
    "weekEnd": "2026-09-20",
    "lead": CHANGE_ROW_EXAMPLE,
    "items": [CHANGE_ROW_EXAMPLE],
    "comingUp": [ROADMAP_ITEM_EXAMPLE],
    "emailSentAt": "2026-09-21T05:00:00Z",
}
UPCOMING_ITEM_EXAMPLE: JsonDict = {
    "changeId": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
    "title": "FI adopts amended rules on paying for investment research",
    "keyDate": "2026-10-01",
    "keyDatePrecision": "day",
    "keyDateLabel": "In force",
    "changeType": {"key": "adopted", "kind": "adopted", "label": "Adopted"},
    "authorityLabel": "Finansinspektionen",
    "suggestedUrgency": {"key": "act_now", "kind": None, "label": "Act now"},
    "sourceUrl": "https://www.fi.se/",
}
CALENDAR_FEED_EXAMPLE: JsonDict = {
    "id": "5f1a7c92-0b34-4e86-9d27-3c6a8e1b4f05",
    "createdAt": "2026-09-21T08:15:00Z",
    "lastUsedAt": "2026-09-21T09:40:00Z",
    "revokedAt": None,
}
# The address with its token written as a placeholder rather than as a value of the right
# shape. A realistic-looking one would be exactly what a secret scanner cannot tell from a
# live credential, and an example allowlisted by hand teaches it to ignore that shape.
CALENDAR_FEED_CREATED_EXAMPLE: JsonDict = {
    "feed": CALENDAR_FEED_EXAMPLE,
    "url": "https://app.bleqq.com/api/v1/calendar/feed.ics?token=<prefix>.<secret-shown-once>",
}

# ---------------------------------------------------------------------------------------
# The sentences repeated across these schemas, so one wording cannot drift from another.
# ---------------------------------------------------------------------------------------
_VOCABULARY = (
    "The values are rows an admin manages, not a closed set: a platform admin may extend, "
    "relabel or retire one without a deploy, so read `GET /vocab/{listName}` for the live "
    "set and match on the key, never on the label."
)
_URGENCY = (
    "How soon this needs work, as `{key, kind, label}` from the `urgency` library "
    "vocabulary: `act_now` (something must change within weeks), `within_3_months` (work "
    "must start this quarter), `six_months_plus` (plan it, no rush), `monitor` (nothing to "
    "do yet) and `no_action` (noted, nothing changes) are seeded on day one, in severity "
    f"order. The pill's tone follows the row's ordinal and is never sent here (NFR-03). {_VOCABULARY}"
)
_QUARTER = (
    "The quarter the date falls in, as the key `YYYY-Qn` (`2026-Q4`), computed by the "
    "server in the bank's own time zone — so a date that is 31 December in Stockholm and "
    "1 January in another zone lands in the quarter the bank reads it in. At most 7 "
    "characters. It is a key for grouping and ordering: the screen renders the phrase from its "
    "own catalog, never from this string."
)
_ITEM_KIND = (
    "What the item is about, a fixed kind the screen branches on: `regulatory` (a date the "
    "outside world set, such as a reform coming into force) or `internal` (a date this bank "
    "set for itself, which the screen marks 'Our deadline'). R1 answers `regulatory` only; "
    "the `internal` branches arrive with the register (chunk 8) and the case workflow "
    "(chunk 9). An empty `internal` list means those branches have not shipped, never that "
    "the bank has no deadlines."
)
_ITEM_TYPE = (
    "What produced the date, a fixed kind the calendar builder branches on: `change_date` "
    "(a regulatory change's key date), `internal_deadline` (a deadline the bank set on its "
    "own work), `action_due` (an action's due date) and `review_due` (a next review falling "
    "due). R1 produces `change_date` only; `review_due` arrives with the register (chunk 8) "
    "and `internal_deadline` and `action_due` with the case workflow (chunk 9)."
)


# ---------------------------------------------------------------------------------------
# The roadmap (HOM-03, FP-03)
# ---------------------------------------------------------------------------------------
class HomeRoadmapItem(CamelSchema):
    """One dated thing on the bank's calendar of regulation: what happens, when, and what
    this bank has open against it.

    Two zones in one row. The date, the label, the title and the source are library facts
    shared by every bank; the case status and the confirmed urgency are this bank's own
    judgement and never leave it. A row appearing here means the bank has a case open on a
    dated change — it does not say the obligation applies to the bank, and it says nothing
    about whether the bank complies, which are separate facts in the register (REG-01,
    REG-02).
    """

    model_config = ConfigDict(json_schema_extra={"examples": [ROADMAP_ITEM_EXAMPLE]})

    id: str = Field(
        max_length=LABEL_MAX,
        description=(
            "The item's own identifier, built by the server from the item's type and the "
            f"record behind it and at most {LABEL_MAX} characters. Stable for as long as that "
            "record is on the roadmap, so a screen may key a list on it; it is not a database "
            "id, it is not the change's id (`changeId` is), and nothing may be looked up by it."
        ),
        examples=["change_date:9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46"],
    )
    kind: RoadmapItemKind = Field(description=_ITEM_KIND, examples=["regulatory"])
    item_type: RoadmapItemType = Field(description=_ITEM_TYPE, examples=["change_date"])
    date: datetime.date = Field(
        description=(
            "The day the item falls on, as a plain calendar date (`2026-10-01`) and never a "
            "timestamp, because a legal date is a date and not a moment, and only as exact as "
            "`datePrecision` says. The roadmap shows today and the future; a date that has passed leaves the roadmap and stays on the "
            "change itself."
        ),
        examples=["2026-10-01"],
    )
    date_precision: DatePrecision = Field(
        description=(
            "How exactly the source stated `date`, a fixed kind: `day` renders as 1 October "
            "2026, `month` as October 2026, `quarter` as Q4 2026 and `year` as 2026. A date "
            "stated less exactly than a day is still stored on a day so it can be ordered, and "
            "a reader must render it by this and never print a day, or count the days left to "
            "one, that the source did not state (HOM-03, INV-S10)."
        ),
        examples=["day"],
    )
    quarter: str = Field(max_length=QUARTER_MAX, description=_QUARTER, examples=["2026-Q4"])
    label: str = Field(
        max_length=LABEL_MAX,
        description=(
            f"What the date is, in the source's own words and at most {LABEL_MAX} characters: "
            "'In force', 'Applies', 'Transition ends'. A library fact copied from the change, "
            "so two banks read the same phrase. It is free text a publisher chose, never a "
            "value the system branches on — `itemType` is what code reads."
        ),
        examples=["In force"],
    )
    title: str = Field(
        max_length=LABEL_MAX,
        description=(
            f"What the item is called, at most {LABEL_MAX} characters. For a regulatory item "
            "it is the reform's title from the shared library, in the source's words; an "
            "internal item will carry the name of the bank's own record. It holds no bank's "
            "judgement and is safe to show in a calendar client."
        ),
        examples=["FI adopts amended rules on paying for investment research"],
    )
    status: CaseCategory = Field(
        description=(
            "Where this bank's own work on the item stands, one of the seven fixed categories "
            "the case state machine reads (D-13): `new` (registered, nobody has looked — the "
            "screen reads 'Needs triage'), `assigned` (triaged with an urgency and an owner), "
            "`assessing` (the owner is working out what it means), `implementing` (actions are "
            "open), `signoff` (waiting for a second person), `closed` and `dismissed` (not for "
            "us, with a reason, and restorable). The bank's own zone: another bank's roadmap "
            "shows its own status for the same date. A closed or dismissed item is not on the "
            "roadmap at all, so those two values never appear here in R1."
        ),
        examples=["new"],
    )
    urgency: LibraryRef | None = Field(
        description=(
            f"{_URGENCY} It starts as the agent's suggestion for every bank and becomes this "
            "bank's own at triage; until then a reader must not report it as the bank's "
            "decision. Null when no urgency has been set at all."
        )
    )
    source_label: str = Field(
        max_length=LABEL_MAX,
        description=(
            f"Where the date comes from, in words a reader recognises and at most {LABEL_MAX} "
            "characters: the publisher for a regulatory item, and the bank's own record for an "
            "internal one. A library fact for a regulatory item, so it names no bank."
        ),
        examples=["Finansinspektionen"],
    )
    change_id: uuid.UUID | None = Field(
        description=(
            "The library change behind the item, as a uuid, so the card can link to the change "
            "page. The same identifier for every bank. Null on an internal item, whose record "
            "is the bank's own; null is not 'the change was deleted'."
        ),
        examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"],
    )
    obligations: list[WatchObligationLink] = Field(
        description=(
            "The library obligations this item touches, as the watch feed answers them, most "
            "confident first. Only links a library editor has confirmed appear here, so a "
            "reader may treat each as checked. An empty list means no obligation has been "
            "linked yet, never that the change affects none."
        )
    )


class HomeRoadmap(CamelSchema):
    """`GET /roadmap`: the whole calendar the filters asked for, grouped by the screen from
    the quarter key on every item."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [ROADMAP_ITEM_EXAMPLE], "quarters": ["2026-Q4", "2027-Q1"]}]})

    items: list[HomeRoadmapItem] = Field(
        description=(
            "Every item the filters matched, earliest date first, with the item's own id as a "
            "stable tiebreak so two dates on one day never swap between two reads. The screen "
            "shows them in this order and sorts nothing itself. An empty list is a 200 and a "
            "real answer: it means nothing is dated ahead, not that something failed."
        )
    )
    quarters: list[str] = Field(
        description=(
            "The quarter keys present in `items`, in date order, so the screen can draw the "
            "quarter roster without reading every item first. Computed by the server in the "
            "bank's own time zone. A quarter with no item is absent, so the roster never shows "
            "an empty heading."
        ),
        examples=[["2026-Q4", "2027-Q1"]],
    )


class HomeRoadmapQuery(CamelSchema):
    """The filters of `GET /roadmap`. Every value is a key or a fixed kind, never a label,
    so a filter a person bookmarks keeps working when someone relabels a vocabulary row.

    The three parameters below are all this route reads; a query string carrying any other
    name is ignored rather than refused, so check the spelling against this list when a
    filter seems not to bite. There is deliberately no "show outside our scope" switch here:
    the roadmap and the briefing always respect the bank's regulatory scope, and the
    inventory is where a person looks outside it (FP-03, chunk 6 rulings).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"kind": "all", "from": "2026-10-01", "to": "2027-03-31"}]},
    )

    kind: FeedFilter = Field(
        default="all",
        description=(
            "Which kinds of item to include, a fixed kind with three members and `all` by "
            "default: `all` (both), `regulatory` (dates the outside world set) and `internal` "
            "(deadlines this bank set for itself). `internal` is accepted and answers an empty "
            "list in R1, because the branches that produce our own deadlines arrive with the "
            "register (chunk 8) and the case workflow (chunk 9); an empty answer is a 200 and "
            "never a 422."
        ),
        examples=["all"],
    )
    date_from: datetime.date | None = Field(
        default=None,
        alias="from",
        description=(
            "Show nothing dated before this calendar date (`2026-10-01`), inclusive. A plain "
            "date and never a timestamp. Omit it to start from the bank's own today, which is "
            "what the roadmap screen does; a date in the past widens nothing, because the "
            "roadmap holds no item whose date has gone."
        ),
        examples=["2026-10-01"],
    )
    date_to: datetime.date | None = Field(
        default=None,
        alias="to",
        description=(
            "Show nothing dated after this calendar date (`2027-03-31`), inclusive. A plain "
            "date and never a timestamp. Omit it for everything ahead. A `to` earlier than "
            "`from` matches nothing and answers a 200 with an empty list, which is the honest "
            "answer to a window that holds nothing."
        ),
        examples=["2027-03-31"],
    )


# ---------------------------------------------------------------------------------------
# Today (HOM-01)
# ---------------------------------------------------------------------------------------
class HomeSourceHealth(CamelSchema):
    """How well bleqq's own watching is going: how many registered sources were checked on
    time and which ones were not. Library facts, the same numbers for every bank, and the
    evidence behind "we did not miss anything"."""

    model_config = ConfigDict(json_schema_extra={"examples": [SOURCE_HEALTH_EXAMPLE]})

    checked: int = Field(
        ge=0,
        description=(
            "How many registered sources have a successful check inside their own cadence, "
            "0 or more, counted by the server. It counts sources and not pages, and a "
            "successful check that found nothing new still counts: finding nothing is a result."
        ),
        examples=[11],
    )
    total: int = Field(
        ge=0,
        description=(
            "How many sources are registered and checked automatically, 0 or more. A source "
            "deliberately left alone (a standards publisher whose terms forbid an automated "
            "fetch) is not counted here, so `checked` below `total` always means a real gap."
        ),
        examples=[12],
    )
    failed: list[WatchSourceCoverage] = Field(
        description=(
            "The coverage rows of the sources that are not healthy — the last check failed, or "
            "the source has gone longer than its cadence without a successful one — exactly as "
            "`GET /sources/coverage` answers them. An empty list means every source is inside "
            "its cadence. A source here does not mean a change was missed; it means we cannot "
            "yet say one was not."
        )
    )


class Home(CamelSchema):
    """`GET /home`: everything the timeline home shows, in one call, so the screen never
    chains a second request behind the first.

    Panels a reader may not see are null rather than refused: a person without `watch.read`
    gets a 200 with `lead` and `sources` empty and the screen hides those panels, instead of
    a 403 that would take the whole page away (chunk 6 defaults). Two panels of the design
    are deliberately absent: what needs a decision is the `counts` object on `GET /me` (D-23),
    and the compliance standing arrives with the register in chunk 8, because "0 gaps" before
    a register exists is a false statement about the bank.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [HOME_EXAMPLE]})

    date: datetime.date = Field(
        description=(
            "Today as the bank reads it: the calendar date in the bank's own time zone, "
            "computed by the server. The screen counts 'days left' from this and never from "
            "the reader's device, so two people in different countries see one bank's day."
        ),
        examples=["2026-09-21"],
    )
    coming_up: list[HomeRoadmapItem] = Field(
        description=(
            "The next dates, earliest first: the same rows, in the same order, that "
            "`GET /roadmap` answers, cut to the length the `HOME_COMING_UP_ITEMS` setting "
            "names. The short list is the same on a phone and on a desktop. An empty list "
            "means nothing is dated ahead inside the bank's regulatory scope."
        )
    )
    roadmap_count: int = Field(
        ge=0,
        description=(
            "How many items the whole roadmap holds, 0 or more, so the screen can offer "
            "'see all' with a number. Counted by the server over the same rows as "
            "`GET /roadmap` with no filters, which is why it is usually larger than `comingUp`."
        ),
        examples=[7],
    )
    lead: WatchChangeRow | None = Field(
        description=(
            "The one change of this week that most deserves attention, as the watch feed "
            "answers a row — the most urgent open, in-scope case of the week, with this bank's "
            "own case beside the library's facts. The screen marks it with the `brand` pill "
            "'Lead'. Null when the week has no such change, and null for a reader without "
            "`watch.read`; a reader must not read null as 'nothing happened this week'."
        )
    )
    sources: HomeSourceHealth | None = Field(
        description=(
            "How the source watching is going, for the panel that answers 'are we still "
            "covered?'. Null for a reader without `watch.read`, and the screen then hides the "
            "panel rather than showing zeros, because a zero here would read as a claim that "
            "nothing was checked."
        )
    )


# ---------------------------------------------------------------------------------------
# The weekly briefing (HOM-02, WAT-05, FP-03)
# ---------------------------------------------------------------------------------------
class HomeBriefing(CamelSchema):
    """One week of regulation as it reached this bank: the week's changes inside the bank's
    regulatory scope, the one that leads, and the dates just ahead.

    The running week is computed live and stored nowhere; a past week is read back from the
    snapshot the weekly job wrote when it sent the mail. A snapshot is append-only, so a
    later change to the feed never alters what a person was sent — reopening last week's
    briefing shows last week's briefing. The bank's own zone throughout: another bank's
    briefing for the same week holds different changes, because the scope and the cases are
    its own.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [BRIEFING_EXAMPLE]})

    week_start: datetime.date = Field(
        description=(
            "The Monday of the week, as a plain calendar date (`2026-09-14`), resolved in the "
            "bank's own time zone. The week is the ISO week, Monday to Sunday. This is the key "
            "`GET /briefings/{weekStart}` takes and the one a mailed link points at."
        ),
        examples=["2026-09-14"],
    )
    week_end: datetime.date = Field(
        description=(
            "The Sunday of the same week, as a plain calendar date (`2026-09-20`), computed by "
            "the server so a screen never has to add six days itself. Inclusive: a change seen "
            "on that Sunday is in this briefing."
        ),
        examples=["2026-09-20"],
    )
    lead: WatchChangeRow | None = Field(
        description=(
            "The change the week is about, chosen by the same rule as the lead card on Today, "
            "so the two never disagree. Null in a week with nothing in scope, which is a real "
            "and quiet week rather than a failure."
        )
    )
    items: list[WatchChangeRow] = Field(
        description=(
            "The week's changes inside the bank's regulatory scope, most urgent first and then "
            "by key date, capped at the `BRIEFING_MAX_ITEMS` setting. Each is a watch feed row: "
            "library facts beside this bank's own case. A 'So what?' that no person has "
            "confirmed is still an AI draft and is labelled as one on screen; it is never "
            "carried into the mail (WAT-05)."
        )
    )
    coming_up: list[HomeRoadmapItem] = Field(
        description=(
            "The next dates after the week, the same rows `GET /roadmap` answers, so a reader "
            "leaves the briefing knowing what is about to fall due. An empty list means nothing "
            "is dated ahead inside the bank's scope."
        )
    )
    email_sent_at: datetime.datetime | None = Field(
        description=(
            "When the weekly mail for this week went out, as an RFC 3339 timestamp in UTC "
            "(`2026-09-21T05:00:00Z`). Null on the running week, which is computed live and "
            "has not been sent, and null on a week whose mail failed. It is not the moment the "
            "briefing was read."
        ),
        examples=["2026-09-21T05:00:00Z"],
    )


# ---------------------------------------------------------------------------------------
# Upcoming public facts and the calendar feed (HOM-04)
# ---------------------------------------------------------------------------------------
class HomeUpcomingItem(CamelSchema):
    """One dated change as the outside world may read it. Library facts only: this shape
    holds no case, no footprint verdict, no owner and no "So what?", which is why an agent's
    key and a newsletter may read the list it comes in. Two banks calling `GET /upcoming` get
    byte-identical answers."""

    model_config = ConfigDict(json_schema_extra={"examples": [UPCOMING_ITEM_EXAMPLE]})

    change_id: uuid.UUID = Field(
        description=(
            "The change's identifier in the shared library, as a uuid. The same identifier for "
            "every bank and for every agent, so a newsletter and a bank's screen can point at "
            "one reform."
        ),
        examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"],
    )
    title: str = Field(
        max_length=LABEL_MAX,
        description=(
            f"What the reform is called, in the source's own words and at most {LABEL_MAX} "
            "characters. A library fact: it names no bank and carries no judgement."
        ),
        examples=["FI adopts amended rules on paying for investment research"],
    )
    key_date: datetime.date = Field(
        description=(
            "The one date that puts the change on a calendar — in force, applies, transition "
            "ends — as a plain calendar date (`2026-10-01`) and never a timestamp. Always "
            "present here: a change with no date is not upcoming and is not in this list."
        ),
        examples=["2026-10-01"],
    )
    key_date_precision: DatePrecision | None = Field(
        description=(
            "How exact that date is, a fixed kind: `day` renders as 1 October 2026, `month` as "
            "October 2026, `quarter` as Q4 2026 and `year` as 2026. Null when the source stated "
            "no precision. A reader must render by this and never print a day the source did "
            "not state."
        ),
        examples=["day"],
    )
    key_date_label: str | None = Field(
        max_length=LABEL_MAX,
        description=(
            f"What the date is, in the source's words and at most {LABEL_MAX} characters: 'In "
            "force', 'Applies', 'Transition ends'. Null when the source named the date without "
            "saying what it is."
        ),
        examples=["In force"],
    )
    change_type: LibraryRef = Field(
        description=(
            "What kind of change this is, as `{key, kind, label}` from the `change_type` "
            "library vocabulary: `proposal` (a draft rule; its dates are proposed, not "
            "decided), `adopted` (decided, application still ahead), `supervision` (a survey or "
            "review, no new rule), `enforcement` (a decision against a named firm) and "
            "`recurring_date` (a date that returns) are seeded on day one. The `kind` member is "
            f"the lifecycle kind the rules branch on. {_VOCABULARY}"
        )
    )
    authority_label: str = Field(
        max_length=LABEL_MAX,
        description=(
            f"Who issued the change, as the source writes it, at most {LABEL_MAX} characters. "
            "Always present, even where the library does not recognise the authority, so a "
            "reader always sees who is behind a date."
        ),
        examples=["Finansinspektionen"],
    )
    suggested_urgency: LibraryRef | None = Field(
        description=(
            f"{_URGENCY} It is the agent's suggestion for the whole library and not any bank's "
            "decision; a reader outside a bank must not present it as one. Null when no "
            "suggestion was made."
        )
    )
    source_url: str = Field(
        max_length=2000,
        description=(
            "The public page the change was found on, as a URL of at most 2000 characters, so "
            "a reader can open the publisher's own words. Always a public address: no source "
            "in the library sits behind a login."
        ),
        examples=["https://www.fi.se/"],
    )


class HomeUpcomingQuery(PageQuery, CamelSchema):
    """The paging of `GET /upcoming`, carrying the shared `limit` and `offset`: 20 by default,
    100 at most, and a larger `limit` answers 422 rather than being clamped. The list is
    ordered by date and carries no total, so a page shorter than `limit` is the end of it.

    `limit` and `offset` are all this route reads; any other name in the query string is
    ignored rather than refused. There is no filter here on purpose: this is the public
    list, the same for everyone, and narrowing it per bank would make it a tenant read."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"limit": 20, "offset": 0}]})


class HomeCalendarFeed(CamelSchema):
    """One calendar subscription belonging to one person in one bank. The bank's own zone:
    a person sees their own subscriptions and nobody else's, and the address itself is never
    in this shape — it is shown once, when the subscription is created, and stored afterwards
    only as a lookup prefix and the secret's hash.

    Every subscription carries the same thing, so there is nothing to choose between: the
    dates the outside world set on the changes this person's bank has open work on. The
    bank's own deadlines never reach a calendar a provider outside the bank can read
    (D-52, AC-TEN1)."""

    model_config = ConfigDict(json_schema_extra={"examples": [CALENDAR_FEED_EXAMPLE]})

    id: uuid.UUID = Field(
        description=(
            "The subscription's identifier, as a uuid, which `DELETE /calendar-feeds/{feedId}` "
            "takes. It is not the secret in the address and reveals nothing: knowing it does "
            "not let anyone read the calendar."
        ),
        examples=["5f1a7c92-0b34-4e86-9d27-3c6a8e1b4f05"],
    )
    created_at: datetime.datetime = Field(
        description=(
            "When the person created the subscription, as an RFC 3339 timestamp in UTC "
            "(`2026-09-21T08:15:00Z`). Set by the server; a caller never sends it."
        ),
        examples=["2026-09-21T08:15:00Z"],
    )
    last_used_at: datetime.datetime | None = Field(
        description=(
            "When a calendar client last fetched this subscription, as an RFC 3339 timestamp "
            "in UTC (`2026-09-21T09:40:00Z`), or null while nothing has fetched it yet. Set by "
            "the server and stamped at most once every few minutes, so it says whether the "
            "address is in use, never exactly how often. It is also what the idle expiry "
            "reads: a subscription nobody fetches for `CALENDAR_FEED_IDLE_DAYS` days stops "
            "working. Null on a subscription made minutes ago is normal; null on an old one "
            "means the address was never pasted anywhere."
        ),
        examples=["2026-09-21T09:40:00Z"],
    )
    revoked_at: datetime.datetime | None = Field(
        description=(
            "When the subscription stopped working, as an RFC 3339 timestamp in UTC "
            "(`2026-09-22T09:00:00Z`), or null while it still works. Revoking is immediate and "
            "final: the address answers 404 from that moment, and a new subscription is the "
            "only way back. The person's own revoke is one way in; the server stamps this "
            "itself when they leave the bank, lose `roadmap.read`, are enrolled again or let "
            "the subscription go idle, so a date here that nobody set by hand is one of those. "
            "The row is kept rather than deleted, so the bank can see that the subscription "
            "existed and when it stopped."
        ),
        examples=[None],
    )


class HomeCalendarFeedInput(WriteBody):
    """`POST /calendar-feeds` (HOM-04): a person subscribes their own calendar client to the
    bank's roadmap.

    The body carries no fields, and that is the whole shape: every subscription carries the
    same public dates, so there is nothing to ask for. It is still a declared body rather
    than none, because a field this shape does not name answers 422 — a client written
    against the designed contract, which offered a `filter` of `all`, `regulatory` or
    `internal`, is told that the choice is gone instead of quietly subscribing to something
    else (D-52).

    No `If-Match`: the subscription carries no version. No passkey step-up either, but the
    caller's session must be young or have stepped up recently, because the address this
    mints outlives the session that asked for it."""

    model_config = ConfigDict(json_schema_extra={"examples": [{}]})


class HomeCalendarFeedCreated(CamelSchema):
    """`POST /calendar-feeds` answers this once and never again: the subscription and the
    address that carries its secret. The address is shown once, copied into a calendar client
    and stored here only as a lookup prefix beside the secret's SHA-256, exactly as an API key
    is (ID-10). Losing it means revoking the subscription and creating another."""

    model_config = ConfigDict(json_schema_extra={"examples": [CALENDAR_FEED_CREATED_EXAMPLE]})

    feed: HomeCalendarFeed = Field(
        description="The subscription that was just created, exactly as `GET /calendar-feeds` lists it afterwards."
    )
    url: str = Field(
        max_length=2000,
        description=(
            "The full address to paste into a calendar client, as a URL of at most 2000 "
            "characters, ending `/calendar/feed.ics?token=<prefix>.<secret>`. The token in the "
            "query string is the only credential the feed has, because a calendar client sends "
            "no header and cannot be asked for a passkey; treat the whole address as a secret, "
            "never post it anywhere and never log it. Anyone holding it can see which "
            "regulatory changes the bank has open work on, which is why revoking is one call "
            "away. It appears in this one response and in no other: the server keeps only the "
            "prefix and a hash of the secret."
        ),
        examples=["https://app.bleqq.com/api/v1/calendar/feed.ics?token=<prefix>.<secret-shown-once>"],
    )
