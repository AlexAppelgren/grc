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
| TEN-02 | Legal entities with licences and certificates (issuer, reference, scope, validity, next audit, owner), departments with a head and the teams in them, and products described the way obligations are scoped. A team is put in a department, moved or taken out on the team list's own create and edit (`extra.orgUnitId`) and in the admin's team form (`ten02-team-department`, TEN-S8) | M | R2 | built |
| TEN-03 | Teams as owners and participants, so ownership survives a person leaving | M | R2 | built |
| TEN-04 | Out-of-office with a delegate for approvals and reminders | S | R2 | built |
| TEN-05 | Removing a member who owns open work offers bulk reassignment | M | R2 | built |
| TEN-06 | Support access grants: requested by the platform, approved by a tenant admin with a passkey, read-only, visible to the tenant, time-boxed, revocable and logged in the bank (D-49) | M | R2 | built |
| TEN-07 | Fill in the legal entities from public registers: an organisation number or LEI, the group from GLEIF, each Swedish company's business, licences and branches from Finansinspektionen; a person picks what to add; licences are shown from the register facts, never typed (`docs/plans/briefs/PUBLIC_REGISTERS.md`) | S | R3 | in_progress |
| TEN-08 | The register facts are re-read nightly, each change audited; a change edits neither the organisation nor the scope, it shows as a suggestion (FP-05) | S | R3 | in_progress |
| ADM-01 | Tenant admin: organisation with departments and teams, members and invitations with team membership, passkey re-enrolment, sessions, roles, footprint with markets, vocabularies, workflow policy, agents, integrations, security policy, data, audit log | M | R1 to R3 | in_progress |
| ADM-03 | Admin duties are separate permissions | M | R1 | built |

**TEN-05's backend is built; the dialog is not, which is why it is `in_progress`.** `GET
/tenant/members/{userId}/open-work`, the refusal of a plain removal (422
`reassignment_required`) and `POST /tenant/members/{userId}/remove` move register entries,
legal entities' rows, gaps and internal items (`c8-ten-reassignment`), and open duty
occurrences, open cases and live actions (`c9-owner-team-and-reassign`), end the member's
participations, case ones included, and team memberships, and deactivate them in one step-up
transaction with one audit event per item (TEN-S5, TEN-S9, TEN-S3). A case or an action passes
to a person, never a team, and a case only to a member who works cases; the team a triage names
beside a case's owner stays with the case. The removal dialog and TEN-S5's journey are
`c8-ui-departments-teams-removal`'s.

**ADM-01 is built in part, which is why it stays `in_progress`.** The R1 slice on `main`:
the organisation profile with its onboarding checklist (TEN-S1); members and invitations,
roles, and each admin screen gated by its own permission (ADM-S1 to ADM-S3); an admin's
passkey re-enrolment of a member and the sessions a person sees and revokes (ID-S12,
ID-S11); the bank's own API keys; the security log; the audit log; the regulatory scope with
its change requests and its markets panel (FP-S10); and the vocabularies. R2 added the
organisation with legal entities, licences and certificates, departments with their heads,
teams and team membership on the member row (TEN-02, TEN-03); support access (TEN-06); the
workflow policy's reminders and escalation (COL-02); the agents a bank adds for itself and
its agent access (AGT-04, ACC-01 to ACC-09); and the security policy's session limits
(ID-08). What remains at the R2 close (2026-09-27, `r2-close-and-readiness`), each with the
Build_Plan.md chunk that delivers it (putting a team in a department, found at the close, was
built by `ten02-team-department`): data, meaning exports, import, retention and tenant exit
(REP-02 to REP-04, AUD-04, chunk 12); integrations beyond the API keys, with the security
policy's SSO and IP allow-list (INT-01 to INT-03, ID-12, ID-13, chunk 13); and the
device-bound passkey policy (ID-07), out of R2 by D-100.

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- **AC-TEN1** A certificate's expiry and next audit appear on the roadmap as
  "Our deadline" with its owner, disappear once it is withdrawn, and never
  appear in the calendar feed. The certificate sits on the entity's licence
  row, carries no term and decides no span.
- **AC-TEN2** Typing 556000-0001 lists Example Bank AB's group from GLEIF with each
  Swedish company's business, licences and branches from Finansinspektionen, the licensed
  companies ticked and the holding company not. Adding them creates the legal entities with
  org number, LEI, country and type, links a company the bank already had, and writes no
  licence row and no scope term. A number no company carries answers "not found".
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

> **c8-ten-organisation (TEN-02, ADM-01).** The organisation and product routes answer for
> real: units with their tree, kind, legal-entity term, registration number, LEI, country and
> head; licences and certificates per legal entity; products with status, launch date, owner,
> unit and scope terms. Writes need `vocab.manage`, check `If-Match` against the row's
> `version`, answer 422 `unknown_key` for a term outside the dimensions obligations are scoped
> with (read from the dimension rows by kind, never listed) and 422 `unknown_member` for a
> head or owner who is not an active member, and are audited with the fields they changed
> before and after; a scope note, statement or description is named in `rewritten`, never
> copied. Units deactivate and licences withdraw; nothing is deleted. TEN-S2's register line
> (a compliance status per entity) is the register's to prove, with `c8-reg-entity-status`;
> the teams inside a department come with the teams packages, and the certificate's two
> roadmap branches (AC-TEN1) with the roadmap, which is why TEN-02 stays `in_progress`.

### TEN-S3 — A team can own work and the ownership survives a member leaving `@integration` (TEN-03)
```gherkin
Given the team "Compliance operations" owns an obligation and a case
When one of its members is removed from the tenant
Then the obligation and the case still list the team as owner
And nothing needs reassignment
```

### TEN-S4 — An out-of-office delegate receives approvals and reminders `@integration` `@e2e` (TEN-04, COL-02)
```gherkin
Given an approver who set out-of-office until next Friday with a delegate
When a sign-off request names that approver
Then the delegate is notified and the approver is not
And the approver's triage reminders reach the delegate on the approver's behalf
And the delegate may sign off under their own cases.signoff
And the audit event records the delegate as actor and the absent approver as delegated
When the window closes
Then the approver receives requests again
```

Reworded (`c10-out-of-office`, D-95): the approval is a case sign-off and the reminder a
triage reminder, the two that exist in R2. The absence is `GET`/`PUT /me/out-of-office`
over the membership's `out_of_office_until` and `delegate`; `collab/logic.notify()` routes
the notices. The delegate gains no permission: they must hold every approve permission the
absent person holds (422 `delegate_cannot_approve`), a second open absence is 409
`already_delegated`, and four eyes still refuses a delegate who asked for sign-off. A
delegate who holds `cases.signoff` is told about a sign-off request once, on their own
account. TEN-04 is `built`: the out-of-office screen (`/me/out-of-office`, `c10-fe-prefs-and-ooo`)
landed with the journey, which walks the absent approver's own screen; where the notices go
stays proved by the integration scenario, since no screen yet requests a sign-off on demand.

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

Which package makes each half green: the request, approve, decline and revoke halves are
`c8-ten-support-grants`; entering, the logged reads, the 403 on a write and the 401 after a
revoke or the end of the window are `c8-support-session-guard`; both are green in
`test_ten_s6`. "The ones after that answer 404" is the platform person's next console
session reading the bank. The journey is `c8-ui-support-console`.

```gherkin
Given a platform admin without any grant
When they read a tenant's cases
Then the request answers 404
When they request support access for two hours with a purpose
Then nothing is granted, the reads still answer 404, and the holders of security.manage are notified
When a tenant admin approves the request with a fresh step-up assertion
Then the grant appears on the tenant's Support access panel with the purpose, the person and the end of the window
And every read under it lands in the bank's audit log as "support_access.read" with the route and the platform user
And a write under it answers 403 "support_read_only"
When the tenant admin revokes the grant
Then the next request answers 401 "support_access_ended" and the ones after that answer 404
When the two hours pass without a revocation
Then the grant ends the same way and the reads answer 404 again
When a tenant admin declines a second request, or nobody decides it within the request's lifetime
Then nothing was ever granted and the request can no longer be approved
```

### TEN-S7 — J-8: tenant B cannot see tenant A `@e2e` (NFR-01, TEN-02, TEN-03, TEN-06, COL-01, COL-02, COL-04, AGT-04, ACC-01, ID-08, J-8)
```gherkin
Given seeded tenants A and B that both hold a case on one change and discuss and take part in the same obligations
And tenant A alone holds a member, a custom role and tag, departments, products and teams, a comment on its case mentioning its administrator, a support request, one of its own agents, an agent access entry with a key and a session policy
When A's administrator signs in
Then each of A's records is there for A
When B's compliance officer signs in and opens the change both banks work on
Then B's case shows none of A's comments and lists only B's evidence
And the comments of A's case and the download of A's evidence answer 404 by URL
When B opens the obligation both banks discuss and the obligation both take part in
Then B sees only its own comment and its own participant
And B's inbox holds nothing of A's, and marking A's notification read answers 404
When B's administrator opens A's member and A's agent access entry by URL
Then each answers 404 and the UI shows "Not found", never the data and never a 403
And A's legal entity, department, product, team, support request, agent, agent access key and access log answer 404 by URL
And B's members, organisation, support access, agents, agent access entries and session limits show only B's own
And B's regulatory scope screen shows no market that A watches, none of A's terms and not A's pending request
And B's roles and tenant tags hold none of A's
```

> **Note — what the journey walks (r2-j8-isolation).** Tenant A's rows are the seed's
> (`EXPECTED_TENANT_A_ONLY`, `EXPECTED_J8_ISOLATION`, `EXPECTED_ORG_REGISTER`,
> `EXPECTED_COMMENTS` and the participants block in `apps/shared/e2e_seed.py`); the journey
> reads their ids in A's own session, then reaches for each from B, in the UI where a screen
> addresses the record by id and through the API from B's signed-in page where none does.
> Every 404 is declared where it is expected, so any other failure still fails the journey.

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
And the team lists "Retail Banking" as its department, and the audit event of the team's creation names it
When they move "Retail compliance" to the department "Cards" with the version they read
Then the team lists "Cards" and one audit event holds the department before and after
When they move it with a version someone has since changed
Then the answer is 409 with code "stale_write"
When they put it in another tenant's department
Then the answer is 404 and the team stays in "Cards"
When they put it in a legal entity, or in "Retail Banking" once they have deactivated it
Then the answer is 422 with code "validation_error"
When they take it out of its department
Then the team lists no department
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

> **ten02-team-department (TEN-02).** A team is a row of the bank's `team` list, so its
> department rides the list's own routes: `POST /vocab/team` and `PATCH /vocab/team/{key}`
> (with `If-Match`) take `extra.orgUnitId`, an active business area, business unit or
> function of the same bank. Another bank's unit, or one that does not exist, answers 404
> `not_found`; a group, a legal entity or a deactivated department 422 `validation_error`;
> null takes the team out, since the model allows a team without a department. The
> `vocabulary.created` and `vocabulary.updated` audit rows carry the list's own columns, the
> department among them, before and after. The admin's team form picks the department from
> the bank's active departments, and the departments section lists each one's teams.

> **c8-ui-organisation (TEN-02, ADM-01).** `/admin/organisation` draws the legal entities as a
> tree under the group, each entity's licences and certificates, and the products, with Add
> and Edit for `vocab.manage` only; `stale_write`, `unknown_member`, `unknown_key` and a 422's
> named fields render where they belong. The departments and teams sections are mounted as
> stubs for their own package. TEN-S2 and TEN-S10 are journeys in `tenants.journey.spec.ts`.

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

### TEN-S13 — The legal entities filled in from the public registers `@integration` `@e2e` (TEN-07, AC-TEN2, J-13)
```gherkin
Given an admin holding vocab.manage at a bank that already has "Example Bank AB" with org number 556000-0001
When they look up "556000-0001" in the public registers
Then a job answers 202 and, once done, lists the group from GLEIF with Example Fonder AB and Example Liv Försäkring AB ticked, the holding company unticked and Example Bank AB marked as already in the organisation
And each Swedish company carries its business, licences and branches from Finansinspektionen with the date read
When they add the ticked companies
Then two legal entities are created with org number, LEI, country, type and parent, Example Bank AB is linked and not added twice, and each gets its register facts
And no licence row and no regulatory scope term is written, and each write has its audit event
And a number no company carries fails the job with "lookup_not_found", and a member without vocab.manage gets 403
```

### TEN-S14 — The nightly re-read refreshes the register facts and nothing else `@integration` (TEN-08)
```gherkin
Given Example Bank AB has register facts read yesterday
When the nightly re-read finds a new licence in Finansinspektionen's register
Then the stored facts carry the licence and the read date, with one audit event naming the change
And no organisation row, licence row or regulatory scope term changes
And a register that cannot be reached leaves the stored facts as they were
```
