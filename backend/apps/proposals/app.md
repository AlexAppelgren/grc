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

Since PRD 0.4 (Alex, 2026-09-20, D-62 and ADR 0054) that second principal is
usually an agent: bleqq staffs no editorial function, so a platform API key
bound to an agent definition, holding the scope `proposals:review`, reads the
same queue a person reads and approves, corrects or rejects through the same
logic. Independence is what four eyes means here — a different agent definition
and a different key from the proposer — and the check constraint refuses a row
whose user, key or agent matches on both sides. A person approving still steps
up with a passkey; a key cannot step up, so for an agent the gate is the scope,
the constraint and the model call behind its decision: an agent's approval or
rejection names the model, the output and its citations and an open run of its
own key, and is refused without them; the call is logged in the AI output log
with the decision, and the audit row names the run (D-80). A person sends
neither. A record applied from a proposal an agent
confirmed carries machine-confirmed provenance (INV-05), never a person's
verification. An obligation version carries it, and since taxonomy 0007 so do a
library list row and a taxonomy term: the approval that writes their wording
records `user` or `agent`, the confirming agent and the proposal. Every label an
agent's approval writes is stored machine-made, and the row keeps naming the
agents until a person has approved all the wording they left. A new instrument
records it on its row, and a new obligation on its row and its first version. So
an agent approves every kind whose record can name it: an obligation version, a
new instrument, a new obligation and, since Alex lifted D-79's interim refusal on
2026-09-23, every vocabulary and term kind. A provision and its versions have no
such column, so `new_provision` and `new_provision_version` answer an agent 409
`person_review_required` and wait for a person, as will any kind added later
without that provenance (D-79). A key bound to no agent definition is
refused at the queue's gate with 403 `agent_not_bound`.

The prototype shows the tenant's compliance officer approving agent
proposals. That is the one place the prototype is wrong: the queue lives in
the console with the `library_editor` role, which bleqq keeps and staffs with
nobody — it is how the platform watches what the agents decided, takes a
proposal over, and switches a human approver back on without rework. Tenants
see library updates and can report a problem, and that report stays inside the bank that filed it: no
editor, other bank, agent or model reads it, and the library is corrected
instead by the watch agents' re-check, which proposes the correction like any
other (D-50, ADR 0043).

A bank reads none of that queue. It reads the other end of it: `GET /library-updates`
lists what was approved and applied since it last marked the library as seen, titled by
the library record and never by the request that carried it, cut to its own footprint,
naming no person, and naming by definition key the agents that proposed or confirmed a
change (INV-05, D-62). Its own requests to a shared list it follows through
`GET /tenant/proposals`, which answers its rows and no other bank's.

A bank's own private records travel the same table but never the console: the
server sets the proposal's owner from the target, and a second person in the
same bank approves under `private_records.approve` with a passkey, through the
same apply code and the same four-eyes constraint (D-57, ADR 0050).

One check function guards the standards rules (INV-08, D-35, D-36) on every door into the
library: at `POST /proposals`, at the agent's proposal creation, over a
reviewer's corrections at approval and at apply. A payload is stored when a
proposal is created, so a check only at apply would leave licensed text in the
platform database. It reads the instrument level's kind and the term dimension's kind,
never a key, and answers four codes: `licensed_text` for a provision or provision version
under a standard, or a source on a standard's obligation that is not an https link;
`one_conformance_obligation` for a new obligation under a standard that already holds an
active one; `standard_term_required` for a standard's obligation whose scope would hold no
standard term or two; and `standard_term_only_on_standards` for a standard's term on a law's
obligation, a new one included. The trigger `provision_not_under_standard` (library 0008)
refuses a standard's provision in the database whatever writes it, so PRO-S10 proves the
provision version case on the check itself: there is no standard's provision to version.

The kinds are chunk 2's vocabulary and term kinds plus `new_obligation_version`: a new
summary in force from a date, with the scope terms that come with it. `new_instrument` and
`new_obligation` bring a record the library does not hold yet: they name no target, every
fact they set carries an https link as its source, and the proposal's `sourceUrl` becomes
the record's own source. An instrument's regime is a term of the regime dimension, or 422
`not_a_regime` at creation, over a correction and at apply (D-39). Approval writes the
record, a new obligation's first version (naming the proposal, so the proposing side reads
as for any version), the audit row and the re-index in one transaction, and stamps who
confirmed it: `verified_origin` `agent` with the confirming agent, or `user`. An agent's
approval of either still waits for a person (D-79) until the vocabulary and term
provenance lands; the stamp is proven through the apply itself meanwhile. The proposal
keeps its sources field by field; there is no citation table yet. `update_obligation` and
`retire_record` wait for a scenario that needs them, and a watch link never travels as a
proposal (D-64). PRO-S1, PRO-S3, PRO-S5 and PRO-S6 cover the two kinds beside the kinds
they were written for: a source per fact, one transaction with the re-index, four eyes and
the idempotent retry. `new_provision` brings a node of a law's text with its first verbatim
text, sourced like a new record, and `new_provision_version` a later text of a provision
that exists, sourced like an obligation version (proposals 0005). Each writes its version,
naming the proposal, its audit row and the provision's re-index in one transaction. Both may
be corrected; an agent's approval of either waits for a person (D-79), since a provision
version has no column to say an agent confirmed it. A bank's library updates list them
uncut, as a record of the library rather than a duty. A proposal a bank's
own person or agent makes is linked to that bank in `proposal_tenant`, a tenant table, so
the bank can follow its own proposals while the console sees only that one came from a
bank, never who made it.

Deliberately simplified for R1: batch proposals (re-tag, backfill) with a
row-by-row review wait for R2.

PRD 0.7 (D-89, Alex 2026-09-24; details answered by default in D-91, ADR 0059,
`docs/plans/briefs/SCOPE_ITEMS.md`) adds group OWN, the bank's own regulations. Alex's
words:
"an agent can always add things to the library, and then another agent can verify it, its then up to the tenant to decide if they want to use it or not",
and
"The previously called 'footprint' can not be agent managed, only a tenant admin can add things that the agents should look out for or regulations that apply to them".
D-89 decides that a bank's people may add to its regulatory scope
a regulation or area the shared library does not yet cover, that the bank's own agents
research it and fill the bank's own library zone with regulation and control inventories
as proposals, and that the bank's people approve or reject them the way the shared queue
works. Here that means OWN-03, the bank's own queue: what the bank's own agent filed
for a scope item, and what its compliance officers propose, waits there and never in
the console. A person holding `private_records.approve` approves with a passkey or
rejects with a reason, never the proposer, through the same apply code and four-eyes
constraint as the shared queue (ADR 0050). PRO-S12 moves from chunk 13 to R2 as written.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| PRO-01 | The review queue is the only way into the library, for agents and people, with a source per changed field | M | R1 | built |
| PRO-02 | Approval applies the payload, writes the version, the audit row and the re-index in one transaction; the reviewer can correct scope and wording first; never the proposer | M | R1 | built |
| PRO-03 | The queue lives in the platform console; tenants see library updates and can report a problem, which stays inside their bank. A bank's private records are proposed and approved inside the bank and never reach the console (D-50, D-57). R1 builds the platform queue, library updates and the bank's own problem reports; a bank's private records (INV-07, PRO-S12) move to R2 with OWN-03 (PRD 0.7) | M | R1 | built |
| PRO-04 | Batch proposals (re-tag, backfill) with a preview, approved whole or row by row | S | R2 | built |
| OWN-03 | The bank's own queue: approve or reject under `private_records.approve` with a passkey, never the proposer, a reason on reject; platform staff never see it (D-57, D-89) | M | R2 | in_progress |

PRO-03 is `built` for R1 (R1 close, 2026-09-24). The console queue, the bank's "Library
updates" screen (`/inventory/updates` over `GET /library-updates`) and "This looks wrong" on
each of its rows, filed through the same report form the obligation card uses and kept
inside the bank, are proven by PRO-S7 at the integration level and by its journey in the
merged batch run. Its last clause, a bank's private records (PRO-S12, INV-07), moved to R2
with OWN-03 in PRD 0.7 and waits for chunk 11; it is named as the cut, not built.

OWN-03 is `in_progress` (d89-proposal-owner, 2026-09-25): a proposal carries `owner_tenant_id`,
set by `logic.create` from its target or, for the bank's own new instrument or obligation,
from the bank the database is scoped to, never from a body; `proposal` is under forced
row-level security in the split shape, so the console reads no owned row
(apps/shared/tests_rls.py); `private_records.approve` belongs to Compliance officer and
Approver; and the bank's own queue, `GET /private-proposals` and `POST
/private-proposals/{proposalId}/approve` and `/reject`, is declared and answers 501 after
loading under row-level security (apps/proposals/tests_private_contract.py). Deciding, and
PRO-S12 whole, are d89-private-records'.

PRO-04 is `built` (c11-proposal-batches-decide, 2026-09-25): a re-tag batch is filed with its
preview and decided row by row, with a rest decision, by a second person holding
`proposals.review` with a fresh passkey. Approved rows rewrite their obligations' scope terms
through `apply()`'s `obligation_scope` branch, inside the proposal door, with an audit row per
row (terms before and after), one naming every row's outcome and the re-index, in one
transaction; PRO-S8 proves it at the integration level. The proposer, who is the person who
asked for the re-tag, is refused with 409 `four_eyes_violation`, and an agent with 409
`person_review_required`; no API key reaches the route. The console screen and PRO-S8's
journey are `c11-fe-console-batch-retag`'s and the console journey package's.

PRO-S13's journey (pro-s13-journey) runs end to end: the console mints a `library-confirmer`
key with `agent-runs:write` and `proposals:review`, which opens a run, reads the queue and
the detail of the proposal `watch-sweeper` filed through its own key (seeded on
`obl-product-governance`, no other journey's), approves it with the model call behind the
decision and that run, and closes the run. A library editor then finds it under Approved,
applied by the agent and machine-confirmed, and a bank's reader finds version 2 on the card
labelled as proposed by one agent and confirmed by the other. A key of the same agent
without `proposals:review` answers 403 at the queue. The 422 and 404 refusals, the logged
call and the audit row stay proven at the integration level (`test_pro_s13`).

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
When it submits a proposal that changes an obligation's summary and scope terms
Then each changed field carries a source reference
And a proposal missing a source for any field answers 422 with code "source_missing"
And a source that is neither an https link nor a provision of the library is refused
And a source given for a field the proposal does not change is refused
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
And that report is readable inside the bank only: the console has no problem-report surface and no platform session returns it
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
When a proposal filed before this rule asks for that term and is approved as it stands
Then the approval answers the same and nothing is written
When a new_obligation proposal under that level carries a standard's term
Then it is refused at creation, and at apply when stored before the rule, with the same code
And a tenant whose regulatory scope names no standard still sees the obligation
```

### PRO-S12 — A private proposal is approved inside the bank and never reaches the console `@integration` (INV-07, PRO-03)
```gherkin
Given a compliance officer in tenant A who proposed a private instrument
Then the proposal carries owner_tenant_id A, set by the server and not by the request body
And the console queue never lists it, and a library editor's fetch answers 404
When the same officer approves it
Then the response is 409 "four_eyes_violation"
When a second person in tenant A with private_records.approve approves it with a fresh step-up
Then the payload is applied, and the audit and outbox rows are written in tenant A's zone
When a member of tenant A files a proposal against a shared record
Then its owner stays empty and the console queue lists it as before
```

### PRO-S13 — An independent agent confirms a proposal from the same queue `@integration` `@e2e` (PRO-01, PRO-02, AUD-02)
```gherkin
Given a proposal filed by the agent "watch-sweeper" through its own key
And a second platform key bound to a different agent definition, holding the scope "proposals:review"
When that key reads the pending proposals through the queue route a person reads
Then it sees the same proposal with the same source beside the same diff
When it approves, corrects or rejects through the same routes
Then the decision applies exactly as a person's does, in one transaction
And a decision sent without the model call behind it answers 422, and one naming a run of another agent's key answers 404, and neither applies anything
And a correction by the agent that moves the original language answers 422 and applies nothing
And the model call behind each decision is logged against the proposal in the run the agent named
And the audit row names the confirming agent, its definition version, its key and that run, and carries no step-up assertion
When it approves a vocabulary proposal from the same queue
Then the list row names the confirming agent and the proposal, every label it wrote is stored machine-made, and the list read names both agents and no person
And a key without the review scope answers 403
And no route under the review scope writes a library row except through apply
```

### PRO-S14 — The same principal can never both propose and approve `@integration` (PRO-02, AC-PRO2)
```gherkin
Given a proposal filed by an agent key
When the same key approves it
Then the request answers 409 with code "four_eyes_violation"
When a second key of the same agent definition approves it
Then the request answers 409 with code "four_eyes_violation"
When the row is written directly, bypassing the logic
Then the check constraint refuses it for a repeated user, key or agent alike
And it refuses a reviewing key that names no agent, so two unbound keys cannot pass on nulls
And such a key is refused before that, on every route of the queue, with 403 "agent_not_bound"
And a key of a different agent definition approves it and the change applies
```
### PRO-S15 — The bank's own queue decides what its own agent filed `@integration` `@e2e` (OWN-03, INV-07, PRO-03, AC-OWN1)
```gherkin
Given proposals tenant A's own agent filed through runner events for an approved scope item
Then tenant A's own queue lists them, the console queue never does, and a platform session's fetch answers 404
When a member of tenant A without private_records.approve approves one
Then the request answers 403
When an approver with private_records.approve approves it without a fresh step-up
Then the request answers 403 with code "step_up_required"
When they approve it with a fresh passkey assertion
Then the record is applied in tenant A's zone and the audit row names the approver and, as proposer, the run's agent
When they reject another without a reason
Then the request answers 422 and nothing changes
When they reject it with a reason
Then it is rejected, audited, and nothing is applied
And tenant B's fetch of either proposal answers 404, and no API key of any scope reaches the approve or reject route
```

