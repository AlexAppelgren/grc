# Private sources and standard editions: a design, not a plan

**Design only. Nothing here is built, and nothing here is a decision.** It is the
design a paused session wrote before any code, recorded in the body of commit
`dbe58c6` on `origin/claude/r1-watch-sources-editions` (based on
`origin/claude/r1-integration` at `20c931b`). That branch is never merged; this page
is where the design lives on main, so the next session starts from it rather than
from nothing.

Where each half goes:

| Half | Scenario | Where it is built | What this page is to it |
|---|---|---|---|
| A new edition of a standard is one change, and only its followers see it | WAT-S10 (WAT-02, WAT-07, CAS-01, AC-FP3) | R1, in this order: FP-01's opt-in rule (FP-S17; `FEATURES_0_3_TASKS.md` f03-T25 to f03-T28), the first standard in the fixture (FP-S16's integration half; f03-T35), then the watch rules for regime and standards (WAT-S10 and WAT-S11; f03-T43, chunk 5) | Input. Those tasks win where they differ |
| A tenant requests a source, and private sources stay private | WAT-S8 (WAT-06) | **R3**, chunk 13: `c13-private-sources`, `c13-private-source-visibility`, `c13-private-source-runs` and their screens in `CHUNK13_TASKS.md` | Input. Not R1 work: WAT-06 is an R3 Should, and its runs wait on Alex (chunk 13's open question 1) |

## WAT-S10: a standard's new edition, seen only by the banks that follow it

It rests on FP-01's opt-in rule, which was not built when this was written (FP-S16
and FP-S17 were still skipped).

- **Taxonomy.** Add `TermDimensionKind.OPT_IN`, with its reason in
  `shared/kinds.py`. `matching.restricting_dimensions()` returns a frozenset
  subclass that also carries which dimensions are opt-in. `in_footprint()` takes it
  as a required keyword, raises `TypeError` without it, and returns False when a
  record has an opt-in term the scope does not name. This way
  `apps/library/reading.py`'s `outside_reasons()` needs no edit.
- **The SQL mirror.** A new taxonomy migration replaces `taxonomy_in_footprint`:
  join on `(d.restricts_footprint OR d.kind = 'opt_in') AND d.active`, and
  `WHERE d.kind = 'opt_in' OR EXISTS(...)`. The reverse SQL repeats the 0001 text.
- **Seeds** (`taxonomy/seeds`, `_EXTRA_DIMENSIONS` and `_EXTRA_TERMS`): the dimension
  `standard` ("Standards followed" / "Standarder vi följer", opt-in, restricts) and
  the term `iso_iec_27001`.
- **Nothing else moves.** Case fan-out, recompute, the feed and the roadmap follow
  with no edits, because they all go through `restricting_dimensions()` or the SQL
  function.
- **Frontend.** In `footprint-presentation`, an empty opt-in group reads "None
  followed" (a new en and sv key), and `narrowedGroups()` never lists an opt-in group.
- **Tests.** Opt-in cases in `tests_matching` for the pure rule and the SQL mirror.
  `test_wat_s10` registers through `POST /changes`, then merges the same stable key
  again with "Published". Tenant A holds `regime:ai_ict` and the standard; tenant B
  holds `regime:ai_ict` only. It checks exactly one case each, `footprint_match` true
  for A and false for B, and the change in A's default feed and roadmap and in
  neither of B's. The taxonomy scenario that lists the restricting set (about line
  792 of `taxonomy/tests_scenarios.py` at `20c931b`) gains `standard`.
- **E2E seed.** Add `standard:iso_iec_27001` to tenant A in `EXPECTED_FOOTPRINTS`.
  In a separate block, add an "ISO/IEC 27001 amendment" change (regime `ai_ict` plus
  the standard term, key date at least 60 days after the tenant-local today, urgency
  not `act_now`), so HOM-S1's lead and first Coming-up item do not move. Tenant B
  holds no `ai_ict`, so the E2E check is weaker than the integration test. STD-06
  said no E2E tenant would hold the term, so FP-S16's journey has to start by
  removing it.

## WAT-S8: a bank asks for a source, and a private source stays in the bank

D-57 and owner item 10 apply. **R3 (WAT-06, chunk 13).** The design below differs
from `CHUNK13_TASKS.md` in three places, and chunk 13's tasks must settle all three
before any code:

- **The request.** This design makes the private `source` row itself the request.
  Chunk 13 plans a `SourceRequest` with a chosen visibility, private or shared.
- **Who decides.** In this design, as in WAT-S8, the private source exists as soon as
  the bank asks and the address passes its checks. Chunk 13's
  `c13-private-source-visibility` creates the owned `Source` only from an approved
  private request, and it names no approver.
- **The route.** This design serves `/private-sources`, and chunk 13 serves
  `/source-requests`.

The design itself:

- **One row, no second table.** The request is the private `source` row itself:
  `owner_tenant` set, kind `tenant_private`, and `source`'s existing mixed
  row-level security keeps it in the bank's zone ("respect the zone column").
- **Names.** Migration `watch 0002_private_sources` drops the global unique on
  `source.name` and adds `UNIQUE(name) WHERE owner_tenant IS NULL` and
  `UNIQUE(owner_tenant, name) WHERE owner_tenant IS NOT NULL`. Otherwise a name clash
  would tell a bank that another bank has a private source.
- **Routes.** `POST` and `GET /private-sources` (`requestPrivateSource`,
  `listPrivateSources`), session only. `POST` is gated by
  `require_any(agents.manage, proposals.create)` (D-57); `GET` by `watch.read`,
  answering `WatchSourceCoverage` rows.
- **Address checks.** https only; no userinfo; a public host (not an IP literal, not
  a special or internal name, and every `getaddrinfo` address `is_global`; tests
  patch `getaddrinfo`); not a host on `STANDARDS_PUBLISHER_HOSTS` (a new setting);
  and not an existing shared source (409 `source_already_watched`, naming it).
- **Cap.** `PRIVATE_SOURCES_MAX` (20) per bank, 409 `private_source_limit_reached`.
  One tenant audit row through `record(tenant_id=...)`. The new codes go in
  `shared/errors.py`'s `STATUS_BY_CODE`.
- **The shared registry never lists it.** `keys.sources_out` and `coverage_rows`
  filter `owner_tenant IS NULL`, so the shared registry and coverage never list a
  bank's private source, not even to that bank.
- **The write door.** Inside a bank's zone, `watch_write()` refuses every watch table
  except `source` (checked with `tenancy.database_tenant_id()` on entry). Run every
  suite that uses the watch builders, because a test might build a change while a
  tenant is active.
- **The fence.** In `tests_library_fence.py`, in its own block: add
  `requestPrivateSource` to `WATCH_WRITING_ROUTES`, with a logic-gate node in
  `WATCH_ROUTE_GATES`. `wrong_watch_gate` must accept any node gate, not only
  `CHANGE_WRITER`. Add a test that the gate names tenant permissions only, that the
  route takes a session only, and that it reaches `watch_write` alone.
- **Screen.** An "Our private sources" section on the `/watch` Coverage tab, reusing
  `SourceCoverageRow`, with a "Request a source" modal (Name, Address) that shows
  `ProblemAlert` on a refusal.

**Deferred, needing Alex.** A change registered from a private source, and the host
re-check at the start of each run. No principal can run a private source in R1:
tenant runs are refused (`tenant_agents_not_available`), and a platform run cannot
see a bank's private rows without a new zone escape. The runner approval is chunk
13's open question 1 (`PRIVATE_SOURCE_RUNNERS_APPROVED`), and `c13-private-source-runs`
already plans for it. The design's own note to set WAT-06 to `in_progress` in
`watch/app.md` is not taken: nothing of WAT-06 is built.
