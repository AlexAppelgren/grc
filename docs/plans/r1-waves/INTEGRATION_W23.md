# R1 waves 2 and 3: the cloud integration

You integrate the finished cloud packages of waves 2 and 3 of the R1 build of Compliance Watch (bleqq), unattended, in one cloud session. CLAUDE.md is authoritative for every rule. You are the integrator, so D-67's grouped gates are yours: the whole backend suite with the coverage floors, the frontend gates, the production build and the full E2E suite run here, over the merged branch.

## Setup
1. Follow "The session's rules" in docs/runbooks/WORKTREES.md (section "Cloud tasks"). Run `bash scripts/cloud-setup.sh --e2e` first (in the background while you merge).
2. `git fetch origin`, then `git checkout -b claude/r1-int-w23 origin/claude/r1-int-base`. That base is main plus the locally integrated part of wave 2 (h16-library-db-policy, vocab-term-provenance, tax-jurisdiction-derivation, watch-curation-confirm-backend, proposals-agent-decision-log), already green under `prepush.sh --all`; it is being shipped to main while you work.

## Merge
Merge, in exactly the order of the list at the end of this file, each with `git merge --no-ff origin/<branch>` and a message `Merge <package key>: <what it lets a person do, in plain English>`. Resolve each conflict keeping both sides' intent. Most wave-3 branches already contain their wave-2 dependencies, so later merges are small. After the list, if `origin/claude/r1w3-watch-curation-confirm-frontend-done` exists, merge it last too; if it does not exist yet, leave it out and say so.

Each cloud branch also pushed a session branch with a random suffix (for example `...-1lrmom`); ignore those.

## Known issues you must resolve (smallest correct change, never by weakening a gate)
1. **The library door guard (H16, ADR 0058) fails closed on purpose.** After the merges it will fail until you add a proof for: every new ProposalKind (proposals-kind-instrument-obligation and proposals-kind-provision-licensed add kinds) in `test_every_proposal_kind_is_approved_through_the_real_path_as_the_app_role`; every new module on WATCH_WRITE_ALLOWLIST in the watch-step test; and every new plain shared model in a library-zone app (make it a LibraryModel, or list it in REFERENCE_TABLES with the trigger). Prove each the way the existing ones are proven: the real create and approve functions, as cw_app. Never loosen the trigger, the census or the allowlist to get green.
2. **Migrations.** Several branches may add migrations with the same number in the same app. Renumber so the graph is linear per app, fix dependencies, and make sure `migrate_from_zero` applies with the H16 trigger in place (migrations run as the schema owner). `makemigrations --check` must say "No changes detected".
3. **Decision and ADR numbers.** D-83 is the last taken row; renumber every `D-8x` placeholder a package added to the next free numbers, updating every reference. The next ADR is 0059.
4. **Search evaluation row `r-nb-01`** (added by tax-nordic-seed, Norwegian "egnethetsvurdering ved investeringsrådgivning" expecting `obl-no-suitability`) fails `apps.shared.tests_embedder.MockEmbedderConcepts.test_every_concept_question_reaches_its_obligation_by_the_vector_leg_alone`: the mock embedder ranks obl-suitability-statement, obl-suitability and obl-idd-demands-needs above it. Fix the cause (for example, the mock embedder's concept vocabulary does not know the Norwegian terms the way it knows the other languages', or the expected key is genuinely wrong for that question). Never raise TOP_N, delete the row or skip the test.
5. **FP-04** in backend/apps/taxonomy/app.md must end with the status the merged code earns (tax-market-journeys was asked to move it).
6. **Generated artefacts.** No cloud branch committed `openapi.json` or `frontend/src/types/api.generated.ts` (the local base did). After the last merge run `bash generate-types.sh` and commit both.
7. `claude/r1w3-tax-watched-feed` has no done marker only because of issue 4; its own gates were green.

## Gates
Run `bash scripts/prepush.sh --all` with the slot loaded. It stops at the first red gate and prints the command that reproduces it. Fix the cause (an interaction between packages, a journey failing against the real stack, a seed collision, a coverage floor) and run again, until it ends "prepush: all gates green". If a gate cannot run in this environment at all (for example a scanner that needs Docker), run every other gate, and name the one that could not run and why in your report; CI on the candidate branch runs it before anything reaches main.

Hard rules: never lower a gate, threshold or coverage floor; never skip, quarantine or fixme a test to get green; never mock an API in E2E; never weaken a CLAUDE.md section 5 invariant. If something cannot be made green without breaking one of these, stop fixing that item, leave it red, push the branch without the done marker, and say precisely what and why. Commit messages: plain English from the user's point of view, the why and the requirement IDs in the body, no model or tool names, no Co-Authored-By trailer. Never push to main or candidate and never run ship.sh.

## Finish
Push `claude/r1-int-w23`. Only when the whole run is green, also push the same commit as `claude/r1-int-w23-done`. Your final message: the merged list, every conflict and how you resolved it, every fix with its commit, each gate's result, and anything left for the owner.

## Merge order
claude/r1w2-tax-nordic-seed-done
claude/r1w2-tax-markets-panel-done
claude/r1w2-tax-scope-journeys-done
claude/r1w2-tax-preview-cases-done
claude/r1w2-vocab-usage-and-merge-done
claude/r1w2-lib-standard-e2e-seed-done
claude/r1w2-lib-standard-presentation-done
claude/r1w2-library-recheck-loop-done
claude/r1w2-problem-reports-backend-done
claude/r1w2-ai-log-read-done
claude/r1w2-console-proposals-frontend-done
claude/r1w2-vocab-screen-pending-proposals-done
claude/r1w2-proposals-standards-check-done
claude/r1w2-proposals-kind-instrument-obligation-done
claude/r1w2-console-agent-keys-screen-done
claude/r1w2-watch-regime-required-done
claude/r1w2-watch-case-reads-name-the-person-done
claude/r1w2-ask-feedback-and-limits-done
claude/r1w2-ask-switch-route-done
claude/r1w2-ask-screen-done
claude/r1w2-search-eval-sets-done
claude/r1w2-nfr-integration-scenarios-done
claude/r1w2-screen-budget-nfr-s7-done
claude/r1w2-api-docs-identity-admin-done
claude/r1w2-api-docs-taxonomy-vocabularies-done
claude/r1w2-security-review-c6-done
claude/r1w2-shell-sign-out-gate-done
claude/r1w2-worktree-drop-databases-done
claude/r1w3-tax-watched-inventory-done
claude/r1w3-tax-watched-feed
claude/r1w3-tax-market-journeys-done
claude/r1w3-std-journeys-done
claude/r1w3-lib-machine-confirmed-journey-done
claude/r1w3-problem-reports-frontend-done
claude/r1w3-ai-log-screen-done
claude/r1w3-aud-s4-integration-done
claude/r1w3-proposals-kind-provision-licensed-done
claude/r1w3-pro-s13-journey-done
claude/r1w3-watch-standards-done
claude/r1w3-agent-j4-smoke-done
claude/r1w3-ask-journeys-done
claude/r1w3-search-index-changes-done
claude/r1w3-ask-standard-no-answer-done
claude/r1w3-console-evaluation-screen-done
claude/r1w3-api-docs-taxonomy-scope-done
