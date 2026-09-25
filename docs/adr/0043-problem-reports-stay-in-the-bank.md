# ADR 0043 — A problem report stays inside the bank, and the watch agents find library errors

**Date:** 2026-09-20 · **Status:** accepted (D-50, Alex 2026-09-19; PRD 0.4 PRO-03, AUD-03, ADM-02)

## Context

Every earlier source assumed the platform console reads banks' problem reports:
PRO-03, AUD-03, ADR 0014, `AUD-S5` and the console card. The recommendation
prepared for this decision built a narrow read window on `problem_report` for
library editors. Alex answered otherwise: bank comments belong to the bank, and
the watch feature should find these deviations on its runs. A problem report is
a bank's own words about a record, written by a named person, and the tenant
fence exists so that such words never leave.

## Decision

A problem report stays inside the bank that filed it. There is no platform read
window on `problem_report`, and no bleqq editor, other bank, agent or model
reads a report. The console loses its problem-report surface. A bank sees its
own reports and their status, and a report never leaves the tenant zone: not to
a log, to Sentry, to an outbox topic a webhook or SIEM stream carries, or to a
model endpoint.

A library error is found instead by the watch agents. On every run, a watch
agent re-checks the library records that came from the sources it checked
against those sources, and where a record no longer matches it proposes a
correction through the normal proposal door: a proposal a second library editor
approves under four eyes, never a direct edit. The re-verification stamp stays
the one write outside a proposal.

Deliberately not done: the read window on named tables and columns, reports as
library rows without row-level security, and a support grant per bank before
its reports can be read.

## Consequences

Easier: the tenant fence keeps one fewer exception, the console keeps one fewer
surface, and nothing a bank writes about a record can reach another bank.
Harder: a bank that spots an error gets no answer from bleqq about that report,
and the correction arrives only as the library changing, on the agent's
schedule. The re-check costs one comparison per record per source check, which
the run budget must carry. To remember: the report dialog must say plainly that
the report stays in the bank and that the library is corrected by the watch, so
nobody waits for a reply; and whether bleqq's own editors may read reports is
still open (D-50).

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The report stays tenant-only: no console route, no platform read, the dialog's wording | Chunk 4 tail |
| 2 | The watch run's re-check of the records of every source it checks, and the correction proposal | Chunk 5 |
