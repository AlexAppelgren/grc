import type { AxiosResponse } from 'axios';

import type { components } from '@/types/api.generated';
import { api } from '@/shared/utils/api-client';

import type {
  Page,
  ProposalRef,
  VocabularyCreate,
  VocabularyListSummary,
  VocabularyMergePreview,
  VocabularyQuery,
  VocabularyRetireResult,
  VocabularyRow,
  VocabularySuggest,
  VocabularyTier,
  VocabularyUpdate,
  VocabularyWrite,
} from './types';

type Schemas = components['schemas'];

// Thin typed wrappers returning `.data` (playbook 6.1). Paths are the
// vocabulary routes under /api/v1 (CHUNK2_BRIEF.md, "API"). The same
// GET /vocab/{list} serves pickers, filters, pills and agents. A write to a
// library list never lands directly: the server answers 202 with the
// proposal it created (VOC-07), which `writeOf` turns into `proposed`.

const VOCAB = '/api/v1/vocab';

const id = (value: string) => encodeURIComponent(value);

/** Lists come as `{items,total}`; a bare array is tolerated while the contract settles. */
export function itemsOf<T>(data: T[] | Page<T> | null | undefined): T[] {
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

function proposalOf(data: unknown): ProposalRef {
  const record = typeof data === 'object' && data !== null ? (data as Record<string, unknown>) : {};
  const nested = typeof record.proposal === 'object' && record.proposal !== null ? (record.proposal as Record<string, unknown>) : record;
  return {
    id: typeof nested.id === 'string' ? nested.id : '',
    kind: typeof nested.kind === 'string' ? nested.kind : '',
    status: typeof nested.status === 'string' ? nested.status : '',
    title: typeof nested.title === 'string' ? nested.title : '',
  };
}

export function writeOf<T>(response: AxiosResponse<T>): VocabularyWrite<T> {
  if (response.status === 202) return { outcome: 'proposed', proposal: proposalOf(response.data) };
  return { outcome: 'applied', result: response.data };
}

/**
 * The API numbers its tiers as the data model does (2: the shared library,
 * 3: the tenant's own); the screens name them. A name is passed through.
 */
export function tierOf(tier: number | string): VocabularyTier {
  return tier === 2 || tier === 'library' ? 'library' : 'tenant';
}

export function listSummaryOf(entry: Schemas['VocabularyListEntry']): VocabularyListSummary {
  return { list: entry.list, tier: tierOf(entry.tier), kind: entry.kind ?? null, count: entry.count, retiredCount: entry.retiredCount };
}

export async function listVocabularies(): Promise<VocabularyListSummary[]> {
  return itemsOf((await api.get<Schemas['VocabularyListPage']>(VOCAB)).data).map(listSummaryOf);
}

export async function listValues(list: string, query: VocabularyQuery = {}): Promise<VocabularyRow[]> {
  const params = query.includeRetired === true ? { includeRetired: true } : {};
  return itemsOf((await api.get<VocabularyRow[] | Page<VocabularyRow>>(`${VOCAB}/${id(list)}`, { params })).data);
}

export async function createValue(list: string, body: VocabularyCreate): Promise<VocabularyWrite<VocabularyRow>> {
  return writeOf(await api.post<VocabularyRow>(`${VOCAB}/${id(list)}`, body));
}

export async function updateValue(list: string, key: string, body: VocabularyUpdate, version?: number): Promise<VocabularyWrite<VocabularyRow>> {
  return writeOf(await api.patch<VocabularyRow>(`${VOCAB}/${id(list)}/${id(key)}`, body, version === undefined ? {} : { version }));
}

export async function reorderValues(list: string, keys: string[]): Promise<void> {
  await api.post(`${VOCAB}/${id(list)}/reorder`, { keys });
}

export async function retireValue(list: string, key: string, confirm: boolean): Promise<VocabularyWrite<VocabularyRetireResult>> {
  return writeOf(await api.post<Schemas['VocabularyRetired']>(`${VOCAB}/${id(list)}/${id(key)}/retire`, { confirm }));
}

/** The inverse of retire: the value is offered by pickers and filters again. */
export async function restoreValue(list: string, key: string): Promise<VocabularyWrite<Schemas['VocabularyRestored']>> {
  return writeOf(await api.post<Schemas['VocabularyRestored']>(`${VOCAB}/${id(list)}/${id(key)}/restore`, {}));
}

/** `repointed` is what moves: the same number on the dry run and on the commit. */
export function mergedOf(raw: Schemas['VocabularyMerged']): VocabularyMergePreview {
  return { from: raw.from, into: raw.into, moved: raw.repointed };
}

export async function previewMerge(list: string, key: string, into: string): Promise<VocabularyMergePreview> {
  return mergedOf((await api.post<Schemas['VocabularyMerged']>(`${VOCAB}/${id(list)}/${id(key)}/merge`, { into }, { params: { dryRun: true } })).data);
}

export async function mergeValue(list: string, key: string, into: string): Promise<VocabularyWrite<VocabularyMergePreview>> {
  const write = writeOf(await api.post<Schemas['VocabularyMerged']>(`${VOCAB}/${id(list)}/${id(key)}/merge`, { into }));
  return write.outcome === 'applied' ? { outcome: 'applied', result: mergedOf(write.result) } : write;
}

export async function suggestValue(list: string, body: VocabularySuggest): Promise<ProposalRef> {
  return proposalOf((await api.post<unknown>(`${VOCAB}/${id(list)}/suggest`, body)).data);
}

// What this tenant has proposed on a library list is not read in chunk 2:
// GET /proposals is the platform review queue. Chunk 4 adds a read scoped to
// the proposer's tenant. Deciding a proposal is the console's, never a tenant
// screen's; the tenant-list suggestion queue is VOC-03, R2.
