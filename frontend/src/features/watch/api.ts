import { api } from '@/shared/utils/api-client';
import type { components, operations } from '@/types/api.generated';

// Thin typed wrappers returning `.data` (playbook 6.1). A change is a library
// record and nothing here writes one: the only writes are this bank's own
// decisions about it, which live on its case (WAT-04, WAT-05). Every shape is
// the generated one, never a hand-written copy, so a contract change is a
// type error here rather than a wrong screen.

type Schemas = components['schemas'];

/** One row of the feed: the library's facts plus this bank's own case, or null when it has none. */
export type ChangeRow = Schemas['WatchChangeRow'];
export type ChangePage = Schemas['WatchChangePage'];
export type ChangeDetail = Schemas['WatchChangeDetail'];
export type ObligationChangePage = Schemas['WatchObligationChangePage'];
export type SourceCoverage = Schemas['WatchSourceCoverage'];
/** `{ref: {key, kind, label}, confidence, suggested}` — the fact is under `ref`. */
export type ChangeFact = Schemas['WatchFact'];
export type LibraryRef = Schemas['LibraryRef'];
/** A platform agent named by its definition key: who suggested or confirmed a curated fact (D-74). */
export type AgentRef = Schemas['AgentRef'];
/** This bank's decision about one suggested obligation link, as the change read carries it. */
export type CaseObligationDecision = Schemas['WatchCaseObligationDecision'];
export type CaseSoWhat = Schemas['CasesSoWhat'];
export type CaseObligationLink = Schemas['CasesObligationLink'];

/** The feed's filters, exactly as the route declares them. */
export type ChangeQuery = NonNullable<operations['listChanges']['parameters']['query']>;

const CHANGES = '/api/v1/changes';
const OBLIGATIONS = '/api/v1/obligations';
const SOURCE_COVERAGE = '/api/v1/sources/coverage';

/**
 * `termId` repeats: the route reads `termId=<uuid>&termId=<uuid>`, where axios
 * would otherwise send `termId[]=…`. Everything else is a scalar, and a filter
 * that is not set is left out rather than sent empty.
 */
export function serializeQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) for (const item of value) search.append(key, String(item));
    else search.append(key, String(value));
  }
  return search.toString();
}

export async function listChanges(query: ChangeQuery = {}): Promise<ChangePage> {
  return (await api.get<ChangePage>(CHANGES, { params: query, paramsSerializer: { serialize: serializeQuery } })).data;
}

export async function getChange(changeId: string): Promise<ChangeDetail> {
  return (await api.get<ChangeDetail>(`${CHANGES}/${changeId}`)).data;
}

export async function listObligationChanges(obligationId: string, page: { limit?: number; offset?: number } = {}): Promise<ObligationChangePage> {
  return (await api.get<ObligationChangePage>(`${OBLIGATIONS}/${obligationId}/changes`, { params: page })).data;
}

/** WAT-05: this bank's own wording, replacing the draft on its case. Saving is the decision, so it confirms too. */
export async function saveSoWhat(changeId: string, text: string): Promise<CaseSoWhat> {
  return (await api.put<CaseSoWhat>(`${CHANGES}/${changeId}/so-what`, { text })).data;
}

/** WAT-05: the draft on this bank's case accepted as it stands. */
export async function confirmSoWhat(changeId: string): Promise<CaseSoWhat> {
  return (await api.post<CaseSoWhat>(`${CHANGES}/${changeId}/so-what/confirm`)).data;
}

/** WAT-04: a suggested obligation really is affected for this bank. Writes this bank's case, never the library's link. */
export async function acceptCaseObligationLink(changeId: string, obligationId: string): Promise<CaseObligationLink> {
  return (await api.post<CaseObligationLink>(`${CHANGES}/${changeId}/case/obligation-links`, { obligationId })).data;
}

/** WAT-04: a suggested obligation is not related to this bank. Stored as a decision on its case; the library's link stays. */
export async function removeCaseObligationLink(changeId: string, obligationId: string): Promise<CaseObligationLink> {
  return (await api.delete<CaseObligationLink>(`${CHANGES}/${changeId}/case/obligation-links/${obligationId}`)).data;
}

/** WAT-01: the last check per source, with the stale rows the tab marks. An empty registry is a 200 and an empty list. */
export async function getSourceCoverage(): Promise<SourceCoverage[]> {
  return (await api.get<SourceCoverage[]>(SOURCE_COVERAGE)).data;
}

/** A scope term as the feed's filter needs it: the id the route matches on, and the label a reader picks by. */
export interface ScopeTerm {
  id: string;
  key: string;
  label: string;
}

/**
 * The terms of one dimension, with their ids. The feed filters on `termId`,
 * so the id has to survive the read; the footprint feature's own term model
 * drops it, because a footprint is stored by key.
 */
export async function listScopeTerms(dimension: string): Promise<ScopeTerm[]> {
  const rows = (await api.get<Schemas['TaxonomyTermPage']>('/api/v1/taxonomy/terms', { params: { dimension } })).data.items;
  return rows.map((row) => ({ id: row.id, key: row.key, label: row.label }));
}
