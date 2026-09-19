# ADR 0011 — Evidence and exports stream through permission-checked endpoints

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-11; nothing for the owner to confirm)

## Context

`docs/inputs/openapi.yaml` designed presigned download links for evidence and
exports. A presigned link is a bearer capability: once issued it can be
forwarded, it is not re-checked against permissions, and the download leaves
no audit row of who fetched it. Every evidence download is a fact an auditor
may ask about (CAS-05, REP-02).

## Decision

Downloads stream through the API: one permission check and one audit row
per download, the file fetched from the private bucket by the server. The
presigned download operations and `DownloadLink` are removed from the
contract (`INPUT_DELTAS.md` §4). Uploads may stay presigned as long as the
malware scan and the content hash happen before the file is visible.
Deliberately not done: signed URLs with short expiry, because they still
skip the audit row.

## Consequences

Easier: "who downloaded this" is always answerable, and another tenant's
evidence answers 404 like any other record. Harder: large files pass through
the API process, so streaming responses and a size allow-list matter. To
remember: `scripts/contract_drift.py` expects this difference to be recorded
in `INPUT_DELTAS.md`, which it is.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | `storage.py` seam with local and S3 backends | Phase 0 |
| 2 | Evidence upload, scan, hash, streamed download | Chunk 9 |
| 3 | Export downloads | Chunk 12 |
