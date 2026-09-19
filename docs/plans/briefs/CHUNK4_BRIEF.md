# Chunk 4 brief: proposals and the platform console (PRO-01 to PRO-03, ADM-02 R1 parts, AUD-03)

Repo `C:\Users\Alex\projects\grc`, branch `main`. Chunks 1 to 3 are on disk: read
`backend/apps/{proposals,library,taxonomy,identity,governance}/**` and `backend/apps/shared/**`
first, then `CLAUDE.md`, `docs/CONVENTIONS.md`, `docs/PLAYBOOK.md` 4.2 (four eyes, step-up),
4.3, 5, 14, 15, 16, `PRD.md` PRO, ADM-02, AUD-01..03, AC-PRO1, AC-PRO2, AC-AUD1, J-4 (the
console half), section 6 (platform roles), `docs/inputs/INPUT_DELTAS.md` 5, 6, 7,
`docs/inputs/schema.sql` (`proposal`, `problem_report`, `audit_event`, `ai_generation`,
`support_access`, `plan`, `tenant_subscription` for the tenants list), `docs/inputs/data-model.md`
4 ("Four eyes"), `backend/apps/proposals/app.md`, `backend/apps/governance/app.md`
(AUD-S1..S7, ADM-S4..S6), the cards `design/screens/console-shell.html`, `console-queue.html`,
`console-problem-reports.html`, `tenant-library-updates.html`, `states.html`, and
`docs/plans/UI_Implementation_Plan.md` chunk 4 rows.

Scope: PRO-01, PRO-02, PRO-03, AUD-03, ADM-02 R1 surfaces (queue, library vocabularies, sources
registry read-only until chunk 5, languages and jurisdictions, problem reports, tenants list with
create-tenant-and-invite-admin, system health), AUD-01/AUD-02 read surfaces (`GET /audit-events`
for `audit.read`, `GET /ai-generations` for `ai_log.read`; the `AiGeneration` model lands now,
empty until chunk 7), J-4's console half. Scenarios: proposals PRO-S1..S9 except the batch ones
(PRO-04 is R2), governance AUD-S1..S5, S7, ADM-S4..S6 (integration and e2e).

## Invariants
Proposals are the only door into the library (AC-PRO1: no API key scope and no tenant role can
change a library record except through an approved proposal; extend the library-fence and
route-permission guards to prove it over the real routes). Approval applies the payload, writes
the new version, the audit row and the search re-index hook (a no-op `reindex(obligation)` in
`apps/search/logic.py` that chunk 7 fills) in ONE transaction. The reviewer can correct scope and
wording before applying (the corrected payload is stored on the proposal with `corrected_by`).
Never the proposer: check constraint + 409 `four_eyes_violation` (AC-PRO2). Agent proposals
carry `proposed_by_agent_run`; a person reviews. Approval and rejection need `proposals.review`
and step-up. Every field carries a source (`field_sources`); a proposal without a source for a
changed field is refused 422 `source_missing`. Idempotency-Key on `POST /proposals`.

## Model (apps/proposals, extend the chunk 2 model)
`Proposal` gains kinds `obligation_create`, `obligation_version` (new summary with
`effective_from`, per-language texts), `obligation_scope` (terms and tags), `obligation_retire`,
`instrument_create`, `instrument_update`, `provision_version`, `change_link` (chunk 5 uses it),
`reverification`; `payload` JSON validated by a Pydantic schema per kind (named in the
lint-suppression comment); `corrected_payload` nullable + `corrected_by`, `corrected_at`;
`rejection_code` kind (`duplicate|not_supported_by_source|out_of_scope|wrong_target|other`);
`applied_version_type`/`applied_version_id` for what approval created. `apply.py`: one function
per kind inside `library_write()`; every apply writes `record()` with before/after and the
step-up assertion id. `ProblemReport` (chunk 3) gains `answered_by`, `answer_text`,
`resolved_by_proposal`; resolving via a proposal moves it to `fixed` when that proposal is
approved (closing the loop, AUD-03). `AiGeneration` (apps/governance; mixed table): purpose
kind, model, model_version, input_ref, output_text, citations JSON (named schema), review_state
kind (`unreviewed|confirmed|rewritten|rejected`), feedback kind nullable, tenant nullable,
agent_run nullable, created_at. `Tenant` creation from the console: `POST /console/tenants`
(`tenants.manage`) creates the tenant, its system roles (chunk 2's tenant hook), and invites
the first admin; `GET /console/tenants` lists tenants with member counts and status.
`GET /console/health` (`system.health`): the `/health/` components plus outbox lag (oldest
unpublished outbox event age), failed jobs count (0 until chunk 5), last agent runs (none yet),
proposal queue age.

## API
Designed: `GET /proposals` (queue for `proposals.review`; a tenant member with
`proposals.create` or `vocab.manage` sees only proposals their own tenant made, which needs a
nullable `proposed_by_tenant` on `Proposal`, set from the principal at creation, and the
mixed-table policy of `audit_event`; chunk 2 deliberately shipped without this read, so the
tenant vocabulary screen's pending list for library lists lands here), `POST /proposals`,
`GET /proposals/{id}` (with the diff against the current version for version kinds, the source
excerpt per field), `POST /proposals/{id}/approve` `{correctedPayload?}` (+step-up, four eyes),
`POST /proposals/{id}/reject` `{rejectionCode, note}` (+step-up), `GET /problem-reports`
(console: all; tenant: own), `PATCH /problem-reports/{id}` (answer, start a proposal from it:
`{action: answer|propose|reject, text}`), `GET /audit-events` (filters subjectType, subjectId,
actor, from, to; a tenant sees its rows and library rows; the console sees library rows),
`GET /ai-generations`. New (INPUT_DELTAS 7 rows): `GET /library-updates` for tenants (applied
proposals since a date, grouped by day, with what changed and "mark as seen" per user via
`membership.last_library_visit_at`), `GET/POST /console/tenants`, `GET /console/tenants/{id}`,
`GET /console/health`, `GET /reference/languages` (exists), `GET/PATCH /console/languages/{key}`,
`GET/PATCH /console/jurisdictions/{key}` (labels and active only, `library_vocab.manage`).

## Seeds and E2E
`seed_e2e`: three pending proposals from the prototype (fixture `proposals`), one made by the
compliance officer (so J-4's four-eyes refusal can be shown when she tries to approve her own),
one from an agent run placeholder (`proposed_by_agent_run` uuid without FK until chunk 5),
one problem report; platform editor `editor@bleqq.test` holds `library_editor`. Journeys
(frontend): PRO-S3, S4, S5, S7, S8, S9, AUD-S3, S4 (empty state), S5, ADM-S4, S5, S6, and the
console half of AGT-S10/J-4 (the editor approves in the console, the obligation shows version 2
with a diff, the tenant sees "what changed" under `/library-updates`); the agent-key half of
J-4 arrives with chunk 5, so the journey seeds the proposal directly for now and says so in its
title.

## Frontend
Console route group `src/app/(console)/console/{queue, queue/[id], vocabularies,
vocabularies/[list], sources (read-only list until chunk 5), languages, problem-reports,
tenants, health}` behind the console shell (`console-shell.html`: separate rail, the seven
destinations, gated by platform permissions in the registry with `surface: 'console'`); tenant
route `/library-updates`. Presentation functions with tests; every string in both catalogs;
empty/loading/error/denied states; console shell must not fire tenant queries (playbook 6.1).

## Gates
Test-first; full Appendix D; `generate-types.sh` last; contract drift explained; status cells;
coverage floors for proposals and governance. Report shapes and deviations.
