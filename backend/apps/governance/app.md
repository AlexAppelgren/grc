# governance — Audit, AI governance and the platform console

> **App spec.** Source: `PRD.md` Module AUD (AUD-01–AUD-04, AC-AUD1) and ADM-02,
> playbook 4.3 (`record()`, `AppendOnlyModel`), 14 (mixed tables), 16 (`ai_generation`),
> `docs/inputs/INPUT_DELTAS.md` §6.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

Every decision is logged. `record()` in `apps/shared/audit.py` is the only way
to write an `audit_event` and its `outbox_event`, in the same transaction as
the change, with a user, agent or system actor, the subject with its title at
the time, a summary, before and after values, and the step-up assertion when
one was used. The table is append-only: the model raises on update or delete,
and a trigger makes that true on Postgres, with a `SET LOCAL cw.maintenance`
escape hatch for a conscious fix that only the schema owner, in a migration, can
use: the trigger ignores the setting when the application role is running.

Every model output is logged in `ai_generation` with purpose, model, version,
input reference, output, citations, review state and feedback. A problem report
stays inside the bank that filed it: no bleqq editor, other bank, agent or model
reads it, and a library error reaches the library instead through the watch
agents' re-check and a proposal (D-50, ADR 0043).

Since PRD 0.4 (Alex, 2026-09-20, D-62 and ADR 0054) a library proposal may be
confirmed by an independent agent rather than a person, so the audit trail
carries decisions nobody signed with a passkey. Nothing about `record()`
changes: the actor is the agent, the row names its definition, its version and
the key it used, the assertion id is null because a key cannot step up, and the
same decision is logged in `ai_generation` where a model produced it. The
console's queue is the surface the platform reads that trail on, and where a
person takes a proposal over.

The platform console lives here too: library vocabularies, sources, languages
and jurisdictions, agent definitions, the proposal queue, evaluation sets,
tenants and plans, support access and system health. It has no problem-report
surface. Each bank's usage figures, failed jobs and stream lag are read through
one SELECT-only window on two tables that hold numbers, kinds and times only,
and every such read writes a platform audit row naming the screen and the
filters, never the figures (D-59, ADR 0052).

Nothing is overwritten, with the two deletions CLAUDE.md §5 names. Ten years
after a record was last used, the daily purge deletes it whole — a closed case
with its children, a removed piece of evidence, or the tenant's audit, published
outbox and login rows — through one database function owned by the schema owner
whose cutoff can never be younger than a year (D-53, ADR 0046). The second is
tenant exit (D-56).

Deliberately simplified for R1: retention with a purge is R3.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| AUD-01 | Append-only audit log written with every change: actor (user, agent, system), action, subject with its title at the time, summary, before and after | M | R1 | built |
| AUD-02 | AI output log with model, version, purpose, citations, review state and feedback | M | R1 | pending |
| AUD-03 | A problem report stays inside the bank that filed it and nobody outside reads it; the loop to the library is closed by the watch agents' re-check, which proposes the correction (D-50) | S | R1 | pending |
| AUD-04 | Retention: a record is deleted ten years after its last use. The purge never updates an append-only row, deletes one only past that age, and runs through one database-guarded path (D-53) | S | R3 | pending |
| ADM-02 | Platform console: library vocabularies, sources, languages and jurisdictions, agent definitions, proposal queue, evaluation sets, tenants and plans, support access, system health (coverage, runs, outbox lag, failed jobs with retry, and each bank's usage figures through one audited read of numbers only). No problem-report surface (D-50, D-59) | M | R1 to R3 | in_progress |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-AUD1** Every mutating request leaves an audit row in the same
  transaction, and the table rejects update and delete.
- **Mixed tables** (`audit_event`, `ai_generation`, `problem_report`,
  `outbox_event`, `api_key`) show library rows to everyone and tenant rows to
  their tenant, and accept a write only in the zone the session is in: a bank
  session writes its own rows, a session with no tenant the platform's.
- The tenant audit log (`GET /audit-events`, `audit.read`) shows the tenant's
  rows and, of the rows without a tenant, only a change to a library record
  (authority, instrument, provision, obligation, vocabulary, taxonomy term)
  made by an agent, the system or platform staff. Proposal rows and platform
  sign-ins and code requests without a tenant never reach a tenant.
- The audit-on-write guard fails a mutating route whose scenario wrote no
  audit row.
- System health shows source coverage, runs, outbox lag and failed jobs with
  retry; `/health/` answers 503 with the failing component named.
- Retention is a tenant setting; the purge removes what it may and reports
  what append-only tables kept.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/governance.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### AUD-S1 — Every write leaves an audit row and an outbox row in the same transaction `@integration` (AUD-01, AC-AUD1)
```gherkin
Given any mutating request in the scenario suite
When it commits
Then an audit_event exists with actor kind, action, subject kind and id, the subject's title at the time, a summary, before and after values
And an outbox_event exists in the same transaction
When record() raises after the change
Then the change is rolled back too
And a mutating route with no scenario, or one that wrote no audit row, fails the guard
```

### AUD-S2 — The audit table rejects update and delete `@integration` (AUD-01, AC-AUD1)
```gherkin
Given an audit event row
When the ORM updates or deletes it
Then AppendOnlyModel raises
When raw SQL updates or deletes it
Then the trigger raises
When SET LOCAL cw.maintenance is set inside a migration's transaction
Then the statement runs and the maintenance intent is visible in the transaction
When the application role sets it instead, in either letter case
Then update and delete are still refused
```

### AUD-S3 — The audit log screen shows who did what, with before and after `@e2e` (AUD-01)
```gherkin
Given a tenant member with audit.read and a record changed with step-up
When they open the audit log and filter by that record (a case, once chunk 9 exists)
Then each row shows actor, action, subject title, time and a diff of before and after
And an event completed with step-up shows that a passkey was used
```

### AUD-S4 — Every model output is logged with its review state `@integration` `@e2e` (AUD-02)
```gherkin
Given a So what draft, an Ask answer and an agent classification
Then each has an ai_generation row with purpose, model, version, input reference, output, citations and review state pending
When a person confirms the So what
Then its row's review state is confirmed with the person and time
When a person marks an answer as wrong
Then feedback is stored on the row
And a holder of ai_log.read can list the rows for their tenant
```

### AUD-S5 — A problem report stays inside the bank that filed it `@integration` `@e2e` (AUD-03)
```gherkin
Given a reader in tenant A reported "This looks wrong" on an obligation
Then the report is readable by tenant A only, and the dialog says so: bleqq is not told, and the watch corrects the library
When a library editor, another tenant, an API key or an agent asks for it
Then each answers 403 or 404, and the console has no problem-report surface
And the report's text reaches no log, no Sentry event, no outbox payload a webhook or SIEM stream carries, and no model
When the watch agents' re-check proposes the correction and an editor approves it
Then tenant A sees the corrected record under "Library updates"
```

### AUD-S6 — The purge deletes ten years after a record's last use and never updates a ledger row `@integration` (AUD-04)
```gherkin
Given a case closed eleven years ago, evidence removed eleven years ago, audit rows of both ages, and footprint history
When the daily purge runs
Then the case with its children, the evidence file and row, and the tenant's audit, published outbox and login rows past ten years are deleted whole
And rows inside the period stay, footprint history is kept for the tenant's life, and no library table is touched
And no ledger row is ever updated, only deleted
And the run writes one retention run row and one audit row with counts only, and running it twice changes nothing more
```

### AUD-S7 — Mixed tables show library rows to everyone and tenant rows to their tenant `@integration` (AUD-01)
```gherkin
Given audit events for a library change an approved proposal applied and for tenant A's own work
When tenant B reads the audit log
Then it sees the library event and not tenant A's
When the row-level security guard enumerates the mixed tables
Then each reads "shared or mine", enabled and forced
And each accepts a write only in the zone the session is in
```

### ADM-S4 — The platform console offers each surface to the platform role that owns it `@integration` `@e2e` (ADM-02)
```gherkin
Given a library editor and a platform admin
When each of them calls every console destination and endpoint that exists
Then the proposal queue, its detail, approve and reject answer to the library editor and 403 the platform admin with requiredPermission "proposals.review"
And the tenants list, creating a tenant and re-issuing an administrator's enrolment answer to the platform admin and 403 the library editor with the permission each wanted
And creating a proposal, whose caller a logic gate decides, 403s the platform admin with requiredPermission named
And each console destination the other role holds is absent from that role's navigation
```

The surfaces this scenario does not yet reach, each with what builds it: sources
(chunk 5), evaluation sets (chunk 7), agent definitions (chunk 11), system health
(chunk 14), support access (TEN-S6), plans (NFR-S17 to S19), and language and
jurisdiction edits (their card; jurisdictions are read-only on the vocabularies
screen).

### ADM-S5 — System health names what is wrong `@integration` `@e2e` (ADM-02)
```gherkin
Given the worker is stopped
When a platform admin opens system health
Then /health/ answers 503 with "worker" named and the screen shows it
And source coverage, recent runs, outbox lag and failed jobs are listed with a retry action per failed job
When the worker is back
Then /health/ answers 200 with every component ok and the worker ping bounded
```

### ADM-S6 — A tenant is created from the console with its first administrator invited `@integration` `@e2e` (ADM-02, ID-01, TEN-01)
```gherkin
Given a platform admin with tenants.manage
When they create a tenant with a name, a short name, a timezone, a language order and the first administrator's address
Then the tenant exists with its system roles, its own vocabularies and its content languages
And the console's tenant list holds it
And one pending administrator invitation is sent to that address
And the creation is audited in the new tenant's own log
When they create another tenant with the same short name
Then the answer is 409
```

### AUD-S8 — The ledger purge refuses a cutoff inside the floor and a paused tenant `@integration` (AUD-04)
```gherkin
Given the purge function owned by the schema owner
When it is called with a cutoff younger than one year
Then it refuses and deletes nothing
When the app role calls UPDATE or DELETE on a ledger table itself, or tries to open the maintenance hatch
Then the database refuses it
When tenant B's purge runs
Then tenant A's rows are untouched, because the function filters on the active tenant
When the tenant is paused
Then the run deletes nothing and says so
```

### ADM-S7 — The console reads each bank's figures through one audited window `@integration` (ADM-02)
```gherkin
Given usage rows and a failed job for two banks
When a platform admin with system.health opens the console
Then the figures and the failed jobs of each bank are listed, from tables that hold numbers, kinds and times only
And one platform audit row records the screen and the filters, never the figures
When a platform principal without tenants.manage or system.health reads them, or a tenant is active
Then the window refuses to open
When the admin retries a failed job
Then it is re-queued as a tenant task from its kind, tenant and subject, and the retry writes an audit row in that bank with a system actor
```

Plans and their limits are NFR-S17 to S19; requesting support access to a tenant is
TEN-S6. The address must be the administrator's own: platform staff are separate
accounts, as `bootstrap_platform` requires from the other side.

### ADM-S8 — A deploy's own seeds carry an empty database to a working bank `@e2e` (ADM-02, ID-01, ID-02, TEN-01, FP-02)
```gherkin
Given a database a deploy has migrated and seeded reference data into, and nothing else
When the owner runs bootstrap_platform and the first platform admin opens the emailed link, enters the code and enrols a passkey
Then they reach the console, whose tenant list is empty rather than broken
When they create the first bank with its administrator's address
And that administrator enrols from their own emailed link, sets the bank's profile and invites a second member
And one of the two requests the first footprint and the other approves it with a passkey step-up
Then the footprint holds the term, and no /api/ call has answered 400 or above undeclared and no page has thrown
And the inventory and the timeline each render their own empty state on a library that has never held a row
```

The journey is `frontend/tests/e2e/coldstart.journey.spec.ts`, tagged `@coldstart`; it
runs on its own stack, booted with `seed_reference` alone (`E2E_COLD_START=1` in
`tests/e2e/support/start-backend.sh`). The watch feed's empty state is the one step it
cannot reach: `/watch` is in the navigation registry and has no route until chunk 5.

### AUD-S9 — An agent's approval is in the audit trail with the agent named `@integration` (AUD-01, AUD-02)
```gherkin
Given a proposal an independent agent approved with its review scope
Then the audit event names the agent, its definition version and the key it used, not the key's id alone
And the event carries no step-up assertion, because a key cannot step up
And a rejection or a correction by that agent is recorded the same way, with its reason
And the model call behind the decision is in the AI output log with its citations and review state
And the audit rows stay append-only: the decision cannot be edited afterwards
```
