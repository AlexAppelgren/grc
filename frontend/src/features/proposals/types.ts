// The proposals feature's names for the queue (PRO-01, PRO-02, PRO-03,
// AC-PRO2). Every shape is an alias over the generated schemas in
// src/types/api.generated.ts (from the backend's OpenAPI export;
// `bash generate-types.sh` regenerates them). A local definition remains
// only where the generator cannot express the shape, each with a reason.
//
// GET /proposals and GET /proposals/{id} answer exactly `ProposalRow`: no
// target title, reference or instrument short name, no `isMine` and no
// `fromOrganisation` (chunk4-T10's enrichment is not on `main`; see the
// screens' own notes for how each is worked around without it).

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type ProposalRow = Schemas['ProposalRow'];
export type ProposalPage = Schemas['ProposalPage'];
export type ProposalApproveBody = Schemas['ProposalApproveBody'];
export type ProposalRejectBody = Schemas['ProposalRejectBody'];

// Local: the generator renders every query parameter as optional strings;
// this is the same shape, named for the feature.
export interface ProposalQuery {
  status?: string;
  kind?: string;
  targetList?: string;
}

// GET /tenant/proposals is chunk4-T10's route ("Queue reads, rejection
// reasons and the tenant's own proposals", docs/plans/briefs/CHUNK4_TASKS.md)
// and is not on `main` yet: no `components['schemas']` shape exists for it,
// so this is hand-typed from that task's own description — what this
// tenant's own member or agent proposed on a library list, filtered to
// status, kind and targetList, open to `vocab.manage`. Reconcile against the
// generated shape and delete this note once T10 lands.
export interface TenantProposalRow {
  id: string;
  kind: string;
  status: string;
  title: string;
  createdAt: string;
}

export interface TenantProposalPage {
  items: TenantProposalRow[];
  total: number;
}

export type TenantProposalQuery = ProposalQuery;

// Local: the fixed kinds `Proposal.kind` and `.status` carry (apps/proposals/models.py).
// Kept narrow rather than `string` so a screen that switches over them is checked by `tsc`.
export type ProposalKind =
  | 'new_obligation_version'
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
