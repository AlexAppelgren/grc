# PRD 0.3 features: the implementation tasks

Every implementation task from the three analyses Alex asked for on 2026-09-19,
with its final IDs, grouped by the chunk that carries it. Written by the PRD 0.3
consolidation (`PRD_0_3_CONSOLIDATION.md`), which landed the PRD bump, the
decisions D-18 to D-47, ADRs 0026 to 0041, the `INPUT_DELTAS` rows, the `app.md`
rows and scenarios with their skipped and fixme stubs, and the plan updates. The
pure documentation tasks of the three briefs are therefore **not** listed here:
they are done.

Sources: `REGULATORY_SCOPE.md` (T01 to T15), `MY_WORK_AND_MARKETS.md` (T-01 to
T-44) and `STANDARDS.md` (STD-01 to STD-33). Each brief now opens with a
"Final IDs (PRD 0.3)" section; read that column, never the drafted IDs.

**How to read a task.** Each runs in its own worktree or cloud session
(`docs/runbooks/WORKTREES.md`), test-first, ending with its own gates and
`bash scripts/prepush.sh --quick`. "Depends on" names other `f03-*` tasks and,
where it matters, the chunk tasks in `CHUNK3_TASKS.md` and `CHUNK4_TASKS.md`,
whose existing tasks this file does not change.

**One ordering that is easy to get wrong.** `chunk3-rest-T4` (`library/reading.py`,
the single scope rule) is being built right now without jurisdiction terms.
`f03-T36`, which derives a record's jurisdiction, therefore runs **after** it and
extends that one rule; it never adds a second one. `f03-T03` is the same work as
`chunk3-rest-T7` and is built there, once.

**Can start now** (nothing but `main` is needed): f03-T04, f03-T05, f03-T11,
f03-T12, f03-T14, f03-T15, f03-T18, f03-T22, f03-T34, f03-T44 and f03-T60.
f03-T01 and f03-T02 are next in line and are held only by a file conflict:
`chunk3-rest-T2` owns the same seed files and `chunk4-T2` the next taxonomy
migration number, so they go first. Everything else waits for a task above it,
or for the chunk that owns the code it touches.

**Nothing is seeded before `f03-T34`.** No fact about ISO, IAF, PCI SSC, Swift or
a national standards body was fetched in the consolidation session, so every one
of them is unverified, listed in `docs/TODO_FOR_alex.md`, and **no** Verification
log row claims otherwise.

## Regulatory scope: the page, its guards and its name (now, R1)

These sit on chunk 2's built footprint code and need nothing from chunk 3's read
API. `f03-T03` is the same work as `chunk3-rest-T7`, so it is built once, there.

### f03-T01 — Seed Banking and Payments, and stop the seeds undoing approved proposals

**From:** REGULATORY_SCOPE T01

**Depends on:** chunk3-rest-T2 (same seed files)

**Owned paths:** `backend/apps/library/fixtures/prototype_data.json`, `backend/apps/taxonomy/seeds/__init__.py`, `backend/apps/taxonomy/tests_vocabulary.py`, `backend/apps/shared/e2e_seed.py`

**Done when:** `check_prototype_data.py` and the full backend suite pass. The fixture diff is two regime terms, two scope rows and one usage note; no key is renamed, removed or reordered. A term or library list row whose sort order, active flag or default changed after seeding keeps it on the next run, proved by a test, and each row the seed creates records its own audit event.

### f03-T02 — One decision per scope request, one waiting request per organisation

**From:** REGULATORY_SCOPE T02 (FP-S6)

**Depends on:** chunk4-T2 (same taxonomy migration number)

**Owned paths:** `backend/apps/taxonomy/models.py`, `backend/apps/taxonomy/migrations/`, `backend/apps/taxonomy/footprint_logic.py`, `backend/apps/taxonomy/api.py`, `backend/apps/taxonomy/tests_footprint.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** `makemigrations --check` is clean and `migrate_from_zero` passes. In the race tests exactly one decision lands and the other answers 409. A second pending insert raises, and the API answers 409 `request_pending`. Per-term audit events name their request. `test_fp_s6` is un-skipped and green; FP-S3 and the existing four-eyes, If-Match and route-permission tests pass unchanged.

### f03-T03 — The preview counts the obligations a change hides and reveals

**From:** REGULATORY_SCOPE T03, built as chunk3-rest-T7

**Depends on:** f03-T02, f03-T25 (the preview must pass `opt_in`)

**Owned paths:** `backend/apps/taxonomy/footprint_logic.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** FP-S2 asserts real obligation counts with the counted flag true. A pending request's preview reflects a library change made after the request. The approval event carries the counts it was approved against. The OpenAPI drift check is clean and `GET /tenant/footprint` stays under `API_BUDGET_MS` on the seeded data.

### f03-T04 — Footprint becomes Regulatory scope in every string people read

**From:** REGULATORY_SCOPE T04  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `frontend/src/messages/footprint/{en,sv}.json`, `frontend/src/messages/nav/{en,sv}.json`, `frontend/src/messages/tenant-admin/{en,sv}.json`, `frontend/src/messages/today/{en,sv}.json`, `frontend/tests/e2e/taxonomy.journey.spec.ts`, `frontend/tests/e2e/shell.journey.spec.ts`, `frontend/src/features/footprint/footprint-presentation.test.ts`, `backend/apps/shared/permissions.py`, `backend/apps/identity/roles_logic.py`

**Done when:** No value in any `frontend/src/messages/<namespace>/{en,sv}.json` matches /footprint|(?<!finger)avtryck/i. The passkey prompts are untouched. `npm run check:messages`, the unit tests, the backend tests, and the taxonomy and shell journeys pass. The scenario prose in `taxonomy/app.md` already says "regulatory scope"; only the code and copy change here.

### f03-T05 — Primitives: dark danger hover, head actions on the right, group hint under the legend

**From:** REGULATORY_SCOPE T05  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `frontend/src/styles/theme.css`, `frontend/src/styles/contrast.test.ts`, `frontend/src/components/ui/Button.tsx`, `frontend/src/components/ui/PageHead.tsx`, `frontend/src/components/ui/Field.tsx`, `frontend/src/components/ui/primitives.test.tsx`

**Done when:** `contrast.test.ts` passes with the new pair in light and dark. A primitives test shows the group hint comes before the first option and is referenced by the fieldset. The API keys and members journeys pass. No copy changes.

### f03-T06 — Presentation rules for scope groups

**From:** REGULATORY_SCOPE T06

**Depends on:** f03-T04

**Owned paths:** `frontend/src/features/footprint/footprint-presentation.ts`, `frontend/src/features/footprint/footprint-presentation.test.ts`, `frontend/src/messages/footprint/{en,sv}.json`

**Done when:** Vitest passes with the new cases: channel, lifecycle stage, theme and termless dimensions are excluded; narrowing is detected and widening is not; the pending pill's tone is `warning`. The screen does not change yet.

### f03-T07 — Read state by default; checkboxes only after Propose a change

**From:** REGULATORY_SCOPE T07

**Depends on:** f03-T05, f03-T06

**Owned paths:** `frontend/src/components/admin/FootprintScreen.tsx`, `frontend/src/messages/footprint/{en,sv}.json`, `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** `FootprintScreen` no longer imports `Chip`. Before "Propose a change" the page has no checkbox. Channel, lifecycle stage, theme and termless dimensions do not render. While a request waits, a removed term shows "Removed when approved". FP-S2 and FP-S5 pass.

### f03-T08 — The change panel, the status line and focus

**From:** REGULATORY_SCOPE T08

**Depends on:** f03-T07, f03-T03

**Owned paths:** `frontend/src/components/admin/FootprintScreen.tsx`, `frontend/src/components/admin/FootprintScreen.test.tsx`, `frontend/src/messages/footprint/{en,sv}.json`, `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** The component test shows that after a send the status line has focus and reads "Sent for approval.", that the warn notice renders for a narrowing draft and not for a widening one, and that exactly one cancel button exists during an edit. FP-S2 and FP-S5 pass against the real API, and FP-S2 asserts an obligation count in the Hides column.

### f03-T09 — Pending banner, approve and reject dialogs

**From:** REGULATORY_SCOPE T09

**Depends on:** f03-T08

**Owned paths:** `frontend/src/components/admin/FootprintScreen.tsx`, `frontend/src/components/admin/FootprintScreen.test.tsx`, `frontend/src/messages/footprint/{en,sv}.json`, `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** The component test shows that after approve and after withdraw the status line has focus, that nothing inside a warn notice uses muted or negative text, and that a blank reject submit focuses the text area with `aria-invalid` true. FP-S2 and FP-S5 pass.

### f03-T10 — Members without scope permissions, proved end to end

**From:** REGULATORY_SCOPE T10 (FP-S7)

**Depends on:** f03-T09

**Owned paths:** `frontend/src/components/home/TodayScreen.tsx`, `frontend/tests/e2e/taxonomy.journey.spec.ts`, `frontend/tests/e2e/shell.journey.spec.ts`

**Done when:** FP-S7 is un-fixme'd and passes for the reader, approver and compliance officer logins, with no mocked API. The reader sees no "Set … under Admin" link. The full taxonomy, shell and tenants journeys pass.

### f03-T11 — Prototype: an Admin-only regulatory scope view with checkboxes and a request

**From:** REGULATORY_SCOPE T11  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `design/prototype/index.html`

**Done when:** Checked in a browser: a user with neither permission has no link and sees a restricted message. A requester can tick only after "Propose a change". "Request approval" leaves a pending banner and changes nothing until Withdraw. Emptying Regimes shows every obligation. Settings has no toggles. No console errors, no horizontal scroll at 375 px.

### f03-T12 — Design card: read and edit states

**From:** REGULATORY_SCOPE T12  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `design/screens/admin-footprint.html`

**Done when:** The card renders in light and dark with no horizontal scroll at 375 px. The header comment lists FP-01, FP-02, FP-03, AC-FP1 and J-6. The wording matches the spec's string table.

### f03-T13 — Design card: pending and decision states

**From:** REGULATORY_SCOPE T13

**Depends on:** f03-T12

**Owned paths:** `design/screens/admin-footprint.html`

**Done when:** Every state in the spec's section 4 appears once. The Swedish approver banner fits at 375 px with at most two buttons per row. Only `text-fg` is used inside warn notices.

### f03-T14 — Scope wording across the other design cards

**From:** REGULATORY_SCOPE T14  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `design/screens/tenant-*.html`, `design/screens/admin-members.html`, `design/screens/admin-organisation.html`, `design/screens/states.html`, `design/screens/auth-step-up.html`

**Done when:** `grep -i footprint` over those files finds only the `/admin/footprint` route and the FP IDs.

## Markets (now, R1; the views follow in chunks 3 and 5)

These need chunk 2 (built) and chunk 3's data layer (on `main`). None of them
needs a chunk 3 route.

### f03-T15 — Record that EU rules reach Norway

**From:** MY_WORK_AND_MARKETS T-11  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `backend/apps/library/seeds/__init__.py`, `backend/apps/library/models.py`, `backend/apps/library/fixtures/prototype_data.json`, `backend/apps/library/tests_library.py`

**Done when:** After the reference seed, the jurisdictions read returns the EU as Norway's parent. `makemigrations --check` reports nothing and `check_prototype_data` passes.

### f03-T16 — Mirror the jurisdiction rows as taxonomy terms

**From:** MY_WORK_AND_MARKETS T-12

**Depends on:** f03-T15

**Owned paths:** `backend/apps/taxonomy/models.py`, `backend/apps/taxonomy/migrations/`, `backend/apps/taxonomy/seeds/__init__.py`, `backend/apps/taxonomy/tests_vocabulary.py`

**Done when:** A guard test asserts the mirror is exact in both directions. The regulatory scope page lists the five jurisdiction terms, and the International row (f03-T30) gets none. A second seed run changes nothing.

### f03-T17 — Refuse proposals and tagging in the mirrored dimension

**From:** MY_WORK_AND_MARKETS T-13 (FP-S12)

**Depends on:** f03-T16

**Owned paths:** `backend/apps/taxonomy/library_lists_logic.py`, `backend/apps/proposals/apply.py`, `backend/apps/proposals/tests_apply.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** `test_fp_s12` is un-skipped and green on Postgres. The refusal is decided from the data, never from a dimension key.

### f03-T18 — Add the watched market model

**From:** MY_WORK_AND_MARKETS T-15  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `backend/apps/taxonomy/models.py`, `backend/apps/taxonomy/migrations/`

**Done when:** The row-level-security structural guard (NFR-S3) passes. The migration applies from zero and reverses.

### f03-T19 — Write the markets logic

**From:** MY_WORK_AND_MARKETS T-16 (FP-S11)

**Depends on:** f03-T16, f03-T18

**Owned paths:** `backend/apps/taxonomy/markets_logic.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** `test_fp_s11` is green. Levels are computed with operating first, watch and unwatch go through `record()` with keys only, a repeated watch answers 409 `already_watching`, and unknown, inactive or non-country keys are refused. Audit and outbox rows are written in the same transaction, and scope approval is untouched.

### f03-T20 — Serve markets on the footprint routes

**From:** MY_WORK_AND_MARKETS T-17 (FP-S10)

**Depends on:** f03-T19

**Owned paths:** `backend/apps/taxonomy/api.py`, `backend/apps/taxonomy/schemas.py`, `backend/apps/taxonomy/http.py`, `openapi.json`, `frontend/src/types/api.generated.ts`

**Done when:** `test_fp_s10` is green. The route-permissions guard (NFR-S13) passes. The jurisdiction key rides in the body of both watching routes and never in a path or query string. The contract drift check passes against the INPUT_DELTAS §7 rows.

### f03-T21 — Prove markets are isolated and stay out of logs

**From:** MY_WORK_AND_MARKETS T-20 (FP-S14)

**Depends on:** f03-T20

**Owned paths:** `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** `test_fp_s14` is green: cross-tenant reads and removals answer 404, and the access-log request line, the application log and the scrubbed error-reporting transaction hold no jurisdiction key.

### f03-T22 — Design the markets panel and the watched-market view

**From:** MY_WORK_AND_MARKETS T-09  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `design/screens/admin-footprint.html`, `design/screens/tenant-inventory.html`, `design/screens/tenant-watch.html`

**Done when:** The cards render in both themes, use only existing pill tones, and every string maps to a catalog key. The panel names the jurisdiction group as the markets we operate in, shows Operating as meta text or a Watching switch, and has its read-only and denied states.

### f03-T23 — Add the 'Markets we watch' panel to the Regulatory scope screen

**From:** MY_WORK_AND_MARKETS T-18

**Depends on:** f03-T22, f03-T20, f03-T09

**Owned paths:** `frontend/src/features/footprint/`, `frontend/src/components/admin/FootprintScreen.tsx`, `frontend/src/messages/footprint/{en,sv}.json`

**Done when:** The screen matches the updated `admin-footprint.html` in both themes. The frontend compares no dimension key. `check:messages` passes, and the footprint unit tests and J-6 stay green.

### f03-T24 — Seed markets and turn on the markets end-to-end tests

**From:** MY_WORK_AND_MARKETS T-19

**Depends on:** f03-T36, f03-T23

**Owned paths:** `backend/apps/shared/e2e_seed.py`, `backend/apps/shared/tests_seed_integrity.py`, `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:** The seed-integrity counts are unchanged. J-6 and the FP-S8 and FP-S10 journeys are un-fixme'd and green against the real stack. Tenant B holds no market.

## Standards: the rules that must land before any standard exists (now, chunk 3)

The opt-in rule edits a built, SQL-mirrored rule, so it lands before any record
carries a standard term. Nothing in this group may be seeded before `f03-T34`
has logged the facts it rests on.

### f03-T25 — Add the opt-in kind to the matcher and the pure rule

**From:** STANDARDS STD-04

**Depends on:** f03-T02

**Owned paths:** `backend/apps/taxonomy/models.py`, `backend/apps/shared/kinds.py`, `backend/apps/taxonomy/matching.py`, `backend/apps/taxonomy/footprint_logic.py`, `backend/apps/taxonomy/tests_matching.py`

**Done when:** The pure cases pass: an opt-in dimension missing from the scope mapping returns false without a TypeError; an opt-in dimension whose restricting flag is false still restricts; scope dimensions are unchanged. Calling the rule without the opt-in argument raises TypeError. The kinds guard and mypy pass.

### f03-T26 — Replace the SQL footprint function for opt-in dimensions

**From:** STANDARDS STD-05 (FP-S17)

**Depends on:** f03-T25, chunk4-T2 (migration number)

**Owned paths:** `backend/apps/taxonomy/migrations/`, `backend/apps/taxonomy/tests_matching.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** `migrate_from_zero` and the reverse migration pass. `test_fp_s17` is un-skipped and green, with the mirror suite covering a dimension missing from the scope and the flag set false. The row-level-security test still passes.

### f03-T27 — Seed the standards dimension and its first term

**From:** STANDARDS STD-06

**Depends on:** f03-T26, f03-T01, chunk3-rest-T2

**Owned paths:** `backend/apps/taxonomy/seeds/__init__.py`, `backend/apps/library/fixtures/prototype_data.json`

**Done when:** The reference seed is idempotent and records one creation event per row it creates, under f03-T01's rule. `check_prototype_data.py` passes. No end-to-end tenant's scope holds the term, and the term's usage note names its regime.

### f03-T28 — Show opt-in groups on the Regulatory scope page

**From:** STANDARDS STD-07

**Depends on:** f03-T27, f03-T06, f03-T07

**Owned paths:** `backend/apps/taxonomy/schemas.py`, `frontend/src/features/footprint/footprint-presentation.ts`, `frontend/src/features/footprint/footprint-presentation.test.ts`, `frontend/src/components/admin/FootprintScreen.tsx`, `frontend/src/messages/footprint/{en,sv}.json`

**Done when:** The presentation tests cover both empty-group texts ("None followed" for an opt-in group) and keep opt-in groups out of the narrowing list. No string literal appears in JSX. The contract drift gate passes.

### f03-T29 — Add the optional standard level kind and the provision trigger

**From:** STANDARDS STD-08

**Depends on:** f03-T26, chunk3-rest-T1, chunk3-rest-T8

**Owned paths:** `backend/apps/taxonomy/models.py`, `backend/apps/taxonomy/registry.py`, `backend/apps/shared/kinds.py`, `backend/apps/taxonomy/migrations/`, `backend/apps/library/migrations/`, `backend/apps/library/fixtures/prototype_data.json`, `backend/apps/library/fixtures/check_prototype_data.py`

**Done when:** The five existing levels keep a null kind. Inserting a provision under a standard-level instrument raises, on insert and on a move. `check_prototype_data --eval` passes and the kinds guard is green.

### f03-T30 — Add the International jurisdiction

**From:** STANDARDS STD-09

**Depends on:** chunk3-rest-T1, f03-T16 (which must give it no mirrored term)

**Owned paths:** `backend/apps/library/models.py`, `backend/apps/library/migrations/`, `backend/apps/library/seeds/`, `backend/apps/shared/kinds.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** The amended I18N-S1 is green with the new row in its expected set. The jurisdictions read returns the row with kind `international`. The seed is idempotent, and the markets derivation derives nothing for it.

### f03-T31 — Require a regime on every instrument

**From:** STANDARDS STD-10

**Depends on:** f03-T30

**Owned paths:** `backend/apps/library/models.py`, `backend/apps/library/migrations/`, `backend/apps/library/tests_scenarios.py`

**Done when:** The database half of `test_inv_s12` is green and the seed still loads all 15 fixture instruments. Every seeded instrument's regime is a term of the regime dimension.

### f03-T32 — Choose the binding pill from the level kind

**From:** STANDARDS STD-11

**Depends on:** f03-T29, chunk3-rest-T5, chunk3-rest-T13

**Owned paths:** `frontend/src/features/library/obligation-presentation.ts`, `frontend/src/features/library/obligation-presentation.test.ts`, `design/system/pills-and-labels.md`, `frontend/src/messages/common/{en,sv}.json`, `frontend/src/messages/library/{en,sv}.json`

**Done when:** The presentation tests cover a null kind with binding true, a null kind with binding false, and `standard`. A standard never shows "Guidance, comply or explain". The pill gallery check passes.

### f03-T33 — Show the licensed-text empty state on a standard's provision tree

**From:** STANDARDS STD-12

**Depends on:** f03-T32, chunk3-rest-T18, f03-T35

**Owned paths:** `frontend/src/features/library/`, `frontend/src/messages/library/{en,sv}.json`, `frontend/tests/e2e/library.journey.spec.ts`

**Done when:** INV-S11 is un-fixme'd and green against the real stack. The empty, loading, error and denied states are all present.

### f03-T34 — Fetch and log the outside facts a standard rests on

**From:** STANDARDS STD-03 (its fetching half; the TODO half is done)  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `docs/plans/Verification_Log.md`

**Done when:** Each fact of STANDARDS §9 is a row with its source URL and a date, or a row marked not verified with its reason: the current edition, its stage and amendment; the catalogue page and any feed; the Annex exclusion rule; the accreditation transition dates; the certification cycle; the systematic review cycle; the Nordic national adoptions; the payment-card version practice; the messaging-scheme attestation window; and the licence and website terms of every publisher and member body named. Nothing is written from memory. **Blocking:** `f03-T35` may not start until this is green.

### f03-T35 — Add the first standard to the demo fixture

**From:** STANDARDS STD-13

**Depends on:** f03-T34, f03-T27, f03-T29, f03-T30, f03-T31, chunk3-rest-T13

**Owned paths:** `backend/apps/library/fixtures/prototype_data.json`, `backend/apps/library/seeds/library.py`, `backend/apps/library/tests_scenarios.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** `check_prototype_data` passes, including `--eval`. The integration halves of INV-S11 and FP-S16 are green. Every date cites a Verification log row, there are no provisions and no relation rows, and no real clause or control title appears anywhere in the repository.

## Chunk 3: the read API and the inventory

These need chunk 3's own tasks. `chunk3-rest-T4` is being built now without
jurisdiction terms, so `f03-T36` extends that one rule rather than adding a
second one.

### f03-T36 — Derive a record's jurisdiction inside chunk 3's scope rule

**From:** MY_WORK_AND_MARKETS T-14 (FP-S9)

**Depends on:** f03-T16, **chunk3-rest-T4** (it must land first)

**Owned paths:** `backend/apps/library/reading.py`, `backend/apps/taxonomy/tests_scenarios.py`

**Done when:** `test_fp_s9` and `test_fp_s8` are green. The SQL twin appends the derived term ids to the array it already passes, and no migration touches the matching function. Chunk 3's footprint agreement test stays green. Nothing is stored on the record.

### f03-T37 — Add the watched-market view to the inventory

**From:** MY_WORK_AND_MARKETS T-21 (FP-S13)

**Depends on:** f03-T36, f03-T19, chunk 3's list routes and inventory screen

**Owned paths:** `backend/apps/library/api.py`, `backend/apps/library/schemas.py`, `backend/apps/library/reading.py`, `frontend/src/features/library/`, `frontend/src/messages/inventory/{en,sv}.json`, `frontend/src/messages/library/{en,sv}.json`

**Done when:** `test_fp_s13` and its journey are green. The lists take one footprint filter value (`in|all|watched`), replacing the designed pair, and return each row's jurisdiction. No new pill. FP-S4 stays green with the `all` value.

## Chunk 4: the queue and the console

### f03-T38 — Add one standards check at proposal creation, correction and apply

**From:** STANDARDS STD-14 (PRO-S11)

**Depends on:** f03-T25, f03-T29, chunk4-T1, chunk4-T6

**Owned paths:** `backend/apps/proposals/standards.py`, `backend/apps/proposals/logic.py`, `backend/apps/proposals/apply.py`, `backend/apps/proposals/tests_scenarios.py`

**Done when:** `test_pro_s11` is green. A refusal at creation stores no proposal; a refusal at approval writes nothing and no audit row. The check runs at the API, at the agent path, over a reviewer's corrections and at apply.

### f03-T39 — Add the out-of-scope rejection reason

**From:** STANDARDS STD-15

**Depends on:** chunk4-T2

**Owned paths:** `backend/apps/taxonomy/seeds/__init__.py`

**Done when:** The amended PRO-S9 is green. The row has en and sv labels and a usage note naming the PRD's sector scope, is seeded create-only, and a relabel survives a redeploy.

### f03-T40 — A console edit of a jurisdiction updates its mirrored term

**From:** MY_WORK_AND_MARKETS T-08 (the CHUNK4_BRIEF half, moved here so chunk 4's own tasks are untouched)

**Depends on:** f03-T16, chunk 4's console vocabulary screens

**Owned paths:** `backend/apps/taxonomy/seeds/__init__.py`, `backend/apps/library/logic.py`, `backend/apps/taxonomy/tests_vocabulary.py`

**Done when:** Editing a jurisdiction's labels or active flag in the console updates its mirrored term in the same transaction, and the mirror guard test still passes in both directions.

## Chunk 5: watch, the agent API and the evaluation gate

### f03-T41 — Give changes their jurisdiction and add the view to the feed

**From:** MY_WORK_AND_MARKETS T-22 (FP-S15)

**Depends on:** f03-T37, chunk 5's change model and feed

**Owned paths:** `backend/apps/watch/api.py`, `backend/apps/watch/logic.py`, `frontend/src/features/watch/`

**Done when:** `test_fp_s15` and its journey are green. A change's jurisdiction terms are derived from its authority at match time, a change with no authority is not restricted by jurisdiction, and the feed takes the same single footprint filter value.

### f03-T42 — Extend the standards check to instrument, obligation and provision proposals

**From:** STANDARDS STD-16 (PRO-S10, INV-S12)

**Depends on:** f03-T38, f03-T31, chunk 5's proposal kinds

**Owned paths:** `backend/apps/proposals/standards.py`, `backend/apps/proposals/apply.py`, `backend/apps/proposals/tests_scenarios.py`, `backend/apps/library/tests_scenarios.py`

**Done when:** `test_pro_s10` and the proposal half of `test_inv_s12` are green, covering `licensed_text` for provisions and non-URL field sources, `one_conformance_obligation`, `not_a_regime`, and an update that would move an instrument with provisions to the standard level.

### f03-T43 — Add the watch rules for regime and standards

**From:** STANDARDS STD-17 (WAT-S10, WAT-S11)

**Depends on:** f03-T30, f03-T35, chunk 5's sources, source documents, change registration and CAS-01

**Owned paths:** `backend/apps/watch/logic.py`, `backend/apps/watch/api.py`, `backend/apps/watch/tests_scenarios.py`, `backend/config/settings.py`, `backend/apps/library/fixtures/prototype_data.json`

**Done when:** `test_wat_s10` and `test_wat_s11` are green. The settings test lists `STANDARDS_PUBLISHER_HOSTS`. Case creation computes the footprint match with the opt-in rule, and the standards-body source kind exists and is seeded inactive.

### f03-T44 — Add sector scope and standards to the watch-sweeper prompt

**From:** STANDARDS STD-18  ·  **Can start now**

**Depends on:** nothing (the prompt is still a draft, so it is edited in place)

**Owned paths:** `agents/watch-sweeper/v1/prompt.md`

**Done when:** The prompt still reads status draft. No list of dimension keys remains in it: it reads the dimensions that restrict or are opt-in at run start. The scope and standards sections are present, and the agent eval README references the new rules.

### f03-T45 — Extend the watch-sweeper definition and run stats

**From:** STANDARDS STD-19

**Depends on:** f03-T44, chunk 5's agent run schemas

**Owned paths:** `agents/watch-sweeper/v1/definition.yaml`, `backend/apps/agents/schemas.py`, `backend/apps/agents/tests_scenarios.py`

**Done when:** The amended AGT-S3 and the run-stats half of `test_agt_s12` are green. The definition reads the instrument level, jurisdiction, relation type, duty type and provision kind lists at run start, and the run carries an out-of-scope count.

### f03-T46 — Add off-sector and standards evaluation rows

**From:** STANDARDS STD-20

**Depends on:** f03-T35

**Owned paths:** `backend/eval/classification.jsonl`, `agents/watch-sweeper/v1/evals/cases.jsonl`, `backend/eval/README.md`

**Done when:** `check_prototype_data --eval` passes. Every new row is authored text, never copied from a publisher, and every existing row reads as in-scope by default. At least four off-sector rows, one law-citing-a-standard row and three standards rows exist.

### f03-T47 — Score in-scope and standard-term accuracy in the evaluation gate

**From:** STANDARDS STD-21 (AGT-S12)

**Depends on:** f03-T46, chunk 5's classifier

**Owned paths:** `backend/scripts/search_eval.py`, `backend/eval/tolerance.json`, `backend/eval/tests_scoring.py`

**Done when:** `search_eval.py --self-test` is green, the mock classifier reports both metrics, each has a tolerance with a rationale, and the evaluation half of `test_agt_s12` is green.

## Chunk 6: Today and the roadmap

### f03-T48 — Today's decisions read the queue counts on `GET /me`

**From:** MY_WORK_AND_MARKETS placement table

**Depends on:** chunk 6's Today work

**Owned paths:** `backend/apps/identity/schemas.py`, `backend/apps/identity/me_logic.py`, `frontend/src/components/home/TodayScreen.tsx`

**Done when:** Today's "Decide now" reads the queue counts on `GET /me`, which gain applicability, and nothing on Today reads `/me/work`. HOM-S1 stays green, and the UI plan row agrees.

## Chunk 7: Ask

### f03-T49 — Make Ask give no answer about a standard's controls

**From:** STANDARDS STD-22 (SRC-S12)

**Depends on:** f03-T35, chunk 7's Ask

**Owned paths:** `backend/eval/retrieval.jsonl`, `backend/apps/search/tests_scenarios.py`

**Done when:** `test_src_s12` is green against the mock and against the recorded real model, and the evaluation row gates the release.

## Chunk 8: the register, My work, participants and the Statement of Applicability

Nothing here can be built earlier: before chunk 8 nothing can be owned, so the
page would be empty and a participant would have nothing to hang on.

### f03-T50 — Add the My work kinds and settings

**From:** MY_WORK_AND_MARKETS T-24

**Depends on:** chunk 8 start

**Owned paths:** `backend/apps/shared/kinds.py`, `backend/config/settings.py`

**Done when:** The kinds-only guard passes, and the work reason, bucket and date kinds each carry their reason. `MY_WORK_DUE_SOON_DAYS`, `MY_WORK_AWARE_DAYS` and `MAX_PARTICIPANTS_PER_RECORD` have typed defaults with env overrides.

### f03-T51 — Add departments with heads and team membership

**From:** MY_WORK_AND_MARKETS T-25 (TEN-S8)

**Depends on:** f03-T50, chunk 8's org units and team rows

**Owned paths:** `backend/apps/tenants/models.py`, `backend/apps/tenants/api.py`, `backend/apps/tenants/logic.py`, `backend/apps/identity/me_logic.py`, `backend/apps/identity/schemas.py`, `frontend/src/features/tenant-admin/`, `frontend/src/components/admin/`

**Done when:** `test_ten_s8` and its journey are green, and NFR-S1 holds for the new route. The database refuses a cross-tenant team membership, department or head, and no team lead flag is built.

### f03-T52 — Add the people picker

**From:** MY_WORK_AND_MARKETS T-26

**Depends on:** f03-T51

**Owned paths:** `backend/apps/tenants/api.py`, `backend/apps/shared/permissions.py`

**Done when:** The route is listed as ungated by design with a reason. An enrolment session gets 403. A test shows another tenant's people and deactivated members never appear, and only ids and names are returned.

### f03-T53 — Add the participant model

**From:** MY_WORK_AND_MARKETS T-27

**Depends on:** f03-T50, f03-T51, chunk 8's register entry

**Owned paths:** `backend/apps/collab/models.py`, `backend/apps/collab/migrations/`

**Done when:** The migration applies from zero and reverses. A model test proves the database refuses a cross-tenant user, team or register entry. The row-level-security guard lists the table.

### f03-T54 — Write the participant logic

**From:** MY_WORK_AND_MARKETS T-28

**Depends on:** f03-T53

**Owned paths:** `backend/apps/collab/logic.py`, `backend/apps/register/logic.py`

**Done when:** Unit tests on Postgres cover each refusal code and the register-entry creation event. Add, remove and leave each go through `record()`, load the subject under row-level security, check the member and their read permission, and enforce the cap.

### f03-T55 — Add the obligation participant routes

**From:** MY_WORK_AND_MARKETS T-29 (COL-S6, COL-S7, COL-S8)

**Depends on:** f03-T54

**Owned paths:** `backend/apps/collab/api.py`, `backend/apps/collab/schemas.py`, `backend/apps/shared/permissions.py`, `backend/apps/shared/routes.py`, `backend/apps/shared/factories.py`, `openapi.json`, `frontend/src/types/api.generated.ts`

**Done when:** `test_col_s6`, `test_col_s7` and `test_col_s8` are green. The tenant-isolation suite and NFR-S13 pass, and the delete route is listed as gated in logic with its reason.

### f03-T56 — Collect the register sources for My work

**From:** MY_WORK_AND_MARKETS T-30

**Depends on:** f03-T55, chunk 8's REG-02, REG-03, REG-05 and REG-07

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_my_work.py`

**Done when:** Unit tests on Postgres cover every source, the department expansion over the units below, and the exclusion of deactivated members.

### f03-T57 — Compute buckets, dates, permissions and counts for My work

**From:** MY_WORK_AND_MARKETS T-31 (HOM-S8, HOM-S10)

**Depends on:** f03-T56

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_scenarios.py`

**Done when:** `test_hom_s8` and `test_hom_s10` are green. Every count comes from the permission-filtered set, unreadable kinds are reported as permission-limited, and the regulatory scope is not applied.

### f03-T58 — Fill the 'changes on your items' bucket

**From:** MY_WORK_AND_MARKETS T-32 (HOM-S11)

**Depends on:** f03-T57

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_scenarios.py`

**Done when:** `test_hom_s11` is green: unconfirmed agent links and the caller's own acts are left out, and a version stays for the awareness window.

### f03-T59 — Serve the My work read

**From:** MY_WORK_AND_MARKETS T-33 (HOM-S7, HOM-S9, HOM-S12)

**Depends on:** f03-T58

**Owned paths:** `backend/apps/home/api.py`, `backend/apps/home/schemas.py`, `backend/apps/shared/permissions.py`, `openapi.json`, `frontend/src/types/api.generated.ts`

**Done when:** `test_hom_s7`, `test_hom_s9` and `test_hom_s12` are green, with a pinned query count that does not grow with the number of items and a response inside the 250 ms budget. The contract drift check passes against its INPUT_DELTAS §7 row.

### f03-T60 — Design My work, the participants panels and the organisation admin

**From:** MY_WORK_AND_MARKETS T-10  ·  **Can start now**

**Depends on:** nothing

**Owned paths:** `design/screens/tenant-my-work.html`, `design/screens/tenant-obligation.html`, `design/screens/tenant-change.html`, `design/screens/admin-organisation.html`, `design/screens/admin-members.html`

**Done when:** The cards render in both themes with no new pill slot or tone, and they are reviewed before chunk 8 starts.

### f03-T61 — Write the My work frontend library

**From:** MY_WORK_AND_MARKETS T-34

**Depends on:** f03-T59, f03-T60

**Owned paths:** `frontend/src/features/my-work/`

**Done when:** The unit tests cover every reason, date kind and bucket, in en and sv, including an overdue count and a days-ahead count.

### f03-T62 — Build the My work screen

**From:** MY_WORK_AND_MARKETS T-35

**Depends on:** f03-T61

**Owned paths:** `frontend/src/app/(tenant)/work/page.tsx`, `frontend/src/components/work/MyWorkScreen.tsx`, `frontend/src/shared/navigation/registry.ts`, `frontend/src/messages/nav/{en,sv}.json`, `frontend/src/messages/work/{en,sv}.json`

**Done when:** HOM-S7 and HOM-S9 are un-fixme'd and green. The registry test (at most four ranked destinations) passes, so the entry sits under More on phones. The screen matches `tenant-my-work.html` in both themes and has every state.

### f03-T63 — Add the participants panel to the obligation page

**From:** MY_WORK_AND_MARKETS T-36

**Depends on:** f03-T55, f03-T52, f03-T60

**Owned paths:** `frontend/src/features/collab/`, `frontend/src/features/register/`

**Done when:** COL-S6 and COL-S7 are un-fixme'd and green. Owners render read-only, the add control shows only with `register.edit`, and Leave shows on your own row.

### f03-T64 — End participations and team memberships on member removal

**From:** MY_WORK_AND_MARKETS T-37 (TEN-S9)

**Depends on:** f03-T54, f03-T51, chunk 8's TEN-05

**Owned paths:** `backend/apps/identity/members_logic.py`, `frontend/src/components/admin/MemberDetailScreen.tsx`

**Done when:** `test_ten_s9` is green: the preview counts participations and lists teams, nothing changes before confirmation, and on confirm everything ends in one transaction with one audit event per item. Team participations are untouched.

### f03-T65 — Run J-9, Monday morning, end to end

**From:** MY_WORK_AND_MARKETS T-38

**Depends on:** f03-T62, f03-T63

**Owned paths:** `backend/apps/shared/e2e_seed.py`, `frontend/tests/e2e/home.journey.spec.ts`

**Done when:** HOM-S13 is un-fixme'd and green against the real stack in the smoke run, with no mocked API. `seed_e2e` stays idempotent.

### f03-T66 — Add certificate columns to the licence row

**From:** STANDARDS STD-23 (TEN-S10)

**Depends on:** chunk 8's org units and licences, f03-T51 (the owner shape)

**Owned paths:** `backend/apps/tenants/models.py`, `backend/apps/tenants/migrations/`, `backend/apps/tenants/logic.py`, `backend/apps/tenants/api.py`, `backend/apps/tenants/schemas.py`, `backend/apps/tenants/tests_scenarios.py`, `frontend/src/features/tenants/`

**Done when:** `test_ten_s10` is green in both halves and the amended TEN-S2 is green. The row-level-security guard lists the licence table, the row carries no term and decides no span, and writes are audited with before and after values.

### f03-T67 — Decide applicability per entity for the conformance obligation

**From:** STANDARDS STD-24 (REG-S12)

**Depends on:** chunk 8's register entry, scope row and applicability request, f03-T25

**Owned paths:** `backend/apps/register/models.py`, `backend/apps/register/migrations/`, `backend/apps/register/logic.py`, `backend/apps/register/tests_scenarios.py`

**Done when:** `test_reg_s12` and the amended REG-S1 are green. A test proves that a read writes no scope row, the one-pending index treats nulls as not distinct, and an entity's span leaves opt-in dimensions out.

### f03-T68 — Add the unit table and its rules

**From:** STANDARDS STD-25

**Depends on:** f03-T67

**Owned paths:** `backend/apps/register/models.py`, `backend/apps/register/migrations/`, `backend/apps/register/logic.py`, `backend/apps/register/tests_scenarios.py`

**Done when:** The row-level-security guard lists the table. The 422 and 409 checks of REG-S13 are green. The register entry keeps its own uniqueness, and approving a unit request writes the unit's applicability.

### f03-T69 — Paste units with a dry run

**From:** STANDARDS STD-26 (REG-S13)

**Depends on:** f03-T68

**Owned paths:** `backend/apps/register/units.py`, `backend/apps/register/api.py`, `backend/apps/register/schemas.py`, `backend/apps/register/tests_scenarios.py`, `backend/config/settings.py`

**Done when:** `test_reg_s13` is green, including the refusal paths. The settings test lists `REGISTER_BULK_MAX`. The dry run refuses duplicates, over-long lines and unknown values, and a commit files one pending request per row that carries an applicability.

### f03-T70 — Decide many pending requests in one call

**From:** STANDARDS STD-27 (REG-S14)

**Depends on:** f03-T68

**Owned paths:** `backend/apps/register/api.py`, `backend/apps/register/logic.py`, `backend/apps/register/tests_scenarios.py`, `backend/apps/shared/tests_four_eyes.py`

**Done when:** `test_reg_s14` is green, including the four-eyes path with no partial decision. A call at the cap stays under `API_BUDGET_MS` with an asserted query count, and the applicability request table is in the four-eyes guard list.

### f03-T71 — Build the units list, the paste dialog and the bulk decision screen

**From:** STANDARDS STD-28

**Depends on:** f03-T69, f03-T70, chunk 8's register screens, f03-T60

**Owned paths:** `frontend/src/features/register/units/`, `frontend/src/messages/register/{en,sv}.json`, `frontend/tests/e2e/register.journey.spec.ts`

**Done when:** REG-S13 and REG-S14 are un-fixme'd and green, using invented units only. No string literal appears in JSX, and the form asks for the tenant's own words with no field for the standard's text.

### f03-T72 — Filter the register into a Statement of Applicability

**From:** STANDARDS STD-29 (REG-S15)

**Depends on:** f03-T70, f03-T71

**Owned paths:** `backend/apps/register/api.py`, `backend/apps/register/logic.py`, `frontend/src/features/register/`

**Done when:** `test_reg_s15` and its journey are green. HOM-S1's standing counts are unchanged by units, and no status is computed across them.

### f03-T73 — Prove nothing written under a standard reaches the index or a model

**From:** STANDARDS STD-30 (SRC-S13)

**Depends on:** f03-T68, chunk 7's indexer, embedder and generation log

**Owned paths:** `backend/apps/search/tests_scenarios.py`

**Done when:** `test_src_s13` is green, written per row, and it fails as soon as a field of any such row is added to an indexer, embedder or model input. It exists before the search scope decision is relaxed at R2.

### f03-T74 — Put certificate dates on the roadmap, never in the calendar feed

**From:** STANDARDS STD-31 (HOM-S15)

**Depends on:** f03-T66, chunk 6's roadmap view and feed, chunk 8's gap and duty branches

**Owned paths:** `backend/apps/home/migrations/`, `backend/apps/home/logic.py`, `backend/apps/home/tests_scenarios.py`

**Done when:** `test_hom_s15` is green and HOM-S4, HOM-S5 and HOM-S6 stay green. Both branches are left out once the row is withdrawn, and neither appears in the feed.

### f03-T75 — Run J-10 end to end

**From:** STANDARDS STD-32 (REG-S16)

**Depends on:** f03-T28, f03-T66, f03-T71, f03-T72, f03-T74

**Owned paths:** `frontend/tests/e2e/register.journey.spec.ts`, `backend/apps/shared/e2e_seed.py`

**Done when:** REG-S16 is un-fixme'd and green against the real stack with no mocked API. `seed_e2e` stays idempotent, and no real clause or control title appears in the repository.

## Chunk 9: the case workflow

### f03-T76 — Add case participants and turn contributor teams into team participants

**From:** MY_WORK_AND_MARKETS T-39 (COL-S9, CAS-S17, amended CAS-S4)

**Depends on:** f03-T55, chunk 9's CAS-02 and CAS-03

**Owned paths:** `backend/apps/collab/api.py`, `backend/apps/cases/logic.py`, `backend/apps/shared/routes.py`, `frontend/src/features/collab/`, `frontend/src/features/cases/`

**Done when:** `test_col_s9`, `test_cas_s17` and the amended `test_cas_s4` are green, and the COL-S9 journey and TEN-S7 are green. The assessment's contributor picker makes single add and remove calls and stores no list.

### f03-T77 — Add the case sources to My work

**From:** MY_WORK_AND_MARKETS T-40 (HOM-S14)

**Depends on:** f03-T76, chunk 9's actions

**Owned paths:** `backend/apps/home/my_work.py`, `backend/apps/home/tests_scenarios.py`

**Done when:** `test_hom_s14` is green and `test_hom_s12`'s pinned query count is unchanged.

## Chunk 10: collaboration

### f03-T78 — Send participant and linked-change notifications through one recipient check

**From:** MY_WORK_AND_MARKETS T-41 (COL-S10)

**Depends on:** f03-T77, chunk 10's COL-02

**Owned paths:** `backend/apps/collab/models.py`, `backend/apps/collab/logic.py`, `backend/apps/collab/tasks.py`, `backend/apps/shared/kinds.py`

**Done when:** `test_col_s10` is green and COL-S1 stays green. One resolver picks active members whose roles can read the subject at send time and sends one notification per person per event; titles and emails carry the library title and a link only.

### f03-T79 — Send review reminders

**From:** MY_WORK_AND_MARKETS T-42 (COL-S11)

**Depends on:** f03-T78

**Owned paths:** `backend/apps/collab/tasks.py`, `backend/apps/collab/tests_scenarios.py`

**Done when:** `test_col_s11` is green: each person responsible for a review date is reminded once at the tenant's lead time, in their language, and a second run the same day reminds nobody.

### f03-T80 — List my comments and mentions on My work

**From:** MY_WORK_AND_MARKETS T-43 (COL-S12)

**Depends on:** f03-T78, chunk 10's COL-01

**Owned paths:** `backend/apps/collab/api.py`, `backend/apps/home/my_work.py`, `frontend/src/components/work/MyWorkScreen.tsx`, `backend/scripts/compliance_check.py`

**Done when:** `test_col_s12` and its journey are green and `test_col_s5` stays green. The read is paginated and filtered by the subject's read permission, the panel carries its visibility line, and the compliance lint covers the new route.

### f03-T81 — Escalate to department heads and build the digest on My work

**From:** MY_WORK_AND_MARKETS T-44 (amended COL-S2)

**Depends on:** f03-T78

**Owned paths:** `backend/apps/collab/tasks.py`, `backend/apps/collab/tests_scenarios.py`

**Done when:** The amended `test_col_s2` is green, with no second definition of open items: the digest calls the My work service for the reader's own scope.

## Chunk 11: tenant-controlled agents

### f03-T82 — Set tenant agents' default scope from the markets

**From:** MY_WORK_AND_MARKETS T-23 (AGT-S11)

**Depends on:** f03-T19, chunk 11's AGT-04 and AGT-06

**Owned paths:** `backend/apps/agents/logic.py`, `backend/apps/agents/models.py`, `agents/watch-sweeper/v2/prompt.md`

**Done when:** `test_agt_s11` is green and AGT-S5 stays green. The scope is built at run start from the market levels unless the row names jurisdictions of its own, a copy is stored on the run, and a platform run reads no tenant row.

## Chunk 12: reports and exports

### f03-T83 — Export the Statement of Applicability

**From:** STANDARDS STD-33 (REP-S6)

**Depends on:** f03-T72, chunk 12's export jobs

**Owned paths:** `backend/apps/reports/`

**Done when:** `test_rep_s6` is green and REP-S3 stays green. The inventory export accepts the instrument and entity filters and produces the unit columns, runs as a job, needs step-up and writes one audit event.
