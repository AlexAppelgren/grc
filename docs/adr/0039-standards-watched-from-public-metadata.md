# ADR 0039 — Standards are watched from public metadata, and only from cleared publishers

**Date:** 2026-09-19 · **Status:** accepted by default (D-45, PRD 0.3 WAT-07, AGT-08; the owner confirms)

## Context

A standard's revision matters to the banks that follow it: a new edition, an
amendment, an accreditation transition rule and the date old certificates stop
being valid. The publishers reportedly reserve text and data mining, and their
pages blocked automated fetches during the research; every one of those facts
is unverified. Source checks hold no URL, hash or snapshot, while source
documents hold snapshots and have no link back to the source, so a flag on the
source kind could not stop a snapshot being kept.

## Decision

One change per edition or amendment, keyed by its stable key: the draft, the
final draft, the publication and the accreditation transition rule are timeline
entries whose change type follows the stage, and the end of the transition is
the key date. Standards-body sources get their own source kind and are
registered inactive with no automated check until the lawyer answers; until
then a library editor enters edition facts as instrument proposals and no case
opens for a revision, because change registration is agent-only. A source
document fetched from a host in `STANDARDS_PUBLISHER_HOSTS` keeps its URL, date
and content hash and no snapshot, and a change carrying a standard's term may
link only documents without a snapshot (422 `licensed_text`). The agent prompt
forbids fetching, quoting, summarising, translating or restating a standard's
text, from a page or from memory, forbids an obligation per clause or control,
and treats a block or a challenge as a failed source check that is never worked
around.

## Consequences

Easier: the case workflow already carries a transition project, and only
tenants that follow the standard match the change. Harder: until a publisher is
cleared, editions arrive by hand, so a revision can be late. To remember: which
publishers may be read automatically is a legal answer, not an engineering one,
and the accreditation forum's documents are the first candidate.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The source kind, the snapshot rule and the change checks | Chunk 5 |
| 2 | The prompt, the definition and the evaluation rows | Chunk 5 |
| 3 | Automated checks per cleared publisher | After the legal answer |
