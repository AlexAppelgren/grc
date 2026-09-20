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
