# Query and request audit (2026-09-28) and the packages that act on it

Alex asked why a simple page costs so many API calls and queries. An audit measured every perf-harness row once, after a warm-up, on main at 077b5cd, in a test database seeded with `seed_e2e`. It logged each query together with the code that issued it.

Result: 6,450 queries over 284 routes. The median route runs 20 queries, the median read 13 and the median write 23. `backend/perf/baseline.json` is out of date for pasteUnits (28 now) and setApplicabilityMany (20 for units).

Alex approved every fix below on 2026-09-28, including the two that touch security mechanics (wave B).

## Findings

1. **Fixed cost on every request: 8 queries, 35% of all queries.** listLanguages costs 9, and only one of them is the route's own. The eight are:
   - open the transaction;
   - switch the identity-lookup flag on (`session_logic.py:272`);
   - read the session joined with its user;
   - switch the flag off;
   - set the tenant for row-level security (`tenancy.activate`);
   - read the membership's role permissions (`build_principal`);
   - read the latest passkey step-up, on every request even though only step-up routes use it;
   - close the transaction.

   Permission checks, rate limits, Server-Timing, CSP and the support guard cost no queries.
2. **Re-reading what sign-in already loaded: 434 queries, 6.7%.** `caller_tenant` re-reads the tenant on 164 routes. `caller_user` (120 routes) and `language_order` (112 routes) re-read the user.

   getMe runs 19 queries: it re-reads user, tenant, membership and step-up, reads platform roles in a bank session (always empty), and runs up to 8 separate counts.

   In all, 307 statements across 87 routes repeat identical SQL with identical parameters.
3. **Audit writes, through `record()`: 846 queries, 13%.** They break down as 193 audit rows, 386 savepoint statements and 45 zone reads. Twelve writes that record more than once do not use `batched()`.
4. **Per-row bulk writes.**
   - **decideProposalBatch: 350 queries, about 28 per row.** Per row it runs a search reindex that opens its own library door (about 14), an unbatched `record()` with a zone read (5), the batch-row save plus an existence check (2), a standards check (1) and a term insert (1).
   - **setApplicabilityMany: about 3 per obligation answer and 6 per legal-entity answer**, which is a new scope row with its own savepoint plus an UPDATE. An obligation without a register entry adds about 11, because `ensure_register_entry` runs before `batched()`. At `REGISTER_BULK_MAX=100` that comes to about 1,700 queries.
5. **Agent key and token calls: 19 routes, 42–58 queries per MCP call.** Key auth costs 9–20 queries, including a last-used update and a login-event insert on every call. MCP resolves the same key twice, and two middlewares each re-read the entry and its scope.
6. **Vocabulary label lookups: 217 queries in 86 routes.** getHome reads the urgency and term labels twice and repeats register reads.
7. **Screens.**
   - Every full page load chains `/auth/refresh`, then `GET /me` (SessionGate renders nothing until it answers), then the page. The account menu also fetches `/reference/languages`.
   - **Obligation page: 12–13 requests in three rounds.** The panels mount only after `GET /obligations/{id}` (`ObligationScreen.tsx:145`), although they need only the id from the URL, and the units then wait on `/register`.
   - **Admin > Agents: 9 + N + M requests.** Runs are fetched per agent, and each open research request is polled every 5 s.
   - **Inventory: 5 requests**, 4 of them filter lists loaded up front. Watch makes 4–5.
   - **Organisation: 4 + N**, with licences fetched per legal entity.
   - **Case: 1 + 5–6**, all waiting on the change.
   - **Today: 3.** `/home` is chained to `/briefings/current` (`TodayScreen.tsx:125`) even though the code's own comment says it never is.
   - **Security: 2, and One vocabulary: 3**, both chained for no reason.
   - Data counts as fresh for only 30 s, so vocabularies are re-fetched on every return. `/tenant/org-units`, `/tenant/products` and `/taxonomy/terms?dimension=regime` are each cached under two keys.

## Packages

### Wave A, in parallel

**perf-request-once** covers findings 1, 2, 5 and 6 plus `/auth/refresh`.
- Fold the flag-off and the tenant into one statement.
- Read the step-up inside the roles query, or only on routes that need it.
- Keep the tenant, user and locale on the request once sign-in has loaded them, and replace every re-read (`caller_tenant`, `caller_user`, `language_order`, getMe's) with them.
- Merge getMe's counts, and skip platform roles in a bank session.
- Memoise vocabulary labels per request. Never cache them per process, and never across tenants.
- Resolve an agent key once per request and reuse it across both middlewares and MCP, while still checking revocation on every request.
- Return the `/me` payload with `/auth/refresh` and update SessionGate to use it, removing a round trip.

It must keep forced RLS, the per-request session validity check, the membership and permission checks, and step-up where it is required. It owns `backend/apps/shared/` authentication, permissions and tenancy, `identity/session_logic`, the key auth, and the frontend SessionGate and session helpers.

**perf-bulk-set-based** covers finding 4.
- decideProposalBatch opens one library door and runs one reindex per batch, not per row, with bulk updates and `batched()`.
- setApplicabilityMany inserts the missing register entries and the new scopes in one statement each (skipping conflicts, then one locked re-read), and runs one UPDATE per (answer, reason), all inside `batched()`. Every answer still gets its own audit row through `record()`.

It owns `backend/apps/proposals/` batch logic and `backend/apps/register/` applicability logic. The change runs in the library-write path, so it needs a security review of its own diff.

**perf-frontend-requests** covers finding 7, except `/auth/refresh`, which perf-request-once owns.
- The obligation panels mount at once from the URL id. Fold the panels into `/register` where that is one query.
- Filter lists load when they are opened.
- `GET /agents` includes each agent's recent runs, and research requests are polled once.
- `/tenant/org-units` includes licences.
- `/home` carries the briefing count.
- Security and a vocabulary page drop their chains.
- One cache key per list, and vocabularies stay fresh for 5 minutes.

It owns `frontend/src/features/*` and `frontend/src/app/*` for those screens, plus the response additions in the backend routes named above.

### Wave B, after wave A is on main, in parallel

**perf-audit-writes** covers finding 3.
- `record()` takes a savepoint only when a write crosses zones.
- It inserts the audit row and the outbox row in one statement.
- The twelve writes that record more than once use `batched()`.

`record()` stays the only way to write these rows: same transaction, append-only triggers unchanged, one audit row per write, the outbox payload unchanged. An ADR records the change, with a security review, and the compliance and audit guard tests stay unchanged and green.

**perf-tenant-in-token** covers finding 1 taken further. The signed session token carries the tenant id, and one query reads session, roles and step-up, taking the fixed cost from 8 to 4.
- This changes the identity-lookup RLS clause and its guard. An ADR records it, along with the threat model of a token whose tenant claim no longer matches the stored session: it must be refused.
- Forced RLS on every tenant table and the `cw_app` role stay exactly as they are.
- Security review.

## Rules for every package

- Follow CLOUD_SESSION.md.
- Measure before and after with the perf harness (`backend/perf/harness.py`, `perf_report`) for the routes you touch, and count requests per screen for frontend work. Put the numbers in the commit body.
- Update the query-count pins (`assertNumQueries`, `*_QUERIES` constants) to the new, lower numbers.
- Update `backend/perf/baseline.json` only for routes you changed, and say why. Parallel packages will conflict there; the integrator regenerates it.
- Never raise a budget, a baseline or a pin to make a test pass. Never weaken a check to save a query.
- Every saved query must still leave each permission, RLS, session and step-up decision made on every request that needs it. A test must prove that a revoked session, a removed membership, a revoked key and another tenant's id are all still refused after the change.
