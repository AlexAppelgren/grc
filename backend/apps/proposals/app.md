# proposals — The review queue

> **App spec.** Source: `PRD.md` Module PRO (PRO-01–PRO-04, AC-PRO1–AC-PRO2), playbook
> 4.3 and 14, D-14, `docs/inputs/INPUT_DELTAS.md` §5.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

The library is shared by every bank, so no single agent or person edits it.
Agents and people propose; a second, independent principal reviews from the
queue, may correct scope and wording, and approves. Approval applies the
payload, writes the new version, the audit row and the search re-index in one
transaction. The proposer never approves their own proposal, and the database
enforces it.

Since PRD 0.4 (Alex, 2026-09-20, D-48 and ADR 0042) that second principal is
usually an agent: bleqq staffs no editorial function, so a platform API key
bound to an agent definition, holding the scope `proposals:review`, reads the
same queue a person reads and approves, corrects or rejects through the same
logic. Independence is what four eyes means here — a different agent definition
and a different key from the proposer — and the check constraint refuses a row
whose user, key or agent matches on both sides. A person approving still steps
up with a passkey; a key cannot step up, so for an agent the scope and the
constraint are the whole gate. A record applied from a proposal an agent
confirmed carries machine-confirmed provenance (INV-05), never a person's
verification.

The prototype shows the tenant's compliance officer approving agent
proposals. That is the one place the prototype is wrong: the queue lives in
the console with the `library_editor` role, which bleqq keeps and staffs with
nobody — it is how the platform watches what the agents decided, takes a
proposal over, and switches a human approver back on without rework. Tenants
see library updates and can report problems.

One check function guards the standards rules (INV-08) on every door into the
library: at `POST /proposals`, at the agent's proposal creation, over a
reviewer's corrections at approval and at apply. A payload is stored when a
proposal is created, so a check only at apply would leave licensed text in the
platform database.

Deliberately simplified for R1: batch proposals (re-tag, backfill) with a
row-by-row review wait for R2.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| PRO-01 | The review queue is the only way into the library, for agents and people, with a source per changed field | M | R1 | in_progress |
| PRO-02 | Approval applies the payload, writes the version, the audit row and the re-index in one transaction; the reviewer can correct scope and wording first; never the proposer | M | R1 | in_progress |
| PRO-03 | The queue lives in the platform console; tenants see library updates and can report problems | M | R1 | pending |
| PRO-04 | Batch proposals (re-tag, backfill) with a preview, approved whole or row by row | S | R2 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-PRO1** No API key scope and no tenant role can change a library record
  except through an approved proposal.
- **AC-PRO2** Approving your own proposal answers 409 `four_eyes_violation`,
  for a person and for an agent alike: the same user, the same key or the same
  agent definition on both sides is refused, and the check constraint refuses
  the row on its own.
- **Playbook rules:** `Idempotency-Key` on proposal submission because agents
  retry; a proposal carries the source for every changed field; `proposal_kind`
  and `proposal_status` are kinds in code; rejection needs a reason and is
  audited; apply runs inside `library_write()` in `proposals/apply.py`.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/proposals.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### PRO-S1 — A proposal carries a source per changed field `@integration` (PRO-01)
```gherkin
Given an agent key with proposals.write
When it submits a proposal that changes an obligation's summary and duty type
Then each changed field carries a source reference
And a proposal missing a source for any field answers 422 with code "source_missing"
And the proposal is "Waiting for approval" in the queue
```

### PRO-S2 — No scope and no tenant role can change a library record directly `@integration` (PRO-01, AC-PRO1)
```gherkin
Given an API key with every scope and a tenant admin holding every tenant permission
When either writes to an instrument, provision, obligation, version or library vocabulary route
Then the request answers 403 or the route does not exist
And the only path that leaves a library change is an approved proposal
```

### PRO-S3 — Approval applies payload, version, audit row and re-index in one transaction `@integration` `@e2e` (PRO-02)
```gherkin
Given a proposal changing an obligation summary
When a library editor who is not the proposer approves it
Then a new summary version exists with the stated effective date
And the audit event, the outbox event and the search chunk update are in the same transaction
And the obligation shows "version 2" with "Show what changed"
When the re-index step fails
Then nothing was applied and the proposal is still waiting
```

### PRO-S4 — The reviewer corrects scope and wording before approving `@integration` `@e2e` (PRO-02)
```gherkin
Given a proposal with a scope term the editor disagrees with
When the editor edits the scope and the wording in the review screen and approves
Then the applied version carries the corrected values
And the proposal keeps both the proposed and the applied payload for the audit trail
```

### PRO-S5 — Approving your own proposal answers four_eyes_violation `@integration` `@e2e` (PRO-02, AC-PRO2)
```gherkin
Given a library editor who submitted a proposal
When they approve it
Then the request answers 409 with code "four_eyes_violation"
And the check constraint on the proposal table refuses the row on its own
And the screen shows "A second person has to approve this"
```

### PRO-S6 — A retried submission with the same Idempotency-Key creates one proposal `@integration` (PRO-01)
```gherkin
Given an agent submitting a proposal with Idempotency-Key "run-42-obl-7"
When the same request arrives twice
Then one proposal exists and the second call returns it with 200
When the same key arrives with a different payload
Then the request answers 409 with code "idempotency_conflict"
```

### PRO-S7 — The queue is in the console and tenants see updates and report problems `@integration` `@e2e` (PRO-03)
```gherkin
Given a tenant compliance officer and a library editor
When the officer opens the tenant app
Then there is no proposal queue and the review route answers 403
When the editor opens the console
Then the queue lists waiting proposals with the source beside the diff
When a proposal is applied
Then the tenant's "Library updates" lists it and "This looks wrong" opens a problem report
```

### PRO-S8 — A batch proposal previews and is approved whole or row by row `@integration` `@e2e` (PRO-04)
```gherkin
Given a re-tag request that would add "Client money" to twelve obligations
When the editor opens it
Then the preview lists the twelve rows with before and after
When they reject two rows and approve the rest
Then ten obligations change, two do not, and one audit event records the batch with each row's outcome
```

### PRO-S9 — A rejection needs a reason and is audited `@integration` `@e2e` (PRO-01)
```gherkin
Given a waiting proposal
When the editor rejects it without a reason
Then the request answers 422
When they reject it with a reason
Then the proposal is rejected, the proposer is notified with the reason and an audit event records it
And the reason list holds the system row "Outside the sector scope", whose usage note names the PRD's sector scope
```

### PRO-S10 — Licensed text and extra obligations never enter a standard `@integration` (INV-08, PRO-01, PRO-02, AC-INV2)
```gherkin
Given the instrument "ISO/IEC 27001:2022" whose level kind is standard
When a provision or provision_version proposal on it is submitted through POST /proposals or the agent API
Then it is refused at creation with 422 "licensed_text" and no proposal row is stored
When a proposal for its conformance obligation carries a field source that is not a URL
Then it is refused at creation with 422 "licensed_text"
When a reviewer's correction adds provision text to a pending proposal and approves it
Then the approval answers 422 "licensed_text" and nothing is written
When a new_obligation proposal adds a second active obligation under it
Then the apply answers 422 "one_conformance_obligation"
When an obligation under it carries no term of an opt-in dimension, or two
Then the apply answers 422 "standard_term_required"
And a provision row inserted under it directly, as a seed would, is refused by the database
```

### PRO-S11 — A standard term never sits on a law's obligation `@integration` (FP-01, INV-08, AC-FP3)
```gherkin
Given an obligation under a level whose kind is not standard
When a new_obligation_version proposal adds a standard's term to it
Then it is refused at creation with 422 "standard_term_only_on_standards"
When a reviewer's correction adds that term to a pending proposal and approves it
Then the approval answers 422 "standard_term_only_on_standards" and nothing is written
And a tenant whose regulatory scope names no standard still sees the obligation
```

### PRO-S12 — An independent agent confirms a proposal from the same queue `@integration` `@e2e` (PRO-01, PRO-02, AUD-02)
```gherkin
Given a proposal filed by the agent "watch-sweeper" through its own key
And a second platform key bound to a different agent definition, holding the scope "proposals:review"
When that key reads the pending proposals through the queue route a person reads
Then it sees the same proposal with the same source beside the same diff
When it approves, corrects or rejects through the same routes
Then the decision applies exactly as a person's does, in one transaction
And the audit row names the confirming agent, its definition version and its key, and carries no step-up assertion
And a key without the review scope answers 403
And no route under the review scope writes a library row except through apply
```

### PRO-S13 — The same principal can never both propose and approve `@integration` (PRO-02, AC-PRO2)
```gherkin
Given a proposal filed by an agent key
When the same key approves it
Then the request answers 409 with code "four_eyes_violation"
When a second key of the same agent definition approves it
Then the request answers 409 with code "four_eyes_violation"
When the row is written directly, bypassing the logic
Then the check constraint refuses it for a repeated user, key or agent alike
And a key of a different agent definition approves it and the change applies
```
