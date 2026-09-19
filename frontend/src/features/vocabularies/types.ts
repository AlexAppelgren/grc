// The vocabulary screen model: what the screens, the picker and the
// presentation functions read. The wire shapes are the generated
// components['schemas'][…] (src/types/api.generated.ts, from openapi.json);
// api.ts reads them and normalises into these (the API numbers its tiers,
// a merge reports `repointed`). A difference in shape is absorbed there,
// once, and never reaches a screen.

import type { Page, PageQuery } from '@/features/tenant-admin/types';

export type { Page, PageQuery };

/** Which tier a list belongs to: a shared library list or the tenant's own. A kind. */
export type VocabularyTier = 'library' | 'tenant';

/** One entry of GET /vocab, the list of lists. */
export interface VocabularyListSummary {
  list: string;
  tier: VocabularyTier;
  /** The fixed kind the list's rows carry, when the list has one (e.g. lifecycle_kind). */
  kind: string | null;
  count: number;
  retiredCount: number;
  /** Suggestions waiting for a decision, when the server counts them. */
  pendingSuggestions?: number;
}

/** One row of GET /vocab/{list}: a value as pickers, filters, pills and agents read it. */
export interface VocabularyRow {
  key: string;
  kind: string | null;
  /** The label in the user's language, resolved by the API from the translation rows. */
  label: string;
  labels: Record<string, string>;
  usageNote: string;
  sortOrder: number;
  active: boolean;
  isSystem: boolean;
  isDefault: boolean;
  usageCount: number;
  /** List-specific facts (a urgency's tone and ordinal, a dimension's restrictsFootprint). */
  extra: Record<string, unknown>;
  /** Present on lists whose rows are versioned; sent back as If-Match. */
  version?: number;
}

export interface VocabularyCreate {
  key?: string;
  labels: Record<string, string>;
  usageNote?: string;
  /** From vocab.manage only: create although a near duplicate exists. */
  force?: boolean;
}

export interface VocabularyUpdate {
  labels?: Record<string, string>;
  usageNote?: string;
  sortOrder?: number;
}

export interface VocabularyRetireResult {
  key: string;
  retired: boolean;
  usageCount: number;
}

export interface VocabularyMergePreview {
  from: string;
  into: string;
  /** Records that will be, or were, re-pointed. */
  moved: number;
  /** Per record kind, when the server breaks the count down. */
  byRecordKind?: Record<string, number>;
}

/** The proposal a library-list write turns into (VOC-07). */
export interface ProposalRef {
  id: string;
  /** Kind: vocabulary_create, vocabulary_relabel, vocabulary_retire, vocabulary_merge, term_create. */
  kind: string;
  /** Kind: open, approved, rejected, superseded. */
  status: string;
  title: string;
}

/** A tenant-list write answers the row (201/200); a library-list write answers 202 with a proposal. */
export type VocabularyWrite<T> = { outcome: 'applied'; result: T } | { outcome: 'proposed'; proposal: ProposalRef };

export interface NearDuplicateCandidate {
  key: string;
  label: string;
  similarity?: number;
}

export interface VocabularySuggest {
  labels: Record<string, string>;
  usageNote?: string;
}

export interface VocabularyQuery {
  includeRetired?: boolean;
}
