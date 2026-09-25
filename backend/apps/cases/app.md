# cases — Case workflow

> **App spec.** Source: `PRD.md` Module CAS (CAS-01–CAS-08, AC-CAS1–AC-CAS2), journeys
> J-2 and J-3, playbook 4.2 (step-up), 4.3, 4.4 (`allowedTransitions`), 15 (statuses
> in categories), D-11, D-13.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

A case carries one regulatory change through one tenant: created in "Needs
triage" with its footprint match, triaged with urgency and owner, assessed
(applies, why, what must change, internal deadline, effort, contributor teams),
implemented through actions with owners and due dates, evidenced, and signed
off by a second person with a passkey step-up. The case file then stands
alone. Closing a case never edits the inventory; that is a proposal.

Statuses live inside fixed categories (`new`, `assigned`, `assessing`,
`implementing`, `signoff`, `closed`, `dismissed`). A tenant may add
sub-statuses; the guards read only the category. Every response lists the
transitions it allows, and concurrent edits are refused, never merged.

Three things a case carries are kept true after it is opened, and none of them is
a workflow step. `footprint_match` is a cached verdict, so `matching.py`
re-decides every open case when the bank's footprint is approved and every
bank's case for a change when that change's scope terms move — one statement
per bank, on the one outbox cursor, changing a boolean and nothing else (D-30).
The library's drafted "So what?" is copied in unconfirmed and brought up to a
better draft by `so_what.py`, which stops at every copy a person has already
confirmed or rewritten: a bank's words are its own. And a bank's decision about
a suggested obligation link is its own row, never the library's link (WAT-04).

Deliberately simplified: R1 ships case creation with the footprint match, the
bank's own "So what?" and its own obligation-link decisions (chunk 5). The
workflow from triage to sign-off is R2 (chunk 9).

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| CAS-01 | One case per tenant per change, created in "needs triage" with its footprint match | M | R1 | built |
| CAS-02 | Triage needs urgency and owner; dismissal needs a reason and can be restored | M | R2 | pending |
| CAS-03 | Impact assessment: applies, why, what must change, internal deadline, effort, and contributor teams, recorded as the case's team participants | M | R2 | pending |
| CAS-04 | Actions with owner and due date, locked while sign-off is pending, exportable as tickets | M | R2 | pending |
| CAS-05 | Evidence as file, link or reference, scanned, hashed, streamed through permission checks | M | R2 | pending |
| CAS-06 | Sign-off only with no open action and at least one piece of evidence, only by a second person, with step-up | M | R2 | pending |
| CAS-07 | A case file that stands alone, as text and as an export | M | R2 | built |
| CAS-08 | Every response lists allowed transitions; concurrent edits are refused, never merged silently | M | R2 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-CAS1** Sign-off is refused with `open_actions` or `evidence_missing`, and
  with `four_eyes_violation` for the requester.
- **AC-CAS2** Two people saving the same assessment: the second receives
  `stale_write`.
- **State machine (Solution Design):** owner on triage, reason on dismissal, a
  why on the assessment, no open action and at least one piece of evidence
  before sign-off, a second person with step-up to close. Dismissed is a
  restorable side exit. An invalid transition answers 409 `invalid_transition`.
- **Labels:** `new` reads "Needs triage", `signoff` reads "Waiting for sign-off".
  Buttons follow the prototype: "Confirm and assign", "Dismiss", "Start
  assessment", "Save assessment and plan actions", "Add action", "Attach
  evidence", "Request sign-off", "Sign off and close", "Show case file".
- **Evidence:** content hash, size and type allow-list, malware scan before the
  file is visible, download streamed through a permission-checked, audited
  endpoint, soft-deleted only.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/cases.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### CAS-S1 — A change creates one case per tenant in "Needs triage" with its footprint match `@integration` (CAS-01)
```gherkin
Given two tenants with different footprints
When a change scoped to "Custody" is registered
Then each tenant gets exactly one case in the category new
And each case caches whether the change matches that tenant's footprint
When the same change is registered again
Then no second case exists for either tenant
```

### CAS-S2 — Triage needs an urgency and an owner `@integration` `@e2e` (CAS-02)
```gherkin
Given a case in "Needs triage" and a compliance officer with cases.triage
When they choose "Confirm and assign" without an owner
Then the request answers 422 naming the owner field
When they set urgency "Within 3 months" and an owner and confirm
Then the case moves to assigned, the owner is notified and the urgency pill renders as warning
```

### CAS-S3 — Dismissal needs a reason and can be restored `@integration` `@e2e` (CAS-02)
```gherkin
Given a case in "Needs triage"
When the officer chooses "Dismiss" without a reason
Then the request answers 422
When they dismiss with the reason key "out_of_scope"
Then the case shows "Dismissed" with the reason and is absent from the open list
When they choose "Move back to triage"
Then the case is back in "Needs triage" and the audit trail shows both moves
```

### CAS-S4 — The impact assessment records what applies and what must change `@integration` `@e2e` (CAS-03)
```gherkin
Given an assigned case and its owner with cases.work
When they choose "Start assessment" and save applies, why, what must change, an internal deadline and an effort size, and add two contributor teams
Then the case moves to assessing and the assessment stores each field with a key for effort
And the two contributor teams are the case's team participants
When they save without a why
Then the request answers 422
```

### CAS-S5 — Two people saving the same assessment: the second receives stale_write `@integration` (CAS-03, CAS-08, AC-CAS2)
```gherkin
Given the owner and a contributor both loaded the assessment at version 2
When the owner saves with If-Match 2
Then it succeeds and the version becomes 3
When the contributor saves with If-Match 2
Then the request answers 409 with code "stale_write" and the screen offers to reload, never merges
```

### CAS-S6 — Actions have an owner and due date, lock during sign-off and export as tickets `@integration` `@e2e` (CAS-04)
```gherkin
Given a case in assessing
When the owner chooses "Add action" with a title, an owner and a due date
Then the action is listed under "Actions" with its due date and the case may move to implementing
When sign-off is requested
Then editing an action answers 409 with code "actions_locked"
When the owner chooses "Send as tickets"
Then an export job is queued and its status endpoint reports it
```

### CAS-S7 — Evidence is scanned, hashed and streamed through permission checks `@integration` `@e2e` (CAS-05)
```gherkin
Given a case in implementing
When the owner chooses "Attach evidence" with a PDF, a link and a reference to an internal document
Then the file is stored with a content hash and stays invisible until the malware scan passes
And a file outside the size or type allow-list answers 422
When a reader downloads the file
Then it streams through the API, the permission is checked and an audit event records the download
```

### CAS-S8 — Sign-off is refused while actions are open or evidence is missing `@integration` `@e2e` (CAS-06, AC-CAS1)
```gherkin
Given a case with one open action and no evidence
When the owner chooses "Request sign-off"
Then the request answers 409 with code "open_actions"
When the action is completed and sign-off is requested again
Then the request answers 409 with code "evidence_missing"
When evidence is attached and sign-off is requested
Then the case reads "Waiting for sign-off"
```

### CAS-S9 — The requester cannot sign off their own case `@integration` `@e2e` (CAS-06, AC-CAS1)
```gherkin
Given a case waiting for sign-off requested by its owner, who also holds cases.signoff
When the owner chooses "Sign off and close"
Then the request answers 409 with code "four_eyes_violation"
And the screen says a second person has to sign off
```

### CAS-S10 — A second person signs off with step-up and the inventory is untouched `@integration` `@e2e` (CAS-06)
```gherkin
Given a case waiting for sign-off and an approver with cases.signoff
When the approver chooses "Sign off and close" without a fresh assertion
Then the request answers 403 with code "step_up_required"
When they pass the passkey prompt and sign off
Then the case is closed, the audit event carries the assertion and no library or register row changed
```

### CAS-S11 — The case file stands alone as text and as an export `@integration` `@e2e` (CAS-07)
```gherkin
Given a closed case
When a user chooses "Show case file"
Then it shows the change, the So what, the assessment, the actions with completion, the evidence list with hashes, the sign-off with both people, and every date
When they export it
Then the export job produces the same content as a document and its download is permission-checked
```

### CAS-S12 — Every response lists allowed transitions and an invalid one is refused `@integration` (CAS-08)
```gherkin
Given a case in assessing
When it is read
Then allowedTransitions lists exactly the categories the guards permit from assessing
When a client posts a transition to closed directly
Then the request answers 409 with code "invalid_transition"
```

### CAS-S13 — Sub-statuses inside a category leave the guards untouched `@integration` (CAS-02, VOC-04)
```gherkin
Given the tenant added "Waiting for legal" under assessing
When a case is set to "Waiting for legal"
Then the state machine treats it as assessing and sign-off rules apply unchanged
And the pill renders the category's tone with the tenant's label
```

### CAS-S14 — J-2: from Today to a triaged case `@e2e` (CAS-01, CAS-02, WAT-05, HOM-01, J-2)
```gherkin
Given the seeded compliance officer
When they open Today, open the lead change, choose "Confirm wording" on the So what, and triage with "Act now" and an owner
Then the case shows assigned with "Act now" as a negative pill and the owner named
And no undeclared API error occurred
```

### CAS-S15 — J-3: assessment to sign-off and the case file `@e2e` (CAS-03, CAS-04, CAS-05, CAS-06, CAS-07, AC-CAS1, J-3)
```gherkin
Given the seeded owner and approver and an assigned case
When the owner records the assessment, adds two actions, completes them, attaches evidence and requests sign-off
And the owner tries "Sign off and close" and is refused
And the approver signs off with a passkey step-up
Then the case is closed and "Show case file" opens a complete file
And the guard declares the one expected 409 on the self sign-off
```

### CAS-S16 — Another tenant's case and evidence answer 404 `@integration` (CAS-05, CAS-07, NFR-01)
```gherkin
Given a case with actions and evidence in tenant A, and tenant B's own case for the same change
When tenant B fetches the case file of that change
Then it reads its own case's file, holding none of A's "So what?", actions, evidence or people
When tenant B fetches A's evidence file, removes it, or edits or removes A's action
Then each answers 404 and no refusal writes an audit row
```

### CAS-S17 — Contributor teams are the case's team participants `@integration` (CAS-03, COL-04)
```gherkin
Given an assigned case and its owner with cases.work
When they add the contributor teams "Legal" and "Retail compliance" on the assessment
Then two team participants exist on the case, each added by its own call, and the assessment stores no separate contributor list
Given Erik added the team "Cards" to the case after the owner loaded the assessment
When the owner removes "Legal" and saves the assessment
Then "Cards" is still a participant, because contributor changes are single adds and removals, never a list replacement
And the case file shows that "Legal" took part until it was removed
```
