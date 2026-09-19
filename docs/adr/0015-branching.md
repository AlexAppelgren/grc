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

## Amendment, 2026-09-19: local worktree branches

Alex asked for sub-agents to work in isolated git worktrees, with the main agent planning
the work, reviewing each result and merging it, in the manner of the superpowers workflow.
This keeps the decision above intact: `main` is still the only branch that is pushed, there
are still no pull requests and no second reviewer before the first real tenant. What changes
is local: each task runs on a short-lived `wt/<task>` branch in its own worktree, and the
main agent squash-merges it into `main` after review, one commit per slice with a playbook
13.4 message. The trigger was concrete: four agents sharing one working tree destroyed each
other's test database mid-run the same day. `docs/runbooks/WORKTREES.md` holds the loop and
`scripts/worktree.sh` the tooling, which gives each worktree its own databases, Redis index
and ports.

## Amendment, 2026-09-19: the real CI runs before `main` moves

Alex asked for work to move off his laptop and into the cloud, to shorten the build without
cutting a corner. The heaviest gates were the local CI mirror's CodeQL, the full E2E suite
and the two container scans, run before every push on a 16 GB machine that also hosts the
parallel worktrees. `main` now reaches GitHub only through `scripts/ship.sh`:

1. The local fast static gates run (`scripts/prepush.sh --quick`: secrets, lockfiles, migration
   drift, lint, types, compliance, requirements and contract checks, OpenAPI drift). The test
   suites, coverage floors, production build, E2E, CodeQL and image scans run in step 3, on
   GitHub's runners, where the whole CI takes about four minutes against more than ten locally.
2. The commit is pushed to `candidate`, a branch that only ever holds the next candidate for
   `main` and is force-pushed each time. It is not the `staging` of tranche 2 above.
3. `ci.yml` and `codeql.yml` are started on `candidate` by hand. A manual run in `ci.yml` is a
   full run: every gate and the full E2E suite.
4. Only when both are green is the same commit pushed to `main`, as a fast-forward.

This is stricter than before, not looser: `main` never holds a commit that the real CI has not
passed, where before it held one that a local mirror of CI had passed. The mirror stays for
anyone who wants it (`scripts/prepush.sh`, `--all`). Still true: `main` is the only branch
that deploys, there are no pull requests, and `wt/*` branches stay local.

The same day Alex approved cloud sessions as build lanes. A cloud session clones GitHub, so
its work comes back on a pushed `claude/<task>` branch, which the main agent reviews,
squash-merges into `main` like a worktree branch, ships, and then deletes. Those branches
never deploy and never trigger CI (`ci.yml` runs on pushes to `main` only).
