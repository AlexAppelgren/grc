# ADR 0058 — The database refuses a library write that never entered a door

**Date:** 2026-09-23 · **Status:** accepted by default (hardening H16, fixed before R1 closes at Alex's request of 2026-09-23; D-8x `h16-library-db-policy`; PRD PRO-01, NFR-01, AC-PRO1; follows D-64, D-65 and D-78)

## Context

The library is shared by every bank, and an approved proposal is the only door into
it, with the re-verification stamp the single exception (PRO-01, INV-06). Until now
that rule lived in Python alone: `library_write()` refuses a `LibraryModel` save,
update or delete outside it, an AST guard keeps `library_write()` to the proposal
applier, the watch door and the reference seeds, and the watch and index doors narrow
what their own callers reach (D-64, D-65).

Python stops where Python stops. The base `QuerySet.update()`, a collector's fast
delete and raw SQL never pass through `LibraryModel.save()` or the fenced queryset.
In the database, most library tables hold no tenant and so carry no row-level
security at all, and `instrument` and `obligation`, mixed on `owner_tenant_id`, still
check a write with their read rule (`library_fence=True` in `rls_operations`). So a
bank's session, running as `cw_app`, could change or delete a shared record through
any path the fence does not see. That is H16.

H16 first proposed splitting the two mixed policies. The split alone would have
covered two tables of about fifty and refused every library write made with a tenant
activated — which the reference seed, the E2E seed and the test builders all do —
unless `library_write()` first learned the zone of every row it writes.

## Decision

A second layer in the database, in the shape of the append-only guard: one trigger
function, attached to every library-zone table, and a transaction-local setting the
sanctioned writers set.

- **The setting.** `cw.library_door` names the door a write comes through:
  `proposal`, `reverification`, `seed`, `watch` or `index`. `library_door()` in
  `apps/shared/tenancy.py` sets it with `set_config(..., true)` and puts back the door
  it found, so doors nest: an approval's proposal door opens the index door for its
  rebuild and gets its own back afterwards. The setting lasts only as long as its
  transaction, so `library_door()` runs its block in one — its own, or a savepoint
  inside one — and a block that raises rolls the savepoint back, which undoes the
  setting with it. `library_write()` opens it with the door its caller names
  (`proposal` from `apply`, `reverification` from `apply_reverification`, `watch` from
  `watch_write()`, and `seed` by default for a reference seed or a test builder);
  `index_write()` opens `index`.
- **The trigger.** `cw_library_door_guard()` (shared 0008) runs BEFORE INSERT,
  UPDATE, DELETE and TRUNCATE, once per statement, on every library-zone table. It
  refuses the statement unless the setting names one of the doors the table accepts,
  which are the trigger's own arguments:
  - the inventory and the library vocabularies: `proposal`, `seed`;
  - `obligation` and `verification`: those two and `reverification` — the stamp reaches
    nothing else;
  - the seven watch tables: `watch` only (D-64);
  - `search_chunk`: `index` only (D-65);
  - the library app's reference rows, `language`, `jurisdiction` and
    `jurisdiction_label`: `seed` only. They are not `LibraryModel`s, so the Python fence
    never saw them, and every bank reads them; no proposal writes them (the jurisdiction
    list is not proposable), and `seed_languages()` and `seed_jurisdictions()` open the
    seed door through `library_write()`.

  Per statement, so a write that would touch no row is refused as a write, and the
  check costs one call however many rows a rebuild or a seed writes. The refusal names
  the operation, the table, the door that was open and the doors the table accepts.
- **The schema owner passes**, recognised by `session_user` exactly as the append-only
  hatch recognises it (shared 0005): never `current_user`, which a SECURITY DEFINER
  function or a cascade changes. Migrations, the E2E seed, the test runner's own
  connection and tenant exit run as the owner. The retention purge does not: `cw_app`
  calls its SECURITY DEFINER function (ADR 0046), so its `session_user` stays `cw_app`.
  It deletes no library row today; a purge that ever reached one would be refused here.
- **Completeness is a test, not a list to remember.** `apps/shared/tests_library_db_guard.py`
  reads every `LibraryModel` table, `search_chunk` and the reference tables from the app
  registry, not from the migration, and fails for a table without the trigger or with the
  wrong doors, and for any row without a tenant in a library-zone app that is none of
  those. A library table created later attaches it in its own migration with
  `library_door_trigger_operations()`.
- **Every real writer is proven as the app role.** The same guard files and approves one
  proposal of every `ProposalKind` through `proposals.logic`, and calls an entry point of
  every module allowed to open the watch door, on the `cw_app` connection. A kind or a
  watch step with no proof there fails it, so a writer that names the wrong door fails the
  backend suite and not only E2E.
- **Who may name a door.** The compliance lint's `library-door` rule refuses the
  setting's name, its constant and `library_door()` anywhere but the tenancy module,
  the index door, the migration helpers, migrations and tests; the library fence pins
  which one function names each of `proposal`, `reverification`, `watch` and `index`,
  and keeps `seed` — `library_write()`'s default and the widest door — to the reference
  seeds' directories, whether a call names it or takes it by default.

The Python fence is untouched. This is a second layer behind it, not a replacement.

## What the setting does not stop

- **Code that sets the setting itself.** `cw_app` may set any setting it likes; nothing
  short of a superuser can forbid that. The trigger refuses a write that reaches the
  database outside a door — an ORM call that bypassed the fence, raw SQL, a cascade, a
  bank session's stray statement — not a statement that sets `cw.library_door` first.
  What keeps the setting in the doors is review, the lint rule and the AST guards, the
  same line `cw.maintenance` held before H11 moved it into the database.
- **Which row a door writes.** A door opens tables, not rows or zones. Inside the
  proposal door a statement may write any shared inventory row; `instrument` and
  `obligation` still check a write with their read rule. What reaches the proposal
  door is the approval itself: four eyes in a check constraint, a step-up for a person.
- **Who is on the other side of a door.** The setting carries no identity. That a
  person with a fresh passkey or an independent agent approved stays the proposal
  logic's and the constraint's to prove.
- **The schema owner.** Anything that authenticates as `cw_migrator` passes. That is the
  migration path, and the owner's credentials are the deploy's, never the app's.
- **Tables outside the library zone.** Tenant tables are row-level security's, and the
  platform's own tables (users, roles, the proposal queue) are not library rows.
- **The rest of the unit test suite.** Its `default` connection is the schema owner, so
  outside the guard's cw_app tests the trigger lets it through. The guard proves every
  proposal kind and every watch step as `cw_app`; a branch of one of them the guard does
  not take, or a writer outside both, shows first in the E2E run, whose server runs as
  `cw_app`, and in the cold-start journey, which seeds as `cw_app`.

## Consequences

Easier: a shared record can no longer be changed from a bank's session by any path the
Python fence does not see, and a door can reach in the database only the tables it may
reach in Python; the watch door and the index door are narrowed twice.

Harder: every door runs its block in a savepoint, a handful of round trips per door
opened; a new library table needs its trigger in the migration that creates it, a new
writer needs a door the table accepts, and a new proposal kind or watch step needs its
proof as the app role in the guard before the suite passes.

To remember: the door is a declaration, not a credential. It turns an accidental write
into a refused one; it does not turn a deliberate one into a refused one.
