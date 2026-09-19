# ADR 0012 — Translations are rows keyed by language

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-12; nothing for the owner to confirm). Restated with its full consequences in ADR 0023.

## Context

`docs/inputs/schema.sql` designed `summary_sv`/`summary_en`, `text_sv`/
`text_en` and `label_sv`/`label_en` columns with `lang IN ('sv','en')`
checks. Five content languages (I18N-01) do not fit in columns, and playbook
Section 17 forbids any column or branch that names a language.

## Decision

Translatable text lives in translation rows keyed by a language row, with
the original language marked and machine translations labelled with a
review state. Vocabulary labels follow the same shape. The API returns the
requested language, falling back along the user's language order.
Deliberately not done: JSON blobs of translations on the record, because
they cannot be indexed per language or reviewed per row.

## Consequences

See ADR 0023 for the full consequences and the search implications.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Language table, translation base model, vocabulary labels | Chunk 2 |
| 2 | Instrument, provision and obligation text | Chunk 3 |
