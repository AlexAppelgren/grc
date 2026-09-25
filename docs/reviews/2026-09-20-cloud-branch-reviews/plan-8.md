# Review of origin/claude/plan-chunk-8-2ek5z2 (BLOCK)

The branch adds one file, docs/plans/briefs/CHUNK8_TASKS.md: 44 c8- packages in 13 waves for the register, organisation, out-of-office, reassignment, support access, tenant scales and the register feeds to Today and the roadmap, beside the 26 f03- tasks. Its rules mirror the parallel plan, every chunk 8 requirement and scenario has an owner, and the guards (four-eyes CHECKs, step-ups, RLS lists, append-only assessments, reads-never-write) are kept. It blocks because it was planned before Alex's 2026-09-19 answers: c8-support-access-mechanism builds RLS bypass policies keyed on a flag and reads a grant "under the schema owner's read", which is not the accepted design and touches the no-bypass invariant. Also stale against main: the tenant lists and register tone entries it plans to create already exist; DELETE /tenant/members lives in identity/api.py; several ownership and order gaps (team list registry entry, withdraw route, QueueCounts dependency on chunk 6, obligation page mount, f03-T51 vs member-removal, close-out before f03-T63/T65).

Questions the plan sends to Alex: Q1 support access - answered (OWNER_RECOMMENDATIONS item 2, recommendation accepted: platform requests, tenant approves with step-up, support session, 4 h default; PRD 0.4). Q2 D-41 lawyer's view - not answered (TODO_FOR_alex legal list). Q3 D-19 Contributor adds participants - not answered, default stands. Q4 D-46 SoA CSV in chunk 8 - not answered (TODO_FOR_alex). Q5 - a default, no question. The "private notes stays with Alex" line is answered by item 13 (no). Items 3 and 14 add no chunk 8 task; only the problem-report-window precedent reference is now wrong.

## Findings

### [HIGH] invariant: Support access mechanism is an RLS bypass shape and implies migrator reads in the API
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:1793
- Scenario: c8-support-access-mechanism adds 'two permissive FOR SELECT policies keyed on the flag' so a platform session with no tenant reads tenant rows, and loads the grant 'under the schema owner's read'. cw_app cannot read support_access rows without a tenant, so 'the schema owner's read' means cw_migrator credentials in the API process, which tests_database_role, the boot guard and HARDENING (unset MIGRATOR_DATABASE_URL before gunicorn) forbid. The accepted answer (OWNER_RECOMMENDATIONS item 2) needs no bypass policy: entering replaces the console session with a support session that activates the tenant under a read-only principal, and the console lists a person's own grants through one SELECT-only policy keyed on app.platform_user_id set only by identity/session_logic.py under an AST guard.
- Fix: Rewrite c8-support-access-mechanism to the accepted design: support session carrying the grant id and expiry (user_session gains the column, key mig:identity and idp), tenancy.activate() for the granted tenant, a principal holding only library.read, watch.read, roadmap.read, register.read, cases.read, reports.read, audit.read, 403 support_read_only on anything else, 401 support_access_ended after revoke or expiry, per-request support_access.read audit rows, the app.platform_user_id policy with its AST guard and a tests_rls entry, and a guard test that calls every GET route as the support principal expecting 2xx or 404. No policy on tenant tables keyed on a session flag, and never migrator credentials in the app.

### [MEDIUM] brief: Q1 is answered and the plan's Option A contradicts the accepted design
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:223
- Scenario: OWNER_RECOMMENDATIONS 'Alex's answers' item 2 accepts the recommendation: the platform admin requests from the console (support_access.grant, no step-up, purpose required, ticket optional, up to SUPPORT_ACCESS_MAX_HOURS default 4, request lapses after SUPPORT_ACCESS_REQUEST_TTL_HOURS), the tenant admin approves with security.manage plus step-up (window starts at approval), declines or revokes without step-up, CHECK approved_by <> platform_user_id, a guard trigger refuses delete and edits after insert, one confined request function emails security.manage holders, and TEN-S6 is rewritten (request, 404, approve, reads logged, a write answers 403, revoke gives 401 then 404). The plan instead has the tenant grant unprompted and name a platform user, SUPPORT_ACCESS_MAX_HOURS default 8, the flag set in tenants/support_access.py, no request or decline route, and TEN-S6 as written; it also holds wave 4 on a question that is closed.
- Fix: Revise c8-tenants-api-contract (console request route, tenant approve/decline/revoke, enter; ADM-S6's clause), c8-ten-support-grants (the two settings, the CHECK, the trigger, the confined request function, the mail), c8-card-people-access (pending requests, Revoke, the support banner, the console list), c8-ui-support-access, c8-e2e-seed-register (a platform admin login for TEN-S6) and the TEN-S6 rewording; remove the Q1 hold; add the PRD 0.4 permission-description change and the ADR to whichever package lands first; add about 45 minutes to the pair as item 2 says.

### [MEDIUM] brief: Cites chunk 4's problem-report window as the guard precedent, which will not be built
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:1796
- Scenario: c8-support-access-mechanism and the Q1 text say the flag is guarded 'exactly as chunk 4's problem-report window is guarded'. Item 3 of Alex's answers replaces that recommendation: no platform read window on problem reports is built (c4-report-window and its tail are replanned). The only window precedent on main is tenancy.identity_lookup() with IDENTITY_LOOKUP_TABLES in tests_rls.py.
- Fix: Point the AST-guard and tests_rls precedent at identity_lookup() (tenancy.py and tests_rls.py), and drop the problem-report reference from the mechanism task, the Q1 option text and c8-security-review.

### [MEDIUM] brief: Private notes still listed as an open question for Alex
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:94
- Scenario: The Cut list says 'Private notes: not built; the open question stays with Alex (D-22)' and c8-close-out copies 'Q1 to Q5' into TODO_FOR_alex.md. Item 13 answers it: no private notes, ADR 0028 moves to accepted and the D-22 question closes. Re-listing it re-opens a decided point.
- Fix: State that D-22's question is closed (item 13) and have c8-close-out copy only Q2 to Q4 and the defaults; Q1 is closed by item 2.

### [MEDIUM] conflict: c8-vocab-scales-reasons rebuilds tenant lists that already exist, and pulls in a chunk 9 package for nothing
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:527
- Scenario: backend/apps/taxonomy/registry.py on main, and at the merge base, already registers link_kind, compliance_status (kind compliance_category, ordinal), risk_rating (ordinal), case_sub_status (kind case_status from CaseStatusCategory in kinds.py), dismissal_reason and close_reason as tier-three lists. The task text 'adds' all of them and depends on c9-state-machine for the fixed case-status categories, which are already in kinds.py. Only gap_status and a risk-acceptance reason list are missing. It also defines gap_status kinds open, remediating, accepted, closed while frontend/src/features/shared/tone-by-kind.ts has GapKind 'risk_accepted'.
- Fix: Scope the task to the two new lists, the VOC-S8 to VOC-S10 tests over the existing lists and the seed rows; drop the c9-state-machine dependency and its precondition line; pick one kind name for the accepted state and change the other side in the same package.

### [MEDIUM] conflict: Register presentation and tone entries already exist on main
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:1379
- Scenario: c8-ui-applicability says nobody owned the register presentation and builds register-presentation.ts and the tone-by-kind register entries from scratch; c8-ui-gaps 'appends the gap entries'. Main has frontend/src/features/register/gap-presentation.ts with its test, and complianceTone, gapTone, severityTone and applicabilityTone in tone-by-kind.ts. Building a second module gives two tone maps, which the plan's own invariant forbids.
- Fix: Have c8-ui-applicability extend the existing module (or fold gap-presentation.ts into register-presentation.ts in one move) and reuse the existing tone entries; c8-ui-gaps adds no tone entries.

### [MEDIUM] conflict: The team vocabulary list has no owner, and c8-ten-teams edits a module another wave-5 package holds
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:1293
- Scenario: c8-ten-teams serves teams 'as a tier-three tenant list so GET /vocab/team feeds every picker', which needs a registry entry in taxonomy/registry.py (key taxreg) and a Vocabulary row model; the task owns neither, and c8-tenants-contract defines Team as a plain TenantModel in tenants. It also sets tenant_obligation.owner_team 'through the existing writers': that writer is register/status_logic.py, owned by c8-reg-entity-status in the same wave 5 under regstatus.
- Fix: Give the registry entry and the list model to c8-vocab-scales-reasons (or let c8-ten-teams own registry.py in a wave where nobody else holds taxreg) and say which model backs GET /vocab/team; move c8-ten-teams after c8-reg-entity-status, or have c8-reg-entity-status accept a team owner and leave c8-ten-teams the team CRUD only.

### [MEDIUM] conflict: The member removal route lives in identity/api.py, which no chunk 8 task owns
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:490
- Scenario: c8-tenants-api-contract stubs 'the reassignment body on the existing DELETE /tenant/members/{id}', but that route is deactivateMember in backend/apps/identity/api.py (key idapi), and the task owns only tenants files. c8-ten-reassignment owns identity/members_logic.py but not the route or its schema. The body has no owner, and idapi is also taken by c8-reg-applicability (wave 4) and f03-T51 (wave 7).
- Fix: Give identity/api.py and identity/schemas.py (the removal body only) to c8-tenants-api-contract with the idapi key and place it in the idapi chain before c8-reg-applicability, or move the body into c8-reg-applicability's idapi slot.

### [MEDIUM] conflict: c8-register-api-contract adds isolation factories on tables that do not exist yet
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:366
- Scenario: The contract package (wave 1, depends only on p03-consolidation) must add every route to TENANT_SCOPED_ROUTES 'with a factory in factories.py that builds the subject on a tenant-private record' and pass tests_tenant_isolation. The register tables arrive in c8-register-models (wave 3) and the tenant tables in c8-tenants-contract (wave 1, in parallel). A 501 stub needs no subject, but the factory does, so the package cannot be green as written.
- Fix: Make c8-register-api-contract depend on c8-register-models and c8-tenants-contract, or leave the factories and the isolation listing to c8-register-models and have the contract package list its routes as 501 stubs only until then.

### [MEDIUM] conflict: Withdraw has no route in the contract, and the GET /me count depends on chunk 6 work not in depends-on
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:883
- Scenario: c8-reg-applicability builds 'Withdraw: the requester may withdraw their own pending request', but c8-register-api-contract declares only list, create, approve and reject; rule 3 forbids a logic package touching api.py. The same task adds applicability to QueueCounts on GET /me, but counts and QueueCounts do not exist on main (identity/me_logic.py and schemas.py have neither); they come from chunk 6's f03-T48, which neither the task nor the preconditions name.
- Fix: Add POST /applicability-requests/{id}/withdraw to c8-register-api-contract under applicability.request; add f03-T48 (chunk 6) to c8-reg-applicability's depends-on and to the preconditions.

### [MEDIUM] conflict: Nobody owns the obligation page component that mounts the new panels
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:1388
- Scenario: c8-ui-applicability, c8-ui-where-we-stand, c8-ui-history-interpretation, c8-ui-internal-links, c8-ui-gaps and f03-T63 each own a new panel file under components/inventory or register, but the obligation page screen (key obpage, last edited by chunk 3's c3-fe-obligation-versions) must import and place each panel. No c8 task owns it or takes obpage, so the first panel package would edit an unowned file.
- Fix: Add the obligation page component to the regfe chain's owned paths with the obpage key, one package at a time, or add one small mount package after c8-ui-applicability.

### [MEDIUM] conflict: Wave 7 runs f03-T51 beside c8-ui-member-removal on the same directories
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:153
- Scenario: FEATURES_0_3_TASKS gives f03-T51 frontend/src/features/tenant-admin/ and frontend/src/components/admin/ directory-wide; the wave table lets it run in wave 7 with c8-ui-member-removal, which owns features/tenant-admin/members/removal.ts and components/admin/MemberDetailScreen.tsx. The wave header promises disjoint paths. The same table also lists f03-T52 and f03-T66 (both ten, both tenants/api.py) together in wave 8.
- Fix: Order f03-T51 after c8-ui-member-removal (or narrow f03-T51's frontend paths to the organisation and members-teams files), and either serialize f03-T52 before f03-T66 explicitly or change the table's claim to 'dispatchable, keys still serialize'.

### [MEDIUM] conflict: Close-out and the security review run before work they must cover is on main
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:159
- Scenario: c8-close-out (wave 13) depends on f03-T65 and must prove no chunk 8 journey is fixme, yet the table runs f03-T63 and f03-T65 beside it; COL-S6 and COL-S7 journeys (f03-T63) would still be fixme. c8-security-review (wave 11) starts beside f03-T56 to T59 and T71 and before f03-T72, so the My work service (permission-filtered rows and counts) and the SoA filter escape the chunk review, and c8-review-fixes (wave 12) may edit register/api.py while f03-T72 holds regapi.
- Fix: Move f03-T63 and f03-T65 before c8-close-out (add f03-T63 to its depends-on); start c8-security-review after f03-T59 and f03-T72, or add a second review pass over them in c8-review-fixes.

### [MEDIUM] brief: Gap writes gated by register.edit although PRD section 6 has gaps.edit
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:358
- Scenario: The contract gates GET/POST /obligations/{id}/gaps, PATCH /gaps/{id} and accept-risk on register.edit. PRD section 6 and permissions.py define gaps.edit (GAPS_EDIT) with the same roles today; tests_route_permissions and the PRD matrix would then carry a permission no route uses, and a tenant role composed with gaps.edit alone could not write a gap.
- Fix: Gate the gap write routes on gaps.edit in c8-register-api-contract, or state the default (register.edit covers gaps) in the commit body and the register app.md and ask for the PRD row to drop gaps.edit.

### [MEDIUM] test: REG-S10 is un-skipped one wave before the roadmap branch it asserts
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:1763
- Scenario: REG-S10 reads 'When the roadmap for Q4 2026 is read, the duty appears with Our deadline'. c8-reg-duty-occurrences (wave 7) un-skips it in full, but the roadmap branch for duties is c8-home-register-feeds (wave 8). REG-S5 has an explicit 'green up to the roadmap line' note; REG-S10 does not, so the test cannot be green without either weakening it or building the branch twice.
- Fix: Say REG-S10 is green up to its roadmap line in c8-reg-duty-occurrences and have c8-home-register-feeds extend it, mirroring REG-S5; or move the un-skip to c8-home-register-feeds.

### [LOW] simplicity: Several packages sit at or beyond the cap for one sub-agent
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:681
- Scenario: c8-register-models (seven tables, composite keys, append-only trigger, AST guard, RLS and four-eyes tests), c8-recurring-duty-library (library model, proposal kind through apply.py, a runtime dependency, a setting, prepush --all), c8-support-access-mechanism and c8-ten-support-grants (60 and 45 minutes before the 45 minutes item 2 adds and the support session), c8-tenants-contract (six models), c8-e2e-seed-register, c8-ui-organisation, c8-ui-where-we-stand, c8-ui-gaps and c8-close-out (60 each) are all far past thirty minutes and at the plan's own 60-minute limit.
- Fix: Split: register-models into entry, scope and request versus gap, assessment, interpretation and link; recurring-duty into model plus fence versus proposal kind plus dependency; the support pair into grant workflow, support session and console list; the three 60-minute UI packages each into panel and journey.

### [LOW] simplicity: One design card package gates three unrelated screens
- Where: `docs/plans/briefs/CHUNK8_TASKS.md`:744
- Scenario: c8-ui-out-of-office (TEN-04) and c8-ui-member-removal (TEN-05) depend on c8-card-people-access, which the plan held on Q1 (support access). Had Q1 stayed open, two screens with no support-access content would have waited with it. Q1 is now answered, but the coupling remains.
- Fix: Split the out-of-office and removal-dialog cards from the support-access cards, so only the support screens depend on the support card.

## Conflicts with main

No file conflict: the branch adds only docs/plans/briefs/CHUNK8_TASKS.md and main's only change on the compared paths is OWNER_RECOMMENDATIONS.md gaining "Alex's answers". Content on main that supersedes or duplicates the plan: (1) item 2 answers Q1 with a design the four support-access tasks and TEN-S6 do not follow; (2) item 3 removes the problem-report window the mechanism task cites as its precedent; (3) item 13 closes the private-notes question the plan keeps open; (4) taxonomy/registry.py and kinds.py already hold the tenant lists and CaseStatusCategory that c8-vocab-scales-reasons plans to add; (5) frontend/src/features/register/gap-presentation.ts and the register tone entries in tone-by-kind.ts already exist; (6) DELETE /tenant/members/{id} is identity/api.py's deactivateMember; (7) tenants/models.py SupportAccess already carries reason, ticket_ref, access_level, approved_by, started_at, ended_at, so 'purpose' and 'granted_by' duplicate reason and approved_by. Resolve by revising those task texts before dispatch; nothing needs a rebase.

## Checked clean

All 44 c8- ids of PARALLEL_PLAN 3.3 are present with the same SR set; plan-wide rules mirror parallel-plan rules 1 to 12 (contracts first, 501 stubs behind real gates, no screen calls a stub, generated files not committed, append ledgers, cloud stop on invariant questions); descope order matches Build_Plan and D-26; the cut list matches D-18, D-21, D-41, D-46 and ruling 20, and the VOC-03 chunk-10 correction is right; step-ups are kept on applicability approval, risk-acceptance approval, member removal and the support grant, and rejections without step-up match playbook 4.2; four-eyes CHECKs on applicability_request and gap join FOUR_EYES_TABLES in the same commit as the tables; compliance_assessment is append-only with a cw_app test; reads never write scope rows (D-42); the not_assessed-or-applies rule keeps a regression test; no UNGATED_BY_DESIGN addition; E2E rules (passkey through the UI, api-guard, seed not mock, anchored clocks) are propagated; the coverage table names an owner for every chunk 8 requirement and scenario, with REG-S9 and TEN-S7 named rather than dropped; TEN-S4's rewording keeps both halves; mig:tenants, mig:register, regfe, regapi and orgscreen chains are internally consistent; the recurring-duty library half stays behind the proposal door with a source per field and waits for r1-readiness as rule 11 requires; brief style matches CHUNK3/4/6_TASKS.md.