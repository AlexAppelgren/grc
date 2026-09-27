# Security review of agent access and the bank's own records

Package `security-review-c11-access-d89`, wave 7 of the R2 build, 2026-09-27. Requirements
ACC-01 to ACC-09, INV-07 and OWN-01 to OWN-04, read against CLAUDE.md section 5,
`docs/plans/briefs/AGENT_ACCESS.md`, `R2_CROSS_CUTTING.md`, ADR 0050 and ADR 0059, and the
D-1xx rows of the acc and d89 packages. `d89-controls` (OWN-05) carries its own review.

**Commit read:** `origin/main` (`7242ac8`) with the seven dependency branches merged:
`acc-summary-j11`, `acc-mcp-tools`, `acc-fe-personal-grants`, `d89-private-records`,
`d89-agent-research`, `d89-fe-scope-items` and `r2-j8-isolation`, and through them every
earlier ACC and D-89 package. The review read the diff `origin/main...HEAD` for the areas of
the acceptance line and the whole of each module on those paths: `apps/shared/authentication.py`
and `agent_access_guard.py`, `apps/identity/api_keys_logic.py` and `personal_tokens.py`,
`apps/agents/agent_access.py`, `what_applies*.py`, `out_of_scope.py`, `runner_events.py`,
`scope_research.py`, `apps/library/reading.py`, `apps/search/hybrid.py`,
`apps/register/agent_read.py` and `overlay.py`, `apps/governance/reach.py` and
`access_log.py`, `apps/integrations/mcp.py` and `mcp_tools.py`, `apps/proposals/logic.py`,
`apply.py`, `private_approval.py` and `tenant_agent.py`, `apps/taxonomy/footprint_logic.py`
and the scope item code, and the RLS migrations `proposals 0009` and `library 0012`.

**The merge itself.** The seven branches merged in text but not in behaviour, and the merge
commits and `851fdec` fix what the whole backend suite then showed red: two seed blocks made
the same tenant agent, six E2E seed blocks lost their end markers, d89-agent-research's tests
filed a bank's own obligation under a shared instrument (which d89-private-records refuses),
a support grant was loaded outside the one module allowed to, and a factory reached the agent
builders the way the fixture guard refuses. One merge slip is a finding of its own (M2).

The whole backend suite (3712 tests on the merge, then every touched app and `apps.shared`
again after each fix) is green; see the gates in the package report.

## Summary

One high and six medium findings, all fixed in this package, each with a test written first
that failed without the fix. The low findings are HARDENING rows H70 to H78.

| # | Severity | Finding | Status |
|---|---|---|---|
| H1 | high | Re-enrolment and re-invitation brought a person's personal tokens back to life | fixed |
| M1 | medium | An MCP tool ran as a session bearer sent beside the agent's key | fixed |
| M2 | medium | The scope statement ran in tests and in no deployment | fixed |
| M3 | medium | The overlay and the bank's tags reached an agent without `tenant:read` | fixed |
| M4 | medium | `/vocab` gave an agent the bank's own lists with tenant reach off | fixed |
| M5 | medium | A personal token read the source registry its person's session was refused | fixed |
| M6 | medium | A key held in another zone made an approval answer 500 | fixed (residual H77) |
| L1 | low | A lone surrogate in an MCP tool argument answered 500 | fixed |
| L2 to L8 | low | Access log parameter names, `ownRecordsLeftOut`, naive expiries, tokens in a second bank, a person's batch under an agent's run, the root tables' write rule, research after a scope item is removed | HARDENING H70 to H76 |

## Findings

### [HIGH] H1, credential death: a token outlived its person's removal and re-enrolment
- Where: `backend/apps/identity/api_keys_logic.py` `person_permissions`,
  `invitation_logic.reissue_enrolment`, `members_logic.deactivate_member`.
- Scenario: a member keeps a `cw_…` token on a laptop that is stolen; an administrator
  re-enrols them (ID-05), which ends every session and retires every passkey. The token was
  only refused while the user was deactivated, so it kept reading the library, and the
  register where its entry had reach, for up to 90 days; once the person enrolled again it
  was fully alive. A member removed and later invited again found every token they had minted
  working, and the security log never showed one end.
- Breaks: AGENT_ACCESS.md section 8 (a token dies with the person), ACC-03, ID-05.
- Fix: removal and re-enrolment revoke every live token the person holds in the bank, each
  with its `token_revoked` security log row, and the audit row counts them (`tokensRevoked`);
  a person who is not active (awaiting enrolment again) holds no token in any bank. Test:
  `apps/identity/tests_access_own_review.py`.
- Left: a token the same person minted in a second bank revives once they enrol again (H73).

### [MEDIUM] M1, MCP: the inner request could authenticate someone other than the credential
- Where: `backend/apps/integrations/mcp_tools.py` `_request`.
- Scenario: `POST /mcp` with `X-API-Key: <trading entry key>` and
  `Authorization: Bearer <a person's session>`. `/mcp` authenticates the key, spends its rate
  and opens its access log row; the tool's inner `GET /obligations/{key}` copied every header,
  and its `SessionAuth` came first, so the route answered the person: no entry narrowing (the
  card duty came back), no support-session allow-list (the inner request runs no middleware),
  and the bank's log recorded the entry for a read it did not make.
- Breaks: ACC-05 (same authentication, no read path of its own), ACC-08 (the log).
- Fix: the inner request carries the MCP request's key as `X-API-Key` and no
  `Authorization` header or cookie. Test: `apps/integrations/tests_access_own_review.py`.

### [MEDIUM] M2, ACC-07: the scope statement was lost from production when the wave merged
- Where: `backend/config/settings.py` `MIDDLEWARE`; `config/test_settings.py` keeps a list
  of its own.
- Scenario: resolving the r2-j8-isolation merge dropped
  `agent_access_guard.ScopeStatementMiddleware` from the production list while the test list
  kept it, so every test passed and no deployment sent `Agent-Access-Scope`: a narrowed
  answer read the same as a full one. Found by the credentials review, caused by this
  package's own merge.
- Breaks: ACC-07, AC-ACC1 (every answer states its scope).
- Fix: restored, and `apps/shared/tests_access_own_review.py` fails when a middleware the
  tests run is missing from the production list or out of its order.

### [MEDIUM] M3, reach gate: the bank's layer reached a credential without `tenant:read`
- Where: `backend/apps/register/overlay.py` `shown_to`, read by `library/reading.py`.
- Scenario: an entry key or token holding only `library:read`, with tenant reach on for the
  bank and the entry, read applicability, compliance status, owner, team and the bank's tags
  on every obligation row and card (and through the MCP tools), and could filter by them;
  the same credential got 403 from `/register-entries`. A person without `register.read`
  could mint such a token and read the register's summary through the library.
- Breaks: AGENT_ACCESS.md section 5 (with tenant reach on **and** `tenant:read`), ACC-04,
  ACC-08, D-76.
- Fix: `shown_to` needs `tenant:read` as well as reach; the layer's filters answer 403
  `tenant_reach_off`, whose detail names both causes; the operation's description says so.
  `tests_agent_access_reads.py` had asserted the overlay for a library-only key; its keys now
  hold both scopes, and `apps/library/tests_access_own_review.py` proves the library-only case.

### [MEDIUM] M4, reach gate: the bank's own lists under `/vocab`
- Where: `backend/apps/taxonomy/api.py` `listVocabularyRows`, `getVocabularyRow`.
- Scenario: with reach off, an agent access credential holding `library:read` read
  `/vocab/tenant_tag` (the bank's tags with their usage counts), `/vocab/team` (teams and
  their addresses) and the bank's reasons and sub-statuses, which the inventory withholds.
- Breaks: ACC-04, ACC-08 (reach off means the library alone), D-76.
- Fix: a bank's own list answers an agent access credential only through the register's gate
  (`taxonomy/http.py` `refuse_own_list_beyond_reach`), else 403 `tenant_reach_off`; library
  lists, a person's session and a bank's integration key are unchanged. Test:
  `apps/library/tests_access_own_review.py`.

### [MEDIUM] M5, token scope: the source registry
- Where: `backend/apps/watch/api.py` `require_watch_reader`.
- Scenario: a custom role with `library.read` and no `watch.read`; its member mints a
  `library:read` token and reads `GET /sources` and `/sources/coverage`, which their own
  session is refused. The registry is not among an agent access credential's reads at all
  (AGENT_ACCESS.md section 5), and it would carry a bank's own sources once WAT-06 lands.
- Breaks: ACC-03 (a token never reads more than its person), ACC-04.
- Fix: an agent access credential answers 403 `permission_denied` on both routes; the
  platform's own agent keys, a person with `watch.read` and the console are unchanged.

### [MEDIUM] M6, two zones: a key held in another zone answered 500
- Where: `backend/apps/proposals/apply.py` `_new_instrument`, `_new_obligation`;
  `library/reading.py` `stable_key_taken` reads under row-level security.
- Scenario: bank A approves its own obligation `eu-2026-123-art-5`; later the shared record
  for the same regulation is proposed with that key. The check that the key is free saw only
  the console's zone, and the approval failed on the global unique index as an unhandled
  error (500), as did a second bank's own approval of a key the first held.
- Breaks: INV-07, D-57 (a bank's record reaches the console in no form), validation at a
  boundary.
- Fix: the create runs in a savepoint and a stable-key violation answers the same 409
  `duplicate_key` a visible key answers, naming no owner, with nothing written. Test:
  `apps/proposals/tests_access_own_review.py`.
- Left: the key stays taken, and the 409 says some zone holds it. A namespace for a bank's own
  keys is a design choice put to Alex (H77, `docs/TODO_FOR_alex.md`).

### [LOW] L1, MCP parsing: a lone surrogate
`json.loads` accepts `"\ud800"`, which UTF-8 cannot encode, so `get_obligation` and
`list_obligations` answered 500. `_scalar` now refuses it as the tool error a model can
correct. Fixed with M1's test module.

### [LOW] L2 to L8
HARDENING H70 to H76: the access log keeps any parameter's name and a key-like value of an
undeclared one; `ownRecordsLeftOut` counts every private record; a naive `expiresAt` answers
500; re-enrolment leaves a token in a second bank; a person may file a batch under an agent's
keyless run; the two root library tables keep their read rule for writes; research goes on
after a scope item is removed. H78 records that the runner-event channel has no caller yet.

## What was checked and found sound

- **Credential resolution.** Prefix lookup, SHA-256 compared with `compare_digest`, revoked
  and expired keys, the entry's `active` read on every request, and revoking an entry revoking
  every key and token under it in one transaction. The database's checks on `api_key` (a token
  has a tenant, a person and an expiry and no agent; an entry credential holds only
  `AGENT_ACCESS_SCOPES`). A token's permissions are re-read per request, never by a sweep.
- **Read-only guard over every route.** Every key-accepting route maps to its operation by the
  resolved template, never the raw path; a write answers 403 `read_only_credential` and an
  unmatched route fails closed; only `POST /search`, `POST /agent-access/what-applies` and
  `POST /mcp` are read-POSTs; a token never opens a session and every step-up route answers 403
  `step_up_required`, inside a route body too.
- **404 parity.** Every addressed library read (by id or stable key, `asOf`, diff, sources,
  instrument, provisions) answers a record outside the footprint or the entry's scope, a bank's
  own, another bank's and a missing one with the same 404 body; related, citing and lineage rows
  are joined through the confined querysets; counts are taken after the scope.
- **Reach gate.** `/register-entries` checks both halves of reach and `tenant:read` on every
  call and answers D-76's fields alone; nothing under a standard reaches an agent; gaps, cases,
  comments, evidence and the audit trail have no agent path. `tools/list` offers the register
  tool on the entry's toggle, and the call still checks both halves.
- **Access log.** One row per MCP request, written in its own transaction; `q`, `description`
  and the tool's text arguments are kept by name only (H70 is the residue).
- **MCP parsing.** Invalid UTF-8, malformed JSON and deep nesting are -32700; batches,
  non-object bodies, odd ids and a missing `jsonrpc` are -32600; only declared arguments,
  escaped into the query, and a path argument must resolve back to the tool's own route; the
  2026-07-28 headers must match the body; errors carry fixed sentences.
- **Rate limit.** Per credential id before any work, once per `/mcp` request, a setting with an
  env override, refused boot deployed with it off.
- **Proposal ownership and RLS.** `owner_tenant_id` comes from the database's own tenant
  setting, never a body; `proposal` is under the split mixed policy, so the console and another
  bank read no bank's own proposal; the bank's queue needs `private_records.approve`, a person's
  session and a step-up, `proposal_four_eyes` still holds and an agent is refused.
- **Child policies.** All fourteen children of `instrument` and `obligation` carry
  `parent_visible` and `parent_owned`, joined to the root owner with `IS NOT DISTINCT FROM`.
- **Apply zone crossing.** A bank's own proposal is only a new instrument or obligation, its
  obligation sits under its own instrument, provisions under it are refused, and every other
  kind reaches shared records only; a bank's own record is never indexed.
- **The tenant-run channel.** The run opens with no key and `refuse_tenant_key` is unchanged;
  a finding naming a shared record, the scope or a re-tag is refused and stores nothing; the
  owner comes from the run; duplicates by reference or key answer `already_in_our_library`; a
  replayed event returns the same proposal under the run's lock; findings pass the injection
  screen; the model input is D-98's named fields, never the description.
- **The wrapper refusal.** `ai.generate` refuses a subject that is a bank's own record before
  any model is asked and writes no row (`refuse_private`); `ai.stream` is Ask's alone and is
  given search chunks, which never hold a bank's own record; the what-applies summary is given
  shared, non-standard titles only.
- **Scope items.** Asked under `footprint.request`, approved by a different person under
  `footprint.approve` with a passkey (the `footprint_change_request_four_eyes` constraint), no
  key or agent route writes one, and the item's rows are under forced RLS.
