# ADR 0059 — A bank researches what the library does not cover, and decides it inside the bank

**Date:** 2026-09-25 · **Status:** accepted (D-89, Alex 2026-09-24; the details answered by default in D-91; PRD 0.7 OWN-01 to OWN-05, INV-07, AGT-04, AGT-05, PRO-03, AC-OWN1, AC-OWN2, J-12; amends ADR 0050's staging and ADR 0053's second tranche)

## Context

Alex decided on 2026-09-24 (D-89): "an agent can always add things to the library, and
then another agent can verify it, its then up to the tenant to decide if they want to use
it or not", and "The previously called 'footprint' can not be agent managed, only a
tenant admin can add things that the agents should look out for or regulations that apply
to them". He also decided that a bank's people may add to its regulatory scope a
regulation or area the shared library does not yet cover, that the bank's own agents then
research it and fill the bank's own library zone with regulation and control inventories
as proposals, and that the bank's people approve or reject them the way the shared queue
works. It is planned with R2.

Three existing rulings stood in the way. ADR 0050 staged a bank's private records in
chunk 13 (R3) and built them around a bank's own private sources. Chunk 11's ruling 2
(`CHUNK11_TASKS.md`) said a tenant agent's findings are run findings in R2, not records,
because private records were chunk 13. And a bank's API key writes nothing to the watch or
the proposal queue (`runs.refuse_tenant_key`, `tenant_agents_not_available`), which is what
keeps a tenant-steered agent from ever writing facts every other bank reads.

## Decision

**A scope item is a regulatory scope change.** A person holding `footprint.request` asks
for it (a name, jurisdiction and regime terms, an official reference where one exists,
the public source addresses to research), and a different person holding
`footprint.approve` approves it with a passkey, through the same request, the same
four-eyes constraint and the same step-up as any other regulatory scope change. No API key
reaches it and no agent writes one. Approving an item widens no term of the scope: it is a
thing the bank's agents look out for, not a term records are matched against.

**The bank's own agent researches it.** An approved item opens a research request (AGT-05)
for the bank's own agent, a bleqq-authored tenant-scoped definition the bank switched on
under AGT-04 (chunk 11's ruling 1 stands: the definition is always bleqq's).

**The channel is the runner, never a key.** The worker opens the tenant run with no API
key and starts it through the `agent_runner` adapter. What the run finds reaches the bank's
queue only as **runner events**, validated at the boundary and applied in the worker, each
proposal written with `owner_tenant_id` taken from the run and never from the event. No API
key gains a proposal scope, `refuse_tenant_key` is unchanged, and a bank's key still writes
nothing to the watch or the queue. A runner event naming a shared library record, the
regulatory scope or a re-tag is refused and nothing is stored.

**The agent never reads the bank's own records back (D-57).** A proposal duplicating, by
official reference, a record the bank already holds answers 409 `already_in_our_library`,
checked by the server. Until Alex answers whether a bank's typed text may reach a model,
only the item's term keys and the pages fetched from its public addresses reach one; the
item's name and the bank's own records never do (D-32 as written).

**The bank decides inside the bank.** The proposals wait in the bank's own queue, and a
person holding `private_records.approve` approves with a passkey or rejects with a reason,
never the proposer, through ADR 0050's approval routes, apply code and four-eyes
constraint. An agent never confirms a bank's own record. What is approved reads "Private to
us", only to that bank, and is never indexed, embedded, reranked, sent to a model, read by
an agent access credential or shown in a support session. The register decides it as it
decides a shared obligation. When the shared library later covers the same regulation,
nothing changes automatically.

So this ADR:

- pulls ADR 0050's tranches 1 (the permission, proposal ownership, the approval routes and
  the four-eyes tests) and 2 (row-level security on the library child tables) into R2,
  chunk 11; tranche 3, a bank's private sources and their per-run host check, stays in
  chunk 13 (WAT-06, R3);
- supersedes chunk 11's ruling 2 for OWN: a tenant agent's findings for a scope item become
  the bank's own proposals, not run findings alone;
- keeps D-57 whole: a private record is never sent to a model, and a bank's own agent is a
  model;
- leaves D-07 and D-32 open: nothing here decides whether a bank's typed text may reach a
  model.

Deliberately not done: an agent writing or approving a scope item, a tenant API key with a
proposal scope, a tenant-authored agent definition, an agent confirming a bank's own
record, a bank's own record reaching the console, and any automatic link or merge with a
shared record that later covers the same regulation.

## Consequences

Easier: the feature needs no new door. The regulatory scope request, the four-eyes
constraint, the step-up, ADR 0050's approval routes and the runner adapter each already
exist or are already planned, and the runner-event channel means the key-based fences need
no exception. Harder: ADR 0050's tranches and the child-table policies move a release
earlier, the runner's event handling becomes a write path that must validate every event,
and a bank reading its own record beside a shared one that later covers the same rule must
reconcile them by hand. To remember: OWN-05's control inventory waits for Alex's answer on
what a control holds (D-91), and D-07's answer may later let the item's name reach the
bank's own agent.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The scope item on the regulatory scope request (FP-S18) | Chunk 11 |
| 2 | ADR 0050's tranches 1 and 2: ownership, the bank's own queue, child-table policies (PRO-S12, PRO-S15, INV-S9, INV-S13, INV-S15) | Chunk 11 |
| 3 | The research request and the runner-event write path (AGT-S14, AGT-S16) | Chunk 11, with the runner adapter |
| 4 | The register on the bank's own obligations and their controls (REG-S17), then J-12 (FP-S19) | Chunk 11, after chunk 8's register |
