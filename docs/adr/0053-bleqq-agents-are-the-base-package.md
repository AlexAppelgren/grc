# ADR 0053 — bleqq's agents are the base package; a bank steers only its own

**Date:** 2026-09-20 · **Status:** accepted (D-61, Alex 2026-09-19; PRD 0.4 AGT-03, AGT-04, AGT-05)

## Context

AGT-04 read as though every agent had tenant controls: on and off, cadence,
scope, pause, budget cap and an AI off switch. But the general
financial-regulation watch is what banks buy: it feeds the shared library that
every tenant reads, and from D-50 it also re-checks the library against its
sources. A bank that could pause it would silently stop its own regulatory
coverage, and an agent a bank steers must not be able to write facts every
other bank reads. Alex settled this in his own words: the general agents bleqq
provides are part of the base package and are not changeable by the tenant,
while a tenant may add its own agents for what it needs.

## Decision

bleqq's agents are platform-owned and platform-run. No tenant switches one off,
pauses it, changes its cadence, scope or budget, or edits its definition; their
versioned definitions stay the platform's under AGT-03, and their runs are
library runs opened by a platform key. A bank adds agents of its own for the
things it must watch, and AGT-04's controls — on and off, cadence, scope, run
now, pause, interrupt, history with findings and cost, monthly budget cap and
the AI off switch — apply to those alone. A tenant's own agent writes only in
that bank's zone: it may register nothing in the shared library, and what it
finds becomes the bank's own private records (ADR 0050) or nothing. AGT-05's
research requests follow the same line: a bank asks its own agents to check a
source or research a topic, while re-tagging library records is asked in the
platform console.

Deliberately not done: a tenant switch that would pause a platform agent for
that bank, a per-tenant cadence on a platform agent, and any path by which a
tenant-steered agent writes the shared library.

## Consequences

Easier: the platform's coverage is the same for every bank, so a missed change
can never be explained by one bank's settings, and the library fence needs no
new case. Harder: a bank that wants a different cadence on the general watch
cannot have one, and the agent screens must separate "bleqq's agents", shown
read-only with their history, from "our agents", which the bank controls. To
remember: two details are open (D-61): whether a tenant's AI off switch touches
only its own agents and AI features, and who pays for a tenant's agents.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The watch agents as platform-owned runs, with no tenant control | Chunk 5 |
| 2 | A tenant's own agents, their controls and their own-zone writes | Chunk 11 |
| 3 | The agent screens, split into bleqq's agents and the bank's own | Chunk 11 UI |
