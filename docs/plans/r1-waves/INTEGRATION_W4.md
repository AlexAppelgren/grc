# R1 wave 4: the cloud integration

You integrate the finished wave-4 packages of the R1 build of Compliance Watch (bleqq) onto main, unattended, in one cloud session. CLAUDE.md is authoritative for every rule. You are the integrator, so D-67's grouped gates are yours: the whole backend suite with the coverage floors, the frontend gates, the production build and the full E2E suite run here, over the merged branch.

## Setup
1. Follow "The session's rules" in docs/runbooks/WORKTREES.md (section "Cloud tasks"). Run `bash scripts/cloud-setup.sh --e2e` first (in the background while you merge).
2. `git fetch origin`, then `git checkout -b claude/r1-int-w4 origin/main`. main already holds every wave-2 and wave-3 package, the last wave-3 package (watch-curation-confirm-frontend) and vocab-agent-confirm, integrated and green including the container gates.

## Merge
Merge, in this order, each with `git merge --no-ff origin/<branch>` and a message `Merge <package>: <what it lets a person do, in plain English>`. Several contain one another (merge-moved-ids contains security-review-c3-f03; agent-write-guards contains security-review-c5; security-review-c4 contains vocab-agent-confirm), so later merges are small.

1. claude/r1w4-security-review-c3-f03-done
2. claude/r1w4-merge-moved-ids-done
3. claude/r1w4-security-review-c4-done
4. claude/r1w4-security-review-c5-done
5. claude/r1w4-agent-write-guards-done
6. claude/r1w4-security-review-c7-done
7. claude/r1w4-r1-perf-done

## Known issues you must resolve (smallest correct change, never by weakening a gate)
1. **HARDENING numbers collide.** Each review numbered its new rows from H23 on its own: c3-f03 used H23-H32, c4 H24-H29, c5 H23-H29, c7 H23-H24, and merge-moved-ids and agent-write-guards mark some of them fixed. Renumber into one sequence after the last number on main, keeping one row per distinct finding, and update every reference to the old numbers (the four docs/security/CHUNK*_REVIEW_2026-09-23.md files, docs/TODO_FOR_alex.md, docs/DECISIONS.md, code comments and test docstrings). Keep each fixed row marked fixed with its commit.
2. **Decision and ADR numbers.** Renumber any colliding `D-8x` row a package added to the next free numbers, updating every reference; check docs/adr/README.md for duplicate ADR numbers.
3. **Migrations.** Several packages may add a migration with the same number in one app (r1-perf adds taxonomy 0008, the footprint guard split). Renumber so each app's graph is linear, fix dependencies, and make sure `migrate_from_zero` applies with the library door trigger in place. `makemigrations --check` must say "No changes detected".
4. **The library door guard (H16, ADR 0058)** fails closed on any new ProposalKind, new watch write module or new plain shared model; add the proof the guard asks for, never loosen it.
5. **Generated artefacts.** After the last merge run `bash generate-types.sh` and commit openapi.json and frontend/src/types/api.generated.ts.
6. **Perf baseline.** If a merge changes a measured route's queries, re-run `perf_report` for it and keep backend/perf/baseline.json consistent; no route may exceed its budget.

## Gates
Run `bash scripts/prepush.sh --all` with the slot loaded. It stops at the first red gate and prints the command that reproduces it. Fix the cause and run again until every gate that can run here is green. The container builds and their Trivy scans cannot run in this environment (Docker cannot trust the session proxy's certificate); name them in your report, and CI on the candidate branch runs them before anything reaches main.

Hard rules: never lower a gate, threshold or coverage floor; never skip, quarantine or fixme a test to get green; never mock an API in E2E; never weaken a CLAUDE.md section 5 invariant. If something cannot be made green without breaking one of these, stop fixing that item, leave it red, push the branch without the done marker, and say precisely what and why. Commit messages: plain English from the user's point of view, the why and the requirement IDs in the body, no model or tool names, no Co-Authored-By trailer. Never push to main or candidate and never run ship.sh.

## Finish
Push `claude/r1-int-w4`. When every gate that can run here is green, also push the same commit as `claude/r1-int-w4-done`. Your final message: the merged list, every conflict and how you resolved it, the HARDENING renumbering table (old number and review, new number), every fix with its commit, each gate's result, and anything left for the owner.
