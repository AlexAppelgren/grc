# No editors: the consolidation of Alex's item 19

Written 2026-09-20, in a cloud session, as documentation and planning only. No product code
changed: the only files under `backend/apps/` and `frontend/` that moved are `app.md` specs and
the skipped scenario stubs CLAUDE.md section 10 requires beside them.

## 1. The decision

Alex, 2026-09-20 (`OWNER_RECOMMENDATIONS.md`, "Alex's answer of 2026-09-20", item 19):

> "Agents do the work, and there should be several agents reading the library. A tenant/bank is
> then responsible for their interpretation. This doesn't change much, just the edit part in
> bleqq, but maybe in the future we would add this on"

> "The agent can work from the queue as well, so who does it doesn't change the function of a
> queue, it's still needed."

It builds on item 3 (a bank's problem report stays in the bank; the watch agents find library
errors themselves) and item 14 (bleqq's agents are platform-owned and platform-run). With those
two, item 19 removes the last staffed human from the library loop.

**What does not change.** A proposal is the only door into the library. Four eyes is a check
constraint that refuses the same principal twice. A person approving steps up with a passkey.
The console queue is built exactly as planned. `library_editor` keeps every permission it has.
Nothing in a bank's own zone changes: applicability, compliance status, the "So what?" and
sign-off stay people's decisions, and the bank answers for its own interpretation.

**What changes.** The second principal may be an independent agent — a different agent definition
**and** a different key from the proposer — reading the same queue through the same route with the
new platform-only scope `proposals:review`, and the record its approval applies carries
machine-confirmed provenance naming both agents instead of a person's verification.

## 2. Every ID assigned

| ID | What | Where it is written | Where it is built |
|---|---|---|---|
| PRD 0.4 | The version bump carrying item 19 | `PRD.md` changelog | — |
| D-48 | Who gives the second pair of eyes, and the shape of it | `docs/DECISIONS.md` | — |
| ADR 0042 | The second pair of eyes on a library proposal may be an independent agent | `docs/adr/0042-agent-approves-from-the-same-queue.md`, indexed in `docs/adr/README.md` | — |
| PRO-S12 | An independent agent confirms a proposal from the same queue (`@integration` `@e2e`) | `proposals/app.md` | `chunk4-T25` (integration); the journey waits for chunk 5 |
| PRO-S13 | The same principal can never both propose and approve (`@integration`) | `proposals/app.md` | `chunk4-T25` |
| INV-S13 | A record an agent confirmed reads as machine-confirmed (`@integration` `@e2e`) | `library/app.md` | `chunk4-T26`; the journey waits for chunk 5 |
| AGT-S14 | The confirming agent is independent of the proposing agent (`@integration`) | `agents/app.md` | chunk 5, with the confirming agent's definition |
| AUD-S8 | An agent's approval is in the audit trail with the agent named (`@integration`) | `governance/app.md` | `chunk4-T25` |
| ID-S27 | The review scope reaches the queue and never a library row (`@integration`) | `identity/app.md` | `chunk4-T25` |
| `chunk4-T25` / `c4-agent-approver` | The review scope, the widened four-eyes constraint and an agent's approval | `CHUNK4_TASKS.md`, `PARALLEL_PLAN.md` §3.3 and §3.3.2 | chunk 4, wave 6 |
| `chunk4-T26` / `c4-machine-provenance` | Machine-confirmed provenance on the record an agent confirmed | `CHUNK4_TASKS.md`, `PARALLEL_PLAN.md` §3.3 and §3.3.2 | chunk 4, wave 7 |
| `proposals:review` | The new platform-only API key scope | PRD §6, `INPUT_DELTAS.md` §2, ADR 0042 | `chunk4-T25` |

`AGT-S13` was **not** used: `CHUNK5_TASKS.md` already reserves it for `c5-library-recheck`, which
has not landed. The agents scenario is therefore `AGT-S14`, and the gap is deliberate.

## 3. Every file changed

**The rules and the requirements**

- `CLAUDE.md` §5 — two invariant lines only: the door line gains the approver clause, the AI
  labelling line gains machine-confirmed provenance. Nothing else in the file moved.
- `PRD.md` — version 0.4 in the changelog; §1's opening paragraph (who decides what, and that a
  bank answers for its own interpretation) and its users list; PRO-01, PRO-02, PRO-03, INV-05 and
  AUD-02; AC-PRO2; §6's platform-roles paragraph.
- `docs/DECISIONS.md` — D-48 added; D-14 narrowed to point at it; the closing note names ADR 0042.
- `docs/adr/0042-agent-approves-from-the-same-queue.md` — new. `docs/adr/README.md` — its row and
  the PRD 0.4 note.
- `docs/inputs/INPUT_DELTAS.md` — §2 gains the `api_key.scopes` departure; §5 gains the proposal's
  reviewer columns and widened CHECK, and the library records' provenance columns.

**The specs and their stubs** (each `@integration` scenario has a skipped test; each `@e2e`
scenario has a `test.fixme`, per CLAUDE.md §10, so `requirements_coverage.py` stays at 0)

- `backend/apps/proposals/app.md` (context, AC-PRO2, PRO-S12, PRO-S13) and `tests_scenarios.py`.
- `backend/apps/library/app.md` (context, INV-S13) and `tests_scenarios.py`.
- `backend/apps/agents/app.md` (context, AGT-S14) and `tests_scenarios.py`.
- `backend/apps/governance/app.md` (context, AUD-S8) and `tests_scenarios.py`.
- `backend/apps/identity/app.md` (context, ID-S27) and `tests_scenarios.py`.
- `frontend/tests/e2e/proposals.journey.spec.ts` (PRO-S12) and `library.journey.spec.ts` (INV-S13).

**The plans**

- `docs/plans/briefs/CHUNK4_TASKS.md` — the header and "what it delivers"; the waves (11 now, with
  `chunk4-T24a` moved to the end); `chunk4-T4` reframed; `chunk4-T14` and `chunk4-T17` reworked in
  place; a new closing section "The approver rework" with `chunk4-T25` and `chunk4-T26` in full.
- `docs/plans/PARALLEL_PLAN.md` — the package count; the name map; two rows in §3.3; the two new
  packages in the §4 wave table (W6, W7); `c4-security-review-1` now waits for both; new §3.3.2.
- `docs/plans/briefs/CHUNK5_TASKS.md` — one default row naming where the confirming agent's
  definition, prompt, key and evaluation belong (`f03-T44`, `f03-T45`, `f03-T46`, `f03-T47`,
  `c5-platform-agent-keys`), and the one sentence of `c5-library-recheck` that said "a second
  editor approves".
- `docs/plans/briefs/CHUNK11_TASKS.md` — new, and deliberately not a task list: chunk 11 is not
  planned, so this file holds the advance note for the session that plans it.
- `docs/plans/briefs/OWNER_RECOMMENDATIONS.md` — item 19 recorded, so the documents citing it have
  something to cite.
- `docs/TODO_FOR_alex.md` — D-14 ticked and answered; a new section with the seven questions below.

**Not touched, on purpose:** `CHUNK9_TASKS.md`, `CHUNK12_TASKS.md`, `CHUNK13_TASKS.md` and
`CHUNK14_TASKS.md` (out of scope by instruction); `FEATURES_0_3_TASKS.md`, whose `f03-T44` to
`f03-T47` are named from `CHUNK5_TASKS.md` rather than edited, because chunk 5's plan is the file
that owns those rows today; `docs/inputs/schema.sql` and `openapi.yaml`, which are inputs and are
departed from through `INPUT_DELTAS.md`, never edited; every `.py` and `.tsx` that is not a
scenario stub.

## 4. Every default taken

Nobody could be asked, so each of these is the documented default and each is reversible.

1. **The scope is `proposals:review`, platform-only.** It names the permission it mirrors
   (`proposals.review`), as every other scope names its area. A tenant key carrying it is refused.
2. **Four eyes is widened in the database, not in Python alone.** `proposal` gains
   `reviewed_by_api_key`, `proposed_by_agent` and `reviewed_by_agent`, and the constraint refuses
   a repeated user, key or agent. The agent columns are denormalised copies of each key's agent,
   because a CHECK cannot dereference a foreign key and two keys of one definition must not be
   able to confirm each other.
3. **Step-up stays a person's gate.** A key cannot step up and no key path ever satisfies one; for
   an agent's decision the scope and the constraint are the whole gate and the audit row's
   assertion id is null. This is the one place where the guard around a library write is thinner
   than it was, which is why `chunk4-T25` carries a security review and amends the fence guard in
   the same edit.
4. **Provenance is columns, not a screen string:** `verified_origin` and `verified_by_agent` on
   the library records, written by `apply.py` from the proposal's two sides.
5. **The re-verification stamp stays a person's act** (INV-06, INV-S8) and still writes
   `verified_by`; a later stamp supersedes the machine-confirmed label.
6. **The console queue is unchanged in scope.** One queue, two kinds of approver: no console
   surface for agents, no approver filter, no second screen. The decided-by line renders a person
   or an agent from the field pair the API already returns for a proposer.
7. **`library_editor` and both E2E editor logins stay**, and so does
   `bootstrap_platform --role library_editor`: that is what "switched on later with no rework"
   means in practice.
8. **J-4 is unchanged** — the golden path still shows a person approving in the console, because
   that path is built and tested end to end. `PRO-S12` is the agent path, and its journey half
   waits for chunk 5.
9. **One confirming agent definition to start**, beside the sweeper and the re-check; "several
   agents reading the library" is already true of those three.
10. **A bank sees both agent names** on a machine-confirmed record, as it already sees an agent
    proposer.
11. **A proposal nobody confirms simply stays open.** No expiry, no escalation, and above all no
    auto-approval, which would remove four eyes.
12. **AC-PRO1 is not weakened and is not reworded away:** no scope changes a library record except
    through an approved proposal, and an agent's approval goes through `proposals/apply.py` like
    everyone else's.
13. **`q-editor-confirm` is untouched.** That open question asks whether one person may confirm a
    suggested classification with no proposal at all. Item 19 neither answers it nor extends it to
    agents, and an agent may not confirm a change's facts while it is open.

## 5. Every question only Alex can answer

All seven are in `docs/TODO_FOR_alex.md` with their defaults. Nothing waits for them.

1. **May a bank see which agent confirmed a fact?** Default: yes, both agents named.
2. **What happens to a proposal no agent confirms within a window?** Default: it stays open for
   ever. A window that auto-approves would remove four eyes and is a stop-and-ask, not a default.
3. **How many independent agents read the library, and is one confirming definition enough?**
   Default: one to start.
4. **Must the confirming agent differ in more than its definition, prompt and key — a different
   model or provider?** Default: no; same model allowed. It also depends on D-07's EU path.
5. **Does J-4 stay the golden path as written, with a person approving?** Default: yes.
6. **Should any proposal kind still need a person?** (Changes what four eyes means.) Default: no
   carve-out. A first-of-its-kind instrument, a retirement, or anything carrying a standard's term
   are the defensible candidates.
7. **Is an agent's approval enough for a record a bank relies on, in front of a vendor review or a
   supervisor?** (Changes what four eyes means.) Default: yes, with machine-confirmed labelling
   and the bank answering for its own interpretation.

## 6. What a reviewer should look at first

- The two amended assertions in `backend/apps/shared/tests_library_fence.py` that `chunk4-T25`
  will rewrite — "a library write needs a signed-in person" and "no scope is named for
  `proposals.review`". They are the written form of the invariant, they are merged on `main`
  (68ac917), and the task amends and strengthens them rather than deleting them. If anything in
  this consolidation is wrong, it is most likely there.
- CLAUDE.md §5's two edited lines, against the ADR: the invariant text and the decision must say
  the same thing, and both must still forbid an agent editing the library directly.
- PRO-S13's Gherkin: it is the scenario that has to fail if the widened constraint is ever
  narrowed back to users.
