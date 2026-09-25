# ADR 0061 — A bank's capped research text may reach its own agent, the second exception beside Ask

**Date:** 2026-09-25 · **Status:** accepted (Alex, 2026-09-25, owner question "May text a bank types for its own agents reach a model?": "yes, guarded, as the default says"; D-98; amends D-07 and D-32; PRD 0.7 OWN-02, AGT-04, AGT-05; follows ADRs 0057 and 0059)

## Context

D-07 lets one piece of a bank's text reach a model: the question typed into Ask, which a
bank can switch off. ADR 0057 said what that always meant, that **we** send no tenant-zone
text to a model except Ask's question. D-32 said the same for a bank's own agents:
jurisdiction keys may reach the tenant-scoped runner, tenant text never does.

R2 gives a bank two things it writes for its own agents. A D-89 scope item names a
regulation the shared library does not cover, with its official reference and the public
addresses to research (OWN-01, OWN-02, ADR 0059), and AGT-05's "research a topic" is a
bank describing what it wants its agent to look into. Keys alone cannot say either: a
regulation the library does not hold has no key yet, which is why the bank added it by
name. ADR 0059 built the keys-only path and left the question open, and the R2 plan asked
it of Alex with a guarded default.

## Decision

A bank's research text may reach its own agent's model: the **second named exception**
beside Ask. The text is the bank's own description of what to look for, sent by us, so it
is fenced as tightly as Ask's question and more.

**What the exception covers, and nothing else.**

- A scope item's name, its official reference and its public source addresses, and the
  topic of an AGT-05 research request. Nothing else a bank writes: not a note, an
  assessment, a case, a register decision, a scope item other than the one researched, or
  any of the bank's own records (D-57 stands whole: a private record never reaches a model).
- Beside them, the keys a run was always allowed: the scope item's id and its jurisdiction
  and regime term keys, or the request's library and taxonomy keys.

**The guards, every one required.**

1. **Length-capped.** Each text field is cut to its cap, a setting with an environment
   override, before it leaves the worker. A structured field stays structured: the input is
   named fields, never a free-form prompt the bank composes.
2. **Screened as untrusted.** The text is treated as fetched content is (AGT-07): screened
   for embedded instructions, never followed, and it widens neither the sector scope, the
   agent's tools nor its budget.
3. **Only through the logged wrapper** (`apps/shared/ai.py`, which writes the
   `ai_generation` row through `apps/governance/ai_log.py`), **to an approved EU
   endpoint** (D-54). No other path sends it anywhere.
4. **Stopped by the bank's AI switch and its budget cap.** With `tenant.ai_enabled` off
   the bank's own agents do not run and the text reaches no model; at the monthly cap the
   run does not start or is interrupted (AGT-04).
5. **Never logged.** Not in a log line, Sentry, analytics, an audit summary or an outbox
   payload; the model-call row keeps a hash and a template name, never the prompt.
6. **Never in a platform run.** Only a run of the bank's own tenant-scoped agent carries
   it; bleqq's agents, which feed the shared library, never read a bank's text, so a bank's
   plans cannot steer or leak through the library (D-32's reason, kept).

**Where it lands.** The first definition that takes it is `scope-researcher` v1
(`backend/agents/scope-researcher/v1/definition.yaml`), whose `inputs` block names the
three fields and the keys, each text field capped and untrusted, and whose tools write
nothing: its findings leave the run only as runner events (ADR 0059).
`d89-agent-research` builds the input and proves the guards for a scope item, and
`c11-research-requests` for a topic.

So D-07 reads: **we** send no tenant-zone text to a model except Ask's question and a
bank's capped research text for its own agent, each of which the bank can switch off.
D-32 reads: jurisdiction keys and, under this ADR, the research text may reach the
tenant-scoped runner; no other tenant text does. ADR 0059's "only the item's term keys and
the pages fetched from its public addresses reach one" becomes "the item's keys, its capped
name, reference and addresses, and those pages", and AGT-S16's model-input line moves with
it when `d89-agent-research` un-skips it.

Deliberately not done: a free-text field beyond the three named ones, any of the bank's own
records as input, the text in a platform run, a non-EU or unlogged endpoint, a way around
the AI switch, and the text reaching the search index or an embedding.

## Consequences

Easier: a scope item names what keys cannot, so the bank's agent can find a regulation the
library has never held, and a bank can ask a question in words. Harder: every builder of a
tenant run's input now carries six guards and their tests, and the text is a new injection
surface, which the screen and the named-field input contain. To remember: Ask is no longer
the only exception, so any third one is a decision of its own, never a widening of this
one.
