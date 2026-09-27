import type { KindRef, PartialDate } from '@/features/shared/presentation-types';
import type { ComplianceKind } from '@/features/shared/tone-by-kind';
import { api } from '@/shared/utils/api-client';
import type { DatePrecision } from '@/shared/utils/format';
import type { components } from '@/types/api.generated';

import type {
  AgentRef,
  DiffSegment,
  Instrument,
  InstrumentAuthorityRef,
  InstrumentDetail,
  InstrumentLineageRef,
  InstrumentQuery,
  InstrumentSummary,
  LibraryRef,
  LocalizedText,
  Obligation,
  ObligationDetail,
  ObligationProvenance,
  ObligationQuery,
  ObligationVersion,
  ObligationVersionRow,
  OutsideReason,
  Page,
  PageQuery,
  ProblemReportBody,
  ProblemReportCreated,
  ProvisionCitedObligation,
  ProvisionNode,
  ProvisionVersionRow,
  RelatedObligation,
  ScopeDimension,
  VersionDiff,
} from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). The library reads sit
// under /api/v1; nothing here writes the library, because proposals are the
// only door into it: the one write besides a problem report is the bank's own
// tags, which live in its own zone. The server's shapes (openapi.json) are
// read through the normalisers below into the types the screen and its presentation functions
// use, so a difference in shape is absorbed here, once.

const OBLIGATIONS = '/api/v1/obligations';
const INSTRUMENTS = '/api/v1/instruments';

type Schemas = components['schemas'];

const PRECISIONS: readonly DatePrecision[] = ['day', 'month', 'quarter', 'year'];
const COMPLIANCE_KINDS: readonly ComplianceKind[] = ['compliant', 'partly', 'gap', 'not_assessed'];

export function refOf(raw: Schemas['LibraryRef']): LibraryRef {
  return { key: raw.key, kind: raw.kind ?? null, label: raw.label };
}

/** One of the bank's own tags: the same shape as a library reference, with no kind of its own. */
function tenantTagOf(raw: Schemas['TaggingTagRef']): LibraryRef {
  return { key: raw.key, kind: raw.kind ?? null, label: raw.label };
}

export function textOf(raw: Schemas['LocalizedText'] | null | undefined): LocalizedText | null {
  if (raw === null || raw === undefined) return null;
  return { text: raw.text, language: raw.language, isOriginal: raw.isOriginal, isMachine: raw.isMachine };
}

/** A legal date with its precision; a precision the formatter has no rule for is read as the day the string carries. */
export function partialDateOf(raw: Schemas['PartialDate'] | null | undefined): PartialDate | null {
  if (raw === null || raw === undefined) return null;
  const precision = (PRECISIONS as readonly string[]).includes(raw.precision) ? (raw.precision as DatePrecision) : 'day';
  return { date: raw.date, precision };
}

export function versionOf(raw: Schemas['ObligationVersionRef'] | null | undefined): ObligationVersion | null {
  if (raw === null || raw === undefined) return null;
  return {
    versionNumber: raw.versionNumber,
    effectiveFrom: partialDateOf(raw.effectiveFrom),
    approvedAt: raw.approvedAt,
    verifiedOrigin: raw.verifiedOrigin,
    confirmedByAgent: agentOf(raw.confirmedByAgent),
    proposedByAgent: agentOf(raw.proposedByAgent),
  };
}

/**
 * A compliance status becomes a pill only when its kind is one of the four
 * the tone map knows: a tone is chosen by kind, never by a person, so a kind
 * nobody has a tone for is not rendered at all (the register fills this in
 * from chunk 8).
 */
export function complianceOf(raw: Schemas['LibraryRef'] | null | undefined): KindRef<ComplianceKind> | null {
  if (raw === null || raw === undefined) return null;
  const kind = raw.kind ?? '';
  if (!(COMPLIANCE_KINDS as readonly string[]).includes(kind)) return null;
  return { key: raw.key, label: raw.label, kind: kind as ComplianceKind };
}

function scopeOf(raw: Schemas['ScopeDimension']): ScopeDimension {
  return { dimension: refOf(raw.dimension), terms: (raw.terms ?? []).map(refOf), allSelected: raw.allSelected };
}

function reasonOf(raw: Schemas['OutsideReason']): OutsideReason {
  return { dimension: refOf(raw.dimension), terms: (raw.terms ?? []).map(refOf) };
}

export function obligationOf(raw: Schemas['ObligationRow']): Obligation {
  return {
    id: raw.id,
    stableKey: raw.stableKey,
    refLabel: raw.refLabel,
    title: textOf(raw.title),
    instrument: { key: raw.instrument.key, shortName: raw.instrument.shortName },
    bindingLevel: refOf(raw.bindingLevel),
    binding: raw.binding,
    dutyType: refOf(raw.dutyType),
    tags: (raw.tags ?? []).map(refOf),
    tenantTags: (raw.tenantTags ?? []).map(tenantTagOf),
    privateToUs: raw.privateToUs,
    scope: (raw.scope ?? []).map(scopeOf),
    version: versionOf(raw.version),
    upcomingVersion: versionOf(raw.upcomingVersion),
    jurisdiction: refOf(raw.jurisdiction),
    inFootprint: raw.inFootprint,
    outsideReason: (raw.outsideReason ?? []).map(reasonOf),
    lastVerifiedAt: raw.lastVerifiedAt,
    verifiedBy: raw.verifiedBy === null || raw.verifiedBy === undefined ? null : { id: raw.verifiedBy.id, name: raw.verifiedBy.name },
    openChangeCount: raw.openChangeCount,
    complianceStatus: complianceOf(raw.complianceStatus),
  };
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
  const data = (await api.get<Schemas['ObligationPage']>(OBLIGATIONS, { params: query, paramsSerializer: { serialize: serializeQuery } })).data;
  return { items: data.items.map(obligationOf), total: data.total };
}

function agentOf(raw: Schemas['AgentRef'] | null | undefined): AgentRef | null {
  return raw === null || raw === undefined ? null : { id: raw.id, key: raw.key };
}

function versionRowOf(raw: Schemas['ObligationVersionRow']): ObligationVersionRow {
  return {
    versionNumber: raw.versionNumber,
    effectiveFrom: partialDateOf(raw.effectiveFrom),
    effectiveTo: partialDateOf(raw.effectiveTo),
    approvedAt: raw.approvedAt,
    verifiedOrigin: raw.verifiedOrigin,
    confirmedByAgent: agentOf(raw.confirmedByAgent),
    proposedByAgent: agentOf(raw.proposedByAgent),
  };
}

function instrumentSummaryOf(raw: Schemas['ObligationInstrumentSummary']): InstrumentSummary {
  return { key: raw.key, shortName: raw.shortName, officialRef: raw.officialRef, name: textOf(raw.name), implementsNote: raw.implementsNote };
}

function provenanceOf(raw: Schemas['ObligationProvenance']): ObligationProvenance {
  return {
    sourceUrl: raw.sourceUrl,
    sourceLabel: raw.sourceLabel,
    lastVerifiedAt: raw.lastVerifiedAt,
    verifiedBy: raw.verifiedBy === null || raw.verifiedBy === undefined ? null : { id: raw.verifiedBy.id, name: raw.verifiedBy.name },
    createdAt: raw.createdAt,
    createdOrigin: raw.createdOrigin,
    createdModel: raw.createdModel,
    verifiedOrigin: raw.verifiedOrigin,
    confirmedByAgent: agentOf(raw.confirmedByAgent),
    proposedByAgent: agentOf(raw.proposedByAgent),
  };
}

function relatedOf(raw: Schemas['RelatedObligation']): RelatedObligation {
  return {
    id: raw.id,
    title: textOf(raw.title),
    instrument: { key: raw.instrument.key, shortName: raw.instrument.shortName },
    relation: refOf(raw.relation),
    binding: raw.binding,
  };
}

export function detailOf(raw: Schemas['ObligationDetail']): ObligationDetail {
  return {
    id: raw.id,
    stableKey: raw.stableKey,
    refLabel: raw.refLabel,
    title: textOf(raw.title),
    instrument: instrumentSummaryOf(raw.instrument),
    regime: refOf(raw.regime),
    bindingLevel: refOf(raw.bindingLevel),
    binding: raw.binding,
    dutyType: refOf(raw.dutyType),
    productScope: raw.productScope,
    triggerFrequency: raw.triggerFrequency,
    retention: raw.retention,
    sanctionExposure: raw.sanctionExposure,
    tags: (raw.tags ?? []).map(refOf),
    tenantTags: (raw.tenantTags ?? []).map(tenantTagOf),
    privateToUs: raw.privateToUs,
    scope: (raw.scope ?? []).map(scopeOf),
    inFootprint: raw.inFootprint,
    outsideReason: (raw.outsideReason ?? []).map(reasonOf),
    summary: textOf(raw.summary),
    translations: (raw.translations ?? []).map(textOf).filter((text): text is LocalizedText => text !== null),
    version: raw.version === null || raw.version === undefined ? null : versionRowOf(raw.version),
    versions: (raw.versions ?? []).map(versionRowOf),
    related: (raw.related ?? []).map(relatedOf),
    provenance: provenanceOf(raw.provenance),
  };
}

// A sentence the server marks with an operation the screen has no colour for
// is shown as it stands: a diff a reader cannot read is worse than one
// sentence rendered plain.
const DIFF_OPS: readonly DiffSegment['op'][] = ['equal', 'insert', 'delete'];

export function segmentOf(raw: Schemas['DiffSegment']): DiffSegment {
  const op = (DIFF_OPS as readonly string[]).includes(raw.op) ? (raw.op as DiffSegment['op']) : 'equal';
  return { op, text: raw.text };
}

export function diffOf(raw: Schemas['VersionDiff']): VersionDiff {
  return {
    fromVersion: raw.fromVersion,
    toVersion: raw.toVersion,
    fromEffective: partialDateOf(raw.fromEffective),
    toEffective: partialDateOf(raw.toEffective),
    language: raw.language,
    isMachine: raw.isMachine,
    segments: (raw.segments ?? []).map(segmentOf),
  };
}

/** One duty as it stood on `asOf`, which defaults to today in the bank's own time zone. */
export async function getObligation(obligationId: string, asOf?: string): Promise<ObligationDetail> {
  const params = asOf === undefined || asOf === '' ? {} : { asOf };
  return detailOf((await api.get<Schemas['ObligationDetail']>(`${OBLIGATIONS}/${obligationId}`, { params })).data);
}

/** What changed between the latest version and the one before it, in the language on screen where both hold it. */
export async function getObligationDiff(obligationId: string, lang?: string): Promise<VersionDiff> {
  const params = lang === undefined || lang === '' ? {} : { lang };
  return diffOf((await api.get<Schemas['VersionDiff']>(`${OBLIGATIONS}/${obligationId}/diff`, { params })).data);
}

/**
 * "This looks wrong": the reader's own words about a library record. The body
 * stays inside the bank that filed it, so nothing here logs it and nothing
 * sends it anywhere else.
 */
export async function reportObligationProblem(obligationId: string, body: ProblemReportBody): Promise<ProblemReportCreated> {
  const data = (await api.post<Schemas['ProblemReportCreated']>(`${OBLIGATIONS}/${obligationId}/problem-reports`, body)).data;
  return { id: data.id, status: data.status, createdAt: data.createdAt };
}

// The bank's own tags on an obligation (VOC-08): markers in the bank's zone, never a
// library write. Each call answers the obligation's tags as they now stand.

const TAGGINGS = '/api/v1/taggings';

export async function tagObligation(obligationId: string, tagKey: string): Promise<LibraryRef[]> {
  const body: Schemas['TaggingBody'] = { tagKey, subjectType: 'obligation', subjectId: obligationId };
  return (await api.post<Schemas['TaggingRecordTags']>(TAGGINGS, body)).data.tags.map(tenantTagOf);
}

export async function untagObligation(obligationId: string, tagKey: string): Promise<LibraryRef[]> {
  const body: Schemas['TaggingBody'] = { tagKey, subjectType: 'obligation', subjectId: obligationId };
  return (await api.post<Schemas['TaggingRecordTags']>(`${TAGGINGS}/remove`, body)).data.tags.map(tenantTagOf);
}

/** Records and how many, as the server counted them; a screen shows the count, never recounts the ids. */
export interface TaggingIds {
  count: number;
  ids: string[];
}

/**
 * What tagging a selection would do (the preview) or did (the commit), in one shape.
 * Records the reader may not read are only counted: the server never names them.
 */
export interface TaggingBatch {
  tag: LibraryRef;
  gained: TaggingIds;
  alreadyTagged: TaggingIds;
  skipped: number;
}

function batchOf(raw: Schemas['TaggingBatchOutcome']): TaggingBatch {
  return {
    tag: tenantTagOf(raw.tag),
    gained: { count: raw.gained.count, ids: raw.gained.ids },
    alreadyTagged: { count: raw.alreadyTagged.count, ids: raw.alreadyTagged.ids },
    skipped: raw.skipped.count,
  };
}

/** VOC-08: what one tag on many obligations would do. A read with a body: nothing is written. */
export async function previewObligationTagging(tagKey: string, obligationIds: readonly string[]): Promise<TaggingBatch> {
  const body: Schemas['TaggingBatchBody'] = { tagKey, subjectType: 'obligation', subjectIds: [...obligationIds] };
  return batchOf((await api.post<Schemas['TaggingBatchOutcome']>(`${TAGGINGS}/preview`, body)).data);
}

/** VOC-08: one tag on many obligations in one transaction, audited once by the server. */
export async function tagObligations(tagKey: string, obligationIds: readonly string[]): Promise<TaggingBatch> {
  const body: Schemas['TaggingBatchBody'] = { tagKey, subjectType: 'obligation', subjectIds: [...obligationIds] };
  return batchOf((await api.post<Schemas['TaggingBatchOutcome']>(`${TAGGINGS}/batch`, body)).data);
}

// Instruments (INV-01, INV-06): the Instruments tab, the instrument filter and the
// instrument card. Reads only, like every obligation read above; "This looks wrong" is
// the one write, and it stays inside the reader's own bank.

function authorityRefOf(raw: Schemas['InstrumentAuthorityRef'] | null | undefined): InstrumentAuthorityRef | null {
  if (raw === null || raw === undefined) return null;
  return { key: raw.key, name: raw.name, shortName: raw.shortName, url: raw.url };
}

export function instrumentOf(raw: Schemas['InstrumentRow']): Instrument {
  return {
    id: raw.id,
    stableKey: raw.stableKey,
    shortName: raw.shortName,
    name: textOf(raw.name),
    level: refOf(raw.level),
    binding: raw.binding,
    jurisdiction: refOf(raw.jurisdiction),
    authority: authorityRefOf(raw.authority),
    regime: refOf(raw.regime),
    officialRef: raw.officialRef,
    inForceFrom: partialDateOf(raw.inForceFrom),
    inForceTo: partialDateOf(raw.inForceTo),
    implementsNote: raw.implementsNote,
    obligationCount: raw.obligationCount,
    inFootprint: raw.inFootprint,
    privateToUs: raw.privateToUs,
    lastVerifiedAt: raw.lastVerifiedAt,
    sourceUrl: raw.sourceUrl,
  };
}

export async function listInstruments(query: InstrumentQuery & PageQuery = {}): Promise<Page<Instrument>> {
  const data = (await api.get<Schemas['InstrumentPage']>(INSTRUMENTS, { params: query })).data;
  return { items: data.items.map(instrumentOf), total: data.total };
}

function lineageOf(raw: Schemas['InstrumentLineageRef']): InstrumentLineageRef {
  return {
    relation: refOf(raw.relation),
    direction: raw.direction === 'outgoing' ? 'outgoing' : 'incoming',
    instrument: { key: raw.instrument.key, shortName: raw.instrument.shortName },
    note: raw.note,
    toRef: raw.toRef,
  };
}

export function instrumentDetailOf(raw: Schemas['InstrumentDetail']): InstrumentDetail {
  return {
    id: raw.id,
    stableKey: raw.stableKey,
    shortName: raw.shortName,
    name: textOf(raw.name),
    level: refOf(raw.level),
    binding: raw.binding,
    jurisdiction: refOf(raw.jurisdiction),
    authority: authorityRefOf(raw.authority),
    regime: refOf(raw.regime),
    officialRef: raw.officialRef,
    eliUri: raw.eliUri,
    inForceFrom: partialDateOf(raw.inForceFrom),
    inForceTo: partialDateOf(raw.inForceTo),
    implementsNote: raw.implementsNote,
    sourceUrl: raw.sourceUrl,
    lastVerifiedAt: raw.lastVerifiedAt,
    verifiedBy: raw.verifiedBy === null || raw.verifiedBy === undefined ? null : { id: raw.verifiedBy.id, name: raw.verifiedBy.name },
    privateToUs: raw.privateToUs,
    lineage: (raw.lineage ?? []).map(lineageOf),
  };
}

export async function getInstrument(instrumentId: string): Promise<InstrumentDetail> {
  return instrumentDetailOf((await api.get<Schemas['InstrumentDetail']>(`${INSTRUMENTS}/${instrumentId}`)).data);
}

/** "This looks wrong" on an instrument card; a provision is reported through the instrument whose card shows it. */
export async function reportInstrumentProblem(instrumentId: string, body: ProblemReportBody): Promise<ProblemReportCreated> {
  const data = (await api.post<Schemas['ProblemReportCreated']>(`${INSTRUMENTS}/${instrumentId}/problem-reports`, body)).data;
  return { id: data.id, status: data.status, createdAt: data.createdAt };
}

// The provision tree (INV-02, INV-04, INV-05): every text version a provision has ever
// carried, so the tree chooses one by its own chip rather than trusting today's date, and
// the diff between any two of them.

function provisionVersionRowOf(raw: Schemas['ProvisionVersionRow']): ProvisionVersionRow {
  return {
    versionNumber: raw.versionNumber,
    effectiveFrom: partialDateOf(raw.effectiveFrom),
    effectiveTo: partialDateOf(raw.effectiveTo),
    transitionalNote: raw.transitionalNote,
    text: textOf(raw.text),
  };
}

function citedObligationOf(raw: Schemas['ProvisionCitedObligation']): ProvisionCitedObligation {
  return { id: raw.id, title: textOf(raw.title), refLabel: raw.refLabel };
}

export function provisionNodeOf(raw: Schemas['ProvisionNode']): ProvisionNode {
  return {
    id: raw.id,
    stableKey: raw.stableKey,
    kind: refOf(raw.kind),
    refLabel: raw.refLabel,
    heading: raw.heading,
    path: raw.path,
    children: (raw.children ?? []).map(provisionNodeOf),
    versions: (raw.versions ?? []).map(provisionVersionRowOf),
    inForceVersion: raw.inForceVersion,
    obligations: (raw.obligations ?? []).map(citedObligationOf),
  };
}

/** The whole provision tree of one instrument, as of a date (default today where the tenant is). */
export async function listInstrumentProvisions(instrumentId: string, asOf?: string): Promise<ProvisionNode[]> {
  const params = asOf === undefined || asOf === '' ? {} : { asOf };
  const data = (await api.get<Schemas['ProvisionNode'][]>(`${INSTRUMENTS}/${instrumentId}/provisions`, { params })).data;
  return data.map(provisionNodeOf);
}

const PROVISIONS = '/api/v1/provisions';

/** What changed between two versions of one provision's verbatim text, in the language on screen where both hold it. */
export async function getProvisionDiff(provisionId: string, lang?: string): Promise<VersionDiff> {
  const params = lang === undefined || lang === '' ? {} : { lang };
  return diffOf((await api.get<Schemas['VersionDiff']>(`${PROVISIONS}/${provisionId}/diff`, { params })).data);
}
