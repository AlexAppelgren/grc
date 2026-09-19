# ADR 0005 — Brand layer: Green tokens with our own brand pair

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-05; the owner picks the replacement values before any real user enrols)

## Context

The prototype's green (`#003824`) and its brass pair (`#efe9dc`, `#685631`)
equal SEB's brand token values (`l2-brand-01`, `l3-brand-02`,
`content-brand-02`), verified 2026-09-19 against the token files. The Green
packages are Apache-2.0, which grants no trademark rights, and the product is
sold to other banks. `design/brand/README.md` lists WCAG-checked placeholders
and the phonetic wordmark `[blɛkː]`.

## Decision

Import the Green 2023 tokens through `scripts/build-tokens.mjs` into
`tokens.generated.css` (never edited) and override every `brand-01` and
`brand-02` variable in `styles/brand.css`, the one file that holds our own
values, starting with the placeholders in `design/brand/README.md`. Hanken
Grotesk for text and Noto Sans Mono for legal references and the wordmark,
self-hosted. The logo is the phonetic wordmark. Deliberately not done:
copying token values into components, or using SEB's typeface.

## Consequences

Easier: a rebrand or a white-label is a change to one file. Harder: every
`brand` variable must be overridden so no SEB value survives by accident; the
list comes from the Green MCP `get_tokens` tool, never from memory. To
remember: the placeholders ship until Alex chooses the final green and sand
and clears the use of Green with SEB (`docs/TODO_FOR_alex.md`).

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Token pipeline, `brand.css` with placeholders, contrast test | Phase 0 |
| 2 | Final values | Owner, before any real user enrols |
