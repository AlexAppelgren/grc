# Variables

Every variable the backend and the web app read, and where each lives.
`backend/config/settings.py` reads them; `.env.example` lists them all with
a comment and no real value. Secrets live only in Railway variables and
GitHub encrypted secrets. Dev-only secrets are literal strings ending in
`-dev-only` or starting `django-insecure-`, allowlisted by exact literal in
`.gitleaks.toml`.

## Environment detection

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `ENVIRONMENT` | api, worker, beat | `local` | `ci` | `test` | `local`, `test` and `ci` are the only names that are not "deployed". Anything else (including `prod`, `Production`, `demo`, `dev`, or unset) fails closed with every guard on. `test` is the one deployed name where mock adapters are allowed and the UI shows a banner |
| `RAILWAY_ENVIRONMENT_NAME` | all | unset | unset | set by Railway | Presence alone means deployed, whatever `ENVIRONMENT` says |
| `DEBUG` | api | `true` | `false` | `false` | Refused when deployed |
| `SECRET_KEY` | api, worker, beat | `django-insecure-dev-only` | a generated value | Railway secret | A missing or default value is refused outside DEBUG |

## Database and cache

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `DATABASE_URL` | api, worker, beat | `postgres://cw_app:cw-app-dev-only@localhost:5432/compliance_watch` | the `cw_app` string against the service container | the `cw_app` connection string | The app refuses to boot if this role is a superuser, owns the tables or has `BYPASSRLS` (ADR 0022) |
| `MIGRATOR_DATABASE_URL` | api (entrypoint), CI | `postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/compliance_watch` | the `cw_migrator` string | the `cw_migrator` connection string | Used only by `migrate`, `migrate_from_zero` and the test runner's database creation |
| `REDIS_URL` | api, worker, beat | `redis://localhost:6379/0` | the service container | Railway Redis URL | Celery broker and cache |

## Hosts and identity

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `ALLOWED_HOSTS` | api | `localhost,127.0.0.1` | `localhost` | the api host | Explicit, never `*` |
| `CORS_ALLOWED_ORIGINS` | api | `http://localhost:3000` | `http://localhost:3000` | `https://<web host>` | Scoped to `/api/` |
| `PRODUCT_NAME` | api, web | `Compliance Watch` | same | `bleqq compliance` | The display name; a rebrand is a variable |
| `WEBAUTHN_RP_ID` | api | `localhost` | `localhost` | the exact test host (`DNS_DOMAINS.md`) | A passkey belongs to one RP ID (D-02, ADR 0002). Required when deployed |
| `WEBAUTHN_ORIGINS` | api | `http://localhost:3000` | `http://localhost:3000` | `https://<test host>` | Comma-separated allowed origins for the ceremonies |

## Storage, mail, models, agents

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `STORAGE_BACKEND` | api, worker | `local` | `local` | `s3` | `local` is refused when deployed |
| `STORAGE_*` (`STORAGE_ENDPOINT`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_REGION`) | api, worker | unset | unset | the private bucket's values | Only read when `STORAGE_BACKEND=s3` |
| `MAIL_PROVIDER` | api, worker | `mock` | `mock` | `smtp` | A mock mailer is refused when deployed except in `test` |
| `MAIL_*` (`MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`) | api, worker | unset | unset | the EU transactional sender | SPF and DKIM on the sending domain |
| `LLM_PROVIDER` | api, worker | `mock` | `mock` | `anthropic` | `mock`, `anthropic`, `bedrock` (D-07, ADR 0007) |
| `ANTHROPIC_API_KEY` | api, worker | unset | unset | Railway secret | Only read when `LLM_PROVIDER=anthropic` |
| `LLM_MODEL` | api, worker | `claude-opus-5` | `claude-opus-5` | `claude-opus-5` | The Messages API model id (E3) |
| `LLM_MAX_TOKENS` | api, worker | `4096` | `4096` | `4096` | A ceiling: a caller asking for more gets this |
| `LLM_TIMEOUT_S` | api, worker | `60.0` | `60.0` | `60.0` | Per socket operation (the connect, then each read of the stream), not per call; also the longest a `retry-after` may hold a request |
| `LLM_MAX_RETRIES` | api, worker | `2` | `2` | `2` | Retried on 408, 409, 429, 5xx and connection failures only, and only before the answer starts |
| `LLM_RETRY_BACKOFF_S` | api, worker | `0.5` | `0.5` | `0.5` | Doubled per attempt unless `retry-after` says otherwise |
| `LLM_DEADLINE_S` | api, worker | `180.0` | `180.0` | `180.0` | The whole call, retries and their waits included; a call ends within this plus one `LLM_TIMEOUT_S` |
| `LLM_MAX_RESPONSE_BYTES` | api, worker | `4194304` | `4194304` | `4194304` | A streamed answer larger than this is refused; raise it with `LLM_MAX_TOKENS` |
| `LLM_MAX_ERROR_BODY_BYTES` | api, worker | `65536` | `65536` | `65536` | An error body is read only this far, for its error type |
| `AI_GENERATION_OUTPUT_MAX_CHARS` | api, worker | `20000` | `20000` | `20000` | How much of a model's answer the AI output log keeps (AUD-02). Model output is text off a network, so the cap is at the boundary; a longer answer is stored up to this length |
| `AI_GENERATION_CITATIONS_MAX` | api, worker | `20` | `20` | `20` | The most citations an agent may report with one drafted "So what?" on `POST /changes` or `PATCH /changes/{changeId}`; over it is a 422 naming the field |
| `EMBEDDER_PROVIDER` | api, worker | `mock` | `mock` | per D-09 | Plus the provider's key variable once D-09 is decided; until then the test deploy searches by keyword only. Switching it on embeds the corpus by itself, but not at once: the sweep below picks the backlog up on its next tick, a batch at a time, and until it has caught up those chunks answer by keyword only. It does **not** rebuild the chunks — text or chunking that changed while no model was contracted still needs `manage.py reindex_library` |
| `SEARCH_EMBED_BATCH_SIZE` | worker | `64` | `64` | `64` | How many chunks one embedding call carries, and the most one outbox delivery embeds before leaving the rest to the sweep (SRC-01) |
| `SEARCH_EMBED_SWEEP_INTERVAL_S` | worker | `60` | `60` | `60` | How often the sweep drains the embeddings the index still owes: the rest of a full rebuild, a rebuild whose outbox row spent its attempts, and the corpus of a deployment that ran with no model contracted |
| `RERANKER_PROVIDER` | api, worker | `mock` | `mock` | `none` until D-09 names one | `mock` is refused when deployed except in `test`; `none` leaves the fused order as the answer |
| `RERANKER_TOP_K` | api, worker | `50` | `50` | `50` | How many fused hits the reranker is given (SRC-01) |
| `SEARCH_RRF_K` | api | `60` | `60` | `60` | The reciprocal rank fusion constant: each leg adds `1/(k + rank)`, so the gap between ranks 1 and 2 is worth more than the whole tail (SRC-01) |
| `SEARCH_RETRIEVAL_DEPTH` | api | `50` | `50` | `50` | How deep each leg reaches. A row ranked below this by a leg was not found by it, so it neither scores nor claims that match kind (SRC-01) |
| `SEARCH_CONCEPT_SCORE_FLOOR` | api | `0.5` | `0.5` | `0.5` | The least cosine similarity that counts as a concept match. The vector leg always has a nearest neighbour, so without a floor every query would call every embedded chunk a concept hit. Re-tune it with the model D-09 chooses (SRC-01) |
| `SEARCH_SNIPPET_CHARS` | api | `240` | `240` | `240` | The most of a hit's text a snippet shows, cut around what matched (SRC-02) |
| `SEARCH_RATE_PER_USER_PER_MINUTE` | api | `60` | `60` | `60` | What one caller may spend on `POST /search` and `POST /search/similar` in a minute: a person's session or an agent's key, each with a window of its own, 429 `rate_limited` over it. Below 1 the app refuses to boot, because there is no value of it that means "no limit" (NFR-02) |
| `ASK_RATE_PER_USER_PER_MINUTE` | api | `10` | `10` | `10` | The same for `POST /ask`, tighter because every call that passes it is a model call the bank pays for. Below 1 the app refuses to boot (NFR-02, D-07) |
| `ASK_STREAMS_PER_USER` | api | `2` | `2` | `2` | How many Ask answers one caller may have streaming at once. Each open stream holds a server thread until the model finishes (up to `LLM_DEADLINE_S`), so without it a few callers could hold every thread for every bank; one past it answers 429 `rate_limited` before any byte. Below 1 the app refuses to boot (NFR-02, H47) |
| `PROBLEM_REPORTS_PER_USER_PER_HOUR` | api | `30` | `30` | `30` | How many problem reports one person may file in an hour, and separately how many they may close; over it is 429 `rate_limited`. Each is a row and an audit row kept for ten years. Below 1 the app refuses to boot (AUD-03, ACC-09, H39) |
| `VISIT_MIN_INTERVAL_SECONDS` | api | `60` | `60` | `60` | A `POST /me/visit` this soon after the person's last one answers 204 and writes nothing, because each visit writes an audit and an outbox row kept for ten years. Below 1 the app refuses to boot (H38) |
| `ASK_RETRIEVAL_DEPTH` | api | `6` | `6` | `6` | How many passages of the reader's own ranking Ask gives the model, best first: the whole of what an answer may rest on, each one a numbered citation. From 1 to `AI_GENERATION_CITATIONS_MAX`, or the app refuses to boot (SRC-03) |
| `ASK_MAX_TOKENS` | api | `1024` | `1024` | `1024` | The most one Ask answer may write, beneath the `LLM_MAX_TOKENS` ceiling: an answer is a few cited sentences. At least 1, or the app refuses to boot (SRC-03) |
| `AGENT_RUNNER` | worker | `mock` | `mock` | `mock` until chunk 11 | `mock` or `managed_agents` (D-08, ADR 0008) |

## Testing, observability, budgets

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `E2E_MODE` | api (E2E only) | set by Playwright's `webServer` | set by the E2E job | never | Makes the enrolment code deterministic and enables `seed_e2e`. Refused on two independent legs when deployed |
| `SENTRY_DSN` | all | unset | unset | optional, EU region DSN | `send_default_pii=False`, bodies never sent, scrubbers on events and transactions |
| `API_BUDGET_MS` | api | `250` | `250` | `250` | A WARNING with the request ID above it |
| `SEARCH_BUDGET_MS` | api | `800` | `800` | `800` | Hybrid search's budget without the reranker, in `Server-Timing` (NFR-02). The search tests hold the route to it, and a performance pass names it as the budget of the search rows it adds to `backend/perf/routes.py` |
| `SEARCH_RERANKED_BUDGET_MS` | api | `1500` | `1500` | `1500` | The same with the reranker on (NFR-02) |
| `ASK_FIRST_TOKEN_BUDGET_MS` | none (tooling) | `2000` | `2000` | never | Ask's budget: the time to the first streamed chunk, not to the whole answer (NFR-02, playbook 10). Only the performance harness reads it: it times a stream to that chunk, and a performance pass names it as the budget of the Ask row it adds to `backend/perf/routes.py`. The service changes when the API itself reads it |
| `PERF_SAMPLES` | none (tooling) | `20` | `20` | never | How many timed requests the performance harness makes per route after one warm-up it drops (`backend/perf/`). Twenty make the 95th percentile the second-slowest request rather than one outlier. The harness refuses a deployed environment |
| `PERF_REGRESSION_PCT` | none (tooling) | `20` | `20` | never | How far above its recorded baseline a route's median may go before `scripts/perf_report.py` fails it. Tighter and a busy machine's noise fails routes nobody changed; looser and a real slowdown hides |
| `API_PAGE_OFFSET_MAX` | api | `100000` | `100000` | `100000` | The largest `offset` any list accepts; above it the request answers 422 naming the field. PostgreSQL walks every skipped row and raises above a signed 64-bit integer, so an unbounded offset makes every paginated route answer 500. Below `API_PAGE_SIZE_MAX` the app refuses to boot |
| `OUTBOX_BATCH_SIZE` | worker | `100` | `100` | `100` | Rows one pass of the outbox cursor delivers; the pass holds the cursor's row lock for its duration |
| `OUTBOX_POLL_INTERVAL_S` | worker | `10` | `10` | `10` | How often beat runs the cursor, and so the longest a registered change waits for its cases at an idle moment |
| `OUTBOX_MAX_ATTEMPTS` | worker | `5` | `5` | `5` | After this many failed attempts the row is left failed (unpublished, with its attempt count and the exception's type name) and the cursor moves on, so one broken consumer cannot hold up every other row |
| `OUTBOX_RETRY_BACKOFF_S` | worker | `60` | `60` | `60` | The wait before a failed row is tried again, doubled per attempt (60 s, 120 s, 240 s, 480 s). Nothing behind that row is delivered while it waits, so order holds |
| `CASE_CREATION_BATCH` | worker | `100` | `100` | `100` | How many bank ids come back per round trip while a registered change reads the list of banks to open cases for (CAS-01). Each bank's case is still one insert of its own, because a session writes one zone; this bounds only the fetches |
| `SOURCE_STALE_AFTER_CHECKS` | api | `1` | `1` | `1` | How many sweeps of one source must fail in a row before the console's Source coverage calls it stale (WAT-01). One, by default: a supervisor's page that will not answer is news the moment it happens. Re-checks are not counted, so a run full of them never makes a source look fresh |
| `SOURCE_STALE_GRACE_HOURS` | api | `24` | `24` | `24` | How long past a source's own cadence a successful sweep may be before the source is called stale. A run is scheduled rather than instantaneous, so a daily source checked a few hours late is late, not unwatched |
| `STANDARDS_PUBLISHER_HOSTS` | api | `iso.org,iec.ch,sis.se,ds.dk,standard.no,sfs.fi,pcisecuritystandards.org` | `iso.org,iec.ch,sis.se,ds.dk,standard.no,sfs.fi,pcisecuritystandards.org` | `iso.org,iec.ch,sis.se,ds.dk,standard.no,sfs.fi,pcisecuritystandards.org` | Standards publishers no run reads automatically (WAT-07, D-45), comma-separated. A source registered on one of these hosts, or a subdomain of one, gets its automated checks switched off, like every source of the `standards_body` kind, and a run's check of it is refused. The default names every publisher whose terms were read on 2026-09-19; a host leaves the list only when a lawyer has cleared its terms |
| `WATCH_RUN_MAX_PROPOSALS` | api | `50` | `50` | `50` | The most proposals one agent run may file (AGT-01, H41); the next answers 422 `run_budget_exhausted` and stores nothing. At least 1, or the app refuses to boot |
| `WATCH_RUN_MAX_CHANGES` | api | `50` | `50` | `50` | The most new changes one agent run may register on the watch feed (AGT-01, H41); a second sighting of a change it already holds is not counted. At least 1, or the app refuses to boot |
| `WATCH_RUN_MAX_RECHECKS` | api | `100` | `100` | `100` | The most re-check lines one agent run may log in the coverage log (WAT-01, H41); a sweep of a source is not counted. At least 1, or the app refuses to boot |
| `HOME_COMING_UP_ITEMS` | api | `5` | `5` | `5` | How many dates Today's "Coming up" panel lists (HOM-01). One number for every screen size, because the panel is the same short list on a 375 px phone and on a desktop; the roadmap count beside it says how many more there are, so a shorter list hides nothing |
| `BRIEFING_SEND_WEEKDAY` | worker | `0` | `0` | `0` | Which day the weekly briefing mail goes out, in each bank's own time zone, as Python's weekday number (Monday is 0). The mail covers the week that has just ended, because a week can only be summed up once it is over. Beat runs the job every hour and it picks the banks whose own clock has just reached this weekday and the hour below, so one schedule serves banks in several time zones |
| `BRIEFING_SEND_HOUR` | worker | `7` | `7` | `7` | The hour of that day, 0 to 23, in each bank's own time zone. Seven in the morning is what the designed briefing screen tells people to expect |
| `BRIEFING_MAX_ITEMS` | worker, api | `10` | `10` | `10` | How many of a week's changes the briefing page and its mail carry, most urgent first (HOM-02). What is left out is not lost: the week's full list stays on the watch feed, which the briefing links to. Raising it makes a longer mail, never a slower one |
| `WORKFLOW_REMINDER_DAYS_BEFORE` | api | `3` | `3` | `3` | How many days before a due date a new bank's members are reminded, as comma-separated day counts (COL-02). Each 1 to 90, at most five; a tenant row outside that is refused by the database. A bank changes its own on its workflow screen, and changing this moves no existing bank |
| `WORKFLOW_REVIEW_REMINDER_DAYS_BEFORE` | api | `30` | `30` | `30` | How many days before a scheduled review a new bank's record owners are reminded, in the same form and bounds as the line above (COL-02) |
| `WORKFLOW_ESCALATE_AFTER_DAYS` | api | `5` | `5` | `5` | How many days a new bank lets work sit overdue before it escalates, 1 to 90 (COL-02) |
| `WORKFLOW_ESCALATE_TO_ROLE` | api | `compliance_officer` | `compliance_officer` | `compliance_officer` | The role a new bank's overdue work escalates to, as a system role key every bank is seeded with (COL-02). A role, never a person, so the escalation survives somebody leaving |
| `WORKFLOW_DIGEST_WEEKDAY` | api | `monday` | `monday` | `monday` | The day a new bank's digest goes out, `monday` to `sunday`, in the bank's own time zone (COL-02) |
| `WORKFLOW_TRIAGE_TARGET_HOURS` | api | `48` | `48` | `48` | How many hours a new change may wait before a new bank has triaged it, 1 to 720 (COL-02) |
| `CALENDAR_FEEDS_PER_USER` | api | `5` | `5` | `5` | How many calendar subscriptions one person may hold at once (HOM-04, D-52). The token in a calendar address is a credential nobody can be asked to confirm, so a handful is a person's phone, laptop and work calendar; an inventory of them would let a stolen session mint addresses nobody notices. Creating one past the cap answers 409, and revoking one makes room |
| `CALENDAR_FEED_IDLE_DAYS` | api | `30` | `30` | `30` | How long a calendar subscription nobody fetches stays alive. A calendar client polls every few hours, so a month of silence means the calendar was removed or the device replaced, and the address stops answering rather than working forever. A subscription in daily use is never touched by this |
| `CALENDAR_FEED_REVOKED_SHOWN` | api | `5` | `5` | `5` | How many stopped calendar subscriptions a person's own list shows beside the ones that still work, most recently stopped first (HOM-04). A person who pasted an address somewhere needs to see that it no longer works, and five is a whole set of addresses just replaced; older ones stay in the table and the audit trail but leave the list, so it stays short without paging however many a person has replaced over the years |
| `MAX_PARTICIPANTS_PER_RECORD` | api | `50` | `50` | `50` | How many people and teams may take part in one register entry or case at once (COL-04, D-18). Every participant receives every notification about the record, and a record everyone takes part in tells nobody anything, so the list is capped; adding past the cap answers 422 `too_many_participants` |
| `CALENDAR_FEED_RATE_PER_MINUTE` | api | `20` | `20` | `20` | How often one calendar address may be fetched, per token and per minute (HOM-04, D-52). A calendar client polls every few hours, so this is generous for every real client and still bounds what somebody who found an address can pull from it; a flood on one address never refuses another. Above it the answer is 429 `rate_limited` |
| `CALENDAR_FEED_LAST_USED_THROTTLE_SECONDS` | api | `300` | `300` | `300` | How often a fetch moves a subscription's last-used stamp and writes its `feed_used` row in the security log, throttled as an API key's stamp is (ID-10). Lower it to see polling in finer detail, at the cost of a write per fetch; raise it and the idle expiry still reads the same column |
| `EXPORT_RETENTION_DAYS` | api, worker | `7` | `7` | `7` | How many days an export's file is kept after the worker built it (REP-02). The file carries a bank's records outside the screens that permission-check them, so it lives only long enough to be downloaded; after that its download answers 409 `export_expired` and the job row stays |
| `LIBRARY_DIFF_MAX_SENTENCES` | api | `50` | `50` | `50` | "Show what changed" compares sentence by sentence up to this many sentences per version, and above it shows the whole old text deleted and the new one inserted. Aligning repeated sentences costs up to the cube of their count: the worst case measured 12 ms at 50, 60 ms at 100 and 211 ms at 200. Raise only after measuring. Outside 1 to 200 the app refuses to boot |
| `LIBRARY_TEXT_MAX_CHARS` | api | `20000` | `20000` | `20000` | A version text longer than this is never split into sentences: "show what changed" shows the whole old text deleted and the whole new one inserted. Splitting is linear in the length of a text a source published, about 57 ms per 200 KB, and a text under the sentence cap above is a few thousand characters |
| `PROPOSAL_SOURCE_MAX_CHARS` | api | `2000` | `2000` | `2000` | The longest source a proposal may give for one changed field (PRO-01). An agent writes these and a reviewer reads them, so each one is an https link or the stable key of a provision the library holds; 2000 is what the library's own `source_url` column takes. Above it the proposal answers 422 |
| `PROPOSAL_SCOPE_MAX_TERMS` | api | `20` | `20` | `20` | The most scope terms one obligation proposal may carry. They are resolved in one query and stored in the payload and its audit row, so the bound keeps a proposal from an agent small; above it the proposal answers 422 |
| `PROPOSAL_TEXT_MAX_CHARS` | api | `50000` | `50000` | `50000` | The longest text per language a proposal may carry, a provision's verbatim text or an obligation's summary (PRO-01, H35). The text is stored in the queue before a reviewer reads it, so it is bounded like a source; the longest article a Nordic or Union source publishes is a few tens of thousands of characters. Above it the proposal, or a reviewer's correction, answers 422 |
| `LIBRARY_UPDATES_DEFAULT_DAYS` | api | `30` | `30` | `30` | How far back `GET /library-updates` looks for a reader who has never marked the library as seen (PRO-03). Once they have, their own bookmark is the start and this is not used. Raise it and a first visit reads further back; lower it and a reader returning from leave sees less than they were away |
| `CREDENTIAL_POLICY_NOTICE_DAYS` | api | `14` | `14` | `14` | How many days ahead a tightened credential policy takes effect by default (ID-07, ADR 0048), so members can enrol a device-bound passkey before theirs stop working. The tenant's own `security_policy.device_bound_from` holds the date it chose |
| `BULK_TAGGING_MAX_RECORDS` | api | `200` | `200` | `200` | How many distinct records one bulk tagging preview or batch may name (VOC-08). A list page holds at most 100 rows, so this covers two pages' selection, and the one audit event a batch writes stays readable. Above it both answer 422 `too_many_records` and nothing is tagged |

## Web app

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | web | `http://localhost:8000` | `http://localhost:8000` | the api's public URL | Baked at build time by Next; a change needs a rebuild |
| `NEXT_PUBLIC_SUPPORT_CONTACT` | web | empty | empty | the address that answers access requests | An email address. The public page's "Write to us" opens a mail to it; empty hides the link. Baked at build time |

## Rules

- Every threshold in `settings.py` (code lifetimes, attempts, session
  limits, rate limits, budgets) has an env override named after the setting;
  the defaults are the numbers in the playbook and the PRD. They are not
  listed here individually; `.env.example` is the complete list.
- A new variable is added in four places in one commit: `settings.py`,
  `.env.example`, this file, and the Railway service it belongs to (by the
  owner).
