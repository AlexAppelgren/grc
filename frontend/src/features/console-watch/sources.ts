'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { checkStatusTone, slotTone, type CheckStatusKind } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { api } from '@/shared/utils/api-client';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';
import type { components } from '@/types/api.generated';

// The console's Sources page (WAT-01, ADM-02, ruling 3): the registry of
// places the agents watch, and how the last check of each one went. Read-only
// throughout — registering and editing a source is `sources.manage` work that
// is not on this page in R1, and "check a source now" is chunk 11 — so nothing
// here writes and no control calls a route this session could not pass.

type Schemas = components['schemas'];

export type Source = Schemas['WatchSourceOut'];
export type SourceCoverage = Schemas['WatchSourceCoverage'];
export type Authority = Schemas['LibraryAuthority'];

const SOURCES = '/api/v1/sources';
const COVERAGE = '/api/v1/sources/coverage';
const AUTHORITIES = '/api/v1/authorities';

/** The registry, ordered by name and unpaged: one row per registered source. */
export async function listSources(): Promise<Source[]> {
  return (await api.get<Source[]>(SOURCES)).data;
}

/** The coverage log's bottom line: when each source was last swept, how it ended, whether it is stale. */
export async function getSourceCoverage(): Promise<SourceCoverage[]> {
  return (await api.get<SourceCoverage[]>(COVERAGE)).data;
}

export async function listAuthorities(): Promise<Authority[]> {
  return (await api.get<Authority[]>(AUTHORITIES)).data;
}

export const consoleSourceKeys = {
  sources: ['console', 'sources'] as const,
  coverage: ['console', 'sources', 'coverage'] as const,
  authorities: ['console', 'authorities'] as const,
};

export function useSources(): UseQueryResult<Source[]> {
  return useQuery({ queryKey: consoleSourceKeys.sources, queryFn: listSources });
}

export function useSourceCoverage(): UseQueryResult<SourceCoverage[]> {
  return useQuery({ queryKey: consoleSourceKeys.coverage, queryFn: getSourceCoverage });
}

export function useAuthorities(): UseQueryResult<Authority[]> {
  return useQuery({ queryKey: consoleSourceKeys.authorities, queryFn: listAuthorities });
}

// ---------------------------------------------------------------------------
// One registry row: the source, its authority and its last check together
// ---------------------------------------------------------------------------

export interface RegistryRow {
  source: Source;
  /** Null while the coverage read has not answered, or where the source is not in it. */
  coverage: SourceCoverage | null;
  /** Null when the library does not know who issues what this source publishes. */
  authority: Authority | null;
}

export function registryRows(sources: readonly Source[], coverage: readonly SourceCoverage[], authorities: readonly Authority[]): RegistryRow[] {
  const byId = new Map(coverage.map((row) => [row.source.id, row]));
  const issuers = new Map(authorities.map((row) => [row.id, row]));
  return sources.map((source) => ({
    source,
    coverage: byId.get(source.id) ?? null,
    authority: source.authorityId === null ? null : (issuers.get(source.authorityId) ?? null),
  }));
}

export interface RegistryFilters {
  jurisdiction: string;
  kind: string;
  failingOnly: boolean;
}

/**
 * `GET /sources` takes no filter and answers the whole registry unpaged, so the
 * three the card draws are applied over the complete list. Nothing is hidden
 * that the server would have sent, and no page can disagree with its own
 * filters, because there is no page.
 */
export function applyFilters(rows: readonly RegistryRow[], filters: RegistryFilters): RegistryRow[] {
  return rows.filter((row) => {
    if (filters.jurisdiction !== '' && row.authority?.jurisdiction.key !== filters.jurisdiction) return false;
    if (filters.kind !== '' && row.source.kind.key !== filters.kind) return false;
    if (filters.failingOnly && !(row.coverage?.lastStatus === 'failed' || row.coverage?.overdue === true)) return false;
    return true;
  });
}

/** The jurisdictions and kinds the registry actually holds, so a filter never offers an empty result. */
export function filterOptions(rows: readonly RegistryRow[]): { jurisdictions: { key: string; label: string }[]; kinds: { key: string; label: string }[] } {
  const jurisdictions = new Map<string, string>();
  const kinds = new Map<string, string>();
  for (const row of rows) {
    if (row.authority !== null) jurisdictions.set(row.authority.jurisdiction.key, row.authority.jurisdiction.label);
    kinds.set(row.source.kind.key, row.source.kind.label);
  }
  const sorted = (map: Map<string, string>) => [...map].map(([key, label]) => ({ key, label })).sort((a, b) => a.label.localeCompare(b.label));
  return { jurisdictions: sorted(jurisdictions), kinds: sorted(kinds) };
}

// ---------------------------------------------------------------------------
// Presentation
// ---------------------------------------------------------------------------

export const SOURCE_SLOT_ORDER = {
  status: 10,
  stale: 20,
  kind: 30,
  jurisdiction: 40,
  paused: 50,
} as const;

const CHECK_STATUS_KEY = {
  ok: 'console.sources.check.ok',
  failed: 'console.sources.check.failed',
  never: 'console.sources.check.never',
} as const satisfies Record<CheckStatusKind, MessageKey>;

const CADENCE_KEY = {
  daily: 'console.sources.cadence.daily',
  weekly: 'console.sources.cadence.weekly',
  monthly: 'console.sources.cadence.monthly',
} as const satisfies Record<Source['checkFrequency'], MessageKey>;

export function presentSource(row: RegistryRow, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `kind:${row.source.kind.key}`, label: row.source.kind.label, tone: slotTone.sourceKind, order: SOURCE_SLOT_ORDER.kind },
  ];
  if (row.coverage !== null) {
    const status = row.coverage.lastStatus as CheckStatusKind;
    pills.push({ key: `status:${status}`, label: t(CHECK_STATUS_KEY[status]), tone: checkStatusTone[status], order: SOURCE_SLOT_ORDER.status });
    // Past its cadence, or failing more times in a row than the stale rule
    // allows: it needs attention, it is not itself bad.
    if (row.coverage.overdue) pills.push({ key: 'stale', label: t('console.sources.stale'), tone: slotTone.stale, order: SOURCE_SLOT_ORDER.stale });
  }
  if (row.authority !== null) {
    pills.push({ key: `jurisdiction:${row.authority.jurisdiction.key}`, label: row.authority.jurisdiction.label, tone: slotTone.jurisdiction, order: SOURCE_SLOT_ORDER.jurisdiction });
  }
  // A source registered and deliberately left alone is not stale and not
  // failing; it is simply not swept (WAT-07, D-45).
  if (!row.source.active) pills.push({ key: 'paused', label: t('console.sources.paused'), tone: slotTone.paused, order: SOURCE_SLOT_ORDER.paused });
  return pills.sort(byOrder);
}

/** The cadence promised, who issues it, and how the last check went. */
export function sourceMeta(row: RegistryRow, t: Translate, ctx: FormatContext): string[] {
  const meta = [t(CADENCE_KEY[row.source.checkFrequency])];
  if (row.authority !== null) meta.push(row.authority.name);
  if (row.coverage === null || row.coverage.lastCheckedAt === null) {
    meta.push(t('console.sources.neverChecked'));
  } else {
    const date = formatDateTime(row.coverage.lastCheckedAt, ctx);
    meta.push(row.coverage.lastStatus === 'failed' ? t('console.sources.lastFailed', { date }) : t('console.sources.lastChecked', { date }));
  }
  return meta;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** The two numbers the coverage read can answer: how much of the registry is fresh, and how much is not. */
export function coverageSummary(rows: readonly RegistryRow[], now: Date): { checked: number; total: number; failing: number } {
  const withCoverage = rows.filter((row) => row.coverage !== null);
  return {
    total: rows.length,
    checked: withCoverage.filter((row) => row.coverage!.lastCheckedAt !== null && now.getTime() - Date.parse(row.coverage!.lastCheckedAt) < DAY_MS).length,
    failing: withCoverage.filter((row) => row.coverage!.lastStatus === 'failed' || row.coverage!.overdue).length,
  };
}
