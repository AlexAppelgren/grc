# ADR 0027 — Participants, departments and one My work service

**Date:** 2026-09-19 · **Status:** accepted by default (D-18 to D-21, D-23 to D-26, PRD 0.3 HOM-05, COL-04; the owner confirms)

## Context

Alex asked for one page of what a person is responsible for or takes part in,
for adding a participant to an inventory item or an upcoming change, and for a
department head's view of the department. Four phrases in the product ("my open
items", "my work", "what I own", "what needs me") had no single definition.
The designed schema already has org units with a head above teams, and
`membership` already has a `(tenant_id, user_id)` unique key. PostgreSQL
foreign-key checks bypass row-level security, so only composite keys make a
cross-tenant row impossible. All of this is about attention, not access.

## Decision

A participant is a tenant row naming a person or a team on a register entry or
a case, with composite foreign keys, removed softly, granting nothing; adding
needs the permission that already edits the record, and anyone may leave their
own row. A department is the org unit of kind business area, business unit or
function with a head, and teams belong to it; the department view is a filter
any member may open, and team leads are not built. My work is one ORM service
under row-level security with two reasons (owner, participant) and four buckets
(overdue, due soon, changes on your items, everything else); every row and
every count comes from the permission-filtered set, and the page, the
reminders, the digest and the member-removal preview all read it. It does not
apply the regulatory scope. Decisions stay on Today's Decide now. "Changes on
your items" means a person-confirmed link to an involved obligation, or a
version applied within the awareness window.

Deliberately not done: a database view, a per-person strip, footprint marking
on My work, participant roles, "affecting" by impact, keyset pagination, and
any of it before chunk 8.

## Consequences

Easier: one definition of open items for the page, the digest, the reminders
and the removal preview; the PRD §6 permission matrix is unchanged; a person
never loses sight of their own work after a scope change. Harder: a union over
about ten sources expanded to every department member can breach the 250 ms
budget without indexes and a pinned query count, and cross-tenant ids need
composite keys, loading under RLS and route-isolation entries, each with its
own test. To remember: a change nobody attaches to a department's people or
teams will not show on its view, and a person in no team under a department
does not appear there.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Departments with heads, teams in them, team membership, the people reference | Chunk 8 |
| 2 | The participant table, its logic and the obligation routes and panel | Chunk 8 |
| 3 | My work v1 with the register sources, buckets, the route and the screen; J-9 | Chunk 8 |
| 4 | Case participants, contributor teams as participants, case sources | Chunk 9 |
| 5 | Comments and mentions on My work, reminders, escalation, the digest | Chunk 10 |
