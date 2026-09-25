# ADR 0029 — The shared library holds a standard's public facts and one conformance duty

**Date:** 2026-09-19 · **Status:** accepted by default (D-35, PRD 0.3 INV-08, AC-INV2; the owner confirms)

## Context

PRD 0.2 brought standards inside the sector scope, and CLAUDE.md §1 says the
shared library holds sourced public facts. A standard's clause and control
numbers, titles and requirement text exist only in the paid standard, and the
licensing research reports that the publishers' terms exclude integration into
compliance systems and any AI processing. Every fact in that research is
unverified and is listed for the owner to confirm before anything is seeded.
A proposal's payload is stored when the proposal is created, so a check that
ran only at apply would already have put pasted text in the platform database.
`library_write()` also admits seeds, the watch pipeline and tenant-private
records.

## Decision

For each edition of a standard the library holds publisher, reference, dates,
lifecycle, national adoptions as a note and a catalogue link, plus exactly one
active conformance obligation written in our own words, whose reference label
equals the official reference and which carries exactly one standard term. It
holds no provisions, no clause or control titles and no paraphrase. One check
function enforces this at proposal creation (both the API and the agent path),
over a reviewer's corrections at approval, and at apply, answering 422
`licensed_text`, `one_conformance_obligation` or `standard_term_required`.
Field sources on a standard's records must be URLs. A database trigger on
`provision` refuses any row under a standard-level instrument, whatever the
write path, and the fixture check refuses one too.

Deliberately not done: holding clause or control titles under a content
licence. That would change an invariant and is a stop-and-ask.

## Consequences

Easier: the product can carry standards without a content licence, and the
guard sits on every door rather than in each caller. Harder: a tenant cannot
search the library for a clause, and the tenant's own units (ADR 0035) carry
that knowledge instead. To remember: Ask must answer "no answer" about a
control, and an evaluation row guards against the model restating one from
training data.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The level kind and the provision trigger | Chunk 3 |
| 2 | The check function for the obligation-version kind | Chunk 4 |
| 3 | The check function for the instrument, obligation and provision kinds | Chunk 5 |
| 4 | The Ask evaluation row | Chunk 7 |
