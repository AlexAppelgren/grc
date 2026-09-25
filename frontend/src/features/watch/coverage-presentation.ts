import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { checkStatusTone, slotTone, type CheckStatusKind } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';

import type { SourceCoverage } from './api';

// One row of the Coverage tab (WAT-01, design/screens/tenant-watch.html):
// what kind of place the source is, how the last check ended, whether it has
// gone stale, and whether it is checked automatically at all. The tone of the
// result comes from the check's own kind; the stale and paused markers come
// from their slots. None of them comes from a sentence in the response.

export const COVERAGE_SLOT_ORDER = {
  status: 10,
  stale: 20,
  kind: 30,
  paused: 40,
} as const;

const CHECK_STATUS_KEY = {
  ok: 'watch.coverage.status.ok',
  failed: 'watch.coverage.status.failed',
  never: 'watch.coverage.status.never',
} as const satisfies Record<CheckStatusKind, MessageKey>;

const CADENCE_KEY = {
  daily: 'watch.coverage.cadence.daily',
  weekly: 'watch.coverage.cadence.weekly',
  monthly: 'watch.coverage.cadence.monthly',
} as const satisfies Record<SourceCoverage['source']['checkFrequency'], MessageKey>;

export function presentSourceCoverage(row: SourceCoverage, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    {
      key: `status:${row.lastStatus}`,
      label: t(CHECK_STATUS_KEY[row.lastStatus]),
      tone: checkStatusTone[row.lastStatus],
      order: COVERAGE_SLOT_ORDER.status,
    },
    { key: `kind:${row.source.kind.key}`, label: row.source.kind.label, tone: slotTone.sourceKind, order: COVERAGE_SLOT_ORDER.kind },
  ];
  if (row.overdue) {
    pills.push({ key: 'stale', label: t('watch.coverage.stale'), tone: slotTone.stale, order: COVERAGE_SLOT_ORDER.stale });
  }
  // A source that is registered and deliberately left alone is not stale and
  // not failing; it is simply not swept (WAT-07, D-45).
  if (!row.source.active) {
    pills.push({ key: 'paused', label: t('watch.coverage.notAutomatic'), tone: slotTone.paused, order: COVERAGE_SLOT_ORDER.paused });
  }
  return pills.sort(byOrder);
}

/** The cadence promised and the last check that happened, in that order. */
export function coverageMeta(row: SourceCoverage, t: Translate, ctx: FormatContext): string[] {
  return [
    t(CADENCE_KEY[row.source.checkFrequency]),
    row.lastCheckedAt === null ? t('watch.coverage.neverChecked') : t('watch.coverage.lastChecked', { date: formatDateTime(row.lastCheckedAt, ctx) }),
  ];
}
