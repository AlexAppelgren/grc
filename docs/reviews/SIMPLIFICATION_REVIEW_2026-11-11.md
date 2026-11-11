# Simplification review, whole application (2026-11-11)

**Commit read:** `f4d3e87` (equal to `main`).

**Question.** Where can the code and the API become smaller without losing function or
security?

**Method.** Three area reviews read the API surface, the backend behind the routes and the
frontend. Scripts counted the callers of each operation in `openapi.json`, compared the
schemas property by property, built the frontend import graph and measured comment and
documentation text. Vulture found dead-code candidates, and each one was counted again by
grep over production code, tests and migrations. Nothing in the repository changed apart
from this file, and no line-reduction figure below was measured by doing the change.

**Result.** The built contract is 2.2 times the designed one (294 operations and 513
schemas against 134 and 167 in `docs/inputs/openapi.yaml`), 24 operations have no
production caller, and about half of the Python lines in the production image are tests,
seeds and tools that the server never runs. Ten changes need no decision from the owner
and six need one.

## 1. Where the size is

| Measure | Value |
|---|---|
| Backend lines outside tests and migrations | about 102,000 |
| of which `api.py` and `schemas.py` | 38,358 (documentation text is 47% of their lines and 71% of their characters) |
| of which comments and docstrings behind the routes | 13,465 of 63,716 (21%); 29% of those narrate history |
| `config/settings.py` | 1,370 lines for 202 environment settings; 49% comments |
| Migrations | 101 files, 13,628 lines, before any production data |
| Backend tests | about 98,000 lines |
| Python lines in the production image that the server never runs | about 111,000 of 220,647 |
| API operations, designed and built | 134 and 294; 101 are in both |
| Schemas, designed and built | 167 and 513 |
| Operations with no production caller | 24 |
| Frontend lines outside tests and generated types | 44,178; clone rate 4.6%; no unreachable production file |

The functions are not the problem: 2,896 functions with a median of 10 lines, and the
long ones are dense rules. The frontend is not the problem either; a safe pass there
removes 5 to 6% of the source. The weight is in the contract (operations, schemas and
their prose), in text beside the code, and in what ships.

## 2. Changes that need no decision from the owner

| ID | Change | Reduction | Risk |
|---|---|---|---|
| B-1 | Remove ten operations that another route already answers or that are superseded: seven redundant reads (`GET /obligations/{id}/interpretation`, `GET /tenant/footprint/scope-items/{id}`, `GET /tenant/org-units/{id}/licences`, `GET /taxonomy/dimensions`, `GET /vocab/{list}/{key}`, `GET /tenant/teams/{key}/members`, `GET /research-requests/{id}`), `DELETE /tenant/members/{user_id}` (superseded by `POST /tenant/members/{id}/remove`, the only one the screens call), `GET /agent-runs` beside `GET /console/agent-runs`, and `GET /reference/product` | 10 operations, about 290 handler lines, 4 schemas, their rows in `permissions.py` and `routes.py` | Low. Move two E2E isolation probes to routes that stay; point `listDimensions` at `/vocab/term_dimension`. The two designed operations (`DELETE /tenant/members/{user_id}`, `GET /agent-runs`) need a row in `docs/inputs/INPUT_DELTAS.md` |
| B-2 | One `{key, kind, label}` reference and one `{id, name}` reference in place of twenty; drop the other exact duplicates and the 30 schemas nothing references | About 60 schemas, 600 lines of `schemas.py` | Low. All 606 referencing properties already carry their own description, so the documentation gate holds |
| B-3 | Keep tests, seeds, `perf/`, `eval/` and `scripts/` out of the image through `backend/.dockerignore` | About 111,000 lines leave the image | Low. CI and the journeys run the seeds from a checkout, not from the image. `apps/library/fixtures/prototype_data.json`, `apps/library/baseline/*.json` and `backend/agents/` stay, because `seed_reference` and the agents read them |
| B-4 | Delete dead code. Backend: five unreferenced functions (`is_reenrolment`, `licence_of`, `product_of`, `VocabularyEntry`, `NOT_BUILT`), the dead settings `CREDENTIAL_POLICY_NOTICE_DAYS`, `EMBEDDER_API_KEY`, `DEFAULT_TENANT_TIMEZONE`, `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE`, and eleven test-only helpers that move to `testing.py`. Frontend: 51 declarations, 36 type aliases, 129 message keys and five Radix packages with no importer (`checkbox`, `popover`, `select`, `switch`, `tabs`) | About 210 backend lines, 280 frontend lines, 258 catalog lines, 5 packages | Low. The Radix pins are named in CLAUDE.md section 4 and ADR 0019, which change with them |
| B-5 | Frontend library data layer: make `features/library/types.ts` aliases over the generated types and delete the 27 field-by-field copies in `features/library/api.ts`, as `docs/CONVENTIONS.md` 3.1 already requires | About 560 source lines and 360 test lines | Medium-low. The four real narrowings stay as small functions |
| B-6 | `settings.py`: give `env_int` `min` and `max` arguments, add `env_choice` and `env_float`, keep one line per setting and the prose in `.env.example` | 1,370 to about 800 lines | Low. 59 of 143 integer settings have a boot-time bound today in 36 separate blocks; with the helper a bound costs nothing, so every threshold can have one |
| B-7 | Shared test scaffolding. Frontend: one `renderWith` and shared wire fixtures (70 render wrappers and 72 adapter scripts today). Backend: one table-driven gate base for the nine per-app contract modules and one refusal table | About 900 frontend and 400 to 700 backend test lines, no assertion removed | Low |
| B-8 | One `FormDialog` and one `ConfirmDialog` (60 `<Modal>` uses today), one show-once secret panel in place of five, one pager in place of twelve, one participants panel in place of two, one loading-error-empty wrapper for 50 chains | About 1,000 to 1,200 frontend source lines | Low to medium. Two dialogs have special closing rules; journeys read `data-new-key` and `data-plain-key` |
| B-9 | Backend duplicates: one API key mint and one revoke in place of four each (the copies have drifted in what they record), one `CasesCase` builder in place of four, one label writer and one label resolver, the 13 copies of `_person`, the 41 written-out `not_found` errors, and one code-to-status table (today `in_use` is 409 through `answers_problems` and 422 through `config/api.py`) | About 500 lines | Low to medium. Every `record()` call and step-up id stays |
| B-10 | Generate the mechanical part of each operation's "Errors:" paragraph from the auth class and the decorators. `unauthenticated` is written by hand 285 times in 50 wordings | About 450 to 500 docstring lines | Low. The decorators stay the source of truth |

## 3. Changes that need a decision from the owner

| ID | Decision | Reduction if taken |
|---|---|---|
| B-11 | Eleven documented operations have no caller: duties and their completion (REG-07), `POST /applicability`, term create and update (VOC-07), source create and update, change documents and events, and `POST /proposal-batches`. Wire them to a screen or an agent, or cut them | 11 operations, 487 handler lines, 14 schemas |
| B-12 | Comment style. `docs/PLAYBOOK.md` lines 69 to 73 prescribe comments that "read like a logbook". One line of reason beside the code, with the history in the ADR or the commit, removes the narrative | 3,500 to 4,500 lines, plus the settings file |
| B-13 | Squash the migrations before the first production data. Hand work, because 85 `RunSQL` operations block Django's squasher; `migrate_from_zero`, `tests_rls.py` and the trigger tests prove the result | 101 files to about 20; 3,000 to 4,000 lines |
| B-14 | Merge routes whose permission is the same on both sides: participants (six routes to three), `POST /taggings/preview` into the batch route with `dryRun`, the two problem-report posts into one, the pause pair into the existing PATCH | 7 operations, about 280 handler lines |
| B-15 | Remove stubs for work that does not exist: `ManagedAgentsRunner` raises `NotImplementedError` in every method, `poll` is never called, and `file_retag` serves a runner that is not built. `BedrockLlm` is the same kind of stub, but it is the EU path of D-54 and stays until that work is planned | About 150 lines |
| B-16 | Remove the green-core spike page and its dependency (`frontend/docs/D-04-spike.md` allows it), and choose one of the two scanners that read the same lockfile (`audit-gate.mjs` and osv-scanner) | One route, one spec, one pinned dependency, 137 script lines |

## 4. What should stay as it is

The eight case transitions, the approve and reject pairs, the four proposal lists and the
tenant settings writes each carry their own permission, guard or step-up, so merging them
would move a check from a decorator into a branch. The per-feature `api.ts`, `hooks.ts`
and `types.ts` files are thin already. The ungated-route registry, the route table and
the structural tests in `apps/shared/` are the proof of the gates. A pagination helper
would save no lines.

## 5. Defects found on the way

- **Console run panel.** `GET /console/agent-runs` answers newest first
  (`backend/apps/agents/platform.py:144`). The frontend assumes oldest first, reads the
  last page and reverses it (`frontend/src/features/agents/api.ts:77-84`,
  `frontend/src/components/console/PlatformRunsPanel.tsx:52`), so the panel shows the
  oldest runs. Read in the code, not run.
- **Runbook drift.** `docs/runbooks/RAILWAY_DEPLOY.md` step 6 offers `seed_demo` on the
  deployed test environment, and the command refuses every deployed environment.
  `.env.example` documents `CREDENTIAL_POLICY_NOTICE_DAYS` as effective, and nothing
  reads it.

## 6. Recommended order

1. **First batch.** B-1 to B-4, because they remove contract surface and shipped code
   with no decision needed. B-6 follows.
2. **Second batch, after the decisions of section 3.** B-11 and B-13 give the largest
   reduction per decision.
3. **Third batch.** B-5 and B-7 to B-10, one per commit, each with the suites of the
   apps it touches.
