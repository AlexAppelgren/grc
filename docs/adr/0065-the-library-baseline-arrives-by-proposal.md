# ADR 0065 — The library's starting inventory arrives by proposal, as a researched baseline

**Date:** 2026-09-30 · **Status:** accepted (Alex, 2026-09-30: "build up the inventory for everything relevant as of today", market abuse included; D-118; PRD PRO-01, PRO-02, INV-01, INV-03, INV-05, WAT-01; follows ADR 0014, ADR 0041, ADR 0054, ADR 0058)

## Context

A deployed library held reference data only: languages, jurisdictions, vocabularies,
taxonomy terms, authorities and agent definitions. The sample library
(`prototype_data.json`) loads only into demo and E2E databases, its text is sample wording,
and ADR 0041 seeds one standard for tests. The first bank would set its regulatory scope
against an empty inventory, and search, Ask and the footprint preview would answer nothing.

The watch agents cannot fill it. The sweeper looks for new or changed documents on its
registered sources and proposes a duty only where a document states a rule the library
lacks, so law that is not new on an index page is never swept. Each run is capped
(`WATCH_RUN_MAX_*`), the source registry is empty on a new deployment, and the real runner
waits for D-07. Market abuse, which every Nordic bank with listed securities or a trading
desk answers to, was not named anywhere in the library's scope.

## Decision

1. **A researched baseline, held as reviewed data.** `backend/apps/library/baseline/` holds
   one file per tranche (EU by area, then Sweden, Denmark, Norway and Finland), each entry
   a `new_instrument` or `new_obligation` payload exactly as `POST /proposals` takes it,
   with the official page it was read from. It covers what was in force, or adopted and
   applying later, on the research day, 2026-09-30, market abuse included. Every fact is
   logged in the Verification log. A plain-Python checker and the backend suite hold every
   entry to the proposal door's own rules before any deploy.
2. **Filed through the proposal door, never the seed door.** A sixth platform definition,
   `library-baseline` (kind `backfill`, draft, manual, calling no model), files the entries
   the library neither holds nor has open. `manage.py file_library_baseline` is its runner:
   it opens runs of the agent with no key through the one opener, hands them to no runner,
   files at most `WATCH_RUN_MAX_PROPOSALS` per run and closes each through the runner-event
   path. Duties are filed on the call after their instrument is approved, because a duty
   names an instrument the library holds.
3. **A second, independent principal approves each entry.** Today that is a person in the
   console with a passkey, and the record reads confirmed by a person. Once
   `library-confirmer` is published and its runner is live, it works the same queue and the
   record reads machine-confirmed, naming both agents. `proposal_four_eyes` refuses
   `library-baseline` as its own reviewer either way.
4. **Where a duty sits.** An EU regulation's duties sit under it; a directive is an
   instrument without duties, and its duties sit under each country's implementing act. A
   government ordinance fits no instrument level and waits for one; a standard waits for
   the legal answer on standard titles (ADR 0041).
5. **Market abuse is securities law.** MAR, CSMAD, their delegated and implementing acts,
   ESMA's guidelines and each country's supplementary and criminal provisions carry the
   regime `securities`. No regime is added, so every bank that follows securities law sees
   them at once.
6. **Keeping it current is the agents' job.** Each watch run re-checks the records of the
   sources it checks and proposes a correction where one has drifted (WAT-01, D-50), and
   registers what is new. A later tranche is a new file and another call of the command.

Rejected: writing the baseline through the seed door, which would put facts in the
library with no second principal and reopen the door H16 closed (ADR 0058); a catch-up
sweep, which the sweeper's design and budget cannot do and its runner cannot yet run;
and a batch kind for new records under PRO-04, a larger change to the approval path that
is worth building only if approving one proposal at a time proves too slow.

## Consequences

Easier: a bank's first scope setting shows real law, every record carries its source and
its approver, and the baseline is reviewable as a diff. Harder: someone approves several
hundred proposals, in two passes, before the library is full; until the confirmer runs,
that someone is a person. To remember: the baseline is AI-researched, so it is AI output
until a principal other than `library-baseline` approves it; a rejected entry is not filed
again until its file changes; and the research day is a snapshot the watch keeps moving.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The corpus, the definition, the command, the checker and the suite | This change |
| 2 | Sources registered for every authority the baseline names, so the sweeper checks them | Alex, in the console, after the test deploy |
| 3 | Government ordinances with a level of their own; sanctions, if in scope | As Alex decides |
