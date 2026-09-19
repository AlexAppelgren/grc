# Hardening follow-ups found in review

Findings from the security reviews of 2026-09-19 that did not block their own merge, because
each existed before that branch or belongs to a later task. Each gets built, not forgotten.
The main agent adds a row here whenever a review turns up such a finding.

| # | Finding | Found in | Severity | Where it gets fixed |
|---|---|---|---|---|
| H1 | `PageQuery.offset` has no upper bound: a huge offset makes the database raise, and every paginated route answers 500 | chunk4-T3 review | low | Task H-A below |
| H2 | `build_principal` (`apps/identity/session_logic.py`) trusts the permissions stored on a tenant role row without limiting them to `TENANT_PERMISSIONS`; seeds and the role editor refuse `proposals.review`, but a row written around them would carry it | chunk4-T11 | low, defence in depth | Task H-A below |
| H3 | Nothing stops a future writer from recording a tenant-derived title under a library subject with no tenant, which `GET /audit-events` would show every tenant | chunk4-T3 review | low, future risk | Task H-A below: a guard test listing every `record(tenant_id=None, ...)` with a library subject type and its actor type |
| H4 | `cw.maintenance` rests on review alone | chunk3-rest-T1 review | low | chunk3-rest-T1 (compliance rule, in progress) |
| H5 | Seeded library-list rows get no audit row, and every deploy undoes an approved reorder, retire or default change | chunk4-T2 and its review | medium | REGULATORY_SCOPE.md T01 (cloud, in progress) |
| H6 | Under the append-only trigger a machine translation cannot be confirmed in place (INV-05, INV-S6) | chunk3-rest-T1 review | low, design | TODO_FOR_alex with a default; built with the screens that confirm (chunk3-rest-T12/T14 or chunk 4) |
| H7 | Child tables of tenant-private library records (titles, versions, summaries, terms, tags) have no RLS of their own; every read must reach them through the parent | chunk3-rest-T4 | low, future risk | Chunk 7's search index must carry the owner and its own RLS; the chunk 7 plan names it |
| H8 | Approval's audit rows carry `steppedUp: false` because `apply.py` does not pass the step-up id | chunk4-T3 review | low | chunk4-T6 (already in its task text) |

## Task H-A: three small guards (after chunk3-rest-T3 merges, which owns `apps/shared/schemas.py`)

**Owned:** `backend/apps/shared/schemas.py` (the `PageQuery.offset` bound only),
`backend/config/settings.py` (one labelled setting), `backend/.env.example`,
`docs/runbooks/RAILWAY_VARIABLES.md`, `backend/apps/identity/session_logic.py` (the principal's
permissions only), `backend/apps/shared/tests_hardening.py` (new).

1. H1: bound `offset` with `le=settings.API_PAGE_OFFSET_MAX` (a setting with an env override;
   default 100000); a test that an offset above it answers 422 on a paginated route.
2. H2: the principal's permissions are the role rows' permissions intersected with
   `TENANT_PERMISSIONS` for a tenant session (and with the platform set for a platform
   session); a test that a role row carrying `proposals.review` does not give it.
3. H3: a guard test that walks every `record(` call in production code (AST), and fails when
   one passes `tenant_id=None` with a library subject type unless its actor is the system, an
   agent or a platform editor and its title is not tenant-derived; list today's calls in the
   test as the allowed set, so a new one must be looked at.

Gates: `apps.shared apps.identity apps.governance` tests, ruff, mypy, compliance lint,
requirements coverage. Security review before merge (authentication).
