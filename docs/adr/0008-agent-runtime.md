# ADR 0008 — Agent runtime behind an adapter, the app as scheduler of record

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-08; the owner confirms after the R2 agent chunk)

## Context

Research agents run outside the API and reach it with scoped keys (Solution
Design). Tenant-scoped runs cannot live under a personal account, and the
first candidate runtime, Claude Managed Agents, is in beta; what is known of
it (API-owned sessions, budgets, webhooks, vaults, beta header) comes from
the Compliance Data chat, not from fetched docs (`Verification_Log.md`).

## Decision

An `agent_runner` adapter in `apps/shared/adapters/agent_runner.py` with a
mock for tests and E2E. First real runner: Claude Managed Agents, one session
per run, the app as scheduler of record (schedules, budgets, run rows and
runner events live in `apps/agents`). Fallback: the Agent SDK inside our
worker. Deliberately not done: building either real runner in Phase 0, or
letting the runner own schedules or budgets.

## Consequences

Easier: the runtime can be swapped without touching tenant controls or the
audit trail. Harder: run state is duplicated (ours is the truth, the runner's
is a source of events), which the worker reconciles. To remember: fetch
current Managed Agents documentation before building D-08 and record it;
production refuses `AGENT_RUNNER=mock`.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Adapter interface and mock | Phase 0 |
| 2 | Agent API with keys (runs, checks, register, propose) | Chunk 5 |
| 3 | Definitions, tenant settings, schedules, the first real runner | Chunk 11 |
