# watch — Regulatory watch

> **App spec.** Source: `PRD.md` Module WAT (WAT-01–WAT-07, AC-WAT1–AC-WAT2, AC-AGT1), playbook
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

A run also looks back at the library. For every source it checks, it re-checks
the library records that came from that source, and where a record no longer
matches its source it proposes the correction through the normal proposal door,
with four eyes and never a direct edit. That re-check is how a library error is
found, because a bank's problem report stays inside the bank (D-50, ADR 0043).
The watch agents that do this are bleqq's own, part of the base package: no
bank switches one off, pauses it or changes its cadence, scope or budget
(D-61, ADR 0053).

A standard's revision is watched the same way, from public metadata only: one
change per edition or amendment, the draft, final draft, publication and
accreditation rule as timeline entries, and the end of the transition as the
key date. A publisher's page keeps a URL, a date and a hash and never a
snapshot, and automated checks run only on publishers whose terms allow them.
Every change carries at least one regime, the sector boundary, and a standard's
term only when the authority's jurisdiction is international.

Deliberately simplified for R1: tenant-requested and private sources wait for
R3.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| WAT-01 | Source registry and coverage log: what was checked, when, with what result. Every run also re-checks the library records of the sources it checked and proposes a correction where a record has drifted (D-50) | M | R1 | built |
| WAT-02 | One record per reform with a timeline from consultation to in force, partial dates, duplicates merged | M | R1 | built |
| WAT-03 | Change types, flags and scope from vocabularies, with at least one regime on every change and a standard term only on a change from a standards body; agent classifications shown as suggestions until confirmed | M | R1 | in_progress |
| WAT-04 | Links to affected obligations with confidence, confirmed by a person | M | R1 | in_progress |
| WAT-05 | A drafted "So what?" per change, labelled AI-drafted until a person confirms or rewrites it per tenant | M | R1 | built |
| WAT-06 | Tenants can request a source; private sources are visible to that tenant only, are public pages checked at the request and again at each run, and run only on an approved EU model endpoint (D-57) | S | R3 | pending |
| WAT-07 | Standards watched from public metadata: one change per edition or amendment, a timeline from draft to publication, a key date for the end of the transition, no snapshot of a publisher's page, and automated checks only where the terms allow | S | R1 | in_progress |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-AGT1** A change without a regime answers 422 `regime_required`, and a
  standard's term is accepted only when the authority's jurisdiction kind is
  international.
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
`@e2e` built by `c5-e2e-watch-journeys-a`, against `c5-seed-watch`'s own four sources.

### WAT-S2 — One record per reform carries a timeline with partial dates `@integration` `@e2e` (WAT-02)
```gherkin
Given a change registered with a consultation date of 2026-03, an adoption date of 2026-06-15 and in force "Q1 2027"
Then one regulatory change row exists with three timeline entries, each with its precision
And the change screen renders "March 2026", "15 June 2026" and "Q1 2027" in the user's language
```
`@e2e` built by `c5-e2e-watch-journeys-a`, in English and once more in Swedish (the one
seeded login whose own `locale` is Swedish, `frontend/tests/e2e/support/passkeys.ts`
`LOGINS.readerSv`). Read as rendered: a day-precision date is `formatDate()`'s own short
month (`15 Jun 2026`), not the long form this scenario's own prose uses.

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
Given an agent classifies a change as type "adopted" with the flag "advice_perimeter" and the scope "securities"
Then each is stored as a key, marked suggested and naming the agent that suggested it
And the change row shows the type as a notice pill, the flag as a brand pill, each marked as a suggestion
When an agent of another definition confirms them, with the model call behind its decision, inside its own open run
Then suggested becomes false and each reads machine-confirmed, naming the suggesting and the confirming agent, never as a person's verification
And the audit event records which agent confirmed, and its decision is in the AI output log under agent_review
And the agent that suggested them cannot confirm them through any key of its own
And a bank's own compliance officer cannot confirm them, because a change's type, flag and scope are library facts
And a person holding proposals.review may confirm one instead only with a fresh passkey, and it then reads confirmed by a person
```
A curation confirmation is D-74's: an agent-bound key of another definition with
`proposals:review`, or a person with `proposals.review` who steps up. It is not four eyes
(no proposal stands behind it) and is labelled machine-confirmed when an agent gave it. The
person's path is proven in `tests_curation.py`. `@e2e` stays `test.fixme()`: the screen, its
seed and the journey are `watch-curation-confirm-frontend`'s.

### WAT-S5 — An unknown key answers unknown_key with the valid keys `@integration` (WAT-03, AC-WAT2)
```gherkin
Given the change type vocabulary holds "amendment" and "new_instrument"
When an agent submits the type "ammendment"
Then the request answers 422 with code "unknown_key" and the valid keys listed
And nothing is stored
```

### WAT-S6 — Links to affected obligations carry a confidence, and the library and the bank decide separately `@integration` `@e2e` (WAT-04)
```gherkin
Given an agent linked a change to two obligations with confidence 0.9 and 0.4
Then the change screen's "Obligations affected" shows both with the confidence as a suggestion
When an agent of another definition confirms the first for the shared library
Then that link reads machine-confirmed for every bank, naming both agents, and the audit event records which agent confirmed
When a compliance officer accepts the first and removes the second on their own bank's case
Then both decisions are stored on that bank's case and audited, the second is hidden from that bank's change page, and the obligation shows "1 open change"
And no library row changed: the second link is still there, still a suggestion, and another bank still sees both
```
`@e2e` built for the bank's half: the compliance officer confirms one link and says the
other is not related on their own bank's case ("Confirm link", "Not related"), the removed
link is hidden from that bank's change page and still stored, and another bank still sees
both links, neither decided. The library's half is asserted by the `@integration` half; it
joins the journey with `watch-curation-confirm-frontend`, and until then the seed stands in
for it with one link a person already confirmed (`c5-seed-watch`). That both decisions are
audited is asserted by the `@integration` half, because the audit log's record-kind filter
offers no case kind yet. PRD WAT-04's "confirmed by a person" stays true per bank, on each
bank's own case; the library's confirmation is D-74's and never reads as a person's.

Still pending in this scenario:
- **"The obligation shows 1 open change" on screen.** No screen mounts the obligation's
  related-changes panel (`ObligationRelatedChanges`): the obligation page shows its "later
  release" placeholder in that place. The `@integration` half reads `openCount` from
  `GET /obligations/{obligationId}/changes`; the journey gains the step when the panel is
  mounted.
- **A removed link on the obligation's side.** That route lists and counts every change
  the library links to the obligation, so the obligation a bank marked "Not related" still
  lists the change and counts it as open for that bank. Until the read leaves out a change
  this bank removed for that obligation, the count cannot show a bank's decision.
- **Reversal.** `POST /changes/{changeId}/case/obligation-links` accepts a link the bank
  removed, but no screen offers it in R1: a removed link is hidden, and when every link is
  removed the panel says so rather than that nothing is linked.

### WAT-S7 — The "So what?" is AI-drafted until a person confirms or rewrites it per tenant `@integration` `@e2e` (WAT-05)
```gherkin
Given a change whose registering run filed a drafted "So what?" with it
Then the tenant's copy shows "AI draft" beside it and an ai_generation row exists with model, version and purpose
When the compliance officer chooses "Confirm wording" or rewrites and chooses "Save and confirm"
Then the tenant's copy is marked confirmed with the person and time
And another tenant's copy is still the draft
```
`@e2e` built for the time: tenant A's compliance officer confirms the draft as it stands,
then rewrites it and saves; the page reads back the bank's own words, confirmed, with the
time and no AI label, and tenant B's administrator still reads the draft with its label and
is offered no control.

Still pending in this scenario: **the person on screen.** "Confirmed with the person and
time" needs the person's name on the change read, which carries `soWhatConfirmedAt` and no
name (nor does an accepted link's `decidedAt`). The person is stored
(`change_case.so_what_confirmed_by`, `case_obligation_link.decided_by`), audited, and named
in the write's own answer, but a reload cannot show it. When the read carries
`soWhatConfirmedByName` and `decidedByName`, the screen renders the design's "Confirmed by
{name}, {date}" (`watch.soWhat.confirmedBy`, `watch.change.confirmedBy`) in place of
"Confirmed {date}" and "Confirmed for us, {date}", and WAT-S6 and WAT-S7 assert the name.

### WAT-S8 — A tenant requests a source and private sources stay private `@integration` `@e2e` (WAT-06)
```gherkin
Given tenant A uses "Request a source" for a public page of a market it watches
Then the address is checked for https, no credentials, a public host, not a standards publisher's host and not an existing shared source
And the source carries owner_tenant_id A, the request writes one tenant audit row, and the cap per bank is enforced
When an agent registers a change from it
Then tenant A sees the change in its feed
And tenant B's feed never lists it and a direct fetch answers 404
And the host is checked again at the start of every run
```

### WAT-S9 — The change row renders its pills in the fixed slot order `@e2e` (WAT-03, NFR-03)
```gherkin
Given a change of type "amendment", urgency "Act now", one flag and status "Needs triage"
When the feed renders it
Then the pills read, in order: the type as notice, "Act now" as negative, the flag as brand
And the header adds "Needs triage" as information, then the authority and date as plain text
```
`@e2e` built by `c5-e2e-watch-journeys-a`, against a seeded change of urgency
"within_3_months" (`warning`) rather than this scenario's own "Act now" example: the same
tone-by-ordinal rule holds for either.

### WAT-S10 — A new edition of a standard is one change, and only tenants that follow it see it `@integration` `@e2e` (WAT-02, WAT-07, CAS-01, AC-FP3)
```gherkin
Given tenant A follows "ISO/IEC 27001" and tenant B follows no standard
When an agent registers the change "ISO/IEC 27001 amendment" with the authority "ISO/IEC", the term "ISO/IEC 27001", the regime "AI and ICT", a draft-for-comment timeline entry and a key date labelled "Transition ends"
And later registers the same stable key with its publication date
Then one change exists with both timeline entries
And each tenant has exactly one case for it, tenant A's matching its scope and tenant B's not
And the change and the transition date appear in tenant A's feed and roadmap and in neither of tenant B's
```

### WAT-S11 — Every change carries a regime, a standard term needs a standards body, and a publisher's page keeps no snapshot `@integration` (WAT-01, WAT-03, WAT-07, AC-AGT1)
```gherkin
Given an agent key with changes:write
When it registers a change with no regime term
Then the API answers 422 with code "regime_required" and the valid regime keys
When it registers a change carrying a standard's term whose authority is a national supervisor
Then the API answers 422 with code "standard_term_only_on_standards"
Given the open web sweep fetches a page on a host listed in the standards publisher setting
Then the stored source document holds the URL, the date and a content hash and no snapshot
When a change carrying an opt-in term links a document that has a snapshot
Then the API answers 422 with code "licensed_text"
And a source of kind "Standards body" registered inactive gets no automated check
```

### WAT-S12 — A run re-checks the library records of the sources it checked and proposes the correction `@integration` (WAT-01, AUD-03)
```gherkin
Given a library obligation whose source page now states a different date
When a watch run checks that source
Then the run's coverage log names the records it re-checked beside the documents it fetched
And the drift becomes a proposal carrying the source per changed field, never a direct edit
When a second library editor approves it
Then the library holds the corrected version, and the re-verification stamp stays the only write outside a proposal
When nothing has drifted
Then the re-check writes no proposal
```
