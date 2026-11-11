// The library's names for the wire shapes (docs/CONVENTIONS.md 3.1): every
// record is an alias over the generated components['schemas'][…]
// (src/types/api.generated.ts, from openapi.json), never a redeclared copy.
// The four facts a screen may not trust as sent are narrowed where they are
// read: a legal date's precision (formatPartialDate), and a compliance
// status's kind, a diff sentence's operation and a lineage link's direction
// (complianceOf, diffOpOf and lineageDirectionOf in api.ts).

import type { Page, PageQuery } from '@/features/tenant-admin/types';
import type { components } from '@/types/api.generated';

export type { Page, PageQuery };

type Schemas = components['schemas'];

/** A vocabulary row or a term as every library read returns it: key, kind and the label in the reader's language. */
export type LibraryRef = Schemas['LibraryRef'];
/** One text in one language, labelled so the screen can say a machine wrote it (INV-05). */
export type LocalizedText = Schemas['LocalizedText'];
/** A summary version by number and the date it takes effect; a null date means "since it began" (INV-04). */
export type ObligationVersion = Schemas['ObligationVersionRef'];
/** The record's terms in one dimension; an empty list means no restriction in it (FP-01). */
export type ScopeDimension = Schemas['ScopeDimension'];
/** A dimension in which none of the record's terms is in the footprint (FP-03). */
export type OutsideReason = Schemas['OutsideReason'];
export type InstrumentRef = Schemas['ObligationInstrumentRef'];
/** One row of GET /obligations (INV-03), with the bank's register overlay (REG-01, REG-02). */
export type Obligation = Schemas['ObligationRow'];
/** A person the library names, by id and name; never a member of a bank (INV-06). */
export type PersonRef = Schemas['PersonRef'];
/** A platform research agent, named by its definition key; never a person or a bank (D-62). */
export type AgentRef = Schemas['AgentRef'];
/**
 * Who confirmed the approval that wrote a version, and which agent proposed it
 * (INV-05, PRO-02). `verifiedOrigin` 'agent' is an independent agent's
 * confirmation, which reads machine-confirmed and never as a person's.
 */
export type VersionConfirmation = Schemas['VersionConfirmation'];
/** One version of a summary with the dates it runs between; `effectiveTo` is derived, never stored (INV-04). */
export type ObligationVersionRow = Schemas['ObligationVersionRow'];
/** The instrument the duty was broken out of, as the detail read summarises it. */
export type InstrumentSummary = Schemas['ObligationInstrumentSummary'];
/** Where the record came from and when a person last held it against its source (INV-06). */
export type ObligationProvenance = Schemas['ObligationProvenance'];
/** A duty the library files beside this one; `relation` is a vocabulary row. */
export type RelatedObligation = Schemas['RelatedObligation'];
/**
 * GET /obligations/{id} (INV-03..INV-06). Being here is not the judgement
 * that the duty applies to this bank, and not the claim that the bank
 * complies with it: both are tenant facts the register holds.
 */
export type ObligationDetail = Schemas['ObligationDetail'];
/** One sentence of a diff and what became of it between the two versions (INV-04). */
export type DiffSegment = Schemas['DiffSegment'];
export type DiffOp = 'equal' | 'insert' | 'delete';
/** Two versions of one duty or provision compared sentence by sentence. */
export type VersionDiff = Schemas['VersionDiff'];
/** POST …/problem-reports: what the reader was looking at, in their own words. */
export type ProblemReportBody = Schemas['ProblemReportBody'];
export type ProblemReportCreated = Schemas['ProblemReportCreated'];
/** Who issued an instrument, in full (INV-01). */
export type InstrumentAuthorityRef = Schemas['InstrumentAuthorityRef'];
/** One row of GET /instruments (INV-01). `obligationCount` follows the same footprint filter the row itself does. */
export type Instrument = Schemas['InstrumentRow'];
/** One instrument-to-instrument relation, from either side (INV-01). */
export type InstrumentLineageRef = Schemas['InstrumentLineageRef'];
/** One text version of a provision (INV-02, INV-04): `effectiveTo` is derived, never stored. */
export type ProvisionVersionRow = Schemas['ProvisionVersionRow'];
/** An obligation that cites a provision, as the tree's own row names it. */
export type ProvisionCitedObligation = Schemas['ProvisionCitedObligation'];
/** One node of the provision tree (INV-02): a chapter, a section, a paragraph or whatever `kind` names. */
export type ProvisionNode = Schemas['ProvisionNode'];
/** GET /instruments/{id} (INV-01, INV-06, INV-09). */
export type InstrumentDetail = Schemas['InstrumentDetail'];
/** Another instrument tied to this one by implementation, as the card links to it. */
export type InstrumentLinkRef = Schemas['InstrumentLinkRef'];
/** The duties under an instrument: held, in the reader's scope, and waiting for review. */
export type InstrumentObligationCounts = Schemas['InstrumentObligationCounts'];
/**
 * What tagging a selection would do (the preview) or did (the commit), in one shape.
 * Records the reader may not read are only counted: the server never names them.
 */
export type TaggingBatch = Schemas['TaggingBatchOutcome'];

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
  /** Library tag keys and the bank's own tag keys; every one named must be on the record. */
  tag?: string[];
  tenantTag?: string[];
  q?: string;
  asOf?: string;
  footprint?: ScopeFilter;
  // The bank's register overlay, each a key or a member's id.
  applicability?: Obligation['applicability'];
  complianceStatus?: string;
  owner?: string;
  ownerTeam?: string;
}

/** The filters of GET /instruments. Jurisdiction, level, authority and asOf are deferred; "as of" applies to obligations only. */
export interface InstrumentQuery {
  regime?: string;
  q?: string;
  footprint?: ScopeFilter;
}
