# tenants — Tenant and organisation

> **App spec.** Source: `PRD.md` Module TEN (TEN-01–TEN-06, AC-TEN1), ADM-01 and ADM-03,
> journeys J-8 and J-9, playbook 4.2 (support access), 14, 15.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

A tenant is one bank. It has a profile, a timezone, default languages, legal
entities with the licences and certificates they hold, products described the
way obligations are scoped, departments (business areas, units and functions)
with a head, and the teams inside them that own work and take part in it, so
ownership survives a person leaving. The tenant
admin surfaces live here: organisation, members and invitations, roles,
security policy, data and the audit log view. Admin duties are separate
permissions so a bank can keep user administration apart from business
configuration.

Platform staff have no bypass. A platform admin asks for read-only access to
one bank, with a purpose and a time limit; a tenant admin approves it with a
passkey, or declines, and may revoke it at any time. Until approval every read
answers 404, the support principal can read and never write, and every request
under the grant lands in the bank's own audit log (D-49, ADR 0042).

A bank that leaves is deleted rather than archived: two different people holding
`security.manage` request and approve the exit, the tenant then goes read-only
while the final export is taken, and the platform operator deletes every row
(D-56, ADR 0049).

Deliberately simplified for R1: only the profile, members, invitations,
re-enrolment and sessions land in chunk 1. Entities, products, teams,
delegation, bulk reassignment and support access follow in chunk 8. A
department is the org unit of kind business area, business unit or function
with a head; team leads are not built, because notices go to a team's active
members (D-21, D-34).

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| TEN-01 | Tenant profile, timezone, default languages, onboarding checklist | M | R1 | built |
| TEN-02 | Legal entities with licences and certificates (issuer, reference, scope, validity, next audit, owner), departments with a head and the teams in them, and products described the way obligations are scoped | M | R2 | pending |
| TEN-03 | Teams as owners and participants, so ownership survives a person leaving | M | R2 | pending |
| TEN-04 | Out-of-office with a delegate for approvals and reminders | S | R2 | pending |
| TEN-05 | Removing a member who owns open work offers bulk reassignment | M | R2 | pending |
| TEN-06 | Support access grants: requested by the platform, approved by a tenant admin with a passkey, read-only, visible to the tenant, time-boxed, revocable and logged in the bank (D-49) | M | R2 | pending |
| ADM-01 | Tenant admin: organisation with departments and teams, members and invitations with team membership, passkey re-enrolment, sessions, roles, footprint with markets, vocabularies, workflow policy, agents, integrations, security policy, data, audit log | M | R1 to R3 | in_progress |
| ADM-03 | Admin duties are separate permissions | M | R1 | built |

**ADM-01 is built in part, which is why it stays `in_progress`.** The R1 slice on `main`:
the organisation profile with its onboarding checklist (TEN-S1); members and invitations,
roles, and each admin screen gated by its own permission (ADM-S1 to ADM-S3); an admin's
passkey re-enrolment of a member and the sessions a person sees and revokes (ID-S12,
ID-S11); the bank's own API keys; the security log; the audit log; the regulatory scope with
its change requests and its markets panel (FP-S10); and the vocabularies. What remains, each
with the Build_Plan.md chunk that delivers it: departments with a head, teams, and team membership on the member row (TEN-02, TEN-03, chunk 8); the
workflow policy's reminders and escalation (COL-02, chunk 10); the agents a bank adds for
itself (AGT-04, chunk 11); data, meaning exports, import, retention and tenant exit (REP-02
to REP-04, AUD-04, chunk 12); and integrations beyond the API keys, with the security
policy's SSO and IP allow-list (INT-01 to INT-03, ID-12, ID-13, chunk 13).

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- **AC-TEN1** A certificate's expiry and next audit appear on the roadmap as
  "Our deadline" with its owner, disappear once it is withdrawn, and never
  appear in the calendar feed. The certificate sits on the entity's licence
  row, carries no term and decides no span.
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
And a licence row may also hold a certificate with its validity, next audit and owner, carrying no term
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

### TEN-S6 — Support access is requested by the platform, approved by the bank and time-boxed `@integration` `@e2e` (TEN-06)
```gherkin
Given a platform admin without any grant
When they read a tenant's cases
Then the request answers 404
When they request support access for two hours with a purpose
Then nothing is granted, the reads still answer 404, and the holders of security.manage are notified
When a tenant admin approves the request with a fresh step-up assertion
Then the grant appears on the tenant's Support access panel with the purpose, the person and the end of the window
And every read under it lands in the bank's audit log as "support_access.read" with the route and the platform user
When the tenant admin revokes the grant
Then the next request answers 401 "support_access_ended" and the ones after that answer 404
When the two hours pass without a revocation
Then the grant ends the same way and the reads answer 404 again
```

### TEN-S7 — J-8: tenant B cannot see tenant A `@e2e` (TEN-06, COL-04, J-8)
```gherkin
Given seeded tenants A and B, a case with evidence, comments and a participant in A, and A watching Norway
When B's compliance officer signs in and opens A's case URL, evidence URL and vocabulary screen
Then each answers 404 and the UI shows "Not found", never the data and never a 403
When B opens the participants of a shared obligation on which A has participants
Then B sees only its own participants
And B's regulatory scope screen shows no market that A watches
And B's lists show only B's records
```

> **Note — what R1 walks (tax-market-journeys).** The `@e2e` journey proves B cannot reach
> A's member by URL and lists only its own members; that B's regulatory scope shows no
> market A watches as watched, none of A's terms as held and neither A's pending request nor
> its requester; and that B's roles and tenant tags hold none of A's own (the seed gives A a
> custom role and a tag for this, `EXPECTED_TENANT_A_ONLY`). The case, evidence, comment and
> participant steps join the journey with chunks 9 and 10, when those screens exist.

### ADM-S1 — Tenant admin surfaces are gated by their own permissions `@integration` `@e2e` (ADM-01, ADM-03)
```gherkin
Given a member holding members.manage and nothing else
When they open the admin area
Then "Members" and "Invitations" are reachable
And "Vocabularies", "Security policy", "Agents" and "Integrations" are absent from the navigation
When they call the vocabulary write endpoint directly
Then it answers 403 with requiredPermission "vocab.manage"
When a member holding watch.read but not agents.manage opens "Agents"
Then they read what bleqq watches with no control on it and a line saying changing agents needs agents.manage, never a page-level 403
And an admin holding agents.manage sees the same read-only watch above the bank's own spend and agents
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

### TEN-S8 — A department has a head and teams, and team membership is set on the member row `@integration` `@e2e` (TEN-02, TEN-03)
```gherkin
Given an admin with vocab.manage
When they add the department "Retail Banking" with Karin as head and the team "Retail compliance" in it
Then GET /me for Karin lists "Retail Banking" among the departments she heads
Given an admin with members.manage
When they put Anna and Johan in "Retail compliance"
Then one audit event is written per call, holding the team keys before and after
When they put a user who is a member only of another tenant in the team
Then the answer is 422 with code "unknown_member"
And the database refuses a team membership, a team's department or a department head that belongs to another tenant
Given a person without members.manage
When they change a member's teams
Then the answer is 403
```

### TEN-S9 — Removing a member ends their participations and team memberships `@integration` (TEN-05, COL-04)
```gherkin
Given Erik owns one obligation, takes part in three items and is in the teams "Legal" and "Cards"
When an admin opens his removal
Then the screen lists what he owns by kind, "Takes part in 3 items" and his two teams
And nothing changes until the admin confirms
When the admin confirms with a new owner for the obligation
Then the obligation is reassigned, his three participations and two team memberships end, and he is removed, in one transaction
And one audit event is written per item
And the participations of his teams are unchanged
```

### TEN-S10 — A legal entity records a certificate it holds `@integration` `@e2e` (TEN-02, AC-TEN1)
```gherkin
Given an admin with vocab.manage and the legal entity "Example Bank AB"
When they record the licence "ISO/IEC 27001:2022 certificate, issued by Example Certification AB" with a certificate number, a scope statement, an issue date, a validity end date, a next audit date and an owner
Then the entity screen lists it under "Licences and certificates" with its validity and next audit
And the write is audited with before and after values
And no obligation, scope row or applicability changes
When they set a withdrawal date
Then the row reads as withdrawn and stays in the history
```

### TEN-S11 — A support session reads and never writes, and never approves itself `@integration` (TEN-06)
```gherkin
Given an approved support grant and a support session opened under it
When the session calls any write route, or downloads evidence or an export
Then the response is 403 with code "support_read_only" and nothing is written
When the session calls search or Ask
Then the response is 403, because both would spend the bank's AI budget
When the platform person who requested the grant tries to approve it
Then the database refuses the row, because the approver is never the requester
```

### TEN-S12 — A closing tenant refuses writes and still lets people sign in and export `@integration` (REP-04)
```gherkin
Given a tenant whose exit request two different admins have requested and approved
When any member calls a mutating route
Then the response is 409 with code "tenant_closing"
When a member signs in, refreshes, steps up, revokes a session or downloads the final export
Then each still succeeds
When a holder of security.manage cancels the exit with a step-up before the delay passes
Then the tenant is active again and writes succeed
```
