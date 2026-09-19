# watch — Regulatory watch

> **App spec.** Source: `PRD.md` Module WAT (WAT-01–WAT-06, AC-WAT1–AC-WAT2), playbook
> 4.3 (idempotency), 6.7 (change pill slots), 16.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

Watch is where a regulatory change is first seen. Agents check sources and
log what they checked, register one record per reform with a timeline from
consultation to in force, classify it with change types, flags and scope from
the vocabularies, link it to the obligations it affects with a confidence, and
draft a "So what?". Every one of those is a suggestion until a person
confirms it, and every finding lands in a queue, never in the inventory.

Duplicates are merged: posting a known `stableKey` adds new pages to the
existing change instead of creating a second one, because agents and senders
retry.

Deliberately simplified for R1: tenant-requested and private sources wait for
R3.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| WAT-01 | Source registry and coverage log: what was checked, when, with what result | M | R1 | pending |
| WAT-02 | One record per reform with a timeline from consultation to in force, partial dates, duplicates merged | M | R1 | pending |
| WAT-03 | Change types, flags and scope from vocabularies; agent classifications shown as suggestions until confirmed | M | R1 | pending |
| WAT-04 | Links to affected obligations with confidence, confirmed by a person | M | R1 | pending |
| WAT-05 | A drafted "So what?" per change, labelled AI-drafted until a person confirms or rewrites it per tenant | M | R1 | pending |
| WAT-06 | Tenants can request a source; private sources are visible to that tenant only | S | R3 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-WAT1** Posting a known `stableKey` merges new pages as duplicates and
  returns the existing change.
- **AC-WAT2** An agent submitting an unknown key receives 422 `unknown_key` with
  the valid keys.
- **Pill contract:** a change row shows change type (`notice`), urgency (tone by
  ordinal: "Act now" `negative`, "Within 3 months" `warning`, "6+ months"
  `notice`, "Monitor" `information`, "No action" `positive`), flags (`brand`),
  then workflow status on the header only, then authority and date as plain
  meta text. Timeline dates are partial dates with a precision.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/watch.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### WAT-S1 — The source registry and coverage log show what was checked and with what result `@integration` `@e2e` (WAT-01)
```gherkin
Given a registered source "Finansinspektionen news" with a check cadence
When an agent run logs a check with status ok and zero new items, and a later check fails
Then the coverage log lists both with time, result and the run
And the console's "Source coverage" shows the source as stale after the failure with the failing check named
```

### WAT-S2 — One record per reform carries a timeline with partial dates `@integration` `@e2e` (WAT-02)
```gherkin
Given a change registered with a consultation date of 2026-03, an adoption date of 2026-06-15 and in force "Q1 2027"
Then one regulatory change row exists with three timeline entries, each with its precision
And the change screen renders "March 2026", "15 June 2026" and "Q1 2027" in the user's language
```

### WAT-S3 — A known stableKey merges duplicates and returns the existing change `@integration` (WAT-02, AC-WAT1)
```gherkin
Given a change registered with stableKey "eu-dora-rts-2026-01"
When an agent posts the same stableKey with a new source page
Then the response is 200 with the existing change id
And the new page is linked as a duplicate document on that change
And no second change row exists
```

### WAT-S4 — Types, flags and scope come from vocabularies and stay suggestions until confirmed `@integration` `@e2e` (WAT-03)
```gherkin
Given an agent classifies a change as type "amendment" with the flag "client_money" and the scope "custody"
Then each is stored as a key with confidence and suggested true
And the change row shows the type as a notice pill, the flag as a brand pill, each marked as a suggestion
When a compliance officer confirms them
Then suggested becomes false and the audit event records who confirmed
```

### WAT-S5 — An unknown key answers unknown_key with the valid keys `@integration` (WAT-03, AC-WAT2)
```gherkin
Given the change type vocabulary holds "amendment" and "new_instrument"
When an agent submits the type "ammendment"
Then the request answers 422 with code "unknown_key" and the valid keys listed
And nothing is stored
```

### WAT-S6 — Links to affected obligations carry a confidence and are confirmed by a person `@integration` `@e2e` (WAT-04)
```gherkin
Given an agent linked a change to two obligations with confidence 0.9 and 0.4
Then the change screen's "Obligations affected" shows both with the confidence as a suggestion
When a compliance officer confirms the first and removes the second
Then the first link is confirmed and audited, the second is gone, and the obligation shows "1 open change"
```

### WAT-S7 — The "So what?" is AI-drafted until a person confirms or rewrites it per tenant `@integration` `@e2e` (WAT-05)
```gherkin
Given a change with a drafted "So what?" from the LLM adapter
Then the tenant's copy shows "AI draft" beside it and an ai_generation row exists with model, version and purpose
When the compliance officer chooses "Confirm wording" or rewrites and chooses "Save wording"
Then the tenant's copy is marked confirmed with the person and time
And another tenant's copy is still the draft
```

### WAT-S8 — A tenant requests a source and private sources stay private `@integration` `@e2e` (WAT-06)
```gherkin
Given tenant A uses "Request a source" for an internal circular
Then a research request is created for the agents and the source carries owner_tenant_id A
When an agent registers a change from it
Then tenant A sees the change in its feed
And tenant B's feed never lists it and a direct fetch answers 404
```

### WAT-S9 — The change row renders its pills in the fixed slot order `@e2e` (WAT-03, NFR-03)
```gherkin
Given a change of type "amendment", urgency "Act now", one flag and status "Needs triage"
When the feed renders it
Then the pills read, in order: the type as notice, "Act now" as negative, the flag as brand
And the header adds "Needs triage" as information, then the authority and date as plain text
```
