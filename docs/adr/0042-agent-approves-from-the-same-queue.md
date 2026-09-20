# ADR 0042 — The second pair of eyes on a library proposal may be an independent agent

**Date:** 2026-09-20 · **Status:** accepted (owner decision, item 19; D-48, PRD 0.4 PRO-01, PRO-02, INV-05, AUD-02)

## Context

The library is shared by every bank, so a proposal has always been the only
door into it and the proposer has never been allowed to approve their own.
Until now the second principal was a person: the platform role `library_editor`
in the console, staffed by bleqq (D-14).

Alex decided on 2026-09-20 (`docs/plans/briefs/OWNER_RECOMMENDATIONS.md`, item
19) that bleqq staffs no editorial function: "Agents do the work, and there
should be several agents reading the library. A tenant/bank is then responsible
for their interpretation. This doesn't change much, just the edit part in bleqq,
but maybe in the future we would add this on", and "The agent can work from the
queue as well, so who does it doesn't change the function of a queue, it's still
needed."

It builds on two earlier answers. Item 3 had already made the library's error
loop agent-driven: a bank's problem report stays inside the bank, and the watch
agents re-check library records against their sources and file corrections as
proposals (`c5-library-recheck`). Item 14 made bleqq's agents platform-owned and
platform-run. Item 19 removes the last staffed human from that loop, and with
nobody in `library_editor` the queue would otherwise never be emptied.

## Decision

A proposal stays the only door into the library, and four eyes stays a check
constraint that refuses the same principal twice. What changes is who the second
principal may be.

- **The approver.** A person, or an independent agent: a platform API key bound
  to an agent definition that differs from the proposer's definition **and** key.
  The key holds the new scope `proposals:review`, which reaches the queue read
  and the approve, correct and reject routes and no library row. No tenant role
  and no tenant key holds it. `AC-PRO1` is untouched: the agent still writes the
  library only by approving a proposal, through `proposals/apply.py`.
- **One queue.** The confirming agent reads pending proposals through the route a
  person reads them through, and its approval, correction or rejection uses the
  same logic, the same corrections rule (only fields the proposal already
  sources) and the same rejection reasons.
- **The constraint.** `proposal` gains `reviewed_by_api_key`, `proposed_by_agent`
  and `reviewed_by_agent`; the agent columns are copied from the key by the one
  write path. `proposal_four_eyes` is widened to refuse a row whose user, key
  **or** agent is the same on both sides, so two keys of one agent definition
  cannot confirm each other. The database, not Python, stays the word on four
  eyes.
- **The step-up.** A person approving still needs a fresh passkey assertion. A
  key cannot step up and never will, so for an agent approval the scope and the
  constraint are the whole gate, and the assertion id on the audit row is null.
- **Provenance.** A record applied from a proposal an agent confirmed carries
  machine-confirmed provenance, naming the proposing and the confirming agent.
  It never reads as verified by a person until a person verifies it, and the
  re-verification stamp (INV-06) stays a person's act.
- **The console queue is still built**, unchanged in scope: it is where the
  platform watches what the agents decided, takes a proposal over, and where a
  human approver is switched on later with no rework. `library_editor` keeps its
  permissions and is simply staffed by nobody.
- **The bank's side is unchanged.** A bank answers for its own interpretation:
  applicability, compliance status, the "So what?" and sign-off are people's
  decisions in the tenant zone, and no agent approval reaches them.

## Consequences

Easier: the library moves without waiting for a person, which is what a shared
library fed by several agents needs; the queue, its screens and its tests are
built once and serve both kinds of approver; switching a human back on is a
staffing change, not a code change.

Harder: four eyes now means "two independent agents" in the routine case, so the
independence has to be real — different definitions, different prompts, and an
evaluation that measures the confirming agent as the sweeper is measured. The
passkey no longer stands behind every library change, so the scope, the
constraint and the audit trail carry that weight alone.

To remember: an agent approval is a machine judgement labelled as one. The moment
a bank is told a fact was human-verified when an agent confirmed it, the labelling
invariant is broken, which is why the provenance is a column and not a screen
string.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The `proposals:review` scope, the proposal columns, the widened constraint, the approve path for a key, the provenance columns | Chunk 4 (`c4-agent-approver`) |
| 2 | The confirming agent's definition, its prompt rules and its evaluation rows | Chunk 5 |
| 3 | The definition's versioned rows and the console's view of what the confirming agent decided | Chunk 11 |
