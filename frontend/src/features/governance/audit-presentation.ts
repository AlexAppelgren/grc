import type { PresentedPill } from '@/features/shared/presentation-types';
import { humaniseKey } from '@/features/tenant-admin/members-presentation';
import type { Translate } from '@/shared/i18n';

import type { AuditEvent, AuditSnapshot } from './types';

// Pills and derived facts for the audit log (AUD-01). The log is a ledger of
// machine facts, so nothing here invents a phrase: the record kind and the
// action are the row's own keys with their separators opened up, exactly as
// permissions and key scopes are shown, and the sentence a row carries is the
// server's `summary`. Tone comes from the slot: a record kind is a neutral
// fact (`information`); a completed passkey step-up is the strong end of the
// assurance scale the row records, so it is `positive`.

const ORDER = { subjectType: 0, steppedUp: 1 };

/**
 * The record kinds the filter offers, in reading order: what a tenant's log
 * can hold (its own rows) plus the library records a change by an agent, the
 * system or platform staff brings in. A kind the backend adds later still
 * appears in the rows; it joins this list when its screen lands.
 */
export const AUDIT_SUBJECT_TYPES: readonly string[] = [
  'api_key',
  'authority',
  'auth_challenge',
  'case',
  'change_case',
  'evidence',
  'footprint',
  'footprint_change_request',
  'instrument',
  'invitation',
  'membership',
  'obligation',
  'proposal',
  'provision',
  'step_up_assertion',
  'support_access',
  'taxonomy_term',
  'tenant',
  'tenant_role',
  'user',
  'user_session',
  'vocabulary',
  'vocabulary_suggestion',
  'watched_market',
  'webauthn_credential',
];

export function subjectTypeLabel(subjectType: string): string {
  return humaniseKey(subjectType);
}

export function actionLabel(action: string): string {
  return humaniseKey(action);
}

export function presentAuditEvent(event: Pick<AuditEvent, 'subjectType' | 'steppedUp'>, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `subject:${event.subjectType}`, label: subjectTypeLabel(event.subjectType), tone: 'information', order: ORDER.subjectType },
  ];
  if (event.steppedUp) {
    pills.push({ key: 'stepped-up', label: t('admin.auditLog.steppedUp'), tone: 'positive', order: ORDER.steppedUp });
  }
  return pills;
}

/** One changed field of a row: the value as the snapshot holds it, `null` where the field was absent. */
export interface DiffRow {
  field: string;
  before: string | null;
  after: string | null;
}

/** A snapshot value as data: a string as written, anything else as its JSON. The column holds JSON, so everything in it stringifies. */
export function snapshotValue(value: unknown): string | null {
  if (value === undefined) return null;
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

/** The fields that differ between the two snapshots, by field name. A field both sides agree on is not a change. */
export function diffRows(before: AuditSnapshot, after: AuditSnapshot): DiffRow[] {
  const fields = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
  return fields
    .map((field) => ({ field, before: snapshotValue(before[field]), after: snapshotValue(after[field]) }))
    .filter((row) => row.before !== row.after);
}

// The UTC instant that local midnight falls on in `timeZone`: Intl reads the
// zone's clock at a candidate instant, and the difference is the offset to
// undo. Without this a filter in a zone ahead of UTC would drop the first
// hours of the day it was asked for.
function startOfDay(day: string, timeZone: string): string {
  const utcMidnight = Date.parse(`${day}T00:00:00Z`);
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(utcMidnight));
  const at = (type: string) => Number(parts.find((part) => part.type === type)?.value);
  // An hour of 24 is how some engines write midnight under hour12: false.
  const shown = Date.UTC(at('year'), at('month') - 1, at('day'), at('hour') % 24, at('minute'), at('second'));
  return new Date(2 * utcMidnight - shown).toISOString();
}

function nextDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

/** A whole calendar day, as the date control writes one. Anything else is no bound at all. */
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/**
 * The two instants a pair of calendar days means to the API: `from` is the
 * start of the first day and `to`, being exclusive, the start of the day
 * after the last, so both days chosen are inside the range.
 */
export function dayRange(fromDay: string, toDay: string, timeZone: string): { from?: string; to?: string } {
  return {
    from: DAY.test(fromDay) ? startOfDay(fromDay, timeZone) : undefined,
    to: DAY.test(toDay) ? startOfDay(nextDay(toDay), timeZone) : undefined,
  };
}
