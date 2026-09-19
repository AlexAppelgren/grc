# Verification log

Claims about the outside world that the design rests on. Re-check on each PRD
bump. Add a row whenever the build relies on something external.

| Claim | Status | Source | Checked |
|---|---|---|---|
| `@sebgroup/green-core` 3.23.0 and `@sebgroup/green-tokens` 3.1.8 are Apache-2.0. Tokens ship as CSS under `2023/css/` with light and dark both scoped to `:root` | Verified | npm package contents | 2026-09-19 |
| Green Core ships an MCP server (`green-core-mcp`) that needs `@modelcontextprotocol/sdk` installed beside it. Tools: `search_components`, `get_component_docs`, `list_guides`, `get_guide`, `get_instructions`, `get_tokens` | Verified by running it | npm package | 2026-09-19 |
| `gds-badge` variants: information, notice, positive, warning, negative, disabled. `information` is grey and `notice` is blue. No brand variant | Verified | Package type definitions and token values | 2026-09-19 |
| The prototype's colours equal Green token values (brand `#003824` = `l2-brand-01`, brass = `l3-brand-02` on `content-brand-02`) | Verified | Token files against the prototype | 2026-09-19 |
| Green components under Next.js server rendering | **Not verified** | Spike in Phase 0 (D-04) | |
| Playwright 1.61 (15 June 2026) adds `browserContext.credentials`, a virtual WebAuthn authenticator that can seed known keys, in all browsers | Verified | Playwright release notes | 2026-09-19 |
| A passkey belongs to one RP ID. Related Origin Requests: Chrome and Edge 128, Safari 18, Firefox 152 (May 2026) | Verified | Chrome for Developers, web.dev, vendor write-ups | 2026-09-19 |
| NIST SP 800-63-4 (July 2025): synced passkeys meet AAL2, device-bound needed for AAL3. AAL2 re-authentication guidance of 12 h and 30 min idle | Secondary sources only | Verify against NIST before quoting to a customer | 2026-09-19 |
| PostgreSQL: superusers and `BYPASSRLS` roles always bypass row security, table owners do unless `FORCE ROW LEVEL SECURITY` | Verified | PostgreSQL documentation, Row Security Policies | 2026-09-19 |
| pgvector HNSW indexes `vector` up to 2,000 dimensions | Verified earlier | pgvector documentation | 2026-09-18 |
| Anthropic's API `inference_geo` accepts only `us` and `global`. EU-pinned inference through Bedrock (including Stockholm) or Vertex. Managed Agents sit outside zero data retention | Parameter verified in Anthropic docs. Values and the ZDR point from secondary sources | Re-check before D-07 is contracted | 2026-09-19 |
| Claude Managed Agents: API-owned sessions, budgets, webhooks, vaults, beta header | From the Compliance Data chat | **Fetch current docs before building D-08** | 2026-09-18 |
| DORA Article 30: locations of services and data with notice of change, audit rights and exit for critical or important functions. Certifications support but do not replace audit rights | Secondary sources | Read the regulation text before drafting contracts | 2026-09-19 |
| Latest on PyPI: `webauthn` 3.0.0, `django-ninja` 1.7.0, `pgvector` 0.5.0. Django 5.2 is the LTS line | Verified | PyPI | 2026-09-19 |
| Railway: EU West region, Postgres templates with pgvector, private S3-compatible buckets | From the Compliance Watch chat | Verify in the Railway console when creating the project | 2026-09-18 |
| Embedding candidates covering sv, da, nb, fi, en at 1024 dimensions | **Not verified** | Decide against the evaluation set (D-09) | |
| Playwright 1.63.0: `browserContext.credentials` is the virtual WebAuthn authenticator (property added in 1.61); `storageState({credentials})` and `setStorageState` restore it, so a seeded passkey survives a saved state | Verified | playwright.dev, BrowserContext documentation | 2026-09-19 |
| Django 5.2.17 is the newest patch of the 5.2 LTS line. Django 6.1.1 exists; D-17 pins 5.2 (ADR 0017) | Verified | PyPI | 2026-09-19 |
| django-ninja 1.7.0, webauthn 3.0.0 and pgvector 0.5.0 are the newest releases | Verified | PyPI | 2026-09-19 |
| Next 16.3.5 and @playwright/test 1.63.0 are the newest releases | Verified | npm | 2026-09-19 |
| TypeScript 7.0.2 ships the native `tsc` and no JavaScript API; the announcement's side-by-side arrangement (`typescript` name resolving to `@typescript/typescript6` 6.0.3 for tools, `@typescript/native` carrying 7.0.2 for the CLI) runs lint (typescript-eslint 8.70.0), typecheck, Vitest, `next build` and openapi-typescript 7.13.0 green | Verified (ADR 0025) | TypeScript 7.0 announcement, devblogs.microsoft.com; the frontend gates | 2026-09-19 |
| Green Core 3.23.0 `GdsButton` renders on the server and hydrates under Next 16 `next start` with only `'use client'` on the rendering component; no dynamic import, manual registration or CSS import needed | Verified by the D-04 spike (`frontend/tests/e2e/green-spike.spec.ts`, ADR 0004) | Production build, Chromium | 2026-09-19 |
| Playwright 1.63.0 typings: the virtual authenticator is `browserContext.credentials`; helper names in `frontend/tests/e2e/support/passkeys.ts` were written against the installed `@playwright/test` type definitions | Verified | `node_modules/@playwright/test` typings | 2026-09-19 |
| Django 6.1.1 passes the whole backend checklist unchanged: 297 tests (168 skipped stubs), coverage floors, ruff, mypy with django-stubs 6.1.1, compliance, requirements, contract and search gates; django-ninja 1.7.0, django-cors-headers 4.9.0 and dj-database-url 3.1.2 declare Django 6 in their classifiers | Verified (ADR 0025) | PyPI classifiers; the backend checklist | 2026-09-19 |
| `python:3.12-alpine` and `node:22-alpine` scan clean at MEDIUM and above once Poetry, pip and npm are removed from the runtime layers; `python:3.12-slim` (Debian 13.7) carried 91 MEDIUM and HIGH OS findings with no upstream fix | Verified with Trivy locally | aquasec/trivy image scans | 2026-09-19 |
