# Security review: chunk 9, the case workflow (2026-09-27)

Package `security-review-c9`, wave 6 of the R2 build (NFR-01, CAS-05, CAS-06).

## Question

Do the chunk 9 surfaces hold the product invariants of CLAUDE.md section 5 and PRD CAS-01
to CAS-08? The surfaces are the case moves (triage, dismissal, restore, the one-person
close, assessment, sign-off request, approval and send-back), actions, evidence and its
scan, case participants, the owner team and a member's removal moving case work, cases
on My work and case deadlines on the roadmap, together with their screens. The
invariants are: two zones, the library fence, four eyes with a passkey step-up, soft
removal only, one audit row per write and download, and no tenant content in logs.

## Standard

The earlier chunk reviews used OWASP ASVS 5.0.0, chapters V4 (API), V5 (files), V8
(authorization), V14 (data protection) and V16 (logging). This review reads them against
CLAUDE.md section 5, `docs/plans/briefs/R2_CROSS_CUTTING.md`, `backend/apps/cases/app.md`,
D-92 and the package brief. The brief asks for evidence (any download before a clean scan,
a server-measured hash and size, no filename in logs, the storage key, infected bytes), four
eyes and step-up (every path by which a requester could sign off; the one-person close paths;
no third door into closed), soft removal of actions and evidence, tenancy on every route, the
library fence across sign-off, permissions, one audit row per write and download, and
transitions only through `state.py`.

## Method

1. Merged the six wave 5 branches the package depends on into `origin/main`, and resolved
   their overlaps. That required two small fixes to merged code: the sign-off answer now
   names the owner team, and the organisation budget's business-unit factory was renamed.
2. Read every production module under `backend/apps/cases/`: `api.py`, `state.py`, `logic.py`,
   `responses.py`, `triage.py`, `assessment.py`, `actions.py`, `evidence.py`, `tasks.py`,
   `signoff.py`, `case_file.py`, `so_what.py`, `links.py`, `creation.py`, `matching.py`,
   `models.py` and the five migrations. Also read the modules they lean on:
   `apps/collab/participants.py`, `apps/tenants/reassignment.py`,
   `apps/home/{my_work,roadmap}.py`, `apps/shared/{audit,storage,permissions,routes}.py`,
   `apps/shared/adapters/scanner.py`, the upload and Sentry settings, and on the frontend
   `components/cases/EvidencePanel.tsx`.
3. Three read-only passes ran in parallel, one per area (evidence; four eyes and the close
   paths; tenancy, permissions and audit). Each passed its claims, with `file:line`, to one
   reviewer, who checked the findings and ranked them.
4. Wrote a failing test for each finding before fixing it, and proved it red on the code
   before the fix.
5. Ran the guard suites and the suites of every app touched, then the gates the standing
   rules list.

## Verdict per area

| Area | Verdict | Evidence |
|---|---|---|
| Bytes before a clean scan | **Holds.** The download refuses a non-file (404), `pending` (409) and anything but `clean` (422) before storage is read. Removed evidence is 404. A scan verdict is final, and the task locks the row before writing it. The case file prints name, hash, URL and state, never bytes. | `tests_evidence.test_a_pending_file_is_409_and_writes_no_audit_row`, `test_an_infected_file_loses_its_bytes_and_keeps_its_row_and_hash`, `test_a_failed_scan_is_retried_then_stays_error_and_cannot_be_downloaded` |
| Hash and size | **Holds.** Both are measured from the bytes read. The form has no hash or size field. | `test_a_hash_and_a_size_the_client_claims_are_ignored_for_the_servers_own` |
| No filename in logs, audit, outbox or Sentry | **Holds.** Audit values carry ids, kind, hash, size and type, and the subject title is the library change's title. Sentry drops bodies and locals. Validation errors never echo input. | `test_upload_scan_and_download_log_no_filename_path_or_byte`, `test_attaching_writes_one_audit_row_with_the_hash_and_never_the_name` |
| Storage key and download headers | **Holds.** The key is `{tenant}/cases/{case}/evidence/{uuid}`, and local storage refuses keys outside its root. The saved name drops control and format characters and ends in the checked type's extension. The download is sent as `attachment` with `nosniff` and `no-store`. Only eight types are stored, and HTML or SVG disguised as text is refused. | `test_the_storage_key_is_the_tenant_the_case_and_a_random_part_never_the_name`, `test_the_saved_name_ends_in_the_checked_type_and_hides_nothing`, `test_a_stored_type_outside_the_allow_list_is_never_served_as_itself` |
| Infected bytes | **Holds, with L2.** The bytes are deleted once the verdict commits and are never served. | `test_an_infected_file_loses_its_bytes_and_keeps_its_row_and_hash` |
| The requester never signs off | **Holds.** The `signoff → closed` guard needs a requester and a different actor. The CHECK `change_case_four_eyes` fails on a missing requester as well as on the same person. Reassignment changes only the owner. Every case route is session-only, so no key or agent reaches it. Every move locks the case and checks `If-Match`. | `tests_signoff.test_the_requester_is_refused_before_anything_is_written`, `test_the_check_refuses_the_requester_as_approver_on_a_direct_write`, `shared/tests_four_eyes`, `tests_scenarios.test_cas_s9` |
| Step-up on approval | **Holds.** `approveSignoff` carries `@requires_step_up`. The assertion is bound to the caller's session, and its id is on the audit row. D-92 puts no step-up on the one-person close or the restore, and there is none. | `tests_signoff.test_a_second_person_closes_it_and_the_audit_row_names_the_assertion`, `test_cas_s10` |
| One-person close | **Holds.** Closing without action needs `cases.work`. `applies = no` closes only for a holder of `cases.work`, checked in logic before any write (403 naming it). A contributor cannot close. | `tests_assessment.test_applies_no_without_cases_work_is_403_naming_it_and_changes_nothing`, `test_cas_s4` |
| A signed-off close is final | **Holds, with L5.** `closed → new` needs a close reason of kind `no_action` or `not_applicable`. Sign-off stores the system `signed_off` row, which no merge can re-point. | `tests_close_paths.test_a_signed_off_close_stays_final` |
| No third door into closed | **Holds.** Only sign-off approval, the close without action (from `assigned` or `assessing`) and `applies = no` (from `assessing`) reach `closed`. Nothing else writes the category outside seeds and test helpers. | `tests_close_paths.test_the_only_edges_into_closed_are_the_one_person_close_and_sign_off` |
| Transitions only in `state.py` | **Holds.** The one production write of `change_case.status` is `logic.transition()`, after `state.check_transition()`. | `tests_state` |
| What is signed off is what was requested | **Did not hold; fixed** (M1). | Below |
| Soft removal | **Holds** for actions and evidence: both the model and queryset deletes raise, and removal sets `removed_at` only. See L1 and L7 for database-level and participant gaps. | `tests_evidence_remove.test_a_hard_delete_is_impossible`, `test_removal_sets_removed_at_only_and_writes_one_audit_row` |
| Tenancy on every route | **Holds.** Every loader filters by the bank as well as relying on row-level security, and another bank's case, action, evidence or participant id answers 404 with no audit row. See L6 for the isolation list's coverage. | `tests_contract.test_another_banks_case_action_and_evidence_are_404_before_the_stub`, `tests_actions.test_another_banks_action_is_404_on_every_write`, `tests_evidence.test_another_banks_evidence_is_404_everywhere_and_leaves_no_audit_row`, `shared/tests_scenarios` isolation guard |
| Permissions | **Holds.** Every route names a permission constant (read, contribute, work, triage, sign-off). Participant removal is the one logic gate, because leaving needs none. No role names appear. | `tests_contract.test_a_session_without_the_permission_is_403_naming_it`, `shared/tests_route_permissions` |
| One audit row per write and download | **Holds, with L9 fixed.** Every write and every download writes exactly one row through `record()` in the request's transaction, and refusals write none. | `tests_evidence.test_a_clean_file_streams_as_an_attachment_of_its_type_with_one_audit_row_per_download`, the scenario client's audit check |
| Library fence across sign-off | **Holds.** Sign-off writes the case, its ledger, audit, outbox and notifications only. | `tests_signoff.test_a_sign_off_moves_no_library_or_register_row`, `shared/tests_library_fence` |
| My work and the roadmap | **Holds.** Case rows need `cases.read`, and a case reached through a register link also needs `register.read`. The department view filters and never grants. Only the change's library title is shown. | `home/tests_my_work_cases`, `home/tests_roadmap_cases` |

## Findings fixed in this package

**M1 (medium): evidence could change while a case waited for sign-off.** A sign-off
request needs one clean piece of evidence, but removal refused only a closed or dismissed
case and took no lock on the case. Someone holding `cases.work` could therefore remove the
only file after the request, or at the same moment as it, and the second person then signed
off a case with no live evidence. Attaching was also open, so what was signed off could
differ from what was requested.

- **Fix:** attaching or removing evidence while the case is in `signoff` now answers 409
  `evidence_locked`, just as the actions answer `actions_locked`. A removal locks the case
  row first and then reads the evidence again under that lock, so it queues behind a
  sign-off request, and two removals racing each other write one removal and one audit
  row.
- **What did not change:** the state machine's guards. The screen already showed evidence
  as read-only in that state.
- **Decision:** this takes option (a) of the `c9-signoff` item in `docs/TODO_FOR_alex.md`.
- **Test:** `tests_evidence_remove.test_evidence_is_locked_while_the_case_waits_for_sign_off`,
  red before the fix (204 where 409 was expected).

**L9 (low, fixed): an action's audit row named the title a person typed.** The actions
module's own rule m keeps typed text out of audit rows, and its values held to it, but the
subject title, which the audit log lists, was the action's title. It is now the change's
title.

- **Test:** `tests_actions.test_the_first_action_moves_the_case_to_implementing_and_the_owner_defaults`,
  red before the fix.
- **Same fix, no test of its own:** the `applies = no` close looked up the bank's
  `not_applicable` reason under row-level security alone. It now also filters by the bank,
  like every other loader.

## Findings left as HARDENING rows

All are low, and each names the package that fixes it:

| Row | Finding |
|---|---|
| H66 | L1: the database allows a hard delete or an in-place rewrite of an evidence row |
| H67 | L2: nothing retries a failed delete of infected bytes, and bytes of `error` scans are never cleaned up |
| H68 | L3: the evidence download is read into memory, not streamed |
| H69 | L4: the approver need not differ from the case's owner (a question in `TODO_FOR_alex.md`) |
| H70 | L5: the restore guard reads the close reason's kind alone |
| H71 | L6: two body-less case routes are missing from the isolation list, whose own check reads `/tenant/` paths only |
| H72 | L7: a `Participant` queryset delete is not refused |
| H73 | L8: a member's removal can pass work to a suspended person, and a reassigned action's audit row names its typed title |

Already logged by `c9-evidence`, and not repeated: H49 (mock scanner in a deployed
environment), H50 (no body cap before spooling) and H51 (a failed scan is not re-queued).

## Informational

- clamd's default `StreamMaxLength` equals `EVIDENCE_MAX_BYTES` (25 MiB). A file near the
  cap is marked `error` and is never downloadable. That fails safe, but the deployed
  clamd should allow more than the upload cap.
- A member's removal hard-deletes `team_member` rows. That table is an association, not
  a record, and the removal is audited.

## Result

Nothing medium or above remains open in the chunk 9 case workflow.
