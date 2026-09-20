"""Upcoming public facts and the revocable calendar feed (HOM-04).

Two different things live here because they answer the same question to two audiences.
`GET /upcoming` is the library's dated changes with nothing of any bank in them, which is
why an agent's key may read it. The calendar feed is one person's subscription in one bank,
whose address carries the only credential a calendar client can send.

The contract is declared ahead of the logic (chunk 6 plan rule 3), so every function here
answers 501 `not_built` behind the route's real gate. `c6-upcoming-calendar-backend` fills
`list_upcoming()` first; the feed half waits for the open question q-feed-token, which asks
Alex whether a secret may sit in a path that every access log writes down.

`GET /calendar/{feedToken}` looks nothing up until then: the route answers 501 before any
token is read, so no timing, no log line and no error tells a caller whether a token exists.
"""

from __future__ import annotations

from typing import NoReturn

from apps.home.logic import not_built


def list_upcoming() -> NoReturn:
    """`GET /upcoming`. Built by `c6-upcoming-calendar-backend`."""
    not_built("The list of upcoming changes is not built yet.")


def list_feeds() -> NoReturn:
    """`GET /calendar-feeds`. Built by `c6-upcoming-calendar-backend`."""
    not_built("Calendar subscriptions are not built yet.")


def create_feed() -> NoReturn:
    """`POST /calendar-feeds`. Built by `c6-upcoming-calendar-backend`."""
    not_built("Calendar subscriptions are not built yet.")


def revoke_feed() -> NoReturn:
    """`DELETE /calendar-feeds/{feedId}`. Built by `c6-upcoming-calendar-backend`."""
    not_built("Calendar subscriptions are not built yet.")


def calendar_ics() -> NoReturn:
    """`GET /calendar/{feedToken}`. Built by `c6-upcoming-calendar-backend` once q-feed-token
    is answered. It reads no token and touches no row while it answers 501."""
    not_built("The calendar feed is not built yet.")
