# PRD 0.3 consolidation: task

One documentation task that turns three analyses into one PRD bump and everything that must
land with it. It runs as a single commit, because `requirements_coverage.py` refuses a PRD ID
without its scenario and stubs. Written 2026-09-19 by the main agent.

**Owned paths:** `PRD.md`, `docs/DECISIONS.md`, new files in `docs/adr/`,
`docs/inputs/INPUT_DELTAS.md`, the `app.md` of every app the bump touches, their
`tests_scenarios.py` (skipped stubs only) and `frontend/tests/e2e/<app>.journey.spec.ts`
(`test.fixme` stubs only), `docs/plans/Build_Plan.md`, `docs/plans/UI_Implementation_Plan.md`,
`docs/plans/IMPLEMENTATION_STATUS.md`, `docs/TODO_FOR_alex.md`, the three briefs (their new
"Final IDs" section only), and the new `docs/plans/briefs/FEATURES_0_3_TASKS.md`. Never
application code, models, migrations, messages or seeds: other tasks change those in
parallel.

## The task

Alex asked on 2026-09-19 for three things, each analysed into a brief: docs/plans/briefs/MY_WORK_AND_MARKETS.md (My work, participants, departments, operating and watched markets), docs/plans/briefs/STANDARDS.md (standards and certifications within the sector scope), and docs/plans/briefs/REGULATORY_SCOPE.md (the footprint renamed Regulatory scope; its section 2 and its TODO item about a PRD glossary line). Consolidate them into ONE documentation change, in one commit:
a. PRD.md 0.3: one version-log row (date 2026-09-19, "Decided by": Alex, requested in chat; the design defaults are DECISIONS rows he can reverse). Apply every changed and new requirement row, acceptance criterion and journey from BOTH drafted bumps (each brief's "PRD bump" appendix), merged so no row is edited twice inconsistently. Add the glossary line: on screen the section is "Regulatory scope"; in code, API paths, permission keys and the route it stays "footprint". Then delete that glossary item from docs/TODO_FOR_alex.md. Do not assert any outside fact about ISO, IAF, PCI SSC, Swift or national standards bodies that STANDARDS.md marks unverified.
b. Final IDs. The briefs' decision IDs and scenario, criterion and journey IDs collide or are provisional (MY_WORK_AND_MARKETS uses D-18 to D-34; STANDARDS uses std-* slugs and provisional IDs; REGULATORY_SCOPE claims FP-S6 and FP-S7, which MY_WORK_AND_MARKETS also claims). Assign final, unique IDs: decisions continue from the highest D- number in docs/DECISIONS.md; scenario IDs continue from the highest existing number per prefix in each app.md, with REGULATORY_SCOPE keeping FP-S6 and FP-S7 (its tasks are already planned under them). Write a mapping table (brief ID -> final ID) into each of the three briefs as a new short section at the top, "Final IDs (PRD 0.3)", so later tasks read the right numbers.
c. docs/DECISIONS.md rows and any ADRs the briefs call for (docs/adr/, next free numbers, following docs/adr/README.md). docs/inputs/INPUT_DELTAS.md rows the briefs call for.
d. Every new or changed requirement gets its app.md row (status pending) and its scenarios in the owning app's app.md (CLAUDE.md section 10 format), a skipped integration test stub per @integration scenario in that app's tests_scenarios.py (`@skip("pending: <ID>")`, docstring carrying the ID), and a test.fixme per @e2e scenario in frontend/tests/e2e/<app>.journey.spec.ts. python backend/scripts/requirements_coverage.py must pass.
e. docs/plans/Build_Plan.md: add the new requirement IDs to the chunk rows the briefs' placement tables give. docs/plans/UI_Implementation_Plan.md: the new screens and cards in their chunks. docs/plans/IMPLEMENTATION_STATUS.md: chunk 3 is "in progress" (its data layer is on main), not "pending".
f. One task file, docs/plans/briefs/FEATURES_0_3_TASKS.md: every implementation task from the three briefs' task lists (skip the pure documentation tasks this change completes), with final IDs, grouped by the chunk the placement gives, each with owned paths, depends-on (including chunk task IDs from CHUNK3_TASKS.md and CHUNK4_TASKS.md) and done-condition. Mark which can start now. Note: chunk3-rest-T4 (library/reading.py, the scope rule) is being built right now without jurisdiction terms; the markets task that derives a record's jurisdiction therefore runs AFTER it and extends that one rule. Do not edit CHUNK3_TASKS.md's existing tasks; add any chunk-3 follow-ups to FEATURES_0_3_TASKS.md instead.
g. docs/TODO_FOR_alex.md: every question the briefs say needs Alex (private notes; aspiring markets outside EU/SE/DK/NO/FI; the standards seed list; the legal questions on standards; the content licence; the sector vocabulary question, answered once for both STANDARDS.md and REGULATORY_SCOPE.md section 12; the SoA export timing), each with the default taken. docs/plans/Verification_Log.md: nothing is logged as verified unless you fetched it in this session; list the outside facts STANDARDS.md section 9 says to fetch as open items in the TODO instead.

## Gates

python backend/scripts/requirements_coverage.py; python backend/scripts/compliance_check.py --all; the backend tests of every app whose tests_scenarios.py you touched (they must pass, with the new stubs skipped); cd frontend && npm run lint && npm run typecheck for the fixme stubs; then bash scripts/prepush.sh --quick.

## Conflicts

other tasks are changing code in parallel on main. Touch only documentation, app.md files, tests_scenarios.py stubs and E2E fixme stubs; never change application code, models, migrations, messages or seeds.
