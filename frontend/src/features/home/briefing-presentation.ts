import type { Translate } from '@/shared/i18n';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// The briefing's week kicker (design/screens/tenant-briefing.html): "Week
// 38, 14 Sep to 20 Sep 2026". The ISO week number is computed from the
// Monday `weekStart` names, the same rule `briefing.week_start` follows
// server-side (Monday to Sunday); the screen never receives a week number
// from the API and never guesses one from the reader's own clock.

/** ISO 8601 week number (1-53) of a UTC-anchored plain date. */
export function isoWeekNumber(date: Date): number {
  const thursday = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const isoDay = thursday.getUTCDay() || 7; // Monday=1 .. Sunday=7
  thursday.setUTCDate(thursday.getUTCDate() + 4 - isoDay);
  const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
  return Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
}

function parsePlainDate(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1));
}

export function weekKicker(weekStart: string, weekEnd: string, t: Translate, ctx: FormatContext): string {
  const week = isoWeekNumber(parsePlainDate(weekStart));
  return t('briefing.weekKicker', { week, from: formatDate(weekStart, ctx), to: formatDate(weekEnd, ctx) });
}
