# ADR 0059 — Agent definitions are platform configuration, not library rows

**Date:** 2026-09-25 · **Status:** accepted (owner decision, 2026-09-25: "Platform config"; D-102; PRD AGT-03, ADM-02; follows ADR 0053 and ADR 0058)

## Context

The console must publish and retire a version of one of bleqq's agents and change the
cadence, jurisdictions and budget it runs with (AGT-03, ADM-02). `agent` and
`agent_version` were built as `LibraryModel`s, because they hold no tenant and every
bank's runs read them. The library fence (`apps/shared/tests_library_fence.py`) lets a
route reach a library write only as a proposal's approval, the re-verification stamp or
the watch door, so `c11-definitions-platform` stopped with the three writes built and red
on the fence, and asked how the console may write an agent definition: a named exception
beside the stamp, or a proposal kind with four eyes.

## Decision

Neither. An agent definition, its versions and its platform settings are **platform
configuration**: what bleqq runs, not a sourced fact about the law. Nothing in them enters
the inventory and no bank reads them as a fact, so the invariant that proposals are the
only door into the library does not reach them, and CLAUDE.md section 5 gains no exception
line.

- **Three routes write them.** `publishAgentVersion`, `retireAgentVersion` and
  `updatePlatformAgentSettings`, each behind the platform permission
  `agent_definitions.manage` (no tenant role holds it, the role editor refuses it, no key's
  principal passes it), a fresh passkey step-up and a person's session. Each leaves one
  `record()` row with no tenant and the step-up assertion, in the write's transaction.
- **One writer each.** `agents/seeds/console.py` holds `publish`, `retire` and
  `set_platform_settings`, named only by the logic of their route. Validation, permission
  and audit are the caller's; the writer writes rows.
- **The fence names them once.** `PLATFORM_CONFIGURATION` lists `Agent` (agent
  definitions, and the platform agent settings each carries) and `AgentVersion` (agent
  versions); `PLATFORM_CONFIGURATION_ROUTES` names the one writer each route may reach.
  `PlatformConfigurationGuard` proves the gate of every route, that the writers are reached
  from nowhere else, that the console module names no other library model, and, on planted
  inputs, that another model, another route, a proposal kind reaching a console writer, or
  a new watch write module is still refused. Every other rule of the fence is unchanged.
- **The machinery stays.** The rows remain `LibraryModel`s: a write outside
  `library_write()` is refused in Python, and one outside a door is refused by the
  database (ADR 0058). The console opens the reference seed's door, which the seed beside
  it already uses to load the shipped definitions.

## Consequences

Easier: the console publishes, retires and configures bleqq's agents without a queue that
nobody staffs, and the proposal door keeps meaning exactly what it did.

Harder, and accepted: a single platform administrator with a fresh passkey changes what
runs for every bank, with no second pair of eyes. The audit row names the person, the
before and after, and the assertion. The database's `seed` door accepts every inventory
table, so what keeps the console to agent rows is the fence, not the trigger; a door of its
own, accepted by `agent` and `agent_version` alone, is a later hardening
(`docs/TODO_FOR_alex.md`, c11-agent-config-platform).
