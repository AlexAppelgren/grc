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

const PRECISIONS: readonly DatePrecision[] = ['day', 'month', 'quarter', 'year'];

/** A legal date's precision as the server names it, `day` when it names none or one the client does not know. */
export function datePrecisionOf(value: string | null | undefined): DatePrecision {
  return PRECISIONS.find((precision) => precision === value) ?? 'day';
}

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

/**
 * A key read as words: `cases.signoff` is "cases signoff", `search:read` is
 * "search read", `tenant_role` is "tenant role". For a grant, a scope or a
 * list nobody has worded yet, never a role name.
 */
export function humaniseKey(key: string): string {
  return key.replace(/[._:-]/g, ' ');
}

/** The calendar day `now` falls on in `timeZone`, as YYYY-MM-DD: the bank's today, never the device's. */
export function tenantToday(timeZone: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone }).format(now);
}

// A partial date is a string plus its precision: "2026" / year,
// "2026-09" / month or quarter, "2026-09-12" / day. Precision beyond what the
// string carries is treated as what the string carries, and a precision the
// formatter has no rule for as the day the string carries.
export function formatPartialDate(
  value: string,
  sentPrecision: string | null | undefined,
  ctx: FormatContext = defaultFormatContext,
): string {
  const precision = datePrecisionOf(sentPrecision);
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
