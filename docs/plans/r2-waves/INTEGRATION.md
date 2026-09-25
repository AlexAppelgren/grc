# R2 wave W: the cloud integration

You integrate the finished packages of one wave of the R2 build of Compliance Watch (bleqq) onto main, unattended, in one cloud session. Your prompt names the wave W. CLAUDE.md is authoritative for every rule. You are the integrator, so D-67's grouped gates are yours: the whole backend suite with the coverage floors, the frontend gates, the production build and the full E2E suite run here, over the merged branch. INTEGRATION_W1.md is the worked example of wave 1; this brief is its general form.

## Setup
1. Follow "The session's rules" in docs/runbooks/WORKTREES.md (section "Cloud tasks"). Run `bash scripts/cloud-setup.sh --e2e` first, in the background while you merge.
2. `git fetch origin`, then `git checkout -b claude/r2-int-wW origin/main`. main already holds every earlier wave, integrated and green in CI. Read `docs/plans/r2-waves/CLOUD_SESSION.md` and `owner_questions.json` on `origin/claude/r2-plan`: the decisions they record bind you (D-98 to D-102 are Alex's answers of 2026-09-25).

## Merge
Merge each `claude/r2wW-<package>-done` branch that exists on origin, in the order of `docs/plans/r2-waves/waveW.json` on `origin/claude/r2-plan`. Merge each with `git merge --no-ff` and the message `Merge <package>: <what it lets a person do, in plain English>`. Packages merged their dependencies' done branches, and many of those are already on main, so later merges shrink. If a package has a branch but no done marker, do not merge it; name it in your report.

## Known issues to resolve (smallest correct change, never by weakening a gate)
1. **Appended blocks in shared docs collide.** Each package appended its own block to files such as docs/plans/UI_Implementation_Plan.md, design/system/pills-and-labels.md, docs/DECISIONS.md, docs/plans/Build_Plan.md, docs/TODO_FOR_alex.md and docs/security/HARDENING.md. Keep both sides' blocks, in plan order, and drop only true duplicates.
2. **Decision, ADR and HARDENING numbers.** Packages numbered their own decision rows D-1xx or D-9x with their key. Renumber each to the next free number after the last on main, and update every reference. Do the same for duplicate ADR numbers (check docs/adr/README.md) and colliding HARDENING rows.
3. **Migrations.** Renumber so each app's graph is linear and fix the dependencies. `makemigrations --check` must say "No changes detected", and `migrate_from_zero` must apply with the library door trigger in place. Wave 1 renamed `agents.AgentVersion.version_no` to `version_number`, but branches built before that may still say `version_no`, so bring every reference onto the new name.
4. **The library door guard (H16, ADR 0058)** fails closed on any new ProposalKind, watch write module or plain shared model. Add the proof it asks for; never loosen it. D-102 moves agent definitions, versions and platform agent settings into an explicit platform-configuration list; c11-agent-config-platform builds that list, and nothing else joins it.
5. **Vocabularies, pills and catalogs.** Keep one seed per vocabulary kind and one presentation function per record type. Keep the en and sv catalogs complete (`check:messages`).
6. **The integrator's two gates.** Packages may not commit the generated API files or the demo recordings, so some done markers were pushed with those two gates red, by rule. After the last merge:
   - run `bash generate-types.sh` and commit openapi.json and frontend/src/types/api.generated.ts;
   - run `npm run demo:record` in frontend/ against the seeded stack and commit the recordings;
   - then run contract drift again, because a stub's explanation line can go stale once the regenerated contract counts its route as built.
7. **Expected, not a failure.** A scenario a package left skipped with a named reason in its report is not yours to force green, and the same goes for a route it left at 501. An example is AGT-S4 until c11-agent-config-platform merges. Everything else red is yours.

## Gates
Run `bash scripts/prepush.sh --all` with the slot loaded. It stops at the first red gate and prints the command that reproduces it. Fix the cause and run it again until every gate that can run here is green. The container builds and their Trivy scans cannot run in this environment, because Docker cannot trust the session proxy's certificate. Name them in your report; CI on the candidate branch runs them before anything reaches main.

Hard rules:
- Never lower a gate, threshold or coverage floor.
- Never skip, quarantine or fixme a test to get green.
- Never mock an API in E2E.
- Never weaken a CLAUDE.md section 5 invariant.

If something cannot be made green without breaking one of these, stop fixing that item and leave it red. Push the branch without the done marker, and say precisely what is red and why.

Commit messages are plain English from the user's point of view, with the why and the requirement IDs in the body, no model or tool names, and no Co-Authored-By trailer. Never push to main or candidate, and never run ship.sh.

## Finish
Push `claude/r2-int-wW`. When every gate that can run here is green, also push the same commit as `claude/r2-int-wW-done`. Your final message covers:
- the packages merged, and any left out, with the reason;
- every conflict and how you resolved it;
- the renumbering tables for decisions, ADRs, migrations and HARDENING rows;
- every fix, with its commit;
- each gate's result;
- anything left for the owner.
