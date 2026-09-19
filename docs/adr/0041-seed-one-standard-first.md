# ADR 0041 — One standard is seeded first, and the rest arrive by proposal

**Date:** 2026-09-19 · **Status:** accepted by default (D-47, PRD 0.3 INV-08; the owner confirms)

## Context

The demo fixture and the end-to-end journeys need one real standard, and the
evaluation set needs rows about it. Seeding more than one multiplies the
unverified facts that must be fetched and the licence terms that must be read,
and a lineage row needs a second edition to point at.

## Decision

Seed ISO/IEC 27001:2022 only, in the demo fixture, once its facts have been
fetched and logged in the Verification log, and with no relation rows. A
"replaces" relation type is added by a vocabulary proposal when a second
edition is entered; "amends" is not added, because an amendment that keeps the
edition is an obligation version. Every other standard arrives by proposal.
Payment-card and messaging-scheme standards stay out until their licence terms
have been read. Test data, seeds and evaluation texts use invented references
and titles and authored text, never a real clause or control title.

## Consequences

Easier: the pattern is proved on one standard, and the licence questions are
asked once. Harder: a bank that follows several standards sees only one until
the editor enters the rest. To remember: no date may be seeded that does not
cite a Verification log row, and no real clause or control title may appear
anywhere in the repository.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The fixture instrument and its conformance obligation | Chunk 3, after the facts are logged |
| 2 | Further standards, by proposal | As the owner decides |
