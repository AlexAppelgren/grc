# Security review: chunk 7, search, Ask, the evaluation set and the AI log (2026-09-23)

## Question

Do the chunk 7 surfaces — `POST /search`, `POST /search/similar`, `POST /ask`,
`POST /answers/{answerId}/feedback`, the three evaluation routes, `PUT /tenant/ai`,
`GET /ai-generations`, the search index and its change handler, and the search, Ask,
evaluation and AI log screens — hold the product invariants of PRD SRC-01, SRC-03, SRC-05
and AUD-02, D-07, D-10, owner items 4, 7, 10 and 14, and hardening row H7: two zones, the
library fence, every model call logged, no tenant text in a log, a prompt or a model beyond
the typed question, and every limit a setting that a deployed environment cannot switch off?

## Standard

The same as the chunk 1 and chunk 6 reviews: OWASP ASVS 5.0.0, chapters V4 (API), V8
(authorization), V14 (data protection) and V16 (logging), read against CLAUDE.md section
5, playbook 4.2, 4.3 and 4.7, and the areas the package brief names: H7; no tenant text in
logs or prompts beyond the typed question; the switch read only with a tenant active;
`aiEnabled` step-up with the assertion id; logging of aborted streams; platform-only
evaluation tables and the `tests_rls` edit; change chunks carry no tenant data; AI log
visibility per tenant; rate limits.

## Method

1. Read `CLAUDE.md`, `docs/CONVENTIONS.md`, the `c7-security-review` and
   `c7-review-fixes` tasks in `docs/plans/briefs/CHUNK7_TASKS.md`, D-07, D-09, D-10, D-81,
   D-82, D-86, D-87 and HARDENING H7, H13, H15, H16.
2. Read every production file under `backend/apps/search/` (`api.py`, `ask.py`,
   `hybrid.py`, `limits.py`, `indexing.py`, `sources.py`, `tasks.py`, `eval.py`,
   `eval_sets.py`, `models.py`, the four migrations and the three commands), the pieces they
   lean on (`apps/shared/ai.py`, `apps/shared/tenancy.py`, `apps/shared/adapters/`
   `{llm,embedder,reranker}.py`, `apps/identity/rate_limit.py`, `config/api.py`'s handlers,
   `apps/shared/sentry_scrub.py`, `docker-entrypoint.sh`'s gunicorn line, the
   production-safety block in `config/settings.py`), `apps/governance/{ai_log,api}.py`,
   `apps/tenants/{api,logic}.py`'s switch, and on the frontend
   `components/search/{SearchScreen,AskPanel}.tsx` and `features/search/*`.
3. Traced a streamed answer past the request: the transaction commits when the view
   returns, the stream runs with no tenant set, `ai.stream`'s log opens its own transaction
   and activates the bank, and `HttpResponseBase.close()` runs the iterator's closer (which
   logs an aborted call) before `request_finished` closes the connection.
4. Compared `backend/apps/shared/tests_library_fence.py` before the first chunk 7 search
   commit (`7adfc88^`) and now, by its constants' syntax trees.
5. Ran the search, governance and tenants suites with the guard suites, then ruff, mypy, the
   compliance lint, requirements coverage, the API documentation gate and contract drift.

## Verdict per area

| Area | Verdict | Evidence |
|---|---|---|
| H7: the index's own zone | **Holds.** `search_chunk` is not a `LibraryModel`, carries `owner_tenant_id`, has RLS enabled and forced with the split H15 shape (a FOR ALL policy confined to the session's own zone and `library_rows_visible` FOR SELECT adding shared rows); `MIXED_TABLES` and `OTHER_POLICIES` name it. Only `apps/search/indexing.py::index_write` opens the `index` door, which the H16 trigger accepts on this table alone. Every read (`run_search`, `find_similar`, `passages`, the reranker's window) goes through the one `_candidates` statement under that policy. | `apps/shared/tests_rls.py`, `tests_library_db_guard.py`, `apps/search/tests_index_model.py`, `tests_index_fence.py`, `tests_hybrid.SearchScopeTests.test_a_chunk_a_bank_owns_is_never_read`, `tests_similar.FindSimilarReachesSharedRowsOnlyTests`. |
| The library fence | **Holds in substance, not byte for byte.** `LIBRARY_WRITE_ALLOWLIST`, `LIBRARY_WRITE_ALLOWED_DIRS` and `LIBRARY_WRITING_ROUTES` are identical to `7adfc88^`; `WATCH_WRITING_ROUTES` gained `confirmChangeCuration`, which is watch-curation-confirm's and not chunk 7's. The file's one chunk 7 edit is the integration fix `6a8629d` (D-87): a `DOOR_NAMERS` row pinning the new `eval` door to its two openers and a reworded comment. See I1. | AST comparison of the four constants; `git log -- backend/apps/shared/tests_library_fence.py`. |
| Shared records only (D-10) | **Holds.** `sources.py` skips any record, or child of one, whose instrument or obligation has an owner; `tasks.index_change` returns before reading anything for an event in a bank's zone and runs with no tenant; a change has no tenant column and its chunk is its title, summary, authority and flags, all library facts. No chunk of a standard's clauses exists (the library holds none) and `passages` leaves every obligation under a standard out before ranking (D-81). | `tests_indexing`, `tests_index_changes`, `tests_seed_integrity` (the standard's rows), `tests_ask` scope tests. |
| Evaluation tables | **Holds.** `eval_question` and `eval_run` have no tenant column, are not `LibraryModel`s, and carry one `platform_only` FOR ALL policy refusing any session with a tenant set, plus the H16 trigger with the `eval` door opened only by `create_question()` and `record_run()`. The routes need `eval.manage`, a platform permission a bank session never carries since H13, and the one route write goes through `record()`. | `tests_rls.PLATFORM_ONLY_TABLES` and its test, `tests_library_db_guard`, `tests_eval_routes`, `tests_eval_sets`. |
| No tenant text in logs, audit, outbox, URLs, analytics | **Holds.** The search app's four log lines carry counts, ids and kinds; validation errors carry the field and pydantic's message, never the input; Sentry drops request bodies and redacts exception values; gunicorn logs the path without the query; the screen keeps the query and the question in component state and the request body only, never in the URL, storage or the `logger`. | `tests_hybrid.SearchWritesNothingTests.test_the_query_text_is_never_logged`, `tests_ask.test_the_question_reaches_no_log_line_no_audit_row_and_no_outbox_row`, `tests_ask_limits.test_no_question_answer_or_note_reaches_the_audit_the_outbox_or_a_log_line`, `tests_similar.test_the_query_a_refused_reader_typed_is_nowhere_in_the_refusal`, `tests_no_query_in_logs`; `SearchScreen.searchOf`. |
| The prompt | **Holds.** The prompt is the numbered library passages and the question folded onto one line; the log keeps a hash of it. The only model call in the product is `ai.stream` from Ask; the wrapper guard fails any other caller of the adapter. | `tests_ask.test_the_prompt_is_the_question_and_the_library_passages_exactly`, `test_a_question_cannot_write_a_passage_of_its_own`, `tests_ai_wrapper`. |
| Tenant text reaching other models | **Did not hold; fixed** (M1). | Below. |
| The switch is read only with a tenant active | **Holds.** `ai.ensure_enabled` reads the database's own `app.tenant_id`, not the Python mirror, so a platform call reads no bank's switch and a bank an earlier transaction activated does not decide one; an unreadable row counts as off; the check comes before the first byte. | `governance/tests_ai_switch.py` (six tests). |
| `aiEnabled` write | **Holds.** `PUT /tenant/ai` needs `security.manage` and `@requires_step_up`; `set_ai_enabled` locks the row and writes `tenant.ai_switched` with before, after and `step_up_assertion_id`. | `tenants/tests_organisation.py`. |
| Aborted and failed streams | **Holds.** A reader who leaves mid-answer closes the response, whose closer closes `_events`, whose `closing(model)` throws into `ai.stream`, which logs `stop_reason = aborted` with the words written so far; a model failure logs `failed` then ends the stream with `model_unavailable`; a stream closed before the model was asked logs nothing. Django runs the closers before `request_finished`. | `tests_ask.test_a_reader_who_leaves_mid_answer_still_leaves_the_call_logged`, `test_a_reader_who_leaves_before_the_model_is_asked_leaves_no_row`, `test_a_model_that_fails_mid_answer_leaves_what_the_reader_saw_logged`. |
| Read-only POSTs, `rateAnswer` | **Holds.** Search, similar and Ask write no audit row and no chunk; `rateAnswer` writes the verdict and its audit row in the request transaction, and an audit failure takes the verdict with it. Who may rate is L2. | `tests_hybrid.SearchWritesNothingTests`, `tests_similar.test_the_read_writes_nothing`, `tests_ask_limits`. |
| AI log visibility per tenant | **Holds.** `GET /ai-generations` needs `ai_log.read`; RLS cuts the mixed table to the bank's own rows and the library's; the review state of a shared "So what?" is each bank's own, computed and never written. No row carries the question; an answer's row carries its output, citations and the reader's note, visible to the bank's AI log readers, which AUD-02 asks for. | `governance/tests_ai_log.py` (`test_a_bank_reads_its_own_rows_and_the_librarys`, `test_a_bank_cannot_write_move_or_delete_the_librarys_row`, the review-state tests). |
| Rate limits and budgets | **Did not hold; fixed** (M2). Each bucket's size already refuses to boot below 1, and every budget is a setting with an env override. Stream concurrency is L1. | Below. |
| The retrieval baseline | **Holds.** `backend/eval/baseline.json` records nothing (`recorded: false`); no baseline was written on the mock chain. | `git log -- backend/eval/baseline.json`. |

## Findings

Severity: critical / high / medium / low / info. Status: fixed / open (with where it gets
fixed) / accepted.

| # | Sev. | Where | Finding | Status |
|---|---|---|---|---|
| M1 | medium | `apps/search/hybrid.py` `run_search`, `find_similar`, `_candidates`, `_reranked` | What a reader types into search is the bank's own text (the module says so), and it went to the embedder and the reranker, both models, whatever the bank's AI switch said. `PUT /tenant/ai` tells an administrator that off means no text of the bank's goes to a model, and D-07 names the Ask question as the only tenant text that does. A bank's own key may also hold `search:read` (`TENANT_KEY_SCOPES`), so up to 8000 characters of its text went the same way through `POST /search/similar`, whose description said a key belongs to no bank. Latent in deployments today (`EMBEDDER_PROVIDER=none` until D-09's key, and a deployed reranker cannot be the mock), live the day either is contracted. | **Fixed.** `run_search` passes the bank's `ai_enabled` and `find_similar` the key's bank's (a platform key has none and passes) to `_candidates` and `_reranked` as `models`; off, the vector leg is `NULL` without calling the embedder and the reranker is `NoReranker`, which is exactly the contracted keyword-only state. Ask is unchanged: `answer_events` refuses a switched-off bank before `passages` runs. The two operations' descriptions and `setTenantAi`'s say so. Tests, red before the fix: `tests_hybrid.HybridLegsTests.test_a_bank_that_switched_its_ai_off_sends_its_query_to_no_model`, `tests_similar.SimilarRouteTests.test_a_banks_own_key_sends_no_text_to_a_model_once_the_bank_switched_its_ai_off`. D-88 (security-review-c7). Whether the query may reach an embedder at all is Alex's (I3). |
| M2 | medium | `config/settings.py` `RATE_LIMITING_ENABLED` | The brief requires that no rate limit can be disabled in a deployed environment. Each bucket's size refuses to boot below 1, but `RATE_LIMITING_ENABLED=false` in the environment switched every bucket off at once — the sign-in ceremonies' (ID-02), search's and Ask's, which caps what one caller spends of the model budget — and a deployed environment booted with it. | **Fixed.** Production-safety rule 9 refuses to boot a deployed environment with it off; laptops and tests keep the switch. Test, red before the fix: two cases in `apps/shared/tests_production_guard.py` (refused on `prod`, boots on `local`); `.env.example` names the rule. |
| L1 | low | `apps/search/limits.py`, `docker-entrypoint.sh` | Ask's limit is a rate (10 a minute per person), not a concurrency cap. Each open stream holds one gunicorn thread until the model finishes, up to `LLM_DEADLINE_S` (180 s), and the default deployment has 2 workers × 4 threads = 8. One member with `search.use` can hold most of them for every bank for as long as the model writes; two can hold all. Authenticated, attributable on the AI log (`asker_id`), availability only. | **Open**, HARDENING H47 (`r1-perf`). |
| L2 | low | `apps/search/ask.py` `rate_answer`, `governance/ai_log.py` `answer_of` | An answer is found by its bank, not its asker, so any member with `search.use` who knows the id of a colleague's answer can replace that colleague's verdict and note. Ids are random and appear only on the AI log, so the reach is a member who also holds `ai_log.read`; every change is audited. | **Open**, HARDENING H48. |
| I1 | info | `apps/shared/tests_library_fence.py` `DOOR_NAMERS` | Not byte for byte: the integration fix `6a8629d` (D-87) added the `eval` door's row naming `create_question()` and `record_run()` as its only openers. It pins a new door to its homes rather than widening the Python fence, which neither list nor any route map changed; the door itself is on Alex's list (TODO, r1-int-w23). | **Accepted, noted.** |
| I2 | info | the stream after the first byte | An exception other than `LlmError` raised while the stream is sent is outside Django's handlers, so gunicorn's error log prints it with its message. Sentry redacts exception values; the one write the stream makes (`log_generation`) has no check constraint whose message could carry the output. Nothing reachable carries tenant text today. | **Accepted, noted.** |
| I3 | info | D-07 | With the switch on, the search query reaches the embedder and the reranker, which D-07's words ("no tenant-zone text is sent by us to a model except the question typed into Ask") do not name; the chunk 7 plan made it conditional on Alex's approval of the embedder. M1 puts it under the switch; the wording is Alex's. | **Open**, `docs/TODO_FOR_alex.md` (security-review-c7). |

## Gates run

Backend: `apps.search`, `apps.governance` and `apps.tenants` with `apps.shared.tests_rls`,
`tests_tenant_isolation`, `tests_library_fence`, `tests_library_db_guard`,
`tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`, `tests_ai_wrapper`,
`tests_production_guard` and `tests_no_query_in_logs` (441 tests, 18 skipped as pending
scenarios, 0 failures); ruff; mypy; `compliance_check.py --all`;
`requirements_coverage.py`; `api_docs_gate.py` (0 outside the ledger, 0 stale);
`contract_drift.py` (0 unexplained); `prepush.sh --quick`. No frontend file changed.
