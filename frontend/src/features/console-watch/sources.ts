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
// here writes and no control calls a route this session could not pass. That
// rules out the card's jurisdiction filter and the issuing authority's name
// too: both come from `GET /authorities`, which is gated on `library.read`
// inside a tenant and refuses a console session (reported).

type Schemas = components['schemas'];

export type Source = Schemas['WatchSourceOut'];
export type SourceCoverage = Schemas['WatchSourceCoverage'];

const SOURCES = '/api/v1/sources';
const COVERAGE = '/api/v1/sources/coverage';

/** The registry, ordered by name and unpaged: one row per registered source. */
export async function listSources(): Promise<Source[]> {
  return (await api.get<Source[]>(SOURCES)).data;
}

/** The coverage log's bottom line: when each source was last swept, how it ended, whether it is stale. */
export async function getSourceCoverage(): Promise<SourceCoverage[]> {
  return (await api.get<SourceCoverage[]>(COVERAGE)).data;
}

export const consoleSourceKeys = {
  sources: ['console', 'sources'] as const,
  coverage: ['console', 'sources', 'coverage'] as const,
};

export function useSources(): UseQueryResult<Source[]> {
  return useQuery({ queryKey: consoleSourceKeys.sources, queryFn: listSources });
}

export function useSourceCoverage(): UseQueryResult<SourceCoverage[]> {
  return useQuery({ queryKey: consoleSourceKeys.coverage, queryFn: getSourceCoverage });
}

// ---------------------------------------------------------------------------
// One registry row: the source and its last check together
// ---------------------------------------------------------------------------

export interface RegistryRow {
  source: Source;
  /** Null while the coverage read has not answered, or where the source is not in it. */
  coverage: SourceCoverage | null;
}

export function registryRows(sources: readonly Source[], coverage: readonly SourceCoverage[]): RegistryRow[] {
  const byId = new Map(coverage.map((row) => [row.source.id, row]));
  return sources.map((source) => ({ source, coverage: byId.get(source.id) ?? null }));
}

export interface RegistryFilters {
  kind: string;
  failingOnly: boolean;
}

/**
 * `GET /sources` takes no filter and answers the whole registry unpaged, so
 * the filters the card draws are applied over the complete list. Nothing is
 * hidden that the server would have sent, and no page can disagree with its
 * own filters, because there is no page.
 */
export function applyFilters(rows: readonly RegistryRow[], filters: RegistryFilters): RegistryRow[] {
  return rows.filter((row) => {
    if (filters.kind !== '' && row.source.kind.key !== filters.kind) return false;
    if (filters.failingOnly && !(row.coverage?.lastStatus === 'failed' || row.coverage?.overdue === true)) return false;
    return true;
  });
}

/** The kinds the registry actually holds, so the filter never offers an empty result. */
export function filterOptions(rows: readonly RegistryRow[]): { kinds: { key: string; label: string }[] } {
  const kinds = new Map<string, string>();
  for (const row of rows) kinds.set(row.source.kind.key, row.source.kind.label);
  return { kinds: [...kinds].map(([key, label]) => ({ key, label })).sort((a, b) => a.label.localeCompare(b.label)) };
}

// ---------------------------------------------------------------------------
// Presentation
// ---------------------------------------------------------------------------

export const SOURCE_SLOT_ORDER = {
  status: 10,
  stale: 20,
  kind: 30,
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
  // A source registered and deliberately left alone is not stale and not
  // failing; it is simply not swept (WAT-07, D-45).
  if (!row.source.active) pills.push({ key: 'paused', label: t('console.sources.paused'), tone: slotTone.paused, order: SOURCE_SLOT_ORDER.paused });
  return pills.sort(byOrder);
}

/** The cadence promised, and how the last check went. */
export function sourceMeta(row: RegistryRow, t: Translate, ctx: FormatContext): string[] {
  const meta = [t(CADENCE_KEY[row.source.checkFrequency])];
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
