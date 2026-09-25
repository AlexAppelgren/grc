# register — The obligations register

> **App spec.** Source: `PRD.md` Module REG (REG-01–REG-08, AC-REG1, AC-REG2, J-10), playbook 4.3
> ("applies" and "we comply" are separate facts), 6.7 (obligation and gap pills),
> `docs/inputs/INPUT_DELTAS.md` §4 (`version` and `If-Match`).
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

The register is the tenant's judgement laid over the shared library. Per
obligation the bank records whether it applies and why, who owns it, its
compliance status per legal entity, a status note, risk, the process and
system, where evidence lives, the next review, gaps with remediation, and the
internal items (policy, procedure, control, process, system) it links to.

"Applies" and "we comply" are separate facts, so a gap can never hide behind
an applicability flag. Applicability is set by one compliance person, confirmed
in a dialog and audited, with no second approver and no step-up (D-75). Risk
acceptance is behind four eyes.

A legal entity follows a standard when its applicability on that standard's one
conformance obligation is set to "Applies"; that answer is the only record of it. For
each following entity the tenant lists the clauses and controls it works with as
units, by its own reference and in its own words, one by one or pasted with a
dry run. Each unit has its own applicability, reason, status and gaps, and its
reference and words are fixed once it has history. The register filtered by
standard and entity is the Statement of Applicability. A unit may exist only
under a standard the library admitted, for an entity whose conformance row
applies, which keeps the product out of general-purpose GRC by structure.

Deliberately simplified: the whole register is R2 (chunk 8). Yearly
attestation and waivers are R3. Copying units forward to a new edition or
another entity, and evidence per unit, are deferred (D-41).

PRD 0.5 (D-76, ADR 0057) lets the bank's own agents read this register. With the
tenant reach switch on (ACC-08, `apps/governance`) and the per-entry toggle set,
an agent access credential holding `tenant:read` reads the register decisions on
the obligations in its scope: applicability and its reason per legal entity,
compliance status and status note, how we read this rule, owner, process, system,
next review and the linked internal items. Never gaps, never cases or their
assessments, never comments, never evidence of any kind, never the audit log, and
never a private record, which D-57 keeps away from every model. A `tenant:read`
is a read of settled decisions: a gap or an open case is the bank arguing with
itself, and it is not what an agent building a service needs in order to build it
right.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| REG-01 | Applicability per obligation, per legal entity where it spans several, and per unit of a standard, with a reason, set by one person holding `applicability.approve` after a confirmation dialog, with an audit event and no second approver or step-up (D-75); many rows set in one call, one audit event per row | M | R2 | in_progress |
| REG-02 | Compliance status, status note, risk, owners, process, system, evidence location, next review, per legal entity where the obligation spans several | M | R2 | built |
| REG-03 | Gaps with owner, severity, target date, remediation, and risk acceptance behind four eyes | M | R2 | in_progress |
| REG-04 | Assessment history and "how we read this rule" per obligation | S | R2 | in_progress |
| REG-05 | Linked internal items (policy, procedure, control, process, system) with external references | M | R2 | in_progress |
| REG-06 | Yearly attestation by the owner, and waivers | C | R3 | pending |
| REG-07 | Recurring duties on the roadmap from recurrence rules | S | R2 | in_progress |
| REG-08 | Statement of Applicability: units per following legal entity, by reference and in the tenant's own words, entered one by one or pasted with a dry run, each with applicability, a reason, a status and gaps, fixed once it has history; nothing written under a standard is indexed, sent to a model or shown to another tenant | M | R2 | in_progress |
| ACC-04 | An agent access credential holding `tenant:read`, under an entry with tenant reach on, reads the register decisions on the obligations in its scope. Never gaps, cases, comments, evidence, the audit log or a private record | M | R2 | pending |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- **AC-REG1** An officer holding `applicability.approve` sets 93 unit decisions
  for one entity in one call, after confirming all of them in one dialog.
  Nothing is stored before they confirm, no step-up is asked, and 93 audit
  events name the officer, each unit's value before and after, and its reason.
  `REGISTER_BULK_MAX` caps a call, and a call above it stores nothing.
- **AC-REG2** Nothing a tenant writes under a standard (units, notes, gaps,
  assessments, interpretations, links) appears in a search chunk, an embedding
  input or an AI-generation input, and tenant B receives 404 for it.
- Setting applicability stores the value and reason at once, after the person
  confirms it in a dialog, and writes one audit event naming them, the value
  before and after, and the reason. No request, no second approver, no step-up
  (D-75).
- The obligation row shows applicability ("Applies" or "Does not apply") and,
  only if it applies, the compliance status pill whose tone comes from the
  category (compliant `positive`, partly `warning`, gap `negative`, not assessed
  `information`).
- A gap shows status, severity and source as pills; risk acceptance needs
  `risk.accept.approve` by a second person with step-up and a reason key.
- Tenant-editable rows carry `version`; a write without a matching `If-Match`
  answers 409 `stale_write`.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/register.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### REG-S1 — One compliance person sets applicability after confirming it `@integration` `@e2e` (REG-01)
```gherkin
Given a compliance officer with applicability.approve
And an obligation that spans several legal entities, where the answer names its entity's scope row
When they answer "Does it apply to us?" with "Does not apply" and a reason
Then a dialog asks them to confirm before anything is stored
When they confirm
Then the obligation shows "Does not apply" with the reason at once, with no "Waiting for approval" and no step-up
And one audit event records the person, the value before and after, and the reason
When they cancel the dialog instead
Then nothing is stored and no audit event is written
```

### REG-S2 — Only a holder of applicability.approve sets applicability `@integration` (REG-01)
```gherkin
Given a member without applicability.approve
When they set applicability on an obligation
Then the request answers 403 with requiredPermission "applicability.approve" and nothing is stored
```

### REG-S3 — Compliance status and its details are kept per legal entity `@integration` `@e2e` (REG-02)
```gherkin
Given an obligation that applies to "Bank AB" and "Bank Finance AB"
When the owner records "Compliant" for Bank AB and "Partly compliant" with a status note for Bank Finance AB
Then each entity row holds its own status, note, risk, owner, process, system, evidence location, next review, and its own applicability with its reason and decision time
And the obligation row shows the worse of the two as its pill
```

### REG-S4 — "Applies" and "we comply" are separate facts `@integration` (REG-01, REG-02)
```gherkin
Given an obligation marked "Does not apply"
Then its compliance status is untouched and still readable in history
When applicability is later set back to "Applies"
Then the previous compliance status and its gaps are visible again, nothing was deleted
```

### REG-S5 — A gap has an owner, severity, target date and remediation `@integration` `@e2e` (REG-03)
```gherkin
Given an obligation with status "Gap"
When the owner chooses "Record a gap" with severity high, a target date and a remediation plan
Then the gap shows the pills "Open" as negative, "High" as negative and its source
And the roadmap lists the target date as "Our deadline"
When remediation starts
Then the gap status reads "Remediating" as warning
```

### REG-S6 — Risk acceptance is behind four eyes with step-up `@integration` `@e2e` (REG-03)
```gherkin
Given an open gap
When the owner chooses "Accept the risk" with a reason key
Then the gap shows "Waiting for approval"
When the owner tries to approve it
Then the request answers 409 with code "four_eyes_violation"
When a compliance officer with risk.accept.approve and a fresh step-up approves
Then the gap reads "Risk accepted" as information and the audit event records both people
```

### REG-S7 — Assessment history and "How we read this rule" are kept per obligation `@integration` `@e2e` (REG-04)
```gherkin
Given an obligation assessed twice over a year
When a user opens the obligation
Then "How we read this rule" shows the current interpretation with its author and date
And the history lists each earlier assessment unchanged, with who and when
```

### REG-S8 — Linked internal items carry external references `@integration` `@e2e` (REG-05)
```gherkin
Given an obligation
When the owner links the policy "Client asset policy" with the reference "POL-014" and the control "Daily reconciliation" with a link kind from the tenant vocabulary
Then "Linked internal items" lists both with their kind label and external reference
And the API exposes them so an external GRC system can read the links
```

### REG-S9 — Yearly attestation and waivers `@integration` `@e2e` (REG-06)
```gherkin
Given an obligation whose owner last attested 13 months ago
Then the owner sees it as due for attestation and the roadmap shows the date
When the owner attests it
Then an attestation row records the person, date and the status attested to
When a waiver is granted for a gap with an expiry
Then the gap shows the waiver and its expiry and returns to open when it lapses
```

### REG-S10 — Recurring duties appear on the roadmap from recurrence rules `@integration` (REG-07)
```gherkin
Given an obligation with a duty recurring every quarter, next due 2026-12-31
When the roadmap for Q4 2026 is read
Then the duty appears with "Our deadline"
When it is completed
Then the next occurrence 2027-03-31 is generated in the tenant's timezone
```

### REG-S11 — A stale write on a register row is refused `@integration` (REG-02)
```gherkin
Given two owners loaded the same tenant obligation at version 3
When the first saves with If-Match 3
Then the save succeeds and the version becomes 4
When the second saves with If-Match 3
Then the request answers 409 with code "stale_write" and nothing is merged
```

### REG-S12 — A legal entity follows a standard when its applicability is set to "Applies" `@integration` `@e2e` (REG-01, REG-02)
```gherkin
Given tenant A follows a standard and has the entities "Example Bank AB", "Example Fonder AB" and "Example Liv Försäkring AB"
Then the conformance obligation offers every legal entity, and reading it writes no scope row
When an officer with applicability.approve sets "Applies" for Bank AB with the reason "Certified" and "Does not apply" for Liv with a reason, confirming each
Then each answer carries its entity's scope row, created in the same transaction, and no other row changes
And Bank AB's row reads "Applies" with its reason and decision time, and Liv's reads "Does not apply"
And the obligation row shows the worse of its entity statuses as its pill
```

### REG-S13 — A tenant lists its clauses and controls as units in its own words `@integration` `@e2e` (REG-08)
```gherkin
Given Bank AB's conformance row for a standard applies, and an officer with register.edit
When they paste 12 lines for Bank AB, each an invented reference and their own title
Then a dry run lists the rows it will create and refuses duplicate references and over-long lines
When they commit
Then 12 units exist for Bank AB, each with one audit event
And the form offers no field for the standard's text and asks for their own words
When they add a unit for Liv, whose conformance row does not apply
Then the API answers 422 with code "scope_not_applicable"
When they add a unit under an obligation whose instrument is not a standard
Then the API answers 422 with code "units_only_under_standards"
When they rename a unit that has an applicability decision
Then the API answers 409 with code "unit_has_history" and the unit is unchanged
And a unit with no history can be renamed with If-Match or removed, each audited
```

### REG-S14 — Unit decisions are set from the paste in one confirmed call `@integration` `@e2e` (REG-01, REG-08, AC-REG1)
```gherkin
Given an officer with register.edit and applicability.approve pastes 93 invented units for Bank AB, each with "applies" or "does not apply" and a reason
Then a dialog shows the 93 decisions and asks them to confirm before anything is stored
When they confirm
Then each unit carries its own decision, reason and time, and 93 audit events name the officer
And a call with more rows than the configured cap is refused and stores nothing
```

### REG-S15 — The register filtered by standard and entity is the Statement of Applicability `@integration` `@e2e` (REG-08)
```gherkin
Given Bank AB's decided units under a standard
When the officer filters the register by that standard and by Bank AB
Then each unit shows its reference, the tenant's title, applies or does not apply, the reason, the status pill, the person who set it and the decision date
And each unit's history lists its applicability decisions with who and when
And the conformance row shows its own assessed status, and no status is computed from the units
And Today's standing counts the standard as one obligation
```

### REG-S16 — J-10: a legal entity follows a standard from regulatory scope to Statement of Applicability `@e2e` (FP-02, TEN-02, REG-01, REG-08, J-10)
```gherkin
Given the seeded compliance officer and approver of tenant A
When the officer adds the standard to the regulatory scope and the approver approves it with a passkey step-up
And the officer records the certificate on Example Bank AB with its next audit date
And sets "Applies" for Bank AB with the reason "Certified", confirming it in a dialog
And the officer pastes three invented units with applicability and reasons
And confirms all three in one call
Then the register filtered by that standard and Example Bank AB shows the three decisions
And the roadmap shows the next audit as "Our deadline"
```

### ACC-S4 — With tenant reach on, an entry reads the register decisions in its scope and nothing else `@integration` (ACC-04)
```gherkin
Given an entry with tenant reach on, holding tenant:read, whose scope covers four obligations the bank has decided on
When it reads the register
Then each row carries applicability and its reason per legal entity, compliance status, the status note, how we read this rule, the owner, the process, the system, the next review and the linked internal items
And no gap, case, assessment, comment, evidence row or audit row appears in any response
And a private record of the bank appears in none of them
When it reads a register entry for an obligation outside its scope
Then the request answers 404
```
