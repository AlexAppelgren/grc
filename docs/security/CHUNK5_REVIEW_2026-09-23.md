# Security review: chunk 5, agents, keys, runs and the watch door (2026-09-23)

## Question

Do the chunk 5 surfaces hold the product invariants of CLAUDE.md section 5, PRD AGT-01,
WAT-01, AUD-01 and NFR-01, D-64, D-74, D-78 and D-80? The surfaces are the agent API and its
runs, agent-key minting and a bank key's scopes, the D-78 zone-escape allowlist, run
provenance, the watch door, curation confirmation and its fence edit, "So what?", fetched
content screening, the standards watch and inactive sources, and the re-check loop. Two
gaps found earlier are to be shown closed:

- a bank's key holding `changes:write`;
- an unvalidated `agentRunId`.

## Standard

The same as the chunk 1 and chunk 6 reviews: OWASP ASVS 5.0.0, chapters V1 (encoding and
injection, for fetched content), V2 (validation), V4 (API), V8 (authorization) and V16
(logging), read against the invariants in CLAUDE.md section 5.

## Method

1. Read CLAUDE.md and the app.md of agents, watch and proposals. Read D-61, D-64, D-74,
   D-78, D-80 and ADR 0058.
2. Read every production module in scope, in three passes:
   - agents: `api.py`, `runs.py`, `screen.py`
   - identity: `api_keys_logic.py` and the key routes, `session_logic.build_principal`
   - shared: `authentication`, `permissions`, `tenancy`, `outbox._enter_zone`
   - watch: `api.py`, `write.py`, `registration.py`, `curation.py`, `keys.py`,
     `sources.py`, `so_what_draft.py`, `schemas.py`, `models.py`
   - proposals: `logic.create`, `_decidable`, `_decision_run`, `standards.py`
   - governance: `ai_log.logged_for`
   - frontend: the machine-confirmed presentation in `features/watch` and
     `components/{watch,console}`
3. Grepped every `agent_run_id` a caller can send and traced each one to its check. Did the
   same for every `set_config` in production code.
4. Wrote a failing test for each fix before making the fix.
5. Ran the guard suites with the watch, agents, identity, proposals and governance suites,
   then the static gates (listed under "Gates run").

Base: `claude/r1-int-w23-done` merged with `claude/r1w3-watch-curation-confirm-frontend-done`.
The merge left `seed_e2e` broken, so every seed-integrity test and every seeding journey
failed:

- two `_confirmer_key()` definitions;
- an Ask seed that still named a confirming editor, which D-74 retired.

That was fixed first, in its own commit. It was not a security finding.

## The two earlier gaps

| Gap | Verdict | Evidence |
|---|---|---|
| A bank's key holding `changes:write` (or `agent-runs:write`, `sources:write`) writes the shared watch | **Closed. Three layers, each proven.** (1) Minting: `create_api_key` grants only `TENANT_KEY_SCOPES` = `ALL_SCOPES − PLATFORM_ONLY_SCOPES`, so asking for a watch scope answers 422. (2) Resolving: an older bank key has those scopes withheld at `resolve_api_key` and gets a `key_scopes_withheld` security-log row. (3) Routes: every run and watch write refuses a key with a tenant, with 403 `tenant_agents_not_available`, before its scopes are read. This goes through `runs.refuses_tenant_keys` on open and close run, source check and add-document, and through `require_change_writer` on create, patch, the two event routes and replace-obligations. `require_open_run` refuses it again in logic. Curation confirmation refuses any key with a tenant, and `proposals:review` is platform-only. Routes added after the gap reach the same gates: "So what?" rides createChange and updateChange, and a standards re-check is a source check. | `identity/tests_scenarios.test_id_s20`; `identity/tests_api_keys.test_a_bank_key_holding_a_watch_write_is_refused_at_the_route`, `test_the_two_sets_divide_every_scope_and_a_bank_writes_only_proposals`; `watch/tests_registration.test_every_watch_write_refuses_a_banks_key_with_the_reason_named` (eight routes, nothing stored, no audit row); `agents/tests_runs.test_a_tenant_bound_key_is_refused_with_the_reason_named`; `watch/tests_curation.test_no_bank_and_no_key_without_the_review_scope_confirms`; `agents/tests_scenarios.test_agt_s1`. |
| An unvalidated `agentRunId` | **Closed for every operation that accepts one.** Each goes through `runs.require_open_run` or `require_open_run_of_key`: a missing run answers 422 `run_not_open`, another key's run (or one that never existed) answers 404, and a closed run answers 422. The operations are: createChange (required from a key); createProposal (required from an agent-bound key, and checked whenever anyone names a run); an agent's approve and reject (`_decision_run`); confirmChangeCuration (`curation._decision_run`); and recordSourceCheck. No route takes a run id for the AI log: an `agent_review` row must name a run, by check constraint. `proposal.agent_run_id` is a plain column, not a foreign key, so the logic check is its only guard, and it holds. | `agents/tests_flow.test_every_step_naming_another_keys_run_answers_404`, `test_a_run_that_never_existed_answers_the_same`, `test_a_proposal_or_a_change_naming_no_run_is_refused`, `test_a_proposal_or_a_change_naming_a_closed_run_is_refused`; `proposals/tests_create.test_naming_no_run_or_a_closed_one_is_refused`, `test_a_run_of_another_key_or_a_person_naming_one_is_not_found`; `governance/tests_agent_review.test_an_agent_decides_only_with_its_decision_inside_an_open_run_of_its_own`; `watch/tests_curation.test_a_key_decides_inside_an_open_run_of_its_own_with_its_model_call`. |

## Verdict per area

| Area | Verdict | Evidence |
|---|---|---|
| The agent API and runs | **Holds.** A key acts only on its own run (404, never 403). The definition is compared with the key's own agent, never looked up by name. Open and close each write their audit and outbox rows in one transaction with the agent as actor (ID-10). A retry replays. `agent_run` is under forced RLS, and a key never reads the run list. | `agents/tests_runs`, `tests_flow`, `tests_models.test_a_tenant_sees_its_own_runs_and_the_library_runs`, `tests_contract.test_a_key_never_reads_the_run_list_or_touches_a_key`. |
| Agent-key minting | **Holds, one low (L5).** A platform key needs `agent_definitions.manage` and a passkey step-up, and a bank session's permissions are cut to `TENANT_PERMISSIONS`. Revocation takes effect on the next request, because the key row is read every time and never cached. A key bound to a draft or inactive definition is still minted and still resolves (L5). | `identity/tests_scenarios.test_id_s20`, `tests_api_keys.test_only_a_platform_admin_reaches_the_keys`. |
| The D-78 allowlist | **Held as written; the net had a hole, now fixed (L4).** Seven entries, with `api_keys_logic.py` narrowed to three functions, and function-level matching is tested. The guard read only callers of `clear_tenant()` and `platform_zone()`, so a module issuing its own `set_config` was never named. `outbox._enter_zone` does exactly that, for a sound reason nobody had recorded. | `shared/tests_tenancy.test_only_record_leaves_the_tenant_zone`, and new `test_only_the_tenancy_module_and_the_outbox_cursor_set_a_session_setting_by_hand` (red with the outbox entry removed). |
| Run provenance | **Holds for every write that names a run, and for the merge path after L2.** The PATCH, event and link writes of a key take no run (L6, handed on). The agents spec promises a run only for changes and proposals. | `agents/tests_flow`; new `watch/tests_so_what_draft.test_a_second_sighting_that_brings_the_first_draft_logs_it_in_its_own_run`. |
| The watch door | **Holds.** Two layers. In Python, `watch_write` refuses any library table outside the seven watch tables. In the database, the `cw.library_door` trigger opens the watch tables to the `watch` door alone and refuses the inventory to it. No watch route reaches `apply` or `apply_reverification`. The Python regex can be slipped (a `WITH … UPDATE`, a schema-qualified name), but the trigger still refuses (I3). | `shared/tests_library_fence.test_a_watch_route_reaching_the_applier_is_refused`, `test_a_watch_route_is_gated_as_its_map_says_and_reaches_nothing_but_the_watch_door`; `shared/tests_library_db_guard.test_each_door_opens_the_tables_it_names_and_no_other`, `test_every_watch_step_writes_through_its_own_entry_point_as_the_app_role` (now including a confirmation); `watch/tests_write`. |
| Curation confirmation on scope separation (D-74) and its fence edit | **Holds.** The confirming agent comes from the key's row, never from the body, which forbids extra fields. An unbound key answers `agent_not_bound`. `changes:write` never reaches confirmation: the fence proves the route carries the confirmer gate and not the writer gate. A person needs `proposals.review` and a fresh passkey. Nobody confirms their own suggestion (`own_suggestion`), and no agent confirms a suggestion by another key of its own definition (`same_agent`); both are backed by check constraints. Everything runs under a row lock on the change. A retry logs no second model call (D-80). The record names both agents, and every screen shows "confirmed" only for a person's confirmation and "machine-confirmed" otherwise. What D-74 accepts is unchanged: this confirmation rests on scope separation, not four eyes. | `shared/tests_library_fence.test_a_curation_confirmation_needs_the_review_scope_or_a_person_who_steps_up`; `watch/tests_curation.test_an_agent_never_confirms_its_own_suggestion_nor_one_of_its_own_agent`, `test_the_database_refuses_a_confirmation_the_route_would_refuse`, `test_a_repeated_confirmation_confirms_nothing_twice_and_writes_nothing`; `watch/tests_curation_races`; the change and console presentation tests. |
| "So what?" | **Holds.** The server makes no model call. It stores what the agent reported, with an `ai_generation` row marked draft and reported-by-agent, and an audit row that leaves the words out. Each bank's copy arrives unconfirmed on its own case, and no bank's words reach the draft or its log. | `watch/tests_so_what_draft` (`test_the_draft_reaches_every_banks_case_unconfirmed`, `test_no_banks_words_reach_the_draft_or_its_log_row`). |
| Fetched content screening | **Did not hold on the correction path; fixed (M1). The proposal path was handed on (M2), fixed since in `agent-write-guards`.** `agents/screen.py` is pure, bounded and never alters text. Registration and add-document screen, and a run's own flags only add to the screen's. | `agents/tests_screen`, `tests_scenarios.test_agt_s9`, `watch/tests_registration.ScreeningWhatWasFetched`, new `watch/tests_curation.ScreeningACorrection`. |
| Input at the trust boundary | **Did not hold; fixed (L1).** Several labels were bounded at 300 characters where the column is 200, and addresses at 2083 where the column is 2000: a run's over-long value answered 500. A 41-character risk flag was silently cut to 40, which altered evidence. | New `watch/tests_registration.WhatARunSendsFitsWhereItIsKept`. |
| The standards watch and inactive sources | **Holds, one bypass fixed (L3), one low handed on (L7).** A `standards_body` source, or a source on a `STANDARDS_PUBLISHER_HOSTS` host, is registered with checks off. A PATCH cannot switch a publisher-host source on. A run may log no check of an inactive source (422 `source_inactive`, before any write). A standard's term needs a standards-body authority, and a standard's provision is refused as `licensed_text`. | `watch/tests_sources` (`test_a_standards_body_source_is_registered_with_its_checks_off`, `test_an_editor_cannot_switch_a_publishers_checks_on_or_move_a_source_onto_one`, `test_a_run_may_not_log_a_check_of_a_source_whose_checks_are_off`, new `test_a_publishers_host_written_with_its_root_dot_is_still_the_publisher`); `proposals/tests_kinds` (`licensed_text`). |
| The re-check loop | **Holds on the invariants; budgets were handed on (M3), enforced since in `agent-write-guards`.** Drift enters only as a `new_obligation_version` proposal through the proposal door. The re-verification stamp takes a session alone, with `proposals.review` and a step-up. The approver is independent by `_decidable` and by check constraint. A check needs an open run of the same key and is audited in its own transaction. | `watch/tests_scenarios.test_wat_s12`, `watch/tests_sources`, `proposals/tests_apply`. |

## Findings

Severity: critical / high / medium / low / info. Status: fixed / open (with where it gets
fixed) / accepted.

| # | Sev. | Where | Finding | Status |
|---|---|---|---|---|
| M1 | medium | `watch/curation.update_change_facts` | `PATCH /changes/{id}` wrote a new title or summary without the injection screen that registration applies (AGT-07). A run that re-read a page could put instruction-like text in front of every bank, and in front of a confirming agent, with no flag anywhere. | **Fixed.** The corrected title or summary is screened. Findings are added to every page of the change (existing flags stay) and named on the audit row as `riskFlags`. The text is stored as it arrived. Test: `ScreeningACorrection`, red before the fix. |
| M2 | medium | `proposals/logic.create` | Nothing screens a proposal's title, payload texts or `fieldSources`, so fetched text that an agent copies into a correction reaches the review queue unflagged. An agent reviewer may confirm it into the library as machine-confirmed. A flag also gates nothing (F9): a machine confirmer may confirm a change whose page is flagged. | **Fixed 2026-09-23** (`agent-write-guards`, HARDENING H23). Every text a proposal arrives with is screened and the findings stored in `proposal.risk_flags`, shown in the queue. An agent's approval of a flagged proposal, an agent's correction bringing flagged text in, and an agent's curation confirmation of a change with a flagged page answer 409 `risk_flagged` and wait for a person. Tests: `proposals/tests_screening.py`, `watch/tests_curation` (flagged page), red before the fix. |
| M3 | medium | `agents/watch-sweeper/v1/definition.yaml` (`max_proposals_per_run`, `max_rechecks_per_run`) | The per-run budgets live only in the agent's definition, and the server enforces none of them. A runaway or injected run can file unbounded proposals and re-check lines under one open run and flood the review queue. A run's stats are self-reported. | **Fixed 2026-09-23** (`agent-write-guards`, HARDENING H24). `WATCH_RUN_MAX_PROPOSALS`, `WATCH_RUN_MAX_CHANGES` and `WATCH_RUN_MAX_RECHECKS`, settings with env overrides, are held under a lock on the run; a write past its budget answers 422 `run_budget_exhausted` and stores nothing. A close keeps the server's own count of sources checked, changes registered, proposals submitted and records re-checked. Tests: `agents/tests_budgets.py`, red before the fix. |
| L1 | low | `watch/schemas.py` | Schema bounds looser than their columns: four labels at 300 characters into 200-character columns, addresses at 2083 characters into 2000. A longer value answered 500 `internal_error` instead of a 422 naming the field, and an over-long risk flag was cut to 40 characters without a word. | **Fixed.** `COLUMN_LABEL_MAX` (200), `PageUrl` (2000) and `RISK_FLAG_MAX` (40), stated in each description. Test: `WhatARunSendsFitsWhereItIsKept`, with seven cases, all red before the fix. |
| L2 | low | `watch/registration._merge` | A second sighting that brought a change its first "So what?" logged the model call with no run, although `register_change` had just checked the run (AUD-02). | **Fixed.** `_merge` receives the checked run. Test: `test_a_second_sighting_that_brings_the_first_draft_logs_it_in_its_own_run`, red before the fix. |
| L3 | low | `watch/sources._on_a_publisher_host` | `https://iso.org./` (a fully qualified name with its root dot) was not recognised as the publisher, so it was registered with its checks on (D-45). | **Fixed.** The trailing dot is stripped. Test: `test_a_publishers_host_written_with_its_root_dot_is_still_the_publisher`, red before the fix. |
| L4 | low | `shared/tests_tenancy.py` | The D-78 guard matched callers of two functions by name, so a module that set `app.tenant_id` with its own `set_config` left a zone without review. `outbox._enter_zone` is one such module (sound, unrecorded). | **Fixed.** A second guard lists every statement string that sets a session setting, allowing `tenancy.py` and `outbox.py::_enter_zone` only. |
| L5 | low | `identity/api_keys_logic.create_agent_key`, `resolve_api_key` | A draft or inactive agent definition is minted working keys, and deactivating a definition leaves its keys working. Both shipped definitions are drafts. A key's scopes are not tied to its agent's kind either (a review agent's key could hold `proposals:write`). Four eyes still stops self-approval. | **Open**, HARDENING H26. |
| L6 | low | `watch/curation.update_change_facts`, `add_event`, `update_event`, `replace_obligations` | A key's correction, milestone and link writes name no run, so a "So what?" filed through PATCH is logged with none. A key bound to no agent (a legacy key) stores its suggestion with no suggester, so a later confirmation names only the confirmer. | **Open**, HARDENING H25. |
| L7 | low | `watch/sources.update_source` | An editor can switch on a `standards_body` source whose host is not in `STANDARDS_PUBLISHER_HOSTS`. D-45 keeps standards bodies off "until the lawyer answers", and the host list is the only lock on that clearance. | **Open**, HARDENING H29. |
| L8 | low | `watch/api.py` (`Idempotency-Key` on createChange, recordSourceCheck, addChangeDocument, addChangeEvent), `watch/registration.register_change`, `proposals/logic.create` | The watch writes accept an `Idempotency-Key` and ignore it. Two concurrent registrations of one stable key answer 500 on the unique constraint, and a retry succeeds. A proposal's replay key is global rather than per proposer: a key reused in a later run answers the old proposal, and a clash with another zone's invisible row is a 500. | **Open**, HARDENING H27. |
| L9 | low | `watch/sources.record_check` | A re-check line can name a library record that does not exist, or one that does not cite this source, so the coverage log (assurance evidence) can show a comparison that never happened. | **Open**, HARDENING H28. |
| I1 | info | `watch/schemas.py` `LABEL_MAX`, `TEXT_MAX`, `KEY_MAX`, `LINKS_MAX` | Constants, not settings. They bound a column or a request body, not a decision (their comment says so), and a setting that could exceed its column would recreate L1. | **Accepted.** |
| I2 | info | `watch/write._WRITE_STATEMENT` | The Python fence's statement pattern misses a write after a CTE and a schema-qualified table name. The database trigger (ADR 0058) refuses both for `cw_app`, so the Python layer is the second line. | **Accepted, noted.** |
| I3 | info | `shared/tests_library_db_guard.py` | The app-role guard counted `watch/curation.py` as proven without a confirmation. | **Fixed.** The guard now confirms as a second editor as the app role. The agent path is proven in `watch/tests_curation`. |
| I4 | info | `identity/api_keys_logic.resolve_api_key` | The `key_scopes_withheld` row is written once per `last_used_at` throttle window, not once per use. | **Accepted.** One row per window is enough to see a bank key carrying a watch scope. |

## Gates run

Backend:
- `apps.shared`, `apps.watch`, `apps.agents`, `apps.identity`, `apps.proposals` and
  `apps.governance`, which include the guard suites (RLS, tenancy, tenant isolation, route
  permissions, audit on write, library fence, library database guard): 1,207 tests, 0
  failures, 34 skipped as pending scenarios.
- ruff and mypy: clean.
- `compliance_check.py --all`: 0 findings.
- `requirements_coverage.py`: 0 problems.
- `api_docs_gate.py`: 0 outside the ledger, 0 stale.
- `contract_drift.py`: 0 unexplained.

Frontend:
- Lint: 0 errors. Two warnings, already present, in `sidebar.test.tsx`.
- Typecheck: clean.
- The watch, console and inventory unit tests: 351 passed.
- `check:messages` and `check:copy-drift`: ok.

E2E: WAT-S1, S2, S4, S6, S7, S9 and S10; AGT-S10 (J-4); INV-S14; PRO-S13; SRC-S4, S5 and
S10 (J-7). All 13 passed. The six pending `fixme` journeys matching the same patterns did
not run: AGT-S4, S5, S6, S7 and S13, and WAT-S8.

`prepush.sh --quick`: all gates green.
