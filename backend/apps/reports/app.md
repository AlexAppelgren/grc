# reports — Reporting, exports, import and exit

> **App spec.** Source: `PRD.md` Module REP (REP-01–REP-04), playbook 4.6 (exports
> stream through permission checks), 10 (async jobs), 18 (exit as a feature), D-11.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

The slow loop: dashboards for the compliance officer, a committee pack, and
exports of the inventory, changes, cases and the audit log. A spreadsheet
register can be imported with a dry run and a near-match mapping asked once
per value. Exit is a feature: a full tenant export in open formats and a
verified deletion, because a bank's vendor review asks for it.

Exports, imports and the tenant export are asynchronous jobs with a status
endpoint. Every export is behind step-up and its download streams through a
permission-checked, audited endpoint. Every report respects the footprint.

Deliberately simplified: the whole app is R3 (chunk 12).

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| REP-01 | Dashboard: open changes by urgency, overdue actions, gaps, unconfirmed AI drafts, time to triage, regime by account heatmap, load per owner | S | R3 | pending |
| REP-02 | Committee pack and exports of inventory (including a dated Statement of Applicability per standard and entity), changes, cases and the audit log | S | R3 | pending |
| REP-03 | Spreadsheet register import: dry run, near-match mapping asked once per value, then commit | S | R3 | pending |
| REP-04 | Full tenant export in open formats and verified deletion | M | R3 | pending |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- Dashboard figures come from one endpoint per tile, computed from keys and
  categories, under the API budget, and filtered by the footprint.
- An export needs `exports.create` and step-up, runs in the worker, reports
  its status, and downloads through the API with an audit row.
- Import: a dry run reports creates, updates, conflicts and unknown values;
  each unknown value is mapped once to an existing key or a new suggestion;
  commit is one audited transaction.
- Tenant exit: register, cases, evidence, configuration and audit log in open
  formats; deletion runs after the export is confirmed, and a verification
  report lists what was removed and what append-only tables retained.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/reports.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### REP-S1 — The dashboard shows the officer's figures from keys and categories `@integration` `@e2e` (REP-01)
```gherkin
Given the seeded tenant
When a user with reports.read opens Reports
Then "Open changes by urgency", "Overdue actions", gaps, unconfirmed AI drafts, time to triage, "Open changes by regime and account" and load per owner render
And each tile came from its own endpoint under 250 ms with counts and keys, never phrases
And records outside the footprint are excluded
```

### REP-S2 — The committee pack and the exports are produced by jobs `@integration` `@e2e` (REP-02)
```gherkin
Given an approver with exports.create
When they choose "Show committee pack" and then export the inventory, changes, cases and the audit log
Then each export is a job with a status the screen polls
And each download streams through the API with an audit event naming the file and the person
```

### REP-S3 — An export needs step-up and never runs inside the request `@integration` (REP-02)
```gherkin
Given a user with exports.create but no fresh assertion
When they request an export
Then the request answers 403 with code "step_up_required"
When they retry with a fresh assertion
Then the response is 202 with a job id and the file is produced by the worker
```

### REP-S4 — A spreadsheet register imports with a dry run and a mapping asked once per value `@integration` `@e2e` (REP-03)
```gherkin
Given a spreadsheet with 40 obligations whose status column holds "Complies", "Partly" and "Gap"
When an admin uploads it
Then the dry run lists 40 rows, the near matches and the three unknown values
When the admin maps "Complies" to the key "compliant" once
Then every row with "Complies" uses it and the question is not asked again
When they commit
Then the register rows exist and one audit event records the import with the mapping
```

### REP-S5 — A tenant can leave with everything and have deletion verified `@integration` `@e2e` (REP-04)
```gherkin
Given a tenant admin with a fresh step-up
When they request the full tenant export
Then a job produces the register, cases, evidence, configuration and audit log in open formats
When they confirm deletion after the export
Then tenant rows are deleted, append-only tables keep their rows under retention, and a verification report lists both
And a later sign-in for the tenant answers 404
```

### REP-S6 — The Statement of Applicability exports as a dated inventory export `@integration` (REP-02, REG-08)
```gherkin
Given a user with exports.create and a fresh step-up
When they export the inventory filtered by a standard's edition and one legal entity
Then the job produces a file carrying its export date and, per unit, the reference, the tenant's title, applicability, reason, status, approver and decision date
And the export writes one audit event
And the request returns before the file is built
```
