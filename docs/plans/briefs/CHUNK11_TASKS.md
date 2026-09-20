# Chunk 11: tasks

Chunk 11 (tenant-controlled agents, AGT-03 to AGT-06) is **not planned yet**. Its packages live
in `docs/plans/PARALLEL_PLAN.md` section 3.3, and the shape Alex's decisions of 2026-09-20 gave
them is in sections 3.3.1 (item 14, platform-owned agents) and 3.3.2 (item 19, the confirming
agent). This file exists to hold the notes written before the plan, so the session that plans
chunk 11 starts from them instead of rediscovering them. It is not a task list, and nothing here
is dispatchable.

## Noted 2026-09-20: the confirming agent (item 19, D-48, ADR 0042)

bleqq staffs no editorial function, so the second pair of eyes on a library proposal is usually
an independent agent: a platform key bound to its own definition, holding the scope
`proposals:review`, working the same queue a person works (chunk 4, `c4-agent-approver`). Its
definition, prompt and evaluation land in chunk 5. What falls to chunk 11:

- `c11-agent-definitions-contract` versions the confirming agent's definition exactly as it
  versions the sweeper's: platform-owned rows, published under `agent_definitions.manage`, one
  audit row per publish, no tenant route reaching a definition in any release. The confirming
  agent is not a special case and needs no column of its own; what it may decide is its scope and
  its prompt, not a flag on the definition row.
- `c11-platform-agent-settings` carries its cadence and budget as platform rows, like the other
  bleqq agents. A tenant cannot switch it off, pause it, or change what it reviews.
- `c11-fe-console-agent-definitions` shows what it decided: the console's agent view links to the
  proposals it approved, corrected or rejected, which is the audit trail chunk 4 already writes.
  This is the surface Alex watches the agents from, beside the queue itself.
- `c11-platform-watch-read` — what a bank may see of bleqq's agents — must answer for the
  confirming agent too. **Open for Alex** (`docs/TODO_FOR_alex.md`): whether a bank may see which
  agent confirmed a fact. The default the build takes until he says otherwise is yes: the record's
  provenance names the proposing and the confirming agent, as it already names an agent proposer.
- Nothing about a **tenant's own** agents changes. A tenant agent writes only its own zone, never
  the library, and no tenant key ever holds `proposals:review` (item 14, ADR 0042).
