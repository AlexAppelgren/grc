# tenants — Tenant and organisation

> **App spec.** Source: `PRD.md` Module TEN (TEN-01–TEN-06), ADM-01 and ADM-03,
> journey J-8, playbook 4.2 (support access), 14, 15.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

A tenant is one bank. It has a profile, a timezone, default languages, legal
entities with licences, products described the way obligations are scoped,
and teams that own work so ownership survives a person leaving. The tenant
admin surfaces live here: organisation, members and invitations, roles,
security policy, data and the audit log view. Admin duties are separate
permissions so a bank can keep user administration apart from business
configuration.

Platform staff have no bypass. They see a tenant's data only through a
support access grant the tenant can see, time-boxed and logged.

Deliberately simplified for R1: only the profile, members, invitations,
re-enrolment and sessions land in chunk 1. Entities, products, teams,
delegation, bulk reassignment and support access follow in chunk 8.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| TEN-01 | Tenant profile, timezone, default languages, onboarding checklist | M | R1 | built |
| TEN-02 | Legal entities with licences, and products described the way obligations are scoped | M | R2 | pending |
| TEN-03 | Teams as owners, so ownership survives a person leaving | S | R2 | pending |
| TEN-04 | Out-of-office with a delegate for approvals and reminders | S | R2 | pending |
| TEN-05 | Removing a member who owns open work offers bulk reassignment | M | R2 | pending |
| TEN-06 | Support access grants: visible to the tenant, time-boxed, logged | M | R2 | pending |
| ADM-01 | Tenant admin: organisation, members and invitations, passkey re-enrolment, sessions, roles, footprint, vocabularies, workflow policy, agents, integrations, security policy, data, audit log | M | R1 to R3 | in_progress |
| ADM-03 | Admin duties are separate permissions | M | R1 | built |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- The tenant profile holds timezone (default `Europe/Stockholm`, storage UTC)
  and a content language order; deadlines and digests convert through it.
- Entities and products carry the same taxonomy terms obligations are scoped
  with, so an obligation can be assessed per entity.
- A team can own anything a person can own; removing a person from a team
  leaves the team's ownership intact.
- A delegate receives approvals and reminders while the out-of-office window is
  open, and the audit event records both people.
- Removing a member with open ownership shows the count and requires a target
  owner per kind before the removal commits, in one audited transaction.
- A support access grant has a purpose, a start, an end, a granting admin, and
  every read under it lands in the support access log the tenant can read.
- The admin permissions `members.manage`, `roles.manage`, `vocab.manage`,
  `workflow.manage`, `security.manage`, `integrations.manage`, `agents.manage`
  gate their screens independently.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/tenants.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### TEN-S1 — A tenant profile holds timezone, languages and the onboarding checklist `@integration` `@e2e` (TEN-01)
```gherkin
Given a new tenant
When an admin sets the name, timezone "Europe/Helsinki" and the language order fi, sv, en
Then the profile stores them and the API returns them as keys
And the onboarding checklist shows footprint, members and vocabularies as not done
And a deadline of 2026-10-01 renders as a Helsinki date on every screen
```

### TEN-S2 — Legal entities and products are scoped like obligations `@integration` `@e2e` (TEN-02)
```gherkin
Given an admin with vocab.manage
When they add the legal entity "Bank AB" with the licence "credit institution" and the product "Custody"
Then both carry taxonomy terms from the same dimensions obligations use
And the register can hold a compliance status for "Bank AB" separately from another entity
```

### TEN-S3 — A team can own work and the ownership survives a member leaving `@integration` (TEN-03)
```gherkin
Given the team "Compliance operations" owns an obligation and a case
When one of its members is removed from the tenant
Then the obligation and the case still list the team as owner
And nothing needs reassignment
```

### TEN-S4 — An out-of-office delegate receives approvals and reminders `@integration` `@e2e` (TEN-04)
```gherkin
Given an approver who set out-of-office until next Friday with a delegate
When a sign-off request names that approver
Then the delegate is notified and may sign off
And the audit event records the delegate as actor and the absent approver as delegated
When the window closes
Then the approver receives requests again
```

### TEN-S5 — Removing a member with open work offers bulk reassignment `@integration` `@e2e` (TEN-05)
```gherkin
Given a member who owns three obligations and two open cases
When an admin removes them
Then the screen shows what they own by kind and asks for a new owner per kind
And nothing changes until the admin confirms
When the admin confirms
Then every item is reassigned and the member removed in one transaction with one audit event per item
```

### TEN-S6 — A support access grant is visible, time-boxed and logged `@integration` `@e2e` (TEN-06)
```gherkin
Given a platform admin without any grant
When they read a tenant's cases
Then the request answers 404
When a tenant admin grants support access for two hours with a purpose
Then the grant appears on the tenant's security screen
And every read under it lands in the support access log with the platform user and the purpose
When the two hours pass
Then the platform admin's reads answer 404 again
```

### TEN-S7 — J-8: tenant B cannot see tenant A `@e2e` (TEN-06, J-8)
```gherkin
Given seeded tenants A and B and a case with evidence and comments in A
When B's compliance officer signs in and opens A's case URL, evidence URL and vocabulary screen
Then each answers 404 and the UI shows "Not found", never the data and never a 403
And B's lists show only B's records
```

### ADM-S1 — Tenant admin surfaces are gated by their own permissions `@integration` `@e2e` (ADM-01, ADM-03)
```gherkin
Given a member holding members.manage and nothing else
When they open the admin area
Then "Members" and "Invitations" are reachable
And "Vocabularies", "Security policy", "Agents" and "Integrations" are absent from the navigation
When they call the vocabulary write endpoint directly
Then it answers 403 with requiredPermission "vocab.manage"
```

### ADM-S2 — The members screen invites, assigns roles, re-issues enrolment and revokes sessions `@e2e` (ADM-01)
```gherkin
Given an admin with members.manage
When they invite a person with two roles, change the roles later, re-issue enrolment and revoke every session
Then each action succeeds through the real UI with the step-up prompt where playbook 4.2 requires it
And the member list shows the resulting state
```

### ADM-S3 — User administration and business configuration can sit with different people `@integration` `@e2e` (ADM-03)
```gherkin
Given one member with members.manage and roles.manage only
And another with vocab.manage and workflow.manage only
When each opens the admin area
Then each sees only their own screens
And neither can call the other's endpoints
```
