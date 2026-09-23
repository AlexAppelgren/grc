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
  /** The instrument's jurisdiction: what "Market we watch" names in the watched view (FP-04). */
  jurisdiction: LibraryRef;
  inFootprint: boolean;
  outsideReason: OutsideReason[];
  lastVerifiedAt: string | null;
  openChangeCount: number;
  /** An applicability change waiting for approval; null until the register overlay lands (chunk 8). */
  pendingApplicability: boolean | null;
  complianceStatus: KindRef<ComplianceKind> | null;
}

/**
 * Which records a list shows against the bank's footprint: one value, never a
 * contradictory pair. `in` is the default and is never sent; `all` lifts the
 * footprint and `watched` shows only what the watched markets add (FP-03, FP-04).
 */
export type ScopeFilter = 'in' | 'watched' | 'all';

/**
 * The filters of GET /obligations. Every value is a key, never a label:
 * `term` is `dimension:key` and repeats, `asOf` is a plain date and defaults
 * to today where the tenant is, and `footprint` is the scope filter's value.
 */
export interface ObligationQuery {
  instrument?: string;
  dutyType?: string;
  term?: string[];
  q?: string;
  asOf?: string;
  footprint?: ScopeFilter;
}

/** A person the library names, by id and name; never a member of a bank (INV-06). */
export interface PersonRef {
  id: string;
  name: string;
}

/** A platform research agent, named by its definition key; never a person or a bank (D-62). */
export interface AgentRef {
  id: string;
  key: string;
}

/**
 * Who confirmed the approval that wrote a version, and which agent proposed it
 * (INV-05, PRO-02). `verifiedOrigin` 'agent' is an independent agent's
 * confirmation, which reads machine-confirmed and never as a person's; 'user'
 * is a person's approval, and '' a seeded version nobody approved. The
 * proposer is a separate fact: a person may propose what an agent confirms.
 */
export interface VersionConfirmation {
  verifiedOrigin: string;
  confirmedByAgent: AgentRef | null;
  proposedByAgent: AgentRef | null;
}

/** One version of a summary with the dates it runs between; `effectiveTo` is derived, never stored (INV-04). */
export interface ObligationVersionRow extends VersionConfirmation {
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

/**
 * Where the record came from and when a person last held it against its
 * source (INV-06), with who confirmed the version in force on the read's date.
 */
export interface ObligationProvenance extends VersionConfirmation {
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
  regime: LibraryRef;
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

/** Who issued an instrument, in full (INV-01). */
export interface InstrumentAuthorityRef {
  key: string;
  name: string;
  shortName: string;
  url: string;
}

/** One row of GET /instruments (INV-01). `obligationCount` follows the same footprint filter the row itself does. */
export interface Instrument {
  id: string;
  stableKey: string;
  shortName: string;
  name: LocalizedText | null;
  level: LibraryRef;
  binding: boolean;
  jurisdiction: LibraryRef;
  authority: InstrumentAuthorityRef | null;
  regime: LibraryRef;
  officialRef: string;
  inForceFrom: PartialDate | null;
  inForceTo: PartialDate | null;
  implementsNote: string;
  obligationCount: number;
  inFootprint: boolean;
  lastVerifiedAt: string | null;
  sourceUrl: string;
}

/** The filters of GET /instruments. Jurisdiction, level, authority and asOf are deferred; "as of" applies to obligations only. */
export interface InstrumentQuery {
  regime?: string;
  q?: string;
  footprint?: ScopeFilter;
}

/** One instrument-to-instrument relation, from either side (INV-01). */
export interface InstrumentLineageRef {
  relation: LibraryRef;
  direction: 'outgoing' | 'incoming';
  instrument: InstrumentRef;
  note: string;
  toRef: string;
}

/** One text version of a provision (INV-02, INV-04): `effectiveTo` is derived, never stored. */
export interface ProvisionVersionRow {
  versionNumber: number;
  effectiveFrom: PartialDate | null;
  effectiveTo: PartialDate | null;
  transitionalNote: string;
  text: LocalizedText | null;
}

/** An obligation that cites a provision, as the tree's own row names it. */
export interface ProvisionCitedObligation {
  id: string;
  title: LocalizedText | null;
  refLabel: string;
}

/** One node of the provision tree (INV-02): a chapter, a section, a paragraph or whatever `kind` names. */
export interface ProvisionNode {
  id: string;
  stableKey: string;
  kind: LibraryRef;
  refLabel: string;
  heading: string;
  path: string;
  children: ProvisionNode[];
  versions: ProvisionVersionRow[];
  /** The version number in force on the read's date, or null when none is. */
  inForceVersion: number | null;
  obligations: ProvisionCitedObligation[];
}

/** GET /instruments/{id} (INV-01, INV-06): the row's own facts, the ELI, the authority in full, who last re-verified it and its lineage. */
export interface InstrumentDetail {
  id: string;
  stableKey: string;
  shortName: string;
  name: LocalizedText | null;
  level: LibraryRef;
  binding: boolean;
  jurisdiction: LibraryRef;
  authority: InstrumentAuthorityRef | null;
  regime: LibraryRef;
  officialRef: string;
  /** The European Legislation Identifier, or an empty string when none is published; never null. */
  eliUri: string;
  inForceFrom: PartialDate | null;
  inForceTo: PartialDate | null;
  implementsNote: string;
  sourceUrl: string;
  lastVerifiedAt: string | null;
  verifiedBy: PersonRef | null;
  lineage: InstrumentLineageRef[];
}
