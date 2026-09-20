# Chunk 9: tasks

Written 2026-09-20 by the planning workflow (read, plan, parallelism and coverage critiques, revise). Each task runs in its own worktree or cloud session (`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`. The task ids are the `c9-` package ids of `docs/plans/PARALLEL_PLAN.md` section 3.3 plus `f03-T76` and `f03-T77` from `docs/plans/briefs/FEATURES_0_3_TASKS.md`; nothing is renamed or dropped, and the five ids this plan adds are named with their reason under "Changes from `PARALLEL_PLAN.md`".

## Revised 2026-09-20

The chunk 9 plan review blocked the first version. What changed, and which
finding each change closes:

| Change | Closes |
|---|---|
| `c9-close-paths` joins rule 8's security-review list and `c9-security-review`'s depends-on, and carries its own `**Security review:** yes` line. The four-eyes close decision is reviewed before it merges, and the chunk-wide sweep waits for it however late q-case-close is answered | HIGH (the close decision unreviewed) |
| CAS-04 closes `in_progress`, not `built`: ruling 3 leaves the ticket half to `c13-tickets-export`, and `c9-close` names that in the `app.md` status cell and in the `IMPLEMENTATION_STATUS.md` notes | MEDIUM (CAS-04 overstated) |
| The `casesmsg` key orders the seven tasks that rewrite the case message catalogs whole, as CHUNK8's `tenadminmsg` does, and the wave list shows the order where four of them share wave 6 | MEDIUM (catalog collision) |
| `c9-evidence-model` depends on `c9-scanner-adapter`: it uses the `ScanState` kind that task creates and appends to the same `kinds.py` entry | MEDIUM (missing dependency) |
| `c9-reference-members` is resolved to `identity` now rather than at run time, takes the `idapi` key, and has its own row in `PARALLEL_PLAN.md` section 3.3 | MEDIUM (app left open) |
| Rule 14 names the green stopping point of the five tasks at the cap — `c9-case-design`, `c9-case-contract`, `c9-e2e-seed`, `c9-evidence` and `c9-fe-cases-feature` — and `c9-review-fixes` gains an **Owned paths** heading like every other task | LOW (cap, format) |
| The open questions say q-case-close was put to Alex on 2026-09-20 and stays open with Option A recommended; four of the five non-blocking items become defaults taken with the source that settles each, and only the multipart-versus-presigned choice reaches `docs/TODO_FOR_alex.md` | MEDIUM (questions that were not questions) |

## Scope, rules and defaults

Chunk 9 plan: the case workflow from triage to sign-off, with evidence, the case file and participants on cases. `Build_Plan.md` gives the chunk CAS-02 to CAS-08, COL-04 (cases), J-2 and J-3. CAS-01 (case creation) is chunk 5's and is a precondition, not work here. The plan has 33 tasks in 15 waves, about 19 agent-hours of package work plus review.

PRECONDITIONS: WHAT MUST BE ON MAIN BEFORE WAVE 2
- Chunk 5, all of it, through `c5-chunk-close`. Parallel-plan rule 11 holds `c9-case-contract` until that close, because this chunk changes the cases and watch API that chunk 5's journeys test. Named individually: `c5-contract-models-cases` (`ChangeCase` with status, urgency, owner and footprint match), `c5-cases-creation` (CAS-01, the per-tenant case behind every scenario here), `c5-cases-so-what-and-links` (the So what J-2 confirms), `c5-cases-footprint-hooks`, `c5-watch-feed-read` (`GET /changes` and `GET /changes/{changeId}`, which this chunk extends), `c5-seed-watch` (the seeded changes and cases), `c5-fe-change-detail` (the change page every case panel mounts on).
- Chunk 8: `c8-tenants-contract` (`Team`, `OrgUnit`), `c8-ten-teams`, `c8-ten-reassignment` (the open-work list TEN-S5 asserts), `f03-T51` (departments, heads, team membership) and `f03-T53` (the `participant` model), because `change_case.owner_team` and every case participant are composite foreign keys into those tables.
- Chunk 10: `c10-collab-models`, which builds `notify()` on `c5-outbox-cursor`. Triage notifies the owner (CAS-S2) and a sign-off request notifies the approvers; neither invents a second notification path.
- Chunk 6: `c6-today-screen` and `f03-T48`, because J-2 starts on Today and Today's "Decide now" counts the triage queue this chunk fills.
- Chunk 12: `c12-exports-contract` (`ExportJob` and `/exports`), for `c9-case-file-export` only. Parallel-plan ruling 7 puts the job framework there and starts it early.
- PRD 0.3: `f03-T55` (the obligation participant routes and the participant logic `f03-T76` reuses), `f03-T59` and `f03-T62` (the My work service and screen `f03-T77` extends).
- Why none of it can wait: every scenario here starts from a case that chunk 5 created on a change chunk 5 registered, and a screen built against a stub is what parallel-plan rule 3 forbids.

WHAT IT DELIVERS
- CAS-02, triage: `POST /changes/{id}/triage` with urgency and owner, `dismiss` with a reason key from the tenant's reason list, `restore` back to triage, and the audit trail behind all three.
- CAS-03, the impact assessment: `assessment/start` and `PUT /assessment` with applies, why, what must change, an internal deadline and an effort key, under `If-Match` with `stale_write`. Contributor teams are the case's team participants (D-20); `impact_assessment` has no contributors column.
- CAS-04, actions: add, edit, complete, reopen and delete, with an owner and a due date, locked once the case waits for sign-off.
- CAS-05, evidence: file, link or reference, hashed, type- and size-checked, invisible until the malware scan passes, downloaded through a streaming, permission-checked, audited endpoint (D-11), soft-deleted only.
- CAS-06, sign-off: requested only with no open action and at least one piece of evidence, approved only by a second person with a passkey step-up, or sent back.
- CAS-07, the case file: `GET /changes/{id}/case-file` as text that stands alone, and the same content as an export job on chunk 12's framework.
- CAS-08: `allowedTransitions` on every case response, `invalid_transition` on anything else, `stale_write` on a concurrent edit, and a `case_transition` ledger row per move.
- COL-04 on cases (`f03-T76`), the case half of My work (`f03-T77`), J-2 and J-3 as `@smoke`.
- The chunk's own security review, its fix package and its close.

RULINGS WHERE THE SOURCES DISAGREE
1. **A case is addressed by its change.** `docs/inputs/openapi.yaml` puts every workflow route under `/changes/{changeId}/…`, and CAS-01 makes exactly one case per tenant per change, so the change id names the case without ambiguity. Kept as designed: no `/cases/{caseId}` route is built. `PATCH /actions/{actionId}` and `DELETE /evidence/{evidenceId}` keep their own ids, because a child has no change in its path; each loads its case under row-level security and answers 404 across tenants.
2. **`impact_assessment.contributors` is dropped.** `schema.sql` §8 has `contributors text[]`; D-20 and INPUT_DELTAS §1 replace it with the case's team participants. `c9-case-models` builds the table without the column, `AssessmentInput` carries no `contributors`, and `f03-T76` builds the picker as single add and remove calls. CAS-S4 is reworded to the assessment's own fields and its contributor clause stays where it already is, in CAS-S17.
3. **"Send as tickets" is not declared here.** Parallel-plan ruling 6 builds it once, in `c13-tickets-export`. Declaring `POST /changes/{id}/actions/export-tickets` as a 501 stub in chunk 9 would leave a 501 route that `c9-close` must prove absent, so chunk 9 declares nothing: `c13-tickets-export` adds the route itself and therefore needs the `casesapi` key, which section 3.3 does not yet give it. CAS-S6 is reworded without its ticket clause, which is named for INT-S3.
4. **Evidence upload is multipart through the API, not a presigned PUT.** INPUT_DELTAS §4 allows a presigned upload "if the scan and the hash still happen before the file is visible", but a presigned PUT puts the object in the bucket before any check, and `apps/shared/storage.py` has no presign seam. `addEvidence` takes `multipart/form-data` when `kind` is `file`; `EvidenceCreated` loses `uploadUrl`. INPUT_DELTAS row written by `c9-case-contract`.
5. **Evidence download streams.** `DownloadLink` and the presigned download operation are removed (INPUT_DELTAS §4 and §7, D-11). `GET /evidence/{evidenceId}/download` answers the bytes behind `cases.read`, with one `record()` row per download and `Content-Disposition: attachment`.
6. **The workflow policy is chunk 10's.** INPUT_DELTAS §7 parks "reminder, escalation and retention settings" for "the workflow policy (chunk 9)", but section 3.1 renames `c9-workflow-policy-contract` to `c10-workflow-policy`. The later plan wins: chunk 9 builds no policy columns, and `change_case.triage_due_at` (`schema.sql` §13, "from the tenant's triage target, drives escalation") waits for `c10-workflow-policy`. `c9-case-models` corrects the INPUT_DELTAS §7 line.
7. **`GET /reference/members?permission=` becomes a filter, not a route.** Section 3.2 ruling 11 gives `c9-case-contract` a new reference read for the owner and approver pickers. PRD 0.3 already declares `GET /reference/people` (INPUT_DELTAS §1), and two reference reads over the same member rows, one of them unfiltered, is the duplication rule 5 and the simplicity rule forbid. `c9-reference-members` adds the `permission` query parameter to the route that exists. The app is resolved here rather than at run time: **`identity`**, because the filter reads members and their roles the way `build_principal` does, and `GET /reference/permissions` is already served from `identity/api.py`. The task takes the `idapi` key and joins the end of chunk 8's `idapi` chain.
8. **Sub-statuses have no route of their own.** D-13 and CAS-S13 give a tenant sub-statuses inside the fixed categories; `case_sub_status` is already a registered tier-three list with the kind `case_status` (`taxonomy/registry.py`), so chunk 9 adds no vocabulary. `change_case` gains a nullable `sub_status` foreign key, `TriageInput` and `AssessmentInput` gain an optional `subStatus` key, and the guards read only the category.
9. **The close-without-action and "applies = no" paths wait for q-case-close.** They are the one place where a single person can take a regulatory change out of the workflow, which touches four eyes. See "Open questions".
10. **The watch feed's workflow tabs are not chunk 9 work.** `UI_Implementation_Plan.md` says the tabs "fill in 9", which they do: the categories are fixed in `kinds.py` from chunk 5, `c5-watch-feed-read` serves the filter and `c5-fe-watch-feed` draws the tabs. Chunk 9 puts cases into the later categories and edits no feed file.

DEFAULTS TAKEN (each stated in its commit body with the source that settles it; only the one open choice under "Open questions" reaches `docs/TODO_FOR_alex.md`)
- Evidence is limited to PDF, DOCX, XLSX, PPTX, PNG, JPEG, TXT and CSV, up to `EVIDENCE_MAX_BYTES` (25 MB), both settings with env overrides (parallel plan §7.2). A file outside either answers 422 before a byte is stored.
- A deployed environment with `SCANNER_PROVIDER=mock` refuses to scan: the adapter factory raises at first use, `addEvidence` answers 503 `scanner_unavailable` and nothing is stored. The production **boot** guard is not changed, because parallel-plan rule 8 reserves `bootguard` to `E4` and `c14-eu-data-location`; a `HARDENING.md` row asks `c14-eu-data-location` to add the boot refusal beside the storage one.
- Evidence is invisible until the scan passes: `evidence.scan_state` (`pending`, `clean`, `infected`, `error`) with `scanned_at`. `listEvidence` returns the state, a download of anything but `clean` answers 409 `scan_pending` or 422 `scan_failed`, and an infected file's bytes are deleted from storage while the row and its audit trail stay.
- The case file exports as text; no PDF library is added (parallel plan §7.2). `c9-case-file-export` adds one `export_kind`, `case_file`, on chunk 12's framework.
- `GET /changes/{id}/case-file` and `GET /evidence/{id}/download` are gated by `cases.read`, which every system role holds (PRD §6), matching `UI_Implementation_Plan.md`'s rows ("All 7; audited per download"). Reader and Auditor download evidence like everyone else; every download is audited, which is the control D-11 relies on. No new permission is added and nothing joins `UNGATED_BY_DESIGN`.
- A sub-status is set on triage and on saving the assessment, never through a route of its own: D-13 gives a tenant sub-statuses inside the fixed categories and no workflow engine, so a separate write would be the engine D-13 refused (ruling 8).
- Every case write takes `If-Match` carrying `change_case.version` and answers 409 `stale_write` without it or with a stale value (INPUT_DELTAS §4). `impact_assessment` and `action` carry their own `version` for their own writes.
- A dismissal reason and a close reason are keys from the tenant's `dismissal_reason` and `close_reason` lists; an unknown key answers 422 `unknown_key` with the valid keys (VOC-S10). The API stores and compares keys, never labels.
- Triage notifies the owner, and a sign-off request notifies the holders of `cases.signoff`, both through `c10-collab-models`'s `notify()` and D-34's one recipient check. Chunk 9 writes no recipient rule of its own.
- Step-up is required on `POST /changes/{id}/signoff/approve` only (playbook 4.2). Triage, dismissal, restore, assessment, actions, evidence, the sign-off request and send-back need none: playbook 4.2 does not list them, and send-back is the safe direction.
- A delegate needs `cases.signoff` themself; out-of-office only routes the notification (parallel plan §7.2, `c8-ten-out-of-office`). Chunk 9 adds no delegation branch.
- `case_transition` is append-only at the database and is written inside the same transaction as every status move, so the time a case spent in each stage cannot be rewritten.
- The case file carries the tenant's own judgement and public library facts only: the change, the confirmed So what, the assessment, actions with completion, the evidence list with hashes and scan states, both sign-off names and every date. An unconfirmed AI draft is labelled, never presented as the bank's text.
- `CASE_ACTIONS_MAX` (200) and `CASE_EVIDENCE_MAX` (200) cap a case's children, so one case cannot make the case file exceed the 250 ms budget.

CUT, WITH REASONS
- `POST /changes/{id}/actions/export-tickets` and INT-S3: ruling 3.
- `DownloadLink`, `EvidenceCreated.uploadUrl` and the presigned operations: rulings 4 and 5.
- `impact_assessment.contributors`: ruling 2.
- `change_case.triage_due_at`, reminders and escalation on cases: ruling 6; `c10-reminders-escalation` owns them and already depends on `c9-case-models`.
- Evidence on a `tenant_obligation` (`evidence.tenant_obligation_id`): the column is built nullable by `c9-evidence-model` because the CHECK needs it, but no chunk 9 route writes it. `c8-reg-gaps` and chunk 12 own the register side; a test proves every chunk 9 write sets `case_id`.
- Comments and mentions on a case: COL-01 is chunk 10's (`c10-comments-api`), and no chunk 9 scenario asks for one.
- A case list of its own (`GET /cases`): the watch feed is the list (ruling 10), and no scenario or screen card asks for a second one.
- Retention and purge of closed cases and removed evidence: D-53 and chunk 12 (`c12-retention-purge`), which already depends on `c9-evidence`.

PLAN-WIDE RULES
1. **Slots.** Every backend and E2E gate runs inside the task's slot: `set -a; . ./.env.worktree; set +a`. A cloud session runs `bash scripts/cloud-setup.sh` (with `--e2e` where the gates include E2E) instead.
2. **Generated files.** No task commits `openapi.json`, `frontend/src/types/api.generated.ts` or `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them locally to run `contract_drift.py` and the typecheck, then reverts them. The main agent regenerates and commits them at the merge, and regenerates the navigation and pill snapshot baselines when `registry.ts` or `tone-by-kind.ts` changed.
3. **The cases backend chain.** One task at a time owns `backend/apps/cases/api.py`, `schemas.py` and `logic.py` (keys `casesapi` and `caseslogic`): `c9-case-contract` writes all three once and sends each operation to a named function that answers 501 `not_built`. `logic.py` holds only the shared case loader, the `If-Match` check and the transition helper. A logic task owns only its own module (`triage.py`, `assessment.py`, `actions.py`, `evidence.py`, `signoff.py`, `case_file.py`, `tasks.py`) and its tests, never `api.py`. A logic task that finds the contract wrong stops and reports. `f03-T76` is the only later task that takes `caseslogic`.
4. **The cases frontend chain.** `c9-fe-cases-feature` writes `frontend/src/features/cases/{types,api,hooks,case-presentation}.ts` once (key `casesfe`) and creates one stub component per panel under `frontend/src/components/cases/`, each rendering nothing, plus the mount inside the change screen (key `changescreen`). Each panel task then owns exactly one of those files and its own message namespace pair. No later chunk 9 task edits `features/cases/` or the change screen.

   The seven namespaces live in one catalog pair, so they need a key of their own: **`casesmsg`** (the case message catalogs, `frontend/src/messages/cases/{en,sv}.json`, the namespace this chain creates under the layout `x-frontend-split` introduced) orders `c9-fe-cases-feature` → `c9-fe-triage-panel` → `c9-fe-assessment-panel` → `c9-fe-actions-panel` → `c9-fe-evidence-panel` → `c9-fe-signoff-panel` → `c9-fe-case-file`. A catalog is one object each task rewrites whole, not an append ledger, so the seven writers are ordered even where four of them share wave 6, exactly as CHUNK8's `tenadminmsg` orders its four. A chain is an order, not a wave: a task starts when its depends-on is on `main` and the key ahead of it is free.
5. **Screens call no stub.** Each panel task depends on every backend task whose routes it calls, and the journey tasks depend on every panel they walk.
6. **Append ledgers** (parallel plan rule 5): `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`, `docs/plans/briefs/HARDENING.md`, the UI plan's ledger rows and status cells, `backend/config/settings.py` setting banners, `backend/.env.example` and `docs/runbooks/RAILWAY_VARIABLES.md`, router mounts in `backend/config/api.py`, `backend/apps/shared/kinds.py`, `factories.py` and `routes.py`, the route lists in `permissions.py`, the guarded-table lists in `tests_rls.py`, `tests_four_eyes.py` and `tests_seed_integrity.py`, `backend/apps/shared/e2e_seed.py` (one seed call per task), `frontend/src/shared/navigation/registry.ts` entries, `frontend/src/features/shared/tone-by-kind.ts` entries, each app's `app.md` status cells, each app's `tests_scenarios.py` skip lines, and each `*.journey.spec.ts` (own test blocks only). Each task adds only its own lines and never edits another's.
7. **Coverage floors.** `backend/scripts/coverage_gate.py` gets the chunk 9 floors once, from `c9-close`, measured at the close with the date beside each. A task states its own `coverage report --include` threshold in its done-condition and never lowers an existing floor.
8. **Security review before merge.** `c9-case-models` and `c9-evidence-model` (new tenant tables under row-level security, one four-eyes CHECK, one append-only ledger), `c9-scanner-adapter` (untrusted bytes), `c9-evidence` (upload, scan, hash and a file-serving route), `c9-signoff` (four eyes and step-up), `c9-case-file-export` (a job that writes a tenant's whole case to a file), `c9-close-paths` (the one decision that can take a change out of the workflow), `f03-T76` (participants) and `c9-review-fixes` each get a security-review sub-agent over `git diff main...<branch>` before the squash merge, with `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write` and `tests_four_eyes`. `c9-security-review` is the chunk-wide sweep after the last journey **and `c9-close-paths`** merge, so the close paths are inside the diff it reads.
9. **Merge at once.** Each task is squash-merged and the full checklist run as soon as it passes review (WORKTREES step 5). Finished work never waits for the rest of the chunk.
10. **Clocks.** Everything dated is anchored to the tenant-local date plus a fixed wall time (CLAUDE.md §8.3 and §11). Due dates, internal deadlines and "days left" are derived from the seed's anchor, never from the real today: an action seeded "due yesterday" must be overdue in every month.
11. **The state machine is one module.** `backend/apps/cases/state.py` holds the categories, the allowed transitions, the guards and `allowed_transitions(case)`. No route, no screen and no test restates a transition table. The categories and the guards are fixed (CLAUDE.md §5); sub-statuses sit inside them and never reach a guard.
12. **Cloud sessions stop on invariant questions** (parallel plan rule 12). `c9-case-models`, `c9-evidence-model`, `c9-evidence`, `c9-signoff`, `c9-scanner-adapter` and `f03-T76` carry that instruction explicitly.
13. **Scenario ownership.** Exactly one task un-skips each integration test and one un-fixmes each journey:

| Scenario | `@integration` | `@e2e` |
|---|---|---|
| CAS-S2 | `c9-triage` | `c9-e2e-triage-journeys` |
| CAS-S3 | `c9-triage` | `c9-e2e-triage-journeys` |
| CAS-S4 (reworded) | `c9-assessment` | `c9-e2e-work-journeys` |
| CAS-S5 | `c9-assessment` | — |
| CAS-S6 (reworded) | `c9-actions` | `c9-e2e-work-journeys` |
| CAS-S7 | `c9-evidence` | `c9-e2e-work-journeys` |
| CAS-S8 | `c9-signoff-request` | `c9-e2e-signoff-journeys` |
| CAS-S9 | `c9-signoff` | `c9-e2e-signoff-journeys` |
| CAS-S10 | `c9-signoff` | `c9-e2e-signoff-journeys` |
| CAS-S11 | `c9-case-file-export` | `c9-e2e-j3` |
| CAS-S12 (reworded) | `c9-signoff` | — |
| CAS-S13 | `c9-assessment` | — |
| CAS-S14 (J-2, `@smoke`) | — | `c9-e2e-triage-journeys` |
| CAS-S15 (J-3, `@smoke`) | — | `c9-e2e-j3` |
| CAS-S16 | `c9-case-file` | — |
| CAS-S17 | `f03-T76` | — |
| CAS-S18 (new, CLAUDE.md §10) | `c9-signoff` | — |
| COL-S9 | `f03-T76` | `f03-T76` |
| VOC-S10 (the dismissal and closure half) | `c9-triage` | — |
| TEN-S3 (the case half) | `c9-triage` | — |
| TEN-S5 (the case and action half) | `c9-actions` | chunk 8's `c8-ui-member-removal` |
| HOM-S14 | `f03-T77` | — |

CAS-S4 has one owner, `c9-assessment`, which un-skips it; `c9-close-paths` adds the close clause back to that same test once q-case-close is answered and re-runs it, and un-skips nothing of its own. No other scenario is written by two tasks. TEN-S7 (J-8) stays chunk 8's and is extended by `c10-j8-extension`; chunk 9 makes its case and evidence rows real and touches the journey in no task.

CAS-S1 is chunk 5's (`c5-cases-creation`) and is not touched here. `c9-case-design`, `c9-state-machine`, `c9-scanner-adapter`, `c9-case-models`, `c9-evidence-model`, `c9-case-contract`, `c9-reference-members`, `c9-e2e-seed`, `c9-fe-cases-feature`, every `c9-fe-*-panel`, `c9-close-paths`, `c9-security-review`, `c9-review-fixes` and `c9-close` un-skip nothing; each proves itself with its own unit tests. TEN-S5's integration may already be un-skipped by `c8-ten-reassignment` for obligations; `c9-actions` then extends it with the case and action rows rather than un-skipping it, and no other chunk 9 task touches it.

14. **The sixty-minute limit** (parallel-plan rule 9). A task past sixty minutes stops at a green point and the rest becomes a new task with the derived id; its scope does not stretch. Five tasks sit at or near the cap, and each one's stopping point is named here so a sub-agent that runs out of room knows where to stop:
    - `c9-case-design`: stop once triage, next step, the impact assessment and actions are drawn in every state of `states.html`, at both widths and in both themes; evidence, sign-off, closed and dismissed and the case-file view become `c9-case-design-b`, which also moves the `UI_Implementation_Plan.md` screen-card row.
    - `c9-case-contract`: stop once `cases/api.py`, `schemas.py`, `logic.py`, the six `not_built` modules and the router mount are green with the route-permission, step-up and tenant-isolation tests; the `Case` block and `allowedTransitions` on `GET /changes/{changeId}` become `c9-case-contract-b`, which holds `watchapi` alone.
    - `c9-e2e-seed`: stop once tenant A's seven cases, their assessment and their actions are seeded, idempotent and anchored; the evidence rows in all three scan states, tenant B's case on the shared change and the "Legal" team membership become `c9-e2e-seed-b`.
    - `c9-evidence`: stop once CAS-S7 is green whole — attach, the allow-list and the cap, the hash, the scan, the stream and its audit row — because the coverage critique rejected splitting that scenario by verb; `removeEvidence`, the `EVIDENCE_SCAN_RETRIES` error-retry path and `CASE_EVIDENCE_MAX` become `c9-evidence-b` on `casestasks`.
    - `c9-fe-cases-feature`: stop once `features/cases/{types,api,hooks,case-presentation}.ts` and their unit tests are green; the six panel stubs and the `CaseWorkPanels` mount become `c9-fe-cases-feature-b`, which holds `changescreen`. `casesmsg` passes to whichever half ran last.

CHANGES FROM `PARALLEL_PLAN.md`, WITH REASONS
- **Five ids added, each a split of a package past the thirty-minute target**, with the mapping section 3.1 uses:

  | Package in 3.3 | Tasks here |
  |---|---|
  | `c9-case-models` (60 min) | `c9-case-models` (the workflow tables) + `c9-evidence-model` (the evidence table) |
  | `c9-signoff` (45 min, four scenarios) | `c9-signoff-request` (CAS-S8) + `c9-signoff` (CAS-S9, CAS-S10, CAS-S12) |
  | `c9-e2e-signoff-journeys` (55 min) | `c9-e2e-signoff-journeys` (CAS-S8 to CAS-S10) + `c9-e2e-j3` (J-3 `@smoke` and CAS-S11) |
  | `c9-case-contract` (60 min) | `c9-case-contract` + `c9-reference-members` (ruling 7, `identity`'s `idapi` key, not the cases API's) |
  | *(new, gated)* | `c9-close-paths`, which builds whichever option Alex picks for q-case-close |

  Each split has an independent done-condition and its own review surface; the plan 5, 7 and 8 reviews all found oversized packages, and the case models and the sign-off routes were this chunk's two worst.
- **`c9-case-contract` gains `c9-evidence-model` in its depends-on.** Its route-permission and tenant-isolation gates need a `factories.py` entry building each route's subject on a tenant-private record, and the evidence routes have no subject until the table exists. This is the shape the chunk 8 review rejected in `c8-register-api-contract`.
- **`c9-signoff` gains `c9-assessment` in its depends-on.** CAS-S12 reads `allowedTransitions` from `assessing`, which no case reaches until the assessment route exists.
- **`c9-case-file` gains `c9-evidence` and `c9-actions`** and owns CAS-S16, which addresses a case, an evidence file and a case file across tenants; all three must exist.
- **`c9-e2e-seed` gains `c9-evidence-model`**, because it seeds evidence rows in each scan state.
- **`c9-triage` and `c9-signoff` keep `c10-collab-models`** as section 3.3 has it, and neither writes a recipient rule: D-34's one check serves both.
- **`c13-tickets-export` needs the `casesapi` key**, which section 3.3 does not give it (ruling 3). The main agent adds it when chunk 13 is planned.
- **`c9-reference-members` has its own row in section 3.3**, added with this revision: chunk 9, R2, depends on `f03-T55` and `c9-case-contract`, 25 minutes, wave 27, serializing on `idapi` (ruling 7). It is the only section 3.3 row this plan adds; the other four added ids stay splits of rows that are already there.
- **`c9-fe-cases-feature` gains the six panel stub files and the `changescreen` mount** so four panel tasks can run side by side. Without it the first panel task would edit an unowned page, which is the finding the chunk 8 review raised about the obligation page.
- **Each panel task owns its own message namespace pair** (`caseTriage`, `caseAssessment`, `caseActions`, `caseEvidence`, `caseSignoff`, `caseFile`) instead of one `cases` namespace, for the same reason.

CHANGES FROM THE TWO CRITIQUES
- Parallelism: the panel stub files and the per-panel namespaces (six tasks on two files); `cases/logic.py` reserved to the contract task and `f03-T76`, so six logic tasks share a wave; `c9-evidence-model` split out of `c9-case-models` so the contract task is not held behind the whole migration; `c9-reference-members` split out so `c9-case-contract` does not hold a second app's API key across a wave; `c9-e2e-j3` split out so the J-3 smoke journey does not wait behind three sign-off journeys; the watch feed left alone (ruling 10), which removes two tasks and two keys.
- Parallelism, second pass: `c9-triage` and `c9-actions` had `c9-reference-members` in their depends-on although all three sit in wave 5 — a backend logic task calls no reference route, so the dependency moved to `c9-fe-triage-panel` and `c9-fe-actions-panel`, where the pickers are; the ownership table gained a footnote so CAS-S4's one owner is unambiguous against `c9-close-paths`, which extends it.
- Coverage, second pass: `sendBackSignoff` had a route, a button and a screen state but no scenario, so CAS-S18 is added by `c9-signoff`; `deleteAction` had the same gap and CAS-S6 gains a delete line from `c9-actions`; TEN-S7 (J-8) covers cases and evidence but belongs to chunk 8 and `c10-j8-extension`, which the ownership note now says so no chunk 9 task edits that journey.
- Coverage: CAS-S12 had no owner, because no task's route both read `allowedTransitions` from `assessing` and offered a transition the machine refuses — `c9-signoff` now owns it with the reworded second clause; CAS-S16 had no owner and is now `c9-case-file`'s; VOC-S10's dismissal half was named by the UI plan but by no task, and is now `c9-triage`'s; CAS-S11's integration would have proved an export that did not exist, so it moved to `c9-case-file-export`; CAS-S6's ticket clause would have stayed fixme past chunk 13, so it is reworded and named (ruling 3); the evidence scan had no state and no refusal code, so a file was visible while the scan ran; the `impact_assessment.contributors` column would have shipped beside the participants that replace it (ruling 2); `case_transition` had no writer and no append-only trigger, so CAS-08's ledger rested on convention; nobody owned the deletion of chunk 9's `contract_drift_pending.txt` lines, so each backend task deletes its own and `c9-close` proves none is left; the close-without-action path let one person take a change out of the workflow, which is q-case-close.

## Waves

Tasks in one wave have disjoint owned paths and can run side by side, except where a serialization key orders them inside the wave (rule 4).

1. `c9-case-design`, `c9-state-machine`, `c9-scanner-adapter`
2. `c9-case-models`
3. `c9-evidence-model`
4. `c9-case-contract`, `c9-e2e-seed`
5. `c9-triage`, `c9-assessment`, `c9-actions`, `c9-evidence`, `c9-reference-members`, `c9-fe-cases-feature` — `casesmsg` starts here, with `c9-fe-cases-feature`
6. `c9-case-file`, `c9-signoff-request`, `c9-fe-triage-panel`, `c9-fe-assessment-panel`, `c9-fe-actions-panel`, `c9-fe-evidence-panel` — `casesmsg`: triage, then assessment, then actions, then evidence
7. `c9-signoff`, `c9-case-file-export`, `f03-T76`
8. `c9-fe-signoff-panel`, `c9-fe-case-file`, `f03-T77`, `c9-close-paths` (held by q-case-close) — `casesmsg`: signoff-panel, then case-file
9. `c9-e2e-triage-journeys`
10. `c9-e2e-work-journeys`
11. `c9-e2e-signoff-journeys`
12. `c9-e2e-j3`
13. `c9-security-review`
14. `c9-review-fixes`
15. `c9-close`

If q-case-close is unanswered when wave 5 starts, `c9-assessment` builds the assessment and stops at a green point (parallel-plan rule 9): `closeWithoutAction` and the `applies = no` branch stay at 501 `not_built`, CAS-S4 is un-skipped without its close clause, and `c9-close-paths` waits. Everything else proceeds. `c9-close-paths` runs in wave 8 if the answer is in by then and in the first wave after the answer otherwise; either way it merges, with its own security review, **before** the wave 13 sweep, which depends on it, and `c9-close` cannot run until both have merged.

## Open questions

- **q-case-close (a product invariant is at stake, so stop and ask Alex).** Two designed paths let one person take a regulatory change out of the workflow and into the `closed` category: `POST /changes/{id}/close` ("Close without action", `closeReason` `no_action`) and `PUT /changes/{id}/assessment` with `applies = no`, which `openapi.yaml` says "closes the case with closeReason not_applicable". Both are gated by `cases.work` alone, with no second person and no step-up.

  That is the cheapest way to end a case, and it is the one a rushed team will reach for, so it decides how much CAS-06's sign-off is worth. CLAUDE.md §5 lists four eyes with a passkey step-up on "sign-off"; it does not say whether a close that claims no work was needed is a sign-off. The PRD does not say either, and neither `docs/DECISIONS.md` nor `OWNER_RECOMMENDATIONS.md` answers it. CAS-02's dismissal is a different thing and is settled: it happens before triage, is explicitly one person with a reason, and is restorable.

  Option A (recommended): both paths go through the same second person. The case moves to `signoff` carrying its intended close reason, and a holder of `cases.signoff` who is not the requester closes it with a step-up. The open-action and evidence guards are lifted for these two reasons, because there is nothing to evidence. It adds no state to the machine, no new route and no new permission, and it makes one rule — a case leaves the workflow only with two people — with no second door for an auditor to find.

  Option B: keep the designed one-person close, audited, with the reason recorded and the case restorable to triage. It is what `openapi.yaml` draws and the least work, and it keeps four eyes only where work is claimed to be done.

  Option C: four eyes on `applies = no` (a judgement about what the law requires of the bank) but not on `no_action` (a judgement about the bank's own work). It draws the line where the risk is, but it puts two close paths with different rules in front of the same person, which is how the wrong one gets used.

  This gates `c9-close-paths`, the close clauses of `c9-assessment` and CAS-S4, and `c9-close`. Nothing else in the chunk waits. **Status: the main agent put it to Alex on 2026-09-20, with Option A recommended. It is open until he answers**, and the wave note says what runs meanwhile.

- **Not questions: four defaults with the source that settles each.** The earlier plan carried these as things to confirm; each already has an answer in a source this plan must follow, so each is a default taken (above), stated in its task's commit body, and none reaches `docs/TODO_FOR_alex.md`:
  - The evidence allow-list and the 25 MB cap: `PARALLEL_PLAN.md` §7.2 sets both, as settings with env overrides (`c9-evidence`).
  - Every role holding `cases.read` may download an evidence file, Reader and Auditor included: PRD section 6 gives all seven roles `cases.read`, and `UI_Implementation_Plan.md`'s download row reads "All 7; audited per download". The audit row per download, not a narrower permission, is D-11's control.
  - A sub-status is set on triage and on saving the assessment, with no route of its own: D-13 (tenant sub-statuses inside fixed categories, no workflow engine), ruling 8.
  - A deployed environment without a real scanner refuses at first use, not at boot: parallel-plan rule 8 reserves `bootguard` to E4 and `c14-eu-data-location`, so a boot refusal here would be a guard change outside the package named for it; `c9-scanner-adapter` leaves a `HARDENING.md` row asking for it there.
- **The one open confirmation, and the only chunk 9 line in `docs/TODO_FOR_alex.md`:** that evidence upload is multipart through the API rather than a presigned PUT (ruling 4). INPUT_DELTAS §4 allows a presigned upload "if the scan and the hash still happen before the file is visible", so this departs from a source rather than following one, and no other source settles it. The build does not wait: `c9-evidence` builds multipart and `c9-close` writes the line.
- Answered already, and therefore **not** asked: who may add or remove a case participant (D-19, `cases.contribute`, and anyone may remove their own row); whether the contributor list and the participant list are one thing (D-20, they are); whether a participation grants access (D-18, it does not); how long a closed case and its evidence are kept (D-53, ten years after last use, built by `c12-retention-purge`); whether urgency levels may be added or re-ranked (D-48, no); whether the case file may hold private notes (D-60, there are none).
- Rejected, from the parallelism critique: merging `c9-triage`, `c9-assessment` and `c9-actions` into one "case workflow" task because all three write `change_case`. They own different modules, different routes and different scenarios, and together they are more than two hours; rule 3's shared loader removes the duplication without removing the split.
- Rejected, from the coverage critique: declaring `POST /changes/{id}/actions/export-tickets` as a 501 stub so CAS-S6 could stay whole. Ruling 3: `c9-close` must prove no chunk 9 route answers 501, and a stub declared here would either fail that proof or force the close to carve out an exception, which is how a 501 survives into a release.
- Rejected, from the coverage critique: giving `c9-evidence` a second task for the download route so CAS-S7 could be split by verb. CAS-S7 is one scenario over one security surface — attach, allow-list, hash, scan, stream, audit — and splitting it would have left two tasks each proving half of it, which is the ownership muddle the chunk 5 and chunk 8 reviews both found.

## Tasks

### c9-case-design: the case work panels, drawn

**Requirements:** CAS-02, CAS-03, CAS-04, CAS-05, CAS-06, CAS-07
**Scenarios:** none
**Depends on:** none

Add the case work panels to `design/screens/tenant-change.html`, whose own header comment says "the prototype's triage, assessment, actions, evidence and sign-off panels are chunk 9", and which `UI_Implementation_Plan.md` lists as "card pending; prototype `vChange()` work panels are the cut". Cut from `design/prototype/index.html` `vChange()`, and design where the prototype is silent:

- **Triage** (status `new`): urgency picker, owner picker, "Confirm and assign" and "Dismiss", the dismissal dialog with its reason list, and the refusal when no reason is given.
- **Next step** (status `assigned`): "Start assessment" and "No action", with the close dialog.
- **Impact assessment** (`assessing` onwards): applies, why, what must change, an internal deadline, an effort size, the contributor-teams picker (single add and remove, D-20), "Save assessment and plan actions", and the `stale_write` state offering a reload and never a merge (CAS-S5).
- **Actions** (`implementing`): the list with owner and due date, the add row, the completion checkbox, and the locked state while sign-off is pending with the reason in words.
- **Evidence**: the list with kind, name, size, who attached it and when; the attach dialog for a file, a link and a reference; the scanning state; the refused-file state naming the allow-list and the cap; remove with its confirm.
- **Sign-off**: "Request sign-off" with the two refusals shown where they happen (open actions, no evidence), the waiting state naming who requested it, "Sign off and close" with the step-up prompt, the self sign-off refusal in words, and "Send back".
- **Closed and dismissed**: who signed off and when, or the dismissal reason and "Move back to triage"; "Show case file" and its view.
- Every panel in all the states of `design/screens/states.html` (loading, empty, error, denied, permission-limited), at 375 px and on a desktop, in light and dark.

Pills only from the six tones, chosen by slot or kind: the status pill takes the category's tone and renders the tenant's sub-status label (CAS-S13), and urgency keeps the tone its row already has (D-48). Update the `UI_Implementation_Plan.md` screen-card row for "case panels on `tenant-change.html`" from `card pending` to `designed`.

**Owned paths:**

- `design/screens/tenant-change.html`
- `docs/plans/UI_Implementation_Plan.md` (the one screen-card row)

**Done when:**

- Every panel, state and dialog above is drawn, at both widths and in both themes.
- Every button label matches `backend/apps/cases/app.md` §3 exactly: "Confirm and assign", "Dismiss", "Start assessment", "Save assessment and plan actions", "Add action", "Attach evidence", "Request sign-off", "Sign off and close", "Show case file".
- No requirement id, no restated invariant and no pill tone chosen by a person appears on screen.
- The card names, for each panel, the operation it calls and the permission that unlocks it, so the screen tasks need no second source.
- Every text pair passes WCAG AA in both themes.

**Gates:**

- Open the card in a browser at 375 px and at 1440 px, in light and dark, and read every state.
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- The prototype decides how things look; the PRD decides what the rules are.
- Six pill tones, chosen by slot or kind, never by a person.
- Screen copy says what the user is doing.

### c9-state-machine: the case state machine, as one module

**Requirements:** CAS-08
**Scenarios:** none
**Depends on:** none

Write `backend/apps/cases/state.py`, a pure module with no database and no import from `models.py`:

- The seven fixed categories come from `apps/shared/kinds.py`'s `CaseStatusCategory`, which chunk 5 already added. This task adds no kind.
- `TRANSITIONS`: the map of `docs/inputs/data-model.md` §"Case status machine" — `new → assigned | dismissed`, `dismissed → new`, `assigned → assessing | closed`, `assessing → implementing | closed`, `implementing → signoff`, `signoff → implementing | closed`.
- `Guard`: a named, testable predicate per edge — an owner on triage, a reason on dismissal, a why on the assessment, no open action and at least one piece of evidence before a sign-off request, a second person with a step-up to close.
- `allowed_transitions(status, *, facts)` returns the categories the guards permit from a status, given a small frozen `CaseFacts` value object (owner set, open action count, usable evidence count, requester). `api.py` and every screen read this and restate nothing.
- `check_transition(from_status, to_status, facts)` raises `InvalidTransition` with the code `invalid_transition`, or the guard's own code (`open_actions`, `evidence_missing`, `four_eyes_violation`), so every refusal carries a code the client branches on (playbook 4.4).
- A sub-status is not a state: the module takes and returns categories only, and a docstring says so.

Write the table-driven test first: every pair of categories, allowed or not; every guard, satisfied and not; and a test that the module imports nothing from Django's ORM, so a later task cannot hide a query in it.

**Owned paths:**

- `backend/apps/cases/state.py`
- `backend/apps/cases/tests_state.py`

**Done when:**

- Every edge of the data-model diagram is in `TRANSITIONS` and nothing else is, proved by a test that enumerates all 49 ordered pairs.
- Each guard has a test for both outcomes and each refusal carries its documented code.
- `allowed_transitions` is total: every category returns a list, `closed` and `dismissed` included.
- The module has no database import; a test asserts the import set.
- `apps/cases/state.py` reaches 100% statement coverage, which a pure module can.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/state.py'` (100)
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- The case state machine's categories and guards are fixed; sub-statuses sit inside them.
- Kinds-only enums: the categories are a kind, the sub-statuses are rows.
- Every refusal is RFC 9457 with a `code`; no trace ever leaves.

### c9-scanner-adapter: the malware scanner seam

**Requirements:** CAS-05
**Scenarios:** none
**Depends on:** none
**Security review:** yes (it takes untrusted bytes)

Build `backend/apps/shared/adapters/scanner.py` beside the existing adapters (playbook 16; `llm.py` and `mailer.py` are the pattern), the one seam that decides whether a file is safe to show. Parallel-plan ruling 8 makes this the only package that builds it; `c12-imports-contract` depends on it.

- `ScanResult` = `{state, signature|None, scanned_at}` where state is the tier-one kind `ScanState` (`clean`, `infected`, `error`), added to `kinds.py` with its INPUT_DELTAS §1 name and reason.
- `MockScanner`: deterministic and offline. It returns `infected` for the EICAR test string and for a seeded marker filename, `error` for a marker that lets a task test the error path, and `clean` otherwise. No network.
- `ClamdScanner`: streams the bytes to a clamd socket from `SCANNER_HOST`, `SCANNER_PORT` and `SCANNER_TIMEOUT_SECONDS`, all settings with env overrides under one banner naming CAS-05. A timeout, a refused connection or an unparsable reply is `error`, never `clean`: an unknown answer is never treated as safe.
- `get_scanner()` chooses on `SCANNER_PROVIDER` (`mock` | `clamd`), refuses an unknown provider, and **raises on a deployed environment when the provider is `mock`**, so a deployed environment without clamd cannot store an unscanned file. It does not touch the production boot guard: parallel-plan rule 8 reserves `bootguard`, and a `HARDENING.md` row asks `c14-eu-data-location` to add the boot refusal beside the storage one.
- The scanner never logs a filename, a path or any file content; it logs the provider, the state and the elapsed milliseconds.

Write the test first, in `apps/shared/tests_adapters.py`'s style: the mock's three outcomes, the unknown provider, the deployed-with-mock refusal, the timeout mapped to `error`, and a log-capture test that no filename reaches a log record.

**Owned paths:**

- `backend/apps/shared/adapters/scanner.py`
- `backend/apps/shared/tests_scanner.py`
- `backend/apps/shared/kinds.py` (the `ScanState` entry only)
- `backend/config/settings.py` (one banner), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `docs/plans/briefs/HARDENING.md` (its own row only)
- `docs/inputs/INPUT_DELTAS.md`
- `docs/plans/Verification_Log.md` (the clamd protocol row)

**Done when:**

- The mock's three outcomes, the unknown provider and the deployed-with-mock refusal each have a test.
- A clamd timeout, a refused connection and a truncated reply each map to `error`, and no path maps an unknown answer to `clean`.
- No filename, path or byte of content reaches a log record, Sentry or an exception message, proved by a log-capture test.
- Every threshold is a setting with an env override, documented in `.env.example` and `RAILWAY_VARIABLES.md`.
- The `HARDENING.md` row names `c14-eu-data-location` as the owner of the boot refusal.
- The clamd `INSTREAM` protocol facts are fetched, not recalled, and logged in `Verification_Log.md`.
- `apps/shared/adapters/scanner.py` holds 95% statement coverage.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/adapters/scanner.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Fetched and uploaded content is untrusted; an unknown answer is never "safe".
- No tenant content in logs or Sentry: a filename is tenant content.
- Every window, cap, rate and threshold is a setting with an env override.
- A guard is never changed outside the package named for it: `bootguard` is not touched.

### c9-case-models: the workflow tables

**Requirements:** CAS-02, CAS-03, CAS-04, CAS-08
**Scenarios:** none
**Depends on:** `c5-contract-models-cases`, `c8-tenants-contract`, `f03-T51`, `f03-T53`
**Security review:** yes (new tenant tables, a four-eyes CHECK, an append-only ledger)
**Stop and report** on any invariant question (parallel-plan rule 12).

Extend `backend/apps/cases/models.py` and add the next `mig:cases` migration, from `docs/inputs/schema.sql` §8 and §13 and `data-model.md`:

- `ChangeCase` gains the workflow columns chunk 5 left out: `triaged_by`, `triaged_at`, `dismissed_reason` (a `dismissal_reason` vocabulary row), `dismissed_by`, `dismissed_at`, `signoff_requested_by`, `signoff_requested_at`, `signed_off_by`, `close_reason` (a `close_reason` vocabulary row), `closed_note`, `closed_at`, `owner_team` (a composite foreign key to `team`, parallel-plan ruling 10), `sub_status` (a nullable `case_sub_status` vocabulary row, ruling 8) and `version` (INPUT_DELTAS §4). The four-eyes CHECK `signed_off_by IS NULL OR signed_off_by <> signoff_requested_by` and the two CHECKs `schema.sql` already names (a dismissal needs a reason; any status past triage needs an owner) come with the migration, and the table joins `FOUR_EYES_TABLES` in the same commit.
- `ImpactAssessment(TenantModel)`: `case` (unique), `applies` (`AssessmentApplies`), `why`, `what_must_change`, `internal_deadline`, `effort` (an `effort_size` vocabulary row), `saved`, `saved_by`, `saved_at`, `version`, `CHECK (NOT saved OR why IS NOT NULL)`, `Meta.ordering`. **No `contributors` column** (ruling 2).
- `Action(TenantModel)`: `case`, `title`, `owner`, `due_date`, `done_at`, `done_by`, `created_by`, `created_at`, `version`, `Meta.ordering = ["due_date", "created_at"]`, and the partial index `schema.sql` names on `(tenant_id, due_date) WHERE done_at IS NULL`. The three ticket columns are **not** added: ruling 3 puts them in `c13-tickets-export`.
- `CaseTransition(TenantModel, AppendOnlyModel)`: `case`, `from_status`, `to_status`, `at`, `by_user`, `note`, `Meta.ordering = ["at"]`, with `migration_helpers.append_only_trigger_operations`, so the time a case spent in each stage cannot be rewritten afterwards — that is CAS-08's ledger, made structural instead of remembered.
- The migration applies `migration_helpers.rls_operations()` to all three new tables, and `ChangeCase` keeps the forced policy chunk 5 gave it. Every foreign key to `team`, `app_user` and `change_case` is composite on `(tenant_id, …)` (INPUT_DELTAS §1, D-18), because PostgreSQL checks foreign keys with row-level security bypassed and only a composite key makes a cross-tenant row impossible.
- Add the three tables to the guarded-table lists in `apps/shared/tests_rls.py` and `tests_seed_integrity.py`, and `change_case`'s constraint to `tests_four_eyes.py`.
- Correct the INPUT_DELTAS §7 line that parks reminder, escalation and retention settings for "the workflow policy (chunk 9)": it is `c10-workflow-policy` (ruling 6), and `triage_due_at` is not built here.
- Write the INPUT_DELTAS §1 rows for the dropped `contributors` column (ruling 2) and the dropped ticket columns (ruling 3), each naming the task that closes it.

**Owned paths:**

- `backend/apps/cases/models.py`
- `backend/apps/cases/migrations/` (one migration)
- `backend/apps/cases/tests_models.py`
- `backend/apps/shared/tests_rls.py`, `tests_four_eyes.py`, `tests_seed_integrity.py` (the guarded-table lists only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- The RLS guard lists `impact_assessment`, `action` and `case_transition` as forced tenant-only, and a cross-tenant read returns nothing under `cw_app`.
- As `cw_app`, UPDATE and DELETE on `case_transition` are refused and INSERT works, on the app alias, with `SET LOCAL cw.maintenance = 'on'` proved not to help.
- A row whose `owner_team`, `owner`, `case` or `by_user` belongs to another tenant is refused by the database, not by Python; one test per composite key.
- The four-eyes CHECK refuses `signed_off_by = signoff_requested_by` at the database, and `tests_four_eyes` enumerates it.
- `impact_assessment` has no `contributors` column and `action` no ticket columns; a test asserts both, so rulings 2 and 3 cannot drift back.
- Every new table carries `version` where INPUT_DELTAS §4 requires it.
- The compliance lint and the kinds-only guard are green; `apps/cases/models.py` holds 95% statement coverage.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Tenant tables carry `tenant_id` under enabled and forced row-level security; `cw_app` cannot bypass it.
- Nothing is overwritten: the transition ledger is append-only at the database.
- Four eyes is a check constraint, not a convention.
- snake_case columns; `Meta.ordering` on anything `.first()`ed; no `JSONField` without a named schema.
- Enums in code are kinds only; statuses, reasons and effort are rows.

### c9-evidence-model: the evidence table

**Requirements:** CAS-05
**Scenarios:** none
**Depends on:** `c9-case-models`, `c9-scanner-adapter` (the `ScanState` kind is that task's, and both write the same `kinds.py` entry)
**Security review:** yes (a tenant table holding a pointer to private bytes)
**Stop and report** on any invariant question.

Add `Evidence(TenantModel)` and the next `mig:cases` migration, from `schema.sql` §8:

- `case` (nullable), `tenant_obligation` (nullable, unwritten in chunk 9 — see the cut list), `kind` (`EvidenceKind`: file, link, reference), `name`, `storage_key`, `url`, `content_hash`, `size_bytes`, `mime_type`, `uploaded_by`, `uploaded_at`, `removed_at` (soft delete), and the designed `CHECK (case_id IS NOT NULL OR tenant_obligation_id IS NOT NULL)`.
- Beyond the design: `scan_state` (`ScanState` plus `pending`) and `scanned_at`, because a file must be invisible until the scan passes (CAS-05, CAS-S7) and `schema.sql` has nowhere to record it. INPUT_DELTAS §1 row naming this task.
- `Meta.ordering = ["-uploaded_at"]`; composite foreign keys on `(tenant_id, …)` to `change_case`, `tenant_obligation` and `app_user`.
- A CHECK per kind: `file` needs `storage_key`, `content_hash`, `size_bytes` and `mime_type`; `link` needs `url`; `reference` needs neither. It stops a half-written row from ever being downloadable.
- The migration applies `migration_helpers.rls_operations()`, and the table joins the guarded-table lists in `tests_rls.py` and `tests_seed_integrity.py`.
- No hard delete: the model's `delete()` raises, and removal sets `removed_at`. A test proves it, because the audit trail keeps the name (CAS-05).

**Owned paths:**

- `backend/apps/cases/models.py` (the `Evidence` model only)
- `backend/apps/cases/migrations/` (one migration)
- `backend/apps/cases/tests_evidence_model.py`
- `backend/apps/shared/kinds.py` (the `pending` value beside `ScanState`)
- `backend/apps/shared/tests_rls.py`, `tests_seed_integrity.py` (the guarded-table lists only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- The RLS guard lists `evidence` as forced tenant-only, and a cross-tenant read returns nothing under `cw_app`.
- Each per-kind CHECK is proved by a refused insert, and the case-or-obligation CHECK by a third.
- A composite-key test proves the database refuses another tenant's case, obligation or user.
- `Evidence.delete()` raises, `removed_at` is the only removal, and a test proves a removed row still carries its name and hash.
- A new row starts at `scan_state = pending`, never `clean`, proved by a test on the model default.
- `apps/cases/models.py` holds its floor; the compliance lint is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/models.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Tenant tables sit under enabled and forced row-level security.
- Nothing is overwritten: evidence is soft-deleted and the audit trail keeps its name.
- A file is not visible until it has been scanned; the default state says so.
- snake_case columns; kinds-only enums.

### c9-case-contract: the case contract, seventeen operations behind their real gates

**Requirements:** CAS-02, CAS-03, CAS-04, CAS-05, CAS-06, CAS-07, CAS-08
**Scenarios:** none
**Depends on:** `c9-case-models`, `c9-evidence-model`, `c9-state-machine`, `c5-cases-creation`, `c5-cases-so-what-and-links`, `c5-watch-feed-read`, `c5-cases-footprint-hooks`, `c5-chunk-close`

Write `backend/apps/cases/api.py`, `schemas.py` and `logic.py` once, and mount the router in `config/api.py`. Every operation carries its auth class and permission and calls a named function in the module that will build it, which answers 501 `not_built` (parallel-plan rule 2):

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `triageChange` | `POST /changes/{changeId}/triage` | SessionAuth, `cases.triage` | `cases/triage.py` |
| `dismissChange` | `POST /changes/{changeId}/dismiss` | SessionAuth, `cases.triage` | `cases/triage.py` |
| `restoreChange` | `POST /changes/{changeId}/restore` | SessionAuth, `cases.triage` | `cases/triage.py` |
| `startAssessment` | `POST /changes/{changeId}/assessment/start` | SessionAuth, `cases.work` | `cases/assessment.py` |
| `saveAssessment` | `PUT /changes/{changeId}/assessment` | SessionAuth, `cases.contribute` | `cases/assessment.py` |
| `closeWithoutAction` | `POST /changes/{changeId}/close` | SessionAuth, `cases.work` | `cases/assessment.py` |
| `listActions` | `GET /changes/{changeId}/actions` | SessionAuth, `cases.read` | `cases/actions.py` |
| `addAction` | `POST /changes/{changeId}/actions` | SessionAuth, `cases.work` | `cases/actions.py` |
| `updateAction` | `PATCH /actions/{actionId}` | SessionAuth, `cases.contribute` | `cases/actions.py` |
| `deleteAction` | `DELETE /actions/{actionId}` | SessionAuth, `cases.work` | `cases/actions.py` |
| `listEvidence` | `GET /changes/{changeId}/evidence` | SessionAuth, `cases.read` | `cases/evidence.py` |
| `addEvidence` | `POST /changes/{changeId}/evidence` | SessionAuth, `cases.contribute` | `cases/evidence.py` |
| `downloadEvidence` | `GET /evidence/{evidenceId}/download` | SessionAuth, `cases.read` | `cases/evidence.py` |
| `removeEvidence` | `DELETE /evidence/{evidenceId}` | SessionAuth, `cases.work` | `cases/evidence.py` |
| `requestSignoff` | `POST /changes/{changeId}/signoff/request` | SessionAuth, `cases.work` | `cases/signoff.py` |
| `approveSignoff` | `POST /changes/{changeId}/signoff/approve` | SessionAuth, `cases.signoff`, `@requires_step_up` | `cases/signoff.py` |
| `sendBackSignoff` | `POST /changes/{changeId}/signoff/send-back` | SessionAuth, `cases.signoff` | `cases/signoff.py` |
| `getCaseFile` | `GET /changes/{changeId}/case-file` | SessionAuth, `cases.read` | `cases/case_file.py` |

`exportActionsAsTickets` is **not** declared (ruling 3).

Schemas, camelCase through `CamelSchema`, reusing chunk 5's `Urgency`, `UserRef`, `SoWhat` and `CaseStatus` rather than restating them:
- `Case` as designed, plus `subStatus|null`, `ownerTeam|null` and `version`: `{id, status, subStatus, urgency, footprintMatch, owner, ownerTeam, soWhat, triagedBy, triagedAt, dismissedReason, dismissedBy, signoffRequestedBy, signoffRequestedAt, signedOffBy, closeReason, closedNote, closedAt, assessment, actions, evidence, openActionCount, canRequestSignoff, allowedTransitions, version}`. Every vocabulary field is `{key, kind, label}` on reads and a `key` on writes.
- `Assessment` and `AssessmentInput` without `contributors` (ruling 2); `AssessmentInput` and `TriageInput` gain optional `subStatus` (ruling 8).
- `Action`, `ActionInput`, `ActionPatch`, `Evidence` (plus `scanState` and `contentHash`), `EvidenceInput`, `EvidenceCreated` (without `uploadUrl`, ruling 4). `DownloadLink` is not declared (ruling 5).
- `Reason`, `Note` and `CloseInput` take a `reasonKey` where the design took free text, because a reason is a vocabulary row.

Also:
- Extend the `Case` block on chunk 5's `GET /changes/{changeId}` with the workflow fields and `allowedTransitions`, computed by `state.allowed_transitions` (key `watchapi`). No screen ever guesses a transition.
- `cases/logic.py` holds only the shared case loader (`load_case(change_id)` under row-level security, 404 across tenants), the `If-Match` check raising 409 `stale_write`, and `transition(case, to_status, *, by, note)`, which calls `state.check_transition`, writes the `case_transition` row and the `record()` row in one transaction, and bumps `version`. Nothing else.
- Add the seventeen routes to the route lists in `apps/shared/permissions.py` and `routes.py`, and a factory per route in `apps/shared/factories.py` building its subject on a tenant-private record, so `tests_tenant_isolation` covers every one. Add no entry to `UNGATED_BY_DESIGN`.
- Write the INPUT_DELTAS rows for rulings 3, 4, 5 and 8, each naming the task that closes it, and add the seventeen operations to `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/cases/api.py`, `schemas.py`, `logic.py`
- `backend/apps/cases/{triage,assessment,actions,evidence,signoff,case_file}.py` (the `not_built` stubs only)
- `backend/apps/cases/tests_contract.py`
- `backend/apps/watch/api.py`, `schemas.py` (the `Case` block on the change read only)
- `backend/config/api.py` (the router mount only)
- `backend/apps/shared/permissions.py`, `routes.py`, `factories.py` (the route lists and one factory per route)
- `backend/scripts/contract_drift_pending.txt`, `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- The seventeen operations appear in `openapi.json` with the ids above and answer 501 `not_built` behind their real gate.
- A session without the permission gets 403 with `requiredPermission`, and an anonymous request gets 401 — both before the 501, proved per route.
- `approveSignoff` without a fresh assertion answers 403 `step_up_required` before the 501, proved.
- An API key reaches none of the seventeen: each answers 401, proved by one parametrised test.
- `GET /changes/{changeId}` carries `allowedTransitions` from `state.py`, and a test proves no transition table exists outside `state.py`.
- The route-permission guard is green and lists no ungated route; `tests_tenant_isolation` passes with a factory for every new route.
- `contract_drift.py` reports the seventeen as delivered-in-part, and no line is deleted yet.
- `bash generate-types.sh` produces types for all seventeen without the task committing them.
- The diff stays inside the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.watch apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/*'` (`api.py` >= 95)
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`; schemas in `schemas.py`.
- Every route has a permission; nothing joins `UNGATED_BY_DESIGN`; no scope reaches a case.
- Step-up on sign-off, per playbook 4.2.
- Errors are RFC 9457 with a `code`; no trace ever leaves; an empty answer is 200.
- The API returns `key` and `kind`, never a phrase.

### c9-reference-members: the member picker filtered by permission

**Requirements:** CAS-02, CAS-04
**Scenarios:** none
**Depends on:** `f03-T55`, `c9-case-contract`

The owner picker on triage needs the members who could own a case, the action picker the same, and the sign-off panel the members who hold `cases.signoff`. Parallel-plan ruling 11 gives `c9-case-contract` a new `GET /reference/members?permission=`; ruling 7 here makes it a filter on the reference read PRD 0.3 already declares, because two reference reads over the same member rows would duplicate one another.

- The app is `identity` (ruling 7), beside `GET /reference/permissions` and the member rows the filter reads, and the task holds the `idapi` key for as long as it runs. If `main` shows the route somewhere else when the task starts, that is a contract question: stop and report rather than move the route.
- Add one optional query parameter, `permission=<key>`, validated against `TENANT_PERMISSIONS` with 422 `unknown_key` and the valid keys. It narrows the array to active members whose roles hold that permission, computed the way `build_principal` computes a session's permissions, so the picker and the server agree about who may act.
- The response shape does not change: ids and names only, a plain array, no email, no title, no role list. Adding the filter must not turn a reference read into a roster: a test asserts the field set is unchanged.
- The read writes nothing and records nothing.

Write the test first: the filter for `cases.work`, `cases.signoff` and a permission nobody holds (an empty array, 200, not 404); an unknown key; a deactivated member excluded; another tenant's member never returned.

**Owned paths:**

- `backend/apps/identity/api.py`, `schemas.py` and `me_logic.py` (key `idapi`; the people read only)
- `backend/apps/identity/tests_reference_members.py` (new)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `GET /reference/people?permission=cases.signoff` returns exactly the active members whose roles hold it, by the same computation as `build_principal`, proved by a test that composes a custom role.
- An unknown permission key answers 422 `unknown_key` with the valid keys; a permission nobody holds answers 200 with an empty array.
- The field set is unchanged and no email, title or role reaches the response.
- A second tenant's members never appear; the tenant-isolation guard is green.
- The read writes no audit row and no bookmark, proved.
- `contract_drift.py` is clean for the operation, and its INPUT_DELTAS row records the filter and the reason ruling 11 was served this way.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/me_logic.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- Permissions, never role names.
- A read writes nothing and records nothing.
- `tenancy.activate()` after auth; the list is read under row-level security.
- No tenant content in logs: a member's name and id are the most that travels.

### c9-e2e-seed: cases in every stage, anchored to the seed's clock

**Requirements:** CAS-02, CAS-03, CAS-04, CAS-05, CAS-06, CAS-07
**Scenarios:** none
**Depends on:** `c9-case-models`, `c9-evidence-model`, `c5-seed-watch`

Extend `backend/apps/shared/e2e_seed.py` with the case data every chunk 9 journey needs, idempotent, deterministic and realistic, from the prototype's data (CLAUDE.md §11). One seed call, added to the ledger:

- Tenant A: one case in `new` (the lead change J-2 triages), one in `assigned` (J-3's start), one in `assessing` with a saved assessment, one in `implementing` with two actions — one done, one open and due relative to the anchor — and one piece of `clean` evidence, one in `signoff` requested by the owner (so CAS-S9's self sign-off is refusable), one `closed` with a full trail for the case file, and one `dismissed` with its reason key.
- Evidence in each scan state: `clean`, `pending` and `infected`, so the journeys can assert the invisible and refused states without waiting for a worker.
- Tenant B: one case on the same shared change, with its own evidence, so CAS-S16 and TEN-S7 have something to be refused.
- The `owner`, `approver`, `contributor` and `compliance_officer` logins already exist in `e2e_logins.py`; this task adds none. It adds team membership for "Legal" so CAS-S17 and HOM-S14 have a team participant to find.
- Every date is derived from the seed's anchor plus a fixed offset, never from the real today (plan-wide rule 10): "due yesterday", "due in 40 days", "came into force last month".
- File bytes are written through `shared/storage.py` into the slot's own media root, never committed to the repository.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (one seed call)
- `backend/apps/shared/tests_seed_integrity.py` (its own assertions only)
- `backend/apps/cases/tests_seed_cases.py`

**Done when:**

- `seed_e2e` run twice changes nothing the second time, proved by a row-count and content comparison.
- Every seeded date is derived from the anchor; a test freezes the clock at a quarter boundary and at a year boundary and the seed is unchanged.
- One case sits in each of the seven categories, and the `signoff` case's requester holds `cases.signoff` so CAS-S9 is reachable.
- Evidence exists in all three scan states, and the `infected` row has no bytes in storage.
- Tenant B's case is on the same change and is invisible to tenant A, proved by a seed-integrity assertion.
- The seed writes through `record()` where a real write would, so the audit trail a seeded case file prints is real.
- No file bytes are added to the repository.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py seed_e2e --settings=config.test_settings` twice
- `./run.sh run coverage run manage.py test apps.shared apps.cases --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- The seed is extended, never mocked: idempotent, deterministic, realistic and time-anchored.
- Tenant isolation holds in the seed as in the app.
- Nothing overwritten: seeded evidence is soft-deletable only.

### c9-triage: confirm, dismiss and restore

**Requirements:** CAS-02, CAS-08
**Scenarios:** CAS-S2, CAS-S3, VOC-S10 (the dismissal and closure half), TEN-S3 (the case half) — all `@integration`
**Depends on:** `c9-case-contract`, `c10-collab-models`

Build `backend/apps/cases/triage.py` and serve the three triage routes:

- `triageChange`: `new → assigned`. `urgency` and `ownerId` are required, and a missing owner answers 422 naming the field (CAS-S2). Optionally `ownerTeamId` beside the owner, and an optional `subStatus` key (ruling 8). It sets `triaged_by` and `triaged_at`, moves the case through `logic.transition()`, and notifies the owner through `c10-collab-models`'s `notify()` under D-34's recipient check.
- `dismissChange`: `new → dismissed`. A missing reason answers 422; an unknown reason key answers 422 `unknown_key` with the valid keys of the tenant's `dismissal_reason` list (VOC-S10). It sets `dismissed_reason`, `dismissed_by` and `dismissed_at`, and the case leaves the open list.
- `restoreChange`: `dismissed → new`. It clears the three dismissal columns, and both moves are in the audit trail and in `case_transition` (CAS-S3).
- Every response carries the full `Case` with `allowedTransitions` from `state.py`. Every write takes `If-Match` and answers 409 `stale_write` on a stale version.
- TEN-S3's case half: a case owned by a team keeps its team owner when one of the team's members is removed from the tenant, and nothing needs reassignment. The test drives the removal through `c8-ten-reassignment`'s logic, not a fixture.

Write each test first, in `apps/cases/tests_scenarios.py` (un-skipping only its own lines) and `apps/cases/tests_triage.py`.

**Owned paths:**

- `backend/apps/cases/triage.py`
- `backend/apps/cases/tests_triage.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S2 and CAS-S3 skip lines only)
- `backend/apps/taxonomy/tests_scenarios.py` (the VOC-S10 skip line only)
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S3 skip line only)
- `backend/apps/cases/app.md` (the CAS-02 status cell only)
- `backend/scripts/contract_drift_pending.txt` (its own three lines)

**Done when:**

- `test_cas_s2`, `test_cas_s3`, `test_voc_s10` and `test_ten_s3` are green and un-skipped.
- Triage without an owner answers 422 naming the field; with an owner it moves the case, notifies once, and the response's urgency renders as the `warning` tone for "Within 3 months" through the pill contract.
- A dismissal without a reason answers 422 and with an unknown key answers 422 `unknown_key` listing the valid keys.
- Restore returns the case to `new`, and the audit trail and `case_transition` show both moves with their actors.
- An `If-Match` mismatch answers 409 `stale_write` on all three routes.
- A second tenant's case answers 404 on all three; the tenant-isolation guard is green.
- One notification per person per event, through `notify()`; chunk 9 defines no recipient rule of its own, proved by a test that a member without `cases.read` is not notified.
- `apps/cases/triage.py` holds 95% statement coverage and its three `contract_drift_pending.txt` lines are deleted.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.taxonomy apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/triage.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Every write goes through `record()` in the same transaction; `If-Match` on a versioned record.
- Store and compare keys, never labels; the API returns `key` and `kind`.
- The state machine's categories and guards are fixed; a sub-status never reaches a guard.
- `tenancy.activate()` after auth; another tenant's case is 404, never 403.

### c9-assessment: the impact assessment

**Requirements:** CAS-03, CAS-08
**Scenarios:** CAS-S4 (reworded), CAS-S5, CAS-S13 — all `@integration`
**Depends on:** `c9-case-contract`

Build `backend/apps/cases/assessment.py` and serve `startAssessment`, `saveAssessment` and — once q-case-close is answered — `closeWithoutAction`:

- `startAssessment`: `assigned → assessing`, creating the `impact_assessment` row at version 1. `cases.work`.
- `saveAssessment`: stores `applies`, `why`, `what_must_change`, `internal_deadline`, `effort` (a key from the tenant's `effort_size` list) and the optional `subStatus`. A save without a `why` answers 422 (the `CHECK (NOT saved OR why IS NOT NULL)` is the database's half). `applies = yes` or `partly` moves `assessing → implementing`. `cases.contribute`, so a contributor may save input (PRD §6).
- `If-Match` carries the assessment's `version`. The owner saving at version 2 succeeds and the version becomes 3; a contributor saving at version 2 afterwards answers 409 `stale_write` and nothing is merged (CAS-S5, AC-CAS2). The refusal carries the current version so the screen can offer a reload.
- CAS-S13: a case set to the tenant's sub-status "Waiting for legal" under `assessing` is treated as `assessing` by every guard; `allowed_transitions` is identical with and without the sub-status, and the sign-off rules are unchanged. A sub-status from another category answers 422 `unknown_key`.
- CAS-S4 is reworded here: the contributor-teams clause moves out (ruling 2) and the scenario names CAS-S17 for it. The `applies = no` clause is left out of the Gherkin until q-case-close is answered, and `c9-close-paths` adds it back with whichever option Alex picks.
- `closeWithoutAction` and the `applies = no` branch answer 501 `not_built` until `c9-close-paths`; the task states that in its commit body and leaves its two `contract_drift_pending.txt` lines.

**Owned paths:**

- `backend/apps/cases/assessment.py`
- `backend/apps/cases/tests_assessment.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S4, CAS-S5 and CAS-S13 skip lines only)
- `backend/apps/cases/app.md` (the CAS-03 status cell and the CAS-S4 rewording only)
- `backend/scripts/contract_drift_pending.txt` (its own lines)

**Done when:**

- `test_cas_s4`, `test_cas_s5` and `test_cas_s13` are green and un-skipped; CAS-S4's reworded Gherkin names CAS-S17 for contributor teams and carries no `applies = no` clause.
- A save without a `why` answers 422, and the database refuses the same row if the check is bypassed, proved by a direct insert.
- The concurrent save answers 409 `stale_write` with the current version, and a test proves no field of the first save was lost.
- `effort` and `subStatus` are stored as keys; an unknown key answers 422 `unknown_key` with the valid keys.
- With a sub-status set, `allowed_transitions` and every guard return exactly what they return without it, proved by a parametrised test over all seven categories.
- `AssessmentInput` carries no `contributors`, proved by a schema test.
- A second tenant's case answers 404; the tenant-isolation guard is green.
- `apps/cases/assessment.py` holds 95% statement coverage on the lines it built, and the two close lines remain in `contract_drift_pending.txt` with q-case-close named.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/assessment.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Concurrent edits are refused, never merged: `If-Match` and 409 `stale_write`.
- Every write goes through `record()` in the same transaction.
- Store and compare keys, never labels.
- A question touching an invariant is not decided by the task: the close paths wait for Alex.

### c9-actions: actions with an owner, a due date and a lock

**Requirements:** CAS-04, CAS-08
**Scenarios:** CAS-S6 (reworded), TEN-S5 (the case and action half) — both `@integration`
**Depends on:** `c9-case-contract`, `c8-ten-reassignment`

Build `backend/apps/cases/actions.py` and serve the four action routes:

- `listActions` (`cases.read`), `addAction` (`cases.work`), `updateAction` (`cases.contribute`, for edit, complete and reopen) and `deleteAction` (`cases.work`).
- A title is required; `ownerId` defaults to the case owner; `dueDate` is a plain date in the tenant's timezone. `CASE_ACTIONS_MAX` caps a case's actions, and the cap answers 409 `too_many_actions`.
- Adding the first action moves `assessing → implementing` through `logic.transition()`; the response's `allowedTransitions` and `openActionCount` say so.
- **The lock:** while the case category is `signoff`, `updateAction`, `addAction` and `deleteAction` answer 409 `actions_locked`. The check reads the category, never a sub-status. CAS-S6's clause is reworded from "when sign-off is requested" to "when the case moves to waiting for sign-off", so it is about the state and not about a route this task does not own; the test drives the move through `logic.transition()`, which is the real code path.
- CAS-S6 is also reworded to drop its "Send as tickets" clause, which names `c13-tickets-export` and INT-S3 instead (ruling 3), and to gain a delete line, because `deleteAction` had a route, a control and a confirm dialog but no scenario (CLAUDE.md §10): deleting an action removes it from the list, writes its audit row, and lowers `openActionCount`. Because that half of CAS-04 is not built here, the status cell moves to `in_progress`, never `built`, and names `c13-tickets-export`; `c9-close` leaves it there.
- TEN-S5's case and action half: a member who owns two open cases and their actions appears in the removal screen's open-work list by kind, and confirming reassigns each with one audit row per item, in one transaction. `c9-actions` adds the case and action rows to the list `c8-ten-reassignment` built; if chunk 8 left TEN-S5 skipped, this task un-skips it.

**Owned paths:**

- `backend/apps/cases/actions.py`
- `backend/apps/cases/tests_actions.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S6 skip line only)
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S5 skip line only)
- `backend/apps/cases/app.md` (the CAS-04 status cell and the CAS-S6 rewording only)
- `backend/config/settings.py` (the `CASE_ACTIONS_MAX` banner), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/scripts/contract_drift_pending.txt` (its own four lines)

**Done when:**

- `test_cas_s6` and `test_ten_s5` are green and un-skipped; CAS-S6's reworded Gherkin names chunk 13 for tickets and states the lock as a property of the category.
- An action without a title answers 422; the first action moves the case to `implementing`; `openActionCount` matches the rows, before and after a delete.
- With the case in `signoff`, all three writes answer 409 `actions_locked`, and `listActions` still answers 200.
- The cap answers 409 `too_many_actions` at `CASE_ACTIONS_MAX + 1`, and the number is a setting with an env override.
- Reassignment through `c8-ten-reassignment` moves the cases and the actions in one transaction with one audit row per item, proved.
- A second tenant's action answers 404 on `PATCH` and `DELETE` by id; the tenant-isolation guard is green.
- `apps/cases/actions.py` holds 95% statement coverage, and its four `contract_drift_pending.txt` lines are deleted.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/actions.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- The guards read a category, never a sub-status.
- Every write goes through `record()`; `If-Match` on a versioned record.
- Every cap is a setting with an env override; a test's number is a fixture.
- Another tenant's row is 404, never 403.

### c9-evidence: attach, scan, hash and stream

**Requirements:** CAS-05
**Scenarios:** CAS-S7 (`@integration`)
**Depends on:** `c9-case-contract`, `c9-evidence-model`, `c9-scanner-adapter`
**Security review:** yes (upload, untrusted bytes, a file-serving route)
**Stop and report** on any invariant question.

Build `backend/apps/cases/evidence.py` and `backend/apps/cases/tasks.py`, and serve the four evidence routes. This is the chunk's one task above forty-five minutes: CAS-S7 is a single scenario over one security surface — attach, allow-list, hash, scan, stream, audit — and splitting it would leave two tasks each proving half of it.

- `addEvidence` (`cases.contribute`): `kind` is `file`, `link` or `reference`.
  - `file` arrives as `multipart/form-data` (ruling 4). The server computes the SHA-256 content hash and the size from the bytes it received, never from the client's claim, and checks the MIME type by sniffing as well as by header. A type outside `EVIDENCE_ALLOWED_TYPES` or a size above `EVIDENCE_MAX_BYTES` answers 422 with the allow-list and the cap in the refusal, before a byte reaches storage.
  - The bytes go to `shared/storage.py` under a key derived from the tenant, the case and a random component, never from the filename. The row is created with `scan_state = pending` and `scan_evidence(evidence_id)` is queued as a `@tenant_task`.
  - `link` stores the URL and fetches nothing: fetched content is untrusted and nothing here needs it. `reference` stores a name only.
- `scan_evidence`: reads the bytes, calls `get_scanner()`, and writes `scan_state` and `scanned_at` through `record()`. On `infected` it deletes the bytes from storage and keeps the row, its name and its hash. On `error` it retries up to `EVIDENCE_SCAN_RETRIES`, then stays `error`. The task never logs a filename.
- `listEvidence` (`cases.read`): every row with its kind, name, size, type, hash, `scanState`, who attached it and when. A `pending` or `infected` row is listed — a bank must see that a file was refused — but carries no download control.
- `downloadEvidence` (`cases.read`): streams the bytes with `Content-Disposition: attachment`, a `no-store` cache header and the stored MIME type, never `text/html`. It answers 409 `scan_pending` while the scan runs, 422 `scan_failed` for `infected` or `error`, 404 for a removed row and 404 across tenants. One `record()` row per download, naming the evidence and the reader (D-11); a test proves exactly one row per call and none on a refusal.
- `removeEvidence` (`cases.work`): sets `removed_at` only. The row, its name and its hash stay for the case file.
- Settings under one banner naming CAS-05: `EVIDENCE_ALLOWED_TYPES` (PDF, DOCX, XLSX, PPTX, PNG, JPEG, TXT, CSV), `EVIDENCE_MAX_BYTES` (25 MB), `EVIDENCE_SCAN_RETRIES`, `CASE_EVIDENCE_MAX`.

**Owned paths:**

- `backend/apps/cases/evidence.py`, `backend/apps/cases/tasks.py`
- `backend/apps/cases/tests_evidence.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S7 skip line only)
- `backend/apps/cases/app.md` (the CAS-05 status cell only)
- `backend/config/settings.py` (one banner), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/scripts/contract_drift_pending.txt` (its own four lines)

**Done when:**

- `test_cas_s7` is green and un-skipped: a PDF, a link and a reference are attached; the file carries a content hash; it is not downloadable until the scan passes; a file outside the size or type allow-list answers 422; a download streams through the API, the permission is checked and one audit row records it.
- The hash and the size are computed from the received bytes; a test sends a wrong `contentHash` and `sizeBytes` and the server's own values win.
- A file whose extension says PDF and whose bytes say HTML is refused, proved.
- An EICAR upload ends `infected`, its bytes are gone from storage, its row and hash remain, and a download answers 422 `scan_failed`.
- A scan `error` retries and then stays `error`; a download of it is refused.
- Removing evidence sets `removed_at`, leaves the row readable in the case file, and a hard delete is impossible.
- No filename, path or byte reaches a log record or Sentry, proved by a log-capture test over the upload, the scan and the download.
- A second tenant's evidence answers 404 on list, download and remove, and no audit row records the attempt.
- `apps/cases/evidence.py` and `tasks.py` hold 95% statement coverage; the four `contract_drift_pending.txt` lines are deleted.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/evidence.py,apps/cases/tasks.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Uploaded content is untrusted: the server measures it, never the client's claim; a file is invisible until it has been scanned.
- Evidence is soft-deleted; the audit trail keeps the name.
- One permission check and one audit row per download (D-11); no presigned link.
- `@tenant_task` in the worker; every write through `record()` in the same transaction.
- No tenant content in logs or Sentry: a filename is tenant content.

### c9-case-file: the case file as text

**Requirements:** CAS-07, NFR-01
**Scenarios:** CAS-S16 (`@integration`)
**Depends on:** `c9-case-contract`, `c9-assessment`, `c9-actions`, `c9-evidence`

Build `backend/apps/cases/case_file.py` and serve `getCaseFile` (`cases.read`, `text/plain`):

- One composed document that stands alone: the change with its identifier, authority, dates and source label; the confirmed So what, or the AI draft with its label (WAT-05); the assessment with every field and who saved it when; the actions with owner, due date and completion; the evidence list with kind, name, hash, scan state and who attached it; the sign-off with both names and the step-up reference; the dismissal reason where there is one; and every date in the tenant's timezone with an explicit offset.
- One query plan, never a chain: the case, its children and the change are fetched in a fixed number of queries pinned by a test, so a case at `CASE_ACTIONS_MAX` and `CASE_EVIDENCE_MAX` stays inside the 250 ms budget.
- The text carries no requirement id, no internal column name and no permission name. It is written from the `caseFile` message catalog in the reader's language, so the same builder serves the export.
- CAS-S16: tenant B fetching tenant A's case, its evidence file and its case file gets 404 on each, and no audit row records a download.

**Owned paths:**

- `backend/apps/cases/case_file.py`
- `backend/apps/cases/tests_case_file.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S16 skip line only)
- `backend/apps/cases/app.md` (the CAS-07 status cell only)
- `backend/scripts/contract_drift_pending.txt` (its own line)

**Done when:**

- `test_cas_s16` is green and un-skipped: the case, the evidence file and the case file each answer 404 for tenant B, and no audit row is written.
- A closed case's file names the change, the So what, the assessment, the actions with completion, the evidence with hashes, both sign-off names and every date.
- An unconfirmed So what appears with its AI label and is never presented as the bank's text, proved.
- A removed piece of evidence appears with its name, hash and removal date; nothing disappears from the file.
- The query count is pinned, and a case at both caps is served inside the 250 ms budget, measured with `Server-Timing: app`.
- Every string comes from the message catalog; a test asserts no literal sentence in the module.
- `apps/cases/case_file.py` holds 95% statement coverage, and its `contract_drift_pending.txt` line is deleted.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/case_file.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Another tenant's record is 404, never 403, and a refused read writes nothing.
- AI output is labelled until a person confirms it.
- Fan out, never chain; every endpoint under 250 ms.
- Nothing overwritten: a removed piece of evidence is still in the file.

### c9-signoff-request: asking for sign-off, and the two refusals

**Requirements:** CAS-06
**Scenarios:** CAS-S8 (`@integration`)
**Depends on:** `c9-case-contract`, `c9-actions`, `c9-evidence`, `c10-collab-models`

Build the `request_signoff` half of `backend/apps/cases/signoff.py` and serve `requestSignoff` (`cases.work`):

- `implementing → signoff`, through `logic.transition()` and `state.check_transition`, so the guards live in one place.
- An open action answers 409 `open_actions` with the count beside the code; no evidence answers 409 `evidence_missing`. Evidence that exists but has not passed the scan does not count: a `pending` or `infected` row leaves the case with `evidence_missing`, because "at least one piece of evidence" means one a reader can open.
- It sets `signoff_requested_by` and `signoff_requested_at`, and notifies the holders of `cases.signoff` through `notify()` under D-34's recipient check. The requester appears only as the name of who asked.
- `Case.canRequestSignoff` is computed from the same guard, so the screen and the server never disagree.
- Once the case is in `signoff`, `c9-actions`'s lock takes effect; a test here proves the lock from the route's own side.

Write `test_cas_s8` first: one open action and no evidence gives `open_actions`; the action completed gives `evidence_missing`; evidence attached and scanned gives `signoff`, and the status label reads "Waiting for sign-off".

**Owned paths:**

- `backend/apps/cases/signoff.py` (the request half only)
- `backend/apps/cases/tests_signoff_request.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S8 skip line only)
- `backend/scripts/contract_drift_pending.txt` (its own line)

**Done when:**

- `test_cas_s8` is green and un-skipped, with all three steps.
- `open_actions` carries the count and `evidence_missing` carries zero, each as evidence beside the code (playbook 4.4).
- Unscanned and infected evidence does not satisfy the guard, proved by two tests.
- `canRequestSignoff` equals the guard's answer on every seeded case, proved by a parametrised test.
- Requesting twice answers 409 `invalid_transition`, from `state.py` and not from a second rule.
- The approvers are notified once each, and a member without `cases.signoff` is not, through `notify()`.
- A second tenant's case answers 404; the request half of `apps/cases/signoff.py` holds 95% statement coverage and its `contract_drift_pending.txt` line is deleted.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/signoff.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- The guards are fixed and live in `state.py`; no route restates one.
- Every refusal carries a `code` and its evidence; no trace ever leaves.
- Every write through `record()`; `If-Match` on a versioned record.
- One notification per person per event, through the one recipient check.

### c9-signoff: a second person signs off, with a step-up

**Requirements:** CAS-06, CAS-08
**Scenarios:** CAS-S9, CAS-S10, CAS-S12 (reworded), CAS-S18 (new) — all `@integration`
**Depends on:** `c9-signoff-request`, `c9-assessment`, `c10-collab-models`
**Security review:** yes (four eyes and step-up)
**Stop and report** on any invariant question.

Build the approve and send-back halves of `backend/apps/cases/signoff.py`:

- `approveSignoff` (`cases.signoff`, `@requires_step_up`): `signoff → closed` with `close_reason = signed_off`, `signed_off_by`, `closed_note` and `closed_at`. The requester is refused with 409 `four_eyes_violation` **before** anything is written, and the database CHECK is the second line of defence, not the first. The audit row carries the step-up assertion id (AC-ID3).
- `sendBackSignoff` (`cases.signoff`): `signoff → implementing` with a note. No step-up: it is the safe direction and playbook 4.2 does not list it. It clears `signoff_requested_by` and `signoff_requested_at` so the next request is a fresh one, and unlocks the actions.
- Closing a case writes nothing to the library and nothing to the register: a test asserts no library or register row changed across the whole call, which is CAS-S10's last line and the "closing a case never edits the inventory" rule of `cases/app.md` §1.
- CAS-S18 is added here, as CLAUDE.md §10 requires for behaviour the PRD's scenarios did not cover: "Given a case waiting for sign-off with two completed actions / When the approver chooses 'Send back' with a note / Then the case reads implementing, the actions can be edited again, the note is in the audit trail, and a fresh sign-off request is possible". Send-back had a route, a button and a screen state but no scenario.
- CAS-S12 is reworded here: "Given a case in assessing / When it is read / Then `allowedTransitions` lists exactly the categories the guards permit from assessing / When a client posts the sign-off approval, which the machine does not allow from assessing / Then the request answers 409 `invalid_transition`". The original's "posts a transition to closed directly" named no route the contract has; this names one.

**Owned paths:**

- `backend/apps/cases/signoff.py` (the approve and send-back halves)
- `backend/apps/cases/tests_signoff.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S9, CAS-S10 and CAS-S12 skip lines, and the new CAS-S18 test)
- `backend/apps/cases/app.md` (the CAS-06 and CAS-08 status cells, the CAS-S12 rewording and the new CAS-S18 Gherkin)
- `backend/scripts/contract_drift_pending.txt` (its own two lines)

**Done when:**

- `test_cas_s9`, `test_cas_s10`, `test_cas_s12` and the new `test_cas_s18` are green.
- The requester holding `cases.signoff` is refused 409 `four_eyes_violation` and nothing is written, proved by a row-count comparison across the call.
- A fresh assertion is required: without one the route answers 403 `step_up_required` before any guard runs, and the completed sign-off's audit row carries the assertion id.
- The database CHECK refuses `signed_off_by = signoff_requested_by` on a direct insert, so the API check is not the only one.
- No library or register row changes during a sign-off, proved by a snapshot of both zones.
- Send-back returns the case to `implementing`, unlocks the actions, clears the request columns and leaves its note in the audit trail (CAS-S18), and a second sign-off request then succeeds.
- `allowedTransitions` from `assessing` equals `state.allowed_transitions` exactly, and the sign-off approval from `assessing` answers 409 `invalid_transition`.
- `tests_four_eyes` and `tests_audit_on_write` are green; `apps/cases/signoff.py` holds 95% statement coverage and its two `contract_drift_pending.txt` lines are deleted.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/signoff.py'`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_four_eyes apps.shared.tests_audit_on_write apps.shared.tests_library_fence --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Four eyes, enforced by a check constraint, with a passkey step-up on sign-off; the approver is never the requester.
- Closing a case never edits the library or the register; that is a proposal.
- The assertion reference is stored on the audit event.
- Every refusal is RFC 9457 with a `code`.

### c9-close-paths: closing without action, once Alex has answered

**Requirements:** CAS-02, CAS-06
**Scenarios:** none of its own; it adds the close clause back to CAS-S4, which `c9-assessment` owns and already un-skipped
**Depends on:** `c9-assessment`, `c9-signoff`, **q-case-close**
**Security review:** yes (the four-eyes close decision: one route can take a regulatory change out of the workflow)
**Stop and report** on any invariant question.

Build whichever option Alex picks for q-case-close, and only that one:

- **Option A:** `closeWithoutAction` and `saveAssessment` with `applies = no` move the case to `signoff` carrying its intended close reason (`no_action` or `not_applicable`), with the open-action and evidence guards lifted for those two reasons. `approveSignoff` then closes it with that reason instead of `signed_off`, keeping the four-eyes check and the step-up. No new state, no new route, no new permission.
- **Option B:** both paths close the case directly under `cases.work`, with the reason key required, the audit row naming the actor, and the case restorable to triage.
- **Option C:** `applies = no` takes Option A's path and `closeWithoutAction` takes Option B's.

Whichever it is: add the close clause back to CAS-S4's Gherkin, delete the two `contract_drift_pending.txt` lines `c9-assessment` left, record the answer in `docs/DECISIONS.md` with an ADR, and write the INPUT_DELTAS row where the behaviour departs from `openapi.yaml`.

**Owned paths:**

- `backend/apps/cases/assessment.py` (the close branch only), `backend/apps/cases/signoff.py` (Option A's close reason only)
- `backend/apps/cases/tests_close_paths.py`
- `backend/apps/cases/tests_scenarios.py` (the CAS-S4 line only), `backend/apps/cases/app.md` (the CAS-S4 close clause only)
- `docs/DECISIONS.md`, `docs/adr/` (one ADR), `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt` (the two close lines)

**Done when:**

- Neither close route answers 501, and `contract_drift.py` is clean for both.
- The chosen option's rule is proved end to end, and the two options not chosen have no code in the tree.
- Under Option A or C, a close as `not_applicable` is refused for the requester with 409 `four_eyes_violation` and needs a step-up.
- Under Option B or C, the one-person close writes its reason key, its audit row and its `case_transition` row, and the case is restorable.
- CAS-S4's Gherkin and `test_cas_s4` carry the close clause, and `requirements_coverage.py` is green.
- The ADR and the `DECISIONS.md` row state what Alex chose and when.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/cases/assessment.py,apps/cases/signoff.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- An invariant question is answered by the owner, never by the build.
- Four eyes and step-up are never weakened to make a path simpler.
- A departure from the designed contract is written down in INPUT_DELTAS with its reason.

### c9-fe-cases-feature: the case feature and the panel mounts

**Requirements:** CAS-02 to CAS-07
**Scenarios:** none
**Depends on:** `c9-case-contract`, `c9-case-design`, `c5-fe-change-detail`

Build the frontend contract for the case panels, so five panel tasks can then run side by side:

- `frontend/src/features/cases/{types,api,hooks}.ts`: every chunk 9 operation, typed from `api.generated.ts`, with the query keys and the mutations, including the `If-Match` header on every write and the `stale_write` branch that offers a reload and never merges.
- `frontend/src/features/cases/case-presentation.ts` and its test: the status pill (the category's tone with the tenant's sub-status label, CAS-S13), the urgency pill (the row's own tone, D-48), the scan-state pill, the "days left" text on a due date, and the close-reason label. It reads `tone-by-kind.ts`'s one tone function and adds its entries there; it defines no second tone map.
- `frontend/src/components/cases/` with one component file per panel — `TriagePanel`, `AssessmentPanel`, `ActionsPanel`, `EvidencePanel`, `SignoffPanel`, `CaseFilePanel` — each a stub rendering nothing, each with a `// built by c9-fe-<name>-panel` marker.
- `frontend/src/components/watch/ChangeScreen.tsx` (key `changescreen`): one `CaseWorkPanels` container that branches on the case's status category and renders the stubs. This is the only chunk 9 edit to the change screen; no panel task touches it.
- The `cases` message namespace pair (en and sv) with the shared strings only: the seven status labels ("Needs triage", "Waiting for sign-off" and the rest), the panel headings, and the `stale_write` reload copy. Each panel task adds its own namespace.

**Owned paths:**

- `frontend/src/features/cases/` (all files)
- `frontend/src/components/cases/` (the six stubs)
- `frontend/src/components/watch/ChangeScreen.tsx`
- the `cases` message namespace pair in `frontend/src/messages/`
- `frontend/src/features/shared/tone-by-kind.ts` (its own entries)

**Done when:**

- The change screen renders `CaseWorkPanels` for a case in each of the seven categories, and every stub renders nothing without an error.
- `case-presentation.ts` has a unit test per pill: a sub-status renders the category's tone with the tenant's label; urgency renders the row's tone; a scan state renders `notice`, `positive` or `negative` by kind.
- No second tone map exists; `tone-by-kind.ts` gained only the chunk's own entries.
- Every write hook sends `If-Match`, and the `stale_write` branch is unit-tested against a 409.
- Every string resolves in en and sv; `check:messages` and `check:copy-drift` are green.
- The change screen still reaches real data within 500 ms against `next start`, and the chunk 5 journeys that walk it are still green.
- `frontend/src/features/cases/` holds the frontend coverage floor.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "WAT-S"` (the chunk 5 change-page journeys, because the screen changed)

**Invariants:**

- Pills only through `Pill` and a presentation function per record type; six tones, chosen by slot or kind.
- No string literals in JSX; typography roles only; `logger` only, never `console.log`.
- Concurrent edits are refused, never merged: the screen offers a reload.
- Measured against `next start`, never `next dev`.

### c9-fe-triage-panel: confirm, assign and dismiss

**Requirements:** CAS-02
**Scenarios:** none (`c9-e2e-triage-journeys` walks it)
**Depends on:** `c9-fe-cases-feature`, `c9-triage`, `c9-reference-members`

Build `frontend/src/components/cases/TriagePanel.tsx` from `design/screens/tenant-change.html`'s Triage panel:
- The urgency picker from the `urgency` vocabulary, the owner picker from `GET /reference/people?permission=cases.work`, "Confirm and assign" and "Dismiss".
- A confirm without an owner shows the server's 422 against the owner field, never a client-side rule of its own.
- The dismissal dialog with the tenant's `dismissal_reason` list and the refusal when no reason is given; "Move back to triage" on a dismissed case.
- The `caseTriage` message namespace pair in en and sv.
- Empty, loading, error, denied and permission-limited states: a reader without `cases.triage` sees the case and no triage controls, and no request answers 403.

**Owned paths:**

- `frontend/src/components/cases/TriagePanel.tsx` and its test
- the `caseTriage` message namespace pair in `frontend/src/messages/`

**Done when:**

- Every control of the design card's Triage panel is present, at 375 px and on a desktop, in both themes.
- The 422 without an owner and the 422 without a reason render where they happen, from the server's `errors[]`, not from a client rule.
- A reader without `cases.triage` sees no control and gets no 403; a reader without `cases.read` sees the permission-limited notice.
- Every string resolves in en and sv; the states render; the panel adds nothing to the change screen's 500 ms budget.
- The unit test covers each state and the refusal branches.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- Permissions decide what renders; the server's 403 stays the enforcer.
- Pills only through `Pill`; no string literals in JSX.
- Screen copy says what the user is doing: no requirement ids, no restated invariants.

### c9-fe-assessment-panel: the impact assessment

**Requirements:** CAS-03, CAS-08
**Scenarios:** none (`c9-e2e-work-journeys` walks it)
**Depends on:** `c9-fe-cases-feature`, `c9-assessment`

Build `frontend/src/components/cases/AssessmentPanel.tsx` from the design card's Impact assessment panel:
- Applies, why, what must change, an internal deadline and an effort picker from the tenant's `effort_size` list; "Start assessment" and "Save assessment and plan actions"; the optional sub-status picker from `case_sub_status`, filtered to the case's category.
- The `stale_write` state: the panel shows what the other person saved, offers a reload, and never merges (CAS-S5). It keeps the user's unsaved text visible so nothing is lost.
- The contributor-teams picker is **not** built here: `f03-T76` adds it when the case participant routes exist (ruling 2, plan-wide rule 5).
- The `caseAssessment` message namespace pair in en and sv, and every state.

**Owned paths:**

- `frontend/src/components/cases/AssessmentPanel.tsx` and its test
- the `caseAssessment` message namespace pair in `frontend/src/messages/`

**Done when:**

- A save without a why renders the server's 422 against the field.
- A 409 `stale_write` renders the reload offer, keeps the user's text and merges nothing, proved by a unit test against a 409 at the hook boundary (never a mocked API in E2E).
- The sub-status picker offers only the case's own category's rows.
- A contributor with `cases.contribute` can save; a reader sees the assessment read-only and no request answers 403.
- Every string resolves in en and sv; the states render; the panel stays inside the screen's budget.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- Concurrent edits are refused, never merged.
- Vocabularies are rows: the effort and sub-status pickers read the tenant's lists and store keys.
- No string literals in JSX; permissions decide what renders.

### c9-fe-actions-panel: actions and the lock

**Requirements:** CAS-04
**Scenarios:** none (`c9-e2e-work-journeys` walks it)
**Depends on:** `c9-fe-cases-feature`, `c9-actions`, `c9-reference-members`

Build `frontend/src/components/cases/ActionsPanel.tsx` from the design card's Actions panel:
- The list with owner, due date and "days left" at tabular numerals; the completion checkbox; the add row with title, owner picker and due date; "Add action" and the delete control with its confirm.
- The locked state while the case waits for sign-off: every control disabled with the reason in words, and a 409 `actions_locked` from a stale tab rendered where it happens.
- "Send as tickets" is not built: ruling 3 names `c13-fe-tickets-screen`.
- The `caseActions` message namespace pair in en and sv, and every state.

**Owned paths:**

- `frontend/src/components/cases/ActionsPanel.tsx` and its test
- the `caseActions` message namespace pair in `frontend/src/messages/`

**Done when:**

- Adding without a title renders the server's 422; the cap's 409 renders with the number from the response.
- The locked state disables every control and states why; a 409 `actions_locked` from a stale tab renders in place.
- An overdue due date renders in the `negative` tone through `Pill` and the presentation function, never from an inline colour.
- A contributor may complete and reopen an action but not add or delete one, and no request answers 403.
- Every string resolves in en and sv; the states render; the panel stays inside the screen's budget.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- Pills only through `Pill` and a presentation function; six tones, chosen by slot or kind.
- Permissions decide what renders; the server's 403 stays the enforcer.
- No string literals in JSX; typography roles only.

### c9-fe-evidence-panel: attach, see the scan, download

**Requirements:** CAS-05
**Scenarios:** none (`c9-e2e-work-journeys` walks it)
**Depends on:** `c9-fe-cases-feature`, `c9-evidence`

Build `frontend/src/components/cases/EvidencePanel.tsx` from the design card's Evidence panel:
- The list with kind, name, size, who attached it and when, and the scan-state pill; the attach dialog for a file, a link and a reference; remove with its confirm.
- A file upload is a multipart form post (ruling 4) with a progress state; the refusal states the allow-list and the cap from the server's response, not from a client copy of the list.
- A `pending` row shows "Being checked" with no download control; an `infected` or `error` row shows why and no download control. Only a `clean` row is downloadable.
- Download goes through the API: the browser follows the streaming endpoint, and nothing writes a URL to `localStorage`, the address bar or a log.
- The `caseEvidence` message namespace pair in en and sv, and every state.

**Owned paths:**

- `frontend/src/components/cases/EvidencePanel.tsx` and its test
- the `caseEvidence` message namespace pair in `frontend/src/messages/`

**Done when:**

- A file outside the allow-list or the cap renders the server's 422 with both stated, and the client never pre-filters with a second copy of the list.
- A `pending`, `infected` or `error` row has no download control, and the reason is in words.
- The scan-state pill comes from the presentation function, and its three tones are unit-tested.
- Nothing writes an evidence URL or a filename to `localStorage`, the URL or a log.
- A contributor may attach but not remove; a reader may download and do nothing else; no request answers 403.
- Every string resolves in en and sv; the states render; the panel stays inside the screen's budget.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- A file is not offered until it has been scanned.
- `logger` only, never `console.log`; no tenant content in a client log.
- Permissions decide what renders; pills only through `Pill`.

### c9-fe-signoff-panel: request, sign off, send back

**Requirements:** CAS-06
**Scenarios:** none (`c9-e2e-signoff-journeys` walks it)
**Depends on:** `c9-fe-cases-feature`, `c9-signoff-request`, `c9-signoff`

Build `frontend/src/components/cases/SignoffPanel.tsx` from the design card's Sign-off panel:
- "Request sign-off", disabled with the reason in words while an action is open or evidence is missing, and the server's 409 `open_actions` or `evidence_missing` rendered where it happens with the count from the response.
- The waiting state naming who requested it and when; "Sign off and close" with the passkey step-up prompt from the shared step-up flow; "Send back" with its note.
- The self sign-off refusal: 409 `four_eyes_violation` rendered as "a second person has to sign off", branching on the `code` and never on `detail`.
- The closed state with both names, the close reason and the date, and the link to the case file.
- The `caseSignoff` message namespace pair in en and sv, and every state.

**Owned paths:**

- `frontend/src/components/cases/SignoffPanel.tsx` and its test
- the `caseSignoff` message namespace pair in `frontend/src/messages/`

**Done when:**

- The request control's disabled reason matches `canRequestSignoff` from the server, and a stale tab's 409 renders in place with its count.
- The step-up prompt is the shared flow; the panel stores no assertion and no token.
- The self sign-off 409 renders from its `code`; a test asserts no branch reads `detail`.
- An approver who is not the requester completes the sign-off and the panel shows the closed state with both names.
- A member without `cases.signoff` sees the waiting state and no sign-off control, and no request answers 403.
- Every string resolves in en and sv; the states render; the panel stays inside the screen's budget.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- The client branches on `code`, never on `detail`.
- Step-up is the server's; the client holds no assertion.
- Permissions decide what renders; no string literals in JSX.

### c9-case-file-export: the case file as an export job

**Requirements:** CAS-07
**Scenarios:** CAS-S11 (`@integration`)
**Depends on:** `c9-case-file`, `c12-exports-contract`
**Security review:** yes (a job that writes a tenant's whole case to a file)

Add the case-file exporter on chunk 12's framework (parallel-plan ruling 7):

- One new `export_kind`, `case_file`, in `kinds.py`, and one exporter registered with `c12-exports-contract`'s registry. It calls `cases/case_file.py`'s builder, so the text on screen and the text in the file come from one place and cannot drift.
- `POST /exports` with `{kind: "case_file", changeId}` under `exports.create` and a step-up (playbook 4.2 lists exports), answering the job; `GET /exports/{id}` reports its status; `GET /exports/{id}/download` streams it, permission-checked and audited, under both `exports.create` and `cases.read` for that case.
- The export is text; no PDF library is added (parallel plan §7.2).
- A case in another tenant answers 404 at creation, and the job refuses to run for a tenant that is not its own.
- CAS-S11: a closed case's file shows the change, the So what, the assessment, the actions with completion, the evidence list with hashes, the sign-off with both people and every date; exporting it produces the same content and its download is permission-checked.

**Owned paths:**

- `backend/apps/reports/exporters/case_file.py` (or the module `c12-exports-contract` names)
- `backend/apps/reports/tests_export_case_file.py`
- `backend/apps/shared/kinds.py` (the `case_file` export kind only)
- `backend/apps/cases/tests_scenarios.py` (the CAS-S11 skip line only)
- `backend/apps/cases/app.md` (the CAS-07 status cell only)

**Done when:**

- `test_cas_s11` is green and un-skipped, both halves.
- The exported text is byte-identical to `GET /changes/{id}/case-file` for the same case and language, proved by a test comparing the two.
- Creating an export for another tenant's case answers 404, and the job refuses a tenant mismatch at run time as a second check.
- The download is permission-checked and writes one audit row; a reader without `cases.read` for that case is refused.
- The export is created under a step-up, and its audit row carries the assertion id.
- No PDF library appears in `pyproject.toml`; the dependency set is unchanged.
- The exporter holds 95% statement coverage.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/exporters/case_file.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- One builder, one text: the screen and the export cannot drift.
- Step-up on exports; one permission check and one audit row per download.
- Another tenant's record is 404, and the worker checks tenancy again.
- No dependency is changed by a task.

### c9-fe-case-file: the case file on screen

**Requirements:** CAS-07
**Scenarios:** none (`c9-e2e-j3` walks it)
**Depends on:** `c9-fe-cases-feature`, `c9-case-file`, `c9-case-file-export`

Build `frontend/src/components/cases/CaseFilePanel.tsx` from the design card's case-file view:
- "Show case file" opens the composed text in a readable layout with its sections, the evidence hashes at monospace, and the dates in the tenant's timezone.
- "Export" creates the job, shows its status, and offers the download when it is ready; a failed job says what failed without a trace.
- The `caseFile` message namespace pair in en and sv, and every state.

**Owned paths:**

- `frontend/src/components/cases/CaseFilePanel.tsx` and its test
- the `caseFile` message namespace pair in `frontend/src/messages/`

**Done when:**

- The case file renders for a closed case with every section of CAS-S11, at 375 px and on a desktop.
- The export job's queued, running, ready and failed states each render, and a failure shows no trace.
- A reader with `cases.read` but without `exports.create` sees the file and no export control, and no request answers 403.
- Every string resolves in en and sv; the panel reaches real data within 500 ms against `next start`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- Never expose a trace; the client branches on `code`.
- Permissions decide what renders; no string literals in JSX.
- Measured against `next start`, never `next dev`.

### f03-T76: case participants, and contributor teams as team participants

**Requirements:** CAS-03, COL-04
**Scenarios:** CAS-S17 (`@integration`), COL-S9 (`@integration`, `@e2e`)
**Depends on:** `f03-T55`, `c9-triage`, `c9-assessment`, `c9-fe-assessment-panel`
**Security review:** yes (participants, cross-tenant refusals)
**Stop and report** on any invariant question.

From `FEATURES_0_3_TASKS.md` (MY_WORK_AND_MARKETS T-39). It reuses `f03-T54`'s participant logic and adds no second rule:

- `GET`, `POST /changes/{changeId}/participants` and `DELETE /changes/{changeId}/participants/{participantId}` in `collab/api.py` (key `collabapi`). Adding needs `cases.contribute` (D-19); removing needs the same, except that a person may always remove their own row, which is gated in logic and listed with its reason.
- A member whose roles cannot read the case answers 422 `participant_cannot_read`; a user of another tenant answers 422 `unknown_member`; a repeat answers 409 `already_participant`; the cap answers 422 `too_many_participants` (D-18).
- A participant added to a closed case answers 409 `invalid_transition`, from `state.py` (COL-S9).
- Cross-tenant: a change private to tenant A gives tenant B 404; on a shared change, B's add lands on B's own case and A's list is unchanged; B removing A's participant by id gives 404.
- `cases/logic.py` (key `caseslogic`) gains the one hook the assessment needs: the contributor teams shown on the assessment are the case's team participants, read from `participant`, and the assessment stores no list (D-20).
- `frontend/src/features/collab/` and `frontend/src/features/cases/`: the contributor-teams picker inside `AssessmentPanel`, making one add or one remove call per change, never a list replacement, so a stale form cannot remove a team someone added in between (D-20, CAS-S17).
- COL-S9's journey in `collab.journey.spec.ts`; CAS-S17 in `cases/tests_scenarios.py`. TEN-S7's case-participant line stays chunk 8's.

**Owned paths:**

- `backend/apps/collab/api.py`, `backend/apps/collab/schemas.py`
- `backend/apps/cases/logic.py` (the team-participant read only)
- `backend/apps/shared/routes.py`, `factories.py` (the three routes)
- `frontend/src/features/collab/`, `frontend/src/features/cases/` (the picker's operations only)
- `frontend/src/components/cases/AssessmentPanel.tsx` (the picker only)
- `backend/apps/cases/tests_scenarios.py` (the CAS-S17 skip line only), `backend/apps/collab/tests_scenarios.py` (the COL-S9 skip line only)
- `frontend/tests/e2e/collab.journey.spec.ts` (the COL-S9 block only)
- `backend/apps/collab/app.md`, `backend/apps/cases/app.md` (the COL-04 and CAS-03 status cells only)

**Done when:**

- `test_col_s9` and `test_cas_s17` are green and un-skipped, and the COL-S9 journey is green against the real stack.
- Each refusal code of D-18 and D-19 has a test, with its evidence beside the code.
- A participant on a closed case answers 409 `invalid_transition`, from `state.py`.
- Every cross-tenant clause of COL-S9 holds, including B's add landing on B's own case.
- The picker makes single add and remove calls and stores no list; a test drives the stale-form case of CAS-S17 and "Cards" survives.
- The case file shows that a removed team took part until it was removed (soft removal, D-18).
- Participation grants no access: a participant without `cases.work` still gets 403 on a write, proved.
- `tests_tenant_isolation` and `tests_route_permissions` are green; the delete route is listed as gated in logic with its reason.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.collab apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/collab/*,apps/cases/logic.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "COL-S9"`

**Invariants:**

- Participation lists and notifies and grants no access (D-18).
- Composite foreign keys make a cross-tenant or non-member row impossible at the database.
- One list of who is involved, never two: the assessment stores no contributors.
- Concurrent edits are refused, never merged: single calls, never a list replacement.

### f03-T77: case work reaches My work

**Requirements:** HOM-05 (the case half), CAS-04
**Scenarios:** HOM-S14 (`@integration`)
**Depends on:** `f03-T76`, `c9-actions`, `f03-T59`

From `FEATURES_0_3_TASKS.md` (MY_WORK_AND_MARKETS T-40). Extend `backend/apps/home/my_work.py` (key `mywork`) with the case sources, adding no second service and no database view (D-23):

- An open case whose owner is the reader, dated by its assessment's internal deadline or by the reader's own action, as HOM-S14's rules name.
- An action the reader owns, bucketed by its due date: overdue, due soon, or everything else.
- A case whose team participant is a team the reader belongs to, with the reason "Your team takes part".
- The footprint is not applied and nothing is marked outside it (D-24).
- Every row and every count comes from the permission-filtered set: a reader without `cases.read` gets no case rows and no case counts, and a permission-limited notice rather than a 403 (AC-HOM1).
- HOM-S12's pinned query count must not move: the case sources join the existing fan-out and add no chained query.

**Owned paths:**

- `backend/apps/home/my_work.py`
- `backend/apps/home/tests_my_work_cases.py`
- `backend/apps/home/tests_scenarios.py` (the HOM-S14 skip line only)
- `backend/apps/home/app.md` (the HOM-05 status cell note only)

**Done when:**

- `test_hom_s14` is green and un-skipped, with every clause: Anna's action under "Overdue" and her case under "Everything you're responsible for"; Erik's item dated by his action; each member of "Legal" seeing the case with "Your team takes part".
- `test_hom_s12`'s pinned query count is unchanged, proved in the same run.
- A reader without `cases.read` gets no case rows and no case counts, and the permission-limited kinds are named rather than refused.
- The footprint hides nothing on My work, proved by a case outside the footprint that still appears.
- A second tenant's cases and actions never reach a row or a count; the tenant-isolation guard is green.
- The read writes nothing and records nothing.
- `apps/home/my_work.py` holds its coverage floor and none is lowered.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.home apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/my_work.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- One service under row-level security, no database view, no second My work.
- Every row and count respects the reader's permissions; a missing permission is a notice, never a page-level 403.
- My work does not apply the footprint (D-24).
- Fan out, never chain: the pinned query count is the proof.

### c9-e2e-triage-journeys: from Today to a triaged case

**Requirements:** CAS-02, J-2
**Scenarios:** CAS-S2 (`@e2e`), CAS-S3 (`@e2e`), CAS-S14 (`@e2e`, `@smoke`)
**Depends on:** `c9-fe-triage-panel`, `c9-e2e-seed`, `c6-today-screen`, `c5-cases-so-what-and-links`, `f03-T77`, `f03-T62`

Un-fixme the three triage journeys in `frontend/tests/e2e/cases.journey.spec.ts`, against the real stack, signing in through the UI with a passkey:

- CAS-S14 (J-2, `@smoke`): the seeded compliance officer opens Today, opens the lead change, chooses "Confirm wording" on the So what, and triages with "Act now" and an owner; the case shows assigned with "Act now" as a `negative` pill and the owner named. No undeclared API error occurs.
- CAS-S2: a confirm without an owner shows the 422 against the owner field — declared with `apiGuard.allow(/\/triage$/, 422, 'triage needs an owner')` where it happens — then urgency "Within 3 months" and an owner move the case to assigned with the `warning` pill, and the owner's My work shows the case (which is why `f03-T77` and `f03-T62` are dependencies).
- CAS-S3: a dismissal without a reason shows the 422, declared where it happens; a dismissal with "out_of_scope" shows "Dismissed" with the label and removes the case from the open list; "Move back to triage" returns it and the audit log shows both moves.
- Every spec imports `test` from `tests/e2e/support/api-guard`; nothing is mocked and no token or cookie is injected.

**Owned paths:**

- `frontend/tests/e2e/cases.journey.spec.ts` (the CAS-S2, CAS-S3 and CAS-S14 blocks only)

**Done when:**

- The three journeys are un-fixme'd and green against the real stack, `@smoke` included.
- Each expected 422 is declared with `apiGuard.allow` where it happens and with its reason; no other `/api/` response of 400 or above occurs.
- The pill tones are asserted by their rendered tone class, so a tone regression fails the journey.
- The dates the journey asserts come from the seed's anchor, so the run is green in any month.
- Teardown restores the seeded case on failure as well as on success.
- `npm run test:e2e -- --grep "@smoke"` is green, because J-2 joins it.

**Gates:**

- `cd frontend && npm run test:e2e -- --grep "CAS-S2|CAS-S3|CAS-S14"`
- `npm run test:e2e -- --grep "@smoke"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- E2E runs against a production Next build and the real backend on a freshly seeded database.
- Sign-in is by passkey through the UI; no token, no cookie, no mocked API.
- Every expected error is declared where it happens.
- Clocks anchor to the tenant-local date plus a fixed wall time.

### c9-e2e-work-journeys: assessment, actions and evidence

**Requirements:** CAS-03, CAS-04, CAS-05
**Scenarios:** CAS-S4 (`@e2e`), CAS-S6 (`@e2e`), CAS-S7 (`@e2e`)
**Depends on:** `c9-fe-assessment-panel`, `c9-fe-actions-panel`, `c9-fe-evidence-panel`, `c9-e2e-seed`, `c9-e2e-triage-journeys`

Un-fixme the three work journeys in `cases.journey.spec.ts`:

- CAS-S4: the owner chooses "Start assessment", saves applies, why, what must change, an internal deadline and an effort size, and the case moves to assessing with each field stored by key. A save without a why shows the 422, declared where it happens. The contributor-teams step is CAS-S17's and is not walked here (ruling 2).
- CAS-S6: "Add action" with a title, an owner and a due date lists the action with its due date and moves the case to implementing; once the case waits for sign-off, editing an action shows the 409 `actions_locked`, declared with its reason. The ticket step is chunk 13's and is named in the reworded Gherkin.
- CAS-S7: attaching a PDF, a link and a reference stores the file with a content hash and leaves it invisible until the scan passes; a file outside the allow-list shows the 422, declared; downloading streams through the API and the audit log shows the download.
- The scan is deterministic under `E2E_MODE`: the seeded mock scanner returns `clean` for the journey's file and `infected` for the marker file, so nothing waits on a real scanner and nothing is mocked at the API boundary.

**Owned paths:**

- `frontend/tests/e2e/cases.journey.spec.ts` (the CAS-S4, CAS-S6 and CAS-S7 blocks only)

**Done when:**

- The three journeys are un-fixme'd and green against the real stack.
- Each expected 422 and 409 is declared with `apiGuard.allow` where it happens and with its reason.
- The downloaded file's bytes match the uploaded file's, and the audit-log row for the download is asserted through the audit-log screen.
- The invisible-until-scanned state is asserted before the scan completes and the download control after it.
- Every date asserted comes from the seed's anchor.
- Teardown restores the seeded case, its actions and its evidence on failure too.

**Gates:**

- `cd frontend && npm run test:e2e -- --grep "CAS-S4|CAS-S6|CAS-S7"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- No API response is mocked; the scanner's determinism comes from `E2E_MODE` and the seed, not from an intercepted request.
- Every expected error is declared where it happens.
- Settle before branching; exact text where copy can collide.

### c9-e2e-signoff-journeys: the three sign-off refusals and the approval

**Requirements:** CAS-06
**Scenarios:** CAS-S8 (`@e2e`), CAS-S9 (`@e2e`), CAS-S10 (`@e2e`)
**Depends on:** `c9-fe-signoff-panel`, `c9-e2e-seed`, `c9-e2e-work-journeys`

Un-fixme the three sign-off journeys in `cases.journey.spec.ts`:

- CAS-S8: with one open action and no evidence, "Request sign-off" shows `open_actions`; with the action completed it shows `evidence_missing`; with evidence attached the case reads "Waiting for sign-off". Both 409s declared where they happen.
- CAS-S9: the owner who requested it, holding `cases.signoff`, chooses "Sign off and close" and the screen says a second person has to sign off; the 409 `four_eyes_violation` is declared with its reason.
- CAS-S10: the approver chooses "Sign off and close" without a fresh assertion and gets the step-up prompt (403 `step_up_required`, declared); passing the passkey prompt through the virtual authenticator closes the case, and the audit event carries the assertion while no library or register row changed.
- The step-up passes through the UI with `browserContext.credentials`, never an injected assertion.

**Owned paths:**

- `frontend/tests/e2e/cases.journey.spec.ts` (the CAS-S8, CAS-S9 and CAS-S10 blocks only)

**Done when:**

- The three journeys are un-fixme'd and green against the real stack.
- Each expected 409 and the 403 `step_up_required` are declared with `apiGuard.allow` where they happen, with their reasons.
- The step-up is passed through the UI with the virtual authenticator; no assertion is injected.
- After the sign-off, the audit-log screen shows the event with its assertion reference, and a spot check of the obligation the change links to shows it unchanged.
- Teardown returns the seeded case to `signoff` on failure too.

**Gates:**

- `cd frontend && npm run test:e2e -- --grep "CAS-S8|CAS-S9|CAS-S10"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Sign-in and step-up go through the UI with a passkey; nothing is injected.
- Every expected error is declared where it happens.
- Closing a case never edits the inventory, and the journey proves it.

### c9-e2e-j3: the whole case, end to end

**Requirements:** CAS-03, CAS-04, CAS-05, CAS-06, CAS-07, J-3
**Scenarios:** CAS-S11 (`@e2e`), CAS-S15 (`@e2e`, `@smoke`)
**Depends on:** `c9-e2e-signoff-journeys`, `c9-fe-case-file`, `c9-case-file-export`

Un-fixme the two remaining journeys in `cases.journey.spec.ts`:

- CAS-S15 (J-3, `@smoke`): the seeded owner records the assessment on an assigned case, adds two actions, completes them, attaches evidence and requests sign-off; the owner tries "Sign off and close" and is refused; the approver signs off with a passkey step-up; the case is closed and "Show case file" opens a complete file. The one expected 409 on the self sign-off is declared.
- CAS-S11: a closed case's "Show case file" shows the change, the So what, the assessment, the actions with completion, the evidence list with hashes, the sign-off with both people and every date; exporting it produces the same content and its download is permission-checked.
- J-3 joins `@smoke`, so this task also runs the whole smoke suite.

**Owned paths:**

- `frontend/tests/e2e/cases.journey.spec.ts` (the CAS-S11 and CAS-S15 blocks only)

**Done when:**

- Both journeys are un-fixme'd and green against the real stack, and no chunk 9 journey is fixme any more.
- The one expected 409 on the self sign-off is declared with its reason, and no other `/api/` response of 400 or above occurs across the whole journey.
- The exported file's text is compared with the on-screen case file inside the journey and matches.
- `npm run test:e2e -- --grep "@smoke"` is green with J-3 in it.
- The journey completes inside the suite's per-test budget, and each screen it opens reaches real data within 500 ms.

**Gates:**

- `cd frontend && npm run test:e2e -- --grep "CAS-S11|CAS-S15"`
- `npm run test:e2e -- --grep "@smoke"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- A golden path is proved end to end against the real stack, or it is not proved.
- Every expected error is declared where it happens; nothing is mocked.
- Measured against `next start`, never `next dev`.

### c9-security-review: the chunk-wide sweep

**Requirements:** NFR-04 (the chunk's share)
**Scenarios:** none
**Depends on:** `c9-e2e-j3`, `c9-case-file-export`, `c9-evidence`, `c9-signoff`, `c9-close-paths`, `f03-T76`, `f03-T77`

A security-review sub-agent reads the whole chunk 9 diff on `main` (`git diff <chunk 9 base>..main`, limited to the chunk's paths) and answers, with evidence:

- **Evidence.** Can a file be downloaded before its scan passes, under any state, any race between the upload and the worker, or any retry? Are the hash and the size the server's own measurement? Can a filename, path or byte reach a log, Sentry, an analytics event, a `Referer` or an error message? Can a storage key be guessed or traversed? Is an infected file's bytes really gone? Does a removed row stay readable only in the case file?
- **Four eyes and step-up.** Can the requester sign off through any path — a send-back and a fresh request by the same person, a delegate, a team owner, a support session? Is the database CHECK reachable if the API check is bypassed? Does every sign-off audit row carry its assertion? Do the two close paths `c9-close-paths` built obey the option Alex chose, and does no third door reach `closed`?
- **Tenancy.** Does every case, action, evidence, participant and export read activate exactly one tenant? Are `impact_assessment`, `action`, `case_transition` and `evidence` under forced row-level security with composite foreign keys, and does `tests_tenant_isolation` cover every new route? Can a shared change let tenant B reach tenant A's case?
- **The library fence.** Does any case write reach a library table? Closing a case must change nothing in the inventory; prove it from the fence and from a diff of both zones across a sign-off.
- **Permissions.** Is every chunk 9 route gated, with no new `UNGATED_BY_DESIGN` entry? Does `cases.contribute` reach anything `cases.work` should hold, or the reverse? Does a permission-filtered field ever become a page-level 403, or a 403 a silent empty page?
- **Audit.** Does every write have a `record()` row in the same transaction, does every download have exactly one, and does no read write one?
- **The state machine.** Is there any transition outside `state.py`? Can a sub-status reach a guard? Can `allowedTransitions` and the server's actual guards disagree?
- **Simplicity.** Is anything here speculative or overbuilt? Name it for the fix package to cut.

Run the guard suites with it: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`.

**Owned paths:**

- `docs/security/CHUNK9_REVIEW_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- The report names every finding with a severity, the file and line, and the fix it asks for.
- A critical or high finding blocks the chunk close and is listed for `c9-review-fixes`.
- Findings below high become rows in `HARDENING.md` with the package that will fix them.
- The six guard suites are green on `main`, and the report says so with the command output.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write apps.shared.tests_four_eyes --settings=config.test_settings --noinput`

**Invariants:**

- The review lowers nothing and fixes nothing; it reports.
- A finding is evidence, not opinion: each carries the code that proves it.

### c9-review-fixes: close the review's findings

**Requirements:** NFR-04 (the chunk's share)
**Scenarios:** the chunk's scenarios stay green
**Depends on:** `c9-security-review`
**Security review:** yes (re-run on its own diff)

Fix every critical, high and medium finding of `c9-security-review`, test first, then re-run the review over this task's diff and repeat until nothing at medium or above remains. If the review found nothing at medium or above, close at once with a note in `HARDENING.md` and no code change.

**Owned paths:**

- the files the review's findings name, and nothing else; a finding that needs a file another task owns waits for that task or becomes its own package (parallel-plan rule 9)
- `docs/security/CHUNK9_REVIEW_2026-09-20.md` (the re-run appended to it)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- No critical, high or medium finding is open.
- Every chunk 9 scenario that was green is still green, and no test was weakened to get there.
- Findings below medium are rows in `HARDENING.md` with a package named.
- The re-run review is appended to `docs/security/CHUNK9_REVIEW_2026-09-20.md`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run build`

**Invariants:**

- No gate lowered, no test skipped or quarantined, no API mocked in E2E.
- A guard, audit row, permission check or validation is never simplified away.

### c9-close: the chunk closes

**Requirements:** CAS-02 to CAS-08, COL-04 (cases), J-2, J-3
**Scenarios:** every chunk 9 scenario green; the deferred ones named
**Depends on:** `c9-review-fixes`, `f03-T77`, `c9-close-paths`

Close the chunk on `main` (playbook Section 3):

- Run `bash scripts/prepush.sh --all` and the full `npm run test:e2e`.
- Prove no chunk 9 route answers 501 and no chunk 9 journey is fixme, by enumerating the seventeen operations and the eleven CAS journeys.
- Prove `backend/scripts/contract_drift_pending.txt` holds no chunk 9 line.
- Add the chunk 9 coverage floors to `backend/scripts/coverage_gate.py`, measured at this close, each with its measured value, statement count and date, and restate the header's measurement note.
- Update `backend/apps/cases/app.md`: CAS-02, CAS-03 and CAS-05 to CAS-08 `built`; **CAS-04 `in_progress`**, its status cell naming the half that is not here — "exportable as tickets" is `c13-tickets-export`'s (ruling 3) — so the row says what is on `main` and not what the requirement reads. The §1 note that the workflow is R2 is replaced by what is on `main`. Update `backend/apps/collab/app.md`'s COL-04 note with the case half now covered, and `backend/apps/home/app.md`'s HOM-05 note with the case sources.
- Update `docs/plans/IMPLEMENTATION_STATUS.md`: chunk 9 implemented and tested with today's date, `in progress` until a person verifies it, and a notes cell that starts with **CAS-04 `in_progress`: actions are built, "exportable as tickets" is `c13-tickets-export`'s (chunk 13)** and then names what else was cut and why (the presigned links, `impact_assessment.contributors`, `triage_due_at` and the case reminders to chunk 10, evidence on a register entry to chunk 8, comments to chunk 10, retention to chunk 12).
- Update `docs/plans/UI_Implementation_Plan.md`'s chunk 9 rows: each status from `later chunk 9, card pending` to `built`, the evidence download row naming the streaming endpoint, the `export-tickets` row renamed to chunk 13, and the "case panels on `tenant-change.html`" screen-card row to `built`.
- Write the open points into `docs/TODO_FOR_alex.md`: the one open confirmation (multipart upload rather than a presigned PUT, ruling 4), q-case-close's answer as it was taken, and the `clamd` service need (parallel plan §7.3) for the R2 deploy. The four defaults that a source settles stay out of that file; they live in their tasks' commit bodies.
- Add the `Verification_Log.md` rows for any provider fact the chunk relied on (the clamd `INSTREAM` protocol and the MIME types the allow-list names), fetched, not recalled.

**Owned paths:**

- `backend/apps/cases/app.md`, `backend/apps/collab/app.md`, `backend/apps/home/app.md` (status cells and notes only)
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `docs/plans/UI_Implementation_Plan.md` (the chunk 9 rows only)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md` (its own rows only)
- `backend/scripts/coverage_gate.py` (the chunk 9 floors only)

**Done when:**

- `bash scripts/prepush.sh --all` is green on the close commit.
- The full E2E suite is green against the real stack, `@smoke` included, with J-2 and J-3 in it.
- No chunk 9 route answers 501, no chunk 9 journey is fixme, and no chunk 9 line is left in `contract_drift_pending.txt`.
- CAS-S1 is still chunk 5's and green; no scenario of another chunk was un-skipped here.
- The status files, the UI plan rows and the three app.md files say what is on `main`, not what was intended.
- The coverage floors are raised to the measured values and none is lowered.
- `requirements_coverage.py` shows every chunk 9 requirement with an owning task and an owning scenario.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `bash scripts/prepush.sh --all`
- `cd frontend && npm run test:e2e`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Status is the truth of `git log`, not intention: a row moves only when its commit is on `main`.
- No gate lowered to close a chunk; a cut is named, never hidden.
- The owner deploys; an agent never does.
