// The library screen model: what the inventory and the obligation card read.
// The wire shapes are the generated components['schemas'][…]
// (src/types/api.generated.ts, from openapi.json); api.ts reads them and
// normalises into these (a legal date's precision and a compliance status's
// kind are checked before a screen or a tone map sees them), so a difference
// in shape is absorbed there, once, and never reaches a screen.

import type { KindRef, PartialDate } from '@/features/shared/presentation-types';
import type { ComplianceKind } from '@/features/shared/tone-by-kind';
import type { Page, PageQuery } from '@/features/tenant-admin/types';

export type { Page, PageQuery };

/** A vocabulary row or a term as every library read returns it: key, kind and the label in the reader's language. */
export interface LibraryRef {
  key: string;
  kind: string | null;
  label: string;
}

/** One text in one language, labelled so the screen can say a machine wrote it (INV-05). */
export interface LocalizedText {
  text: string;
  language: string;
  isOriginal: boolean;
  isMachine: boolean;
}

/** A summary version by number and the date it takes effect; a null date means "since it began" (INV-04). */
export interface ObligationVersion {
  versionNumber: number;
  effectiveFrom: PartialDate | null;
}

/** The record's terms in one dimension; an empty list means no restriction in it (FP-01). */
export interface ScopeDimension {
  dimension: LibraryRef;
  terms: LibraryRef[];
  allSelected: boolean;
}

/** A dimension in which none of the record's terms is in the footprint (FP-03). */
export interface OutsideReason {
  dimension: LibraryRef;
  terms: LibraryRef[];
}

export interface InstrumentRef {
  key: string;
  shortName: string;
}

/** One row of GET /obligations (INV-03). */
export interface Obligation {
  id: string;
  stableKey: string;
  refLabel: string;
  title: LocalizedText | null;
  instrument: InstrumentRef;
  bindingLevel: LibraryRef;
  binding: boolean;
  dutyType: LibraryRef;
  tags: LibraryRef[];
  scope: ScopeDimension[];
  /** The version in force on the read's date, and the next one after it. */
  version: ObligationVersion | null;
  upcomingVersion: ObligationVersion | null;
  inFootprint: boolean;
  outsideReason: OutsideReason[];
  lastVerifiedAt: string | null;
  openChangeCount: number;
  /** An applicability change waiting for approval; null until the register overlay lands (chunk 8). */
  pendingApplicability: boolean | null;
  complianceStatus: KindRef<ComplianceKind> | null;
}

/**
 * The filters of GET /obligations. Every value is a key, never a label:
 * `term` is `dimension:key` and repeats, `asOf` is a plain date and defaults
 * to today where the tenant is, and `outsideFootprint` lifts the footprint
 * filter and reports why each row would be hidden.
 */
export interface ObligationQuery {
  instrument?: string;
  dutyType?: string;
  term?: string[];
  q?: string;
  asOf?: string;
  outsideFootprint?: boolean;
}

/** A person the library names, by id and name; never a member of a bank (INV-06). */
export interface PersonRef {
  id: string;
  name: string;
}

/** One version of a summary with the dates it runs between; `effectiveTo` is derived, never stored (INV-04). */
export interface ObligationVersionRow {
  versionNumber: number;
  effectiveFrom: PartialDate | null;
  effectiveTo: PartialDate | null;
  approvedAt: string | null;
}

/** The instrument the duty was broken out of, as the detail read summarises it. */
export interface InstrumentSummary {
  key: string;
  shortName: string;
  officialRef: string;
  name: LocalizedText | null;
  implementsNote: string;
}

/** Where the record came from and when a person last held it against its source (INV-06). */
export interface ObligationProvenance {
  sourceUrl: string;
  sourceLabel: string;
  lastVerifiedAt: string | null;
  verifiedBy: PersonRef | null;
  createdAt: string;
  createdOrigin: string;
  createdModel: string;
}

/** A duty the library files beside this one; `relation` is a vocabulary row. */
export interface RelatedObligation {
  id: string;
  title: LocalizedText | null;
  instrument: InstrumentRef;
  relation: LibraryRef;
  binding: boolean;
}

/**
 * GET /obligations/{id} (INV-03..INV-06). Being here is not the judgement
 * that the duty applies to this bank, and not the claim that the bank
 * complies with it: both are tenant facts the register holds from chunk 8.
 */
export interface ObligationDetail {
  id: string;
  stableKey: string;
  refLabel: string;
  title: LocalizedText | null;
  instrument: InstrumentSummary;
  regime: LibraryRef | null;
  bindingLevel: LibraryRef;
  binding: boolean;
  dutyType: LibraryRef;
  productScope: string;
  triggerFrequency: string;
  retention: string;
  sanctionExposure: string;
  tags: LibraryRef[];
  scope: ScopeDimension[];
  inFootprint: boolean;
  outsideReason: OutsideReason[];
  /** The summary in the best language for this reader, of the version in force on the read's date. */
  summary: LocalizedText | null;
  /** Every language that version holds its summary in, which is what the language chips offer. */
  translations: LocalizedText[];
  version: ObligationVersionRow | null;
  versions: ObligationVersionRow[];
  related: RelatedObligation[];
  provenance: ObligationProvenance;
}

/** One sentence of a diff and what became of it between the two versions (INV-04). */
export interface DiffSegment {
  op: 'equal' | 'insert' | 'delete';
  text: string;
}

/** GET /obligations/{id}/diff: two versions of one duty compared sentence by sentence. */
export interface VersionDiff {
  fromVersion: number;
  toVersion: number;
  fromEffective: PartialDate | null;
  toEffective: PartialDate | null;
  language: string;
  /** True when either side is a machine translation nobody has confirmed (INV-05). */
  isMachine: boolean;
  segments: DiffSegment[];
}

/** POST /obligations/{id}/problem-reports: what the reader was looking at, in their own words. */
export interface ProblemReportBody {
  description: string;
  versionNumber?: number;
  language?: string;
}

export interface ProblemReportCreated {
  id: string;
  status: string;
  createdAt: string;
}
