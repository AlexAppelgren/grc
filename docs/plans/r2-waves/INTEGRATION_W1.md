# R2 wave 1: the cloud integration

You integrate the finished wave-1 packages of the R2 build of Compliance Watch (bleqq) onto main, unattended, in one cloud session. CLAUDE.md is authoritative for every rule. You are the integrator, so D-67's grouped gates are yours: the whole backend suite with the coverage floors, the frontend gates, the production build and the full E2E suite run here, over the merged branch.

## Setup
1. Follow "The session's rules" in docs/runbooks/WORKTREES.md (section "Cloud tasks"). Run `bash scripts/cloud-setup.sh --e2e` first (in the background while you merge).
2. `git fetch origin`, then `git checkout -b claude/r2-int-w1 origin/main`. Read `docs/plans/r2-waves/CLOUD_SESSION.md` and `owner_questions.json` on `origin/claude/r2-plan`: the answers there bind you.

## Merge
Merge each `claude/r2w1-<package>-done` branch that exists on origin, in the order of `docs/plans/r2-waves/wave1.json` on `origin/claude/r2-plan`, each with `git merge --no-ff` and a message `Merge <package>: <what it lets a person do, in plain English>`. If a package has a branch but no done marker, do not merge it; name it in your report.

## Known issues you must resolve (smallest correct change, never by weakening a gate)
1. **Appended blocks in shared docs collide.** Trial merges already conflict in docs/plans/UI_Implementation_Plan.md, design/system/pills-and-labels.md, docs/DECISIONS.md and docs/plans/Build_Plan.md. Every package appended its own block: keep both sides' blocks, in plan order, and drop only true duplicates.
2. **Alex's answers (2026-09-25) become decision rows.** Add D-98 to D-101 to docs/DECISIONS.md, each marked "Alex, 2026-09-25", in the house style of the rows around them:
   - D-98: a bank's own text for its own agents (AGT-05's topic, a D-89 scope item's name, official reference and source addresses) may reach a model as a second named exception beside Ask. It is length-capped, screened as untrusted, sent only through the logged wrapper to an approved EU endpoint, and stopped by the bank's AI switch and budget cap. It is never logged and never reaches a platform run. It amends D-07 and D-32. The ADR is written by d89-researcher-definition.
   - D-99: the control inventory D-89 names is REG-05 internal items of the control kind, linked to the bank's private obligation and created by the same private approval (OWN-05).
   - D-100: the device-bound passkey policy (ID-07, ID-S16, ID-S29) moves out of R2. Banks can still require passkeys, not specific models. identity/app.md keeps ID-07 pending with "after R2 (D-100)", PRD.md's ID-07 release cell reads "after R2 (D-100)", and design/screens' admin-security card loses its passkey-policy section (session limits and tenant reach stay).
   - D-101: evidence files are uploaded multipart through the API (the INPUT_DELTAS departure is confirmed). Alex provisions clamd in Railway EU West; until then a deployed environment refuses evidence files with 503 scanner_unavailable.
   In docs/TODO_FOR_alex.md, mark each of the plan's owner questions answered, with its D-number. Mark the clamd item as Alex's own action.
3. **Decision and ADR numbers.** Packages numbered their own rows D-9x or D-1xx. Renumber each to the next free number after D-101 and update every reference. Check docs/adr/README.md for duplicate ADR numbers.
4. **Migrations.** Several packages add migrations to the same app: tenants, register, cases, collab, agents and proposals. Renumber so each app's graph is linear, fix the dependencies, and make sure `migrate_from_zero` applies with the library door trigger in place. `makemigrations --check` must say "No changes detected".
5. **The library door guard (H16, ADR 0058)** fails closed on any new ProposalKind, new watch write module or new plain shared model. c8-recurring-duty-library adds a shared record; add the proof the guard asks for and never loosen it.
6. **Vocabularies and pills.** Several packages add vocabulary kinds and pill slots. Keep one seed per kind and one presentation function per record type. Keep `check:messages` and the en and sv catalogs complete.
7. **Generated artefacts.** After the last merge run `bash generate-types.sh` and commit openapi.json and frontend/src/types/api.generated.ts.
8. **HARDENING rows.** Renumber any colliding rows into one sequence after the last number on main, and update every reference.

## Gates
Run `bash scripts/prepush.sh --all` with the slot loaded. It stops at the first red gate and prints the command that reproduces it. Fix the cause and run again until every gate that can run here is green. The container builds and their Trivy scans cannot run in this environment, because Docker cannot trust the session proxy's certificate. Name them in your report; CI on the candidate branch runs them before anything reaches main.

Hard rules: never lower a gate, threshold or coverage floor; never skip, quarantine or fixme a test to get green; never mock an API in E2E; never weaken a CLAUDE.md section 5 invariant. If something cannot be made green without breaking one of these, stop fixing that item, leave it red, push the branch without the done marker, and say precisely what and why. Commit messages: plain English from the user's point of view, the why and the requirement IDs in the body, no model or tool names, no Co-Authored-By trailer. Never push to main or candidate and never run ship.sh.

## Finish
Push `claude/r2-int-w1`. When every gate that can run here is green, also push the same commit as `claude/r2-int-w1-done`. Your final message:
- the merged list, and any package left out and why;
- every conflict and how you resolved it;
- the renumbering tables (decisions, ADRs, migrations, HARDENING);
- every fix, with its commit;
- each gate's result;
- anything left for the owner.
