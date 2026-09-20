import type { KindRef, PartialDate } from '@/features/shared/presentation-types';
import type { ComplianceKind } from '@/features/shared/tone-by-kind';
import { api } from '@/shared/utils/api-client';
import type { DatePrecision } from '@/shared/utils/format';
import type { components } from '@/types/api.generated';

import type { LibraryRef, LocalizedText, Obligation, ObligationQuery, ObligationVersion, OutsideReason, Page, PageQuery, ScopeDimension } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). The library reads sit
// under /api/v1; nothing here writes, because proposals are the only door
// into the library. The server's shapes (openapi.json) are read through the
// normalisers below into the types the screen and its presentation functions
// use, so a difference in shape is absorbed here, once.

const OBLIGATIONS = '/api/v1/obligations';

type Schemas = components['schemas'];

const PRECISIONS: readonly DatePrecision[] = ['day', 'month', 'quarter', 'year'];
const COMPLIANCE_KINDS: readonly ComplianceKind[] = ['compliant', 'partly', 'gap', 'not_assessed'];

export function refOf(raw: Schemas['LibraryRef']): LibraryRef {
  return { key: raw.key, kind: raw.kind ?? null, label: raw.label };
}

function textOf(raw: Schemas['LocalizedText'] | null | undefined): LocalizedText | null {
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
  return { versionNumber: raw.versionNumber, effectiveFrom: partialDateOf(raw.effectiveFrom) };
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
    scope: (raw.scope ?? []).map(scopeOf),
    version: versionOf(raw.version),
    upcomingVersion: versionOf(raw.upcomingVersion),
    inFootprint: raw.inFootprint,
    outsideReason: (raw.outsideReason ?? []).map(reasonOf),
    lastVerifiedAt: raw.lastVerifiedAt,
    openChangeCount: raw.openChangeCount,
    pendingApplicability: raw.pendingApplicability,
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
