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
and a trigger makes that true on Postgres with a `SET LOCAL cw.maintenance`
escape hatch for a conscious fix.

Every model output is logged in `ai_generation` with purpose, model, version,
input reference, output, citations, review state and feedback. Problem reports
from tenants are resolved by a proposal, which closes the loop to the agents.

The platform console lives here too: library vocabularies, sources, languages
and jurisdictions, agent definitions, the proposal queue, problem reports,
evaluation sets, tenants and plans, support access and system health.

Deliberately simplified for R1: retention with a purge is R3.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| AUD-01 | Append-only audit log written with every change: actor (user, agent, system), action, subject with its title at the time, summary, before and after | M | R1 | in_progress |
| AUD-02 | AI output log with model, version, purpose, citations, review state and feedback | M | R1 | pending |
| AUD-03 | Problem reports resolved by a proposal, closing the loop to the agents | S | R1 | pending |
| AUD-04 | Retention per tenant with a purge that respects append-only tables | S | R3 | pending |
| ADM-02 | Platform console: library vocabularies, sources, languages and jurisdictions, agent definitions, proposal queue, problem reports, evaluation sets, tenants and plans, support access, system health | M | R1 to R3 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-AUD1** Every mutating request leaves an audit row in the same
  transaction, and the table rejects update and delete.
- **Mixed tables** (`audit_event`, `ai_generation`, `problem_report`,
  `outbox_event`, `api_key`) show library rows to everyone and tenant rows to
  their tenant.
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
When SET LOCAL cw.maintenance is set inside a transaction
Then the statement runs and the maintenance intent is visible in the transaction
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

### AUD-S5 — A problem report is resolved by a proposal `@integration` `@e2e` (AUD-03)
```gherkin
Given a reader reported "This looks wrong" on an obligation
When a library editor opens the report in the console
Then they can open a proposal from it with the report linked
When the proposal is approved
Then the report is resolved, the reporter is notified, and the agents' next run sees the correction
```

### AUD-S6 — Retention per tenant purges what it may and keeps append-only rows `@integration` (AUD-04)
```gherkin
Given a tenant retention of 24 months for notifications and 10 years for audit events
When the purge job runs
Then notifications older than 24 months are deleted
And audit events are kept and the job report says which tables were exempt
And the purge refuses to run without the environment guard
```

### AUD-S7 — Mixed tables show library rows to everyone and tenant rows to their tenant `@integration` (AUD-01)
```gherkin
Given audit events for a library change an approved proposal applied and for tenant A's own work
When tenant B reads the audit log
Then it sees the library event and not tenant A's
When the row-level security guard enumerates the mixed tables
Then each has a "shared or mine" policy, enabled and forced
```

### ADM-S4 — The platform console offers each surface to the platform role that owns it `@integration` `@e2e` (ADM-02)
```gherkin
Given a library editor and a platform admin
When the editor opens the console
Then the proposal queue, library vocabularies, sources, languages and jurisdictions, problem reports and evaluation sets are reachable
And tenants and plans, agent definitions, support access and system health are absent
When the platform admin opens it
Then the reverse holds, and each direct endpoint answers 403 to the wrong role with requiredPermission named
```

### ADM-S5 — System health names what is wrong `@integration` `@e2e` (ADM-02)
```gherkin
Given the worker is stopped
When a platform admin opens system health
Then /health/ answers 503 with "worker" named and the screen shows it
And source coverage, recent runs, outbox lag and failed jobs are listed with a retry action per failed job
When the worker is back
Then /health/ answers 200 with every component ok and the worker ping bounded
```

### ADM-S6 — Tenants, plans and support access are managed from the console `@integration` `@e2e` (ADM-02)
```gherkin
Given a platform admin with tenants.manage
When they create a tenant, assign a plan and invite its first admin
Then the tenant exists with the plan's limits and the invitation is sent
When they request support access to it
Then the request is visible to the tenant's admins and grants nothing until a tenant admin approves it
```
