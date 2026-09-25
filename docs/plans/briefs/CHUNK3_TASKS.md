# Chunk 3 (rest): tasks

Written 2026-09-19 by the planning workflow (read, plan, parallelism and coverage critiques, revise). Each task runs in its own worktree (`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`.

## Scope, rules and defaults

chunk3-rest: finish INV-01..06 (library reads, writes and inventory screens), NFR-S10, the J-6 inventory half of FP-S5, and VOC-02 usage counts for library lists. This builds on the library data layer (squash 51f9efa) and the redesign foundations (squash 18a935b), both already on main.

Precondition (main agent, before wave 1): run `bash scripts/prepush.sh --all` on main at 51f9efa to confirm a green baseline, then start wave 1. Nothing needs to be merged or committed first: both branches are already squash-merged into main, `git status` is clean, tests_production_guard.py was committed in 1ce47b6, and CHUNK4_BRIEF.md is tracked.

Plan-wide rules:
1. Slots. Every backend and E2E gate runs inside the task's worktree slot (`set -a; . ./.env.worktree; set +a`).
2. Generated files. Only the main agent commits openapi.json and frontend/src/types/api.generated.ts. It regenerates them with generate-types.sh after each merge (Appendix D item 6). A task regenerates them locally to run contract_drift.py and the typecheck, then reverts them before it commits. Frontend tasks start from a main that already has the regenerated types.
3. Library backend chain. One backend task at a time owns backend/apps/library/{api.py, schemas.py, reading.py, testing.py, tests_scenarios.py, tests_reading.py}, shared/permissions.py, docs/inputs/INPUT_DELTAS.md and backend/scripts/contract_drift_pending.txt, in this order: T4, T6, T11b, T13, T16.
4. Frontend chain. One frontend task at a time owns features/library/{types,api,hooks}.ts, their api.test.ts and hooks.test.tsx, messages/common/{en,sv}.json, messages/inventory/{en,sv}.json, messages/library/{en,sv}.json and tests/e2e/library.journey.spec.ts, in this order: T5 (messages only), T9, T12, T14, T17, T18.
5. Security review before merge (WORKTREES step 4). T1, T2, T3, T4, T6, T7, T8, T11a, T11b, T13 and T16 touch tenancy, the library fence, audit, four eyes or the proposal door. For each of them, the main agent runs a security-review sub-agent over `git diff main...wt/<task>` before the squash merge, together with apps.shared.tests_rls, tests_tenant_isolation, tests_library_fence, tests_route_permissions, tests_audit_on_write and tests_four_eyes. A critical or high finding sends the work back to the task and blocks the merge. T19 is the only review task: one chunk-wide sweep after T18 has merged.
6. Merge at once (WORKTREES step 5). Each task is squash-merged, and the full checklist run, as soon as it passes review. A task starts once everything in its depends_on is on main. The waves show which tasks can run side by side because their files are disjoint.
7. Scenario ownership. Each scenario has exactly one task that un-skips its integration test and one that un-fixmes its journey:
- INV-S3, S4, S5 and S6: T6.
- INV-S7: T11b (obligation), extended by T13 (instrument read).
- INV-S8: T11b.
- INV-S1 and INV-S10: T13.
- INV-S2: T16.
- FP-S2 and FP-S4 (backend): T7.
- NFR-S10: T3.
- Journeys: FP-S5 inventory step T9, preview count T12; INV-S3 and INV-S6 T12; INV-S4, INV-S5 and the obligation half of INV-S7 T14; INV-S1 and the instrument half of INV-S7 T17; INV-S2 and the provision half of INV-S7 T18.
- T1, T2 and T4 only contribute to scenarios.
8. Time bombs. Research payments version 2 and the FFFS 2017:2 9 kap. 6 § amendment take effect 2026-10-01, twelve days from today. Every test and journey pins its dates or chooses versions by chip, and never relies on today's date.

Defaults taken. Each is stated in its commit body and copied into TODO_FOR_alex.md by T20.
- J-6: one sample advice-only obligation is added (from_prototype: false). No prototype obligation is rescoped, because no prototype obligation is advice-only.
- The FFFS 2017:2 provision tree and FFFS 2026:11 are sample rows taken from the instrument card, marked from_prototype: false. They are never presented as verbatim law.
- Seeded records carry no verifier. The fixture's verifier is a tenant user, so verified_by stays null until someone re-verifies. The card shows "by <name>" only when verifiedBy is set.
- An instrument's verified date is derived from its obligations, or is the fixture anchor date when it has none.
- A provision is shown on its instrument's card, under the instrument's source link and verified date, and is reported through the instrument's "This looks wrong".
- A problem report takes {description, versionNumber?, language?}. There is no "Where" field until Alex answers the open question. Reports can be filed on obligations and instruments.
- GET /problem-reports moves to chunk 4, and GET /authorities to chunk 5 (console-sources, which builds its add form).
- Lineage and version lists are embedded in the detail reads. The obligation detail cites provisions by reference and path, without their text; the card shows none.
- GET /instruments filters by regime, q and outsideFootprint only, and takes no asOf. The Instruments tab lists every visible instrument with its in-force dates, and "As of" applies to obligations only. GET /obligations has no tag filter. The unused designed filters are deferred.
- Footprint scope rule, in one place in library/reading.py. An instrument's scope is its regime. An obligation's scope is its own terms plus its instrument's regime. Neither inherits a jurisdiction term, because none is seeded.
- The footprint preview shows how many obligations it hides and reveals, not their titles.
- Language: `?lang=` is accepted only on the diff reads. Everything else follows language_order, and translations[] feeds the language chips.
- Re-verification needs proposals.review plus a step-up. This is the stricter of the brief and the UI plan.
- Re-pointing records when library lists are merged stays in chunk 4 (proposals/apply.py).
- INV-S9 stays skipped (R3). FP-S4 stays fixme until the feed, roadmap, briefing and reports exist.

## Waves

Tasks in one wave have disjoint files and can run side by side.

1. `chunk3-rest-T1`, `chunk3-rest-T2`, `chunk3-rest-T3`, `chunk3-rest-T4`, `chunk3-rest-T5`
2. `chunk3-rest-T6`, `chunk3-rest-T7`, `chunk3-rest-T8`, `chunk3-rest-T9`, `chunk3-rest-T11a`
3. `chunk3-rest-T11b`, `chunk3-rest-T12`
4. `chunk3-rest-T13`, `chunk3-rest-T14`
5. `chunk3-rest-T16`, `chunk3-rest-T17`
6. `chunk3-rest-T18`
7. `chunk3-rest-T19`
8. `chunk3-rest-T20`

## Open questions

- Urgency and the rule that a tone is never chosen by a person (NFR-S10). INPUT_DELTAS §1 says urgency has a 'fixed ordinal and tone'. Yet the chunk 2 registry lists urgency with the kind 'pill_tone', so a library editor who proposes a new urgency row picks its tone. Option A: urgency rows are fixed, create is refused, and only labels and SLA days can be edited. Option B: an editor may add an urgency level and pick its tone. Until Alex decides, T3 leaves urgency unchanged and refuses only fields named tone or colour. A product invariant may be at stake, so this needs Alex's answer.
- Problem area ('Where' in the report form; needs Alex before wave 3). tenant-obligation.html has a Where select (legal text, translation, scope, duty, source or reference, something else), and console-problem-reports.html filters and pills by it. Nothing in the rules branches on it, and it is not in INPUT_DELTAS §1's kind list. Under 'Enums in code are for kinds only; types and reasons are rows', it cannot be a code enum. Until Alex answers, T11a, T11b and T14 build the designed body {description} plus the optional versionNumber and language context, with no area column and no Where select. If Alex wants the field, it becomes a tier-2 library vocabulary (a registry entry plus seeded system rows) in a later task.
- Rejected: the T2 fix that moves load_library() after seed_logins() so the platform editor can be stamped as verifier. The diagnosis is correct: seed_e2e loads the library first (e2e_seed.py around line 325), so the plan's lookup would always give null. But nothing in scope needs a seeded verifier name: INV-06 and INV-S7 require only the date, and verified_by is set for real by a re-verification (INV-S8). The simpler fix from the other T2 critique is taken instead: seeds leave verified_by null, the card adds 'by <name>' only when it is set, and the guard keeps 'no verifier is a tenant member' as a regression pin.
- Rejected: the premise of the T2 simplification critique that editor@bleqq.test is first seeded in chunk 4. SEED_LOGINS has seeded it with library_editor since chunk 1 (backend/apps/shared/e2e_logins.py line 60); CHUNK4_BRIEF.md only restates that. Its fix (drop the conditional lookup, and add only last_verified_at because all 15 instruments already have a source_url) is still taken, for the reasons above.
- Rejected: the part of the GET /authorities critique that has T20 add the operation to the chunk 5 row of Build_Plan.md. Build_Plan rows list outcomes and requirement IDs, not operations. contract_drift_pending.txt is by design the tracker of each undelivered operation's chunk (its header says so), and T13 re-annotates the line there to chunk 5. The move to chunk 5 itself is correct: UI_Implementation_Plan.md line 70 puts console-sources.html in chunk 5, and T20 records it in IMPLEMENTATION_STATUS.
- Rejected in part: the test that the obligations list and the instrument row agree 'for a jurisdiction-restricted footprint'. The jurisdiction dimension has no seeded terms: taxonomy/seeds creates the dimension, and prototype_data.json has no jurisdiction taxonomy_terms. The critique's 'neither inherits the jurisdiction term' branch is therefore taken. One rule lives in library/reading.py (instrument_scopes() is the regime, and obligation_scopes() inherits through it), and T13's agreement test uses a regime-restricted footprint.

## Tasks

### chunk3-rest-T1: Append-only version tables, the sentence diff and version_diff

**Requirements:** INV-02, INV-04, INV-05, AC-INV1  
**Scenarios:** none  
**Depends on:** nothing

Add backend/apps/library/migrations/0004_append_only_versions.py. It applies migration_helpers.append_only_trigger_operations (the existing cw_append_only_guard) to provision_version, provision_text, obligation_version, obligation_summary and verification. The app role can then insert rows but never update or delete them.

Add pure functions to library/logic.py:
- split_sentences(text). It never splits after the legal abbreviations kap., art., p., nr, t.ex., bl.a., m.m., jfr, e.g. and i.e., and never before a digit or before §.
- sentence_diff(old, new). It returns [(op, text)] with op equal, insert or delete, using difflib, and is deterministic.
- version_diff(from_texts, to_texts, language_order, lang). It picks the first language both versions have, trying lang first and then language_order, and returns (language, is_machine, segments). T6 and T16 then only resolve versions and serialize.

Write the tests first, in a new library/tests_versions.py:
- As cw_app on the app alias, UPDATE and DELETE are refused and INSERT works, on each of the five tables.
- load_library() runs twice with the triggers in place.
- The diff handles English and Swedish cases such as '9 kap. 6 §'.
- version_diff covers a ?lang= hit, the fallback to language_order, the machine flag, and two versions that share no language.

This task contributes to INV-S2, INV-S4 and INV-S5, which T6 and T16 un-skip.

**Owned paths:**

- `backend/apps/library/migrations/0004_append_only_versions.py`
- `backend/apps/library/logic.py`
- `backend/apps/library/tests_versions.py`

**Done when:**

All of the following hold:
- migrate_from_zero applies 0004.
- tests_versions.py proves, as cw_app, that UPDATE and DELETE are refused and INSERT succeeds on all five tables.
- load_library() is idempotent under the triggers.
- The sentence_diff tests pass. Nothing is split inside '9 kap. 6 §' or 'art. 13', and one changed sentence comes back as a delete plus an insert.
- The version_diff tests pass for a lang hit, the fallback, the machine flag and no shared language.
- The apps/library/logic.py coverage floor still holds.

**Gates:**

- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings`
- `./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/library/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

Nothing is overwritten: version and text rows are written once. ProvisionVersion.effective_to is never set after insert; reads derive effectiveTo from the next version. Do not change cw_append_only_guard or its cw.maintenance escape hatch. The merge-step review checks that request code cannot reach that hatch. Test flush uses TRUNCATE, which the trigger does not block. The diff functions are pure and log no text. Security review runs before merge (rule 5).

### chunk3-rest-T2: Seed the J-6 advice-only obligation and instrument verified dates

**Requirements:** FP-01, FP-03, AC-FP1, J-6, INV-06  
**Scenarios:** none  
**Depends on:** nothing

Add one sample obligation to prototype_data.json, marked from_prototype: false:
- It belongs to an existing Swedish instrument.
- Its only service_type term is advice, and every other restricting dimension is inside tenant A's seeded footprint.
- It has one version, in force since always, with an sv original summary and an en machine translation.
- It has a last_verified_at.
Switching off Advice then hides it (J-6). No prototype obligation is advice-only today.

In load_library, an instrument without its own last_verified_at takes the latest last_verified_at among its obligations' fixture rows, or _meta.anchor_date when it has none. All 15 instruments already carry a source_url; none carries a verified date. verified_by stays null: the loader never sets it, and the fixture's verifier (sara) is a tenant user.

Also update check_prototype_data.py, the fixture README, EXPECTED_LIBRARY in e2e_seed.py (16 obligations) and the load_library count assertions in tests_library.py.

Extend tests_seed_integrity to assert:
- Tenant A without advice hides at least one obligation, and with advice hides none. Each obligation's scope is its own terms plus its instrument's regime.
- Every instrument and every obligation has a source link and a verified date.
- No library verified_by is a tenant member (a regression pin).

**Owned paths:**

- `backend/apps/library/fixtures/prototype_data.json`
- `backend/apps/library/fixtures/check_prototype_data.py`
- `backend/apps/library/fixtures/README.md`
- `backend/apps/library/seeds/library.py`
- `backend/apps/shared/e2e_seed.py`
- `backend/apps/shared/tests_seed_integrity.py`
- `backend/apps/library/tests_library.py`

**Done when:**

All of the following hold:
- check_prototype_data.py --eval exits 0.
- seed_demo and seed_e2e run twice with identical counts.
- The seed guard asserts the J-6 hide, the instrument source links and verified dates, and that no verifier is a tenant member.
- EXPECTED_LIBRARY and the tests_library counts match.
- The @smoke E2E journeys pass on the new seed.

**Gates:**

- `python backend/apps/library/fixtures/check_prototype_data.py --eval`
- `cd backend && ./run.sh run coverage run manage.py test apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/library/seeds/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `cd frontend && npm run test:e2e -- --grep "@smoke"`

**Invariants:**

Writes happen only through load_library, inside library_write() in library/seeds, which is a fence-allowlisted directory. The new obligation gets its record(). Version and summary rows are inserted with every field set at create time and are never saved again, because T1's trigger lands in the same wave. Stable keys never change. Do not rescope prototype obligations. Anchor dates to _meta.anchor_date, never to today. A tenant user never becomes a library verifier. Security review runs before merge (rule 5).

### chunk3-rest-T3: NFR-S10: refuse tone and colour on every vocabulary write, send no phrase

**Requirements:** NFR-03, VOC-01  
**Scenarios:** NFR-S10  
**Depends on:** nothing

Add a write-body base with extra="forbid" in shared/schemas.py. Use it for:
- VocabularyCreateBody, VocabularyPatchBody, VocabularySuggestBody, VocabularyReorderBody, VocabularyRetireBody, VocabularyMergeBody and TaxonomyTermCreateBody.
- The vocabulary and term proposal payloads in proposals/schemas.py (ProposalVocabulary*Payload and ProposalTerm*Payload), which validated_payload parses.

Refuse the keys tone, colour and color inside `extra` when the write is made, never when it is approved. That means refusing them both in the extra-column check in tenant_lists_logic (used by /vocab writes) and in proposals/logic.py validated_payload (used by POST /proposals). Such payloads answer 422 validation_error.

Un-skip test_nfr_s10 in shared/tests_scenarios.py. The test:
- Enumerates every POST, PATCH and PUT route under /vocab and /taxonomy/terms from the Ninja API, and proves that a tone field and a colour field each answer 422.
- POSTs /proposals with a vocabulary_create payload carrying tone, and with extra.colour. It does this once as the platform editor and once as an API key with proposals:write, and expects 422 each time.
- Walks every response schema of the live OpenAPI. It fails on any property named like tone, colo(u)r, pill, badge or phrase, and on any vocabulary reference that is not exactly {key, kind, label}.

Urgency's kind is left as it is (open question).

**Owned paths:**

- `backend/apps/shared/schemas.py`
- `backend/apps/taxonomy/schemas.py`
- `backend/apps/taxonomy/tenant_lists_logic.py`
- `backend/apps/proposals/schemas.py`
- `backend/apps/proposals/logic.py`
- `backend/apps/shared/tests_scenarios.py`

**Done when:**

All of the following hold:
- test_nfr_s10 is un-skipped and green, including the POST /proposals cases for both principals.
- The VOC, FP and PRO scenario tests still pass.
- The VOC journeys still pass, which proves the frontend sends no unknown fields.
- No generated file is committed.

**Gates:**

- `cd backend && ./run.sh run python manage.py test apps.taxonomy apps.proposals apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && python backend/scripts/contract_drift.py (then revert openapi.json and api.generated.ts)`
- `cd frontend && npm run test:e2e -- --grep "VOC-S"`

**Invariants:**

A pill's tone is chosen by slot or kind, never by a person. The API returns key and kind, never a phrase. Forbid extra fields only on write bodies and proposal payloads, never on response schemas. A malformed payload is refused when the proposal is made, never when it is approved. The schema walk is generic, so it covers the library routes that land later. Security review runs before merge, because proposals are the library's door (rule 5).

### chunk3-rest-T4: Obligations list read with the footprint

**Requirements:** INV-03, INV-04, INV-05, FP-01, FP-03, NFR-03  
**Scenarios:** none  
**Depends on:** nothing

Build GET /obligations (listObligations), answering {items,total} with limit and offset. Its filters are instrument (stable key), dutyType, term (repeatable, dimension:key), q, asOf and outsideFootprint. asOf defaults to today in the tenant's time zone, and in_force() is the only rule.

Each row carries the brief's facts, plus:
- version, and upcomingVersion {versionNumber, effectiveFrom{date,precision}}.
- scope [{dimension, terms, allSelected}].
- inFootprint, and outsideReason [{dimension, terms}].
- openChangeCount 0, pendingApplicability null and complianceStatus null.

Create library/reading.py for helpers that later reads reuse:
- LocalizedText {text, language, isOriginal, isMachine}, with the language_order fallback.
- PartialDate, and scope by dimension.
- obligation_scopes(): the single place for the rule 'an obligation's terms plus its instrument's regime', with a SQL twin over taxonomy_in_footprint for the list filter.
- The footprint verdict and reason, built on taxonomy.matching.

Add a logic gate, require_library_read, in taxonomy/http.py: a person with library.read in their tenant, or an agent key with library:read. It sits beside the existing require_library_reader (vocabularies: any session), which stays unchanged. Record the gate in UNGATED_BY_DESIGN with its reason.

Create library/testing.py with builders (instrument; obligation with terms and versions) that write inside library_write, for later tasks.

Add an INPUT_DELTAS §7 row for `GET /obligations` (tag filter deferred) and delete its pending line.

This task contributes to INV-S3, INV-S4 and FP-S4, which T6 and T7 un-skip or extend.

**Owned paths:**

- `backend/apps/library/api.py`
- `backend/apps/library/schemas.py`
- `backend/apps/library/reading.py`
- `backend/apps/library/testing.py`
- `backend/apps/library/tests_reading.py`
- `backend/apps/taxonomy/http.py`
- `backend/apps/shared/permissions.py`
- `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

tests_reading.py covers:
- Every filter.
- asOf on 2026-06-30 and 2026-10-01 as fixed dates, with upcomingVersion.
- Rows outside the footprint hidden by default, and returned with their reason when asked.
- allSelected.
- Pagination.
- assertNumQueries equal for one row and for many.
- 403 for a key without library:read and for a tenant role without library.read; 200 for a key with the scope.
- As cw_app, another tenant's private obligation is never returned by the list, the total, q or the filters.

The route-permission, query-ordering and audit-on-write guards pass. Contract drift is clean locally.

**Gates:**

- `cd backend && ./run.sh run python manage.py test apps.library apps.taxonomy apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && python backend/scripts/contract_drift.py (then revert openapi.json and api.generated.ts)`

**Invariants:**

Reads run as cw_app under forced RLS (shared or mine), never on a superuser alias. The footprint rule lives in one place. Responses carry keys, kinds, counts and dates, never a phrase, and no field named tone or pill. Neither q nor tenant content reaches the logs.

Library builders go only in library/testing.py, which the fence exempts; shared/factories.py must not write library models. The builders only insert obligation_version, obligation_summary, provision_version, provision_text and verification rows, with every field set at create time, and never save or update them afterwards: T1's append-only triggers land in the same wave.

Security review runs before merge (rule 5).

### chunk3-rest-T5: Library presentation functions and legal-text components

**Requirements:** NFR-03, INV-01, INV-03, INV-04, INV-05, INV-06  
**Scenarios:** NFR-S8  
**Depends on:** nothing

In features/shared/tone-by-kind.ts, add named slots: the header's 'Guidance, comply or explain' as warning (the row's 'Guidance' stays information) and jurisdiction as brand. Fix presentObligation's header to use the warning slot, as pills-and-labels.md and the obligation card require. Regenerate both pills-gallery baselines: win32 locally, and linux inside mcr.microsoft.com/playwright:v1.63.0-noble following the steps in HANDOVER_2026-09-19.

Add pure, unit-tested presentation:
- presentInstrument: short name as brand; level as information; 'Binding' as information or 'Guidance, comply or explain' as warning; jurisdiction as brand; regime as information.
- Per-dimension scope text: 'All services' when allSelected; 'Not client-specific' or the matching 'not <dimension>-specific' text when a dimension is empty.
- Version and date labels, built on formatPartialDate and including 'Q4 2026': 'Version 2, from 1 Oct 2026', 'In force 3 Jan 2018 to 30 Sep 2026', 'Verified 30 Jun 2026' and 'Outside your footprint: Advice'.

Add two components:
- components/inventory/DiffText.tsx renders segments as ins and del on positive-soft and negative-soft, with accessible added and removed text.
- LegalText.tsx renders a sand block with a brass § margin, an optional machine-translation label and a lang attribute.

Add en and sv messages for all of it.

**Owned paths:**

- `frontend/src/features/shared/tone-by-kind.ts`
- `frontend/src/features/library/obligation-presentation.ts`
- `frontend/src/features/library/obligation-presentation.test.ts`
- `frontend/src/features/library/instrument-presentation.ts`
- `frontend/src/features/library/instrument-presentation.test.ts`
- `frontend/src/features/library/version-presentation.ts`
- `frontend/src/features/library/version-presentation.test.ts`
- `frontend/src/features/shared/presentation-types.ts`
- `frontend/src/shared/utils/format.test.ts`
- `frontend/src/components/inventory/DiffText.tsx`
- `frontend/src/components/inventory/DiffText.test.tsx`
- `frontend/src/components/inventory/LegalText.tsx`
- `frontend/src/components/inventory/LegalText.test.tsx`
- `frontend/src/messages/common/{en,sv}.json`
- `frontend/src/messages/library/{en,sv}.json`
- `frontend/tests/e2e/pills.gallery.spec.ts-snapshots/`

**Done when:**

All of the following hold:
- Unit tests cover every function, including the header's warning tone and quarter precision.
- Component tests cover DiffText and LegalText.
- The linux and win32 pills-gallery baselines are updated, and pills.gallery passes.
- Every pill goes through Pill with a tone from a named slot, and no JSX holds a string literal.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `cd frontend && npx playwright test pills.gallery`

**Invariants:**

Six tones, each chosen by slot or kind in tone-by-kind.ts and never hardcoded at the call site. Pills go only through Pill. No string literals in JSX. Colours come from theme.css tokens (the Green MCP server for anything new). Presentation functions stay pure and take facts, never API phrases.

### chunk3-rest-T6: Obligation detail and diff reads

**Requirements:** INV-03, INV-04, INV-05, INV-06, AC-INV1  
**Scenarios:** INV-S3, INV-S4, INV-S5, INV-S6  
**Depends on:** chunk3-rest-T4, chunk3-rest-T1

Build GET /obligations/{id}?asOf= (getObligation). It returns:
- The version in force, and versions[] with effectiveFrom and its precision, effectiveTo derived from the next version, and approvedAt.
- The summary as of the date in the caller's language order, plus translations[] of that version.
- The title, instrument summary, regime, binding level, duty type, trigger, retention, sanction exposure, product scope, tags, scope with allSelected, and the footprint verdict.
- The cited provisions, by reference and path only, without text (default).
- Related obligations: title, instrument short name, binding and relation.
- Provenance: createdOrigin, createdModel, createdAt, verifiedBy as a PersonRef (null for seeded rows), lastVerifiedAt, sourceUrl and sourceLabel.

Build GET /obligations/{id}/diff?from=&to=&lang= (getObligationDiff). It resolves the two versions and serializes T1's version_diff as {fromVersion, toVersion, fromEffective, toEffective, language, isMachine, segments[{op,text}]}.

Un-skip INV-S3, INV-S4, INV-S5 and INV-S6 in library/tests_scenarios.py:
- INV-S4 uses its own versions dated 2025-01-01 and 2026-10-01, and shows that a raw UPDATE is refused.
- INV-S6 reads as an en user in tenant A, whose original text is sv.

Add INPUT_DELTAS rows for the detail shape (provisions without text), for `GET /obligations/{id}/versions` being embedded in the detail, and for the diff. Re-annotate `GET /obligations/{}/changes` to chunk 5.

**Owned paths:**

- `backend/apps/library/api.py`
- `backend/apps/library/schemas.py`
- `backend/apps/library/reading.py`
- `backend/apps/library/testing.py`
- `backend/apps/library/tests_scenarios.py`
- `backend/apps/library/tests_reading.py`
- `backend/apps/shared/permissions.py`
- `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

All of the following hold:
- INV-S3, S4, S5 and S6 are un-skipped and green.
- An unknown id and another tenant's private obligation both answer 404.
- An unknown version number answers 422.
- The detail's query count is pinned.
- Contract drift is clean locally.

**Gates:**

- `cd backend && ./run.sh run python manage.py test apps.library apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && python backend/scripts/contract_drift.py (then revert openapi.json and api.generated.ts)`

**Invariants:**

Every read goes through shared-or-mine RLS, and a record the caller cannot see answers 404, not 403. in_force() is the only 'as of' rule. No response holds a phrase. verifiedBy is null or a platform person, so no tenant user's name crosses tenants. Version approvers are not named, matching the card. No text is logged. Security review runs before merge (rule 5).

### chunk3-rest-T7: Footprint preview counts and library vocabulary usage

**Note (2026-09-19):** the preview-count half is done by REGULATORY_SCOPE T03, merged with the T01 integration branch: `preview_of` counts through `library.reading.obligation_scopes()` and `matching.in_footprint`, and test_fp_s2 asserts real counts. T7 keeps only the library vocabulary usage counts in `registry.py`.

**Requirements:** FP-02, FP-03, AC-FP1, J-6, VOC-02  
**Scenarios:** FP-S2, FP-S4  
**Depends on:** chunk3-rest-T4, chunk3-rest-T2

Wire taxonomy/footprint_logic.preview_of to count the obligations the proposed adds and removes would hide and reveal, with available: true. It compares the footprint before and after through library.reading.obligation_scopes() and taxonomy.matching.in_footprint. footprint_logic still names no library model. The preview stays counts only (default).

In taxonomy/registry.py, replace _no_usage for duty_type, instrument_level, library_tag, relation_type and provision_kind with real counts from library records, so VOC-02's usage counts and the retire warning are true. Every library foreign key to these lists uses related_name="+" (library/models.py lines 192, 242, 266, 331, 348, 433 and 447), so the existing _count(relation) helper cannot reach them. Count with Subquery and OuterRef over the library models inside registry.py instead. This is fence-safe because registry.py makes no write calls.

Extend the two scenario tests:
- test_fp_s2: removing Advice hides exactly the seeded advice-only obligation, counted in the preview.
- test_fp_s4: GET /obligations hides that obligation, and returns it with outsideFootprint=true and a reason naming the service Advice.

Re-pointing records on a library-list merge stays in chunk 4.

**Owned paths:**

- `backend/apps/taxonomy/footprint_logic.py`
- `backend/apps/taxonomy/registry.py`
- `backend/apps/taxonomy/tests_scenarios.py`
- `backend/apps/taxonomy/tests_vocabulary.py`

**Done when:**

All of the following hold:
- test_fp_s2 and test_fp_s4 are green with real counts.
- The vocabulary list endpoints report non-zero usage for the seeded duty types, levels, tags, relation types and provision kinds.
- The FP-S2 and FP-S5 journeys still pass unchanged.

**Gates:**

- `cd backend && ./run.sh run coverage run manage.py test apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `cd frontend && npm run test:e2e -- --grep "FP-S2|FP-S5"`

**Invariants:**

The preview only reads: a dry run writes nothing. The footprint flow's four eyes, step-up and one audit event per term are untouched. footprint_logic names no library model. library/models.py and library/migrations stay untouched. Do not edit library/reading.py, which T6 owns this wave; if a read function is missing, report it instead. Usage counts run under RLS as cw_app. Security review runs before merge (rule 5).

### chunk3-rest-T8: Seed the FFFS 2017:2 provision tree and its amendment

**Requirements:** INV-01, INV-02, INV-06  
**Scenarios:** none  
**Depends on:** chunk3-rest-T2, chunk3-rest-T1

Add rows per design/screens/tenant-instrument.html, marked from_prototype: false:
- FFFS 2017:2 chapters 9 kap. (Skydd för investerare), 10 kap. and 11 kap.
- Sections 9 kap. 6 § (Betalning för analys), 10 § and 23 §, and at least one paragraph (stycke) under a section, so the tree has three levels.
- A text version for each unit from 2018-01-03 (sv original, en machine translation). For 9 kap. 6 §, also a version 2 from 2026-10-01 carrying the card's transitional note.
- The relation_type row amends (sv Ändrar).
- Sample instrument FFFS 2026:11: FI, SE, authority_regulation, binding, in force 2026-10-01, source fi.se. It amends FFFS 2017:2, and its verified date falls to the anchor date under T2's rule.
- obligation_provisions linking obl-research-payments and obl-costs-charges to their sections.

Load them in load_library, write-once and idempotent, and validate them in check_prototype_data.py. load_library creates Provision rows without _audit() today. Call _audit('provision', …) for every provision created, as the loader already does for instruments and obligations.

Extend the seed guard:
- The tree has three levels.
- 9 kap. 6 § has two versions; the later one is after the anchor date and carries a transitional note.
- There is exactly one library.seeded audit row per provision stable key, and a second load writes none.

Update EXPECTED_LIBRARY (16 instruments) and the tests_library counts.

**Owned paths:**

- `backend/apps/library/fixtures/prototype_data.json`
- `backend/apps/library/fixtures/check_prototype_data.py`
- `backend/apps/library/fixtures/README.md`
- `backend/apps/library/seeds/library.py`
- `backend/apps/shared/e2e_seed.py`
- `backend/apps/shared/tests_seed_integrity.py`
- `backend/apps/library/tests_library.py`

**Done when:**

All of the following hold:
- check_prototype_data.py --eval exits 0.
- The loaders are idempotent under T1's triggers.
- The seed guard asserts the three-level tree, the two 6 § versions, the amends relation, and one audit row per provision with none on reload.
- Counts match everywhere.
- The @smoke journeys pass.

**Gates:**

- `python backend/apps/library/fixtures/check_prototype_data.py --eval`
- `cd backend && ./run.sh run coverage run manage.py test apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/library/seeds/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `cd frontend && npm run test:e2e -- --grep "@smoke"`

**Invariants:**

Leave effective_to null; reads derive it. Texts are written once. The sample texts come from the card and are never presented as verbatim law. Stable keys follow the fixture README's `<instrument>/<unit>` form. Writes happen only inside library_write() in library/seeds, and every record created leaves one record() row. Nothing depends on today's date. Security review runs before merge (rule 5).

### chunk3-rest-T9: Inventory screen: obligations

**Requirements:** INV-03, INV-04, FP-03, J-6, NFR-03  
**Scenarios:** FP-S5  
**Depends on:** chunk3-rest-T4, chunk3-rest-T5, chunk3-rest-T2

Add features/library/{types,api,hooks}.ts for GET /obligations over the regenerated api.generated.ts, with api.test.ts and hooks.test.tsx under the 98% features floor.

Add /inventory: app/(tenant)/inventory/page.tsx renders components/inventory/InventoryScreen.tsx per design/screens/tenant-inventory.html. The screen has:
- A PageHead.
- Regime, service and duty-type filters from useTerms and useVocabularyValues, which store keys.
- An 'As of' date input with its banner and 'Back to today'.
- The 'Show outside footprint' chip.
- ObligationRow, built on presentObligation('row'). It shows the ref label, scope, upcoming version and verified date; a row outside the footprint is dashed and shows its reason. Each row links to /inventory/obligations/[id].
- Two empty states (nothing matches; nothing for the footprint), plus loading, error and restricted states.

Extend FP-S5 in taxonomy.journey.spec.ts: after approval the inventory no longer lists the seeded advice-only obligation, and 'Show outside footprint' shows it dashed with its reason. Find rows by data attribute, never by library copy.

The instrument filter and the Instruments tab come with T17.

**Owned paths:**

- `frontend/src/features/library/types.ts`
- `frontend/src/features/library/api.ts`
- `frontend/src/features/library/hooks.ts`
- `frontend/src/features/library/api.test.ts`
- `frontend/src/features/library/hooks.test.tsx`
- `frontend/src/components/inventory/InventoryScreen.tsx`
- `frontend/src/components/inventory/InventoryScreen.test.tsx`
- `frontend/src/components/inventory/ObligationRow.tsx`
- `frontend/src/components/inventory/InventoryFilters.tsx`
- `frontend/src/app/(tenant)/inventory/page.tsx`
- `frontend/src/messages/inventory/{en,sv}.json`
- `frontend/src/messages/library/{en,sv}.json`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:**

All of the following hold:
- FP-S5 is green with the inventory assertion, and FP-S2 still passes.
- Component and hook tests cover the row mapping, the dashed outside rows and every state.
- The copy matches the card.
- No generated file is edited.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `cd frontend && npm run test:e2e -- --grep "FP-S5|FP-S2"`

**Invariants:**

Pills go only through Pill, via the presentation functions. No string literals in JSX. Filters and URLs carry keys, never labels. The API sends facts, and the screen turns them into phrases. The journey pins its 'as of' date and never relies on today. FP-S5's finally block still restores Advice.

### chunk3-rest-T11a: Problem-report writer and the re-verification stamp (logic)

**Requirements:** INV-06  
**Scenarios:** none  
**Depends on:** chunk3-rest-T1

Add migration 0005_problem_report_context. It gives ProblemReport an optional version_number and an optional language (the Language key), recording what the reader was looking at. It adds no area column; see the open question.

Add library/reports.py with create_report(). It takes a subject that the caller has already resolved, the tenant and reporter from the principal, a description, and the optional version_number and language. It writes the row and a record() under the tenant id, and neither the summary, the payload nor any log line holds the text. The module names no Obligation or Instrument class.

Add apply_reverification() to proposals/apply.py, which is already on the fence allowlist. It writes a Verification row. On no_change it also stamps last_verified_at and verified_by inside library_write(), with one audit row carrying the step-up assertion reference.

Test first:
- library/tests_reports.py: the tenant comes from the caller; the problem_report mixed RLS policy admits the insert as cw_app; audit and outbox rows share the transaction.
- proposals/tests_apply.py: only the stamp fields change on no_change; the other outcomes write a Verification row and no stamp.

Use T4's builders in library/testing.py without editing them.

**Owned paths:**

- `backend/apps/library/models.py`
- `backend/apps/library/migrations/0005_problem_report_context.py`
- `backend/apps/library/reports.py`
- `backend/apps/library/tests_reports.py`
- `backend/apps/proposals/apply.py`
- `backend/apps/proposals/tests_apply.py`

**Done when:**

All of the following hold:
- makemigrations --check is clean, and migrate_from_zero applies 0005 after T1's 0004.
- tests_reports.py and tests_apply.py are green.
- The library-fence guard passes with its allowlist unchanged.
- The coverage floors for apps/proposals/apply.py still hold.

**Gates:**

- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.library apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/library/*,apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

Proposals are the only door into the library; the stamp is the single exception, and it lives in proposals/apply.py. The fence allowlist does not change. Audit and outbox rows are written in the same transaction, through record(). Report text is tenant content: it never reaches logs, outbox payloads or the audit summary. The tenant comes from the principal, never from input. Verification rows are append-only (T1). No new code enum. Security review runs before merge (rule 5).

### chunk3-rest-T11b: Problem-report and re-verification routes

**Requirements:** INV-06  
**Scenarios:** INV-S7, INV-S8  
**Depends on:** chunk3-rest-T6, chunk3-rest-T11a

Build POST /obligations/{id}/problem-reports (reportObligationProblem) and POST /instruments/{id}/problem-reports (reportInstrumentProblem):
- The body is {description, versionNumber?, language?}.
- The routes are gated by problems.report and answer 201 {id, status, createdAt}.
- The subject must be visible through a library.reading lookup, or the route answers 404.
- They call T11a's create_report.

Build POST /obligations/{id}/verifications (reverifyObligation). It takes {outcome, note?}, is session only, and is gated by proposals.review plus requires_step_up. It calls apply_reverification.

Un-skip INV-S7 (the obligation half: the read carries a source link and a verified date, the report is created and acknowledged, and tenant B cannot see it) and INV-S8. Write these assertions first:
- A report whose text holds a unique sentinel leaves the sentinel in no AuditEvent (summary, before, after), in no OutboxEvent payload, and nowhere in the logs captured with assertLogs on the root logger.
- An API key holding every scope is refused (401 or 403) on the verifications route, and no Verification row is written.
- Only the stamp changes.
- The fence scanner flags a module outside the allowlist that writes Obligation.

Add INPUT_DELTAS rows for the three operations; the instrument route and the context fields are not in the design. Remove their pending lines. GET /problem-reports stays in chunk 4.

**Owned paths:**

- `backend/apps/library/api.py`
- `backend/apps/library/schemas.py`
- `backend/apps/library/reading.py`
- `backend/apps/library/testing.py`
- `backend/apps/library/tests_scenarios.py`
- `backend/apps/shared/permissions.py`
- `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

test_inv_s7 and test_inv_s8 are green, including the sentinel and API-key assertions. The tests_scenarios docstring names reportObligationProblem, reportInstrumentProblem and reverifyObligation, and the audit-on-write guard passes.

The refusals answer as follows:
- 403 without problems.report.
- step_up_required without a step-up.
- 403 for any tenant role on verifications.
- 404 for a subject the caller cannot see.

Contract drift is clean locally.

**Gates:**

- `cd backend && ./run.sh run python manage.py test apps.library apps.proposals apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && python backend/scripts/contract_drift.py (then revert openapi.json and api.generated.ts)`

**Invariants:**

No API key scope reaches the library, which the test proves. Step-up is required on the stamp. The tenant comes from the principal, never from the body. Report text never reaches logs, outbox payloads or the audit summary, which the test proves. There is no logic in api.py. Security review runs before merge (rule 5).

### chunk3-rest-T12: Obligation card: header, text, scope, duty and provenance

**Requirements:** INV-03, INV-05, INV-06, NFR-03, AC-FP1  
**Scenarios:** INV-S3, INV-S6, FP-S5  
**Depends on:** chunk3-rest-T6, chunk3-rest-T9, chunk3-rest-T7, chunk3-rest-T8

Add /inventory/obligations/[obligationId]: a thin page that renders components/inventory/ObligationScreen.tsx per design/screens/tenant-obligation.html. The card has:
- A back link, and header pills via presentObligation('header') for instrument, regime and binding level. The compliance status slot stays empty until chunk 8.
- The title.
- The summary in LegalText with language chips from translations[]. The original carries no label, and a machine translation carries its label. A tenant language with no text shows 'No … text yet' with 'Show the original'.
- The scope block, the duty panel and a static versions list.
- Related obligations.
- 'Where it comes from': the source link, 'Last verified <date>', plus 'by <name>' only when verifiedBy is set, and 'Created by'.
- Placeholders for the register overlay and related changes.
- Loading, error, not-found and restricted states.

Un-fixme INV-S3: header order on research payments; 'All services' and 'Not client-specific' on the DORA ICT register; 'Guidance, comply or explain' on ESMA.

Un-fixme INV-S6: an en user sees the labelled machine translation, and 'Show original' reveals the sv text.

Strengthen FP-S5 so the officer's preview shows a non-zero count of hidden obligations (counts only, by default).

**Owned paths:**

- `frontend/src/app/(tenant)/inventory/obligations/[obligationId]/page.tsx`
- `frontend/src/components/inventory/ObligationScreen.tsx`
- `frontend/src/components/inventory/ObligationScreen.test.tsx`
- `frontend/src/components/inventory/ObligationPanels.tsx`
- `frontend/src/features/library/types.ts`
- `frontend/src/features/library/api.ts`
- `frontend/src/features/library/hooks.ts`
- `frontend/src/features/library/api.test.ts`
- `frontend/src/features/library/hooks.test.tsx`
- `frontend/src/messages/inventory/{en,sv}.json`
- `frontend/src/messages/library/{en,sv}.json`
- `frontend/tests/e2e/library.journey.spec.ts`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:**

All of the following hold:
- INV-S3, INV-S6 and FP-S5 are green.
- The not-found journey step declares its 404 with apiGuard.allow.
- Component and hook tests cover every state and the language-chip logic.
- Library titles are found by data attribute or regex.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `cd frontend && npm run test:e2e -- --grep "INV-S3|INV-S6|FP-S5"`

**Invariants:**

Pills go only through Pill. The header tone comes from T5's named slot. No string literals in JSX. Nothing on this card writes. The journey names dates or versions explicitly and never relies on today.

### chunk3-rest-T13: Instruments list and detail reads

**Requirements:** INV-01, INV-06, FP-03  
**Scenarios:** INV-S1, INV-S10, INV-S7  
**Depends on:** chunk3-rest-T11b, chunk3-rest-T8

Build GET /instruments (listInstruments). Its filters are regime, q and outsideFootprint; jurisdiction, level, authority and asOf are deferred (default). Each row carries:
- The short name, the name as LocalizedText, level, binding, jurisdiction, authority, regime and officialRef.
- inForceFrom and inForceTo as PartialDate, and implementsNote.
- obligationCount, inFootprint, lastVerifiedAt and sourceUrl.
obligationCount counts the visible obligations: those in the footprint, or all of them when outsideFootprint is set.

Add instrument_scopes() (the instrument's regime) to library/reading.py, and have obligation_scopes() inherit through it, so one rule serves both.

Build GET /instruments/{id} (getInstrument). It adds eliUri, authority {key, name, shortName, url}, verifiedBy, and lineage [{relation, direction outgoing|incoming, instrument summary, note, toRef}], so the designed `GET /instruments/{id}/relations` is served inside the detail.

Un-skip INV-S1 on FFFS 2017:2. It checks:
- Level, binding and the official reference; ELI null ('where available'); SE and FI.
- In force 3 Jan 2018 with day precision; implements the MiFID II delegated directive; amended by FFFS 2026:11.
- No tenant_id column, and readable by tenants A and B.

Un-skip INV-S10: an in-force date with quarter precision is stored as a date plus 'quarter' and read back as {date, precision}.

Extend test_inv_s7 with the instrument read. Add a test that an instrument row's inFootprint agrees with its obligations' inherited regime under a regime-restricted footprint.

Add INPUT_DELTAS rows (deferred filters, no asOf, relations embedded), and re-annotate `GET /authorities` to chunk 5 in contract_drift_pending.txt.

**Owned paths:**

- `backend/apps/library/api.py`
- `backend/apps/library/schemas.py`
- `backend/apps/library/reading.py`
- `backend/apps/library/testing.py`
- `backend/apps/library/tests_scenarios.py`
- `backend/apps/library/tests_reading.py`
- `backend/apps/shared/permissions.py`
- `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

All of the following hold:
- INV-S1 and INV-S10 are un-skipped and green, and INV-S7 also covers the instrument read.
- The instrument and obligation footprint verdicts agree.
- Another tenant's private instrument answers 404, and never appears in the list or in any lineage.
- Query counts are pinned.
- Contract drift is clean locally.

**Gates:**

- `cd backend && ./run.sh run python manage.py test apps.library apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && python backend/scripts/contract_drift.py (then revert openapi.json and api.generated.ts)`

**Invariants:**

Shared-or-mine RLS applies to every read. Relation rows that point at an instrument the caller cannot see are dropped, never returned with nulls. The footprint rule lives in one place. A legal date is always a date plus a precision, never a timestamp. No response holds a phrase. Stable keys never change. Security review runs before merge (rule 5).

### chunk3-rest-T14: Obligation card: versions, as of, what changed and This looks wrong

**Requirements:** INV-04, INV-06, AC-INV1  
**Scenarios:** INV-S4, INV-S5, INV-S7  
**Depends on:** chunk3-rest-T12, chunk3-rest-T11b

Extend ObligationScreen with:
- Version chips: 'Version 1' and 'Version 2, from 1 Oct 2026'.
- An 'As of' date input that re-reads the obligation, with the banner 'Showing version 1, in force on <date>. Back to today'.
- 'Show what changed', which renders GET /obligations/{id}/diff through DiffText and names both effective dates.
- components/inventory/ReportProblemModal.tsx: 'What looks wrong?', 'What you see', Cancel and 'Send report', then 'Report sent. Thank you.'. It posts {description, versionNumber, language} for what is on screen to POST /obligations/{id}/problem-reports. There is no 'Where' select until Alex answers the open question.

Un-fixme INV-S4: typed as-of dates 2026-06-30 and 2026-10-01 show version 1 and version 2.

Un-fixme INV-S5: research payments version 1 to version 2 marks the added sentences and names both dates.

Un-fixme the obligation half of INV-S7: the source link, 'Verified <date>', and a report sent and acknowledged.

**Owned paths:**

- `frontend/src/components/inventory/ObligationScreen.tsx`
- `frontend/src/components/inventory/ObligationScreen.test.tsx`
- `frontend/src/components/inventory/ObligationPanels.tsx`
- `frontend/src/components/inventory/VersionBar.tsx`
- `frontend/src/components/inventory/VersionBar.test.tsx`
- `frontend/src/components/inventory/ReportProblemModal.tsx`
- `frontend/src/components/inventory/ReportProblemModal.test.tsx`
- `frontend/src/features/library/types.ts`
- `frontend/src/features/library/api.ts`
- `frontend/src/features/library/hooks.ts`
- `frontend/src/features/library/api.test.ts`
- `frontend/src/features/library/hooks.test.tsx`
- `frontend/src/messages/inventory/{en,sv}.json`
- `frontend/src/messages/library/{en,sv}.json`
- `frontend/tests/e2e/library.journey.spec.ts`

**Done when:**

All of the following hold:
- INV-S4, INV-S5 and INV-S7 (obligation) are green.
- The report mutation invalidates nothing it does not need to.
- Component and hook tests cover the version bar, the banner, and the modal's validation and success states.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `cd frontend && npm run test:e2e -- --grep "INV-S4|INV-S5|INV-S7"`

**Invariants:**

Dates are typed into 'as of' and never taken from today. The report text is never logged client-side. The modal uses the Modal primitive and the card's copy. Pills go only through Pill. No string literals in JSX.

### chunk3-rest-T16: Provision tree read and provision diff

**Requirements:** INV-02, INV-04, INV-05  
**Scenarios:** INV-S2  
**Depends on:** chunk3-rest-T13, chunk3-rest-T8, chunk3-rest-T1

Build GET /instruments/{id}/provisions?asOf= (listInstrumentProvisions), answering the tree in a bounded number of queries. Each node is:
{id, stableKey, kind{key,kind,label}, refLabel, heading, path, children[], versions[{versionNumber, effectiveFrom, effectiveTo derived, transitionalNote, text LocalizedText}], inForceVersion, obligations[{id, title, refLabel}]}
The kind comes with its structural kind from ProvisionKind.

Build GET /provisions/{id}/diff?from=&to=&lang= (getProvisionDiff). It resolves the two versions and serializes T1's version_diff with T6's diff response schema. `GET /provisions/{id}/versions` is served inside the tree (INPUT_DELTAS row).

Un-skip INV-S2. The test builds a tree of chapter, section and paragraph, and adds an amendment in force on 2026-11-01 with a transitional note as a new version row. It then proves the as-of reads before and after that date, the diff, and that the earlier row is unchanged. It also asserts the seeded FFFS 2017:2 tree.

**Owned paths:**

- `backend/apps/library/api.py`
- `backend/apps/library/schemas.py`
- `backend/apps/library/reading.py`
- `backend/apps/library/testing.py`
- `backend/apps/library/tests_scenarios.py`
- `backend/apps/library/tests_reading.py`
- `backend/apps/shared/permissions.py`
- `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

All of the following hold:
- INV-S2 is un-skipped and green.
- The tree's query count does not grow with the size of the tree.
- An instrument or provision the caller cannot see answers 404.
- The citing obligations respect visibility.
- No 'chunk 3' pending line remains for the provision operations.
- Contract drift is clean locally.

**Gates:**

- `cd backend && ./run.sh run python manage.py test apps.library apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && python backend/scripts/contract_drift.py (then revert openapi.json and api.generated.ts)`

**Invariants:**

effectiveTo is derived and nothing is updated. in_force() is the only 'as of' rule. Texts carry their language and machine flag. Shared-or-mine RLS applies to every read. No response holds a phrase. Security review runs before merge (rule 5).

### chunk3-rest-T17: Instruments tab and instrument card

**Requirements:** INV-01, INV-06, FP-03, NFR-03  
**Scenarios:** INV-S1, INV-S7  
**Depends on:** chunk3-rest-T13, chunk3-rest-T14

Add the Obligations and Instruments tabs to InventoryScreen, an instrument filter whose options show obligation counts from GET /instruments, and InstrumentRow per the card. 'As of' applies to the Obligations tab only (default).

Add /inventory/instruments/[instrumentId], rendering InstrumentScreen per tenant-instrument.html:
- Header pills via presentInstrument, the in-force line with its precision, and the source.
- An Identity panel: official reference; ELI or 'Not available'; level; binding force; jurisdiction; authority; in force; and last verified.
- 'This looks wrong', which posts to POST /instruments/{id}/problem-reports through T14's modal.
- Lineage: implements, elaborated by, and amended by with its in-force date.
- 'Obligations from this instrument', via GET /obligations?instrument=.
- Loading, error, not-found and restricted states.

Un-fixme INV-S1, and add the instrument half of INV-S7: the card's source link, 'Verified <date>' and a report.

The provision tree panel comes with T18.

**Owned paths:**

- `frontend/src/components/inventory/InventoryScreen.tsx`
- `frontend/src/components/inventory/InventoryScreen.test.tsx`
- `frontend/src/components/inventory/InventoryFilters.tsx`
- `frontend/src/components/inventory/InstrumentRow.tsx`
- `frontend/src/components/inventory/InstrumentScreen.tsx`
- `frontend/src/components/inventory/InstrumentScreen.test.tsx`
- `frontend/src/app/(tenant)/inventory/instruments/[instrumentId]/page.tsx`
- `frontend/src/features/library/types.ts`
- `frontend/src/features/library/api.ts`
- `frontend/src/features/library/hooks.ts`
- `frontend/src/features/library/api.test.ts`
- `frontend/src/features/library/hooks.test.tsx`
- `frontend/src/messages/inventory/{en,sv}.json`
- `frontend/src/messages/library/{en,sv}.json`
- `frontend/tests/e2e/library.journey.spec.ts`

**Done when:**

All of the following hold:
- INV-S1 and the instrument half of INV-S7 are green.
- The FFFS 2017:2 header shows no guidance pill, and the ESMA guidelines header shows 'Guidance, comply or explain'.
- Component and hook tests cover the tabs, the rows and every state.
- The not-found step is declared with apiGuard.allow.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `cd frontend && npm run test:e2e -- --grep "INV-S1|INV-S7|FP-S5"`

**Invariants:**

Pills go only through Pill: the short name and jurisdiction are brand pills, and level, binding and regime are information pills (tones from T5's slots). Legal dates render with their precision. There is no 'Adopted' row, because no such data exists. No string literals in JSX. Filters store keys.

### chunk3-rest-T18: Provision tree on the instrument card

**Requirements:** INV-02, INV-04, INV-05, INV-06  
**Scenarios:** INV-S2, INV-S7  
**Depends on:** chunk3-rest-T16, chunk3-rest-T17

Add components/inventory/ProvisionTree.tsx to InstrumentScreen as the card's disclosure list. Each unit shows:
- The text of the selected version in LegalText, with the machine label when it applies.
- Version chips: 'In force 3 Jan 2018 to 30 Sep 2026' and 'In force from 1 Oct 2026'.
- The transitional note.
- Links to the obligations that cite it.
- 'Show what changed', which renders GET /provisions/{id}/diff through DiffText.

Instruments without a tree show the 'No provisions yet' empty state.

Un-fixme INV-S2 on FFFS 2017:2 9 kap. 6 §, choosing versions by chip and never relying on today's date. Extend it with the provision half of INV-S7: with 6 § expanded, the card shows the instrument's source link and 'Verified <date>'.

**Owned paths:**

- `frontend/src/components/inventory/ProvisionTree.tsx`
- `frontend/src/components/inventory/ProvisionTree.test.tsx`
- `frontend/src/components/inventory/InstrumentScreen.tsx`
- `frontend/src/components/inventory/InstrumentScreen.test.tsx`
- `frontend/src/features/library/types.ts`
- `frontend/src/features/library/api.ts`
- `frontend/src/features/library/hooks.ts`
- `frontend/src/features/library/api.test.ts`
- `frontend/src/features/library/hooks.test.tsx`
- `frontend/src/messages/inventory/{en,sv}.json`
- `frontend/src/messages/library/{en,sv}.json`
- `frontend/tests/e2e/library.journey.spec.ts`

**Done when:**

All of the following hold:
- INV-S2 is green, including the provision step for the source link and verified date.
- Component tests cover expanding and collapsing, choosing a version chip, the transitional note, the diff toggle and the empty state.
- The tree is keyboard-operable.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `cd frontend && npm run test:e2e -- --grep "INV-S2|INV-S1|INV-S7"`

**Invariants:**

The journey selects versions explicitly, because the default version flips on 2026-10-01. Legal text is shown as stored, with its language. No string literals in JSX. Pills go only through Pill.

### chunk3-rest-T19: Security sweep over the whole chunk

**Requirements:** INV-01, INV-02, INV-06, FP-03, NFR-03  
**Scenarios:** none  
**Depends on:** chunk3-rest-T1, chunk3-rest-T2, chunk3-rest-T3, chunk3-rest-T4, chunk3-rest-T5, chunk3-rest-T6, chunk3-rest-T7, chunk3-rest-T8, chunk3-rest-T9, chunk3-rest-T11a, chunk3-rest-T11b, chunk3-rest-T12, chunk3-rest-T13, chunk3-rest-T14, chunk3-rest-T16, chunk3-rest-T17, chunk3-rest-T18

A read-only review of `git diff 51f9efa..main` after T18 has merged. It complements the per-branch reviews done at merge (rule 5) with checks that only show across the whole chunk:
- The library fence allowlist and LIBRARY_WRITE_ALLOWED_DIRS are unchanged since 51f9efa.
- No tenant content (problem-report text, q) reaches logs, Sentry or outbox payloads, frontend logger calls included.
- Every new library GET carries the library-read gate with a justified UNGATED_BY_DESIGN entry, and the key-scope path works.
- No response field names a tone or a phrase.
- Lineage, the provision tree's citing obligations and both diffs never reveal a record the caller cannot see.
- verifiedBy is never a tenant user.

**Owned paths:**


**Done when:**

A findings report ranked by severity, each finding with its file, line and failure scenario. Either no critical or high finding remains, or each one has become a fix task that merges before T20.

**Gates:**

- `Read-only review of git diff 51f9efa..main against CLAUDE.md section 5 and playbook 4.2 and 4.3`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write apps.shared.tests_scenarios --settings=config.test_settings --noinput`

**Invariants:**

Read-only: it edits no file. Its findings are data for the main agent and are never applied here. It covers tenancy, the library fence, audit and logging across the whole chunk.

### chunk3-rest-T20: Close chunk 3: statuses, floors and ledger

**Requirements:** INV-01, INV-02, INV-03, INV-04, INV-05, INV-06, NFR-03  
**Scenarios:** none  
**Depends on:** chunk3-rest-T1, chunk3-rest-T2, chunk3-rest-T3, chunk3-rest-T4, chunk3-rest-T5, chunk3-rest-T6, chunk3-rest-T7, chunk3-rest-T8, chunk3-rest-T9, chunk3-rest-T11a, chunk3-rest-T11b, chunk3-rest-T12, chunk3-rest-T13, chunk3-rest-T14, chunk3-rest-T16, chunk3-rest-T17, chunk3-rest-T18, chunk3-rest-T19

After every task has merged:
- Set INV-01 to INV-06 to built in library/app.md; INV-07 stays pending. Note under INV-S7 that provisions are shown and reported through their instrument's card for now.
- Update the FP-02, FP-03 and VOC-02 notes in taxonomy/app.md (the preview shows counts only), and the NFR-03 note in shared/app.md.
- Add coverage floors, each with its measured value, statement count and date from a full run: apps/library/api.py, apps/library/reading.py and apps/library/reports.py. Restate logic.py, the seeds, proposals/apply.py and every other touched floored module.
- Mark the chunk 3 rows built in UI_Implementation_Plan.md, noting the deviations: no 'Adopted' row; no 'Where' select; the register overlay, related changes and library updates come in later chunks.
- Write the chunk 3 row in IMPLEMENTATION_STATUS.md, naming what was cut: GET /problem-reports to chunk 4, GET /authorities to chunk 5, FP-S4's other surfaces, and merge re-pointing to chunk 4.
- Copy every item under 'Defaults taken', together with the open questions (urgency tone, problem area), into TODO_FOR_alex.md.
- Confirm that no 'chunk 3' line remains in contract_drift_pending.txt and that requirements coverage passes.

**Owned paths:**

- `backend/apps/library/app.md`
- `backend/apps/taxonomy/app.md`
- `backend/apps/shared/app.md`
- `backend/scripts/coverage_gate.py`
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `docs/plans/UI_Implementation_Plan.md`
- `docs/TODO_FOR_alex.md`

**Done when:**

All of the following hold:
- The status cells, floors and ledger rows match what is merged.
- coverage_gate.py passes on a full run, with the measured values and dates restated, including the new library api.py floor.
- requirements_coverage.py and contract_drift.py pass.
- TODO_FOR_alex lists every default taken and both open questions.

**Gates:**

- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `python backend/scripts/requirements_coverage.py`
- `python backend/scripts/contract_drift.py`
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

Floors sit just below the measured coverage and are never lowered to go green. Status stays 'built', not 'verified', until the owner has exercised it against a running server. Anything that needs a person goes to TODO_FOR_alex.md.
