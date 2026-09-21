# search — Search and ask

> **App spec.** Source: `PRD.md` Module SRC (SRC-01–SRC-05, AC-SRC1–AC-SRC2), journey
> J-7, playbook 10 (budgets), 16, 17, D-07, D-09, D-10.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

A question should take a minute. Search is hybrid: exact identifiers such as
"FFFS 2017:2" are won by keyword, concepts such as "nudging in onboarding" by
vector, fused by reciprocal rank and reranked, per language with the matching
Postgres text search configuration. Filters come from the vocabularies, an
"as of" date picks the version in force, and every hit says how it matched.

Ask answers only from retrieved chunks, cites every statement, flags pending
changes and returns "no answer" instead of guessing. A labelled evaluation
set gates releases: a drop in retrieval or classification quality beyond the
recorded tolerance fails CI.

Nothing a tenant writes under a standard reaches an index or a model: units,
scope notes, gaps, assessments, interpretations and links under a
standard-level instrument are kept out of search chunks, embedding inputs and
AI-generation inputs, and a guard test written per row proves it before D-10 is
relaxed at R2. Ask returns "no answer" about a standard's clauses and controls,
because the library holds none of them.

Deliberately simplified for R1: the library only is indexed (D-10), tenant
content is not; the embedder is a mock in tests and the real model is chosen
against the evaluation set (D-09). The only tenant-zone text sent to a model
is the question typed into Ask, which a tenant can switch off (D-07). Saved
searches wait for R3.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| SRC-01 | Hybrid search: exact identifiers by keyword, concepts by vector, fused by rank, reranked, per language | M | R1 | built |
| SRC-02 | Filters from vocabularies, an "as of" date, and the match kind on every hit | M | R1 | built |
| SRC-03 | Cited answers grounded only in the inventory, pending changes flagged, "no answer" instead of a guess | M | R1 | pending |
| SRC-04 | Saved searches with notification, and "what changed since my last visit" | S | R3 | pending |
| SRC-05 | An evaluation set that gates releases | M | R1 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-SRC1** "FFFS 2017:2" is won by keyword and "nudging in onboarding" by
  concept, in one query.
- **AC-SRC2** Every statement in an answer carries a citation, and a question
  with no support returns "no answer".
- **Budgets (playbook 10):** hybrid search under 800 ms without the reranker,
  under 1.5 s with it; Ask first token under 2 s, streamed; measured through
  `Server-Timing`, warm, on the evaluation corpus. Rate limited.
- **Mechanics:** one SQL statement over one chunk table, filtered by validity
  before ranking, 1024-dimension vectors under an HNSW index; chunks copy
  validity dates so "as of" filters without a join; every Ask call writes an
  `ai_generation` row.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/search.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### SRC-S1 — An identifier is won by keyword and a concept by vector in one query `@integration` `@e2e` (SRC-01, AC-SRC1)
```gherkin
Given the evaluation corpus is indexed with the mock embedder
When a user searches "FFFS 2017:2"
Then the first hit is that instrument with match kind "keyword"
When they search "nudging in onboarding"
Then the top hits are the conduct obligations with match kind "concept"
And both came from one fused query with the reranker applied over the top 50
```

### SRC-S2 — Chunks are indexed per language with the matching text search configuration `@integration` (SRC-01)
```gherkin
Given a sv chunk and a fi chunk of the same obligation
Then each chunk's tsvector uses its language's configuration (swedish, finnish)
When a user searches in Swedish
Then the sv chunk ranks above the fi chunk for the same term
```

### SRC-S3 — Filters come from vocabularies, "as of" picks the version, and each hit states its match kind `@integration` `@e2e` (SRC-02)
```gherkin
Given search results across jurisdictions and duty types
When a user filters by jurisdiction "SE" and duty type "reporting" and sets "As of" to 2026-06-30
Then only chunks valid on that date and carrying those keys are returned
And each hit shows an information pill with its match kind
And the filter values are keys, so a renamed label changes nothing
```

### SRC-S4 — An answer cites every statement and flags pending changes `@integration` `@e2e` (SRC-03, AC-SRC2)
```gherkin
Given a question the inventory can answer
When a user asks it
Then every statement in the streamed answer carries a citation to a chunk
And a cited obligation with an open change shows "Change pending: in force 1 Oct" as a warning pill
And an ai_generation row records purpose, model, version, input reference, output and citations
```

### SRC-S5 — A question without support returns "no answer" `@integration` `@e2e` (SRC-03, AC-SRC2)
```gherkin
Given a question about a topic the inventory does not cover
When a user asks it
Then the response carries noAnswer true and no invented statement
And the screen says the inventory has nothing on it and offers a plain search
```

### SRC-S6 — The Ask question is the only tenant text sent to a model, and a tenant can switch it off `@integration` (SRC-03)
```gherkin
Given the LLM adapter records every prompt
When a user asks a question
Then the prompt holds the question and library chunks only, never a register row, note or comment
When the tenant switches Ask off
Then the Ask route answers 403 with code "feature_off" and no model call is made
```

### SRC-S7 — Saved searches notify and show what changed since the last visit `@integration` `@e2e` (SRC-04)
```gherkin
Given a user saved the search "custody" with notifications on
When a new obligation matching it is applied to the library
Then the user is notified in their language
When they open the saved search
Then the new hit is marked "New since your last visit"
```

### SRC-S8 — The evaluation set gates releases `@integration` (SRC-05)
```gherkin
Given the labelled question set and the classification set with recorded scores and tolerances
When search_eval.py runs
Then it reports retrieval recall and classification accuracy per language
And it exits non-zero when any score drops beyond its tolerance
```

### SRC-S9 — Search and Ask stay within their budgets and are rate limited `@integration` (SRC-01, NFR-02)
```gherkin
Given the evaluation corpus and a warm cache
When hybrid search runs without the reranker
Then Server-Timing reports under 800 ms, and under 1.5 s with it
When Ask runs
Then the first streamed chunk arrives under 2 s
When a user exceeds the search rate limit (a setting)
Then the request answers 429
```

### SRC-S10 — J-7: search by identifier and by concept, then Ask with citations and "as of" `@e2e` (SRC-01, SRC-02, SRC-03, AC-SRC1, AC-SRC2, J-7)
```gherkin
Given the seeded reader
When they search "FFFS 2017:2", then "nudging in onboarding", then ask a question with "As of" set
Then the identifier hit is first, the concept hits are relevant, and the answer shows citations that open the cited obligation
```

### SRC-S11 — Only the library is indexed in R1 `@integration` (SRC-01)
```gherkin
Given a tenant assessment note containing a distinctive phrase
When the phrase is searched
Then no chunk contains it and no embedding was requested for it
```

### SRC-S12 — A question about a standard's control gets "no answer" `@integration` (SRC-03, SRC-05, INV-08, AC-INV2)
```gherkin
Given the library holds a standard's edition with its conformance obligation and no clause text
When a user asks what one of that standard's controls requires
Then the answer is "no answer" and states nothing about the control
And the evaluation set holds this question expecting no answer, and it gates the release
```

### SRC-S13 — Nothing a tenant writes under a standard reaches the index or a model `@integration` (REG-08, SRC-01, AC-REG2)
```gherkin
Given tenant A has the invented units "X.1" and "X.2" with its own titles for Example Bank AB under a standard
And a status note, a gap, an assessment, an interpretation and an internal link on that conformance obligation
When the index is rebuilt and a user of tenant A asks a question
Then no search chunk, embedding input or AI-generation input contains text from any of those rows
And a user of tenant B searching those titles finds nothing and receives 404 for the rows
```
