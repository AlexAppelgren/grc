import type { KindRef } from '@/features/shared/presentation-types';
import type { ComplianceKind } from '@/features/shared/tone-by-kind';
import { api } from '@/shared/utils/api-client';
import type { components } from '@/types/api.generated';

import type {
  DiffOp,
  Instrument,
  InstrumentDetail,
  InstrumentLineageRef,
  InstrumentQuery,
  LibraryRef,
  Obligation,
  ObligationDetail,
  ObligationQuery,
  Page,
  PageQuery,
  ProblemReportBody,
  ProblemReportCreated,
  ProvisionNode,
  TaggingBatch,
  VersionDiff,
} from './types';

export type { TaggingBatch } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). The library reads sit
// under /api/v1; nothing here writes the library, because proposals are the
// only door into it: the one write besides a problem report is the bank's own
// tags, which live in its own zone. The records are the generated shapes
// (types.ts); three of the four facts a screen may not trust as sent are
// narrowed by the small functions below, where a screen or a tone map reads
// them; a legal date's precision is narrowed by formatPartialDate.

const OBLIGATIONS = '/api/v1/obligations';
const INSTRUMENTS = '/api/v1/instruments';

type Schemas = components['schemas'];

const COMPLIANCE_KINDS: readonly ComplianceKind[] = ['compliant', 'partly', 'gap', 'not_assessed'];
const DIFF_OPS: readonly DiffOp[] = ['equal', 'insert', 'delete'];

/**
 * A compliance status becomes a pill only when its kind is one of the four
 * the tone map knows: a tone is chosen by kind, never by a person, so a kind
 * nobody has a tone for is not rendered at all.
 */
export function complianceOf(raw: Schemas['LibraryRef'] | null | undefined): KindRef<ComplianceKind> | null {
  if (raw === null || raw === undefined) return null;
  const kind = COMPLIANCE_KINDS.find((known) => known === raw.kind);
  return kind === undefined ? null : { key: raw.key, label: raw.label, kind };
}

/**
 * A sentence the server marks with an operation the screen has no colour for
 * is shown as it stands: a diff a reader cannot read is worse than one
 * sentence rendered plain.
 */
export function diffOpOf(op: string): DiffOp {
  return DIFF_OPS.find((known) => known === op) ?? 'equal';
}

/** A lineage link is outgoing only when the server says so; anything else reads from the other side. */
export function lineageDirectionOf(link: Pick<InstrumentLineageRef, 'direction'>): 'outgoing' | 'incoming' {
  return link.direction === 'outgoing' ? 'outgoing' : 'incoming';
}

/**
 * `term` repeats: the route reads `term=regime:securities&term=service_type:advice`,
 * where axios would otherwise send `term[]=…`. Everything else is a scalar.
 */
export function serializeQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) for (const item of value) search.append(key, String(item));
    else search.append(key, String(value));
  }
  return search.toString();
}

export async function listObligations(query: ObligationQuery & PageQuery = {}): Promise<Page<Obligation>> {
  return (await api.get<Page<Obligation>>(OBLIGATIONS, { params: query, paramsSerializer: { serialize: serializeQuery } })).data;
}

/** One duty as it stood on `asOf`, which defaults to today in the bank's own time zone. */
export async function getObligation(obligationId: string, asOf?: string): Promise<ObligationDetail> {
  const params = asOf === undefined || asOf === '' ? {} : { asOf };
  return (await api.get<ObligationDetail>(`${OBLIGATIONS}/${obligationId}`, { params })).data;
}

/** What changed between the latest version and the one before it, in the language on screen where both hold it. */
export async function getObligationDiff(obligationId: string, lang?: string): Promise<VersionDiff> {
  const params = lang === undefined || lang === '' ? {} : { lang };
  return (await api.get<VersionDiff>(`${OBLIGATIONS}/${obligationId}/diff`, { params })).data;
}

/**
 * "This looks wrong": the reader's own words about a library record. The body
 * stays inside the bank that filed it, so nothing here logs it and nothing
 * sends it anywhere else.
 */
export async function reportObligationProblem(obligationId: string, body: ProblemReportBody): Promise<ProblemReportCreated> {
  return (await api.post<ProblemReportCreated>(`${OBLIGATIONS}/${obligationId}/problem-reports`, body)).data;
}

// The bank's own tags on an obligation (VOC-08): markers in the bank's zone, never a
// library write. Each call answers the obligation's tags as they now stand.

const TAGGINGS = '/api/v1/taggings';

export async function tagObligation(obligationId: string, tagKey: string): Promise<LibraryRef[]> {
  const body: Schemas['TaggingBody'] = { tagKey, subjectType: 'obligation', subjectId: obligationId };
  return tagsOf((await api.post<Schemas['TaggingRecordTags']>(TAGGINGS, body)).data);
}

export async function untagObligation(obligationId: string, tagKey: string): Promise<LibraryRef[]> {
  const body: Schemas['TaggingBody'] = { tagKey, subjectType: 'obligation', subjectId: obligationId };
  return tagsOf((await api.post<Schemas['TaggingRecordTags']>(`${TAGGINGS}/remove`, body)).data);
}

/** The bank's own tags carry no kind of their own; they read as library references with none. */
function tagsOf(raw: Schemas['TaggingRecordTags']): LibraryRef[] {
  return raw.tags.map((tag) => ({ key: tag.key, kind: tag.kind ?? null, label: tag.label }));
}

/** VOC-08: what one tag on many obligations would do. A read with a body: nothing is written. */
export async function previewObligationTagging(tagKey: string, obligationIds: readonly string[]): Promise<TaggingBatch> {
  const body: Schemas['TaggingBatchBody'] = { tagKey, subjectType: 'obligation', subjectIds: [...obligationIds] };
  return (await api.post<TaggingBatch>(`${TAGGINGS}/preview`, body)).data;
}

/** VOC-08: one tag on many obligations in one transaction, audited once by the server. */
export async function tagObligations(tagKey: string, obligationIds: readonly string[]): Promise<TaggingBatch> {
  const body: Schemas['TaggingBatchBody'] = { tagKey, subjectType: 'obligation', subjectIds: [...obligationIds] };
  return (await api.post<TaggingBatch>(`${TAGGINGS}/batch`, body)).data;
}

// Instruments (INV-01, INV-06): the Instruments tab, the instrument filter and the
// instrument card. Reads only, like every obligation read above; "This looks wrong" is
// the one write, and it stays inside the reader's own bank.

export async function listInstruments(query: InstrumentQuery & PageQuery = {}): Promise<Page<Instrument>> {
  return (await api.get<Page<Instrument>>(INSTRUMENTS, { params: query })).data;
}

export async function getInstrument(instrumentId: string): Promise<InstrumentDetail> {
  return (await api.get<InstrumentDetail>(`${INSTRUMENTS}/${instrumentId}`)).data;
}

/** "This looks wrong" on an instrument card; a provision is reported through the instrument whose card shows it. */
export async function reportInstrumentProblem(instrumentId: string, body: ProblemReportBody): Promise<ProblemReportCreated> {
  return (await api.post<ProblemReportCreated>(`${INSTRUMENTS}/${instrumentId}/problem-reports`, body)).data;
}

// The provision tree (INV-02, INV-04, INV-05): every text version a provision has ever
// carried, so the tree chooses one by its own chip rather than trusting today's date, and
// the diff between any two of them.

/** The whole provision tree of one instrument, as of a date (default today where the tenant is). */
export async function listInstrumentProvisions(instrumentId: string, asOf?: string): Promise<ProvisionNode[]> {
  const params = asOf === undefined || asOf === '' ? {} : { asOf };
  return (await api.get<ProvisionNode[]>(`${INSTRUMENTS}/${instrumentId}/provisions`, { params })).data;
}

const PROVISIONS = '/api/v1/provisions';

/** What changed between two versions of one provision's verbatim text, in the language on screen where both hold it. */
export async function getProvisionDiff(provisionId: string, lang?: string): Promise<VersionDiff> {
  const params = lang === undefined || lang === '' ? {} : { lang };
  return (await api.get<VersionDiff>(`${PROVISIONS}/${provisionId}/diff`, { params })).data;
}
