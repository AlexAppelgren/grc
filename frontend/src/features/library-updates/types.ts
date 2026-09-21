// The tenant's library-updates feed: what changed in the shared library since
// this reader's bookmark, filtered to their footprint (design/screens/tenant-library-updates.html;
// PRO-03, INV-04, FP-03, chunk4-T13b).
//
// GET /library-updates is chunk4-T13b's route and is not on `main` yet (the
// dependency this screen's own task, chunk4-T19, names). These shapes are
// this screen's best-effort contract from that task's own description in
// docs/plans/briefs/CHUNK4_TASKS.md — kind, applied time, effective date, the
// library record touched, filtered to the footprint unless
// `outsideFootprint=true`, grouped by the tenant-local day — hand-written
// rather than generated because `bash generate-types.sh` has nothing to read
// yet. When T13b lands, reconcile this file against the real
// `components['schemas']` shape the generator then produces and delete this
// note.

/** The library record an update touched: an obligation (a vocabulary update names no record of its own). */
export interface LibraryUpdateTarget {
  id: string;
  title: string;
  referenceLabel: string;
  instrumentShortName: string;
}

export interface LibraryUpdateRow {
  /** The proposal that carried the change, for a stable row key; this screen never shows the proposal's own wording (PRO-03). */
  id: string;
  kind: string;
  appliedAt: string;
  effectiveFrom: string | null;
  /** The library record's own title, reference and instrument, never the proposal's title (chunk4-T13b: "titled by the library record"). Null for a vocabulary-list update. */
  target: LibraryUpdateTarget | null;
  /** The vocabulary list a non-obligation update touched, e.g. "flag". */
  vocabularyList: string | null;
  inFootprint: boolean;
  outsideTerms: string[];
}

export interface LibraryUpdateDay {
  date: string;
  items: LibraryUpdateRow[];
}

export interface LibraryUpdatesPage {
  since: string;
  days: LibraryUpdateDay[];
  total: number;
}

export interface LibraryUpdatesQuery {
  kind?: string;
  outsideFootprint?: boolean;
}
