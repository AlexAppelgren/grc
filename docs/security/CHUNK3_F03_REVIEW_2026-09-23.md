# Security review: chunk 3's library reads, standards and the regulatory-scope features, with chunk 2's residue (2026-09-23)

## Question

Do the library read API (instruments, provisions, obligations and their record sources),
the standards rules of PRD 0.3 (the standard level kind, the provision trigger, the opt-in
matcher and its SQL twin, the E2E-only standard), the jurisdiction mirror and its derived
scope, markets watch and unwatch with the watched views, and vocabulary usage and merge
hold the product invariants of CLAUDE.md section 5 (INV-01, INV-02, INV-08, FP-01 to FP-04,
VOC-02)? No chunk 2 review is on record, so this one also rules on chunk 2's regulatory
scope request flow (four eyes, step-up, audit per term) and the library vocabulary writes.
HARDENING H16 landed before this review (ADR 0058, D-83), so it is reviewed as built: do its
app-role proofs cover every `ProposalKind` and every watch write module after the wave 2
and 3 merge?

## Standard

The same as the chunk 1 and chunk 6 reviews: OWASP ASVS 5.0.0 chapters V2 (validation),
V4 (API), V8 (authorization), V14 (data protection) and V16 (logging), read against the
product invariants in CLAUDE.md section 5, D-30, D-36, D-64, D-65, D-83 and D-87.

## Method

1. Base: `claude/r1-int-w23-done` (main plus every wave 2 and 3 package, integrated).
2. Read `apps/library/` (`api.py`, `reading.py`, `logic.py`, `models.py`, `schemas.py`,
   migrations 0008 and 0009, `seeds/`, `testing.py`), `apps/proposals/standards.py` and
   `apply.py`, `apps/taxonomy/` (`api.py`, `http.py`, `footprint_logic.py`,
   `markets_logic.py`, `library_lists_logic.py`, `tenant_lists_logic.py`, `terms_logic.py`,
   `repoint.py`, `registry.py`, `matching.py`, `seeds/`, migrations 0001 to 0007),
   `apps/watch/write.py`, `apps/shared/tenancy.py`, `migration_helpers.py`, shared 0008,
   search 0003, the `e2e_follow_standard` command and ADR 0058, and on the frontend every
   component that renders a source link.
3. Read each area's tests against the code, then ran the guard suites with the library,
   taxonomy and proposals suites as `cw_app` where the suites do.
4. Wrote a failing test for every finding fixed here before the fix (each one red on the
   base, named below), then re-ran the gates.

## Verdict per area

| Area | Verdict | Evidence |
|---|---|---|
| Instrument, provision and obligation reads, record sources | **Holds.** Every read calls `require_library_read` (a person's `library.read` or a key's `library:read`); tenancy is active before any read; a library answer joins tenant data only through the caller's own scope and watched markets, and applicability and compliance are never joined in (R2); `PageQuery` bounds the page to 1..100; ordering is fixed on `stable_key`; a record the caller may not see answers the same 404 as one that never existed. The lookup a proposal targets did not refuse a bank's own private obligation (L10, **fixed**). | `tests_reading.ObligationListPerformance`, `InstrumentListTests` (query counts pinned), `PrivateObligationIsolation`, `PrivateInstrumentIsolation`, `ProvisionTreeCitationIsolation`, `RecordSourcesTests`, `test_a_person_needs_library_read_and_a_key_needs_library_read_scope`; `tests_route_permissions`. |
| The standard level kind and the provision trigger | **Holds, one race open (L2).** `cw_provision_not_under_standard` and the regime-required triggers run as the writer, not SECURITY DEFINER, fail closed on an instrument the writer cannot see, and the app role cannot disable them; the standards check runs at proposal creation, correction and apply; a trigger's text never reaches a caller (`apply` maps it to `invalid_transition`). | `tests_library.StandardsAndRegimes.test_the_database_refuses_*`, `test_no_zone_writes_a_provision_under_an_instrument_it_cannot_see`, `proposals/tests_kinds.py`, `proposals/tests_scenarios.py` (`provision_not_under_standard`). |
| The opt-in rule and its SQL twin | **Holds.** Python and SQL agree on every combination, with the opt-in flag as seeded and cleared; `taxonomy_in_footprint` is SECURITY INVOKER, so row-level security applies inside it. | `tests_matching.SqlMirrorsPython.test_every_combination_agrees`, `OptInMirror.test_every_combination_agrees_with_the_flag_as_seeded` and `_cleared`. |
| The E2E-only standard | **Holds.** `e2e_follow_standard` writes the scope directly, which is acceptable only because `refuse_when_deployed` stops it wherever `RAILWAY_ENVIRONMENT_NAME` is set. The licensed-text empty state holds because no provision can exist under a standard. | `test_the_standard_toggle_refuses_a_deployed_environment`. |
| The jurisdiction mirror and its derivation | **Holds for terms; the dimension row is outside the rule (L5).** The mirror is written by the seed alone, which stops on a hand-written term under a mirrored key; mirrored terms are refused at proposal creation, at apply and when a change is tagged; a record's jurisdiction is derived at read time from library rows only, so a bank influences nothing but its own four-eyes scope and watched markets. | `tests_scenarios.test_fp_s12`, `tests_vocabulary.JurisdictionTermMirror`, `tests_reading.JurisdictionDerivationTests`, `JurisdictionReach`, `test_international_is_seeded_for_standards_bodies_and_never_mirrored_as_a_market`. |
| Markets watch and unwatch, privacy | **Holds; a double audit row under a race (L6).** A direct write under `footprint.request` with no step-up and no second person, as D-30 and FP-04 rule; `watched_market` is a tenant table under forced RLS, unique per market; the audit row and the logs carry the market key only; nothing aggregates `watched_market` across banks, so no bank learns what another watches. | `test_fp_s10`, `test_fp_s11`, `test_fp_s14` (logs and Sentry), `test_two_tenants_watch_the_same_market`, `test_a_tenant_watches_a_market_once`; `tests_rls`. |
| The watched views of the inventory and the feed | **Holds; one bank proven (L8).** The filter is server side, by `tenant_id` and under RLS (`library/reading.py`, `watch/reading.py`). | `test_fp_s13`, `test_fp_s15`. |
| Vocabulary usage and merge re-pointing | **Fences hold; the history is complete since M2's fix.** A tenant merge needs `vocab.manage` and is fenced by `tenant_id` and RLS; a library merge is only ever a proposal, and `library_links` refuses to move outside a dry run; the approval moves inventory rows through `apply` and watch rows through the watch door (D-87); system rows are refused; the source row is retired, never deleted, so past versions and audit rows still resolve; library usage counts read library tables only. | `test_voc_s5`, `test_a_library_list_moves_nothing_outside_an_approved_merge`, `test_the_watch_doors_re_point_writes_watch_tables_and_no_inventory_table`, `test_urgency_counts_the_librarys_suggestions_and_never_a_banks_case`. |
| Tenant vocabulary writes | **Did not hold under concurrency; fixed (M1).** Permission, `record()` and rollback on refusal held; `If-Match` did not. | Below. |
| Library vocabulary writes (chunk 2) | **Holds.** Every create, relabel, retire, restore and merge on a library list answers 202 with a proposal; `terms_logic` writes nothing; an agent's key reads with `library:read` and never writes; a platform session reads library lists and no tenant list. | `tests_vocabulary.RejectionReasons.test_a_write_is_a_proposal_and_a_new_reason_leaves_the_contract_as_it_was`, `test_an_agent_reads_with_library_read_and_never_writes`, `test_a_platform_session_reads_library_lists_and_no_tenant_list`. |
| Chunk 2: the regulatory scope request flow | **Holds, with three validation gaps (L1 open, L11 and L12 fixed).** Four eyes: logic refuses the requester on approve and reject, and the check constraint `footprint_change_request_four_eyes` refuses it in the database, compared by user id, so a second session or membership is the same person; every scope route takes a person's session only, so no key requests or approves. Step-up: approval requires a fresh passkey assertion (`STEP_UP_FRESHNESS_MINUTES`, env override); a request, a rejection and a withdrawal change no scope and take none. Audit per term: one `record()` and one history row per term that actually changed, each naming the request, in the approval's transaction. One decision per request under a row lock; one waiting request per organisation by a partial unique index; another bank's request answers 404; the preview counts only what the organisation may see. | `test_fp_s2`, `test_fp_s3` (the route and the raw constraint), `test_fp_s6`, `tests_footprint.FootprintRaces`, `PreviewIsolation`, `tests_four_eyes.test_every_four_eyes_table_has_its_check_constraint`, `tests_rls`. |
| H16 as built (ADR 0058, D-83) | **Holds.** Every library-zone table, `search_chunk`, the eval tables (search 0003, door `eval`) and the three reference tables carry the trigger with the doors they accept, compared in both directions against `pg_trigger`; the census of proposal kinds is derived from `ProposalKind` (12 kinds, all filed and approved as cw_app, a vocabulary merge among them proving `watch/write.repoint`); the watch census compares the modules proven against `WATCH_WRITE_ALLOWLIST`, and the fence's AST guard catches a new watch module first; only `tenancy.py` sets `cw.library_door`; the seed door stays in the seed directories; no raw SQL, COPY or TRUNCATE reaches a library table and cw_app holds no TRUNCATE grant. The proofs are per module, not per function (L7). | `tests_library_db_guard` (16 tests, among them `test_every_library_zone_table_carries_the_trigger_with_the_doors_it_accepts`, `test_every_proposal_kind_is_approved_through_the_real_path_as_the_app_role`, `test_every_watch_step_writes_through_its_own_entry_point_as_the_app_role`, `test_a_write_that_slips_past_the_python_fence_is_refused_by_the_database`); `tests_library_fence.test_each_door_is_named_by_its_one_writer_and_by_no_other`, `test_the_seed_door_named_or_taken_by_default_is_opened_by_the_reference_seeds_alone`. |
| Raw SQL and injection | **Holds.** The only interpolated SQL interpolates constants (`matching.SQL_FUNCTION`, migration texts) and binds every value. | Read. |

## Findings

Severity: critical / high / medium / low / info. Status: fixed / handed on (named task) /
open (HARDENING row) / accepted.

| # | Sev. | Where | Finding | Status |
|---|---|---|---|---|
| M1 | medium | `taxonomy/tenant_lists_logic.py` `patch_row`, `retire`, `restore`, `merge` | A write read its row without a lock, compared the `If-Match` version in Python and saved `version + 1`. Two admins editing one value at once both passed, and the second overwrote the first: `If-Match` did not do its job (playbook 4.3). Two retirements at once both wrote an audit row. | **Fixed.** `row_for_write()` locks the rows a write changes (`FOR UPDATE` on the bare rows, in key order, before the grouped read with its usage count), so the second writer reads what the first committed and gets `stale_write` or `invalid_transition`. Test: `tests_footprint.TenantListRaces` (two edits at once, two retirements at once, each on two cw_app connections), red on the base with `('landed', 'landed')`. |
| M2 | medium | `proposals/apply.py` `_repoint_rows`, `watch/write.py` `repoint`, `taxonomy/repoint.py` | A merge moves current link rows in place and deletes twins, and its audit row keeps a count per table, so which records carried the merged value and which duplicate links went cannot be rebuilt from the log. Past versions keep the source value and the source row stays retired, so nothing a version points at is lost. | **Fixed** in named fix task `merge-moved-ids` (HARDENING H23). The re-point answers, per table, the ids moved and the ids of the twins dropped, and the `vocabulary.merged` audit row (library and tenant) carries them as `rows` in the same transaction, ids only; the rows are locked as their ids are read and exactly those rows are written, so the merge does to the data what it did before. Tests: `tests_apply.LibraryMergeRepoints` and `tests_scenarios.test_voc_s5`, red on the base. |
| L1 | low | `taxonomy/schemas.py` `FootprintRequestBody` | No cap on the number of terms a scope change names or on its note. | Open, H24. |
| L2 | low | library 0008 `cw_provision_not_under_standard` | Reads the instrument's level unlocked; a provision insert and a level merge committed together can each pass. | Open, H25. |
| L3 | low | seven frontend components | Source links render without a scheme check; React 19 blocks `javascript:`, so nothing runs today. | Open, H26. |
| L4 | low | `library/schemas.py` inventory filters | String filters without a length limit (bound parameters, no injection). | Open, H27. |
| L5 | low | `taxonomy/library_lists_logic.py`, `registry.py`, `apply.py` | The jurisdiction dimension row is outside the mirror rule; a dimension merge moves none of its terms; either merge accepts a retired target. | Open, H28. |
| L6 | low | `taxonomy/markets_logic.py` `unwatch` | Two concurrent unwatches both write an audit row. | Open, H29. |
| L7 | low | `shared/tests_library_db_guard.py` | The H16 proofs are per module, not per function, and the shared-row census exempts any model with a `tenant` field. | Open, H30. |
| L8 | low | the watched views | Proven for one bank only. | Open, H31. |
| L9 | low | `taxonomy/repoint.py`, `tenant_lists_logic.list_of_lists` | Query counts that grow with the data. | Open, H32. |
| L10 | low | `library/reading.py` `active_obligation` | The lookup a proposal targets found the proposing bank's own private obligation (visible to it under RLS); apply then refused it in the platform's zone, so no library row was written, but the proposal reached the queue. | **Fixed.** Filtered by `owner_tenant__isnull=True`. Test: `tests_reading.PrivateObligationIsolation.test_a_library_proposal_never_targets_the_proposing_banks_own_private_obligation`, as cw_app, red on the base. |
| L11 | low | `taxonomy/footprint_logic.py` `_validate_change` | A scope change naming one term twice passed validation and hit `footprint_change_add_unique`: a 500 on untrusted input (the dry run accepted it silently). | **Fixed.** 422 `validation_error`, before anything is written. Test: `tests_vocabulary.VocabularyEdges.test_a_footprint_change_naming_a_term_twice_is_refused_before_anything_is_written` (dry run and create, adds and removes). |
| L12 | low | `taxonomy/footprint_logic.py` `approve` | An approval switched on a term retired while the request waited: the terms were checked only when the request was made. | **Fixed.** 409 `stale_write`, and the request keeps waiting. Test: `VocabularyEdges.test_an_approval_never_switches_on_a_term_retired_while_the_request_waited`. The two operations' error lists say so. |
| I1 | info | `taxonomy/migrations/0006_opt_in_footprint.py`, library 0008 | The SQL functions set no `search_path`; they run as the caller and cw_app holds only USAGE on `public`. | Accepted; worth adding with the next migration that replaces them. |
| I2 | info | `library/reading.py` record sources | A version proposal's source `url` may be a provision stable key; no screen reads the route today. | Accepted, noted. |
| I3 | info | `taxonomy/footprint_logic.py` | `If-Match` is optional on a decision; the row lock still makes one decision, so this is a gap against the convention, not a race. The stored preview is recounted at approval rather than being the one the approver saw. | Accepted. |
| I4 | info | `shared/permissions.py` | A step-up authorises any step-up action in its freshness window (ID-06, as designed); no general guard requires every approval route to carry `@requires_step_up` (the scope approval's is pinned by `test_fp_s2`). | Accepted. |
| I5 | info | ADR 0058 | Code running as cw_app may set `cw.library_door` itself; the lint and the AST guards hold that line, as ADR 0058 states. | Accepted (D-83). |

## H16

Built and reviewed as built: nothing waits and no chunk 14 cut is needed. The proofs cover
all twelve `ProposalKind` members and every module allowed to open the watch door after the
wave 2 and 3 merge (`registration`, `curation`, `sources`, `so_what_draft`, `write`); the
per-function refinement is H30.

## Gates run

Backend: `apps.shared.tests_rls`, `tests_tenant_isolation`, `tests_library_fence`,
`tests_library_db_guard`, `tests_route_permissions`, `tests_audit_on_write`,
`tests_four_eyes` with `apps.library`, `apps.taxonomy` and `apps.proposals`; ruff; mypy;
`compliance_check.py --all`; `requirements_coverage.py`; `api_docs_gate.py` (0 outside the
ledger, 0 stale); `contract_drift.py` (0 unexplained). E2E: the regulatory scope and
vocabulary journeys (FP-S, VOC-S). Then `prepush.sh --quick`.
