# ADR 0045 — The calendar feed carries its secret in the query string and public dates only

**Date:** 2026-09-20 · **Status:** accepted (D-52, Alex 2026-09-19)

## Context

Google adds a calendar by link only if the calendar is public, and Outlook
subscribes only by web address, so a subscribed feed cannot send a header and
the secret has to ride in the URL. That is the class of problem already fixed
for invitation tokens, where the token moved out of the path. Our gunicorn
format and the Sentry scrubber keep query strings out of our own logs, while a
token in the path lands in the hosting edge's HTTP log.

## Decision

The address is `GET /api/v1/calendar/feed.ics?token=<prefix>.<secret>`, 256
bits of secret, stored as a prefix plus SHA-256 and shown once; the path form
is not built. This route is the one named exception to CONVENTIONS 3.6, and a
guard test pins that no other route reads a token from the query string. Any
member with `roadmap.read` creates, lists and revokes their own feeds, up to
`CALENDAR_FEEDS_PER_USER` (5), and creating one needs a recent sign-in or a
step-up so a stolen access token cannot mint a lasting feed.

The feed carries the user's open, in-footprint cases with a day-precision key
date today or later, and every field it emits comes from library columns: the
change title in the user's language, the date label, the authority, the stable
key as the event UID and a link that needs sign-in. It carries no internal
deadline, action title, owner, urgency or So-what text, and a guard test pins
the emitted fields. Token lookup uses the identity-lookup clause, making
`calendar_feed` its fifth table. Unknown, revoked and expired tokens all answer
404. Each fetch checks that the membership is active, still holds
`roadmap.read` and has not been re-enrolled since the feed was created, and
revokes the feed if any check fails; a feed idle for `CALENDAR_FEED_IDLE_DAYS`
(30) expires. Every automatic revocation writes a `record()` row with a system
actor in the same transaction. Addresses are not rotated on a schedule: a
person replaces theirs at will.

This departs from RFC 6750 twice, knowingly: §2.3 discourages the query
method, and §5.3 advises short-lived credentials and keeping them out of URLs.

Deliberately not done: the token in the path with redacted logs, scheduled
rotation, which breaks calendars silently, a token in the fragment or in
Basic-auth, our own deadlines in the feed, per-item downloads instead of a
feed, and one public feed with no token.

## Consequences

Easier: a calendar subscription works in every client without an integration,
and a leaked address exposes public regulatory dates only. Harder: a leaked
address still shows which regulatory changes the bank has open, which the
dialog must say. To remember: a new security-log kind, `feed_used`, is
throttled and records no IP, and on the first test deploy a probe must check
whether the hosting edge's HTTP log includes the query string, with the answer
in the Verification log.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The table, the token, the route, the revocation rules and the guard tests | `c6-upcoming-calendar-backend` |
| 2 | The feeds screen and the dialog's wording | `c6-calendar-feeds-screen` |
| 3 | The hosting-edge log probe and its Verification log row | First test deploy |
