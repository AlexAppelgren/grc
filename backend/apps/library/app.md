# library — Inventory (the shared library)

> **App spec.** Source: `PRD.md` Module INV (INV-01–INV-08, AC-INV1, AC-INV2), playbook 4.3
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

Labelling covers who confirmed a fact, not only who wrote it. Since PRD 0.4
(D-62, ADR 0054) the proposal that applies a record may have been confirmed by
an independent agent rather than a person, so the record carries
machine-confirmed provenance — `verified_origin`, the proposing agent and the
confirming agent — and never reads as verified by a person until a person
verifies it. The re-verification stamp of INV-06 stays a person's act and is
still the single exception to the proposal door.

A standard within the sector scope is an instrument like any other, one per
edition, and the library holds only its public facts plus exactly one duty to
conform written in our own words. Its licensed text, clause and control titles
and any paraphrase of them stay out: a check at proposal creation, at a
reviewer's correction and at apply refuses them, and a database trigger refuses
a provision under a standard whatever the write path. Every instrument carries
a regime, which is the sector boundary.

A bank's own instruments, obligations and sources are tenant content, not
library content: a compliance officer proposes one and a second person in the
same bank approves it with a passkey under `private_records.approve`, through
the same proposal table, apply code and four-eyes constraint. Platform staff
never see or approve them, and no owned row or child of one is indexed,
embedded, reranked or sent to a model (D-57, ADR 0050).

Deliberately simplified for R1: the provision tree is Should, and tenant-private
instruments from a bank's own sources wait for R3. The R1 library is seeded from
the prototype's sample data.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| INV-01 | Instruments with level (a standard's level says so), binding force, official reference, ELI where available, jurisdiction (International for standards bodies), authority, a regime, in-force dates and lineage | M | R1 | built |
| INV-02 | Provision tree with verbatim text versions, in-force dates and transitional notes; never for a standard, whose text is licensed | S | R1 | built |
| INV-03 | Obligations: plain-language duty, duty type, scope facets, trigger, retention, sanction exposure, provenance, related obligations | M | R1 | built |
| INV-04 | Versioned summaries with effective dates, "as of" reads and a sentence-level diff | M | R1 | built |
| INV-05 | Text in the original language plus translations, machine translations labelled | M | R1 | built |
| INV-06 | Source link and last-verified date on every record, and a "this looks wrong" report | M | R1 | built |
| INV-07 | Tenant-private instruments and obligations from the tenant's own sources, proposed and approved inside that bank by a second person; never seen by platform staff, a model, the search index or another tenant (D-57) | C | R3 | pending |
| INV-08 | Standards as instruments, one per edition: publisher, reference, dates, lifecycle, national adoptions as a note, a catalogue link and exactly one conformance duty in our own words carrying the standard's term; no standard text, clause or control title, or paraphrase, anywhere. Built for tests and E2E: the first standard is seeded by `seed_e2e` only until the publishers' terms are cleared (TODO_FOR_alex, legal) | M | R1 | built |

> **Note — what the standard clauses still lack (2026-09-23).** Built: the `standard`
> instrument level with its tier-one kind (D-37), the seeded International jurisdiction of
> kind `international`, left out of the footprint mirror (D-38), `instrument.regime` NOT
> NULL with every seeded regime a term of the `regime` dimension (D-39), and the database
> refusing a provision under a standard on every path a row takes there (D-35, library
> 0008): a provision inserted under, or moved to, a standard or an instrument the writer
> cannot see; an instrument holding provisions moved onto a standard level; and an existing
> level given the kind `standard` while provisions sit under it, and the screens that read
> "Standard" in the binding slot and "licensed" in the tree, walked by INV-S11's journey
> (std-journeys). The `new_instrument` proposal refuses a regime from another dimension with
> 422 `not_a_regime` at creation, over a reviewer's correction and at apply (INV-S12,
> green). Missing, so INV-01, INV-02 and INV-08 stay in progress: the
> ISO/IEC 27001:2022 edition with its one conformance duty is seeded for tests and E2E only
> (`fixtures/e2e_standard.json`, loaded by `seed_e2e` and never by `seed_demo`), linked to
> the standard's term, which a new database files active (watch-standards) and `seed_e2e`
> switches on where it was held (D-85), until Alex
> answers the legal question in `docs/TODO_FOR_alex.md`; and the proposal checks
> of D-35 at creation, at a reviewer's correction and at apply (422 `licensed_text`,
> `one_conformance_obligation`, `standard_term_required`, AC-INV2).

## 3. Acceptance criteria (from PRD, condensed)

- **AC-INV1** "As of" a date returns the version in force on it (the latest
  effective date on or before the date), and the diff shows what changed between
  two versions at sentence level.
- **AC-INV2** A provision or provision-version proposal under a standard is
  refused at creation, through `POST /proposals` and the agent API, with 422
  `licensed_text`. A provision row under a standard is refused by the database.
  The Ask evaluation row about a standard's control expects "no answer", and it
  gates the release.
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
Then it holds level, binding force, official reference, ELI, jurisdiction SE, authority, a regime, in-force date with precision and the instrument it amends
And the API returns the binding level as key, kind and label
And the instrument screen shows the short name as a brand pill, the regime as information and "Guidance, comply or explain" only when it is not binding and the level kind is not standard
And the record carries no tenant_id and is readable by every tenant
```

### INV-S2 — The provision tree holds verbatim text versions `@integration` `@e2e` (INV-02)
```gherkin
Given an instrument with chapters, sections and paragraphs, whose level kind is not standard
When a provision's text is replaced by an amendment in force on 2026-11-01
Then a new text version row exists with that effective date and a transitional note
And the tree screen shows the current text with "Show what changed" opening the diff
```

### INV-S3 — An obligation states the duty and its facets `@integration` `@e2e` (INV-03)
```gherkin
Given a seeded obligation
Then it holds a plain-language duty, a duty type key, scope facet terms, a trigger, retention, sanction exposure, provenance to its provision and related obligations
And the obligation header shows instrument, regime, binding level and compliance status in that order, and reads "Standard" in the binding slot when the level kind is standard
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
Then a problem report is created inside the reader's own bank and the reader sees it acknowledged
And nobody outside that bank reads it, bleqq included (Alex, 2026-09-19, OWNER_RECOMMENDATIONS item 3)
```

> **Note — the provision's own report.** A provision has no source link or
> "this looks wrong" of its own; both are shown and filed through its
> instrument's card (chunk3-rest T17, T18), because the source, the
> last-verified date and the re-verification stamp all sit on the instrument
> row, never on a provision. A reader who spots a wrong sentence in the tree
> reports it against the instrument that carries it.

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
And a platform session, in the console or under a support grant, never returns it either
When tenant B writes a child row under a shared parent, or under tenant A's parent
Then the database refuses it
```

### INV-S10 — Legal dates are plain dates with a precision `@integration` (INV-01, INV-02)
```gherkin
Given an in-force date known only to the quarter
When it is stored
Then the row holds the date and precision "quarter", never a timestamp
And the API and the screen show it as "Q4 2026" in the user's language
```

### INV-S11 — An edition of a standard is an instrument with public facts and no text `@integration` `@e2e` (INV-01, INV-02, INV-08)
```gherkin
Given the instrument "ISO/IEC 27001:2022" at the level "Standard" under the jurisdiction "International" and the authority "ISO/IEC"
Then it holds its official reference, publication date with precision, catalogue link and regime
And the API returns bindingLevel with kind "standard", and a null kind for every other level
And the obligation header and the obligation row show "Standard" in the binding slot, never "Guidance, comply or explain"
And the provision tree reads "The text of this standard is licensed and not held here" with the catalogue link
And the instrument has exactly one obligation and no provision
```

### INV-S12 — Every instrument carries a regime from the regime dimension `@integration` (INV-01, INV-08)
```gherkin
Given an instrument row written without a regime
Then the database refuses it
And every seeded instrument's regime is a term of the regime dimension
When an instrument proposal names a term of the dimension "Service" as its regime and a reviewer approves it
Then the apply answers 422 with code "not_a_regime" and nothing is written
```

### INV-S13 — A private record's text never reaches a model, the index or another bank `@integration` (INV-07)
```gherkin
Given tenant A's private instrument, its obligation and their version rows
When the indexer runs and the worker dispatches its outbox events
Then no chunk, embedding or rerank call carries their text
When a member of tenant A asks for similar records, or opens a private change
Then find-similar returns shared records only and the private change carries no AI-drafted "So what?"
When tenant A's exit deletes the tenant
Then its private instruments and obligations go with their append-only children
```

### INV-S14 — A record an agent confirmed reads as machine-confirmed `@integration` `@e2e` (INV-05, INV-06, PRO-02)
```gherkin
Given a proposal filed by one agent and approved by an independent agent
When the version is applied
Then the record's provenance names the proposing agent and the confirming agent
And verified_origin is "agent" and no person is named as its verifier
And the screen labels it machine-confirmed, in the same place a person's verification would read
When a person later re-verifies the record against its source
Then the stamp names that person and the machine-confirmed label gives way
```
