# taxonomy — Vocabularies, footprint and languages

> **App spec.** Source: `PRD.md` Module VOC (VOC-01–VOC-09, AC-VOC1–AC-VOC3),
> Module FP (FP-01–FP-04, AC-FP1–AC-FP3), I18N-01, journeys J-5 and J-6, playbook 15 and 17,
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
| VOC-01 | Every extendable list is rows in three tiers; only kinds are code | M | R1 | built |
| VOC-02 | One vocabulary screen per surface: real pill in light and dark, usage count, inline rename, drag to reorder, retire, merge | M | R1 | built |
| VOC-03 | Create where you use it: "Create" with `vocab.manage`, "Suggest" without, both with a near-duplicate hint | S | R2 | in_progress |
| VOC-04 | Statuses are tenant-defined inside fixed categories; a category never goes empty | M | R2 | pending |
| VOC-05 | Tenant scales for compliance status and risk mapped to fixed ordinals | S | R2 | pending |
| VOC-06 | Reason lists for dismissal, closure and risk acceptance | S | R2 | pending |
| VOC-07 | Library vocabulary changes go through the proposal queue | M | R1 | built |
| VOC-08 | Bulk tagging from list views with preview and one audit entry | S | R2 | pending |
| VOC-09 | Tenant configuration is versioned, exportable and importable | S | R3 | pending |
| FP-01 | Footprint across all dimensions; a record matches when every dimension it carries has a term in the footprint; an empty dimension does not restrict, except an opt-in dimension (standards), which matches only what the scope names; an obligation also needs its instrument's regime | M | R1 | in_progress |
| FP-02 | A footprint change previews what it hides and reveals, needs a second person and step-up, one audit event per term | M | R1 | built |
| FP-03 | Feed, inventory, roadmap, briefing and reports respect the footprint, with a visible way to look outside it | M | R1 | in_progress |
| FP-04 | Markets: each covered country is operating, watching or not followed; operating markets are the footprint's jurisdictions; a record's jurisdiction comes from its instrument or authority and EU rules reach every member country and Norway; watching hides nothing and adds a view | M | R1 | pending |
| I18N-01 | Content in `en`, `sv`, `da`, `nb`, `fi` as translation rows; jurisdictions EU, SE, DK, NO, FI as data | M | R1 | built |
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
- **AC-FP2** Turning Denmark on in the jurisdictions previews the change and waits
  for a second person with step-up, and EU rules keep showing with Denmark;
  operating in Norway alone shows EU rules too; watching Norway is one audited
  write that changes no default view, and no market key appears in a URL.
- **AC-FP3** A tenant whose regulatory scope names no standard sees no standard's
  obligations or changes, and its case for such a change is created with
  `footprintMatch` false. After an approved change adding the standard it sees
  them. A law's obligation or change never carries a standard term.
- **On screen this section is "Regulatory scope"** (PRD glossary). In the code, the
  API paths, the permission keys and the route the word stays `footprint`.
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

> **Note — the preview shows counts only.** `relation_type`'s `VocabularyList` entry
> carries no `usage=` annotation, so its usage count is `registry._no_usage()`, hardcoded to
> 0 for every row (registry.py). Chunk3-rest (T8) filed the first real use of one of its
> values, the "Amends" row, on FFFS 2026:11's `instrument_relations` row to FFFS 2017:2, but
> the vocabulary screen still shows 0 for it: nothing in `registry.py` counts
> `instrument_relations` yet. Wiring a real count (`_count("...")` against that relation) is
> not INV-01 or INV-02 work and is left for the chunk that next touches `relation_type`.

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
Then the request answers 409 with code "duplicate_key" and the existing "Custody"
And the screen says the value already exists
When someone creates "Custdy"
Then the request answers 422 with code "near_duplicate" and "Custody" offered
And the screen asks "Did you mean Custody?"
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
Given the seeded compliance officer
When they propose the flag "Client money" with a usage note, and a library editor approves it
(flags are a library list, so every change is a proposal; PRD section 6 gives
proposals.create to the compliance officer, not the admin, see TODO_FOR_alex.md)
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
Given an obligation with no scope terms at all, under an instrument whose regime is in the footprint
Then it matches every tenant with that regime and its scope block reads "Not client-specific"
Given an obligation carrying a term of an opt-in dimension
Then it matches only a footprint that names that term
```

### FP-S2 — A regulatory scope change previews, waits for a second person and audits per term `@integration` `@e2e` (FP-02, AC-FP1)
```gherkin
Given a compliance officer with footprint.request
When they choose "Propose a change" and remove "Advice"
Then the preview counts the obligations that would be hidden and any that would appear, and cases are not counted yet
And a change request is stored and shown as "Waiting for approval"
When the library changes while it waits
Then the waiting request's preview is counted again against today's library
When an approver with footprint.approve and a fresh step-up approves it
Then advice-only obligations and changes are hidden everywhere
And one audit event per term records the change with the assertion reference
And every decided request — approved, rejected or withdrawn — carries the counts it was decided against, the same ones its decision event holds
```

> **Note — the preview shows counts only.** `footprint_logic.preview_of()` counts
> obligations, never instruments, because a footprint change never hides or reveals an
> instrument row by itself; it only changes which obligations under it a bank can see. Chunk
> 3's rest (T13) taught `reading.obligation_scopes()` to inherit an obligation's scope through
> its instrument's own regime (`reading.instrument_scopes()`, the one footprint rule), so an
> obligation whose instrument's regime narrowed is counted correctly, but the preview's shape
> is unchanged: one `FootprintPreviewCount` for obligations, one for cases, and nothing that
> counts instruments on their own.

### FP-S3 — The requester cannot approve their own footprint change `@integration` (FP-02)
```gherkin
Given a footprint change request created by Anna
When Anna approves it
Then the request answers 409 with code "four_eyes_violation"
And the database check constraint refuses the row on its own
```

### FP-S4 — Every surface respects the regulatory scope and offers a way to look outside it `@integration` `@e2e` (FP-03)
```gherkin
Given a regulatory scope without "Advice"
When a user opens the feed, the inventory, the roadmap and the briefing
Then advice-only records are absent from each
When they choose "Show outside our scope" on the inventory
Then the advice-only records appear marked as outside our scope
```
Reports are the note below.

> **Note — the cached verdict.** Two of the four surfaces filter on `change_case.
> footprint_match`, a cached answer written when the case was opened. `apps/cases/matching.py`
> is what keeps it true afterwards: an approved footprint change re-decides that bank's open
> cases, and a change whose scope terms move re-decides every bank's case for it, both on the
> one outbox cursor and both one statement per bank. The scenario above drives that path
> rather than seeding the column, which is what the journey was waiting for.

> **Note — the reports.** The designed scenario named the reports as a fifth surface. Every
> report reads the obligation register (`GET /reports/gaps`, `/reports/overdue-actions`,
> `/reports/summary`), and R1 has no register, so there is no report to open and nothing the
> scope could hide there yet. Chunk 12 builds the reports and proves the scope on them with
> its own scenario. The four surfaces above are every one that exists, and the way to look
> outside the scope is the inventory's, which chunk 3 built: the feed, the roadmap and the
> briefing carry no such switch on purpose, because a person planning work should see the
> work that is theirs (chunk 6 defaults).

> **Note — the journey.** The `@e2e` half walks tenant A's scope as seeded and never
> changes it, because FP-S5 changes that scope and the home and watch journeys read it in
> parallel; dropping Advice and watching records hide is FP-S5's (J-6) and the integration
> half's. The E2E seed leaves pension accounts out of tenant A's scope
> (`EXPECTED_OUTSIDE_SCOPE` in `apps/shared/e2e_seed.py`), so one obligation, the pension
> transfer right, and one change, `chg-e2e-outside-scope`, fall outside it through that term
> alone. The journey finds the change absent from the feed and then marked under "Show
> outside our scope", the obligation absent from the inventory and then marked under the
> same switch, and the change absent from the roadmap and the briefing. The seed-integrity
> guard checks every seeded case's cached verdict against the rule, so a case can no longer
> read as outside on the roadmap while the feed shows its change inside, and it fails when
> a seeded proposal or a named seed record comes to use the outside obligation.

> **Note — the Instruments tab.** Chunk3-rest (T17) split the inventory into an
> Obligations tab and an Instruments tab. Both filter through the same footprint rule
> (`reading.obligation_scopes()` and `reading.instrument_scopes()`, one rule for both kinds,
> INV-01) and both carry their own "Show outside our scope" switch, so the scenario above
> holds unchanged for the new tab: an instrument outside the regulatory scope is absent by
> default and appears marked as outside it when a reader asks to see past the scope.

### FP-S5 — J-6: regulatory scope change with preview and second-person approval `@e2e` (FP-01, FP-02, FP-03, AC-FP1, J-6)
```gherkin
Given the seeded compliance officer and approver
When the officer proposes a change removing "Advice", reads the preview and sends it for approval
And the approver approves it with a passkey step-up
Then the inventory no longer lists the seeded advice-only obligation
And the audit log lists one event per term
```

### FP-S6 — One decision per request, and one waiting request per organisation `@integration` (FP-02)
```gherkin
Given a pending regulatory scope change request
When an approver approves it and the requester withdraws it at the same moment
Then exactly one decision lands and the other answers 409 with code "invalid_transition"
And exactly one history row and one audit event exist per term
When two approvals arrive at the same moment
Then only one writes the terms
When a second request is created while one is pending
Then the database refuses the row and the API answers 409 with code "request_pending"
And each per-term audit event names the request that caused it
```

### FP-S7 — Members without scope permissions cannot open the regulatory scope page `@e2e` (FP-02, ADM-01)
```gherkin
Given a reader with neither footprint.request nor footprint.approve
Then the Admin navigation has no "Regulatory scope" entry
When they open /admin/footprint directly
Then the restricted page says the page is not available to them and names the permission
Given an approver who holds footprint.approve only
When they open the page
Then no checkbox and no "Propose a change" action is present
And at a 375 px viewport the page does not scroll sideways
```

### FP-S8 — Turning on a country brings the EU rules that reach it `@integration` `@e2e` (FP-04, AC-FP2)
```gherkin
Given a tenant whose footprint has no jurisdiction, and obligations from EU, Swedish, Danish and Norwegian instruments
And a compliance officer with footprint.request
When they turn on Denmark in the footprint's jurisdictions and choose "Preview"
Then the preview says that the Swedish and Norwegian obligations will be hidden, and hides no EU obligation
When they send it for approval and an approver with footprint.approve and a fresh step-up approves it
Then the request held Denmark only
And the inventory lists the EU and Danish obligations and no Swedish or Norwegian one
And one audit event and one history row are written for the term
```

### FP-S9 — A record's jurisdiction comes from its instrument, and EU rules reach every member country and Norway `@integration` (FP-04, AC-FP2)
```gherkin
Given a footprint whose only jurisdiction is Norway
And one obligation each from an EU, a Norwegian and a Swedish instrument
Then the EU and Norwegian obligations match and the Swedish one does not
And no jurisdiction term is stored for any of them
When a proposal would tag an obligation with a jurisdiction term
Then applying it answers 422
And the SQL function, called unchanged, and the Python rule give the same answers
And the code that decides this names no country and no dimension
```

### FP-S10 — Watching a market is one audited write that hides nothing `@integration` `@e2e` (FP-04, AC-FP2)
```gherkin
Given a tenant operating in Sweden and an admin with footprint.request
When they switch on "Watching" for Norway
Then one watched market row and one audit event "markets.watch_added" holding the key only are written, with no second person and no step-up
And the footprint and every default view are unchanged
When Norway is watched again through the API
Then the answer is 409 with code "already_watching"
When they switch "Watching" off for Norway
Then the row is removed and the audit event is "markets.watch_removed"
Given a Reader
When they read the footprint
Then they see which markets are operating and which are watched
And watching one answers 403 with requiredPermission "footprint.request"
```

### FP-S11 — A market's level is computed, and operating comes first `@integration` (FP-04)
```gherkin
Given a tenant operating in Sweden and watching Norway
When a request to operate in Norway is approved
Then Norway reads as operating, its watch row is untouched, and no watch event is written
When a request to stop operating in Norway is approved
Then Norway reads as watching again
Given Finland was never watched
When a request to operate in Finland is approved and later reversed
Then Finland reads as not followed
```

### FP-S12 — Jurisdiction terms mirror the jurisdiction rows and cannot be proposed `@integration` (FP-04)
```gherkin
Given the seeded jurisdictions EU, Sweden, Denmark, Norway and Finland
Then the jurisdiction dimension holds exactly one term per active jurisdiction, with the same key and labels
And each country's term has the EU's term as parent, Norway's included
And the international jurisdiction gets no mirrored term
And GET /tenant/footprint lists five jurisdiction terms
And GET /taxonomy/terms marks exactly those five terms as mirrored
When a proposal adds or renames a term in the jurisdiction dimension
Then it answers 422 jurisdiction_term_mirrored and nothing reaches the queue
When an obligation proposal's scope or a change's terms name a jurisdiction term
Then it answers 422 jurisdiction_term_mirrored and nothing is stored
And the refusal names no dimension and no country
When seed_reference runs a second time
Then nothing changes
```

### FP-S13 — The watched-market view of the inventory shows only what watching adds `@integration` `@e2e` (FP-04)
```gherkin
Given a tenant operating in Sweden with the service "Custody" and watching Denmark
And Danish obligations scoped to "Custody" and to "Advice"
When a user chooses "Markets we watch" in the inventory
Then the Danish "Custody" obligation is listed with "Market we watch: Denmark"
And the Danish "Advice" obligation is absent, because the other dimensions still apply
And no EU or Swedish obligation is listed, because they are already in the footprint
And the list takes one footprint filter value, so no contradictory pair can be sent
```

### FP-S14 — Markets stay inside the tenant and out of logs and error reports `@integration` (FP-04, NFR-01, AC-NFR1)
```gherkin
Given tenant A watches Norway and tenant B watches nothing
When tenant B reads its footprint
Then Norway is not watched and no id of tenant A's rows is returned
When tenant B asks to stop watching Norway
Then the answer is 404 and tenant A's row is unchanged
When tenant A watches and stops watching a market
Then the request line that the access log prints, the application log and the captured error-reporting transactions and error events hold no jurisdiction key
```

### FP-S15 — A change's jurisdiction comes from its authority, and the watch feed has the watched-market view `@integration` `@e2e` (FP-04)
```gherkin
Given a footprint whose only jurisdiction is Sweden
And changes from a Danish authority, from an EU authority and with no authority
Then the Danish change does not match, the EU change matches, and the change with no authority matches, because a missing jurisdiction never hides a record
Given the tenant watches Denmark and has the service "Custody"
When a user chooses "Markets we watch" in the watch feed
Then the Danish "Custody" change is listed with "Market we watch: Denmark"
And its case gets no urgency from the market and nobody is notified
```

### FP-S16 — A standard shows only to tenants whose regulatory scope names it `@integration` `@e2e` (FP-01, FP-02, INV-08, AC-FP3)
```gherkin
Given the dimension "Standards followed" of kind opt_in with the term "ISO/IEC 27001"
And the obligation "ISO/IEC 27001:2022 conformance" carrying that term under an instrument whose regime is "AI and ICT"
And tenant A's regulatory scope holds the regime "AI and ICT" and no standard
Then the obligation is absent from tenant A's inventory and appears with "Show outside our scope"
And the regulatory scope page shows "None followed" for the group
When a compliance officer with footprint.request proposes adding "ISO/IEC 27001"
Then the preview reveals the obligation, hides nothing and shows no narrowing warning
When an approver with footprint.approve and a fresh step-up approves it
Then the obligation appears in the inventory
And one audit event records the added term with the assertion reference and the request
When the officer later proposes removing it
Then the preview counts the obligation as hidden and the warning shows
```

### FP-S17 — The pure rule and the SQL function agree on opt-in dimensions, whatever the flag says `@integration` (FP-01)
```gherkin
Given every combination of record terms and scope terms over a scope dimension and an opt-in dimension
Then in_footprint and taxonomy_in_footprint give the same answer for each
And a record carrying an opt-in term matches only when the scope names that term, also when the scope has no entry for the dimension
And an empty scope dimension still does not restrict
And a record carrying no opt-in term is unaffected by the opt-in dimension
When the opt-in dimension's restricts_footprint is false
Then both still treat it as restricting, and the regulatory scope read says it restricts
And calling in_footprint without restricting_dimensions()'s answer, which names the opt-in dimensions, raises a TypeError
```

### I18N-S1 — Languages and jurisdictions are rows, never columns or branches `@integration` (I18N-01)
```gherkin
Given the seeded languages en, sv, da, nb, fi and the jurisdictions EU, SE, DK, NO, FI with their authorities
And the International jurisdiction row for standards bodies, of kind international
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
