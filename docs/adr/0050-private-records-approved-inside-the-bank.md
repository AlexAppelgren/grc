# ADR 0050 — A bank's private records are proposed and approved inside that bank

**Date:** 2026-09-20 · **Status:** accepted (D-57, Alex 2026-09-19; PRD 0.4 INV-07, PRO-03, WAT-06, §6)

## Context

INV-07 and WAT-06 let a bank hold instruments, obligations and sources of its
own. The proposal queue is the only door into the library and it lives in the
platform console, so the obvious design has a library editor approving a bank's
private records: that would need a platform bypass into tenant rows and would
put bank-confidential material in front of bleqq staff. The invariants that
must survive are the proposal door, four eyes, and "tenant content never
reaches an unapproved model endpoint".

## Decision

Private records stay in the bank. A compliance officer proposes, and a second
person in the same bank approves with a passkey under a new tenant permission,
`private_records.approve`, granted to Compliance officer and Approver and never
a platform grant or an API key scope. `POST /private-proposals/{id}/approve`
and `/reject` take a person's session, the permission and a step-up, and run
the same approve and apply code, the same four-eyes constraint and the same
standards checks as shared proposals, writing audit and outbox rows in the
tenant zone through `record()`. `ProposalDoorGuard` names exactly three routes
that write the library. The server sets `proposal.owner_tenant_id` from the
target — the active tenant for a private-record kind or an owned target, NULL
otherwise — and never from the request body, so a shared proposal filed from a
bank still reaches the console. Forced row-level security on `proposal` covers
reads of shared rows and the bank's own, inserts of either, and updates and
deletes within the session's own zone; each library child table gains a FOR
SELECT policy where the parent is visible and a FOR ALL policy where the
parent's owner is the session tenant, so a bank cannot write a child row under
a shared parent.

No owned row, and no child of one, is indexed, embedded, reranked or sent to a
model; private changes get no AI-drafted "So what?"; find-similar returns
shared records only. A private source is requested by a member with
`agents.manage` or `proposals.create`, writes one tenant audit row, and is
checked at the request for https, no credentials in the URL, a public host, not
a standards publisher's host, not an existing shared source (409) and a cap of
`PRIVATE_SOURCES_MAX`; the host is re-checked at the start of each run. Two
cuts are stated openly: a private instrument holds no provisions in R3, and a
private source is a public page, so internal documents wait for a model
decision.

Deliberately not done: a library editor approving private records in the
console, direct writes by one member, giving tenants `proposals.review` or
reusing `applicability.approve`, and separate tenant tables.

## Consequences

Easier: private records need no exception to the two-zone rule, the search
fence or the model rules, because they are simply tenant content. Harder: a
second approval route to keep in step with the shared one, and child-table
policies on four more tables. To remember: if R3 runs short, the cheaper
fallback is to cut private instruments and obligations, which are a Could, and
ship private sources only, which still needs the watch child-table policies.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The permission, proposal ownership, the approval routes and the four-eyes tests | `c13-private-contract` |
| 2 | Row-level security on the library and watch child tables | The child-table package beside it |
| 3 | Private sources and their per-run host check | `c13-private-obligations` and the watch packages |
