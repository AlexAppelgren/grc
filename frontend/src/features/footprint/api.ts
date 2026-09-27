import type { ProposalRef } from '@/features/vocabularies/types';
import type { components } from '@/types/api.generated';
import { api } from '@/shared/utils/api-client';

import type {
  Footprint,
  FootprintChangeRequest,
  FootprintPreview,
  FootprintRejectBody,
  FootprintRequestCreate,
  FootprintRequestStatus,
  JurisdictionRef,
  Market,
  Page,
  PageQuery,
  PersonRef,
  ScopeItem,
  TaxonomyDimension,
  TaxonomyTerm,
  TermSuggest,
} from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). Paths are the
// footprint and taxonomy routes under /api/v1 (CHUNK2_BRIEF.md, "API").
// There is no PUT /tenant/footprint: a change is a request with a preview,
// approved by a second person behind step-up (INPUT_DELTAS section 5).
// Step-up is the api client's business. Watching a market is a direct write
// whose key rides in the body, never the path, so no access log line names a
// market (D-30).

const FOOTPRINT = '/api/v1/tenant/footprint';
const REQUESTS = `${FOOTPRINT}/requests`;
const WATCHING = `${FOOTPRINT}/watching`;
const TAXONOMY = '/api/v1/taxonomy';

const id = (value: string) => encodeURIComponent(value);

type Schemas = components['schemas'];

// The server's shapes (openapi.json) are read through the normalisers below
// into the types the screen and its presentation functions use, so a
// difference in shape is absorbed here, once, and never reaches a screen.

/** The server counts each record kind with both sides; the screen reads each side across kinds. */
export function previewOf(raw: Schemas['FootprintPreview'] | null | undefined): FootprintPreview {
  const hidden: FootprintPreview['hidden'] = {};
  const revealed: FootprintPreview['revealed'] = {};
  // A record kind may be absent; when present, its counts are always sent.
  for (const [kind, count] of Object.entries(raw ?? {})) {
    if (count === undefined) continue;
    hidden[kind] = { count: count.hidden, available: count.available };
    revealed[kind] = { count: count.revealed, available: count.available };
  }
  return { hidden, revealed };
}

const STATUSES: readonly FootprintRequestStatus[] = ['pending', 'approved', 'rejected', 'withdrawn'];

function statusOf(status: string): FootprintRequestStatus {
  return (STATUSES as readonly string[]).includes(status) ? (status as FootprintRequestStatus) : 'pending';
}

function termOf(term: Schemas['FootprintTermRef']): TaxonomyTerm {
  return { dimension: term.dimension, key: term.key, kind: term.kind ?? null, label: term.label };
}

export function scopeItemOf(raw: Schemas['ScopeItemRow']): ScopeItem {
  return {
    id: raw.id ?? null,
    key: raw.key,
    name: raw.name,
    description: raw.description,
    jurisdiction: { key: raw.jurisdiction.key, kind: raw.jurisdiction.kind ?? null, label: raw.jurisdiction.label },
    regimeTerm: termOf(raw.regimeTerm),
    officialReference: raw.officialReference,
    sourceUrl: raw.sourceUrl,
    status: raw.status,
    research: raw.research ?? null,
  };
}

/** A person the server no longer names (a removed member) reads as nobody, never as the viewer. */
const NOBODY: PersonRef = { id: '', name: '' };

export function requestOf(raw: Schemas['FootprintRequestRow']): FootprintChangeRequest {
  return {
    id: raw.id,
    status: statusOf(raw.status),
    requestedBy: raw.requestedBy ?? NOBODY,
    requestedAt: raw.requestedAt,
    adds: (raw.adds ?? []).map(termOf),
    removes: (raw.removes ?? []).map(termOf),
    scopeItemAdds: (raw.scopeItemAdds ?? []).map(scopeItemOf),
    scopeItemRemoves: (raw.scopeItemRemoves ?? []).map(scopeItemOf),
    preview: previewOf(raw.preview),
    decidedBy: raw.decidedBy ?? null,
    decidedAt: raw.decidedAt ?? null,
    decisionNote: raw.decisionNote,
    version: raw.version,
  };
}

export function marketOf(raw: Schemas['MarketRow']): Market {
  return { jurisdiction: { key: raw.jurisdiction.key, kind: raw.jurisdiction.kind ?? null, label: raw.jurisdiction.label }, level: raw.level };
}

export function footprintOf(raw: Schemas['FootprintView']): Footprint {
  return {
    dimensions: raw.dimensions.map((d) => ({
      dimension: { key: d.dimension.key, kind: d.dimension.kind ?? null, label: d.dimension.label },
      restrictsFootprint: d.restrictsFootprint,
      terms: (d.terms ?? []).map((term) => ({ key: term.key, kind: term.kind ?? null, label: term.label })),
      allSelected: d.allSelected,
    })),
    pendingRequest: raw.pendingRequest === null || raw.pendingRequest === undefined ? null : requestOf(raw.pendingRequest),
    markets: (raw.markets ?? []).map(marketOf),
    scopeItems: (raw.scopeItems ?? []).map(scopeItemOf),
  };
}

/** A term names its dimension by reference on the wire; the screen matches on the key. */
export function taxonomyTermOf(raw: Schemas['TaxonomyTermRow']): TaxonomyTerm {
  return { dimension: raw.dimension.key, key: raw.key, kind: raw.kind ?? null, label: raw.label, usageNote: raw.usageNote, sortOrder: raw.sortOrder, active: raw.active, mirrored: raw.mirrored };
}

export async function getFootprint(): Promise<Footprint> {
  return footprintOf((await api.get<Schemas['FootprintView']>(FOOTPRINT)).data);
}

export async function listFootprintRequests(query: PageQuery = {}): Promise<Page<FootprintChangeRequest>> {
  const data = (await api.get<Schemas['FootprintRequestPage']>(REQUESTS, { params: query })).data;
  return { items: data.items.map(requestOf), total: data.total };
}

/**
 * The same call with `dryRun`: the server answers with the preview it would
 * store and persists nothing, so the counted Hides and Reveals can be shown
 * before Request approval (design/screens/admin-footprint.html).
 */
export async function previewFootprintRequest(body: FootprintRequestCreate): Promise<FootprintPreview> {
  return previewOf((await api.post<Schemas['FootprintDryRun']>(REQUESTS, body, { params: { dryRun: true } })).data.preview);
}

export async function createFootprintRequest(body: FootprintRequestCreate): Promise<FootprintChangeRequest> {
  return requestOf((await api.post<Schemas['FootprintRequestRow']>(REQUESTS, body)).data);
}

export async function approveFootprintRequest(requestId: string, version?: number): Promise<FootprintChangeRequest> {
  return requestOf((await api.post<Schemas['FootprintRequestRow']>(`${REQUESTS}/${id(requestId)}/approve`, {}, version === undefined ? {} : { version })).data);
}

export async function rejectFootprintRequest(requestId: string, body: FootprintRejectBody, version?: number): Promise<FootprintChangeRequest> {
  return requestOf((await api.post<Schemas['FootprintRequestRow']>(`${REQUESTS}/${id(requestId)}/reject`, body, version === undefined ? {} : { version })).data);
}

export async function withdrawFootprintRequest(requestId: string, version?: number): Promise<FootprintChangeRequest> {
  return requestOf((await api.post<Schemas['FootprintRequestRow']>(`${REQUESTS}/${id(requestId)}/withdraw`, {}, version === undefined ? {} : { version })).data);
}

export async function watchMarket(key: string): Promise<Market> {
  return marketOf((await api.post<Schemas['MarketRow']>(WATCHING, { jurisdiction: key })).data);
}

export async function unwatchMarket(key: string): Promise<Market> {
  return marketOf((await api.post<Schemas['MarketRow']>(`${WATCHING}/remove`, { jurisdiction: key })).data);
}

/** The reference list, for the jurisdiction whose rules reach each market ("Also included"). */
export async function listJurisdictions(): Promise<JurisdictionRef[]> {
  const rows = (await api.get<Schemas['JurisdictionRow'][]>('/api/v1/reference/jurisdictions')).data;
  return rows.map((row) => ({ key: row.key, kind: row.kind ?? null, label: row.label, parentKey: row.parentKey ?? null }));
}

export async function listTerms(dimension?: string): Promise<TaxonomyTerm[]> {
  const params = dimension === undefined ? {} : { dimension };
  return (await api.get<Schemas['TaxonomyTermPage']>(`${TAXONOMY}/terms`, { params })).data.items.map(taxonomyTermOf);
}

/** Dimensions are vocabulary rows; `restrictsFootprint` rides in their list-specific facts. */
export async function listDimensions(): Promise<TaxonomyDimension[]> {
  const rows = (await api.get<Schemas['TaxonomyDimensionPage']>(`${TAXONOMY}/dimensions`)).data.items;
  return rows.map((row) => ({ key: row.key, kind: row.kind ?? null, label: row.label, restrictsFootprint: row.extra?.restrictsFootprint === true }));
}

/** A term nobody can add directly: the write becomes a proposal (VOC-07). */
export async function suggestTerm(body: TermSuggest): Promise<ProposalRef> {
  const data = (await api.post<{ proposal?: ProposalRef } | ProposalRef>(`${TAXONOMY}/terms`, body)).data;
  const nested = 'proposal' in data && data.proposal !== undefined ? data.proposal : (data as ProposalRef);
  return { id: nested.id ?? '', kind: nested.kind ?? '', status: nested.status ?? '', title: nested.title ?? '' };
}
