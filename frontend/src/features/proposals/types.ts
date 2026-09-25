// The proposals feature's names for the queue (PRO-01, PRO-02, PRO-03,
// AC-PRO2). Every shape is an alias over the generated schemas in
// src/types/api.generated.ts (from the backend's OpenAPI export;
// `bash generate-types.sh` regenerates them). A local definition remains
// only where the generator cannot express the shape, each with a reason.

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

/** The proposal as every answer carrying one returns it (approve and reject answer this). */
export type ProposalRow = Schemas['ProposalRow'];
/** A row of GET /proposals: the proposal plus the server's own `target` and `isMine`. */
export type ProposalQueueRow = Schemas['ProposalQueueRow'];
/** GET /proposals/{id}: the row plus the diff, the sources and the version an approval wrote. */
export type ProposalDetail = Schemas['ProposalDetail'];
export type ProposalPage = Schemas['ProposalPage'];
export type ProposalApproveBody = Schemas['ProposalApproveBody'];
export type ProposalRejectBody = Schemas['ProposalRejectBody'];
export type TenantProposalRow = Schemas['TenantProposalRow'];
export type TenantProposalPage = Schemas['TenantProposalPage'];

/** Which end of the queue comes first (`ProposalQuery.order`): the route's two values. */
export type ProposalOrder = 'oldest' | 'newest';

// The route's filters and its page, as the generated query schemas name them,
// minus the nulls a caller never sends and with `order` narrowed to its two values.
type Unnulled<T> = { [K in keyof T]?: Exclude<T[K], null> };
export type ProposalQuery = Unnulled<Omit<Schemas['ProposalQuery'], 'order'> & Schemas['PageQuery']> & { order?: ProposalOrder };
export type TenantProposalQuery = Unnulled<Schemas['TenantProposalQuery']>;

// Local: the fixed kinds `Proposal.kind` and `.status` carry (apps/proposals/models.py).
// Kept narrow rather than `string` so a screen that switches over them is checked by `tsc`.
export type ProposalKind =
  | 'new_instrument'
  | 'new_obligation'
  | 'new_obligation_version'
  | 'new_provision'
  | 'new_provision_version'
  | 'vocabulary_create'
  | 'vocabulary_relabel'
  | 'vocabulary_retire'
  | 'vocabulary_restore'
  | 'vocabulary_merge'
  | 'term_create'
  | 'term_update';

export type ProposalStatus = 'open' | 'approved' | 'rejected' | 'superseded';

export const OBLIGATION_KINDS: readonly ProposalKind[] = ['new_obligation_version'];
export const VOCABULARY_KINDS: readonly ProposalKind[] = [
  'vocabulary_create',
  'vocabulary_relabel',
  'vocabulary_retire',
  'vocabulary_restore',
  'vocabulary_merge',
];
export const TERM_KINDS: readonly ProposalKind[] = ['term_create', 'term_update'];

/** The `new_obligation_version` payload, as the schema names its fields (schemas.py `ProposalObligationVersionPayload`). */
export interface ObligationVersionPayload {
  summaries: Record<string, string>;
  originalLanguage: string;
  isMachine?: boolean;
  effectiveFrom?: string | null;
  effectiveFromPrecision?: string;
  terms?: string[] | null;
}

/** The vocabulary-kind payloads share this shape; a given kind reads only the fields its own schema names. */
export interface VocabularyProposalPayload {
  list?: string;
  dimension?: string;
  key?: string;
  into?: string;
  parent?: string | null;
  labels?: Record<string, string>;
  usageNote?: string | null;
  sortOrder?: number | null;
}
