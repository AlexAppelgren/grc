# Security review: chunk 4, the proposal door, four eyes, the agent approver and the problem-report tail (2026-09-23)

Package `security-review-c4`, wave 4 of the R1 build. It covers CHUNK4 T15 (the door, four eyes,
audit and tenancy, over everything chunk 4 built since, the independent agent included) and T22
(the problem-report tail: T16, T18, T21). Reviewed on `origin/claude/r1-int-w23-done` merged with
`origin/claude/r1w4-vocab-agent-confirm-done`, the package that lifted D-79's interim refusal on
Alex's answer. So the rule is reviewed as built: agents may confirm vocabulary and term proposals,
and those records carry machine-confirmed provenance.

## Question

Do chunk 4's surfaces hold the CLAUDE.md section 5 invariants and PRD AC-PRO1, AC-PRO2, AC-AUD1,
AC-NFR1 and AUD-03? The surfaces are the proposal door and its eleven kinds, four eyes with a
person or an independent agent as the second principal, the D-79 rule as lifted, the source and
standards checks, the library fence, step-up, the `proposals:review` scope, agent decision
logging, the tenant's own proposal list, the audit read, `GET /library-updates`,
`POST /me/visit`, console tenant creation, `bootstrap_platform --role` and a bank's problem
reports. The invariants in scope:

- Proposals are the only door into the library.
- The approver is a second, independent principal.
- Two zones.
- Nothing overwritten.
- Audit on every write.
- AI output labelled until a person confirms it.
- Tenant content never where another bank or the platform can read it.

## Standard

The same as the chunk 1 and chunk 6 reviews: OWASP ASVS 5.0.0 chapters V4 (API), V8
(authorization), V14 (data protection) and V16 (logging), read against CLAUDE.md section 5,
D-35, D-36, D-50, D-62, D-79, D-80, D-83 and ADRs 0054 and 0058.

## Method

1. Read `CLAUDE.md`, `docs/CONVENTIONS.md`, the `app.md` of proposals, governance, tenants and
   identity, the CHUNK4 T15 and T22 task text, and the decisions and ADRs above.
2. Merged the lifted rule. The conflict in `apps/proposals` was resolved keeping both sides:
   - The integrated waves' new kinds (`new_instrument`, `new_obligation`, `new_provision`,
     `new_provision_version`) are kept.
   - `AGENT_CONFIRMABLE_KINDS` is kept, and those four kinds stay outside it.
3. Read every production file of `apps/proposals` (`logic.py`, `apply.py`, `standards.py`,
   `api.py`, `reading.py`, `updates.py`, the models and migrations), the problem-report
   modules (`library/reports.py`, `governance/problem_reports_logic.py` and the routes), and
   the pieces they lean on:
   - `shared/tenancy.py` (`library_write`, `library_door`);
   - `shared/migration_helpers.py` (`rls_operations`, `split_policy_operations`, the door
     trigger);
   - `identity/api_keys_logic.py`, `agents/runs.py`, `governance/logic.py` (the audit row rule)
     and `identity/me_logic.py`;
   - `tenants/logic.py` and `bootstrap_platform`;
   - on the frontend, the record screens' problem-report section and the console shell.
4. Traced the D-79 lift through `apply.py` against each vocabulary and term kind, and
   `git show 2492f80` and the two lift commits against the fence's allowlists.
5. Before and after each fix, ran the proposals, governance, tenants, identity, shared,
   taxonomy and library suites. Each fix was written test-first, and each new test was seen
   red without its fix. Then ran ruff, mypy, migration drift, `migrate_from_zero` and the
   remaining gates in the package report.

## Verdict per area

### T15: the door, four eyes, audit and tenancy

#### Four eyes, the widened agent clauses, corrections, the new lock

**Verdict: holds.** The approver is not the proposer as the principal model defines it: a
different definition and key. Whether that model is enough is M5 below.

**How it holds.**
- **The constraint.** `proposal_four_eyes` (proposals 0003) refuses:
  - the same user;
  - the same key;
  - the same agent definition;
  - a reviewing key that names no agent.
- **The logic.** `logic._decidable` answers the same rules first, with 409
  `four_eyes_violation`, under `select_for_update` on the proposal row. So two decisions cannot
  both land.
- **Row locks.** The obligation, the instrument and the provision rows are locked before a
  version is numbered or a conformance obligation is counted.
- **Corrections.** A correction is recorded as the reviewer's: `corrected_by`, or the reviewing
  agent read through `reviewed_by_agent`.

**Evidence.**
- `tests_scenarios.test_pro_s5` and `test_pro_s14`: the same key, a sibling key of one agent,
  an unbound key on all four routes, and a direct SQL update per clause.
- `tests_decide.test_the_same_principal_twice_is_still_refused_on_a_vocabulary_or_term_proposal`
- `ProposalDecisionRaces.test_an_approval_and_a_rejection_at_once_land_one_decision`
- `ProposalDecisionRaces.test_two_approvals_at_once_apply_once`
- `ObligationVersionRaces.test_two_approvals_on_one_obligation_at_once_add_two_versions`

#### D-79 as lifted: agents confirm vocabulary and term kinds

**Verdict: did not hold; fixed (M3).**

**What held.**
- `AGENT_CONFIRMABLE_KINDS` is the obligation version, every `vocabulary_*` kind and both
  `term_*` kinds. Any other kind answers an agent 409 `person_review_required` before anything
  is written or logged.
- Every label an agent writes is stored machine-made, the original included.
- A person's approval clears the mark only on the labels it writes.
- `_restamp` keeps the agents named until a person has confirmed all of their wording.
- Retire, restore, merge and a sort order leave the stamp.
- An agent's correction cannot move `originalLanguage` (422).
- The reads name `verifiedOrigin`, `confirmedByAgent` and `proposedByAgent`.

**What did not hold.** A relabel that changed only a row's own columns (`extra`) kept the old
stamp, and its audit row held only labels.

**Evidence.**
- `tests_provenance.ListAndTermProvenance`: 10 tests, including the new
  `test_a_column_an_agent_changed_names_the_agents_and_its_audit_row_holds_the_values`.
- `tests_decide.test_an_independent_agent_approves_every_vocabulary_and_term_kind_and_the_rows_say_a_machine_did`
- `test_pro_s13`
- `tests_library_db_guard.test_an_independent_agent_approves_every_vocabulary_and_term_kind_as_the_app_role`

**The kinds still closed to agents.** `new_instrument`, `new_obligation`, `new_provision` and
`new_provision_version` stamp the same provenance, yet stay closed to an agent. Only
`new_provision` is proven refused (`tests_kinds.test_an_agent_cannot_approve_a_provision_yet`).
That is L15, and Alex's question in `TODO_FOR_alex.md`.

#### Source checks at creation and at approval

**Verdict: holds, with gaps at the boundary (L2, L3, L5).**

**How it holds.**
- `check_field_sources` runs at creation and again over a correction.
- Each source is an https link or a provision the library holds, capped at
  `PROPOSAL_SOURCE_MAX_CHARS`.
- A correction introducing an unsourced field answers 422 `source_missing`.
- Payloads forbid unknown fields.
- A correction cannot move the kind, the target or the key.

**Evidence.**
- `tests_create.test_every_changed_field_needs_a_source`
- `test_a_source_is_a_link_or_a_provision_the_library_holds` (`javascript:`, `http:`, "n/a")
- `test_a_source_longer_than_the_cap_is_refused`
- `tests_kinds.test_a_correction_adding_an_unsourced_fact_is_refused`

#### The standards checks on every obligation kind

**Verdict: did not hold; fixed (M1, M4).**

**What held.** `standards.check_payload` runs at creation and over a correction, and
`standards.check` runs at apply for `new_obligation` (under the instrument's lock),
`new_obligation_version`, `new_provision` and `new_provision_version`.

**What did not hold.**
- A vocabulary merge on `instrument_level` moved instruments between a law's level and a
  standard's with no check at all (M1).
- D-35's rule that a standard's obligation is labelled by the official reference was not
  enforced (M4).

**Evidence.**
- `tests_kinds.StandardsCheck`: 9 tests, including the new
  `test_a_standards_obligation_is_labelled_by_the_official_reference_alone`.
- `tests_scenarios.test_pro_s10`
- `tests_apply.LibraryMergeRepoints.test_a_merge_across_kinds_of_level_is_refused_when_proposed_and_when_approved`

#### The library fence and its 2492f80 edits

**Verdict: holds.**

**How it holds.**
- 2492f80 widened no allowlist. It let `approveProposal` take a key, gated by `require_reviewer`
  in its body. The step-up assertion it dropped was restored as the `ENFORCE_STEP_UP` call-edge
  assertion.
- The lift commits (3fe9779, 2478880) touch no fence list.
- No `library_write` caller exists outside `proposals/apply.py`, `watch/write.py` and the seed
  directories.
- The database door trigger (D-83) stands behind every library-zone table.
- **Scopes (AC-PRO1).** An agent's key reaches the inventory only through `approveProposal`.
  Otherwise it reaches only the watch door (`changes:write`, `sources:write`, the curation
  confirmation). No key scope names an inventory table.

**Evidence.** `tests_library_fence`:
- `test_library_write_is_called_only_from_allowlisted_modules`
- `test_only_the_approval_the_stamp_and_the_watch_door_reach_a_library_write`
- `test_a_route_reaching_a_library_write_needs_proposals_review_a_step_up_and_a_person`
- `test_each_door_is_named_by_its_one_writer_and_by_no_other`
- `test_the_watch_door_reaches_no_inventory_table_and_no_key_scope_names_one`

`tests_library_db_guard`:
- `test_every_write_outside_a_door_is_refused_on_every_library_table`
- `test_every_proposal_kind_is_approved_through_the_real_path_as_the_app_role`

#### Step-up on approvals, and none for keys

**Verdict: holds.**

**How it holds.**
- A person's approval runs `enforce_step_up`. The assertion id reaches every audit row the
  approval writes.
- A key presents none.
- A person who sends `decision` or `agentRunId` is refused.
- The re-verification stamp is session-only, with `proposals.review` and a step-up.

**Evidence.**
- `tests_decide.test_a_person_approving_without_a_step_up_is_refused_and_nothing_applies`
- `test_a_step_up_older_than_the_window_is_refused_and_nothing_applies`
- `test_pro_s13` (the assertion is null for an agent)
- `identity.tests_scenarios.test_id_s31`

#### The review scope: platform only, and unbound keys

**Verdict: holds as built. What the scope does not tie a key to is M5.**

**How it holds.**
- `proposals:review` is in `PLATFORM_ONLY_SCOPES`.
- A bank key is refused it at creation and stripped of it at resolution.
- The gate refuses any key carrying a tenant.
- A tenant session keeps only `TENANT_PERMISSIONS`.
- An unbound key answers 403 `agent_not_bound`.

**Evidence.**
- `test_id_s31`
- `test_pro_s14`
- `tests_library_fence.test_a_reviewing_key_needs_the_scope_and_never_a_tenant_role_or_key`
- `test_no_tenant_role_and_no_key_holds_proposals_review`

#### Agent decision logging and run ids (D-80)

**Verdict: holds, with L6.**

**How it holds.**
- Every agent decision needs an `AgentDecision` and an open run of the deciding key itself.
- One `agent_review` row is written in the decision's transaction, and the database constraint
  `ai_generation_agent_review_names_its_run` holds it.
- A refused decision logs nothing.
- The audit row names the run and the key prefix.

**Evidence.**
- `test_pro_s13`
- `test_pro_s14`
- `DecidingOutsideARequest.test_a_decision_whose_audit_row_fails_keeps_no_logged_model_call`

#### `proposal_tenant` RLS and `GET /tenant/proposals`

**Verdict: did not hold at the create call's retry; fixed (M2). The list holds.**

**How the list holds.** `proposal_tenant` is a tenant table under enabled and forced row-level
security, with one `tenant_isolation` policy, and is listed in `TENANT_ONLY_TABLES`. The list
reads through it alone.

**What did not hold.** The retry key of `POST /proposals` answered one bank with another's
proposal (M2).

**Evidence.**
- `tests_rls`
- `tests_reading.test_a_bank_lists_its_own_proposals_and_never_another_banks`
- `test_a_bank_filters_its_own_list`
- `test_the_review_routes_stay_the_consoles`
- the new `tests_create.ProposalTenantLink.test_a_retry_key_answers_only_the_proposer_that_sent_it`

#### The audit read's row rule

**Verdict: holds in Python. The database layer is L7, L8 and L9.**

**How it holds.**
- **The rule.** `governance/logic.py` returns the caller's tenant's rows, plus rows with no
  tenant that meet both conditions:
  - a library subject;
  - an agent, a system or a platform-role actor.
- **Rows with no tenant.** No `record(tenant_id=None)` has a tenant member as its actor.
- **Rows with a bank's words.** `proposal.approved`, `proposal.rejected` and `proposal.replayed`
  carry a bank's title and a note. Their subject is `proposal`, so the rule hides them.

**Evidence.**
- `tests_audit_events.test_a_library_change_is_shown_only_when_made_by_an_agent_the_system_or_platform_staff`
- `test_another_tenant_never_sees_proposal_rows_platform_sign_ins_or_code_requests`
- `governance.tests_scenarios.test_aud_s7`
- `tests_hardening.LibraryAuditRowsCarryNoTenantWords`

#### The proposer withheld from the console

**Verdict: holds.**

**How it holds.**
- `logic.row()` nulls `proposedBy` and `proposedByAgent` when `proposed_in_tenant` is set, on
  every console surface.
- `proposer_row` withholds the reviewers from a bank's own retry.
- The `ai_generation` read policy leaves `agent_review` out.

**Evidence.**
- `tests_reading.test_a_proposal_made_inside_a_bank_reaches_the_console_without_its_proposer`
- `test_a_banks_retry_after_the_decision_names_nobody_who_decided_it`
- `tests_agent_review.test_a_bank_reads_the_librarys_draft_and_never_a_decision`

#### `GET /library-updates`

**Verdict: holds today. The owner cut is latent, with INV-07 (I3).**

**How it holds.**
- It lists approved proposals only.
- The footprint cut runs in SQL, with the server's tenant.
- Titles come from the library record or the row's current label, never from the proposal.
- No person is named.
- `PageQuery` bounds the page.

**Evidence.** `tests_updates`:
- `test_a_reader_sees_the_new_version_titled_by_the_library_record`
- `test_a_change_names_the_agents_behind_it_and_never_a_person`
- `test_a_duty_outside_the_footprint_is_hidden_until_the_reader_asks_for_it`
- `test_a_vocabulary_change_one_bank_asked_for_reaches_another_under_the_rows_own_label`
- `test_the_list_is_a_persons_and_needs_the_library_read`

#### `POST /me/visit`

**Verdict: holds, with L10.**

**How it holds.**
- It writes the server's `now()` onto the caller's own membership only, under row-level
  security.
- It writes one `member.visited` audit row in the caller's bank.
- A session with no bank answers 404.
- It needs a bearer header, so it is not open to CSRF.

**Evidence.** `identity/tests_visit.py`, all five tests.

#### Console tenant creation and its slug

**Verdict: holds, with L11 and I4.**

**How it holds.**
- **Permission.** `tenants.manage`.
- **The slug.** The server derives it, never the caller:
  - ASCII only, Nordic letters spelled out, cut to 80 characters;
  - a collision gets `-n`, under a savepoint;
  - it is used in no route, host or path.
- **Activation.** `tenancy.activate(new id)` runs right after the insert, and everything after
  it writes only the new tenant.

**Evidence.** `tests_console_tenants`:
- `test_every_audit_row_the_call_writes_belongs_to_the_new_tenant`
- `test_two_banks_of_the_same_name_created_at_once_are_both_created`
- `test_a_short_name_holds_only_lower_case_letters_digits_and_single_hyphens`
- `test_a_platform_account_cannot_be_a_banks_first_admin`

#### `bootstrap_platform --role`

**Verdict: holds, with I5.**

**How it holds.**
- **What it grants.** Only `platform_admin` (the default) or `library_editor`. A tenant role or
  an unknown key is refused.
- **Who it refuses.** A bank member (read through `identity_lookup()`) is refused before a
  passkey holder is.
- **Audit.** `platform_role.assigned` is written in the same transaction, only for a new grant.

**Evidence.**
- `tests_commands.BootstrapPlatformRole`: six tests.
- `identity.tests_policies`: the passkey refusal.

#### The console shell fires no tenant queries

**Verdict: holds.**

**Evidence.** `frontend/src/components/shell/console.test.tsx` asserts the exact request set:
refresh, `/me` and `/reference/languages`.

### T22: the problem report stays inside the bank

#### The zone

**Verdict: holds, with L12.**

**How it holds.**
- **The policies.** `problem_report` carries exactly `tenant_isolation` (FOR ALL, own zone both
  ways) and `library_rows_visible` (FOR SELECT). There is:
  - no other policy;
  - no library-door trigger;
  - no transaction-local flag.
- **`tenancy.py`.** Untouched by the tail. Its same-day edits are H16's door.
- **The `tests_rls` edit (e8eece7).** It only adds a test, a stricter one. Nothing was removed
  from a list and no allowlist was widened.
- **H15 holds for this table.** A bank cannot write, change, delete or claim a platform row.

**Evidence.**
- `tests_rls.test_problem_report_carries_the_mixed_shape_and_nothing_else`
- `MixedTablesWriteOnlyTheirOwnZone`: four tests.
- `test_every_mixed_table_writes_only_its_own_zone`

#### Cross-zone reads

**Verdict: holds.**

**How it holds.**
- Both reads filter `tenant_id = caller`, on top of row-level security.
- `problems.report` is held by no platform role.
- Keys answer 401.

**Evidence.**
- `tests_problem_reports.test_platform_sessions_and_keys_are_refused`
- `test_another_bank_lists_nothing_and_cannot_close_it`
- `governance.tests_scenarios.test_aud_s5`
- `proposals.tests_scenarios.test_pro_s7`: sweeps every fillable GET route for the report text.

#### The permission split

**Verdict: holds.** `proposals.create` sees the bank's reports and anyone else only their own.
Closing a colleague's report needs `proposals.create`, and the 403 names it.

**Evidence.**
- `test_an_officer_lists_every_report_of_the_bank_and_a_member_only_their_own`
- `test_a_member_without_proposals_create_cannot_close_a_colleagues_report`
- `test_the_reporter_closes_their_own_with_a_note`

#### The close

**Verdict: holds.**

**How it holds.**
- A request transaction.
- `select_for_update`, then the open-status check, then a four-column save.
- A 409 `already_closed` on a second close.
- The audit and outbox rows sit under the tenant and hold no text.
- A check constraint requires the note, the closer and the time.

**Evidence.**
- `test_a_closed_report_cannot_be_closed_again`
- `test_the_close_is_audited_without_the_words`
- `test_a_close_needs_a_closing_status_and_a_note`

#### The record section

**Verdict: holds.**

**How it holds.**
- `RecordProblemReports.tsx` renders only what the server returns, and nothing without
  `problems.report`.
- It is mounted only on the tenant obligation and instrument screens.
- Nothing in the tail reaches the frontend logger, `console` or storage.

**Evidence.** `RecordProblemReports.test.tsx`.

#### What the console can reach

**Verdict: holds.** No route, no screen, no registry entry. The only seed is inside tenant A.

**Evidence.**
- `test_pro_s7`: `/console/problem-reports` answers 404.
- `shell.test.tsx`

#### Filing a report

**Verdict: holds, with L13 and L14.**

**How it holds.**
- The subject is resolved under row-level security, so another bank's private record is the
  same 404 as no record.
- The tenant and the reporter come from the principal.
- The text is capped at `LIBRARY_REPORT_TEXT_MAX_CHARS`.

**Evidence.**
- `library.tests_scenarios.test_inv_s7`
- `test_the_tenant_and_the_reporter_come_from_the_caller`
- `test_cw_app_cannot_file_a_report_for_another_tenant`

## Findings

Severity: critical / high / medium / low / info. Status: fixed / open, with where it gets fixed /
accepted. No critical and no high finding was found.

### M1 (medium): a merge on `instrument_level` crossed the standard line with no check

**Status: fixed**, commit `A list value merges only into another active value of the same kind`.

**Where.** `apply._vocabulary_merge`, and `logic._validate_target` for a merge.

**What happened.** An approved merge re-pointed `Instrument.level` with no standards check. The
database refused only an instrument holding provisions moving *onto* a standard level. The
reproduction takes three proposals, and since D-79's lift the first and the last need no person:

1. A `vocabulary_create` of a level with the kind `standard`, approved by an independent agent.
2. The standard's instrument and its conformance obligation, which a person approves.
3. A `vocabulary_merge` of that level into `eu_guidance`, approved by an agent.

**Effect.**
- The conformance obligation's opt-in term then sat under a non-standard instrument, which
  `standard_term_only_on_standards` exists to refuse.
- `new_provision` under it then passed, which opens the way to licensed clause text (INV-08,
  D-35, D-36).
- The reverse merge also passed: a law's level into `standard` leaves obligations with no
  standard term under a standard.

**Fix.**
- `logic.merge_pair` reads both rows when the merge is proposed (through the vocabulary route
  and through `POST /proposals`) and again at approval.
- A value merges only into another active value of the same kind. Otherwise:
  - the same value twice is 422 `validation_error`;
  - a retired target is 409 `invalid_transition`;
  - two kinds are 409 `invalid_transition`.

**Tests.**
- `LibraryMergeRepoints.test_a_merge_across_kinds_of_level_is_refused_when_proposed_and_when_approved`:
  both directions, at creation and for a proposal filed before the rule.
- `test_a_merge_into_itself_or_into_a_retired_value_is_refused_through_every_door`

Both are red without the fix.

### M2 (medium): the proposal retry key was global, so one bank was answered with another's proposal

**Status: fixed**, commit `A proposal's retry key answers only the proposer that sent it`.

**Where.** `logic.create`, and `Proposal.idempotency_key` (`unique=True`).

**What happened.**
- The replay lookup had no scope. Bank B's officer sending bank A's key and body got 200 with
  bank A's proposal: its id, its status, its `rejectionCode` and its `reviewNote`. When the
  first proposal was the platform's, the answer also named the platform reviewer.
- Any caller could claim a platform agent's predictable key first, and the agent's own filing
  then answered 409 for ever.

**Fix.**
- The lookup is scoped to the proposer (the person or the key).
- The same person in another bank is 409 `idempotency_conflict`, never a replay.
- Proposals 0006 replaces the global unique index with one per person and one per key.
- A key longer than the column is 422.

**Test.** `ProposalTenantLink.test_a_retry_key_answers_only_the_proposer_that_sent_it`, red
without the fix.

### M3 (medium): an agent-approved change to a list row's own columns kept the old stamp

**Status: fixed**, commit `A list row's own columns changed by an approval say who confirmed them`.

**Where.** `apply._vocabulary_relabel`.

**What happened.**
- `_restamp` ran only for labels or a usage note. Two agents could change a list row's own
  columns while the row still read as seeded or person-confirmed (INV-05, D-62). The columns
  include:
  - `term_dimension.restricts_footprint`, which changes how every bank's footprint matches;
  - a level's `binding_default` or `rank`;
  - an urgency's `sla_days`.
- The `vocabulary.updated` audit row held labels only (AUD-01).

**Fix.**
- A change to a row's own columns stamps the row as wording does, under the same rule that keeps
  the agents named.
- The audit row holds the columns before and after.

**Test.**
`ListAndTermProvenance.test_a_column_an_agent_changed_names_the_agents_and_its_audit_row_holds_the_values`,
red without the fix.

### M4 (medium): D-35's rule that `ref_label` equals the official reference was not enforced

**Status: fixed**, commit `A standard's obligation is labelled by its official reference alone`.

**Where.** `standards.check`.

**What happened.** A conformance obligation labelled `A.5.1 Policies for information security`
passed every check and reached the library.

**Fix.** The check takes a new obligation's `ref_label` and refuses any other value under a
standard with 422 `licensed_text`, at creation, over a correction and at apply.

**Test.** `StandardsCheck.test_a_standards_obligation_is_labelled_by_the_official_reference_alone`.
Two fixtures now carry the standard's official reference, as `e2e_standard.json` already did.

### M5 (medium, privileged insider): agent independence is checked by definition and key, never by the person behind them

**Status: open.** Named fix task H23, plus Alex's question in `TODO_FOR_alex.md`.

**Where.** `identity/api_keys_logic.create_agent_key`, `logic._decidable` and `require_reviewer`.

**What happens.**
- **One admin as both agents.** A platform admin holding `agent_definitions.manage` can:
  1. mint a key for `watch-sweeper` with `proposals:write`;
  2. mint a key for `library-confirmer` with `proposals:review`;
  3. file with one key and approve with the other.

  That is two "independent agents" and one person. Since D-14's answer (no editorial staff), this
  is the library's whole second pair of eyes.
- **A person as proposer and reviewer.** A person holding both `library_vocab.manage` and
  `agent_definitions.manage` can propose as themself and approve with a key they minted.
- **What key creation does not check.** It does not check the agent's kind (`review`) or that
  the agent is active, and it allows `proposals:write` and `proposals:review` on one key.

**Why not fixed here.** The invariant as written ("an agent of a different definition and key")
holds, and ADR 0054 chose it. Tightening it changes who may mint review keys, which is Alex's
call.

### Low findings

Each has a row in `docs/plans/briefs/HARDENING.md`.

| # | Where | Finding | HARDENING |
|---|---|---|---|
| L1 | `apply._vocabulary_relabel`, `_vocabulary_active`, `_vocabulary_merge`, `_term_update` | These read the row without `select_for_update` and save the whole row. Two approvals of *different* proposals on one row at once can lose the other's stamp or version bump. For example, a person's relabel overwrites an agent's `agent` stamp while a machine label remains. | H24 |
| L2 | `logic.create` | `sourceUrl` is checked as an https link only for the new-record kinds. On a version, vocabulary or term proposal an `http:` or other scheme is stored, and the console renders it as the proposal's source link. React refuses `javascript:`, but not `http:`. | H25 |
| L3 | proposal payload schemas | Payload texts have no length cap (summaries, titles, labels, usage notes). A label longer than the 200-character column is accepted into the queue and fails at approval with a 500. | H25 |
| L4 | `apply._new_obligation` | A proposal's free-text `sourceLabel` (up to 500 characters) lands on a standard's obligation unchecked. The D-35 links-only rule reads `fieldSources`, not the label. | H25 |
| L5 | `logic.corrected` | A correction keeps the proposer's source even when it changes the sourced value. The precision fields and `originalLanguage` are unsourced. | H25 |
| L6 | `agents/runs.require_open_run_of_key` | The run is read without a lock, so a decision can land in a run another request closes at that moment, and the run's counts miss it. | H26 |
| L7 | `audit_event` read policy | The rule is `tenant_id IS NULL`, so under a bank's session the database returns the platform's `proposal.rejected` rows, which carry another bank's title and note. Only the Python `Q` hides them. | H27 |
| L8 | `governance/logic.py` | Whether a library audit row is shown depends on the actor's platform role *now*. Revoking an editor's role hides every library change they made from every bank's log. | H27 |
| L9 | `tests_hardening.LibraryAuditRowsCarryNoTenantWords` | The H3 guard fingerprints the title only, not `summary`, `before` or `after`. | H27 |
| L10 | `POST /me/visit` | No throttle: every call appends an audit and an outbox row, and each is kept for ten years. | H28 |
| L11 | console tenant creation | The name refuses no control or bidi characters. A newline makes the invitation mail's subject raise `BadHeaderError` in the worker, so the first admin is never invited. | H28 |
| L12 | `library/reports.create_report` | A report with no tenant is refused only by the type hint. The table keeps `library_rows_visible`, so such a row would be read by every bank. No path writes one today. | H29 |
| L13 | `ProblemReportBody` | `versionNumber` has no upper bound, so 2^31 is a 500. A NUL character in a description or a note is a 500 (no NUL guard exists anywhere in the backend). | H29 |
| L14 | problem reports | Filing and closing have no rate limit. The damage stays inside the bank; per-credential limits are ACC-09 (R2). | H29 |
| L15 | `tests_kinds` | Only `new_provision` is proven refused to an agent, and at the logic level. `new_instrument`, `new_obligation` and `new_provision_version` would pass CI if added to `AGENT_CONFIRMABLE_KINDS` by mistake. | H24 |

### Info

- **I1.** The `reverification` door admits an update to any column of `obligation`, not only the
  two stamp columns (ADR 0058's known limit). The door itself is a setting the app role can set.
- **I2.** `proposed_by_agent` is copied from the key only in `api.createProposal`. A future caller
  of `logic.create` that builds a `Proposer` with a key but no agent would store a null agent,
  which the constraint's agent clause passes. Not reachable today; a composite foreign key would
  make the database the word.
- **I3.** `GET /library-updates` and `reading.active_obligation` have no owner-tenant cut. That is
  latent until INV-07 lets a tenant-private record be proposed.
- **I4.** Console tenant creation takes no step-up, by design (T7, playbook 4.2), while CLAUDE.md
  section 5 lists role changes under step-up. Asked in `TODO_FOR_alex.md`.
- **I5.** `bootstrap_platform` audits as `system` and names no operator. Its printed link is
  already in `TODO_FOR_alex.md`.
- **I6.** `GET /tenant/proposals` documents a 404 for a principal in no bank that it cannot
  return.
- **I7.** The console's reject dialog hint (`console.queue.rejectDialog.hint`, en and sv) still
  says a rejection goes back to "the problem report", which D-50 removed.
- **I8.** Every member reads the audit rows of a colleague's report (who reported which record,
  and who closed it) through `audit.read`, although only `proposals.create` lists the report
  itself. The text never appears.
- **I9.** Under an agent's correction a reworded original-language summary is stored not
  machine-made. That matches D-79's wording ("every translated summary"), while a list label's
  original is marked.

## Gates

Run on this branch after the fixes, 2026-09-23. Every gate below was green.

- The backend suites of every app the review read or changed, 1207 tests, OK with 51 skips
  that were there before: `apps.proposals`, `apps.governance`, `apps.tenants`,
  `apps.identity`, `apps.shared`, `apps.taxonomy`, `apps.library` and `apps.agents`.
- Migration drift and `migrate_from_zero`, since proposals 0006 is new.
- ruff and mypy.
- The compliance lint, requirements coverage, the API documentation gate and contract drift.
- Frontend lint (0 errors), typecheck, and the message and copy-drift checks. No frontend file
  changed.
- E2E: 7 of 7 journeys for the scenarios in scope, against the full stack: PRO-S3, PRO-S5,
  PRO-S7, PRO-S13, AUD-S5, ADM-S4 and ADM-S6. PRO-S2, PRO-S14 and AUD-S7 have integration
  tests only.
- `scripts/prepush.sh --quick`, with the OpenAPI artefacts regenerated in the working tree and
  not committed (runbook rule 4).
