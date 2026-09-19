# ADR 0015 — One branch during the build, staging and main before the first real tenant

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-15; the owner decides when to switch)

## Context

During the build one person deploys `main` to a test environment and speed
matters. A bank's vendor review will expect change control on production: a
second reviewer and a promotion step. Playbook Section 12 describes both
phases.

## Decision

Now: all work committed directly to `main` in small commits per whole slice,
each passing the pre-push checklist; no feature branches, no branch guard.
Before the first real tenant: `staging` auto-deploys, `main` is production
and is merged only from `staging` after the owner approves, enforced by
`main-branch-guard.yml`, with a second reviewer on production changes. That
switch is recorded in an ADR that supersedes this one. Deliberately not
done: feature branches and pull requests during the build.

## Consequences

Easier: no merge queue while one agent builds. Harder: a red `main` is a
red test deploy, so the checklist runs before every push. To remember: the
switch, the branch guard and the reviewer rule belong in one ADR.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | `main` only, CI on push | Phase 0 |
| 2 | `staging`, branch guard, second reviewer | Before the first bank tenant |
