# ADR 0007 — LLM provider adapter and the inference region

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-07; the owner contracts an EU-pinned path before the first bank tenant); amended by ADR 0057 (D-72, D-76): **we** send no tenant-zone text to a model except Ask's question, and a bank pulling its own register decisions into its own agent through agent access, after two of its own people switched tenant reach on, is the bank's act and not ours

## Context

Tenant content is a bank's confidential material and may only go to a model
endpoint the tenant's contract allows (playbook 4.7). Anthropic's API
`inference_geo` parameter was verified in Anthropic docs on 2026-09-19; the
accepted values (`us`, `global`) and the point that Managed Agents sit outside
zero data retention come from secondary sources and must be re-checked before
D-07 is contracted. EU-pinned inference needs Bedrock (including Stockholm) or
Vertex.

## Decision

One `llm` adapter in `apps/shared/adapters/llm.py` with providers `mock`,
`anthropic` and `bedrock`, chosen by `LLM_PROVIDER`. The test environment uses
`anthropic`. Until an EU-pinned path is contracted, no tenant-zone text is
sent to any model, with one exception a tenant can switch off: the question
typed into Ask. Library text (public facts) may be sent. Deliberately not
done: sending register rows, notes, comments or evidence to a model under any
provider, and any provider call outside the adapter.

## Consequences

Easier: the provider is a setting, and the data-flow story for a vendor
review is one sentence. Harder: the So what draft and classification work on
library text only until D-07 is contracted; Ask carries a tenant off switch
(SRC-S6, AGT-S6). To remember: production refuses `mock`; every call writes
`ai_generation`; fetch current provider docs before building a provider.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Adapter interface and mock | Phase 0 |
| 2 | `anthropic` provider for the test deploy | Chunk 5 |
| 3 | `bedrock` provider once the EU path is contracted | Before the first bank tenant |
