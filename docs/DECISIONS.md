# Decisions and defaults

The build never waits on these. Each has a default the agent uses, the reason,
and what the owner should confirm. In Phase 0 each becomes an ADR with status
`accepted by default`. When the owner changes one, the ADR is superseded and
the PRD version bumps if behaviour changes.

| ID | Decision | Default the build uses | Why | Owner confirms |
|---|---|---|---|---|
| D-01 | Product or internal tool | Multi-tenant product: one shared library, many tenants | The two-zone model works unchanged with one tenant | Before the first external tenant |
| D-02 | WebAuthn RP ID | `WEBAUTHN_RP_ID` = the exact app host per environment. Proposed production host `compliance.bleqq.com` | A passkey belongs to one RP ID. The exact host keeps other bleqq.com sites from requesting these credentials. A later rebrand means re-enrolment, or keeping this host alive and serving `/.well-known/webauthn` for Related Origin Requests | **Before any real user enrols.** Test deploys use throwaway passkeys |
| D-03 | Auth library | `webauthn` (py_webauthn) with our own thin endpoints for invitation, code and passkeys | The rules are few, specific and product invariants (code works once, no fallback, admin recovery, tenant credential policy). A framework's generic flows would be overridden more than used. SSO in R3 is decided then | Nothing now |
| D-04 | UI foundation | Tailwind + Radix primitives + our own components that reproduce the prototype, on Green tokens. A Green Core component only after a Phase 0 spike proves it renders and hydrates under `next start` and matches the design | The prototype uses Green's token values but none of its components. Green's own agent instructions require its text and layout components everywhere, which would fight the prototype and Tailwind | After the spike |
| D-05 | Brand layer | Import Green 2023 tokens, override `brand-01` and `brand-02` in `brand.css` with our own green and sand. Hanken Grotesk and Noto Sans Mono. Logo is the phonetic wordmark `[blɛkː]` | The prototype's brand green and brass pair are SEB's brand tokens by value, and Apache-2.0 grants no trademark rights. The product is sold to other banks | **Pick the replacement values.** Until then `brand.css` ships the placeholders in `design/brand/README.md` |
| D-06 | Sessions | Access token in memory, rotating refresh in an HttpOnly cookie, `user_session` row for revocation. Defaults: idle 30 min, absolute 12 h, both tenant policy | Instant revocation plus the last repo's proven refresh design | The default limits |
| D-07 | LLM provider and inference region | Adapter with `mock`, `anthropic` and `bedrock` providers. Test environment uses `anthropic`. No tenant-zone text is sent to a model except the question typed into Ask, which a tenant can switch off | Anthropic's own API offers only US or global inference. EU-pinned inference needs Bedrock or Vertex | Before the first bank tenant: contract the EU path |
| D-08 | Agent runtime | `agent_runner` adapter with a mock. First real runner: Claude Managed Agents, one session per run, the app as scheduler. Fallback: the Agent SDK inside our worker. Fetch current docs before building either | Tenant-scoped runs cannot live under a personal account. Managed Agents is in beta, so the adapter keeps it swappable | After the R2 agent chunk |
| D-09 | Embedding model and reranker | `embedder` adapter, 1024 dimensions, mock in tests. Choose the real model against the evaluation set from candidates covering all five languages | The model must be chosen on evidence. pgvector's HNSW index limit for `vector` is 2,000 dimensions | **Supply a key for the first candidate** so search works on the test deploy |
| D-10 | Search scope | Library only in R1. Tenant content is not indexed | Keeps tenant text out of embeddings until D-07 is settled | At R2 |
| D-11 | Evidence delivery | Stream through permission-checked endpoints, no presigned download links | One permission check and one audit row per download | Nothing |
| D-12 | Translations | Rows keyed by language, original marked, machine translations labelled | Five languages do not fit in columns | Nothing |
| D-13 | Statuses | Tenant sub-statuses inside fixed categories, no workflow engine | Flexibility without moving the guards auditors rely on | Nothing |
| D-14 | Library curation | Platform role `library_editor` in the console. Tenants report problems and propose | The library is shared | Who the first editors are |
| D-15 | Branching | One branch, `main`, during the build. `staging` and `main` with a second reviewer before the first real tenant | Speed now, change control when it matters | When to switch |
| D-16 | Hosting | Railway EU West, container-only, nothing Railway-specific in code | The tenant zone may have to move into a bank's environment | Nothing now |
| D-17 | Django version | 5.2 LTS | Long support window | Nothing |
