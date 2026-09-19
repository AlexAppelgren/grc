# Worktrees and the sub-agent loop

How the main agent runs parallel sub-agents without them breaking each other's work.
Adopted 2026-09-19 at Alex's request, modelled on the superpowers workflow
(github.com/obra/superpowers): plan, one isolated worktree per task with a verified clean
baseline, a fresh sub-agent per task, review between tasks, then finish by merging and
cleaning up. ADR 0015 records how this fits the one-branch rule.

## Why

On 2026-09-19 four sub-agents shared one working tree. Django's test runner creates and
destroys `test_compliance_watch` on every run, so concurrent runs dropped each other's
database mid-run and produced failures that belonged to nobody. Two E2E stacks would also
have fought over ports 8000 and 3000. A worktree gives a task its own files; a slot gives it
its own databases, Redis index and ports.

## The slot

`scripts/worktree.sh` allocates slot N (1 to 14) per worktree and writes `.env.worktree`.
The main checkout is slot 0 and keeps the defaults.

| Resource | Slot N |
|---|---|
| Database | `compliance_watch_wtN` (test runner uses `test_compliance_watch_wtN`) |
| Scratch database | `compliance_watch_wtN_scratch` (`migrate_from_zero` derives it) |
| E2E database | `compliance_watch_wtN_e2e` |
| Redis | index N+1 |
| API and web ports | `8000 + 10N` and `3000 + 10N` |

Dependencies are shared with the main checkout through a junction (Windows) or a symlink:
`backend/.venv` and `frontend/node_modules`. **Never change dependencies through a shared
link**, since that changes them for every worktree and for main. A task that must add or
upgrade a package runs `init --own-deps` first, which installs its own copies.

## Commands

```bash
bash scripts/worktree.sh new <task>          # create .claude/worktrees/<task> on branch wt/<task>, init it
bash scripts/worktree.sh init                # inside a worktree a tool created: allocate a slot, verify baseline
bash scripts/worktree.sh list                # every worktree with its slot and branch
bash scripts/worktree.sh remove <task>       # drop its databases, unlink dependencies, remove, delete merged branch
```

Inside a worktree, load the slot before any backend or E2E command:

```bash
set -a; . ./.env.worktree; set +a
# or, where a sandbox refuses to source a file:
export $(grep -v '^#' .env.worktree | xargs)
```

`init` refuses to finish on a red baseline: it runs the backend suite in the slot's own
database first. A task never starts on a broken branch, because then nobody can tell which
failures it caused.

## The loop the main agent runs

1. **Plan small tasks.** Write the chunk brief in `docs/plans/briefs/`, then split it into
   tasks a sub-agent can finish in about thirty minutes: one API area, one screen, one group
   of scenarios. Each task names its owned paths, its done-condition and the gates it runs.
   Tasks that touch the same file run one after the other, never side by side.
2. **Branch from a committed main.** A worktree starts from `main`, so everything a task
   builds on must be committed first. Uncommitted work in the main checkout is invisible to
   a worktree.
3. **Dispatch.** One fresh sub-agent per task, in its own worktree (`new`, or the Agent
   tool's worktree isolation followed by `init`), with `model` set explicitly. It works
   test-first, commits on its own branch, never pushes, and never touches `main`, the main
   checkout or another worktree.
4. **Review before merging.** The main agent reads `git diff main...wt/<task>` against the
   brief, the product invariants in `CLAUDE.md` and its simplicity test (anything
   speculative or overbuilt goes back to be cut). Anything touching auth, tenancy, the
   library fence, audit or four eyes also gets a security-review sub-agent. A critical
   finding blocks the merge and goes back to the task.
5. **Integrate at once.** As soon as a task passes review, merge it into `main` squashed
   (`git merge --squash wt/<task>`), run `bash scripts/prepush.sh --quick`, and commit with a
   playbook 13.4 message; a red gate means no commit. Then ship with `bash scripts/ship.sh`
   (in the background: 20 to 40 minutes). It runs the real CI and CodeQL, including the full
   E2E suite, on `candidate`, and moves `main` only when both are green. Several merged tasks
   may ride one ship. Then `remove` the worktree.
   Never let finished work wait for the rest of the chunk. When a later branch conflicts,
   merge `main` into it inside its own worktree and rerun its gates there.

## What each sub-agent runs

A sub-agent runs the gates for what it touched, in its own slot: the unit and scenario tests
of its apps and directories, lint and types, the compliance lint, and the E2E journeys of
its own scenarios. The main agent alone runs the whole checklist and the whole E2E suite, once
per merge, on `main`. Running everything in every task doubles the time and, in a shared
tree, makes the runs collide.

## New requests while tasks are running

A new request becomes a new small task in its own worktree. Do not redirect a running
sub-agent unless its current work would otherwise be wasted: a message only reaches it at its
next tool call, and changing its scope mid-task is how the long runs of 2026-09-19 happened.

## Cloud tasks

Alex approved moving work off the laptop on 2026-09-19. A task can run in a Claude Code cloud
session instead of a local worktree when its files are disjoint from every running task and
everything it builds on is already on `origin/main` (a cloud session clones GitHub, not the
laptop). The cloud machine has 4 CPUs and 15 GB, enough for a full E2E stack of its own.

1. **Dispatch.** The main agent creates a one-off routine with `RemoteTrigger` (no schedule):
   repository `AlexAppelgren/grc`, model `claude-opus-5` set explicitly, the task's branch
   `claude/<task>`, and a short prompt that names the task and its brief and points at "The
   session's rules" below. Then it runs the routine once.
2. **The session** runs `bash scripts/cloud-setup.sh` (with `--e2e` when its gates include E2E),
   builds the task test-first exactly like a local sub-agent, runs its gates, commits, and
   pushes only its own `claude/<task>-…` branch. It never pushes `main` or `candidate` and
   never opens a pull request.
3. **Follow it** with `RemoteTrigger` `list_runs` and `get_run_log`: a cloud session sends no
   completion notice, so the main agent checks it whenever it is next active.
4. **Review and integrate** as for a worktree: `git fetch origin claude/<task>-…`, read the
   diff against the brief, security review where the task touches an invariant, then
   `git merge --squash`, `prepush.sh --quick`, commit, `ship.sh`. Delete the remote branch
   after the merge (`git push origin --delete claude/<task>-…`).

### The session's rules

A cloud session's prompt only names its task and brief; these are its standing rules.

1. Run `bash scripts/cloud-setup.sh` first, with `--e2e` when the task's gates include E2E. If
   it fails, fix only what stops it, say exactly what in the report, and continue.
2. Read CLAUDE.md (loaded), this runbook, the brief's opening sections and the task in full,
   then every file the task names. Stay inside the task's owned paths; any other file touched
   is kept minimal and named in the report.
3. Nobody can answer questions: take the documented default for any open decision and say so.
4. Test-first where there is code. Never simplify away a guard, test, audit row, permission
   check or validation. Never lower a gate, skip or quarantine a test, or mock an API in E2E.
   Never commit `openapi.json` or `frontend/src/types/api.generated.ts`. Never change
   dependencies.
5. Run every gate the task lists, then `bash scripts/prepush.sh --quick`; all must be green.
6. Commit on the session's own `claude/...` branch with a playbook 13.4 message (no model or
   tool names, no Co-Authored-By line) and `git push -u origin HEAD`. Never push `main` or
   `candidate`, never open a pull request, never send push notifications.
7. End with a report: branch and commit; files changed; each gate and its result; every
   default taken; any deviation from the task and why; what a reviewer should look at.

Model and effort: the routine takes a model (`claude-opus-5`, set explicitly, never a smaller
one); on 2026-09-19 its API accepted no effort setting, so a cloud session runs at the model's
default effort.

## What went wrong on 2026-09-19, which this loop prevents

| What happened | Cause | Now |
|---|---|---|
| Sub-agents ran for over an hour and several died at a usage limit mid-task | A task was half a chunk | Tasks of about thirty minutes with a done-condition |
| Chunks 1 and 2 sat uncommitted for hours, so no worktree could see them | Finished work waited for its chunk | Merge each task as soon as it passes review |
| Test runs deleted each other's database and E2E builds hit half-saved files | Every agent worked in one tree | One worktree and one slot per task |
| The same full suites and E2E ran over and over | Every agent ran every gate | Sub-agents run their own gates, the main agent runs the full set once per merge |
| Four design requests became four more agents in the same tree, redirected by message | New work went into running work | A new request is a new task

## Rules

- `main` is the only branch that deploys, and it moves only through `bash scripts/ship.sh`: the
  quick local gates, then the real CI and CodeQL on `candidate`, then a fast-forward of `main`
  (ADR 0015, 2026-09-19). `wt/*` branches are local and short-lived.
- One slot per worktree; `remove` frees it. Fourteen slots is the ceiling: slot N uses Redis index N+1, and Redis has 16 databases. Memory, not slots, is the practical limit: at most three worktrees run an E2E stack at once on a 16 GB machine.
- A worktree made by a tool has no slot until `init` runs in it (`list` shows `- (none)`),
  and until then it must not run the suite, since it would use the shared default database.
- Never recursively delete a worktree directory by hand while its dependency links exist:
  a recursive delete can follow a link into the main checkout. `remove` unlinks first and
  refuses to continue if a link survives.
