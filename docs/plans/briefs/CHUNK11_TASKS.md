# Chunk 11: tasks

Written 2026-09-20 by the planning workflow (read, plan, a parallelism critique, a coverage
critique, revise). Each task runs in its own worktree or cloud session
(`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`.
The task ids are the `c11-` package ids of `docs/plans/PARALLEL_PLAN.md` section 3.3 plus
`f03-T82` from `docs/plans/briefs/FEATURES_0_3_TASKS.md`; nothing is renamed, added or
dropped. Where a package exceeded the thirty-minute target it is split in two, and the pair
keeps the parent id as a prefix (`-a`, `-b`), as chunk 5's ruling L does; the second half
depends on the first.

## Revised 2026-09-20

A review of this plan against `main` (which now carries the merged chunk 5 and chunk 7 plans)
found ten places where it named work that did not exist, duplicated work another task already
owned, or left an actor unstated. Each is closed below; nothing else changed, and no task was
added or dropped.

| Fix | Finding it closes |
|---|---|
| `c11-fe-agents-budget-ai` says the AI control calls `c7-ask-switch`'s route under `security.manage` behind the step-up dialog, renders read-only without that permission, and gains `c7-ask-switch` in its depends-on | HIGH: the switch's route, gate and step-up were unstated, so the screen could have been built writable for a member who cannot write it |
| `c11-ai-off-switch` narrows to the tenant agent-run paths: the wrapper check and the platform-call-still-goes-through test are `c7-ask-switch`'s, the two restated done-conditions are gone, and it no longer writes that file | MEDIUM: it duplicated `c7-ask-switch` and two tasks wrote one wrapper |
| `PlatformWatchItem` gains `nextRunAt` and a status-only `lastRun`, and both field-set assertions (`c11-tenant-agents-contract-b`, `c11-platform-watch-read`) list the new set | MEDIUM: the schema was pinned to five fields with "no run detail" while `c11-e2e-agent-controls-b` asserts the panel still shows a next run, and ADR 0053 shows the agents read-only with their history |
| `obligation_scope` is planned as a `ProposalKind` enum member (`c11-batch-proposals-contract-a`) with its payload schema (`-contract-b`) and its `apply()` branch (`c11-batch-proposals-b`); the OpenAPI change is expected and `proposals/seeds/` is gone | MEDIUM: it was planned as a vocabulary seed row in a directory that does not exist, with "openapi.json unchanged", while `ProposalKind` is a code enum `apply()` branches on |
| `c11-batch-proposals-contract-a` depends on `c5-library-provenance-models` and `c5-library-proposal-kinds` | MEDIUM: it named `c5-library-links-provenance`, which the merged chunk 5 plan renamed and split |
| AGT-S4's rewording moves to `c11-platform-agent-settings-b`, the task that un-skips it; `c11-tenant-agents-contract-b` rewords the other three | MEDIUM: the rewording and the test that depends on it sat in one wave with no ordering between them |
| Every chunk 11 edit to `UI_Implementation_Plan.md` is `c11-chunk-close`'s, which first splits row 92 and row 95 one screen per row | MEDIUM: rows 92 and 95 each cover two screens, so `c11-cards-agents-a`/`-b` collided on one row and `c11-cards-security-batch-a` shared another with chunk 13 |
| Item 8's member list, `meetsPolicy` and shell notice are named as deferred to chunk 13 (`c13-fe-credential-compliance`), and ID-07 closes this chunk at `in_progress` | MEDIUM: no task built that package, yet ID-07 was to be marked built |
| The split count reads nineteen, the nineteen are listed, and the six packages left whole each carry the green point they stop at | LOW: the count said eighteen |
| `q-tenant-definition` is stated as a confirmation, because `schema.sql` already ships `agent.scope` and `tenant_configurable` and `PARALLEL_PLAN` 3.3.1 is the outlier; `c11-runner-managed-agents` is recorded as answered by item 7, D-54 and ADR 0047 rather than asked; and AGT-S7's actor is stated as `agents.manage` alone, with the reason and the one-line reversal | Questions: three entries asked for what the inputs had already settled, or left an actor to the reader |

## Scope, rules and defaults

Chunk 11 plan: agents. `Build_Plan.md` gives the chunk AGT-03 to AGT-06 (including AGT-04's
default market scope), PRO-04, ID-07 and ID-08; PRD 0.4 rewrites AGT-03 to AGT-05 around
Alex's decision of 2026-09-19 (item 14 of `OWNER_RECOMMENDATIONS.md`, D-61, ADR 0053), and
`f03-T82` carries AGT-S11. The plan has 51 tasks in 16 waves, about 26 agent-hours of task
work plus review, and one task held for a key.

### The decision this chunk is built around

bleqq's general financial-regulation watch is the product. It is **platform-owned and
platform-run**: no tenant switches one of its agents off, pauses it, changes its cadence,
scope or budget, or edits its definition, and there is no tenant off switch anywhere near it.
A bank may add agents of its own for what it must watch; **only those** get AGT-04's controls,
they run under the bank's own monthly cap, and they write only the bank's zone — never a
library row. A tenant's AI off switch stops the bank's own agents and its own AI features and
nothing else. A tenant agent's key never opens a platform run, and a platform run reads no
tenant row.

Every task below is written to that rule. A task that finds a route, column or screen
contradicting it stops and reports (parallel-plan rule 12).

### Hard preconditions from other chunks

No chunk 11 task starts before the work it names is on `main`:

- **`r1-readiness`**, for every task that touches the proposal door (`c11-batch-proposals-contract-a`
  and `-b`, `c11-batch-proposals-a` and `-b`) or authentication and sessions
  (`c11-credential-policy-a` and `-b`, `c11-session-policy`). Parallel-plan rule 11.
- **Chunk 5**, all of it: `c5-contract-models-agents` (E5, already merged: `Agent`, `AgentRun`,
  `ApiKey.agent`, the seed reader), `c5-contract-api-agent` and `c5-agent-runs` (the run API
  this chunk schedules), `c5-platform-agent-keys` (platform keys bound to an agent),
  `c5-ai-log-contract` (the one wrapper every model call goes through, which
  `c7-ask-switch` put the AI-off check inside and `c11-ai-off-switch` only extends to tenant
  agent runs), `c5-watch-sources-coverage` (the source registry
  a research request checks), `c5-library-recheck` (the re-check the platform watch performs,
  which this chunk schedules but does not change) and `c5-chunk-close`.
- **Chunk 4**: `c4-console-shell` and through it `x-frontend-split`; `c4-approve-apply` (the
  apply path batch approval extends); `c4-library-updates`; `c4-fe-approve` (the console
  approve controls the batch screen reuses).
- **Chunk 7**: `c7-ask-switch`, which owns the single `Tenant.ai_enabled` column, the
  wrapper's check, the step-up-gated write and the proof that a platform call still goes
  through (`PARALLEL_PLAN` ruling 13); `c7-ask-backend`, whose Ask route
  `c11-ai-off-switch`'s test drives, and `c7-ask-screen`, which renders `feature_off`.
- **Chunk 10**: `c10-notifications-api`, for the "the admin is notified" line of AGT-S6.
  The contingency below says what happens if it is late.
- **`f03-T19`** (the markets logic) for `f03-T82`, and **`f03-T16`**'s mirror guard through it.
- **`h-a-guards`** and **H-C** (`HARDENING.md`), because every mixed table this chunk adds
  copies H-C's split policy shape and `c11-credential-policy` builds on H2's intersected
  principal permissions.

### What it delivers

- **AGT-03**: `agent_version` rows with the publishing path under `agent_definitions.manage`,
  an audit row per publish, a run pinned to the version it started under, and a 403 for any
  tenant request that would reach a definition. The versioned folders under `backend/agents/`
  grow the fields a published version needs.
- **AGT-03, the platform half that is new**: bleqq's general watch agents carry their cadence,
  scope and budget as **platform rows**, edited in the console by a platform admin and audited
  through `record()`. There is no tenant column on them and no tenant write path: a control
  write naming a platform agent answers 403 with `agent_definitions.manage`.
- **AGT-04**: a bank's own agents — add, on and off, cadence inside the plan limit, scope,
  run now, pause, resume, interrupt, a run history with findings and cost, one monthly budget
  cap for the bank, and the AI off switch. Each control refuses a platform agent.
- **AGT-04, the read-only half that is new**: "What bleqq watches" — each general agent's
  name, purpose, the jurisdictions it sweeps, its check cadence, when it next runs and the
  status of its last run, and nothing else. No prompt, tool, model, version internals, budget,
  cost, findings, proposal counts or setting, and nothing writable. ADR 0053 shows bleqq's
  agents read-only **with their history**, so the next run and a status-only run summary are
  part of the read, not run detail.
- **AGT-05**: research requests on the bank's own agents (check a source now, check a URL,
  research a topic, run now), and the platform console's own `retag` request, which produces
  one batch proposal with a preview and never a direct edit. A bank with no agent of its own
  is refused, because it cannot command a platform agent.
- **AGT-06**: the runner adapter as the seam the worker starts runs through, the app as the
  scheduler of record, runner events updating the run row, and interrupt.
- **AGT-S11 / `f03-T82`**: a tenant agent's default scope is the bank's operating markets
  first, then the watched ones, copied onto the run at run start; a platform run reads no
  tenant row.
- **PRO-04**: batch proposals with a preview, approved whole or row by row, one audit event
  for the batch and one per row, and the `obligation_scope` proposal kind chunk 4 cut
  (ruling 14 of the parallel plan).
- **ID-07, the enforcing half**: the tenant credential policy of ADR 0048 — `any_passkey` or
  `device_bound`, an allow-list from a committed platform list, binding on new registrations
  at once and on sign-in from a notice date, with the backup-eligibility comparison for every
  bank, and the policy form. **Not** the telling half: item 8's member list, `meetsPolicy` on
  My passkeys and the shell notice are deferred (see Cut), so ID-07 closes this chunk at
  `in_progress`.
- **ID-08**: the tenant session policy — idle and absolute limits inside platform maximums,
  refused above them with `above_platform_maximum`.
- **ADM-01**: the Agents and Security panels of the tenant admin; **ADM-02**: the console's
  Agent definitions surface.
- The chunk's own security review, its fix package and its close.

### Rulings where the sources disagree

1. **A definition is always bleqq's; a bank adds an agent, not a prompt.** `PARALLEL_PLAN`
   section 3.3.1 says a tenant agent "points at a tenant-created definition". `Agent` is a
   `LibraryModel`, so a tenant-created definition row would be a tenant writing the library,
   which the fence forbids and which no proposal covers. AGT-03 and ADR 0053 both say the
   versioned definitions stay the platform's. So: every `agent` row is bleqq's, a definition
   carries `scope` (`platform` or `tenant`) and `tenant_configurable`, and a bank "adds its
   own agent" by creating a `tenant_agent` row against a **tenant-scoped** definition with its
   own cadence, scope, sources and budget. A `tenant_agent` pointing at a `scope='platform'`
   definition is refused by a database CHECK and by the route. This is `q-tenant-definition`
   under Open questions; the recommended option is what the build does, so nothing waits.
2. **A tenant agent's findings are run findings in R2, not records.** ADR 0053 says what a
   tenant agent finds "becomes the bank's own private records (ADR 0050) or nothing", and
   private records are chunk 13 (`c13-private-*`, WAT-06, R3). In chunk 11 a tenant agent
   writes its own `agent_run`, its `research_request` result and nothing else. AGT-04's
   "history with findings and cost" is served by the run's stats and cost, not by new library
   or watch rows. **No chunk 11 task edits `tests_library_fence.py`, its allowlists,
   `LIBRARY_WRITE_ALLOWED_DIRS`, `authentication.py`, `tenancy.py`, `middleware.py` or the
   production boot guard.** `c11-chunk-close` proves the diff of the whole chunk touches none
   of them.
3. **One cap for the bank, not one per agent.** `schema.sql` has `tenant_agent.monthly_budget`
   per agent; the prototype's `vAgents()` and AGT-04 both show one monthly cap with one
   "Spend this month". Ruling 13 of the parallel plan says chunk 11's settings row holds only
   the monthly cap. The build takes one tenant-wide cap (`TenantAgentBudget`, one row per
   tenant) and does not build `tenant_agent.monthly_budget`: two caps would be two things to
   explain and nothing asks for the second. Spend is summed from the month's `agent_run.cost`
   for the tenant's own runs; no second ledger is built.
4. **The managed-agents runner cannot ship.** D-08 named Claude Managed Agents as the first
   real runner with the Agent SDK in our own worker as the fallback. D-54 and ADR 0047 are
   later and answered: on every deployed environment except `ENVIRONMENT=test` the boot
   refuses `managed_agents`, and production agents run in our own worker on Bedrock in an EU
   region. So chunk 11 ships the adapter seam, the mock and the event handling, and
   `c11-runner-managed-agents` stays held and outside the waves with that reason recorded.
   The real runner is the Agent SDK leg, a later package with its own ADR amendment.
   `c11-runner-adapter` changes no boot guard: `MOCK_ADAPTER_SETTINGS` in
   `backend/config/settings.py` already refuses `AGENT_RUNNER=mock` outside the named test
   environment, which is AGT-S8's last line.
5. **`agents.manage` is the permission for every tenant agent control and every research
   request — alone, not in a pair.** Three sources disagree. AGT-S7's Gherkin names a
   compliance officer; the prototype's Agents view says "an administrator or the compliance
   officer"; `PARALLEL_PLAN` line 1132 and item 10 both write "`agents.manage` **or**
   `proposals.create`". PRD section 6 grants `agents.manage` to Admin alone and
   `proposals.create` to the Compliance officer alone, so that `or` is two roles, not one
   actor. 0.4 adds no permission, and the design decides look and flow, never the rules
   (CLAUDE.md section 2). **The plan takes `agents.manage` alone**, because a research request
   spends the bank's agent budget under the bank's agent settings and `proposals.create` comes
   with no control over the cap; item 10's pair is about requesting a **private source** in
   chunk 13, which is a different act and is left alone. AGT-S7 is reworded to a tenant admin
   holding `agents.manage`, and the prototype's line is not copied onto the card. The console's
   `retag` request is `proposals.review`, as AGT-05 says. This is the one-line confirmation
   under Open questions: reversing it adds an `or` on three routes and nothing else.
6. **"What bleqq watches" is a member's read, not an admin's.** It carries public facts about
   the platform's coverage — name, purpose, jurisdictions, cadence — so it is gated by
   `watch.read`, which every system role holds, rather than by `agents.manage`. A reader who
   cannot manage agents still needs to know what is covered. The admin Agents screen shows the
   same panel; the route is the same.
7. **The admin Security card is chunk 11's, not chunk 13's.** `UI_Implementation_Plan.md`
   row 95 marks `admin-security.html` "chunk 13, card pending", but ID-07 and ID-08 are R2 and
   the Build plan puts them in chunk 11. `c11-cards-security-batch-a` draws the card and
   `c11-chunk-close` corrects the UI plan row to chunk 11, leaving the IP allow-list panel
   (ID-13) named for chunk 13.
8. **`VOC-S12` is not chunk 11's.** UI plan row 249 lists batch proposals against PRO-S8,
   VOC-S12 and AGT-S7. VOC-08 (bulk tagging from a tenant list view) is chunk 10's and writes
   tenant rows, not library rows. Chunk 11 owns PRO-S8 and AGT-S7 and leaves VOC-S12 alone.
9. **`GET /agent-runs` is chunk 5's route.** `c5-contract-api-agent` declared it and
   `c5-agent-runs` serves it. `c11-tenant-agents-contract-b`, which holds `agentsapi`, adds
   the chunk 11 query parameters and response fields to it in one edit;
   `c11-run-history` serves the extended reading from its own module and never touches
   `agents/api.py`.
10. **`f03-T82` loses `models.py` and the sweeper prompt.** Its owned paths in
    `FEATURES_0_3_TASKS.md` are `agents/logic.py`, `agents/models.py` and
    `agents/watch-sweeper/v2/prompt.md`. Under item 14 the default market scope belongs to a
    **tenant** agent, and `watch-sweeper` is one of bleqq's platform agents whose prompt no
    tenant market may reach (D-32). So `f03-T82` owns `backend/apps/agents/scope.py` and its
    tests, adds no column (`tenant_agent.scope` arrives with
    `c11-tenant-agents-contract-a`) and writes no platform prompt. Its done-condition is
    unchanged.

### Defaults taken (each stated in its commit body, and copied into `docs/TODO_FOR_alex.md` by `c11-chunk-close`)

- **The AI off switch stops only the bank's own agents and AI features** (D-61's first open
  detail, proposed answer taken). A platform run has `tenant_id` NULL and is never stopped by
  a tenant setting; bleqq's agents read only public sources.
- **A bank's own agents run under the bank's own monthly cap** (D-61's second open detail,
  proposed answer taken). bleqq's general watch runs at bleqq's cost and no tenant figure
  includes it: "Spend this month" sums the tenant's own runs only.
- **Publishing a definition version and changing a platform agent's settings each ask for a
  passkey step-up.** Playbook 4.2 does not list them, but each changes what runs in every
  bank, which is the class of change the list is drawn from. Adding a step-up never weakens a
  gate; it is named in `TODO_FOR_alex.md` for confirmation.
- **A published version is immutable.** `agent_version` is an `AppendOnlyModel` with the
  trigger from `migration_helpers.append_only_trigger_operations`, so AGT-S4's "earlier runs
  still reference 3" is structural rather than remembered. Retiring a version sets
  `retired_at`, which is the one column the trigger's update exception allows, as the library
  versions already do.
- **A run pins its version at start.** `agent_run.agent_version_id` is written when the run
  opens and never after, so a publish mid-run changes nothing.
- **Cadence keys are `daily`, `weekly`, `monthly` and `manual`** (`schema.sql`), and the plan
  limit is a setting, `AGENT_MIN_CADENCE_BY_PLAN`, read from the tenant's plan row; above it
  the request answers 422 `above_plan_limit`.
- **`AgentCadence`, `AgentScopeKind`, `AgentRuntime`, `AgentEnvironment`, `RunTrigger` and
  `ResearchRequestKind` are tier-one kinds** in `apps/shared/kinds.py`: the scheduler and the
  screens branch on them and no admin adds one (INPUT_DELTAS section 5). `research_request.kind`
  gains `retag` there, as INPUT_DELTAS asks.
- **A tenant agent is paused, never deleted.** Disabling sets `enabled` false and keeps the
  row, so its runs keep a parent. Nothing overwritten (CLAUDE.md section 5).
- **A research request is capped per plan** (`RESEARCH_REQUESTS_PER_MONTH`, a setting with an
  env override) and answers 429 `plan_limit_reached` above it.
- **A batch proposal is one `proposal` row with a batch of rows beneath it**, so four eyes,
  the rejection reason and the audit row are the ones chunk 4 already built. A row decision
  writes its own audit event and the batch writes one more with each row's outcome, which is
  PRO-S8's last line.
- **The credential policy's allow-list is a committed platform list** built from the FIDO
  Metadata Service, read from a repository file, never downloaded at runtime (ADR 0048).
- **Session limits are `SESSION_IDLE_MAX_MINUTES` and `SESSION_ABSOLUTE_MAX_HOURS`**, settings
  with env overrides, and a tenant value above either answers 422 `above_platform_maximum`.
- **Every threshold is a setting with an env override**, in one labelled block naming its
  task, with a row in `.env.example` and `docs/runbooks/RAILWAY_VARIABLES.md`.
- **Coverage floors** are set once, from a measured full run at `c11-chunk-close`, and are
  never lowered.

### Cut, with reasons

- **`tenant_agent.monthly_budget`, `currency` and `pinned_version_id`**: ruling 3 for the
  first two; a bank that cannot edit a definition has no reason to pin a version of one, and
  `agent_run.agent_version_id` already records what ran.
- **`tenant_agent.environment` and `external_environment_id`**: ruling 4. No self-hosted
  runner exists to name, and the column would describe a choice nobody can make.
- **`source_request`** (`schema.sql` PART 3): WAT-06, chunk 13. A bank requesting a source is
  the private-sources feature, not an agent control.
- **Tenant-private records written by a tenant agent**: ruling 2, chunk 13.
- **The Managed Agents runner**: ruling 4. `c11-runner-managed-agents` is held.
- **`newsletter_issue`, `newsletter_item` and `prompt_template`**: no chunk 11 requirement or
  scenario asks for them. `agent_version` carries the prompt reference the publish path needs.
- **Per-agent spend on the tenant screen**: AGT-04 asks for cost in the run history and one
  monthly cap. Cost is on each run row; a per-agent total is a report (chunk 12).
- **A console screen for research requests other than `retag`**: AGT-05 puts topic and source
  requests with the bank. The console gets the re-tag form only.
- **VOC-S12**: ruling 8.
- **The IP allow-list panel of `admin-security.html`**: ID-13, chunk 13.
- **Item 8's credential-compliance frontend package**, deferred to **chunk 13** as
  `c13-fe-credential-compliance`: the list of members without a compliant passkey,
  `meetsPolicy` on My passkeys, and the notice in the shell. Item 8 puts it after
  `c11-credential-policy` and it is what tells a bank who a stricter policy will refuse, but
  it touches three screens no chunk 11 card covers (`admin-members.html`, `me-passkeys.html`
  and the shell) and no chunk 11 task builds it. Chunk 13 already holds
  `admin-security.html`'s remaining panel (ID-13) and SSO, so it goes there with them.
  Consequence, and the reason this is written down rather than left implicit: **ID-07 stays
  `in_progress` at the close**, with chunk 13 named beside it, and a bank can set the policy
  before it can see who it will lock out. `c11-chunk-close` writes this into
  `docs/TODO_FOR_alex.md` as a default taken, because a shorter deferral (into chunk 12, or a
  thirty-minute package inside chunk 11 with its own card) is Alex's call, not the plan's.

### Plan-wide rules

1. **Slots.** Every backend and E2E gate runs inside the task's slot:
   `set -a; . ./.env.worktree; set +a`. A cloud session runs `bash scripts/cloud-setup.sh`
   (with `--e2e` where the gates include E2E) instead.
2. **Generated files.** No task commits `openapi.json`, `frontend/src/types/api.generated.ts`
   or `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them locally
   to run `contract_drift.py` and the typecheck, then reverts them. The main agent regenerates
   and commits them at the merge, and regenerates the navigation and pill snapshot baselines
   when `registry.ts` or `tone-by-kind.ts` changed.
3. **The agents backend chain.** Two tasks and only two write `backend/apps/agents/api.py` and
   `schemas.py` (key `agentsapi`), in this order: `c11-agent-definitions-contract-b` writes the
   platform half, `c11-tenant-agents-contract-b` appends the tenant half. Every operation is
   sent to a named function in the module that will build it, which answers 501 `not_built`
   (parallel-plan rule 2). A logic task owns only its own module (`definitions.py`,
   `platform.py`, `platform_read.py`, `tenant_agents.py`, `control.py`, `budget.py`,
   `requests.py`, `runs_read.py`, `scope.py`, `tasks.py`) and its tests, never `api.py`. A
   logic task that finds the contract wrong stops and reports.
4. **The agents frontend chain.** One task at a time owns
   `frontend/src/features/agents/{types,api,hooks}.ts` (key `agentsfe`), in this order:
   `c11-fe-console-agent-definitions-a`, `-b`, `c11-fe-admin-agents-a`, `-b`,
   `c11-fe-agents-budget-ai`, `c11-fe-research-requests`. Each adds only the operations its own
   screen calls. `c11-fe-admin-security` has its own feature directory
   (`features/security-policy/`) and joins no chain; `c11-fe-console-batch-review` holds
   `consoleq`.
5. **Screens call no stub.** Each screen task depends on every backend task whose routes it
   calls. The AI off switch's screen half is `c7-ask-screen`'s; `c11-ai-off-switch` is backend
   only and takes no frontend key (a change from `PARALLEL_PLAN`, which gave it `searchscreen`).
6. **Append ledgers** (parallel-plan rule 5): `docs/inputs/INPUT_DELTAS.md`,
   `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`,
   `docs/plans/Verification_Log.md`, `docs/plans/briefs/HARDENING.md`,
   `backend/config/settings.py` setting banners, `backend/.env.example`,
   `docs/runbooks/RAILWAY_VARIABLES.md`, router mounts in `backend/config/api.py`,
   `backend/apps/shared/kinds.py`, `factories.py`, the route lists in `permissions.py`, the
   guarded-table lists in `tests_rls.py`, `tests_four_eyes.py` and `tests_seed_integrity.py`,
   `backend/apps/shared/e2e_seed.py`, `e2e_logins.py`, `e2e_passkeys.py` and
   `frontend/tests/e2e/support/passkeys.ts` (one seed call or one login per task),
   `frontend/src/shared/navigation/registry.ts` entries,
   `frontend/src/features/shared/tone-by-kind.ts` entries, each app's `app.md` status cells,
   each `tests_scenarios.py` skip line (its own only), and each `*.journey.spec.ts` (own test
   blocks only). Each task adds only its own lines and never edits another's.
   **`docs/plans/UI_Implementation_Plan.md` is not one of them in this chunk**:
   its row 92 covers `admin-agents.html` and `console-agent-definitions.html` together and its
   row 95 covers `admin-security.html` and `admin-integrations.html` together, so a per-task
   edit would have `c11-cards-agents-a` and `-b` writing one row and
   `c11-cards-security-batch-a` writing chunk 13's. Every chunk 11 edit to that file is
   `c11-chunk-close`'s, which splits both rows one screen per row before setting any status.
7. **Coverage floors.** `backend/scripts/coverage_gate.py` gets the chunk 11 floors once, from
   `c11-chunk-close`, measured at the close with the date beside each. A task states its own
   `coverage report --include` threshold in its done-condition and never lowers an existing
   floor.
8. **Security review before merge.** Every task marked **SR** below gets a security-review
   sub-agent over `git diff main...<branch>` before the squash merge, with `tests_rls`,
   `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`,
   `tests_audit_on_write` and `tests_four_eyes`. `c11-security-review-a` and `-b` are the
   chunk-wide sweeps after the last screen merges, and `c11-review-fixes` closes their
   findings.
9. **Merge at once.** Each task is squash-merged and the full checklist run as soon as it
   passes review (WORKTREES step 5). Finished work never waits for the rest of the chunk.
10. **Test first, in every task.** The failing test comes first, then the code, then green. A
    task that cannot write its test first stops and reports.
11. **Cloud sessions stop on an invariant question** (parallel-plan rule 12), commit nothing
    further and report it. The tasks that carry that instruction explicitly are
    `c11-agent-definitions-contract-a`, `c11-tenant-agents-contract-a` and `-b`,
    `c11-platform-agent-settings-a`, `c11-tenant-agent-controls-a` and `-b`,
    `c11-run-scheduler-a` and `-b`, `c11-batch-proposals-contract-a`, `c11-batch-proposals-b`,
    `c11-credential-policy-a` and `-b`, `c11-session-policy` and `c11-research-requests-a`.
12. **CLAUDE.md section 11 in full** goes into the prompt of every task that touches UI or a
    journey: a production Next build, the real backend, passkey sign-in through the UI, `test`
    imported from `support/api-guard`, expected errors declared where they happen, `seed_e2e`
    extended and never mocked.
13. **Clocks.** Everything dated is anchored to the tenant-local date plus a fixed wall time
    (CLAUDE.md sections 8.3 and 11). A cadence, a next-run time, a notice date and a month's
    spend are all clock-sensitive: tests freeze the clock and the seed derives its dates from
    the anchor. No fixture depends on the real "today".
14. **Every agent run is a job with a status endpoint** (CLAUDE.md section 6). Starting a run,
    a research request and a batch decision each answer at once with a row whose status is
    read from `GET /agent-runs/{runId}`, `GET /research-requests/{requestId}` or
    `GET /proposal-batches/{batchId}`; none of them does the work inside the request.
15. **Every model call is logged and fetched content is untrusted.** Chunk 11 adds no second
    model path: a run's model calls go through `c5-ai-log-contract`'s wrapper, and anything a
    run fetches is screened by `agents/screen.py` exactly as chunk 5 built it. A task that
    needs a model call outside the wrapper stops and reports.
16. **Agents read vocabularies at run start and use existing keys only** (AGT-02). A scope, a
    cadence or a research topic stored on a tenant agent is validated against the live
    vocabulary and the kinds at write time and again at run start; an unknown key answers 422
    `unknown_key` with the valid keys.
17. **Scenario ownership.** Exactly one task un-skips each integration test and one un-fixmes
    each journey. The table below is the authority; a task never touches a half it does not own.

| Scenario | `@integration` owner | `@e2e` owner |
|---|---|---|
| AGT-S4 (AGT-03, reworded) | `c11-platform-agent-settings-b` | `c11-e2e-definitions-requests-a` |
| AGT-S5 (AGT-04, reworded) | `c11-tenant-agent-controls-b` | `c11-e2e-agent-controls-a` |
| AGT-S6 (AGT-04, reworded) | `c11-run-scheduler-b` | `c11-e2e-agent-controls-b` |
| AGT-S7 (AGT-05, reworded) | `c11-research-requests-b` | `c11-e2e-definitions-requests-b` |
| AGT-S8 (AGT-06) | `c11-runner-adapter` | — |
| AGT-S11 (AGT-04, reworded) | `f03-T82` | — |
| AGT-S14 (AGT-03, AGT-04), new | `c11-platform-agent-settings-a` | — |
| PRO-S8 (PRO-04) | `c11-batch-proposals-b` | `c11-e2e-definitions-requests-b` |
| ID-S16 (ID-07) | `c11-credential-policy-a` | — |
| ID-S17 (ID-08) | `c11-session-policy` | — |
| ADM-S1 (ADM-01, ADM-03) | stays green, extended by `c11-fe-admin-security-b` | stays green, extended by `c11-fe-admin-agents-b` |
| ADM-S4 (ADM-02) | stays green, extended by `c11-fe-console-agent-definitions-b` | stays green, extended by `c11-fe-console-agent-definitions-b` |
| NFR-S1, NFR-S5 (NFR-01) | stay green, extended to every chunk 11 tenant route and table | — |
| NFR-S13 (NFR-01) | stays green; every contract task adds its routes | — |
| NFR-S6 (NFR-02) | stays green; every route task asserts `Server-Timing: app` and its budget | — |
| AGT-S1, AGT-S2, AGT-S3, AGT-S9, AGT-S10, AGT-S12, AGT-S13 | stay green, chunk 5's | stay green, chunk 5's |

`AGT-S14` is new: the PRD and ADR 0053 describe the platform fence around bleqq's agents but
`agents/app.md` has no scenario for it. `c11-platform-agent-settings-a` writes the scenario and
its test together, in the house format (CLAUDE.md section 10). The contract, model, seed,
runner-event, scope, budget, history, platform-read and frontend data-layer tasks carry no
scenario of their own and prove their behaviour in their own test module; each is named above
as a dependency of the task that does own the scenario.

### Changes from `PARALLEL_PLAN.md`, with reasons

- **Nineteen packages are split in two** (`-a`/`-b`) because each was 45 to 60 minutes, which
  the plan's own rule 9 and three earlier plan reviews call too long for one sub-agent. The
  parent ids are kept as prefixes and the pairs are ordered. The nineteen are
  `c11-cards-agents`, `c11-cards-security-batch`, `c11-agent-definitions-contract`,
  `c11-security-policy`, `c11-batch-proposals-contract`, `c11-tenant-agents-contract`,
  `c11-platform-agent-settings`, `c11-credential-policy`, `c11-tenant-agent-controls`,
  `c11-batch-proposals`, `c11-run-scheduler`, `c11-research-requests`,
  `c11-fe-console-agent-definitions`, `c11-fe-admin-security`, `c11-fe-admin-agents`,
  `c11-fe-console-batch-review`, `c11-e2e-agent-controls`, `c11-e2e-definitions-requests` and
  `c11-security-review`.
- **Six more are left whole but told where to stop**, because their seam is a green point
  rather than a file boundary: a pre-split would have given the second half nothing to own.
  Each runs to its named green point, commits there, and hands the remainder to a follow-on
  task if it has run past the target (parallel-plan rule 9), rather than carrying on:
  - `c11-runner-adapter`: the seam, `RunHandle` and `MockAgentRunner` green, before
    `runner_events.py` and AGT-S8.
  - `c11-agent-definitions`: the sweeper folder's new scalars and the seed reader green,
    before the `tenant-source-watch` folder.
  - `c11-platform-runs`: the run list, its paging and its tenant-exclusion tests green, before
    the per-page source-coverage join and its query-count and budget tests.
  - `c11-e2e-seed`: the definitions, the platform runs and the two logins green, before tenant
    A's agent, its runs, its budget row and the batch.
  - `c11-fe-agents-budget-ai`: the spend panel, the cap and the meter green, before the AI
    switch and its step-up dialog.
  - `c11-fe-research-requests`: the three request forms green, before the request list and the
    three refusal states.
- **`c11-platform-watch-read` and `c11-platform-runs` lose the `agentsapi` key.** Four packages
  held it, which would have put four tasks inside one `api.py`. Under rule 3 the two contract
  tasks declare every agents route once and these two serve their own modules.
- **`c11-ai-off-switch` loses the `searchscreen` key** (rule 5) **and narrows to tenant agent
  runs**: `c7-ask-switch` already writes the wrapper's check and the test that a platform call
  still goes through, so restating either here would have been two tasks writing one file. It
  takes `agentstasks` instead, for the pre-run check in `agents/tasks.py`; the Ask screen's
  off state stays `c7-ask-screen`'s.
- **`f03-T82` loses `agents/models.py` and `agents/watch-sweeper/v2/prompt.md`** and gains
  `agents/scope.py` (ruling 10).
- **`c11-fe-research-requests` covers the tenant panel only.** The console's re-tag request
  form moves to `c11-fe-console-batch-review-b`, which already holds `consoleq` and draws the
  batch it produces; two tasks would otherwise have written the same console surface.
- **`c11-security-policy` splits along the zone boundary**: the row and its migration are the
  tenants app's (`mig:tenants`), the read and write routes are `ten`, and every enforcement of
  either policy is identity's (`idp`), in `c11-credential-policy` and `c11-session-policy`.
- **`c11-runner-managed-agents` leaves the wave plan** and keeps its held state with ruling 4's
  reason.
- **`c11-fe-console-batch-review` loses `c11-e2e-seed` from its depends-on.** It owns no
  journey — PRO-S8's `@e2e` half is `c11-e2e-definitions-requests-b`'s — so it needs the
  screen's own data, not the E2E seed, and waiting on the seed would have held the console
  screen three waves for nothing.
- **Each E2E task gets its own helper file** (`support/agent-controls.ts`,
  `agent-budget.ts`, `agent-definitions.ts`, `agent-requests.ts`), because four tasks
  sharing one helper would collide in the two waves that run two journeys side by side.
- **`c11-cards-agents` and `c11-cards-security-batch` split by card file**, so no two card
  tasks write one HTML file.

### Changes from the two critiques

**From the parallelism critique**

1. Four packages held `agentsapi`; the contract chain of rule 3 now holds it twice and no
   logic task touches `api.py`.
2. `c11-fe-admin-agents` and `c11-fe-agents-budget-ai` both hold `agentsfe` and were in
   adjacent waves with no ordering; rule 4 names the order and they never share a wave.
3. `f03-T82` and `c11-tenant-agent-controls-a` both owned `backend/apps/agents/models.py`;
   ruling 10 moves `f03-T82` off it entirely.
4. `c11-batch-proposals` held `apply` and `prop` together while `c4-approve-apply` may still
   be settling; only `-b` holds `apply`, and it is one wave after `-a`.
5. `c11-security-policy`, `c11-credential-policy` and `c11-session-policy` all held `idp` in
   one region of the plan; the split above leaves `idp` to the identity pair, serialized.
6. Four E2E tasks sat in two waves with three other E2E-running tasks; they are now spread so
   at most three E2E stacks run at once (the runbook's memory ceiling).
7. `c11-run-scheduler` depends on `c10-notifications-api`, a cross-chunk dependency the wave
   numbers hid; it is named in the preconditions and given a contingency.
8. `c11-e2e-seed` was scheduled before `c11-batch-proposals`, whose batch it must seed; it
   moves after both halves.
9. Two design-card packages each wrote two card files; each is split by file so two card tasks
   can run side by side.

**From the coverage critique**

1. AGT-S8, ID-S16 and ID-S17 had no owning package in section 3.3; they are now
   `c11-runner-adapter`, `c11-credential-policy-a` and `c11-session-policy`.
2. PRO-S8's two halves had no owners; they are `c11-batch-proposals-b` and
   `c11-e2e-definitions-requests-b`.
3. Nothing proved the platform fence itself — that a tenant cannot switch off, pause,
   re-scope, re-cadence, re-budget or re-define one of bleqq's agents. AGT-S14 is new and
   `c11-platform-agent-settings-a` owns it.
4. Nothing owned rewording AGT-S4, AGT-S5, AGT-S6 and AGT-S11 to the split.
   `c11-tenant-agents-contract-b` does AGT-S5, AGT-S6 and AGT-S11 in one edit to
   `agents/app.md`. **AGT-S4's rewording goes to `c11-platform-agent-settings-b`**, the task
   that un-skips it: the two sit in the same wave, so a scenario reworded in one and tested in
   the other would have needed an ordering the plan did not have, and a task must not write
   its test against wording that has not landed.
5. The `retag` research kind (INPUT_DELTAS section 5) and the `obligation_scope` proposal kind
   (ruling 14) had no owner; they are `c11-tenant-agents-contract-a` and
   `c11-batch-proposals-contract-a`. `obligation_scope` is a member of the code enum
   `apply()` branches on, not a vocabulary row, so it needs three owners rather than one: the
   enum member is `c11-batch-proposals-contract-a`'s, its named payload schema
   `c11-batch-proposals-contract-b`'s, and the `apply()` branch `c11-batch-proposals-b`'s.
6. The database refusal of a `tenant_agent` pointing at a platform definition had no test
   owner; it is `c11-tenant-agents-contract-a`'s, at the database and at the route.
7. No task deleted chunk 11's `contract_drift_pending.txt` lines; each contract and logic task
   deletes its own, and the close proves none is left.
8. Nothing proved that no chunk 11 route still answers 501, and nothing measured the coverage
   floors; both are `c11-chunk-close`'s.
9. The run's budget check had no place to stand: a cap reached mid-run must stop the run, not
   only the next one. `c11-run-scheduler-b` owns both points and its test drives the second.
10. AGT-S6's "the admin is notified" had no notification owner; `c11-run-scheduler-b` calls
    `c10-notifications-api`'s `notify()` and the contingency covers a late chunk 10.
11. ADM-01's Agents and Security panels and ADM-02's Agent definitions surface had no task
    naming ADM-S1 and ADM-S4; the three frontend tasks extend them without un-skipping.
12. `agent_version`'s immutability was a convention, not a structure; it is an
    `AppendOnlyModel` with the trigger, so AGT-S4's "earlier runs still reference 3" cannot be
    broken by a later edit.
13. AGT-02's "agents read vocabularies at run start" had no owner for a **tenant** agent: the
    scope was validated when the admin saved it and never again. `f03-T82` now drops a key
    retired since, records it on the run, and keeps the row's own choice visible.

### Contingency

- **If `c10-notifications-api` is late**, `c11-run-scheduler-b` builds the cap check, the pause
  and the audit row, leaves the notification behind one call to `notify()` that the test
  asserts is made, and stops at that green point (parallel-plan rule 9). AGT-S6's
  `@integration` half is un-skipped without the notification line, which
  `c11-e2e-agent-controls-b` then asserts once chunk 10 lands; `c11-chunk-close` names it.
- **If `c7-ask-switch` is late**, `c11-ai-off-switch` cannot start: there is no column, and no
  check in the wrapper, to extend.
  Everything else proceeds and the close cannot run.
- **If `r1-readiness` has not run**, the proposal-door and identity tasks hold
  (`c11-batch-proposals-contract-a` and `-b`, `c11-batch-proposals-a` and `-b`,
  `c11-credential-policy-a` and `-b`, `c11-session-policy`). The agents half of the chunk is
  independent of all eight and proceeds.

## Waves

Tasks in one wave have disjoint owned paths and share no serialization key. Dispatch is by
readiness: a task starts as soon as everything in its depends-on has merged and its keys are
free, whatever wave it sits in here.

1. `c11-cards-agents-a`, `c11-cards-agents-b`, `c11-cards-security-batch-a`,
   `c11-cards-security-batch-b`, `c11-agent-definitions-contract-a`,
   `c11-agent-definitions-contract-b`, `c11-security-policy-a`,
   `c11-batch-proposals-contract-a`, `c11-runner-adapter`
2. `c11-tenant-agents-contract-a`, `c11-agent-definitions`, `c11-security-policy-b`,
   `c11-batch-proposals-contract-b`, `c11-platform-agent-settings-a`
3. `c11-tenant-agents-contract-b`, `c11-platform-agent-settings-b`, `c11-credential-policy-a`
4. `c11-tenant-agent-controls-a`, `c11-platform-watch-read`, `c11-run-history`,
   `c11-credential-policy-b`, `c11-batch-proposals-a`, `c11-fe-console-agent-definitions-a`
5. `c11-tenant-agent-controls-b`, `c11-session-policy`, `c11-batch-proposals-b`,
   `c11-fe-admin-security-a`, `c11-run-scheduler-a`
6. `f03-T82`, `c11-platform-runs`, `c11-fe-admin-security-b`
7. `c11-run-scheduler-b`, `c11-fe-console-agent-definitions-b`
8. `c11-ai-off-switch`, `c11-research-requests-a`, `c11-fe-admin-agents-a`
9. `c11-research-requests-b`, `c11-fe-admin-agents-b`, `c11-e2e-seed`
10. `c11-fe-agents-budget-ai`, `c11-fe-console-batch-review-a`
11. `c11-fe-research-requests`, `c11-fe-console-batch-review-b`, `c11-e2e-agent-controls-a`
12. `c11-e2e-agent-controls-b`, `c11-e2e-definitions-requests-a`
13. `c11-e2e-definitions-requests-b`
14. `c11-security-review-a`, `c11-security-review-b`
15. `c11-review-fixes`
16. `c11-chunk-close`

Held, in no wave: `c11-runner-managed-agents` (ruling 4 and `k-managed-agents`).

Why the waves fall this way:

- **The `mig:agents` chain** runs one task at a time: `c11-agent-definitions-contract-a` (1),
  `c11-tenant-agents-contract-a` (2). Nothing else in the chunk adds an agents migration.
- **The `agentsapi` chain** is rule 3's pair: `c11-agent-definitions-contract-b` (1),
  `c11-tenant-agents-contract-b` (3). `-b` of the first shares wave 1 with `-a` because the
  schemas are Pydantic and reference no model.
- **The `agentsfe` chain** is rule 4's order, one task per wave:
  `c11-fe-console-agent-definitions-a` (4), `-b` (7), `c11-fe-admin-agents-a` (8), `-b` (9),
  `c11-fe-agents-budget-ai` (10), `c11-fe-research-requests` (11). It is the chunk's longest
  chain and it sets the chunk's length; nothing else waits on it.
- **The `idp` chain**: `c11-credential-policy-a` (3), `-b` (4), `c11-session-policy` (5).
- **The `prop`/`apply` chain**: `c11-batch-proposals-contract-b` (2), `c11-batch-proposals-a`
  (4), `-b` (5). `c11-batch-proposals-contract-a` holds only `mig:proposals` and sits in
  wave 1.
- **`agentstasks`** is held once at a time: `c11-run-scheduler-a` (5), `-b` (7),
  `c11-ai-off-switch` (8), with `f03-T82` (6) between the first two because the tenant half
  builds its scope with `scope.py` and the scope task needs a platform run to prove its last
  line against.
- **`c11-e2e-seed` sits in wave 9**, after the definitions it seeds (2), the tenant agents (3),
  the controls (5) and both halves of the batch proposal (4 and 5), so its seeded rows are
  made by the real functions rather than by hand.
- **The E2E stacks** are waves 11, 12 and 13, at most two at a time, inside the runbook's
  memory ceiling. Waves 6 and 7 each run one journey grep (`ADM-S1`, `ADM-S4`) beside
  backend-only tasks.
- **The security reviews split by area** so they run side by side in wave 14: `-a` reads the
  agents diff, `-b` the identity and proposals diff.

## Open questions

- **q-tenant-definition — a confirmation, not a choice to make** (a product invariant is at
  stake, so it still goes to Alex; the build does not wait, and nothing is held for it). Item
  14 says a bank "can add their own agents to monitor specific things they have a requirement
  for", and `PARALLEL_PLAN` section 3.3.1 reads that as a **tenant-created definition**.
  `Agent` is a `LibraryModel`. A tenant-created definition row is therefore a tenant writing
  the shared library, which "proposals are the only door into the library" forbids and which
  no proposal kind covers. AGT-03 and ADR 0053 both say the versioned definitions stay the
  platform's.

  **The inputs have already answered it.** `docs/inputs/schema.sql` PART 3 ships
  `agent.scope` (`platform` | `tenant`) and `agent.tenant_configurable` on the `agent` table
  itself, under the comment "Agent definitions are platform-owned and versioned", and
  `agent_version` carries "Tenants never edit instructions or tools, they get a version".
  That **is** Option A, in the contract this build is written from. `PARALLEL_PLAN` section
  3.3.1 is the outlier, and it is the one source of the four that CLAUDE.md section 2's
  precedence puts last. So Option A is not a recommendation the plan invented; it is the
  input's shape, and B and C are below only so the cost of overturning it is on the page.

  **Option A (the input's own shape, and what the build does, so nothing waits).** bleqq
  authors every definition. A definition carries `scope` (`platform` or `tenant`) and
  `tenant_configurable`, as `schema.sql` PART 3 already has it. A bank "adds its own agent" by creating a
  `tenant_agent` row against a **tenant-scoped** definition and giving it its own cadence,
  scope, sources and budget. No tenant writes a library row, no bank authors a prompt or a
  tool list, and the fence is untouched. What a bank cannot do is invent a kind of agent bleqq
  has not published.

  **Option B.** Tenant-authored definitions in a separate tenant-zone table
  (`tenant_agent_definition`), never a library row, with the prompt screened as untrusted
  input before every run. It gives a bank the freedom the sentence suggests, and it adds a
  prompt-injection surface pointed at bleqq's own runner and model budget, a second definition
  reader, and a review of who pays for a prompt a bank wrote. It needs its own ADR and a
  security review of its own.

  **Option C.** No tenant agents in R2; AGT-04's controls arrive with private sources in
  chunk 13.

  This shapes `c11-tenant-agents-contract-a`'s model and `c11-tenant-agent-controls-a`'s
  create route. Under Option A both are built as written below. If Alex chooses B, those two
  tasks are rebuilt and one table, one screen and one security review are added; nothing else
  in the chunk changes.

- **Non-blocking, to confirm** (defaults are taken and the build does not wait);
  `c11-chunk-close` writes each into `docs/TODO_FOR_alex.md`:
  - D-61's two open details, both taken as proposed: a tenant's AI off switch stops only the
    bank's own agents and AI features, and a bank's own agents run under the bank's own
    monthly cap while bleqq's general watch runs at bleqq's cost.
  - That publishing a definition version and changing a platform agent's settings each ask for
    a passkey step-up, although playbook 4.2 does not list them.
  - **AGT-S7's actor.** `PARALLEL_PLAN` line 1132 gates a research request on "`agents.manage`
    **or** `proposals.create`", and item 10 uses the same pair for requesting a private source.
    PRD section 6 grants `agents.manage` to Admin alone and `proposals.create` to the
    Compliance officer alone, so the pair is not one actor but two different roles. **The plan
    takes `agents.manage` alone** and rewords AGT-S7 to a tenant admin (ruling 5), for two
    reasons: a research request starts a run that spends the bank's agent budget and is
    steered by the bank's agent settings, which is what `agents.manage` is for, and adding
    `proposals.create` would let a compliance officer spend that budget with no control over
    the cap. Item 10's pair is about a **private source** in chunk 13, a different act, and is
    left alone. Reversing this needs no new permission — only the `or` on the three research
    routes of `c11-tenant-agents-contract-b` — so it is a confirmation, not a hold. If Alex
    wants the compliance officer to be able to ask, say so and that one word goes in.
  - That a bank with no agent of its own cannot make a research request, because it cannot
    command a platform agent (`PARALLEL_PLAN` section 3.3.1 already states this default).
  - That item 8's credential-compliance frontend package is deferred to chunk 13, which leaves
    ID-07 at `in_progress` when the chunk closes (see Cut).

- **Answered, not asked: `c11-runner-managed-agents`.** It is held, and nothing about it is
  open. Item 7 of `OWNER_RECOMMENDATIONS.md` is marked "OK" in Alex's answers of 2026-09-19,
  D-54 and ADR 0047 record it, and together they refuse `managed_agents` on every deployed
  environment except `ENVIRONMENT=test` and put production agents in our own worker on Bedrock
  in an EU region. So the plan states it as settled (ruling 4) rather than putting it back to
  Alex. What does still need a person is a different thing and is logged as such: the ADR 0008
  amendment and the Verification log row for the Agent SDK leg, which the held task names and
  which `c11-chunk-close` writes into `docs/TODO_FOR_alex.md` as held work, not as a question.

- **Rejected, from the parallelism critique**: merging `c11-platform-agent-settings` and
  `c11-agent-definitions-contract` because both concern bleqq's agents. They own different
  modules and different scenarios, the contract must land before anything serves it, and
  together they exceed the limit.

- **Rejected, from the coverage critique**: serving "Spend this month" as zero for a bank with
  no agents of its own, so the meter always renders. A figure of zero beside a cap the bank has
  not set says the bank is spending nothing on agents, which is true but reads as though
  bleqq's watch were switched off. The panel shows the cap control and a line naming bleqq's
  watch as running at bleqq's cost instead.

- **Rejected, from the coverage critique**: adding a tenant "request a cadence change" flow for
  bleqq's agents so a bank has some say. ADR 0053 deliberately does not do this, and a request
  nobody can grant is a worse answer than the read-only panel.

## Tasks

### c11-cards-agents-a: the design card for the bank's own agents

**Requirements:** AGT-04, AGT-05, ADM-01
**Scenarios:** none
**Depends on:** none

Draw `design/screens/admin-agents.html` on the tenant shell, from `design/prototype/index.html`
`vAgents()` and the design contract in `design/README.md` and
`design/system/pills-and-labels.md`. The card decides look, reading and flow, never the rules
(CLAUDE.md section 2).

The screen has two halves and the card must make the difference obvious without a sentence of
policy on screen:
- **Our agents**: one panel per agent the bank added, with its status pill (`Off`, `On`,
  `Paused` — tone by kind, never chosen by a person), the version pill, what it covers, what it
  writes to, next run, the cadence control, Switch on/off, Pause/Resume, Run now, Stop run, and
  "Recent runs" with time, status, cost, trigger, who asked, findings and proposals.
- **Spend this month**: the figure, the cap, the meter, "Set cap", and a line that names
  bleqq's watch as running at bleqq's cost so the number is not misread (ruling 3 and the
  rejected zero-meter above).
- The empty state for a bank with no agent of its own: what adding one is for, the "Add an
  agent" control, and the read-only bleqq panel still present above it.

Not on this card: any control over one of bleqq's agents, a prompt, a tool list, a per-agent
spend total, a private-sources panel (chunk 13). The prototype's "an administrator or the
compliance officer" line is not copied: `agents.manage` is the Admin role's (ruling 5).

Every string is written for the message catalogs by the screen task, not here; the card shows
the copy so the screen task can lift it.

**Owned paths:**

- `design/screens/admin-agents.html`

**Done when:**

- The card renders in light and dark, at 375 px and at desktop width, with no horizontal
  scroll and no tone chosen by a person.
- Every pill on it exists in `design/system/pills-and-labels.md` with its tone and slot; a new
  one is added there with its reason.
- The card shows no control that would reach a platform agent, and the read-only panel carries
  the next run and the last run's status and nothing more: no prompt, tool, model, version
  internals, budget, cost, findings, proposal counts or setting.
- `c11-chunk-close` moves the UI plan's row for `admin-agents.html` to "designed"; this task
  edits no plan file (plan-wide rule 6).

**Gates:**

- Open the card in a browser in both themes and both widths; no build step is involved.
- `cd frontend && npm run lint` if any shared style file changed (none is expected).

**Invariants:**

- Six pill tones, chosen by slot or kind, never by a person.
- Screen copy says what the user is doing: no requirement IDs and no restated invariants on
  screen.
- The design reproduces the prototype's flow; it never decides a rule.

### c11-cards-agents-b: the design card for the console's agent definitions

**Requirements:** AGT-03, ADM-02
**Scenarios:** none
**Depends on:** none

Draw `design/screens/console-agent-definitions.html` on the console shell
(`design/screens/console-shell.html`), for a platform admin holding
`agent_definitions.manage`:
- The definition list: key, kind, scope (`Platform` or `Tenant`), current version, active.
- One definition: its versions with `version_no`, model, change note, who published and when,
  and which are retired; "Publish a new version" with its change note and the step-up notice.
- The platform settings panel for a platform-scoped definition: cadence, the jurisdictions it
  sweeps, and its budget, each audited, each with the "changes this for every bank" notice in
  plain words.
- The platform runs panel: recent runs with status, cost, findings, proposals and source
  coverage, linking to the console Sources page chunk 5 built.

Not on this card: any tenant figure, any bank's name beside a run, a prompt body (the version
names its prompt file; the body is repository content, not a screen).

**Owned paths:**

- `design/screens/console-agent-definitions.html`

**Done when:**

- The card renders in light and dark, at 375 px and at desktop width.
- Every pill exists in `design/system/pills-and-labels.md` with its tone and slot.
- No tenant name, count or figure appears anywhere on the card.
- `c11-chunk-close` moves the UI plan's row for `console-agent-definitions.html` to
  "designed"; this task edits no plan file (plan-wide rule 6).

**Gates:**

- Open the card in a browser in both themes and both widths.

**Invariants:**

- Pills only through the documented tones and slots.
- Tenant content never reaches a platform surface.

### c11-cards-security-batch-a: the design card for the tenant security policy

**Requirements:** ID-07, ID-08, ADM-01
**Scenarios:** none
**Depends on:** none

Draw `design/screens/admin-security.html` on the tenant shell, for an admin holding
`security.manage`, from ADR 0048 and ID-08:
- **Passkeys we accept**: `Any passkey` or `Device-bound, from the list`, the authenticator
  allow-list picker, the notice date with its default of 14 days ahead, and the plain-words
  explanation that new registrations bind at once and existing passkeys stop working on the
  notice date.
- **Sessions**: idle and absolute limits with the platform maximum shown beside each.
- The step-up notice on Save, and the "this would lock you out" refusal state (409) drawn as a
  state, not as an error banner.

Not on this card: the IP allow-list (ID-13, chunk 13), SSO (chunk 13), retention (chunk 12).
Each is named in the card's header comment with its chunk, as `tenant-roadmap.html` does.

**Owned paths:**

- `design/screens/admin-security.html`

**Done when:**

- The card renders in light and dark, at 375 px and at desktop width.
- The lock-out refusal and the notice-date states are both drawn.
- The header comment names the panels that arrive in chunks 12 and 13.
- `c11-chunk-close` moves the UI plan's row for `admin-security.html` from "chunk 13, card
  pending" to "chunk 11, designed" (ruling 7); this task edits no plan file (plan-wide
  rule 6).

**Gates:**

- Open the card in a browser in both themes and both widths.

**Invariants:**

- Six pill tones by slot or kind; no string literal decides a rule.
- No password appears anywhere, in any state.

### c11-cards-security-batch-b: the design card for the console's batch review

**Requirements:** PRO-04, AGT-05, ADM-02
**Scenarios:** none
**Depends on:** none

Draw `design/screens/console-queue-batch.html`, the batch variant of the console queue
(`design/screens/console-queue.html`), for a library editor holding `proposals.review`:
- The batch header: what was asked, who asked, how many rows, and the source of the request.
- The preview table: one row per record with before and after, each row approvable or
  rejectable on its own, with a rejection reason from the vocabulary.
- "Approve the rest", "Reject all", and the step-up notice.
- The result state: how many changed, how many did not, and the link to the audit entry.
- The "Ask for a re-tag" form that creates the request, with its near-duplicate hint from the
  vocabulary picker.

**Owned paths:**

- `design/screens/console-queue-batch.html`

**Done when:**

- The card renders in light and dark, at 375 px and at desktop width, with a table that stays
  readable at phone width.
- Row-level and whole-batch decisions are both drawn, and the four-eyes refusal is a drawn
  state.
- `c11-chunk-close` moves the UI plan's batch row to "designed"; this task edits no plan
  file (plan-wide rule 6).

**Gates:**

- Open the card in a browser in both themes and both widths.

**Invariants:**

- A rejection carries a reason from a vocabulary row, never a free phrase in code.
- Pills only through the documented tones and slots.

### c11-agent-definitions-contract-a: the version row and the platform columns

**Requirements:** AGT-03
**Scenarios:** none
**Depends on:** `c5-contract-models-agents` (merged), `c5-chunk-close`
**Security review:** yes (a library table, a new append-only ledger, the platform fence's first
column)
**Keys:** `mig:agents`

Carries the stop-and-report instruction. Extend `backend/apps/agents/models.py` and add
`migrations/0002_agent_versions.py`, from `docs/inputs/schema.sql` PART 3 and
`docs/inputs/data-model.md`:

- `AgentVersion(LibraryModel, AppendOnlyModel)`: `agent`, `version_no`, `model`,
  `prompt_path` (the file inside the version folder, not a body), `tools` (`JSONField` with an
  inline suppression naming its schema, `AgentToolList`), `external_agent_id`, `change_note`,
  `published_by`, `published_at`, `retired_at`, unique `(agent, version_no)`,
  `Meta.ordering = ["agent", "-version_no"]`. The append-only trigger comes from
  `migration_helpers.append_only_trigger_operations` with `retired_at` as its one permitted
  update, so a published version cannot be rewritten under a run that points at it.
- `Agent` gains the schema v0.3 columns that the fence and the scheduler read: `scope`
  (`platform` | `tenant`, default `platform`), `tenant_configurable` (default false),
  `runtime`, `default_cadence` and `writes_to`. A `scope='platform'` row carries
  `tenant_configurable = false`, enforced by a CHECK: the platform fence starts in the
  database, not in a route. It also gains the two platform settings a platform agent carries
  in place of a tenant's controls, with no tenant column beside either: `platform_scope`
  (`JSONField` with an inline suppression naming `PlatformAgentScope`: the jurisdiction keys
  the agent sweeps) and `platform_monthly_budget`. A CHECK refuses both on a
  `scope='tenant'` row, so the two kinds of agent cannot borrow each other's settings.
- `AgentRun` gains the chunk 11 columns of schema v0.3: `agent_version_id`, `tenant_agent_id`
  (added by the next task's migration, named here as the forward reference),
  `trigger` (`schedule` | `manual` | `request` | `api`), `research_request_id`,
  `requested_by`, `external_session_id`, `budget_limit`, `changes_found`, `proposals_made`,
  `interrupted_at`, `interrupted_by`, `cost`, `tokens_in`, `tokens_out`. `agent_version_id` is
  written once, when the run opens.
- The migration applies `migration_helpers.rls_operations()` to `agent_version` as a library
  table and leaves `agent_run`'s existing split policy alone.

Also: add `AgentRuntime`, `AgentCadence` and `AgentScopeKind` to `apps/shared/kinds.py` with
their INPUT_DELTAS section 5 names and reasons, add `agent_version` to the guarded-table list
in `apps/shared/tests_rls.py` and to `tests_seed_integrity.py`, and write the INPUT_DELTAS
rows for ruling 1 (a definition is always the platform's, `scope` and `tenant_configurable`
carry it), ruling 3 (one tenant-wide cap, `tenant_agent.monthly_budget` not built) and
ruling 4 (`managed_agents` refused, the runner seam only), each naming the task that closes it.

**Owned paths:**

- `backend/apps/agents/models.py`
- `backend/apps/agents/migrations/0002_agent_versions.py`
- `backend/apps/agents/tests_models.py` (the new classes only)
- `backend/apps/shared/kinds.py` (its own entries only)
- `backend/apps/shared/tests_rls.py`, `tests_seed_integrity.py` (the guarded-table lists only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- As `cw_app`, UPDATE and DELETE on `agent_version` are refused and INSERT works, except that
  setting `retired_at` succeeds; a test proves all three on the app alias.
- A `scope='platform'` row with `tenant_configurable = true` is refused by the database, and
  so is a `scope='tenant'` row carrying `platform_scope` or `platform_monthly_budget`.
- `agent_version` is listed as a library table by the RLS guard, and a tenant session cannot
  write one.
- The kinds-only guard and the compliance lint are green, and each new kind's reason names
  what branches on it.
- Every new `JSONField` carries an inline suppression naming its schema.
- The task edits no file under `apps/agents/` other than the four named, so it can share a
  wave with the contract task.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*' (models.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing overwritten: a published version is an append-only row.
- Proposals are the only door into the library; this task adds a library table and no new
  writer of one.
- Enums in code are for kinds only; a type, status, tag or reason is a row.
- `Meta.ordering` on anything `.first()`ed; `JSONField` only with a named schema.

### c11-agent-definitions-contract-b: the console's agent routes, all answering not_built

**Requirements:** AGT-03, ADM-02
**Scenarios:** none
**Depends on:** `c5-contract-api-agent`, `c4-console-tenants-api`
**Keys:** `agentsapi`

Write the platform half of `backend/apps/agents/api.py` and `schemas.py` and mount the router
in `config/api.py` if chunk 5 has not. Every operation carries its auth class and permission
and calls a named function in the module that will build it, which answers 501 `not_built`
(parallel-plan rule 2):

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `listAgentDefinitions` | `GET /console/agents` | SessionAuth, `agent_definitions.manage` | `agents/definitions.py` |
| `getAgentDefinition` | `GET /console/agents/{agentKey}` | SessionAuth, `agent_definitions.manage` | `agents/definitions.py` |
| `publishAgentVersion` | `POST /console/agents/{agentKey}/versions` | SessionAuth, `agent_definitions.manage`, step-up | `agents/definitions.py` |
| `retireAgentVersion` | `DELETE /console/agents/{agentKey}/versions/{versionNo}` | SessionAuth, `agent_definitions.manage`, step-up | `agents/definitions.py` |
| `getPlatformAgentSettings` | `GET /console/agents/{agentKey}/settings` | SessionAuth, `agent_definitions.manage` | `agents/platform.py` |
| `updatePlatformAgentSettings` | `PUT /console/agents/{agentKey}/settings` | SessionAuth, `agent_definitions.manage`, step-up | `agents/platform.py` |
| `listPlatformRuns` | `GET /console/agent-runs` | SessionAuth, `agent_definitions.manage` | `agents/platform.py` |

Schemas, camelCase through `CamelSchema`, app-prefixed where the shape is this app's:
`AgentDefinition`, `AgentDefinitionDetail`, `AgentVersion`, `AgentVersionInput`,
`PlatformAgentSettings`, `PlatformAgentSettingsInput`, `PlatformRunListItem`,
`PlatformRunQuery` (the shared `limit`, default 20, maximum 100). `AgentRunStats` already
exists and is reused, not restated.

Also: add the seven routes to the route lists in `apps/shared/permissions.py`, add no entry to
`UNGATED_BY_DESIGN`, and add this task's lines to `backend/scripts/contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/agents/api.py` and `backend/apps/agents/schemas.py` (the console operations only)
- `backend/apps/agents/tests_contract.py`
- `backend/config/api.py` (the router mount only)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- The seven operations appear in `openapi.json` with the ids above and answer 501 `not_built`
  behind their real gate.
- A session without `agent_definitions.manage` gets 403 with `requiredPermission`, an
  anonymous request 401, and an API key of any scope 403 — each before the 501, proved per
  route.
- A tenant session gets 403 on every one of them, proved per route: no tenant principal
  reaches a definition, in any release (AGT-03).
- `publishAgentVersion`, `retireAgentVersion` and `updatePlatformAgentSettings` answer 403
  `step_up_required` without a fresh assertion, before the 501.
- The route-permission guard is green and lists no ungated route.
- `bash generate-types.sh` produces types for all seven without the task committing them.
- The diff stays inside the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`.
- Every route has a permission; nothing joins `UNGATED_BY_DESIGN`.
- Errors are RFC 9457 with a `code`; no trace ever leaves.
- Step-up where playbook 4.2 and this plan's default list it.

### c11-security-policy-a: the tenant security policy row

**Requirements:** ID-07, ID-08
**Scenarios:** none
**Depends on:** `c8-tenants-contract`, `r1-readiness`
**Security review:** yes (a tenant table holding an authentication policy)
**Keys:** `mig:tenants`

Add `SecurityPolicy(TenantModel)` to `backend/apps/tenants/models.py` with
`migrations/000n_security_policy.py`, from ADR 0048 and ID-08:

- `credential_policy` (`any_passkey` | `device_bound`), `allowed_authenticators` (a list of
  AAGUIDs, `JSONField` with an inline suppression naming `AuthenticatorAllowList`),
  `device_bound_from` (nullable date), `session_idle_minutes`, `session_absolute_hours`,
  `updated_by`, `updated_at`, one row per tenant (unique `tenant`),
  `Meta.ordering = ["tenant"]`.
- The migration applies `migration_helpers.rls_operations()` and adds the table to the guarded
  list in `apps/shared/tests_rls.py`.
- A tenant with no row reads the platform defaults; the row is created on first write, never by
  a migration backfill, so a tenant that never set a policy has nothing to export or delete.
- `CredentialPolicy` and `SessionPolicyField` are not kinds: `credential_policy` is a
  tier-one kind (the code branches on it) and goes in `apps/shared/kinds.py`; the limits are
  integers bounded by settings.

**Owned paths:**

- `backend/apps/tenants/models.py`
- `backend/apps/tenants/migrations/000n_security_policy.py`
- `backend/apps/tenants/tests_models.py` (the new class only)
- `backend/apps/shared/kinds.py` (its own entry only)
- `backend/apps/shared/tests_rls.py` (the guarded-table list only)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`,
  `docs/runbooks/RAILWAY_VARIABLES.md`
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- The RLS guard lists `security_policy` as forced tenant-only, and a cross-tenant read returns
  nothing under `cw_app`.
- `SESSION_IDLE_MAX_MINUTES` and `SESSION_ABSOLUTE_MAX_HOURS` are settings with env overrides
  and appear in `.env.example` and `RAILWAY_VARIABLES.md`.
- A tenant with no row reads the platform defaults, proved by a test that queries the policy
  for a fresh tenant.
- The kinds-only guard and the compliance lint are green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Tenant tables carry `tenant_id` under enabled and forced row-level security; `cw_app`
  cannot bypass it.
- No passwords, ever: nothing on this row can weaken the passkey-only rule, only narrow it.
- Every threshold is a setting with an env override.

### c11-batch-proposals-contract-a: the batch rows and the obligation_scope kind

**Requirements:** PRO-04, AGT-05
**Scenarios:** none
**Depends on:** `c4-library-updates`, `c5-library-provenance-models`,
`c5-library-proposal-kinds`, `r1-readiness`
**Security review:** yes (the proposal door)
**Keys:** `mig:proposals`

Carries the stop-and-report instruction. Extend `backend/apps/proposals/models.py` with a
migration:

- `ProposalBatchRow(LibraryModel, AppendOnlyModel)`: `proposal` (the batch's single parent
  proposal row), `subject_type`, `subject_id`, `before` and `after` (`JSONField`s with an
  inline suppression naming `ProposalBatchRowPayload`), `decision`
  (`pending` | `approved` | `rejected`), `rejection_reason` (a vocabulary row, nullable),
  `decided_by`, `decided_at`, unique `(proposal, subject_type, subject_id)`,
  `Meta.ordering = ["proposal", "subject_type", "subject_id"]`. Append-only with `decision`,
  `rejection_reason`, `decided_by` and `decided_at` as the permitted updates, so a decided row
  cannot be silently re-decided.
- `Proposal` gains `is_batch` (default false) and `row_count`. Nothing else about a proposal
  changes: four eyes, the rejection reason, the audit row and the apply path stay chunk 4's.
- The `obligation_scope` proposal kind chunk 4 cut (parallel-plan ruling 14). `ProposalKind`
  in `backend/apps/proposals/models.py` is a **code enum** that `apply()` branches on, already
  allowlisted in `apps/shared/kinds.py` ("PRO-01: what a proposal changes; apply() branches on
  it"), and `c5-library-proposal-kinds` added the chunk 4 members to it the same way. So this
  is a new member, `OBLIGATION_SCOPE = "obligation_scope"`, not a seeded vocabulary row: there
  is no `proposals/seeds/` directory and none is created. `apps/shared/kinds.py` needs no new
  entry, because the class is already listed. Its named payload schema is
  `c11-batch-proposals-contract-b`'s (it owns `proposals/schemas.py`) and the `apply()` branch
  is `c11-batch-proposals-b`'s; this task adds the member, widens the `kind` choices and
  proves the existing kinds still round-trip.

**Owned paths:**

- `backend/apps/proposals/models.py`
- `backend/apps/proposals/migrations/000n_proposal_batches.py`
- `backend/apps/proposals/tests_models.py` (the new class and the new kind member only)
- `backend/apps/shared/tests_rls.py`, `tests_four_eyes.py` (the guarded-table lists only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- As `cw_app`, UPDATE of anything other than the four decision columns on
  `proposal_batch_row` is refused, DELETE is refused and INSERT works.
- A second decision on an already-decided row is refused, proved by a test.
- `obligation_scope` is a member of `ProposalKind`, appears in the `kind` choices and in the
  migration's altered field, and the kinds-only guard stays green with no new entry in
  `apps/shared/kinds.py`.
- `openapi.json` **does** change, because the kind is an enum inside a schema rather than a
  vocabulary row: `bash generate-types.sh` is run so the drift check passes, and both
  generated files are reverted for the main agent to regenerate at the merge (plan-wide
  rule 2).
- The four-eyes guard lists the batch parent, and a batch approved by its proposer answers
  409 `four_eyes_violation` at the model level.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; revert both generated files
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Proposals are the only door into the library; a batch is one proposal, not a second door.
- Four eyes, enforced by a check constraint, with a passkey step-up on approval.
- Nothing overwritten: append-only rows with a trigger.
- Reasons are vocabulary rows, never phrases in code.

### c11-runner-adapter: the runner seam, its events and interrupt

**Requirements:** AGT-06
**Scenarios:** AGT-S8 (`@integration`, un-skipped)
**Depends on:** `c5-agent-runs`
**Security review:** yes (an external executor writing run state)
**Keys:** `runner`

Finish `backend/apps/shared/adapters/agent_runner.py`, which Phase 0 left as a seam, so the
app is the scheduler of record:

- `RunHandle` carries a `RunStatus` kind now that `apps.agents` defines them, plus
  `started_at` and the runner's own external id.
- `AgentRunnerAdapter` gains `poll(handle)` and a documented event shape,
  `RunnerEvent(run_id, status, stats, cost, tokens_in, tokens_out, error)`, which is the only
  thing a runner may tell the app. A runner never writes a row; one function in
  `backend/apps/agents/runner_events.py` applies an event to the run inside one transaction
  through `record()`, refuses an event for a run that is already finished, and refuses an
  event whose run belongs to another zone than the event's source.
- `MockAgentRunner` completes a run immediately with no findings and emits the events a test
  needs, deterministically, seeded from the run id so a test never depends on the clock.
- `ManagedAgentsRunner` keeps its `NotImplementedError` with ruling 4's reason written into
  the docstring: D-54 refuses `managed_agents` on every deployed environment, so it cannot be
  the first real runner.
- The adapter changes no boot guard. `MOCK_ADAPTER_SETTINGS` already refuses
  `AGENT_RUNNER=mock` outside the named test environment, and `c11-runner-adapter` adds the
  test that proves it for this setting specifically, which is AGT-S8's last line.

`AGT-S8` is reworded by this task in `agents/app.md`: "the beat schedule fires for a tenant"
becomes "the beat schedule fires", because both platform and tenant runs start through the
same seam and a platform run has no tenant (item 14).

**Owned paths:**

- `backend/apps/shared/adapters/agent_runner.py`
- `backend/apps/agents/runner_events.py`
- `backend/apps/agents/tests_runner_events.py`
- `backend/apps/agents/tests_scenarios.py` (the AGT-S8 test only)
- `backend/apps/agents/app.md` (AGT-06's status cell and AGT-S8's wording only)

**Done when:**

- `test_agt_s8` is green, written before the code: a run started through the adapter is
  recorded before the runner answers, runner events update the run row, and booting with
  `AGENT_RUNNER=mock` outside the test environment is refused.
- An event for a finished run is refused and leaves the row alone, proved by a test.
- An event naming a run of another zone than its source is refused, proved with a platform run
  and a tenant run in the same test.
- Every event application writes an audit row through `record()` in the same transaction.
- `ManagedAgentsRunner` still raises, and a test pins the reason so the ruling cannot be
  quietly reversed.
- The diff touches no boot guard and no file under `backend/config/`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*,apps/shared/adapters/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- The app is the scheduler of record; the runner is an executor and writes no row.
- Audit and outbox rows in the same transaction as every write, through `record()`.
- Fetched and external content is untrusted: a runner event is validated at the boundary, not
  trusted because it came from our own executor.
- Tenant content never reaches a log: an event's error text is stored, never logged.

### c11-tenant-agents-contract-a: the tenant agent, the research request and the platform fence in the database

**Requirements:** AGT-04, AGT-05
**Scenarios:** none
**Depends on:** `c11-agent-definitions-contract-a`, `c5-contract-models-watch`,
`p03-consolidation`
**Security review:** yes (two new tenant tables and the fence that keeps a bank away from a
platform agent)
**Keys:** `mig:agents`

Carries the stop-and-report instruction. Add to `backend/apps/agents/models.py` with
`migrations/0003_tenant_agents.py`, from `schema.sql` PART 3 and ruling 1:

- `TenantAgent(TenantModel)`: `agent`, `enabled` (default false), `cadence` (`AgentCadence`),
  `run_weekday`, `run_hour`, `next_run_at`, `scope` (`JSONField` with an inline suppression
  naming `TenantAgentScope`: jurisdiction keys and term keys, never free text),
  `paused_at`, `paused_by`, `updated_by`, `updated_at`, unique `(tenant, agent)`,
  `Meta.ordering = ["tenant", "agent"]`, and the partial index
  `tenant_agent_due_idx ON (next_run_at) WHERE enabled AND paused_at IS NULL`.
  **The fence:** a database CHECK plus a trigger refuse a row whose `agent` has
  `scope='platform'` or `tenant_configurable = false`. A bank steers only a tenant-scoped
  definition (ruling 1). `monthly_budget`, `currency`, `pinned_version_id`, `environment` and
  `external_environment_id` are **not** built (the cut list).
- `ResearchRequest(TenantModel)`: `tenant_agent` (nullable for the console's `retag`
  request, which has no tenant agent), `requested_by`, `kind`
  (`run_now` | `check_source` | `check_url` | `research_topic` | `reverify` | `retag`),
  `topic`, `source`, `url`, `status`
  (`queued` | `running` | `done` | `failed` | `rejected` | `cancelled`), `result_summary`,
  `changes_found`, `created_at`, `completed_at`, `Meta.ordering = ["-created_at", "id"]`.
- `TenantAgentBudget(TenantModel)`: `monthly_cap`, `currency`, `updated_by`, `updated_at`,
  one row per tenant (ruling 3).
- `AgentRun.tenant_agent` and `AgentRun.research_request`, completing the forward reference
  the previous migration named.
- The migration applies `migration_helpers.rls_operations()` to all three new tables and adds
  them to the guarded list in `apps/shared/tests_rls.py`.

Also: add `ResearchRequestKind` (with `retag`, INPUT_DELTAS section 5), `ResearchRequestStatus`
and `RunTrigger` to `apps/shared/kinds.py`, and the three tables to
`apps/shared/tests_seed_integrity.py`.

**Owned paths:**

- `backend/apps/agents/models.py`
- `backend/apps/agents/migrations/0003_tenant_agents.py`
- `backend/apps/agents/tests_models.py` (the new classes only)
- `backend/apps/shared/kinds.py` (its own entries only)
- `backend/apps/shared/tests_rls.py`, `tests_seed_integrity.py` (the guarded-table lists only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- A `tenant_agent` row pointing at a `scope='platform'` definition is refused **by the
  database**, proved by a test that inserts directly on the app alias, not only through a
  route.
- A `tenant_agent` pointing at a tenant-scoped definition with `tenant_configurable = false`
  is refused the same way.
- The RLS guard lists `tenant_agent`, `research_request` and `tenant_agent_budget` as forced
  tenant-only, and every cross-tenant read returns nothing under `cw_app`.
- `TenantAgentScope` accepts only keys that exist in the live vocabularies, refusing an
  unknown one with 422 `unknown_key` and the valid list (AGT-02), proved at the model's
  validator.
- The kinds-only guard and the compliance lint are green, and `ResearchRequestKind`'s reason
  names `retag` and the batch it produces.
- No column from the cut list exists.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*' (models.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Two zones: tenant tables carry `tenant_id` under enabled and forced row-level security.
- A bank never steers one of bleqq's agents, and the database says so before any route does.
- Agents use existing vocabulary keys only; store and compare keys, never labels.
- `JSONField` only with a named schema; `Meta.ordering` on anything `.first()`ed.

### c11-agent-definitions: the published versions of bleqq's agents

**Requirements:** AGT-03
**Scenarios:** none
**Depends on:** `c11-agent-definitions-contract-a`
**Keys:** `sweeper`

Grow the versioned definition folders under `backend/agents/` to what a published
`agent_version` row needs, and teach the reference seed to load them:

- `backend/agents/watch-sweeper/v1/definition.yaml` gains the top-level scalars the seed reads
  for a version: `model` and `change_note`, beside the `id`, `version`, `kind`, `status` and
  `description` it already carries. E5's own reader stays (parallel-plan ruling 19); this task
  adds the two field names to it and to the PyYAML cross-check test, and never replaces it.
- `definition.yaml` gains `scope: platform` and `tenant_configurable: false`, which the seed
  writes onto the `agent` row, so the platform fence is set by the definition and not by hand.
- The tenant-scoped definition a bank can instantiate ships as its own folder,
  `backend/agents/tenant-source-watch/v1/`, with `scope: tenant`,
  `tenant_configurable: true`, its prompt, its tool list limited to the operations a tenant
  agent may call, and `writes_to: tenant`. Its evals folder carries the same README shape as
  the sweeper's.
- `apps/agents/seeds/__init__.py` creates one `AgentVersion` row per shipped version folder
  beside the `agent` row, inside `library_write()`, with an audit event each, and leaves an
  existing row alone — a deploy never silently rewrites a version a run points at.

**Owned paths:**

- `backend/agents/watch-sweeper/v1/definition.yaml`
- `backend/agents/tenant-source-watch/v1/` (new: `definition.yaml`, `prompt.md`,
  `evals/README.md`, `evals/cases.jsonl`)
- `backend/agents/README.md`
- `backend/apps/agents/seeds/__init__.py`, `seeds/definition.py`
- `backend/apps/agents/tests_definition_files.py` (new: the reader, the seed and the shipped folders)

**Done when:**

- `seed_reference` creates an `agent` row and an `AgentVersion` row per shipped folder, with
  one audit event each, and a second run creates nothing and changes nothing (proved by a
  test, which is H5's rule applied here).
- The reader and PyYAML agree on every field of every shipped definition, proved by the
  existing cross-check test extended to the new scalars.
- `watch-sweeper` seeds with `scope='platform'` and `tenant_configurable=false`;
  `tenant-source-watch` with `scope='tenant'` and `tenant_configurable=true`.
- A definition file the reader cannot read stops the seed with its path named, and a test
  proves it.
- The tenant definition's tool list contains no operation that writes a library row, proved by
  a test that compares it with the API key scopes that reach the library.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Definitions are the platform's; a version folder never changes after it ships.
- Seeded library rows are written inside `library_write()` with an audit event each.
- A tenant agent never carries a tool that writes the shared library.

### c11-security-policy-b: reading and writing the security policy

**Requirements:** ID-07, ID-08, ADM-01
**Scenarios:** none
**Depends on:** `c11-security-policy-a`
**Security review:** yes (an authentication policy write)
**Keys:** `ten`

Declare and serve the policy routes in `backend/apps/tenants/api.py`, `schemas.py` and a new
`tenants/security_policy.py`:

| Operation | Route | Gate |
|---|---|---|
| `getSecurityPolicy` | `GET /tenant/security-policy` | SessionAuth, `security.manage` |
| `putSecurityPolicy` | `PUT /tenant/security-policy` | SessionAuth, `security.manage`, step-up |
| `listAllowedAuthenticators` | `GET /reference/authenticators` | SessionAuth, `security.manage` |

The logic is the write and the read only; every enforcement of either policy belongs to
`c11-credential-policy` and `c11-session-policy`, so this task's module makes no decision
about a passkey or a session:

- The write validates the limits against `SESSION_IDLE_MAX_MINUTES` and
  `SESSION_ABSOLUTE_MAX_HOURS` and answers 422 `above_platform_maximum` above either.
- A `device_bound` policy with an empty allow-list is refused with 422
  `empty_authenticator_list`: an empty root set locks everyone out (ADR 0048).
- `device_bound_from` defaults to 14 days ahead when the policy tightens, is refused in the
  past, and is ignored when the policy loosens, because loosening takes effect at once.
- A change that would refuse the acting admin's own passkeys from now on answers 409
  `would_lock_out_actor`; the compliance decision itself comes from
  `c11-credential-policy-a`'s function, which this task calls and does not re-implement. Until
  that task lands, the call sits behind a named function that answers `not_built`, and this
  task's test asserts the call is made.
- The write is audited through `record()` with before and after and the step-up assertion id,
  and notifies the other `security.manage` holders through the outbox.
- `GET /reference/authenticators` reads the committed platform list from the repository file,
  never the network.

**Owned paths:**

- `backend/apps/tenants/api.py` and `backend/apps/tenants/schemas.py` (the three operations only)
- `backend/apps/tenants/security_policy.py`
- `backend/apps/tenants/tests_security_policy.py`
- `backend/apps/identity/data/authenticators.json` (the committed platform list)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- The three operations appear in `openapi.json`, and the write answers 403
  `step_up_required` without a fresh assertion and 403 with `requiredPermission` without
  `security.manage`.
- A limit above either platform maximum answers 422 `above_platform_maximum`.
- A `device_bound` policy with an empty list answers 422 `empty_authenticator_list`.
- A tightening write with no date gets the default notice date; a date in the past is refused;
  a loosening write ignores the date.
- Tenant B reading or writing tenant A's policy gets 404 (AC-NFR1).
- The write leaves one audit row with before, after and the assertion id, in the same
  transaction, and one outbox event.
- `GET /reference/authenticators` makes no network call, proved by a test that fails on any
  outbound request.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.tenants apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/tenants/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Step-up on a security policy change (playbook 4.2), with the assertion on the audit event.
- No passwords, ever; no self-service fallback is added by any state of this policy.
- `record()` on every write, in the same transaction.
- No logic in `api.py`; the client branches on `code`, never on `detail`.

### c11-batch-proposals-contract-b: the batch routes, all answering not_built

**Requirements:** PRO-04
**Scenarios:** none
**Depends on:** `c11-batch-proposals-contract-a`
**Keys:** `prop`

Declare the batch operations in `backend/apps/proposals/api.py` and `schemas.py`, each calling
a named function in `proposals/batch.py` that answers 501 `not_built`:

| Operation | Route | Gate |
|---|---|---|
| `createProposalBatch` | `POST /proposal-batches` | SessionAuth `proposals.review`, or ApiKeyAuth `proposals:write` |
| `getProposalBatch` | `GET /proposal-batches/{batchId}` | SessionAuth, `proposals.review` |
| `decideProposalBatch` | `POST /proposal-batches/{batchId}/decide` | SessionAuth, `proposals.review`, step-up |

Schemas: `ProposalBatch`, `ProposalBatchRow`, `ProposalBatchInput`, `ProposalBatchDecision`
(a list of row decisions plus an optional "the rest" decision), `ProposalBatchQuery`, and
`ObligationScopePayload`, the named payload schema for the `obligation_scope` kind
`c11-batch-proposals-contract-a` added to `ProposalKind` (the terms to add or remove per
obligation), validated when the proposal is created as every other kind's payload is. The
existing `Proposal` schema gains `isBatch` and `rowCount`, which is the one edit this task
makes to a chunk 4 shape.

Add the three routes to `apps/shared/permissions.py`'s route lists and this task's lines to
`contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/proposals/api.py` and `backend/apps/proposals/schemas.py`
- `backend/apps/proposals/tests_contract.py`
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- The three operations appear in `openapi.json` and answer 501 `not_built` behind their real
  gate, and `ObligationScopePayload` appears beside them.
- A batch created with an `obligation_scope` payload that does not match the schema answers
  422 at creation, proved by a test.
- `decideProposalBatch` answers 403 `step_up_required` without a fresh assertion, before the
  501.
- A tenant session and an API key without `proposals:write` each get 403 on
  `createProposalBatch`, proved per principal.
- The route-permission guard is green; nothing joins `UNGATED_BY_DESIGN`.
- `bash generate-types.sh` produces types for all three without the task committing them.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No logic in `api.py`; schemas in `schemas.py`, never `Dict[str, Any]`.
- Four eyes with a step-up on every approval path.
- Errors are RFC 9457 with a `code`.

### c11-platform-agent-settings-a: bleqq's agents carry their settings as platform rows

**Requirements:** AGT-03
**Scenarios:** AGT-S14 (`@integration`, new)
**Depends on:** `c11-agent-definitions-contract-a`, `c11-agent-definitions-contract-b`
**Security review:** yes (the platform fence)

Carries the stop-and-report instruction. Build `backend/apps/agents/platform.py`, which serves
`getPlatformAgentSettings`, `updatePlatformAgentSettings` and, later,
`listPlatformRuns`:

- A platform agent's cadence, the jurisdictions it sweeps and its budget live on the `agent`
  row itself (`default_cadence` and two columns this task adds in **no** new migration — they
  come from `c11-agent-definitions-contract-a`'s migration, which already carries
  `platform_scope` and `platform_monthly_budget`). There is **no tenant column** on any of
  them and no tenant write path.
- `updatePlatformAgentSettings` needs `agent_definitions.manage` and a step-up, validates the
  jurisdictions against the live vocabulary (422 `unknown_key` with the valid list), and
  writes one audit row through `record()` with before and after, the assertion id and
  `tenant_id=None`.
- **The fence, which is this task's real product:** one function,
  `refuse_platform_agent(agent)`, raises `ValidationError` with 403 and
  `agent_definitions.manage` for any tenant-principal write naming a platform agent. Every
  tenant control route calls it; a guard test walks the tenant routes of `agents/api.py` and
  fails on one that does not.
- `AGT-S14` is new — the PRD and ADR 0053 describe the fence but `agents/app.md` has no
  scenario for it — so this task writes the scenario into `backend/apps/agents/app.md` in the
  house format and writes `test_agt_s14` with it:

  ```gherkin
  Given bleqq's general watch agent "watch-sweeper" and a tenant admin with agents.manage
  When the admin tries to switch it off, pause it, change its cadence, change its scope,
    set a budget for it, or edit its definition
  Then every one of those answers 403 naming agent_definitions.manage
  And the agent's settings are unchanged and no audit row is written under the tenant
  When the tenant switches all AI features off
  Then the platform agent's next run is still scheduled
  ```

**Owned paths:**

- `backend/apps/agents/platform.py`
- `backend/apps/agents/tests_platform.py`
- `backend/apps/agents/tests_scenarios.py` (the AGT-S14 test only)
- `backend/apps/agents/app.md` (the AGT-S14 scenario and AGT-03's status cell only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- `test_agt_s14` is green, written before the code, and covers all six refusals plus the AI
  off switch line.
- `GET` and `PUT /console/agents/{agentKey}/settings` answer 200 for a platform admin with a
  fresh assertion and 403 for everyone else, including every tenant role.
- An unknown jurisdiction key answers 422 `unknown_key` with the valid list.
- The write leaves exactly one audit row, with `tenant_id=None`, before, after and the
  assertion id.
- The guard test fails when a tenant control route is added without calling
  `refuse_platform_agent`.
- No tenant row is read anywhere in the diff, proved by a test with two tenants' rows present
  that asserts the query set touches none.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- bleqq's agents are the base package: no tenant off switch, pause, cadence, scope, budget or
  definition edit exists anywhere.
- A platform run reads no tenant row.
- Permissions, never role names; the 403 names the permission.
- `record()` on every write, in the same transaction.

### c11-tenant-agents-contract-b: the tenant's agent routes, all answering not_built

**Requirements:** AGT-04, AGT-05
**Scenarios:** none (it rewords three and un-skips none; AGT-S4's rewording is
`c11-platform-agent-settings-b`'s, which un-skips it)
**Depends on:** `c11-agent-definitions-contract-b`, `c11-tenant-agents-contract-a`
**Security review:** yes (every tenant-facing agent route is declared here)
**Keys:** `agentsapi`

Carries the stop-and-report instruction. Append the tenant half to
`backend/apps/agents/api.py` and `schemas.py`. Every operation carries its auth class and
permission and calls a named function that answers 501 `not_built`:

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `listTenantAgents` | `GET /agents` | SessionAuth, `agents.manage` | `agents/tenant_agents.py` |
| `createTenantAgent` | `POST /agents` | SessionAuth, `agents.manage` | `agents/tenant_agents.py` |
| `updateTenantAgent` | `PATCH /agents/{tenantAgentId}` | SessionAuth, `agents.manage` | `agents/tenant_agents.py` |
| `listPlatformWatch` | `GET /agents/platform` | SessionAuth, `watch.read` | `agents/platform_read.py` |
| `runTenantAgentNow` | `POST /agents/{tenantAgentId}/runs` | SessionAuth, `agents.manage` | `agents/control.py` |
| `pauseTenantAgent` | `POST /agents/{tenantAgentId}/pause` | SessionAuth, `agents.manage` | `agents/control.py` |
| `resumeTenantAgent` | `DELETE /agents/{tenantAgentId}/pause` | SessionAuth, `agents.manage` | `agents/control.py` |
| `interruptAgentRun` | `POST /agent-runs/{runId}/interrupt` | SessionAuth, `agents.manage` | `agents/control.py` |
| `getAgentBudget` | `GET /tenant/agent-budget` | SessionAuth, `agents.manage` | `agents/budget.py` |
| `putAgentBudget` | `PUT /tenant/agent-budget` | SessionAuth, `agents.manage` | `agents/budget.py` |
| `listResearchRequests` | `GET /research-requests` | SessionAuth, `agents.manage` | `agents/requests.py` |
| `createResearchRequest` | `POST /research-requests` | SessionAuth, `agents.manage` | `agents/requests.py` |
| `getResearchRequest` | `GET /research-requests/{requestId}` | SessionAuth, `agents.manage` | `agents/requests.py` |
| `createRetagRequest` | `POST /console/research-requests` | SessionAuth, `proposals.review` | `agents/requests.py` |

Schemas: `TenantAgent`, `TenantAgentInput`, `TenantAgentUpdate`, `PlatformWatchItem`
(`{key, name, purpose, jurisdictions[], cadence, nextRunAt, lastRun}`, where `lastRun` is a
status-only summary, `{finishedAt, status}`, and nothing else — no prompt, tool, model,
version internals, budget, cost, findings, proposal counts or setting. ADR 0053 shows bleqq's
agents read-only **with their history**, and `c11-e2e-agent-controls-b` asserts the panel
still shows a next run with the tenant's AI off, so both fields are part of the read),
`AgentBudget`, `AgentBudgetInput`, `ResearchRequest`,
`ResearchRequestInput`, `RetagRequestInput`, `TenantRunListItem`, `TenantRunQuery`. The
chunk 5 `AgentRunPage` gains the chunk 11 fields (`cost`, `changesFound`, `proposalsMade`,
`trigger`, `requestedBy`, `interruptedAt`) and `GET /agent-runs` gains the
`tenantAgentId` and `mine` query parameters, which is the one edit this task makes to a
chunk 5 shape (ruling 9).

Also, in one edit, this task rewords three of the four scenarios the split changed, in
`backend/apps/agents/app.md` (CLAUDE.md section 10). AGT-S4 is **not** one of them: it is
reworded by `c11-platform-agent-settings-b`, in the same edit that un-skips it, because the
two tasks share a wave and a test may not be written against wording that has not landed.
- **AGT-S5**: "switch on nordic-watch" becomes a tenant's own agent, added by the bank, and
  the scenario states that the same calls against a platform agent answer 403.
- **AGT-S6**: the cap and the AI off switch are named as covering the bank's own agents and
  Ask, and the scenario gains the line that bleqq's watch is unaffected.
- **AGT-S11**: the platform line becomes "a platform library run reads no tenant row and
  sweeps every covered jurisdiction", which is what a platform run's scope is.

Every route list in `apps/shared/permissions.py` gains its rows, nothing joins
`UNGATED_BY_DESIGN`, and this task adds its lines to `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/agents/api.py` and `backend/apps/agents/schemas.py` (the tenant operations only)
- `backend/apps/agents/tests_contract.py` (the tenant operations only)
- `backend/apps/agents/app.md` (the AGT-S5, AGT-S6 and AGT-S11 rewordings and AGT-04's and
  AGT-05's status cells only; AGT-S4's block is not touched)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- The fourteen operations appear in `openapi.json` with the ids above and answer 501
  `not_built` behind their real gate.
- A session without the named permission gets 403 with `requiredPermission` and an anonymous
  request 401, both before the 501, proved per route.
- An API key of any scope gets 403 on every one of them: a tenant agent's key never opens or
  steers a run through these routes, proved per route.
- `listPlatformWatch` answers for a plain reader holding `watch.read` and returns exactly
  `{key, name, purpose, jurisdictions, cadence, nextRunAt, lastRun{finishedAt, status}}` — no
  prompt, tool, model, version internals, budget, cost, findings, proposal counts or setting —
  proved by asserting the schema's field set, so a later addition fails the test.
- Tenant B calling any `{tenantAgentId}` or `{runId}` route of tenant A gets 404 (AC-NFR1),
  proved per route once the routes are served; at contract stage the test asserts the 501 is
  reached only inside the caller's own tenant.
- The route-permission guard is green and lists no ungated route.
- `agents/app.md`'s AGT-S5, AGT-S6 and AGT-S11 read as the split, AGT-S4's block is unchanged
  by this task, and no skip line is deleted.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`.
- A tenant agent's key never opens a platform run, and no agent key reaches these routes.
- The API returns `key` and `kind`, never a phrase.
- Every route has a permission; nothing joins `UNGATED_BY_DESIGN`.

### c11-platform-agent-settings-b: publishing a version

**Requirements:** AGT-03, ADM-02
**Scenarios:** AGT-S4 (`@integration`, un-skipped)
**Depends on:** `c11-platform-agent-settings-a`, `c11-agent-definitions`
**Security review:** yes (a platform write that changes every bank's runs)

Build `backend/apps/agents/definitions.py`, which serves `listAgentDefinitions`,
`getAgentDefinition`, `publishAgentVersion` and `retireAgentVersion`:

- **Publish** takes the version folder's contents as read by the seed's reader (never a body
  pasted into a request), creates the `agent_version` row with the next `version_no`, sets
  `published_by` and `published_at`, moves `agent.current_version`, and writes one audit row
  through `record()` with before, after, the change note and the step-up assertion id.
  Publishing a `version_no` that already exists answers 409 `version_exists`; publishing a
  folder the reader cannot read answers 422 with the path named and creates nothing.
- **Runs pin their version.** A run opened after the publish carries the new
  `agent_version_id`; a run opened before it keeps the old one. The test proves both halves,
  which is AGT-S4's second line.
- **Retire** sets `retired_at` and nothing else, and refuses to retire the only unretired
  version of an active agent with 409 `last_version`.
- **The tenant 403** comes from `c11-platform-agent-settings-a`'s route gates; this task's
  scenario test drives it rather than re-implementing it.

This task also **rewords AGT-S4** in `backend/apps/agents/app.md`, in the same edit that
un-skips it: "a tenant admin's request to edit the prompt answers 403" becomes a request to
reach the definition at all, naming `agent_definitions.manage`. The rewording sits here rather
than with the other three, which are `c11-tenant-agents-contract-b`'s, because that task
shares this wave and the test below must be written against wording that has already landed.
The two tasks touch different blocks and different status cells of the same file, as
plan-wide rule 6 allows.

**Owned paths:**

- `backend/apps/agents/definitions.py`
- `backend/apps/agents/tests_definitions.py`
- `backend/apps/agents/tests_scenarios.py` (the AGT-S4 test only)
- `backend/apps/agents/app.md` (AGT-S4's wording and AGT-03's status cell only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- `test_agt_s4` is green, written before the code: a platform admin publishes version 4 with a
  changed prompt, runs started after it reference 4, earlier runs still reference 3, and a
  tenant admin's request to reach the definition answers 403.
- Publishing without a fresh assertion answers 403 `step_up_required` and creates nothing.
- Publishing an existing `version_no` answers 409 `version_exists`.
- A published row cannot be updated afterwards: the append-only trigger refuses it, proved on
  the app alias.
- Retiring the last unretired version of an active agent answers 409 `last_version`.
- Every publish leaves exactly one audit row with `tenant_id=None`, the change note and the
  assertion id.
- No chunk 11 line of `contract_drift_pending.txt` for these operations is left.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing overwritten: a published version is append-only.
- Definitions are the platform's; no tenant principal reaches one.
- Four eyes is not required here (nothing enters the library), but the step-up and the audit
  row are.
- `record()` on every write, in the same transaction.

### c11-credential-policy-a: the compliance decision and registration

**Requirements:** ID-07
**Scenarios:** ID-S16 (`@integration`, un-skipped)
**Depends on:** `c11-security-policy-b`, `q-credential` (answered: item 8), `r1-readiness`,
`h-a-guards`
**Security review:** yes (authentication)
**Keys:** `idp`

Carries the stop-and-report instruction. Build the compliance decision and the registration
half of ADR 0048 in `backend/apps/identity/passkey_logic.py` and a new
`identity/credential_policy.py`:

- **One function decides**, `passkey_is_compliant(passkey, policy)`, and it does not trust
  py_webauthn's own result alone. In a `device_bound` tenant, registration asks for direct
  attestation and accepts only `packed` or `tpm` statements carrying a certificate chain; the
  chain is verified against the roots of the claimed model only; an empty root set is refused;
  the certificate's AAGUID extension must match the authenticator's when present, and must be
  present when a root serves several models; backup eligibility must be unset. The `apple`,
  `android-key` and `android-safetynet` formats are refused, because the library adds its own
  vendor roots for them.
- A non-compliant registration answers 422 `credential_policy` and stores nothing.
- **For every bank, not only `device_bound` ones**, the backup-eligibility flag in each
  assertion is compared with the stored one at sign-in and at step-up, as WebAuthn Level 3
  requires and today's code does not do. A mismatch is a refused assertion with a security-log
  row.
- Each refusal writes a security-log row through the existing `security_log.py`, naming the
  person and the reason, and no fetched or attested blob reaches a log.

**Owned paths:**

- `backend/apps/identity/credential_policy.py`
- `backend/apps/identity/passkey_logic.py` (the registration and assertion checks only)
- `backend/apps/identity/tests_policies.py` (the credential cases only)
- `backend/apps/identity/tests_scenarios.py` (the ID-S16 test only)
- `backend/apps/identity/app.md` (ID-07's status cell only)
- `backend/config/settings.py` (one labelled block), `backend/.env.example`,
  `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- `test_id_s16` is green, written before the code: in a `device_bound` tenant a synced passkey
  whose AAGUID is not on the list answers 422 `credential_policy`, and an attested
  authenticator on the list succeeds.
- Each of the six refusal reasons above has its own test with a planted statement: wrong
  format, no chain, empty root set, AAGUID mismatch, missing AAGUID where a root serves
  several models, backup eligibility set.
- A backup-eligibility mismatch at sign-in and at step-up is refused, in a tenant of either
  policy, with a security-log row.
- No attestation blob, certificate or AAGUID reaches a log, Sentry or an error body, proved by
  a test.
- `c11-security-policy-b`'s lock-out call now answers from this function, and its 409 test
  goes from asserting the call to asserting the outcome.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/*' (credential_policy.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No passwords, ever, and no self-service fallback: a refused passkey is recovered by an admin
  re-issuing enrolment, or by platform support for the last admin.
- Nothing weakens: a loosening policy takes effect at once, a tightening one never locks out
  the acting admin.
- Tenant content never reaches logs or Sentry.
- Input from a user, an agent, the network or an external service is never an impossible case:
  every attestation field is validated at the boundary.

### c11-tenant-agent-controls-a: a bank adds an agent, switches it on, sets its cadence and scope

**Requirements:** AGT-04
**Scenarios:** none (AGT-S5 is `-b`'s)
**Depends on:** `c11-tenant-agents-contract-b`, `c11-platform-agent-settings-a`
**Security review:** yes (the tenant zone's first agent writes)

Carries the stop-and-report instruction. Build `backend/apps/agents/tenant_agents.py`, which
serves `listTenantAgents`, `createTenantAgent` and `updateTenantAgent`:

- **Create** takes a tenant-scoped definition key, and refuses a platform one through
  `refuse_platform_agent()` with 403 naming `agent_definitions.manage` (ruling 1). It writes
  `enabled` false, the definition's `default_cadence` and an empty scope, so a new agent does
  nothing until the bank switches it on.
- **Update** takes `enabled`, `cadence`, `run_weekday`, `run_hour` and `scope`. The cadence is
  checked against the tenant's plan limit, `AGENT_MIN_CADENCE_BY_PLAN` (a setting with an env
  override, read against the tenant's plan row); above it the request answers 422
  `above_plan_limit`. A scope key that is not a live vocabulary row answers 422 `unknown_key`
  with the valid list (AGT-02).
- **List** returns the bank's own agents with their status, cadence, scope, next run and last
  run. It never lists a platform agent: that is `listPlatformWatch`'s, and a test asserts the
  two sets do not overlap.
- Every write goes through `record()` in the same transaction, with before and after, under
  the acting tenant. No step-up: playbook 4.2 does not list an agent control, and switching an
  agent off is the safe direction.
- `next_run_at` is computed from the cadence and the tenant's timezone at write time, anchored
  to the tenant-local date plus a fixed wall time; the scheduler reads it and does not
  recompute it.

**Owned paths:**

- `backend/apps/agents/tenant_agents.py`
- `backend/apps/agents/tests_tenant_agents.py`
- `backend/config/settings.py` (one labelled block), `backend/.env.example`,
  `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- Creating an agent against a platform definition answers 403 naming
  `agent_definitions.manage`, and nothing is written.
- Creating against a tenant-scoped definition writes a disabled row with the definition's
  default cadence and an empty scope.
- A cadence above the plan limit answers 422 `above_plan_limit`; one at the limit succeeds.
- An unknown scope key answers 422 `unknown_key` with the valid list.
- Tenant B reading or updating tenant A's agent gets 404.
- Every write leaves one audit row with before and after under the acting tenant, in the same
  transaction.
- `listTenantAgents` returns no platform agent, proved with both kinds seeded.
- `next_run_at` is computed from a frozen clock in the test, never from the real "today".

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- A bank steers only its own agents; a platform agent answers 403.
- Agents read vocabularies and use existing keys only; store and compare keys, never labels.
- `record()` on every write, in the same transaction, under the acting tenant.
- Every threshold is a setting with an env override.

### c11-platform-watch-read: what bleqq watches, read-only

**Requirements:** AGT-03, AGT-04
**Scenarios:** none
**Depends on:** `c11-platform-agent-settings-a`, `c11-tenant-agents-contract-b`

Build `backend/apps/agents/platform_read.py`, which serves `listPlatformWatch`: for each
active platform agent, its key, name, purpose, the jurisdictions it sweeps, its check cadence,
when it next runs (`nextRunAt`) and a **status-only** summary of its last run (`finishedAt`
and `status`). Nothing else — no prompt, tool, budget, cost, findings, proposal counts, model,
version internals or setting, and nothing writable. ADR 0053 shows bleqq's agents read-only
with their history, and a bank that can see a next run can see that the coverage it pays for
is still running; a cost or a finding would be run detail and is not carried.

The panel exists because a bank that cannot change bleqq's watch still has to be able to see
what it covers, which is what a vendor review will ask. Gated by `watch.read`, which every
system role holds (ruling 6), so a reader sees the same list as an admin.

**Owned paths:**

- `backend/apps/agents/platform_read.py`
- `backend/apps/agents/tests_platform_read.py`
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- The route answers 200 for every system role and 401 for an anonymous request.
- The response carries exactly `{key, name, purpose, jurisdictions, cadence, nextRunAt,
  lastRun{finishedAt, status}}`, proved by asserting the schema's field set so a later
  addition fails the test.
- `nextRunAt` is computed from the agent's cadence against a frozen clock in the test, and a
  platform agent that has never run carries a null `lastRun` rather than a missing field.
- A retired or inactive platform agent is not listed.
- No tenant agent appears in the response, proved with both kinds seeded.
- The read touches no tenant table, proved by a test with two tenants' rows present.
- The route is a read: a `PUT`, `PATCH`, `POST` or `DELETE` on the same path answers 405.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing about a platform agent is writable by a tenant, in any release.
- The API returns `key` and `kind`, never a phrase; the screen renders the words.
- An empty answer is 200.

### c11-run-history: the bank's own runs, with findings and cost

**Requirements:** AGT-04
**Scenarios:** none
**Depends on:** `c11-tenant-agents-contract-b`

Build `backend/apps/agents/runs_read.py`, which serves the extended `GET /agent-runs` for a
tenant session (ruling 9): the bank's own runs, newest first, with status, trigger, who asked,
duration, cost, `changes_found`, `proposals_made`, `interrupted_at` and the run's stats;
filtered by `tenantAgentId`, and by `mine` for the caller's own requests. Paged at 20 with a
maximum of 100, ordered by `started_at` descending with a stable tiebreak on id.

bleqq's platform runs reach a bank as watch items and proposals, not as run rows, so a tenant
session sees **no** platform run in this list. That is a change from chunk 5's read, which
gave a tenant the library's runs read-only for the agent API's own flow: the tenant-facing
history filters them out, and chunk 5's key-facing behaviour is unchanged. A test proves both
halves.

**Owned paths:**

- `backend/apps/agents/runs_read.py`
- `backend/apps/agents/tests_runs_read.py`
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- A tenant session's `GET /agent-runs` returns only that tenant's runs, with both kinds
  seeded, and never a platform run.
- An agent key's `GET /agent-runs` behaves exactly as chunk 5 built it, proved by chunk 5's
  own test staying green.
- `tenantAgentId` and `mine` filter as described; an unknown `tenantAgentId` of another tenant
  gets 404.
- Paging defaults to 20, caps at 100, and orders stably; a test pins the order with two runs
  started in the same microsecond.
- The endpoint answers inside the 250 ms budget with 200 seeded runs and asserts
  `Server-Timing: app`.
- Cost is the run's own; no figure on this page includes a platform run.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Two zones: a tenant reads its own rows.
- Paginate (default 20, maximum 100); `Meta.ordering` on anything `.first()`ed.
- An empty answer is 200.

### c11-credential-policy-b: the notice date at sign-in

**Requirements:** ID-07
**Scenarios:** none (ID-S16 is `-a`'s)
**Depends on:** `c11-credential-policy-a`
**Security review:** yes (authentication)
**Keys:** `idp`

Carries the stop-and-report instruction. Build the sign-in half of ADR 0048 in
`backend/apps/identity/session_logic.py` and `credential_policy.py`:

- After an assertion verifies, a non-compliant passkey in a `device_bound` tenant **past
  `device_bound_from`** answers 403 `credential_policy` with a security-log row. Before that
  date it signs in as before.
- A refused step-up leaves the action undone; the action is never half-applied.
- Sessions opened before the notice date run out at the absolute limit rather than being cut
  mid-request, which is what ADR 0048 chose.
- Non-compliant passkeys are kept, not deleted: they open nothing, and recovery is an admin
  re-issuing enrolment, or platform support for the last admin. A test proves the row survives.
- The refusal is the same shape for a sign-in and for a step-up, so a client branches on
  `code` and not on the route.

**Owned paths:**

- `backend/apps/identity/session_logic.py` (the policy check only)
- `backend/apps/identity/credential_policy.py` (the date decision only)
- `backend/apps/identity/tests_policies.py` (the notice-date cases only)

**Done when:**

- A non-compliant passkey in a `device_bound` tenant signs in before the notice date and is
  refused with 403 `credential_policy` on and after it, proved with a frozen clock at three
  points.
- A refused step-up leaves the attempted action undone, proved on a real sensitive route.
- A session opened before the date survives to its absolute limit and no further.
- The refused passkey row still exists afterwards.
- Each refusal writes one security-log row and no tenant content reaches a log.
- A loosening policy takes effect at once, with no date, proved by a test.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No passwords, ever; no self-service fallback.
- Step-up is a fresh passkey assertion, and a refused one changes nothing.
- The client branches on `code`, never on `detail`; no trace ever leaves.
- Clocks are frozen in tests; nothing depends on the real "today".

### c11-batch-proposals-a: creating a batch with its preview

**Requirements:** PRO-04, AGT-05
**Scenarios:** none (PRO-S8 is `-b`'s)
**Depends on:** `c11-batch-proposals-contract-b`
**Keys:** `prop`

Build `backend/apps/proposals/batch.py`'s creation half, serving `createProposalBatch` and
`getProposalBatch`:

- A batch is **one** proposal of kind `obligation_scope` (a re-tag) or
  `new_obligation_version` (a backfill), with one `proposal_batch_row` per record, each
  carrying `before` and `after` for the fields that would change and nothing else.
- The preview is computed at creation and stored on the rows, so the reviewer decides on what
  was proposed rather than on what the library says now. A row whose record has moved since
  creation is marked `stale` at read time and cannot be approved until the batch is recreated;
  that is the `If-Match` rule applied to a batch.
- `PROPOSAL_BATCH_MAX_ROWS` is a setting with an env override; a batch above it answers 422
  `batch_too_large`, which keeps the preview read inside the 250 ms budget.
- The rows carry no tenant content: a batch touches library records, and a re-tag asked by a
  bank is refused — AGT-05 puts re-tagging in the platform console (ruling 5). A test proves a
  tenant session cannot create one.
- Creation is idempotent through the existing `Idempotency-Key` header and
  `idempotency_record`, as every other proposal write is.

**Owned paths:**

- `backend/apps/proposals/batch.py` (creation and read only)
- `backend/apps/proposals/tests_batch.py`
- `backend/config/settings.py` (one labelled block), `backend/.env.example`,
  `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- A re-tag over twelve obligations creates one proposal with twelve rows, each with before and
  after, and the live records are unchanged.
- A tenant session creating a batch answers 403; a library editor and an agent key with
  `proposals:write` both succeed.
- A batch above `PROPOSAL_BATCH_MAX_ROWS` answers 422 `batch_too_large`.
- A row whose record changed after creation reads as `stale` and cannot be approved.
- A retried creation with the same `Idempotency-Key` creates one batch.
- `GET /proposal-batches/{batchId}` answers inside the 250 ms budget for a maximum-size batch
  and asserts `Server-Timing: app`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.proposals apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Proposals are the only door into the library; a preview writes nothing.
- Idempotency on agent writes.
- `If-Match` on versioned records, which a stale row is the batch form of.
- Every threshold is a setting with an env override.

### c11-tenant-agent-controls-b: run now, pause, resume and interrupt

**Requirements:** AGT-04, AGT-06
**Scenarios:** AGT-S5 (`@integration`, un-skipped)
**Depends on:** `c11-tenant-agent-controls-a`, `c11-runner-adapter`, `c7-ask-switch`
**Security review:** yes (a tenant starting and stopping work)

Carries the stop-and-report instruction. Build `backend/apps/agents/control.py`, which serves
`runTenantAgentNow`, `pauseTenantAgent`, `resumeTenantAgent` and `interruptAgentRun`:

- **Run now** opens an `agent_run` with `trigger='manual'`, `requested_by` the caller, the
  tenant agent's current scope copied onto it, and the run's budget limit from the bank's cap;
  it hands the run to `get_agent_runner().start()` and answers with the run. The work happens
  in the worker; the request returns a row whose status is read from `GET /agent-runs/{runId}`
  (plan-wide rule 14).
- **Pause** sets `paused_at` and `paused_by`; **resume** clears both and recomputes
  `next_run_at`. Neither touches a run already in flight.
- **Interrupt** calls `interrupt()` on the adapter and sets `interrupted_at` and
  `interrupted_by` when the event returns; a run that has already finished answers 409
  `run_finished`.
- **Every one of the four refuses a platform agent or a platform run** through
  `refuse_platform_agent()`, with 403 naming `agent_definitions.manage`. Interrupt also
  refuses a run of another tenant with 404.
- **Run now is refused** when the bank's cap is reached (422 `budget_cap_reached`), when the
  agent is paused (409 `agent_paused`) or disabled (409 `agent_disabled`), and when the
  tenant's AI is off (403 `feature_off`). The cap check itself is
  `c11-run-scheduler-b`'s function, called here and not re-implemented; until it lands, the
  call sits behind a named function answering `not_built` and this task's test asserts the
  call is made.
- Every one writes an audit row through `record()` in the same transaction.

**Owned paths:**

- `backend/apps/agents/control.py`
- `backend/apps/agents/tests_control.py`
- `backend/apps/agents/tests_scenarios.py` (the AGT-S5 test only)
- `backend/apps/agents/app.md` (AGT-04's status cell only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- `test_agt_s5` is green, written before the code and reworded to the split: a tenant admin
  switches on the bank's own agent, sets a weekly cadence within the plan limit, restricts the
  scope to SE and FI and chooses "Run now"; a run is queued with those settings and the
  history lists it with findings and cost; "Stop run" interrupts it and the status says so;
  a cadence above the plan limit answers 422 `above_plan_limit`; and the same four calls
  against a platform agent each answer 403.
- Interrupting a finished run answers 409 `run_finished` and changes nothing.
- Interrupting another tenant's run answers 404.
- A paused, disabled or AI-off agent refuses "Run now" with its own code.
- The run stores a copy of the scope at start, so a later scope change does not alter it.
- Every control leaves one audit row under the acting tenant, in the same transaction.
- No control call reaches the runner before the run row exists, proved by a test that fails
  the adapter and asserts the row.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- A tenant agent's key never opens a platform run, and no tenant control reaches one.
- The app is the scheduler of record; the row exists before the runner is called.
- Every agent run is a job with a status endpoint.
- `record()` on every write, in the same transaction.

### c11-session-policy: idle and absolute limits inside the platform maximums

**Requirements:** ID-08
**Scenarios:** ID-S17 (`@integration`, un-skipped)
**Depends on:** `c11-security-policy-b`, `r1-readiness`
**Security review:** yes (sessions)
**Keys:** `idp`

Carries the stop-and-report instruction. Apply the tenant session policy in
`backend/apps/identity/session_logic.py`:

- A refresh whose session has been idle longer than `session_idle_minutes` answers 401 and
  revokes the session row, so a revoked session cannot be refreshed a second time.
- A session older than `session_absolute_hours` answers 401 at its next refresh, whatever its
  idle time.
- A tenant with no policy row uses the platform maximums.
- A policy write above either maximum answers 422 `above_platform_maximum`, which
  `c11-security-policy-b` already refuses; this task's scenario drives it rather than
  re-implementing it.
- A platform session (no tenant) uses the platform maximums and reads no tenant row.
- The idle clock is the session's `last_used_at`, updated on refresh only, so a page of reads
  does not extend a session silently.

**Owned paths:**

- `backend/apps/identity/session_logic.py` (the limit checks only)
- `backend/apps/identity/tests_policies.py` (the session cases only)
- `backend/apps/identity/tests_scenarios.py` (the ID-S17 test only)
- `backend/apps/identity/app.md` (ID-08's status cell only)

**Done when:**

- `test_id_s17` is green, written before the code: idle 15 and absolute 8 set on a tenant, a
  session idle for 16 minutes answers 401 at its next refresh, and an absolute limit above the
  platform maximum answers 422 `above_platform_maximum`.
- A revoked-by-idle session cannot be refreshed again, proved by a second attempt.
- A tenant with no policy row uses the platform maximums.
- A platform session reads no tenant row, proved with two tenants' policies present.
- The clock is frozen at every point; no test depends on the real "now".

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.tenants apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Sessions are revocable at once; a limit narrows, never widens, the platform maximum.
- No trace ever leaves; the client branches on `code`.
- UTC timestamps; tenant-local only where a person reads a date.

### c11-batch-proposals-b: approving a batch whole or row by row

**Requirements:** PRO-04
**Scenarios:** PRO-S8 (`@integration`, un-skipped)
**Depends on:** `c11-batch-proposals-a`, `c4-approve-apply`
**Security review:** yes (the apply path)
**Keys:** `apply`

Carries the stop-and-report instruction. Build the decision half of
`backend/apps/proposals/batch.py` and extend `proposals/apply.py` to apply a batch:

- `decideProposalBatch` takes a list of row decisions and an optional decision for the rest,
  needs `proposals.review` and a fresh step-up, and refuses the proposer with 409
  `four_eyes_violation` before deciding anything — the whole call decides nothing, as AC-REG1
  does for applicability.
- Approved rows are applied through the same `apply.py` path a single proposal uses, in **one
  transaction**: each approved record gets its new version, its audit row and its re-index,
  and each rejected row gets its reason. A stale row cannot be approved (422 `stale_write`)
  and does not stop the rest.
- **`apply()`'s `obligation_scope` branch is this task's**, beside the batch branch: the kind
  is a member of the code enum `apply()` branches on (`c11-batch-proposals-contract-a`) with
  its payload schema declared (`-contract-b`), and this is where the branch that writes the
  re-tagged terms, the version and the citations lands. An `obligation_scope` proposal with no
  branch would be an unreachable kind, so the test that walks every `ProposalKind` member and
  asserts each has a branch is extended here.
- Audit: one `record()` per row with before and after, plus one more for the batch naming each
  row's outcome, which is PRO-S8's last line. Every one carries the step-up assertion id.
- A batch whose rows all fail leaves the proposal open rather than half-closed; the parent
  closes only when no row is pending.
- A tenant principal never reaches this route, and no API key scope does either.

**Owned paths:**

- `backend/apps/proposals/batch.py` (the decision half only)
- `backend/apps/proposals/apply.py` (the batch branch and the `obligation_scope` branch only)
- `backend/apps/proposals/tests_apply.py` (the batch cases only)
- `backend/apps/proposals/tests_scenarios.py` (the PRO-S8 test only)
- `backend/apps/proposals/app.md` (PRO-04's status cell only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- `test_pro_s8` is green, written before the code: a re-tag that would add a flag to twelve
  obligations previews twelve rows, the editor rejects two and approves the rest, ten
  obligations change, two do not, and one audit event records the batch with each row's
  outcome.
- The proposer deciding their own batch answers 409 `four_eyes_violation` and changes nothing
  at all.
- Deciding without a fresh assertion answers 403 `step_up_required` and changes nothing.
- Ten approved rows leave ten new versions, ten row audit rows and one batch audit row, all in
  one transaction: a failure part-way leaves no record changed.
- A stale row answers 422 `stale_write` and the others still apply.
- Every `ProposalKind` member has an `apply()` branch, `obligation_scope` included, proved by
  a test that walks the enum.
- The parent proposal closes only when no row is pending.
- A tenant session and an API key each answer 403.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.proposals apps.library apps.search apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/*' (apply.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Proposals are the only door into the library; approval applies the payload, the version, the
  audit row and the re-index in one transaction.
- Four eyes, enforced by a check constraint, with a passkey step-up on approval; never the
  proposer.
- A rejection carries a reason from a vocabulary row.
- Nothing overwritten: a new version, never an edit in place.

### c11-run-scheduler-a: the platform beat, from the platform settings

**Requirements:** AGT-03, AGT-06
**Scenarios:** none (AGT-S6 is `-b`'s)
**Depends on:** `c11-platform-agent-settings-a`, `c11-agent-definitions`, `c11-runner-adapter`
**Security review:** yes (the worker's first agent schedule)
**Keys:** `agentstasks`

Carries the stop-and-report instruction. Build `backend/apps/agents/tasks.py`'s platform half
and the chunk's first `CELERY_BEAT_SCHEDULE` entry:

- One beat task walks the active platform agents whose `default_cadence` is due, opens an
  `agent_run` with `tenant_id` NULL, `trigger='schedule'` and the version pinned, and hands it
  to the adapter. It is **not** a `@tenant_task`: a platform run has no tenant and must
  activate none, which is the structural form of "a platform run reads no tenant row" (D-32).
  A guard test asserts the platform task is not wrapped and that it opens no tenant
  connection.
- The run's scope is the agent's `platform_scope`: every covered jurisdiction, no tenant's
  markets.
- No tenant setting is read anywhere in this half: not `ai_enabled`, not a cap, not a pause.
  A test with a tenant that has switched everything off asserts the platform run still starts,
  which is AGT-S14's last line proved from the scheduler's side.
- The beat entry and its registration test are this task's alone
  (`backend/apps/shared/tests_celery_registration.py` gains one case).
- `AGENT_BEAT_INTERVAL_MINUTES` and `AGENT_RUNS_PER_BEAT` are settings with env overrides, so
  one beat cannot start the whole library at once.

**Owned paths:**

- `backend/apps/agents/tasks.py` (the platform half only)
- `backend/apps/agents/tests_tasks.py`
- `backend/apps/shared/tests_celery_registration.py` (its own case only)
- `backend/config/settings.py` (the beat entry and one labelled block),
  `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- A due platform agent gets one run per beat, with `tenant_id` NULL, `trigger='schedule'` and
  the current `agent_version_id`.
- A second beat inside the cadence starts nothing, proved with a frozen clock.
- The platform task is not a `@tenant_task` and activates no tenant, proved by a guard test.
- A tenant with AI off, a zero cap and every agent paused does not stop the platform run.
- `AGENT_RUNS_PER_BEAT` bounds one beat, proved with more due agents than the limit.
- The run row exists before the adapter is called, proved with a failing adapter.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- A platform run reads no tenant row and no tenant setting stops it.
- `@tenant_task` in the worker for anything tenant-scoped; a platform task activates nothing.
- The app is the scheduler of record.
- Every threshold is a setting with an env override.

### f03-T82: a tenant agent's default scope from the markets

**Requirements:** AGT-04, FP-04
**Scenarios:** AGT-S11 (`@integration`, un-skipped)
**Depends on:** `f03-T19`, `c11-tenant-agent-controls-a`, `c11-run-scheduler-a`
**Security review:** yes (D-32's two-zone rule)

From `FEATURES_0_3_TASKS.md`, with ruling 10's owned paths. Build
`backend/apps/agents/scope.py`:

- At run start the scope is built from the tenant's market levels — operating first, then
  watched, then the EU jurisdictions that reach them — unless the `tenant_agent` row names
  jurisdictions of its own, which override it. A copy is stored on the run, so a later market
  change does not alter a finished run's scope.
- A platform run never calls this function: it reads `platform_scope` instead, and a guard
  test asserts `scope.py` is reached only from the tenant path.
- **The vocabularies are read again at run start** (AGT-02, plan-wide rule 16): a scope key
  that has been retired since the admin set it is dropped from the run's stored scope and the
  fact is recorded on the run, so a run never carries a key the agent may not submit. The row
  keeps the key, so the admin still sees what they chose.
- Jurisdiction keys may reach the tenant-scoped runner; tenant text never does (D-32). A test
  asserts the scope payload carries keys only — no market name, no tenant name, no free text.

**Owned paths:**

- `backend/apps/agents/scope.py`
- `backend/apps/agents/tests_scope.py`
- `backend/apps/agents/tests_scenarios.py` (the AGT-S11 test only)
- `backend/apps/agents/app.md` (AGT-04's status cell only)

**Done when:**

- `test_agt_s11` is green, written before the code and reworded to the split: a tenant
  operating in Sweden and watching Norway, with a tenant agent that has no scope of its own,
  starts a run whose stored scope lists Sweden as operating, Norway as watching and the EU as
  reaching them, in that order; later market changes do not alter that run; restricting the
  agent to SE and FI changes the next run only; and a platform run's scope contains no
  tenant's markets and sweeps every covered jurisdiction.
- The stored scope carries keys only, proved by asserting the payload's shape.
- A scope key retired after the admin set it is dropped at run start, recorded on the run, and
  still shown on the `tenant_agent` row, proved by a test.
- The guard test fails if a platform path calls `scope.py`.
- The task adds no column and edits no prompt (ruling 10).

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Two zones: a bank's expansion plans never steer or leak through the shared library.
- Store and compare keys, never labels; no market key appears in a URL.
- Nothing overwritten: a run keeps the scope it started with.

### c11-run-scheduler-b: tenant runs, the budget cap and the pause it causes

**Requirements:** AGT-04, AGT-06
**Scenarios:** AGT-S6 (`@integration`, un-skipped)
**Depends on:** `c11-run-scheduler-a`, `f03-T82`, `c11-tenant-agent-controls-b`,
`c11-run-history`, `c10-notifications-api`
**Security review:** yes (spend and a tenant schedule)
**Keys:** `agentstasks`

Carries the stop-and-report instruction. Build `backend/apps/agents/tasks.py`'s tenant half and
`backend/apps/agents/budget.py`:

- A `@tenant_task` walks the bank's `tenant_agent` rows that are `enabled`, not paused and due
  (`tenant_agent_due_idx`), opens a run with `trigger='schedule'`, the scope from
  `agents/scope.py` and the budget limit from the bank's cap, and hands it to the adapter.
- **The cap has two points.** Before a run starts: the month's spend for the tenant's own runs
  plus the run's budget limit against `monthly_cap`; above it the run is not started, the
  agent is paused with a reason and the admins holding `agents.manage` are notified through
  `c10-notifications-api`'s `notify()`. During a run: a runner event whose cumulative cost
  passes the cap interrupts the run through the adapter and pauses the agent the same way. The
  second point is what keeps a single long run from spending the year.
- **The spend figure** is the sum of `agent_run.cost` for the tenant's own runs in the
  tenant-local month. A platform run is never in it (the default taken above), proved by a
  test with both kinds seeded.
- `getAgentBudget` and `putAgentBudget` serve the cap and the figure; a cap below the month's
  spend is accepted and pauses at once, because a bank must be able to stop spending.
- Every pause writes an audit row through `record()` with the reason, under the tenant.

**Owned paths:**

- `backend/apps/agents/tasks.py` (the tenant half only)
- `backend/apps/agents/budget.py`
- `backend/apps/agents/tests_budget.py`
- `backend/apps/agents/tests_tasks.py` (the tenant cases only)
- `backend/apps/agents/tests_scenarios.py` (the AGT-S6 test only)
- `backend/apps/agents/app.md` (AGT-04's and AGT-06's status cells only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- `test_agt_s6` is green, written before the code and reworded to the split: with a cap set
  and the month's spend close to it, a run that would exceed the cap is not started and the
  admin is notified; with all AI features off, no tenant run starts, Ask answers 403
  `feature_off` and the LLM adapter records no call for the tenant; and bleqq's watch is
  unaffected by either.
- A runner event that passes the cap mid-run interrupts the run and pauses the agent, proved
  by a test.
- The month's spend excludes every platform run, proved with both kinds seeded.
- A cap set below the current spend pauses at once and is not refused.
- The tenant task is a `@tenant_task` and the registration guard is green.
- Each pause leaves one audit row with its reason under the tenant, and one notification.
- If `c10-notifications-api` is late, the notification sits behind one `notify()` call the
  test asserts is made, the AGT-S6 line about notifying stays out of the un-skipped test, and
  `c11-chunk-close` names it (the contingency above).

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.collab apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- `@tenant_task` in the worker; a tenant run never reads another tenant's rows.
- A tenant setting stops the bank's own agents and nothing of bleqq's.
- `record()` on every write, in the same transaction.
- Every threshold is a setting with an env override; a cap is data, not a literal.

### c11-research-requests-a: a bank asks its own agents

**Requirements:** AGT-05
**Scenarios:** none (AGT-S7 is `-b`'s)
**Depends on:** `c11-tenant-agent-controls-b`, `c11-run-scheduler-b`,
`c5-watch-sources-coverage`
**Security review:** yes (a tenant starting work against an external source)

Carries the stop-and-report instruction. Build `backend/apps/agents/requests.py`'s tenant half,
serving `createResearchRequest`, `listResearchRequests` and `getResearchRequest`:

- Kinds a bank may ask for: `run_now`, `check_source` (a registered source), `check_url` (a
  public URL) and `research_topic`. Each names one of the **bank's own** agents; a request
  naming a platform agent answers 403 through `refuse_platform_agent()`, and a request from a
  bank with **no agent of its own** answers 409 `no_tenant_agent` with the reason in
  user-facing words — it cannot command a platform agent (the default taken above).
- Each request opens a run with `trigger='request'` and the request on it, so the request is a
  job with a status endpoint (`GET /research-requests/{requestId}`, plan-wide rule 14).
- `check_url` validates the URL at the boundary: scheme `https` only, no private or
  loopback address, no redirect to one, and the host is not in `STANDARDS_PUBLISHER_HOSTS`
  (D-45). The fetched body is screened by `agents/screen.py` exactly as chunk 5 built it, and
  is stored as data, never executed and never rendered as HTML.
- `RESEARCH_REQUESTS_PER_MONTH` is a setting with an env override; above it the request
  answers 429 `plan_limit_reached`.
- A request inherits the budget cap: a bank at its cap answers 422 `budget_cap_reached`.
- `topic` is tenant text and never leaves the tenant's zone: it reaches the tenant-scoped
  runner and no platform run, no shared library row and no log (D-32).

**Owned paths:**

- `backend/apps/agents/requests.py` (the tenant half only)
- `backend/apps/agents/tests_requests.py`
- `backend/config/settings.py` (one labelled block), `backend/.env.example`,
  `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- Each of the four kinds creates a request and opens a run with `trigger='request'`.
- A request naming a platform agent answers 403; a bank with no agent of its own answers 409
  `no_tenant_agent`.
- A `check_url` with `http`, a private address, a loopback address, a redirect to one or a
  publisher host from `STANDARDS_PUBLISHER_HOSTS` is refused, each with its own test.
- A fetched body containing "ignore previous instructions" is flagged by the screen and stored
  as data, proved by a test.
- Above `RESEARCH_REQUESTS_PER_MONTH` the request answers 429 `plan_limit_reached`.
- A bank at its cap answers 422 `budget_cap_reached`.
- Tenant B reading tenant A's request gets 404; no request text reaches a log or Sentry,
  proved by a test.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.watch apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Fetched content is untrusted: screened, stored as data, never executed, never rendered as
  HTML.
- Input from the network is never an impossible case; validation at the trust boundary.
- A tenant's own agent writes only in that bank's zone.
- Tenant content never reaches logs, Sentry, analytics or an unapproved model endpoint.

### c11-research-requests-b: the console's re-tag request

**Requirements:** AGT-05, PRO-04
**Scenarios:** AGT-S7 (`@integration`, un-skipped)
**Depends on:** `c11-research-requests-a`, `c11-batch-proposals-b`

Build `backend/apps/agents/requests.py`'s console half, serving `createRetagRequest`:

- A library editor holding `proposals.review` asks for a re-tag ("re-tag custody records with
  Client money"). The request runs against the platform's own agent, produces **one batch
  proposal** with its preview, and never a direct edit.
- The request is a job: it answers at once with a row whose status is read from
  `GET /research-requests/{requestId}`, and the batch id appears on it when the run closes.
- A tenant session answers 403: re-tagging library records is asked in the platform console
  (AGT-05).
- The request's `tenant_id` is NULL and it reads no tenant row.

**Owned paths:**

- `backend/apps/agents/requests.py` (the console half only)
- `backend/apps/agents/tests_requests.py` (the console cases only)
- `backend/apps/agents/tests_scenarios.py` (the AGT-S7 test only)
- `backend/apps/agents/app.md` (AGT-05's status cell only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- `test_agt_s7` is green, written before the code and reworded to the split: a tenant admin
  holding `agents.manage` requests "check this source now" and "research DORA subcontracting"
  on the bank's own agent, a library editor requests "re-tag custody records with Client
  money" in the console, three research requests exist with their kinds, and the re-tag
  produces one batch proposal with a preview and no direct edit.
- A tenant session calling `POST /console/research-requests` answers 403.
- The re-tag request reads no tenant row, proved with two tenants' rows present.
- The batch the request produces is the one `c11-batch-proposals-a` creates; no second
  creation path exists, proved by a test that counts the writers.
- No chunk 11 line of `contract_drift_pending.txt` for the research operations is left.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.proposals apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*,apps/proposals/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Agents find and propose; people decide. A re-tag is a proposal, never an edit.
- Four eyes on the approval that follows.
- A platform request reads no tenant row.

### c11-ai-off-switch: the tenant's AI off switch stops the tenant's AI, and only that

**Requirements:** AGT-04
**Scenarios:** none (AGT-S6 is `c11-run-scheduler-b`'s)
**Depends on:** `c11-tenant-agent-controls-b`, `c11-run-scheduler-b`, `c7-ask-switch`,
`c7-ask-backend`
**Security review:** yes (a switch that must not stop the platform's coverage)
**Keys:** `agentstasks`

**`c7-ask-switch` already built the check and its proof**, inside `c5-ai-log-contract`'s one
wrapper (parallel-plan ruling 13 and rule 1): the wrapper reads `Tenant.ai_enabled` only when
a tenant is active, a tenant call with the switch off raises 403 `feature_off` before the
adapter, Ask is refused, and `backend/apps/governance/tests_ai_switch.py` proves in one run
that a platform model call still goes through untouched. None of that is rebuilt or restated
here, and this task does **not** write the wrapper.

What is left is the one path chunk 7 could not reach, because it did not exist yet: **a
tenant's own agent runs**. This task extends the existing check to them, and to nothing else:

- A tenant agent run is refused **before it opens**, not part-way through its first model
  call. The scheduler and `runTenantAgentNow` both open a run through the one opener in
  `agents/tasks.py`, and the check goes there, once: the control answers 422 `feature_off` and
  the schedule skips the run with an audit row, so a bank with AI off does not accumulate
  half-finished runs. `agents/control.py` is not edited; it calls the same opener.
- A run already in flight when the switch goes off fails its next model call through the
  wrapper's existing check, with the tenant active under `@tenant_task`, and the run closes as
  interrupted rather than as an error with a trace.
- **bleqq's platform runs are untouched**, which the wrapper's no-tenant rule already
  guarantees; this task adds no second reader of the switch and no new place it is consulted.

**Owned paths:**

- `backend/apps/agents/tasks.py` (the pre-run check only)
- `backend/apps/agents/tests_ai_off.py` (new: the agent-run cases only)

**Done when:**

- With a tenant's AI off, `runTenantAgentNow` answers 422 `feature_off` and opens no run.
- With a tenant's AI off, the scheduled run for that tenant is skipped with one audit row and
  no `agent_run` row, proved with a frozen clock.
- A run in flight when the switch goes off closes as interrupted, with no trace in the
  response and no `ai_generation` row for the call that did not happen.
- Every other tenant's and the platform's runs are unaffected in the same test run.
- The diff adds no second switch, no second column, no second reader of `ai_enabled` and no
  screen file, and does not touch the wrapper `c7-ask-switch` owns.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- One check, in the wrapper `c7-ask-switch` already extended; this task adds a caller, not a
  second reader of the switch.
- A tenant's switch stops the tenant's AI and never bleqq's coverage.
- The client branches on `code`, never on `detail`.

### c11-platform-runs: the console's platform run list

**Requirements:** AGT-03, ADM-02
**Scenarios:** none
**Depends on:** `c11-run-scheduler-a`, `c11-platform-agent-settings-a`,
`c5-watch-sources-coverage`, `c5-fe-console-sources`
**Security review:** yes (a platform surface that must carry no tenant content)

Build `listPlatformRuns` in `backend/apps/agents/platform.py`: the platform's own runs, newest
first, with status, trigger, duration, cost, `changes_found`, `proposals_made` and the source
coverage of each run, linking to the console Sources page chunk 5 built. Paged at 20 with a
maximum of 100.

**No tenant run appears**, and no tenant name, count or figure appears on any row: a platform
surface carries platform facts. A test with tenant runs seeded asserts the list excludes them,
and a second test asserts the response schema has no field that could carry a tenant's name.

**Owned paths:**

- `backend/apps/agents/platform.py` (the run list only)
- `backend/apps/agents/tests_platform.py` (the run-list cases only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- The route answers 200 for `agent_definitions.manage` and 403 for every tenant role and every
  API key.
- No tenant run and no tenant figure appears, proved with both kinds seeded.
- Each row carries the run's source-check counts from chunk 5's coverage log, with one query
  per page rather than one per row, pinned by a query-count test.
- Paging defaults to 20, caps at 100, and orders stably.
- The endpoint answers inside the 250 ms budget with 200 seeded runs and asserts
  `Server-Timing: app`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.watch apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/agents/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Tenant content never reaches a platform surface.
- Fan out, never chain; paginate (default 20, maximum 100).
- An empty answer is 200.

### c11-fe-console-agent-definitions-a: the console's definition list and publish

**Requirements:** AGT-03, ADM-02
**Scenarios:** none
**Depends on:** `c11-agent-definitions-contract-b`, `c11-platform-agent-settings-b`,
`c11-cards-agents-b`, `c4-console-shell`, `x-frontend-split`
**Keys:** `agentsfe`

Build the first half of the console's Agent definitions screen against
`design/screens/console-agent-definitions.html`:

- `frontend/src/features/agents/{types,api,hooks}.ts` are created here (the head of rule 4's
  chain) and carry only the operations this screen calls: `listAgentDefinitions`,
  `getAgentDefinition`, `publishAgentVersion`, `retireAgentVersion`.
- `agents-presentation.ts` gives the pill for a definition's scope and a version's state,
  through `Pill` and `tone-by-kind.ts`, never a tone chosen in the component.
- The screen lists definitions, opens one with its versions, and publishes a version behind
  the step-up dialog the app already has.
- Its own catalog namespace, `console-agents`, in `src/messages/`; every string in it, no
  string literal in JSX.
- A navigation entry in `registry.ts` for `/console/agents`, gated by
  `agent_definitions.manage`.

**Owned paths:**

- `frontend/src/features/agents/{types,api,hooks,agents-presentation}.ts` and their tests
- `frontend/src/components/console/AgentDefinitionsScreen.tsx`,
  `AgentDefinitionDetail.tsx`
- `frontend/src/app/(console)/console/agents/page.tsx`
- `frontend/src/messages/console-agents/{en,sv}.json`
- `frontend/src/shared/navigation/registry.ts` (its own entry only)
- `frontend/src/features/shared/tone-by-kind.ts` (its own entries only)

**Done when:**

- The screen renders the seeded definitions against the real backend, in light and dark, at
  375 px and at desktop width, with no horizontal scroll.
- A publish asks for the passkey step-up and shows the new version on success.
- A session without `agent_definitions.manage` does not see the navigation entry and gets the
  structured 403 the UI renders as is if it reaches the route.
- Every pill comes from `Pill` and a presentation function; no tone is chosen in a component.
- `npm run check:messages` and `check:copy-drift` are green; no string literal sits in JSX.
- No route this screen calls answers 501.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Pills only through `Pill`; six tones by slot or kind.
- Typography roles only; every string in the message catalogs.
- Screen copy says what the user is doing: no requirement IDs on screen.
- No screen calls a stub.

### c11-fe-console-agent-definitions-b: platform settings and platform runs

**Requirements:** AGT-03, ADM-02
**Scenarios:** ADM-S4 extended (both halves stay green; this task adds the surface, un-skips
nothing)
**Depends on:** `c11-fe-console-agent-definitions-a`, `c11-platform-runs`
**Keys:** `agentsfe`

Add the two remaining panels of the console screen:

- **Settings** for a platform-scoped definition: cadence, the jurisdictions it sweeps, the
  budget, each saved behind the step-up dialog, each with the plain-words notice that it
  changes this for every bank.
- **Platform runs**: the recent runs with status, cost, findings and proposals, and the link
  to the console Sources page.
- ADM-S4's list of platform surfaces gains Agent definitions in `governance/app.md`'s
  scenario text and in the journey's expected set, without un-skipping anything: chunk 5 owns
  both halves and they stay green.

**Owned paths:**

- `frontend/src/features/agents/{types,api,hooks}.ts` (the settings and runs operations only)
- `frontend/src/components/console/PlatformAgentSettings.tsx`, `PlatformRunsPanel.tsx`
- `frontend/src/messages/console-agents/{en,sv}.json` (its own keys only)
- `backend/apps/governance/app.md` (ADM-S4's surface list only)
- `frontend/tests/e2e/console.journey.spec.ts` (ADM-S4's own block only, extended not
  un-fixmed)

**Done when:**

- Both panels render against the real backend in both themes and both widths.
- A settings save asks for the step-up and shows the new values.
- The runs panel shows no tenant name, count or figure.
- ADM-S4 stays green with Agent definitions in its surface set, run as
  `npm run test:e2e -- --grep "ADM-S4"`.
- `npm run check:messages` and `check:copy-drift` are green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "ADM-S4"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Tenant content never reaches a platform surface.
- `test` imported from `support/api-guard`; no API mocked in E2E.
- Pills only through `Pill`; no string literal in JSX.

### c11-fe-admin-security-a: the passkey policy panel

**Requirements:** ID-07, ADM-01
**Scenarios:** none
**Depends on:** `c11-security-policy-b`, `c11-cards-security-batch-a`, `x-frontend-split`

Build `frontend/src/features/security-policy/` and the first panel of
`/admin/security`, against `design/screens/admin-security.html`:

- Choose `Any passkey` or `Device-bound, from the list`; pick authenticators from
  `GET /reference/authenticators`; set the notice date with its 14-day default.
- Save behind the step-up dialog. The 409 `would_lock_out_actor` and the 422
  `empty_authenticator_list` are rendered as the states the card draws, from the `code`,
  never from the `detail`.
- Its own catalog namespace, `admin-security`, and a `registry.ts` entry for `/admin/security`
  gated by `security.manage`.

**Owned paths:**

- `frontend/src/features/security-policy/{types,api,hooks,security-presentation}.ts` and tests
- `frontend/src/components/admin/SecurityPolicyScreen.tsx`, `CredentialPolicyPanel.tsx`
- `frontend/src/app/(tenant)/admin/security/page.tsx`
- `frontend/src/messages/admin-security/{en,sv}.json`
- `frontend/src/shared/navigation/registry.ts` (its own entry only)

**Done when:**

- The panel renders against the real backend in both themes and both widths.
- A save asks for the step-up; both refusal states render from their `code`.
- A session without `security.manage` does not see the entry and gets the structured 403.
- `npm run check:messages` and `check:copy-drift` are green; no string literal in JSX.
- No route this panel calls answers 501.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- The client branches on `code`, never on `detail`.
- No password appears anywhere, in any state.
- Every string in the message catalogs; typography roles only.

### c11-fe-admin-security-b: the session policy panel

**Requirements:** ID-08, ADM-01
**Scenarios:** ADM-S1 extended (stays green)
**Depends on:** `c11-fe-admin-security-a`, `c11-session-policy`

Add the Sessions panel to `/admin/security`: idle and absolute limits with the platform
maximum shown beside each, and the 422 `above_platform_maximum` rendered from its `code`.
ADM-S1's surface list in `tenants/app.md` gains Security, without un-skipping either half.

**Owned paths:**

- `frontend/src/features/security-policy/{types,api,hooks}.ts` (the session fields only)
- `frontend/src/components/admin/SessionPolicyPanel.tsx`
- `frontend/src/messages/admin-security/{en,sv}.json` (its own keys only)
- `backend/apps/tenants/app.md` (ADM-S1's surface list only)
- `frontend/tests/e2e/admin.journey.spec.ts` (ADM-S1's own block only, extended not un-fixmed)

**Done when:**

- The panel renders in both themes and both widths and saves behind the step-up.
- A value above either platform maximum shows the refusal from its `code`, with the maximum
  named in the copy.
- ADM-S1 stays green with Security in its surface set, run as
  `npm run test:e2e -- --grep "ADM-S1"`.
- `npm run check:messages` and `check:copy-drift` are green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "ADM-S1"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Permissions, never role names, decide what a person sees.
- `test` imported from `support/api-guard`; no API mocked in E2E.

### c11-fe-admin-agents-a: our agents, and their controls

**Requirements:** AGT-04, ADM-01
**Scenarios:** none
**Depends on:** `c11-tenant-agent-controls-b`, `c11-run-history`, `c11-cards-agents-a`,
`c11-fe-console-agent-definitions-b`
**Keys:** `agentsfe`

Build the "Our agents" half of `/admin/agents` against `design/screens/admin-agents.html`:

- One panel per agent the bank added: status pill, version pill, what it covers, what it
  writes to, next run, cadence control, Switch on/off, Pause/Resume, Run now, Stop run.
- "Add an agent" from the tenant-scoped definitions the platform publishes, and the empty
  state for a bank with none.
- "Recent runs" from `GET /agent-runs`, with time, status, cost, trigger, who asked, findings
  and proposals.
- Its own catalog namespace, `admin-agents`, and a `registry.ts` entry for `/admin/agents`
  gated by `agents.manage`.
- Every refusal the backend can answer is a rendered state from its `code`:
  `above_plan_limit`, `agent_paused`, `agent_disabled`, `budget_cap_reached`, `feature_off`,
  `run_finished`.

**Owned paths:**

- `frontend/src/features/agents/{types,api,hooks,agents-presentation}.ts` (the tenant
  operations only) and their tests
- `frontend/src/components/admin/AgentsScreen.tsx`, `OurAgentsPanel.tsx`, `AgentRunsList.tsx`
- `frontend/src/app/(tenant)/admin/agents/page.tsx`
- `frontend/src/messages/admin-agents/{en,sv}.json`
- `frontend/src/shared/navigation/registry.ts` (its own entry only)
- `frontend/src/features/shared/tone-by-kind.ts` (its own entries only)

**Done when:**

- The screen renders against the real backend in both themes and both widths.
- Each of the six refusal codes renders its own state, proved by a unit test per code on the
  presentation function.
- No control on this screen can reach a platform agent: the panel is built from
  `GET /agents`, which returns none, and a unit test asserts the component renders no control
  for a platform row if one were ever returned.
- `npm run check:messages` and `check:copy-drift` are green; no string literal in JSX.
- No route this screen calls answers 501.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Pills only through `Pill` and a presentation function per record type.
- The client branches on `code`, never on `detail`.
- Screen copy says what the user is doing; no restated invariants on screen.

### c11-fe-admin-agents-b: what bleqq watches

**Requirements:** AGT-03, AGT-04, ADM-01
**Scenarios:** ADM-S1 extended (stays green)
**Depends on:** `c11-fe-admin-agents-a`, `c11-platform-watch-read`
**Keys:** `agentsfe`

Add the read-only "What bleqq watches" panel above "Our agents": each general agent's name,
purpose, the jurisdictions it sweeps, its check cadence, when it next runs and the status of
its last run, with no control of any kind and a one-line explanation in the bank's own words
that these run as part of the service. ADM-S1's surface list in `tenants/app.md` gains Agents.

The panel is shown to every member holding `watch.read`, not only to an admin (ruling 6), so
the screen's permission-limited state shows the bleqq panel and hides the controls rather than
answering a page-level 403.

**Owned paths:**

- `frontend/src/features/agents/{types,api,hooks}.ts` (the platform-watch operation only)
- `frontend/src/components/admin/PlatformWatchPanel.tsx`
- `frontend/src/messages/admin-agents/{en,sv}.json` (its own keys only)
- `backend/apps/tenants/app.md` (ADM-S1's surface list only)
- `frontend/tests/e2e/admin.journey.spec.ts` (ADM-S1's own block only, extended not un-fixmed)

**Done when:**

- The panel renders for a reader holding `watch.read` with no control visible, and for an
  admin above the controls.
- A reader without `agents.manage` sees the panel and a permission-limited notice, never a
  page-level 403.
- The panel shows the next run and the last run's status and nothing more: no prompt, tool,
  model, version internals, budget, cost, findings, proposal counts or setting, proved by a
  unit test on the presentation function's output shape.
- ADM-S1 stays green with Agents in its surface set, run as
  `npm run test:e2e -- --grep "ADM-S1"`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "ADM-S1"`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Nothing about a platform agent is writable by a tenant.
- A role without a permission gets a permission-limited notice, never a page-level 403.
- `test` imported from `support/api-guard`; no API mocked in E2E.

### c11-fe-agents-budget-ai: spend, the cap and the AI off switch

**Requirements:** AGT-04, ADM-01
**Scenarios:** none
**Depends on:** `c11-fe-admin-agents-b`, `c11-run-scheduler-b`, `c11-ai-off-switch`,
`c7-ask-switch`
**Keys:** `agentsfe`

Add the "Spend this month" panel to `/admin/agents`: the figure, the cap, the meter with its
accessible label, "Set cap", and the line naming bleqq's watch as running at bleqq's cost so
the figure is not misread (ruling 3).

The AI off switch sits beside it and is **`c7-ask-switch`'s route, not a second switch**: it
reads and writes `aiEnabled` on the organisation profile, which is gated by `security.manage`
**and `@requires_step_up`**. So the control here:

- calls that same route behind the step-up dialog the other security writes use, and treats a
  403 `step_up_required` as the prompt to re-assert rather than as an error state;
- renders **read-only** for a member without `security.manage` — the current value with a
  permission-limited notice, never a page-level 403 and never a control that would 403 on
  click. An admin holds both `agents.manage` (the rest of this screen) and `security.manage`,
  so on the common path both halves are writable;
- reuses `c7-ask-switch`'s organisation-namespace copy for the switch itself and adds only the
  line that places it on this screen. The copy still says the switch stops the bank's own AI
  and says nothing about bleqq's watch, which it does not touch.

**Owned paths:**

- `frontend/src/features/agents/{types,api,hooks}.ts` (the budget operations only)
- `frontend/src/components/admin/AgentBudgetPanel.tsx`, `AiOffSwitch.tsx`
- `frontend/src/messages/admin-agents/{en,sv}.json` (its own keys only)

**Done when:**

- The panel renders against the real backend in both themes and both widths, and the meter
  carries an accessible label with the percentage.
- Setting a cap below the month's spend succeeds and the screen shows the paused state.
- Switching AI off goes through the step-up dialog against `c7-ask-switch`'s route, shows the
  state and the consequence in the bank's own words, and switching it on restores it.
- A refused or cancelled step-up leaves the switch as it was, proved by a component test.
- A member with `agents.manage` but not `security.manage` sees the switch read-only with the
  permission-limited notice, proved by a component test.
- The panel names bleqq's watch as outside the figure, in the catalog, not in JSX.
- `npm run check:messages` and `check:copy-drift` are green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- One AI switch, one column, one route; this screen adds no second one.
- A security change carries a passkey step-up; a refused step-up changes nothing.
- Permissions, never role names; a missing permission is a read-only state, not a page 403.
- Every string in the message catalogs; typography roles only.
- WCAG AA in both themes, including the meter.

### c11-fe-research-requests: asking the bank's own agents

**Requirements:** AGT-05, ADM-01
**Scenarios:** none
**Depends on:** `c11-research-requests-a`, `c11-fe-agents-budget-ai`, `c11-cards-agents-a`
**Keys:** `agentsfe`

Add the research-request panel to `/admin/agents`: "Check this source now" (from the registered
sources), "Check a URL", "Research a topic", each naming one of the bank's own agents, with the
request list and each request's status read from its status endpoint.

The 409 `no_tenant_agent` is a rendered state that explains, in the bank's own words, that the
bank must add an agent of its own first and that bleqq's watch runs on its own schedule. The
429 `plan_limit_reached` and the 422 `budget_cap_reached` are rendered from their codes too.

**Owned paths:**

- `frontend/src/features/agents/{types,api,hooks}.ts` (the research operations only)
- `frontend/src/components/admin/ResearchRequestPanel.tsx`, `ResearchRequestList.tsx`
- `frontend/src/messages/admin-agents/{en,sv}.json` (its own keys only)

**Done when:**

- Each of the three request kinds can be made against the real backend and appears in the list
  with its status.
- The three refusal codes each render their own state, proved by a unit test per code.
- A request's status is polled from its status endpoint, never computed in the client.
- `npm run check:messages` and `check:copy-drift` are green; no string literal in JSX.
- No route this panel calls answers 501.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Every agent run is a job with a status endpoint; the client reads it and invents nothing.
- The client branches on `code`, never on `detail`.
- Screen copy says what the user is doing.

### c11-fe-console-batch-review-a: the batch preview and its row decisions

**Requirements:** PRO-04, ADM-02
**Scenarios:** none (PRO-S8's `@e2e` half is `c11-e2e-definitions-requests-b`'s)
**Depends on:** `c11-batch-proposals-b`, `c11-cards-security-batch-b`, `c4-fe-approve`
**Keys:** `consoleq`

Build the batch variant of the console queue detail against
`design/screens/console-queue-batch.html`: the batch header, the preview table with before and
after per row, per-row approve and reject with a reason from the vocabulary, "Approve the
rest", "Reject all", and the step-up dialog on decide.

The result state shows how many changed and how many did not, and links to the audit entry.
`four_eyes_violation` and `stale_write` are rendered from their codes as the card draws them.

**Owned paths:**

- `frontend/src/features/proposals/{types,api,hooks}.ts` (the batch operations only)
- `frontend/src/components/console/BatchReviewScreen.tsx`, `BatchPreviewTable.tsx`
- `frontend/src/messages/console-queue/{en,sv}.json` (its own keys only)

**Done when:**

- A seeded batch renders against the real backend in both themes and both widths, with the
  table readable at 375 px.
- Per-row and whole-batch decisions both work, behind the step-up.
- `four_eyes_violation` and `stale_write` render their own states from their codes.
- The result state shows the counts and links to the audit entry.
- `npm run check:messages` and `check:copy-drift` are green; no string literal in JSX.
- No route this screen calls answers 501.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Four eyes with a step-up on approval; the refusal is a state, not a crash.
- A rejection carries a reason from a vocabulary row.
- Pills only through `Pill`; no string literal in JSX.

### c11-fe-console-batch-review-b: asking for a re-tag

**Requirements:** AGT-05, PRO-04, ADM-02
**Scenarios:** none
**Depends on:** `c11-fe-console-batch-review-a`, `c11-research-requests-b`
**Keys:** `consoleq`

Add the "Ask for a re-tag" form to the console queue: the records to re-tag, the term to add,
the near-duplicate hint from the vocabulary picker, and the request's status read from its
status endpoint until the batch it produced appears, at which point the screen links to it.

This is the console half of `c11-fe-research-requests`, kept here because it writes the same
console surface and the same catalog namespace (the change from `PARALLEL_PLAN` above).

**Owned paths:**

- `frontend/src/features/proposals/{types,api,hooks}.ts` (the retag-request operation only)
- `frontend/src/components/console/RetagRequestForm.tsx`
- `frontend/src/messages/console-queue/{en,sv}.json` (its own keys only)

**Done when:**

- A re-tag request can be made against the real backend, shows its status, and links to the
  batch when it appears.
- The near-duplicate hint comes from the vocabulary check the picker already uses, not from a
  second lookup.
- A tenant session never reaches the form: it is behind `proposals.review` and the console
  shell.
- `npm run check:messages` and `check:copy-drift` are green.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- A re-tag is a proposal, never an edit.
- Every agent run is a job with a status endpoint.
- Create where you use it, with a near-duplicate hint.

### c11-e2e-seed: the chunk 11 seed for E2E

**Requirements:** AGT-03, AGT-04, AGT-05, PRO-04
**Scenarios:** none
**Depends on:** `c11-agent-definitions`, `c11-batch-proposals-b`,
`c11-tenant-agent-controls-b`, `c3-seed-provisions`

Extend `backend/apps/shared/e2e_seed.py` with one seed call for chunk 11, idempotent,
deterministic and clock-anchored (plan-wide rule 13), from the prototype's data:

- Two platform definitions with published versions (`watch-sweeper` at v1 and v2, so AGT-S4's
  journey has a version to publish against) and one tenant-scoped definition
  (`tenant-source-watch`).
- For tenant A: one tenant agent of its own, switched on, weekly, with a scope; a handful of
  its runs across the last four weeks with costs that put the month's spend near a cap; and a
  budget row with that cap. For tenant B: none, so the "no agent of its own" state and
  AC-NFR1's 404 both have a subject.
- Platform runs for the platform agents, so the console's list is not empty and the tenant's
  history can be proved to exclude them.
- One open batch proposal of twelve rows, created through `c11-batch-proposals-a`'s own
  function rather than by hand, so the seed cannot drift from the code.
- One platform admin login and one tenant admin login holding `agents.manage`, added to
  `e2e_logins.py` and `passkeys.ts` as one login each.
- Every date is derived from the seed anchor, never from the real "today": a month boundary
  must not change what the spend panel shows.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (one seed call only)
- `backend/apps/shared/e2e_logins.py`, `e2e_passkeys.py` (one login each)
- `frontend/tests/e2e/support/passkeys.ts` (the LOGINS map, its own entries only)
- `backend/apps/agents/tests_seed.py`

**Done when:**

- `seed_e2e` is idempotent: a second run creates nothing and changes nothing, proved by a
  test.
- Every seeded date is derived from the anchor; a test with the clock moved across a month
  boundary asserts the spend figure is unchanged.
- The seeded batch is created through the real function, proved by a test that fails if a row
  is built by hand.
- Tenant B has no agent of its own and no budget row.
- The seed integrity guard is green and lists the new tables.
- `npm run test:e2e -- --grep @smoke` still passes with the new seed.

**Gates:**

- `set -a; . ./.env.worktree; set +a` (or `bash scripts/cloud-setup.sh --e2e`)
- `cd backend && ./run.sh run coverage run manage.py test apps.agents apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `cd frontend && npm run test:e2e -- --grep @smoke`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Extend `seed_e2e`, never mock: idempotent, deterministic, realistic.
- Clocks anchor to the tenant-local date plus a fixed wall time.
- Two tenants, so isolation has a subject on every surface.

### c11-e2e-agent-controls-a: AGT-S5's journey

**Requirements:** AGT-04
**Scenarios:** AGT-S5 (`@e2e`, un-fixmed)
**Depends on:** `c11-fe-admin-agents-b`, `c11-tenant-agent-controls-b`,
`c11-platform-watch-read`, `c11-run-scheduler-b`, `c11-run-history`, `c11-e2e-seed`

Write the AGT-S5 journey in `frontend/tests/e2e/agents.journey.spec.ts`, against the real
stack: a production Next build, the real backend on a freshly seeded throwaway database, and
passkey sign-in through the UI with the virtual authenticator. `test` is imported from
`support/api-guard`; any expected error is declared where it happens.

The journey: the tenant admin signs in, opens `/admin/agents`, sees "What bleqq watches" with
no control on it, switches on the bank's own agent, sets a weekly cadence, restricts the scope
to SE and FI, chooses "Run now", sees the run in "Recent runs" with its cost, chooses "Stop
run" and sees the interrupted status, then tries a cadence above the plan limit and sees the
`above_plan_limit` state (declared with `apiGuard.allow`).

The bleqq panel is asserted to carry no control and no budget figure, which is AGT-S14's
screen half.

**Owned paths:**

- `frontend/tests/e2e/agents.journey.spec.ts` (the AGT-S5 block only)
- `frontend/tests/e2e/support/agent-controls.ts` (this task's own helper file)
- `backend/apps/agents/app.md` (AGT-S5's status only)

**Done when:**

- `npm run test:e2e -- --grep "AGT-S5"` is green against the real stack, with no mocked API
  and no injected token or cookie.
- The journey settles before branching (`await expect(a.or(b).first()).toBeVisible()`) and
  uses exact text where copy can collide.
- The `above_plan_limit` response is declared with `apiGuard.allow` where it happens, and no
  other `/api/` response of 400 or above is undeclared.
- Teardown restores the seeded data, on failure too.
- The journey is clock-anchored and passes with the clock moved a week forward.

**Gates:**

- `bash scripts/cloud-setup.sh --e2e` (or the slot's env locally)
- `cd frontend && npm run test:e2e -- --grep "AGT-S5"`
- `npm run lint && npm run typecheck`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Sign in through the UI with a passkey; never inject tokens or cookies.
- Never mock an API in E2E; backend down means tests fail.
- Declare an expected error where it happens.

### c11-e2e-agent-controls-b: AGT-S6's journey

**Requirements:** AGT-04
**Scenarios:** AGT-S6 (`@e2e`, un-fixmed)
**Depends on:** `c11-e2e-agent-controls-a`, `c11-fe-agents-budget-ai`, `c11-ai-off-switch`

Write the AGT-S6 journey in the same spec file, its own block only (rule 6): with the seeded
spend near the cap, the admin sets a cap the next run would exceed, sees the agent paused and
the notice, then switches all AI features off, sees Ask answer its `feature_off` state, and
sees "What bleqq watches" still listing its next run — the line that proves a tenant switch
never stops bleqq's coverage.

**Owned paths:**

- `frontend/tests/e2e/agents.journey.spec.ts` (the AGT-S6 block only)
- `frontend/tests/e2e/support/agent-budget.ts` (this task's own helper file)
- `backend/apps/agents/app.md` (AGT-S6's status only)

**Done when:**

- `npm run test:e2e -- --grep "AGT-S6"` is green against the real stack.
- Ask's `feature_off` response is declared with `apiGuard.allow` where it happens.
- The bleqq panel still shows a next run with AI off, asserted by exact text.
- No figure on the spend panel includes a platform run, asserted against the seeded numbers.
- Teardown restores the seeded data, on failure too.

**Gates:**

- `bash scripts/cloud-setup.sh --e2e`
- `cd frontend && npm run test:e2e -- --grep "AGT-S6"`
- `npm run lint && npm run typecheck`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- A tenant's switch stops the tenant's AI and never bleqq's coverage.
- `test` imported from `support/api-guard`; expected errors declared where they happen.

### c11-e2e-definitions-requests-a: AGT-S4's journey

**Requirements:** AGT-03
**Scenarios:** AGT-S4 (`@e2e`, un-fixmed)
**Depends on:** `c11-fe-console-agent-definitions-b`, `c11-platform-agent-settings-b`,
`c11-e2e-seed`

Write the AGT-S4 journey in `frontend/tests/e2e/console.journey.spec.ts`, its own block only:
the platform admin signs in, opens `/console/agents`, publishes a new version of
`watch-sweeper` with a change note behind the step-up, sees the version list grow, and sees an
earlier run still naming the earlier version. Then the tenant admin signs in and cannot reach
`/console/agents` at all — the navigation entry is absent and a direct visit answers the
structured 403 the UI renders as is.

**Owned paths:**

- `frontend/tests/e2e/console.journey.spec.ts` (the AGT-S4 block only)
- `frontend/tests/e2e/support/agent-definitions.ts` (this task's own helper file)
- `backend/apps/agents/app.md` (AGT-S4's status only)

**Done when:**

- `npm run test:e2e -- --grep "AGT-S4"` is green against the real stack.
- The step-up is completed through the UI with the virtual authenticator, never bypassed.
- The tenant's 403 is declared with `apiGuard.allow` where it happens.
- The earlier run's version is asserted by exact text, so a version bump cannot pass silently.
- Teardown restores the seeded data, on failure too.

**Gates:**

- `bash scripts/cloud-setup.sh --e2e`
- `cd frontend && npm run test:e2e -- --grep "AGT-S4"`
- `npm run lint && npm run typecheck`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Step-up through the UI with a passkey; never injected.
- Definitions are the platform's; no tenant principal reaches one.

### c11-e2e-definitions-requests-b: AGT-S7's and PRO-S8's journey

**Requirements:** AGT-05, PRO-04
**Scenarios:** AGT-S7 (`@e2e`, un-fixmed), PRO-S8 (`@e2e`, un-fixmed)
**Depends on:** `c11-e2e-definitions-requests-a`, `c11-fe-research-requests`,
`c11-fe-console-batch-review-b`, `c11-research-requests-b`, `c11-e2e-seed`

Write two journeys, each in its own block:

- **AGT-S7**, in `agents.journey.spec.ts`: the tenant admin asks "check this source now" and
  "research DORA subcontracting" on the bank's own agent and sees both requests with their
  status; then, in the console, the library editor asks for "re-tag custody records with
  Client money" and sees the request produce one batch proposal with a preview.
- **PRO-S8**, in `console.journey.spec.ts`: the editor opens that batch, sees the twelve rows
  with before and after, rejects two, approves the rest behind the step-up, and sees ten
  records changed, two unchanged, and one audit entry naming each row's outcome. A second
  editor is used for the approval, so four eyes holds; the first editor's own attempt is
  asserted to answer `four_eyes_violation`, declared with `apiGuard.allow`.

**Owned paths:**

- `frontend/tests/e2e/agents.journey.spec.ts` (the AGT-S7 block only)
- `frontend/tests/e2e/console.journey.spec.ts` (the PRO-S8 block only)
- `frontend/tests/e2e/support/agent-requests.ts` (this task's own helper file)
- `backend/apps/agents/app.md`, `backend/apps/proposals/app.md` (AGT-S7's and PRO-S8's status
  only)

**Done when:**

- `npm run test:e2e -- --grep "AGT-S7|PRO-S8"` is green against the real stack.
- The four-eyes refusal is driven through the UI and declared where it happens.
- The audit entry is opened from the result state and asserted to name each row's outcome.
- No API is mocked and no token or cookie is injected anywhere in either journey.
- Teardown restores the seeded data, on failure too.

**Gates:**

- `bash scripts/cloud-setup.sh --e2e`
- `cd frontend && npm run test:e2e -- --grep "AGT-S7|PRO-S8"`
- `npm run lint && npm run typecheck`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Agents find and propose; people decide.
- Four eyes with a step-up; never the proposer.
- Never mock an API in E2E.

### c11-security-review-a: the agents sweep

**Requirements:** AGT-03, AGT-04, AGT-05, AGT-06
**Scenarios:** none
**Depends on:** `c11-e2e-definitions-requests-b`, `c11-e2e-agent-controls-b`,
`c11-platform-runs`, `c11-fe-research-requests`, `f03-T82`

A security-review sub-agent reads the merged diff of every agents task in this chunk against
`main`, with the guard suites running beside it (`tests_rls`, `tests_tenant_isolation`,
`tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`).
What it must prove rather than assume:

- **The platform fence holds at every layer**: the database CHECK on `tenant_agent`, the
  `refuse_platform_agent()` call on every tenant control route, and the absence of any tenant
  path to a definition, a platform setting or a platform run. It re-runs AGT-S14 and reads the
  routes itself rather than trusting the guard test.
- **A tenant agent writes only the tenant's zone**: no chunk 11 code path calls
  `library_write()`, the fence allowlist is byte-identical to `main`'s before the chunk, and
  no agent key scope reaches a library table.
- **A platform run reads no tenant row**: the scheduler's platform half is not a
  `@tenant_task`, `scope.py` is unreachable from it, and no platform surface carries tenant
  content.
- **Fetched and external content is untrusted**: `check_url`'s boundary validation, the
  screen on every fetched body, and the runner event's validation.
- **Budget and cap cannot be escaped**: the two cap points, the month boundary, and a
  concurrent pair of "Run now" calls at the cap.
- **Secrets and content in logs**: no research topic, request URL, attestation blob or run
  error text reaches a log, Sentry or an error body.
- **Audit**: one row per write, in the same transaction, with the assertion id where a step-up
  was asked.

A critical or high finding blocks the merge of anything still open and goes to
`c11-review-fixes`. A finding at medium or below that belongs to another chunk becomes a row
in `HARDENING.md` and a package.

**Owned paths:**

- `docs/reviews/` (the review's own file)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- Every bullet above is answered with the file and line that proves it, or with a finding.
- The six guard suites are green on the reviewed commit.
- Each finding carries a severity, the invariant or rule it breaks, and the task that fixes it.
- The review file names the commit it read.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write apps.shared.tests_four_eyes --settings=config.test_settings --noinput`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No gate is lowered and no finding is waved through; a review that finds nothing at medium or
  above says so in writing.

### c11-security-review-b: the identity and proposals sweep

**Requirements:** ID-07, ID-08, PRO-04
**Scenarios:** none
**Depends on:** `c11-fe-admin-security-b`, `c11-fe-console-batch-review-b`,
`c11-credential-policy-b`, `c11-session-policy`, `c11-batch-proposals-b`

A second security-review sub-agent reads the merged diff of the credential policy, the session
policy, the security policy row and the batch proposals, with the same guard suites. What it
must prove:

- **The credential policy cannot lock a tenant out by accident**: the empty-root refusal, the
  acting-admin lock-out refusal, the notice date's three points in time, and that a refused
  passkey is kept rather than deleted.
- **The attestation path trusts nothing**: every refusal reason has a planted-statement test,
  and py_webauthn's own result is not the policy.
- **The session policy narrows and never widens** the platform maximums, and a platform
  session reads no tenant row.
- **The batch is one door**: four eyes before anything is decided, the step-up on the decide,
  one transaction for the applied rows, no tenant principal and no API key on the decide
  route, and a stale row refused.
- **Audit and secrets**: one row per decided row plus one for the batch, each with the
  assertion id, and no attestation blob, AAGUID or certificate in a log.

**Owned paths:**

- `docs/reviews/` (the review's own file)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- Every bullet above is answered with the file and line that proves it, or with a finding.
- The six guard suites are green on the reviewed commit.
- Each finding carries a severity, the invariant or rule it breaks, and the task that fixes it.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write apps.shared.tests_four_eyes --settings=config.test_settings --noinput`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- No passwords, ever; four eyes; step-up on approvals and security changes.
- No gate is lowered.

### c11-review-fixes: fix what the reviews found

**Requirements:** the ones each finding names
**Scenarios:** the ones each finding names
**Depends on:** `c11-security-review-a`, `c11-security-review-b`

Fix every critical, high and medium finding of both reviews, re-run each review on the fix
diff, and repeat until nothing at medium or above remains. A finding that belongs to a later
chunk becomes a row in `HARDENING.md` with its owner, never a silent pass. When both reviews
find nothing at medium or above, this task closes at once with a note saying so.

Owned paths are whatever the findings name; the task lists them in its commit body and stays
inside them.

**Done when:**

- No critical, high or medium finding is open in either review.
- Each fix has a test that fails without it, written first.
- Each deferred finding is a `HARDENING.md` row with a severity, a reason and an owner.
- The six guard suites and the full backend suite are green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash scripts/prepush.sh --quick`

**Invariants:**

- Never lower a gate, skip or quarantine a test, or mock an API in E2E.
- A guard, test, audit row, permission check or validation is never simplified away.

### c11-chunk-close: statuses, floors and the ledger

**Requirements:** AGT-03 to AGT-06, PRO-04, ID-07, ID-08, ADM-01, ADM-02
**Scenarios:** none
**Depends on:** every other chunk 11 task, `c11-review-fixes`

Close the chunk:

- **Statuses.** Set the status cell of every requirement this chunk delivered in
  `backend/apps/agents/app.md`, `identity/app.md`, `proposals/app.md`, `tenants/app.md` and
  `governance/app.md` to `built` or `verified` as its scenarios warrant, and leave a cell at
  `in_progress` only with the chunk that finishes it named beside it. Two do: AGT-06 stays
  `in_progress` until a real runner exists, with ruling 4's reason, and **ID-07 stays
  `in_progress` with chunk 13 named**, because item 8's member list, `meetsPolicy` and shell
  notice are deferred to `c13-fe-credential-compliance` (see Cut). ID-S16 is green either way:
  it covers the enforcement, not the telling.
- **No stubs.** Prove that no chunk 11 route answers 501 `not_built` and that
  `backend/scripts/contract_drift_pending.txt` holds no chunk 11 line left.
- **No fixmes.** Prove that every chunk 11 journey is un-fixmed and green, and that every
  scenario the ownership table names is un-skipped, by running the full suite
  (`npm run test:e2e`) and the full backend suite.
- **Guards untouched.** Prove that the chunk's whole diff against `main` at its start touches
  none of `tests_library_fence.py` and its allowlists, `UNGATED_BY_DESIGN`,
  `authentication.py`, `tenancy.py`, `middleware.py` or the production boot guard (ruling 2).
- **Floors.** Measure the chunk's coverage on a full run and set the chunk 11 floors in
  `backend/scripts/coverage_gate.py`, with the date beside each. Never lower an existing one.
- **Ledger.** Write the non-blocking confirmations and `q-tenant-definition` into
  `docs/TODO_FOR_alex.md`, each with its default and its reason; **split the UI plan's row 92
  into one row per screen** (`admin-agents.html`, `console-agent-definitions.html`) **and its
  row 95 into one row per screen** (`admin-security.html` moved to chunk 11 by ruling 7,
  `admin-integrations.html` left at chunk 13), then set each of those rows and the batch row to
  "designed" or further as the cards and screens warrant — every chunk 11 edit to that file is
  this task's (plan-wide rule 6); update `docs/plans/IMPLEMENTATION_STATUS.md`; and close the
  chunk's `INPUT_DELTAS.md` rows that this chunk answered.
- **Held work named**: `c11-runner-managed-agents` with ruling 4's reason, and anything the
  contingency left behind (the AGT-S6 notification line if chunk 10 was late).

**Owned paths:**

- `backend/apps/*/app.md` (status cells only)
- `backend/scripts/coverage_gate.py`
- `docs/plans/IMPLEMENTATION_STATUS.md`, `docs/plans/UI_Implementation_Plan.md`,
  `docs/TODO_FOR_alex.md`, `docs/inputs/INPUT_DELTAS.md`
- `backend/scripts/contract_drift_pending.txt`

**Done when:**

- No chunk 11 route answers 501, proved by a test that walks the chunk's operation ids.
- No chunk 11 journey is fixme and the full E2E suite is green.
- The full backend suite and `coverage_gate.py` are green with the new floors.
- `prepush.sh --all` is green.
- The guard-diff check passes and its command is written into the commit body so it can be
  re-run.
- Every open question and default is a row in `docs/TODO_FOR_alex.md`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `bash scripts/prepush.sh --all`
- `cd frontend && npm run test:e2e`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- No gate is lowered; coverage floors only ratchet up.
- A chunk closes with its state written down, not remembered.

### c11-runner-managed-agents (held, in no wave)

**Requirements:** AGT-06
**Scenarios:** none
**Depends on:** `c11-runner-adapter`, `c11-run-scheduler-b`, `k-managed-agents`
**Held because:** ruling 4. D-54 and ADR 0047 refuse `managed_agents` on every deployed
environment except `ENVIRONMENT=test`, so the runner D-08 named first cannot ship. The seam,
the mock and the event handling are built by `c11-runner-adapter`; the real runner is the
Agent SDK leg in our own worker on Bedrock in an EU region, which needs an amendment to
ADR 0008 and a Verification log row from current provider documentation before a line is
written. This task stays in the plan with that reason so it is not dispatched by mistake.
