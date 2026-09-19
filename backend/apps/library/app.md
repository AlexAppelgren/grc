# library — Inventory (the shared library)

> **App spec.** Source: `PRD.md` Module INV (INV-01–INV-07, AC-INV1), playbook 4.3
> and 14, D-11, D-12.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

The library holds sourced public facts shared by every tenant: jurisdictions,
languages, authorities, instruments with their lineage, the provision tree with
verbatim text, and obligations broken out of instruments with a plain-language
duty, duty type, scope facets, trigger, retention, sanction exposure and
provenance. Nothing here carries a `tenant_id` and nothing is written outside a
`library_write()` fence: content changes only through approved proposals, and
the re-verification stamp is the single exception.

Nothing is overwritten. Summaries and legal text are version rows with
effective dates, which is what makes "as of" reads and "show what changed"
possible. Text lives in its original language with translations as rows and
machine translations labelled.

Deliberately simplified for R1: the provision tree is Should, and tenant-private
instruments from a bank's own sources wait for R3. The R1 library is seeded from
the prototype's sample data.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| INV-01 | Instruments with level, binding force, official reference, ELI where available, jurisdiction, authority, in-force dates and lineage | M | R1 | pending |
| INV-02 | Provision tree with verbatim text versions, in-force dates and transitional notes | S | R1 | pending |
| INV-03 | Obligations: plain-language duty, duty type, scope facets, trigger, retention, sanction exposure, provenance, related obligations | M | R1 | pending |
| INV-04 | Versioned summaries with effective dates, "as of" reads and a sentence-level diff | M | R1 | pending |
| INV-05 | Text in the original language plus translations, machine translations labelled | M | R1 | pending |
| INV-06 | Source link and last-verified date on every record, and a "this looks wrong" report | M | R1 | pending |
| INV-07 | Tenant-private instruments and obligations from the tenant's own sources | C | R3 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-INV1** "As of" a date returns the version in force on it (the latest
  effective date on or before the date), and the diff shows what changed between
  two versions at sentence level.
- **Playbook 4.3:** library tables carry no `tenant_id`; instruments, provisions
  and obligations carry an immutable key; legal dates are plain dates with a
  precision (day, month, quarter, year), never timestamps; every model output
  and translation is labelled until a person confirms.
- **Pill contract:** the obligation row shows instrument, "Guidance, comply or
  explain" when not binding, applicability, compliance status if it applies,
  "Change waiting for approval", "N open changes"; library tags render as `brand`
  pills after the flags.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/library.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### INV-S1 — An instrument carries its identity, dates and lineage `@integration` `@e2e` (INV-01)
```gherkin
Given the seeded instrument "FFFS 2017:2" from the Swedish FSA
Then it holds level, binding force, official reference, ELI, jurisdiction SE, authority, in-force date with precision and the instrument it amends
And the instrument screen shows the short name as a brand pill, the regime as information and "Guidance, comply or explain" only when it is not binding
And the record carries no tenant_id and is readable by every tenant
```

### INV-S2 — The provision tree holds verbatim text versions `@integration` `@e2e` (INV-02)
```gherkin
Given an instrument with chapters, sections and paragraphs
When a provision's text is replaced by an amendment in force on 2026-11-01
Then a new text version row exists with that effective date and a transitional note
And the tree screen shows the current text with "Show what changed" opening the diff
```

### INV-S3 — An obligation states the duty and its facets `@integration` `@e2e` (INV-03)
```gherkin
Given a seeded obligation
Then it holds a plain-language duty, a duty type key, scope facet terms, a trigger, retention, sanction exposure, provenance to its provision and related obligations
And the obligation header shows instrument, regime, binding level and compliance status in that order
And the scope block shows one brand pill per term, "All services" when every service is selected and "Not client-specific" when the client list is empty
```

### INV-S4 — "As of" returns the version in force on a date `@integration` `@e2e` (INV-04, AC-INV1)
```gherkin
Given an obligation with summary versions effective 2025-01-01 and 2026-10-01
When a user reads it as of 2026-06-30
Then the 2025-01-01 version is returned
When they read it as of 2026-10-01
Then the 2026-10-01 version is returned
And no version row has been modified since it was written
```

### INV-S5 — The diff between two versions is at sentence level `@integration` `@e2e` (INV-04, AC-INV1)
```gherkin
Given two summary versions that differ in one sentence
When a user opens "Show what changed"
Then the diff marks that sentence as changed and the others as unchanged
And the screen names the two effective dates being compared
```

### INV-S6 — Text exists in the original language with labelled translations `@integration` `@e2e` (INV-05)
```gherkin
Given an obligation whose original text is sv
When a user whose language order is en, sv reads it
Then the en translation is shown with the label "Machine translation" until a person confirms it
And "Show original" reveals the sv text
```

### INV-S7 — Every record has a source link, a last-verified date and a way to report it `@integration` `@e2e` (INV-06)
```gherkin
Given any instrument, provision or obligation
Then the screen shows the source link and "Verified <date>"
When a reader chooses "This looks wrong" and describes the problem
Then a problem report is created for the library editors and the reader sees it acknowledged
```

### INV-S8 — The re-verification stamp is the only write outside a proposal `@integration` (INV-06)
```gherkin
Given a library editor
When they re-verify a record against its source
Then only last_verified and the verifier change, inside library_write()
And the library fence guard fails on any other module that writes a LibraryModel
```

### INV-S9 — Tenant-private records are visible to their owner only `@integration` (INV-07)
```gherkin
Given tenant A registered a private source and an obligation derived from it
Then the obligation carries owner_tenant_id A
And tenant A sees it beside the shared library
And tenant B's reads never return it and a direct fetch answers 404
```

### INV-S10 — Legal dates are plain dates with a precision `@integration` (INV-01, INV-02)
```gherkin
Given an in-force date known only to the quarter
When it is stored
Then the row holds the date and precision "quarter", never a timestamp
And the API and the screen show it as "Q4 2026" in the user's language
```
