# Chunk 4: tasks

Written 2026-09-19 by the planning workflow (read, plan, parallelism and coverage critiques, revise). Each task runs in its own worktree (`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`.

## Scope, rules and defaults

Chunk 4 plan: proposals and the platform console. Baseline is main at 51f9efa, which already holds the chunk 3 data layer and the redesign foundations (18a935b). The plan has 27 tasks in 9 waves; with Q1 unanswered it is 20 tasks in 7 waves. Nothing was edited while planning.

HARD PRECONDITION: THE REST OF CHUNK 3 IS ON MAIN BEFORE WAVE 1
- What must be on main:
  - The read API with the sentence diff, and its deletions from contract_drift_pending.txt.
  - POST /obligations/{id}/verifications with its library-fence edit.
  - POST /obligations/{id}/problem-reports and the "This looks wrong" dialog.
  - The append-only trigger on version rows, with its library migration.
  - The sample provision texts and the J-6 seed assertion.
  - The inventory, instrument and obligation screens, with "Show what changed".
- Why it cannot wait:
  - Every chunk 4 wave from 1 to 8 has a task that owns en.json and sv.json.
  - Chunk 3's backend half touches e2e_seed.py, tests_seed_integrity.py, contract_drift_pending.txt and the library migrations.
  - So no chunk 3 task can share a wave with this plan.
- Ownership: T16b alone owns listProblemReports. Chunk 3 builds only the create route and the dialog.

WHAT IT DELIVERS
- PRO-01 to PRO-03:
  - One obligation proposal kind, new_obligation_version, with a source per changed field (422 source_missing). The source check runs at creation and again over the corrected payload at approval.
  - Approve takes payloadOverrides. The corrected payload is stored with corrected_by. Apply, the re-index hook and every audit row carrying the step-up assertion id run in one transaction.
  - Rejection needs a reason that is a rejection_reason row.
  - A tenant sees its own pending library proposals.
  - The console queue shows the source beside the sentence diff, and never shows a tenant member's name.
  - Tenants see library updates since their last visit (POST /me/visit).
- AUD-03: the report-to-proposal loop, gated by Q1.
- AUD-01:
  - GET /audit-events and a tenant audit log screen.
  - Rows without a tenant reach tenants only for library records written by agents, the system or platform staff.
- ADM-02, the R1 part of the console:
  - Shell and platform landing, vocabularies, queue, problem reports, and tenants with create-and-invite-first-admin.
  - ADM-S4 is reworded to the surfaces that exist, with each deferred surface named with its chunk.
- A second library editor login, and bootstrap_platform --role library_editor with an audited role grant.

DEFAULTS TAKEN (say so in commit bodies)
- Designed and fixture kind names over the brief's obligation_* names, because inputs outrank the brief.
- payloadOverrides (designed, and already promised by INPUT_DELTAS) instead of correctedPayload.
- Rejection reasons:
  - They become a library vocabulary list without a kind.
  - It is seeded with schema.sql's seven codes (wrong_fact, wrong_scope, bad_source, duplicate, not_relevant, poor_wording, other), not the brief's five, because inputs outrank the brief.
  - CLAUDE.md says reasons are rows, and a new tier-one kind would need a PRD bump.
- No step-up on reject. Playbook 4.2, the UI plan and the shipped chunk 2 route agree.
- The tenant's pending list:
  - It uses a proposal_tenant link table under forced RLS and a separate GET /tenant/proposals.
  - Proposal gains only a boolean, proposed_in_tenant, so the console can withhold a tenant member's identity without learning which tenant.
- Proposal creation is audited under the proposer's tenant. Decisions stay library rows.
- PRO-S1 is reworded to "summary and scope terms". Duty type sits on the unversioned Obligation node and belongs to update_obligation (chunk 5).
- A reviewer's overrides may change only fields the proposal already sources. An override that adds an unsourced field is refused with 422 source_missing.
- The tenant audit read shows a row without a tenant only when both hold:
  - its subject is a library record (authority, instrument, provision, obligation, vocabulary, taxonomy_term);
  - its actor is an agent, the system or a platform role holder.
  - Proposal rows without a tenant stay hidden from every tenant.
- GET /library-updates titles each item by the library record, never by the proposal.
- No fixture proposal is seeded. p1's version 2 is already filed. p2 and p3 are kinds deferred to chunk 5.
- The four-eyes refusal uses a proposal made by the editor, because the compliance officer lacks proposals.review.
- ADM-S6 is narrowed to tenant creation. Plans live in NFR-S17 to S19; support access requests move into TEN-S6.
- ADM-S4 is narrowed to the console surfaces that exist, with the deferred ones named.
- AUD-S3 filters by any record.
- Library editors are invited by bootstrap_platform --role.
- Tenant creation activates only the tenant it has just created. T15 reviews this.

CUT, WITH REASONS
- new_obligation and reverification proposal kinds:
  - No scenario and no producer until chunk 5's agents.
  - reverification also overlaps chunk 3's direct stamp route (INV-S8).
  - Their queue detail variants and the new-obligation scope suggestion go with them.
- Other schema v0.3 kinds (instrument, provision, update_obligation, retire, change link): chunk 5.
- AiGeneration and GET /ai-generations: chunk 7, and nothing produces rows yet. AUD-S4 stays skipped.
- Console health: its card is chunk 14, and there is no outbox publisher, no jobs and no runs. ADM-S5 stays skipped.
- Console language and jurisdiction edits:
  - A direct PATCH would write library rows outside the proposal door.
  - The seeds reset them on every deploy, and there is no card.
- Console Sources: no Source model until chunk 5.
- GET /console/tenants/{id} and member counts: no card, and platform reads of membership are under RLS.
- applied_version_type and applied_version_id: ObligationVersion.applied_by_proposal already links the version.
- Card extras cut for now:
  - Withdraw.
  - Rail counts.
  - Source excerpts and fetch time.
  - Machine translation after approval.
  - "Affects N changes".
  - The console's "Open the obligation".
  - A console audit read.
- AGT-S10 stays fixme: J-4 is chunk 5.
- J-5's watch steps wait for chunk 5.

WAVE LOGIC
- The proposals backend chain: T1, T6, T10, T13b, then T18.
- The governance scenario-file chain: T3, T7, T16b, then T18.
- The contract_drift_pending.txt chain: T3, T13a, T16b, T18, T24a, then T24b.
- Exactly one frontend task per wave owns the catalogs and registry.ts: T5, T9, T12, T14, T17, T19, T21, T23. T20 touches no catalog and runs beside T19.
- Security reviews:
  - T15 runs in wave 5 and covers every task that does not need Q1.
  - T22 covers only the Q1 work.
  - The main agent's per-merge security review still applies to the tenancy, fence, audit and four-eyes tasks.
- If Q1 is unanswered when wave 3 starts, hold T16a, T16b, T18, T21, T22, T23 and T24b. Everything else proceeds, and T24a closes the chunk with AUD-03 in progress.

CHANGES FROM THE REVIEW
- Chunk 3 is now a hard precondition.
- Two proposal kinds are cut.
- T11 shrinks to the fence proof and moves to wave 1.
- T13 is split into T13a and T13b. T16 is split into T16a and T16b. T24 is split into T24a and T24b.
- PRO-S9 moves from T6 to T10.
- T16a's policy is limited to SELECT and UPDATE, with a column trigger.
- T3's row rule is tightened.
- PRO-S1 and ADM-S4 are reworded.
- The step-up id must be on every audit row an approval writes.
- Proposer identity is withheld from the console.
- bootstrap_platform audits its role grant.
- The E2E journeys assert rows by id, never counts.
- Coverage floors appear in the task gates.
- The rejection-reason keys follow schema.sql. This was found while checking the critiques.

## Waves

Tasks in one wave have disjoint files and can run side by side.

1. `chunk4-T1`, `chunk4-T2`, `chunk4-T3`, `chunk4-T4`, `chunk4-T5`, `chunk4-T11`
2. `chunk4-T6`, `chunk4-T7`, `chunk4-T8`, `chunk4-T9`, `chunk4-T13a`
3. `chunk4-T10`, `chunk4-T12`, `chunk4-T16a`
4. `chunk4-T13b`, `chunk4-T14`, `chunk4-T16b`
5. `chunk4-T15`, `chunk4-T17`, `chunk4-T18`
6. `chunk4-T19`, `chunk4-T20`, `chunk4-T22`
7. `chunk4-T21`, `chunk4-T24a`
8. `chunk4-T23`
9. `chunk4-T24b`

## Open questions

- Q1 (a product invariant is at stake, so stop and ask Alex): how may platform staff read and resolve tenants' problem reports?
  
  The problem:
  - problem_report is a mixed table under forced RLS, so a console session (no tenant) sees only rows without a tenant.
  - The console list, Reject, Start a proposal, and marking a report fixed when its proposal is approved all read or write tenant rows.
  - 'Platform staff have no bypass' forbids that without a support access grant.
  - A platform session also cannot write a tenant's audit_event or outbox_event rows. A resolution's audit and outbox rows would therefore be library rows, carrying no report text and no reporter.
  
  Option A (recommended), a narrow exception on problem_report only:
  - Two permissive policies, FOR SELECT and FOR UPDATE, keyed on a transaction-local flag. INSERT and DELETE never match it.
  - A BEFORE UPDATE trigger limits flagged writes to status, resolution_note, resolved_by, resolved_at and resolved_by_proposal.
  - Only apps/governance/problem_reports_logic.py may set the flag, after proposals.review is checked. An AST guard enforces that.
  - The reporter's identity is never returned to platform staff. The organisation name is shown, as the card draws it.
  
  Option B, a report becomes a library row, like a tenant-made proposal:
  - The tenant link lives in its own RLS table.
  - The console shows no organisation name and has no organisation filter.
  - Chunk 3's ProblemReport model changes.
  
  This gates chunk4-T16a, T16b, T18, T21, T22, T23 and T24b. If Q1 is unanswered when wave 3 starts, those are held. Everything else proceeds, and T24a closes the chunk with AUD-03 in progress.
- Rejected (in part), the T6 source-at-approval critique: its fix has the approve body carry fieldSources for fields an override introduces, and has T17's form ask for them.
  - No scenario adds a field at review, so that mechanism is speculative.
  - The accepted part stands: T6 re-runs the source check over the merged payload, and an override that introduces an unsourced field answers 422 source_missing and applies nothing.
  - T17's correction form therefore offers only fields the proposal already sources.
- Rejected (in part), the T3 and T1 collision critique: it suggests building AUD-S7's library event from a proposal row, such as proposal.approved with no tenant, or a console-made proposal.created.
  - Under the accepted T3 audit-visibility fix, proposal rows without a tenant are hidden from every tenant, so that event would be invisible.
  - T3 builds the event from an applied library change instead: a vocabulary row changed by an approved proposal, with no tenant and a library editor as actor.
  - That removes the collision just the same.
- Rejected (in part), the T14 rejection_reason catalog critique: it asks for a test that every library list the backend registry returns has a catalog title.
  - A frontend unit test cannot read the backend registry, and a mirrored list would drift.
  - T14 writes the rejection_reason title and marker keys, and T20 adds the two map entries.
  - T20's test proves that every key in listTitle and listMarker, rejection_reason included, resolves in en and sv.
- Not raised by any critique, corrected while checking them: T2 had seeded the brief's five reason keys and said no input defines any.
  - docs/inputs/schema.sql defines proposal.rejection_code as a CHECK over seven codes: wrong_fact, wrong_scope, bad_source, duplicate, not_relevant, poor_wording, other.
  - The plan's own rule is that inputs outrank the brief, so T2 now seeds those seven.
  - T24a records the move from CHECK to vocabulary list in INPUT_DELTAS §1.

## Tasks

### chunk4-T1: The obligation version proposal kind, a source per field and the tenant link

**Requirements:** PRO-01, PRO-02, AC-PRO1, AUD-01, INV-04, INV-05  
**Scenarios:** PRO-S1 (reworded to summary and scope terms, un-skipped), PRO-S2, PRO-S5, PRO-S6 stay green  
**Depends on:** nothing

Extend the chunk 2 Proposal in migration proposals/0002:
- Add the kind new_obligation_version, the designed and fixture name. The other schema v0.3 kinds wait for chunk 5.
- Add nullable corrected_payload, with corrected_by and corrected_at.
- Add a boolean proposed_in_tenant that carries no tenant id. The console uses it to withhold a tenant member's identity (T10).
- Add a ProposalTenant link table (tenant, proposal) under forced tenant-only RLS.
- At creation, when the proposer acts inside a tenant (tenancy.active_tenant_id()), write the link row and set proposed_in_tenant.

Name the payload schema:
- summaries, keyed by language, with originalLanguage and isMachine;
- effectiveFrom with a precision;
- optional terms, written as dimension:key.

At creation:
- Refuse a missing or retired target obligation (422).
- Refuse any changed field without a fieldSources entry (422 source_missing). Put this check in one function, which T6 calls again at approval.
- Vocabulary kinds keep their chunk 2 rules.

Record proposal.created and proposal.replayed under the proposer's tenant when there is one.

PRO-S1:
- In proposals/app.md, reword it from 'summary and duty type' to 'summary and scope terms'.
- The reason: duty type is a field of the unversioned Obligation and belongs to update_obligation (chunk 5).
- Then un-skip it.

**Owned paths:**

- `backend/apps/proposals/models.py`
- `backend/apps/proposals/migrations/0002_obligation_proposals.py`
- `backend/apps/proposals/schemas.py`
- `backend/apps/proposals/logic.py`
- `backend/apps/proposals/tests_scenarios.py`
- `backend/apps/proposals/tests_create.py`
- `backend/apps/proposals/app.md`
- `backend/apps/shared/tests_rls.py`

**Done when:**

- PRO-S1 is reworded in app.md, un-skipped and green.
- makemigrations --check is clean and migrate_from_zero applies the graph.
- The RLS guard lists proposal_tenant as forced tenant-only.
- A proposal made by a tenant member writes one link row and sets proposed_in_tenant. Its creation audit row carries that tenant.
- A proposal made in the console or by a platform key writes no link, and proposed_in_tenant stays false.
- Tests prove source_missing, an unknown or retired target, the payload schema, and that vocabulary kinds are unchanged.
- The source check is one importable function.
- The diff stays inside the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.proposals apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*' (logic.py >= 97, api.py >= 96, apply.py >= 90)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit openapi.json or api.generated.ts`

**Invariants:**

- Proposal stays in the library zone and gets no tenant FK. proposed_in_tenant carries no tenant id. The tenant link lives in its own table under forced RLS.
- JSON fields carry the schema-naming suppression comment.
- Per-language text is a dict keyed by language, never _en or _sv fields (I18N guard).
- Kinds stay in the allowlisted ProposalKind.
- The four-eyes check constraint and Idempotency-Key replay are untouched.
- No library write happens here.
- The audit row is in the same transaction.

### chunk4-T2: Rejection reasons as a library vocabulary list

**Requirements:** PRO-01, VOC-01, VOC-07, AC-VOC1  
**Scenarios:** VOC-S1 and VOC-S11 stay green; PRO-S9 consumes the list in chunk4-T10  
**Depends on:** nothing

Add the tier-two library vocabulary list rejection_reason:
- A Vocabulary model and a label model.
- A registry entry: proposable, no kind.
- Migration taxonomy/0002.
- System rows with schema.sql's seven codes: wrong_fact, wrong_scope, bad_source, duplicate, not_relevant, poor_wording and other, each labelled in en and sv.

Seeding:
- seed_library_vocabularies seeds the rows create-only.
- seed_reference therefore files them on every deploy, and a relabel survives.

Why schema.sql's list: the brief listed five other keys, but inputs outrank the brief, and schema.sql's rejection_code CHECK is the only list in the inputs.

Why a list, not a kind: this replaces the brief's rejection-code kind. CLAUDE.md says reasons are rows an admin manages, and a new tier-one kind would need a PRD bump.

**Owned paths:**

- `backend/apps/taxonomy/models.py`
- `backend/apps/taxonomy/registry.py`
- `backend/apps/taxonomy/migrations/0002_rejection_reason.py`
- `backend/apps/taxonomy/seeds/__init__.py`
- `backend/apps/taxonomy/tests_vocabulary.py`
- `backend/apps/shared/tests_vocabulary_integrity.py`

**Done when:**

- After seed_reference, GET /vocab lists rejection_reason with its seven rows.
- A write to the list answers 202 {proposal}.
- Adding a row changes neither openapi.json nor api.generated.ts.
- Re-running the seed keeps a relabelled row's label.
- The vocabulary integrity guard and migrate_from_zero are green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.taxonomy apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/*' (registry.py >= 96)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Keys are immutable.
- The API returns key and label, never an enum.
- No TextChoices, and no TypeScript union of reasons.
- The seed writes library rows only from the seed module the library fence allows.
- Later changes go through proposals (VOC-07).

### chunk4-T3: Tenant audit log read

**Requirements:** AUD-01, AC-AUD1, ADM-01  
**Scenarios:** AUD-S1, AUD-S2, AUD-S7 (un-skipped), AUD-S3 (Gherkin wording only)  
**Depends on:** nothing

Serve GET /audit-events from apps/governance (SessionAuth, audit.read):
- Filters: subjectType, subjectId, actorId, from and to.
- Newest first, paginated as {items, total}: default 20, max 100.
- Each row: id, createdAt, actor {type, id, label}, action, subjectType, subjectId, subjectTitle, summary, before, after, and steppedUp (a step-up assertion is present).

What a tenant sees:
- Its own rows, through RLS.
- A row without a tenant, only when both hold:
  - the subject is a library record (authority, instrument, provision, obligation, vocabulary, taxonomy_term);
  - the actor is an agent, the system, or a user holding a platform role.
- Never a proposal row without a tenant. A tenant-made proposal's title, the editor's rejection note, and chunk 2's proposal.created rows (with a tenant member as actor) must never reach another tenant.
- Never platform identity or session events.

Also:
- Mount the governance router in config/api.py.
- Un-skip AUD-S1 and AUD-S2 by driving the existing guard proofs from the scenario tests.
- Un-skip AUD-S7 through the endpoint.
- In governance/app.md, reword AUD-S3's Given and When to filter by a record (a case, once chunk 9 exists).

**Owned paths:**

- `backend/apps/governance/api.py`
- `backend/apps/governance/logic.py`
- `backend/apps/governance/schemas.py`
- `backend/apps/governance/tests_scenarios.py`
- `backend/apps/governance/tests_audit_events.py`
- `backend/apps/governance/app.md`
- `backend/config/api.py`
- `backend/scripts/contract_drift_pending.txt (only if GET /audit-events turns out to match the designed shape and its line becomes stale)`

**Done when:**

- AUD-S1, AUD-S2 and AUD-S7 are un-skipped and green.
- AUD-S7's library event is an applied library change: a vocabulary row changed by an approved proposal, with no tenant and a library editor as actor. The test therefore does not depend on who creates proposals (T1).
- Tenant B reads after a tenant A footprint event and that library change, and sees only the library change.
- Tenant B sees none of these:
  - a rejected tenant-A proposal's decision row;
  - a chunk-2-style proposal.created row with no tenant and a tenant member as actor;
  - a platform sign-in or code-request event.
- The route-permission guard reads audit.read on the operation.
- A limit above 100 is capped.
- The query count does not grow with page size.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- RLS makes the tenant cut. Python only narrows the rows without a tenant further, never replaces RLS.
- No tenant member's name or tenant-authored text reaches another tenant.
- No platform read of tenant audit rows, and no console audit view in this chunk.
- audit_event stays append-only.
- No write route.
- No tenant content in logs.

### chunk4-T4: A second library editor and audited editor invitations

**Requirements:** PRO-02, AC-PRO2, ADM-02, ID-01, AUD-01  
**Scenarios:** supports AUD-S5, VOC-S11, PRO-S3 (a second editor approves)  
**Depends on:** nothing

Add a second platform library editor to the E2E roster: editor2@bleqq.test, Kari Nygaard (the name on the console cards). An editor who starts a proposal can then have it approved by another editor.
- Regenerate the fixed passkeys with backend/scripts/generate_e2e_passkeys.py.
- Replace the .gitleaks.toml block the script prints.
- Add editor, editor2 and platform to LOGINS in passkeys.ts.

Give bootstrap_platform a --role option:
- platform_admin by default, or library_editor.
- Only platform role keys are accepted.
- The command grants the role and records platform_role.assigned, with the role key, through record() in the same transaction as the invitation. Today the grant writes no audit row.
- The owner can then invite library editors on the test deploy.

Update FIRST_RUN_SETUP step 13 to use it.

**Owned paths:**

- `backend/apps/shared/e2e_logins.py`
- `backend/apps/shared/e2e_passkeys.py`
- `backend/apps/shared/management/commands/bootstrap_platform.py`
- `backend/apps/shared/tests_commands.py`
- `backend/apps/shared/tests_seed_integrity.py`
- `frontend/tests/e2e/support/e2e-passkeys.generated.ts`
- `frontend/tests/e2e/support/passkeys.ts`
- `.gitleaks.toml`
- `docs/runbooks/FIRST_RUN_SETUP.md`

**Done when:**

- seed_e2e creates editor2 with library_editor and a passkey. The seed-integrity guard is green.
- signInAs(page, LOGINS.editor2) works in a journey.
- bootstrap_platform --role library_editor invites a library editor and writes one platform_role.assigned audit row naming the role key.
- A tenant role key or an unknown key is refused.
- gitleaks is clean with the new literals.
- The existing sign-in journeys still pass.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared apps.identity --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `gitleaks git . --config .gitleaks.toml (if the binary is local)`
- `cd frontend && npm run lint && npm run typecheck`
- `npm run test:e2e -- --grep "J-1"`

**Invariants:**

- No passwords.
- The private keys stay test fixtures, allowlisted by exact literal.
- seed_e2e still refuses a deployed environment.
- bootstrap_platform still prints only the one-time link, still refuses a user who holds a live passkey, and now audits the role it grants.
- The command invites; it never creates a session.

### chunk4-T5: Console shell, platform landing and console vocabularies

**Requirements:** ADM-02, PRO-03, VOC-07  
**Scenarios:** supports ADM-S4 and VOC-S11; VOC-S* and J-5 stay green  
**Depends on:** nothing

Add the (console) route group:
- A layout with SessionGate and AppShell surface='console'.
- /console redirects to the first console destination the person's permissions unlock. Anyone without one, including every tenant member, gets the Restricted screen.
- /console/vocabularies and /console/vocabularies/[list] render the existing vocabulary screens with library lists only. library_vocab.manage may write, and every write is a proposal.

A person without a tenant:
- lands on /console after sign-in and from /;
- sees the logo link there;
- sees the console rail on the /me pages. (tenant)/layout.tsx picks the surface from the principal instead of hard-coding 'tenant'.

Registry changes:
- Remove console-sources (chunk 5).
- Remove console-queue; chunk4-T14 re-adds it with its page.
- Keep console-vocabularies.

NavIcon gets icons for console-tenants and console-problem-reports. The shell copy goes into both catalogs.

**Owned paths:**

- `frontend/src/app/(console)/**`
- `frontend/src/app/(tenant)/page.tsx`
- `frontend/src/app/(tenant)/layout.tsx`
- `frontend/src/components/shell/**`
- `frontend/src/components/auth/SignInScreen.tsx`
- `frontend/src/components/admin/VocabulariesScreen.tsx`
- `frontend/src/components/admin/VocabularyScreen.tsx`
- `frontend/src/shared/navigation/**`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`

**Done when:**

- The library editor signs in and lands on /console/vocabularies inside the console rail.
- The editor's /me/passkeys shows the console rail.
- A tenant member opening /console sees the Restricted screen.
- A test shows the console layout fires no tenant query.
- The tenant vocabulary journeys are unchanged and green.
- Unit tests cover the redirect, the gating, the surface choice and the library-only list.
- Feature coverage is at least 98%.
- check:messages is green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run check:copy-drift (if an existing string is reworded)`
- `npm run test:e2e -- --grep "VOC-S|J-1|J-5"`

**Invariants:**

- Permissions only, never role names. The server's 403 remains the enforcer.
- No destination renders 'coming soon'. A destination is registered only when its page exists.
- No string literals in JSX. Pills only through Pill.
- The console shell fires no tenant queries (playbook 6.1).
- Tenant surfaces behave exactly as before for tenant members.

### chunk4-T11: Prove the only door over the real routes

**Requirements:** PRO-01, AC-PRO1, INV-06  
**Scenarios:** PRO-S2 stays green; its AC-PRO1 proof extends to the obligation routes in the fence guard  
**Depends on:** nothing

Extend apps/shared/tests_library_fence.py to prove AC-PRO1 over the real routes:
- apply.apply is called only from proposals.logic.approve.
- approveProposal requires proposals.review, which no tenant role and no API key scope grants.
- Every write operation under /instruments, /provisions, /obligations and /vocab does one of two things:
  - it writes no library row (a problem report, a proposal); or
  - it is chunk 3's re-verification stamp, the single exception.

Leave test_pro_s2 in proposals/tests_scenarios.py untouched: T1 owns that file in this wave, and its vocabulary half stays green.

**Owned paths:**

- `backend/apps/shared/tests_library_fence.py`

**Done when:**

- The fence guard names apply.apply's only caller and the stamp route as the only other library write.
- It is proven to fail once when a second caller of apply.apply is added, then restored.
- It is proven to fail once when a scope or tenant role is given proposals.review, then restored.
- The diff is the one test file.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared apps.proposals apps.library --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- A guard is only strengthened, never loosened.
- The re-verification stamp remains the single exception to proposals and remains only a stamp.
- The proofs of failure are reverted before committing.

### chunk4-T6: Approval applies a new obligation version, with corrections

**Requirements:** PRO-02, AC-PRO2, AC-ID3, PRO-01, INV-04, INV-05  
**Scenarios:** PRO-S3 (un-skipped), PRO-S4 (un-skipped), PRO-S5, PRO-S9 stay green  
**Depends on:** chunk4-T1

Apply new_obligation_version inside library_write():
- Create version n+1 with:
  - ObligationSummary rows per language, original and machine marked;
  - the effective date with its precision;
  - applied_by_proposal, approved_by and approved_at;
  - caused_by_change, from change_id.
- When the payload carries terms, replace the obligation's ObligationTerm links, with before and after in the audit row.

Approve takes the designed body {note, payloadOverrides}:
- Overrides merge over the payload and are validated by the kind's schema. They are allowed for the obligation kind only.
- The merged payload passes T1's source check again. An override that introduces a field without a source (for example terms on a proposal that carried none) answers 422 source_missing and applies nothing.
- The merged result is stored as corrected_payload, with corrected_by and corrected_at, and apply uses it.

Also:
- Add a no-op reindex(obligation_id) in apps/search/logic.py and call it inside the transaction.
- Pass the step-up assertion id to every record() that apply writes, for vocabulary kinds too.
- Un-skip PRO-S3 and PRO-S4.

**Owned paths:**

- `backend/apps/proposals/apply.py`
- `backend/apps/proposals/logic.py`
- `backend/apps/proposals/schemas.py`
- `backend/apps/proposals/api.py`
- `backend/apps/proposals/tests_scenarios.py`
- `backend/apps/proposals/tests_apply.py`
- `backend/apps/search/logic.py`

**Done when:**

- PRO-S3 is un-skipped and green, including the failure case: with reindex patched to raise, there is no new version, no audit row, and the proposal stays open.
- PRO-S4 is un-skipped and green:
  - payload and corrected_payload are both kept;
  - the applied version carries the corrected text and scope;
  - an override adding an unsourced field answers 422 source_missing and writes nothing.
- A test collects every audit row an approval transaction wrote, for the obligation kind and a vocabulary kind, and asserts each carries the assertion id.
- PRO-S5 and PRO-S9 are green.
- The proposals floors hold: apply 90, logic 97, api 96.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.proposals apps.search apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- Everything is one transaction.
- Library writes happen only in apply.py, under library_write().
- Nothing is overwritten: a new version row is added and earlier rows stay untouched.
- Four eyes is unchanged (constraint and 409). The reviewer's corrections are recorded as the reviewer's.
- A field without a source never reaches the library.
- Approval keeps @requires_step_up.
- Decision audit rows are library rows and carry no tenant member's identity.

### chunk4-T7: Create a tenant and invite its first admin from the console

**Requirements:** ADM-02, ADM-03, ID-01, TEN-01  
**Scenarios:** ADM-S6 (narrowed, un-skipped), ADM-S4 (reworded, integration un-skipped), TEN-S6 (Gherkin clause added, stays skipped)  
**Depends on:** chunk4-T3, chunk4-T4

Add two routes under tenants.manage:
- GET /console/tenants lists name, slug, status, default language and created.
- POST /console/tenants takes {name, slug, timezone, defaultLanguage, contentLanguages, firstAdminEmail, firstAdminTitle?}.

Creation:
- Writes the tenant.
- Activates only that new tenant, inside the same transaction.
- Runs set_content_languages, ensure_system_roles, ensure_tenant_vocabularies, and create_invitation with roles_by_keys(['admin']).
- Records tenant.created in that tenant's audit log.
- A taken slug answers 409 duplicate_key.

Scenarios in governance/app.md:
- Narrow ADM-S6 to creating a tenant with its first admin invited. Plans are NFR-S17 to S19; append the support-access-request clause to TEN-S6's Gherkin.
- Reword ADM-S4: every console destination and endpoint that exists answers to its owning platform role and 403s the other.
- Under ADM-S4, name each deferred surface with its chunk: sources (5), evaluation sets (7), agent definitions (11), system health (14), support access (TEN-S6), plans (NFR-S17 to S19), and language and jurisdiction edits (their card; jurisdictions are read-only on the vocabularies screen).
- Un-skip ADM-S6.
- Un-skip ADM-S4 as a data-driven test:
  - Every operation gated by a platform permission answers 403 naming requiredPermission to the other platform role.
  - So does each route in an explicit list of logic-gated platform routes: POST /proposals now; chunk4-T16b adds GET /problem-reports.

Update FIRST_RUN_SETUP steps 6 and 7.

**Owned paths:**

- `backend/apps/tenants/logic.py`
- `backend/apps/tenants/api.py`
- `backend/apps/tenants/schemas.py`
- `backend/apps/tenants/tests_console_tenants.py`
- `backend/apps/tenants/app.md`
- `backend/apps/governance/app.md`
- `backend/apps/governance/tests_scenarios.py`
- `docs/runbooks/FIRST_RUN_SETUP.md`

**Done when:**

- ADM-S6 and ADM-S4 are reworded, un-skipped and green.
- The new tenant has its system roles, tenant vocabularies, content languages and one pending admin invitation. The mock outbox holds its mail after commit.
- The library editor gets 403 naming tenants.manage.
- The platform admin gets 403 on POST /proposals, with requiredPermission named.
- There are no member counts and no tenant detail route.
- requirements_coverage is green after the app.md edits.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.tenants apps.governance apps.identity apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*' (logic.py >= 87, api.py >= 96)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- Platform staff have no bypass: the call activates only the tenant it just created and reads no other tenant's rows (chunk4-T15 reviews this).
- The invitation token never appears in a path or a log.
- Audit rows are in the same transaction.
- No step-up, matching the tenant-side invite and playbook 4.2.
- Permissions, never role names.
- A scenario is narrowed only in app.md, with its deferred parts named.

### chunk4-T8: Seed each journey's proposal and a problem report

**Requirements:** PRO-01, PRO-02, AUD-03  
**Scenarios:** seeds PRO-S3, PRO-S4, PRO-S5, PRO-S7, PRO-S9, AUD-S5  
**Depends on:** chunk4-T1, chunk4-T4

Extend seed_e2e idempotently. Every seeded proposal goes through proposals.logic.create, so it passes validation.

No fixture proposal is seeded:
- p1: the library loader already filed its version 2.
- p2 and p3: their kinds are deferred to chunk 5.

One pending new_obligation_version proposal per consuming journey, with a source per changed field:
- PRO-S3.
- PRO-S4, carrying a sourced scope term to correct.
- PRO-S9.
- PRO-S7.
- Each sits on a distinct obligation that has version 1 only, is inside tenant A's footprint and is not advice-only. Candidates: obl-client-assets, obl-costs-charges, obl-appropriateness, plus one more.
- A constant maps each proposal to its journey.

Also seed:
- One vocabulary_relabel proposed by editor@bleqq.test, for PRO-S5.
- One open problem report from tenant A's reader on the research payment obligation, for AUD-S5.

Extend the seed-integrity guard to demand all of these. Recreate a seeded proposal only when none of its kind is waiting on that target.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py`
- `backend/apps/shared/tests_seed_integrity.py`

**Done when:**

- The seed-integrity guard is green with the proposal and report expectations.
- Running seed_e2e twice changes nothing.
- Every seeded proposal is open with a source per changed field.
- The PRO-S5 proposal has proposed_by_user = editor.
- No research-payments proposal is waiting.
- The seed still refuses a deployed environment.
- e2e_seed.py holds its floor of 96.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared apps.proposals --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/e2e_seed.py' (>= 96)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- Extend the seed, never mock.
- Deterministic, with no randomness and no time-relative values.
- Proposals are library-zone. The report is a tenant row, written with its tenant activated.
- Every row is audited through record().
- The seed creates proposals but never applies them, so there are no library writes outside the allowed paths.

### chunk4-T9: Tenant audit log screen

**Requirements:** AUD-01, ADM-01  
**Scenarios:** AUD-S3 (un-fixme'd)  
**Depends on:** chunk4-T3, chunk4-T5

Build /admin/audit-log (audit.read) from the prototype's vAudit() cut and the shared states:
- Filters: subject type, a record, actor and date range.
- Each row: actor, action, subject title, time, a before-and-after diff, and a marker when a passkey step-up completed the action.
- Empty, loading, error and denied states.

Also:
- Add features/governance: api, hooks, and audit presentation with tests.
- Add the registry entry admin-audit-log under Admin.
- Add audit.read to the Admin index permissions, so every role reaches it.
- Write the copy in both catalogs.
- Un-fixme AUD-S3: an admin creates an API key with step-up, then filters the log to that event and sees its passkey marker.

**Owned paths:**

- `frontend/src/app/(tenant)/admin/audit-log/**`
- `frontend/src/components/admin/AuditLogScreen.tsx`
- `frontend/src/features/governance/**`
- `frontend/src/shared/navigation/**`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/governance.journey.spec.ts`

**Done when:**

- AUD-S3 is un-fixme'd and green.
- The reader login sees Admin, with Organisation and Audit log only.
- features/governance coverage is at least 98%.
- check:messages is green.
- ADM-S1 still passes.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "AUD-S3|ADM-S1"`

**Invariants:**

- Pills only through Pill, with tones by kind.
- No string literals in JSX.
- Before and after are rendered as data, never turned into phrases by the client.
- Nothing from the log is written to the console logger.

### chunk4-T13a: Mark the library as seen (POST /me/visit)

**Requirements:** PRO-03, AUD-01, AC-AUD1  
**Scenarios:** supports PRO-S7 (the since bookmark)  
**Depends on:** chunk4-T3

Implement the designed POST /me/visit (markVisit, 204) on a tenant session:
- It sets Membership.last_visit_at to now.
- It writes one audit row in the member's tenant.
- Register it in UNGATED_BY_DESIGN as self.
- Delete its stale line in contract_drift_pending.txt.

Nothing else in this plan touches the identity files, and T13b reads the bookmark this sets.

**Owned paths:**

- `backend/apps/identity/api.py`
- `backend/apps/identity/me_logic.py`
- `backend/apps/identity/schemas.py`
- `backend/apps/identity/tests_visit.py`
- `backend/apps/shared/permissions.py`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- markVisit moves the bookmark and writes one audit row carrying the member's tenant.
- A session without a tenant answers 403 or 404 as the route guard expects, and writes nothing.
- The route-permission and audit-on-write guards are green.
- contract_drift is clean for POST /me/visit.
- The floors hold: identity/api.py 95, me_logic.py 89, permissions.py 97.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/api.py,apps/identity/me_logic.py,apps/shared/permissions.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- The membership is written under RLS, in the caller's tenant only.
- Audit on write, in the same transaction.
- No tenant content in logs.

### chunk4-T10: Queue reads, rejection reasons and the tenant's own proposals

**Requirements:** PRO-01, PRO-03, VOC-07, INV-04  
**Scenarios:** PRO-S9 (moved to a seeded reason key), supports PRO-S7 and VOC-S11; PRO-S1..S6 stay green  
**Depends on:** chunk4-T6, chunk4-T2

Enrich GET /proposals/{id} for the version kind and the vocabulary kinds:
- The target obligation's title and reference, and the instrument's short name.
- The current version's summary in the proposal's original language.
- The proposed text, or the corrected text.
- The sentence diff, from chunk 3's function.
- A source {field, label, url} per changed field.
- Scope before and after.
- rejectionReason {key, label}.
- Once applied, the version it created, found through ObligationVersion.applied_by_proposal.

Every row of GET /proposals carries: target title and reference, instrument short name, source label, proposer, and isMine.
- For a proposal with proposed_in_tenant, return no proposer name or id. Return fromOrganisation=true instead, the same rule the console applies to problem reporters.
- Compute isMine on the server.
- Add origin (agent|user) and notMine filters.
- Batch the lookups and re-pin PROPOSAL_QUEUE_QUERIES.

Rejection: validate rejectionCode against active rejection_reason rows (422 reason_required otherwise), and move PRO-S9 to a seeded reason key.

Add GET /tenant/proposals (vocab.manage):
- It lists only proposals linked to the caller's tenant through proposal_tenant.
- Filters: status, kind and targetList.
- It feeds the tenant vocabulary screen's pending list.

**Owned paths:**

- `backend/apps/proposals/logic.py`
- `backend/apps/proposals/schemas.py`
- `backend/apps/proposals/api.py`
- `backend/apps/proposals/tests_scenarios.py`
- `backend/apps/proposals/tests_reading.py`
- `backend/apps/proposals/reading.py (only if the reads move out of logic.py)`

**Done when:**

- Tests cover:
  - the detail for the version kind and a vocabulary kind;
  - the diff ops;
  - a source per changed field;
  - the row fields;
  - the origin and notMine filters.
- A tenant-made proposal's row and detail carry no proposer name or id, and a platform editor's own proposal carries isMine=true.
- PRO-S9 is green. An unknown or retired reason answers 422 reason_required.
- Tenant B's GET /tenant/proposals never returns tenant A's proposals.
- The queue query count is constant in the row count.
- GET /proposals and GET /proposals/{id} still answer 403 to every tenant role.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.proposals apps.library apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- The review routes stay proposals.review only (PRO-S7).
- The tenant read goes through RLS on proposal_tenant, never a Python tenant filter.
- No tenant member's identity reaches platform staff, and no proposer identity from another tenant reaches a tenant.
- There is one sentence-diff implementation, chunk 3's.
- Performance budget: 250 ms.

### chunk4-T12: Tenants screen and the console role matrix

**Requirements:** ADM-02, ADM-03  
**Scenarios:** ADM-S6 (un-fixme'd), ADM-S4 (un-fixme'd, registry-driven)  
**Depends on:** chunk4-T7, chunk4-T9, chunk4-T4

Build /console/tenants (tenants.manage):
- The tenant list, with status and created date.
- A Create tenant form: name, slug, timezone, default and content languages from GET /reference/languages, and the first admin's email and title. A 409 duplicate_key is shown in place.
- The four states.

Add the console-tenants registry entry, features/console-tenants (api, hooks and presentation, with tests), and the copy in both catalogs.

Un-fixme two journeys:
- ADM-S6: the platform admin creates a tenant with a per-attempt slug, and the invitation mail appears in the mock outbox.
- ADM-S4, driven by the registry:
  - For the editor and for the platform admin, each of their own console destinations is visible and opens.
  - The other role's destinations are absent, and their direct URLs show the Restricted screen naming the missing permission.
  - Later registry entries (queue, problem reports) join the journey without editing it.

**Owned paths:**

- `frontend/src/app/(console)/console/tenants/**`
- `frontend/src/components/console/TenantsScreen.tsx`
- `frontend/src/features/console-tenants/**`
- `frontend/src/shared/navigation/**`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/governance.journey.spec.ts`

**Done when:**

- ADM-S6 and ADM-S4 are un-fixme'd and green, with retries settling.
- The library editor never sees Tenants.
- The ADM-S4 journey reads the destinations from the registry, not from a hard-coded list.
- features coverage is at least 98%.
- check:messages is green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "ADM-S4|ADM-S6"`

**Invariants:**

- The screen reads only the tenant list, with no member data.
- The console fires no tenant query.
- The server's 403 decides, and the screen renders its requiredPermission.
- No string literals.

### chunk4-T16a: The problem-report review window in the database (needs Q1)

**Requirements:** AUD-03, INV-06  
**Scenarios:** supports AUD-S5 and AUD-S7 (mixed-table policy stays pinned)  
**Depends on:** chunk4-T1

Starts only after Alex answers Q1 with option A. Written test-first.

The policies:
- Leave the FOR ALL tenant policy on problem_report as it is.
- Add two permissive policies keyed on a transaction-local flag, one FOR SELECT and one FOR UPDATE. INSERT and DELETE therefore never match the flag.

The trigger:
- Add a BEFORE UPDATE trigger, like cw_outbox_guard.
- While the flag is on, it refuses a change to any column other than status, resolution_note, resolved_by, resolved_at and resolved_by_proposal.

The flag:
- tenancy.problem_review() sets it for the shortest possible block and clears it after.
- Only apps/governance/problem_reports_logic.py may call it, enforced by an AST guard like identity_lookup's.

The model: add resolution_note, resolved_by and resolved_at in the next library migration after chunk 3's.

Pin the policy and trigger text in tests_rls.py.

This task does not depend on T15. Like every tenancy change it gets the main agent's per-merge security review, and T22 reviews it in full.

**Owned paths:**

- `backend/apps/shared/tenancy.py`
- `backend/apps/shared/tests_tenancy.py`
- `backend/apps/shared/tests_rls.py`
- `backend/apps/shared/factories.py`
- `backend/apps/library/models.py`
- `backend/apps/library/migrations/<next after chunk 3>_problem_report_review.py`

**Done when:**

- On the app alias, with the flag set:
  - INSERT is refused, and so is DELETE.
  - An update to text, tenant_id, reporter_id, subject_type or subject_id is refused.
  - An update to the resolution columns succeeds.
- Without the flag, a console session sees only rows without a tenant, as before.
- The flag is off after the block, including when the block raises.
- The RLS guard pins both new policies and the trigger.
- The AST guard is proven to fail once when another module calls problem_review(), then restored.
- makemigrations --check and migrate_from_zero are clean.
- tenancy.py holds its floor of 96.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.shared apps.library --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/tenancy.py' (>= 96)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- Forced RLS stays.
- The exception covers problem_report only, SELECT and UPDATE only, the resolution columns only, and only inside one module.
- The app role still cannot bypass RLS.
- If Alex chooses option B, re-plan this task before starting.

### chunk4-T13b: Library updates since the last visit

**Requirements:** PRO-03, FP-03, INV-04  
**Scenarios:** PRO-S7 (un-skipped)  
**Depends on:** chunk4-T10, chunk4-T13a

Add GET /library-updates (library.read, tenant session). It returns approved proposals applied since `since`:
- `since` defaults to the membership's last_visit_at (set by T13a). Otherwise it goes back LIBRARY_UPDATES_DEFAULT_DAYS, a setting with an env override.
- Results are grouped by the tenant-local date.
- Each item gives kind, applied time, effective date, the obligation or vocabulary row touched, and the version created. For an obligation that is id, title, reference and instrument short name.
- Each item is titled by the library record, never by the proposal: a tenant-made proposal's own wording never reaches another tenant.
- Results are filtered to the footprint through taxonomy.matching unless outsideFootprint=true. Vocabulary changes are always listed.
- No proposer identity.

Un-skip PRO-S7:
- The officer gets 403 on the review route.
- The queue detail carries sources and the diff.
- The tenant lists an applied proposal.
- 'This looks wrong' creates a report through chunk 3's route.

**Owned paths:**

- `backend/apps/proposals/updates.py`
- `backend/apps/proposals/schemas.py`
- `backend/apps/proposals/api.py`
- `backend/apps/proposals/tests_scenarios.py`
- `backend/apps/proposals/tests_updates.py`
- `backend/config/settings.py`
- `.env.example`
- `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- PRO-S7 is un-skipped and green.
- An update on an advice-only obligation is hidden from tenant A unless outsideFootprint=true.
- A vocabulary change applied from a tenant-A proposal reaches tenant B under the vocabulary row's label, not the proposal title.
- The setting is documented in .env.example and RAILWAY_VARIABLES.md.
- The query count is constant in the item count.
- config/settings.py holds its floor of 85.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.proposals apps.identity apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*,config/settings.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- A tenant session read (membership under RLS).
- The footprint cut comes only from taxonomy.matching.
- No other tenant's data, wording or proposer identity.
- Dates convert through the tenant's timezone explicitly.
- The window is a setting.

### chunk4-T14: Proposal queue list and detail (read)

**Requirements:** PRO-01, PRO-03, AC-PRO2  
**Scenarios:** PRO-S5 (un-fixme'd), ADM-S4 stays green with Queue in the editor's rail  
**Depends on:** chunk4-T10, chunk4-T12, chunk4-T8

Build /console/queue and /console/queue/[proposalId] from console-queue.html.

The list:
- Waiting, Approved and Rejected tabs, with totals from the API.
- Kind, origin and Not mine filters.
- Each row: kind and status pills, the proposer, time, a Yours marker from isMine, title, target and source. The proposer is an agent run, a named platform person, or 'A member of an organisation' when fromOrganisation.

The detail:
- The source panel beside What changes, with sentence diff marks.
- Effective date, and scope before and after.
- The vocabulary variant.
- Applied and rejected states.
- On the editor's own proposal, the card's four-eyes notice replaces Approve.

Also:
- Add features/proposals: api, hooks, presentation, and tones by kind and status in tone-by-kind.ts.
- Re-add the console-queue registry entry.
- Write the copy in both catalogs, including:
  - the keys chunk4-T20's pending list needs, so that task touches no catalog;
  - admin.vocabularies.list.rejection_reason and admin.vocabularies.marker.rejection_reason.
- Un-fixme PRO-S5.

**Owned paths:**

- `frontend/src/app/(console)/console/queue/**`
- `frontend/src/components/console/QueueScreen.tsx`
- `frontend/src/components/console/ProposalDetailScreen.tsx`
- `frontend/src/features/proposals/**`
- `frontend/src/features/shared/tone-by-kind.ts`
- `frontend/src/features/shared/tone-by-kind.test.ts`
- `frontend/src/shared/navigation/**`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/proposals.journey.spec.ts`

**Done when:**

- PRO-S5 is un-fixme'd and green.
- ADM-S4 is green with Queue in the rail.
- No journey asserts an exact queue count.
- No tenant member's name is rendered on any queue surface.
- features coverage is at least 98%.
- check:messages is green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "PRO-S5|ADM-S4"`

**Invariants:**

- Tones are chosen by kind or slot, never by a person. Pills only through Pill.
- The client branches on kind and code, never on detail or a phrase.
- No string literals.
- The server enforces four eyes; the screen only explains it.

### chunk4-T16b: Problem reports reach the console (needs Q1)

**Requirements:** AUD-03, PRO-03, ADM-02  
**Scenarios:** supports AUD-S5; ADM-S4 (logic-gated list extended)  
**Depends on:** chunk4-T16a, chunk4-T3, chunk4-T7, chunk4-T13a

Starts only after Q1 is answered with option A and chunk4-T16a is on main.

Serve GET /problem-reports as a logic gate, and register it in UNGATED_BY_DESIGN.

A proposals.review holder:
- Reads inside tenancy.problem_review().
- Gets every report, with organisation name, subject title and version, and resolvedByProposal {id}.
- Never gets the reporter.

A tenant member:
- Gets only rows whose tenant_id is their own tenant, and no rows without a tenant.
- mine=true narrows to their own reports.

Any other caller gets 403 naming proposals.review. That includes a platform session without proposals.review and an API key.

Filters: status and organisation.

Also:
- Add GET /problem-reports to ADM-S4's explicit list of logic-gated platform routes in governance/tests_scenarios.py.
- Keep or delete its contract_drift_pending line according to the built shape.

**Owned paths:**

- `backend/apps/governance/problem_reports_logic.py`
- `backend/apps/governance/api.py`
- `backend/apps/governance/schemas.py`
- `backend/apps/governance/tests_problem_reports.py`
- `backend/apps/governance/tests_scenarios.py`
- `backend/apps/shared/permissions.py`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- A console read lists reports from tenants A and B, with organisation names, resolvedByProposal and no reporter field.
- Tenant B never sees tenant A's reports, and a tenant never sees reports without a tenant.
- The platform admin and an API key get 403 naming proposals.review, and ADM-S4 asserts it.
- The flag is off after the read.
- The floors hold: permissions.py at 97, and governance holds its measured coverage.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/*,apps/shared/permissions.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- The review window opens only after proposals.review is checked, and only inside problem_reports_logic.py.
- Platform staff never see the reporter.
- Tenant content never reaches logs or Sentry.

### chunk4-T15: Security review 1: the door, four eyes, audit and tenancy

**Requirements:** AC-PRO1, AC-PRO2, AC-AUD1, AC-ID3, AC-NFR1  
**Scenarios:** PRO-S2, PRO-S3, PRO-S4, PRO-S5, PRO-S7, AUD-S7, ADM-S4, ADM-S6  
**Depends on:** chunk4-T1, chunk4-T2, chunk4-T3, chunk4-T4, chunk4-T5, chunk4-T6, chunk4-T7, chunk4-T8, chunk4-T9, chunk4-T10, chunk4-T11, chunk4-T12, chunk4-T13a, chunk4-T13b, chunk4-T14

Review main after the tasks that do not need Q1 (T1 to T14) against the CLAUDE.md invariants. The areas:
- Four eyes: the constraint, the 409, and corrections recorded as the reviewer's.
- The source check at creation and approval.
- The library fence and the AC-PRO1 proof.
- Step-up on approval, and the assertion id on every audit row an approval writes.
- proposal_tenant RLS and the isolation of GET /tenant/proposals.
- The audit read's row rule:
  - library subjects and platform, agent or system actors only;
  - tenant-authored proposal text in any row another tenant can see;
  - every record(tenant_id=None) whose actor is a tenant member.
- Proposer identity withheld from the console for tenant-made proposals.
- GET /library-updates: the footprint cut, record titles, no other tenant's data.
- POST /me/visit.
- Console tenant creation activating only its own new tenant.
- bootstrap_platform --role: which role it grants, its platform_role.assigned audit row, and its refusal of a user who already holds a passkey.
- The console shell firing no tenant queries.

Write findings, with severity and a reproduction, into the review file. A critical or high finding becomes a fix task before wave 6 merges.

**Owned paths:**

- `docs/security/CHUNK4_REVIEW_2026-09-19.md`

**Done when:**

- The review file gives each listed area a verdict with evidence: a test, a query or a probe.
- Findings are ranked by severity.
- No critical finding is left without a fix task.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.proposals apps.governance apps.tenants apps.identity apps.shared --settings=config.test_settings --noinput (read-only verification, plus throwaway probes that are never committed)`

**Invariants:**

Read-only on code. The only output is the review file. Never lower a gate or weaken a guard to demonstrate a finding; prove it with a probe and revert.

### chunk4-T17: Approve, correct and reject in the queue

**Requirements:** PRO-02, AC-PRO2, AC-ID3  
**Scenarios:** PRO-S3, PRO-S4, PRO-S9 (un-fixme'd), PRO-S5 stays green  
**Depends on:** chunk4-T14, chunk4-T6, chunk4-T10, chunk4-T2

On the queue detail add:
- Correct before approving:
  - The form offers only fields the proposal already sources: text per language with the original marked, effective date, and the scope chips when the proposal carries terms.
  - Corrections are sent as payloadOverrides.
  - A 422 source_missing renders in place.
- Approve and apply, through the global step-up dialog. A four-eyes 409 renders as the card's alert.
- Reject:
  - With a reason picked from the rejection_reason list, plus a note.
  - The button stays disabled until both are given.

Un-fixme three journeys:
- PRO-S3: approve and see the applied state; then a tenant reader opens the obligation and sees version 2 with Show what changed.
- PRO-S4: the corrected text and scope are what the obligation shows.
- PRO-S9: a reject without a reason is refused; one with a reason lands under Rejected.

**Owned paths:**

- `frontend/src/components/console/ProposalDetailScreen.tsx`
- `frontend/src/components/console/ProposalCorrectionForm.tsx`
- `frontend/src/components/console/RejectProposalDialog.tsx`
- `frontend/src/features/proposals/**`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/proposals.journey.spec.ts`

**Done when:**

- PRO-S3, PRO-S4 and PRO-S9 are un-fixme'd and green.
- Each journey settles on 'waiting or already applied', so a retry passes.
- Every 403 step_up_required, and every 409 or 422 provoked on purpose, is declared with apiGuard.allow.
- features coverage is at least 98%.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "PRO-S3|PRO-S4|PRO-S5|PRO-S9"`

**Invariants:**

- Step-up only through the global StepUpProvider.
- No client-side four-eyes rule or source rule replaces the server's.
- No string literals. Pills through Pill.
- Journeys never mock an API and never assert exact queue counts.

### chunk4-T18: A proposal resolves a problem report (needs Q1)

**Requirements:** AUD-03, PRO-02, AC-AUD1, AC-ID3  
**Scenarios:** AUD-S5 (un-skipped)  
**Depends on:** chunk4-T16b, chunk4-T13b, chunk4-T6, chunk4-T10

POST /proposals takes an optional problemReportId from a console proposer (proposals.review or library_vocab.manage):
- It links the report's resolved_by_proposal in the same transaction, inside tenancy.problem_review().
- The report then reads 'In a proposal'.

What happens next:
- Approving that proposal sets the report to fixed, with resolved_by and resolved_at.
- Rejecting it returns the report to open, with the rejection note as its resolution note.
- PATCH /problem-reports/{id} (proposals.review) takes {status: 'rejected', resolutionNote}. The note is required.

Each resolution writes a library audit row and an outbox event, problem_report.resolved. Neither carries report text or the reporter.

Every audit row written during an approval carries the approval's step_up_assertion_id, including problem_report.resolved.

Un-skip AUD-S5. In app.md, note that the agents' next-run clause arrives with chunk 5, which reads that topic.

**Owned paths:**

- `backend/apps/governance/problem_reports_logic.py`
- `backend/apps/governance/api.py`
- `backend/apps/governance/schemas.py`
- `backend/apps/governance/tests_scenarios.py`
- `backend/apps/governance/app.md`
- `backend/apps/proposals/logic.py`
- `backend/apps/proposals/schemas.py`
- `backend/apps/proposals/api.py`
- `backend/apps/proposals/tests_apply.py`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- AUD-S5 is un-skipped and green.
- A report can be linked only once.
- A tenant member's problemReportId is refused.
- Approve and reject move the report inside their own transaction, or roll back with it.
- The approval test asserts every audit row it wrote carries the assertion id, problem_report.resolved included.
- GET /problem-reports shows resolvedByProposal after linking.
- The audit-on-write guard is green for the PATCH operation.
- The proposals floors hold.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/*,apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`

**Invariants:**

- The report is written only inside problem_reports_logic, under the Q1 mechanism, and only in its resolution columns.
- Four eyes is unchanged: the editor who starts a proposal cannot approve it.
- One transaction.
- No report text or reporter in the audit or outbox rows.
- Proposals stay the only door.

### chunk4-T19: Library updates screen

**Requirements:** PRO-03, INV-04, INV-06, FP-03  
**Scenarios:** PRO-S7 (un-fixme'd), chunk 3's INV-S4, INV-S5, INV-S7 stay green  
**Depends on:** chunk4-T13a, chunk4-T13b, chunk4-T17

Build /inventory/updates from tenant-library-updates.html:
- The 'since' line, and Mark as seen (POST /me/visit).
- Kind chips, and Show outside footprint.
- Day groups, with kind and instrument pills.
- Show what changed links to chunk 3's obligation diff. This looks wrong opens chunk 3's report dialog.
- The four states.

Also:
- Add a Library updates link to chunk 3's inventory screen.
- Add features/library-updates: api, hooks, presentation, and tones by update kind.
- Write the copy in both catalogs.

Un-fixme PRO-S7:
- The compliance officer's direct /console/queue shows Restricted, with the 403 declared.
- The editor approves the seeded PRO-S7 proposal.
- A tenant member, on a login no other journey marks as seen, finds it under today's date, opens the diff and sends a report.

**Owned paths:**

- `frontend/src/app/(tenant)/inventory/updates/**`
- `frontend/src/components/inventory/LibraryUpdatesScreen.tsx`
- `frontend/src/components/inventory/<chunk 3 inventory screen> (one link only)`
- `frontend/src/features/library-updates/**`
- `frontend/src/features/shared/tone-by-kind.ts`
- `frontend/src/features/shared/tone-by-kind.test.ts`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/proposals.journey.spec.ts`

**Done when:**

- PRO-S7 is un-fixme'd and green, and settles on 'waiting or already applied' on retry.
- The outside-footprint toggle and the day grouping are proven in unit tests.
- features coverage is at least 98%.
- check:messages is green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "PRO-S7|INV-S"`

**Invariants:**

- The footprint rule is the server's.
- Tones by kind. Pills through Pill.
- No string literals.
- Every member can read and report, and nothing on this screen edits the library.

### chunk4-T20: The tenant's pending library proposals and VOC-S11's console half

**Requirements:** VOC-07, PRO-03  
**Scenarios:** VOC-S11 (extended), VOC-S15 (J-5) stays green  
**Depends on:** chunk4-T10, chunk4-T14, chunk4-T17, chunk4-T4

On the tenant vocabulary screen of a library list:
- List what this tenant proposed and is still waiting (GET /tenant/proposals?status=open&targetList=<list>), under [data-pending-proposals].
- Each row carries its proposal id.
- Use the keys chunk4-T14 wrote.
- Remove the chunk 4 comment.

In features/vocabularies/vocabulary-presentation.ts:
- Add rejection_reason to listTitle and listMarker, using the keys T14 wrote.
- Add a unit test that every key in both maps resolves in en and sv.

Extend VOC-S11 to match its Gherkin, safe under fullyParallel and a retry:
- The compliance officer's proposal is asserted by the proposal id the POST returned, present in her pending list. No count is asserted.
- The library editor proposes a value with a label unique to the attempt on the console vocabularies screen.
- It stays absent until editor2 approves it in the queue, then it appears. The approval step settles on 'waiting or already applied'.

**Owned paths:**

- `frontend/src/components/admin/VocabularyScreen.tsx`
- `frontend/src/features/vocabularies/**`
- `frontend/tests/e2e/taxonomy.journey.spec.ts`

**Done when:**

- VOC-S11 is green end to end, and passes when run twice against the same database.
- J-5 is still green.
- The Swedish list of lists shows rejection_reason's catalog title.
- Neither message catalog changed.
- features coverage is at least 98%.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "VOC-S11|VOC-S15"`

**Invariants:**

- The tenant sees only its own tenant's proposals, enforced by the server through RLS.
- The tenant side has no approval UI.
- The journey approves with step-up as editor2, never as the proposer.
- No exact counts in journeys.

### chunk4-T22: Security review 2: the problem-report exception (needs Q1)

**Requirements:** AC-NFR1, AC-AUD1, AC-PRO2, AUD-03  
**Scenarios:** AUD-S5, AUD-S7, ADM-S4  
**Depends on:** chunk4-T15, chunk4-T16a, chunk4-T16b, chunk4-T18

Review T16a, T16b and T18 on main. The areas:
- The Q1 mechanism:
  - the policy text: SELECT and UPDATE only;
  - the column trigger;
  - flag scope and lifetime;
  - the AST guard;
  - no other table touched;
  - no reporter identity reaches platform staff;
  - writes limited to the resolution columns.
- GET /problem-reports: the 403 for every caller without proposals.review or a tenant, and tenant isolation.
- The resolution loop:
  - four eyes when an editor starts a proposal;
  - transaction boundaries;
  - the assertion id on the resolution row;
  - audit and outbox rows free of report text.

Append the findings to the chunk 4 review file. A critical or high finding becomes a fix task before chunk4-T23 merges.

**Owned paths:**

- `docs/security/CHUNK4_REVIEW_2026-09-19.md`

**Done when:**

- The review file gains a section giving each listed area a verdict and evidence.
- No critical finding is left without a fix task.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.governance apps.proposals apps.library apps.shared --settings=config.test_settings --noinput (read-only verification, plus throwaway probes that are never committed)`

**Invariants:**

Read-only on code. The only output is the review file. Never weaken a guard to show a finding; prove it with a probe and revert.

### chunk4-T21: Problem reports in the console (needs Q1)

**Requirements:** AUD-03, ADM-02  
**Scenarios:** ADM-S4 stays green with Problem reports in the editor's rail and Restricted for the platform admin; supports AUD-S5  
**Depends on:** chunk4-T16b, chunk4-T18, chunk4-T19

Build /console/problem-reports and its detail from console-problem-reports.html:
- Open, In a proposal, Fixed and Rejected tabs. In a proposal is derived from open plus resolvedByProposal.
- An organisation filter, plus a 'where' filter if chunk 3 stores that field.
- Each row: status and 'where' pills, organisation, time, the quoted report and the record it concerns.
- The detail, with Reject with a reason (PATCH) and the fixed state.
- The four states.

Also:
- Add the console-problem-reports registry entry (proposals.review). The registry-driven ADM-S4 journey then opens /console/problem-reports as the platform admin and expects Restricted, with no spec edit.
- Add features/problem-reports: api, hooks, presentation, and tones by report status.
- Write the copy in both catalogs.

**Owned paths:**

- `frontend/src/app/(console)/console/problem-reports/**`
- `frontend/src/components/console/ProblemReportsScreen.tsx`
- `frontend/src/components/console/ProblemReportDetailScreen.tsx`
- `frontend/src/features/problem-reports/**`
- `frontend/src/features/shared/tone-by-kind.ts`
- `frontend/src/features/shared/tone-by-kind.test.ts`
- `frontend/src/shared/navigation/**`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`

**Done when:**

- Unit tests cover the tabs, the derived In a proposal state and reject.
- ADM-S4 is green, including the platform admin's Restricted screen on /console/problem-reports.
- No reporter identity is rendered anywhere.
- features coverage is at least 98%.
- check:messages is green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "ADM-S4"`

**Invariants:**

- Tones by kind. Pills through Pill.
- No reporter details.
- No string literals.
- The console fires no tenant queries apart from the report read Q1 allows.

### chunk4-T24a: Close chunk 4 without the Q1 tail: contract, floors, status and runbooks

**Requirements:** PRO-01, PRO-02, PRO-03, AUD-01, AUD-03, ADM-02  
**Scenarios:** all non-Q1 chunk 4 scenarios reported; AGT-S10, AUD-S4, AUD-S6, ADM-S5, PRO-S8 stay pending with their chunks named; AUD-S5 pending on Q1  
**Depends on:** chunk4-T1, chunk4-T2, chunk4-T3, chunk4-T4, chunk4-T5, chunk4-T6, chunk4-T7, chunk4-T8, chunk4-T9, chunk4-T10, chunk4-T11, chunk4-T12, chunk4-T13a, chunk4-T13b, chunk4-T14, chunk4-T15, chunk4-T17, chunk4-T19, chunk4-T20

INPUT_DELTAS:
- In §7, record each reshaped or new operation this plan built outside Q1:
  - GET /audit-events;
  - GET /proposals row fields and the GET /proposals/{id} detail;
  - approve with payloadOverrides;
  - rejectionCode as a rejection_reason key;
  - GET /tenant/proposals;
  - GET /library-updates;
  - GET and POST /console/tenants.
- In §1, record rejection_reason as a tier-two list replacing schema.sql's rejection_code CHECK.
- Delete the matching pending lines.

Set coverage floors for the new and changed modules outside Q1, from a full coverage run on main.

Status and ledgers:
- app.md status cells: PRO-01 to PRO-03 built, AUD-01 in progress, AUD-03 in progress, ADM-02 in progress, and VOC-07 if VOC-S11 completes it.
- UI plan ledger rows: paths fixed and cards built. Languages, health, AI log, sources and the new-obligation and re-verification queue variants are deferred with their chunks.
- The IMPLEMENTATION_STATUS chunk 4 row:
  - every cut and default;
  - the PRO-S1, ADM-S4 and ADM-S6 narrowings;
  - the Q1 tasks (T16a, T16b, T18, T21, T22, T23, T24b) named as outstanding or merged, as git log shows.
- The chunk 2 note on the pending list.

Other docs:
- The fixture README: p1 is filed; p2 and p3 are deferred with their kinds to chunk 5.
- FIRST_RUN_SETUP's deploy-seed row for rejection reasons.
- TODO_FOR_alex: D-14 editors via bootstrap_platform --role.

**Owned paths:**

- `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`
- `backend/scripts/coverage_gate.py`
- `backend/apps/proposals/app.md`
- `backend/apps/governance/app.md`
- `backend/apps/taxonomy/app.md`
- `docs/plans/UI_Implementation_Plan.md`
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `backend/apps/library/fixtures/README.md`
- `docs/runbooks/FIRST_RUN_SETUP.md`
- `docs/TODO_FOR_alex.md`

**Done when:**

- contract_drift passes with no stale or unexplained line.
- A full-suite coverage_gate passes with the new floors.
- requirements_coverage and compliance_check --all are green.
- The status files name every cut, default and narrowing of this plan, and every Q1 task still outstanding.
- The docs changed are only the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`
- `python backend/scripts/requirements_coverage.py && python backend/scripts/compliance_check.py --all`

**Invariants:**

- Floors sit just below measured coverage and never go lower than before.
- A pending line moves to INPUT_DELTAS only with its reason.
- Status reflects git log, not intentions.
- Operations the Q1 tasks own are recorded by chunk4-T24b, not here.

### chunk4-T23: Start a proposal from a report and close the loop for the reporter (needs Q1)

**Requirements:** AUD-03, PRO-02, PRO-03  
**Scenarios:** AUD-S5 (un-fixme'd), PRO-S7 stays green  
**Depends on:** chunk4-T21, chunk4-T18, chunk4-T22

On the console report detail, add Start a proposal for an obligation report:
- A dialog pre-filled with the current version's text in the original language, plus an effective date and a source label and link.
- It posts a new_obligation_version proposal with problemReportId.
- The report then shows In a proposal.

On Library updates, show 'Your problem report was fixed' (or rejected, with the note) for the caller's own reports resolved since the bookmark, read from GET /problem-reports?mine=true.

Un-fixme AUD-S5:
- The editor opens the seeded report and starts a proposal.
- editor2 approves it with step-up.
- The report shows Fixed.
- The reader sees the fixed row on Library updates.

**Owned paths:**

- `frontend/src/components/console/ProblemReportDetailScreen.tsx`
- `frontend/src/components/console/StartProposalDialog.tsx`
- `frontend/src/features/problem-reports/**`
- `frontend/src/features/proposals/**`
- `frontend/src/components/inventory/LibraryUpdatesScreen.tsx`
- `frontend/src/features/library-updates/**`
- `frontend/src/messages/en.json`
- `frontend/src/messages/sv.json`
- `frontend/tests/e2e/governance.journey.spec.ts`

**Done when:**

- AUD-S5 is un-fixme'd and green, with retries settling on 'in a proposal or fixed'.
- PRO-S7 is still green.
- features coverage is at least 98%.
- check:messages is green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "AUD-S5|PRO-S7"`

**Invariants:**

- The proposer editor never approves: a second editor does, with step-up.
- A source per changed field is required before sending.
- No reporter identity in the console.
- No string literals.

### chunk4-T24b: Close the Q1 tail of chunk 4

**Requirements:** AUD-03, ADM-02  
**Scenarios:** AUD-S5 reported built  
**Depends on:** chunk4-T16a, chunk4-T16b, chunk4-T18, chunk4-T21, chunk4-T22, chunk4-T23, chunk4-T24a

Once chunk4-T23 is on main:
- Record in INPUT_DELTAS §7:
  - GET and PATCH /problem-reports as built;
  - POST /proposals with problemReportId.
- Delete their pending lines.
- Set floors for governance/problem_reports_logic.py and re-measure the modules T16a to T23 changed.
- Set AUD-03 to built in governance/app.md.
- Update the IMPLEMENTATION_STATUS chunk 4 row, and the UI plan's problem-reports rows.

**Owned paths:**

- `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`
- `backend/scripts/coverage_gate.py`
- `backend/apps/governance/app.md`
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `docs/plans/UI_Implementation_Plan.md`

**Done when:**

- contract_drift passes with no stale or unexplained line.
- A full-suite coverage_gate passes with the new floors.
- requirements_coverage and compliance_check --all are green.
- The status files show AUD-03 built and no chunk 4 task outstanding.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit the regenerated files`
- `python backend/scripts/requirements_coverage.py && python backend/scripts/compliance_check.py --all`

**Invariants:**

- Floors never go lower than before.
- Status reflects git log.
- Only the Q1 operations and modules change here.
