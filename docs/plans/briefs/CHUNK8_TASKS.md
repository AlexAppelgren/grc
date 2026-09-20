# Chunk 8: tasks

Written 2026-09-19 by the planning workflow (read, plan, parallelism and coverage critiques, revise). Each task runs in its own worktree or cloud session (`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`, and for a cloud session on `origin/main`.

The task ids are the `c8-` package ids of `docs/plans/PARALLEL_PLAN.md` section 3.3; all 44 of them are here. Seven of them were split on 2026-09-20 under rule 11, which gives 51 ids: a split keeps the parent's id for its first half and derives the second (`c8-register-models-core` and `c8-register-models-gaps-history`, `c8-recurring-duty-model` and `c8-recurring-duty-proposal`, `c8-support-access-console-list` beside `c8-ten-support-grants` and `c8-support-access-mechanism`, `c8-card-support-access` beside `c8-card-people-access`, and a `-journey` package after each of `c8-ui-organisation`, `c8-ui-where-we-stand` and `c8-ui-gaps`). The parallel plan's rows for the parents carry both halves; nothing else about their dependencies changes. `c8-reference-members` is not one of them: it is a name the chunk 8 map used, and plan ruling 11 resolves it to `c9-case-contract`. The chunk 8 tasks that carry the PRD 0.3 requirements keep their `f03-` ids and stay specified in `docs/plans/briefs/FEATURES_0_3_TASKS.md`; this file does not restate them, but it places them in the waves and names the files they share with a `c8-` package, because that is where the collisions are.

## Revised 2026-09-20

`docs/reviews/2026-09-20-cloud-branch-reviews/plan-8.md` blocked the first version, and
Alex answered the open questions on 2026-09-19 (`docs/plans/briefs/OWNER_RECOMMENDATIONS.md`,
"Alex's answers"). What changed, and which finding each change closes:

| Change | Closes |
|---|---|
| `c8-support-access-mechanism` is rewritten: no policy on a tenant table keyed on a session flag and no read under the schema owner. A support session carries the grant id, the request activates that one tenant through `tenancy.activate()` exactly as a member's session does, a read-only guard refuses every write, and each request writes a `support_access.read` audit row in that tenant | HIGH invariant |
| The whole support-access chain follows the accepted design of item 2: the platform admin requests from the console, a tenant admin approves with a step-up, declines or revokes, `SUPPORT_ACCESS_MAX_HOURS` defaults to 4, a request lapses after `SUPPORT_ACCESS_REQUEST_TTL_HOURS`, and TEN-S6 is rewritten. Q1's hold is gone; the pair grows by about 45 minutes | MEDIUM brief (Q1) |
| The AST-guard and `tests_rls` precedent is `tenancy.identity_lookup()` with `IDENTITY_LOOKUP_TABLES`, not chunk 4's problem-report window, which item 3 removed | MEDIUM brief (precedent) |
| Private notes: D-22's question is closed by item 13, not re-opened. `c8-close-out` copies Q2 to Q4 and the defaults | MEDIUM brief (private notes) |
| `c8-vocab-scales-reasons` adds only the two lists main does not have, `gap_status` and `risk_acceptance_reason`, plus the `team` list and its registry entry; it tests VOC-S8 to VOC-S10 over the lists already in `taxonomy/registry.py`, drops the `c9-state-machine` dependency, and names the accepted gap kind `risk_accepted` to match `tone-by-kind.ts` | MEDIUM conflict (vocab) |
| `c8-ui-applicability` extends the register presentation module and the tone entries that exist on main; the only tone append chunk 8 makes is `riskTone`. `c8-ui-gaps` adds no tone entry and no second module | MEDIUM conflict (presentation) |
| The `team` list model and its registry entry belong to `c8-vocab-scales-reasons`, which also says `GET /vocab/team` is served from it; `c8-tenants-contract` drops `Team`; each logic package accepts a team owner in its own module; and `c8-ten-teams` keeps `TeamMember` and the ownership rules and starts after `c8-reg-entity-status` | MEDIUM conflict (teams) |
| `c8-tenants-api-contract` owns `identity/api.py` and `identity/schemas.py` for the removal body, takes `idapi`, and heads the `idapi` chain | MEDIUM conflict (member removal) |
| `c8-register-api-contract` registers routes and permission lists only; the `TENANT_SCOPED_ROUTES` entries and their factories land with the tables, in `c8-register-models-core` and `c8-register-models-gaps-history` | MEDIUM conflict (factories) |
| `POST /applicability-requests/{id}/withdraw` is in the contract, and `c8-reg-applicability` depends on f03-T48, which creates `QueueCounts` | MEDIUM conflict (withdraw, counts) |
| The obligation page screen joins the `regfe` chain's owned paths under the `obpage` key, one package at a time | MEDIUM conflict (obligation page) |
| f03-T51 runs after `c8-ui-member-removal`; the wave table now says what it means, and the keys that serialize inside a wave are named | MEDIUM conflict (wave 7) |
| `c8-security-review` starts after f03-T59 and f03-T72; `c8-close-out` depends on f03-T63 and runs after it and f03-T65 | MEDIUM conflict (order) |
| The gap write routes are gated on `gaps.edit` | MEDIUM brief (gaps.edit) |
| REG-S10 is green up to its roadmap line in `c8-reg-duty-occurrences`, and `c8-home-register-feeds` extends it, mirroring REG-S5 | MEDIUM test (REG-S10) |
| Seven packages are split, as above, and rule 11 names the green stopping point of the three that stay whole at the cap | LOW simplicity (cap) |
| `c8-card-support-access` holds the three support-access cards, so out of office and member removal wait for nothing | LOW simplicity (design card) |
| The `tenadminmsg` key serializes the four packages that write `frontend/src/messages/tenant-admin/{en,sv}.json` whole — `c8-ui-organisation`, `c8-ui-teams`, `c8-ui-member-removal`, `c8-ui-support-access` — and change 11 no longer claims wave 7 holds only one of them | MEDIUM review 2 (wave 7 catalogs) |
| The support-access read-only guard is an allow-list of route templates, `SUPPORT_READ_ROUTES` in `apps/shared/routes.py`, not a method rule, and the sweep expects 403 `support_read_only` for every GET that is not on it, proved by a planted new GET route | MEDIUM review 2 (read-only guard) |
| The package count matches the wave table: 51 `c8-` packages in 15 waves | LOW review 2 (count) |

## Scope, rules and defaults

Chunk 8 plan: the register. `Build_Plan.md` gives it REG-01, REG-02, REG-03, REG-05, REG-08, HOM-05, COL-04, TEN-02, TEN-03, TEN-05 and TEN-06, then the cuttable REG-04, REG-07, TEN-04 and VOC-04 to VOC-06, in that order (D-26: the order, not the priority, is what the descope rule respects). 51 `c8-` packages in 15 waves, beside the 26 `f03-` tasks of chunk 8.

### What it delivers

- **REG-01 Applicability.** A request with a reason, waiting for approval, decided by a second person with a passkey step-up. Per legal entity where the obligation spans several (f03-T67), per unit of a standard (f03-T68), and many pending requests decided in one call with four eyes on every row (f03-T70).
- **REG-02 Compliance status.** Status, status note, risk, first-line owner, compliance contact, process, system, evidence location and next review, on the register entry and again per legal entity, with `version` and `If-Match`. "Applies" and "we comply" stay separate facts: a status survives a "does not apply" and is readable again afterwards.
- **REG-03 Gaps.** Owner, severity, target date, remediation and status, with risk acceptance behind four eyes, a step-up and a reason key.
- **REG-05 Linked internal items.** Policies, procedures, controls, processes and systems with their external references, readable by an outside GRC system.
- **REG-08 Statement of Applicability** (f03-T67 to f03-T72, f03-T75): units per following legal entity in the tenant's own words, pasted with a dry run, decided in one call, and the register filtered by standard and entity.
- **TEN-02 and TEN-03 Organisation.** Legal entities with their licences, products scoped the way obligations are, org units, teams and team membership; departments with a head and certificates come with f03-T51 and f03-T66.
- **TEN-04 Out of office**, **TEN-05 removal with bulk reassignment**, **TEN-06 support access**: a platform admin requests read-only access to one bank with a purpose, a bank admin approves it with a passkey and can revoke it at once, and every read under the grant lands in the bank's own audit log (`OWNER_RECOMMENDATIONS.md` item 2, accepted 2026-09-19).
- **HOM-05 My work** and **COL-04 participants** (f03-T50 to f03-T65), on the rows this chunk creates.
- **VOC-04 to VOC-06**: tenant statuses inside fixed categories, tenant scales mapped to fixed ordinals, and the reason lists dismissal, closure and risk acceptance use.
- **Today and the roadmap** gain the register: "Where we stand", next reviews, gap target dates and duty occurrences as "Our deadline".
- **The inventory** gains the register overlay: applicability, the compliance pill, the owner and a pending-approval marker.

### Preconditions

- `p03-consolidation` is on `main`: `PRD.md` 0.3, D-18 to D-47, the `app.md` rows and the skipped and fixme stubs this chunk un-skips.
- `c4-console-tenants-api` is on `main` before `c8-tenants-api-contract`, and `c4-console-shell` before `c8-ui-support-access`.
- `x-frontend-split` is on `main` before any frontend task, so each feature owns its own message catalogs.
- `r1-readiness` is on `main` before `c8-recurring-duty-proposal` (it changes a dependency and the proposal door) and before `c8-support-access-mechanism` (it changes `authentication.py` and `middleware.py`), under plan rule 11.
- f03-T48 (chunk 6) is on `main` before `c8-reg-applicability`: it creates `QueueCounts` on `GET /me`, to which that package adds `applicability`. Neither the counts nor the schema exist on `main` today.
- `c9-state-machine` is **not** a precondition. `CaseStatusCategory` and the `case_sub_status` list are already in `taxonomy/models.py` and `registry.py` on `main`, so VOC-S8 can be tested over them the day the chunk starts.
- **Q1 is answered** (`OWNER_RECOMMENDATIONS.md` item 2, accepted 2026-09-19), so nothing in this chunk waits on it. The four support-access packages build the accepted design and `c8-close-out` closes TEN-06 as built.

### Plan-wide rules

1. **Slots.** Every backend and E2E gate runs inside the task's worktree slot (`set -a; . ./.env.worktree; set +a`). A cloud session runs `bash scripts/cloud-setup.sh` first, with `--e2e` when its gates include a journey.
2. **Generated files.** No task commits `openapi.json`, `frontend/src/types/api.generated.ts` or `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them locally to run `contract_drift.py` and the typecheck, then reverts them. The main agent regenerates and commits them with the merge.
3. **Contracts land first, logic lands in its own module.** `c8-register-api-contract` and `c8-tenants-api-contract` each write their app's `api.py` and `schemas.py` once. Every operation calls a named function in the module of the logic package that will build it, and that function answers 501 `not_built` behind its real permission gate and its step-up. A logic package owns only its own module and its tests, never the app's `api.py`:
   - register: `status_logic.py`, `applicability.py`, `gaps.py`, `history.py`, `links.py`, `duties.py`, `overlay.py`. `register/logic.py` holds only `ensure_register_entry()` and the shared loaders, and belongs to `c8-register-models-core` and then to the `reglogic` f03 tasks.
   - tenants: `organisation.py`, `out_of_office.py`, `support_access.py`, `teams.py`, `reassignment.py`. `tenants/logic.py` is the chunk 1 profile logic and is not touched.
   A logic package that finds the contract wrong stops and reports; the contract package fixes it.
4. **No screen calls a stub.** Each `c8-ui-*` task depends on every backend package whose routes it calls. `c8-close-out` proves no chunk 8 route answers 501.
5. **Serialization keys** are the plan's (section 3.4), plus one this file adds: `cards:<file>` for a design card several packages extend. A chain is an order, not a wave: a package starts when everything in its depends-on is on `main` and the key ahead of it is free. The chains that matter here:
   - `regfe` (`frontend/src/features/register/` and its catalogs) **and `obpage`** (the obligation page screen component, last edited by chunk 3's `c3-fe-obligation-versions`, which every panel package must mount its panel on): `c8-ui-applicability` → `c8-ui-where-we-stand` → `c8-ui-where-we-stand-journey` → `c8-ui-history-interpretation` → `c8-ui-internal-links` → `c8-ui-gaps` → `c8-ui-gaps-journey` → `c8-ui-risk-acceptance` → f03-T71 → f03-T72 → f03-T63. Eleven packages; it is the chunk's longest chain and it sets the close. Each package holds `obpage` only long enough to mount its own panel, so nobody else edits the screen while it does.
   - `regstatus` (`register/status_logic.py`): `c8-reg-status` → `c8-reg-entity-status`. `c8-ten-teams` does **not** join it: each logic package accepts a team owner in its own module, and `c8-ten-teams` only depends on `c8-reg-status` having done so.
   - `mig:register`: `c8-register-models-core` → `c8-register-models-gaps-history` → f03-T67 → f03-T68 → `c8-reg-duty-occurrences`.
   - `mig:tenants` (plan ruling 15, with `c8-ten-out-of-office` added because its model lives in the same file): `c8-tenants-contract` → `c8-ten-out-of-office` → `c8-ten-support-grants` → `c8-ten-teams` (`TeamMember` and its composite key) → f03-T51 → f03-T66.
   - `mig:taxonomy` and `taxreg`: `c8-vocab-scales-reasons` → `c8-vocab-register-usage`.
   - `mig:library`, `prop`, `apply` and `deps`: `c8-recurring-duty-model` → `c8-recurring-duty-proposal`.
   - `regapi`: `c8-register-api-contract` → f03-T69 → f03-T70 → f03-T72.
   - `ten`: `c8-tenants-api-contract` → f03-T51 → f03-T52 → f03-T66. f03-T52 and f03-T66 both hold `ten`, so f03-T52 runs first even though the wave table lists them together.
   - `idp` (`identity/session_logic.py`): `c8-support-access-mechanism` (the support session and the `app.platform_user_id` setting) → `c8-support-access-console-list` (which should need no change there at all).
   - `orgscreen`: `c8-ui-organisation` → `c8-ui-organisation-journey` → `c8-ui-teams` → f03-T51.
   - `members`: `c8-ten-reassignment` → `c8-ui-member-removal` → f03-T51 → f03-T64. f03-T51 owns `frontend/src/features/tenant-admin/` and `frontend/src/components/admin/` directory-wide, so it runs after `c8-ui-member-removal`, never beside it.
   - `tenadminmsg` (`frontend/src/messages/tenant-admin/en.json` and `sv.json`): `c8-ui-organisation` → `c8-ui-teams` → `c8-ui-member-removal` → `c8-ui-support-access`. A catalog is one object each package rewrites whole, not an append ledger, so the four writers are ordered even when two of them share a wave, as `c8-ui-teams` and `c8-ui-member-removal` do in wave 7.
   - `cards:tenant-obligation.html`: `c8-card-obligation-register` → f03-T60. `cards:admin-organisation.html`: `c8-card-organisation` → f03-T60. `cards:admin-members.html`: f03-T60 → `c8-card-people-access`. `c8-card-support-access` holds no `cards:` key: both its files are new and nobody else touches them. It deliberately draws nothing on `tenant-obligation.html`, so it never queues behind `c8-card-obligation-register` and f03-T60.
   - `idapi` (identity `api.py`, `schemas.py`, `me_logic.py`): `c8-tenants-api-contract` (the removal body on `DELETE /tenant/members/{id}`) → f03-T48 (chunk 6, `QueueCounts`) → `c8-reg-applicability` (the `applicability` count) → f03-T51.
6. **Append ledgers** (plan rule 5) are not keys. In this chunk they are `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`, `docs/plans/briefs/HARDENING.md`, the UI plan's ledger rows and status cells, `backend/config/settings.py` settings banners, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`, `backend/config/api.py` router mounts, `apps/shared/kinds.py`, `factories.py`, `routes.py`, the route lists in `permissions.py`, the guarded-table lists in `tests_rls.py`, `tests_four_eyes.py` and `tests_seed_integrity.py`, `apps/shared/e2e_seed.py`, `e2e_logins.py` and `e2e_passkeys.py`, `frontend/tests/e2e/support/passkeys.ts`, `frontend/src/shared/navigation/registry.ts`, `frontend/src/features/shared/tone-by-kind.ts`, each `app.md` status cell and skip line, and each journey spec, where a package edits only its own scenarios' blocks.
7. **Security review before merge** for every package marked SR in the plan: `c8-tenants-contract`, `c8-register-api-contract`, `c8-tenants-api-contract`, `c8-ten-support-grants`, `c8-support-access-mechanism`, `c8-support-access-console-list`, `c8-vocab-scales-reasons`, `c8-register-models-core`, `c8-register-models-gaps-history`, `c8-reg-applicability`, `c8-ten-reassignment`, `c8-reg-risk-acceptance`, `c8-recurring-duty-model`, `c8-recurring-duty-proposal`, `c8-reg-duty-occurrences` and `c8-review-fixes`. A split inherits the parent's SR mark on both halves. The guard suites run with it: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`. `c8-security-review` is the chunk-wide sweep and `c8-review-fixes` closes it.
8. **Cloud sessions stop on an invariant question** (plan rule 12). `c8-support-access-mechanism` carries that instruction explicitly: it changes `tenancy.py` and the rule that platform staff have no bypass.
9. **Merge at once** (WORKTREES step 5). A task is squash-merged as soon as it passes review, never held for the rest of the chunk.
10. **Scenario ownership.** Exactly one task un-skips each integration test and exactly one un-fixmes each journey; the table under "Coverage" names them. A task that only extends a scenario someone else owns says so and keeps it green.
11. **The 60-minute limit.** A package past 60 minutes stops at a green point and the rest becomes a new package. Seven packages were split up front on 2026-09-20 rather than in flight; the ids are in the opening paragraph. Three stay whole at the cap, each with its stopping point named here, so a sub-agent that runs out of room knows where to stop:
   - `c8-tenants-contract` (five models): stop once `OrgUnit`, `Licence` and the two product tables are green with their RLS and composite-key tests; `InternalItem` becomes `c8-tenants-contract-b` on `mig:tenants`.
   - `c8-e2e-seed-register`: stop once tenant A's organisation, the register entries and the logins are seeded and idempotent; the gaps, links, interpretation and tenant B's small register become `c8-e2e-seed-register-b`.
   - `c8-close-out`: stop once the status cells, the ledgers and `tests_no_stubs.py` are green; the floor ratchet and the full-suite run become `c8-close-out-b`.
12. **Test-first, everywhere.** The failing test comes first. Nothing is simplified away: not a guard, a test, an audit row, a permission check, a step-up or a validation at a trust boundary.

### Descope: what can still be cut, and when

The descope rule cuts from the bottom of the chunk's requirement list: VOC-04 to VOC-06 first, then TEN-04, REG-07, REG-04.

**VOC-04 to VOC-06 can only be cut before wave 2.** `c8-vocab-scales-reasons` runs in wave 2 because `c8-register-models-core` (wave 3) stores compliance status, risk and gap status as tenant vocabulary rows. Cutting the scales after wave 3 would mean migrating every status column a second time and rewriting the pill presentation. If they are to be cut, they are cut before `c8-vocab-scales-reasons` starts, and `c8-register-models-core` then stores the fixed kinds of `docs/inputs/schema.sql` with an INPUT_DELTAS row saying the tier-three lists are deferred.

The cut is smaller than it was, because `compliance_status`, `risk_rating`, `link_kind`, `case_sub_status`, `dismissal_reason` and `close_reason` are already tenant lists in `taxonomy/registry.py` on `main`. What a cut of VOC-04 to VOC-06 still reaches is `gap_status`, the risk-acceptance reason list and the VOC-S8 to VOC-S10 tests. The `team` list is **not** part of VOC-04 to VOC-06 and is never cut: TEN-03 needs it, and `c8-vocab-scales-reasons` carries it for the registry key, not for the requirement.

TEN-04 (`c8-ten-out-of-office`, `c8-ui-out-of-office`), REG-07 (`c8-recurring-duty-model`, `c8-recurring-duty-proposal`, `c8-reg-duty-occurrences`) and REG-04 (`c8-reg-history-interpretation`, `c8-ui-history-interpretation`) can be cut at any point; each is a leaf except that `c8-home-register-feeds` reads duty occurrences and `f03-T56` reads duties and interpretations, so cutting REG-07 or REG-04 also narrows My work's sources, which f03-T56's tests must then say.

### Defaults taken (each stated in its commit body, collected by `c8-close-out`)

- **Register and tenants logic is one module per feature**, as rule 3 sets out. The reason is parallelism: four register logic packages share a wave.
- **Statuses and scales are tenant vocabulary rows** (INPUT_DELTAS §1 tier three): `compliance_status`, `risk_rating`, `gap_status` and `link_kind` are lists with an immutable key, a fixed kind and a fixed ordinal. The column holds the row, and the pill tone comes from the kind, never from the label. All but `gap_status` are already registered on `main`; chunk 8 adds `gap_status` and the risk-acceptance reason list and then uses them.
- **The accepted gap kind is `risk_accepted`, not `accepted`.** `frontend/src/features/shared/tone-by-kind.ts` on `main` already has `GapKind = 'open' | 'remediating' | 'risk_accepted' | 'closed'`, so the backend takes the frontend's name and no tone map changes. Picking the other name would have meant editing a shipped module for nothing.
- **`team` is a tier-three tenant list in `taxonomy`** (`Team(TenantListVocabulary)` with the extra field `email`, and `TeamLabel`), which is what MY_WORK_AND_MARKETS §3.2 means by "`GET /vocab/team` feeds every picker" and what `c8-close-out` records in INPUT_DELTAS §1. Create, rename and retire are then the tenant-list routes under `vocab.manage`, so the tenants API needs no team CRUD of its own. `TeamMember` stays in `tenants` with a composite key to the taxonomy `team` table, and f03-T51 adds the team's department to that row, so it takes `mig:taxonomy` beside `mig:tenants`.
- **Gap writes are gated on `gaps.edit`**, not on `register.edit`. PRD section 6 and `permissions.py` both define `GAPS_EDIT` with the same roles today, so nothing about who can do what changes; the alternative would leave a permission the matrix names and no route uses.
- **The `not_assessed OR applies` rule moves from a database CHECK to `register/status_logic.py`** with a regression test, because a CHECK cannot read the kind of a row in another table. The four-eyes CHECK constraints, the audit trigger and the RLS policies are unchanged.
- **`ensure_register_entry()` is the only writer that creates a register entry**, and it writes its own `register.entry_created` audit event in the same transaction (MY_WORK_AND_MARKETS §3.2).
- **An interpretation is a version without an approval step** (plan 7.2). `interpretation.approved_by` stays nullable and unused in R2.
- **A delegate needs the approve permission themself; delegation only routes work** (plan 7.2).
- **An internal item is created or picked from the link dialog**; there is no separate internal-items admin screen in R2. The item carries kind, name, reference, url, owner, org unit, external system and reference, and last and next review.
- **Duty occurrences are generated one at a time**: the next occurrence is written when the current one is completed, and the roadmap reads the next due date. No horizon of rows is generated.
- **RRULE expansion uses `python-dateutil`**, added by `c8-recurring-duty-proposal`, which holds the `deps` key and therefore waits for `r1-readiness`. A pin that fails to install is replaced by the nearest working version and the change is reported with its reason.
- **`REGISTER_BULK_MAX` defaults to 100**, the page maximum (D-44). `RISK_ACCEPTANCE_REASON_LIST` and the other list keys are settings with env overrides, as the playbook requires.
- **Support access follows `OWNER_RECOMMENDATIONS.md` item 2 exactly** (accepted 2026-09-19): the platform admin requests, the bank admin approves with a step-up, the window starts at approval, `SUPPORT_ACCESS_MAX_HOURS` defaults to 4 and `SUPPORT_ACCESS_REQUEST_TTL_HOURS` lapses a request that nobody decides. A grant is read-only: `access_level` is written as `read`, and the write level is refused with 422 `unknown_key`, which leaves the chunk 1 one-shot recovery row as the only write-level row there has ever been.
- **A support session reaches a tenant the ordinary way.** It activates that one tenant through `tenancy.activate()`, so every row-level-security policy applies to it exactly as it applies to a member. No tenant table gains a policy keyed on a session flag, no role gains `BYPASSRLS`, and the API process never holds migrator credentials. The only new policy in the chunk is one SELECT-only policy on `support_access` keyed on `app.platform_user_id`, so a platform person can check and list their own grants before any tenant is active; the setting behind it is written in one module under an AST guard, the same shape as `tenancy.identity_lookup()` on `main`.
- **Each panel package mounts its own panel.** The obligation page screen is in the `regfe` chain's owned paths under the `obpage` key, one package at a time; no package leaves its panel unmounted for someone else to wire up.
- **Removing a standard or any term from the regulatory scope hides the rows and deletes none** (D-42). A hidden register entry keeps its status, its gaps and its history.
- **My work ignores the regulatory scope** (D-24). The register screens do not; FP-03 names the inventory.
- **Products are scoped with the same taxonomy terms obligations use** (TEN-S2) through `tenant_product_term`, and a product decides no applicability on its own in R2: `tenant_obligation_scope.product_id` is built and nullable, and only the org-unit branch is served.

### Cut, with reasons

- **REG-06 attestations and waivers**: R3, chunk 13. REG-S9 stays skipped and `c8-close-out` names it.
- **`requirement_status`**: replaced by `soa_unit` (D-41). It is never created.
- **Unit-level evidence, and copying units forward to a new edition or another entity**: deferred (D-41).
- **`team_member.is_lead`**: not built. Departments have heads on the org unit and team notices go to a team's active members (D-21, D-34).
- **Participant roles (contributor, informed)**: not built (D-18).
- **Private notes**: not built, and the question is closed, not open. `OWNER_RECOMMENDATIONS.md` item 13 was accepted on 2026-09-19: notes on My work are the shared comments, ADR 0028 moves to accepted and D-22's open question closes in `DECISIONS.md` and `TODO_FOR_alex.md`. Chunk 8 builds nothing for it and `c8-close-out` does not re-list it.
- **Custom fields (`custom_field_def`, the `custom` jsonb)**: R3.
- **Bulk tagging (VOC-08) and create-or-suggest (VOC-03)**: chunk 10. The UI plan's "built with chunk 8" note on the suggestion routes is corrected by `c8-close-out`, because `Build_Plan.md` puts VOC-03 in chunk 10 and the build plan is the plan.
- **The SoA "as of" and its dated export**: R3's filtered inventory export (REP-02, D-46). Open question Q4 below.
- **A separate Markets screen**: D-27; markets sit on the Regulatory scope screen and are f03 work.
- **A roll-up across units**: the conformance row per entity keeps its own assessed status (D-41).
- **`GET /reports/*`**: chunk 12. Today reads its own home endpoint (plan ruling 20).

### Wave logic

- The two contract packages and the organisation card start in wave 1, because everything else waits for them and they are cloud-eligible from `p03`.
- `c8-vocab-scales-reasons` is in wave 2, before `c8-register-models-core` in wave 3, for the reason under "Descope" above.
- Wave 4 is the widest: ten packages, each owning one logic module, one seed or one design card.
- The `regfe` chain from wave 5 to wave 13 is the spine. Each frontend package edits one feature directory, one catalog namespace, one journey spec block and, while it holds `obpage`, the obligation page screen.
- `c8-recurring-duty-proposal` and `c8-support-access-mechanism` wait for `r1-readiness` and therefore land in waves 6 and 7 whatever else is ready.
- `c8-security-review` starts once every SR backend package, every SR f03 task of chunk 8, f03-T59 and f03-T72 are on `main`, which puts it in wave 13; `c8-close-out` runs last and alone, after f03-T63 and f03-T65.

### Changes from the critiques

**From the parallelism critique**

1. `c8-card-obligation-register`, `c8-card-gaps` and f03-T60 all edit `design/screens/tenant-obligation.html`, and the plan starts all three in the same wave. `c8-card-gaps` now owns only the new `design/screens/tenant-gaps.html`, the obligation page's register panels belong to `c8-card-obligation-register`, and f03-T60 adds the participants panel after it. The `cards:<file>` key is added for this.
2. `c8-card-organisation` and f03-T60 both edit `admin-organisation.html`, and `c8-card-people-access` and f03-T60 both edit `admin-members.html`. Ordered `c8-card-organisation` (wave 1) → f03-T60 (wave 3) → `c8-card-people-access` (wave 4). `c8-card-people-access` moved from wave 3 to wave 4 for this.
3. `c8-reg-applicability`, `c8-reg-gaps`, `c8-reg-history-interpretation` and `c8-reg-internal-links` share a wave with no serialization key in the plan. Rule 3 gives each its own module, so `register/logic.py` is touched only by `c8-register-models-core` and the `reglogic` f03 tasks. The same was done for the five tenants logic packages.
4. `c8-vocab-scales-reasons` had no dependency on `c9-state-machine`, whose fixed case-status categories VOC-S8 asserts, and one was added. **Superseded on 2026-09-20:** `CaseStatusCategory` and the `case_sub_status` list are already in `taxonomy/models.py` and `registry.py` on `main`, so the dependency was removed again.
5. Nobody owned `frontend/src/features/register/register-presentation.ts` or its `tone-by-kind.ts` entries, although six frontend packages render its pills. **Corrected on 2026-09-20:** `frontend/src/features/register/gap-presentation.ts` and the `complianceTone`, `gapTone`, `severityTone` and `applicabilityTone` maps are already on `main`. `c8-ui-applicability` renames `gap-presentation.ts` to `register-presentation.ts` in one move, keeping its test, and extends it; `c8-ui-gaps` extends the same module and adds no tone entry. The only tone append the chunk makes is `riskTone` for `risk_rating`.
6. `c8-ten-teams` sets `tenant_obligation.owner_team` but takes no `mig:register` key. The column moves into `c8-register-models-core`, built with the table. **Corrected on 2026-09-20:** `c8-ten-teams` does not write it either, because the writer is `register/status_logic.py`, which `c8-reg-status` and `c8-reg-entity-status` hold. Each logic module accepts a team owner itself, and `c8-ten-teams` depends on them having done so.
7. `c8-reg-applicability` adds `applicability` to `QueueCounts` on `GET /me` (MY_WORK_AND_MARKETS §3.3), which takes `idapi`. It therefore runs before f03-T51, which holds the same key. **Extended on 2026-09-20:** `QueueCounts` does not exist on `main`; f03-T48 (chunk 6) creates it, so it is a dependency and it sits in the `idapi` chain, which `c8-tenants-api-contract` now heads with the member-removal body.
8. `c8-reg-inventory-overlay-api` takes `libread`, so it cannot run beside f03-T36 or any chunk 3 read package. It starts after the chunk 3 read chain is on `main`, which its `c3-provision-read` dependency already implies; the key is now stated so the dispatch check catches it.
9. `c8-reg-internal-links` needed a migration for `internal_link` and would have taken `mig:register` in a wave of pure logic packages. The table moves into `c8-register-models-gaps-history`, so wave 4 adds no migration at all.
10. `c8-ui-gaps` depends on `c8-home-register-feeds` and `c6-roadmap-screen` in the plan, which look unrelated to a gaps screen. They are kept, and **on 2026-09-20 they moved to `c8-ui-gaps-journey`**, the half that un-fixmes REG-S5, whose last step reads the roadmap for "Our deadline"; the screen half needs neither.
11. `c8-ui-teams` and `c8-ui-member-removal` both write the `tenant-admin` message catalogs, and the plan starts them in the same wave. **Corrected on 2026-09-20:** moving `c8-ui-member-removal` to wave 7 did not separate them, because `c8-ui-teams` is in wave 7 too, and a catalog is rewritten whole rather than appended to. The four writers — `c8-ui-organisation` (wave 5), `c8-ui-teams` and `c8-ui-member-removal` (wave 7) and `c8-ui-support-access` (wave 9) — are ordered by the `tenadminmsg` key of rule 5, which is what keeps the two wave 7 packages off the files at the same time.
12. `c8-support-access-mechanism` and `c8-reg-duty-occurrences` share wave 7 and both would edit `tests_rls.py`, but only one of them is making an append: the mechanism changes the guard itself. Its policy tests move into their own module, so `tests_rls.py` stays an append ledger and the two can run side by side.

**From the coverage critique**

13. `FOUR_EYES_TABLES` gains `applicability_request` in `c8-register-models-core` and `gap` in `c8-register-models-gaps-history`, not in f03-T70. The guard test demands every four-eyes table be listed, so leaving it to f03-T70 would keep it red from wave 3 to wave 8.
14. The new register and tenant routes had no owner for `TENANT_SCOPED_ROUTES`, `apps/shared/routes.py`, `factories.py` and the route-permission list. The two contract packages own them, so every route is gated and isolation-tested from the moment it exists, stub or not.
15. `internal_item` had no owner. It goes to `c8-tenants-contract` (it is part of the tenant's organisation, schema section 17, and `mig:tenants`), because f03-T56 reads it for My work while `c8-reg-internal-links` only links to it.
16. TEN-S4's Gherkin names a sign-off request and a notification, and neither exists before chunks 9 and 10. `c8-ten-out-of-office` rewords it to an approval request and the audit record, says why in `tenants/app.md`, and `c9-signoff` and `c10-delegation` add their halves back. Without this the scenario could not be un-skipped in chunk 8 at all.
17. TEN-S5's two open cases and TEN-S3's case half are chunk 9 (plan ruling 10). `c8-ten-reassignment` and `c8-ten-teams` prove the obligation, gap and duty halves and say so; `c8-close-out` names the case halves.
18. REG-S9 has no chunk 8 owner: REG-06 is R3. It stays skipped, and `c8-close-out` names it rather than leaving a silent gap.
19. TEN-S7 (J-8) stays fixme through chunk 8; `c10-j8-extension` owns it. The participant step it needs from this chunk is f03-T55's.
20. HOM-S1's standing counts and HOM-S4's roadmap are chunk 6 scenarios. `c8-home-register-feeds` fills their register half and `c8-ui-home-register` proves it; neither owns them.
21. `duty_occurrence` was split between two packages with no line between them. `c8-reg-duty-occurrences` owns the table, the generation and REG-S10; `c8-home-register-feeds` owns the roadmap and Today reads over it.
22. AC-REG1 and AC-REG2 belong to f03-T70 and f03-T73, and AC-TEN1 to f03-T66 and f03-T74. The `c8-` packages own AC-REG's applicability, status, gap and stale-write rows only, and `register/app.md` says which criterion each task closes.

**From the 2026-09-20 review** (`docs/reviews/2026-09-20-cloud-branch-reviews/plan-8.md`)

23. The support-access mechanism was a row-level-security bypass in shape: two permissive `FOR SELECT` policies keyed on a transaction-local flag, and the grant read "under the schema owner's read", which means migrator credentials in the API process. Both are gone. A support session activates the one granted tenant through `tenancy.activate()` and reads it under the same policies a member reads it under. The grant row itself is read after the activation, under those policies, so nothing needs to see across tenants. The one new policy is SELECT-only on `support_access`, keyed on `app.platform_user_id`, so a platform person can check their own grant before entering and list their own grants in the console.
24. The whole support-access chain was planned before Alex answered Q1. It now follows `OWNER_RECOMMENDATIONS.md` item 2: the request comes from the console and grants nothing, the bank approves with a step-up, the window starts at approval, and 4 hours is the default, not 8.
25. Chunk 4's problem-report window is not a precedent: item 3 replaced that recommendation and it will not be built. The precedent for a pinned read and its AST guard is `tenancy.identity_lookup()` with `IDENTITY_LOOKUP_TABLES` in `tests_rls.py`, both on `main`.
26. Six tenant lists the plan meant to add were already in `taxonomy/registry.py`, and `frontend/src/features/register/gap-presentation.ts` and the register tone entries were already in the frontend. Both tasks now extend what exists.
27. The `team` list had no model and no registry owner, and `c8-ten-teams` would have written `register/status_logic.py`, which `c8-reg-entity-status` holds in the same wave. The list belongs to `c8-vocab-scales-reasons`, each logic package accepts a team owner in its own module, and `c8-ten-teams` moves behind `c8-reg-entity-status`.
28. `DELETE /tenant/members/{id}` is `deactivateMember` in `identity/api.py`, which no chunk 8 package owned. `c8-tenants-api-contract` owns it and the removal body's schema, takes `idapi`, and heads that chain.
29. `c8-register-api-contract` could not have been green in wave 1: `TENANT_SCOPED_ROUTES` demands a factory that builds the subject, and the register tables arrive two waves later. The routes, the permission lists and the 501 stubs stay in the contract; the isolation entries and their factories land with the tables.
30. Withdraw had no route and the `GET /me` count had no chunk 6 dependency. Both are fixed.
31. The obligation page screen had no owner, although six packages mount a panel on it. It joins the `regfe` chain's owned paths under `obpage`.
32. Wave 7 ran f03-T51, which owns `features/tenant-admin/` and `components/admin/` directory-wide, beside `c8-ui-member-removal`, which owns two files inside them. f03-T51 runs after it, in the `members` chain.
33. `c8-close-out` ran beside f03-T63 and f03-T65, whose journeys it must prove are not fixme, and `c8-security-review` ran before f03-T59 and f03-T72. The tail is reordered.
34. The gap write routes were gated on `register.edit` although `gaps.edit` exists with the same roles; they now use `gaps.edit`.
35. REG-S10 was un-skipped a wave before the roadmap branch it asserts. It is green up to its roadmap line, as REG-S5 already was, and `c8-home-register-feeds` extends it.
36. Seven packages at or past the 60-minute cap are split, and the design cards are split so out of office and member removal do not wait on support access.

## Waves

The tasks in one wave are dispatchable together: their owned paths are disjoint, and where two of them share a serialization key, the key serializes them in the order rule 5 gives — a wave is not a promise that everything in it runs at once. What is binding is depends-on: a task starts when everything in its depends-on is on `main`. The second column lists the chunk 8 `f03-` tasks that become dispatchable in that wave; they are specified in `FEATURES_0_3_TASKS.md` and are shown only so the main agent can see the shared files.

| Wave | `c8-` packages | `f03-` tasks that may run beside them | Keys that serialize inside the wave |
|---|---|---|---|
| 1 | `c8-card-organisation`, `c8-tenants-contract`, `c8-register-api-contract` | f03-T50 | — |
| 2 | `c8-card-obligation-register`, `c8-card-gaps`, `c8-card-support-access`, `c8-tenants-api-contract`, `c8-vocab-scales-reasons` | — | — |
| 3 | `c8-ten-org-api`, `c8-ten-out-of-office`, `c8-register-models-core`, `c8-register-models-gaps-history` | f03-T60 | `mig:register`: core, then gaps-history |
| 4 | `c8-card-people-access`, `c8-reg-status`, `c8-e2e-seed-register`, `c8-reg-applicability`, `c8-reg-gaps`, `c8-reg-history-interpretation`, `c8-reg-internal-links`, `c8-ten-reassignment`, `c8-ten-support-grants`, `c8-vocab-register-usage` | — | — |
| 5 | `c8-ui-organisation`, `c8-reg-entity-status`, `c8-reg-risk-acceptance`, `c8-ui-applicability` | f03-T67 | — |
| 6 | `c8-ui-organisation-journey`, `c8-ten-teams`, `c8-ui-out-of-office`, `c8-reg-inventory-overlay-api`, `c8-recurring-duty-model`, `c8-recurring-duty-proposal`, `c8-ui-where-we-stand` | f03-T68 | `mig:library`/`deps`: model, then proposal |
| 7 | `c8-ui-teams`, `c8-ui-where-we-stand-journey`, `c8-ui-history-interpretation`, `c8-ui-inventory-overlay`, `c8-ui-member-removal`, `c8-reg-duty-occurrences`, `c8-support-access-mechanism` | f03-T69 | `regfe`/`obpage`: where-we-stand-journey, then history-interpretation. `tenadminmsg`: teams, then member-removal |
| 8 | `c8-ui-internal-links`, `c8-home-register-feeds`, `c8-support-access-console-list` | f03-T51, f03-T52, f03-T53, f03-T66, f03-T70, f03-T73 | `ten`: f03-T51, then f03-T52, then f03-T66. `mig:tenants`: f03-T51, then f03-T66 |
| 9 | `c8-ui-gaps`, `c8-ui-home-register`, `c8-ui-support-access` | f03-T54, f03-T74 | — |
| 10 | `c8-ui-gaps-journey`, `c8-ui-risk-acceptance` | f03-T55, f03-T64 | `regfe`: gaps-journey, then risk-acceptance |
| 11 | — | f03-T56, f03-T57, f03-T58, f03-T59, f03-T71 | `mywork`: T56, then T57, then T58, then T59 |
| 12 | — | f03-T61, f03-T62, f03-T72 | — |
| 13 | `c8-security-review` | f03-T63, f03-T65, f03-T75 | — |
| 14 | `c8-review-fixes` | — | — |
| 15 | `c8-close-out` | — | — |

`c8-security-review` starts once every SR package of waves 1 to 8, every chunk 8 `f03-` task marked SR, f03-T59 (the My work service) and f03-T72 (the Statement of Applicability filter) are on `main`, so neither the permission-filtered My work rows nor the SoA filter escapes the chunk review. `c8-review-fixes` therefore never edits `register/api.py` while f03-T72 still holds `regapi`. `c8-close-out` starts once every row above it, `c8-review-fixes` and f03-T63, f03-T64, f03-T65, f03-T73 and f03-T75 are on `main`, so no chunk 8 journey it walks is still fixme. Waves 11 to 15 are later in wall-clock time than their number suggests: the My work chain f03-T55 → f03-T59 and the `regfe` tail run through them.

## Coverage

Every chunk 8 requirement and every scenario, with the one task that owns it.

| Requirement | Owning tasks |
|---|---|
| REG-01 | `c8-reg-applicability` (the single request), f03-T67 (per entity), f03-T70 (many in one call) |
| REG-02 | `c8-reg-status` (the entry), `c8-reg-entity-status` (per legal entity) |
| REG-03 | `c8-reg-gaps`, `c8-reg-risk-acceptance` |
| REG-04 | `c8-reg-history-interpretation` |
| REG-05 | `c8-tenants-contract` (the item), `c8-register-models-gaps-history` (the link row), `c8-reg-internal-links` (the logic and the routes) |
| REG-07 | `c8-recurring-duty-model` and `c8-recurring-duty-proposal` (the library rows and their door), `c8-reg-duty-occurrences` (the tenant occurrences) |
| REG-08 | f03-T67 to f03-T72, f03-T75 |
| TEN-02 | `c8-tenants-contract`, `c8-ten-org-api`, f03-T51 (departments and heads), f03-T66 (certificates) |
| TEN-03 | `c8-vocab-scales-reasons` (the `team` list and its registry entry), `c8-ten-teams` (`TeamMember` and team ownership), f03-T51 (the membership routes and the department) |
| TEN-04 | `c8-ten-out-of-office`, `c8-ui-out-of-office` |
| TEN-05 | `c8-ten-reassignment`, `c8-ui-member-removal`, f03-T64 |
| TEN-06 | `c8-ten-support-grants` (request, approve, decline, revoke), `c8-support-access-mechanism` (the support session and what it reaches), `c8-support-access-console-list` (the platform person's own grants), `c8-ui-support-access` |
| HOM-05 | f03-T50, f03-T55 to f03-T62, f03-T65 |
| COL-04 | f03-T53, f03-T54, f03-T55, f03-T63 |
| VOC-04, VOC-05, VOC-06 | `c8-vocab-scales-reasons`; VOC-02's usage counts for the new lists in `c8-vocab-register-usage` |

| Scenario | Un-skipped or un-fixme'd by | Extended by |
|---|---|---|
| REG-S1 `@integration` | `c8-reg-applicability` | f03-T67 adds the entity's scope row |
| REG-S1 `@e2e` | `c8-ui-applicability` | — |
| REG-S2 | `c8-reg-applicability` | — |
| REG-S3, REG-S4 `@integration` | `c8-reg-entity-status` | — |
| REG-S3 `@e2e` | `c8-ui-where-we-stand-journey` | — |
| REG-S5 `@integration` | `c8-reg-gaps` | — |
| REG-S5 `@e2e` | `c8-ui-gaps-journey` | — |
| REG-S6 `@integration` | `c8-reg-risk-acceptance` | — |
| REG-S6 `@e2e` | `c8-ui-risk-acceptance` | — |
| REG-S7 `@integration` | `c8-reg-history-interpretation` | — |
| REG-S7 `@e2e` | `c8-ui-history-interpretation` | — |
| REG-S8 `@integration` | `c8-reg-internal-links` | — |
| REG-S8 `@e2e` | `c8-ui-internal-links` | — |
| REG-S9 | nobody: REG-06 is R3 (chunk 13). Stays skipped, named by `c8-close-out` | — |
| REG-S10 | `c8-reg-duty-occurrences`, green up to its roadmap line | `c8-home-register-feeds` makes the roadmap line true, as it does for REG-S5 |
| REG-S11 | `c8-reg-status` | — |
| REG-S12 to REG-S16 | f03-T67, f03-T69, f03-T70, f03-T71, f03-T72, f03-T75 | — |
| TEN-S2 `@integration` and `@e2e` | `c8-ten-org-api` (integration), `c8-ui-organisation-journey` (journey) | `c8-ui-teams` extends the journey with the teams section; f03-T66 adds the certificate line |
| TEN-S3 | `c8-ten-teams` (register half) | `c9-triage` adds the case half (plan ruling 10) |
| TEN-S4 `@integration` and `@e2e` | `c8-ten-out-of-office` (integration), `c8-ui-out-of-office` (journey), reworded | `c9-signoff` and `c10-delegation` |
| TEN-S5 `@integration` and `@e2e` | `c8-ten-reassignment` (integration), `c8-ui-member-removal` (journey) | `c9-actions` adds cases and actions; f03-T64 adds participations and teams |
| TEN-S6 `@integration` and `@e2e`, rewritten | `c8-ten-support-grants` rewrites the scenario and owns the request, approve and revoke halves; `c8-support-access-mechanism` owns the 404, the logged reads, the 403 on a write and the 401 after revoke; `c8-ui-support-access` (journey) | — |
| TEN-S7 | `c10-j8-extension` (chunk 10). Stays fixme, named by `c8-close-out` | — |
| TEN-S8, TEN-S9, TEN-S10 | f03-T51, f03-T64, f03-T66 | — |
| HOM-S7 to HOM-S14 | f03-T56 to f03-T62, f03-T65 | — |
| HOM-S15 | f03-T74 | — |
| HOM-S1, HOM-S4, HOM-S6 | chunk 6 owns them | `c8-home-register-feeds` and `c8-ui-home-register` keep them green with the register data |
| COL-S6, COL-S7, COL-S8 | f03-T55, f03-T63 | — |
| VOC-S8, VOC-S9, VOC-S10 | `c8-vocab-scales-reasons` | — |
| VOC-S3, VOC-S4 | chunk 2 and chunk 3 own them | `c8-vocab-register-usage` adds the register lists' usage counts |
| INV-S3, INV-S4 | chunk 3 owns them | `c8-ui-inventory-overlay` adds the overlay columns |
| AC-REG1, AC-REG2 | f03-T70, f03-T73 | — |
| AC-TEN1 | f03-T66, f03-T74 | — |

## Open questions

Q1 and the private-notes question were answered on 2026-09-19 and are recorded here as closed, so nobody re-opens them. Q2 to Q4 are still open and none of them blocks; Q5 was never a question.

- **Q1 (support access) is answered and closed.** Alex accepted the recommendation on 2026-09-19 (`OWNER_RECOMMENDATIONS.md` item 2, "Alex's answers" row 2). Nothing in this chunk waits on it, and the design it settles is binding on `c8-tenants-api-contract`, `c8-ten-support-grants`, `c8-support-access-mechanism`, `c8-support-access-console-list`, `c8-card-support-access`, `c8-ui-support-access` and `c10-j8-extension`:
  - **The platform admin requests**, from the console, under `support_access.grant` and with no step-up, because a request grants nothing. A purpose is required, a ticket reference is optional, and the duration may be up to `SUPPORT_ACCESS_MAX_HOURS` (default 4). A request nobody decides lapses after `SUPPORT_ACCESS_REQUEST_TTL_HOURS`. Until approval, reads answer 404.
  - **The bank admin decides**, under `security.manage`. Approve needs a passkey step-up and starts the window; decline and revoke need none. A database CHECK enforces `approved_by <> platform_user_id`, and a guard trigger refuses a DELETE and refuses any change to the tenant, the person, the purpose, the ticket, the level or the duration after insert.
  - **Entering** needs `support_access.grant` plus a step-up. It replaces the console session with a support session carrying the grant id and expiring with the window; the session may refresh and sign out. Every request re-reads the grant, and a revoked or expired grant answers 401 `support_access_ended`.
  - **What it reaches**: `library.read`, `watch.read`, `roadmap.read`, `register.read`, `cases.read`, `reports.read` and `audit.read`, and nothing else. No search and no Ask, because both are POST and would spend the bank's AI budget; no role rows and no platform grants. The routes those reads cover are named one by one in the `SUPPORT_READ_ROUTES` allow-list of `apps/shared/routes.py`, and everything else answers 403 `support_read_only`: every write, the evidence and export downloads, and any route added later until someone puts it on the list.
  - **Every request writes one `support_access.read` audit row in that tenant**, holding the route template and the path ids, never a query string and never a body, and it reaches the bank's SIEM stream through the outbox.
  - **It is read-only.** `access_level` is written as `read`; the write level answers 422 `unknown_key`, which leaves the chunk 1 one-shot recovery row as the only write-level row.
  - **PRD 0.4** changes two permission descriptions and adds no permission: `support_access.grant` becomes "request support access to a tenant and enter it read-only once a tenant admin approves", and `security.manage` gains "includes approving, declining and revoking support access". `c8-ten-support-grants` carries that change, the ADR and the `permissions.py` descriptions, because it is the first support-access package to land.
  - **TEN-S6 is rewritten** by `c8-ten-support-grants`: request, 404, approve, reads logged, a write answers 403, then revoke gives 401 and 404 after that.

- **The private-notes question (D-22) is closed**, not open. `OWNER_RECOMMENDATIONS.md` item 13 was accepted: no private notes; notes on My work are the shared comments, ADR 0028 moves to accepted, and the question closes in `DECISIONS.md` and `TODO_FOR_alex.md`. `c8-close-out` does not copy it forward.

- **Q2 (a product invariant is at stake): may the tenant zone hold a standard's clause and control references at all?** D-41 records the default and its fallback, and its "owner confirms" column asks for a lawyer's view before the first bank uses units.
  - Recommended: keep D-41's default. `soa_unit` holds the tenant's own reference and its own words, the library holds no clause title and no paraphrase, and f03-T73's guard test proves nothing written under a standard reaches an index, an embedder or a model.
  - If the answer is no, chunk 8 ships without `soa_unit`: f03-T68 to f03-T72 and f03-T75 are cut, the conformance row per entity stands with the tenant's own SoA as evidence, and nothing else in this plan changes.
  - It does not block: the build takes D-41's default and f03-T67 lands either way.

- **Q3: may a Contributor add participants to a register entry?** D-19's owner-confirms row. The default is no: adding needs `register.edit`, which keeps the PRD section 6 matrix unchanged. Changing it would add a permission and bump the PRD, so it is Alex's. Nothing waits; f03-T55 builds the default.

- **Q4: should a Statement of Applicability CSV export be pulled into chunk 8?** D-46's open question. The default is no: the register filtered by standard and entity is the SoA in R2, and the dated export is REP-02 in R3. Banks need the document at a certification audit, so Alex may want it earlier. If yes, it is a new package on top of f03-T72 and `c12-exports-contract`, not a change to an existing one.

- **Q5: the risk-acceptance reason list.** VOC-06 gives the tenant dismissal, closure and risk-acceptance reasons. `c8-vocab-scales-reasons` seeds each list with system rows an admin can relabel but not remove. The seeded keys for risk acceptance are `accepted_by_management`, `cost_disproportionate`, `compensating_control`, `time_limited` and `other`. No input defines them, so this is a default, not a question; it is listed here so Alex sees the words that will appear on screen.

## Tasks

### c8-card-organisation: the organisation card — entities, licences and products

**Requirements:** TEN-02, TEN-03, ADM-01  
**Scenarios:** contributes to TEN-S2 and TEN-S8; no test un-skipped  
**Depends on:** p03-consolidation

Extend the chunk 1 card `design/screens/admin-organisation.html` with the sections chunk 8 builds, in both themes, on Green tokens and the existing pill slots:
- **Legal entities and org units.** A tree of org units by kind (group, legal entity, business area, business unit, function), each with its name, org number, LEI, country and the legal-entity scope term it ties to. Inactive units are dimmed, never hidden.
- **Licences and certificates**, per legal entity: licence type, reference, granted, withdrawn, the services it covers and a scope note. Leave the validity, next audit and owner fields as empty slots with a note that f03-T66 fills them, so that task adds no layout.
- **Products**: name, description, status (planned, live, retired), launch date, owner and the taxonomy terms that scope it, shown with the same chips the obligation scope uses.
- **Teams**: name, email and the members count, with the department column left as an empty slot for f03-T51.
- **States**: empty, loading, error and denied, and the phone width.

Do not draw departments with heads, team membership or the certificate fields: f03-T60 adds them on top of this card, and it starts only once this one is merged (`cards:admin-organisation.html`).

**Owned paths:**

- `design/screens/admin-organisation.html`
- `design/README.md` (the card's row only)

**Done when:**

- The card renders in light and dark with no new pill slot and no new tone, and is reachable from `design/README.md`.
- Every field the chunk 8 tenants API will return has a place on the card, and every place has a field.
- The certificate, department and team-membership slots are present and empty, with a comment naming f03-T66 and f03-T51.
- No message key, no component and no backend file changes.

**Gates:**

- Open the card in both themes at phone and desktop width and check it against `design/system/` and `design/brand/README.md`.
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- Six pill tones only, chosen by slot or kind. Pills only through the `Pill` pattern.
- Typography roles only (`text-display`, `text-title`, `text-body`, `text-meta`, `.microlabel`).
- The prototype in `design/` decides how things look, never what the rules are.

### c8-tenants-contract: the tenant organisation tables

**Requirements:** TEN-02, TEN-03, REG-05  
**Scenarios:** contributes to TEN-S2, TEN-S3, TEN-S8, TEN-S10, HOM-S7  
**Depends on:** p03-consolidation

Add the tenant organisation models in one `tenants` migration, every one a `TenantModel` under enabled and forced row-level security:
- **`OrgUnit`**: `parent`, `kind` (a tier-one kind: group, legal entity, business area, business unit, function), `name`, `org_number`, `lei`, `country_code`, `entity_term` (a `legal_entity` taxonomy term), `active`. `head_user` is **not** added here; f03-T51 adds it with its composite key.
- **`Licence`**: `org_unit`, `authority`, `licence_type`, `reference`, `granted_on`, `withdrawn_on`, `service_terms`, `scope_note`. The certificate columns are f03-T66's.
- **`TenantProduct`** and **`TenantProductTerm`**: name, description, status, launch date, owner, org unit, and the taxonomy terms that scope it.
- **`InternalItem`**: `kind` (the `link_kind` tenant list), `name`, `reference`, `url`, `owner`, `org_unit`, `external_system`, `external_ref`, `last_reviewed_on`, `next_review_on`, `active`, unique per `(tenant, kind, name)`. It lives here, not in `register`, because it is part of the tenant's organisation and f03-T56 reads it for My work.
- **`UNIQUE (tenant_id, id)`** on `OrgUnit`, added as SQL in the migration the way the RLS policies are, so f03-T51's and f03-T53's composite keys can point at it.

`Team` and `TeamMember` are **not** here. A team is a tier-three tenant list (the default above), so `Team` and `TeamLabel` belong to `c8-vocab-scales-reasons` in `taxonomy`, and `TeamMember` with its composite keys to that table and to `membership` belongs to `c8-ten-teams`, which takes `mig:tenants` after this package.

Register every new table in `apps/shared/tests_rls.py`'s guarded list and in `tests_seed_integrity.py` where it is seeded. Add no route: `c8-tenants-api-contract` owns the API.

**Owned paths:**

- `backend/apps/tenants/models.py`
- `backend/apps/tenants/migrations/0002_organisation.py`
- `backend/apps/shared/kinds.py` (the org-unit kind only, an append)
- `backend/apps/tenants/tests_models.py`
- `backend/apps/shared/tests_rls.py` (the guarded-table list, an append)
- `backend/apps/tenants/app.md` (the TEN-02 and TEN-03 status cells)

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies and reverses the graph.
- Every new table is listed in the RLS guard as forced tenant-only, and a test as `cw_app` proves tenant B sees none of tenant A's rows.
- A test proves the database refuses an org unit whose parent belongs to another tenant, and an internal item whose org unit belongs to another tenant.
- `UNIQUE (tenant_id, id)` exists on `org_unit`.
- `Meta.ordering` is set on every model something will `.first()`.
- The diff stays inside the owned paths and adds no route and no logic.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Every tenant table carries `tenant_id` under enabled and forced row-level security; `cw_app` cannot bypass it.
- snake_case columns, camelCase only in the API. No `JSONField` without an inline suppression naming its schema.
- Kinds in code are kinds only; `link_kind` and the statuses are rows.
- Composite foreign keys, because PostgreSQL foreign-key checks bypass row-level security.
- No `admin.py`, no logic in a model beyond `__str__`.

### c8-register-api-contract: every register route, stubbed behind its real gate

**Requirements:** REG-01, REG-02, REG-03, REG-04, REG-05, REG-07  
**Scenarios:** none un-skipped; it makes REG-S1 to REG-S11 reachable  
**Depends on:** p03-consolidation

Write `backend/apps/register/api.py` and `schemas.py` once, mount the router in `config/api.py`, and send every operation to a named function that answers 501 `not_built`:
- `PATCH /obligations/{id}/register` → `status_logic.update_register`, `register.edit`, `If-Match`.
- `GET /obligations/{id}/register` → `status_logic.read_register`, `register.read`.
- `GET /applicability-requests`, `POST /obligations/{id}/applicability-requests` → `applicability.list_requests`, `applicability.request_change`; `register.read` and `applicability.request`.
- `POST /applicability-requests/{id}/approve` and `/reject` → `applicability.approve`, `applicability.reject`; `applicability.approve` plus `@requires_step_up` on approve.
- `POST /applicability-requests/{id}/withdraw` → `applicability.withdraw_request`, `applicability.request`, no step-up. The requester withdraws their own pending request; anyone else's answers 403. Without this route `c8-reg-applicability` would have to write `api.py`, which rule 3 forbids.
- `GET/POST /obligations/{id}/gaps`, `PATCH /gaps/{id}`, `POST /gaps/{id}/accept-risk`, `POST /gaps/{id}/accept-risk/approve` → `gaps.*`; **`gaps.edit`** on the writes, and `risk.accept.approve` with `@requires_step_up` on the approval. `gaps.edit` (`GAPS_EDIT`) is in PRD section 6 and in `permissions.py` with the same roles `register.edit` has, so nothing about who may do what changes; gating the gap writes on `register.edit` would leave a permission the matrix names and no route uses, and would make a role composed with `gaps.edit` alone unable to write a gap.
- `GET /gaps` → `gaps.list_gaps`, `register.read`.
- `GET /obligations/{id}/assessments`, `GET/PUT /obligations/{id}/interpretation` → `history.*`; `register.read` and `register.edit`.
- `GET/POST /obligations/{id}/internal-links`, `DELETE /internal-links/{id}` → `links.*`; `register.read` and `register.edit`.
- `GET /obligations/{id}/duties`, `POST /duty-occurrences/{id}/complete` → `duties.*`; `register.read` and `register.edit`.

Schemas in `schemas.py` only, camelCase through the alias generator, app-prefixed where they are register-specific, never `Dict[str, Any]`. Every vocabulary-valued field is `{key, kind, label}` on reads and `key` on writes.

Add every route to `apps/shared/routes.py` and to the route lists in `permissions.py`, so every route is gated from the moment it exists. Add one `contract_drift_pending.txt` line per operation the designed contract does not have, each with its reason.

**The isolation entries are not this package's.** `TENANT_SCOPED_ROUTES` demands a factory that builds the route's subject on a tenant-private record, and the register tables do not exist until wave 3. `c8-register-models-core` and `c8-register-models-gaps-history` each register the routes whose subject their own tables create, with the factory, in the commit that creates the table; `c8-close-out` proves every chunk 8 route is listed. Registering a route here with no factory would leave the isolation guard red for two waves.

**Owned paths:**

- `backend/apps/register/api.py`
- `backend/apps/register/schemas.py`
- `backend/config/api.py` (the router mount, an append)
- `backend/apps/shared/routes.py` (an append; not `TENANT_SCOPED_ROUTES`, and not `factories.py`)
- `backend/apps/shared/permissions.py` (the route lists only, an append)
- `backend/scripts/contract_drift_pending.txt` (an append)
- `backend/apps/register/tests_api_contract.py`

**Done when:**

- Every route answers 401 without a session, 403 without its permission, `step_up_required` where required, and 501 `not_built` for a caller who holds everything.
- `tests_route_permissions` passes with every new route listed and no route in `UNGATED_BY_DESIGN`; `tests_tenant_isolation` stays green and unchanged, because this package adds nothing to `TENANT_SCOPED_ROUTES`.
- `generate-types.sh` runs clean and `contract_drift.py` passes with the new pending lines.
- The mutating operation ids are named in the skipped scenarios that will build them.
- `api.py` holds no logic and no `*args`/`**kwargs`.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only; do not commit openapi.json or api.generated.ts`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Routes only in `api.py`: an auth class, `@requires_permission`, `@requires_step_up`.
- RFC 9457 problem details with a `code`; never a trace. An empty answer is 200.
- `If-Match` on every versioned record.
- The API returns `key` and `kind`, never a phrase, and no OpenAPI `enum` of tenant values.
- A stub is not a quarantine: it answers behind its real gate and its scenario stays skipped.

### c8-card-obligation-register: the obligation page's register panels

**Requirements:** REG-01, REG-02, REG-04, REG-05, REG-08  
**Scenarios:** contributes to REG-S1, REG-S3, REG-S7, REG-S8, REG-S13, REG-S15  
**Depends on:** p03-consolidation

Extend `design/screens/tenant-obligation.html` with the right-column register panels, from the prototype's `vObligation()`:
- **Does it apply to us** — the applicability pill, the reason, who decided and when, "Waiting for approval" while a request is pending, and the request and approve actions with their step-up marker.
- **Where we stand** — the compliance pill, the status note, risk, first-line owner, compliance contact and next review, with the stale-write message.
- **How we handle it** — process, system and evidence location.
- **Per legal entity** — one row per scope row with its own applicability, status, note, owner and next review, and the worst-of roll-up shown on the header.
- **How we read this rule** — the current interpretation with its author and date, and the assessment history beneath it.
- **Linked internal items** — kind label, name, external reference and the outside link.
- **Units** — the list and the paste dialog's entry point, drawn as empty slots with a comment naming f03-T71, so that task adds no layout.

Leave a slot for the participants panel with a comment naming f03-T60, which extends this card after it merges.

**Owned paths:**

- `design/screens/tenant-obligation.html`
- `design/README.md` (the card's row only)

**Done when:**

- Every panel renders in both themes at phone and desktop width, with existing pill slots and tones only.
- The applicability pill and the compliance pill are drawn from the kind, and the card says so.
- The units and participants slots are present, empty and commented.
- No message key, component or backend file changes.

**Gates:**

- Read the card against `design/system/pills-and-labels.md` and the prototype's `vObligation()`.
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- Six pill tones, chosen by slot or kind, never by a person.
- Typography roles only. No requirement ID and no restated invariant on screen.
- The card shows no clause or control text of a standard, only the tenant's own words.

### c8-card-gaps: the gaps screen and the gap record

**Requirements:** REG-03  
**Scenarios:** contributes to REG-S5 and REG-S6  
**Depends on:** p03-consolidation

Draw the new card `design/screens/tenant-gaps.html` from the prototype's `vGaps()` and `vGap()`:
- **The list**: gaps across the register with filters for status, severity, owner and target date, each row showing the obligation, the title, the status pill, the severity pill and the source pill, the owner and the days to target.
- **The record**: title, description, severity, source, identified by and when, owner, target date, the remediation plan, and the actions Record a gap, Start remediation, Close and Accept the risk.
- **Risk acceptance**: the reason picker, "Waiting for approval", the four-eyes refusal and the approver's step-up, then "Risk accepted" in the `information` tone.
- **States**: empty, loading, error, denied and the phone width.

This card owns no part of `tenant-obligation.html`: the gaps panel on the obligation page belongs to `c8-card-obligation-register`.

**Owned paths:**

- `design/screens/tenant-gaps.html`
- `design/README.md` (the card's row only)

**Done when:**

- The card renders in both themes with no new pill slot and no new tone.
- Open is `negative`, Remediating is `warning`, Accepted is `information` and Closed is `positive`, each from the status row's kind.
- Every field the gaps API will return has a place, and every place a field.

**Gates:**

- Read the card against `design/system/pills-and-labels.md` and the prototype's `vGaps()` and `vGap()`.
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- Pills only through the `Pill` pattern, tones from the kind.
- Screen copy says what the user is doing; no requirement IDs.

### c8-card-support-access: the support access cards, both sides

**Requirements:** TEN-06  
**Scenarios:** contributes to TEN-S6  
**Depends on:** p03-consolidation

Draw the two support-access cards to the design Q1 settles, and the read-only banner with them. They are separate from `c8-card-people-access` so that out of office and member removal, which have no support-access content, wait for nothing this card waits for:
- **`design/screens/admin-support-access.html`** (new), the bank's Support access panel: the pending requests with the platform person's name and role, the purpose, the ticket and the asked-for window, with Approve (step-up marked), Decline and, on a live grant, Revoke; the active grant with its window and who approved it; and the history, linked to the audit log, of every read under a grant.
- **`design/screens/console-support-access.html`** (new), the platform side: request a grant for one bank with a purpose, an optional ticket and a duration up to `SUPPORT_ACCESS_MAX_HOURS`; the person's own grants with their state; and Enter, marked with its step-up. The bank is named by its organisation name and never by a member's name, and an approval shows as a time, not a person.
- **The read-only banner** a support session carries on every tenant screen, drawn once as a component sample inside `admin-support-access.html`, with the copy for 403 `support_read_only` and 401 `support_access_ended`. It is drawn here and not on `tenant-obligation.html`, so this card queues behind nothing.

**Owned paths:**

- `design/screens/admin-support-access.html`
- `design/screens/console-support-access.html`
- `design/README.md` (the card rows only)

**Done when:**

- Each card renders in both themes at phone and desktop width with no new pill slot and no new tone.
- The bank's card shows the purpose, the window, the platform person, the approver and the log, as AC-TEN1's sibling criterion requires, and shows Revoke on a live grant.
- The console card names no tenant member anywhere, and shows the request as a request: nothing on it says access is granted before a bank admin approves.
- The banner sample is on `admin-support-access.html` and no other card file changed.
- No message key, no component and no backend file changes.

**Gates:**

- Read the cards against `design/system/` and the prototype.
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- Six pill tones only. Typography roles only.
- No tenant content and no member name on a console card.
- Never a 403 where a 404 hides existence: the card's refused state reads "Not found".
- Screen copy says what the user is doing; no requirement IDs.

### c8-tenants-api-contract: every tenant organisation route, stubbed behind its real gate

**Requirements:** TEN-02, TEN-03, TEN-04, TEN-05, TEN-06, ADM-01, ADM-03  
**Scenarios:** none un-skipped; it makes TEN-S2 to TEN-S6 reachable  
**Depends on:** c4-console-tenants-api, c8-tenants-contract

Extend `backend/apps/tenants/api.py` and `schemas.py` with the chunk 8 routes, each sent to a named function that answers 501 `not_built`:
- `GET/POST /tenant/org-units`, `PATCH /tenant/org-units/{id}` → `organisation.*`, `vocab.manage` to write, any member to read.
- `GET/POST /tenant/org-units/{id}/licences`, `PATCH /tenant/licences/{id}` → `organisation.*`, `vocab.manage`.
- `GET/POST /tenant/products`, `PATCH /tenant/products/{id}` → `organisation.*`, `vocab.manage`.
- `GET /tenant/teams`, `GET /tenant/teams/{id}/members` → `teams.*`, any member. **No team CRUD here:** a team is a tier-three tenant list, so create, rename and retire are the existing `/vocab/team` routes under `vocab.manage`. f03-T51 adds the membership writes.
- `GET/PUT /me/out-of-office` → `out_of_office.*`, any member for their own row; `members.manage` to read another's.
- `GET /tenant/members/{id}/open-work` → `reassignment.open_work`, `members.manage`.
- **The reassignment body on `DELETE /tenant/members/{id}`.** That route is `deactivateMember` in `backend/apps/identity/api.py`, not in `tenants`, so this package owns `identity/api.py` and the removal body in `identity/schemas.py` and takes the `idapi` key, heading that chain. The body sends a target owner per kind; the route calls `reassignment.remove_member` under `members.manage` with `@requires_step_up`. Without this, nobody in chunk 8 owned the route and `c8-ten-reassignment` would have had to edit an `api.py` rule 3 keeps it out of.
- **Support access, exactly as Q1 settles it.** The console side, in the same module as the chunk 4 console tenant routes (`/console/tenants/...` in `tenants/api.py`): `POST /console/tenants/{id}/support-access` → `support_access.request_access`, `support_access.grant`, **no step-up**, because a request grants nothing (ADM-S6: the request is not access until a tenant admin approves it); `GET /console/support-access` → `support_access.my_grants`, `support_access.grant`, the requester's own grants only; `POST /console/support-access/{id}/enter` → `support_access.enter`, `support_access.grant` with `@requires_step_up`. The tenant side: `GET /tenant/support-access` → `support_access.list_for_tenant`, any member; `POST /tenant/support-access/{id}/approve` → `support_access.approve`, `security.manage` with `@requires_step_up`; `POST /tenant/support-access/{id}/decline` and `/revoke` → `support_access.decline`, `support_access.revoke`, `security.manage`, no step-up (playbook 4.2: a refusal never needs one).

Add every route to `apps/shared/routes.py`, `factories.py`, `TENANT_SCOPED_ROUTES` and the route lists in `permissions.py`, and one `contract_drift_pending.txt` line per operation the designed contract does not have.

**Owned paths:**

- `backend/apps/tenants/api.py`
- `backend/apps/tenants/schemas.py`
- `backend/apps/identity/api.py` (the removal body on `deactivateMember` only) and `backend/apps/identity/schemas.py` (that body only); it holds `idapi`
- `backend/apps/shared/routes.py`, `backend/apps/shared/factories.py` (appends; the tenant tables exist from `c8-tenants-contract`, so this package does register its routes in `TENANT_SCOPED_ROUTES` with their factories)
- `backend/apps/shared/permissions.py` (the route lists only, an append)
- `backend/scripts/contract_drift_pending.txt` (an append)
- `backend/apps/tenants/tests_api_contract.py`

**Done when:**

- Every route answers 401, 403, `step_up_required` and 501 `not_built` as above, and `tests_route_permissions` and `tests_tenant_isolation` list them all.
- `DELETE /tenant/members/{id}` keeps its current behaviour for a member with no open work, with a regression test; the new body is optional on the wire until `c8-ten-reassignment` requires it.
- ADM-S1 and ADM-S3 stay green: each admin permission still gates its own screens independently.
- `generate-types.sh` runs clean and `contract_drift.py` passes.
- `api.py` holds no logic.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.tenants apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Permissions, never role names. Admin duties stay separate permissions (ADM-03).
- Step-up on the removal, on the approval of a support grant and on entering one; never on a request, a decline or a revoke (playbook 4.2).
- No logic in `api.py`; schemas in `schemas.py`.
- Nothing about support access is decided here: the shape is Q1's answer and the routes answer 501 until `c8-ten-support-grants` builds them.

### c8-vocab-scales-reasons: tenant statuses, scales and reason lists

**Requirements:** VOC-04, VOC-05, VOC-06, VOC-01, VOC-02  
**Scenarios:** VOC-S8, VOC-S9, VOC-S10 un-skipped; VOC-S1, VOC-S3, VOC-S4, VOC-S14 stay green  
**Depends on:** c3-no-tone, p03-consolidation

**Most of these lists are already on `main`.** `taxonomy/registry.py` registers `link_kind`, `compliance_status` (kind `compliance_category`, with `ordinal`), `risk_rating` (with `ordinal`), `case_sub_status` (kind `case_status` from `CaseStatusCategory`), `dismissal_reason` and `close_reason` as tier-three tenant lists, and `CaseStatusCategory` is in `taxonomy/models.py`. This package adds only what is missing, and proves VOC-S8 to VOC-S10 over the lists that exist. It does **not** depend on `c9-state-machine`.

Add, each a vocabulary row with an immutable `key`, a fixed `kind`, labels per language, a `usage_note`, `sort_order`, `active`, `is_system` and `is_default`:
- **`gap_status`** with kinds `open`, `remediating`, `risk_accepted`, `closed`, and a system row per kind. The accepted state is `risk_accepted`, not `accepted`, because `frontend/src/features/shared/tone-by-kind.ts` on `main` already spells it that way; taking the frontend's name means no shipped module changes and no second name for one state. The kind enum goes in `taxonomy/models.py` beside `ComplianceCategory`.
- **The risk-acceptance reason list**, seeded with `accepted_by_management`, `cost_disproportionate`, `compensating_control`, `time_limited` and `other` (Q5 above). Dismissal and closure reasons exist already.
- **`team`**, the tier-three list TEN-03 and MY_WORK_AND_MARKETS §3.2 need: `Team(TenantListVocabulary)` with the extra field `email`, and `TeamLabel`, with its registry entry so `GET /vocab/team` feeds every picker and create, rename and retire are the tenant-list routes under `vocab.manage`. Add `UNIQUE (tenant_id, id)` on `team` as SQL in the migration, the way the RLS policies are, so `c8-ten-teams`' `TeamMember` and f03-T51's department can point at it with a composite key, and add the table to the RLS guarded list. `team` is not part of VOC-04 to VOC-06 and is never descoped; it rides here because this package holds `taxreg`.

Then prove the scenarios over the whole set, existing lists included:

Rules:
- A category never goes empty: retiring the last active row under a category answers 409 `category_empty` (VOC-S8), tested over `compliance_status`, `case_sub_status`, `close_reason` and the new `gap_status`.
- A tone comes from the kind's ordinal, never from the label (VOC-S9).
- An unknown reason key answers 422 `unknown_key` with the valid keys (VOC-S10).
- Adding a row changes neither `openapi.json` nor `api.generated.ts`.
- `seed_reference` files the system rows create-only, and a relabel, a reorder, a retire or a default change survives the next run.

**Owned paths:**

- `backend/apps/taxonomy/registry.py`
- `backend/apps/taxonomy/models.py`
- `backend/apps/taxonomy/migrations/000X_register_lists.py`
- `backend/apps/taxonomy/seeds/__init__.py`
- `backend/apps/taxonomy/tenant_lists_logic.py`
- `backend/apps/taxonomy/tests_vocabulary.py`
- `backend/apps/taxonomy/tests_scenarios.py`
- `backend/apps/shared/tests_rls.py` (the `team` and `team_label` tables, an append)
- `backend/apps/taxonomy/app.md` (the VOC-04, VOC-05, VOC-06 status cells)

**Done when:**

- `test_voc_s8`, `test_voc_s9` and `test_voc_s10` are un-skipped and green over the new lists **and** the lists already on `main`.
- Only `gap_status`, the risk-acceptance reason list and `team` are added: a test asserts that the registry gained exactly those three entries and that no existing entry changed.
- `GET /vocab/team` returns the tenant's active teams with their keys and labels, and `team` and `team_label` are forced tenant-only in the RLS guard with a `cw_app` test.
- `UNIQUE (tenant_id, id)` exists on `team`.
- `makemigrations --check` is clean and `migrate_from_zero` applies the graph.
- The vocabulary integrity guard passes: every list has a registry entry, every system row a label in en and sv, and every key is immutable.
- Retiring the last row of a category answers 409 `category_empty`, and a test covers each category.
- The pill tone test derives every tone from the kind, and no TypeScript union of statuses exists.
- Re-running the seed keeps a relabelled, reordered or retired row.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Enums in code are kinds only; types, statuses, tags and reasons are rows an admin manages.
- Store and compare keys, never labels. The API returns `key` and `kind`.
- A tenant list is written under `vocab.manage`; a library list write is still a proposal (VOC-07).
- Six pill tones, from the kind.
- Every write goes through `record()`, with the audit and outbox rows in the same transaction.

### c8-ten-org-api: legal entities, licences and products

**Requirements:** TEN-02  
**Scenarios:** TEN-S2 `@integration` un-skipped  
**Depends on:** c8-tenants-contract, c8-tenants-api-contract

Build `backend/apps/tenants/organisation.py` and replace the stubs:
- Create, read and amend org units, with the parent tree, the kind, the org number, the LEI, the country and the `legal_entity` term it ties to. A unit is deactivated, never deleted.
- Licences per legal entity, with their services as taxonomy terms and a scope note. A withdrawn licence stays readable.
- Products with their status, launch date, owner, org unit and scope terms, written the way an obligation's scope is written, so the register can ask which obligations hit a product.
- Every write goes through `record()` with before and after values, under `vocab.manage`, with `If-Match` on the versioned rows.
- 422 `unknown_key` for a term that is not of the dimension the field takes, and 422 `unknown_member` for an owner who is not an active member of this tenant.

TEN-S2 is un-skipped for the entity, licence and product halves. Its certificate line stays as the scenario's last `And`, which f03-T66 makes true; note that in `tenants/app.md` rather than weakening the scenario.

**Owned paths:**

- `backend/apps/tenants/organisation.py`
- `backend/apps/tenants/tests_organisation.py`
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S2 block only)
- `backend/apps/tenants/app.md` (the TEN-02 status cell and the TEN-S2 note)

**Done when:**

- `test_ten_s2` is un-skipped and green for entities, licences and products.
- Entities and products carry terms from the same dimensions obligations are scoped with, proved by a test that reads the dimension from the registry, not from a literal.
- A cross-tenant term, owner or org unit is refused, and tenant B receives 404 for tenant A's rows.
- Every write has an audit row in the same transaction, with before and after values.
- `GET /tenant/org-units` stays under `API_BUDGET_MS` on the seeded tree.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.tenants apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- All logic in `organisation.py`, none in `api.py`. No `*args`/`**kwargs`.
- Every write through `record()`; `If-Match` on versioned records.
- Permissions, never role names; `tenancy.activate()` after auth.
- `ValidationError` with user-facing text; the client branches on `code`.
- Nothing is overwritten: a licence is withdrawn, a unit deactivated.

### c8-ten-out-of-office: a delegate receives approvals while you are away

**Requirements:** TEN-04  
**Scenarios:** TEN-S4 `@integration` reworded and un-skipped  
**Depends on:** c8-tenants-contract, c8-tenants-api-contract

Build `backend/apps/tenants/out_of_office.py`:
- An `OutOfOffice` row per user per window: `from`, `to`, `delegate`, in the tenant's timezone, under forced row-level security, with `version` and `If-Match`.
- One resolver, `delegates_for(user, at)`, which every approval route asks: while the window is open the delegate may act in the absent person's place.
- **The delegate needs the approve permission themself** (plan 7.2). Delegation routes work; it grants nothing. A delegate without the permission is refused 422 `participant_cannot_read`'s sibling, 422 `delegate_cannot_approve`.
- The audit event records the delegate as actor and the absent approver as delegated, in the same transaction.
- A window that has closed routes nothing; a person may hold at most one open window, and a second answers 409 `already_delegated`.
- Four eyes is unchanged: a delegate who is also the requester is still refused with 409 `four_eyes_violation`.

**Rewording TEN-S4, with its reason in `tenants/app.md`.** The scenario names a sign-off request and a notification, and neither exists before chunks 9 and 10. Chunk 8 proves it on an applicability approval and on the audit record; `c9-signoff` adds the sign-off step and `c10-delegation` adds the notification. Say this in `app.md` beside the scenario and keep both halves named, so nothing is lost.

**Owned paths:**

- `backend/apps/tenants/out_of_office.py`
- `backend/apps/tenants/models.py` (the `OutOfOffice` model only) and `backend/apps/tenants/migrations/0003_out_of_office.py`. It therefore holds `mig:tenants`, free since wave 1
- `backend/apps/tenants/tests_out_of_office.py`
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S4 block only)
- `backend/apps/tenants/app.md` (the TEN-04 status cell and the TEN-S4 rewording)

**Done when:**

- `test_ten_s4` is un-skipped and green in its reworded form: the delegate may approve inside the window, cannot outside it, and the audit event names both people.
- A delegate without the approve permission is refused, with a test.
- Windows are evaluated in the tenant's timezone and stored in UTC, with a test that pins the dates and never reads today's date.
- The row is in the RLS guard list and `migrate_from_zero` is green.
- Four eyes still refuses a delegate who is the requester.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.tenants apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Four eyes, enforced by a check constraint, is never routed around: a delegate is a second person, not a way past one.
- A delegation grants no permission.
- UTC timestamps; the tenant's timezone converts them.
- Every write through `record()`, audit in the same transaction.
- A reworded scenario keeps both halves named; nothing is deleted from `app.md`.

### c8-register-models-core: the register entry, its scope rows and applicability requests

**Requirements:** REG-01, REG-02  
**Scenarios:** contributes to REG-S1 to REG-S4 and REG-S11; none un-skipped  
**Depends on:** c8-tenants-contract, c8-vocab-scales-reasons, c8-register-api-contract

The first half of the register migration. Every model is a `TenantModel` under enabled and forced row-level security, with `version` on every tenant-editable row:
- **`TenantObligation`**: `obligation`, `applicability` (a tier-one kind), `applicability_reason`, `applicability_decided_at`, `compliance_status` and `risk_rating` as tenant vocabulary rows, `status_note`, `first_line_owner`, `compliance_contact`, `owner_team` (the `team` list row `c8-vocab-scales-reasons` created), `process`, `system`, `evidence_location`, `next_review_date`, `version`, `updated_at`. `UNIQUE (tenant, obligation)` and `UNIQUE (tenant_id, id)` for the composite keys f03-T53 needs.
- **`TenantObligationScope`**: `tenant_obligation`, `org_unit`, `product`, `applicability`, `applicability_reason`, `applicability_decided_at`, `compliance_status`, `status_note`, `owner`, `next_review_date`, `version`. `UNIQUE NULLS NOT DISTINCT (tenant_obligation, org_unit, product)` and a check that one of the two is set.
- **`ApplicabilityRequest`**: `tenant_obligation`, `proposed_applicability`, `reason`, `requested_by`, `requested_at`, `status`, `decided_by`, `decided_at`, `decision_note`, with the four-eyes CHECK `decided_by <> requested_by` and a one-pending unique index. f03-T67 widens the index to the scope row and f03-T68 to the unit.

Also here, because nothing else may do it:
- **`ensure_register_entry()`** in `register/logic.py`: the one writer that creates a register entry on its first write, with its own `register.entry_created` audit event in the same transaction.
- **`applicability_request` joins `FOUR_EYES_TABLES`** in `apps/shared/tests_four_eyes.py`. The guard demands every four-eyes table be listed, so adding it later would leave the guard red for waves.
- **The isolation entries for the routes these tables serve** — the register read and write, the applicability list, request, approve, reject and withdraw — join `TENANT_SCOPED_ROUTES` with a factory in `factories.py` that builds the subject on a tenant-private record. `c8-register-api-contract` deliberately left them here, because a factory needs a table.
- Every new table joins the guarded list in `tests_rls.py`.

**Owned paths:**

- `backend/apps/register/models.py`
- `backend/apps/register/migrations/0001_register.py`
- `backend/apps/register/logic.py`
- `backend/apps/register/tests_models.py`
- `backend/apps/shared/tests_rls.py`, `backend/apps/shared/tests_four_eyes.py`, `backend/apps/shared/routes.py`, `backend/apps/shared/factories.py` (the guarded and route lists, appends)
- `backend/apps/register/app.md` (the REG-01 and REG-02 status cells only)

**Done when:**

- `makemigrations --check` is clean; `migrate_from_zero` applies and reverses the graph.
- Every table is forced tenant-only in the RLS guard, and a test as `cw_app` proves tenant B sees none of tenant A's rows.
- `applicability_request` is in `FOUR_EYES_TABLES` and the guard is green.
- `ensure_register_entry()` is the only creator, proved by an AST guard test over production code, and it writes one audit event.
- `UNIQUE (tenant_id, id)` exists on `tenant_obligation`.
- Every register and applicability route is in `TENANT_SCOPED_ROUTES` with a factory, and `tests_tenant_isolation` is green with them.
- `Meta.ordering` is set on every model something will `.first()`.
- No route, no screen, no business rule beyond the entry creator.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Two zones: every register table is tenant-zone, carries `tenant_id` and is under forced row-level security.
- Four eyes by check constraint on applicability.
- "Applies" and "we comply" stay separate columns; no column derives from the other.
- Statuses are rows, not enums. Kinds in code are kinds only.
- Audit and outbox in the same transaction as every write, through `record()`.

### c8-register-models-gaps-history: gaps, assessments, interpretations and links

**Requirements:** REG-03, REG-04, REG-05  
**Scenarios:** contributes to REG-S5 to REG-S8; none un-skipped  
**Depends on:** c8-register-models-core

The second half of the register migration, in its own migration on `mig:register` straight after the first:
- **`ComplianceAssessment`**: the append-only history of every status assessment, with `method`, `status`, `risk_rating`, `likelihood`, `impact`, `rationale`, `next_review_date` and its scope row. It joins the append-only tables and their trigger.
- **`Gap`**: `tenant_obligation`, `org_unit`, `title`, `description`, `severity`, `source`, `status`, `identified_by`, `identified_at`, `owner`, `owner_team`, `target_date`, `remediation`, `acceptance_reason`, `accepted_by`, `closed_by`, `closed_at`, `version`, with the CHECKs `status <> risk_accepted OR (acceptance_reason AND accepted_by)` and `accepted_by <> identified_by`.
- **`Interpretation`**: `tenant_obligation`, `version_no`, `body`, `author`, `status`, `created_at`, unique per `(tenant_obligation, version_no)`.
- **`InternalLink`**: `tenant_obligation`, `internal_item`, `kind`, `label`, `url`, `external_ref`, `created_by`, `created_at`, with a composite key to `internal_item` so another tenant's item cannot be linked.
- **`gap` joins `FOUR_EYES_TABLES`**, for the same reason `applicability_request` did.
- The gap, assessment, interpretation and internal-link routes join `TENANT_SCOPED_ROUTES` with their factories.
- Every new table joins the guarded list in `tests_rls.py`.

**Owned paths:**

- `backend/apps/register/models.py`
- `backend/apps/register/migrations/0002_gaps_history_links.py`
- `backend/apps/register/tests_models.py`
- `backend/apps/shared/tests_rls.py`, `backend/apps/shared/tests_four_eyes.py`, `backend/apps/shared/routes.py`, `backend/apps/shared/factories.py` (appends)
- `backend/apps/register/app.md` (the REG-03, REG-04 and REG-05 status cells only)

**Done when:**

- `makemigrations --check` is clean; `migrate_from_zero` applies and reverses the whole graph, both register migrations included.
- Every table is forced tenant-only in the RLS guard, with a `cw_app` test per table.
- `gap` is in `FOUR_EYES_TABLES` and the guard is green.
- `compliance_assessment` is append-only: an UPDATE and a DELETE are refused by the trigger, tested as `cw_app`, including with `cw.maintenance` set.
- The check constraints refuse a risk-accepted gap with no reason and no approver, and an approver who is the identifier, tested at the database.
- Every gap, assessment, interpretation and link route is in `TENANT_SCOPED_ROUTES` with a factory, and `tests_tenant_isolation` is green.
- `Meta.ordering` is set on every model something will `.first()`.
- No route, no screen and no business rule.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing overwritten: assessments are an append-only ledger with a trigger; a status is superseded, never deleted.
- Four eyes by check constraint on risk acceptance.
- A composite key keeps another tenant's internal item out of a link.
- Statuses, severities and sources are rows; the accepted gap kind is `risk_accepted`.
- Audit and outbox in the same transaction as every write, through `record()`.

### c8-card-people-access: out of office and member removal

**Requirements:** TEN-04, TEN-05  
**Scenarios:** contributes to TEN-S4, TEN-S5 and TEN-S9  
**Depends on:** f03-T60, p03-consolidation

Draw the two people cards. The support-access cards are `c8-card-support-access`', so nothing here waits on anything support access waits on:
- **`design/screens/me-out-of-office.html`** (new): the window, the delegate picker, what the delegate may do and what they may not, and the note that they need the approve permission themself.
- **The removal and reassignment dialog** on `design/screens/admin-members.html`: what the person owns by kind with a count, a target owner per kind, "Takes part in N items", their teams, and the statement that nothing changes until the admin confirms.

**Owned paths:**

- `design/screens/me-out-of-office.html`
- `design/screens/admin-members.html` (the removal dialog only; f03-T60 owns the rest and merges first)
- `design/README.md` (the card rows only)

**Done when:**

- Each card renders in both themes at phone and desktop width with no new pill slot and no new tone.
- The removal dialog shows the counts before the confirm, and no destructive action is reachable without it.
- The f03-T60 sections of `admin-members.html` are untouched.

**Gates:**

- Read the cards against `design/system/` and the prototype.
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- Six pill tones only. Typography roles only.
- Screen copy says what the user is doing; no requirement IDs.

### c8-reg-status: compliance status on the register entry

**Requirements:** REG-02  
**Scenarios:** REG-S11 un-skipped; contributes to REG-S3 and REG-S4  
**Depends on:** c8-register-models-core, c8-register-api-contract

Build `backend/apps/register/status_logic.py` and replace the `PATCH`/`GET /obligations/{id}/register` stubs:
- Read the entry for an obligation, creating nothing. An obligation with no entry reads as the defaults, with `version` 0.
- Write status, status note, risk, first-line owner, compliance contact, process, system, evidence location and next review, through `ensure_register_entry()` and `record()`, under `register.edit`.
- **The `not_assessed OR applies` rule** lives here, with a regression test: a status other than the `not_assessed` row while applicability is not `applies` answers 409. The database CHECK cannot express it once the status is a vocabulary row, and the default above says so.
- `If-Match` is required; a mismatched version answers 409 `stale_write` and merges nothing (REG-S11).
- An owner or contact who is not an active member answers 422 `unknown_member`; a status or risk key that is not an active row of the tenant's list answers 422 `unknown_key` with the valid keys.
- Write one `ComplianceAssessment` row per status change, with the rationale, so REG-S7's history has rows from the first write.

**Owned paths:**

- `backend/apps/register/status_logic.py`
- `backend/apps/register/tests_status.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S11 block only)
- `backend/apps/register/app.md` (the REG-02 status cell)

**Done when:**

- `test_reg_s11` is un-skipped and green: the first save wins, the version becomes 4, the second answers 409 `stale_write` and nothing is merged.
- A status set while applicability is not `applies` answers 409, with a test per applicability value.
- Every write has one audit row with before and after values, and one assessment row.
- `PATCH` and `GET` stay under `API_BUDGET_MS` on the seeded register, with an asserted query count.
- Tenant B receives 404 for tenant A's entry.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- "Applies" and "we comply" are separate facts; this route never writes applicability.
- `If-Match` on every versioned record; `stale_write` is a 409 with a `code`.
- Store and compare keys, never labels.
- Every write through `record()`; audit and outbox in the same transaction.
- Tenant content never reaches a log or Sentry.

### c8-e2e-seed-register: the register's seeded world

**Requirements:** REG-01, REG-02, REG-03, REG-05, TEN-02, TEN-03  
**Scenarios:** feeds REG-S1 to REG-S8 and TEN-S2 to TEN-S6  
**Depends on:** c8-register-models-gaps-history, c8-tenants-contract, c8-vocab-scales-reasons

Extend `seed_e2e`, never mock:
- Tenant A gets the org units "Example Bank AB", "Example Fonder AB" and "Example Liv Försäkring AB" under a group, with their licences and two products with scope terms. The teams "Retail compliance", "Legal" and "Cards" are rows of the `team` tenant list with their labels in en and sv, seeded the way the other tenant lists are.
- Register entries over the seeded obligations: one applying and compliant, one applying with a gap, one not applying with its earlier status kept, one under assessment with a pending applicability request, and one spanning two legal entities with different statuses.
- One gap per severity, one open risk-acceptance request, two internal items with their links, and an interpretation with two earlier assessments.
- Tenant B gets its own small register, so every isolation journey has something to be refused from.
- One login per negative case that the register journeys need: an owner with `register.edit` and `gaps.edit` but not `applicability.approve`, an approver with `applicability.approve` and `risk.accept.approve`, and a reader with `register.read` only.
- **A platform admin login with `support_access.grant`**, and a tenant admin with `security.manage`, so TEN-S6 can be walked end to end: the platform person requests, the bank admin approves, the platform person enters. No grant is seeded live; the journey creates it, because the window and the revoke are what the scenario is about.
- Dates anchor to the tenant-local date plus a fixed wall time; nothing derives from today.

Add each new login to `e2e_logins.py` and `frontend/tests/e2e/support/passkeys.ts` as one entry, and each new table to `tests_seed_integrity.py`.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (this package's seed calls only, an append ledger)
- `backend/apps/shared/e2e_logins.py`, `backend/apps/shared/e2e_passkeys.py` (appends)
- `frontend/tests/e2e/support/passkeys.ts` (the LOGINS map, an append)
- `backend/apps/shared/tests_seed_integrity.py` (an append)

**Done when:**

- `seed_e2e` is idempotent: running it twice changes nothing, proved by a test.
- Every seeded row is deterministic and realistic, taken from the prototype's data, and every date is anchored.
- The `team` rows carry labels in en and sv and are reachable through `GET /vocab/team`, with a test.
- The seed integrity guard covers every new table.
- The existing journeys stay green and no login is duplicated.
- No API is mocked and no token is injected anywhere.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared apps.register apps.tenants --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`
- `cd frontend && npm run test:e2e -- --grep @smoke`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Extend `seed_e2e`, never mock. Two tenants, one login per system role, one per negative case.
- Clocks anchor to the tenant-local date plus a fixed wall time.
- The seed writes tenant rows only; the library fence is untouched.
- Teardown restores seeded data on failure too.

### c8-reg-applicability: a request a second person approves

**Requirements:** REG-01  
**Scenarios:** REG-S1 `@integration` and REG-S2 un-skipped  
**Depends on:** c8-register-models-core, c8-register-api-contract, f03-T48

f03-T48 (chunk 6) is in the depends-on because it creates `QueueCounts` on `GET /me`; neither the counts nor their schema exist on `main`, so the queue count below has nothing to extend without it. Both hold `idapi`, so they run one after the other anyway.

Build `backend/apps/register/applicability.py` and replace the four stubs:
- **Request.** Under `applicability.request`, store the proposed applicability and a reason on a pending `ApplicabilityRequest`, through `ensure_register_entry()`. The entry keeps its current applicability and reads as "Waiting for approval". A second pending request for the same subject answers 409 `request_pending`; a request that changes nothing answers 409.
- **Approve.** Under `applicability.approve` with `@requires_step_up`, apply the requested value, its reason and its decision time in one transaction, with one `record()` carrying both people and the step-up assertion id. A request the caller filed answers 409 `four_eyes_violation` and changes nothing, before any write.
- **Reject.** Under `applicability.approve`, with a decision note, no step-up (playbook 4.2 and the chunk 2 precedent).
- **Withdraw.** `POST /applicability-requests/{id}/withdraw`, which `c8-register-api-contract` declares under `applicability.request`: the requester may withdraw their own pending request, anyone else's answers 403, and a pending request is never edited (D-44). Without the route in the contract this package would have had to write `api.py`, which rule 3 forbids.
- **List.** `GET /applicability-requests` filtered by status and obligation, paginated (default 20, max 100).
- **The queue count.** Add `applicability` to `QueueCounts` on `GET /me`, beside `signoffs`, counting the requests this person may decide and did not file (MY_WORK_AND_MARKETS §3.3). `QueueCounts` is f03-T48's, not this package's: it does not exist on `main`, so f03-T48 is in the depends-on above. This takes the `idapi` key, so it runs after `c8-tenants-api-contract` and f03-T48 and before f03-T51.
- Applying does **not** touch the compliance status: REG-S4's "nothing was deleted" is a property of this code.

**Owned paths:**

- `backend/apps/register/applicability.py`
- `backend/apps/register/tests_applicability.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S1 and REG-S2 blocks only)
- `backend/apps/identity/me_logic.py`, `backend/apps/identity/schemas.py` (the `applicability` queue count only)
- `backend/apps/register/app.md` (the REG-01 status cell)

**Done when:**

- `test_reg_s1` and `test_reg_s2` are un-skipped and green.
- The four-eyes refusal answers 409 `four_eyes_violation` and writes nothing, proved by a test that counts rows before and after.
- An approval without a fresh step-up answers `step_up_required`, and the audit row of an approval carries the assertion id.
- A concurrency test shows exactly one decision lands on a race and the other answers 409.
- The compliance status and the gaps of an obligation turned to "does not apply" are unchanged and still readable.
- `GET /me` returns the new count on f03-T48's `QueueCounts`, filtered to what the caller may decide, and `contract_drift.py` passes with its pending line.
- Withdrawing a pending request leaves the entry's applicability and its compliance status untouched, and anyone but the requester is refused 403, each with a test.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Four eyes, enforced by the check constraint and checked before any write, with a passkey step-up on the approval.
- "Applies" and "we comply" are separate facts.
- Every write through `record()`, audit and outbox in the same transaction, carrying the assertion id.
- Nothing overwritten: a decided request keeps its reason, its decider and its time.
- Pagination: default 20, max 100.

### c8-reg-gaps: a gap has an owner, a severity, a target date and a plan

**Requirements:** REG-03  
**Scenarios:** REG-S5 `@integration` un-skipped  
**Depends on:** c8-register-models-gaps-history, c8-register-api-contract, c8-vocab-scales-reasons

Build `backend/apps/register/gaps.py` and replace the gap stubs:
- Record a gap on a register entry, optionally on one legal entity, with a title, a description, a severity row, a source row, an owner or an owner team, a target date and a remediation plan, under `gaps.edit` through `ensure_register_entry()`.
- Amend it with `If-Match`; move it from `open` to `remediating` to `closed`, each a row of the tenant's `gap_status` list, each audited.
- `GET /gaps` across the register with filters for status, severity, owner, legal entity and target date, paginated, ordered by target date then id.
- A severity, source or status key that is not an active row answers 422 `unknown_key`; an owner who is not an active member answers 422 `unknown_member`.
- A gap on an obligation that does not apply answers 409, because a gap is a fact about how we comply.
- The write routes are gated on `gaps.edit`, the reads on `register.read`, as `c8-register-api-contract` declares. A test proves a principal holding `gaps.edit` and `register.read` alone can record and amend a gap.
- Risk acceptance is **not** built here: `c8-reg-risk-acceptance` adds it on top, and the stub stays until then.

**Owned paths:**

- `backend/apps/register/gaps.py`
- `backend/apps/register/tests_gaps.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S5 block only)
- `backend/apps/register/app.md` (the REG-03 status cell, set to `in_progress`)

**Done when:**

- `test_reg_s5` is un-skipped and green up to the roadmap line, which `c8-home-register-feeds` makes true; say so in `app.md`.
- Each status, severity and source is stored as a key and returned as `{key, kind, label}`.
- `GET /gaps` stays under `API_BUDGET_MS` on the seeded register, with an asserted query count that does not grow with the number of gaps.
- Every write has one audit row with before and after values.
- Tenant B receives 404 for tenant A's gap, by id.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- A gap can never hide behind an applicability flag.
- Statuses, severities and sources are rows; tones come from the kind.
- `If-Match` on every versioned record.
- Pagination: default 20, max 100.
- Every write through `record()`.

### c8-reg-history-interpretation: how we read this rule, and what we said before

**Requirements:** REG-04  
**Scenarios:** REG-S7 `@integration` un-skipped  
**Depends on:** c8-register-models-gaps-history, c8-register-api-contract

Build `backend/apps/register/history.py` and replace its stubs:
- `GET /obligations/{id}/assessments`: the append-only assessment history, newest first, each row with its author, time, method, status, risk, rationale and the scope row it belongs to. Paginated.
- `GET/PUT /obligations/{id}/interpretation`: "How we read this rule". A `PUT` writes a new `Interpretation` version, marks the previous one superseded and leaves it readable. The current one is the highest active version, with its author and date.
- **An interpretation is a version without an approval step** (plan 7.2): `approved_by` stays null and no four-eyes check applies. Say so in `register/app.md` beside REG-S7.
- `If-Match` on the interpretation; a stale write answers 409 `stale_write`.
- Nothing is ever edited in place: an amendment is a new version.

**Owned paths:**

- `backend/apps/register/history.py`
- `backend/apps/register/tests_history.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S7 block only)
- `backend/apps/register/app.md` (the REG-04 status cell and the interpretation note)

**Done when:**

- `test_reg_s7` is un-skipped and green: the current interpretation shows with its author and date, and each earlier assessment is listed unchanged with who and when.
- A second `PUT` writes version 2, supersedes version 1 and leaves it readable.
- An UPDATE or DELETE on an assessment row is refused by the append-only trigger, tested as `cw_app`.
- Both reads stay under `API_BUDGET_MS` with an asserted query count.
- Interpretation text never reaches a log, Sentry, an audit after value or an outbox payload; a test asserts it.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing overwritten: versions with dates, append-only ledgers with a trigger.
- Tenant content never reaches logs, Sentry, analytics or a model endpoint.
- `If-Match` on versioned records.
- Every write through `record()`; the audit row carries ids, never the body.

### c8-reg-internal-links: linked policies, procedures and controls

**Requirements:** REG-05  
**Scenarios:** REG-S8 `@integration` un-skipped  
**Depends on:** c8-register-models-gaps-history, c8-register-api-contract, c8-tenants-contract

Build `backend/apps/register/links.py` and replace its stubs:
- `POST /obligations/{id}/internal-links` under `register.edit`: pick an existing `InternalItem` or create one from the same call with its kind, name, reference, url, owner, org unit, external system and reference, and its last and next review. There is no separate internal-items admin screen in R2; this is the default above, and `register/app.md` records it.
- The link carries its own label and external reference, so an ad hoc link with no item still works.
- `GET /obligations/{id}/internal-links` returns the items with their kind as `{key, kind, label}`, their external references and their urls, shaped so an outside GRC system can read them.
- `DELETE /internal-links/{id}` under `register.edit`, audited; the item survives the link.
- A kind that is not an active row of `link_kind` answers 422 `unknown_key`; an item of another tenant answers 404.
- A duplicate link of the same item to the same obligation answers 409 `already_linked`.

**Owned paths:**

- `backend/apps/register/links.py`
- `backend/apps/register/tests_links.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S8 block only)
- `backend/apps/register/app.md` (the REG-05 status cell and the item-creation note)

**Done when:**

- `test_reg_s8` is un-skipped and green: the policy with `POL-014` and the control with a link kind from the tenant list are both listed with their kind label and external reference.
- Creating an item from the link call writes one item, one link and one audit event each, in one transaction.
- Deleting a link leaves the item, proved by a test.
- Tenant B receives 404 for tenant A's link and item, by id.
- The read stays under `API_BUDGET_MS` with an asserted query count.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.tenants apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Link kinds are rows; the API returns `key` and `kind`.
- Every write through `record()`, audit in the same transaction.
- A composite key keeps an item of another tenant out of a link.
- Tenant content never reaches a log.

### c8-ten-reassignment: removing a member who owns open work

**Requirements:** TEN-05  
**Scenarios:** TEN-S5 `@integration` un-skipped for the register half  
**Depends on:** c8-register-models-gaps-history, c8-tenants-contract, c8-tenants-api-contract

Build `backend/apps/tenants/reassignment.py` and replace its stubs:
- `GET /tenant/members/{id}/open-work` under `members.manage`: what the member owns, grouped by kind, with a count per kind. In chunk 8 the kinds are register entries, entity rows, gaps, duty occurrences and internal items; `c9-actions` adds cases and actions and f03-T64 adds participations and team memberships (plan ruling 10).
- The removal body on `DELETE /tenant/members/{id}` takes a target owner per kind. **The route and its body schema are `c8-tenants-api-contract`'s** (they live in `identity/api.py` and `identity/schemas.py`, under `idapi`); this package builds the function behind them and touches neither file. Nothing changes until the body is sent: a removal with open work and no target answers 422 `reassignment_required` with the counts.
- On confirm, reassign every item and deactivate the member in one transaction, with one audit event per item and one for the removal, and `@requires_step_up`.
- A target owner who is not an active member, or who is the person being removed, answers 422 `unknown_member`.
- A team's ownership is untouched: a team keeps what it owns when one of its members leaves (TEN-S3).
- The open-work read is the same query the My work service will use, so f03-T56 extends it instead of writing a second one (D-23).

**Owned paths:**

- `backend/apps/tenants/reassignment.py`
- `backend/apps/tenants/tests_reassignment.py`
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S5 block only)
- `backend/apps/identity/members_logic.py` (the removal hook only; it holds `members`)
- `backend/apps/tenants/app.md` (the TEN-05 status cell and the chunk 9 note)

**Done when:**

- `test_ten_s5` is un-skipped and green for obligations, entity rows, gaps, duties and internal items, with the case half named in `app.md` as `c9-actions`'.
- Nothing changes before the confirm, proved by a test that counts rows after the preview.
- The confirm writes one audit event per item and one for the removal, all in one transaction; a failure halfway leaves nothing changed.
- A removal without a fresh step-up answers `step_up_required`.
- Team ownership is unchanged after the removal, with a test.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.tenants apps.identity apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*' --include='apps/identity/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Step-up on a removal (playbook 4.2).
- One transaction, one audit event per item; nothing partially applied.
- A person is deactivated, never deleted: nothing is overwritten.
- Ownership survives a person leaving, through teams (TEN-03).
- Permissions, never role names.

### c8-ten-support-grants: the bank decides who comes in, and for how long

**Requirements:** TEN-06  
**Scenarios:** TEN-S6 rewritten; its request, approve, decline and revoke halves un-skipped, the rest named for `c8-support-access-mechanism`  
**Depends on:** c8-tenants-contract, c8-tenants-api-contract

Build `backend/apps/tenants/support_access.py` and the grant workflow that `OWNER_RECOMMENDATIONS.md` item 2 settles, on the chunk 1 `SupportAccess` row. This package is the request and the decision; it makes nothing readable.

- **Extend `SupportAccess`, reusing what is there.** `reason` is the purpose and `approved_by` is the approver, so no `purpose` and no `granted_by` column is added. New columns: `requested_at`, `status` (a tier-one kind: `requested`, `approved`, `declined`, `revoked`, `expired`), `request_expires_at`, `expires_at`, and `approved_step_up_assertion` for the approver's step-up id. `started_at` becomes nullable and is set at approval, because the window starts when the bank says yes; the chunk 1 one-shot recovery rows keep their values and keep working, with a regression test.
- **Request**, from the console, under `support_access.grant` and with no step-up: a purpose, an optional ticket reference and a duration up to `SUPPORT_ACCESS_MAX_HOURS`. One confined function writes the `SupportAccess` row and its tenant audit row and nothing else, and mails the tenant's `security.manage` holders; a test pins that it writes only those two rows. A request nobody decides lapses after `SUPPORT_ACCESS_REQUEST_TTL_HOURS`, evaluated on read, with no job.
- **Approve** under `security.manage` with `@requires_step_up`: the window starts now and ends `duration` later, the approver and the assertion id are stored, and `record()` carries both people. **Decline** and **revoke** need no step-up (playbook 4.2). A revoke sets `ended_at` and takes effect on the platform session's next request.
- **Four eyes at the database.** A CHECK enforces `approved_by <> platform_user_id`. A guard trigger refuses every DELETE, and refuses any change to `tenant`, `platform_user`, `reason`, `ticket_ref`, `access_level` or the duration after insert; only the status, the decision columns and `ended_at` may move. Tested as `cw_app`, including with `cw.maintenance` set.
- **Read-only.** `access_level` is written as `read`; the write level answers 422 `unknown_key`. That leaves the chunk 1 recovery row, which is one-shot and never approved, as the only write-level row there has ever been, and a test asserts it.
- **Two settings**, each with an env override and a banner: `SUPPORT_ACCESS_MAX_HOURS` (default 4, item 2) and `SUPPORT_ACCESS_REQUEST_TTL_HOURS` (default 24; no input sets it, so this is a default and the commit body says so). A request over the maximum answers 422, with a test at the bound.
- **`GET /tenant/support-access`** for any member: the pending requests, the live grant and the past ones, each with its purpose, ticket, window, platform person and approver, and the `support_access.read` audit rows beneath them.
- **No new log table.** Item 2 logs each read as a tenant audit row (`support_access.read`), and the audit ledger is already append-only with its trigger and already reaches the bank's SIEM stream through the outbox. A second ledger would be a second copy of the same facts.
- **The console-list policy.** Add, in this migration, one permissive **SELECT-only** policy on `support_access` matching `platform_user_id = current_setting('app.platform_user_id', true)::uuid`, and append it to `tests_rls.py`'s `OTHER_POLICIES` with its reason. It is inert until `c8-support-access-mechanism` sets that setting; it lives here because `mig:tenants` serializes tenants migrations and this package holds the key. It is a read of one table by the person the row already names, not a bypass: nothing about it lets a session read another tenant's rows.
- **PRD 0.4 and the ADR.** Two permission descriptions change and no permission is added: `support_access.grant` becomes "request support access to a tenant and enter it read-only once a tenant admin approves", and `security.manage` gains "includes approving, declining and revoking support access". Change them in `PRD.md` section 6 and in `permissions.py`'s description map (the `roles` key), and write the ADR for the whole mechanism here, because this is the first support-access package to land.
- **Rewrite TEN-S6** in `tenants/app.md` to item 2's wording — request, 404, approve, reads logged, a write answers 403, revoke gives 401 and then 404 — keeping every half named, and mark in `app.md` which package makes each half green.

**Owned paths:**

- `backend/apps/tenants/support_access.py`
- `backend/apps/tenants/models.py` (the `SupportAccess` columns only)
- `backend/apps/tenants/migrations/0004_support_grants.py`
- `backend/apps/tenants/mail.py` or the existing tenants mail module (the request notice only)
- `backend/apps/tenants/tests_support_access.py`
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S6 block only)
- `backend/apps/shared/permissions.py` (the two descriptions only; it holds `roles`)
- `PRD.md` (the two permission descriptions only), `docs/adr/` (one new ADR)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the two settings, appends)
- `backend/apps/shared/tests_rls.py` (the policy name and its reason in `OTHER_POLICIES`, an append)
- `backend/apps/tenants/app.md` (the TEN-06 status cell and the TEN-S6 rewrite)

**Done when:**

- TEN-S6's request, approve, decline and revoke halves are green; its enter, logged-read, 403 and 401 halves stay skipped with a comment naming `c8-support-access-mechanism`.
- A request grants nothing: a platform read of the tenant before approval answers 404, with a test.
- The CHECK refuses an approver who is the platform user, and the trigger refuses a DELETE and each frozen column, tested at the database as `cw_app`.
- A request past `SUPPORT_ACCESS_REQUEST_TTL_HOURS` reads as lapsed and cannot be approved; a window past `SUPPORT_ACCESS_MAX_HOURS` answers 422.
- The request function writes exactly the grant row and one audit row, proved by counting rows, and mails only the tenant's `security.manage` holders.
- An approval without a fresh step-up answers `step_up_required`, and its audit row carries the assertion id; a decline and a revoke need none.
- `migrate_from_zero` applies and reverses; the chunk 1 recovery rows still work.
- The SELECT-only policy exists, is listed in `OTHER_POLICIES` with its reason, and a test proves it matches nothing while `app.platform_user_id` is unset.
- The commit body names both settings, the ADR and the PRD 0.4 change.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.tenants apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Platform staff have no bypass. A grant is a row the bank approved; it is not yet a capability, and nothing here makes one.
- Four eyes at the database: the approver is never the person asking.
- Step-up on the approval, never on a request, a decline or a revoke (playbook 4.2).
- Nothing overwritten: a declined or revoked grant keeps its purpose, its people and its times, and the trigger refuses the delete.
- Every threshold is a setting with an env override.
- A cloud session stops and reports on any question that would widen what a grant reaches.

### c8-vocab-register-usage: usage counts for the register's lists

**Requirements:** VOC-02, VOC-04, VOC-05, VOC-06  
**Scenarios:** VOC-S3 and VOC-S4 stay green with the new lists  
**Depends on:** c8-register-models-gaps-history, c8-vocab-scales-reasons

Teach the vocabulary screen's usage count about the register:
- Add a counter per new list — `compliance_status`, `risk_rating`, `gap_status`, `link_kind` and the three reason lists — reading the register tables under row-level security.
- Retiring a used value still shows the count before the confirm, keeps the records rendering their label and leaves the pickers and filters without it (VOC-S4).
- Merging two rows re-points every register row in one audited transaction, with the count of records moved (VOC-S5), reusing `taxonomy/repoint.py`; add only the new tables to its map.
- A count is a single query per list, not one per row.

**Owned paths:**

- `backend/apps/taxonomy/registry.py` (the usage entries for the new lists)
- `backend/apps/taxonomy/repoint.py` (the new tables only)
- `backend/apps/taxonomy/tests_vocabulary.py`

**Done when:**

- Every new list reports a usage count, proved by a test per list.
- A retire of a used value shows the count and leaves history readable.
- A merge re-points every register row in one transaction and writes one audit event with both keys and the count; a failure halfway leaves nothing changed.
- The counts are one query per list, with an asserted query count, and the vocabulary screen stays under `API_BUDGET_MS`.
- VOC-S3, VOC-S4, VOC-S5 and VOC-S14 stay green.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.taxonomy apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Keys are immutable; a retire never deletes.
- One audited transaction for a merge.
- Counts respect row-level security; no cross-tenant count.
- No N+1: a count is one query.

### c8-ui-organisation: the organisation admin screen

**Requirements:** TEN-02, ADM-01  
**Scenarios:** contributes to TEN-S2; the journey is `c8-ui-organisation-journey`'s  
**Depends on:** c8-card-organisation, c8-ten-org-api, x-frontend-split

Build the entities, licences and products sections of `/admin/organisation` on the chunk 1 screen, from the card. It stops at a green point with the screen built and unit-tested; `c8-ui-organisation-journey` proves it against the real stack, which is how a 60-minute package becomes two.

- `frontend/src/features/tenant-admin/organisation/` with `api.ts`, `hooks.ts` and `organisation-presentation.ts`, and the screen sections in `frontend/src/components/admin/`.
- The org-unit tree with its kinds, the licence list per legal entity, and the product list with its scope chips.
- Create, amend and deactivate, each behind `vocab.manage`, with the stale-write message on a 409 `stale_write` and the field errors from the problem detail's `code`.
- Every string in the `tenant-admin` message catalogs, en and sv. No string literal in JSX.
- States: empty, loading, error, denied, and the phone width.

**Owned paths:**

- `frontend/src/features/tenant-admin/organisation/**`
- `frontend/src/components/admin/OrganisationScreen.tsx` and its sections
- `frontend/src/messages/tenant-admin/en.json`, `sv.json`

**Done when:**

- The screen matches `admin-organisation.html` in both themes and has every state.
- `check:messages` and `check:copy-drift` are green; the presentation unit tests cover every kind and pill in en and sv.
- A member without `vocab.manage` sees the lists read-only and the write endpoints answer 403, proved by a component test over the permission.
- `features` coverage is at or above its floor and the production build is clean.
- TEN-S2's journey is untouched and still fixme, with a comment naming `c8-ui-organisation-journey`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Pills only through `Pill`, tones from the kind; typography roles only.
- No string literal in JSX; every string in the catalogs.
- Permissions, never role names.
- Measured against `next start`, never `next dev`.

### c8-ui-organisation-journey: TEN-S2 against the real stack

**Requirements:** TEN-02, ADM-01  
**Scenarios:** TEN-S2 `@e2e` un-fixme'd  
**Depends on:** c8-ui-organisation, c8-e2e-seed-register

Un-fixme TEN-S2 and make it green against the real backend on a freshly seeded database and a production Next build. It holds `orgscreen` after `c8-ui-organisation` and hands it to `c8-ui-teams`.

- Sign in through the UI with a passkey from the seeded authenticator; never inject a token or a cookie, never mock an API.
- Walk the entities, licences and products sections: create a legal entity, add a licence, add a product with its scope chips, and read them back.
- The certificate line stays the scenario's last `And`, which f03-T66 makes true; the note in `tenants/app.md` says so and the journey does not weaken it.
- Declare every expected error on the api-guard where it happens.

**Owned paths:**

- `frontend/tests/e2e/tenants.journey.spec.ts` (the TEN-S2 block only)
- `frontend/src/components/admin/OrganisationScreen.tsx` (only if the journey finds a defect; the fix is named in the commit body)

**Done when:**

- TEN-S2 is un-fixme'd and green, signing in through the UI with a passkey.
- No API is mocked and no token is injected; the run fails if the backend is down.
- The journey's clock is anchored to the tenant-local date plus a fixed wall time.
- Teardown restores the seeded data, on failure too.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run build`
- `npm run test:e2e -- --grep "TEN-S2"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Every spec imports `test` from `tests/e2e/support/api-guard`; an expected error is declared where it happens.
- Sign in through the UI with a passkey; never inject a token or a cookie, never mock an API.
- Measured against `next start`, never `next dev`.
- Never quarantine a journey to get green.

### c8-reg-entity-status: status per legal entity, and the worst-of roll-up

**Requirements:** REG-02, REG-01  
**Scenarios:** REG-S3 `@integration` and REG-S4 un-skipped  
**Depends on:** c8-reg-status, c8-tenants-contract

Extend `backend/apps/register/status_logic.py`:
- A scope row per legal entity (and, in the model, per product) with its own applicability, reason, decision time, compliance status, note, owner and next review.
- A scope row is created, through `record()`, in the transaction of the write that needs it. **A read never writes one** — a test proves it, because f03-T67 depends on that rule.
- Which entities an obligation spans comes from the obligation's terms matched against each entity's terms, with **opt-in dimensions left out** (D-36, STANDARDS §3.1); f03-T67 relies on this and must not have to change it.
- The obligation row shows the **worse** of its entity statuses as its pill, by the kind's ordinal, computed in one place with a unit test per combination.
- REG-S4: turning an obligation to "does not apply" leaves every entity row's status, note and gaps untouched and readable in history; turning it back reveals them unchanged.
- `If-Match` per scope row; a stale write answers 409 `stale_write`.

**Owned paths:**

- `backend/apps/register/status_logic.py`
- `backend/apps/register/tests_status.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S3 and REG-S4 blocks only)
- `backend/apps/register/app.md` (the REG-02 status cell)

**Done when:**

- `test_reg_s3` and `test_reg_s4` are un-skipped and green.
- A read of an obligation spanning three entities writes no row, proved by counting rows before and after.
- The span leaves opt-in dimensions out, with a test using a standard term.
- The worst-of roll-up is one function with a test per pair of kinds, and it reads the ordinal, never the label.
- The read stays under `API_BUDGET_MS` with an asserted query count that does not grow with the number of entities.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.tenants apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Reads never write.
- "Applies" and "we comply" stay separate, per entity as well.
- Nothing overwritten: a hidden status stays readable in history.
- Tones from the ordinal, never the label.
- `If-Match` on every versioned record.

### c8-ten-teams: a team can own work

**Requirements:** TEN-03  
**Scenarios:** TEN-S3 un-skipped for the register half  
**Depends on:** c8-vocab-scales-reasons, c8-tenants-contract, c8-tenants-api-contract, c8-reg-status, c8-reg-entity-status

The team rows themselves are a tier-three tenant list `c8-vocab-scales-reasons` created, so create, rename, retire and read are the existing `/vocab/team` routes under `vocab.manage` and this package writes none of them. What is left is membership and ownership. It takes `mig:tenants` after `c8-ten-support-grants`, and it starts after `c8-reg-entity-status` because the owner-team writes it asserts live in `register/status_logic.py`, which that package holds.

- **`TeamMember`**: `(team, user)` in `tenants/models.py`, with a composite key to the taxonomy `team` table and one to `membership`, so the database refuses a team of another tenant and a user who is not a member of this one. Its migration is this package's.
- Build `backend/apps/tenants/teams.py` and replace the two read stubs: `GET /tenant/teams` (the active teams with their labels and member counts) and `GET /tenant/teams/{id}/members`. The membership write routes are f03-T51's; this package exposes only the reads the pickers and the removal preview need.
- **A team can own anything a person can own.** `tenant_obligation.owner_team` and the gap and duty owner fields already accept a team, because `c8-reg-status`, `c8-reg-entity-status`, `c8-reg-gaps` and `c8-reg-duty-occurrences` each accept one in their own module (rule 3 keeps one module to one package). This package proves the behaviour end to end and owns the scenario.
- Removing a person from a team, or from the tenant, leaves the team's ownership intact and needs no reassignment (TEN-S3).
- A team of another tenant answers 422 `unknown_key`; a retired team is not offered but still renders on the records that carry it.

**Owned paths:**

- `backend/apps/tenants/teams.py`
- `backend/apps/tenants/models.py` (the `TeamMember` model only) and `backend/apps/tenants/migrations/0005_team_member.py`; it holds `mig:tenants`
- `backend/apps/tenants/tests_teams.py`
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S3 block only)
- `backend/apps/shared/tests_rls.py` (the `team_member` table, an append)
- `backend/apps/tenants/app.md` (the TEN-03 status cell and the chunk 9 note)

**Done when:**

- `test_ten_s3` is un-skipped and green for the obligation half; its case half is named in `app.md` as `c9-triage`'s (plan ruling 10).
- An obligation owned by a team still lists the team after one of its members is removed from the tenant, and the removal preview asks for nothing.
- `GET /vocab/team` returns the active teams with their keys, unchanged by this package, and a retired team still renders on the records that carry it.
- A cross-tenant team and a non-member user are both refused by the database as well as by the logic, each with a test.
- `makemigrations --check` is clean and `migrate_from_zero` applies and reverses; `team_member` is forced tenant-only in the RLS guard.
- Every write has one audit row.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.tenants apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Ownership survives a person leaving.
- Teams are rows, not code; `is_lead` is not built (D-21).
- Composite keys keep another tenant's team, and a stranger, out of a membership.
- Every write through `record()`.

### c8-reg-risk-acceptance: accepting a risk needs a second person

**Requirements:** REG-03  
**Scenarios:** REG-S6 `@integration` un-skipped  
**Depends on:** c8-reg-gaps

Extend `backend/apps/register/gaps.py` with risk acceptance and replace its two stubs:
- `POST /gaps/{id}/accept-risk` under `gaps.edit`: a reason key from the tenant's risk-acceptance list and an optional note. The gap reads "Waiting for approval" and its status does not move.
- `POST /gaps/{id}/accept-risk/approve` under `risk.accept.approve` with `@requires_step_up`: a second person moves the gap to the `risk_accepted` row, storing the reason, the approver and the time, with one `record()` carrying both people and the assertion id.
- The person who identified the gap cannot approve their own acceptance: 409 `four_eyes_violation`, before any write, backed by the `accepted_by <> identified_by` CHECK.
- A reason key that is not an active row answers 422 `unknown_key` with the valid keys.
- An accepted gap can be reopened under `gaps.edit`, which clears the acceptance and is audited; the earlier acceptance stays readable in the audit log.

**Owned paths:**

- `backend/apps/register/gaps.py`
- `backend/apps/register/tests_gaps.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S6 block only)
- `backend/apps/register/app.md` (the REG-03 status cell, set to `built`)

**Done when:**

- `test_reg_s6` is un-skipped and green, including the 409 `four_eyes_violation` for the identifier.
- An approval without a fresh step-up answers `step_up_required`, and the audit row carries the assertion id.
- The check constraint refuses an accepted row without a reason and an approver, tested at the database.
- A race test shows exactly one acceptance lands.
- The accepted pill is `information`, from the kind.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Four eyes by check constraint, with a passkey step-up on the approval.
- Reasons are rows; the API returns `key` and `kind`.
- Every write through `record()`, carrying the assertion id.
- Nothing overwritten: reopening keeps the earlier acceptance in the audit log.

### c8-ui-applicability: does it apply to us

**Requirements:** REG-01  
**Scenarios:** REG-S1 `@e2e` un-fixme'd  
**Depends on:** c8-card-obligation-register, c8-reg-applicability, c8-reg-status, c3-fe-obligation-versions, c8-e2e-seed-register

Build the register feature's foundation and its first panel:
- `frontend/src/features/register/` with `api.ts` and `hooks.ts`, and **`register-presentation.ts`**, which is **not** a new module: `frontend/src/features/register/gap-presentation.ts` and its test are already on `main`, so this package renames them in one move (`git mv`, so the history follows) and extends the renamed module with the presentation functions this chunk needs — applicability, compliance status and risk — beside the gap functions that are already there. Five later packages build on it. Writing a second module would give the chunk two tone maps, which the plan's own invariant forbids.
- **Reuse the tone entries that exist.** `complianceTone`, `gapTone`, `severityTone` and `applicabilityTone` are already in `frontend/src/features/shared/tone-by-kind.ts`, and `GapKind` there already spells the accepted state `risk_accepted`, which is why `c8-vocab-scales-reasons` uses that key. The **only** tone entry chunk 8 appends is `riskTone` for `risk_rating`'s four kinds (`low`, `medium`, `high`, `critical`), which has no map today; `severityTone` has three kinds and is the gap's, not the risk rating's. No later package appends another.
- **Mount the panel.** This package holds `obpage` while it adds the panel to the obligation page screen, so the panel is live the moment it merges and nobody inherits an unmounted component. Each later panel package does the same, one at a time, in the `regfe` chain's order.
- The "Does it apply to us" panel on the obligation page: the current value, the reason, who decided and when, "Waiting for approval" while a request is pending, the request form behind `applicability.request`, and Approve and Reject behind `applicability.approve` with the passkey step-up prompt.
- The four-eyes refusal renders from the `code` `four_eyes_violation`, never from the detail text.
- Every string in the `register` catalogs, en and sv.

**Owned paths:**

- `frontend/src/features/register/**` (including the rename of `gap-presentation.ts` and its test to `register-presentation.ts`)
- `frontend/src/features/shared/tone-by-kind.ts` (`riskTone` only, an append)
- `frontend/src/components/inventory/ObligationRegisterPanel.tsx`
- the obligation page screen component (it holds `obpage`; the mount only)
- `frontend/src/messages/register/en.json`, `sv.json`
- `frontend/tests/e2e/register.journey.spec.ts` (the REG-S1 block only)

**Done when:**

- REG-S1 is un-fixme'd and green against the real stack: the owner requests, the page still shows "Applies" with "Waiting for approval", the approver signs the step-up with a passkey and the value and reason change.
- `register-presentation.ts` has a unit test per kind and per pill in en and sv, the gap tests that came with `gap-presentation.ts` still pass unchanged, and no tone is chosen by a literal.
- `tone-by-kind.ts` gained `riskTone` and nothing else, asserted by reading the diff; no existing map changed.
- The panel is mounted on the obligation page and visible in the journey, not only exported.
- The requester's own Approve answers 409 and the page renders the four-eyes message from the `code`, with the error declared on the api-guard.
- `check:messages` and `check:copy-drift` are green; `features` coverage is at or above its floor.
- The panel matches `tenant-obligation.html` in both themes and has every state.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "REG-S1"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Six pill tones, chosen by slot or kind, never by a person; pills only through `Pill`.
- The client branches on `code`, never on `detail`.
- No string literal in JSX; typography roles only.
- Sign in through the UI with a passkey; no injected token, no mocked API.
- A step-up prompt where playbook 4.2 requires it.

### c8-ui-out-of-office: away, with a delegate

**Requirements:** TEN-04  
**Scenarios:** TEN-S4 `@e2e` un-fixme'd, reworded  
**Depends on:** c8-card-people-access, c8-ten-out-of-office, x-frontend-split

Build the out-of-office screen from `me-out-of-office.html`:
- The window with its dates in the tenant's timezone, the delegate picker over the tenant's members, and the line saying what a delegate may do and that they need the approve permission themself.
- End it early; a second open window is refused and the message comes from the `code` `already_delegated`.
- The delegate's own view, showing what has been routed to them.
- Every string in the `me` catalogs, en and sv.

**Owned paths:**

- `frontend/src/features/me/out-of-office/**`
- `frontend/src/app/(tenant)/me/out-of-office/page.tsx`
- `frontend/src/shared/navigation/registry.ts` (one entry, an append)
- `frontend/src/messages/me/en.json`, `sv.json`
- `frontend/tests/e2e/tenants.journey.spec.ts` (the TEN-S4 block only)

**Done when:**

- TEN-S4 is un-fixme'd and green in its reworded form: the delegate approves an applicability request inside the window and cannot outside it.
- Dates render in the tenant's timezone on every screen, with the journey's clock anchored.
- The navigation snapshot baselines are regenerated by the main agent after the merge, and the registry test (at most four ranked destinations) passes.
- `check:messages` is green and the screen has every state.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "TEN-S4"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Clocks anchor to the tenant-local date plus a fixed wall time.
- A delegation grants no permission, and the screen says so.
- No string literal in JSX; every string in the catalogs.
- No injected token, no mocked API.

### c8-ui-teams: teams on the organisation screen

**Requirements:** TEN-03, ADM-01  
**Scenarios:** extends the TEN-S2 journey; TEN-S8's journey is f03-T51's  
**Depends on:** c8-card-organisation, c8-ten-teams, c8-ui-organisation-journey

Add the teams section to `/admin/organisation`:
- The team list with its name, email and member count. Create, rename and retire go through the tenant-list routes behind `vocab.manage`, because a team is a tier-three list; this section is a view onto that list, not a second editor.
- The team picker component every owner field will use, reading `GET /vocab/team`, with the retired rows rendered but not offered. `c8-ui-where-we-stand` already reads that route inline; this package lifts it into the shared picker and that panel uses it.
- The department column is left as the card's empty slot; f03-T51 fills it.
- Every string in the `tenant-admin` catalogs.

**Owned paths:**

- `frontend/src/features/tenant-admin/organisation/teams.ts` and its tests
- `frontend/src/components/admin/TeamsSection.tsx`
- `frontend/src/messages/tenant-admin/en.json`, `sv.json`
- `frontend/tests/e2e/tenants.journey.spec.ts` (the TEN-S2 block only, extended)

**Done when:**

- The TEN-S2 journey covers the teams section and stays green.
- The team picker has unit tests for the retired, empty and denied states in en and sv.
- A member without `vocab.manage` sees the list read-only.
- `check:messages` is green; `features` coverage is at or above its floor.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "TEN-S2"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Teams are rows; the screen shows labels and sends keys.
- No string literal in JSX; typography roles only.
- Permissions, never role names.

### c8-ui-member-removal: removing a member who owns open work

**Requirements:** TEN-05, ADM-01  
**Scenarios:** TEN-S5 `@e2e` un-fixme'd  
**Depends on:** c8-card-people-access, c8-ten-reassignment, c8-e2e-seed-register, x-frontend-split

Build the removal dialog on the member detail screen:
- What the member owns by kind with its count, a target owner per kind (a person or a team), and the statement that nothing changes until the admin confirms.
- The confirm with its passkey step-up, then the resulting state.
- A removal attempted without a target renders the `reassignment_required` message from the `code` and the counts from the body.
- The "Takes part in N items" and teams lines are the card's empty slots; f03-T64 fills them.

**Owned paths:**

- `frontend/src/features/tenant-admin/members/removal.ts` and its tests
- `frontend/src/components/admin/MemberDetailScreen.tsx` (the removal dialog only; it holds `members`)
- `frontend/src/messages/tenant-admin/en.json`, `sv.json`
- `frontend/tests/e2e/tenants.journey.spec.ts` (the TEN-S5 block only)

**Done when:**

- TEN-S5 is un-fixme'd and green for the register half: the counts appear, nothing changes before the confirm, and after it every item is reassigned and the member removed.
- The step-up prompt appears on the confirm and the journey signs it with the virtual authenticator.
- The 422 is declared on the api-guard where it happens.
- `check:messages` is green and the dialog has every state.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "TEN-S5"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing changes before the confirm, and the screen says so.
- Step-up where playbook 4.2 requires it.
- The client branches on `code`.
- No mocked API; backend down means the test fails.

### c8-reg-inventory-overlay-api: the register overlay on the inventory

**Requirements:** REG-01, REG-02, INV-03  
**Scenarios:** INV-S3 and INV-S4 stay green with the overlay; FP-S4 unchanged  
**Depends on:** c3-provision-read, c8-reg-entity-status, c8-reg-applicability, c5-watch-feed-read

Build `backend/apps/register/overlay.py` and add the overlay to the library reads:
- `GET /obligations` and the obligation detail gain the tenant's applicability, the compliance pill with its kind, the first-line owner or owner team, a pending-approval marker and the open change count, for the caller's tenant only.
- Filters: applicability, compliance status, owner and "has a pending request", on top of the existing regime, `q` and `outsideFootprint`.
- The overlay is one joined query per page, never one query per obligation, with an asserted query count. It reads through row-level security and returns nothing for a tenant with no entry.
- It takes the `libread` key, so it cannot run beside a chunk 3 read package or f03-T36. The single scope rule in `library/reading.py` is extended, never duplicated.
- An obligation outside the regulatory scope keeps its overlay when the caller asked for `outsideFootprint`; the scope hides rows, it does not hide a tenant's own judgement about a row it can see.

**Owned paths:**

- `backend/apps/register/overlay.py`
- `backend/apps/library/reading.py`, `backend/apps/library/schemas.py` (the overlay fields only; it holds `libread`)
- `backend/apps/register/tests_overlay.py`
- `backend/apps/library/tests_reading.py`

**Done when:**

- The inventory read returns the overlay for the caller's tenant and nothing for another's, with a test as tenant B.
- The query count is asserted and does not grow with the page size; `GET /obligations` stays under `API_BUDGET_MS` on the seeded library.
- INV-S3, INV-S4 and FP-S4 stay green and the chunk 3 reads are unchanged in shape.
- `contract_drift.py` passes with the new response fields.
- No second scope rule exists: a test asserts the one function is the only caller of `in_footprint`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.register apps.library apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*' --include='apps/library/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- The library read stays a library read: the overlay is a join, and no library row is written.
- One scope rule, in `library/reading.py`.
- No N+1; the budget is measured.
- Tenant content never leaves the tenant's session.

### c8-recurring-duty-model: the recurring duty row, behind the library fence

**Requirements:** REG-07, PRO-01  
**Scenarios:** contributes to REG-S10; none un-skipped  
**Depends on:** c3-close, c4-library-updates, c5-library-links-provenance

The table and its fence, and nothing else. It changes no dependency and no proposal, so it does not wait for `r1-readiness` and it runs on `prepush.sh --quick`.

- **`RecurringDuty`**, a `LibraryModel` on an obligation: `title`, `recurrence_rule` (an RFC 5545 RRULE, stored as text and validated by `c8-recurring-duty-proposal`), `due_rule_note`, `recipient_authority`, `lead_days`, `status`. No tenant column; it is a public fact about the duty.
- It joins the library fence's watched models, so a write outside `proposals/apply.py` and the seeds is refused at runtime and by the AST guard.
- No agent key scope reaches it, proved by the scope test.

**Owned paths:**

- `backend/apps/library/models.py`, `backend/apps/library/migrations/000X_recurring_duty.py` (it holds `mig:library`)
- `backend/apps/library/tests_models.py`
- `backend/apps/shared/tests_library_fence.py` (the model list, an append; it holds `fence`)

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies and reverses the graph.
- A write to `recurring_duty` outside `apply.py` and the seeds is refused by the library fence, with a test that plants one.
- No API key scope reaches the table, proved by the scope test.
- `Meta.ordering` is set, and the row carries no tenant column, asserted by the library-model guard.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/library/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Proposals are the only door into the library; agents never edit it and no API key scope reaches it.
- A library row is a sourced public fact: no tenant column, no tenant judgement.
- Nothing overwritten.

### c8-recurring-duty-proposal: the door, the rule parser and its cap

**Requirements:** REG-07, PRO-01, VOC-07  
**Scenarios:** contributes to REG-S10; none un-skipped  
**Depends on:** c8-recurring-duty-model, r1-readiness

The proposal kind and the one dependency this chunk adds. It holds `deps`, so it waits for `r1-readiness` under plan rule 11, and it runs `prepush.sh --all`.

- **A proposal kind, `new_recurring_duty`**, with a source per field, applied through `proposals/apply.py` in the same transaction as its audit rows and the re-index hook. Agents never write the table; a library editor decides the proposal in the console queue, which needs no new console code because the queue renders kinds generically.
- **`python-dateutil`** is added as a runtime dependency for RRULE expansion, with one wrapper, `library/recurrence.py`, that expands a rule from a date and refuses anything it cannot parse (422 `invalid_recurrence`). A pin that fails to install is replaced by the nearest working version and the change is reported with its reason.
- A rule that would expand to more than `RECURRENCE_MAX_OCCURRENCES` (a setting with an env override, default 120) in ten years is refused at proposal creation, so a bad rule cannot become a denial of service.

**Owned paths:**

- `backend/apps/library/recurrence.py`
- `backend/apps/proposals/apply.py`, `backend/apps/proposals/logic.py`, `backend/apps/proposals/schemas.py` (the new kind only; it holds `prop` and `apply`)
- `backend/apps/shared/kinds.py` (the proposal kind, an append)
- `backend/pyproject.toml`, `poetry.lock` (it holds `deps`)
- `backend/config/settings.py`, `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (the new setting, appends)
- `backend/apps/library/tests_recurrence.py`, `backend/apps/proposals/tests_create.py`

**Done when:**

- The new kind needs a source per field and is refused without one (422 `source_missing`), at creation and again over the corrected payload at approval.
- Applying the proposal writes the row, its audit rows and the re-index hook in one transaction, and a failure halfway leaves nothing.
- The RRULE wrapper has tests for a daily, monthly, quarterly and yearly rule, for a rule it cannot parse, and for one over the cap.
- The dependency change is the only one in its ship, and `osv-scanner`, `npm audit`, the licence check and Trivy are green.
- The library fence still refuses every writer but `apply.py` and the seeds.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh install && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.library apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/library/*' --include='apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --all` (it changes a dependency and the proposal door)

**Invariants:**

- Proposals are the only door into the library; agents never edit it and no API key scope reaches it.
- A source per changed field, checked at creation and again at approval.
- Audit and outbox rows in the same transaction as the apply.
- Every threshold is a setting with an env override.
- One dependency change per ship.

### c8-ui-where-we-stand: where we stand, per legal entity

**Requirements:** REG-02  
**Scenarios:** contributes to REG-S3 and REG-S4; the journey is `c8-ui-where-we-stand-journey`'s  
**Depends on:** c8-card-obligation-register, c8-reg-entity-status, c8-vocab-scales-reasons, c8-ui-applicability, c8-e2e-seed-register

Build the status panels on the obligation page and mount them. It holds `regfe` and `obpage`.

- **Where we stand**: the compliance pill, the status note, risk, first-line owner, compliance contact and next review, editable behind `register.edit`, with the `stale_write` message rendered from the `code`.
- **How we handle it**: process, system and evidence location.
- **Per legal entity**: one row per scope row with its own pills and fields, and the worst-of roll-up shown on the header with a line naming which entity it came from.
- The owner field takes a person or a team. The team picker reads `GET /vocab/team`, which the tenant-list routes already serve from `c8-vocab-scales-reasons`' list, so this package does not wait for `c8-ten-teams`; `c8-ui-teams` later lifts the picker into a shared component and this panel uses it.
- The compliance and risk pills come from `register-presentation.ts`, extended by `c8-ui-applicability`; no new presentation module and no tone entry.
- Every string in the `register` catalogs.

**Owned paths:**

- `frontend/src/features/register/**` (the status hooks and presentation)
- `frontend/src/components/inventory/ObligationStatusPanel.tsx`
- the obligation page screen component (it holds `obpage`; the mount only)
- `frontend/src/messages/register/en.json`, `sv.json`

**Done when:**

- The panels match `tenant-obligation.html` in both themes and have every state, including a reader's read-only view, proved by component tests.
- A concurrent save renders the stale-write message from the `code` and merges nothing, proved by a unit test over the hook.
- The panels are mounted on the obligation page, not only exported.
- `check:messages` and `check:copy-drift` are green; presentation tests cover every pill in en and sv.
- REG-S3's journey is untouched and still fixme, with a comment naming `c8-ui-where-we-stand-journey`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Pills through `Pill`, tones from the kind; one presentation module per feature.
- The client branches on `code`, never on `detail`.
- No string literal in JSX.
- Measured against `next start`.

### c8-ui-where-we-stand-journey: REG-S3 against the real stack

**Requirements:** REG-02  
**Scenarios:** REG-S3 `@e2e` un-fixme'd; REG-S4's journey half stays with it  
**Depends on:** c8-ui-where-we-stand, c8-e2e-seed-register

Un-fixme REG-S3 and make it green. It holds `regfe` after `c8-ui-where-we-stand`.

- Two entities hold their own status and the header shows the worse of them, read through the UI after a passkey sign-in.
- A concurrent save renders the stale-write message and merges nothing, with the 409 declared on the api-guard where it happens.
- REG-S4's journey half rides with it: an obligation turned to "does not apply" keeps its statuses and shows them again when it is turned back.

**Owned paths:**

- `frontend/tests/e2e/register.journey.spec.ts` (the REG-S3 block only)
- `frontend/src/components/inventory/ObligationStatusPanel.tsx` (only if the journey finds a defect; the fix is named in the commit body)

**Done when:**

- REG-S3 is un-fixme'd and green against the real stack.
- The 409 is declared on the api-guard where it happens, and no other undeclared error of 400 or above occurs.
- The clock is anchored; nothing reads today's date.
- Teardown restores the seeded data, on failure too.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run build`
- `npm run test:e2e -- --grep "REG-S3"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Sign in through the UI with a passkey; no injected token, no mocked API.
- Every spec imports `test` from `tests/e2e/support/api-guard`.
- Measured against `next start`.
- Never quarantine a journey to get green.

### c8-ui-history-interpretation: how we read this rule

**Requirements:** REG-04  
**Scenarios:** REG-S7 `@e2e` un-fixme'd  
**Depends on:** c8-card-obligation-register, c8-reg-history-interpretation, c8-ui-applicability, c8-e2e-seed-register

Build the interpretation and history panels:
- **How we read this rule**: the current interpretation with its author and date, and an editor behind `register.edit` that saves a new version with `If-Match`.
- **History**: each earlier assessment with who, when, the status then and the rationale, paginated, newest first, and each superseded interpretation beneath it.
- Every string in the `register` catalogs.

**Owned paths:**

- `frontend/src/features/register/**` (the history hooks and presentation)
- `frontend/src/components/inventory/ObligationHistoryPanel.tsx`
- the obligation page screen component (it holds `obpage`; the mount only)
- `frontend/src/messages/register/en.json`, `sv.json`
- `frontend/tests/e2e/register.journey.spec.ts` (the REG-S7 block only)

**Done when:**

- REG-S7 is un-fixme'd and green: the current interpretation shows with its author and date and the history lists each earlier assessment unchanged.
- Saving a new version leaves the old one readable on the page.
- The panels match the card in both themes and have every state.
- `check:messages` is green; `features` coverage is at or above its floor.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "REG-S7"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing overwritten: an earlier assessment is never edited on screen.
- Typography roles only; no string literal in JSX.
- No mocked API.

### c8-ui-inventory-overlay: the register on the inventory

**Requirements:** REG-01, REG-02, INV-03  
**Scenarios:** INV-S3 and INV-S4 stay green with the overlay columns  
**Depends on:** c8-reg-inventory-overlay-api, c3-fe-instruments, c8-ui-where-we-stand

Add the overlay to the inventory screen:
- Columns for applicability, the compliance pill, the owner and a "Waiting for approval" marker, rendered by the register presentation functions, not by new ones.
- Filters for applicability, compliance status, owner and pending requests, beside the existing ones, with the filter state in the URL as the screen already does.
- A tenant with no register entry sees the columns empty, never an error.
- Every string in the `library` catalogs, which this package holds through `invscreen`.

**Owned paths:**

- `frontend/src/components/inventory/InventoryScreen.tsx`
- `frontend/src/features/library/inventory-presentation.ts` and its tests
- `frontend/src/messages/library/en.json`, `sv.json`
- `frontend/tests/e2e/library.journey.spec.ts` (the INV-S3 and INV-S4 blocks only, extended)

**Done when:**

- INV-S3 and INV-S4 stay green and cover the new columns and one filter.
- The register presentation functions are reused, not copied, proved by the import graph and a lint rule.
- The screen reaches real data inside the 500 ms budget against `next start`, measured on the seeded library.
- `check:messages` and `check:copy-drift` are green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "INV-S3|INV-S4"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- One presentation function per record type; no second tone map.
- Measured against `next start`, never `next dev`.
- No string literal in JSX.

### c8-reg-duty-occurrences: dated duties in the tenant's calendar

**Requirements:** REG-07  
**Scenarios:** REG-S10 un-skipped, green up to its roadmap line  
**Depends on:** c8-recurring-duty-proposal, c8-register-models-core, c8-register-api-contract

Build `backend/apps/register/duties.py` and the tenant half of REG-07:
- **`DutyOccurrence`**, a tenant row on a recurring duty, a register entry and optionally a legal entity: `due_date`, `status`, `owner`, `completed_at`, `completed_by`, `note`, `version`, unique per `(recurring_duty, tenant, org_unit, due_date)` with nulls not distinct. Its migration holds `mig:register`.
- `GET /obligations/{id}/duties` lists the duties of the obligation with their next occurrence, under `register.read`.
- `POST /duty-occurrences/{id}/complete` under `register.edit`: mark it done and **generate only the next occurrence**, computed from the RRULE in the tenant's timezone. No horizon of rows is written; this is the default above.
- The first occurrence is created when the obligation's applicability is approved, or on the first read of a duty that has none, through one writer, audited.
- A completion that would generate an occurrence already present is idempotent and writes nothing twice.
- Add the table to the RLS guard list.

**Owned paths:**

- `backend/apps/register/duties.py`
- `backend/apps/register/models.py`, `backend/apps/register/migrations/000X_duties.py`
- `backend/apps/register/tests_duties.py`
- `backend/apps/register/tests_scenarios.py` (the REG-S10 block only)
- `backend/apps/shared/tests_rls.py` (an append)
- `backend/apps/register/app.md` (the REG-07 status cell)

**Done when:**

- `test_reg_s10` is un-skipped and green **up to its roadmap line**, which `c8-home-register-feeds` makes true, exactly as REG-S5 is handled: the quarterly duty due 2026-12-31 exists and reads back through `GET /obligations/{id}/duties`, and completing it generates 2027-03-31 in the tenant's timezone. The roadmap step ("the duty appears with 'Our deadline'") is asserted by `c8-home-register-feeds`, which builds that branch a wave later; say so in `register/app.md` beside the scenario rather than weakening the Gherkin, and leave the assertion in place behind a comment naming that package.
- `makemigrations --check` is clean and `migrate_from_zero` applies and reverses.
- Exactly one occurrence is generated per completion, proved by a count, and a repeated completion is idempotent.
- Every date is pinned in the tests; nothing reads today's date.
- The table is forced tenant-only in the RLS guard, tested as `cw_app`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.register apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/register/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- UTC timestamps; legal dates are plain dates with a precision; the tenant's timezone converts them.
- Idempotency on a repeated write.
- Every write through `record()`.
- The recurrence rule is a library fact; the occurrence is the tenant's work. No tenant row is written into the library.

### c8-support-access-mechanism: the support session, and what it reaches

**Requirements:** TEN-06, NFR-01  
**Scenarios:** TEN-S6's enter, logged-read, write-refusal and expiry halves un-skipped  
**Depends on:** c8-ten-support-grants, r1-readiness

**This package changes `apps/shared/authentication.py` and `middleware.py`. It runs in a cloud session with the stop-and-report instruction (plan rule 12): on any question that would widen what a grant reaches, it stops, commits nothing further and reports.**

The design is `OWNER_RECOMMENDATIONS.md` item 2, accepted on 2026-09-19. **A support session reaches a tenant the ordinary way.** There is no new policy on a tenant table, no flag a policy reads, no role with `BYPASSRLS` and no migrator credential anywhere near the API process: the session activates the one granted tenant through `tenancy.activate()`, and every row-level-security policy applies to it exactly as it applies to a member of that bank.

- **The support session.** `user_session` gains `support_access`, a nullable foreign key to the grant, and its existing `tenant` column — null for a platform session — is set to the granted bank, so the session row alone says which tenant to activate. `expires_at` is the window's end. It holds `mig:identity` for that column and `idp` for `identity/session_logic.py`, which mints the session. The support session may refresh and sign out, and refreshing never extends it past the window.
- **Reading the grant with no tenant active.** `POST /console/support-access/{id}/enter`, under `support_access.grant` with `@requires_step_up`, has to check the grant while the caller is still a console session with no tenant. It does that through the **SELECT-only policy on `support_access` keyed on `app.platform_user_id`** that `c8-ten-support-grants` created: this package sets that setting, with `SET LOCAL` for the request's transaction, only for a platform session and only to that session's own user id, cleared in `finally`, in `identity/session_logic.py` and nowhere else, under an AST guard. The caller can therefore read the rows that already name them, and nothing else. `c8-support-access-console-list` then uses the same setting for the console's list.
- **Entering the tenant.** For a request on a support session, the auth layer reads the session under `tenancy.identity_lookup()` as it already does, activates `session.tenant_id` with `tenancy.activate()`, and **then** loads the grant by id under that tenant's own policies — so no read ever crosses a tenant, and the load proves in one step that the grant belongs to the tenant the session claims. If the grant is missing, not `approved`, revoked or past `expires_at`, the request answers **401 `support_access_ended`** and nothing else runs. The check is per request, so a revoke takes effect on the next one with no job and no cache.
- **The support principal.** It holds `library.read`, `watch.read`, `roadmap.read`, `register.read`, `cases.read`, `reports.read` and `audit.read`, and nothing else: no role rows, no platform grants, no search and no Ask, because both are POST and would spend the bank's AI budget.
- **The read-only guard.** One guard in the request path answers **403 `support_read_only`** before any handler runs to every request on a support session whose route is not on an allow-list. The list is `SUPPORT_READ_ROUTES` in `apps/shared/routes.py`: the exact `(method, route template)` pairs a grant reaches, written out one by one, which are the GET reads the seven permissions cover and nothing else. A method rule would not do, because it admits every GET added afterwards; the evidence and export downloads are themselves GETs that are deliberately left off. The guard matches the route template `routes.py` already resolves, never a raw path, so a path id can never smuggle a request onto the list. Anything not on it — a new GET as much as a POST, PATCH, PUT or DELETE — is refused until someone adds it on purpose, in this file, under this package's tests.
- **The log is an audit row.** Every request under a grant writes one `support_access.read` audit row in that tenant, through `record()`, in the request's transaction. It carries the route template and the path ids, the platform person and the grant id — never a query string, never a body and never tenant content.
- **Outside a grant nothing exists.** A platform session with no live grant reading a tenant row answers **404**, which is what it already does: with no tenant activated, the policies return no rows. No code is added for that; a test pins it.
- `cw_app` still cannot bypass row-level security and the boot guard still refuses a role that can; `tests_database_role` and the production guard are unchanged and stay green.

**Guards and tests this package adds, by name:**

- `backend/apps/shared/tests_support_session.py`: the principal's permission set is exactly the seven reads; every request off `SUPPORT_READ_ROUTES`, non-GET and GET alike, answers 403 `support_read_only`; a revoked, declined, expired or missing grant answers 401 `support_access_ended` on the next request; the session cannot refresh past the window.
- **The route sweep**: a test that walks every GET the API registers as a support principal and splits them by the allow-list — a GET on `SUPPORT_READ_ROUTES` answers 2xx or 404, never 403 and never 5xx, so a read the bank's own members can do is never hidden behind the wrong code; **every GET that is not on the list answers 403 `support_read_only`**, so a read nobody approved is never reachable. The proof that the default is refusal is a new GET route planted on the test's own router: the sweep sees it, expects the 403 and gets it with no edit to the guard or the list.
- **The audit test**: one `support_access.read` row per request, in the same transaction, with the route template and no query string, no body and no tenant content; a planted body in the row fails it.
- **The AST guard**: only `identity/session_logic.py` may set `app.platform_user_id` or mint a support session, and only `tenants/support_access.py` may load a grant for one, each with a planted violation in its own test. A test also proves the setting is cleared when the request's block ends. Its precedent is `tenancy.identity_lookup()`, whose callers are restricted the same way and whose tables are pinned in `tests_rls.py`'s `IDENTITY_LOOKUP_TABLES`; chunk 4's problem-report window is **not** a precedent, because `OWNER_RECOMMENDATIONS.md` item 3 replaced that recommendation and it will not be built.
- `tests_rls.py` and `tests_tenant_isolation.py` stay green with no change but the `OTHER_POLICIES` line `c8-ten-support-grants` already appended: this package adds no policy and no guarded table, which is the point.

**Owned paths:**

- `backend/apps/shared/authentication.py`, `backend/apps/shared/middleware.py` (it holds `auth`)
- `backend/apps/shared/routes.py` (the `SUPPORT_READ_ROUTES` allow-list, an append)
- `backend/apps/identity/session_logic.py` (it holds `idp`)
- `backend/apps/identity/models.py`, `backend/apps/identity/migrations/000X_support_session.py` (the `user_session.support_access` column; it holds `mig:identity`)
- `backend/apps/tenants/support_access.py` (the grant check for a support session; `c8-ten-support-grants` merges first and hands the module over)
- `backend/apps/shared/tests_support_session.py` (new)
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S6 block only)

**Done when:**

- TEN-S6's enter, logged-read, write-refusal and expiry halves are green: 404 before the grant, reads and their audit rows during it, a write answering 403 `support_read_only`, and 401 `support_access_ended` after a revoke and again after the window.
- The route sweep passes over every GET: the ones on `SUPPORT_READ_ROUTES` answer 2xx or 404, and a planted new GET route is refused with 403 `support_read_only`, as a planted non-GET one is, without anyone editing the guard.
- The AST guard fails on a planted violation in each of its modules, and `app.platform_user_id` is empty again after the request, proved by reading `current_setting`.
- A platform session reading `support_access` sees only rows naming itself, and a tenant session's read of the table is unchanged, each with a test.
- `migrate_from_zero` applies and reverses the identity migration.
- The whole guard suite is green and `tests_rls.py` is byte-identical: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`.
- The report names every read the support principal can do and every one it deliberately cannot.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --all` (it changes the auth path)

**Invariants:**

- Two zones: no tenant table gains a policy for this, no role gains `BYPASSRLS`, and the app never reads as the schema owner. A support session is a tenant session with seven read permissions and an expiry.
- Platform staff have no bypass: a grant is a narrow, logged, time-boxed read the bank approved, and never a write.
- `cw_app` cannot bypass row-level security, and the app refuses to boot on a role that can.
- Never a 403 where a 404 hides existence; `support_read_only` is a 403 about the route, on a tenant the caller is already inside.
- The audit row is in the same transaction as the read.
- A cloud session stops on an invariant question rather than deciding it.

### c8-support-access-console-list: a platform person sees their own grants

**Requirements:** TEN-06  
**Scenarios:** contributes to TEN-S6  
**Depends on:** c8-ten-support-grants, c8-support-access-mechanism

The console has to list a platform person's own requests and grants across banks, with no tenant active. The machinery is already there: `c8-ten-support-grants` created the SELECT-only policy on `support_access` keyed on `app.platform_user_id`, and `c8-support-access-mechanism` set that setting in `identity/session_logic.py` under its AST guard so `enter` could check a grant. This package only replaces the `GET /console/support-access` stub and proves the read is as narrow as it claims. It takes `idp` after `c8-support-access-mechanism`.

- `GET /console/support-access` returns the caller's own requests and grants: the bank by its organisation name, the purpose, the ticket, the window, the state, and the approval as a time. **No tenant member's name, ever**, and a test asserts the response carries none.
- A second platform person's rows never appear, proved by a test that sets the setting to another id and reads nothing.
- Nothing here reads a tenant's records: the policy is on one table, for SELECT only, and matches only rows that already name the caller.

**Owned paths:**

- `backend/apps/identity/session_logic.py` (only if the console read needs the setting widened, which it should not; it holds `idp`)
- `backend/apps/tenants/support_access.py` (the console read only)
- `backend/apps/tenants/tests_support_access.py` (an append)

**Done when:**

- `GET /console/support-access` lists the caller's own rows and nobody else's, with a test per case, and answers 200 with an empty list for a platform person with none.
- A second platform person's rows never appear, proved by a test that reads as that other person.
- No member name appears in the response, asserted over the whole payload, and the bank is named by its organisation name.
- The read is paginated (default 20, max 100) and stays under `API_BUDGET_MS`.
- `tests_rls` stays green with the policy in `OTHER_POLICIES`, and `session_logic.py` is unchanged.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/*' --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- One table, one verb, one module, one setting, pinned by an AST guard and by `tests_rls`: the same shape as the identity lookup already on `main`.
- Pagination: default 20, max 100.
- No tenant content and no member name on a console screen or in a console response.
- Nothing overwritten; the console reads and never writes a grant.
- A cloud session stops on an invariant question rather than deciding it.

### c8-ui-internal-links: linked internal items

**Requirements:** REG-05  
**Scenarios:** REG-S8 `@e2e` un-fixme'd  
**Depends on:** c8-card-obligation-register, c8-reg-internal-links, c8-ui-applicability, c8-e2e-seed-register

Build the "Linked internal items" panel:
- The list with each item's kind label, name, external reference and outside link.
- The add dialog behind `register.edit`: pick an existing item or enter a new one with its kind, name, reference, url, owner, org unit and next review, in one call.
- Remove a link, with the item surviving.
- The near-duplicate and `already_linked` messages render from their `code`.
- Every string in the `register` catalogs.

**Owned paths:**

- `frontend/src/features/register/**` (the links hooks and presentation)
- `frontend/src/components/inventory/ObligationLinksPanel.tsx`
- the obligation page screen component (it holds `obpage`; the mount only)
- `frontend/src/messages/register/en.json`, `sv.json`
- `frontend/tests/e2e/register.journey.spec.ts` (the REG-S8 block only)

**Done when:**

- REG-S8 is un-fixme'd and green: the policy with `POL-014` and the control with its link kind are both listed with their kind label and external reference.
- Creating an item from the dialog writes one item and one link, checked through the API in the journey by id, never by a count.
- A reader sees the list and no add control.
- `check:messages` is green and the panel has every state.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "REG-S8"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Link kinds are rows; the screen shows labels and sends keys.
- The client branches on `code`.
- No string literal in JSX.
- No mocked API.

### c8-home-register-feeds: the register on Today and the roadmap

**Requirements:** HOM-01, HOM-03, REG-02, REG-03, REG-07  
**Scenarios:** HOM-S1, HOM-S4 and HOM-S6 stay green with register data; it completes REG-S5's and REG-S10's roadmap lines  
**Depends on:** c6-briefing-backend, c6-home-backend, c8-reg-gaps, c8-reg-duty-occurrences, c8-reg-entity-status, c8-reg-applicability, c8-reg-risk-acceptance

Feed the chunk 6 home surfaces from the register:
- **"Where we stand"** on Today: the counts per compliance category and the number of open gaps, per legal entity where they differ, read from its own home endpoint, never from `/reports/*` (plan ruling 20).
- **The roadmap** gains three branches, each of kind `internal`, shown as "Our deadline" with its owner: a gap's target date, a duty occurrence's due date, and a register entry's or scope row's next review. A compliant row's next review is included (HOM-S8 depends on it).
- A branch is left out when its row is closed, accepted, completed or deactivated.
- None of the three enters the calendar feed: the feed carries public facts only, and a test asserts it.
- The counts and the roadmap respect the reader's permissions and the regulatory scope, as FP-03 already requires of the roadmap.
- One query per branch; the query count is asserted and does not grow with the number of rows.

**Owned paths:**

- `backend/apps/home/logic.py`, `backend/apps/home/api.py`, `backend/apps/home/schemas.py` (it holds `homecore`)
- `backend/apps/home/migrations/000X_roadmap_register_branches.py` (the roadmap view)
- `backend/apps/home/tests_scenarios.py`, `backend/apps/home/tests_roadmap.py`

**Done when:**

- HOM-S1, HOM-S4, HOM-S5 and HOM-S6 stay green and now carry register rows.
- A gap target, a duty due date and a next review each appear once on the roadmap with their owner, and each disappears when its row closes.
- REG-S5's and REG-S10's roadmap lines are now asserted: this package turns on the branch each of them reads, extends both scenarios to cover it, and leaves both fully green. Neither scenario is owned here; `c8-reg-gaps` and `c8-reg-duty-occurrences` own them and said in `app.md` that this package finishes them.
- None of the three appears in the calendar feed, with a test per branch.
- Today and the roadmap stay under `API_BUDGET_MS` with asserted query counts.
- `migrate_from_zero` applies and reverses the view change.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.home apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py) as a check only`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- The calendar feed carries public facts only.
- Fan out, never chain; one query per branch.
- Permissions filter rows and counts alike.
- Every threshold is a setting.
- No tenant content in a log.

### c8-ui-support-access: the tenant sees who came in

**Requirements:** TEN-06, ADM-01  
**Scenarios:** TEN-S6 `@e2e` un-fixme'd  
**Depends on:** c8-card-support-access, c8-ten-support-grants, c8-support-access-mechanism, c8-support-access-console-list, c4-console-shell

Build both sides from `c8-card-support-access`' cards, to the design Q1 settles:
- **The bank's Support access panel**: the pending requests, each with the platform person's name and role, the purpose, the ticket and the asked-for window, and Approve behind `security.manage` with its passkey step-up, Decline and, on a live grant, Revoke, neither of which prompts for one; the active grant with its window and its approver; and the history beneath them, read from the `support_access.read` audit rows and paginated, with a link into the audit log.
- **The console screen** on the chunk 4 shell: request a grant for one bank with a purpose, an optional ticket and a duration up to the maximum; the person's own requests and grants with their state; and Enter, with its passkey step-up. The bank is named by its organisation name and never by a member's name, and an approval shows as a time.
- **The read-only banner** a support session carries on every tenant screen, and the copy for 403 `support_read_only` and 401 `support_access_ended`, each rendered from the `code`.
- A read outside a grant renders "Not found", never the data and never a 403.
- Every string in the `tenant-admin` and `console` catalogs.

**Owned paths:**

- `frontend/src/features/tenant-admin/support-access/**`
- `frontend/src/components/admin/SupportAccessScreen.tsx`
- `frontend/src/components/console/ConsoleSupportAccessScreen.tsx`
- `frontend/src/shared/navigation/registry.ts` (two entries, an append)
- `frontend/src/messages/tenant-admin/en.json`, `sv.json`, `frontend/src/messages/console/en.json`, `sv.json`
- `frontend/tests/e2e/tenants.journey.spec.ts` (the TEN-S6 block only)

**Done when:**

- TEN-S6 is un-fixme'd and green end to end in its rewritten form: the platform admin requests, a read answers 404, the bank admin approves with a passkey step-up, the platform person enters and reads, each read leaves a `support_access.read` row naming them and the purpose, a write answers 403, and after Revoke the next request answers 401 and a read answers 404, with the clock anchored.
- The console shows no tenant member's name anywhere, asserted over the rendered page in the journey.
- Decline and Revoke prompt for no step-up, and Approve and Enter both do.
- The 404s are declared on the api-guard where they happen.
- `check:messages` is green and both screens have every state.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "TEN-S6"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Never a 403 where a 404 hides existence; the UI says "Not found".
- No tenant member's name on a console screen.
- Step-up where playbook 4.2 requires it.
- No mocked API; the clock is anchored.

### c8-ui-gaps: the gaps screen

**Requirements:** REG-03  
**Scenarios:** contributes to REG-S5; the journey is `c8-ui-gaps-journey`'s  
**Depends on:** c8-card-gaps, c8-reg-gaps, c8-ui-applicability, c8-e2e-seed-register

Build `/gaps` and the gaps panel on the obligation page. It holds `regfe` and `obpage`.

- The list with its filters, each row showing the obligation, the title, the status, severity and source pills, the owner and the days to target.
- The record with Record a gap, Start remediation and Close, each behind `gaps.edit`.
- **The gap presentation is already there.** `register-presentation.ts` carries `presentGap` (it began life as `gap-presentation.ts` on `main` and `c8-ui-applicability` renamed and extended it), and `gapTone`, `severityTone` and `slotTone.source` are already in `tone-by-kind.ts`. This package writes no presentation module and **appends no tone entry**.
- The navigation entry for `/gaps`, in the secondary group.
- Every string in the `register` catalogs.

**Owned paths:**

- `frontend/src/features/register/gaps/**`
- `frontend/src/app/(tenant)/gaps/page.tsx`, `frontend/src/components/register/GapsScreen.tsx`
- the obligation page screen component (it holds `obpage`; the gaps panel mount only)
- `frontend/src/shared/navigation/registry.ts` (one entry, an append)
- `frontend/src/messages/register/en.json`, `sv.json`

**Done when:**

- The screen and the panel match `tenant-gaps.html` and `tenant-obligation.html` in both themes and have every state.
- "Open" renders `negative`, "High" `negative`, "Remediating" `warning`, "Risk accepted" `information` and "Closed" `positive`, each from the row's kind, with a unit test per kind in en and sv.
- `tone-by-kind.ts` is unchanged by this package, asserted by reading the diff.
- The registry test (at most four ranked destinations) passes, and the main agent regenerates the navigation snapshot baselines after the merge.
- The screen reaches real data inside the 500 ms budget against `next start`.
- `check:messages` and `check:copy-drift` are green.
- REG-S5's journey is untouched and still fixme, with a comment naming `c8-ui-gaps-journey`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Pills through `Pill`, tones from the kind; six tones only.
- One presentation module per feature; no duplicate tone map.
- Measured against `next start`.
- No string literal in JSX.

### c8-ui-gaps-journey: REG-S5 against the real stack, roadmap line included

**Requirements:** REG-03  
**Scenarios:** REG-S5 `@e2e` un-fixme'd  
**Depends on:** c8-ui-gaps, c8-e2e-seed-register, c8-home-register-feeds, c6-roadmap-screen

Un-fixme REG-S5 and make it green. It holds `regfe` after `c8-ui-gaps`. The roadmap dependencies live here rather than on the screen half: REG-S5's last step reads the roadmap for "Our deadline", and that branch is `c8-home-register-feeds`'.

- The gap shows "Open" as negative, "High" as negative and its source; the roadmap lists the target date as "Our deadline"; starting remediation reads "Remediating" as warning.
- Sign in through the UI with a passkey; declare every expected error on the api-guard.

**Owned paths:**

- `frontend/tests/e2e/register.journey.spec.ts` (the REG-S5 block only)
- `frontend/src/components/register/GapsScreen.tsx` (only if the journey finds a defect; the fix is named in the commit body)

**Done when:**

- REG-S5 is un-fixme'd and green end to end, roadmap step included.
- No API is mocked and no token is injected.
- The clock is anchored; the target date is a pinned date, never derived from today.
- Teardown restores the seeded data, on failure too.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run build`
- `npm run test:e2e -- --grep "REG-S5"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Sign in through the UI with a passkey; no injected token, no mocked API.
- Every spec imports `test` from `tests/e2e/support/api-guard`.
- Clocks anchor to the tenant-local date plus a fixed wall time.
- Never quarantine a journey to get green.

### c8-ui-home-register: the register on Today and the roadmap

**Requirements:** HOM-01, HOM-03  
**Scenarios:** HOM-S1, HOM-S4 and HOM-S6 stay green  
**Depends on:** c8-home-register-feeds, c6-roadmap-screen, c6-today-screen

Render the register's contribution to the chunk 6 screens:
- "Where we stand" on Today: the counts per compliance category and the open gaps, each linking into the inventory or `/gaps` with the filter applied.
- The roadmap's three new branches, each with the "Our deadline" pill in the `brand` tone, the date, the days left and its owner.
- A tenant with no register entry sees the empty state, never an error.
- Every string in the `home` catalogs, which this package holds through `today`.

**Owned paths:**

- `frontend/src/components/home/TodayScreen.tsx`, `frontend/src/components/home/RoadmapScreen.tsx`
- `frontend/src/features/home/**` (the standing and roadmap presentation)
- `frontend/src/messages/home/en.json`, `sv.json`
- `frontend/tests/e2e/home.journey.spec.ts` (the HOM-S1, HOM-S4 and HOM-S6 blocks only, extended)

**Done when:**

- HOM-S1, HOM-S4 and HOM-S6 stay green and now assert the register rows.
- "Our deadline" renders as `brand` and an urgency renders as its own tone, from the kind.
- Each Today link lands on the filtered list, checked in the journey.
- Today reaches real data inside the 500 ms budget against `next start`.
- `check:messages` and `check:copy-drift` are green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "HOM-S1|HOM-S4|HOM-S6"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Six pill tones, chosen by slot or kind.
- Screen copy says what the user is doing; no requirement IDs.
- Measured against `next start`.
- No mocked API.

### c8-ui-risk-acceptance: accepting a risk on screen

**Requirements:** REG-03  
**Scenarios:** REG-S6 `@e2e` un-fixme'd  
**Depends on:** c8-ui-gaps-journey, c8-reg-risk-acceptance

Add risk acceptance to the gap record:
- "Accept the risk" behind `gaps.edit` with the reason picker over the tenant's list, then "Waiting for approval".
- The four-eyes refusal for the person who identified the gap, rendered from the `code`.
- Approve behind `risk.accept.approve` with the passkey step-up, then "Risk accepted" in the `information` tone with both names and the time.
- Reopen behind `gaps.edit`.
- Every string in the `register` catalogs.

**Owned paths:**

- `frontend/src/features/register/gaps/**` (the acceptance hooks and presentation)
- `frontend/src/components/register/GapAcceptancePanel.tsx`
- `frontend/src/messages/register/en.json`, `sv.json`
- `frontend/tests/e2e/register.journey.spec.ts` (the REG-S6 block only)

**Done when:**

- REG-S6 is un-fixme'd and green: the owner's own Approve answers 409 and the page says so, and the approver's passkey step-up moves the gap to "Risk accepted".
- The 409 is declared on the api-guard where it happens.
- The reason picker sends keys and shows labels, with unit tests in en and sv.
- `check:messages` is green and the panel has every state.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep "REG-S6"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Four eyes with a passkey step-up, prompted through the UI.
- The client branches on `code`.
- Reasons are rows; the screen sends keys.
- No mocked API, no injected token.

### c8-security-review: the chunk-wide sweep

**Requirements:** NFR-01, and every chunk 8 requirement  
**Scenarios:** none; it reads the diff  
**Depends on:** c8-register-models-core, c8-register-models-gaps-history, c8-reg-status, c8-reg-entity-status, c8-reg-applicability, c8-reg-gaps, c8-reg-risk-acceptance, c8-reg-history-interpretation, c8-reg-internal-links, c8-reg-duty-occurrences, c8-reg-inventory-overlay-api, c8-recurring-duty-model, c8-recurring-duty-proposal, c8-ten-org-api, c8-ten-teams, c8-ten-out-of-office, c8-ten-reassignment, c8-ten-support-grants, c8-support-access-mechanism, c8-support-access-console-list, f03-T59, f03-T72, and every chunk 8 f03 task marked SR

f03-T59 and f03-T72 are named because they are the My work read and the Statement of Applicability filter: both return permission-filtered tenant rows, and reviewing the chunk without them would leave two of its riskiest reads unreviewed. Waiting for them is what puts this package in wave 13.

Read chunk 8's whole diff against `main` at the chunk's start, with the guard suites, and write the findings into `docs/reviews/`:
- **Tenancy.** Every new table is forced tenant-only; every composite key is present; no read crosses a tenant.
- **Support access.** No tenant table gained a policy for it; the one new policy is SELECT-only on `support_access`, keyed on `app.platform_user_id`, set in one module under an AST guard and listed in `OTHER_POLICIES`. A support session activates its one tenant through `tenancy.activate()` and holds exactly seven read permissions; every non-GET answers 403; every request leaves one `support_access.read` audit row with no body and no query string; a revoke takes effect on the next request. No role has `BYPASSRLS` and the app holds no migrator credential.
- **Four eyes and step-up.** Applicability, bulk decision, risk acceptance, member removal and the support grant each refuse the same person and each carry the assertion id on their audit rows.
- **The library fence.** `recurring_duty` is reachable only through `apply.py` and the seeds; no register write touches the library; no agent key scope reaches either.
- **Audit and outbox.** Every 2xx write has its rows in the same transaction, and no after value carries an interpretation, a status note, a gap description or a comment.
- **Logs and outbound calls.** No tenant content in the application log, Sentry, an outbox payload or a model input; f03-T73's guard covers the standards half.
- **Input at the trust boundaries.** The paste, the bulk decision, the RRULE and every vocabulary key are validated, capped and refused with a `code`.
- **Permissions.** Every route is gated, nothing new is in `UNGATED_BY_DESIGN`, and the admin permissions still gate independently.

A critical or high finding blocks the chunk. A finding that does not block becomes a row in `HARDENING.md` and a package.

**Owned paths:**

- `docs/reviews/CHUNK8_SECURITY_REVIEW.md`
- `docs/plans/briefs/HARDENING.md` (new rows, an append)
- `docs/TODO_FOR_alex.md` (anything needing a person, an append)

**Done when:**

- Every area above is covered in writing, each finding with its severity, its evidence and where it gets fixed.
- The guard suites are green on the reviewed tree: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`.
- Every non-blocking finding has a `HARDENING.md` row and a named package.
- No code changes here.

**Gates:**

- `bash scripts/cloud-setup.sh`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No gate is lowered, no test skipped or quarantined, no finding closed without a fix or a row.
- A review writes no production code.

### c8-review-fixes: close the review

**Requirements:** NFR-01  
**Scenarios:** every chunk 8 scenario stays green  
**Depends on:** c8-security-review

Fix the findings of `c8-security-review`, rerun the review over the fix diff, and repeat until nothing critical, high or medium remains. If the review found nothing at medium or above, close at once with a note in `docs/reviews/`.

Each fix is minimal, test-first, and keeps every scenario green. A fix that would change a product invariant stops and goes to Alex instead.

**Owned paths:**

- The files each finding names, listed in the commit body
- `docs/reviews/CHUNK8_SECURITY_REVIEW.md` (the closing note)
- `docs/plans/briefs/HARDENING.md` (an append)

**Done when:**

- Every critical, high and medium finding is fixed with a test that fails without the fix, or is a `HARDENING.md` row with Alex's reason.
- The guard suites and the full backend suite are green.
- No coverage floor is lowered and no test is skipped.
- The rerun of the review finds nothing at medium or above.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --all`

**Invariants:**

- Never lower a gate, skip or quarantine a test, or mock an API in E2E.
- A fix that would weaken an invariant is a stop, not a change.

### c8-close-out: close chunk 8

**Requirements:** every chunk 8 requirement  
**Scenarios:** every chunk 8 scenario reported  
**Depends on:** c8-ui-applicability, c8-ui-where-we-stand-journey, c8-ui-gaps-journey, c8-ui-risk-acceptance, c8-ui-history-interpretation, c8-ui-internal-links, c8-ui-inventory-overlay, c8-ui-home-register, c8-ui-organisation-journey, c8-ui-teams, c8-ui-out-of-office, c8-ui-member-removal, c8-ui-support-access, c8-vocab-register-usage, c8-review-fixes, f03-T63, f03-T64, f03-T65, f03-T73, f03-T75

f03-T63 is in the depends-on because COL-S6 and COL-S7 are its journeys, and this package's first job is to prove that no chunk 8 journey is still fixme. f03-T65 is there for HOM-S13, for the same reason.

Close the chunk on `main`:
- **Prove no 501 is left.** A test walks every chunk 8 route and fails on `not_built`. Delete the `contract_drift_pending.txt` lines the chunk built, and record the built operations in `INPUT_DELTAS.md` §7, with the shape changes of §1 that this chunk realised: `team` as a tier-three list, `tenant_obligation_scope.next_review_date` and its applicability reason and decision time, `soa_unit`, `licence`'s certificate columns, the participant table, and the move of `compliance_status`, `risk_rating`, `gap_status` and `link_kind` from CHECK constraints to tenant lists.
- **Status cells.** Set REG-01, REG-02, REG-03, REG-04, REG-05, REG-07, REG-08, TEN-02, TEN-03, TEN-04, TEN-05, TEN-06, HOM-05, COL-04, VOC-04, VOC-05 and VOC-06 to `built` in their `app.md`s. TEN-06 is `built`: Q1 is answered and all four of its packages are in this chunk. ADM-01 stays `in_progress`: it spans R1 to R3.
- **Name what is not done**, each with the chunk that owns it: REG-06 and REG-S9 (chunk 13); TEN-S7 (chunk 10, `c10-j8-extension`); the case halves of TEN-S3 and TEN-S5 (chunk 9, plan ruling 10); TEN-S4's sign-off and notification halves (chunks 9 and 10); VOC-03 and VOC-S6, VOC-S7 (chunk 10, correcting the UI plan row that says chunk 8); the SoA export (R3, REP-02).
- **Ledgers.** Update `IMPLEMENTATION_STATUS.md`'s chunk 8 row and the UI plan's register, organisation and My work rows. Copy every default this brief lists into `docs/TODO_FOR_alex.md`, with **Q2, Q3 and Q4** only. Q1 was answered on 2026-09-19 (`OWNER_RECOMMENDATIONS.md` item 2) and Q5 was always a default, not a question; the private-notes question (D-22) was closed by item 13 and is not copied forward. Re-listing an answered question is how a decided point gets re-opened.
- **Floors.** Ratchet the coverage floors for `apps/register/*`, `apps/tenants/*`, `apps/home/*`, `apps/collab/*` and the new frontend features to what the chunk measures; never lower one.
- **The full suite.** `prepush.sh --all` and the whole `npm run test:e2e`.

**Owned paths:**

- `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`
- `backend/scripts/coverage_gate.py`
- `backend/apps/register/app.md`, `backend/apps/tenants/app.md`, `backend/apps/home/app.md`, `backend/apps/collab/app.md`, `backend/apps/taxonomy/app.md`
- `docs/plans/IMPLEMENTATION_STATUS.md`, `docs/plans/UI_Implementation_Plan.md`
- `docs/TODO_FOR_alex.md`
- `backend/apps/shared/tests_no_stubs.py`

**Done when:**

- No chunk 8 route answers 501 and no chunk 8 journey is fixme, except those named above with their chunk.
- `contract_drift.py` passes with no stale or unexplained line.
- A full-suite `coverage_gate.py` passes with the new floors, and no floor is lower than before.
- `requirements_coverage.py` and `compliance_check.py --all` are green.
- `prepush.sh --all` and the full E2E suite are green on the exact commit.
- The status files match `git log`: every requirement's cell is the truth of what is on `main`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)`
- `python backend/scripts/requirements_coverage.py && python backend/scripts/compliance_check.py --all`
- `cd frontend && npm run test:e2e`
- `bash scripts/prepush.sh --all`

**Invariants:**

- Floors never go lower than before.
- Status reflects `git log`, never intent.
- Nothing is quietly dropped: what is not built is named with the chunk that owns it.
- No gate is lowered to close a chunk.
