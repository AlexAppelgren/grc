# Early R1 packages: chunk 5 and 7 work that starts before chunks 3 and 4 finish

Written 2026-09-19 by the main agent from the chunk 5 to 7 package maps of the parallel-plan
workflow (docs/plans/PARALLEL_PLAN.md follows). Alex asked for the build to run in parallel
across chunks without cutting a corner. These five packages depend only on what is already on
`main` and share no file with a running task, so each runs now as a cloud task
(docs/runbooks/WORKTREES.md, "Cloud tasks"). Their chunks' full task files come later and
build on them.

Rules for all five, beyond the session's standing rules:
- Read the PRD rows named, `docs/inputs/schema.sql` and `docs/inputs/data-model.md` for any
  table, `docs/DECISIONS.md` for D-07 and D-09, and the existing code you extend.
- Put your tests in the new test module your package owns. Do not edit a shared test module
  (`tests_adapters.py`, `tests_rls.py`, `tests_production_guard.py`) unless the package says
  so, because other packages run beside you.
- `backend/config/settings.py`, `backend/.env.example` and `docs/runbooks/RAILWAY_VARIABLES.md`
  are shared by several packages: add your settings as one block with a comment naming the
  package, and touch nothing else in them. Every threshold is a setting with an env override.
- Provider documentation is fetched, never recalled, and each claim relied on gets a row in
  `docs/plans/Verification_Log.md` with its URL and today's date.

## E1: fetched text is screened for embedded instructions (chunk 5, AGT-07)

**Owned:** `backend/apps/agents/screen.py`, `backend/apps/agents/tests_screen.py`,
`frontend/eslint.config.js` (one rule), one new frontend test file.

`screen(text)` returns the risk-flag kinds found (`embedded_instructions`). Deterministic, no
model call, pure. It normalises Unicode (NFKC, zero-width characters) before matching and
catches instruction phrases, role and system prefixes, claims of authority, asides addressed to
an AI in en, sv, da, nb and fi, tool-call shaped payloads, and HTML comments or hidden
elements. The stored text is never altered. Guard against pathological input: prove a 200 KB
string screens in well under a second (no catastrophic regex backtracking).

Test first from `backend/eval/classification.jsonl`: every injection row is flagged and no
clean row is (tolerance 0). Add adversarial cases (casing, spacing, zero-width characters,
mixed languages). T-AGT-07-3: ESLint `react/no-danger` as an error, plus a test proving no
component renders fetched text through `innerHTML` / `dangerouslySetInnerHTML`.

**Gates:** `apps.agents` tests, ruff, mypy, compliance lint; frontend lint, typecheck, test.

## E2: console cards for change facts and platform agent keys (chunk 5, design)

**Owned:** `design/screens/console-change-facts.html`, `design/screens/console-agent-keys.html`.
**May add a row to:** `design/screens/console-shell.html` (its rail destinations only).

Card `console-change-facts.html`: changes waiting for confirmation (type, urgency, flags,
scope, library links, timeline edits), reached from the queue's Change facts filter. Card
`console-agent-keys.html`: platform keys with agent, scopes, a secret shown once, the passkey
step-up on create, and revoke. Every card shows empty, loading, error and denied states in
both themes, follows `design/system/foundations.md`, `design/system/pills-and-labels.md` and
`design/system/navigation.md`, and uses only existing tokens (the Green MCP server if you need
a value). Screen copy says what the user is doing; no requirement IDs on screen. Check each
card in a headless browser at 390, 820 and 1280 px.

**Gates:** `bash scripts/prepush.sh --quick`.

## E3: the Anthropic provider behind the LLM adapter, with streaming (chunks 5 and 7)

**Owned:** `backend/apps/shared/adapters/llm.py`, `backend/apps/shared/tests_llm.py` (new).

Fetch the current Anthropic Messages API documentation (requests, streaming events, errors,
timeouts, model and version fields, and what it says about inference region) and log what you
rely on. Implement `AnthropicLlm.complete()` and add `stream()` to `LlmAdapter`, yielding text
deltas and final usage. Model id, timeout, retries and max tokens are settings with env
overrides; the API key comes only from the environment. Make `MockLlm` deterministic and
grounded: it answers only from the context chunks in the prompt, one statement per cited chunk
with `[n]` markers, and nothing when given no chunks, so Ask's scenarios can assert on it.

No prompt or output text in logs or Sentry. The caller's rule stays: no tenant-zone text is
sent (D-07); production still refuses the mock at boot. Tests use a stubbed transport; never a
live call. Do not add an SDK dependency: use the HTTP client the project already has, or say
in the report why that is impossible and stop before changing dependencies.

**Gates:** `apps.shared` tests, ruff, mypy, compliance lint.

## E4: a concept-aware mock embedder and the reranker adapter (chunk 7, SRC-01, AC-SRC1)

**Owned:** `backend/apps/shared/adapters/embedder.py`, `backend/apps/shared/adapters/reranker.py`
(new), `backend/apps/shared/tests_embedder.py` (new).
**May add to:** the production guard's mock list (one entry for the reranker mock) and its
test, if the guard is table-driven; otherwise name the change in the report.

Today's `MockEmbedder` hashes whole texts, so no concept can ever match. Replace it with a
deterministic embedder built from hashed stems plus a small concept table kept as test data,
so that across the evaluation corpus in all five languages "nudging in onboarding" reaches
`obl-esma-warnings` by the vector leg alone and "FFFS 2017:2" matches by keyword. Unknown text
keeps a hash vector. Add the reranker adapter (interface, mock, none) with `RERANKER_PROVIDER`
and the top-50 window as settings. The production guard refuses the mock reranker.

**Gates:** `apps.shared` tests (including the production guard), ruff, mypy, compliance lint,
`python backend/scripts/search_eval.py` if it runs against the embedder.

## E5: agent and run records, and API keys bound to an agent (chunk 5, AGT-01, ID-10)

**Owned:** `backend/apps/agents/models.py`, `backend/apps/agents/migrations/`,
`backend/apps/agents/seeds/`, `backend/apps/agents/tests_models.py`, one identity migration,
`backend/apps/identity/models.py` (the `ApiKey.agent` field only),
`backend/apps/identity/api_keys_logic.py` and `backend/apps/shared/authentication.py` (the
agent on the principal only), `backend/apps/shared/management/commands/seed_reference.py`
(one seed call), `backend/apps/shared/kinds.py` (new kinds only),
`backend/apps/shared/tests_rls.py` (add `agent_run` to the guarded tables only).

Models per `schema.sql` `agent` and `agent_run` (v0.3, R1 columns only). `Agent`: immutable
key, kind, description, active, current version; loaded idempotently by `seed_reference` from
`backend/agents/<agent>/v<n>/definition.yaml` (watch-sweeper v1). The definition says kind `watch`,
which `AgentKind` lacks: add it or map it, and add an INPUT_DELTAS row saying which. `AgentRun`:
agent, api_key, tenant nullable (null is a platform run for the shared library), started_at,
finished_at, status (a kind), model, pipeline_version, stats (JSON with a named schema),
output_ref, error, idempotency_key unique per key. A mixed table with RLS enabled and forced:
library rows visible to all, tenant rows to their tenant only.

ID-10, the chunk 5 half: `ApiKey.agent` becomes a foreign key to `Agent`. `resolve_api_key`
puts the agent id and label on the principal so `record()` writes an agent actor. No key
scope reaches the library.

Test first: model and constraint tests, the RLS isolation test for `agent_run` as `cw_app`,
seed idempotency, and that an agent key's writes are audited with the agent as actor.

**Gates:** `makemigrations --check`, `migrate_from_zero`, `apps.agents`, `apps.identity` and
`apps.shared` tests, ruff, mypy, compliance lint, requirements coverage. Security review before
merge (tenancy, authentication, audit).
