# register — The obligations register

> **App spec.** Source: `PRD.md` Module REG (REG-01–REG-07), playbook 4.3
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
an applicability flag. Applicability changes through a request a second person
approves. Risk acceptance is behind four eyes.

Deliberately simplified: the whole register is R2 (chunk 8). Yearly
attestation and waivers are R3.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| REG-01 | Applicability per obligation with a reason, changed only through a request a second person approves | M | R2 | pending |
| REG-02 | Compliance status, status note, risk, owners, process, system, evidence location, next review, per legal entity where the obligation spans several | M | R2 | pending |
| REG-03 | Gaps with owner, severity, target date, remediation, and risk acceptance behind four eyes | M | R2 | pending |
| REG-04 | Assessment history and "how we read this rule" per obligation | S | R2 | pending |
| REG-05 | Linked internal items (policy, procedure, control, process, system) with external references | M | R2 | pending |
| REG-06 | Yearly attestation by the owner, and waivers | C | R3 | pending |
| REG-07 | Recurring duties on the roadmap from recurrence rules | S | R2 | pending |

## 3. Acceptance criteria (from PRD, condensed)

The PRD states no lettered criterion for this module. The criteria below are
the PRD rows and the playbook rules read as tests:

- An applicability request stores the requested value and reason, shows as
  "Waiting for approval", and applies only when a holder of
  `applicability.approve` who is not the requester approves it with step-up.
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

### REG-S1 — Applicability changes through a request a second person approves `@integration` `@e2e` (REG-01)
```gherkin
Given an obligation owner with applicability.request
When they answer "Does it apply to us?" with "Does not apply" and a reason
Then the obligation still shows "Applies" with "Waiting for approval" beside it
When a compliance officer with applicability.approve and a fresh step-up approves
Then the obligation shows "Does not apply" with the reason, and the audit event carries both people and the assertion
```

### REG-S2 — The requester cannot approve their own applicability request `@integration` (REG-01)
```gherkin
Given an applicability request created by Anna
When Anna approves it
Then the request answers 409 with code "four_eyes_violation"
```

### REG-S3 — Compliance status and its details are kept per legal entity `@integration` `@e2e` (REG-02)
```gherkin
Given an obligation that applies to "Bank AB" and "Bank Finance AB"
When the owner records "Compliant" for Bank AB and "Partly compliant" with a status note for Bank Finance AB
Then each entity row holds its own status, note, risk, owner, process, system, evidence location and next review
And the obligation row shows the worse of the two as its pill
```

### REG-S4 — "Applies" and "we comply" are separate facts `@integration` (REG-01, REG-02)
```gherkin
Given an obligation marked "Does not apply"
Then its compliance status is untouched and still readable in history
When applicability is later approved back to "Applies"
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
