# Chunk 6: tasks

Written 2026-09-19 by the planning workflow (read, plan, parallelism and coverage critiques, revise). Each task runs in its own worktree or cloud session (`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`. The task ids are the `c6-` package ids of `docs/plans/PARALLEL_PLAN.md` section 3.3, plus `f03-T48` from `docs/plans/briefs/FEATURES_0_3_TASKS.md`; nothing is renamed, added or dropped.

## Scope, rules and defaults

Chunk 6 plan: the timeline home, the weekly briefing with its email, the roadmap page and the calendar feed. `Build_Plan.md` gives the chunk HOM-01 to HOM-04; PRD 0.3 adds `f03-T48` (Today's "Decide now" reads the queue counts on `GET /me`, D-23). HOM-05 (My work) is R2 and belongs to chunk 8 (D-26); nothing here builds it. The plan has 15 tasks in 9 waves, about 12 agent-hours of package work plus review.

PRECONDITIONS: WHAT MUST BE ON MAIN BEFORE WAVE 1
- Chunk 5: `c5-contract-models-watch` (RegulatoryChange, Source), `c5-contract-models-cases` and `c5-cases-creation` (ChangeCase with its urgency, owner and footprint match), `c5-contract-api-screens` (ChangeListItem, Urgency, SourceCoverage schemas), `c5-watch-sources-coverage` (`GET /sources/coverage`), `c5-seed-watch` (the seeded changes and cases), `c5-fe-change-detail` (the change page every chunk 6 screen links to).
- Chunk 4: `c4-queue-reads` (`GET /tenant/proposals`, the proposals count), `c4-mark-seen` (`POST /me/visit` and `Membership.last_visit_at`), `c4-console-shell`, and through it `x-frontend-split` (the per-namespace message catalogs every chunk 6 screen writes).
- Chunk 3: the inventory and the library read chain, because FP-S4's journey walks the inventory before it walks the roadmap and the briefing.
- Why it cannot wait: every date on the roadmap, every item in the briefing and the lead card on Today is a change case. Without chunk 5 there is nothing to show, and a screen would be built against a stub, which rule 3 of the parallel plan forbids.

WHAT IT DELIVERS
- HOM-01, Today: `GET /home` in one fan-out (never chained) with the tenant-local date, "Coming up" (the next roadmap items, the same short list on a 375 px phone and on a desktop), the roadmap count, the lead change with the `brand` pill "Lead", and source health. "Decide now" reads the queue counts on `GET /me` (D-23), which gains `counts` and `lastVisitAt` (INPUT_DELTAS §7).
- HOM-02, the briefing: `GET /briefings/current` computed live, `GET /briefings/{weekStart}` read from the snapshot, part of it on Today, and a weekly `@tenant_task` that writes the snapshot and sends the mail in each recipient's language. A later change to the feed does not alter a sent briefing: `briefing_item` is append-only.
- HOM-03, the roadmap: `GET /roadmap` by quarter in the tenant's timezone, with `kind`, `from` and `to`, the card expanding in place, the urgency pill, the date and days left as text.
- HOM-04: `GET /upcoming`, public library facts only, for a reader session or an agent key with `upcoming:read`; and a revocable per-user calendar feed whose ICS address is shown once, stored hashed, and answers 404 the moment it is revoked.
- FP-03 on both new surfaces, and FP-S4 reworded to the surfaces that exist and closed.
- The chunk's own security review, its fix package and its close.

RULINGS WHERE THE SOURCES DISAGREE
1. **"Decide now" has one source.** `docs/inputs/openapi.yaml` puts `decideNow` on `Home`, and D-23 puts the queue counts on `GET /me`. D-23 is the later input and wins: `Home` carries no `decideNow`, `GET /me` gains `counts` and `lastVisitAt`, and `f03-T48` builds them once, before the screen that reads them. Recorded in INPUT_DELTAS §1 and §7.
2. **"Where we stand" is chunk 8.** Ruling 20 of the parallel plan gives Today's standing panel to `c8-home-register-feeds`, and `tenant_obligation` does not exist in R1. `Home` therefore carries no `standing` field in chunk 6. Zeros were rejected: "0 gaps" before a register exists is a false statement about the bank's compliance. HOM-S1 is reworded to the panels that exist, naming chunk 8 for the standing panel.
3. **The roadmap's own deadlines are chunks 8 and 9.** `v_roadmap_item` has four branches; three of them (assessment deadlines, actions, next reviews) read tables that R1 does not have, and `design/screens/tenant-roadmap.html` says so in its own header comment. Chunk 6 builds the regulatory branch. `c8-home-register-feeds` adds reviews and gap targets, chunk 9 adds assessment deadlines and actions, and `f03-T74` adds the certificate branches (D-43). HOM-S4 and HOM-S6 are reworded to the R1 branch, HOM-03's status cell stays `in_progress` at the close, and the "Our deadline" pill keeps its unit test in `roadmap-presentation.test.ts`.
4. **Ruling 17 stands.** `c6-e2e-seed` seeds the dates and the lead item only; the seeded emailed snapshot moves into `c6-briefing-screen`, which needs the briefing builder to write one.
5. **One roadmap query.** `c6-roadmap-backend` owns `home/roadmap.py`; `c6-home-backend` calls its function for "Coming up" and the count and writes no roadmap query of its own.
6. **The ICS route is declared once, with the rest.** `c6-home-api-contract` declares all nine operations, the ICS route included, answering 501 `not_built` before any token is looked at. Only the behaviour behind it waited for q-feed-token. **Corrected 2026-09-21 (`c6-feed-contract`, Alex's approval):** it was declared as `GET /calendar/{feedToken}`, and D-52 with ADR 0045 had already decided the address is `GET /api/v1/calendar/feed.ics?token=<prefix>.<secret>` and that the path form is not built. The contract, the `calendar_feed` table, the `UNGATED_BY_DESIGN` entry and the security-log kind now carry the decided shape; the path form answers 404 and nothing rebuilds it.

DEFAULTS TAKEN (each stated in its commit body, and copied into `docs/TODO_FOR_alex.md` by `c6-chunk-close`)
- `GET /home` is gated by `roadmap.read`, not left ungated. Every system role holds `roadmap.read` (PRD §6), so this is "any member" in practice, and it avoids an entry in `UNGATED_BY_DESIGN`, which is an allowlist and therefore a guard change reserved to the packages named in parallel-plan rule 8. The UI plan row is corrected by the close.
- Each panel of `GET /home` is filtered by the reader's own permissions: the lead change and source health need `watch.read`, and a reader without it gets those fields empty, never a 403 on the page.
- The briefing goes to every active member of the tenant whose roles hold `watch.read`, in the member's locale, one mail per person per week. Per-person opt-out arrives with COL-02's notification preferences in chunk 10 (D-34 owns the recipient check from there on).
- The briefing mail carries library facts and a confirmed "So what?" only. An unconfirmed AI draft is never emailed; the screen shows it with its label (WAT-05).
- The briefing week is the ISO week, Monday to Sunday, in the tenant's timezone, matching `briefing.week_start` in `schema.sql`.
- `GET /briefings/current` computes the current week live and stores nothing. A snapshot row is written only by the weekly job, in the transaction that sends the mail.
- The roadmap and the briefing respect the regulatory scope and get **no** "Show outside our scope" toggle: the designed `/roadmap` takes `kind`, `from` and `to` only, and FP-S4 proves the toggle on the inventory, where chunk 3 built it.
- Quarters are labelled `YYYY-Qn` as keys; the screen renders the phrase from its catalog.
- The calendar feed token is `<prefix>.<secret>` with 256 bits of secret, stored as a unique 16-character lookup prefix beside the secret's SHA-256, shown once in `CalendarFeedCreated.url`, and never listed again (the `admin-api-keys.html` pattern). **Superseded 2026-09-21** the earlier default here, which was 32 bytes stored as one hashed column: D-52 and ADR 0045 decided the prefix-and-hash form with the query-string address.
- The ICS body carries the item's date, its label and the record's title, and no tenant judgement: no "So what?", no case note, no owner name.
- A revoked or unknown token answers 404, never 401 or 403, so the URL says nothing about whether it ever existed. An expired one answers the same way.
- `GET /upcoming` defaults to 20 items and caps at 100, like every other list.
- Feed creation and revocation are audited through `record()` under the member's tenant, and so is every automatic revocation, with a system actor. Revocation needs nothing of the caller: a person whose address has leaked stops it at once. Creation needs a recent sign-in or a step-up (`enforce_recent_sign_in_or_step_up`, already in force on the route), because the address outlives the session that minted it (D-52).
- A person holds at most `CALENDAR_FEEDS_PER_USER` subscriptions (5) and one idle for `CALENDAR_FEED_IDLE_DAYS` (30) expires. Both are settings, already in `config/settings.py`, `.env.example` and the Railway runbook.
- A calendar subscription has no filter: it carries the dates the outside world set and never the bank's own, so `CalendarFeedInput` names no field and `calendar_feed` has no `filter` column (D-52, ADR 0045, AC-TEN1). `feed_filter` stays the roadmap read's `kind` filter.
- `RoadmapItemKind` (`regulatory`, `internal`) and `RoadmapItemType` (`change_date`, `internal_deadline`, `action_due`, `review_due`) are tier-one kinds: the screen and the ICS builder branch on them. Both are declared in full, and R1 produces only `regulatory` / `change_date`.

CUT, WITH REASONS
- `Home.decideNow` and `Home.standing`: rulings 1 and 2.
- The three internal roadmap branches: ruling 3.
- `GET /reports/summary`: it is chunk 12's (ruling 20), and nothing on Today reads it.
- Recurring dates from `regulatory_change.recurrence_rule`: no seeded change carries a rule, and no scenario asks for one. The roadmap reads `key_date`. When a recurring change lands, the branch is a change to `home/roadmap.py`.
- Briefing feedback (`content_feedback` on a briefing item): chunk 7 builds the feedback route; no chunk 6 scenario asks for it.
- A briefing archive list: `GET /briefings/{weekStart}` is reached from the mail's link and from the previous-week control on the briefing page. There is no designed index, and no scenario needs one.
- My work (HOM-05) and everything in `home/my_work.py`: chunk 8 (D-26).

PLAN-WIDE RULES
1. **Slots.** Every backend and E2E gate runs inside the task's slot: `set -a; . ./.env.worktree; set +a`. A cloud session runs `bash scripts/cloud-setup.sh` (with `--e2e` where the gates include E2E) instead.
2. **Generated files.** No task commits `openapi.json`, `frontend/src/types/api.generated.ts` or `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them locally to run `contract_drift.py` and the typecheck, then reverts them. The main agent regenerates and commits them at the merge, and regenerates the navigation and pill snapshot baselines when `registry.ts` changed.
3. **The home backend chain.** One task at a time owns `backend/apps/home/api.py` and `schemas.py` (key `homecore`): `c6-home-api-contract` writes them once and sends each operation to a named function that answers `not_built`. A logic task owns only its own module (`roadmap.py`, `logic.py`, `calendar.py`, `briefing.py`, `tasks.py`) and its tests, never `api.py`. A logic task that finds the contract wrong stops and reports.
4. **The home frontend chain.** One task at a time owns `frontend/src/features/home/{types,api,hooks}.ts` (key `homefe`), in this order: `c6-roadmap-screen`, `c6-today-screen`, `c6-briefing-screen`. Each adds only the operations its own screen calls. The calendar feeds screen has its own feature directory and joins no chain.
5. **Screens call no stub.** Each screen task depends on every backend task whose routes it calls. Today's "This week in brief" panel is therefore built by `c6-briefing-screen`, not by `c6-today-screen`.
6. **Append ledgers** (parallel plan rule 5): `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`, the UI plan's ledger rows and status cells, `backend/config/settings.py` setting banners, router mounts in `backend/config/api.py`, `backend/apps/shared/kinds.py`, the route lists in `permissions.py`, the guarded-table lists in `tests_rls.py` and `tests_seed_integrity.py`, `backend/apps/shared/e2e_seed.py` (one seed call per task), `frontend/src/shared/navigation/registry.ts` entries, `frontend/src/features/shared/tone-by-kind.ts` entries, `backend/apps/home/app.md` status cells, `home/tests_scenarios.py` skip lines, and each `*.journey.spec.ts` (own test blocks only). Each task adds only its own lines and never edits another's.
7. **Coverage floors.** `backend/scripts/coverage_gate.py` gets the chunk 6 floors once, from `c6-chunk-close`, measured at the close with the date beside each. A task states its own `coverage report --include` threshold in its done-condition and never lowers an existing floor.
8. **Security review before merge.** `c6-home-models` (RLS on three new tenant tables), `c6-upcoming-calendar-backend` (an unauthenticated token route), `c6-briefing-backend` (outbound mail carrying tenant judgement) and `f03-T48` (identity) each get a security-review sub-agent over `git diff main...<branch>` before the squash merge, with `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write` and `tests_four_eyes`. `c6-security-review` is the chunk-wide sweep after the last screen merges, and `c6-review-fixes` closes its findings.
9. **Merge at once.** Each task is squash-merged and the full checklist run as soon as it passes review (WORKTREES step 5). Finished work never waits for the rest of the chunk.
10. **Clocks.** Everything dated is anchored to the tenant-local date plus a fixed wall time (CLAUDE.md §8.3 and §11). No seed, fixture, test or journey may depend on the real "today": a quarter boundary would make the roadmap green in September and red in October. Tests freeze the clock; the seed derives its dates from the anchor.
11. **Scenario ownership.** Exactly one task un-skips each integration test and one un-fixmes each journey:

| Scenario | `@integration` | `@e2e` |
|---|---|---|
| HOM-S1 (reworded) | `c6-home-backend` | `c6-today-screen` |
| HOM-S2 | — | `c6-today-screen` |
| HOM-S3 | `c6-briefing-backend` | `c6-briefing-screen` |
| HOM-S4 (reworded) | `c6-roadmap-backend` | `c6-roadmap-screen` |
| HOM-S5 | `c6-upcoming-calendar-backend` | `c6-calendar-feeds-screen` |
| HOM-S6 (reworded) | — | `c6-roadmap-screen` |
| FP-S4 (reworded) | `c6-briefing-backend` | `c6-briefing-screen` |

HOM-S7 to HOM-S15 stay skipped and fixme with their chunk named. `c6-home-api-contract`, `c6-home-models`, `c6-e2e-seed` and `f03-T48` contribute to scenarios and un-skip none.

CHANGES FROM `PARALLEL_PLAN.md`, WITH REASONS
- **`f03-T48` moves from wave 14 to wave 1** and drops `frontend/src/components/home/TodayScreen.tsx` from its owned paths. Under ruling 1 the counts are the only source for "Decide now", so building Today against `Home.decideNow` and rewriting it afterwards would write the panel twice and put two sources of the same number on main in between. Its depends-on becomes `c4-mark-seen`, `c4-queue-reads` and `c5-cases-creation`; `c6-today-screen` gains it.
- **`c6-home-backend` loses the `idapi` key.** With `f03-T48` owning the `GET /me` half, no chunk 6 backend task touches identity.
- **`c6-roadmap-screen` gains `c5-fe-change-detail`** in its depends-on: an expanded roadmap card links to the change page.
- **`c6-today-screen` loses `/briefings/current`**; the briefing panel on Today belongs to `c6-briefing-screen` (rule 5 above).
- **New key `homefe`** for `features/home/{types,api,hooks}.ts`, which four screen tasks would otherwise have edited.
- **`c6-calendar-feeds-screen` gets its own feature directory** (`features/calendar-feeds/`) so it can run beside `c6-today-screen`.

CHANGES FROM THE TWO CRITIQUES
- Parallelism: the `homefe` key and the calendar-feeds split (four tasks on one file); the roadmap function shared instead of duplicated (ruling 5); Today's briefing panel moved (a screen calling a stub); `f03-T48` moved (two tasks owning one file and one number); `c5-fe-change-detail` added to the roadmap screen; the first `CELERY_BEAT_SCHEDULE` entry and its registration test named as `c6-briefing-backend`'s alone; `c6-home-models` forbidden to touch `home/app.md`, so it can share wave 1 with the contract task.
- Coverage: "Where we stand" had no R1 owner (ruling 2); the roadmap's own deadlines had no R1 producer (ruling 3); FP-S4 named the roadmap and the briefing and would have stayed fixme past R1, so chunk 6 now owns its rewording and its close; HOM-S5's agent-key half had no test owner and is now `c6-upcoming-calendar-backend`'s integration; the `GET /me` counts had no backend owner and are now `f03-T48`'s; `kinds.py` describes `FeedFilter` as a footprint kind, which it is not, and `c6-home-models` corrects the line; no task owned the deletion of chunk 6's `contract_drift_pending.txt` lines, so each backend task deletes its own and the close proves none is left; the access log would have written the ICS token, the same class of finding as H10, so `c6-upcoming-calendar-backend` owns the scrub; HOM-S1's "one fan-out, none chained" had no test, so `c6-home-backend` pins the query count.

## Waves

Tasks in one wave have disjoint files and can run side by side.

1. `c6-home-api-contract`, `c6-home-models`, `f03-T48`
2. `c6-roadmap-backend`, `c6-e2e-seed`
3. `c6-home-backend`, `c6-upcoming-calendar-backend`
4. `c6-briefing-backend`, `c6-roadmap-screen`
5. `c6-today-screen`, `c6-calendar-feeds-screen`
6. `c6-briefing-screen`
7. `c6-security-review`
8. `c6-review-fixes`
9. `c6-chunk-close`

If q-feed-token is unanswered when wave 3 starts, `c6-upcoming-calendar-backend` builds `GET /upcoming` alone and stops at that green point (parallel plan rule 9); the feed half and `c6-calendar-feeds-screen` wait, HOM-S5 stays skipped, and `c6-chunk-close` cannot run. **That happened, and it is over.** The feed half stopped because the contract carried the path form the answer refuses. `c6-feed-contract` put the decided shape into `apps/home/api.py`, `schemas.py`, `models.py` with home 0002, the `UNGATED_BY_DESIGN` entry and the security log on 2026-09-21, so **HOM-S5's feed half is unblocked**: `c6-upcoming-calendar-backend` builds the four operations against a committed contract, `c6-calendar-feeds-screen` follows it, HOM-S5 is un-skipped by the first of those, and `c6-chunk-close` is no longer held by this.

## Open questions

- **q-feed-token — ANSWERED (D-52, ADR 0045; Alex, 2026-09-19).** The address is `GET /api/v1/calendar/feed.ics?token=<prefix>.<secret>` and the path form below is not built. What follows is the question as it was asked, kept because the options a decision rejected are half of what it decided. The calendar feed's token sits in the URL a calendar client fetches, so every server that logs a request line — Django's request logger on a 4xx, gunicorn's access log, the hosting edge — writes the token down. That is the class of problem F29 fixed for invitation tokens (e604de7) and H10 fixed for search text, and it is the invariant "a secret never reaches a log".

  The design has no alternative that keeps the feature: a calendar client sends no header and no body, follows no sign-in and cannot be asked for a passkey, so the URL is the only credential it can carry.

  Option A (recommended, **not taken**): accept the token in the path, with the mitigations that made F29 acceptable elsewhere — 32 bytes of entropy, stored only as a SHA-256 hash, never returned again after creation, revocable from the screen with immediate effect, the response marked `no-store`, the `/calendar/` path added to the access-log and Sentry scrub beside `?q=` (H10's mechanism), and the route excluded from `loggable_route`. Rotation is revoke-and-create, which the screen already offers.

  Option B: no calendar feed in R1. HOM-04 keeps `GET /upcoming` for agents and newsletters, and the subscription is cut to a later release once an alternative (a per-client secret in a header, which no calendar client sends) is found.

  Option C: a short-lived signed URL. It breaks the feature: a subscription is fetched for months without a person present to refresh it.

  **The answer was a fourth option this brief did not list:** the token moves out of the path and into the query string, where our own scrubbing already works and a hosting edge's request line does not reach. It carries 256 bits stored as a lookup prefix beside the secret's SHA-256, a person holds at most `CALENDAR_FEEDS_PER_USER`, minting one takes a recent sign-in or a step-up, a fetch re-checks membership and `roadmap.read` and revokes the subscription when a check fails, an idle one expires after `CALENDAR_FEED_IDLE_DAYS`, and `feed_used` joins the security log. The path form is not built, and the scrub work Option A described is not needed: `loggable_route` already prints the route without the query.

  This gated the feed half of `c6-upcoming-calendar-backend`, all of `c6-calendar-feeds-screen`, HOM-S5 and `c6-chunk-close`. It gates none of them now.
- Non-blocking, to confirm (defaults are taken and the build does not wait): who receives the weekly briefing mail before COL-02's preferences exist (default: every active member holding `watch.read`); that a confirmed "So what?" may travel in that mail while an unconfirmed draft may not; and that Today's standing panel and the roadmap's own deadlines arriving in chunk 8 is acceptable for the first test deploy. `c6-chunk-close` writes all three into `docs/TODO_FOR_alex.md`.
- Rejected, from the parallelism critique: the suggestion that `c6-home-backend` and `c6-roadmap-backend` merge into one task because both read change cases. They own different modules and different scenarios, and together they exceed the 60-minute limit; ruling 5 removes the duplication without removing the split.
- Rejected, from the coverage critique: the suggestion that `Home.standing` be served as zeros so HOM-S1 needs no rewording. A compliance figure that reads "0 gaps" before the register exists is a false statement about the bank, and the screen would have to show it on the first test deploy. The field is omitted and the panel named for chunk 8 instead.
- Rejected in part, from the coverage critique: the suggestion that chunk 6 add the internal roadmap branches now, reading `change_case` for a deadline. `change_case` has no date column of its own (`schema.sql` §7); every internal date lives in `impact_assessment`, `action` or `tenant_obligation`, none of which exists in R1. The accepted part is ruling 3's rewording and the named chunks.
- Rejected, from the parallelism critique: giving `c6-e2e-seed` the whole chunk 6 seed including the emailed snapshot. Ruling 17 of the parallel plan splits them, and the snapshot needs the briefing builder that lands two waves later.

## Tasks

### c6-home-api-contract: the home contract, nine operations behind their real gates

**Requirements:** HOM-01, HOM-02, HOM-03, HOM-04
**Scenarios:** none (it un-skips nothing; every scenario stub stays as it is)
**Depends on:** `c5-contract-api-screens`

Write `backend/apps/home/api.py` and `schemas.py` once, and mount the router in `config/api.py`. Every operation carries its auth class and permission and calls a named function in the module that will build it, which answers 501 `not_built` (parallel plan rule 2):

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `getHome` | `GET /home` | SessionAuth, `roadmap.read` | `home/logic.py` |
| `getCurrentBriefing` | `GET /briefings/current` | SessionAuth, `watch.read` | `home/briefing.py` |
| `getBriefing` | `GET /briefings/{weekStart}` | SessionAuth, `watch.read` | `home/briefing.py` |
| `getRoadmap` | `GET /roadmap` | SessionAuth, `roadmap.read` | `home/roadmap.py` |
| `listUpcoming` | `GET /upcoming` | SessionAuth `roadmap.read` or ApiKeyAuth `upcoming:read` | `home/calendar.py` |
| `listCalendarFeeds` | `GET /calendar-feeds` | SessionAuth, `roadmap.read` | `home/calendar.py` |
| `createCalendarFeed` | `POST /calendar-feeds` | SessionAuth, `roadmap.read` | `home/calendar.py` |
| `revokeCalendarFeed` | `DELETE /calendar-feeds/{feedId}` | SessionAuth, `roadmap.read` | `home/calendar.py` |
| `getCalendarIcs` | `GET /calendar/feed.ics?token=<prefix>.<secret>` | none (the token is the credential) | `home/calendar.py` |

> **Corrected 2026-09-21 by `c6-feed-contract` (Alex approved the correction).** This task
> wrote `GET /calendar/{feedToken}` and a `calendar_feed` row to match. D-52 and ADR 0045
> had decided the other shape and say in as many words that the path form is not built, so
> `c6-upcoming-calendar-backend` stopped rather than build it. What is on `main` now, and
> what the rest of the chunk builds against: the address is
> `GET /api/v1/calendar/feed.ics?token=<prefix>.<secret>`; `createCalendarFeed` takes a body
> with no fields and refuses a session that is neither recent nor freshly confirmed, with
> `step_up_required`; `HomeCalendarFeed` carries `lastUsedAt` and no `filter`; and
> `UNGATED_BY_DESIGN` holds `("GET", "/calendar/feed.ics")` with the mitigations ADR 0045
> decided. Nobody rebuilds the path form.

Schemas, camelCase through `CamelSchema`, reusing chunk 5's `ChangeListItem`, `Urgency` and `SourceCoverage` rather than restating them:
- `Home` = `{date, comingUp[RoadmapItem], roadmapCount, lead|null, sources}`. No `decideNow` (ruling 1) and no `standing` (ruling 2).
- `RoadmapItem` = the designed shape minus the fields no R1 branch fills: `{id, kind, itemType, date, quarter, label, title, status, urgency|null, sourceLabel, changeId|null, obligations[]}`. `soWhat`, `what` and `owner` arrive with the branches that have them (chunks 8 and 9).
- `Roadmap` = `{items, quarters}`; `Briefing` = `{weekStart, weekEnd, lead|null, items, comingUp, emailSentAt|null}`; `UpcomingItem` as designed. The three calendar shapes are **not** as designed since the correction above: `CalendarFeed` = `{id, createdAt, lastUsedAt|null, revokedAt|null}`, `CalendarFeedInput` names no field, and `CalendarFeedCreated.url` ends `/calendar/feed.ics?token=<prefix>.<secret>` (INPUT_DELTAS §7, §9).
- `RoadmapQuery` = `{kind?: RoadmapItemKind|'all', from?: date, to?: date}`; `UpcomingQuery` carries the shared `limit` (default 20, max 100).

Also:
- Add the nine routes to the route lists in `apps/shared/permissions.py`. Two of them did have to join `UNGATED_BY_DESIGN` after all, against this line's expectation: `GET /upcoming` (a person's permission or an agent's scope, which one decorator cannot say) and the ICS route, which presents no principal at all. `getHome` carries `roadmap.read` as planned. The ICS entry is keyed `("GET", "/calendar/feed.ics")` and its note carries the mitigations ADR 0045 decided.
- Write the INPUT_DELTAS §1 and §7 rows for ruling 1 (no `decideNow`; `GET /me` gains `counts` and `lastVisitAt`), ruling 2 (no `standing` until chunk 8) and ruling 3 (the R1 roadmap branch), each naming the task that closes it.

**Owned paths:**

- `backend/apps/home/api.py`
- `backend/apps/home/schemas.py`
- `backend/apps/home/tests_contract.py`
- `backend/config/api.py` (the router mount only)
- `backend/apps/shared/permissions.py` (the route lists only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- The nine operations appear in `openapi.json` with the ids above and answer 501 `not_built` behind their real gate.
- A session without the permission gets 403 with `requiredPermission`, and an anonymous request gets 401 — both before the 501, proved per route.
- `GET /calendar/feed.ics?token=…` answers 501 for any token and reads nothing, and the path form answers 404.
- The route-permission guard is green and lists no ungated route.
- `contract_drift.py` reports the nine operations as delivered-in-part, and no line is deleted yet.
- `bash generate-types.sh` produces types for all nine without the task committing them.
- The diff stays inside the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.home apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`.
- Every route has a permission or a declared credential; nothing joins `UNGATED_BY_DESIGN`.
- Errors are RFC 9457 with a `code`; no trace ever leaves.
- The API returns `key` and `kind`, never a phrase.

### c6-home-models: briefing, briefing item and calendar feed

**Requirements:** HOM-02, HOM-04
**Scenarios:** none
**Depends on:** `c5-contract-models-cases`
**Security review:** yes (three new tenant tables, one holding a credential)

Add `backend/apps/home/models.py` and `migrations/0001_home.py`, from `docs/inputs/schema.sql` §9 and `data-model.md`:
- `Briefing(TenantModel)`: `week_start` (date, Monday), `generated_at`, `email_sent_at` (nullable), unique `(tenant, week_start)`, `Meta.ordering = ["-week_start"]`.
- `BriefingItem(TenantModel, AppendOnlyModel)`: `briefing`, `case`, `rank` (1 is the lead), unique `(briefing, case)`, `Meta.ordering = ["rank"]`. The append-only trigger comes from `migration_helpers.append_only_trigger_operations`, so a sent briefing cannot be rewritten by a later feed change — that is HOM-S3's last line, made structural instead of remembered.
- `CalendarFeed(TenantModel)`: `user`, `token_prefix` (unique, 16 characters), `token_hash` (the secret's SHA-256), `created_at`, `last_used_at` (nullable), `revoked_at` (nullable), `Meta.ordering = ["-created_at"]`. No plaintext token column exists and there is **no** `filter` column. **Corrected 2026-09-21 by `c6-feed-contract` (home 0002):** this task built `token_hash` unique with a `filter` column, from `schema.sql` §9; D-52 and ADR 0045 had decided the prefix-and-hash form, the idle stamp and a feed that carries the outside world's dates only, so the filter has two values that could never mean anything. Nobody puts it back.

The migration applies `migration_helpers.rls_operations()` to all three tables and `migration_helpers.append_only_trigger_operations` to `briefing_item`. Home 0002 then replaces `calendar_feed`'s policies with `split_policy_operations(identity_lookup=True)`, because a calendar client presents no session and no key and the row has to be found before a tenant is known — `calendar_feed` is the fifth identity-lookup table.

Also:
- Add `RoadmapItemKind` and `RoadmapItemType` to `apps/shared/kinds.py` with their INPUT_DELTAS §1 names and reasons, and correct the existing `FeedFilter` line, which today says "FP-03: inside or outside the footprint": `feed_filter` is the roadmap read's `all | regulatory | internal` filter, and nothing branches on it for the footprint. (Corrected again on 2026-09-21: it is no longer a calendar subscription's scope either, because a subscription has nothing to choose between.)
- Add the three tables to the guarded-table list in `apps/shared/tests_rls.py`, and `calendar_feed` to `IDENTITY_LOOKUP_TABLES` beside it.

**Owned paths:**

- `backend/apps/home/models.py`
- `backend/apps/home/migrations/0001_home.py`
- `backend/apps/home/tests_models.py`
- `backend/apps/shared/kinds.py`
- `backend/apps/shared/tests_rls.py` (the guarded-table list only)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- The RLS guard lists `briefing`, `briefing_item` and `calendar_feed` as forced tenant-only, and a cross-tenant read returns nothing under `cw_app`.
- As `cw_app`, UPDATE and DELETE on `briefing_item` are refused and INSERT works; a test proves it on the app alias.
- `token_prefix` is unique, and no model field, `__str__` or `__repr__` can return a plaintext token or either of its halves.
- The kinds-only guard and the compliance lint are green, and `FeedFilter`'s reason names the surface that still reads it.
- The task edits no file under `apps/home/` other than the three named, so it can share a wave with the contract task.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.home apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/*,apps/shared/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Tenant tables carry `tenant_id` under enabled and forced row-level security; `cw_app` cannot bypass it.
- Nothing overwritten: the briefing snapshot is append-only at the database, not by convention.
- A credential is stored hashed, never in plaintext.
- snake_case columns; `Meta.ordering` on anything `.first()`ed; no `JSONField` without a named schema.

### f03-T48: Today's decisions read the queue counts on `GET /me`

**Requirements:** HOM-01, ID-04, AC-HOM1 (the Decide-now half)
**Scenarios:** contributes to HOM-S1, which `c6-home-backend` and `c6-today-screen` un-skip
**Depends on:** `c4-mark-seen`, `c4-queue-reads`, `c5-cases-creation`
**Security review:** yes (identity)

Give `GET /me` the designed `counts` and `lastVisitAt`, which INPUT_DELTAS §7 parked "until the home chunk, when there is a queue to count" (D-23):
- `counts` = `{triage, proposals, assignedToMe}`, each computed under RLS for the caller's tenant and filtered by the caller's own permissions: `triage` counts cases waiting for triage and is 0 without `cases.triage`; `proposals` counts the tenant's pending library proposals and is 0 without `proposals.create`; `assignedToMe` counts open cases whose owner is the caller.
- The designed `signoffs` and `unreadNotifications` are **not** added: sign-off arrives in chunk 9 and notifications in chunk 10, and a field that always reads 0 is a lie the screen would render. The chunk that builds each adds its own count. `applicability` joins in chunk 8.
- `lastVisitAt` is the caller's `Membership.last_visit_at`, which `c4-mark-seen` already writes.
- A platform session (no tenant) gets `counts` as null and `lastVisitAt` as null, not zeros.
- Counts come from three independent queries in one fan-out; nothing is chained, and a pinned query-count test proves it.

Write the test first in a new `apps/identity/tests_me_counts.py`. Do not edit `apps/identity/api.py`: the route exists and its shape comes from `schemas.py`.

**Owned paths:**

- `backend/apps/identity/schemas.py`
- `backend/apps/identity/me_logic.py`
- `backend/apps/identity/tests_me_counts.py`
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `GET /me` carries `counts` and `lastVisitAt`; nothing on any screen reads `/me/work`, which does not exist until chunk 8.
- Each count is 0, not refused, for a member without the permission behind it, and the per-permission matrix is tested.
- A second tenant's rows never reach a count; the tenant-isolation guard is green.
- The read writes nothing: no audit row, no bookmark move.
- `apps/identity/me_logic.py` holds its coverage floor and the query count is pinned.
- `contract_drift.py` is clean for `getMe`, and its INPUT_DELTAS §7 row is updated from "waits for chunk 6" to what was built, naming the two deferred counts and their chunks.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/identity/me_logic.py,apps/identity/schemas.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- `tenancy.activate()` after auth; every count is read under row-level security.
- Permissions, never role names.
- A read writes nothing and records nothing.
- No tenant content in logs: a count is a number, and no title travels with it.

### c6-roadmap-backend: the roadmap by quarter, with the regulatory branch

**Requirements:** HOM-03, FP-03
**Scenarios:** HOM-S4 (reworded, un-skipped); contributes to HOM-S6
**Depends on:** `c6-home-api-contract`, `c5-contract-models-watch`, `c5-cases-creation`

Build `backend/apps/home/roadmap.py` and serve `GET /roadmap`:
- One query over the tenant's change cases joined to their change, under RLS: status not closed or dismissed, `footprint_match` true (FP-03), `key_date` not null and not before the tenant-local today, ordered by date.
- Each item: a stable id, `kind` `regulatory`, `itemType` `change_date`, the date, the quarter key (`YYYY-Qn`, computed in the tenant's timezone), the change's `key_date_label` as `label`, the title, the case status key, the case's urgency as `{key, kind, label}`, the change's `source_label`, its `changeId`, and its confirmed obligation links.
- Filters: `kind` (`all`, `regulatory`, `internal`; `internal` answers an empty list in R1 and is not an error), `from` and `to` as plain dates.
- `quarters` is the ordered list of quarter keys present in `items`.
- Two exported functions, so no second roadmap query is ever written: `roadmap_items(...)` and `coming_up(limit)` with its count, which `c6-home-backend` calls.

Rewording, in `backend/apps/home/app.md`, with the reason in the commit body (ruling 3):
- HOM-S4's Given becomes regulatory dates across two quarters; its "our deadlines with 'Our deadline'" step is moved to a named note that `c8-home-register-feeds` (reviews and gap targets), chunk 9 (assessment deadlines and actions) and `f03-T74` (certificate expiry and next audit, D-43) each prove for their own branch.
- HOM-S6 keeps the urgency half and names the same note for the "Our deadline" half; `roadmap-presentation.test.ts` already pins that pill's tone.
- Then un-skip HOM-S4 and delete the `getRoadmap` line from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/home/roadmap.py`
- `backend/apps/home/tests_roadmap.py`
- `backend/apps/home/tests_scenarios.py` (the HOM-S4 skip line and body only)
- `backend/apps/home/app.md`
- `backend/scripts/contract_drift_pending.txt` (its own line only)

**Done when:**

- HOM-S4 is reworded in app.md, un-skipped and green with a frozen clock.
- Quarters are computed in the tenant's timezone, proved by a tenant in `Europe/Stockholm` and one in `UTC` sharing a date that falls in different quarters.
- A case outside the regulatory scope is absent, and one inside is present (FP-03).
- A closed or dismissed case, and a change whose key date has passed, are both absent.
- `kind=internal` answers `{items: [], quarters: []}` with 200, never 422.
- The read runs a fixed number of queries whatever the number of items, pinned by a test, and answers within the 250 ms budget on the seeded data.
- The route answers under 250 ms with `Server-Timing: app` and no WARNING.
- The task writes no query against cases outside `roadmap.py`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.home apps.watch apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/*' (roadmap.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- All logic in `roadmap.py`; `api.py` is untouched.
- The footprint rule is chunk 2's and chunk 3's, called, never restated.
- Dates are plain dates with a precision; timestamps are UTC.
- Every threshold (the "Coming up" length) is a setting with an env override.
- Keys and kinds leave the API, never a phrase.

### c6-e2e-seed: the chunk 6 dates and the lead item

**Requirements:** HOM-01, HOM-03
**Scenarios:** supports HOM-S1, HOM-S2, HOM-S4, HOM-S5 and HOM-S6
**Depends on:** `c5-seed-watch`, `c6-home-models`

Extend `seed_e2e` with one seed call for chunk 6 (ruling 17: the dates and the lead item only; the emailed snapshot is `c6-briefing-screen`'s):
- Anchored to the tenant-local date plus a fixed wall time, never to the real "today": changes with key dates in the current quarter and the next, at fixed offsets, so a quarter boundary never changes what the journeys see.
- One lead case: the most urgent open case of the current week, with a confirmed "So what?" so the lead card and the briefing have text a person wrote.
- One case outside the regulatory scope, so FP-S4 and the roadmap's footprint test have something that must not appear.
- One source whose last check failed, so Today's source health has a failure to show.
- Tenant B gets its own two dates, so an isolation journey can prove tenant A never sees them.
- `EXPECTED_TENANTS` and the seed-integrity guard gain the rows this adds, so a later seed change cannot hollow the journeys out.

Idempotent by natural key, deterministic, realistic, built from the prototype's data. No new login: every chunk 6 journey signs in as a seeded role.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (one seed call only)
- `backend/apps/shared/tests_seed_integrity.py` (its own expectations only)

**Done when:**

- `seed_e2e` runs twice with no duplicate row and no error.
- Every seeded date is derived from the anchor; a grep of the diff finds no `date.today()` and no literal year.
- The seeded dates land in two quarters whatever the day the suite runs, proved by a test that runs the derivation on four anchor dates a quarter apart.
- The seed-integrity guard names the lead case, the out-of-scope case and the failed source check.
- `E2E_MODE` off, the seed still runs against a local database.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared apps.watch apps.home --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/e2e_seed.py' (>= 96)`
- `./run.sh run python manage.py seed_e2e --settings=config.test_settings` twice, then once more after `migrate_from_zero`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all`

**Invariants:**

- The seed writes library rows only from the seed modules the library fence allows.
- Seeded tenant rows are written with the tenant active, under RLS.
- No real clause text, no real person, no secret in the repository.
- Time-anchored fixtures follow CLAUDE.md §8.3.

### c6-home-backend: Today in one fan-out

**Requirements:** HOM-01, FP-03, NFR-02
**Scenarios:** HOM-S1 (reworded, un-skipped)
**Depends on:** `c6-home-api-contract`, `c6-roadmap-backend`, `c5-watch-sources-coverage`, `c5-cases-creation`, `c4-queue-reads`, `c4-mark-seen`

Build `backend/apps/home/logic.py` and serve `GET /home`:
- `date`: the tenant-local calendar day.
- `comingUp` and `roadmapCount`: `roadmap.coming_up(HOME_COMING_UP_ITEMS)`, the same function and therefore the same rows as `/roadmap`.
- `lead`: the week's lead case as a `ChangeListItem` — the most urgent open, in-scope case of the current week, with its confirmed "So what?" when there is one and the AI label when there is not. Null when the week has none, and null for a reader without `watch.read`.
- `sources`: `{checked, total, failed[]}` from chunk 5's coverage read, for a reader with `watch.read`; otherwise `{checked: 0, total: 0, failed: []}` is **not** returned — the field is null, and the screen hides the panel.
- The four reads fan out and none is chained: a pinned query-count test proves it, and the route holds the 250 ms budget on the seeded data.

Rewording, in `home/app.md` (ruling 2), then un-skip HOM-S1:
- Its "Where we stand shows the compliance standing counts" step moves to a named note: `c8-home-register-feeds` adds the standing panel with the register (ruling 20 of the parallel plan).
- Its "what needs a decision" step reads the queue counts on `GET /me` (D-23), which `f03-T48` built.
- Delete the `getHome` line from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/home/logic.py`
- `backend/apps/home/tests_home.py`
- `backend/apps/home/tests_scenarios.py` (the HOM-S1 skip line and body only)
- `backend/apps/home/app.md`
- `backend/config/settings.py` (one labelled settings block: `HOME_COMING_UP_ITEMS`, default 5)
- `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (its own rows only)
- `backend/scripts/contract_drift_pending.txt` (its own line only)

**Done when:**

- HOM-S1 is reworded, un-skipped and green.
- The lead is the same case the briefing would lead with, proved by a test that calls both selectors on the same seeded week once `c6-briefing-backend` lands, and by a shared selector until then.
- A reader without `watch.read` gets a 200 with `lead` and `sources` null, never a 403 and never another tenant's row.
- "Coming up" and `/roadmap` return the same first items, proved by a test that calls both.
- The query count is pinned and does not grow with the number of cases; `Server-Timing: app` stays under `API_BUDGET_MS`.
- `HOME_COMING_UP_ITEMS` is a setting with an env override, and the settings banner names this task.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.home apps.watch apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/*' (logic.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- Fan out, never chain (playbook 6).
- Permission-filtered fields, never a page-level 403 for a panel a reader cannot see.
- AI output is labelled until a person confirms it.
- No tenant content in logs, Sentry or analytics.
- All logic in `logic.py`; `api.py` untouched.

### c6-upcoming-calendar-backend: public upcoming facts and the revocable feed

**Requirements:** HOM-04
**Scenarios:** HOM-S5 (un-skipped)
**Depends on:** `c6-home-models`, `c6-home-api-contract`, `c6-roadmap-backend`, `c5-contract-models-watch`, `c6-feed-contract`
**Security review:** yes (an unauthenticated token route, a stored credential, an outbound log path)

Build `backend/apps/home/calendar.py`. `GET /upcoming` is built and green; the feed half is what is left, and it is no longer held by an open question.

`GET /upcoming` (built 2026-09-21):
- Active changes with a key date from today on, ordered by date, `limit` default 20 and max 100.
- Each item is `UpcomingItem` and nothing else: change id, title, key date with its precision and label, change type, authority label, suggested urgency, source URL. No case, no tenant judgement, no footprint filter — these are public library facts, the same list the app, the newsletter agent and the feed read (`schema.sql` `v_upcoming`).
- Readable by a member session with `roadmap.read` and by an API key with `upcoming:read`. A key without that scope gets 403; no key scope reaches anything else here.

The calendar feed, against the contract `c6-feed-contract` committed (D-52, ADR 0045; **do not reshape it, and do not rebuild the path form**):
- `POST /calendar-feeds` mints a 16-character prefix and 256 bits of secret, stores the prefix and the secret's SHA-256 on `calendar_feed`, and returns the address once in `CalendarFeedCreated.url` as `…/calendar/feed.ics?token=<prefix>.<secret>`. The body names no field. The route already calls `enforce_recent_sign_in_or_step_up`, so the freshness rule is in force; what this task adds is the `CALENDAR_FEEDS_PER_USER` cap, which needs a 409 and a code of its own (`apps/shared/errors.py` has no fitting one, and the API documentation gate refuses a code no route raises, which is why the contract describes the refusal in words and names no code yet — add the code and the sentence together).
- `GET /calendar-feeds` lists the caller's own feeds with no token and no other member's row; `DELETE /calendar-feeds/{feedId}` sets `revoked_at` and a second delete is idempotent.
- `GET /calendar/feed.ics?token=…` reads the prefix, finds the row through `tenancy.identity_lookup()` (add `apps/home/calendar.py` to the AST allow-list of callers in `apps/shared/tests_tenancy.py`), compares the secret's hash in constant time, refuses an unknown, revoked or expired token with the same 404, activates the feed's tenant and serves `text/calendar` from the owner's roadmap. The ICS carries date, label and record title only: no "So what?", no case note, no owner name, no tenant name, and a guard test pins the emitted fields.
- Each fetch checks that the membership is active, still holds `roadmap.read` and has not been re-enrolled since the feed was created, and revokes the feed when a check fails; a feed idle for `CALENDAR_FEED_IDLE_DAYS` expires. Every automatic revocation writes a `record()` row with a system actor in the same transaction. Each fetch writes a throttled `feed_used` row in the security log through `log_event()`, carrying no address and no IP, and stamps `last_used_at` on the same throttle.
- The response is `no-store` with `Cache-Control: private`. No scrub work is needed: `loggable_route` already prints the route and never the query string, which is why D-52 put the token there; a test that captures the log handler proves it rather than assuming it.
- Create and revoke are audited through `record()` in the same transaction; reading the feed writes no audit row and is rate limited per token.
- Write the CONVENTIONS 3.6 exception with this package, as D-52 says: the one route that reads a credential from a query string, with the guard in `apps/home/tests_contract.py` that keeps it one route wide.

Un-skip HOM-S5's integration, proving both halves: an agent key reads `/upcoming` and gets library facts only; a user subscribes, fetches the ICS, revokes and gets 404. Delete the four `contract_drift_pending.txt` lines this task delivers.

**Owned paths:**

- `backend/apps/home/calendar.py`
- `backend/apps/home/tests_calendar.py`
- `backend/apps/home/tests_scenarios.py` (the HOM-S5 skip line and body only)
- `backend/apps/home/app.md` (its status cells only; it rewords nothing, so it can share wave 3 with `c6-home-backend`, which rewords HOM-S1)
- `backend/apps/shared/tests_tenancy.py` (the `identity_lookup()` caller allow-list only)
- `backend/apps/shared/errors.py` (the one new code for the per-person cap)
- `backend/config/settings.py` (one labelled block: `CALENDAR_FEED_RATE_PER_MINUTE`, `UPCOMING_DEFAULT_LIMIT`; `CALENDAR_FEEDS_PER_USER` and `CALENDAR_FEED_IDLE_DAYS` are already there with their `.env.example` and runbook rows)
- `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (its own rows only)
- `backend/scripts/contract_drift_pending.txt` (its own lines only)

**Done when:**

- HOM-S5 is un-skipped and green.
- `/upcoming` returns no tenant column: a test asserts the response keys against `UpcomingItem` exactly, and a second proves two tenants' keys get identical bodies.
- A key without `upcoming:read` is refused, and no key scope reaches `/home`, `/roadmap`, `/briefings` or `/calendar-feeds`.
- A feed's plaintext token appears exactly once, in the create response; neither it nor its prefix is in the list read, the database, an audit row, an error body, any log line or any Sentry event, proved by a test that captures the log handler.
- A revoked token, an unknown token, an expired one and another tenant's all answer 404 with the same body and the same timing path.
- A sixth subscription is refused with the cap's 409 and its code, and revoking one makes room; a stale session is already refused with `step_up_required` by the route.
- The ICS body contains no tenant judgement, proved by asserting the rendered text against the seeded "So what?" string.
- Create and revoke each write one audit row in the caller's tenant; the ICS read writes none.
- The rate limit refuses a flood on one token without refusing another.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.home apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/*' (calendar.py >= 96)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `gitleaks git . --config .gitleaks.toml`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- A secret never reaches a log, Sentry or an analytics event.
- A credential is stored hashed; an unknown credential is indistinguishable from a revoked one.
- `tenancy.activate()` before any tenant row is read, including on the token route.
- No API key scope reaches the library door; `/upcoming` reads, never writes.
- `record()` on every write, in the same transaction.

### c6-briefing-backend: the weekly briefing, its snapshot and its mail

**Requirements:** HOM-02, WAT-05, FP-03
**Scenarios:** HOM-S3 (un-skipped), FP-S4 (reworded, its roadmap and briefing steps un-skipped)
**Depends on:** `c6-home-models`, `c6-home-api-contract`, `c6-home-backend`, `c6-roadmap-backend`
**Security review:** yes (tenant judgement leaves the system by mail)

Build `backend/apps/home/briefing.py` and `backend/apps/home/tasks.py`:
- `current_briefing()` computes the running week live: the week's in-scope cases (FP-03), ordered by urgency then key date, capped at `BRIEFING_MAX_ITEMS`; the lead is the same selector `c6-home-backend` uses; `comingUp` is `roadmap.coming_up()`; `emailSentAt` is null until the job runs.
- `GET /briefings/{weekStart}` reads the snapshot: the `briefing` row and its `briefing_item` ranks, resolved to `ChangeListItem`s as they are now, with the week's dates. A week with no snapshot answers 404.
- The weekly job is a `@tenant_task` on the beat schedule: for each active tenant, in the tenant's timezone, it writes the `briefing` row and its items, composes the mail in each recipient's locale from the message catalog, sends it through the mailer adapter, and sets `email_sent_at` — all in one transaction per tenant, with one `record()` per briefing.
- Recipients: active members whose roles hold `watch.read`. The mail carries the week's titles, the confirmed "So what?" of the lead, and a link to `/briefing/{weekStart}`; never an unconfirmed AI draft, never a case note.
- Re-running the job for a week that already has a snapshot sends nothing and writes nothing (idempotent by `(tenant, week_start)`).

This adds the first entry to `CELERY_BEAT_SCHEDULE`; `apps.shared.tests_celery_registration` must stay green, and this task adds only its own entry and its own test block.

FP-S4 (ruling in the scope section): reword it in `backend/apps/taxonomy/app.md` to the surfaces that exist — the feed, the inventory, the roadmap and the briefing — with reports named for chunk 12, and extend its integration test so a record outside the regulatory scope is absent from the roadmap read and the briefing read as well.

**Owned paths:**

- `backend/apps/home/briefing.py`
- `backend/apps/home/tasks.py`
- `backend/apps/home/tests_briefing.py`
- `backend/apps/home/tests_scenarios.py` (the HOM-S3 skip line and body only)
- `backend/apps/home/app.md`
- `backend/apps/taxonomy/app.md` (the FP-S4 block only)
- `backend/apps/taxonomy/tests_scenarios.py` (the FP-S4 body only)
- `backend/config/settings.py` (one labelled block: `BRIEFING_SEND_WEEKDAY`, `BRIEFING_SEND_HOUR`, `BRIEFING_MAX_ITEMS`, and the beat entry)
- `backend/apps/shared/tests_celery_registration.py` (its own block only)
- `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (its own rows only)
- `backend/apps/home/mail.py` (the mail's subject and body in en and sv, the composer `c10-mail-catalog` extends in chunk 10, ruling 21)
- `backend/scripts/contract_drift_pending.txt` (its own two lines only)

**Done when:**

- HOM-S3 is un-skipped and green: the briefing opens from Today's panel data, the job writes a snapshot with its date, the mail links to it, and a later change to the feed leaves the snapshot byte-identical.
- FP-S4 is reworded and its roadmap and briefing steps are green; its reports step names chunk 12.
- The snapshot cannot be rewritten: the append-only trigger refuses an UPDATE on `briefing_item` as `cw_app`, proved in this task's tests too.
- Running the job twice for one week sends one mail and writes one snapshot.
- The mock mailer's outbox holds one mail per eligible member and none for a member without `watch.read` or for a deactivated member.
- No mail body contains an unconfirmed "So what?", proved against a seeded unconfirmed draft.
- Each tenant's job runs with that tenant active; a test proves no row of tenant B reaches tenant A's briefing.
- `BRIEFING_*` are settings with env overrides; the beat entry points at a task that exists.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.home apps.taxonomy apps.watch apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/home/*' (briefing.py >= 95, tasks.py >= 96)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- `@tenant_task` in the worker; `tenancy.activate()` per tenant; no cross-tenant read.
- `record()` on every write, in the same transaction as the write.
- Nothing overwritten: the snapshot is append-only.
- AI output is labelled until confirmed, and an unconfirmed draft never leaves by mail.
- Nothing logs a recipient address or a body (playbook 4.7).
- Every threshold is a setting with an env override.

### c6-roadmap-screen: the roadmap page, quarter by quarter

**Requirements:** HOM-03, FP-03
**Scenarios:** HOM-S4 (`@e2e`), HOM-S6 (`@e2e`)
**Depends on:** `c6-home-api-contract`, `c6-roadmap-backend`, `c6-e2e-seed`, `c5-fe-change-detail`

Build `/roadmap` from `design/screens/tenant-roadmap.html`:
- `frontend/src/features/home/{types,api,hooks}.ts` are created here (key `homefe`) with the roadmap operation only; later screens append theirs.
- `frontend/src/features/home/roadmap-presentation.ts` already exists and decides the pill; extend it only for facts the API now returns, and add no second pill source.
- `frontend/src/components/home/RoadmapScreen.tsx`: the quarter roster, the chips (`all`, `regulatory`, `internal`), and the card that expands in place — inline on a phone, beside the roster on a desktop — showing the pill, the date, the days left as text, and a link to the change page. Expanding navigates nowhere.
- The `internal` chip is shown and answers with the empty state that names where our own deadlines come from; it is not hidden, because the API serves the filter.
- Empty, loading, error and denied states; `roadmap.read` gates the destination, which the registry already carries.
- The `roadmap` message namespace in en and sv; no string literal in JSX.

Un-fixme HOM-S4 and HOM-S6 in `frontend/tests/e2e/home.journey.spec.ts`, signing in through the UI with a passkey, against the real stack.

**Owned paths:**

- `frontend/src/app/(tenant)/roadmap/page.tsx`
- `frontend/src/components/home/RoadmapScreen.tsx`
- `frontend/src/features/home/types.ts`, `api.ts`, `hooks.ts` and their tests
- `frontend/src/features/home/roadmap-presentation.ts` and its test
- the `roadmap` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/tests/e2e/home.journey.spec.ts` (the HOM-S4 and HOM-S6 blocks only)

**Done when:**

- HOM-S4 and HOM-S6 are un-fixme'd and green against the real stack with no mocked API and no injected token.
- The quarter headings and the item order match the API's; the screen sorts nothing itself.
- A card expands in place, and the URL does not change; the change link navigates.
- The pill comes from `presentRoadmapItem` through `Pill`; no tone is chosen in the component.
- Every string resolves in en and sv; `check:messages` and `check:copy-drift` are green.
- Empty, loading, error and denied states render, and the screen reaches real data within 500 ms measured against `next start`.
- `npm run build` passes and the diff stays inside the owned paths.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "HOM-S4|HOM-S6"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Pills only through `Pill`, from a presentation function; six tones, chosen by slot or kind.
- No string literals in JSX; typography roles only.
- `logger` only, never `console.log`.
- Screen copy says what the user is doing: no requirement IDs, no restated invariants.
- E2E signs in through the UI with a passkey and mocks no API.

### c6-calendar-feeds-screen: my calendar subscriptions

**Requirements:** HOM-04
**Scenarios:** HOM-S5 (`@e2e`)
**Depends on:** `c6-home-api-contract`, `c6-upcoming-calendar-backend`, `c6-e2e-seed`, `c6-feed-contract`

Build `/me/calendar-feeds` from `design/screens/tenant-calendar-feeds.html`, in its own feature directory so it runs beside Today:
- `frontend/src/features/calendar-feeds/{types,api,hooks,presentation}.ts`.
- `frontend/src/components/account/CalendarFeedsScreen.tsx`: my subscriptions, a create control with **no** "Include" choice (D-52 removed it: a feed carries the outside world's dates and never the bank's own, so the create body names no field), the address shown once with a copy control and a warning that it will not be shown again, and revoke with a confirm dialog that says the address stops working. The dialog also says what a leaked address shows — which regulatory changes the bank has open work on — because that is the residual risk ADR 0045 accepted on the bank's behalf.
- The screen has to handle two refusals the contract makes plain: `step_up_required` on create, where it asks for the passkey and retries, and the per-person cap, where it tells the person to revoke one first. A row's `lastUsedAt` is what tells them which one to revoke.
- A registry entry under the account parent, so the who panel lists it.
- The `calendarFeeds` message namespace in en and sv.
- Empty, loading, error and denied states.

Un-fixme HOM-S5's journey: subscribe through the UI, fetch the address returned once and assert the ICS body, revoke, and assert the same address answers 404. Declare that 404 where it happens with `apiGuard.allow`.

**Owned paths:**

- `frontend/src/app/(tenant)/me/calendar-feeds/page.tsx`
- `frontend/src/components/account/CalendarFeedsScreen.tsx`
- `frontend/src/features/calendar-feeds/` (all files)
- the `calendarFeeds` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/src/shared/navigation/registry.ts` (one entry)
- `frontend/tests/e2e/home.journey.spec.ts` (the HOM-S5 block only)

**Done when:**

- HOM-S5 is un-fixme'd and green against the real stack.
- The address is rendered once, after creation, and never appears in the list; a reload loses it.
- Revoking removes the row from the list and the address answers 404, declared in the guard with its reason.
- Nothing writes the address to `localStorage`, the URL or a log.
- Every string resolves in en and sv; the states render; the screen reaches data within 500 ms.
- The navigation snapshot changes only by the one new account entry, for the main agent to regenerate and review.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "HOM-S5"`
- `npm run test:e2e -- --grep "@smoke"` (the navigation journey, because the registry changed)

**Invariants:**

- A secret is shown once and never stored by the client.
- Destinations come from the registry and are gated by permission, never by role name.
- No string literals in JSX; pills only through `Pill`.
- E2E declares each expected error where it happens and mocks nothing.

### c6-today-screen: the timeline home

**Requirements:** HOM-01
**Scenarios:** HOM-S1 (`@e2e`), HOM-S2 (`@e2e`)
**Depends on:** `c6-home-api-contract`, `c6-home-backend`, `c6-e2e-seed`, `f03-T48`, `c5-fe-change-detail`, `c4-console-shell`

Replace the Phase 0 placeholder in `frontend/src/components/home/TodayScreen.tsx` with the screen of `design/screens/tenant-today.html`:
- "Coming up": the same short list at 375 px and on a desktop, each row with the urgency dot, the date at tabular numerals and the record's title, linking to the change page; a link to the roadmap with the count.
- The lead card: the change, its pill "Lead" in the `brand` tone, the confirmed "So what?" or the AI label, and its actions — two buttons sharing one row on a phone with the primary on the right (playbook 6.8).
- "Decide now": the counts from `GET /me` (D-23), each linking to the queue it counts, and a count the reader's permissions do not unlock is absent rather than zero.
- The source check in the foot, from `Home.sources`, hidden for a reader without `watch.read`.
- "This week in brief" is **not** built here: `c6-briefing-screen` adds the panel when the briefing exists (plan-wide rule 5).
- Add the roadmap and change operations already in `features/home/api.ts`; append the home operation (key `homefe`).
- The `today` message namespace in en and sv.

Un-fixme HOM-S1 and HOM-S2 in `home.journey.spec.ts`, HOM-S2 at a 375 px viewport asserting the same items as the desktop run.

**Owned paths:**

- `frontend/src/components/home/TodayScreen.tsx`
- `frontend/src/features/home/api.ts`, `hooks.ts`, `types.ts` (its own operations only)
- `frontend/src/features/home/today-presentation.ts` and its test
- the `today` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/tests/e2e/home.journey.spec.ts` (the HOM-S1 and HOM-S2 blocks only)

**Done when:**

- HOM-S1 and HOM-S2 are un-fixme'd and green against the real stack.
- The phone run and the desktop run assert the same item ids in the same order.
- The lead carries the `brand` pill through `Pill`, and an unconfirmed "So what?" is labelled.
- A reader without `watch.read` sees Today with no lead and no source panel, and no request answers 403.
- Nothing on the screen calls `/me/work` or `/reports/*`.
- Every string resolves in en and sv; empty, loading, error and denied states render; Today reaches real data within 500 ms against `next start`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "HOM-S1|HOM-S2"`
- `npm run test:e2e -- --grep "@smoke"` (Today is the landing screen of every smoke journey)

**Invariants:**

- Pills only through `Pill` and a presentation function per record type.
- Permissions decide what renders; the server's 403 stays the enforcer.
- No string literals in JSX; typography roles only.
- Measured against `next start`, never `next dev`.

### c6-briefing-screen: the weekly briefing, on its page and on Today

**Requirements:** HOM-02, FP-03
**Scenarios:** HOM-S3 (`@e2e`), FP-S4 (`@e2e`)
**Depends on:** `c6-home-api-contract`, `c6-briefing-backend`, `c6-e2e-seed`, `c6-today-screen`

Build `/briefing` and `/briefing/[weekStart]` from `design/screens/tenant-briefing.html`:
- The week kicker, the lead feature card, "Also this week", "Coming up", and — on a past week — the snapshot banner saying this is the briefing as it was sent, with its send date.
- The "This week in brief" panel on Today, with its first items and "Read the briefing" (this task owns that edit to `TodayScreen.tsx`, key `today`).
- Append the two briefing operations to `features/home/{api,hooks}.ts` (key `homefe`), and add `briefing-presentation.ts`.
- The `briefing` message namespace in en and sv, beside the mail text `c6-briefing-backend` wrote in `home/mail.py`.
- Seed the emailed snapshot (ruling 17): one seed call in `e2e_seed.py` that runs the briefing builder for the previous week and marks it sent, so the journey can open a briefing as sent without waiting for the beat.

Un-fixme HOM-S3 and FP-S4 in the journeys: HOM-S3 walks Today's panel to the briefing and then to the past week's snapshot; FP-S4 walks the feed, the inventory, the roadmap and the briefing with a scope that excludes "Advice", asserts the advice-only record is absent from each, and shows it again with "Show outside our scope" on the inventory. Its reports step stays named for chunk 12 in the reworded Gherkin.

**Owned paths:**

- `frontend/src/app/(tenant)/briefing/page.tsx`, `frontend/src/app/(tenant)/briefing/[weekStart]/page.tsx`
- `frontend/src/components/home/BriefingScreen.tsx`
- `frontend/src/components/home/TodayScreen.tsx` (the briefing panel only)
- `frontend/src/features/home/api.ts`, `hooks.ts`, `types.ts` (its own operations only)
- `frontend/src/features/home/briefing-presentation.ts` and its test
- the `briefing` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/src/shared/navigation/registry.ts` (one entry)
- `backend/apps/shared/e2e_seed.py` (one seed call)
- `frontend/tests/e2e/home.journey.spec.ts` (the HOM-S3 block only)
- `frontend/tests/e2e/taxonomy.journey.spec.ts` (the FP-S4 block only)

**Done when:**

- HOM-S3 and FP-S4 are un-fixme'd and green against the real stack.
- A past week renders from the snapshot and does not change when a case changes afterwards, proved inside the journey by changing one and reloading.
- Today's panel shows the first items of the running week and links to the full briefing.
- Every string resolves in en and sv, and the mail's keys and the screen's keys do not collide.
- The seeded snapshot is idempotent and anchored to the seed's date anchor, not to the real "today".
- The briefing reaches real data within 500 ms against `next start`.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `set -a; . ./.env.worktree; set +a && cd backend && ./run.sh run python manage.py seed_e2e --settings=config.test_settings` twice
- `cd frontend && npm run test:e2e -- --grep "HOM-S3|FP-S4"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- A snapshot is what was sent; nothing rewrites it.
- The footprint applies to the briefing, and the only way to look outside it is the inventory's, which chunk 3 built.
- No string literals in JSX; pills only through `Pill`.
- The seed is idempotent, deterministic and time-anchored.

### c6-security-review: the chunk-wide sweep

**Requirements:** NFR-04 (the chunk's share)
**Scenarios:** none
**Depends on:** `c6-today-screen`, `c6-roadmap-screen`, `c6-calendar-feeds-screen`, `c6-briefing-screen`, `c6-upcoming-calendar-backend`, `c6-briefing-backend`

A security-review sub-agent reads the whole chunk 6 diff on `main` (`git diff <chunk 6 base>..main` limited to the chunk's paths) and answers, with evidence:
- **The token route.** Can the ICS token reach a log, Sentry, an analytics event, a `Referer` or a stored client value? Is a revoked token indistinguishable from an unknown one, in body and in timing? Is the lookup constant-time enough that it leaks nothing useful? Is the rate limit per token, and can it be used to enumerate?
- **Tenancy.** Does every read on the token route and in the beat task activate exactly one tenant? Do `briefing`, `briefing_item` and `calendar_feed` sit under forced RLS with no bypass, and does `tests_tenant_isolation` cover each?
- **The public list.** Can `GET /upcoming` return anything tenant-derived under any filter, any key scope or any session? Does an API key reach any other chunk 6 route?
- **The mail.** Can an unconfirmed AI draft, a case note, a comment or another tenant's row enter a briefing mail? Does the outbox hold a mail for a member without `watch.read` or for a deactivated one?
- **Permissions.** Is every chunk 6 route gated, with no new `UNGATED_BY_DESIGN` entry? Does a permission-filtered field ever turn into a page-level 403, or a 403 into a silent empty page?
- **Audit.** Does every write have a `record()` row in the same transaction, and no read write one?
- **Simplicity.** Is anything here speculative or overbuilt? Name it for the fix package to cut.

Run the guard suites with it: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write`, `tests_four_eyes`.

**Owned paths:**

- `docs/security/CHUNK6_REVIEW_2026-09-19.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- The report names every finding with a severity, the file and line, and the fix it asks for.
- A critical or high finding blocks the chunk close and is listed for `c6-review-fixes`.
- Findings below high become rows in `HARDENING.md` with the package that will fix them.
- The six guard suites are green on `main`, and the report says so with the command output.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_library_fence apps.shared.tests_route_permissions apps.shared.tests_audit_on_write apps.shared.tests_four_eyes --settings=config.test_settings --noinput`

**Invariants:**

- The review lowers nothing and fixes nothing; it reports.
- A finding is evidence, not opinion: each carries the code that proves it.

### c6-review-fixes: close the review's findings

**Requirements:** NFR-04 (the chunk's share)
**Scenarios:** the chunk's scenarios stay green
**Depends on:** `c6-security-review`
**Security review:** yes (re-run on its own diff)

Fix every critical, high and medium finding of `c6-security-review`, test first, then re-run the review over this task's diff and repeat until nothing at medium or above remains. If the review found nothing at medium or above, close at once with a note in `HARDENING.md` and no code change.

Owned paths are the files the findings name, and nothing else; a finding that needs a file another task owns waits for that task or becomes its own package (parallel plan rule 9).

**Done when:**

- No critical, high or medium finding is open.
- Every chunk 6 scenario that was green is still green, and no test was weakened to get there.
- Findings below medium are rows in `HARDENING.md` with a package named.
- The re-run review is appended to `docs/security/CHUNK6_REVIEW_2026-09-19.md`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run build`

**Invariants:**

- No gate lowered, no test skipped or quarantined, no API mocked in E2E.
- A guard, audit row, permission check or validation is never simplified away.

### c6-chunk-close: the chunk closes

**Requirements:** HOM-01, HOM-02, HOM-03, HOM-04
**Scenarios:** every chunk 6 scenario green; the deferred ones named
**Depends on:** `c6-today-screen`, `c6-roadmap-screen`, `c6-calendar-feeds-screen`, `c6-briefing-screen`, `c6-upcoming-calendar-backend`, `c6-review-fixes`

Close the chunk on `main` (playbook Section 3):
- Run `bash scripts/prepush.sh --all` and the full `npm run test:e2e`.
- Prove no chunk 6 route answers 501 and no chunk 6 journey is fixme, by enumerating the nine operations and the six HOM journeys.
- Prove `backend/scripts/contract_drift_pending.txt` holds no chunk 6 line.
- Add the chunk 6 coverage floors to `backend/scripts/coverage_gate.py`, measured at this close, each with its measured value, statement count and date, and restate the header's measurement note.
- Update `backend/apps/home/app.md` status cells: HOM-01, HOM-02 and HOM-04 `built`; HOM-03 `in_progress` with the note that the regulatory branch is built and our own deadlines join with chunks 8 and 9 (ruling 3). Update `backend/apps/taxonomy/app.md`'s FP-03 note with the two surfaces now covered and reports named for chunk 12.
- Update `docs/plans/IMPLEMENTATION_STATUS.md`: chunk 6 implemented and tested with today's date, `in progress` until a person verifies it, and a notes cell naming what was cut and why (`Home.decideNow`, `Home.standing`, the three internal roadmap branches, recurrences, briefing feedback).
- Update `docs/plans/UI_Implementation_Plan.md`'s chunk 6 rows: `GET /home` gated by `roadmap.read` rather than "any member", "Decide now" fed by `GET /me` counts, the standing panel moved to chunk 8, and each row's status from `designed` to `built`.
- Write the open points into `docs/TODO_FOR_alex.md`: the three non-blocking confirmations above, and q-feed-token's answer as it was taken.
- Add the `Verification_Log.md` row for any provider fact the chunk relied on (the ICS media type and the RFC 5545 fields the feed writes), fetched, not recalled.

**Owned paths:**

- `backend/apps/home/app.md`, `backend/apps/taxonomy/app.md` (status cells and notes only)
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `docs/plans/UI_Implementation_Plan.md` (the chunk 6 rows only)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md` (its own rows only)
- `backend/scripts/coverage_gate.py` (the chunk 6 floors only)

**Done when:**

- `bash scripts/prepush.sh --all` is green on the close commit.
- The full E2E suite is green against the real stack, `@smoke` included.
- No chunk 6 route answers 501, no chunk 6 journey is fixme, and no chunk 6 line is left in `contract_drift_pending.txt`.
- HOM-S7 to HOM-S15 are still skipped or fixme, each with its chunk named, and the requirements-coverage gate is green.
- The status files, the UI plan rows and the two app.md files say what is on `main`, not what was intended.
- The coverage floors are raised to the measured values and none is lowered.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `bash scripts/prepush.sh --all`
- `cd frontend && npm run test:e2e`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Status is the truth of `git log`, not intention: a row moves only when its commit is on `main`.
- No gate lowered to close a chunk; a cut is named, never hidden.
- The owner deploys; an agent never does.
