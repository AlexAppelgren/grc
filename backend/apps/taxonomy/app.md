# taxonomy — Vocabularies, footprint and languages

> **App spec.** Source: `PRD.md` Module VOC (VOC-01–VOC-09, AC-VOC1–AC-VOC3),
> Module FP (FP-01–FP-03, AC-FP1), I18N-01, journeys J-5 and J-6, playbook 15 and 17,
> `docs/inputs/INPUT_DELTAS.md` §1 and §3.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

A new type, status, tag or reason must never need engineering. Every list a
person might extend is rows: library vocabularies the platform curates,
tenant vocabularies a tenant admin manages, and only kinds stay in code. The
abstract `Vocabulary` model (immutable `key`, optional fixed `kind`, labels per
language, `usage_note`, `sort_order`, `active`, `is_system`, `is_default`)
serves pickers, filters, pills and the agents from the same rows.

The footprint is how a bank describes itself once: terms across every
taxonomy dimension. Everything downstream (feed, inventory, roadmap,
briefing, reports) is filtered by it, so changing it has a wide blast radius
and needs a preview, a second person and step-up.

Languages and jurisdictions are data. No column or branch names a country.

Deliberately simplified for R1: tenant sub-statuses, scales, reason lists,
bulk tagging and configuration export come in R2 and R3. In R1 the three tiers,
the vocabulary screen, retire and merge, library changes through proposals,
and the footprint land.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| VOC-01 | Every extendable list is rows in three tiers; only kinds are code | M | R1 | pending |
| VOC-02 | One vocabulary screen per surface: real pill in light and dark, usage count, inline rename, drag to reorder, retire, merge | M | R1 | pending |
| VOC-03 | Create where you use it: "Create" with `vocab.manage`, "Suggest" without, both with a near-duplicate hint | S | R2 | pending |
| VOC-04 | Statuses are tenant-defined inside fixed categories; a category never goes empty | M | R2 | pending |
| VOC-05 | Tenant scales for compliance status and risk mapped to fixed ordinals | S | R2 | pending |
| VOC-06 | Reason lists for dismissal, closure and risk acceptance | S | R2 | pending |
| VOC-07 | Library vocabulary changes go through the proposal queue | M | R1 | pending |
| VOC-08 | Bulk tagging from list views with preview and one audit entry | S | R2 | pending |
| VOC-09 | Tenant configuration is versioned, exportable and importable | S | R3 | pending |
| FP-01 | Footprint across all dimensions; a record matches when every dimension it carries has a term in the footprint; an empty dimension does not restrict | M | R1 | pending |
| FP-02 | A footprint change previews what it hides and reveals, needs a second person and step-up, one audit event per term | M | R1 | pending |
| FP-03 | Feed, inventory, roadmap, briefing and reports respect the footprint, with a visible way to look outside it | M | R1 | pending |
| I18N-01 | Content in `en`, `sv`, `da`, `nb`, `fi` as translation rows; jurisdictions EU, SE, DK, NO, FI as data | M | R1 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-VOC1** An admin adds a change type, a tag and a sub-status with no deploy:
  each appears in pickers, filters, agent vocabulary reads and pills, and
  `openapi.json` is unchanged.
- **AC-VOC2** Retiring a used value keeps history readable and removes it from
  pickers.
- **AC-VOC3** Creating "custody " when "Custody" exists is refused with the near
  match offered (case-insensitive uniqueness, trigram and vector similarity).
- **AC-FP1** Switching off "Advice" previews the obligations and open cases it
  hides, waits for a second person, then hides advice-only obligations and
  changes everywhere.
- **Playbook 15 rules:** retire, never delete, showing the usage count first;
  merge re-points duplicates in one audited transaction; system rows can be
  relabelled but not removed; every list keeps a default; the API returns `key`
  and `kind`, never an enum of values; filters, saved searches, reports, webhooks
  and exports store keys.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/taxonomy.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### VOC-S1 — Extendable lists are rows in three tiers and kinds stay in code `@integration` (VOC-01)
```gherkin
Given the vocabulary registry
Then every list in INPUT_DELTAS §1 tier 2 is a library vocabulary and every tier 3 list a tenant vocabulary under row-level security
And the only enums in code are those in the tier-one allowlist, each with a reason
And the kinds-only guard fails on any TextChoices, Postgres enum or generated union outside the allowlist
```

### VOC-S2 — An admin adds a change type, a tag and a sub-status without a deploy `@integration` `@e2e` (VOC-01, AC-VOC1)
```gherkin
Given a library editor and a tenant admin with vocab.manage
When the editor's proposal adds the change type "Supervisory statement" and the admin adds the tag "Custody" and the sub-status "Waiting for legal" under the category assessing
Then each appears in its picker, its filter, the agent vocabulary read and as a pill of the slot's tone
And the exported openapi.json is byte-identical to before
```

### VOC-S3 — The vocabulary screen renders the real pill with usage count, rename and reorder `@integration` `@e2e` (VOC-02)
```gherkin
Given a tenant admin on the vocabulary screen for tags
Then each row renders as the real pill in the current theme with its usage count
When they rename "Custody" to "Custody services" inline
Then every record that carried the key shows the new label and no record changed
When they drag "Custody services" above "Advice"
Then sort_order is stored and the picker follows it
```

### VOC-S4 — Retiring a used value keeps history readable and leaves pickers `@integration` `@e2e` (VOC-02, AC-VOC2)
```gherkin
Given the tag "Custody" is used by four obligations
When the admin retires it
Then the screen showed the usage count 4 before asking to confirm
And the four obligations still render the label
And the picker and the filter no longer offer it
And the row still exists with active false
```

### VOC-S5 — Merging re-points duplicates in one audited transaction `@integration` `@e2e` (VOC-02)
```gherkin
Given the tags "Custody" and "Custody svcs" both in use
When the admin merges "Custody svcs" into "Custody"
Then every record that carried "Custody svcs" now carries "Custody"
And "Custody svcs" is retired
And one audit event records the merge with both keys and the count of records moved
And a failure halfway leaves nothing changed
```

### VOC-S6 — Create where you use it offers Create or Suggest by permission `@integration` `@e2e` (VOC-03)
```gherkin
Given a picker for tags on an obligation
When a holder of vocab.manage types a value that does not exist
Then the picker offers "Create"
When a member without vocab.manage does the same
Then the picker offers "Suggest" and the suggestion lands with the admin
```

### VOC-S7 — A near-duplicate is refused with the near match offered `@integration` `@e2e` (VOC-03, AC-VOC3)
```gherkin
Given the tag "Custody" exists
When someone creates "custody " with trailing space and different case
Then the request answers 409 with code "near_duplicate" and the near match "Custody"
And the screen asks "Did you mean Custody?"
When someone creates "Custdy"
Then the trigram check answers the same with "Custody" offered
```

### VOC-S8 — Statuses live inside fixed categories and a category never goes empty `@integration` (VOC-04)
```gherkin
Given the case status categories new, assigned, assessing, implementing, signoff, closed, dismissed
When an admin adds "Waiting for legal" under assessing
Then the state machine, the reports and the pill tone read the category only
When the admin retires the last status under assessing
Then the request answers 409 with code "category_empty"
```

### VOC-S9 — Tenant scales map to fixed ordinals and the tone follows the ordinal `@integration` (VOC-05)
```gherkin
Given a tenant compliance scale with "Fully compliant", "Mostly compliant" and "Gap"
When each is mapped to the fixed categories compliant, partly and gap
Then the API returns key and kind for each
And the pill renders positive, warning and negative from the kind, never from the label
```

### VOC-S10 — Reason lists drive dismissal, closure and risk acceptance `@integration` (VOC-06)
```gherkin
Given a tenant reason list for dismissal with "Out of scope" and "Duplicate"
When a compliance officer dismisses a case with the key "out_of_scope"
Then the case stores the key and the screen shows the label
When an agent or a person submits a reason key that does not exist
Then the request answers 422 with code "unknown_key" and the valid keys
```

### VOC-S11 — A library vocabulary change goes through the proposal queue `@integration` `@e2e` (VOC-07)
```gherkin
Given a library editor
When they add a taxonomy term through the console
Then a proposal of kind vocabulary is created instead of a direct write
And the term appears only after a second editor approves it
And the direct write route for library vocabularies does not exist
```

### VOC-S12 — Bulk tagging from a list previews and writes one audit entry `@integration` `@e2e` (VOC-08)
```gherkin
Given a compliance officer with vocab.manage on the obligation list with six rows selected
When they apply the tag "Custody"
Then the preview lists the six obligations and which already carry the tag
When they commit
Then the tag is linked to each obligation and one audit event records the batch with the six ids
```

### VOC-S13 — Tenant configuration is versioned, exportable and importable `@integration` (VOC-09)
```gherkin
Given a tenant's vocabularies, roles, scales and policies
When an admin exports the configuration
Then the export is an open format keyed by immutable keys with a version stamp
When the export is imported into another tenant
Then a dry run lists creates, updates and conflicts before anything commits
```

### VOC-S14 — System rows can be relabelled but not removed, and the API returns key and kind `@integration` (VOC-01)
```gherkin
Given the system urgency row "act_now"
When an admin renames its label to "Act immediately"
Then the label changes and the key does not
When the admin tries to retire it
Then the request answers 409 with code "system_row"
And GET /vocab/urgency returns key, kind and label per language for each row and never an enum
```

### VOC-S15 — J-5: a flag is added, used, rendered as brand, renamed and merged `@e2e` (VOC-01, VOC-02, VOC-07, AC-VOC1, AC-VOC2, J-5)
```gherkin
Given the seeded tenant admin
When they add the flag "Client money" with a usage note
Then it appears in the change picker, the feed filter and the agent vocabulary read
And it renders as a brand pill on a change
When they rename it and later merge it into another flag
Then every change that carried it still shows a readable history
```

### FP-S1 — A record matches when every dimension it carries has a term in the footprint `@integration` (FP-01)
```gherkin
Given a footprint with the services "Custody" and "Payments" and no client category terms
And an obligation scoped to the service "Custody" and the client category "Retail"
Then the obligation matches, because an empty client category dimension does not restrict
Given an obligation scoped to the service "Advice" only
Then it does not match
Given an obligation with no scope terms at all
Then it matches every tenant and its scope block reads "Not client-specific"
```

### FP-S2 — A footprint change previews, waits for a second person and audits per term `@integration` `@e2e` (FP-02, AC-FP1)
```gherkin
Given a compliance officer with footprint.request
When they switch off "Advice"
Then the preview lists the obligations and open cases that would be hidden and any that would appear
And a change request is stored and shown as "Waiting for approval"
When an approver with footprint.approve and a fresh step-up approves it
Then advice-only obligations and changes are hidden everywhere
And one audit event per term records the change with the assertion reference
```

### FP-S3 — The requester cannot approve their own footprint change `@integration` (FP-02)
```gherkin
Given a footprint change request created by Anna
When Anna approves it
Then the request answers 409 with code "four_eyes_violation"
And the database check constraint refuses the row on its own
```

### FP-S4 — Every surface respects the footprint and offers a way to look outside it `@integration` `@e2e` (FP-03)
```gherkin
Given a footprint without "Advice"
When a user opens the feed, the inventory, the roadmap, the briefing and the reports
Then advice-only records are absent from each
When they choose "Show outside footprint" on the inventory
Then the advice-only records appear marked as outside the footprint
```

### FP-S5 — J-6: footprint change with preview and second-person approval `@e2e` (FP-01, FP-02, FP-03, AC-FP1, J-6)
```gherkin
Given the seeded compliance officer and approver
When the officer switches off "Advice", reads the preview and sends it for approval
And the approver approves it with a passkey step-up
Then the inventory no longer lists the seeded advice-only obligation
And the audit log lists one event per term
```

### I18N-S1 — Languages and jurisdictions are rows, never columns or branches `@integration` (I18N-01)
```gherkin
Given the seeded languages en, sv, da, nb, fi and the jurisdictions EU, SE, DK, NO, FI with their authorities
Then no model column and no code branch names a language or a country
And instrument.jurisdiction and authority.jurisdiction reference the jurisdiction table
And a user's locale references the language table
```

### I18N-S2 — Translations are rows with the original marked and machine output labelled `@integration` (I18N-01)
```gherkin
Given an obligation summary written in sv
When a machine translation to en is stored
Then a translation row exists per language with the original marked
And the en row carries machine_translated true and a review state
And the API returns the requested language, falling back along the user's language order
```
