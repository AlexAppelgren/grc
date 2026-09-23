# Security review: chunk 6, the timeline home, briefing, roadmap and calendar feed (2026-09-23)

## Question

Do the chunk 6 surfaces — `GET /home`, the weekly briefing (live, snapshot and mail),
`GET /roadmap`, `GET /upcoming`, the four calendar-feed operations and the calendar-feeds
screen — hold the product invariants of PRD HOM-01 to HOM-04, D-52 and ADR 0045: two zones,
nothing overwritten, audit on every write, tenant content never in a log, a mail or a
calendar client it was not meant for, and a legal date never printed more exactly than it
was stated (INV-S10)?

## Standard

The same as the chunk 1 review (`CHUNK1_AUTH_REVIEW_2026-09-19.md`): OWASP ASVS 5.0.0,
chapters V4 (API), V7 (session and token handling, for the feed token), V8 (authorization),
V14 (data protection) and V16 (logging), read against the product invariants in CLAUDE.md
section 5. RFC 5545 §3.1 and §3.3.11 for the iCalendar document.

## Method

1. Read `CLAUDE.md`, `docs/CONVENTIONS.md`, `backend/apps/home/app.md`, D-52 and ADR 0045.
2. Read every production file under `backend/apps/home/` (`api.py`, `feed.py`,
   `calendar.py`, `roadmap.py`, `briefing.py`, `logic.py`, `mail.py`, `tasks.py`,
   `models.py`, `schemas.py`, both migrations), the pieces they lean on
   (`config/api.py` exception handlers, `apps/shared/tenancy.py` `identity_lookup` and
   `tenant_task`, `apps/shared/sentry_scrub.py`, `docker-entrypoint.sh`'s access-log format,
   `identity/session_logic.py` `resolve_access_token` and `build_principal`), and on the
   frontend `features/calendar-feeds/*`, `components/account/CalendarFeedsScreen.tsx`,
   `components/home/{RoadmapScreen,ComingUpPanel}.tsx` and `shared/utils/format.ts`.
3. Traced `calendar_ics`'s automatic revoke through `ATOMIC_REQUESTS`: the `ProblemError`
   it raises is answered by Ninja's handler inside the view, so Django's request atomic
   block sees a normal return and commits; only `handle_unexpected` marks a rollback.
4. Ran the home suite with the guard suites, then ruff, mypy, the compliance lint,
   requirements coverage, the API documentation gate and contract drift, and the frontend
   lint, typecheck, unit tests, message and copy-drift checks.

## Verdict per area

| Area | Verdict | Evidence |
|---|---|---|
| The token route, `GET /calendar/feed.ics` | **Holds.** 256-bit secret shown once, kept as a 16-character prefix beside its SHA-256, compared in constant time; unknown, malformed, revoked and expired all leave through one `_no_such_feed()`; the answer is `private, no-store`; the token rides in the query, which the gunicorn access format (`%(U)s`) and the Sentry scrubber (`query_string` redacted) both drop; the lookup runs inside `identity_lookup()` and the tenant is activated before any tenant row is read. | `tests_feed.MintingAnAddress`, `FetchingTheCalendar.test_unknown_revoked_expired_and_malformed_all_answer_one_404`, `test_no_token_prefix_or_secret_reaches_a_log_line`, `test_a_refusal_never_echoes_the_token_back`, `test_a_flood_on_one_address_never_refuses_another`; `apps/shared/tests_no_query_in_logs.py`; `tests_rls.IDENTITY_LOOKUP_TABLES`. |
| The automatic revoke under `ATOMIC_REQUESTS` | **Holds.** The revoke and its system-actor audit row commit before the 404, because the `ProblemError` never leaves the view. `assert_stopped` runs in a `TestCase`, whose request savepoint would roll the stamp back if the exception escaped, so reading the stamp after the 404 proves it. | `tests_feed.TheServerStopsASubscriptionItself` (owner leaves, loses `roadmap.read`, enrolled again here or in another bank, idle). |
| Subscriptions: list, create, revoke, the cap | **Holds.** `roadmap.read` on each; own rows by the query itself; another person's id answers `not_found`; create needs a recent sign-in or a fresh assertion; the cap counts live rows after stopping idle and pre-re-enrolment ones, under a lock on the caller's membership; every write is audited and no audit row carries the address. | `tests_feed.TheListAndTheCapStopWhatNoLongerWorks`, `TheCapHoldsUnderConcurrency.test_a_second_subscribe_waits_for_the_first`, `MintingAnAddress.test_creating_and_revoking_each_write_one_audit_row_that_names_no_address`, `test_another_persons_subscription_is_neither_listed_nor_revocable`; `tests_route_permissions`, `tests_audit_on_write`. |
| The feed's kind and precision filters | **Holds.** `calendar_items()` reads the regulatory branch alone and only day-precision dates; each event is five library properties, the UID is the stable key and every text value is escaped and folded. | `FetchingTheCalendar.test_the_calendar_is_the_roadmaps_regulatory_items_stated_to_the_day`, `test_a_date_the_source_gave_as_a_quarter_stays_off_the_calendar`, `test_an_event_carries_the_librarys_facts_and_no_judgement_of_the_banks`, `test_a_stable_key_that_is_not_a_slug_adds_no_line_to_anyones_calendar`. |
| Tables `briefing`, `briefing_item`, `calendar_feed` | **Holds.** Tenant tables under forced RLS for `cw_app`; `briefing_item` append-only by trigger; `calendar_feed` is the fifth identity-lookup table and nothing else widens it. | `apps/shared/tests_rls.py`, `tests_tenant_isolation.py`, `tests_briefing.TheSnapshotIsWhatWasSent.test_the_database_refuses_to_rewrite_a_sent_briefings_items`. |
| The briefing, live and snapshot | **Holds.** `watch.read`; a non-Monday, an unsent week and another bank's week answer one 404; the snapshot fixes selection and order by `rank`. | `tests_briefing.TheRunningWeek`, `TheSnapshotIsWhatWasSent`. |
| The briefing mail's content | **Holds.** Library titles and a *confirmed* "So what?" only, one recipient per active member whose roles carry `watch.read`; the audit row names the week and counts, never a title or an address; nothing is logged. Delivery reliability is H21 below. | `tests_briefing.TheWeeklyJob`, `AnUnconfirmedDraftNeverLeavesByMail`. |
| `GET /upcoming` | **Holds.** Library rows only, never joined to a case; a key needs `upcoming:read`; two banks read byte-identical answers. | `tests_calendar.UpcomingHoldsNoBank`. |
| The calendar-feeds screen | **Holds.** The address lives only in the create mutation's answer (`gcTime: 0`), is dropped by `reset()`, reaches no storage, URL or `logger` call, and only Done closes the dialog. | `CalendarFeedsScreen.test.tsx`. |
| Legal dates on the roadmap and in Coming up | **Did not hold; fixed** (M1). | Below. |

## Findings

Severity: critical / high / medium / low / info. Status: fixed / open (with where it gets
fixed) / accepted.

| # | Sev. | Where | Finding | Status |
|---|---|---|---|---|
| M1 | medium | `apps/home/schemas.py` `HomeRoadmapItem`, `RoadmapScreen.tsx`, `ComingUpPanel.tsx` | Carried over from `calendar-feed-hardening` (ND1). The roadmap item carried `date` with no precision and both screens rendered `formatDate(item.date)` with a days-left count, so a date the source stated as a quarter was printed as the day it happens to be stored on and counted down to it. A bank plans work against that date, and printing a day nobody published breaks HOM-03 and INV-S10. `roadmap.py` read the precision for the calendar alone. | **Fixed.** `HomeRoadmapItem.datePrecision` (documented, `day`/`month`/`quarter`/`year`, the change's own library column); `roadmapWhen()` in `roadmap-presentation.ts` renders it with `formatPartialDate` and counts days only for a date stated to the day; the roadmap card, its detail and Coming up all read it. Tests: `tests_roadmap.RoadmapContents.test_a_row_carries_its_dates_precision_so_a_quarter_never_reads_as_a_day`, `RoadmapRoute.test_a_reader_gets_the_roadmap_in_camel_case_with_its_roster`, `roadmap-presentation.test.ts` (`roadmapWhen`), `RoadmapScreen.test.tsx` and a new `ComingUpPanel.test.tsx`, each with a quarter-precision item. The E2E seed already held one (WAT-S2's change, key date 1 January 2027 stated as a quarter), which the roadmap printed as "1 Jan 2027"; its card now reads "Q1 2027", so HOM-S4 finds the quarter headings by role rather than by text. |
| L1 | low | `apps/home/feed.py` `_subscription_ended` | A session is refused for a person whose account status is `deactivated` (`session_logic.resolve_access_token`), but a feed checks only the membership. No production code sets that status today, so nothing is reachable now. | **Open**, HARDENING H19. |
| L2 | low | `apps/home/feed.py` `calendar_ics` | The only limit on the unauthenticated route is per token prefix, so a client presenting a new random prefix each time gets a fresh bucket: an unbounded stream of one indexed read each. | **Open**, HARDENING H20. |
| L3 | low | `apps/home/tasks.py` | The weekly mails go out synchronously inside the snapshot transaction, and the hourly beat matches one hour a week. A relay failure rolls the snapshot back, but the next matching hour is a week later and snapshots the next week, so the failed week is never sent (the docstring says the next run retries); a failure part-way has already delivered mails a retry would repeat. Availability of HOM-02, no exposure. | **Open**, HARDENING H21. |
| L4 | low | `apps/home/roadmap.py` `_cases` | An item stays while `key_date >= today`. The day a month- or quarter-precision date is stored on is whatever the proposer supplied, so such an item can leave the roadmap and Today while its month or quarter is still running. | **Open**, HARDENING H22. |
| I1 | info | `config/api.py` | `ProblemError` and `ValidationError` answers commit the request's writes; only an unexpected exception rolls back. The feed's revoke-then-404 relies on it on purpose, and no home route writes before a refusal it did not mean to keep. | **Accepted, noted.** |
| I2 | info | `apps/home/tasks.py` `_recipients` | Recipients are chosen by `roles__permissions__contains=[watch.read]` rather than through `build_principal`, which also intersects with `TENANT_PERMISSIONS` (H2); `watch.read` is a tenant permission, so the two answer alike. | **Accepted.** |

## Gates run

Backend: `apps.home` with `apps.shared.tests_rls`, `tests_tenant_isolation`,
`tests_route_permissions` and `tests_audit_on_write` (195 tests, 8 skipped as pending
scenarios, 0 failures); ruff; mypy; `compliance_check.py --all`; `requirements_coverage.py`;
`api_docs_gate.py` (0 outside the ledger, 0 stale); `contract_drift.py` (0 unexplained).
Frontend: lint, typecheck, the home and account unit tests, `check:messages`,
`check:copy-drift`. E2E: HOM-S1 to HOM-S6.
