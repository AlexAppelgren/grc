import { defaultLocale, localeTags, t, type Locale } from '@/shared/i18n';

// Every date on screen goes through these (playbook 6.6). Instants (ISO with
// a time) are shown in the tenant's timezone; plain dates (YYYY-MM-DD) are
// calendar days and never shift with a timezone.
export interface FormatContext {
  locale: Locale;
  timeZone: string;
}

export const defaultFormatContext: FormatContext = { locale: defaultLocale, timeZone: 'Europe/Stockholm' };

export type DatePrecision = 'day' | 'month' | 'quarter' | 'year';

const PLAIN_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const PARTIAL = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/;

function plainDate(value: string): Date | null {
  const m = PLAIN_DATE.exec(value);
  if (!m) return null;
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
}

function formatWith(date: Date, options: Intl.DateTimeFormatOptions, ctx: FormatContext): string {
  return new Intl.DateTimeFormat(localeTags[ctx.locale], options).format(date);
}

export function formatDate(value: string | Date, ctx: FormatContext = defaultFormatContext): string {
  const asPlain = typeof value === 'string' ? plainDate(value) : null;
  if (asPlain) {
    return formatWith(asPlain, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }, ctx);
  }
  const date = typeof value === 'string' ? new Date(value) : value;
  return formatWith(date, { day: 'numeric', month: 'short', year: 'numeric', timeZone: ctx.timeZone }, ctx);
}

export function formatDateTime(value: string | Date, ctx: FormatContext = defaultFormatContext): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  return formatWith(
    date,
    { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: ctx.timeZone },
    ctx,
  );
}

// "Friday 19 September 2026": the Today kicker (prototype `longDate`).
export function formatLongDate(value: string | Date, ctx: FormatContext = defaultFormatContext): string {
  const asPlain = typeof value === 'string' ? plainDate(value) : null;
  const options: Intl.DateTimeFormatOptions = { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' };
  if (asPlain) return formatWith(asPlain, { ...options, timeZone: 'UTC' }, ctx);
  const date = typeof value === 'string' ? new Date(value) : value;
  return formatWith(date, { ...options, timeZone: ctx.timeZone }, ctx);
}

// A partial date is a string plus its precision: "2026" / year,
// "2026-09" / month or quarter, "2026-09-12" / day. Precision beyond what the
// string carries is treated as what the string carries.
export function formatPartialDate(
  value: string,
  precision: DatePrecision,
  ctx: FormatContext = defaultFormatContext,
): string {
  const m = PARTIAL.exec(value);
  if (!m) return value;
  const year = Number(m[1]);
  const month = m[2] === undefined ? undefined : Number(m[2]);
  const day = m[3] === undefined ? undefined : Number(m[3]);

  if (precision === 'day' && month !== undefined && day !== undefined) {
    return formatDate(value, ctx);
  }
  if ((precision === 'day' || precision === 'month') && month !== undefined) {
    return formatWith(new Date(Date.UTC(year, month - 1, 1)), { month: 'long', year: 'numeric', timeZone: 'UTC' }, ctx);
  }
  if (precision === 'quarter' && month !== undefined) {
    return t('format.quarter', { quarter: Math.floor((month - 1) / 3) + 1, year }, ctx.locale);
  }
  return String(year);
}
