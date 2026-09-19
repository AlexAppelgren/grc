# ADR 0023 — Translations as rows: the full consequences of D-12

**Date:** 2026-09-19 · **Status:** accepted by default (extends ADR 0012 / DECISIONS D-12; playbook 17)

## Context

ADR 0012 records the decision. This ADR records what it means for the
schema, the API, search and the UI, because the input files
(`docs/inputs/schema.sql`, `openapi.yaml`) were designed with language
columns and `INPUT_DELTAS.md` §3 replaces them. I18N-01 requires content in
`en`, `sv`, `da`, `nb`, `fi`; I18N-02 requires the UI in `en` and `sv` at R1.

## Decision

- A `language` table seeded with the five content languages; every
  translatable record has a translation table keyed by (record, language)
  holding the text, `is_original`, `machine_translated`, a review state and
  the reviewer.
- Vocabulary labels and usage notes are translation rows in the same shape.
- `search_chunk.lang` references the language table and its `tsv` uses the
  language's text search configuration (`swedish`, `danish`, `norwegian`,
  `finnish`, `english`).
- The API returns the requested language and falls back along the user's
  content language order; the original is always reachable.
- Machine translations are labelled in the UI until a person confirms them
  and are logged as `ai_generation` rows.
- UI copy is separate: message catalogs per UI language, checked by
  `messages-check.mjs`.

Deliberately not done: `summary_sv`-style columns, JSON translation blobs,
`lang IN (...)` checks, any branch on a language code.

## Consequences

Easier: adding a sixth content language is a row and a text search
configuration, not a migration of every table. Harder: reads join or
prefetch translations, so list endpoints pin their query counts. To
remember: the embedding model must cover all five languages (D-09) and the
evaluation set checks it per language.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Language table, translation base model, vocabulary labels | Chunk 2 |
| 2 | Library text and the per-language chunks | Chunks 3 and 7 |
| 3 | Remaining UI languages | Chunk 13 |
