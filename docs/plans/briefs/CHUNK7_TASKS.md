# Chunk 7: tasks

Written 2026-09-19 by the planning session (read, plan, parallelism and coverage critiques,
revise). Each task runs in its own worktree (`docs/runbooks/WORKTREES.md`) or, where its lane
says `cloud`, in a cloud session under that runbook's "Cloud tasks". A task starts once
everything in its depends-on is merged, and for a cloud task once it is on `origin/main`.

The task ids are the `c7-` package ids of `docs/plans/PARALLEL_PLAN.md` section 3.3, plus
`f03-T49` from `docs/plans/briefs/FEATURES_0_3_TASKS.md`, which that plan places in chunk 7.
Where the revision below splits a package, the halves keep the original id as their stem
(`c7-search-index` becomes `c7-search-index-model` and `c7-search-index-apply`), so a row in
PARALLEL_PLAN 3.3 still finds its work. Lanes, minute estimates, serialization keys and the
global wave numbers otherwise stay as the plan has them; the waves below are chunk-local and
say which of them may run side by side.

## Revised 2026-09-20

The first version of this file was written before Alex answered the owner questions on
2026-09-19 and before E4 and the contract branch landed. `docs/reviews/2026-09-20-cloud-branch-reviews/plan-7.md`
blocked it. Every HIGH and MEDIUM finding there is closed below, and both LOWs that a small
change closes; the third LOW (task sizes) is closed by the splits it names. A second review of
the revision then found two MEDIUMs and four LOWs, which the last six rows close. What changed:

| Change | Closes |
|---|---|
| `c7-search-index` is rebuilt to Alex's accepted Option B (item 4) and split into `c7-search-index-model` and `c7-search-index-apply`: `SearchChunk` is a derived model outside `LibraryModel`, with its own `index_write()` fence, its own AST guard, and split RLS policies in the `agent_run` shape. The library-fence allowlist entry is gone from the owned paths, from rule 7, from the wave notes and from `c7-security-review`; embedding is filled from outbox events with no tenant active, never from a second relay. An ADR, a DECISIONS row and an INPUT_DELTAS line are named. `q-search-fence` is answered | HIGH 1, LOW 13 |
| `c7-eval-sets` no longer builds library rows: `eval_question` and `eval_run` become platform tables outside `LibraryModel`, written through `record()` under `eval.manage` and from a management command in `apps/shared/management/commands/`, which is already inside the fence's allowed seed directories. The unfenced `apps/search/seeds/` directory is gone. The library fence allowlist and `ProposalDoorGuard` are untouched. The task is split into `c7-eval-models-commands` and `c7-eval-routes` | HIGH 2, LOW 13 |
| `c7-eval-gate` no longer records a baseline on the mock. `is_mock` becomes "any adapter in the chain is a mock", the task proves the not-yet-recorded path and the self-test's synthetic baseline instead, and the real retrieval baseline is recorded once by `c7-embedder-selection-baseline` after `k-embedder`. SRC-S8's done-condition, `f03-T49`'s re-record clause and `c7-chunk-close` follow; the unrecorded track goes to `docs/TODO_FOR_alex.md` | HIGH 3, LOW 12 |
| `c7-embedder-mock-reranker` is marked done at `d10daf8` on `main`. It is out of wave 1 and out of the "in review" text, and stays only as a satisfied dependency | MEDIUM 4 |
| `c7-index-changes` indexes shared (platform) changes only. A change event carrying a tenant owner is skipped, with a test proving no chunk and no embedding request, and the handler runs with no tenant active. The H7 wording in the index tasks, the retrieval tasks and `c7-security-review` becomes "shared rows only in R1" | MEDIUM 5 |
| `c7-ask-switch` governs tenant-zone AI only (item 14): bleqq's platform agents ignore it, the logging wrapper reads it only when a tenant is active, a test proves a platform model call is unaffected, and the toggle copy names the tenant's own features. The `aiEnabled` write also takes `@requires_step_up`, with the step-up id on the audit row | MEDIUM 6, MEDIUM 9 |
| `SearchFilters` carries `jurisdiction` and `dutyType` (vocabulary keys) and drops `applicability` and `complianceStatus`, which are the register overlay's and belong to chunk 8. The keys travel in `search_chunk.metadata` and are filtered before ranking | MEDIUM 7 |
| AUD-S4's integration half leaves `c7-ai-log-backend`, which keeps only the filters, the feedback write and the mark-reviewed function chunk 5 calls. A new task, `c7-aud-s4-integration`, owns the scenario and waits for the three producers and the chunk 5 confirm route. The file collision is gone by itself: the contract puts `rateAnswer`'s stub in `apps/search/ask.py`, so no chunk 7 task creates `apps/governance/ai_log.py` | MEDIUM 8 |
| `c7-embedder-selection-baseline` scores only EU-hostable candidates (Bedrock in an EU region, or none) per item 7, and its done-condition is that the test environment boots with the real provider while production stays keyword-only until `c14-eu-data-location` admits it | MEDIUM 10 |
| `c7-eval-gate` no longer edits `.github/workflows/ci.yml` or `scripts/prepush.sh`, and drops the `ci` key: both already run `search_eval.py` (ci.yml line 256, prepush.sh line 185 under `--all`) | LOW 11 |
| The five packages the review named are split at their green points, and each screen is split from its journeys: `c7-hybrid-search-backend` into `c7-hybrid-search-core` and `c7-search-similar-limits`; `c7-ask-backend` into `c7-ask-grounding-stream` and `c7-ask-limits-switch-feedback`; `c7-search-screen` and `c7-ask-screen` each into a screen task and a journey task. `c7-security-review` and `c7-embedder-selection-baseline` stay whole: one is a single read of one diff and the other is a single recorded run, and neither has an interior green point | LOW 13 |
| The search API contract is adopted as the branch being corrected now lands it: Ask is a streamed `text/event-stream` whose event kinds are Pydantic models in `apps/search/schemas.py`; the `search` and `findSimilar` stubs live in `apps/search/hybrid.py` and the `ask` and `rateAnswer` stubs in `apps/search/ask.py`, with `api.py` holding routes only; the contract's own frontend feature files are removed, so the chunk 7 frontend tasks own `frontend/src/features/search/**` | the contract decisions the revision was told to adopt |
| `c7-eval-models-commands` no longer asks for an `OTHER_POLICIES` entry it cannot have: `tests_rls.py` enumerates only models with a foreign key to `shared.Tenant` and asserts `OTHER_POLICIES` over those tables alone, so the task instead adds a second constant, `PLATFORM_ONLY_TABLES`, and one new test of its own for `eval_question` and `eval_run`; rule 7 carves that edit out by name and the per-merge security review covers it | second review MEDIUM 1 |
| `c7-ask-switch` adds `aiEnabled` to `tenants/schemas.py`, so its gates gain `bash generate-types.sh` with the contract-drift check, as a check only with the generated files reverted and never committed, and the `npm run check:copy-drift` its own text already requires | second review MEDIUM 2 |
| `c7-search-index-model`, `c7-search-index-apply`, `c7-index-changes` and `c7-e2e-seed` change chunking or embeddings, so each one's gates gain `python backend/scripts/search_eval.py` (CLAUDE.md §7 item 9) | second review LOW 3 |
| Rule 7 names the guard edits chunk 7 is allowed to make, instead of banning every guard change while two tasks own `tests_rls.py` | second review LOW 4 |
| `docs/plans/UI_Implementation_Plan.md` joins rule 4's append-ledger list, because two screen tasks in different waves each edit their own rows in it | second review LOW 5 |
| `c7-ask-limits-switch-feedback` depends on `c7-ai-log-backend` directly, not only transitively, because `rate_answer` calls its `set_feedback` | second review LOW 6 |

Deviations from PARALLEL_PLAN 3.3 and 3.4 that the main agent carries back into that file:
the eight new package ids above; the new keys `hybrid` (`apps/search/hybrid.py`), `askmod`
(`apps/search/ask.py`), `indexmod` (`apps/search/indexing.py`) and `searchjourney`
(`frontend/tests/e2e/search.journey.spec.ts`); the `ci` key leaving `c7-eval-gate`; the
`fence` key leaving the chunk (no chunk 7 task touches the library fence any more); and the
two cross-chunk dependency renames, `c5-agent-api-flow` and PARALLEL_PLAN's rewrite row for
`c5-search-similar`, which both now point at `c7-search-similar-limits` rather than at
`c7-hybrid-search-backend`.

Not changed, and why: the review's question 4 (whether the regulatory scope applies to search
by default) is answered nowhere, so it stays a default taken and a line for Alex. Item 3's
library re-check by the watch agents is chunk 5's work and needs no chunk 7 task.

## Scope, rules and defaults

Chunk 7 is search and ask: the last R1 chunk before `r1-readiness` and Alex's first test deploy.
It has 26 tasks in 13 chunk-local waves. One further package, `c7-embedder-mock-reranker`, is
already merged on `main`, and one, `c7-embedder-selection-baseline`, waits for a key that may
never arrive in time. Nothing was edited while planning; this file and the review directory it
cites are the only commit.

HARD PRECONDITIONS: WHAT MUST BE ON MAIN BEFORE EACH WAVE

- Before wave 1: `x-frontend-split` (every chunk 7 screen owns a message namespace, and before
  the split each of them would hold the `cat` key and serialise the whole frontend half of the
  chunk), and `c4-console-tenants-api` (the tenant record the Ask switch extends).
- Before wave 2: `c4-approve-apply`, which leaves the no-op `reindex(obligation_id)` in
  `apps/search/logic.py` that `c7-search-index-apply` fills, and `c5-contract-models-watch`,
  whose `RegulatoryChange` is the third indexed source type and the pending-change flag Ask
  reads. `H-C` is not a precondition of chunk 7: the split RLS shape `c7-search-index-model`
  builds is `agent_run`'s, written in its own migration, and it touches no mixed library table.
- Before wave 3: `c5-ai-log-contract` (the `AiGeneration` model, `log_generation()` and the one
  wrapper every model call goes through) and `c5-llm-anthropic-provider` (E3, merged, which
  added `stream()` and the grounded `MockLlm`).
- Before wave 4: `c5-outbox-cursor` (the one ordered cursor over `outbox_event`), plus
  `c5-watch-registration` and `c5-watch-curation`, whose writes produce the change events
  `c7-index-changes` consumes, and `c5-seed-watch` for `c7-e2e-seed`.
- Before wave 5: `c3-fe-obligation-versions` (a hit opens the obligation card at a version).
- Before wave 7: `c4-console-shell` (the console the evaluation screen lives in).
- Before wave 9: `c4-fe-audit-log`, which creates `features/governance` and the admin log
  pattern the AI log screen follows; `f03-T35`, which puts the first standard in the demo
  fixture so `f03-T49` has something to ask about; and, for `c7-aud-s4-integration`,
  `c5-ai-log-and-so-what-draft`, `c5-cases-so-what-and-links` and `c5-watch-registration`.
- Before wave 11: every other chunk 7 task, `c7-review-fixes` included.

WHAT IT DELIVERS

- SRC-01, hybrid search:
  - One `search_chunk` row per legal unit per language, built from obligation versions,
    provision versions and registered changes, with the generated `tsvector` in that language's
    Postgres text search configuration and a 1024-dimension embedding under an HNSW index.
  - One SQL statement per query: the keyword leg and the vector leg fused by reciprocal rank,
    then reranked over the top 50, filtered by validity and by what the caller may see before
    ranking.
  - `POST /search` and `POST /search/similar`, the second the agents' route.
- SRC-02: filters from the vocabularies (jurisdiction, duty type, instrument, binding, language,
  terms), an "as of" date that picks the version in force, the regulatory scope applied with a
  visible way to look outside it, and a match kind on every hit.
- SRC-03, Ask:
  - `POST /ask`, streamed as `text/event-stream`, grounded only in retrieved library chunks,
    every statement carrying a citation, a pending change flagged as a warning, and `noAnswer`
    instead of a guess.
  - The tenant's Ask switch (`Tenant.ai_enabled`), the one switch over the tenant's own AI
    features. bleqq's platform agents are outside it (owner item 14).
  - The question is the only tenant-zone text that reaches a model (D-07).
- SRC-05: the retrieval half of the release gate wired and enforced by
  `backend/scripts/search_eval.py`, and the evaluation set managed in the console
  (`eval_question`, `eval_run`, `eval.manage`, ADM-02's evaluation surface). The retrieval
  baseline itself is recorded only against a real embedder.
- AUD-02: `GET /ai-generations` gains its filters and feedback, `POST /answers/{id}/feedback`
  stores helpful or wrong with a note, and `/admin/ai-log` shows what a model produced with its
  model, version, purpose, citations and review state.
- J-7: search by identifier, then by concept, then Ask with citations and an "as of" date,
  green as `@smoke` against the real stack.
- H7, in the shape owner item 4 accepts: the search index is derived data with its own write
  fence and its own row-level security, enabled and forced, with a `FOR ALL` policy confined to
  the session's own zone and a `FOR SELECT` policy that adds shared rows. `owner_tenant_id` is
  always NULL in R1 and only shared records are indexed, so no tenant-private library record
  can be reached through a chunk.

PLAN-WIDE RULES (they hold for every task below)

1. **Tests first.** The failing test comes first, then the code, then green. A task that cannot
   write its test first stops and reports.
2. **Contracts land first, and no screen calls a stub.** `c7-search-api-contract` writes
   `apps/search/api.py` and `apps/search/schemas.py` once and sends each operation to a named
   function in the module of the task that will build it: `apps/search/hybrid.py` for `search`
   and `findSimilar`, `apps/search/ask.py` for `ask` and `rateAnswer`. Those functions answer
   501 `not_built` behind their real permission gate until their task lands. A logic task owns
   only its own module and tests and never edits `api.py`; a logic task that finds the contract
   wrong stops and reports, and the contract task fixes it.
3. **Read-only POSTs go through a plain client in scenarios.** `search`, `findSimilar` and `ask`
   answer 200 and write no `audit_event`, because AUD-01 audits changes and nothing changed.
   The scenario client fails any 2xx mutating request without an audit row, so these calls use
   the plain `Client()` helper and assert the audit count is unchanged, exactly as the chunk 2
   dry-run previews already do (`apps/taxonomy/tests_scenarios.py::_preview`). **No guard is
   changed for this, and no allowlist is added**; `rateAnswer` is a real write and goes through
   `record()` like any other.
4. **Append ledgers.** Several chunk 7 tasks touch the same files and each adds, or in the
   pending file deletes, only its own lines: `apps/search/tests_scenarios.py` and
   `apps/governance/tests_scenarios.py` (own test methods and own skip lines), the app.md status
   cells, `backend/config/settings.py` (one labelled block per task), `backend/.env.example`,
   `docs/runbooks/RAILWAY_VARIABLES.md`,
   `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`,
   `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`,
   `docs/plans/UI_Implementation_Plan.md` (each screen task's own rows only),
   `apps/shared/e2e_seed.py`,
   `apps/shared/kinds.py`, `config/api.py` router mounts, `frontend/src/shared/navigation/registry.ts`,
   `frontend/src/features/shared/tone-by-kind.ts`, and each `*.journey.spec.ts` (own test blocks
   only). The later merge takes the union in its own worktree and reruns its gates.
5. **Generated files are never committed by a task**: `openapi.json`,
   `frontend/src/types/api.generated.ts`, `frontend/tests/e2e/support/e2e-passkeys.generated.ts`
   and the snapshot baselines. Each task runs `bash generate-types.sh` as a check and reverts it;
   the main agent regenerates them in the merge commit.
6. **E2E journeys run against the real stack.** CLAUDE.md section 11 is pasted in full into every
   task prompt that touches UI or journeys: a production Next build, the real backend on a freshly
   seeded throwaway database, sign-in by passkey through the virtual authenticator, `test`
   imported from `tests/e2e/support/api-guard`, expected errors declared where they happen, no
   injected token or cookie and no mocked API response. The mock LLM, embedder and reranker
   adapters that `E2E_MODE` boots are the stack's own adapters, not mocked API responses. A
   screen task and its journey task are consecutive waves, never far apart: a screen is not
   finished until its journeys are green.
7. **Guard changes.** **No chunk 7 task touches the library fence.** Owner item 4 keeps
   `LIBRARY_WRITE_ALLOWLIST` and `LIBRARY_WRITE_ALLOWED_DIRS` exactly as they are, and
   `ProposalDoorGuard` keeps naming only the proposal routes. What chunk 7 adds instead is a
   guard of its own, in `c7-search-index-model`: the `index_write()` runtime fence and an AST
   guard that allows a `SearchChunk` write only in `apps/search/indexing.py`. That one new
   guard is reviewed before its merge, and `c7-security-review` checks that the library fence
   is byte-for-byte unchanged. Two tasks also extend the row-level-security guard, and only
   there: `c7-search-index-model` adds `search_chunk` to the guarded tables and its
   `FOR SELECT` policy to `OTHER_POLICIES`, and `c7-eval-models-commands` adds the
   `PLATFORM_ONLY_TABLES` constant and the one test that asserts it, both in
   `backend/apps/shared/tests_rls.py`. Those two, with the new fence, are the only guard edits
   the chunk makes, and each is reviewed before its merge.
   `c7-embedder-mock-reranker` carried the production boot guard's
   reranker entry and is already merged and reviewed. No other task touches a guard, an
   allowlist, `UNGATED_BY_DESIGN`, the library fence, `authentication.py`, `tenancy.py` or
   `middleware.py`.
8. **Every threshold is a setting with an env override**, in one labelled block naming the task:
   the fusion constant, the rerank window, the retrieval depth, the score floor, the snippet
   length, the search and Ask rate limits, the embedding batch size and the Ask token cap.
9. **No tenant content leaves the tenant zone.** A query, a question, an answer and a chunk body
   never reach a log line, a Sentry event, an audit summary, an outbox payload or a URL. `POST`
   is used for search and Ask so no query string carries them (H10, already merged). The only
   tenant text that reaches a model is the Ask question (D-07).
10. **No scenario-stub task.** Chunk 7 needs none: SRC-S1 to SRC-S13 already sit skipped in
    `apps/search/tests_scenarios.py` and fixme'd in `frontend/tests/e2e/search.journey.spec.ts`,
    and AUD-S4 and ADM-S4 in the governance pair. Each task deletes only its own skip line.
11. **Simplicity.** A task builds what its requirement asks. Where the design offers more than a
    scenario needs, the extra is in "Cut, with reasons" and stays cut.

DEFAULTS TAKEN (each is written in the commit body of the task named)

- The regulatory scope applies to search, as it does to the inventory. FP-03 names the feed,
  inventory, roadmap, briefing and reports, not search, but `design/screens/tenant-search.html`
  draws an "Outside our scope" toggle that is off by default and an empty state offering
  "Search outside our scope", and showing hidden records by default would undo J-6. Search
  therefore reuses chunk 3's one scope rule in `library/reading.py`, and hits shown with the
  toggle on are marked as outside our scope (`c7-hybrid-search-core`, `c7-search-screen`). D-24
  exempts only My work, so this is still a default to confirm.
- Ask retrieves only chunks the scope admits, and says nothing about what is outside it
  (`c7-ask-grounding-stream`).
- An Ask answer writes an `ai_generation` row and no audit row (rule 3 above). The answer's log
  is AUD-02's row, readable under `ai_log.read` (`c7-ask-grounding-stream`).
- `POST /ask` answers `text/event-stream`. The event kinds are Pydantic models in
  `apps/search/schemas.py`, so the shapes are generated and not hand-written on either side: a
  `start` event carrying the answer id, one `statement` event per statement, then a terminal
  `answer` event whose body is the designed `Answer`. The budget is "first token under 2 s,
  streamed", so a single JSON response would miss it. `c7-search-api-contract` writes the
  INPUT_DELTAS row.
- `POST /search/similar` is the agents' route, gated on the `search:read` key scope alone. No
  permission in the PRD §6 matrix gives a person a similarity read, so the earlier plan's "or a
  platform session holding `proposals.review`" is dropped; a console surface that wants one
  comes with its own permission and its own review (`c7-search-api-contract`, INPUT_DELTAS §7,
  AGT-02). No tenant screen calls it in R1, as the UI plan already says.
- The answer id is generated before the stream starts, so the client can post feedback on it,
  and the `ai_generation` row is written when the model call completes, inside the request
  (`c7-ask-grounding-stream`).
- Embedding happens out of band, and through the one relay. `reindex()` writes the chunk rows
  and their `tsvector` inside the caller's transaction and emits an outbox event; the worker
  fills the embedding from that event through `c5-outbox-cursor`, with no tenant active. There
  is no `transaction.on_commit` hand-off and no second relay (PARALLEL_PLAN ruling 9). Approval
  stays inside the 250 ms budget, and a chunk not yet embedded is still found by the keyword leg
  (`c7-search-index-apply`).
- `search_chunk` is indexed per content language using that language's Postgres configuration
  (`swedish`, `danish`, `norwegian`, `finnish`, `english`), following INPUT_DELTAS §3, not
  `schema.sql`'s `sv`/`en` check (`c7-search-index-model`).
- The evaluation questions are seeded create-only from `backend/eval/retrieval.jsonl`, which
  stays the committed corpus the CI gate reads. A question added in the console is marked as not
  yet in the release gate until `manage.py dump_eval_questions` writes it into the jsonl and a
  person commits it (`c7-eval-models-commands`).
- The AI switch governs the tenant's own AI features only: Ask, the tenant's WAT-05 drafts, and
  from chunk 11 the tenant's own agents. bleqq's platform agents are part of the base package
  and no tenant can switch them off (owner item 14), so the logging wrapper reads the switch
  only when a tenant is active (`c7-ask-switch`, PARALLEL_PLAN ruling 13).
- The two screens whose design cards are still pending draw them in the task that builds them:
  `design/screens/admin-ai-log.html` in `c7-ai-log-screen` and
  `design/screens/console-evaluation.html` in `c7-fe-console-eval-sets`. The plan has no design
  package for chunk 7, and a card drawn away from its screen would be reviewed twice.

CUT, WITH REASONS

- `search_query_log`. No requirement and no scenario in chunk 7 needs it; SRC-05's corpus is the
  labelled set, not production queries. Building it would put raw tenant queries in a table for
  nobody to read. It returns with SRC-04's saved searches in chunk 13 if anything needs it.
- `POST /eval/runs` (`startEvalRun`). Running the harness from the console is a job, and there is
  no job runner with a status endpoint until `c14-job-runs`. `c7-eval-routes` moves its line in
  `contract_drift_pending.txt` from chunk 7 to chunk 14. Runs are recorded by
  `manage.py record_eval_run` after `search_eval.py --record`, which is how the gate earns them.
- Saved searches and "what changed since my last visit" (SRC-04, SRC-S7): R3, chunk 13.
- Tenant content in the index (D-10): R2. SRC-S11 proves it is absent, and SRC-S13, which proves
  it for what a tenant writes under a standard, belongs to `f03-T73` in chunk 8.
- Tenant-owned library records in the index (owner item 10): not in R1 and not in R2's first
  pass. `owner_tenant_id` exists on the chunk so the rule is enforceable, and it stays NULL
  until an ADR supersedes ADR 0010.
- `applicability` and `complianceStatus` search filters: the register overlay's, chunk 8.
- Highlighting inside the chunk body beyond the returned snippet, a "did you mean", query
  spelling correction, and search analytics: nothing asks for them.
- A second relay for embeddings and for change indexing. Both go through `c5-outbox-cursor`
  (PARALLEL_PLAN rulings 9 and 16); no watch writer and no `on_commit` hook is used.

WAVE LOGIC

- The backend chain that sets the pace: `c7-search-api-contract` and `c7-search-index-model`,
  then `c7-search-index-apply`, then `c7-hybrid-search-core`, then `c7-ask-grounding-stream`,
  then the screens and their journeys, then J-7, then the review, the fixes and the close.
- `apps/search/api.py` and `schemas.py` (`searchapi`) is held by `c7-search-api-contract` in
  wave 1 and by `c7-eval-routes` in wave 7. Nothing else may edit them.
- `apps/search/models.py` and migrations (`mig:search`) is held by `c7-search-index-model` in
  wave 2 and `c7-eval-models-commands` in wave 6.
- `apps/search/indexing.py` (`indexmod`) is written by `c7-search-index-apply` in wave 3 and
  extended by `c7-index-changes` in wave 4. They never run together.
- `apps/search/hybrid.py` (`hybrid`) is written by `c7-hybrid-search-core` in wave 4 and
  extended by `c7-search-similar-limits` in wave 5.
- `apps/search/ask.py` (`askmod`) is written by `c7-ask-grounding-stream` in wave 6 and extended
  by `c7-ask-limits-switch-feedback` in wave 7.
- The search screen and its namespace (`searchscreen`) is held by `c7-search-screen` in wave 5
  and `c7-ask-screen` in wave 8; Ask is a mode of the same screen, so they are never parallel.
- `frontend/tests/e2e/search.journey.spec.ts` (`searchjourney`) is held by `c7-search-journeys`
  in wave 6, `c7-ask-journeys` in wave 9 and `c7-j7-journey` in wave 10.
- `frontend/tests/e2e/governance.journey.spec.ts` is an append ledger with two owners in
  different waves: `c7-fe-console-eval-sets` (the ADM-S4 block, wave 8) and `c7-ai-log-screen`
  (the AUD-S4 block, wave 9).
- `apps/search/tests_scenarios.py` is an append ledger: `c7-search-index-model`,
  `c7-hybrid-search-core`, `c7-search-similar-limits`, `c7-ask-grounding-stream`,
  `c7-ask-limits-switch-feedback`, `c7-eval-gate` and `f03-T49` each add their own test methods
  and delete only their own skip lines.
- Security review: `c7-security-review` reads the whole chunk after wave 10, `c7-review-fixes`
  closes its findings, and the per-merge review still applies to every task marked SR in the
  plan (`c7-search-index-model`, `c7-search-index-apply`, `c7-hybrid-search-core`,
  `c7-search-similar-limits`, `c7-ask-grounding-stream`, `c7-ask-limits-switch-feedback`,
  `c7-ask-switch`, `c7-index-changes`, `c7-eval-models-commands`, `c7-eval-routes`,
  `c7-search-api-contract`).
- `q-search-fence` is answered, so nothing in the chunk is held on it any more.
- If `k-embedder` never arrives, `c7-embedder-selection-baseline` is cut, the retrieval track of
  the gate stays unrecorded, the test deploy searches by keyword with the mock vectors, and
  `c7-chunk-close` names all three.

CHANGES FROM THE CRITIQUES (2026-09-19) AND FROM THE REVIEW (2026-09-20)

- Parallelism: `c7-e2e-seed` keeps `c7-embedder-mock-reranker` as a dependency, now satisfied on
  `main`. It embeds the seeded corpus, and without the concept-aware mock the seeded J-7 concept
  query would not hit.
- Parallelism: `c7-hybrid-search-core` and `c7-search-similar-limits` are forbidden by their
  invariants to edit `api.py` or `schemas.py` (rule 2). Neither holds `searchapi`; the contract
  task keeps it.
- Parallelism: `c7-index-changes` adds one entry to the outbox cursor's dispatch table, and
  `c7-search-index-apply` adds one more for the embedding event. That table is an append point
  like the other shared registries; each entry is named in its task's owned paths, and
  `c10-collab-models` and `c13-int-contract`, the other packages that add one, are in later
  chunks.
- Parallelism: `apps/search/limits.py` is created by `c7-search-similar-limits` with both
  buckets, so one task owns the file and the Ask tasks only call it.
- Parallelism: `c7-ai-log-screen` extends `frontend/src/features/governance/**`, which
  `c4-fe-audit-log` owns. Chunk 4 has merged by wave 9, and no chunk 7 task in that wave touches
  it, so it stays a sequential edit rather than a new feature directory.
- Parallelism: the contract task no longer ships `frontend/src/features/search/**`. Those files
  are the chunk 7 frontend tasks' to write: `c7-search-screen` creates `api.ts`, `hooks.ts` and
  `search-presentation.ts`, and `c7-ask-screen` adds the Ask half.
- Parallelism: `c7-ask-switch` adds no journey of its own; it must not edit TEN-S1's test block
  to prove the toggle. Its lane may drop from local-e2e to local-unit if a slot is short.
- Coverage: SRC-S2 is owned by `c7-hybrid-search-core`, not by an index task. Its "then" ranks
  one language above another, which needs the query leg; the index task proves the per-language
  configuration in its own model tests instead.
- Coverage: SRC-S9 is owned by `c7-ask-limits-switch-feedback`, which is the first task with
  both budgets and both rate limits in place.
- Coverage: AUD-S4's integration half is owned by `c7-aud-s4-integration` and its journey half by
  `c7-ai-log-screen`. They are different tests in different files, and the integration half waits
  for the chunk 5 packages that produce the So what draft, its confirm route and the agent
  classification (review finding MEDIUM 8).
- Coverage: ADM-S4's list of console surfaces is amended once in chunk 7, by
  `c7-fe-console-eval-sets`, which adds evaluation sets to it.
- Coverage: SRC-S13 is not chunk 7's. It needs the units, gaps, assessments and interpretations
  of chunk 8 and is owned by `f03-T73`. `c7-chunk-close` records it as the one SRC scenario still
  skipped besides SRC-S7.
- Coverage: the four `POST` operations each have an owner for their pending line, so no line is
  left behind: `/search` with `c7-hybrid-search-core`, `/search/similar` with
  `c7-search-similar-limits`, `/ask` with `c7-ask-grounding-stream`, `/answers/{}/feedback` with
  `c7-ask-limits-switch-feedback`, the eval lines with `c7-eval-routes`. `GET /ai-generations`
  is checked by `c7-ai-log-backend` and deleted there if `c5-ai-log-contract` has not already
  deleted it.
- Coverage: `c7-eval-gate` teaches the scorer, and `validate_retrieval`, that a row with no
  expected keys is a question the retriever must answer with nothing. `validate_retrieval`
  refuses an empty `expected` today (`search_eval.py` line 138), so both the validator and the
  scorer change, in the one task that owns `search_eval.py`.
- Coverage, found while checking the critiques: the audit-on-write guard would have failed every
  read-only POST scenario. The chunk 2 dry-run precedent removes the problem without touching the
  guard, and it is rule 3 above instead of an open question about loosening an audit guard.

## Waves

Tasks in one wave have disjoint owned paths and can run side by side.

1. `c7-search-api-contract` (in flight; see its task), `c7-ask-switch`
2. `c7-search-index-model`
3. `c7-search-index-apply`, `c7-ai-log-backend`
4. `c7-hybrid-search-core`, `c7-e2e-seed`, `c7-index-changes`
5. `c7-search-similar-limits`, `c7-eval-gate`, `c7-search-screen`
6. `c7-ask-grounding-stream`, `c7-eval-models-commands`, `c7-search-journeys`
7. `c7-ask-limits-switch-feedback`, `c7-eval-routes`
8. `c7-ask-screen`, `c7-fe-console-eval-sets`
9. `c7-ask-journeys`, `c7-ai-log-screen`, `c7-aud-s4-integration`, `f03-T49`
10. `c7-j7-journey`
11. `c7-security-review`
12. `c7-review-fixes`
13. `c7-chunk-close`

Already on `main`, not dispatched: `c7-embedder-mock-reranker` (E4, `d10daf8`).
`c7-embedder-selection-baseline` runs whenever `k-embedder` arrives, any time after wave 9 (it
needs `f03-T49`'s no-answer row in the corpus before it records), and merges before wave 13 or
is cut.

## Open questions

- **q-search-fence: answered.** `docs/plans/briefs/OWNER_RECOMMENDATIONS.md` item 4, Alex "OK",
  accepts Option B: the index is derived data with its own write fence and its own row-level
  security, and the library fence's allowlist stays exactly as it is. `c7-search-index-model`
  and `c7-search-index-apply` build it, and the ADR, the DECISIONS row and the INPUT_DELTAS line
  land with them. Nothing in the chunk is held on this any more.
- Carried, not chunk 7's to answer: `k-embedder` (`docs/TODO_FOR_alex.md`, D-09: an API key for
  the first embedding model to try, approval that typed search queries may reach that endpoint,
  and a CI secret or committed vectors). Owner item 7 now narrows the candidates: production
  accepts only `bedrock` in an EU region, or `none`, for the embedder and the reranker, so a
  US-hosted candidate can be a test-environment choice at most. Without the key,
  `c7-embedder-selection-baseline` is cut, the retrieval track of the release gate stays
  unrecorded, and the test deploy searches with the mock vectors, so the concept leg is only as
  good as the mock.
- Carried: `k-anthropic`. D-07 already fixes the test environment to `anthropic`, and owner item
  7 exempts `ENVIRONMENT=test` with a visible banner, so the provider choice needs no further
  answer. What is still unrecorded is the cost of a run and Alex's approval that tenant-typed Ask
  questions may reach that endpoint on the test deploy. Ask works on the mock without it; the
  test deploy answers nothing real until it lands.
- To confirm, nothing waits: that search applies the regulatory scope by default, as the design
  card draws it, even though FP-03's list does not name search and D-24 exempts only My work.

## Tasks

### c7-embedder-mock-reranker: done, merged on main

**Requirements:** SRC-01, AC-SRC1
**Scenarios:** none of its own; it makes SRC-S1's concept leg possible
**State:** **done.** Merged into `main` at `d10daf8` ("A Danish question finds the Swedish
obligation that answers it, before a model is contracted"), built from
`docs/plans/briefs/EARLY_R1_PACKAGES.md` E4 and reviewed with its merge.

Do not dispatch it and do not review the cloud branch again. What is on `main`:

- `MockEmbedder`, deterministic, built from hashed stems plus a small concept table kept as
  test data, so that "nudging in onboarding" reaches `obl-esma-warnings` by the vector leg alone
  across all five content languages; unknown text keeps a hash vector.
- The reranker adapter (interface, mock, none) with `RERANKER_PROVIDER` and `RERANKER_TOP_K`.
- `MOCK_ADAPTER_SETTINGS` and the production boot guard's reranker entry, with its guard test.

It stays in this file only as a satisfied dependency of `c7-hybrid-search-core`, `c7-e2e-seed`
and `c7-embedder-selection-baseline`.

### c7-search-api-contract: the search and ask contract

**Requirements:** SRC-01, SRC-02, SRC-03, AUD-02
**Scenarios:** none built; the four operation ids are named in the skipped SRC scenarios so the audit-on-write guard's enumeration passes
**Depends on:** nothing
**State:** in flight on `origin/claude/c7-search-api-contract-uzma46`, being corrected to the
decisions below before it merges. Do not dispatch a second contract task; the corrections are
that branch's work.

Write `apps/search/api.py` and `apps/search/schemas.py` once, mount the router in
`config/api.py`, and send each operation to a named function that answers 501 `not_built`:

- `search` → `apps.search.hybrid.run_search` (`SessionAuth` with `search.use`).
- `findSimilar` → `apps.search.hybrid.find_similar` (an API key with the `search:read` scope,
  and nothing else: no permission in the PRD §6 matrix gives a person a similarity read).
- `ask` → `apps.search.ask.answer_question` (`SessionAuth` with `search.use`, a person's session
  only, no API key).
- `rateAnswer` → `apps.search.ask.rate_answer` (`SessionAuth` with `search.use`). It calls into
  `apps/governance/ai_log.py`, which `c5-ai-log-contract` creates; this task creates no file in
  the governance app, so nothing here collides with chunk 5.

Schemas, camelCase through `CamelSchema`, in the designed shapes: `SearchRequest`,
`SearchResponse`, `SearchHit` (with `matchKind` keyword | concept | both), `SimilarRequest`,
`SearchFilters`, `AskRequest`, `Answer`, `AnswerStatement`, `AnswerCitation`,
`AnswerFeedbackBody`, and the Ask stream's event models.

`SearchFilters` carries the R1 fields only: `instrumentId`, `termIds`, `binding`, `inFootprint`,
`jurisdiction` and `dutyType`.

- `jurisdiction` and `dutyType` are **keys**, not ids: `Jurisdiction` is a `Vocabulary` in
  `library/models.py` and `DutyType` a `Vocabulary` in `taxonomy/models.py`, so neither fits
  `termIds`, and `ObligationQuery` in `library/schemas.py` already filters both as bare key
  strings. The review named these fields `jurisdictionId` and `dutyTypeId`; the plan keeps the
  existing convention instead, because an `Id` suffix on a `UUID`-typed field elsewhere in the
  API would mislead. SRC-S3 filters by jurisdiction "SE" and duty type "reporting", and the
  search screen draws both filters, so without them `c7-hybrid-search-core` would find the
  contract wrong and stop (rule 2).
- `applicability` and `complianceStatus` are **not** in the R1 contract. They are the register
  overlay's filters and land with the register in chunk 8, with their own scenarios; naming them
  now would promise a filter no R1 task can serve.

Ask streams. Declare `ask` as `text/event-stream`: a `start` event carrying the answer id, one
`statement` event per statement, then a terminal `answer` event whose body is the designed
`Answer`. Each event kind is a Pydantic model in `schemas.py`, so both sides generate their
shapes rather than hand-writing them. Write the INPUT_DELTAS row (§4, errors and concurrency)
naming `POST /ask`, saying the response is a stream of the designed shape and why (the
first-token budget), and the row for the two added `SearchFilters` fields and the two removed
ones.

Also:
- Add the four operation ids to the docstrings of the skipped SRC scenarios in
  `apps/search/tests_scenarios.py`, so rule 1 of the audit-on-write guard is satisfied while the
  routes are stubs.
- Leave the four lines in `contract_drift_pending.txt`; the tasks that serve each route delete
  their own.
- No screen calls a stub, and this task ships **no frontend files**. `frontend/src/features/search/**`
  belongs to `c7-search-screen` and `c7-ask-screen`; a data layer written against a 501 stub
  would be reviewed twice and would take the `searchscreen` key out of their hands.

**Owned paths:**

- `backend/apps/search/api.py`
- `backend/apps/search/schemas.py`
- `backend/apps/search/hybrid.py` (the two `not_built` functions only)
- `backend/apps/search/ask.py` (the two `not_built` functions only)
- `backend/apps/search/tests_contract.py` (new)
- `backend/apps/search/tests_scenarios.py` (the operation ids in the skipped docstrings)
- `backend/apps/shared/kinds.py` (the hit-type, match-kind and feedback kinds)
- `backend/config/api.py` (the router mount)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`
- `docs/inputs/INPUT_DELTAS.md` (its rows)

**Done when:**

- Every one of the four operations is registered, answers 501 `not_built` in the problem shape,
  and refuses the wrong principal before it gets there: a key without `search:read` is 403, an
  API key on `ask` is 401 or 403, a session without `search.use` is 403 with `requiredPermission`
  named.
- `SearchFilters` carries `jurisdiction` and `dutyType` as keys and carries no `applicability`
  and no `complianceStatus`.
- `bash generate-types.sh` produces the four operations with the designed request and response
  shapes, the Ask stream's event models included, and the run is reverted, not committed.
- The route-permission guard and the audit-on-write guard are green.
- The diff stays inside the owned paths, and no file under `frontend/` is touched.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit openapi.json or api.generated.ts`
- `bash scripts/prepush.sh --quick`

**Invariants:**

No logic in `api.py`. No `Dict[str, Any]` and no `*args`/`**kwargs`. Every route carries its auth
class and its permission or scope decorator. A stub answers 501 behind the gate, never before it.
The problem shape is RFC 9457 with a `code`; no trace is exposed. Filters carry keys, never
labels. No string literal reaches the frontend from here.

### c7-ask-switch: the tenant's AI switch over its own AI features

**Requirements:** SRC-03, TEN-01
**Scenarios:** none of its own; SRC-S6's second half, owned by `c7-ask-limits-switch-feedback`, proves it
**Depends on:** `c4-console-tenants-api`, `x-frontend-split`

One column, `Tenant.ai_enabled` (default true), in `apps/shared/models.py` with its migration.

**What the switch governs, and what it does not.** It is the one switch over the **tenant's own**
AI features: Ask, the tenant's WAT-05 drafts, and from chunk 11 the tenant's own agents. It does
**not** reach bleqq's platform agents. Owner item 14 makes the general watch agents part of the
base package: no tenant can switch them off, pause them or change them, and AGT-04's tenant
controls apply only to a tenant's own agents. So:

- The check lives inside the one logging wrapper every model call goes through, and the wrapper
  reads the switch **only when a tenant is active**. A platform (library) run has no tenant
  active, so it never consults it.
- A test proves it both ways: with tenant A's switch off, an Ask call for tenant A is refused
  and a platform model call in the same test run still goes through untouched.
- Chunk 11's tenant settings row holds only the monthly cap, and `c11-ai-off-switch` adds only
  the tenant's own agents to the same check (ruling 13).

**The write is a security change, so it steps up.** Switching Ask on decides whether
tenant-typed text leaves the tenant to a model (D-07), which playbook 4.2 and CLAUDE.md §5 both
put behind a passkey step-up:

- Expose it on the organisation profile read and write in the tenants app (`aiEnabled`), gated by
  `security.manage` **and `@requires_step_up`**, audited through `record()` with before, after
  and the step-up assertion id on the row.
- A write without a fresh step-up answers the step-up problem shape, proved by a test.
- Add the toggle to `/admin/organisation` with its own copy in the organisation namespace and
  the step-up prompt the other security writes use. The copy says plainly that turning it off
  stops Ask and the drafts a model writes **for this organisation**, and says nothing about
  bleqq's own watch agents, which it does not touch.
- A component test covers on, off, saving, the step-up prompt and the denied state. No journey
  changes: TEN-S1's test block belongs to another task.

**Owned paths:**

- `backend/apps/shared/models.py` (the one column)
- `backend/apps/shared/migrations/` (one migration)
- `backend/apps/tenants/api.py`, `logic.py`, `schemas.py`
- `backend/apps/tenants/tests_organisation.py`
- `backend/apps/governance/tests_ai_switch.py` (new: the wrapper reads the switch only with a
  tenant active)
- `frontend/src/components/admin/OrganisationScreen.tsx`
- `frontend/src/features/tenant-admin/**`
- the organisation message namespace (en and sv)

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the graph.
- Reading and writing `aiEnabled` works, needs a step-up, is audited with before, after and the
  step-up id, and a member without `security.manage` is refused with `requiredPermission` named.
- A platform model call is unaffected by any tenant's switch, proved by a test.
- The toggle renders in both themes with its empty, loading, error, step-up and denied states,
  and `check:messages` and `check:copy-drift` are green.
- No requirement ID and no invariant text appears on screen.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.tenants apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit openapi.json or api.generated.ts`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

One switch, not two, and it reaches the tenant's own AI only. The column is a plain boolean on
the tenant, not a vocabulary. The write is audited in the same transaction and carries its
step-up. Permissions, never role names. No string literal in JSX.

### c7-search-index-model: the derived index, its fence and its row-level security

**Requirements:** SRC-01, SRC-02, INV-08 (nothing of a standard beyond its own records), H7
**Scenarios:** SRC-S11 (un-skipped)
**Depends on:** `c4-approve-apply`, `c5-contract-models-watch`

Build `SearchChunk` in `apps/search/models.py` from `schema.sql` §6, in the shape owner item 4
accepts: **derived data outside `LibraryModel`, with its own write fence and its own row-level
security. The library fence's allowlist is not touched.**

- Columns: source type (`provision_version`, `obligation_version`, `change`), source id, language,
  title, body, hierarchy path, `valid_from`, `valid_to`, a named-schema `metadata` JSON
  (instrument id, obligation id, regime, binding, term ids, **jurisdiction key, duty-type key**),
  the generated `tsv`, `embedding` `vector(1024)`, embedding model, embedding version, embedded
  at. Unique on (source type, source id, language).
- Indexes: GIN on `tsv`, HNSW on `embedding` with cosine ops, and one on the validity dates.
- `owner_tenant_id`, a nullable foreign key to `shared.Tenant`, copied from the record indexed
  and **always NULL in R1**: only shared records are indexed until an ADR supersedes ADR 0010
  (owner items 4 and 10). The column exists so the rule is enforceable in the database, not
  because anything fills it yet.
- **Row-level security, enabled and forced, in the `agent_run` shape, not `rls_operations(mixed=True)`.**
  The mixed helper's single `FOR ALL` policy checks writes with the read rule, which would let a
  bank session write, move and delete shared chunks (H15). Instead: one `FOR ALL` policy whose
  `USING` and `WITH CHECK` are `owner_tenant_id IS NOT DISTINCT FROM <tenant setting>`, so a
  session writes only inside its own zone and the indexer, running with no tenant active, writes
  the shared zone; plus one permissive `FOR SELECT` policy adding `owner_tenant_id IS NULL`, so
  every tenant reads shared chunks. Add the `FOR SELECT` policy to `OTHER_POLICIES` in
  `tests_rls.py` with its reason, and add `search_chunk` to the guarded-table list.
- A `cw_app` test proves all four: tenant A cannot insert, cannot update, cannot delete a shared
  chunk, and cannot read tenant B's chunk.
- **The fence.** `index_write()` in `apps/search/indexing.py` covers save, delete and queryset
  writes on `SearchChunk`, and an AST guard in `apps/search/tests_index_fence.py` allows
  `index_write(` and any `SearchChunk` write **only** in `apps/search/indexing.py`. The guard is
  proven to fail by planting a write in another module and reverting it, the way the library
  fence's own docstring records its proof. `indexing.py` names no library model: library rows
  are read in `apps/search/sources.py` (`c7-search-index-apply`), which makes no write call, so
  the library fence keeps passing unchanged and keeps watching both modules.
- Per language, not per `sv`/`en`: the generated `tsvector` uses the content language's Postgres
  configuration (`swedish`, `danish`, `norwegian`, `finnish`, `english`), per INPUT_DELTAS §3. A
  model test proves each configuration is the one used.
- Nothing a tenant writes is indexed (D-10), and under a standard-level instrument only the
  standard's own public records exist to index (D-35). SRC-S11 proves a tenant assessment note's
  distinctive phrase is in no chunk and asked for no embedding.
- Write the ADR (the index is derived data with its own fence and its own RLS; the alternatives
  and why they were rejected), the DECISIONS row, and the INPUT_DELTAS line recording the
  departure from `schema.sql`, which labels `search_chunk` LIBRARY.

**Owned paths:**

- `backend/apps/search/models.py`
- `backend/apps/search/migrations/0001_search_chunk.py`
- `backend/apps/search/indexing.py` (the model, the `index_write()` fence and nothing else yet)
- `backend/apps/search/tests_index_model.py`
- `backend/apps/search/tests_index_fence.py`
- `backend/apps/search/tests_scenarios.py` (SRC-S11 only)
- `backend/apps/shared/tests_rls.py` (`search_chunk` in the guarded tables, the one
  `OTHER_POLICIES` entry)
- `docs/adr/` (one new ADR), `docs/DECISIONS.md` (one row), `docs/inputs/INPUT_DELTAS.md` (one line)

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph, HNSW index
  included, on Postgres with pgvector.
- The RLS guard lists `search_chunk` as enabled and forced, `OTHER_POLICIES` names the
  `FOR SELECT` policy with its reason, and the four `cw_app` isolation tests pass.
- The AST guard fails any module other than `indexing.py` that writes a chunk, proved and
  reverted.
- **`backend/apps/shared/tests_library_fence.py` is unchanged**, byte for byte, and
  `git diff` proves it.
- SRC-S11 is un-skipped and green.
- The ADR, the DECISIONS row and the INPUT_DELTAS line are written.
- The diff stays inside the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.search apps.library apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`

**Invariants:**

The index is derived; it is never a second source of truth for a library fact, and it is never a
`LibraryModel`. The library fence's allowlist and `ProposalDoorGuard` are untouched. Only one
module writes a chunk. Row-level security is forced, not merely enabled, and writes are confined
to the session's own zone while reads add the shared zone. `owner_tenant_id` stays NULL in R1.
`JSONField` carries the schema-naming suppression comment. Tenant content is never indexed.

### c7-search-index-apply: the approval hook, the library reads and the rebuild

**Requirements:** SRC-01, SRC-02
**Scenarios:** none of its own; SRC-S11 stays green
**Depends on:** `c7-search-index-model`, `c4-approve-apply`, `c5-outbox-cursor`

Fill the index from the library, through the door that already exists.

- `apps/search/sources.py` (new): every read of a library row the index needs — obligation
  versions, provision versions, registered changes — with their validity dates, their instrument,
  their regime and binding, their term ids, and the **jurisdiction and duty-type keys** the
  filters compare. It makes no write call of any kind, so the library fence keeps passing and
  keeps watching it.
- `apps/search/indexing.py` grows `reindex(obligation_id)`, which replaces the no-op chunk 4 left
  in `apps/search/logic.py`: inside the caller's transaction it rebuilds that obligation's chunk
  rows and their `tsvector`, copying the validity dates so "as of" filters without a join. Only
  shared records are indexed; a record with an owner is skipped.
- `reindex_provision(provision_id)` and `reindex_all()` behind
  `manage.py reindex_library`, for the seed and a full rebuild. A rebuild writes **one** system
  audit row with counts only; there is no audit row per chunk, because the library writes behind
  them are already audited.
- Inside the approval transaction, `apply.py` calls `reindex()`. Approval stays inside the 250 ms
  budget because no embedding happens there.
- **Embedding goes through the one relay.** `reindex()` emits an outbox event; the worker fills
  the embeddings from that event through `c5-outbox-cursor`'s dispatch table, **with no tenant
  active**, batching by `SEARCH_EMBED_BATCH_SIZE`. There is no `transaction.on_commit` hand-off
  and no second Celery relay of our own (PARALLEL_PLAN ruling 9 and this plan's Cut list). A
  chunk with no embedding is still found by the keyword leg.

**Owned paths:**

- `backend/apps/search/sources.py`
- `backend/apps/search/indexing.py` (the reindex functions; the fence itself stays as built)
- `backend/apps/search/logic.py` (the `reindex` body only)
- `backend/apps/search/tasks.py` (the embedding handler only)
- `backend/apps/search/management/commands/reindex_library.py`
- `backend/apps/search/tests_indexing.py`
- the outbox cursor's dispatch table (one entry, for the embedding event)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- Approving an obligation-version proposal rewrites that obligation's chunks in the same
  transaction, and the approval stays inside the 250 ms budget.
- The embedding lands from the outbox event, with no tenant active, proved by a test that asserts
  the tenant setting is empty inside the handler.
- A library record carrying an owner is skipped, with no chunk and no embedding request, proved
  by a test.
- `reindex_library` rebuilds the whole corpus and writes exactly one audit row with counts.
- Re-running it changes nothing beyond the counts.
- `sources.py` contains no write call, and the library fence suite is green and unchanged.
- The diff stays inside the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.library apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`

**Invariants:**

Library rows are read in `sources.py` and written nowhere. Only `indexing.py` writes a chunk, and
only through `index_write()`. No embedding call happens inside a write transaction. The worker
embeds with no tenant active. Shared records only, in R1. Tenant content is never indexed.

### c7-ai-log-backend: AI log filters, answer feedback and mark-reviewed

**Requirements:** AUD-02
**Scenarios:** none of its own; AUD-S4's integration half is `c7-aud-s4-integration`'s, because it needs producers chunk 5 builds later (review finding MEDIUM 8)
**Depends on:** `c5-ai-log-contract`, `c7-search-api-contract`

Extend the governance app, which already has the `AiGeneration` model, `log_generation()` and the
plain read from `c5-ai-log-contract`. This task owns the three functions and nothing else:

- `GET /ai-generations` gains the designed filters (`purpose`, `status`, `subjectId`) with the
  shared pagination, under `ai_log.read`, showing the tenant's own rows only.
- The response gains `feedback` and `feedbackNote`, because AUD-02 names feedback as part of the
  log. Write the INPUT_DELTAS row for the added fields.
- `apps/governance/ai_log.py::set_feedback(generation_id, feedback, note)` is what
  `apps/search/ask.py::rate_answer` calls: `helpful` or `wrong` with an optional note, on a row of
  the caller's own tenant, idempotent for the same value, through `record()` in the same
  transaction, with no answer text in the audit summary.
- `apps/governance/ai_log.py::mark_reviewed(generation_id, user)` sets `reviewed_by` and
  `reviewed_at`; a model output stays labelled until then. Chunk 5's So-what confirm route calls
  it, so it exists before that route needs it.
- Delete the `GET /ai-generations` line from `contract_drift_pending.txt` if `c5-ai-log-contract`
  has not already deleted it. The `POST /answers/{}/feedback` line belongs to
  `c7-ask-limits-switch-feedback`, which serves the route.

**Owned paths:**

- `backend/apps/governance/ai_log.py`
- `backend/apps/governance/api.py`, `logic.py`, `schemas.py`
- `backend/apps/governance/tests_ai_log.py`
- `backend/scripts/contract_drift_pending.txt` (at most one line)
- `docs/inputs/INPUT_DELTAS.md` (one row)

**Done when:**

- The filters work, pagination defaults to 20 and caps at 100, and a holder of `ai_log.read`
  lists the rows for their tenant only.
- `set_feedback` stores helpful or wrong with its note, is idempotent for the same value, and
  leaves an audit row in the same transaction that carries no answer text and no question text.
- Feedback on another tenant's row answers 404, and a member without `ai_log.read` is refused
  with `requiredPermission` named.
- `mark_reviewed` sets the reviewer and the time, and a row stays labelled until it runs.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit openapi.json or api.generated.ts`

**Invariants:**

`ai_generation` is a mixed table: library rows to everyone, tenant rows to their tenant, under
forced row-level security. AI output stays labelled until a person confirms it. The feedback
write goes through `record()`. No tenant content reaches the audit summary, the outbox payload or
a log line. Statuses are the designed kinds, never phrases.

### c7-hybrid-search-core: one fused query, filters, "as of" and the match kind

**Requirements:** SRC-01, SRC-02, AC-SRC1, FP-03 (the scope rule reused)
**Scenarios:** SRC-S1 (integration half), SRC-S2, SRC-S3 (integration half)
**Depends on:** `c7-search-index-apply`, `c7-search-api-contract`, `c7-embedder-mock-reranker` (done)

Build `apps/search/hybrid.py::run_search`:

- One SQL statement per query over `search_chunk`: the keyword leg (`tsv @@ websearch_to_tsquery`
  in the query's language) and the vector leg (cosine distance to the embedded query), fused by
  reciprocal rank with `SEARCH_RRF_K`, then reranked over the top `SEARCH_RERANK_WINDOW` (50)
  through the reranker adapter that is already on `main`.
- Filters are applied before ranking, never after: validity against `asOf` (default today),
  language, `types`, `instrumentId`, `termIds`, `binding`, **`jurisdiction` and `dutyType`**
  (compared as keys against the keys the indexer put in `metadata`), and the regulatory scope
  through chunk 3's one rule in `library/reading.py`. `inFootprint: false` widens the search and
  marks each hit that is outside the scope.
- `matchKind` on every hit: keyword, concept or both, from which leg found it.
- The snippet is built from the chunk body around the best match, capped by `SEARCH_SNIPPET_CHARS`.
- Only shared chunks exist in R1, and the query says so: the read is confined to
  `owner_tenant_id IS NULL` in code as well as by the policy, so a later owned row cannot leak
  through a query written before it existed.
- Delete the `POST /search` line from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/search/hybrid.py` (`run_search` and its helpers; `find_similar` stays a stub)
- `backend/apps/search/tests_hybrid.py`
- `backend/apps/search/tests_scenarios.py` (SRC-S1, SRC-S2 and SRC-S3 only)
- `backend/scripts/contract_drift_pending.txt` (one line)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- SRC-S1's integration half is green: "FFFS 2017:2" is won by keyword and "nudging in onboarding"
  by concept, in one query, with the reranker applied over the top 50.
- SRC-S2 is green: the sv chunk ranks above the fi chunk for the same Swedish term, each using
  its own configuration.
- SRC-S3's integration half is green: filtering by jurisdiction "SE" and duty type "reporting"
  with an "as of" date returns only chunks valid on that date and carrying those keys, each hit
  shows its match kind, and a renamed label changes nothing because filters are keys.
- One statement per query, proved by counting queries around the call.
- Search stays inside 800 ms on the seeded corpus, with `Server-Timing` measured.
- The pending line is gone and `contract_drift.py` is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.library apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`
- `(cd backend && ./run.sh run python scripts/contract_drift.py)`

**Invariants:**

This task never edits `api.py` or `schemas.py`; a wrong contract stops it and is reported. The
scope rule is reused, never re-implemented. Filters compare keys, never labels. A read-only POST
writes nothing, and its scenario proves the audit count is unchanged. The query text never
reaches a log line, an audit row or a URL. No raw SQL string is built from user input. Shared
rows only, in R1.

### c7-search-similar-limits: the agents' nearest-neighbour read, the rate limits and the budget

**Requirements:** SRC-01, AC-SRC1, NFR-02
**Scenarios:** none of its own; SRC-S9's search half is proved here and asserted by `c7-ask-limits-switch-feedback`
**Depends on:** `c7-hybrid-search-core`

Finish the retrieval half:

- `apps/search/hybrid.py::find_similar(text, types, limit)` serves `POST /search/similar` from the
  vector leg, falling back to the keyword leg where no embedding exists yet. It never returns a
  record its caller may not see: an agent key reaches **shared library rows only**, which in R1
  is every chunk there is, and a test proves an owned record would be excluded if one existed.
- `apps/search/limits.py` (new, owned here): the search and Ask rate-limit buckets, reusing
  `apps.identity.rate_limit.enforce`, with `SEARCH_RATE_PER_USER_PER_MINUTE` and
  `ASK_RATE_PER_USER_PER_MINUTE`. `run_search` calls the search bucket; the Ask tasks call the
  Ask bucket and edit nothing here.
- Measure and pin the budgets for search: under 800 ms without the reranker, under 1.5 s with it,
  reported in `Server-Timing`, warm, on the seeded corpus.
- Delete the `POST /search/similar` line from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/search/hybrid.py` (`find_similar` and the search bucket call only)
- `backend/apps/search/limits.py`
- `backend/apps/search/tests_similar.py`
- `backend/apps/search/tests_scenarios.py` (its own lines only, if any)
- `backend/scripts/contract_drift_pending.txt` (one line)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- `findSimilar` on an agent key returns the nearest shared records, and a key without
  `search:read` is refused before it gets there.
- A session, with any permission, is refused on `findSimilar`: it is the agents' route.
- Exceeding the search rate limit answers 429 `rate_limited`, and the limit is a setting.
- The budgets are measured and reported in `Server-Timing`.
- The pending line is gone and `contract_drift.py` is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `(cd backend && ./run.sh run python scripts/contract_drift.py)`

**Invariants:**

Never edits `api.py` or `schemas.py`. An agent key reaches shared rows only. Every limit and every
threshold is a setting with an env override, and none of them can be disabled in a deployed
environment. The query text never reaches a log line or a URL.

### c7-e2e-seed: the seeded corpus, index and logins for the chunk 7 journeys

**Requirements:** SRC-01, SRC-02, SRC-03, J-7
**Scenarios:** none of its own; it is what SRC-S1, SRC-S3, SRC-S4, SRC-S5, SRC-S10 and AUD-S4 run against
**Depends on:** `c7-search-index-apply`, `c7-ask-switch`, `c7-embedder-mock-reranker` (done), `c5-seed-watch`

Extend `seed_e2e`, never mock:

- Index the seeded library after the library and watch seeds have run, by calling
  `reindex_all()` and embedding synchronously with the mock embedder, so a journey never races an
  asynchronous embedding.
- Make sure the corpus carries what J-7 needs and nothing more: the FFFS 2017:2 instrument with
  its provision tree, the conduct obligations the concept query must reach, records across at
  least two jurisdictions and two duty types so SRC-S3's filters have something to narrow, one
  obligation with a pending change so Ask can flag it, and one question the inventory cannot
  answer.
- Seed the second tenant with Ask switched off, so the off state can be shown without touching
  another journey's data.
- Add nothing to `e2e_logins.py` beyond what the chunk needs; the reader and the library editor
  already exist.
- Idempotent, deterministic, realistic, and anchored to the tenant-local date plus a fixed wall
  time (CLAUDE.md section 11).

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (its own seed calls only)
- `backend/apps/shared/e2e_logins.py` (its own logins only, if any)
- `backend/apps/shared/tests_seed_integrity.py` (its own assertions)
- `backend/apps/library/fixtures/check_prototype_data.py` (only if a new fixture key needs checking)

**Done when:**

- `npm run test:e2e -- --grep @smoke` boots on the seeded database with a populated index, and
  the seed integrity test asserts the chunk count per source type, that every seeded chunk is
  embedded, and that every seeded chunk's `owner_tenant_id` is NULL.
- Re-running the seed changes nothing.
- The second tenant has Ask off and the first has it on.
- No journey is edited here.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared apps.search --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `python backend/scripts/search_eval.py`
- `cd frontend && npm run test:e2e -- --grep @smoke`

**Invariants:**

The seed extends, never mocks. It is deterministic and idempotent, restores seeded data on
failure too, and holds no real personal data. Clocks anchor to the tenant-local date. Nothing a
tenant writes is indexed.

### c7-index-changes: registered changes reach the index through the outbox

**Requirements:** SRC-01, WAT-01 (the search side)
**Scenarios:** none of its own; it is what makes `POST /search/similar` useful to `c5-agent-api-flow` and AGT-S1
**Depends on:** `c7-search-index-apply`, `c5-watch-registration`, `c5-watch-curation`, `c5-outbox-cursor`

Index regulatory changes without touching a watch writer:

- Register one handler with the outbox cursor's dispatch table for the change events
  (registered, curated, confirmed), which calls `indexing.reindex_change(change_id)`.
- **Shared (platform) changes only, per owner items 4 and 10.** The handler runs with **no tenant
  active** — not `@tenant_task` — and a change event carrying a tenant owner is skipped, with a
  test proving no chunk row and no embedding request was made for it. No owned row, and no child
  of one, is indexed, embedded, reranked or sent to a model in R1, and find-similar returns
  shared rows only; this is the index half of item 10.
- A shared change's chunk carries its title, summary, the authority, the regime, the jurisdiction
  key and its own validity dates in `metadata`, like any other chunk, with `owner_tenant_id`
  NULL.
- Idempotent: the same event twice leaves one chunk per language, and a replayed event updates
  rather than duplicates.
- A change withdrawn or superseded loses its chunk.

**Owned paths:**

- `backend/apps/search/indexing.py` (the change source type only)
- `backend/apps/search/tasks.py` (the one handler)
- `backend/apps/search/tests_index_changes.py`
- the outbox cursor's dispatch table (one entry)

**Done when:**

- Registering, curating and confirming a shared change leaves exactly one chunk per language,
  found by both legs.
- A change event carrying a tenant owner leaves no chunk and asks for no embedding, proved by a
  test.
- The handler runs with no tenant active, proved by a test that asserts the tenant setting is
  empty inside it, and by a `cw_app` test that the written row is shared.
- A replayed event changes nothing; a withdrawn change's chunk is gone.
- No watch writer is edited, and the `watchwrite` key is untouched.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.watch apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`

**Invariants:**

One relay only: the outbox cursor. No tenant is activated, because nothing tenant-owned is
indexed in R1. Writes are idempotent and go through `index_write()` in `indexing.py` alone. The
chunk is subject to the same forced row-level security. No watch writer is hooked.

### c7-eval-gate: the retrieval track of the release gate, wired but not yet recorded

**Requirements:** SRC-05, AC-SRC1
**Scenarios:** SRC-S8 (un-skipped)
**Depends on:** `c7-hybrid-search-core`

Wire the real retriever into `backend/scripts/search_eval.py`. **It does not record a baseline.**
`record()` refuses any evaluator with `is_mock=True`, and until `k-embedder` arrives the only
embedder is the mock, so a recorded retrieval baseline here could only be earned by declaring a
mock chain real — which would lower the gate, not raise it (review finding HIGH 3). The real
baseline is recorded once, by `c7-embedder-selection-baseline`, when a real embedder exists.

- `apps/search/eval.py::Retriever` implements the documented protocol
  (`search(query, lang, as_of) -> [stable keys, best first]`, `name`, `is_mock`), setting up
  Django itself and reading the seeded fixture corpus.
- **`is_mock` is true when any adapter in the chain is a mock**: the embedder, the reranker, or
  both. `name` says which, so the harness's output names the chain that ran. A test pins that a
  mock embedder with a real reranker still reports `is_mock=True`.
- Run the 53 labelled questions across the five languages and report recall@10 and MRR per
  language and per match kind. With the mock chain this is a **smoke check**: it proves the
  harness, the retriever and the corpus fit together and asserts **nothing about quality**. No
  threshold is derived from it and no score of it is written anywhere.
- Prove the two paths that exist before a baseline: an unrecorded track scores and exits 0 with
  the "scored without a baseline" line, and the self-test's synthetic recorded baseline already
  exits non-zero when a score drops, which is what SRC-S8 asserts.
- Teach `search_eval.py` one rule it lacks, in both places it needs it: `validate_retrieval`
  refuses an empty `expected` today (line 138), and the scorer treats an empty expectation as a
  zero. A row with no expected keys becomes a question the retriever must answer with nothing,
  scored right when it returns nothing and wrong when it returns a hit. That is what `f03-T49`'s
  "no answer" row needs, and it keeps `search_eval.py` in one task's hands.
- The screen tolerance stays 0. No tolerance is widened.
- Note in `backend/eval/README.md` that the retrieval track is wired and **not yet recorded**,
  what blocks it (`k-embedder`), and who will record it.
- Add one line to `docs/TODO_FOR_alex.md`: the retrieval track of the release gate is unrecorded
  until D-09's key arrives, so a retrieval regression would not fail CI until then.

**Owned paths:**

- `backend/apps/search/eval.py`
- `backend/scripts/search_eval.py` (the retriever wiring, the `is_mock` rule and the
  no-expected-keys rule)
- `backend/eval/tests_scoring.py` (the new rule's cases)
- `backend/eval/README.md`
- `backend/apps/search/tests_scenarios.py` (SRC-S8 only)
- `docs/TODO_FOR_alex.md` (one line)

**Done when:**

- SRC-S8 is green: the harness reports recall and accuracy per language, and the self-test's
  synthetic recorded baseline exits non-zero when a score drops beyond its tolerance, with the
  metric named.
- `python backend/scripts/search_eval.py` passes and prints that the retrieval track is scored
  without a baseline; `--self-test` is green.
- A retriever on a mock embedder reports `is_mock=True`, and `--record` refuses it, proved by a
  test rather than by running `--record`.
- `backend/eval/baseline.json` is **unchanged** by this task, proved by `git diff`.
- A row with no expected keys is validated, scored as "must return nothing", and covered in
  `tests_scoring.py`.
- `backend/eval/README.md` and `docs/TODO_FOR_alex.md` say the track is unrecorded and why.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/search_eval.py && python backend/scripts/search_eval.py --self-test`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

No gate is lowered and no tolerance is widened to go green. `--record` refuses the mock, and this
task never runs it. A baseline is recorded only in the same commit as the real run that earned
it. The mock chain proves plumbing, never quality. The evaluation corpus is authored text, never
a publisher's. `.github/workflows/ci.yml` and `scripts/prepush.sh` are **not** touched: both
already run `search_eval.py` (ci.yml line 256; prepush.sh line 185, under `--all`).

### c7-search-screen: the search screen

**Requirements:** SRC-01, SRC-02, FP-03
**Scenarios:** none directly; SRC-S1 and SRC-S3's journey halves are `c7-search-journeys`'
**Depends on:** `c7-search-api-contract`, `c7-hybrid-search-core`, `c7-e2e-seed`, `c3-fe-obligation-versions`

Build `/search` from `design/screens/tenant-search.html` and the shared states:

- The query field with the recent and suggested chips, the filter row (type, jurisdiction, duty
  type, instrument, binding, language), the "As of" date and the "Outside our scope" toggle.
  Jurisdiction and duty type send **keys**, the two fields the contract added.
- Results with the match-kind pill on every hit through `Pill` and a presentation function, the
  instrument short name, the version, the validity, the snippet with the query terms marked in
  the hit's own language, and a link that opens the obligation card at that version.
- Empty ("No match in the inventory", offering the search outside our scope), loading, error and
  denied states, in both themes, at 390, 820 and 1280 px.
- `features/search` with `api.ts`, `hooks.ts`, `types.ts` and `search-presentation.ts`, tested.
  The contract task ships no frontend files, so this task creates the directory; the filter
  values are keys and never labels.
- The registry entry already exists (`nav.search`); add only what the screen needs.
- No journey is edited here. `c7-search-journeys`, the next wave, un-fixmes SRC-S1 and SRC-S3.

**Owned paths:**

- `frontend/src/app/(tenant)/search/**`
- `frontend/src/components/search/SearchScreen.tsx`
- `frontend/src/features/search/**`
- `frontend/src/features/shared/tone-by-kind.ts` (the match-kind entries)
- the search message namespace (en and sv)

**Done when:**

- The screen renders the seeded corpus against the real backend, with every state covered by a
  component test.
- `features/search` coverage is at least 98%, `check:messages` and `check:copy-drift` are green,
  and the production build passes.
- Every pill comes from `Pill` and a presentation function; no tone is chosen by a person and no
  string literal sits in JSX.
- The screen shows real data within 500 ms of the seeded corpus, measured against `next start`.
- No file under `frontend/tests/e2e/` is touched.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

Typography roles only. The screen copy says what the user is doing: no requirement IDs, no
restated invariants. Filters send keys, never labels. `logger`, never `console.log`. The query
never reaches a URL or an analytics call.

### c7-search-journeys: SRC-S1 and SRC-S3 against the real stack

**Requirements:** SRC-01, SRC-02, AC-SRC1
**Scenarios:** SRC-S1 (journey half), SRC-S3 (journey half)
**Depends on:** `c7-search-screen`

Un-fixme SRC-S1 and SRC-S3's journeys: sign in as the seeded reader through the UI with a
passkey, search "FFFS 2017:2" and see the instrument first with a keyword pill, search "nudging
in onboarding" and see the conduct obligations with concept pills, then filter by jurisdiction
and duty type with an "as of" date and see only what is valid.

- Settle before branching, assert rows by id, and use exact text where copy can collide.
- If a journey fails, read the screenshot and the trace before touching the screen. A screen fix
  that the journey needs goes back to `c7-search-screen`'s files only if it is small; anything
  larger stops and reports.

**Owned paths:**

- `frontend/tests/e2e/search.journey.spec.ts` (the SRC-S1 and SRC-S3 blocks only)

**Done when:**

- SRC-S1's and SRC-S3's journeys are un-fixme'd and green against the real stack, twice in a row.
- No screenshot shows a blank or error state at any step.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run test:e2e -- --grep "SRC-S1|SRC-S3"`

**Invariants:**

Every spec imports `test` from `tests/e2e/support/api-guard`, and an expected error is declared
where it happens. No API response is mocked and no token or cookie is injected; backend down
means the tests fail.

### c7-ask-grounding-stream: retrieval, grounding, citations and the stream

**Requirements:** SRC-03, AUD-02, AC-SRC2
**Scenarios:** SRC-S4 (integration half), SRC-S5 (integration half)
**Depends on:** `c7-search-similar-limits`, `c7-ai-log-backend`, `c5-contract-models-watch`, `c5-llm-anthropic-provider` (merged)

Build `apps/search/ask.py::answer_question`, the grounding and streaming half:

- Retrieve the top `ASK_RETRIEVAL_DEPTH` chunks through `hybrid`, with the same scope rule, the
  same "as of" and the caller's language.
- Nothing above the score floor means `noAnswer` true, no model call and no invented statement.
- Otherwise call the model through the one logging wrapper, streaming `text/event-stream`: a
  `start` event with the pre-generated answer id, one `statement` event per statement with its
  citation indexes, then the terminal `answer` event. The event bodies are the contract's
  Pydantic models; this task writes none of its own shapes.
- The prompt holds the question and the retrieved library chunks only: never a register row, a
  note, a comment or any other tenant row. A test asserts the exact prompt content (D-07, SRC-S6's
  first half).
- Every statement carries at least one citation; a statement the model returns without one is
  dropped, and an answer left with none becomes `noAnswer`.
- A cited obligation with an open change carries `pendingChangeId` and `pendingChangeLabel`, which
  the screen renders as a warning pill.
- Write the `ai_generation` row when the model call completes: purpose `answer`, the user, the
  tenant, model and version, `prompt_hash`, `input` (question, `asOf`, the chunk ids given to the
  model), output, citations, status draft.
- Delete the `POST /ask` line from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/search/ask.py` (`answer_question` and its helpers; `rate_answer` stays a stub)
- `backend/apps/search/tests_ask.py`
- `backend/apps/search/tests_scenarios.py` (SRC-S4 and SRC-S5 only)
- `backend/scripts/contract_drift_pending.txt` (one line)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- SRC-S4's and SRC-S5's integration halves are green, including the `ai_generation` row and the
  pending-change flag.
- An answer that cannot be grounded says so; no test accepts an uncited statement.
- The recorded prompt holds the question and library chunks only, proved by an exact assertion.
- The first streamed event arrives under 2 s on the seeded corpus.
- The read-only POST writes no audit row, and its scenario proves the count is unchanged.
- The pending line is gone and `contract_drift.py` is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.governance apps.watch apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`
- `(cd backend && ./run.sh run python scripts/contract_drift.py)`

**Invariants:**

Every model call goes through the one logging wrapper; a guard test fails any other call to the
LLM adapter. The question is the only tenant text that reaches a model, and no prompt or output
text reaches a log line or Sentry. AI output is labelled until a person confirms it. No guess:
"no answer" is a correct answer. Never edits `api.py` or `schemas.py`.

### c7-ask-limits-switch-feedback: the switch, the rate limit and the feedback write

**Requirements:** SRC-03, AUD-02, NFR-02
**Scenarios:** SRC-S6, SRC-S9
**Depends on:** `c7-ask-grounding-stream`, `c7-ask-switch`, `c7-ai-log-backend` (it owns the
`set_feedback` that `rate_answer` calls)

Finish `apps/search/ask.py`:

- With the tenant's switch off, `POST /ask` answers 403 `feature_off` and **no model call is
  made**. The check is inside the logging wrapper, which reads the switch only when a tenant is
  active, so this refuses the tenant's own Ask and nothing else (owner item 14).
- Rate limits: call the Ask bucket in `limits.py`; over the limit is 429 `rate_limited`.
- `rate_answer(answer_id, body, user_id)` serves `POST /answers/{answerId}/feedback` by calling
  `apps.governance.ai_log.set_feedback`. It is a real write, through `record()`, in the same
  transaction, with no answer text and no question text in the audit summary.
- Delete the `POST /answers/{}/feedback` line from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/search/ask.py` (the switch check, the Ask bucket call and `rate_answer` only)
- `backend/apps/search/tests_ask_limits.py`
- `backend/apps/search/tests_scenarios.py` (SRC-S6 and SRC-S9 only)
- `backend/scripts/contract_drift_pending.txt` (one line)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- SRC-S6 is green: the recorded prompt holds the question and library chunks only, and with the
  switch off the route answers 403 `feature_off` with no model call.
- SRC-S9 is green: search reports under 800 ms in `Server-Timing` on the seeded corpus and under
  1.5 s with the reranker, Ask's first streamed event arrives under 2 s, and exceeding either
  rate limit answers 429.
- Feedback on an answer writes its audit row in the same transaction, and feedback on another
  tenant's answer answers 404.
- The pending line is gone and `contract_drift.py` is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.governance apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `(cd backend && ./run.sh run python scripts/contract_drift.py)`

**Invariants:**

The switch is checked before the call, not after, and it governs the tenant's own AI only. Every
limit is a setting and none can be disabled in a deployed environment. `rateAnswer` goes through
`record()`. Never edits `api.py` or `schemas.py`.

### c7-eval-models-commands: the evaluation set as platform tables, with its commands

**Requirements:** SRC-05, ADM-02
**Scenarios:** none of its own
**Depends on:** `c7-eval-gate`

Build `EvalQuestion` and `EvalRun` in the search app from `schema.sql` §11, **as platform tables,
not library tables** (review finding HIGH 2):

- Neither model extends `LibraryModel` and neither carries a tenant column. Row-level security is
  enabled and forced with one policy that refuses any session with a tenant active, so no tenant
  principal can read or write an evaluation row at the database level.
- **The guard change this needs, named.** `backend/apps/shared/tests_rls.py` enumerates only
  models with a foreign key to `shared.Tenant` (`tenant_scoped_models()`) and asserts
  `others == OTHER_POLICIES` over exactly those tables. `eval_question` and `eval_run` have no
  tenant column, so they are invisible to that enumeration and an entry in `OTHER_POLICIES`
  would make the existing test fail. This task therefore adds a **second constant**,
  `PLATFORM_ONLY_TABLES = frozenset({"eval_question", "eval_run"})`, with a comment saying why a
  platform table is listed by hand, and **one new test of its own** in the same file that reads
  `pg_class` and `pg_policies` for each named table and demands: row-level security enabled and
  forced, exactly the one policy, and that policy's `USING` and `WITH CHECK` both refusing any
  session with a tenant active. The existing tests and constants are not edited. A `cw_app` test
  proves the same from the outside: a session with a tenant active sees nothing and writes
  nothing.
- This is the guard edit rule 7 carves out for this task, so the diff gets the per-merge security
  review that rule requires before it is merged: the reviewer checks that the new constant and
  test only add, that `IDENTITY_LOOKUP_TABLES` and `OTHER_POLICIES` are unchanged, and that no
  existing assertion was weakened to make room.
- **Why not library rows.** `schema.sql` labels them LIBRARY, but a library row may be written
  only from `proposals/apply.py`, `watch/logic.py` and the four allowed seed directories, and
  `ProposalDoorGuard` demands that only `approveProposal` and `reverifyObligation` reach a library
  write. An `eval.manage` console route writing them would need both guards loosened, which rule 7
  and CLAUDE.md §5 forbid. An evaluation question is also not a sourced public fact: nobody's
  judgement about the law is at stake in it. Record the departure from `schema.sql`'s LIBRARY
  label in `docs/inputs/INPUT_DELTAS.md`, with this reason.
- **Where the seed writes from.** `manage.py seed_eval_questions` lives in
  `backend/apps/shared/management/commands/`, which is already one of the fence's allowed seed
  directories, so the seed sits inside the fenced path even though these rows are not library
  rows and the fence does not reach them. There is **no** `apps/search/seeds/` directory: an
  unfenced seeds directory is exactly what the review refused. No platform proposal is needed,
  because nothing here is a library row.
- `EvalQuestion`: a stable key, the question, its language, an optional "as of", the expected
  obligation and provision ids, notes, active, and `source` (`seed` or `console`). Seeded
  create-only from `backend/eval/retrieval.jsonl`, so the committed corpus the gate reads and the
  set the console shows are the same rows; re-seeding keeps an edited row.
- `EvalRun`: the run time, the config (embedder, reranker, fusion constant), the metrics and the
  per-question results, written by `manage.py record_eval_run` after `search_eval.py --record`.
  Nothing writes it from a route.
- `manage.py dump_eval_questions` writes the set back into `retrieval.jsonl` for a person to
  commit, and a test proves the seeded rows and the jsonl agree.

**Owned paths:**

- `backend/apps/search/models.py` (the two models)
- `backend/apps/search/migrations/0002_eval_sets.py`
- `backend/apps/search/eval_sets.py` (the logic the commands and the routes share)
- `backend/apps/shared/management/commands/seed_eval_questions.py`
- `backend/apps/search/management/commands/record_eval_run.py`, `dump_eval_questions.py`
- `backend/apps/search/tests_eval_sets.py`
- `backend/apps/shared/tests_rls.py` (the new `PLATFORM_ONLY_TABLES` constant and the one new
  test that asserts it; nothing existing is edited)
- `docs/inputs/INPUT_DELTAS.md` (one row)

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the graph.
- Neither model is a `LibraryModel`, `tests_library_fence.py` is unchanged byte for byte, and
  `ProposalDoorGuard` is unchanged.
- `PLATFORM_ONLY_TABLES` names both tables and its own test passes over them, while
  `OTHER_POLICIES`, `IDENTITY_LOOKUP_TABLES` and every existing test in `tests_rls.py` are
  unchanged.
- A `cw_app` session with a tenant active can neither read nor write an evaluation row.
- After `seed_eval_questions`, the 53 seeded questions are present, and re-seeding keeps an
  edited row.
- `record_eval_run` writes one row from a recorded run.
- The seeded rows and `retrieval.jsonl` agree, proved by a test.
- The INPUT_DELTAS row records the departure from `schema.sql`'s LIBRARY label.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.search apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`

**Invariants:**

Platform rows: no tenant column, forced row-level security that refuses a tenant session, and no
tenant principal reaches them. The library fence allowlist and `ProposalDoorGuard` are untouched.
Keys are immutable. The gate's corpus stays the committed file; the database never becomes a
second, invisible source for CI.

### c7-eval-routes: the three evaluation routes

**Requirements:** SRC-05, ADM-02
**Scenarios:** none of its own; SRC-S8 stays green and ADM-S4's amendment belongs to the screen task
**Depends on:** `c7-eval-models-commands`

This task holds `searchapi` after `c7-search-api-contract` has let it go, and writes the contract
and the logic of its three routes together: nothing is built against a stub of them, and a
separate contract task for three small routes would cost a wave.

- Routes in `apps/search/api.py`: `GET /eval/questions`, `POST /eval/questions`, `GET /eval/runs`,
  all under `eval.manage`, all audited where they write through `record()`, paginated as the
  shared page.
- `eval.manage` is a platform permission: a tenant session and a tenant API key are refused, and
  the refusal names `requiredPermission`.
- A question added through the console carries `source: console` and is reported as not yet in the
  release gate, with one line saying how it gets there (`dump_eval_questions`, then a person
  commits the jsonl).
- Move the `POST /eval/runs` line in `contract_drift_pending.txt` from chunk 7 to chunk 14 with
  the reason, and delete the three lines this task serves.

**Owned paths:**

- `backend/apps/search/api.py`, `backend/apps/search/schemas.py` (the three operations)
- `backend/apps/search/eval_sets.py` (the route-facing functions only)
- `backend/apps/search/tests_eval_routes.py`
- `backend/scripts/contract_drift_pending.txt` (four lines)

**Done when:**

- A holder of `eval.manage` lists the questions, adds one (audited, marked as not yet in the
  gate) and lists the runs newest first.
- A tenant session and a tenant key are refused on all three, with `requiredPermission` named.
- `startEvalRun` is annotated as chunk 14 and the three served lines are gone.
- `bash generate-types.sh` produces the three operations, and the run is reverted, not committed.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit openapi.json or api.generated.ts`

**Invariants:**

No logic in `api.py`. Every write is audited through `record()`. The console is platform-only: no
tenant principal reaches an evaluation row, at the route and at the database. The library fence
and `ProposalDoorGuard` stay untouched.

### c7-ask-screen: Ask, its citations and its feedback

**Requirements:** SRC-03, AUD-02, AC-SRC2
**Scenarios:** none directly; SRC-S4 and SRC-S5's journey halves are `c7-ask-journeys`'
**Depends on:** `c7-search-screen`, `c7-ask-limits-switch-feedback`, `c7-ai-log-backend`, `c7-e2e-seed`

Build Ask as the second mode of the search screen (`/search?mode=ask`), from
`design/screens/tenant-ask.html`:

- The question field, the streamed answer rendered statement by statement from the
  `text/event-stream` the contract declares, numbered citations that open the cited obligation at
  its version, the AI label until a person confirms, and the "As of" date carried into the
  question.
- A cited obligation with an open change shows "Change pending: in force 1 Oct" as a warning pill
  through `Pill`.
- "No answer" says the inventory has nothing on it and offers a plain search.
- Helpful and Wrong post feedback, with a reason for Wrong; the state after sending is visible.
- The "Ask is switched off" state when the tenant has the switch off, and the loading, error and
  denied states. The copy names this organisation's Ask, not bleqq's agents.
- No journey is edited here. `c7-ask-journeys`, a later wave, un-fixmes SRC-S4 and SRC-S5.

**Owned paths:**

- `frontend/src/components/search/AskPanel.tsx` and the mode switch in `SearchScreen.tsx`
- `frontend/src/features/search/**` (the ask API, hooks and presentation)
- the search message namespace (en and sv)

**Done when:**

- Every state renders against the real backend, with a component test each.
- The first streamed statement appears without the screen sitting blank: a visible streaming
  state until it does.
- Coverage, `check:messages`, `check:copy-drift` and the production build are green.
- No file under `frontend/tests/e2e/` is touched.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

AI output is labelled. Pills through `Pill` only, with the tone chosen by kind. No string literal
in JSX. The question never reaches a URL, a log line or an analytics call.

### c7-ask-journeys: SRC-S4 and SRC-S5 against the real stack

**Requirements:** SRC-03, AC-SRC2
**Scenarios:** SRC-S4 (journey half), SRC-S5 (journey half)
**Depends on:** `c7-ask-screen`, `c7-search-journeys`

Un-fixme SRC-S4 and SRC-S5's journeys against the real stack and the mock model adapter the E2E
stack boots:

- Every statement shows a citation that opens its obligation, the pending change shows its
  warning pill, and the unsupported question gives "no answer" with a plain search offered.
- Feedback posts and the screen says it was received.

**Owned paths:**

- `frontend/tests/e2e/search.journey.spec.ts` (the SRC-S4 and SRC-S5 blocks only)

**Done when:**

- SRC-S4 and SRC-S5's journeys are un-fixme'd and green, twice in a row.
- No screenshot shows a blank or error state at any step.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run test:e2e -- --grep "SRC-S4|SRC-S5"`

**Invariants:**

No API response is mocked; the stack's mock model adapter is the stack's, not the test's. `test`
comes from `support/api-guard`, and an expected error is declared where it happens. No token or
cookie is injected.

### c7-fe-console-eval-sets: the evaluation screen in the console

**Requirements:** SRC-05, ADM-02
**Scenarios:** ADM-S4 (amended to include evaluation sets, and its assertions extended)
**Depends on:** `c7-eval-routes`, `c4-console-shell`, `x-frontend-split`

Draw `design/screens/console-evaluation.html` and build `/console/evaluation` from it:

- The question set with language, expected records, "as of" and active, filterable by language;
  the add-a-question form; and the marker on a question not yet in the release gate, with one
  line saying how it gets there.
- The recorded baseline per metric with who recorded it and when, and the past runs with their
  metrics, newest first. **While the retrieval track is unrecorded** (until `k-embedder`), the
  screen says so plainly in its empty state rather than showing a zero, and one line says what
  it is waiting for.
- Empty, loading, error and denied states in both themes, at 390, 820 and 1280 px, following
  `design/system/foundations.md`, `pills-and-labels.md` and `navigation.md`, with existing tokens
  only (the Green MCP server for a value).
- The console rail gains Evaluation for `eval.manage`; the platform admin does not see it.
- Amend ADM-S4 in `governance/app.md` to include evaluation sets in the library editor's list,
  and extend its journey accordingly.

**Owned paths:**

- `design/screens/console-evaluation.html`
- `frontend/src/app/(console)/console/evaluation/**`
- `frontend/src/components/console/EvaluationScreen.tsx`
- `frontend/src/features/evaluation/**`
- `frontend/src/shared/navigation/registry.ts` (one entry)
- the console message namespace (en and sv)
- `frontend/tests/e2e/governance.journey.spec.ts` (the ADM-S4 block only)
- `backend/apps/governance/app.md` (ADM-S4's wording)
- `docs/plans/UI_Implementation_Plan.md` (the two rows for this screen)

**Done when:**

- ADM-S4 is green with evaluation sets reachable for the library editor and absent for the
  platform admin, each direct endpoint answering 403 with `requiredPermission` named.
- A question added on the screen appears with its not-yet-in-the-gate marker.
- The unrecorded baseline reads as unrecorded, not as zero.
- The card matches the built screen in both themes at the three widths.
- Coverage, `check:messages`, `check:copy-drift` and the production build are green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "ADM-S4"`

**Invariants:**

The console is platform-only: no tenant permission reaches it and no tenant content appears on
it. Permissions, never role names. Design decides how it looks; the rules come from the PRD. No
string literal in JSX.

### c7-ai-log-screen: the AI log

**Requirements:** AUD-02
**Scenarios:** AUD-S4 (journey half)
**Depends on:** `c7-ai-log-backend`, `c7-ask-screen`, `c7-e2e-seed`, `c4-fe-audit-log`

Draw `design/screens/admin-ai-log.html` and build `/admin/ai-log` (`ai_log.read`), following the
audit log screen `c4-fe-audit-log` built:

- Filters: purpose, review state and a record. Rows: purpose, model and version, the subject, the
  time, the review state, the citations and the feedback.
- A row opens to show the output and its citations, each opening the cited record.
- The AI label is on every row until a person has confirmed it.
- Empty, loading, error and denied states, in both themes, at the three widths.
- Extend `features/governance` with the AI log api, hooks and presentation, tested.
- The registry entry under Admin for `ai_log.read`.
- Un-fixme AUD-S4's journey: ask a question as the seeded reader, mark the answer wrong with a
  reason, then open the AI log as an approver and see the row with its model, purpose, citations
  and review state.

**Owned paths:**

- `design/screens/admin-ai-log.html`
- `frontend/src/app/(tenant)/admin/ai-log/**`
- `frontend/src/components/admin/AiLogScreen.tsx`
- `frontend/src/features/governance/**` (the AI log additions only)
- `frontend/src/shared/navigation/registry.ts` (one entry)
- the admin message namespace (en and sv)
- `frontend/tests/e2e/governance.journey.spec.ts` (the AUD-S4 block only)
- `docs/plans/UI_Implementation_Plan.md` (the row for this screen)

**Done when:**

- AUD-S4's journey is un-fixme'd and green.
- A reader without `ai_log.read` does not see the screen in the rail and is denied on the route.
- `features/governance` coverage stays at or above its floor, and `check:messages`,
  `check:copy-drift` and the build are green.
- The card matches the built screen in both themes at the three widths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "AUD-S4"`

**Invariants:**

Only a holder of `ai_log.read` reaches it, and only their tenant's rows. AI output is labelled
until confirmed. No model or provider name appears in copy beyond the model field the log holds.
Pills through `Pill`; no string literal in JSX.

### c7-aud-s4-integration: every model output is logged with its review state

**Requirements:** AUD-02
**Scenarios:** AUD-S4 (integration half, un-skipped)
**Depends on:** `c7-ask-limits-switch-feedback`, `c7-ai-log-backend`, `c5-ai-log-and-so-what-draft`, `c5-cases-so-what-and-links`, `c5-watch-registration`

AUD-S4's "given" is three producers at once — a So what draft, an Ask answer and an agent
classification — and its "when" confirms the So what through chunk 5's
`POST /changes/{id}/so-what/confirm`. Chunk 5 builds the draft in `c5-ai-log-and-so-what-draft`
(global wave 9) and the confirm route in `c5-cases-so-what-and-links` (global wave 11), both
after `c7-ai-log-backend`'s global wave 6, which is why the scenario cannot live there (review
finding MEDIUM 8). This task is nothing but the scenario, and it runs once all three producers
have merged, at global wave 12 or later.

- Make one of each kind of `ai_generation` row, then assert each carries purpose, model, version,
  input reference, output, citations and review state pending.
- Confirm the So what through the chunk 5 route and assert the row's review state becomes
  confirmed with the person and the time.
- Mark an answer as wrong through `POST /answers/{id}/feedback` and assert the feedback is stored.
- Assert a holder of `ai_log.read` lists the rows for their tenant only.
- Delete only AUD-S4's skip line.

**Owned paths:**

- `backend/apps/governance/tests_scenarios.py` (AUD-S4's integration half only)

**Done when:**

- AUD-S4's integration half is un-skipped and green.
- No production file is touched: if a producer is missing a field the scenario needs, the task
  stops and reports rather than adding it here.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.search apps.watch apps.cases apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

A scenario proves behaviour that exists; it never adds behaviour. No tenant content reaches an
audit summary. AI output is labelled until a person confirms it.

### f03-T49: Ask gives no answer about a standard's controls

**Requirements:** SRC-03, SRC-05, INV-08, AC-INV2
**Scenarios:** SRC-S12 (un-skipped)
**Depends on:** `f03-T35`, `c7-ask-grounding-stream`, `c7-eval-gate`

From STANDARDS STD-22. The library holds a standard's edition, its public facts and its one
conformance obligation, and no clause or control text at all, so a question about one of its
controls must get "no answer":

- Add the evaluation row to `backend/eval/retrieval.jsonl` with no expected keys, which
  `c7-eval-gate`'s validator and scorer read as "the retriever must return nothing", so the
  release gate keeps it true once the baseline is recorded.
- **Do not re-record the baseline.** `backend/eval/baseline.json` is not this task's file, and
  the retrieval track has no recorded baseline yet (review findings HIGH 3 and LOW 12): there is
  nothing for a new row to move. `c7-embedder-selection-baseline` records the track once, with
  this row already in the corpus.
- Write `test_src_s12` against the mock model and against the recorded real model's answer.
- The answer states nothing about the control and cites nothing.

**Owned paths:**

- `backend/eval/retrieval.jsonl`
- `backend/apps/search/tests_scenarios.py` (SRC-S12 only)

**Done when:**

- `test_src_s12` is green against the mock and the recorded model.
- `python backend/scripts/search_eval.py` validates and scores the new row, and
  `backend/eval/baseline.json` is unchanged, proved by `git diff`.
- No real clause or control title appears anywhere in the repository.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search --settings=config.test_settings --noinput`
- `python backend/scripts/search_eval.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

The library never holds a standard's licensed text, clause or control titles, or a paraphrase,
and neither do the index, Ask or the evaluation set. The tolerance for this row is not widened,
and no baseline is written here.

### c7-j7-journey: J-7 end to end

**Requirements:** SRC-01, SRC-02, SRC-03, AC-SRC1, AC-SRC2, J-7
**Scenarios:** SRC-S10 (un-fixme'd, `@smoke`)
**Depends on:** `c7-search-journeys`, `c7-ask-journeys`, `c7-e2e-seed`, `f03-T49`

One journey, marked `@smoke`, signed in through the UI with a passkey as the seeded reader:

- Search "FFFS 2017:2": the instrument is first, with a keyword match pill.
- Search "nudging in onboarding": the conduct obligations come back with concept pills.
- Set "As of" and ask a question: the answer streams, every statement shows a citation, and a
  citation opens the cited obligation at the version in force on that date.
- Settle before branching, assert rows by id, and use exact text where copy can collide.

**Owned paths:**

- `frontend/tests/e2e/search.journey.spec.ts` (the SRC-S10 block only)

**Done when:**

- SRC-S10 is un-fixme'd and green as `@smoke` against the real stack, twice in a row.
- The whole `@smoke` set still passes.
- No screenshot shows a blank or error state at any step.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run test:e2e -- --grep "SRC-S10"`
- `npm run test:e2e -- --grep @smoke`

**Invariants:**

`test` comes from `support/api-guard`, expected errors are declared where they happen, and the
journey fails on any undeclared `/api/` response of 400 or above or any page exception. No token
or cookie is injected and no API response is mocked. When it fails, read the screenshot and trace
before touching code.

### c7-security-review: security sweep over the whole chunk

**Requirements:** SRC-01, SRC-02, SRC-03, SRC-05, AUD-02, H7
**Scenarios:** none
**Depends on:** every other chunk 7 task except `c7-review-fixes` and `c7-chunk-close`

A read-only review of the whole chunk's diff on `main`, complementing the per-merge reviews with
what only shows across the chunk. It stays one task: it is a single read of a single diff, and
splitting it would mean two people each holding half the picture.

- H7 in the shape item 4 accepts: `search_chunk` is **not** a `LibraryModel`, carries
  `owner_tenant_id`, has row-level security enabled and forced with a `FOR ALL` policy confined
  to the own zone and a `FOR SELECT` policy adding shared rows, and `OTHER_POLICIES` names that
  second policy with its reason. No read path reaches a chunk whose owner the caller may not see,
  including `POST /search/similar` on an agent key and the reranker's inputs.
- **The library fence is untouched.** `backend/apps/shared/tests_library_fence.py` is unchanged
  byte for byte across the whole chunk diff: `LIBRARY_WRITE_ALLOWLIST` gained no entry,
  `LIBRARY_WRITE_ALLOWED_DIRS` gained no directory, and `ProposalDoorGuard` still names only the
  proposal routes. The new `index_write()` fence and its AST guard are the chunk's only new
  guard, and nothing but `apps/search/indexing.py` writes a chunk.
- **Shared rows only, in R1.** No owned library record, and no child of one, is indexed,
  embedded, reranked or sent to a model; `owner_tenant_id` is NULL on every row the seeds and the
  tests produce; the change handler skips an owned change and runs with no tenant active
  (owner items 4 and 10).
- The evaluation tables are platform tables: not `LibraryModel`, no tenant column, forced RLS
  that refuses a tenant session, written only from `eval.manage` routes through `record()` and
  from a command in the fenced seed directory. No tenant principal reaches an evaluation row at
  the route or at the database.
- No query, question, answer, prompt or chunk body reaches a log line, a Sentry breadcrumb, an
  audit summary, an outbox payload, a URL or an analytics call, frontend `logger` calls included.
- The only tenant text reaching a model is the Ask question; the guard test on the LLM adapter
  still fails any call outside the wrapper; the switch is checked before the call; and the switch
  is read **only when a tenant is active**, so a platform (library) model call ignores it (owner
  item 14).
- The `aiEnabled` write carries `@requires_step_up` and its audit row carries the step-up id.
- Read-only POSTs write nothing at all, and `rateAnswer` writes its audit row in the same
  transaction.
- The rate limits and the budgets are settings, and none of them can be disabled in a deployed
  environment.
- Nothing of a standard's text is in a chunk, an embedding input or a model input.
- No baseline was recorded on a mock chain: `backend/eval/baseline.json` moved only if
  `c7-embedder-selection-baseline` ran, and then only in that task's own commit.

**Owned paths:**

(none: it edits no file)

**Done when:**

A findings report ranked by severity, each finding with its file, line and failure scenario.
Either nothing critical, high or medium remains, or each such finding has become work for
`c7-review-fixes`, which merges before the close. Anything below medium becomes a row in
`HARDENING.md`.

**Gates:**

- `Read-only review of the chunk 7 diff on main against CLAUDE.md section 5, playbook 4.2 and 4.3, and OWNER_RECOMMENDATIONS items 4, 7, 10 and 14`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write apps.shared.tests_four_eyes apps.search.tests_index_fence --settings=config.test_settings --noinput`

**Invariants:**

Read-only: it edits no file. Its findings are data for the main agent and are never applied here.

### c7-review-fixes: close the review's findings

**Requirements:** as the findings name
**Scenarios:** as the findings name
**Depends on:** `c7-security-review`

Fix every critical, high and medium finding, rerun the review over the fix diff, and repeat until
nothing at medium or above remains. If the review found nothing at medium or above, close at once
with a note saying so. Findings below medium become rows in `HARDENING.md` with the task that
will fix them, never a silent pass.

**Owned paths:**

- whatever the findings name, kept minimal and listed in the report
- `docs/plans/briefs/HARDENING.md` (its own rows)

**Done when:**

- No critical, high or medium finding remains open.
- Each fix has a test that fails without it.
- The guard suites and the touched apps' tests are green.
- Every finding below medium is a row in `HARDENING.md` with an owner.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

A fix never lowers a gate, skips a test or weakens a guard to go green. No finding is closed by
rewording it. The library fence stays untouched.

### c7-embedder-selection-baseline: choose an EU embedder and record the retrieval baseline

**Requirements:** SRC-01, SRC-05, D-09
**Scenarios:** none; it is what makes SRC-S8's gate bite
**Depends on:** `c7-search-similar-limits`, `c7-eval-gate`, `f03-T49`, `c7-embedder-mock-reranker` (done), `k-embedder`

Only once Alex supplies the keys and the approval that typed search queries may reach the
candidate endpoint. Runs locally: it holds `embed`, `eval` and `deps`. It stays one task because
its deliverable is one recorded run; there is no interior point at which it is half done.

**The candidates are EU-hostable only (owner item 7).** The production boot guard accepts, for
the embedder and the reranker, `none` or `bedrock` in `eu-central-1`, `eu-west-1`, `eu-west-3`,
`eu-south-1`, `eu-south-2` or `eu-north-1`, with an in-region model id; London (`eu-west-2`) and
Zurich (`eu-central-2`) are refused, and so are `global.`, `us.` and `apac.` profiles. A
US-hosted model can therefore be a **test-environment** choice at most, and production search
stays keyword-only until an EU endpoint is logged. Score only models that can run under that
rule, or say plainly in the README and in `docs/TODO_FOR_alex.md` that the chosen model is
test-only and what production is missing.

- Fetch each candidate's current documentation before using it and log every claim relied on in
  `docs/plans/Verification_Log.md` with its URL and the date.
- Score each candidate covering all five content languages against the retrieval set, per
  language, and write the comparison into the evaluation README.
- Wire the chosen provider behind the existing `embedder` adapter, keeping 1024 dimensions and
  the HNSW limit, and re-embed the corpus with `manage.py reindex_library`.
- **Record the retrieval baseline** with `search_eval.py --record`, in the same commit, with the
  model and version in the run config. This is the first and only recording of that track: the
  retriever now reports `is_mock=False` because no adapter in its chain is a mock. Then remove
  the "unrecorded" line `c7-eval-gate` put in `docs/TODO_FOR_alex.md` and update
  `backend/eval/README.md`.
- Prove the gate bites: make a deliberate regression (remove a question's record from the index),
  see `search_eval.py` exit non-zero naming the metric, and revert it.
- If the keys never arrive, this task is cut and `c7-chunk-close` says so: the retrieval track
  stays unrecorded and the test deploy searches with the mock vectors.

**Owned paths:**

- `backend/apps/shared/adapters/embedder.py` (the real provider only)
- `backend/apps/shared/tests_embedder.py` (its own tests)
- `backend/eval/baseline.json`, `backend/eval/README.md`
- `backend/config/settings.py` (one labelled block), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `docs/plans/Verification_Log.md` (its own rows)
- `docs/TODO_FOR_alex.md` (the unrecorded-track line)
- `backend/pyproject.toml` and `poetry.lock`, only if the provider needs a client and no HTTP
  call will do

**Done when:**

- The chosen model is justified by scores per language, recorded in the README, and it is either
  EU-hostable or explicitly marked test-only with production's gap named.
- The retrieval baseline is recorded by a real run in the same commit, and the gate passes
  against it.
- A deliberate regression fails the gate with the metric named, and is reverted.
- **The test environment boots with the real provider**, and the production boot guard still
  refuses the mock and refuses a non-EU processor. Production stays keyword-only until
  `c14-eu-data-location` admits an EU endpoint; the task does not claim a production boot it
  cannot have.
- The key comes only from the environment and appears in no file, and gitleaks is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared apps.search --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/search_eval.py --record` (once) `&& python backend/scripts/search_eval.py`
- `gitleaks git . --config .gitleaks.toml`
- `bash scripts/prepush.sh --quick`

**Invariants:**

Provider documentation is fetched, never recalled. A key lives only in the environment. No tenant
content reaches the embedder; only the query and the library text do, and only after Alex's
approval. The baseline is recorded in the same commit as the real run that earned it, and never
on a mock. No tolerance is widened. Dependencies change in this task alone, and only if an HTTP
call cannot do the job.

### c7-chunk-close: close chunk 7

**Requirements:** SRC-01, SRC-02, SRC-03, SRC-05, AUD-02, J-7
**Scenarios:** none
**Depends on:** `c7-j7-journey`, `c7-ai-log-screen`, `c7-aud-s4-integration`, `c7-index-changes`, `c7-eval-routes`, `c7-review-fixes`

After every task has merged:

- Set SRC-01, SRC-02, SRC-03 and SRC-05 to `built` in `search/app.md`; SRC-04 stays `pending`.
  Set AUD-02 to `built` in `governance/app.md` and note ADM-02's evaluation surface as built with
  the rest still to come.
- Record that SRC-S7 (chunk 13) and SRC-S13 (`f03-T73`, chunk 8) are the only SRC scenarios still
  skipped, each with its owner.
- Add coverage floors with their measured value, statement count and date from a full run:
  `apps/search/hybrid.py`, `ask.py`, `indexing.py`, `sources.py`, `eval_sets.py`, `api.py`, and
  restate the governance floors the AI log moved.
- Mark the chunk 7 rows built in `UI_Implementation_Plan.md`, with the deviations named:
  `POST /eval/runs` deferred to chunk 14, saved searches to chunk 13, and the register filters
  (`applicability`, `complianceStatus`) deferred to chunk 8 with the register.
- Write the chunk 7 row in `IMPLEMENTATION_STATUS.md`, naming what was cut and whether
  `c7-embedder-selection-baseline` ran.
- **Say plainly whether the retrieval track of the release gate is recorded.** If
  `c7-embedder-selection-baseline` was cut, the row says the track is wired but unrecorded, that
  a retrieval regression will not fail CI until `k-embedder` arrives, and that the line stays in
  `docs/TODO_FOR_alex.md`.
- Copy every default taken and every open question into `docs/TODO_FOR_alex.md`, including
  `q-search-fence`'s answer (item 4, Option B, built), the scope-applies-to-search default, the
  cost and approval half of `k-anthropic`, and the unrecorded track.
- Prove no chunk 7 route answers 501, no chunk 7 journey is fixme, and no "chunk 7" line remains
  in `contract_drift_pending.txt` except the one moved to chunk 14.
- Prove the library fence is unchanged across the whole chunk: `git diff` on
  `backend/apps/shared/tests_library_fence.py` over the chunk's commits is empty.
- Run the full E2E suite and the whole pre-push checklist.

**Owned paths:**

- `backend/apps/search/app.md`
- `backend/apps/governance/app.md`
- `backend/scripts/coverage_gate.py`
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `docs/plans/UI_Implementation_Plan.md`
- `docs/TODO_FOR_alex.md`

**Done when:**

- The status cells, floors and ledger rows match what is merged.
- `coverage_gate.py` passes on a full run with the measured values and dates restated.
- `requirements_coverage.py`, `contract_drift.py` and `compliance_check.py --all` pass.
- The full `npm run test:e2e` is green, `@smoke` included.
- `TODO_FOR_alex.md` lists every default taken and every open question.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `python backend/scripts/requirements_coverage.py && python backend/scripts/contract_drift.py && python backend/scripts/compliance_check.py --all`
- `python backend/scripts/search_eval.py`
- `cd frontend && npm run test:e2e`
- `bash scripts/prepush.sh --all`

**Invariants:**

Floors sit just below the measured coverage and are never lowered to go green. Status stays
`built`, not `verified`, until Alex has exercised it against a running server. Anything needing a
person goes to `docs/TODO_FOR_alex.md`. The chunk does not close with a route answering 501, a
journey left fixme, or a release gate quietly unrecorded and unmentioned.
