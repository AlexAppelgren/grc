// The footprint screen model: what the screen and its presentation
// functions read. The wire shapes are the generated components['schemas'][…]
// (src/types/api.generated.ts, from openapi.json); api.ts reads them and
// normalises into these (the preview arrives per record kind and is read per
// side, a term names its dimension by reference, a requester may be gone).

import type { Page, PageQuery } from '@/features/tenant-admin/types';

export type { Page, PageQuery };

/** A vocabulary reference as every read returns it: key, kind and the label in the user's language. */
export interface TermRef {
  key: string;
  kind: string | null;
  label: string;
}

/** A scope term with the dimension it belongs to; what /taxonomy/terms returns. */
export interface TaxonomyTerm extends TermRef {
  dimension: string;
  usageNote?: string;
  sortOrder?: number;
  active?: boolean;
  /** True for a term that mirrors a jurisdiction row: its group is the markets we operate in. */
  mirrored?: boolean;
}

export interface TaxonomyDimension extends TermRef {
  restrictsFootprint: boolean;
}

export interface FootprintDimension {
  dimension: TermRef;
  restrictsFootprint: boolean;
  terms: TermRef[];
  allSelected: boolean;
}

/** A term named by its dimension and key, as the request body carries it. */
export interface TermChange {
  dimension: string;
  key: string;
}

export interface FootprintPreviewCount {
  count: number;
  /** False while the record kind's table does not exist yet: the count is not known, not zero. */
  available: boolean;
}

/** Per record kind (obligations, cases), what the change hides and reveals. */
export interface FootprintPreview {
  hidden: Record<string, FootprintPreviewCount>;
  revealed: Record<string, FootprintPreviewCount>;
}

export interface PersonRef {
  id: string;
  name: string;
}

/** Request status is a kind: pending, approved, rejected or withdrawn. */
export type FootprintRequestStatus = 'pending' | 'approved' | 'rejected' | 'withdrawn';

export interface FootprintChangeRequest {
  id: string;
  status: FootprintRequestStatus;
  requestedBy: PersonRef;
  requestedAt: string;
  adds: TaxonomyTerm[];
  removes: TaxonomyTerm[];
  preview: FootprintPreview;
  decidedBy: PersonRef | null;
  decidedAt: string | null;
  decisionNote: string;
  version: number;
}

/** A market's level is a kind the server computes: operating first, then watching, otherwise not followed. */
export type MarketLevel = 'operating' | 'watching' | 'not_followed';

/** One active country and how closely the organisation follows it. */
export interface Market {
  jurisdiction: TermRef;
  level: MarketLevel;
}

/** A jurisdiction from the reference list, with the one whose rules reach it. */
export interface JurisdictionRef extends TermRef {
  parentKey: string | null;
}

export interface Footprint {
  dimensions: FootprintDimension[];
  pendingRequest: FootprintChangeRequest | null;
  markets: Market[];
}

export interface FootprintRequestCreate {
  adds: TermChange[];
  removes: TermChange[];
}

export interface FootprintRejectBody {
  note: string;
}

export interface TermSuggest {
  dimension: string;
  key?: string;
  labels: Record<string, string>;
  usageNote?: string;
}
